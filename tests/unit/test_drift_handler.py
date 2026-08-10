"""Drift Lambda: the window it reads, the two window rules, and the event."""

import datetime
import io
import json
import os
from unittest import mock

import pytest

from src.common import drift
from tests.unit.conftest import VALID, import_with_stubbed_boto3, varied_records

os.environ.setdefault("ARTIFACTS_BUCKET", "test-artifacts")
os.environ.setdefault("BASELINE_KEY", "monitor/baseline/baseline.json")
os.environ.setdefault("CAPTURE_PREFIX", "capture")

drift_handler = import_with_stubbed_boto3("src.monitoring.drift_handler")

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


@pytest.fixture
def aws():
    """Stub S3 listing/reading and the EventBridge client."""
    with (
        mock.patch.object(drift_handler, "s3") as s3,
        mock.patch.object(drift_handler, "events") as events,
    ):
        yield s3, events


def stub_capture(s3, records, baseline=BASELINE):
    """Serve `records` from the listing, and `baseline` from its own key."""
    keys = [f"capture/2026/08/07/10/{index}.json" for index in range(len(records))]
    s3.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": key} for key in keys]}
    ]
    by_key = {key: body({"record": record}) for key, record in zip(keys, records, strict=True)}
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


def test_a_shifted_window_emits_the_violation_event(aws):
    s3, events = aws
    stub_capture(s3, SHIFTED)

    result = drift_handler.handler({}, None)

    assert result["drifted"] is True
    entry = events.put_events.call_args.kwargs["Entries"][0]
    assert entry["Source"] == drift.EVENT_SOURCE
    assert entry["DetailType"] == drift.EVENT_DETAIL_TYPE
    detail = json.loads(entry["Detail"])
    assert detail["status"] == drift.DRIFT_STATUS
    assert "tenure" in detail["drifted_columns"]


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
