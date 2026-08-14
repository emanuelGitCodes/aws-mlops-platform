---
type: answer
title: How to explain this repo in an interview
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../overview.md", "../architecture/data-and-ingestion.md", "../architecture/permissions.md", "../architecture/deployment-and-pipeline-troubleshooting.md", "../concepts/contracts-and-preprocessing.md", "../concepts/closed-drift-loop.md", "../decisions/platform-design.md", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md"]
summary: "An interview-ready explanation organized around resources, event flow, contracts, permissions, and failure behavior."
---
# How to explain this repo in an interview

## Confirmed

Start with the outcome. This is a closed-loop AWS MLOps reference platform for
telco churn. The model is deliberately ordinary. The system shows ingestion,
training lineage, gated promotion, secure serving, and monitoring-driven
retraining.

Then walk the runtime in order:

1. S3 and EventBridge detect a new raw file.
2. SQS and its DLQ make the validation reliable.
3. The shared schema protects the data contract.
4. SageMaker trains and evaluates a challenger.
5. The registry and the approval event control the release.
6. API Gateway and the proxy Lambda protect the inference.
7. The drift Lambda and the retrain Lambda close the loop.

For the deployment, explain the separate control-plane path.
`${AWS_ADMIN_USER_NAME}` is the break-glass administrator.
`${MLOPS_DEPLOYER_USER_NAME}` is the normal CDK identity. CDK bootstrap creates
the standard roles and the asset bucket. CloudFormation then applies a separate
customer-managed execution policy. The deployment user assumes the CDK lookup,
deploy, and file-publishing roles only. It holds no direct application-service
permission and no IAM administration right.

## Synthesis

For each component, explain four things: the resource it owns, why it exists,
what permission it holds, and what happens when it fails. Two distinctions
matter most. Schema validation and feature encoding are different stages.
Training-data ingestion and inference requests are different flows.

Separate the three CDK commands as well. `synth` creates the local templates.
`diff` previews the changes. `deploy` asks CloudFormation to apply them. An IAM
inspection command fails under `${MLOPS_DEPLOYER_USER_NAME}`, and that failure
is the expected least-privilege behavior. Use `${AWS_ADMIN_USER_NAME}` for an
IAM inspection, and keep the deployment identity on the deployment path.

The deployment session gives an interview five concrete failures:

1. The denied actions showed which CloudFormation permissions the execution policy needed.
2. The Lambda packaging had to target Python 3.12, not the local Python 3.14.
3. The API authentication fix was separate from the missing SageMaker endpoint.
4. The ingestion accepted 7,043 rows.
5. The pipeline then failed at the Processing boundary, because the job did not package `src.common.schema`.

The lesson is to name the boundary of each failure. Do not describe "AWS
deployment" as one operation.

## Tensions or open questions

- Say clearly that CDK owns the infrastructure and the IAM wiring. The pipeline uses an SDK-driven setup, because it is a versioned live SageMaker object.
- Be explicit that training logs appear only after `Preprocess` succeeds. A successful ingestion Lambda log proves that curated data exists, not that SageMaker training has started.
