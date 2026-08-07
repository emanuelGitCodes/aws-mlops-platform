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
    """An unknown category is a client error, not an unhandled encoder crash.

    This used to escape validation as a bare `str`, raise KeyError inside
    `encode_features`, and surface to the caller as a 502 from API Gateway.
    """
    with mock.patch.object(proxy_handler, "runtime") as runtime:
        resp = proxy_handler.handler(_event({**VALID, "Contract": "Three year"}), None)

    assert resp["statusCode"] == 422
    assert "Contract" in json.loads(resp["body"])["error"]
    runtime.invoke_endpoint.assert_not_called()


@pytest.mark.parametrize("code", sorted(proxy_handler.UNAVAILABLE_ERROR_CODES))
def test_endpoint_not_ready_returns_503_with_retry_after(code):
    """The endpoint-updating window is routine here, not exceptional.

    Every approved challenger updates the endpoint, and invocations during that
    window fail. Unguarded, they reached the caller as a 502 with a Lambda
    stack trace instead of a retryable 503.
    """
    runtime = _runtime_raising(ClientError(code, "endpoint is updating"))
    with mock.patch.object(proxy_handler, "runtime", runtime):
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 503
    assert resp["headers"]["Retry-After"] == str(proxy_handler.RETRY_AFTER_SECONDS)
    # The AWS error code is operator detail. It must not reach a caller.
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
    """The code is withheld from the response, so it must be in the log."""
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
