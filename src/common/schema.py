"""Shared input schema for the Telco churn model.

Used by the ingestion validation Lambda (rows from raw CSVs) and the
serving proxy Lambda (inference requests). Single source of truth so the
training data contract and the API contract can't drift apart.
"""

from pydantic import BaseModel, Field, field_validator

from src.common.features import FEATURE_COLUMNS, LABEL_COLUMN

__all__ = ["CustomerRecord", "FEATURE_COLUMNS", "LABEL_COLUMN"]

YES_NO = {"Yes", "No"}


class CustomerRecord(BaseModel):
    """One customer row; label optional so the same model validates inference requests."""

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

    @field_validator("gender")
    @classmethod
    def _gender(cls, v: str) -> str:
        if v not in {"Male", "Female"}:
            raise ValueError(f"invalid gender: {v}")
        return v

    @field_validator("Partner", "Dependents", "PhoneService", "PaperlessBilling")
    @classmethod
    def _yes_no(cls, v: str) -> str:
        if v not in YES_NO:
            raise ValueError(f"expected Yes/No, got: {v}")
        return v

    @field_validator("TotalCharges", mode="before")
    @classmethod
    def _blank_total(cls, v):
        # The public Telco CSV has blank TotalCharges for tenure-0 customers.
        if isinstance(v, str) and not v.strip():
            return 0.0
        return v

    @field_validator("Churn")
    @classmethod
    def _churn(cls, v: str | None) -> str | None:
        if v is not None and v not in YES_NO:
            raise ValueError(f"expected Yes/No churn label, got: {v}")
        return v
