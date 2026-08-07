"""Post-deploy smoke test: hits the live /predict endpoint.

Run manually or from CI after a deploy:
    API_URL=... API_KEY=... pytest tests/integration -q
Skipped when the env vars aren't set (e.g. during unit CI).

These tests cover every status the public path reaches from outside: 200, the
422 and 400 request rejections, and the 403 from the API key boundary.

The 503 and 502 mappings are absent. Both need the SageMaker endpoint to be
missing, mid-update, or answering with something other than a probability, and
the public API cannot induce that without breaking real traffic.
tests/unit/test_proxy_handler.py covers them against a stubbed runtime client.
"""

import json
import os
import urllib.error
import urllib.request

import pytest

from src.common.features import DEFAULT_THRESHOLD
from tests.unit.test_schema import VALID

pytestmark = pytest.mark.skipif(
    not (os.getenv("API_URL") and os.getenv("API_KEY")),
    reason="API_URL/API_KEY not set",
)


def _post(payload=None, *, api_key=None, send_key=True, raw=None):
    """POST to /predict, returning (status, body) rather than raising on 4xx."""
    headers = {"Content-Type": "application/json"}
    if send_key:
        headers["x-api-key"] = api_key or os.environ["API_KEY"]
    request = urllib.request.Request(
        os.environ["API_URL"],
        data=raw if raw is not None else json.dumps(payload).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, {"raw": body.decode(errors="replace")}


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


def test_the_model_is_not_reachable_without_a_key():
    """The API key is the only boundary in front of the model until Phase 6."""
    status, _ = _post(VALID, send_key=False)

    assert status == 403


def test_a_wrong_api_key_is_rejected():
    # Keep this under ten characters. Beside `api_key=`, a longer literal
    # reads to the gitleaks `generic-api-key` rule as a real key.
    status, _ = _post(VALID, api_key="wrong")

    assert status == 403
