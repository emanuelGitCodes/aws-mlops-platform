---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-07-11"
sources: ["../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../src/pipeline/preprocess.py", "../../../src/pipeline/evaluate.py", "../../../src/pipeline/pipeline.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/evaluation-report-rollout-july-11-2026.md"]
summary: "A gated challenger run produces held-out metrics and report artifacts before registry promotion; serverless monitoring capture remains a future design boundary."
---
# Closed drift-to-retrain loop

## Confirmed

The intended serving design captures request and response data to S3, then has
Model Monitor compare live traffic against a baseline and emit a retraining
event. The current serverless endpoint cannot use SageMaker
`DataCaptureConfig`, so that built-in capture-and-monitoring leg remains
deferred; it is not evidence of active monitoring today.

The challenger is evaluated before registration. A `ConditionStep` compares its test AUC with the current champion, so a drift signal can initiate training without automatically promoting a worse model. Approval of a registered package produces the deployment event that updates the endpoint.

Before the gate uses AUC, the `Evaluate` ProcessingStep now records the full
held-out test result in the artifacts bucket: metrics, row-level predictions,
and confusion-matrix, ROC, precision-recall, calibration, and score-
distribution charts. The report uses the exact same 0.50 threshold as the API;
its visual metrics therefore describe the deployed classification rule rather
than a disconnected offline cutoff.

The first live pipeline checkpoint failed in `Preprocess` because the Processing job could not import `src.common.schema`. That packaging issue is resolved: execution `nntqc422p0p1` completed preprocessing, training, and evaluation, logged test AUC `0.8398`, and registered approved model package `churn-model-group/1`.

The approval-to-endpoint handoff is now working for low-cost serving: the deploy Lambda omits unsupported `DataCaptureConfig`, the serverless endpoint is `InService`, and API Gateway returns model predictions. The closed loop remains incomplete only at the monitoring boundary because serverless endpoints cannot supply SageMaker Model Monitor's built-in request/response capture.

Execution `53ww289tjhoz` confirmed that this report path succeeds in the live
environment, producing AUC `0.8398` and the full S3 visual-artifact bundle.

## Synthesis

This is a feedback loop with a quality gate, not an unconditional retraining loop:

```text
traffic -> capture -> monitor -> violation -> pipeline -> challenger
                                               -> AUC gate -> registry -> approval -> endpoint
```

The loop separates detection, remediation, evaluation, and release. That makes failures diagnosable: a violation can exist without a successful training run, a training run can fail the quality gate, and a registered model can still await approval.

## Tensions or open questions

- The monitor baseline and schedule require a live endpoint and are configured by `scripts/setup_monitor.py`; the deployment workflow should keep this operational dependency visible.
- `churn-serverless-dev` uses on-demand serverless inference without configured provisioned concurrency, so it does not retain a real-time hosting instance while idle.
- If built-in Model Monitor is needed, change the capture design or use a provisioned endpoint; do not re-add `DataCaptureConfig` to the serverless configuration.
- The current 0.50 threshold has recall `0.5370` on the held-out set. Choose a
  lower threshold only when the cost of retention offers and missed churn has
  been defined, then keep the report and proxy Lambda aligned.
