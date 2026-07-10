---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-07-10"
sources: ["../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../src/pipeline/pipeline.py"]
summary: "Captured inference traffic can produce a monitoring violation that starts a gated challenger training run and eventual redeployment."
---
# Closed drift-to-retrain loop

## Confirmed

The serving endpoint captures request and response data to S3. A Model Monitor schedule compares live traffic against a baseline. When the schedule emits `CompletedWithViolations`, EventBridge invokes a retrain Lambda, which starts the named SageMaker Pipeline.

The challenger is evaluated before registration. A `ConditionStep` compares its test AUC with the current champion, so a drift signal can initiate training without automatically promoting a worse model. Approval of a registered package produces the deployment event that updates the endpoint.

## Synthesis

This is a feedback loop with a quality gate, not an unconditional retraining loop:

```text
traffic -> capture -> monitor -> violation -> pipeline -> challenger
                                               -> AUC gate -> registry -> approval -> endpoint
```

The loop separates detection, remediation, evaluation, and release. That makes failures diagnosable: a violation can exist without a successful training run, a training run can fail the quality gate, and a registered model can still await approval.

## Tensions or open questions

- The monitor baseline and schedule require a live endpoint and are configured by `scripts/setup_monitor.py`; the deployment workflow should keep this operational dependency visible.
