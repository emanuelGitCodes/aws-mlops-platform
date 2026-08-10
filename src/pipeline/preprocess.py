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
from src.common.features import FEATURE_COLUMNS, LABEL_COLUMN, encode_features


def encode_labeled_row(row: dict) -> list[float]:
    """Label-first row for XGBoost training CSVs."""
    label = 1.0 if row[LABEL_COLUMN] == "Yes" else 0.0
    return [label, *encode_features(row)]


def split_records(records: list[dict]) -> dict[str, list[dict]]:
    """Create deterministic train, validation, and held-out test splits."""
    shuffled = list(records)
    random.Random(42).shuffle(shuffled)
    n = len(shuffled)
    return {
        "train": shuffled[: int(n * 0.7)],
        "validation": shuffled[int(n * 0.7) : int(n * 0.85)],
        "test": shuffled[int(n * 0.85) :],
    }


def write_preprocessed_splits(splits: dict[str, list[dict]], output_root: str) -> None:
    """Write XGBoost-compatible CSVs and the raw held-out API test fixture."""
    root = pathlib.Path(output_root)
    for name in ("train", "validation", "test"):
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
    for path in glob.glob(f"{input_dir}/*.csv"):
        with open(path) as f:
            records.extend(csv.DictReader(f))

    splits = split_records(records)
    write_preprocessed_splits(splits, "/opt/ml/processing")
    log_event("preprocess_complete", **{name: len(split) for name, split in splits.items()})


if __name__ == "__main__":
    main()
