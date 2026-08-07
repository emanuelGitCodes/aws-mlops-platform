import json

import pytest
from pydantic import ValidationError

from src.common.features import encode_features
from src.common.schema import FEATURE_COLUMNS, CustomerRecord
from tests.unit.conftest import REPO_ROOT, VALID


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
    [
        ("gender", "X"),
        ("Partner", "Maybe"),
        ("tenure", -1),
        ("Churn", "Perhaps"),
        # The ten columns that once validated as bare `str`. Each one reached
        # the encoder and raised KeyError instead of being rejected.
        ("Contract", "Three year"),
        ("PaymentMethod", "Crypto"),
        ("InternetService", "5G"),
        ("MultipleLines", "Sometimes"),
        ("OnlineSecurity", "Maybe"),
        ("StreamingTV", "Occasionally"),
        # A column-specific "No" variant must not leak across columns.
        ("Partner", "No internet service"),
        ("PhoneService", "No phone service"),
    ],
)
def test_invalid_values_rejected(field, value):
    with pytest.raises(ValidationError):
        CustomerRecord.model_validate({**VALID, field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("MultipleLines", "No phone service"),
        ("OnlineSecurity", "No internet service"),
        ("InternetService", "Fiber optic"),
        ("Contract", "Two year"),
    ],
)
def test_real_source_values_still_accepted(field, value):
    """Tightening the schema must not reject values the public Telco CSV uses."""
    assert CustomerRecord.model_validate({**VALID, field: value})


def test_feature_columns_match_model_fields():
    assert set(FEATURE_COLUMNS) <= set(CustomerRecord.model_fields)


@pytest.mark.parametrize("path", sorted(REPO_ROOT.glob("sample*.json")), ids=lambda p: p.name)
def test_committed_sample_payloads_stay_valid(path):
    """Every sample payload in the repo must still validate and encode.

    These are what a reader curls at the API, so a schema change that leaves
    them behind is a broken example. Tightening the categorical vocabulary
    could have invalidated them silently; this makes that a test failure.
    """
    record = CustomerRecord.model_validate(json.loads(path.read_text()))
    encode_features({column: getattr(record, column) for column in FEATURE_COLUMNS})
