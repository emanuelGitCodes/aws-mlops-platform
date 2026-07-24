"""Preprocessing: curated Telco CSV -> train/validation/test CSVs for XGBoost.

`encode_features` is dependency-free (no pandas) so the serving proxy Lambda
can reuse the exact same encoding at inference time.

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

from src.common.features import FEATURE_COLUMNS, LABEL_COLUMN

# Fixed ordinal maps: deterministic, no fitted state to ship to the Lambda.
YES_NO_MAP = {"No": 0, "Yes": 1, "No phone service": 2, "No internet service": 2}
CATEGORY_MAPS = {
    "gender": {"Female": 0, "Male": 1},
    "InternetService": {"No": 0, "DSL": 1, "Fiber optic": 2},
    "Contract": {"Month-to-month": 0, "One year": 1, "Two year": 2},
    "PaymentMethod": {
        "Electronic check": 0,
        "Mailed check": 1,
        "Bank transfer (automatic)": 2,
        "Credit card (automatic)": 3,
    },
}
NUMERIC = {"SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges"}


def encode_features(row: dict) -> list[float]:
    """Encode one record (dict of raw feature values) into the numeric vector."""
    out = []
    for col in FEATURE_COLUMNS:
        v = row[col]
        if col in NUMERIC:
            out.append(float(v) if str(v).strip() else 0.0)
        elif col in CATEGORY_MAPS:
            out.append(float(CATEGORY_MAPS[col][v]))
        else:
            out.append(float(YES_NO_MAP[v]))
    return out


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
    print({name: len(split) for name, split in splits.items()})


if __name__ == "__main__":
    main()
