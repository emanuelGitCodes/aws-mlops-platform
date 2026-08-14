"""Serve the public demo website from one container.

The site publishes the model input contract, the newest evaluation report,
a rate-limited prediction form, and a mailing-list form. It runs on the
Python standard library, so the image needs no web framework.

`route` maps one request to a status and a payload. The HTTP handler class
below it only moves bytes. Keep request logic in `route`.
"""

import json
import os
import re
import time
import urllib.error
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

from src.common.events import log_event
from src.common.features import (
    DEFAULT_THRESHOLD,
    FEATURE_VOCABULARY,
    LABEL_COLUMN,
    NUMERIC,
)
from src.common.schema import FEATURE_COLUMNS, CustomerRecord, format_validation_error
from src.common.signing import SigningError, post_prediction

s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")

TABLE_NAME = os.environ.get("TABLE_NAME", "")
ARTIFACTS_BUCKET = os.environ.get("ARTIFACTS_BUCKET", "")
EVALUATION_PREFIX = os.environ.get("EVALUATION_PREFIX", "evaluations")
PREDICT_URL = os.environ.get("PREDICT_URL", "")
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))
PORT = int(os.environ.get("PORT", "80"))

# Serve the cached evaluation report for this many seconds.
RESULTS_CACHE_SECONDS = 300

# Accept one address shape. The mailing list confirms nothing by mail.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")

# Reject a request body larger than this many bytes.
MAX_BODY_BYTES = 16_384

INDEX_HTML = """<!doctype html>
<title>Churn model demo</title>
<h1>Telco churn model</h1>
<p>An MLOps reference platform on AWS. This page reads the live model.</p>
<h2>Input schema</h2>
<pre id="schema">loading</pre>
<h2>Latest evaluation</h2>
<pre id="results">loading</pre>
<h2>Try the model</h2>
<textarea id="record" rows="12" cols="60"></textarea>
<button onclick="predict()">Predict</button>
<pre id="prediction"></pre>
<h2>Keep in touch</h2>
<input id="email" size="40" placeholder="you@example.com">
<button onclick="subscribe()">Subscribe</button>
<pre id="subscribed"></pre>
<script>
async function show(path, id) {
  const r = await fetch(path);
  document.getElementById(id).textContent = JSON.stringify(await r.json(), null, 2);
}
async function send(path, body, id) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  document.getElementById(id).textContent = JSON.stringify(await r.json(), null, 2);
}
function predict() {
  let record;
  try { record = JSON.parse(document.getElementById('record').value); }
  catch (e) { document.getElementById('prediction').textContent = 'invalid JSON'; return; }
  send('/api/predict', record, 'prediction');
}
async function subscribe() {
  const r = await fetch('/api/subscribe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email: document.getElementById('email').value})
  });
  const d = await r.json();
  document.getElementById('subscribed').textContent = d.subscribed
    ? 'Signed up at ' + d.created_at
    : d.error;
}
show('/api/schema', 'schema');
show('/api/results', 'results');
</script>
"""


class RateLimiter:
    """Count requests per caller inside a sliding window."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record one request for `key`. Return False when it exceeds the limit."""
        moment = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and moment - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(moment)
        return True


limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)

# Hold the newest evaluation report and the time it was read.
_results_cache: dict[str, Any] = {"payload": None, "read_at": 0.0}


def schema_payload() -> dict[str, Any]:
    """Return the model input contract.

    `src.common.features` owns every value. This function only reshapes it.
    """
    return {
        "feature_columns": FEATURE_COLUMNS,
        "label_column": LABEL_COLUMN,
        "numeric_columns": sorted(NUMERIC),
        "categorical_values": {
            column: sorted(values) for column, values in FEATURE_VOCABULARY.items()
        },
        "decision_threshold": DEFAULT_THRESHOLD,
    }


def latest_results(now: float | None = None) -> dict[str, Any]:
    """Return the newest evaluation report under the report prefix.

    The result stays cached for `RESULTS_CACHE_SECONDS`, so page views do not
    reach S3 for every reader.
    """
    moment = time.monotonic() if now is None else now
    cached = _results_cache["payload"]
    if cached is not None and moment - _results_cache["read_at"] < RESULTS_CACHE_SECONDS:
        return dict(cached)

    try:
        listing = s3.list_objects_v2(Bucket=ARTIFACTS_BUCKET, Prefix=f"{EVALUATION_PREFIX}/")
        objects = [item for item in listing.get("Contents", []) if item["Key"].endswith(".json")]
        if not objects:
            return {"available": False}

        newest = max(objects, key=lambda item: item["LastModified"])
        body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=newest["Key"])["Body"].read()
        payload = {
            "available": True,
            "key": newest["Key"],
            "generated_at": newest["LastModified"].isoformat(),
            "report": json.loads(body),
        }
    except (ClientError, OSError, json.JSONDecodeError) as error:
        # A denied read, a throttle, or an unreadable report reaches here. The
        # page loses one section rather than the whole response.
        log_event("website_results_failed", reason=type(error).__name__)
        return {"available": False, "error": "the evaluation report is unavailable"}

    _results_cache["payload"] = payload
    _results_cache["read_at"] = moment
    return dict(payload)


def predict(record: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Validate one record and forward it to the signed prediction API."""
    try:
        validated = CustomerRecord(**record)
    except ValidationError as error:
        return 400, {"error": format_validation_error(error)}

    payload = validated.model_dump(exclude_none=True)
    try:
        return 200, post_prediction(PREDICT_URL, payload, boto3.Session())
    except urllib.error.HTTPError as error:
        log_event("website_predict_failed", status=error.code)
        return 502, {"error": f"the prediction API returned HTTP {error.code}"}
    except (OSError, SigningError, json.JSONDecodeError) as error:
        log_event("website_predict_failed", reason=type(error).__name__)
        return 502, {"error": "the prediction API is unavailable"}


def subscribe(email: str) -> tuple[int, dict[str, Any]]:
    """Store one mailing-list address with the time it first arrived.

    `if_not_exists` keeps the first signup time. A second signup from the same
    address moves `last_signup_at` and leaves `created_at` alone, so the record
    still answers when the reader joined.
    """
    if not isinstance(email, str) or not EMAIL_PATTERN.match(email.strip()):
        return 400, {"error": "a valid email address is required"}
    address = email.strip().lower()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        item = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"email": {"S": address}},
            UpdateExpression=(
                "SET created_at = if_not_exists(created_at, :now), last_signup_at = :now"
            ),
            ExpressionAttributeValues={":now": {"S": now}},
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except (ClientError, OSError) as error:
        log_event("website_subscribe_failed", reason=type(error).__name__)
        return 502, {"error": "the mailing list is unavailable"}

    created_at = item["created_at"]["S"]
    log_event("website_subscribed", returning=created_at != now)
    return 200, {"subscribed": True, "created_at": created_at}


def route(method: str, path: str, body: bytes, caller: str) -> tuple[int, str, str | bytes]:
    """Return the status, content type, and body for one request."""
    if method == "GET" and path == "/":
        return 200, "text/html; charset=utf-8", INDEX_HTML
    if method == "GET" and path == "/api/schema":
        return 200, "application/json", json.dumps(schema_payload())
    if method == "GET" and path == "/api/results":
        return 200, "application/json", json.dumps(latest_results())
    if method == "GET" and path == "/api/health":
        return 200, "application/json", json.dumps({"ok": True})

    if method == "POST" and path in ("/api/predict", "/api/subscribe"):
        if len(body) > MAX_BODY_BYTES:
            return 413, "application/json", json.dumps({"error": "request body is too large"})
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return 400, "application/json", json.dumps({"error": "request body must be JSON"})
        if not isinstance(parsed, dict):
            return 400, "application/json", json.dumps({"error": "request body must be an object"})

        if path == "/api/subscribe":
            status, payload = subscribe(parsed.get("email", ""))
            return status, "application/json", json.dumps(payload)

        if not limiter.allow(caller):
            return (
                429,
                "application/json",
                json.dumps({"error": "too many predictions; wait one minute"}),
            )
        status, payload = predict(parsed)
        return status, "application/json", json.dumps(payload)

    return 404, "application/json", json.dumps({"error": "not found"})


def caller_address(forwarded_for: str | None, peer: str) -> str:
    """Return the caller address for rate limiting.

    CloudFront appends the viewer address to `X-Forwarded-For`, so the first
    entry names the viewer. The security group admits CloudFront only.
    """
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return peer


class WebsiteHandler(BaseHTTPRequestHandler):
    """Adapt one HTTP request to `route`."""

    server_version = "mlops-website"

    def _respond(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, MAX_BODY_BYTES + 1)) if length else b""
        caller = caller_address(self.headers.get("X-Forwarded-For"), self.client_address[0])
        try:
            status, content_type, payload = route(method, self.path.split("?")[0], body, caller)
        except Exception as error:
            # `BaseHTTPRequestHandler` answers nothing when the handler raises,
            # so the caller reads an empty reply and no status code.
            log_event("website_request_failed", reason=type(error).__name__)
            status, content_type = 500, "application/json"
            payload = json.dumps({"error": "the website failed to answer"})
        encoded = payload.encode() if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._respond("POST")

    def log_message(self, format: str, *args: Any) -> None:
        """Emit one structured line in place of the default stderr format."""
        log_event("website_request", detail=format % args)


def main() -> None:
    """Serve until the container stops."""
    log_event("website_starting", port=PORT)
    ThreadingHTTPServer(("", PORT), WebsiteHandler).serve_forever()


if __name__ == "__main__":
    main()
