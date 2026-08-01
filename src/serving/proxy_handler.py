"""Thin proxy Lambda: API Gateway -> SageMaker serverless endpoint.

Validates the request against the shared schema, shapes it into the CSV
feature vector XGBoost expects, invokes the endpoint, and returns the churn
probability. No inference logic lives here.
"""

import json
import os
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

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]

# SageMaker Runtime failures that mean "not ready yet" rather than "this
# request is wrong". These are routine rather than exceptional on a serverless
# endpoint: every approved challenger triggers an endpoint update, and
# invocations during that window fail until the new variant is live. A missing
# or not-yet-InService endpoint is reported as ValidationError, not as a
# modelled not-found error, so it has to be listed here too.
UNAVAILABLE_ERROR_CODES = frozenset(
    {
        "ModelNotReadyException",
        "ServiceUnavailable",
        "ThrottlingException",
        "TooManyRequestsException",
        "ValidationError",
    }
)

# Seconds. A serverless cold start or an endpoint update is over in well under
# a minute; this only has to stop a client from retrying instantly.
RETRY_AFTER_SECONDS = 15


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

    # Unguarded, this call surfaced every SageMaker failure to the caller as a
    # 502 with a Lambda stack trace -- including the endpoint-updating window,
    # which this architecture enters on every promotion.
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
        # The AWS error code is logged, not returned: it is operator detail on
        # a public endpoint.
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
        # The endpoint answered, but not with a probability -- a wrong model or
        # a wrong content type. Not retryable, so not a 503.
        log_event("inference_unreadable", endpoint=ENDPOINT_NAME, error=str(error))
        return _response(502, {"error": "model endpoint returned an unreadable response"})

    prediction = {"churn_probability": score, "churn": score >= DEFAULT_THRESHOLD}
    log_event("inference_response", endpoint=ENDPOINT_NAME, **prediction)
    return _response(200, prediction)
