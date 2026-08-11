---
type: "source"
title: "Evaluation report rollout — July 11, 2026"
created: "2026-07-11"
updated: "2026-08-10"
sources: ["../../raw/evaluation-report-rollout-july-11-2026.md"]
summary: "Evidence for the held-out evaluation-report rollout, Python 3.9 compatibility recovery, and successful visual-artifact execution."
---
# Evaluation report rollout — July 11, 2026

## Key claims

- The existing `Evaluate` ProcessingStep now writes a SageMaker-compatible AUC
  report plus detailed metrics, row-level predictions, and five PNG charts.
- `Preprocess` emits a raw, labeled `api_test` fixture so a deployed API can be
  tested without reversing the categorical feature encoding.
- The first post-update execution failed only during chart rendering because
  the managed Processing image uses Python 3.9, which does not support
  `zip(..., strict=True)`.
- After replacing those loops with Python 3.9-compatible index-based access,
  retry execution `<pipeline-execution-id>` produced the complete S3 report bundle.
- The held-out dataset contains 1,057 records and produced AUC `0.8398`,
  accuracy `0.8023`, precision `0.6332`, recall `0.5370`, F1 `0.5812`, and
  specificity `0.8933` at the shared `0.50` threshold.

## Entities and concepts

- `src/pipeline/preprocess.py` and the `api_test` Processing output.
- `src/pipeline/evaluate.py`, `metrics.json`, `predictions.csv`, and PNG report
  artifacts.
- SageMaker pipeline executions `<pipeline-execution-id>` (partial failure) and
  `<pipeline-execution-id>` (successful retry).
- The shared serving/evaluation `0.50` classification threshold.

See the maintained [deployment and pipeline troubleshooting checkpoint](../architecture/deployment-and-pipeline-troubleshooting.md)
and [closed drift-to-retrain loop](../concepts/closed-drift-loop.md) for the
current operational synthesis.

## Tensions or open questions

- The `0.50` threshold is deliberately consistent with the API, but it misses
  125 of the 270 churners in this held-out test split. A later business-cost
  decision may choose a lower threshold and must update serving and reporting
  together.
