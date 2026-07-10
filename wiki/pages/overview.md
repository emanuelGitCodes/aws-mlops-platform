---
type: overview
title: AWS MLOps platform overview
created: "2026-07-10"
updated: "2026-07-10"
sources: ["../../README.md", "../../infra/app.py"]
summary: "A portfolio-grade AWS platform whose main deliverable is the closed drift-to-retrain-to-deploy engineering loop."
---
# AWS MLOps platform overview

## Confirmed

The repository is a CDK application split into data, ingestion, training, registry, serving, and monitoring stacks. The model is intentionally simple; the engineering story is the closed operational loop around it.

The runtime path is:

1. Raw CSV data enters S3 and is validated into a curated bucket.
2. A SageMaker Pipeline preprocesses, trains, evaluates, and conditionally registers a challenger model.
3. An approved model is deployed to a SageMaker serverless endpoint and exposed through an API Gateway plus proxy Lambda.
4. Model Monitor observes captured traffic and can trigger retraining when drift violations occur.

## Synthesis

The most important boundaries are the [training and inference contracts](concepts/contracts-and-preprocessing.md), the [raw-data ingestion path](architecture/data-and-ingestion.md), and the [closed drift loop](concepts/closed-drift-loop.md). The platform's resource and permission choices are captured in [platform design decisions](decisions/platform-design.md) and [permission boundaries](architecture/permissions.md).

## Tensions or open questions

- The pipeline and Model Monitor are created or updated through SDK-driven scripts because they depend on live SageMaker state; this is a deliberate split from CDK-owned wiring and should be revisited if deployment requirements change.
