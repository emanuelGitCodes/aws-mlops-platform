import datetime
import io
import json
import urllib.error
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from src.common.features import FEATURE_VOCABULARY
from tests.unit.conftest import VALID, import_with_stubbed_boto3

server = import_with_stubbed_boto3("src.website.server")


@pytest.fixture(autouse=True)
def _reset_state():
    """Clear the results cache and the rate limiter between tests."""
    server._results_cache["payload"] = None
    server._results_cache["read_at"] = 0.0
    server.limiter = server.RateLimiter(10)
    yield


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
    payload = server.schema_payload()

    assert payload["feature_columns"] == server.FEATURE_COLUMNS
    assert payload["label_column"] == "Churn"
    assert set(payload["categorical_values"]) == set(FEATURE_VOCABULARY)
    assert payload["categorical_values"]["Contract"] == sorted(FEATURE_VOCABULARY["Contract"])
    assert payload["decision_threshold"] == 0.5


def test_latest_results_returns_the_newest_report():
    """Select the report with the newest last-modified time."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json", "evaluations/b.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        payload = server.latest_results()

    assert payload["available"] is True
    assert payload["key"] == "evaluations/b.json"
    assert payload["report"] == {"auc": 0.86}
    assert payload["generated_at"].startswith("2026-08-14")


def test_latest_results_ignores_objects_that_are_not_reports():
    """Read only the JSON reports under the prefix."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/model.tar.gz")
        assert server.latest_results() == {"available": False}
        s3.get_object.assert_not_called()


def test_latest_results_reports_an_empty_prefix():
    """Report no evaluation before the first pipeline run."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = {}
        assert server.latest_results() == {"available": False}


def test_latest_results_serves_the_cache_inside_the_window():
    """Reach S3 once for each cache window."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        server.latest_results(now=1000.0)
        server.latest_results(now=1000.0 + server.RESULTS_CACHE_SECONDS - 1)
        assert s3.list_objects_v2.call_count == 1

        s3.get_object.return_value = _body({"auc": 0.86})
        server.latest_results(now=1000.0 + server.RESULTS_CACHE_SECONDS)
        assert s3.list_objects_v2.call_count == 2


def test_latest_results_survives_a_denied_read():
    """Lose one page section rather than the whole response."""
    denied = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.side_effect = denied
        payload = server.latest_results()

    assert payload == {
        "available": False,
        "error": "the evaluation report is unavailable",
    }


def test_latest_results_survives_an_unreadable_report():
    """Report an object that does not hold JSON."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = {"Body": io.BytesIO(b"not json")}
        assert server.latest_results()["available"] is False


def test_a_failed_read_is_not_cached():
    """Retry the next request rather than serving the failure for 300 seconds."""
    with mock.patch.object(server, "s3") as s3:
        s3.list_objects_v2.side_effect = ClientError({"Error": {}}, "ListObjectsV2")
        server.latest_results(now=1000.0)

        s3.list_objects_v2.side_effect = None
        s3.list_objects_v2.return_value = _listing("evaluations/a.json")
        s3.get_object.return_value = _body({"auc": 0.86})
        assert server.latest_results(now=1001.0)["available"] is True


def test_predict_forwards_a_valid_record():
    """Sign and forward a record that matches the schema."""
    with mock.patch.object(server, "post_prediction") as post:
        post.return_value = {"churn_probability": 0.25, "churn": False}
        status, payload = server.predict(dict(VALID))

    assert status == 200
    assert payload == {"churn_probability": 0.25, "churn": False}
    assert "Churn" not in post.call_args.args[1]


def test_predict_rejects_an_unknown_category():
    """Name the field that breaks the schema."""
    record = dict(VALID, Contract="Decade")
    status, payload = server.predict(record)

    assert status == 400
    assert "Contract" in payload["error"]


def test_predict_reports_an_api_failure():
    """Return a gateway error when the prediction API fails."""
    error = urllib.error.HTTPError("https://x/predict", 503, "busy", {}, None)
    with mock.patch.object(server, "post_prediction", side_effect=error):
        status, payload = server.predict(dict(VALID))

    assert status == 502
    assert "503" in payload["error"]


def test_predict_reports_an_unreachable_api():
    """Hide the transport failure detail from the caller."""
    with mock.patch.object(server, "post_prediction", side_effect=OSError("no route")):
        status, payload = server.predict(dict(VALID))

    assert status == 502
    assert payload == {"error": "the prediction API is unavailable"}


def test_subscribe_stores_a_normalized_address_and_the_signup_time():
    """Store the address in lower case and answer with the signup time."""
    with mock.patch.object(server, "dynamodb") as table:
        table.update_item.return_value = {
            "Attributes": {"created_at": {"S": "2026-08-14T12:00:00Z"}}
        }
        status, payload = server.subscribe("  Reader@Example.COM ")

    assert status == 200
    assert payload == {"subscribed": True, "created_at": "2026-08-14T12:00:00Z"}
    call = table.update_item.call_args.kwargs
    assert call["Key"] == {"email": {"S": "reader@example.com"}}
    assert call["ExpressionAttributeValues"][":now"]["S"].endswith("Z")


def test_subscribe_keeps_the_first_signup_time():
    """Never overwrite `created_at`. A second signup keeps the original."""
    with mock.patch.object(server, "dynamodb") as table:
        table.update_item.return_value = {
            "Attributes": {"created_at": {"S": "2026-01-01T00:00:00Z"}}
        }
        _, payload = server.subscribe("reader@example.com")

    expression = table.update_item.call_args.kwargs["UpdateExpression"]
    assert "if_not_exists(created_at, :now)" in expression
    assert "last_signup_at = :now" in expression
    # The stored time wins over the time of this request.
    assert payload["created_at"] == "2026-01-01T00:00:00Z"


def test_subscribe_reports_a_failed_write():
    """Return an error rather than raising when the table refuses the write."""
    with mock.patch.object(server, "dynamodb") as table:
        table.update_item.side_effect = ClientError({"Error": {}}, "UpdateItem")
        status, payload = server.subscribe("reader@example.com")

    assert status == 502
    assert payload == {"error": "the mailing list is unavailable"}


@pytest.mark.parametrize("address", ["", "reader", "reader@example", "a b@example.com", 42])
def test_subscribe_rejects_an_invalid_address(address):
    """Reject an address that cannot receive mail."""
    with mock.patch.object(server, "dynamodb") as table:
        status, payload = server.subscribe(address)

    assert status == 400
    assert "error" in payload
    table.update_item.assert_not_called()


def test_the_rate_limiter_counts_inside_the_window():
    """Allow the configured count, then refuse."""
    limiter = server.RateLimiter(2, window_seconds=60.0)

    assert limiter.allow("1.2.3.4", now=0.0) is True
    assert limiter.allow("1.2.3.4", now=1.0) is True
    assert limiter.allow("1.2.3.4", now=2.0) is False
    # A second caller keeps its own count.
    assert limiter.allow("5.6.7.8", now=2.0) is True
    # The window moves past the first two requests.
    assert limiter.allow("1.2.3.4", now=61.0) is True


def test_the_rate_limiter_reads_the_clock_by_default():
    """Use the monotonic clock when the caller passes no time."""
    limiter = server.RateLimiter(1)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [("9.9.9.9, 1.1.1.1", "9.9.9.9"), (None, "10.0.0.1"), ("", "10.0.0.1")],
)
def test_the_caller_address_prefers_the_forwarded_viewer(forwarded, expected):
    """Read the viewer address CloudFront puts first."""
    assert server.caller_address(forwarded, "10.0.0.1") == expected


def test_route_serves_the_index_page():
    """Return HTML at the site root."""
    status, content_type, body = server.route("GET", "/", b"", "1.2.3.4")

    assert status == 200
    assert content_type.startswith("text/html")
    assert "Telco churn model" in body


def test_route_serves_the_schema_and_health():
    """Answer the two read-only JSON routes."""
    status, _, body = server.route("GET", "/api/schema", b"", "1.2.3.4")
    assert status == 200
    assert json.loads(body)["feature_columns"] == server.FEATURE_COLUMNS

    status, _, body = server.route("GET", "/api/health", b"", "1.2.3.4")
    assert (status, json.loads(body)) == (200, {"ok": True})


def test_route_serves_the_results():
    """Answer the results route from S3."""
    with mock.patch.object(server, "latest_results", return_value={"available": False}):
        status, _, body = server.route("GET", "/api/results", b"", "1.2.3.4")

    assert (status, json.loads(body)) == (200, {"available": False})


def test_route_rate_limits_the_prediction_route():
    """Refuse a caller that passes the configured limit."""
    server.limiter = server.RateLimiter(1)
    with mock.patch.object(server, "predict", return_value=(200, {"churn": False})) as predict:
        first, _, _ = server.route("POST", "/api/predict", json.dumps(VALID).encode(), "1.2.3.4")
        second, _, body = server.route(
            "POST", "/api/predict", json.dumps(VALID).encode(), "1.2.3.4"
        )
        # The refused request never reaches the prediction API.
        assert predict.call_count == 1

    assert first == 200
    assert second == 429
    assert "too many" in json.loads(body)["error"]


def test_route_forwards_a_subscription():
    """Pass the address to the mailing-list writer."""
    with mock.patch.object(server, "subscribe", return_value=(200, {"subscribed": True})) as sub:
        status, _, body = server.route(
            "POST", "/api/subscribe", b'{"email": "reader@example.com"}', "1.2.3.4"
        )

    assert (status, json.loads(body)) == (200, {"subscribed": True})
    sub.assert_called_once_with("reader@example.com")


@pytest.mark.parametrize("path", ["/api/predict", "/api/subscribe"])
def test_route_rejects_a_body_that_is_not_json(path):
    """Report a body the parser cannot read."""
    status, _, body = server.route("POST", path, b"not json", "1.2.3.4")

    assert status == 400
    assert json.loads(body)["error"] == "request body must be JSON"


@pytest.mark.parametrize("path", ["/api/predict", "/api/subscribe"])
def test_route_rejects_a_body_that_is_not_an_object(path):
    """Report a JSON body that is not an object."""
    status, _, body = server.route("POST", path, b"[1, 2]", "1.2.3.4")

    assert status == 400
    assert json.loads(body)["error"] == "request body must be an object"


def test_route_rejects_an_oversized_body():
    """Refuse a body larger than the limit before parsing it."""
    payload = b"x" * (server.MAX_BODY_BYTES + 1)
    status, _, body = server.route("POST", "/api/predict", payload, "1.2.3.4")

    assert status == 413
    assert "too large" in json.loads(body)["error"]


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/missing"), ("POST", "/"), ("DELETE", "/api/schema")]
)
def test_route_reports_an_unknown_request(method, path):
    """Return 404 for any route the site does not serve."""
    status, _, body = server.route(method, path, b"", "1.2.3.4")

    assert status == 404
    assert json.loads(body)["error"] == "not found"


def _handler(method, path, body=b"", headers=None):
    """Drive the HTTP handler without opening a socket."""
    handler = server.WebsiteHandler.__new__(server.WebsiteHandler)
    handler.headers = headers or {}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.client_address = ("10.0.0.1", 51234)
    handler.path = path
    handler.send_response = mock.Mock()
    handler.send_header = mock.Mock()
    handler.end_headers = mock.Mock()
    getattr(handler, f"do_{method}")()
    return handler


def test_the_handler_answers_a_get_and_drops_the_query_string():
    """Route on the path alone and write the payload."""
    handler = _handler("GET", "/api/health?ref=email")

    handler.send_response.assert_called_once_with(200)
    assert json.loads(handler.wfile.getvalue()) == {"ok": True}
    assert ("Content-Type", "application/json") in [
        call.args for call in handler.send_header.call_args_list
    ]


def test_the_handler_reads_a_post_body_and_the_forwarded_address():
    """Pass the declared body and the viewer address to the router."""
    body = b'{"email": "reader@example.com"}'
    headers = {"Content-Length": str(len(body)), "X-Forwarded-For": "9.9.9.9, 1.1.1.1"}
    with mock.patch.object(server, "route", return_value=(200, "application/json", "{}")) as route:
        _handler("POST", "/api/subscribe", body, headers)

    route.assert_called_once_with("POST", "/api/subscribe", body, "9.9.9.9")


def test_the_handler_answers_500_when_a_route_raises():
    """Answer every request. A raising handler would send no status at all."""
    with mock.patch.object(server, "route", side_effect=RuntimeError("boom")):
        handler = _handler("GET", "/api/results")

    handler.send_response.assert_called_once_with(500)
    assert json.loads(handler.wfile.getvalue()) == {"error": "the website failed to answer"}


def test_the_handler_logs_one_structured_line(capsys):
    """Replace the default access-log format with a JSON event."""
    handler = server.WebsiteHandler.__new__(server.WebsiteHandler)
    handler.log_message("%s %s", "GET", "/")

    assert json.loads(capsys.readouterr().out) == {
        "event": "website_request",
        "detail": "GET /",
    }


def test_main_serves_until_the_container_stops():
    """Start the threading server on the configured port."""
    with mock.patch.object(server, "ThreadingHTTPServer") as http_server:
        server.main()

    assert http_server.call_args.args[0] == ("", server.PORT)
    http_server.return_value.serve_forever.assert_called_once_with()
