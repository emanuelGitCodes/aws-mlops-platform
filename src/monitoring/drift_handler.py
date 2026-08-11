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


def read_captured(prefixes: list[str]) -> list[dict[str, Any]]:
    """Read every captured record under the given prefixes."""
    records = []
    paginator = s3.get_paginator("list_objects_v2")
    for prefix in prefixes:
        for page in paginator.paginate(Bucket=ARTIFACTS_BUCKET, Prefix=prefix):
            for entry in page.get("Contents", []):
                body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=entry["Key"])["Body"].read()
                records.append(json.loads(body)["record"])
    return records


def read_baseline() -> dict[str, Any]:
    """Read the baseline the preprocessing step wrote."""
    body = s3.get_object(Bucket=ARTIFACTS_BUCKET, Key=BASELINE_KEY)["Body"].read()
    baseline: dict[str, Any] = json.loads(body)
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
    records = read_captured(window_prefixes(now, WINDOW_HOURS))

    if len(records) < MIN_RECORDS:
        # Record an unscored window as a separate outcome.
        log_event("drift_window_too_small", records=len(records), required=MIN_RECORDS)
        return {"skipped": "insufficient_records", "records": len(records)}

    distinct = distinct_record_count(records)
    if distinct < MIN_DISTINCT_RECORDS:
        # Record a low-diversity window as a separate outcome.
        log_event(
            "drift_window_too_uniform",
            records=len(records),
            distinct=distinct,
            required=MIN_DISTINCT_RECORDS,
        )
        return {"skipped": "uniform_records", "records": len(records), "distinct": distinct}

    result = compare(read_baseline(), records)
    if not result["drifted"]:
        log_event("drift_evaluated", **result)
        return {"drifted": False, **result}

    emit_violation(result)
    log_event("drift_violation", **result)
    return {"drifted": True, **result}
