import io
import json
import os
from unittest import mock

os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")

with mock.patch("boto3.client"):
    from src.serving import proxy_handler

from tests.unit.test_schema import VALID


def _event(body) -> dict:
    return {"body": json.dumps(body) if isinstance(body, dict) else body}


def test_valid_request_invokes_endpoint_and_returns_score():
    with mock.patch.object(proxy_handler, "runtime") as runtime:
        runtime.invoke_endpoint.return_value = {"Body": io.BytesIO(b"0.83")}
        resp = proxy_handler.handler(_event(VALID), None)

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body == {"churn_probability": 0.83, "churn": True}

    call = runtime.invoke_endpoint.call_args.kwargs
    assert call["EndpointName"] == "test-endpoint"
    assert call["ContentType"] == "text/csv"
    # payload is the encoded feature vector, one float per feature
    values = call["Body"].split(",")
    assert all(float(v) >= 0 for v in values)


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
