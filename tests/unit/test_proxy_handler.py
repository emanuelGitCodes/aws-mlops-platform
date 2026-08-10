import io
import json
from unittest import mock

import pytest

from tests.unit.conftest import VALID, ClientError, import_with_stubbed_boto3

proxy_handler = import_with_stubbed_boto3("src.serving.proxy_handler")


def _runtime_raising(error: Exception) -> mock.Mock:
    """A stubbed sagemaker-runtime whose invoke_endpoint fails with `error`."""
    runtime = mock.Mock()
    runtime.exceptions.ClientError = ClientError
    runtime.invoke_endpoint.side_effect = error
    return runtime


def _event(body) -> dict:
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


def test_valid_request_invokes_endpoint_and_returns_score():
    with (
        mock.patch.object(proxy_handler, "runtime") as runtime,
        mock.patch("builtins.print") as log,
    ):
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"0.83")}
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body == {"churn_probability": 0.83, "churn": True}

    call = runtime.invoke_endpoint.call_args.kwargs
    assert call["EndpointName"] == "test-endpoint"
    assert call["ContentType"] == "text/csv"
    # The payload is the encoded feature vector, one float per feature.
    values = call["Body"].split(",")
    assert all(float(v) >= 0 for v in values)
    assert json.loads(log.call_args.args[0]) == {
        "event": "inference_response",
        "endpoint": "test-endpoint",
        "churn_probability": 0.83,
        "churn": True,
    }


def test_low_score_maps_to_churn_false():
    with mock.patch.object(proxy_handler, "runtime") as runtime:
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"0.12")}
        resp = proxy_handler.handler(_event(VALID), None)
    assert json.loads(resp["body"])["churn"] is False


def test_malformed_json_returns_400():
    resp = proxy_handler.handler(_event("not json{"), None)
    assert resp["statusCode"] == 400


def test_schema_violation_returns_422_with_field():
    resp = proxy_handler.handler(_event({**VALID, "tenure": -5}), None)
    assert resp["statusCode"] == 422
    assert "tenure" in json.loads(resp["body"])["error"]


def test_missing_body_returns_422():
    resp = proxy_handler.handler({"body": None}, None)
    assert resp["statusCode"] == 422


def test_unknown_category_returns_422_not_a_500():
    """Return HTTP 422 for an unknown category."""
    with mock.patch.object(proxy_handler, "runtime") as runtime:
        resp = proxy_handler.handler(_event({**VALID, "Contract": "Three year"}), None)

    assert resp["statusCode"] == 422
    assert "Contract" in json.loads(resp["body"])["error"]
    runtime.invoke_endpoint.assert_not_called()


@pytest.mark.parametrize("code", sorted(proxy_handler.UNAVAILABLE_ERROR_CODES))
def test_endpoint_not_ready_returns_503_with_retry_after(code):
    """Return HTTP 503 and `Retry-After` for an unavailable endpoint."""
    runtime = _runtime_raising(ClientError(code, "endpoint is updating"))
    with mock.patch.object(proxy_handler, "runtime", runtime):
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 503
    assert resp["headers"]["Retry-After"] == str(proxy_handler.RETRY_AFTER_SECONDS)
    # Keep the AWS error code out of the API response.
    assert code not in resp["body"]
    assert "retry" in json.loads(resp["body"])["error"]


def test_unexpected_client_error_returns_502_not_503():
    """A non-transient failure must not advertise itself as retryable."""
    runtime = _runtime_raising(ClientError("ModelError", "container failed"))
    with mock.patch.object(proxy_handler, "runtime", runtime):
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 502
    assert "Retry-After" not in resp["headers"]
    assert "ModelError" not in resp["body"]


def test_client_error_is_logged_with_its_code():
    """Write the SageMaker error code to the operator log."""
    runtime = _runtime_raising(ClientError("ModelNotReadyException", "warming up"))
    with (
        mock.patch.object(proxy_handler, "runtime", runtime),
        mock.patch("builtins.print") as log,
    ):
        proxy_handler.handler(_event(VALID), None)

    assert json.loads(log.call_args.args[0]) == {
        "event": "inference_failed",
        "endpoint": "test-endpoint",
        "error_code": "ModelNotReadyException",
        "status": 503,
    }


def test_unreadable_endpoint_response_returns_502():
    """The endpoint answered, but not with a probability."""
    with mock.patch.object(proxy_handler, "runtime") as runtime:
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"<html>error</html>")}
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 502
    assert "Retry-After" not in resp["headers"]


def _served(capture_bucket="test-artifacts"):
    """Serve one valid request with capture pointed at a stubbed S3."""
    with (
        mock.patch.object(proxy_handler, "runtime") as runtime,
        mock.patch.object(proxy_handler, "s3") as s3,
        mock.patch.object(proxy_handler, "CAPTURE_BUCKET", capture_bucket),
        mock.patch.object(proxy_handler, "CAPTURE_PREFIX", "capture"),
        mock.patch("builtins.print"),
    ):
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"0.83")}
        response = proxy_handler.handler(_event(VALID), None)
    return response, s3


def test_a_served_prediction_is_captured_to_s3():
    response, s3 = _served()

    assert response["statusCode"] == 200
    call = s3.put_object.call_args.kwargs
    assert call["Bucket"] == "test-artifacts"
    captured = json.loads(call["Body"])
    # Store the raw feature record for drift scoring.
    assert captured["record"] == VALID
    assert captured["churn_probability"] == 0.83
    assert captured["churn"] is True
    assert captured["captured_at"]


def test_the_capture_key_is_partitioned_by_hour():
    _, s3 = _served()
    key = s3.put_object.call_args.kwargs["Key"]
    prefix, year, month, day, hour, name = key.split("/")
    assert prefix == "capture"
    assert (len(year), len(month), len(day), len(hour)) == (4, 2, 2, 2)
    assert name.endswith(".json")


def test_capture_is_off_when_no_bucket_is_configured():
    response, s3 = _served(capture_bucket="")
    assert response["statusCode"] == 200
    s3.put_object.assert_not_called()


def test_a_capture_failure_never_changes_the_response():
    # Preserve the completed prediction response after a capture failure.
    with (
        mock.patch.object(proxy_handler, "runtime") as runtime,
        mock.patch.object(proxy_handler, "s3") as s3,
        mock.patch.object(proxy_handler, "CAPTURE_BUCKET", "test-artifacts"),
        mock.patch("builtins.print") as log,
    ):
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"0.83")}
        s3.put_object.side_effect = RuntimeError("bucket on fire")
        response = proxy_handler.handler(_event(VALID), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"churn_probability": 0.83, "churn": True}
    assert "capture_failed" in " ".join(str(c) for c in log.call_args_list)


def test_a_rejected_request_is_never_captured():
    with (
        mock.patch.object(proxy_handler, "s3") as s3,
        mock.patch.object(proxy_handler, "CAPTURE_BUCKET", "test-artifacts"),
    ):
        response = proxy_handler.handler(_event({"gender": "Female"}), None)

    assert response["statusCode"] == 422
    s3.put_object.assert_not_called()
