"""Post-deploy smoke test: hits the live /predict endpoint.

Run manually or from CI after a deploy:
    API_URL=... API_KEY=... pytest tests/integration -q
Skipped when the env vars aren't set (e.g. during unit CI).
"""

import json
import os
import urllib.request

import pytest

from tests.unit.test_schema import VALID

pytestmark = pytest.mark.skipif(
    not (os.getenv("API_URL") and os.getenv("API_KEY")),
    reason="API_URL/API_KEY not set",
)


def test_predict_returns_probability():
    req = urllib.request.Request(
        os.environ["API_URL"],
        data=json.dumps(VALID).encode(),
        headers={"Content-Type": "application/json", "x-api-key": os.environ["API_KEY"]},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert isinstance(body["churn"], bool)
