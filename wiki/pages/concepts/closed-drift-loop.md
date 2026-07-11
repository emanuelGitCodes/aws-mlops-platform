---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-07-11"
sources: ["../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../src/pipeline/pipeline.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "Captured inference traffic can produce a monitoring violation that starts a gated challenger training run and eventual redeployment."
---
# Closed drift-to-retrain loop

## Confirmed

The serving endpoint captures request and response data to S3. A Model Monitor schedule compares live traffic against a baseline. When the schedule emits `CompletedWithViolations`, EventBridge invokes a retrain Lambda, which starts the named SageMaker Pipeline.

The challenger is evaluated before registration. A `ConditionStep` compares its test AUC with the current champion, so a drift signal can initiate training without automatically promoting a worse model. Approval of a registered package produces the deployment event that updates the endpoint.

The first live pipeline checkpoint failed in `Preprocess` because the Processing job could not import `src.common.schema`. That packaging issue is resolved: execution `nntqc422p0p1` completed preprocessing, training, and evaluation, logged test AUC `0.8398`, and registered approved model package `churn-model-group/1`.

The approval-to-endpoint handoff is now working for low-cost serving: the deploy Lambda omits unsupported `DataCaptureConfig`, the serverless endpoint is `InService`, and API Gateway returns model predictions. The closed loop remains incomplete only at the monitoring boundary because serverless endpoints cannot supply SageMaker Model Monitor's built-in request/response capture.

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
