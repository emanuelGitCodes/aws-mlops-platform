# Evaluation-report rollout — July 11, 2026

## Scope

The `churn-training-pipeline-dev` SageMaker Pipeline was extended to preserve
raw, labeled held-out records for API verification and to publish visual and
machine-readable test-set evaluation reports from the existing `Evaluate`
ProcessingStep.

## Implemented behavior

- `Preprocess` writes `api_test/api_test.jsonl`, containing API-shaped raw
  feature values, a binary label, and a stable test-row identifier.
- `Evaluate` retains the existing SageMaker-compatible `evaluation.json` AUC
  contract used by the champion gate and additionally writes `metrics.json`,
  `predictions.csv`, `confusion_matrix.png`, `roc_curve.png`,
  `precision_recall_curve.png`, `calibration_curve.png`, and
  `score_distribution.png`.
- The report uses the same fixed `0.50` probability threshold as the live API:
  a score greater than or equal to `0.50` is classified as churn.
- `scripts/evaluate_api.py` can read the labeled `api_test` fixture, invoke the
  public API, validate the probability/classification contract, and summarize
  endpoint metrics.

## Deployment and execution evidence

The SDK-managed pipeline was upserted in `us-east-1`, account `${AWS_ACCOUNT_ID}`,
without starting a job. The normal `${MLOPS_DEPLOYER_USER_NAME}` identity cannot directly
call SageMaker; the existing `${AWS_ADMIN_USER_NAME}` break-glass profile was used only to
upsert this SDK-managed pipeline.

The first post-update execution,
`arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id>`,
reached `Evaluate` but failed after writing JSON and CSV artifacts. Its
CloudWatch log showed Python 3.9 rejected `zip(..., strict=True)` with:

```text
TypeError: zip() takes no keyword arguments
```

The Processing image is Python 3.9, so chart-generation loops were rewritten
to use index-based access. The focused evaluation-artifact tests passed, the
pipeline was upserted again, and retry execution
`arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id>`
completed and produced the full report bundle in:

```text
s3://${ARTIFACTS_BUCKET}/churn-training-pipeline-dev/<pipeline-execution-id>/Evaluate/output/evaluation/
```

## Measured held-out test results

The successful report evaluated 1,057 held-out records: 270 churners and 787
non-churners.

```json
{
  "threshold": 0.5,
  "auc": 0.8398418749117607,
  "accuracy": 0.8022705771050141,
  "precision": 0.6331877729257642,
  "recall": 0.5370370370370371,
  "f1": 0.5811623246492986,
  "specificity": 0.8932655654383735,
  "confusion_matrix": {
    "true_negative": 703,
    "false_positive": 84,
    "false_negative": 125,
    "true_positive": 145
  }
}
```

The result has useful ranking power (AUC about 0.84) and high specificity at
the 0.50 threshold, but recalls only 145 of 270 churners. Lowering the serving
threshold would increase recall and false-positive retention offers; any such
change must update both the API and report threshold together.
