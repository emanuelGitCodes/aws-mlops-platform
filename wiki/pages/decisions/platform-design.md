---
type: decision
title: Platform design decisions
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../../README.md", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py"]
summary: "The platform favors managed SageMaker lineage where it matters and small AWS primitives where simple event wiring is clearer."
---
# Platform design decisions

## Confirmed

- **Serving:** SageMaker Serverless Inference avoids paying for idle capacity and keeps the model in the SageMaker registry ecosystem; cold-start latency is accepted and named.
- **Managed versus primitive services:** SageMaker owns training, registry, and monitoring lineage. S3, SQS, EventBridge, and Lambda provide simpler ingestion and integration boundaries.
- **Orchestration:** SageMaker Pipelines provide step lineage and caching without introducing a separate hand-built orchestrator.
- **Promotion:** A challenger MUST beat the champion test AUC before registration. The gate stops a silent regression.
- **Infrastructure as code:** CDK keeps infrastructure and ML code in Python while allowing SDK-driven configuration for live SageMaker objects.
- **CI authentication:** GitHub OIDC avoids long-lived cloud keys in repository secrets.

## Synthesis

The design consistently spends complexity where it buys lineage, quality, or safety, and uses primitives for straightforward transport. This is the rationale behind the [permission boundaries](../architecture/permissions.md) and the [closed loop](../concepts/closed-drift-loop.md).

## Tensions or open questions

- “One command to a working platform” is a useful portfolio goal. The live
  endpoint setup still needs SDK-driven steps and environment-specific outputs.
