---
type: overview
title: AWS MLOps platform overview
created: "2026-07-10"
updated: "2026-08-10"
sources: ["../../README.md", "../../infra/app.py", "../../infra/stacks/monitoring_stack.py", "../../src/monitoring/drift_handler.py", "../../src/monitoring/retrain_handler.py", "../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../raw/evaluation-report-rollout-july-11-2026.md", "../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../raw/aws-security-hardening-phase-1-implementation-july-12-2026.md", "../raw/aws-security-hardening-phase-1-completion-july-12-2026.md"]
summary: "A portfolio-grade AWS platform with gated models, reproducible evaluation reports, and a deployed drift-to-retrain loop."
---
# AWS MLOps platform overview

## Confirmed

The repository is a nine-stack CDK application. The model is intentionally
simple; the engineering story is the closed operational loop around it.

The SageMaker pipeline preprocesses, trains, evaluates, and conditionally
registers a model. The serverless endpoint returns IAM-authorized API
predictions. Each evaluation writes metrics, predictions, and five diagnostic
charts. The proxy captures live inputs and scores for the PSI drift job.

The runtime path is:

1. Raw CSV data enters S3 and is validated into a curated bucket.
2. A SageMaker Pipeline preprocesses, trains, evaluates, and conditionally registers a challenger model.
3. An approved model is deployed to a SageMaker serverless endpoint and exposed through an API Gateway plus proxy Lambda.
4. The proxy writes an hour-partitioned capture record for each prediction.
5. The hourly drift Lambda compares the capture window with the training
   baseline and emits a violation when enough columns move.
6. The retrain Lambda starts one pipeline execution and suppresses duplicates.

## Synthesis

The most important boundaries are the [training and inference contracts](concepts/contracts-and-preprocessing.md), the [raw-data ingestion path](architecture/data-and-ingestion.md), and the [closed drift loop](concepts/closed-drift-loop.md). The platform's resource and permission choices are captured in [platform design decisions](decisions/platform-design.md) and [permission boundaries](architecture/permissions.md).

The approved improvement is the
[phased AWS security hardening roadmap](architecture/phased-security-hardening.md).
Phases 0-2 and 5 are complete. Phase 3 is partial, and Phase 6 is deployed to
dev with observation open. Phase 4 and Phases 7-9 are not started.

## Tensions or open questions

- The pipeline and Model Monitor are created or updated through SDK-driven scripts because they depend on live SageMaker state; this is a deliberate split from CDK-owned wiring and should be revisited if deployment requirements change.
- Infrastructure deployment, data ingestion, pipeline execution, and API serving have separate observable failure boundaries; successful CloudWatch ingestion logs do not prove that training or endpoint deployment succeeded.
