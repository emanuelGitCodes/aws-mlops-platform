"""Evaluation ProcessingStep: score a challenger on the held-out test split.

``evaluation.json`` keeps the SageMaker ModelMetrics AUC shape the promotion
gate reads. The same step also writes a fuller per-execution report: a metrics
JSON file, a prediction CSV, and diagnostic PNG charts.
"""

# The SageMaker managed image uses an older Python version.
# Deferred annotations preserve compatibility with that image.
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import tarfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from src.common.events import log_event
from src.common.features import (
    BASELINE_CHAMPION_AUC,
    DEFAULT_THRESHOLD,
    NO_CHAMPION_ARN,
)

MODEL_DIR = "/opt/ml/processing/model"
TEST_DIR = "/opt/ml/processing/test"
OUTPUT_DIR = "/opt/ml/processing/evaluation"


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_classification_metrics(
    labels: list[int], scores: list[float], threshold: float = DEFAULT_THRESHOLD
) -> dict:
    """Calculate binary-classification metrics using the serving decision rule."""
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have the same length")
    if not labels:
        raise ValueError("evaluation requires at least one test record")
    if len(set(labels)) != 2:
        raise ValueError("evaluation requires both churn classes to compute ROC AUC")

    predictions = [int(score >= threshold) for score in scores]
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        labels, predictions, labels=[0, 1]
    ).ravel()
    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    return {
        "threshold": threshold,
        "sample_count": len(labels),
        "positive_count": sum(labels),
        "negative_count": len(labels) - sum(labels),
        "auc": roc_auc_score(labels, scores),
        "accuracy": _safe_divide(true_positive + true_negative, len(labels)),
        "precision": precision,
        "recall": recall,
        "f1": _safe_divide(2 * precision * recall, precision + recall),
        "specificity": _safe_divide(true_negative, true_negative + false_positive),
        "confusion_matrix": {
            "true_negative": int(true_negative),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
            "true_positive": int(true_positive),
        },
    }


def _save_confusion_matrix(metrics: dict, output_dir: pathlib.Path) -> None:
    matrix = metrics["confusion_matrix"]
    values = [
        [matrix["true_negative"], matrix["false_positive"]],
        [matrix["false_negative"], matrix["true_positive"]],
    ]
    fig, ax = plt.subplots(figsize=(5, 4))
    image = ax.imshow(values, cmap="Blues")
    fig.colorbar(image, ax=ax)
    ax.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["Predicted stay", "Predicted churn"],
        yticklabels=["Actual stay", "Actual churn"],
        title=f"Confusion matrix (threshold {metrics['threshold']:.2f})",
    )
    for row in range(2):
        for column in range(2):
            ax.text(column, row, values[row][column], ha="center", va="center")
    fig.tight_layout()
    fig.savefig(output_dir / "confusion_matrix.png", dpi=160)
    plt.close(fig)


def _save_roc_curve(
    labels: list[int], scores: list[float], metrics: dict, output_dir: pathlib.Path
) -> None:
    false_positive_rate, true_positive_rate, _ = roc_curve(labels, scores)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(false_positive_rate, true_positive_rate, label=f"AUC = {metrics['auc']:.3f}")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="Random")
    ax.set(
        xlabel="False positive rate",
        ylabel="True positive rate",
        title="ROC curve",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_dir / "roc_curve.png", dpi=160)
    plt.close(fig)


def _save_precision_recall_curve(
    labels: list[int], scores: list[float], output_dir: pathlib.Path
) -> None:
    precision, recall, _ = precision_recall_curve(labels, scores)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(recall, precision)
    ax.set(
        xlabel="Recall",
        ylabel="Precision",
        title="Precision-recall curve",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    fig.tight_layout()
    fig.savefig(output_dir / "precision_recall_curve.png", dpi=160)
    plt.close(fig)


def _save_calibration_curve(
    labels: list[int], scores: list[float], output_dir: pathlib.Path
) -> None:
    observed, predicted = calibration_curve(labels, scores, n_bins=10, strategy="uniform")
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(predicted, observed, marker="o", label="Model")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="Perfectly calibrated")
    ax.set(
        xlabel="Mean predicted churn probability",
        ylabel="Observed churn frequency",
        title="Calibration curve",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output_dir / "calibration_curve.png", dpi=160)
    plt.close(fig)


def _save_score_distribution(
    labels: list[int], scores: list[float], output_dir: pathlib.Path
) -> None:
    stayed_scores = [scores[index] for index, label in enumerate(labels) if label == 0]
    churn_scores = [scores[index] for index, label in enumerate(labels) if label == 1]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(stayed_scores, bins=20, alpha=0.65, label="Actual stay")
    ax.hist(churn_scores, bins=20, alpha=0.65, label="Actual churn")
    ax.axvline(DEFAULT_THRESHOLD, color="black", linestyle="--", label="Threshold 0.50")
    ax.set(
        xlabel="Predicted churn probability",
        ylabel="Test records",
        title="Predicted-score distribution",
        xlim=(0, 1),
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "score_distribution.png", dpi=160)
    plt.close(fig)


def write_evaluation_artifacts(
    labels: list[int], scores: list[float], output_dir: str, threshold: float = DEFAULT_THRESHOLD
) -> dict:
    """Write the complete report bundle and return its metrics dictionary."""
    metrics = calculate_classification_metrics(labels, scores, threshold)
    destination = pathlib.Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    predictions = [int(score >= threshold) for score in scores]

    with open(destination / "evaluation.json", "w") as f:
        json.dump(
            {
                "binary_classification_metrics": {
                    "auc": {"value": metrics["auc"], "standard_deviation": "NaN"},
                }
            },
            f,
        )
    with open(destination / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    with open(destination / "predictions.csv", "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["record_index", "label", "score", "prediction", "correct"]
        )
        writer.writeheader()
        for index, label in enumerate(labels):
            writer.writerow(
                {
                    "record_index": index,
                    "label": label,
                    "score": scores[index],
                    "prediction": predictions[index],
                    "correct": int(label == predictions[index]),
                }
            )

    _save_confusion_matrix(metrics, destination)
    _save_roc_curve(labels, scores, metrics, destination)
    _save_precision_recall_curve(labels, scores, destination)
    _save_calibration_curve(labels, scores, destination)
    _save_score_distribution(labels, scores, destination)
    return metrics


def _load_test_data(test_dir: str) -> tuple[list[int], list[list[float]]]:
    labels, features = [], []
    for path in pathlib.Path(test_dir).glob("*.csv"):
        with open(path) as f:
            for row in csv.reader(f):
                labels.append(int(float(row[0])))
                features.append([float(value) for value in row[1:]])
    return labels, features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion-model-package-arn", default=NO_CHAMPION_ARN)
    parser.add_argument("--champion-test-auc", type=float, default=BASELINE_CHAMPION_AUC)
    parser.add_argument("--challenger-model-artifact", default="unknown")
    args = parser.parse_args()

    # Load XGBoost inside the processing entrypoint.
    # This processing step supplies the XGBoost runtime.
    import xgboost as xgb

    with tarfile.open(f"{MODEL_DIR}/model.tar.gz") as tar:
        tar.extractall(MODEL_DIR)

    booster = xgb.Booster()
    booster.load_model(f"{MODEL_DIR}/xgboost-model")
    labels, features = _load_test_data(TEST_DIR)
    scores = [float(score) for score in booster.predict(xgb.DMatrix(features))]
    metrics = write_evaluation_artifacts(labels, scores, OUTPUT_DIR)
    log_event(
        "challenger_evaluation",
        challenger_model_artifact=args.challenger_model_artifact,
        challenger_test_auc=round(metrics["auc"], 4),
        champion_model_package_arn=args.champion_model_package_arn,
        champion_test_auc=args.champion_test_auc,
        promotion_decision="register" if metrics["auc"] > args.champion_test_auc else "reject",
    )


if __name__ == "__main__":
    main()
