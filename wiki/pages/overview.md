---
type: overview
title: AWS MLOps platform overview
created: "2026-07-10"
updated: "2026-07-11"
sources: ["../../README.md", "../../infra/app.py", "../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../raw/evaluation-report-rollout-july-11-2026.md"]
summary: "A portfolio-grade AWS platform whose closed loop produces gated models plus reproducible held-out evaluation reports."
---
# AWS MLOps platform overview

## Confirmed

The repository is a CDK application split into data, ingestion, training, registry, serving, and monitoring stacks. The model is intentionally simple; the engineering story is the closed operational loop around it.

The July 10 deployment verified the six-stack infrastructure and the raw-to-curated ingestion path. The current end-to-end checkpoint is documented in the [deployment and pipeline troubleshooting page](architecture/deployment-and-pipeline-troubleshooting.md): the SageMaker pipeline preprocesses, trains, evaluates, and registers an approved model, while the serverless endpoint returns protected API predictions. Each successful evaluation now writes a reproducible S3 report bundle with metrics, predictions, and five diagnostic charts. SageMaker Model Monitor capture is deferred because serverless endpoints do not support data capture.

The runtime path is:

1. Raw CSV data enters S3 and is validated into a curated bucket.
2. A SageMaker Pipeline preprocesses, trains, evaluates, and conditionally registers a challenger model.
3. An approved model is deployed to a SageMaker serverless endpoint and exposed through an API Gateway plus proxy Lambda.
4. Model Monitor observes captured traffic and can trigger retraining when drift violations occur.

## Synthesis

The most important boundaries are the [training and inference contracts](concepts/contracts-and-preprocessing.md), the [raw-data ingestion path](architecture/data-and-ingestion.md), and the [closed drift loop](concepts/closed-drift-loop.md). The platform's resource and permission choices are captured in [platform design decisions](decisions/platform-design.md) and [permission boundaries](architecture/permissions.md).

## Tensions or open questions

- The pipeline and Model Monitor are created or updated through SDK-driven scripts because they depend on live SageMaker state; this is a deliberate split from CDK-owned wiring and should be revisited if deployment requirements change.
- Infrastructure deployment, data ingestion, pipeline execution, and API serving have separate observable failure boundaries; successful CloudWatch ingestion logs do not prove that training or endpoint deployment succeeded.
