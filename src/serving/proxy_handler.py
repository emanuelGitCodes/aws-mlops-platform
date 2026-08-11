"""Proxy API Gateway requests to the SageMaker endpoint.

It validates the request against the shared schema. It encodes the record into
the CSV feature vector XGBoost expects. It invokes the endpoint and returns the
churn probability. No inference logic lives here.

The handler writes each served record and score to S3. Serverless endpoints do
not support `DataCaptureConfig`. `src.monitoring.drift_handler` reads the
captured objects.
"""

import datetime
import json
import os
import uuid
from typing import Any

import boto3
from pydantic import ValidationError

from src.common.events import log_event
from src.common.features import DEFAULT_THRESHOLD, encode_features
from src.common.schema import (
    FEATURE_COLUMNS,
    CustomerRecord,
    format_validation_error,
)

runtime = boto3.client("sagemaker-runtime")
s3 = boto3.client("s3")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]

# Capture is disabled when either capture variable is absent.
CAPTURE_BUCKET = os.environ.get("CAPTURE_BUCKET", "")
CAPTURE_PREFIX = os.environ.get("CAPTURE_PREFIX", "")

# These SageMaker errors report an unavailable endpoint.
# Endpoint updates can return these errors before the new variant is live.
# SageMaker reports a missing endpoint as `ValidationError`.
UNAVAILABLE_ERROR_CODES = frozenset(
    {
        "ModelNotReadyException",
        "ServiceUnavailable",
        "ThrottlingException",
        "TooManyRequestsException",
        "ValidationError",
    }
)

# Return this retry delay for an unavailable endpoint.
RETRY_AFTER_SECONDS = 15


def capture_key(now: datetime.datetime) -> str:
    """Return the hour-partitioned S3 key for one captured prediction."""
    return (
        f"{CAPTURE_PREFIX}/{now:%Y/%m/%d/%H}/{uuid.uuid4()}.json"
        if CAPTURE_PREFIX
        else f"{now:%Y/%m/%d/%H}/{uuid.uuid4()}.json"
    )


def capture(record: CustomerRecord, prediction: dict[str, Any]) -> None:
    """Write one served record and score without changing the API response."""
    if not CAPTURE_BUCKET:
        return
    now = datetime.datetime.now(datetime.UTC)
    try:
        s3.put_object(
            Bucket=CAPTURE_BUCKET,
            Key=capture_key(now),
            Body=json.dumps(
                {
                    "captured_at": now.isoformat(),
                    "record": {column: getattr(record, column) for column in FEATURE_COLUMNS},
                    **prediction,
                }
            ).encode(),
            ContentType="application/json",
        )
    except Exception as error:  # noqa: BLE001
        log_event("capture_failed", endpoint=ENDPOINT_NAME, error=str(error))


def _response(
    status: int, body: dict[str, Any], *, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(body),
    }


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "request body must be JSON"})

    try:
        record = CustomerRecord.model_validate(payload)
    except ValidationError as e:
        return _response(422, {"error": format_validation_error(e)})

    features = encode_features({c: getattr(record, c) for c in FEATURE_COLUMNS})
    csv_line = ",".join(str(v) for v in features)

    # Map SageMaker endpoint errors to stable API responses.
    try:
        result = runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="text/csv",
            Body=csv_line,
        )
    except runtime.exceptions.ClientError as error:
        code = str((getattr(error, "response", None) or {}).get("Error", {}).get("Code", ""))
        unavailable = code in UNAVAILABLE_ERROR_CODES
        log_event(
            "inference_failed",
            endpoint=ENDPOINT_NAME,
            error_code=code,
            status=503 if unavailable else 502,
        )
        # Log the AWS error code. Do not return it to the API caller.
        if unavailable:
            return _response(
                503,
                {"error": "model endpoint is unavailable, retry shortly"},
                headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
            )
        return _response(502, {"error": "model endpoint returned an error"})

    try:
        score = float(result["Body"].read().decode().strip())
    except (ValueError, KeyError) as error:
        # Map a nonnumeric endpoint response to HTTP 502.
        log_event("inference_unreadable", endpoint=ENDPOINT_NAME, error=str(error))
        return _response(502, {"error": "model endpoint returned an unreadable response"})

    prediction = {"churn_probability": score, "churn": score >= DEFAULT_THRESHOLD}
    log_event("inference_response", endpoint=ENDPOINT_NAME, **prediction)
    # Capture the final prediction without logging customer input.
    capture(record, prediction)
    return _response(200, prediction)
