"""Score a capture window and emit a drift violation event.

`src.common.drift` owns the statistic. Preprocessing writes the baseline.
The serving proxy writes capture objects. EventBridge invokes this handler on
the configured monitor schedule.
"""

import datetime
import json
import os
import re
from typing import Any
from urllib.parse import unquote, urlparse

import boto3
from botocore.exceptions import ClientError

from src.common.drift import (
    BASELINE_RUN_PREFIX,
    BASELINE_URI_METADATA_KEY,
    DRIFT_STATUS,
    EVENT_DETAIL_TYPE,
    EVENT_SOURCE,
    compare,
    distinct_record_count,
    validate_baseline,
)
from src.common.events import log_event
from src.common.registry import extract_model_package_name

s3 = boto3.client("s3")
events = boto3.client("events")
sm = boto3.client("sagemaker")

ARTIFACTS_BUCKET = os.environ["ARTIFACTS_BUCKET"]
BASELINE_KEY = os.environ["BASELINE_KEY"]
CAPTURE_PREFIX = os.environ["CAPTURE_PREFIX"]
ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]

IN_SERVICE_STATUS = "InService"

# Score this many complete hours before the current hour.
WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "1"))

# Skip windows with fewer captured records than this value.
MIN_RECORDS = int(os.environ.get("MIN_RECORDS", "100"))

# Skip point-mass windows with fewer distinct records than this value.
# `make smoke` can create repeated prediction records.
MIN_DISTINCT_RECORDS = int(os.environ.get("MIN_DISTINCT_RECORDS", "25"))


def window_prefixes(now: datetime.datetime, hours: int) -> list[str]:
    """Return the complete hour prefixes before `now`."""
    return [
        f"{CAPTURE_PREFIX}/{(now - datetime.timedelta(hours=offset)):%Y/%m/%d/%H}/"
        for offset in range(1, hours + 1)
    ]


def read_captured(prefixes: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Read every captured record under the given prefixes."""
    records = []
    unreadable_count = 0
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in prefixes:
        for page in paginator.paginate(Bucket=ARTIFACTS_BUCKET, Prefix=prefix):
            for entry in page.get("Contents", []):
                try:
                    body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=entry["Key"])["Body"].read()
                    records.append(json.loads(body)["record"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    unreadable_count += 1
                    log_event(
                        "capture_object_unreadable",
                        key=entry["Key"],
                        skipped=unreadable_count,
                    )
    return records, unreadable_count


def _endpoint_snapshot() -> tuple[str, str]:
    """Return the configured endpoint status and endpoint-config name."""
    endpoint = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
    status = endpoint.get("EndpointStatus")
    config_name = endpoint.get("EndpointConfigName")
    if not isinstance(status, str) or not isinstance(config_name, str) or not config_name:
        raise ValueError("endpoint status or config is missing")
    return status, config_name


def _skip_unhealthy_endpoint(status: str) -> dict[str, Any]:
    """Record an endpoint that cannot provide a stable serving model."""
    reason = f"endpoint_status_{status.lower()}"
    log_event(
        "drift_endpoint_not_healthy", endpoint=ENDPOINT_NAME, endpoint_status=status, reason=reason
    )
    return {"skipped": "endpoint_not_healthy", "endpoint_status": status, "reason": reason}


def _baseline_key(uri: object, model_package_name: str) -> str:
    """Return a validated key for one versioned baseline URI."""
    parsed = urlparse(uri if isinstance(uri, str) else "")
    path = unquote(parsed.path)
    prefix = f"{BASELINE_RUN_PREFIX}/"
    if (
        parsed.scheme != "s3"
        or parsed.netloc != ARTIFACTS_BUCKET
        or parsed.query
        or parsed.fragment
        or not path.startswith("/")
        or path.startswith("//")
    ):
        log_event(
            "drift_baseline_uri_invalid", package=model_package_name, reason="bucket_or_scheme"
        )
        raise ValueError("baseline URI must use the configured artifacts bucket")
    key = path[1:]
    run_id = key[len(prefix) : -len("/baseline.json")] if key.startswith(prefix) else ""
    if (
        not key.startswith(prefix)
        or not key.endswith("/baseline.json")
        or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id)
    ):
        log_event(
            "drift_baseline_uri_invalid", package=model_package_name, reason="versioned_prefix"
        )
        raise ValueError("baseline URI must name one versioned baseline object")
    return key


def read_baseline(key: str) -> dict[str, Any]:
    """Read and validate one baseline object from the artifacts bucket."""
    try:
        body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=key)["Body"].read()
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "NoSuchKey":
            log_event(
                "drift_baseline_missing",
                bucket=ARTIFACTS_BUCKET,
                key=key,
            )
        raise
    try:
        baseline = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        log_event("drift_baseline_invalid", bucket=ARTIFACTS_BUCKET, key=key, reason="json")
        raise ValueError(
            f"Baseline object s3://{ARTIFACTS_BUCKET}/{key} is invalid JSON"
        ) from error
    try:
        return validate_baseline(baseline)
    except ValueError as error:
        log_event("drift_baseline_invalid", bucket=ARTIFACTS_BUCKET, key=key, reason="schema")
        raise ValueError(
            f"Baseline object s3://{ARTIFACTS_BUCKET}/{key} is invalid: {error}"
        ) from error


def resolve_serving_baseline(endpoint_config_name: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve the baseline bound to the model currently in the endpoint."""
    endpoint_config = sm.describe_endpoint_config(EndpointConfigName=endpoint_config_name)
    variants = endpoint_config.get("ProductionVariants")
    if not isinstance(variants, list) or len(variants) != 1:
        raise ValueError("endpoint config must name exactly one production variant")
    model_name = variants[0].get("ModelName") if isinstance(variants[0], dict) else None
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("endpoint config must name one model")
    model = sm.describe_model(ModelName=model_name)
    model_package_name = extract_model_package_name(model, "serving model")
    package = sm.describe_model_package(ModelPackageName=model_package_name)
    metadata = package.get("CustomerMetadataProperties")
    baseline_uri = metadata.get(BASELINE_URI_METADATA_KEY) if isinstance(metadata, dict) else None
    if not isinstance(baseline_uri, str) or not baseline_uri:
        log_event("drift_baseline_metadata_missing", package=model_package_name)
        raise ValueError(f"model package has no {BASELINE_URI_METADATA_KEY} metadata")
    baseline = read_baseline(_baseline_key(baseline_uri, model_package_name))
    return baseline, {
        "endpoint_config_name": endpoint_config_name,
        "model_name": model_name,
        "model_package_name": model_package_name,
        "baseline_uri": baseline_uri,
    }


def emit_violation(result: dict[str, Any]) -> None:
    """Put the violation event that starts a retraining run."""
    response = events.put_events(
        Entries=[
            {
                "Source": EVENT_SOURCE,
                "DetailType": EVENT_DETAIL_TYPE,
                "Detail": json.dumps({"status": DRIFT_STATUS, **result}),
            }
        ]
    )

    failed_count = response.get("FailedEntryCount", 0)
    if not isinstance(failed_count, int) or failed_count <= 0:
        return

    error = response["Entries"][0].get("ErrorCode", "unknown")
    raise RuntimeError(f"EventBridge rejected {failed_count} drift events: {error}")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    now = datetime.datetime.now(datetime.UTC)
    records, unreadable_count = read_captured(window_prefixes(now, WINDOW_HOURS))
    skipped = {"unreadable_count": unreadable_count}

    if len(records) < MIN_RECORDS:
        # Record an unscored window as a separate outcome.
        log_event("drift_window_too_small", records=len(records), required=MIN_RECORDS)
        return {"skipped": "insufficient_records", "records": len(records), **skipped}

    distinct = distinct_record_count(records)
    if distinct < MIN_DISTINCT_RECORDS:
        # Record a low-diversity window as a separate outcome.
        log_event(
            "drift_window_too_uniform",
            records=len(records),
            distinct=distinct,
            required=MIN_DISTINCT_RECORDS,
        )
        return {
            "skipped": "uniform_records",
            "records": len(records),
            "distinct": distinct,
            **skipped,
        }

    endpoint_status, endpoint_config_name = _endpoint_snapshot()
    if endpoint_status != IN_SERVICE_STATUS:
        return _skip_unhealthy_endpoint(endpoint_status)

    baseline, identity = resolve_serving_baseline(endpoint_config_name)
    result = compare(baseline, records)
    latest_status, latest_config_name = _endpoint_snapshot()
    if latest_status != IN_SERVICE_STATUS:
        return _skip_unhealthy_endpoint(latest_status)
    if latest_config_name != endpoint_config_name:
        log_event(
            "drift_serving_model_changed",
            endpoint=ENDPOINT_NAME,
            previous_endpoint_config=endpoint_config_name,
            current_endpoint_config=latest_config_name,
        )
        return {"skipped": "serving_model_changed", "reason": "endpoint_config_changed"}

    result.update(identity | {"endpoint_name": ENDPOINT_NAME, "unreadable_count": unreadable_count})
    if not result["drifted"]:
        log_event("drift_evaluated", **result)
        return {"drifted": False, **result}

    emit_violation(result)
    log_event("drift_violation", **result)
    return {"drifted": True, **result}
