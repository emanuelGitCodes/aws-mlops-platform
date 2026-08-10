import pytest

from src.common.features import (
    CATEGORY_MAPS,
    FEATURE_COLUMNS,
    FEATURE_VOCABULARY,
    NUMERIC,
    YES_NO_MAP,
    encode_features,
)
from tests.unit.conftest import VALID


def test_vocabulary_covers_exactly_the_categorical_columns():
    """A new feature column must land in the vocabulary or the numeric set."""
    assert set(FEATURE_VOCABULARY) | NUMERIC == set(FEATURE_COLUMNS)
    assert not set(FEATURE_VOCABULARY) & NUMERIC


@pytest.mark.parametrize(
    "column,value",
    sorted((column, value) for column, values in FEATURE_VOCABULARY.items() for value in values),
)
def test_every_accepted_value_is_encodable(column, value):
    """Encode every value accepted by the feature vocabulary."""
    vector = encode_features({**VALID, column: value})
    assert len(vector) == len(FEATURE_COLUMNS)
    assert all(isinstance(element, float) for element in vector)


def test_no_phone_and_no_internet_stay_column_specific():
    """The spelled-out "No" variants are not interchangeable between columns."""
    assert "No phone service" in FEATURE_VOCABULARY["MultipleLines"]
    assert "No phone service" not in FEATURE_VOCABULARY["Partner"]
    assert "No internet service" in FEATURE_VOCABULARY["OnlineSecurity"]
    assert "No internet service" not in FEATURE_VOCABULARY["PhoneService"]


def test_unknown_category_names_its_column():
    """Unvalidated input must not surface as a bare KeyError."""
    with pytest.raises(ValueError, match="Contract"):
        encode_features({**VALID, "Contract": "Three year"})


def test_encoded_vocabulary_has_no_unreachable_values():
    """Every encodable category is reachable through the vocabulary.

    Guards the other direction: a map entry no column accepts is dead weight
    that hides a missing vocabulary entry.
    """
    accepted = {value for values in FEATURE_VOCABULARY.values() for value in values}
    for column, mapping in CATEGORY_MAPS.items():
        assert set(mapping) == FEATURE_VOCABULARY[column]
    assert set(YES_NO_MAP) <= accepted
