"""Test the deployed `/predict` endpoint.

Run manually or from CI after a deploy:
    API_URL=... pytest tests/integration -q
The tests skip when `API_URL` is not set.

Each test signs its request with SigV4. Credentials come from the ambient AWS
session. That identity needs `execute-api:Invoke` on the method.

These tests cover HTTP 200, 422, 400, and 403 responses.
`tests/unit/test_proxy_handler.py` covers HTTP 503 and 502 mappings.
"""

import json
import os
import urllib.error
import urllib.request

import boto3
import pytest
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from src.common.features import DEFAULT_THRESHOLD
from tests.unit.test_schema import VALID

pytestmark = pytest.mark.skipif(not os.getenv("API_URL"), reason="API_URL not set")


def _sign(url, body):
    """Return SigV4 headers for one POST. The signature covers the body."""
    session = boto3.Session()
    request = AWSRequest(
        method="POST", url=url, data=body, headers={"Content-Type": "application/json"}
    )
    SigV4Auth(session.get_credentials(), "execute-api", session.region_name).add_auth(request)
    return dict(request.headers)


def _post(payload=None, *, sign=True, tamper=False, raw=None):
    """POST to `/predict` and return the status and body for all responses."""
    url = os.environ["API_URL"]
    body = raw if raw is not None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers = _sign(url, body)
    if tamper:
        # The headers are signed for the payload above. This sends other bytes
        # under them.
        body = json.dumps({**VALID, "tenure": 999}).encode()
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        raw_body = error.read()
        try:
            return error.code, json.loads(raw_body)
        except json.JSONDecodeError:
            return error.code, {"raw": raw_body.decode(errors="replace")}


def test_predict_returns_probability():
    status, body = _post(VALID)

    assert status == 200
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert isinstance(body["churn"], bool)


def test_the_returned_class_matches_the_returned_probability():
    """The deployed decision rule must be the one evaluation asserts against."""
    _, body = _post(VALID)

    assert body["churn"] is (body["churn_probability"] >= DEFAULT_THRESHOLD)


def test_a_schema_invalid_record_is_rejected_before_the_model():
    """422 naming the field, not a 502 from the endpoint choking on bad input."""
    status, body = _post({**VALID, "tenure": "not-a-number"})

    assert status == 422
    assert "tenure" in body["error"]


def test_a_non_json_body_is_rejected():
    status, body = _post(raw=b"this is not json")

    assert status == 400
    assert "JSON" in body["error"]


def test_the_model_is_not_reachable_without_a_signature():
    """SigV4 is the only boundary in front of the model."""
    status, _ = _post(VALID, sign=False)

    assert status == 403


def test_a_body_changed_after_signing_is_rejected():
    """The signature covers the payload. A replayed header set with a new body
    must not authorize."""
    status, _ = _post(VALID, tamper=True)

    assert status == 403
