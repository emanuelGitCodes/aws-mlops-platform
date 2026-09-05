"""Score a capture window and emit a drift violation event.

`src.common.drift` owns the statistic. Preprocessing writes the baseline.
The serving proxy writes capture objects. EventBridge invokes this handler on
the configured monitor schedule.
"""

import datetime
import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.common.drift import (
    DRIFT_STATUS,
    EVENT_DETAIL_TYPE,
    EVENT_SOURCE,
    compare,
    distinct_record_count,
)
from src.common.events import log_event

s3 = boto3.client("s3")
events = boto3.client("events")

ARTIFACTS_BUCKET = os.environ["ARTIFACTS_BUCKET"]
BASELINE_KEY = os.environ["BASELINE_KEY"]
CAPTURE_PREFIX = os.environ["CAPTURE_PREFIX"]

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


def read_baseline() -> dict[str, Any]:
    """Read the baseline the preprocessing step wrote."""
    try:
        body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=BASELINE_KEY)["Body"].read()
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "NoSuchKey":
            log_event(
                "drift_baseline_missing",
                bucket=ARTIFACTS_BUCKET,
                key=BASELINE_KEY,
            )
        raise
    baseline: dict[str, Any] = json.loads(body)
    if not isinstance(baseline.get("counts"), dict) or not baseline.get("counts"):
        raise ValueError(
            f"Baseline object s3://{ARTIFACTS_BUCKET}/{BASELINE_KEY} "
            "must include non-empty 'counts' mapping."
        )
    record_count = baseline.get("record_count")
    if not isinstance(record_count, int) or record_count < 1:
        raise ValueError(
            f"Baseline object s3://{ARTIFACTS_BUCKET}/{BASELINE_KEY} "
            "must include integer 'record_count' above 0."
        )
    return baseline


def emit_violation(result: dict[str, Any]) -> None:
    """Put the violation event that starts a retraining run."""
    events.put_events(
        Entries=[
            {
                "Source": EVENT_SOURCE,
                "DetailType": EVENT_DETAIL_TYPE,
                "Detail": json.dumps({"status": DRIFT_STATUS, **result}),
            }
        ]
    )


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

    result = compare(read_baseline(), records)
    result["unreadable_count"] = unreadable_count
    if not result["drifted"]:
        log_event("drift_evaluated", **result)
        return {"drifted": False, **result}

    emit_violation(result)
    log_event("drift_violation", **result)
    return {"drifted": True, **result}
