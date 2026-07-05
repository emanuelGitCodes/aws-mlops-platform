import os

os.environ.setdefault("CURATED_BUCKET", "test-curated")

from unittest import mock

with mock.patch("boto3.client"):
    from src.ingestion.validate_handler import validate_rows

from tests.unit.test_schema import VALID


def test_validate_rows_splits_good_and_bad():
    good = {**VALID, "Churn": "Yes"}
    bad = {**VALID, "gender": "Robot", "Churn": "No"}
    valid, rejected = validate_rows([good, bad])
    assert len(valid) == 1
    assert len(rejected) == 1
    assert "gender" in rejected[0]["reason"]
