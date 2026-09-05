import csv
import io
import json
import sys
import tarfile
import types
from unittest import mock

import pytest

from src.pipeline import evaluate
from src.pipeline.evaluate import calculate_classification_metrics, write_evaluation_artifacts


def _archive(member_name="xgboost-model", payload=b"model", symlink=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = "outside"
        else:
            member.size = len(payload)
        archive.addfile(member, None if symlink else io.BytesIO(payload))
    return output.getvalue()


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


def test_write_evaluation_artifacts_uses_a_custom_score_chart_threshold(tmp_path):
    from matplotlib.axes import Axes

    calls = []
    original = Axes.axvline

    def capture(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    with mock.patch.object(Axes, "axvline", capture):
        write_evaluation_artifacts(
            labels=[0, 0, 1, 1],
            scores=[0.1, 0.6, 0.5, 0.9],
            output_dir=str(tmp_path),
            threshold=0.8,
        )

    assert calls[0][0][0] == pytest.approx(0.8)


def test_write_evaluation_artifacts_records_the_gate_decision(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1],
        scores=[0.1, 0.6, 0.5, 0.9],
        output_dir=str(tmp_path),
        champion_test_auc=0.7,
    )

    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["champion_test_auc"] == 0.7
    assert "current_champion_auc" not in metrics
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


def test_current_champion_auc_overrides_historical_value(tmp_path):
    write_evaluation_artifacts(
        labels=[0, 0, 1, 1],
        scores=[0.1, 0.6, 0.5, 0.9],
        output_dir=str(tmp_path),
        champion_test_auc=0.1,
        current_champion_auc=0.9,
    )

    evaluation = json.loads((tmp_path / "evaluation.json").read_text())
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert evaluation["current_champion_auc"] == 0.9
    assert metrics["current_champion_auc"] == 0.9
    assert metrics["promotion_decision"] == "reject"


def test_no_champion_uses_the_baseline_without_aws_reads():
    with mock.patch.object(evaluate.boto3, "client") as client:
        assert (
            evaluate._load_champion_booster("none", "artifacts-bucket", "us-east-1", mock.Mock())
            is None
        )

    client.assert_not_called()


@pytest.mark.parametrize(
    "archive",
    [_archive(member_name="../../xgboost-model"), _archive(symlink=True)],
)
def test_model_loader_rejects_unsafe_model_members(archive):
    with pytest.raises(ValueError, match="regular xgboost-model"):
        evaluate._load_booster_from_archive(archive, mock.Mock())


@pytest.mark.parametrize(
    "model_uri",
    [
        "https://artifacts-bucket/training/model.tar.gz",
        "s3://other-bucket/training/model.tar.gz",
        "s3://artifacts-bucket/other/model.tar.gz",
    ],
)
def test_champion_loader_rejects_invalid_or_cross_bucket_artifacts(model_uri):
    client = mock.Mock()
    client.describe_model_package.return_value = {
        "InferenceSpecification": {"Containers": [{"ModelDataUrl": model_uri}]}
    }
    with mock.patch.object(evaluate.boto3, "client", return_value=client):
        with pytest.raises(ValueError, match="champion model artifact"):
            evaluate._load_champion_booster(
                "arn:package", "artifacts-bucket", "us-east-1", mock.Mock()
            )

    client.get_object.assert_not_called()


def test_champion_loader_rejects_a_package_without_a_model_artifact():
    client = mock.Mock()
    client.describe_model_package.return_value = {"InferenceSpecification": {"Containers": []}}

    with mock.patch.object(evaluate.boto3, "client", return_value=client):
        with pytest.raises(ValueError, match="one model artifact"):
            evaluate._load_champion_booster(
                "arn:package", "artifacts-bucket", "us-east-1", mock.Mock()
            )

    client.get_object.assert_not_called()


def test_champion_loader_rejects_multiple_model_containers():
    client = mock.Mock()
    client.describe_model_package.return_value = {
        "InferenceSpecification": {
            "Containers": [
                {"ModelDataUrl": "s3://artifacts-bucket/training/one/model.tar.gz"},
                {"ModelDataUrl": "s3://artifacts-bucket/training/two/model.tar.gz"},
            ]
        }
    }

    with mock.patch.object(evaluate.boto3, "client", return_value=client):
        with pytest.raises(ValueError, match="one model artifact"):
            evaluate._load_champion_booster(
                "arn:package", "artifacts-bucket", "us-east-1", mock.Mock()
            )

    client.get_object.assert_not_called()


def test_main_scores_champion_and_challenger_on_the_same_features(tmp_path, monkeypatch):
    model_dir = tmp_path / "model"
    test_dir = tmp_path / "test"
    output_dir = tmp_path / "evaluation"
    model_dir.mkdir()
    test_dir.mkdir()
    (model_dir / "model.tar.gz").write_bytes(_archive(payload=b"challenger"))
    (test_dir / "test.csv").write_text("0,0\n0,1\n1,2\n1,3\n")

    matrices = []
    loaded_types = []

    class DMatrix:
        def __init__(self, features):
            self.features = features
            matrices.append(features)

    class Booster:
        def load_model(self, payload):
            loaded_types.append(type(payload))
            self.scores = (
                [0.1, 0.6, 0.5, 0.9] if bytes(payload) == b"challenger" else [0.1, 0.2, 0.8, 0.9]
            )

        def predict(self, matrix):
            return self.scores

    monkeypatch.setitem(
        sys.modules, "xgboost", types.SimpleNamespace(Booster=Booster, DMatrix=DMatrix)
    )
    monkeypatch.setattr(evaluate, "MODEL_DIR", str(model_dir))
    monkeypatch.setattr(evaluate, "TEST_DIR", str(test_dir))
    monkeypatch.setattr(evaluate, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate.py",
            "--champion-model-package-arn",
            "none",
            "--model-package-group",
            "fresh-group",
            "--champion-test-auc",
            "0.0",
            "--artifacts-bucket",
            "artifacts-bucket",
        ],
    )
    sagemaker = mock.Mock()
    sagemaker.describe_model_package.return_value = {
        "InferenceSpecification": {
            "Containers": [{"ModelDataUrl": "s3://artifacts-bucket/training/champion/model.tar.gz"}]
        }
    }
    s3 = mock.Mock()
    s3.get_object.return_value = {"Body": io.BytesIO(_archive(payload=b"champion"))}
    with (
        mock.patch.object(
            evaluate, "get_champion", return_value=("fresh-arn", 0.1)
        ) as get_champion,
        mock.patch.object(evaluate.boto3, "client", side_effect=[sagemaker, s3]),
    ):
        evaluate.main()

    evaluation = json.loads((output_dir / "evaluation.json").read_text())
    metrics = json.loads((output_dir / "metrics.json").read_text())
    assert evaluation["current_champion_auc"] == pytest.approx(1.0)
    assert metrics["promotion_decision"] == "reject"
    assert matrices == [[[0.0], [1.0], [2.0], [3.0]]] * 2
    assert loaded_types == [bytearray, bytearray]
    get_champion.assert_called_once_with("fresh-group", "us-east-1")
    sagemaker.describe_model_package.assert_called_once_with(ModelPackageName="fresh-arn")
