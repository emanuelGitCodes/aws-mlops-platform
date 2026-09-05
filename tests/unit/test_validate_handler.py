import csv
import io
import json
import urllib.parse
from unittest import mock

import pytest

from src.common.features import FEATURE_COLUMNS
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


def _feature_header() -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FEATURE_COLUMNS)
    writer.writeheader()
    return buf.getvalue().encode()


def _sqs_event(bucket: str, key: str) -> dict:
    detail = {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}
    return {"Records": [{"body": json.dumps(detail)}]}


def _dest_key(prefix: str, source_key: str) -> str:
    return f"{prefix}/{urllib.parse.quote(source_key.lstrip('/'), safe='')}"


def test_handler_writes_curated_and_quarantine():
    rows = [
        {**VALID, "Churn": "Yes"},
        {**VALID, "tenure": "-1", "Churn": "No"},
    ]
    s3 = mock.Mock()
    s3.get_object.side_effect = [
        {"Body": io.BytesIO(_csv_bytes(rows))},
        {"Body": io.BytesIO(_csv_bytes(rows))},
    ]

    with mock.patch.object(validate_handler, "s3", s3):
        result = validate_handler.handler(_sqs_event("raw-bucket", "drops/telco.csv"), None)

    assert result["processed"] == [{"key": "drops/telco.csv", "valid": 1, "rejected": 1}]

    puts = {c.kwargs["Key"]: c.kwargs for c in s3.put_object.call_args_list}
    assert set(puts) == {
        _dest_key("telco", "drops/telco.csv"),
        _dest_key("quarantine", "drops/telco.csv"),
    }
    assert all(c["Bucket"] == "test-curated" for c in puts.values())
    assert b"reason" in puts[_dest_key("quarantine", "drops/telco.csv")]["Body"]


def test_handler_rejects_unparsable_upload_and_reports_rows_unparsable():
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_feature_header())}

    with (
        mock.patch.object(validate_handler, "s3", s3),
        mock.patch.object(validate_handler, "log_event") as log_event,
    ):
        with pytest.raises(
            ValueError,
            match=r"unparsable CSV payload for source key 'raw/empty.csv': no rows "
            r"parsed",
        ):
            validate_handler.handler(_sqs_event("raw-bucket", "raw/empty.csv"), None)

    assert log_event.call_count == 1
    assert log_event.call_args.args[0] == "rows_unparsable"
    assert log_event.call_args.kwargs["key"] == "raw/empty.csv"
    assert log_event.call_args.kwargs["reason"] == "no rows parsed"
    s3.delete_object.assert_not_called()


def test_handler_rejects_payloads_without_feature_columns():
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(b"foo,bar\\nalpha,beta\\n")}

    with (
        mock.patch.object(validate_handler, "s3", s3),
        mock.patch.object(validate_handler, "log_event") as log_event,
    ):
        with pytest.raises(
            ValueError,
            match=r"unparsable CSV payload for source key 'raw/weird.csv': "
            r"missing required feature columns",
        ):
            validate_handler.handler(_sqs_event("raw-bucket", "raw/weird.csv"), None)

    assert log_event.call_count == 1
    assert log_event.call_args.args[0] == "rows_unparsable"
    assert log_event.call_args.kwargs["key"] == "raw/weird.csv"
    assert log_event.call_args.kwargs["reason"] == "missing required feature columns"


def test_handler_rejects_rows_that_missing_churn_label():
    rows = [{**VALID}]
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_csv_bytes(rows))}

    with mock.patch.object(validate_handler, "s3", s3):
        result = validate_handler.handler(_sqs_event("raw-bucket", "raw/label.csv"), None)

    assert result["processed"] == [{"key": "raw/label.csv", "valid": 0, "rejected": 1}]
    puts = {c.kwargs["Key"]: c.kwargs for c in s3.put_object.call_args_list}
    expected_key = _dest_key("quarantine", "raw/label.csv")
    assert set(puts) == {expected_key}
    assert b"missing required value: Churn" in puts[expected_key]["Body"]


def test_handler_writes_distinct_source_keys_from_full_raw_key():
    rows = [
        {**VALID, "Churn": "Yes"},
        {**VALID, "tenure": "-1", "Churn": "No"},
    ]
    s3 = mock.Mock()
    s3.get_object.side_effect = [
        {"Body": io.BytesIO(_csv_bytes(rows))},
        {"Body": io.BytesIO(_csv_bytes(rows))},
    ]

    with mock.patch.object(validate_handler, "s3", s3):
        validate_handler.handler(
            {
                "Records": [
                    _sqs_event("raw-bucket", "a/telco.csv")["Records"][0],
                    _sqs_event("raw-bucket", "b/telco.csv")["Records"][0],
                ]
            },
            None,
        )

    puts = {c.kwargs["Key"] for c in s3.put_object.call_args_list}
    expected = {
        _dest_key("telco", "a/telco.csv"),
        _dest_key("quarantine", "a/telco.csv"),
        _dest_key("telco", "b/telco.csv"),
        _dest_key("quarantine", "b/telco.csv"),
    }
    assert puts == expected
    assert len({_dest_key("telco", "a/telco.csv"), _dest_key("telco", "b/telco.csv")}) == 2
    assert all(key.count("/") == 1 for key in puts)


def test_handler_deletes_stale_quarantine_when_clean():
    key = "reupload/telco.csv"
    s3 = mock.Mock()
    s3.get_object.side_effect = [
        {"Body": io.BytesIO(_csv_bytes([{**VALID, "tenure": "-1", "Churn": "No"}]))},
        {"Body": io.BytesIO(_csv_bytes([{**VALID, "Churn": "Yes"}]))},
    ]

    with mock.patch.object(validate_handler, "s3", s3):
        validate_handler.handler(_sqs_event("raw-bucket", key), None)
        validate_handler.handler(_sqs_event("raw-bucket", key), None)

    assert {
        "Bucket": "test-curated",
        "Key": _dest_key("quarantine", key),
    } in [c.kwargs for c in s3.delete_object.call_args_list]


def test_handler_deletes_stale_curated_when_replacement_is_all_invalid():
    key = "reupload/telco.csv"
    s3 = mock.Mock()
    s3.get_object.side_effect = [
        {"Body": io.BytesIO(_csv_bytes([{**VALID, "Churn": "Yes"}]))},
        {"Body": io.BytesIO(_csv_bytes([{**VALID, "tenure": "-1", "Churn": "No"}]))},
    ]

    with mock.patch.object(validate_handler, "s3", s3):
        validate_handler.handler(_sqs_event("raw-bucket", key), None)
        validate_handler.handler(_sqs_event("raw-bucket", key), None)

    assert {
        "Bucket": "test-curated",
        "Key": _dest_key("telco", key),
    } in [c.kwargs for c in s3.delete_object.call_args_list]
    quarantine_put = [
        call.kwargs
        for call in s3.put_object.call_args_list
        if call.kwargs["Key"] == _dest_key("quarantine", key)
    ]
    assert len(quarantine_put) == 1


def test_handler_propagates_failure_to_delete_stale_curated_data():
    s3 = mock.Mock()
    s3.get_object.return_value = {
        "Body": io.BytesIO(_csv_bytes([{**VALID, "tenure": "-1", "Churn": "No"}]))
    }
    s3.delete_object.side_effect = RuntimeError("curated bucket unavailable")

    with mock.patch.object(validate_handler, "s3", s3):
        with pytest.raises(RuntimeError, match="curated bucket unavailable"):
            validate_handler.handler(_sqs_event("raw-bucket", "telco.csv"), None)

    s3.put_object.assert_not_called()


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
