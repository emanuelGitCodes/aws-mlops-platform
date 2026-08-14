from unittest import mock

import pytest
from fastapi.testclient import TestClient

from tests.unit.conftest import VALID, import_with_stubbed_boto3
from website.backend.rate_limit import RateLimiter

app_module = import_with_stubbed_boto3("website.backend.app")
# Read `services` through the app module. Importing it directly here builds
# real boto3 clients at collection time, and `test_pipeline.py` then reaches
# S3 through the live default session.
services = app_module.services


@pytest.fixture
def client():
    """Return a client with a fresh rate limiter and results cache."""
    app_module.limiter = RateLimiter(app_module.settings.rate_limit_per_minute)
    app_module.results_cache = services.ResultsCache(app_module.settings.results_cache_seconds)
    # Report the 500 handler's response rather than re-raising in the test.
    return TestClient(app_module.app, raise_server_exceptions=False)


def test_health_reports_a_serving_process(client):
    """Answer the health route without reaching AWS."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_the_schema_route_publishes_the_shared_contract(client):
    """Serve the feature contract from `src.common`."""
    response = client.get("/api/schema")

    assert response.status_code == 200
    assert response.json()["feature_columns"] == services.FEATURE_COLUMNS


def test_the_results_route_serves_the_report(client):
    """Return whatever the service reports."""
    payload = {"available": True, "key": "evaluations/a.json", "report": {"auc": 0.86}}
    with mock.patch.object(app_module.services, "latest_results", return_value=payload):
        response = client.get("/api/results")

    assert response.status_code == 200
    assert response.json() == payload


def test_the_predict_route_returns_a_prediction(client):
    """Forward a valid record and answer with the prediction."""
    with mock.patch.object(app_module.services, "predict") as predict:
        predict.return_value = {"churn_probability": 0.25, "churn": False}
        response = client.post("/api/predict", json=dict(VALID))

    assert response.status_code == 200
    assert response.json() == {"churn_probability": 0.25, "churn": False}
    # The label never reaches the prediction API.
    assert "Churn" not in predict.call_args.args[1]


def test_the_predict_route_names_the_invalid_field(client):
    """Report the field that breaks the schema."""
    response = client.post("/api/predict", json=dict(VALID, Contract="Decade"))

    assert response.status_code == 400
    assert "Contract" in response.json()["error"]


def test_the_predict_route_rate_limits_one_caller(client):
    """Refuse the request that passes the configured limit."""
    app_module.limiter = RateLimiter(1)
    with mock.patch.object(app_module.services, "predict") as predict:
        predict.return_value = {"churn_probability": 0.25, "churn": False}
        first = client.post("/api/predict", json=dict(VALID))
        second = client.post("/api/predict", json=dict(VALID))

    assert first.status_code == 200
    assert second.status_code == 429
    assert "too many" in second.json()["error"]
    # The refused request never reaches the prediction API.
    assert predict.call_count == 1


def test_the_rate_limit_separates_two_viewers(client):
    """Count each forwarded viewer address on its own."""
    app_module.limiter = RateLimiter(1)
    with mock.patch.object(app_module.services, "predict") as predict:
        predict.return_value = {"churn": False}
        first = client.post(
            "/api/predict", json=dict(VALID), headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"}
        )
        second = client.post(
            "/api/predict", json=dict(VALID), headers={"x-forwarded-for": "8.8.8.8, 1.1.1.1"}
        )

    assert (first.status_code, second.status_code) == (200, 200)


def test_the_subscribe_route_answers_with_the_signup_time(client):
    """Store the address in lower case and report when it first arrived."""
    with mock.patch.object(app_module.services, "subscribe") as subscribe:
        subscribe.return_value = "2026-08-14T12:00:00Z"
        response = client.post("/api/subscribe", json={"email": "  Reader@Example.COM  "})

    assert response.status_code == 200
    assert response.json() == {"subscribed": True, "created_at": "2026-08-14T12:00:00Z"}
    assert subscribe.call_args.args[1] == "reader@example.com"


@pytest.mark.parametrize("email", ["", "reader", "reader@example", "a b@example.com"])
def test_the_subscribe_route_rejects_an_invalid_address(client, email):
    """Reject an address that cannot receive mail."""
    with mock.patch.object(app_module.services, "subscribe") as subscribe:
        response = client.post("/api/subscribe", json={"email": email})

    assert response.status_code == 400
    subscribe.assert_not_called()


def test_a_failed_backing_service_answers_502(client):
    """Answer a service failure with a gateway status."""
    error = services.ServiceError("the mailing list is unavailable")
    with mock.patch.object(app_module.services, "subscribe", side_effect=error):
        response = client.post("/api/subscribe", json={"email": "reader@example.com"})

    assert response.status_code == 502
    assert response.json() == {"error": "the mailing list is unavailable"}


def test_an_unexpected_error_answers_500(client):
    """Answer every request. An unhandled error would close the socket."""
    with mock.patch.object(app_module.services, "latest_results", side_effect=RuntimeError("x")):
        response = client.get("/api/results")

    assert response.status_code == 500
    assert response.json() == {"error": "the website failed to answer"}


def test_an_unknown_route_answers_404(client):
    """Serve nothing outside the documented routes."""
    assert client.get("/missing").status_code == 404
