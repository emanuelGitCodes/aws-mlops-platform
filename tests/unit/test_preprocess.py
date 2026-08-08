import json

from src.common.features import encode_features
from src.common.schema import FEATURE_COLUMNS
from src.pipeline.preprocess import (
    encode_labeled_row,
    split_records,
    write_preprocessed_splits,
)
from tests.unit.conftest import VALID


def test_encode_features_length_and_numeric():
    vec = encode_features(VALID)
    assert len(vec) == len(FEATURE_COLUMNS)
    assert all(isinstance(v, float) for v in vec)


def test_encode_labeled_row_label_first():
    row = encode_labeled_row({**VALID, "Churn": "Yes"})
    assert row[0] == 1.0
    assert row[1:] == encode_features(VALID)

    row = encode_labeled_row({**VALID, "Churn": "No"})
    assert row[0] == 0.0


def test_no_internet_service_maps():
    vec = encode_features({**VALID, "OnlineSecurity": "No internet service"})
    idx = FEATURE_COLUMNS.index("OnlineSecurity")
    assert vec[idx] == 2.0


def test_preprocess_writes_raw_labeled_api_test_fixture(tmp_path):
    records = [{**VALID, "Churn": "Yes" if index % 2 else "No"} for index in range(20)]
    splits = split_records(records)
    write_preprocessed_splits(splits, str(tmp_path))

    assert {name: len(rows) for name, rows in splits.items()} == {
        "train": 14,
        "validation": 3,
        "test": 3,
    }
    assert len((tmp_path / "test" / "test.csv").read_text().splitlines()) == 3
    fixture_path = tmp_path / "api_test" / "api_test.jsonl"
    fixture = [json.loads(line) for line in fixture_path.read_text().splitlines()]
    assert [row["row_id"] for row in fixture] == [0, 1, 2]
    assert {key for key in fixture[0]["record"]} == set(FEATURE_COLUMNS)
    assert fixture[0]["label"] in {0, 1}


def test_preprocess_writes_the_drift_baseline(tmp_path):
    from src.common.drift import compare

    records = [{**VALID, "Churn": "No", "tenure": value} for value in range(40)]
    splits = split_records(records)
    write_preprocessed_splits(splits, str(tmp_path))

    baseline = json.loads((tmp_path / "baseline" / "baseline.json").read_text())
    # The baseline describes the training split alone. Validation and test
    # rows are data the model never learned.
    assert baseline["record_count"] == len(splits["train"])
    assert "tenure" in baseline["edges"]

    # It has to be usable by the drift job exactly as written.
    assert compare(baseline, splits["train"])["drifted"] is False
