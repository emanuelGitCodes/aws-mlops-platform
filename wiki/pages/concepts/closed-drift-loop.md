---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-08-10"
sources: ["../decisions/drift-capture-design.md", "../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../src/monitoring/drift_handler.py", "../../../src/monitoring/retrain_handler.py", "../../../src/serving/proxy_handler.py", "../../../src/pipeline/preprocess.py", "../../../src/pipeline/evaluate.py", "../../../src/pipeline/pipeline.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/evaluation-report-rollout-july-11-2026.md"]
summary: "Proxy capture, PSI drift evaluation, retraining, challenger evaluation, registry promotion, and endpoint deployment form a closed operational loop."
---
# Closed drift-to-retrain loop

## Confirmed

The proxy Lambda writes each request and score to an hour-partitioned S3
capture prefix. The preprocessing step writes the training distribution as a
baseline. An hourly Lambda compares the previous capture window with that
baseline through Population Stability Index. A violation event starts a new
pipeline execution through the retrain Lambda.

The challenger is evaluated before registration. A `ConditionStep` compares its test AUC with the current champion, so a drift signal can initiate training without automatically promoting a worse model. Approval of a registered package produces the deployment event that updates the endpoint.

Before the gate uses AUC, the `Evaluate` ProcessingStep now records the full
held-out test result in the artifacts bucket: metrics, row-level predictions,
and confusion-matrix, ROC, precision-recall, calibration, and score-
distribution charts. The report uses the exact same 0.50 threshold as the API;
its visual metrics therefore describe the deployed classification rule rather
than a disconnected offline cutoff.

The first live pipeline checkpoint failed in `Preprocess` because the Processing job could not import `src.common.schema`. That packaging issue is resolved: execution `<pipeline-execution-id>` completed preprocessing, training, and evaluation, logged test AUC `0.8398`, and registered approved model package `churn-model-group/1`.

The approval-to-endpoint handoff works for low-cost serving. The serverless
endpoint is `InService`, and API Gateway returns model predictions. A live
drift event has started a pipeline execution, and the retrain guard has
suppressed a duplicate while that run was active.

Execution `<pipeline-execution-id>` confirmed that this report path succeeds in the live
environment, producing AUC `0.8398` and the full S3 visual-artifact bundle.

## Synthesis

This is a feedback loop with a quality gate, not an unconditional retraining loop:

```text
traffic -> capture -> monitor -> violation -> pipeline -> challenger
                                               -> AUC gate -> registry -> approval -> endpoint
```

The loop separates detection, remediation, evaluation, and release. That makes failures diagnosable: a violation can exist without a successful training run, a training run can fail the quality gate, and a registered model can still await approval.

## Tensions or open questions

- `churn-serverless-dev` uses on-demand serverless inference without configured provisioned concurrency, so it does not retain a real-time hosting instance while idle.
- Built-in Model Monitor is **not** the route. See
  [drift capture design](../decisions/drift-capture-design.md) for the decision.
  Do not add `DataCaptureConfig` to the serverless configuration.
- That decision also fixes the loop's ceiling: churn labels are never observed
  after a prediction, so this loop can detect that the input traffic changed
  and can never detect that the model got worse.
- The current 0.50 threshold has recall `0.5370` on the held-out set. Choose a
  lower threshold only when the cost of retention offers and missed churn has
  been defined, then keep the report and proxy Lambda aligned.
