---
type: answer
title: How to explain this repo in an interview
created: "2026-07-10"
updated: "2026-07-11"
sources: ["../overview.md", "../architecture/data-and-ingestion.md", "../architecture/permissions.md", "../architecture/deployment-and-pipeline-troubleshooting.md", "../concepts/contracts-and-preprocessing.md", "../concepts/closed-drift-loop.md", "../decisions/platform-design.md", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "An interview-ready explanation organized around resources, event flow, contracts, permissions, and failure behavior."
---
# How to explain this repo in an interview

## Confirmed

Start with the outcome: this is a closed-loop AWS MLOps reference platform for telco churn. The model is intentionally ordinary; the system demonstrates ingestion, training lineage, gated promotion, secure serving, and monitoring-driven retraining.

Then walk the runtime in order: S3 and EventBridge detect a new raw file, SQS and its DLQ make validation reliable, the shared schema protects the data contract, SageMaker trains and evaluates a challenger, the registry and approval event control release, API Gateway and the proxy Lambda protect inference, and Model Monitor closes the loop.

For deployment, explain the separate control-plane path: `${AWS_ADMIN_USER_NAME}` is the break-glass administrator, `${MLOPS_DEPLOYER_USER_NAME}` is the normal CDK identity, CDK bootstrap creates the standard roles and asset bucket, and CloudFormation applies a separate customer-managed execution policy. The deployment user can assume only the CDK lookup, deploy, and file-publishing roles; it does not receive direct application-service permissions or IAM administration rights.

## Synthesis

For each component, explain four things: the resource it owns, why it exists, what permission it has, and what happens when it fails. The most important distinction is that schema validation and feature encoding are different stages, while training-data ingestion and inference requests are different flows.

Also distinguish the CDK lifecycle: `synth` creates local templates, `diff` previews changes, and `deploy` asks CloudFormation to apply them. If an IAM inspection command fails under `${MLOPS_DEPLOYER_USER_NAME}`, that is expected least-privilege behavior; use `${AWS_ADMIN_USER_NAME}` for IAM inspection and keep the deployment identity focused on the deployment path.

The deployment session provides a concrete failure narrative for an interview: CloudFormation permissions were added from specific denied actions; Lambda packaging had to target Python 3.12 rather than the local Python 3.14; API authentication was fixed separately from the missing SageMaker endpoint; ingestion accepted 7,043 rows; and the pipeline then failed at the Processing boundary because `src.common.schema` was not packaged. The key lesson is to name the boundary where each failure occurred instead of treating “AWS deployment” as one operation.

## Tensions or open questions

- Be explicit that CDK owns infrastructure and IAM wiring, while the pipeline and monitor use SDK-driven setup because they are versioned or live SageMaker objects.
- Be explicit that training logs appear only after `Preprocess` succeeds. A successful ingestion Lambda log proves that curated data exists, not that SageMaker training has started.
