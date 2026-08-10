"""Define the dependency-free feature contract for training and serving.

This module owns the ordered columns, accepted raw values, and numeric encoding.
The SageMaker sklearn image imports it without Pydantic.
`tests/unit/test_features.py` compares validation and encoding vocabularies.
"""

# The SageMaker managed image uses an older Python version.
# Deferred annotations preserve compatibility with that image.
from __future__ import annotations

from typing import Any

# Training and inference use this feature order.
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

# Serving and evaluation classify scores at or above this threshold as churn.
DEFAULT_THRESHOLD = 0.5

# The pipeline and evaluation step share this promotion baseline.
# A challenger uses it when the registry has no approved package.
NO_CHAMPION_ARN = "none"
BASELINE_CHAMPION_AUC = 0.5

YES_NO = frozenset({"Yes", "No"})
NO_PHONE_SERVICE = "No phone service"
NO_INTERNET_SERVICE = "No internet service"

# These fixed ordinal maps require no fitted state in Lambda.
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

# These add-on columns accept `No internet service`.
# Only `MultipleLines` accepts `No phone service`.
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
    """Encode one raw feature record into the model vector."""
    out = []
    for col in FEATURE_COLUMNS:
        v = row[col]
        if col in NUMERIC:
            out.append(float(v) if str(v).strip() else 0.0)
            continue
        table = CATEGORY_MAPS[col] if col in CATEGORY_MAPS else YES_NO_MAP
        if v not in table:
            # Include the column name when validation did not run.
            raise ValueError(f"{col}: value not in the feature vocabulary: {v!r}")
        out.append(float(table[v]))
    return out
