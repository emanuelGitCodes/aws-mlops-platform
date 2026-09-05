"""Drift Lambda: the window it reads, the two window rules, and the event."""

import datetime
import io
import json
import os
from unittest import mock

import pytest
from botocore.exceptions import ClientError as BotoClientError

from src.common import drift
from src.common.drift import BASELINE_RUN_PREFIX, BASELINE_URI_METADATA_KEY
from tests.unit.conftest import VALID, import_with_stubbed_boto3, varied_records

os.environ.setdefault("ARTIFACTS_BUCKET", "test-artifacts")
os.environ.setdefault("BASELINE_KEY", "monitor/baseline/baseline.json")
os.environ.setdefault("CAPTURE_PREFIX", "capture")

drift_handler = import_with_stubbed_boto3("src.monitoring.drift_handler")
BASELINE_RUN_KEY = f"{BASELINE_RUN_PREFIX}/execution-1/baseline.json"
BASELINE_URI = f"s3://test-artifacts/{BASELINE_RUN_KEY}"
MODEL_PACKAGE_ARN = "arn:aws:sagemaker:us-east-1:123456789012:model-package/group/1"
MODEL_NAME = "test-endpoint-model-1"
ENDPOINT_CONFIG_NAME = "test-endpoint-config-1"

# Build baseline and stable windows from varied feature records.
BASELINE = drift.build_baseline(varied_records(600, seed=1))
STABLE = varied_records(200, seed=2)
SHIFTED = varied_records(
    200,
    seed=3,
    tenure=180,
    MonthlyCharges=400.0,
    TotalCharges=60000.0,
    Contract="Two year",
    InternetService="DSL",
    PaymentMethod="Mailed check",
)
# The shape a health check produces: plenty of records, one distinct value.
UNIFORM = [dict(VALID) for _ in range(200)]


def body(payload):
    """Stand in for the streaming body an S3 GetObject returns."""
    return {"Body": io.BytesIO(json.dumps(payload).encode())}


def stub_serving(sm, baseline_uri=BASELINE_URI):
    """Serve one stable endpoint and its model package metadata."""
    sm.describe_endpoint.return_value = {
        "EndpointStatus": "InService",
        "EndpointConfigName": ENDPOINT_CONFIG_NAME,
    }
    sm.describe_endpoint_config.return_value = {"ProductionVariants": [{"ModelName": MODEL_NAME}]}
    sm.describe_model.return_value = {
        "Containers": [{"Mode": "SingleModel", "ModelPackageName": MODEL_PACKAGE_ARN}]
    }
    sm.describe_model_package.return_value = {
        "CustomerMetadataProperties": {BASELINE_URI_METADATA_KEY: baseline_uri}
    }


@pytest.fixture
def aws():
    """Stub S3, SageMaker, and EventBridge clients."""
    with (
        mock.patch.object(drift_handler, "s3") as s3,
        mock.patch.object(drift_handler, "events") as events,
        mock.patch.object(drift_handler, "sm") as sm,
    ):
        stub_serving(sm)
        yield s3, events


def stub_capture(s3, records, baseline=BASELINE, baseline_uri=BASELINE_URI):
    """Serve `records` from the listing, and `baseline` from its own key."""
    drift_handler.sm.describe_model_package.return_value = {
        "CustomerMetadataProperties": {BASELINE_URI_METADATA_KEY: baseline_uri}
    }
    keys = [f"capture/2026/08/07/10/{index}.json" for index in range(len(records))]
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": key} for key in keys]}
    ]
    by_key = {key: body({"record": record}) for key, record in zip(keys, records, strict=True)}
    by_key[BASELINE_RUN_KEY] = body(baseline)
    by_key[drift_handler.BASELINE_KEY] = body(baseline)
    s3.get_object.side_effect = lambda Bucket, Key: by_key[Key]


def test_window_prefixes_cover_the_hours_before_now():
    now = datetime.datetime(2026, 8, 7, 10, 30, tzinfo=datetime.UTC)
    assert drift_handler.window_prefixes(now, 1) == ["capture/2026/08/07/09/"]
    assert drift_handler.window_prefixes(now, 3) == [
        "capture/2026/08/07/09/",
        "capture/2026/08/07/08/",
        "capture/2026/08/07/07/",
    ]


def test_the_window_never_includes_the_current_hour():
    # Exclude the incomplete current hour from the scoring window.
    now = datetime.datetime(2026, 8, 7, 10, 30, tzinfo=datetime.UTC)
    assert "capture/2026/08/07/10/" not in drift_handler.window_prefixes(now, 5)


def test_window_prefixes_roll_back_over_midnight():
    now = datetime.datetime(2026, 8, 7, 0, 5, tzinfo=datetime.UTC)
    assert drift_handler.window_prefixes(now, 1) == ["capture/2026/08/06/23/"]


def test_a_small_window_is_skipped_rather_than_scored(aws):
    s3, events = aws
    stub_capture(s3, varied_records(3, seed=4))

    result = drift_handler.handler({}, None)

    # Too few records is its own outcome. It must not read as "no drift".
    assert result["skipped"] == "insufficient_records"
    assert result["records"] == 3
    assert "drifted" not in result
    events.put_events.assert_not_called()


def test_an_empty_window_is_skipped(aws):
    s3, events = aws
    s3.get_paginator.return_value.paginate.return_value = [{}]

    result = drift_handler.handler({}, None)

    assert result["skipped"] == "insufficient_records"
    assert result["records"] == 0
    events.put_events.assert_not_called()


def test_baseline_missing_raises_and_logs_bucket_key(aws):
    s3, _ = aws
    by_key = {}

    def read_object(Bucket: str, Key: str):
        if Key == drift_handler.BASELINE_KEY:
            raise BotoClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing baseline"}},
                "GetObject",
            )
        return by_key[Key]

    s3.get_object.side_effect = read_object

    with mock.patch.object(drift_handler, "log_event") as log_event:
        with pytest.raises(BotoClientError):
            drift_handler.read_baseline(drift_handler.BASELINE_KEY)
    log_event.assert_called_once_with(
        "drift_baseline_missing",
        bucket=drift_handler.ARTIFACTS_BUCKET,
        key=drift_handler.BASELINE_KEY,
    )


def test_invalid_baseline_shape_aborts_drift_scoring(aws):
    s3, _ = aws
    baseline_key = drift_handler.BASELINE_KEY
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "capture/2026/08/07/09/0.json"}]}
    ]
    by_key = {
        "capture/2026/08/07/09/0.json": body({"record": VALID}),
        baseline_key: body({}),
    }
    s3.get_object.side_effect = lambda Bucket, Key: by_key[Key]

    with pytest.raises(
        ValueError,
        match=(
            f"Baseline object s3://{drift_handler.ARTIFACTS_BUCKET}/{drift_handler.BASELINE_KEY}.*counts"
        ),
    ):
        drift_handler.read_baseline(drift_handler.BASELINE_KEY)


def test_invalid_baseline_record_count_aborts_drift_scoring(aws):
    s3, _ = aws
    baseline_key = drift_handler.BASELINE_KEY
    baseline = {"record_count": 0, "counts": {"Contract": {"One year": 1}}, "edges": {}}
    by_key = {baseline_key: body(baseline)}
    s3.get_object.side_effect = lambda Bucket, Key: by_key[Key]

    with pytest.raises(
        ValueError,
        match=(
            f"Baseline object s3://{drift_handler.ARTIFACTS_BUCKET}/{drift_handler.BASELINE_KEY}.*record_count"
        ),
    ):
        drift_handler.read_baseline(drift_handler.BASELINE_KEY)


def test_invalid_baseline_missing_feature_distribution_aborts_drift_scoring(aws):
    s3, _ = aws
    baseline = json.loads(json.dumps(BASELINE))
    del baseline["counts"]["Contract"]
    s3.get_object.return_value = body(baseline)

    with pytest.raises(ValueError, match="every feature column"):
        drift_handler.read_baseline(drift_handler.BASELINE_KEY)


def test_read_captured_skips_unreadable_objects_and_tracks_skips(aws):
    s3, _ = aws
    good_key = "capture/2026/08/07/09/0.json"
    bad_key = "capture/2026/08/07/09/1.json"
    by_key = {
        good_key: body({"record": VALID}),
        bad_key: {"Body": io.BytesIO(b"{")},
    }
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": good_key}, {"Key": bad_key}]}
    ]
    s3.get_object.side_effect = lambda Bucket, Key: by_key[Key]

    with mock.patch.object(drift_handler, "log_event") as log_event:
        records, unreadable_count = drift_handler.read_captured(["capture/2026/08/07/09/"])

    assert records == [VALID]
    assert unreadable_count == 1
    log_event.assert_called_once_with(
        "capture_object_unreadable",
        key=bad_key,
        skipped=1,
    )


def test_a_uniform_window_is_skipped_even_when_it_is_large(aws):
    """Skip a large point-mass window from repeated prediction requests."""
    s3, events = aws
    stub_capture(s3, UNIFORM)

    result = drift_handler.handler({}, None)

    assert result["skipped"] == "uniform_records"
    assert result["records"] == 200
    assert result["distinct"] == 1
    # It cleared the record count and still must not retrain.
    assert result["records"] >= drift_handler.MIN_RECORDS
    events.put_events.assert_not_called()


def test_a_stable_window_reports_no_drift_and_emits_nothing(aws):
    s3, events = aws
    stub_capture(s3, STABLE)

    result = drift_handler.handler({}, None)

    assert result["drifted"] is False
    assert result["drifted_columns"] == []
    assert result["record_count"] == 200
    events.put_events.assert_not_called()


def test_a_shifted_window_with_one_unreadable_object_emits_count_in_result_and_detail(aws):
    s3, events = aws
    good_keys = [f"capture/2026/08/07/09/{index}.json" for index in range(200)]
    bad_key = "capture/2026/08/07/09/201.json"
    shifted_count = len(SHIFTED)
    by_key: dict[str, dict[str, io.BytesIO]] = {}
    for index, key in enumerate(good_keys):
        by_key[key] = body({"record": SHIFTED[index % shifted_count]})
    by_key[bad_key] = {"Body": io.BytesIO(b"{")}
    by_key[BASELINE_RUN_KEY] = body(BASELINE)
    by_key[drift_handler.BASELINE_KEY] = body(BASELINE)
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": key} for key in [*good_keys, bad_key]]}
    ]
    s3.get_object.side_effect = lambda Bucket, Key: by_key[Key]

    result = drift_handler.handler({}, None)

    assert result["drifted"] is True
    assert result["unreadable_count"] == 1
    assert result["record_count"] == len(good_keys)
    entry = events.put_events.call_args.kwargs["Entries"][0]
    assert entry["Source"] == drift.EVENT_SOURCE
    assert entry["DetailType"] == drift.EVENT_DETAIL_TYPE
    detail = json.loads(entry["Detail"])
    assert detail["status"] == drift.DRIFT_STATUS
    assert "tenure" in detail["drifted_columns"]
    assert detail["unreadable_count"] == 1


def test_put_events_failure_raises_with_a_named_error_code(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    events.put_events.return_value = {
        "FailedEntryCount": 1,
        "Entries": [{"ErrorCode": "InternalFailure"}],
    }

    with pytest.raises(RuntimeError, match="InternalFailure"):
        drift_handler.handler({}, None)

    events.put_events.assert_called_once()


def test_the_shift_is_detected_on_its_merits_not_on_uniformity(aws):
    """The window that triggers a violation is as diverse as the stable one."""
    assert drift.distinct_record_count(SHIFTED) == len(SHIFTED)
    assert drift.distinct_record_count(STABLE) == len(STABLE)
    # Only the configured shifted columns move.
    moved = drift.compare(BASELINE, SHIFTED)["drifted_columns"]
    assert set(moved) <= {
        "tenure",
        "MonthlyCharges",
        "TotalCharges",
        "Contract",
        "InternetService",
        "PaymentMethod",
    }


def test_the_emitted_detail_is_what_the_retrain_handler_matches(aws):
    """The producer's event must satisfy the consumer's guard."""
    s3, events = aws
    stub_capture(s3, SHIFTED)
    drift_handler.handler({}, None)

    retrain = import_with_stubbed_boto3("src.monitoring.retrain_handler")
    detail = json.loads(events.put_events.call_args.kwargs["Entries"][0]["Detail"])
    assert detail["status"] == retrain.VIOLATION_STATUS


def test_the_four_window_outcomes_stay_distinguishable(aws):
    """Too few, too uniform, scored clean, and scored drifting are four
    different readings, and only the last one may retrain."""
    s3, events = aws

    stub_capture(s3, varied_records(3, seed=5))
    assert drift_handler.handler({}, None)["skipped"] == "insufficient_records"

    stub_capture(s3, UNIFORM)
    assert drift_handler.handler({}, None)["skipped"] == "uniform_records"

    stub_capture(s3, STABLE)
    assert drift_handler.handler({}, None)["drifted"] is False

    events.put_events.assert_not_called()

    stub_capture(s3, SHIFTED)
    assert drift_handler.handler({}, None)["drifted"] is True
    events.put_events.assert_called_once()


def test_current_serving_package_binds_the_drift_result(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)

    result = drift_handler.handler({}, None)

    assert result["model_package_name"] == MODEL_PACKAGE_ARN
    assert result["endpoint_config_name"] == ENDPOINT_CONFIG_NAME
    detail = json.loads(events.put_events.call_args.kwargs["Entries"][0]["Detail"])
    assert detail["baseline_uri"] == BASELINE_URI


def test_current_package_is_used_instead_of_the_latest_approved_package(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    latest = mock.patch("src.common.registry.get_champion")

    with latest as get_champion:
        drift_handler.handler({}, None)

    get_champion.assert_not_called()
    detail = json.loads(events.put_events.call_args.kwargs["Entries"][0]["Detail"])
    assert detail["model_package_name"] == MODEL_PACKAGE_ARN


def test_legacy_package_without_baseline_metadata_fails_closed(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    drift_handler.sm.describe_model_package.return_value = {"CustomerMetadataProperties": {}}

    with mock.patch.object(drift_handler, "log_event") as log_event:
        with pytest.raises(ValueError, match=BASELINE_URI_METADATA_KEY):
            drift_handler.handler({}, None)

    log_event.assert_called_once_with("drift_baseline_metadata_missing", package=MODEL_PACKAGE_ARN)
    events.put_events.assert_not_called()
    assert BASELINE_RUN_KEY not in [call.kwargs["Key"] for call in s3.get_object.call_args_list]


@pytest.mark.parametrize(
    "baseline_uri",
    [
        "s3://other-artifacts/monitor/baselines/execution-1/baseline.json",
        "s3://test-artifacts/monitor/baseline/baseline.json",
        "s3://test-artifacts/monitor/baselines/../baseline.json",
    ],
)
def test_untrusted_baseline_uri_fails_closed(aws, baseline_uri):
    s3, events = aws
    stub_capture(s3, SHIFTED, baseline_uri=baseline_uri)

    with pytest.raises(ValueError, match="baseline URI"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()
    assert BASELINE_RUN_KEY not in [call.kwargs["Key"] for call in s3.get_object.call_args_list]


def test_malformed_serving_baseline_fails_closed(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED, baseline={})

    with pytest.raises(ValueError, match="Baseline object"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()


def test_transitional_endpoint_state_skips_before_model_lookup(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    drift_handler.sm.describe_endpoint.return_value = {
        "EndpointStatus": "Updating",
        "EndpointConfigName": ENDPOINT_CONFIG_NAME,
    }

    result = drift_handler.handler({}, None)

    assert result == {
        "skipped": "endpoint_not_healthy",
        "endpoint_status": "Updating",
        "reason": "endpoint_status_updating",
    }
    drift_handler.sm.describe_endpoint_config.assert_not_called()
    events.put_events.assert_not_called()


def test_endpoint_config_change_drops_result_before_publication(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    drift_handler.sm.describe_endpoint.side_effect = [
        {"EndpointStatus": "InService", "EndpointConfigName": ENDPOINT_CONFIG_NAME},
        {"EndpointStatus": "InService", "EndpointConfigName": "test-endpoint-config-2"},
    ]

    result = drift_handler.handler({}, None)

    assert result == {"skipped": "serving_model_changed", "reason": "endpoint_config_changed"}
    events.put_events.assert_not_called()


def test_primary_container_model_package_shape_is_supported(aws):
    s3, events = aws
    stub_capture(s3, STABLE)
    drift_handler.sm.describe_model.return_value = {
        "PrimaryContainer": {"ModelPackageName": MODEL_PACKAGE_ARN}
    }

    result = drift_handler.handler({}, None)

    assert result["drifted"] is False
    events.put_events.assert_not_called()


@pytest.mark.parametrize(
    "model",
    [
        {"Containers": []},
        {"Containers": [{"ModelPackageName": MODEL_PACKAGE_ARN}, {}]},
        {"Containers": [{}]},
        {"Containers": [{"ModelPackageName": 7}]},
        {"Containers": "invalid"},
        {"PrimaryContainer": {}},
    ],
)
def test_model_without_one_named_package_fails_closed(aws, model):
    s3, events = aws
    stub_capture(s3, STABLE)
    drift_handler.sm.describe_model.return_value = model

    with pytest.raises(ValueError, match="serving model"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()


def test_endpoint_snapshot_requires_status_and_config(aws):
    s3, events = aws
    stub_capture(s3, STABLE)
    drift_handler.sm.describe_endpoint.return_value = {"EndpointStatus": "InService"}

    with pytest.raises(ValueError, match="status or config"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()


def test_invalid_serving_baseline_json_fails_closed(aws):
    s3, events = aws
    stub_capture(s3, STABLE)
    original_get_object = s3.get_object.side_effect

    def get_object(Bucket, Key):
        if Key == BASELINE_RUN_KEY:
            return {"Body": io.BytesIO(b"{")}
        return original_get_object(Bucket=Bucket, Key=Key)

    s3.get_object.side_effect = get_object

    with pytest.raises(ValueError, match="invalid JSON"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()


@pytest.mark.parametrize(
    "endpoint_config",
    [{"ProductionVariants": []}, {"ProductionVariants": [{"ModelName": ""}]}],
)
def test_endpoint_config_without_one_model_fails_closed(aws, endpoint_config):
    s3, events = aws
    stub_capture(s3, STABLE)
    drift_handler.sm.describe_endpoint_config.return_value = endpoint_config

    with pytest.raises(ValueError, match="endpoint config"):
        drift_handler.handler({}, None)

    events.put_events.assert_not_called()


def test_endpoint_becomes_unhealthy_before_publication(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)
    drift_handler.sm.describe_endpoint.side_effect = [
        {"EndpointStatus": "InService", "EndpointConfigName": ENDPOINT_CONFIG_NAME},
        {"EndpointStatus": "Updating", "EndpointConfigName": ENDPOINT_CONFIG_NAME},
    ]

    result = drift_handler.handler({}, None)

    assert result["reason"] == "endpoint_status_updating"
    events.put_events.assert_not_called()
