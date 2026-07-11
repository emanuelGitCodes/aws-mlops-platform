"""Evaluation ProcessingStep: score the challenger on the test split.

Loads the trained XGBoost model artifact, computes AUC on the held-out test
set, and writes evaluation.json in the shape SageMaker's ConditionStep /
ModelMetrics expect.
"""

import argparse
import csv
import json
import pathlib
import tarfile

import xgboost as xgb
from sklearn.metrics import roc_auc_score

MODEL_DIR = "/opt/ml/processing/model"
TEST_DIR = "/opt/ml/processing/test"
OUTPUT_DIR = "/opt/ml/processing/evaluation"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion-model-package-arn", default="none")
    parser.add_argument("--champion-test-auc", type=float, default=0.5)
    parser.add_argument("--challenger-model-artifact", default="unknown")
    args = parser.parse_args()

    with tarfile.open(f"{MODEL_DIR}/model.tar.gz") as tar:
        tar.extractall(MODEL_DIR)

    booster = xgb.Booster()
    booster.load_model(f"{MODEL_DIR}/xgboost-model")

    labels, features = [], []
    for path in pathlib.Path(TEST_DIR).glob("*.csv"):
        with open(path) as f:
            for row in csv.reader(f):
                labels.append(float(row[0]))
                features.append([float(v) for v in row[1:]])

    scores = booster.predict(xgb.DMatrix(features))
    auc = roc_auc_score(labels, scores)

    report = {
        "binary_classification_metrics": {
            "auc": {"value": auc, "standard_deviation": "NaN"},
        }
    }
    pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    with open(f"{OUTPUT_DIR}/evaluation.json", "w") as f:
        json.dump(report, f)
    print(
        json.dumps(
            {
                "event": "challenger_evaluation",
                "challenger_model_artifact": args.challenger_model_artifact,
                "challenger_test_auc": round(auc, 4),
                "champion_model_package_arn": args.champion_model_package_arn,
                "champion_test_auc": args.champion_test_auc,
                "promotion_decision": "register" if auc > args.champion_test_auc else "reject",
            }
        )
    )


if __name__ == "__main__":
    main()
