"""Dependency-free feature contract shared by training and serving.

Keep the ordered model columns separate from the Pydantic model, so SageMaker
preprocessing can import the training contract in the stock sklearn image. That
image does not include Pydantic.

This module owns the whole raw-value contract: which columns exist, which
values each one accepts, and how those values become numbers. Keep validation
and encoding together here. Apart, they drift, and a value the schema accepts
raises ``KeyError`` in the encoder. ``tests/unit/test_features.py`` asserts
that the accepted vocabulary and the encodable vocabulary stay equal.
"""

# The SageMaker ProcessingStep entrypoints import this module. Their managed
# image runs an older Python than 3.12. Deferred annotations keep modern syntax
# safe here.
from __future__ import annotations

from typing import Any

# The order matters. Training and inference both use this feature order.
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

# Decision rule shared by serving and evaluation: a score at or above this
# threshold means churn.
DEFAULT_THRESHOLD = 0.5

# Promotion gate, shared by the pipeline definition and the evaluation step.
# When the registry holds no approved package, the challenger is compared
# against this baseline, so the first model still has a bar to clear.
NO_CHAMPION_ARN = "none"
BASELINE_CHAMPION_AUC = 0.5

YES_NO = frozenset({"Yes", "No"})
NO_PHONE_SERVICE = "No phone service"
NO_INTERNET_SERVICE = "No internet service"

# Fixed ordinal maps. They are deterministic, so no fitted state ships to the
# Lambda.
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

# Columns whose "No" variant the source data spells out. These columns are why
# the vocabulary is per-column and not one shared Yes/No set. Only
# MultipleLines may say "No phone service". Only these six add-on services may
# say "No internet service". One shared set would accept
# `Partner="No internet service"`.
_INTERNET_ADDON_COLUMNS = (
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
)

# The raw values each categorical column accepts. Numeric columns are absent.
# Their contract is the range check on the Pydantic model, not a value set.
FEATURE_VOCABULARY: dict[str, frozenset[str]] = {
    **{column: YES_NO for column in ("Partner", "Dependents", "PhoneService", "PaperlessBilling")},
    "MultipleLines": YES_NO | {NO_PHONE_SERVICE},
    **{column: YES_NO | {NO_INTERNET_SERVICE} for column in _INTERNET_ADDON_COLUMNS},
    **{column: frozenset(values) for column, values in CATEGORY_MAPS.items()},
}


def encode_features(row: dict[str, Any]) -> list[float]:
    """Encode one record of raw feature values into the numeric vector.

    This function needs no pandas, so the serving proxy Lambda applies the same
    encoding at inference time that training used.
    """
    out = []
    for col in FEATURE_COLUMNS:
        v = row[col]
        if col in NUMERIC:
            out.append(float(v) if str(v).strip() else 0.0)
            continue
        table = CATEGORY_MAPS[col] if col in CATEGORY_MAPS else YES_NO_MAP
        if v not in table:
            # This is reachable only if a caller skipped CustomerRecord
            # validation. Name the column instead of raising a bare KeyError.
            raise ValueError(f"{col}: value not in the feature vocabulary: {v!r}")
        out.append(float(table[v]))
    return out
