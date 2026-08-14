---
type: architecture
title: AWS resource and permission boundaries
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../../raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md"]
summary: "Runtime roles are separated by component, while the phased hardening roadmap removes the remaining broad SageMaker policies one role at a time."
---
# AWS resource and permission boundaries

## Confirmed

| Component | Main resource | Permission boundary |
|---|---|---|
| Data | Raw, curated, and artifacts S3 buckets | Each bucket stays private, TLS-only, KMS-encrypted, versioned, and retained. |
| Ingestion | Validation Lambda, SQS queue, DLQ | The Lambda reads a raw object and writes a curated object. SQS invokes the Lambda. |
| Training | SageMaker pipeline execution role | SageMaker assumes the role. The role reads curated data and reads and writes artifacts. |
| Serving | API Gateway, proxy Lambda, serverless endpoint | A caller MUST sign the request with SigV4. Only the proxy invokes the endpoint. |
| Deployment | Approval-event deploy Lambda | The Lambda updates the endpoint after a model-package approval event. |
| Monitoring | Retrain-trigger Lambda, EventBridge rule | The trigger starts the configured SageMaker pipeline only. |

## Synthesis

The platform separates resource ownership from runtime authority. CDK defines
the durable resources and the wiring. Each Lambda role or SageMaker role is the
narrow actor at one boundary. The public API therefore never gets direct
`sagemaker:InvokeEndpoint` access, and the
[ingestion path](data-and-ingestion.md) fails independently of serving.

The runtime boundaries are separate from the human deployment boundary. The
`${MLOPS_DEPLOYER_USER_NAME}` identity assumes the CDK bootstrap roles.
CloudFormation then applies the templates through its own execution role. See
[CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md) for the
control-plane flow and its verification checkpoints.

The third human boundary is the read-only investigation identity,
`${AWS_SECURITY_AUDITOR_USER_NAME}`. It does the pre-flight baselines and the
post-deploy verification, and it holds no mutation rights. Since Phase 2E it
also holds the hand-managed inline policy `mlops-dev-auditor-audit-log-read`.
That policy grants `logs:FilterLogEvents` on the
`/aws/cloudtrail/mlops-dev-audit` log group and `kms:Decrypt` on the audit key,
and the log-group encryption context confines it. The auditor can therefore
attribute a security-alarm fire from the audit trail, instead of making a fresh
denial through a trial call. A human keeps this policy outside CDK, as it keeps
the identity itself outside CDK. Every change to the policy MUST be an explicit
`${AWS_ADMIN_USER_NAME}` action, and the operator MUST record it on this page.
`budgets:ViewBudget` stays outside the auditor scope. See the
[Phase 2E record](../sources/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md).

The [phased security hardening roadmap](phased-security-hardening.md) keeps
these component boundaries and replaces the broad SageMaker managed policies. It
changed the proxy, model, deployment, and pipeline roles one at a time. A live
component check followed each role, so one `AccessDenied` points at one policy
change. All four roles landed, and no role attaches
`AmazonSageMakerFullAccess` now. `AWSLambdaBasicExecutionRole` is a separate
remainder. Phases 5A and 5C took the proxy Lambda and the deploy Lambda off it.
`ValidateFn`, `RetrainTriggerFn`, and the CDK provider Lambdas still carry it,
and each one has its own acknowledgement in `infra/security_checks.py`.

## Tensions or open questions

- The Phase 5D follow-up asked whether Model Monitor shares the pipeline role.
  That question is closed, and a role split did not close it. The platform does
  not use Model Monitor. The drift loop runs as `DriftEvaluationFn` with its own
  execution role. That role reads the capture prefix and the baseline, and it
  writes nothing. See
  [drift capture design](../decisions/drift-capture-design.md). The pipeline
  role keeps the `monitor/` prefix, which the preprocessing step writes.
- Phase 6 moved the serving access boundary from API-key identification to
  IAM SigV4 authorization. The account holds no API key and no usage plan. The
  inference response contract did not change.
