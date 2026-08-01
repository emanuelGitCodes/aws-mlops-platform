"""Dependency-free feature contract shared by training and serving.

Keep the ordered model columns separate from the Pydantic validation model so
SageMaker preprocessing can import the training contract in the stock sklearn
image, which does not include Pydantic.

This module owns the *whole* raw-value contract: which columns exist, which
values each one accepts, and how those values become numbers. Validation and
encoding used to live apart -- the schema in ``schema.py``, the maps in
``pipeline/preprocess.py`` -- and drifted: the schema typed ten categorical
columns as bare ``str``, so a plausible-looking value such as
``Contract="Three year"`` validated cleanly and then raised ``KeyError`` in
the encoder. Keeping both here means the accepted vocabulary and the
encodable vocabulary cannot disagree; ``tests/unit/test_features.py`` asserts
they still don't.
"""

# This module is imported by the SageMaker ProcessingStep entrypoints, whose
# managed image runs an older Python than the 3.12 the rest of the repo
# targets. Deferring annotation evaluation keeps modern syntax safe here.
from __future__ import annotations

from typing import Any

# Order matters: this is the feature order used for both training and inference.
FEATURE_COLUMNS = [
    "gender",
    "SeniorCitizen",
    "Partner",
    "Dependents",
    "tenure",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
    "MonthlyCharges",
    "TotalCharges",
]
LABEL_COLUMN = "Churn"

# Decision rule shared by serving and evaluation: churn iff score >= threshold.
DEFAULT_THRESHOLD = 0.5

YES_NO = frozenset({"Yes", "No"})
NO_PHONE_SERVICE = "No phone service"
NO_INTERNET_SERVICE = "No internet service"

# Fixed ordinal maps: deterministic, no fitted state to ship to the Lambda.
YES_NO_MAP = {"No": 0, "Yes": 1, NO_PHONE_SERVICE: 2, NO_INTERNET_SERVICE: 2}
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

# Columns whose "No" variant the source data spells out. These are the reason
# the vocabulary is per-column rather than one shared Yes/No set: only
# MultipleLines may say "No phone service", and only the six add-on services
# may say "No internet service". A single shared set would quietly start
# accepting `Partner="No internet service"`.
_INTERNET_ADDON_COLUMNS = (
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
)

# The raw values each categorical column accepts. Numeric columns are absent:
# their contract is the range check on the Pydantic model, not a value set.
FEATURE_VOCABULARY: dict[str, frozenset[str]] = {
    **{column: YES_NO for column in ("Partner", "Dependents", "PhoneService", "PaperlessBilling")},
    "MultipleLines": YES_NO | {NO_PHONE_SERVICE},
    **{column: YES_NO | {NO_INTERNET_SERVICE} for column in _INTERNET_ADDON_COLUMNS},
    **{column: frozenset(values) for column, values in CATEGORY_MAPS.items()},
}


def encode_features(row: dict[str, Any]) -> list[float]:
    """Encode one record (dict of raw feature values) into the numeric vector.

    Dependency-free (no pandas) so the serving proxy Lambda can reuse the exact
    same encoding at inference time that training used.
    """
    out = []
    for col in FEATURE_COLUMNS:
        v = row[col]
        if col in NUMERIC:
            out.append(float(v) if str(v).strip() else 0.0)
            continue
        table = CATEGORY_MAPS[col] if col in CATEGORY_MAPS else YES_NO_MAP
        if v not in table:
            # Reachable only if a caller skipped CustomerRecord validation:
            # name the column, rather than surfacing a bare KeyError.
            raise ValueError(f"{col}: value not in the feature vocabulary: {v!r}")
        out.append(float(table[v]))
    return out
