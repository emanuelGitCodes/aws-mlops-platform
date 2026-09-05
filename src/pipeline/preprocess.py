"""Convert the curated Telco CSV into XGBoost data splits.

`src.common.features` owns the shared encoding and vocabulary. This module owns
the training labels and data splits.

This runs as a script inside a SageMaker ProcessingStep. It reads curated CSVs
from /opt/ml/processing/input. It writes label-first headerless CSVs, the
format XGBoost expects, to /opt/ml/processing/{train,validation,test}.
"""

# The SageMaker managed image uses an older Python version.
# Deferred annotations preserve compatibility with that image.
from __future__ import annotations

import csv
import glob
import json
import pathlib
import random
from typing import Any

from src.common.drift import build_baseline
from src.common.events import log_event
from src.common.features import FEATURE_COLUMNS, LABEL_COLUMN, YES_NO, encode_features

SPLIT_NAMES = ("train", "validation", "test")
MIN_SPLIT_SIZE = 2


def encode_labeled_row(row: dict[str, Any]) -> list[float]:
    """Label-first row for XGBoost training CSVs."""
    label = 1.0 if row[LABEL_COLUMN] == "Yes" else 0.0
    return [label, *encode_features(row)]


def _validate_splits(splits: dict[str, list[dict[str, Any]]]) -> None:
    """Reject splits that cannot train and evaluate a binary classifier."""
    if set(splits) != set(SPLIT_NAMES):
        raise ValueError("splits must contain train, validation, and test")
    for name in SPLIT_NAMES:
        rows = splits[name]
        if len(rows) < MIN_SPLIT_SIZE:
            raise ValueError(f"{name} split requires at least {MIN_SPLIT_SIZE} records")
        if {row[LABEL_COLUMN] for row in rows} != YES_NO:
            raise ValueError(f"{name} split requires both No and Yes churn classes")


def _split_sizes(record_count: int) -> tuple[int, int, int]:
    """Return split sizes with the minimum rows reserved for each split."""
    train = int(record_count * 0.7)
    validation = int(record_count * 0.85) - train
    test = record_count - train - validation
    if min(train, validation, test) < MIN_SPLIT_SIZE:
        validation = max(validation, MIN_SPLIT_SIZE)
        test = max(test, MIN_SPLIT_SIZE)
        train = record_count - validation - test
    if min(train, validation, test) < MIN_SPLIT_SIZE:
        raise ValueError("input requires at least 6 records for the three splits")
    return train, validation, test


def _class_preserving_splits(
    shuffled: list[dict[str, Any]], sizes: tuple[int, int, int]
) -> dict[str, list[dict[str, Any]]]:
    """Assign rows to fixed-size splits while keeping both churn classes."""
    by_label: dict[str, list[tuple[int, dict[str, Any]]]] = {label: [] for label in sorted(YES_NO)}
    for index, row in enumerate(shuffled):
        label = row[LABEL_COLUMN]
        if label not in by_label:
            raise ValueError("input must contain only No and Yes churn labels")
        by_label[label].append((index, row))
    if any(len(rows) < len(SPLIT_NAMES) for rows in by_label.values()):
        raise ValueError("input needs at least 3 records in each churn class")

    splits: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLIT_NAMES}
    used: set[int] = set()
    for rows in by_label.values():
        for split_index, name in enumerate(SPLIT_NAMES):
            index, row = rows[split_index]
            splits[name].append(row)
            used.add(index)
    split_index = 0
    for index, row in enumerate(shuffled):
        if index in used:
            continue
        while len(splits[SPLIT_NAMES[split_index]]) >= sizes[split_index]:
            split_index = (split_index + 1) % len(SPLIT_NAMES)
        splits[SPLIT_NAMES[split_index]].append(row)
        split_index = (split_index + 1) % len(SPLIT_NAMES)
    return splits


def split_records(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Create deterministic train, validation, and held-out test splits."""
    shuffled = list(records)
    random.Random(42).shuffle(shuffled)
    train_size, validation_size, test_size = _split_sizes(len(shuffled))
    splits = {
        "train": shuffled[:train_size],
        "validation": shuffled[train_size : train_size + validation_size],
        "test": shuffled[train_size + validation_size :],
    }
    try:
        _validate_splits(splits)
    except ValueError:
        splits = _class_preserving_splits(shuffled, (train_size, validation_size, test_size))
        _validate_splits(splits)
    return splits


def write_preprocessed_splits(splits: dict[str, list[dict[str, Any]]], output_root: str) -> None:
    """Write XGBoost-compatible CSVs and the raw held-out API test fixture."""
    _validate_splits(splits)
    root = pathlib.Path(output_root)
    for name in SPLIT_NAMES:
        out_dir = root / name
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{name}.csv", "w", newline="") as f:
            csv.writer(f).writerows(encode_labeled_row(row) for row in splits[name])

    # Store API fields and labels separately in the held-out fixture.
    api_test_dir = root / "api_test"
    api_test_dir.mkdir(parents=True, exist_ok=True)
    with open(api_test_dir / "api_test.jsonl", "w") as f:
        for row_id, row in enumerate(splits["test"]):
            json.dump(
                {
                    "row_id": row_id,
                    "record": {column: row[column] for column in FEATURE_COLUMNS},
                    "label": int(row[LABEL_COLUMN] == "Yes"),
                },
                f,
            )
            f.write("\n")

    # Build the drift baseline from the training split only.
    baseline_dir = root / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    with open(baseline_dir / "baseline.json", "w") as f:
        json.dump(build_baseline(splits["train"]), f)


def main() -> None:
    input_dir = "/opt/ml/processing/input"
    records: list[dict[str, Any]] = []
    for path in sorted(glob.glob(f"{input_dir}/*.csv")):
        with open(path) as f:
            records.extend(csv.DictReader(f))

    splits = split_records(records)
    write_preprocessed_splits(splits, "/opt/ml/processing")
    log_event("preprocess_complete", **{name: len(split) for name, split in splits.items()})


if __name__ == "__main__":
    main()
