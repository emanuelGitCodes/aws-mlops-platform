import datetime
import io
import json
import urllib.error
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from src.common.features import FEATURE_VOCABULARY
from tests.unit.conftest import VALID, import_with_stubbed_boto3
from website.backend.settings import Settings

services = import_with_stubbed_boto3("website.backend.services")

SETTINGS = Settings(
    table_name="test-table",
    artifacts_bucket="test-artifacts",
    evaluation_prefix="evaluations",
    predict_url="https://example.test/predict",
    rate_limit_per_minute=10,
    port=8080,
    results_cache_seconds=300,
    max_body_bytes=16384,
)


@pytest.fixture
def cache():
    return services.ResultsCache(SETTINGS.results_cache_seconds)


def _listing(*keys):
    base = datetime.datetime(2026, 8, 14, tzinfo=datetime.UTC)
    return {
        "Contents": [
            {"Key": key, "LastModified": base + datetime.timedelta(hours=index)}
            for index, key in enumerate(keys)
        ]
    }


def _body(payload):
    return {"Body": io.BytesIO(json.dumps(payload).encode())}


def test_schema_payload_comes_from_the_shared_contract():
    """Publish the feature contract without restating it."""
    payload = services.schema_payload()

    assert payload["feature_columns"] == services.FEATURE_COLUMNS
    assert payload["label_column"] == "Churn"
    assert set(payload["categorical_values"]) == set(FEATURE_VOCABULARY)
    assert payload["categorical_values"]["Contract"] == sorted(FEATURE_VOCABULARY["Contract"])
    assert payload["decision_threshold"] == 0.5


def test_numeric_bounds_come_from_the_request_model():
    """Read each numeric range from `CustomerRecord`, never from a literal."""
    bounds = services.numeric_bounds()

    assert set(bounds) == set(services.NUMERIC)
    # `SeniorCitizen` is the one integer flag, so the form can render a choice.
    assert bounds["SeniorCitizen"] == {"integer": True, "minimum": 0, "maximum": 1}
    assert bounds["tenure"] == {"integer": True, "minimum": 0}
    assert bounds["MonthlyCharges"] == {"integer": False, "minimum": 0}


def test_examples_come_from_the_canonical_sample_files():
    """Seed the form from the payloads the fixtures and curl calls already use."""
    examples = services.example_records()

    assert [example["key"] for example in examples] == ["typical", "high_risk"]
    for example in examples:
        assert set(example["record"]) >= set(services.FEATURE_COLUMNS)
        assert example["label"]


def test_a_missing_sample_file_drops_its_example(tmp_path, monkeypatch):
    """Lose one example rather than the whole schema route."""
    services.example_records.cache_clear()
    monkeypatch.setattr(services, "_REPO_ROOT", tmp_path)
    (tmp_path / "sample.json").write_text(json.dumps(VALID))
    try:
        examples = services.example_records()
    finally:
        services.example_records.cache_clear()

    assert [example["key"] for example in examples] == ["typical"]


def test_latest_results_returns_the_newest_report(cache):
    """Select the report with the newest last-modified time."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json", "evaluations/b.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        payload = services.latest_results(SETTINGS, cache)

    assert payload["available"] is True
    assert payload["key"] == "evaluations/b.json"
    assert payload["report"] == {"auc": 0.86}


def test_latest_results_ignores_objects_that_are_not_reports(cache):
    """Read only the JSON reports under the prefix."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/model.tar.gz")
        assert services.latest_results(SETTINGS, cache) == {"available": False}
        s3.get_object.assert_not_called()


def test_latest_results_reports_an_empty_prefix(cache):
    """Report no evaluation before the first pipeline run."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = {}
        assert services.latest_results(SETTINGS, cache) == {"available": False}


def test_latest_results_serves_the_cache_inside_the_window(cache):
    """Reach S3 once for each cache window."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        services.latest_results(SETTINGS, cache, now=1000.0)
        services.latest_results(SETTINGS, cache, now=1000.0 + SETTINGS.results_cache_seconds - 1)
        assert s3.list_objects_v2.call_count == 1

        s3.get_object.return_value = _body({"auc": 0.86})
        services.latest_results(SETTINGS, cache, now=1000.0 + SETTINGS.results_cache_seconds)
        assert s3.list_objects_v2.call_count == 2


def test_latest_results_survives_a_denied_read(cache):
    """Lose one page section rather than the whole response."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        payload = services.latest_results(SETTINGS, cache)

    assert payload == {"available": False, "error": "the evaluation report is unavailable"}


def test_latest_results_survives_an_unreadable_report(cache):
    """Report an object that does not hold JSON."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = {"Body": io.BytesIO(b"not json")}
        assert services.latest_results(SETTINGS, cache)["available"] is False


def test_a_failed_read_is_not_cached(cache):
    """Retry the next request rather than serving the failure for 300 seconds."""
    with mock.patch.object(services, "s3") as s3:
        s3.list_objects_v2.side_effect = ClientError({"Error": {}}, "ListObjectsV2")
        services.latest_results(SETTINGS, cache, now=1000.0)

        s3.list_objects_v2.side_effect = None
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        assert services.latest_results(SETTINGS, cache, now=1001.0)["available"] is True


def test_predict_forwards_the_record():
    """Sign and forward the validated record."""
    with mock.patch.object(services, "post_prediction") as post:
        post.return_value = {"churn_probability": 0.25, "churn": False}
        assert services.predict(SETTINGS, dict(VALID)) == {
            "churn_probability": 0.25,
            "churn": False,
        }
    assert post.call_args.args[0] == SETTINGS.predict_url


def test_predict_names_an_api_failure():
    """Report the status the prediction API returned."""
    error = urllib.error.HTTPError("https://x/predict", 503, "busy", {}, None)
    with mock.patch.object(services, "post_prediction", side_effect=error):
        with pytest.raises(services.ServiceError, match="503"):
            services.predict(SETTINGS, dict(VALID))


def test_predict_hides_a_transport_failure():
    """Keep the transport detail out of the caller's error."""
    with mock.patch.object(services, "post_prediction", side_effect=OSError("no route")):
        with pytest.raises(services.ServiceError, match="unavailable"):
            services.predict(SETTINGS, dict(VALID))


def test_predict_names_an_unset_predict_url():
    """Name the missing setting. botocore would raise from inside the signer."""
    unset = Settings(**{**SETTINGS.__dict__, "predict_url": ""})

    with mock.patch.object(services, "post_prediction") as post:
        with pytest.raises(services.ServiceError, match="not configured"):
            services.predict(unset, dict(VALID))
        post.assert_not_called()


def test_subscribe_returns_the_stored_signup_time():
    """Answer with the time the table holds, not the time of this request."""
    with mock.patch.object(services, "dynamodb") as table:
        table.update_item.return_value = {
            "Attributes": {"created_at": {"S": "2026-01-01T00:00:00Z"}}
        }
        assert services.subscribe(SETTINGS, "reader@example.com") == "2026-01-01T00:00:00Z"

    call = table.update_item.call_args.kwargs
    assert call["Key"] == {"email": {"S": "reader@example.com"}}
    # `if_not_exists` is what keeps the first signup time.
    assert "if_not_exists(created_at, :now)" in call["UpdateExpression"]
    assert "last_signup_at = :now" in call["UpdateExpression"]


def test_subscribe_reports_a_failed_write():
    """Raise a service error rather than a botocore error."""
    with mock.patch.object(services, "dynamodb") as table:
        table.update_item.side_effect = ClientError({"Error": {}}, "UpdateItem")
        with pytest.raises(services.ServiceError, match="mailing list"):
            services.subscribe(SETTINGS, "reader@example.com")
