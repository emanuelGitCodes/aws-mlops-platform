---
type: architecture
title: AWS resource and permission boundaries
created: "2026-07-10"
updated: "2026-07-10"
sources: ["../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py"]
summary: "Each runtime component receives only the storage, invocation, or orchestration permissions needed for its position in the loop."
---
# AWS resource and permission boundaries

## Confirmed

| Component | Main resource | Permission boundary |
|---|---|---|
| Data | Raw, curated, and artifacts S3 buckets | Buckets are private, TLS-only, KMS-encrypted, versioned, and retained. |
| Ingestion | Validation Lambda, SQS queue, DLQ | Lambda reads raw objects and writes curated objects; SQS invokes the Lambda. |
| Training | SageMaker pipeline execution role | Reads curated data and reads/writes artifacts; the role is assumed by SageMaker. |
| Serving | API Gateway, proxy Lambda, serverless endpoint | API clients need an API key; only the proxy invokes the endpoint. |
| Deployment | Approval-event deploy Lambda | Updates the endpoint after a model-package approval event. |
| Monitoring | Retrain-trigger Lambda, EventBridge rule | The trigger may start only the configured SageMaker pipeline. |

## Synthesis

The platform separates resource ownership from runtime authority. CDK defines durable resources and wiring, while each Lambda or SageMaker role is the narrow actor at one boundary. This is why the public API never receives direct `sagemaker:InvokeEndpoint` access and why the [ingestion path](data-and-ingestion.md) can fail independently of serving.

These runtime boundaries are separate from the human deployment boundary. The `${MLOPS_DEPLOYER_USER_NAME}` identity assumes CDK bootstrap roles, while CloudFormation uses its own execution role to apply the templates. See [CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md) for the control-plane flow and its verification checkpoints.

## Tensions or open questions

- The training role currently attaches the AWS-managed `AmazonSageMakerFullAccess` policy. It is convenient for a reference platform, but a production hardening pass should replace it with an action- and resource-scoped policy.
