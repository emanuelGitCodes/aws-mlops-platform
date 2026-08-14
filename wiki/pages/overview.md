---
type: overview
title: AWS MLOps platform overview
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../README.md", "../../infra/app.py", "../../infra/stacks/monitoring_stack.py", "../../src/monitoring/drift_handler.py", "../../src/monitoring/retrain_handler.py", "../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../raw/evaluation-report-rollout-july-11-2026.md", "../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../raw/aws-security-hardening-phase-1-implementation-july-12-2026.md", "../raw/aws-security-hardening-phase-1-completion-july-12-2026.md"]
summary: "A portfolio-grade AWS platform with gated models, reproducible evaluation reports, and a deployed drift-to-retrain loop."
---
# AWS MLOps platform overview

## Confirmed

The repository is a nine-stack CDK application. The model is deliberately
simple. The closed operational loop around the model is the engineering work
that matters.

The SageMaker pipeline preprocesses, trains, evaluates, and conditionally
registers a model. The serverless endpoint returns IAM-authorized API
predictions. Each evaluation writes metrics, predictions, and five diagnostic
charts. The proxy captures live inputs and scores for the PSI drift job.

The runtime path is:

1. Raw CSV data enters S3. The validation Lambda writes each accepted row to the curated bucket.
2. A SageMaker Pipeline preprocesses, trains, evaluates, and conditionally registers a challenger model.
3. The deploy Lambda sends an approved model to a SageMaker serverless endpoint. API Gateway and the proxy Lambda expose that endpoint.
4. The proxy writes an hour-partitioned capture record for each prediction.
5. The hourly drift Lambda compares the capture window with the training
   baseline and emits a violation when enough columns move.
6. The retrain Lambda starts one pipeline execution and suppresses duplicates.

## Synthesis

Three boundaries matter most: the
[training and inference contracts](concepts/contracts-and-preprocessing.md), the
[raw-data ingestion path](architecture/data-and-ingestion.md), and the
[closed drift loop](concepts/closed-drift-loop.md). Two pages hold the resource
and permission choices: [platform design decisions](decisions/platform-design.md)
and [permission boundaries](architecture/permissions.md).

The approved improvement is the
[phased AWS security hardening roadmap](architecture/phased-security-hardening.md).
Phases 0-2, 5, and 6 are complete. Phase 3 is partial. Phase 4 and Phases 7-9
are not started.

Two navigation aids sit beside this wiki. The
[generated CDK diagrams](architecture/generated-cdk-diagrams.md) render the
synthesized resource graph. The
[graphify code graph](decisions/graphify-knowledge-graph.md) indexes the source
tree and these pages together. A tool builds each one from the repository.
Neither replaces a page here.

## Tensions or open questions

- SDK-driven scripts create and update the pipeline and Model Monitor, because
  both depend on live SageMaker state. This is a deliberate split from the
  CDK-owned wiring. Reopen the split if the deployment requirements change.
- Four parts fail independently: infrastructure deployment, data ingestion,
  pipeline execution, and API serving. A successful CloudWatch ingestion log
  does not prove that training or endpoint deployment succeeded.
