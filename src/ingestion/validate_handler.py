"""Validation Lambda: it validates CSV rows and writes them to the curated
bucket or to quarantine.

EventBridge triggers it on S3 ObjectCreated in the raw bucket, through SQS.
Valid rows go to s3://<curated>/telco/<basename>. Invalid rows go to
s3://<curated>/quarantine/<basename> with a `reason` column appended.
"""

import csv
import io
import json
import os
import urllib.parse
from typing import Any

import boto3
from pydantic import ValidationError

from src.common.events import log_event
from src.common.schema import CustomerRecord, format_validation_error

s3 = boto3.client("s3")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]


def validate_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into valid rows and rejected rows. Each rejected row carries
    a `reason`."""
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        try:
            CustomerRecord.model_validate(row)
            valid.append(row)
        except ValidationError as e:
            row["reason"] = format_validation_error(e)
            rejected.append(row)
    return valid, rejected


def _write_csv(bucket: str, key: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode())


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for record in event["Records"]:
        detail = json.loads(record["body"])["detail"]
        bucket = detail["bucket"]["name"]
        key = urllib.parse.unquote_plus(detail["object"]["key"])
        basename = key.rsplit("/", 1)[-1]

        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
        rows = list(csv.DictReader(io.StringIO(body)))
        valid, rejected = validate_rows(rows)

        _write_csv(CURATED_BUCKET, f"telco/{basename}", valid)
        _write_csv(CURATED_BUCKET, f"quarantine/{basename}", rejected)
        results.append({"key": key, "valid": len(valid), "rejected": len(rejected)})
        log_event("rows_validated", **results[-1])
    return {"processed": results}
