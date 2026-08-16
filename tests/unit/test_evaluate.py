import csv
import json

import pytest

from src.pipeline.evaluate import calculate_classification_metrics, write_evaluation_artifacts


def test_calculate_classification_metrics_uses_threshold_boundary():
    metrics = calculate_classification_metrics(labels=[0, 0, 1, 1], scores=[0.1, 0.6, 0.5, 0.9])

    assert metrics["threshold"] == 0.5
    assert metrics["auc"] == pytest.approx(0.75)
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == pytest.approx(0.8)
    assert metrics["specificity"] == pytest.approx(0.5)
    assert metrics["confusion_matrix"] == {
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 0,
        "true_positive": 2,
    }


def test_write_evaluation_artifacts_creates_json_csv_and_charts(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1], scores=[0.1, 0.6, 0.5, 0.9], output_dir=str(tmp_path)
    )

    model_metrics = json.loads((tmp_path / "evaluation.json").read_text())
    detailed_metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert model_metrics["binary_classification_metrics"]["auc"]["value"] == pytest.approx(0.75)
    assert detailed_metrics["confusion_matrix"]["true_positive"] == 2
    with open(tmp_path / "predictions.csv") as f:
        predictions = list(csv.DictReader(f))
    assert predictions[2] == {
        "record_index": "2",
        "label": "1",
        "score": "0.5",
        "prediction": "1",
        "correct": "1",
    }
    for filename in (
        "confusion_matrix.png",
        "roc_curve.png",
        "precision_recall_curve.png",
        "calibration_curve.png",
        "score_distribution.png",
    ):
        assert (tmp_path / filename).stat().st_size > 0


def test_write_evaluation_artifacts_records_the_gate_decision(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1],
        scores=[0.1, 0.6, 0.5, 0.9],
        output_dir=str(tmp_path),
        champion_test_auc=0.7,
    )

    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["champion_test_auc"] == 0.7
    assert metrics["promotion_decision"] == "register"


def test_write_evaluation_artifacts_rejects_a_worse_challenger(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1],
        scores=[0.1, 0.6, 0.5, 0.9],
        output_dir=str(tmp_path),
        champion_test_auc=0.9,
    )

    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["promotion_decision"] == "reject"


def test_write_evaluation_artifacts_omits_the_gate_without_a_champion(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1], scores=[0.1, 0.6, 0.5, 0.9], output_dir=str(tmp_path)
    )

    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert "champion_test_auc" not in metrics
    assert "promotion_decision" not in metrics
