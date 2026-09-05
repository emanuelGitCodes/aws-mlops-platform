import csv
import json
import random
from unittest import mock

import pytest

from src.common.features import encode_features
from src.common.schema import FEATURE_COLUMNS
from src.pipeline import preprocess
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

    records = [
        {**VALID, "Churn": "Yes" if value % 2 else "No", "tenure": value} for value in range(40)
    ]
    splits = split_records(records)
    write_preprocessed_splits(splits, str(tmp_path))

    baseline = json.loads((tmp_path / "baseline" / "baseline.json").read_text())
    # The baseline describes the training split alone. Validation and test
    # rows are data the model never learned.
    assert baseline["record_count"] == len(splits["train"])
    assert "tenure" in baseline["edges"]

    # It has to be usable by the drift job exactly as written.
    assert compare(baseline, splits["train"])["drifted"] is False


def test_valid_canonical_sized_input_keeps_the_existing_row_mapping():
    records = [
        {**VALID, "Churn": "Yes" if index % 2 else "No", "tenure": index} for index in range(7043)
    ]
    expected = list(records)
    random.Random(42).shuffle(expected)

    splits = split_records(records)

    assert [row["tenure"] for row in splits["train"]] == [row["tenure"] for row in expected[:4930]]
    assert [row["tenure"] for row in splits["validation"]] == [
        row["tenure"] for row in expected[4930:5986]
    ]
    assert [row["tenure"] for row in splits["test"]] == [row["tenure"] for row in expected[5986:]]


def test_imbalanced_input_uses_a_deterministic_class_preserving_fallback():
    indexes = list(range(20))
    random.Random(42).shuffle(indexes)
    positives = set(indexes[:3])
    records = [{**VALID, "Churn": "Yes" if index in positives else "No"} for index in range(20)]

    splits = split_records(records)

    assert {name: len(rows) for name, rows in splits.items()} == {
        "train": 14,
        "validation": 3,
        "test": 3,
    }
    assert all({row["Churn"] for row in rows} == {"No", "Yes"} for rows in splits.values())


def test_input_without_enough_rows_per_class_is_rejected_before_output(tmp_path):
    records = [{**VALID, "Churn": "Yes" if index < 2 else "No"} for index in range(20)]

    with pytest.raises(ValueError, match="3 records in each churn class"):
        split_records(records)

    assert not list(tmp_path.iterdir())


def test_write_rejects_missing_split_names_before_output(tmp_path):
    with pytest.raises(ValueError, match="train, validation, and test"):
        write_preprocessed_splits({"train": [], "test": []}, str(tmp_path / "output"))

    assert not (tmp_path / "output").exists()


def test_write_rejects_undersized_external_splits_before_output(tmp_path):
    rows = {name: [{**VALID, "Churn": "No"}] for name in ("train", "validation", "test")}

    with pytest.raises(ValueError, match="train split requires at least 2 records"):
        write_preprocessed_splits(rows, str(tmp_path / "output"))

    assert not (tmp_path / "output").exists()


def test_minimum_viable_input_produces_two_class_splits():
    records = [{**VALID, "Churn": "Yes" if index < 3 else "No"} for index in range(6)]

    splits = split_records(records)

    assert {name: len(rows) for name, rows in splits.items()} == {
        "train": 2,
        "validation": 2,
        "test": 2,
    }
    assert all({row["Churn"] for row in rows} == {"No", "Yes"} for rows in splits.values())


def test_five_rows_are_rejected_before_any_split_is_returned():
    records = [{**VALID, "Churn": "Yes" if index % 2 else "No"} for index in range(5)]

    with pytest.raises(ValueError, match="at least 6 records"):
        split_records(records)


def test_main_sorts_multiple_input_files_before_splitting(tmp_path):
    records = [
        {**VALID, "Churn": "Yes" if index < 10 else "No", "tenure": index} for index in range(20)
    ]
    paths = [tmp_path / "b.csv", tmp_path / "a.csv"]
    for path, rows in ((paths[0], records[:10]), (paths[1], records[10:])):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)

    captured = []
    for order in (paths, list(reversed(paths))):
        with (
            mock.patch.object(preprocess.glob, "glob", return_value=[str(path) for path in order]),
            mock.patch.object(
                preprocess,
                "write_preprocessed_splits",
                side_effect=lambda splits, _: captured.append(splits),
            ),
            mock.patch.object(preprocess, "log_event"),
        ):
            preprocess.main()

    assert captured[0] == captured[1]
