"""Validation Lambda: it validates CSV rows and writes them to the curated
bucket or to quarantine.

EventBridge triggers it on S3 ObjectCreated in the raw bucket, through SQS.
Valid rows go to s3://<curated>/telco/<full source key>. Invalid rows go to
s3://<curated>/quarantine/<full source key> with a `reason` column appended.
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
from src.common.features import FEATURE_COLUMNS, LABEL_COLUMN
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
        if LABEL_COLUMN not in row or row[LABEL_COLUMN] in ("", None):
            row["reason"] = f"missing required value: {LABEL_COLUMN}"
            rejected.append(row)
            continue

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


def _flatten_source_key(source_key: str) -> str:
    safe_key = source_key.lstrip("/")
    return urllib.parse.quote(safe_key, safe="")


def _dest_key(prefix: str, source_key: str) -> str:
    return f"{prefix}/{_flatten_source_key(source_key)}"


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for record in event["Records"]:
        detail = json.loads(record["body"])["detail"]
        bucket = detail["bucket"]["name"]
        source_key = urllib.parse.unquote_plus(detail["object"]["key"])

        body = s3.get_object(Bucket=bucket, Key=source_key)["Body"].read().decode()
        reader = csv.DictReader(io.StringIO(body))
        if not reader.fieldnames or not all(
            feature in reader.fieldnames for feature in FEATURE_COLUMNS
        ):
            log_event(
                "rows_unparsable",
                key=source_key,
                reason="missing required feature columns",
            )
            raise ValueError(
                f"unparsable CSV payload for source key {source_key!r}: "
                "missing required feature columns"
            )

        rows = list(reader)
        if not rows:
            log_event("rows_unparsable", key=source_key, reason="no rows parsed")
            raise ValueError(
                f"unparsable CSV payload for source key {source_key!r}: no rows parsed"
            )

        valid, rejected = validate_rows(rows)
        curated_key = _dest_key("telco", source_key)
        quarantine_key = _dest_key("quarantine", source_key)

        if valid:
            _write_csv(CURATED_BUCKET, curated_key, valid)
        else:
            # Delete stale curated data only after parsing and row validation.
            s3.delete_object(Bucket=CURATED_BUCKET, Key=curated_key)
        if rejected:
            _write_csv(CURATED_BUCKET, quarantine_key, rejected)
        else:
            s3.delete_object(Bucket=CURATED_BUCKET, Key=quarantine_key)

        results.append({"key": source_key, "valid": len(valid), "rejected": len(rejected)})
        log_event("rows_validated", **results[-1])
    return {"processed": results}
