---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-08-21"
sources: ["../decisions/drift-capture-design.md", "../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../infra/stacks/security_stack.py", "../../../src/monitoring/drift_handler.py", "../../../src/monitoring/retrain_handler.py", "../../../src/serving/proxy_handler.py", "../../../src/pipeline/preprocess.py", "../../../src/pipeline/evaluate.py", "../../../src/pipeline/pipeline.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/evaluation-report-rollout-july-11-2026.md"]
summary: "Proxy capture, PSI drift evaluation, retraining, challenger evaluation, registry promotion, and endpoint deployment form a closed operational loop."
---
# Closed drift-to-retrain loop

## Confirmed

The proxy Lambda writes each request and score to an hour-partitioned S3
capture prefix. The preprocessing step writes the training distribution as a
baseline. An hourly Lambda compares the previous capture window with that
baseline through Population Stability Index. A violation event starts a new
pipeline execution through the retrain Lambda.

The pipeline evaluates the challenger before registration. A `ConditionStep`
compares the challenger test AUC with the champion test AUC. A drift signal
therefore starts training but does not promote a worse model. Approval of a
registered package sends the deployment event that updates the endpoint.

Before the gate uses AUC, the `Evaluate` ProcessingStep now records the full
held-out test result in the artifacts bucket: metrics, row-level predictions,
and confusion-matrix, ROC, precision-recall, calibration, and score-
distribution charts. The report uses the same 0.50 threshold as the API. Its
visual metrics therefore describe the deployed classification rule, not a
separate offline threshold.

The first live pipeline checkpoint failed in `Preprocess`, because the
Processing job could not import `src.common.schema`. The repository fixed that
packaging defect. Execution `<pipeline-execution-id>` then completed
preprocessing, training, and evaluation. It logged test AUC `0.8398` and
registered the approved model package `churn-model-group/1`.

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

The loop separates detection, remediation, evaluation, and release. Each stage
therefore fails on its own. A violation can exist without a successful training
run. A training run can fail the quality gate. A registered model can wait for
approval.

### The failure signal

SageMaker publishes no CloudWatch metric for a failed pipeline execution, so no
alarm can watch one. `mlops-<env>-ops-pipeline-failed` is an EventBridge rule
instead. It matches `SageMaker Model Building Pipeline Execution Status Change`
for the `Failed` and `Stopped` states of this environment's pipeline, and it
sends a readable line to `mlops-<env>-ops-alerts`.

Two grants in `SecurityStack` carry the message: `sns:Publish` on the ops topic,
and `kms:Decrypt` with `kms:GenerateDataKey*` on the audit key. Both conditions
scope the source ARN to `mlops-<env>-ops-*`. Any operational rule that pages the
operator MUST keep that name prefix.

The rule target reads the topic through `Topic.from_topic_arn`. An imported
topic has an immutable resource policy. A mutable one makes the CDK SNS target
add its own publish grant for `events.amazonaws.com` with no source condition.

### The handler error alarms

Five handlers carry the platform: `ingest`, `proxy`, `deploy`, `drift`, and
`retrain`. Each one now has a `mlops-<env>-<slug>-errors` alarm on its Lambda
`Errors` metric, at a threshold of one error over fifteen minutes. Every alarm
publishes to `mlops-<env>-ops-alerts`. `handler_error_alarm` in
`infra/stacks/shared.py` builds all five.

One error is the correct threshold. Each handler runs a few times each hour at
most, so a single exception is already a broken edge. The alarms treat missing
data as not breaching, because an idle handler publishes no datapoint.

The `deploy` alarm closes the widest gap. A deploy handler that throws leaves
the endpoint on the old model while the registry shows the new package as
approved. Nothing else in the platform compares those two facts.

## Tensions or open questions

- `churn-serverless-dev` uses on-demand serverless inference and configures no
  provisioned concurrency. It therefore keeps no hosting instance while idle.
- Built-in Model Monitor is **not** the route. See
  [drift capture design](../decisions/drift-capture-design.md) for the decision.
  Do not add `DataCaptureConfig` to the serverless configuration.
- That decision also sets the limit of the loop. The platform never receives a
  churn label after a prediction. The loop can therefore detect a change in the
  input traffic. It can never detect that the model got worse.
- The current 0.50 threshold has recall `0.5370` on the held-out set. Define the
  cost of a retention offer and the cost of missed churn first. Only then choose
  a lower threshold, and keep the report and the proxy Lambda on the same value.
