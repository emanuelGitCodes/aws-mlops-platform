"""Drift Lambda: it scores a capture window against the training baseline and
emits a violation event.

This replaces SageMaker Model Monitor, which supports neither serverless
endpoints nor new customers. The statistic lives in ``src.common.drift``, the
baseline comes from the preprocessing step, and the capture objects come from
``src.serving.proxy_handler``.

EventBridge invokes this on the schedule in ``monitor.schedule_cron``. A
violation goes back to EventBridge as the platform's own event, which
``src.monitoring.retrain_handler`` consumes.
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

# The window this job scores, in hours. It matches the schedule, so successive
# runs read successive hours and no captured record is scored twice.
WINDOW_HOURS = int(os.environ.get("WINDOW_HOURS", "1"))

# Below this many captured records the window is not scored at all. A
# serverless endpoint is idle most of the time, so most windows are small or
# empty, and PSI over a handful of rows reports drift that is sampling noise.
# Reporting "not enough data" is a distinct outcome from "no drift".
MIN_RECORDS = int(os.environ.get("MIN_RECORDS", "100"))

# Below this many *distinct* records the window is not scored either. Counting
# records is not enough: a caller that repeats one payload produces a point
# mass, every column's PSI explodes, and the drifted-column fraction cannot
# help because every column moved. `make smoke` posts one fixed payload, so a
# health check on `/predict` is the realistic source of such a window.
#
# Measured against the live curated data: windows of 50 to 1000 real records
# were 100 percent distinct, and the repeated-payload case is 1. This sits
# between them with a wide margin on both sides.
MIN_DISTINCT_RECORDS = int(os.environ.get("MIN_DISTINCT_RECORDS", "25"))


def window_prefixes(now: datetime.datetime, hours: int) -> list[str]:
    """Return the hour-partition prefixes covering the window before ``now``.

    Listing per hour keeps the job off the whole capture prefix, which grows
    without bound.
    """
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
        # Not an error, and not a clean bill of health either. Both readings
        # need to stay distinguishable in the log.
        log_event("drift_window_too_small", records=len(records), required=MIN_RECORDS)
        return {"skipped": "insufficient_records", "records": len(records)}

    distinct = distinct_record_count(records)
    if distinct < MIN_DISTINCT_RECORDS:
        # A third outcome, kept separate from the other two. This window holds
        # enough records to score and still must not be scored.
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
