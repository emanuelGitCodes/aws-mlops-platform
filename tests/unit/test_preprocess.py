from src.common.schema import FEATURE_COLUMNS
from src.pipeline.preprocess import encode_features, encode_labeled_row
from tests.unit.test_schema import VALID


def test_encode_features_length_and_numeric():
    vec = encode_features(VALID)
    assert len(vec) == len(FEATURE_COLUMNS)
    assert all(isinstance(v, float) for v in vec)


def test_encode_labeled_row_label_first():
    row = encode_labeled_row({**VALID, "Churn": "Yes"})
    assert row[0] == 1.0
    assert row[1:] == encode_features(VALID)

    row = encode_labeled_row({**VALID, "Churn": "No"})
    assert row[0] == 0.0


def test_no_internet_service_maps():
    vec = encode_features({**VALID, "OnlineSecurity": "No internet service"})
    idx = FEATURE_COLUMNS.index("OnlineSecurity")
    assert vec[idx] == 2.0
