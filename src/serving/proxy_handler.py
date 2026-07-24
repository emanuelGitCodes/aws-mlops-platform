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
from src.common.features import DEFAULT_THRESHOLD
from src.common.schema import (
    FEATURE_COLUMNS,
    CustomerRecord,
    format_validation_error,
)
from src.pipeline.preprocess import encode_features

runtime = boto3.client("sagemaker-runtime")

ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
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

    result = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="text/csv",
        Body=csv_line,
    )
    score = float(result["Body"].read().decode().strip())
    prediction = {"churn_probability": score, "churn": score >= DEFAULT_THRESHOLD}
    log_event("inference_response", endpoint=ENDPOINT_NAME, **prediction)
    return _response(200, prediction)
