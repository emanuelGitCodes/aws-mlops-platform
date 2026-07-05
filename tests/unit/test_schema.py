import pytest
from pydantic import ValidationError

from src.common.schema import FEATURE_COLUMNS, CustomerRecord

VALID = {
    "gender": "Female",
    "SeniorCitizen": 0,
    "Partner": "Yes",
    "Dependents": "No",
    "tenure": 12,
    "PhoneService": "Yes",
    "MultipleLines": "No",
    "InternetService": "DSL",
    "OnlineSecurity": "No",
    "OnlineBackup": "Yes",
    "DeviceProtection": "No",
    "TechSupport": "No",
    "StreamingTV": "No",
    "StreamingMovies": "No",
    "Contract": "Month-to-month",
    "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 53.85,
    "TotalCharges": 646.2,
}


def test_valid_record_without_label():
    rec = CustomerRecord.model_validate(VALID)
    assert rec.Churn is None


def test_valid_record_with_label():
    rec = CustomerRecord.model_validate({**VALID, "Churn": "No"})
    assert rec.Churn == "No"


def test_blank_total_charges_coerced_to_zero():
    rec = CustomerRecord.model_validate({**VALID, "TotalCharges": " "})
    assert rec.TotalCharges == 0.0


@pytest.mark.parametrize(
    "field,value",
    [("gender", "X"), ("Partner", "Maybe"), ("tenure", -1), ("Churn", "Perhaps")],
)
def test_invalid_values_rejected(field, value):
    with pytest.raises(ValidationError):
        CustomerRecord.model_validate({**VALID, field: value})


def test_feature_columns_match_model_fields():
    assert set(FEATURE_COLUMNS) <= set(CustomerRecord.model_fields)
