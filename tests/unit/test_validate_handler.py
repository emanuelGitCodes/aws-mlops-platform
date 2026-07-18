import csv
import io
import json
from unittest import mock

from tests.unit.conftest import VALID, import_with_stubbed_boto3

validate_handler = import_with_stubbed_boto3("src.ingestion.validate_handler")


def test_validate_rows_splits_good_and_bad():
    good = {**VALID, "Churn": "Yes"}
    bad = {**VALID, "gender": "Robot", "Churn": "No"}
    valid, rejected = validate_handler.validate_rows([good, bad])
    assert len(valid) == 1
    assert len(rejected) == 1
    assert "gender" in rejected[0]["reason"]


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _sqs_event(bucket: str, key: str) -> dict:
    detail = {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}
    return {"Records": [{"body": json.dumps(detail)}]}


def test_handler_writes_curated_and_quarantine():
    rows = [
        {**VALID, "Churn": "Yes"},
        {**VALID, "tenure": "-1", "Churn": "No"},
    ]
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_csv_bytes(rows))}

    with mock.patch.object(validate_handler, "s3", s3):
        result = validate_handler.handler(_sqs_event("raw-bucket", "drops/telco.csv"), None)

    assert result["processed"] == [{"key": "drops/telco.csv", "valid": 1, "rejected": 1}]

    puts = {c.kwargs["Key"]: c.kwargs for c in s3.put_object.call_args_list}
    assert set(puts) == {"telco/telco.csv", "quarantine/telco.csv"}
    assert all(c["Bucket"] == "test-curated" for c in puts.values())
    assert b"reason" in puts["quarantine/telco.csv"]["Body"]


def test_handler_all_valid_skips_quarantine_write():
    rows = [{**VALID, "Churn": "No"}]
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_csv_bytes(rows))}

    with mock.patch.object(validate_handler, "s3", s3):
        validate_handler.handler(_sqs_event("raw-bucket", "telco.csv"), None)

    keys = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    assert keys == ["telco/telco.csv"]


def test_handler_url_decodes_object_key():
    rows = [{**VALID, "Churn": "No"}]
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_csv_bytes(rows))}

    with mock.patch.object(validate_handler, "s3", s3):
        validate_handler.handler(_sqs_event("raw-bucket", "drops/my+file.csv"), None)

    assert s3.get_object.call_args.kwargs["Key"] == "drops/my file.csv"
