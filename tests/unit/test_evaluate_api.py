import json
import urllib.error
from unittest import mock

import pytest

from scripts import evaluate_api
from tests.unit.test_schema import VALID


def _fixture(label: int, row_id: int) -> dict:
    return {"row_id": row_id, "record": VALID, "label": label}


def test_select_records_is_deterministic_and_class_balanced():
    records = [_fixture(index % 2, index) for index in range(20)]

    selected = evaluate_api.select_records(records, limit=6, all_records=False)

    assert selected == evaluate_api.select_records(records, limit=6, all_records=False)
    assert len(selected) == 6
    assert {record["label"] for record in selected} == {0, 1}


def test_evaluate_api_records_reports_labeled_endpoint_results():
    records = [_fixture(0, 0), _fixture(0, 1), _fixture(1, 2), _fixture(1, 3)]
    responses = [
        {"score": 0.1, "prediction": 0},
        {"score": 0.6, "prediction": 1},
        {"score": 0.5, "prediction": 1},
        {"score": 0.9, "prediction": 1},
    ]
    with mock.patch.object(evaluate_api, "invoke_prediction", side_effect=responses):
        report = evaluate_api.evaluate_api_records(records, "https://example.test/predict", "key")

    assert report["source"] == "deployed_api"
    assert report["evaluated_record_count"] == 4
    assert report["accuracy"] == pytest.approx(0.75)
    assert report["confusion_matrix"]["false_positive"] == 1


def test_invoke_prediction_rejects_mismatched_score_and_classification():
    response = mock.MagicMock()
    response.read.return_value = json.dumps({"churn_probability": 0.7, "churn": False}).encode()
    response.__enter__.return_value = response
    with mock.patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="does not match"):
            evaluate_api.invoke_prediction("https://example.test/predict", "key", VALID)


def test_invoke_prediction_reports_http_failure():
    error = urllib.error.HTTPError("https://example.test/predict", 503, "unavailable", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(evaluate_api.ApiEvaluationError, match="HTTP 503"):
            evaluate_api.invoke_prediction("https://example.test/predict", "key", VALID)
