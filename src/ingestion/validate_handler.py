"""Validation Lambda: SQS-wrapped S3 events -> validate CSV rows -> curated or quarantine.

Triggered by EventBridge (S3 ObjectCreated on the raw bucket) buffered through SQS.
Valid rows go to s3://<curated>/telco/<basename>; invalid rows to
s3://<curated>/quarantine/<basename> with a `reason` column appended.
"""

import csv
import io
import json
import os
import urllib.parse

import boto3
from pydantic import ValidationError

from src.common.schema import CustomerRecord, format_validation_error

s3 = boto3.client("s3")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]


def validate_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split rows into (valid, rejected-with-reason)."""
    valid, rejected = [], []
    for row in rows:
        try:
            CustomerRecord.model_validate(row)
            valid.append(row)
        except ValidationError as e:
            row["reason"] = format_validation_error(e)
            rejected.append(row)
    return valid, rejected


def _write_csv(bucket: str, key: str, rows: list[dict]) -> None:
    if not rows:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode())


def handler(event, context):
    results = []
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
        print(json.dumps(results[-1]))
    return {"processed": results}
