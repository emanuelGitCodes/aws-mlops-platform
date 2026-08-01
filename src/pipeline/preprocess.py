"""Preprocessing: curated Telco CSV -> train/validation/test CSVs for XGBoost.

The encoding itself lives in `src.common.features` alongside the vocabulary it
depends on, so the serving proxy Lambda reuses the exact same encoding at
inference time. This module is the training-only half: labels and splits.

As a SageMaker ProcessingStep this runs as a script: reads curated CSVs from
/opt/ml/processing/input, writes label-first headerless CSVs (XGBoost's
expected format) to /opt/ml/processing/{train,validation,test}.
"""

# This module runs inside the SageMaker FrameworkProcessor managed image,
# whose Python is older than the 3.12 the rest of the repo targets. Deferring
# annotation evaluation keeps modern syntax here from being a runtime error.
from __future__ import annotations

import csv
import glob
import json
import pathlib
import random
from typing import Any

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

    # This contains only fields accepted by the public prediction API. Keeping
    # the label separate makes it possible to evaluate a deployed endpoint
    # without reversing the lossy categorical encoding used for XGBoost.
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
