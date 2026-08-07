---
type: architecture
title: AWS resource and permission boundaries
created: "2026-07-10"
updated: "2026-07-30"
sources: ["../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../../raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md"]
summary: "Runtime roles are separated by component, while the phased hardening roadmap removes the remaining broad SageMaker policies one role at a time."
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

A third human boundary is the read-only investigation identity,
`${AWS_SECURITY_AUDITOR_USER_NAME}`. It performs pre-flight baselines and
post-deploy verification without mutation rights, and since Phase 2E it also
holds the hand-managed inline policy `mlops-dev-auditor-audit-log-read`:
`logs:FilterLogEvents` on the `/aws/cloudtrail/mlops-dev-audit` log group plus
`kms:Decrypt` on the audit key, confined by the log-group encryption context.
This lets the auditor attribute a security-alarm fire from the audit trail
instead of generating a fresh denial by trying. Like the identity itself, the
policy is deliberately managed outside CDK — human identities stay out of the
stacks — and any change to it is an explicit recorded `${AWS_ADMIN_USER_NAME}`
action. `budgets:ViewBudget` remains outside the auditor scope. See the
[Phase 2E record](../sources/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md).

The [phased security hardening roadmap](phased-security-hardening.md) preserves
these component boundaries while replacing broad SageMaker managed policies.
It changed the proxy, model, deployment, and pipeline roles independently, with
a live component check after each role so an `AccessDenied` can be attributed to
one policy change. All four have landed and no role attaches
`AmazonSageMakerFullAccess` any more. `AWSLambdaBasicExecutionRole` is a
separate residue: 5A and 5C took the proxy and deploy Lambdas off it, but
`ValidateFn`, `RetrainTriggerFn`, and the CDK provider Lambdas still carry it,
each with its own acknowledgement in `infra/security_checks.py`.

## Tensions or open questions

- The Phase 5D follow-up about Model Monitor sharing the pipeline role is
  closed, and not by splitting that role. Model Monitor is out of the platform:
  the drift loop now runs as `DriftEvaluationFn` with an execution role of its
  own, which reads the capture prefix and the baseline and writes nothing. See
  [drift capture design](../decisions/drift-capture-design.md). The pipeline
  role keeps the `monitor/` prefix, which the preprocessing step now writes.
- Phase 6 changes the serving access boundary from API-key identification to
  IAM/SigV4 authorization. The inference response contract does not change.
