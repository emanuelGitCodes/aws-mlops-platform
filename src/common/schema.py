"""Define the shared Telco churn input schema.

Ingestion validates raw CSV rows with this schema. Serving validates inference
requests with the same schema.
"""

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

from src.common.features import (
    FEATURE_COLUMNS,
    FEATURE_VOCABULARY,
    LABEL_COLUMN,
    YES_NO,
)

__all__ = [
    "CustomerRecord",
    "FEATURE_COLUMNS",
    "LABEL_COLUMN",
    "format_validation_error",
]


def format_validation_error(exc: ValidationError) -> str:
    """Render the first validation failure as ``<field.path>: <message>``."""
    first = exc.errors()[0]
    return f"{'.'.join(str(x) for x in first['loc'])}: {first['msg']}"


class CustomerRecord(BaseModel):
    """Represent one customer row with an optional label."""

    gender: str
    SeniorCitizen: int = Field(ge=0, le=1)
    Partner: str
    Dependents: str
    tenure: int = Field(ge=0)
    PhoneService: str
    MultipleLines: str
    InternetService: str
    OnlineSecurity: str
    OnlineBackup: str
    DeviceProtection: str
    TechSupport: str
    StreamingTV: str
    StreamingMovies: str
    Contract: str
    PaperlessBilling: str
    PaymentMethod: str
    MonthlyCharges: float = Field(ge=0)
    TotalCharges: float = Field(ge=0)
    Churn: str | None = None

    # Validate each categorical value against the encoder vocabulary.
    @field_validator(*FEATURE_VOCABULARY)
    @classmethod
    def _known_category(cls, v: str, info: ValidationInfo) -> str:
        allowed = FEATURE_VOCABULARY[str(info.field_name)]
        if v not in allowed:
            raise ValueError(f"expected one of {sorted(allowed)}, got: {v}")
        return v

    @field_validator("TotalCharges", mode="before")
    @classmethod
    def _blank_total(cls, v: object) -> object:
        # The Telco CSV uses blank `TotalCharges` for tenure-zero customers.
        if isinstance(v, str) and not v.strip():
            return 0.0
        return v

    @field_validator("Churn")
    @classmethod
    def _churn(cls, v: str | None) -> str | None:
        if v is not None and v not in YES_NO:
            raise ValueError(f"expected Yes/No churn label, got: {v}")
        return v
