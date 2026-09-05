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
import io
import json
import pathlib
import tarfile
from typing import Any
from urllib.parse import urlparse

import boto3
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
from src.common.registry import get_champion

MODEL_DIR = "/opt/ml/processing/model"
TEST_DIR = "/opt/ml/processing/test"
OUTPUT_DIR = "/opt/ml/processing/evaluation"


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _load_booster_from_archive(archive: bytes, xgb: Any) -> Any:
    """Load the regular XGBoost model member from a model archive."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            members = [member for member in tar.getmembers() if member.name == "xgboost-model"]
            if len(members) != 1 or not members[0].isreg():
                raise ValueError("model archive must contain one regular xgboost-model member")
            model_file = tar.extractfile(members[0])
            if model_file is None:
                raise ValueError("model archive does not contain readable xgboost-model data")
            model_bytes = model_file.read()
    except (EOFError, OSError, tarfile.TarError) as error:
        raise ValueError("model archive is invalid") from error

    booster = xgb.Booster()
    booster.load_model(bytearray(model_bytes))
    return booster


def _load_champion_booster(
    model_package_arn: str,
    artifacts_bucket: str,
    region: str,
    xgb: Any,
) -> Any | None:
    """Resolve and load the champion artifact from the platform bucket."""
    if model_package_arn == NO_CHAMPION_ARN:
        return None
    sagemaker = boto3.client("sagemaker", region_name=region)
    package = sagemaker.describe_model_package(ModelPackageName=model_package_arn)
    try:
        containers = package["InferenceSpecification"]["Containers"]
    except (KeyError, TypeError) as error:
        raise ValueError("champion model package has no model artifact") from error
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("champion model package must contain one model artifact")
    container = containers[0]
    if not isinstance(container, dict) or not isinstance(container.get("ModelDataUrl"), str):
        raise ValueError("champion model package must contain one model artifact")
    model_uri = container["ModelDataUrl"]

    parsed = urlparse(model_uri)
    key = parsed.path.lstrip("/")
    if parsed.scheme != "s3" or not parsed.netloc or not key or parsed.query or parsed.fragment:
        raise ValueError("champion model artifact URI is invalid")
    if parsed.netloc != artifacts_bucket or not key.startswith("training/"):
        raise ValueError("champion model artifact must be under the artifacts training prefix")

    s3 = boto3.client("s3", region_name=region)
    archive = s3.get_object(Bucket=parsed.netloc, Key=key)["Body"].read()
    return _load_booster_from_archive(archive, xgb)


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
    labels: list[int],
    scores: list[float],
    output_dir: pathlib.Path,
    threshold: float,
) -> None:
    stayed_scores = [scores[index] for index, label in enumerate(labels) if label == 0]
    churn_scores = [scores[index] for index, label in enumerate(labels) if label == 1]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(stayed_scores, bins=20, alpha=0.65, label="Actual stay")
    ax.hist(churn_scores, bins=20, alpha=0.65, label="Actual churn")
    ax.axvline(
        threshold,
        color="black",
        linestyle="--",
        label=f"Threshold {threshold:.2f}",
    )
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
    labels: list[int],
    scores: list[float],
    output_dir: str,
    threshold: float = DEFAULT_THRESHOLD,
    champion_test_auc: float | None = None,
    current_champion_auc: float | None = None,
) -> dict:
    """Write the complete report bundle and return its metrics dictionary.

    ``current_champion_auc`` records the score the challenger had to beat.
    ``champion_test_auc`` remains accepted for older callers.
    """
    metrics = calculate_classification_metrics(labels, scores, threshold)
    comparison_auc = current_champion_auc if current_champion_auc is not None else champion_test_auc
    if comparison_auc is not None:
        metrics["champion_test_auc"] = comparison_auc
        if current_champion_auc is not None:
            metrics["current_champion_auc"] = comparison_auc
        metrics["promotion_decision"] = "register" if metrics["auc"] > comparison_auc else "reject"
    destination = pathlib.Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    predictions = [int(score >= threshold) for score in scores]

    evaluation: dict[str, Any] = {
        "binary_classification_metrics": {
            "auc": {"value": metrics["auc"], "standard_deviation": "NaN"},
        }
    }
    if current_champion_auc is not None:
        evaluation["current_champion_auc"] = current_champion_auc
    with open(destination / "evaluation.json", "w") as f:
        json.dump(evaluation, f)
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
    _save_score_distribution(labels, scores, destination, threshold)
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
    parser.add_argument("--model-package-group")
    parser.add_argument("--champion-test-auc", type=float, default=BASELINE_CHAMPION_AUC)
    parser.add_argument("--artifacts-bucket", default="")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--challenger-model-artifact", default="unknown")
    args = parser.parse_args()

    # Load XGBoost inside the processing entrypoint.
    # This processing step supplies the XGBoost runtime.
    import xgboost as xgb

    champion_model_package_arn = args.champion_model_package_arn
    if args.model_package_group:
        champion_model_package_arn, _ = get_champion(args.model_package_group, args.region)
    challenger_archive = pathlib.Path(f"{MODEL_DIR}/model.tar.gz").read_bytes()
    challenger = _load_booster_from_archive(challenger_archive, xgb)
    labels, features = _load_test_data(TEST_DIR)
    challenger_scores = [float(score) for score in challenger.predict(xgb.DMatrix(features))]
    champion = _load_champion_booster(
        champion_model_package_arn,
        args.artifacts_bucket,
        args.region,
        xgb,
    )
    champion_auc = BASELINE_CHAMPION_AUC
    if champion is not None:
        champion_scores = [float(score) for score in champion.predict(xgb.DMatrix(features))]
        champion_auc = calculate_classification_metrics(labels, champion_scores)["auc"]
    metrics = write_evaluation_artifacts(
        labels,
        challenger_scores,
        OUTPUT_DIR,
        current_champion_auc=champion_auc,
    )
    log_event(
        "challenger_evaluation",
        challenger_model_artifact=args.challenger_model_artifact,
        challenger_test_auc=round(metrics["auc"], 4),
        champion_model_package_arn=champion_model_package_arn,
        champion_test_auc=champion_auc,
        promotion_decision=metrics["promotion_decision"],
    )


if __name__ == "__main__":
    main()
