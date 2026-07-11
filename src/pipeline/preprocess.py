"""Preprocessing: curated Telco CSV -> train/validation/test CSVs for XGBoost.

`encode_features` is dependency-free (no pandas) so the serving proxy Lambda
can reuse the exact same encoding at inference time.

As a SageMaker ProcessingStep this runs as a script: reads curated CSVs from
/opt/ml/processing/input, writes label-first headerless CSVs (XGBoost's
expected format) to /opt/ml/processing/{train,validation,test}.
"""

import csv
import glob
import os
import random

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


def main():
    input_dir = "/opt/ml/processing/input"
    rows = []
    for path in glob.glob(f"{input_dir}/*.csv"):
        with open(path) as f:
            rows.extend(encode_labeled_row(r) for r in csv.DictReader(f))

    random.Random(42).shuffle(rows)
    n = len(rows)
    splits = {
        "train": rows[: int(n * 0.7)],
        "validation": rows[int(n * 0.7) : int(n * 0.85)],
        "test": rows[int(n * 0.85) :],
    }
    for name, split in splits.items():
        out_dir = f"/opt/ml/processing/{name}"
        os.makedirs(out_dir, exist_ok=True)
        with open(f"{out_dir}/{name}.csv", "w", newline="") as f:
            csv.writer(f).writerows(split)
    print({name: len(split) for name, split in splits.items()})


if __name__ == "__main__":
    main()
