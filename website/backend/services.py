"""Reach the AWS services the website reads and writes.

The route handlers in `app.py` hold no boto3 call, so this module is the one
place that touches S3, DynamoDB, and the prediction API. Each function returns
data or raises `ServiceError`; none of them knows about HTTP.

`src/common` owns the feature contract, the request schema, and the SigV4
helpers. This module MUST NOT restate any of them.
"""

import json
import time
import urllib.error
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.common.events import log_event
from src.common.features import (
    DEFAULT_THRESHOLD,
    FEATURE_VOCABULARY,
    LABEL_COLUMN,
    NUMERIC,
)
from src.common.schema import FEATURE_COLUMNS, CustomerRecord
from src.common.signing import SigningError, post_prediction
from website.backend.settings import Settings


class ServiceError(RuntimeError):
    """Raised when a backing service cannot answer."""


s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")


# The repository root, which is `/app` inside the image and the checkout
# during local development. Both hold the sample payloads beside `src/`.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The canonical request payloads. They already back the unit fixtures and the
# hand-run `curl` calls, so the website reads the same files rather than
# restating one record in TypeScript or in this module.
_EXAMPLE_FILES = (
    ("typical", "A typical customer", "sample.json"),
    ("high_risk", "A high-risk customer", "sample-high-risk.json"),
)


@lru_cache(maxsize=1)
def example_records() -> list[dict[str, Any]]:
    """Read the sample payloads that seed the prediction form.

    A missing file drops its example rather than failing the schema route. The
    form then starts from the schema defaults, and the page still works.
    """
    examples: list[dict[str, Any]] = []
    for key, label, filename in _EXAMPLE_FILES:
        path = _REPO_ROOT / filename
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            log_event("website_example_missing", file=filename, reason=type(error).__name__)
            continue
        examples.append({"key": key, "label": label, "record": record})
    return examples


@lru_cache(maxsize=1)
def numeric_bounds() -> dict[str, dict[str, Any]]:
    """Read each numeric column's range from the shared request model.

    A numeric column has no value set. Its contract is the range check on
    `CustomerRecord`, so the form reads that model rather than repeating a
    minimum or a maximum that the schema already states.
    """
    properties = CustomerRecord.model_json_schema()["properties"]
    bounds: dict[str, dict[str, Any]] = {}
    for column in sorted(NUMERIC):
        spec = properties.get(column, {})
        entry: dict[str, Any] = {"integer": spec.get("type") == "integer"}
        for key in ("minimum", "maximum"):
            if key in spec:
                entry[key] = spec[key]
        bounds[column] = entry
    return bounds


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
        "numeric_bounds": numeric_bounds(),
        "decision_threshold": DEFAULT_THRESHOLD,
        "examples": example_records(),
    }


class ResultsCache:
    """Hold the newest evaluation report for a fixed time.

    A page view would otherwise reach S3 for every reader. A failed read is
    never cached, so a recovered permission shows on the next request.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._payload: dict[str, Any] | None = None
        self._read_at = 0.0

    def get(self, now: float) -> dict[str, Any] | None:
        if self._payload is not None and now - self._read_at < self.ttl_seconds:
            return dict(self._payload)
        return None

    def put(self, payload: dict[str, Any], now: float) -> None:
        self._payload = payload
        self._read_at = now


def latest_results(
    settings: Settings, cache: ResultsCache, now: float | None = None
) -> dict[str, Any]:
    """Return the newest evaluation report under the report prefix."""
    moment = time.monotonic() if now is None else now
    cached = cache.get(moment)
    if cached is not None:
        return cached

    try:
        listing = s3.list_objects_v2(
            Bucket=settings.artifacts_bucket, Prefix=f"{settings.evaluation_prefix}/"
        )
        objects = [item for item in listing.get("Contents", []) if item["Key"].endswith(".json")]
        if not objects:
            return {"available": False}

        newest = max(objects, key=lambda item: item["LastModified"])
        body = s3.get_object(Bucket=settings.artifacts_bucket, Key=newest["Key"])["Body"].read()
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

    cache.put(payload, moment)
    return dict(payload)


def predict(settings: Settings, record: dict[str, Any]) -> dict[str, Any]:
    """Forward one validated record to the signed prediction API.

    The caller validates the record against `CustomerRecord` first. This
    function signs the request with the instance role, so a visitor never holds
    AWS credentials.
    """
    if not settings.predict_url:
        # SigV4 signs the Host header. An empty URL leaves it unset, and
        # botocore then raises `AttributeError` from inside the signer. Name
        # the missing setting instead.
        log_event("website_predict_failed", reason="PREDICT_URL is unset")
        raise ServiceError("the prediction API is not configured")

    try:
        return post_prediction(settings.predict_url, record, boto3.Session())
    except urllib.error.HTTPError as error:
        log_event("website_predict_failed", status=error.code)
        raise ServiceError(f"the prediction API returned HTTP {error.code}") from error
    except (OSError, SigningError, json.JSONDecodeError, ValueError) as error:
        # `URLError` is an `OSError`, so a network failure lands here. An empty
        # or malformed `PREDICT_URL` raises `ValueError` from urllib instead,
        # and a configuration mistake MUST NOT read as an internal error.
        log_event("website_predict_failed", reason=type(error).__name__)
        raise ServiceError("the prediction API is unavailable") from error


def subscribe(settings: Settings, email: str) -> str:
    """Store one address and return the time it first arrived.

    `if_not_exists` keeps the first signup time. A second signup from one
    address moves `last_signup_at` and leaves `created_at` alone, so the record
    still answers when the reader joined.
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        item = dynamodb.update_item(
            TableName=settings.table_name,
            Key={"email": {"S": email}},
            UpdateExpression=(
                "SET created_at = if_not_exists(created_at, :now), last_signup_at = :now"
            ),
            ExpressionAttributeValues={":now": {"S": now}},
            ReturnValues="ALL_NEW",
        )["Attributes"]
    except (ClientError, OSError) as error:
        log_event("website_subscribe_failed", reason=type(error).__name__)
        raise ServiceError("the mailing list is unavailable") from error

    created_at: str = item["created_at"]["S"]
    log_event("website_subscribed", returning=created_at != now)
    return created_at
