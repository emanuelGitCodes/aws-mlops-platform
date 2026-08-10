---
type: architecture
title: AWS security hardening Phase 0 baseline
created: "2026-07-12"
updated: "2026-08-10"
sources: ["../../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../../raw/aws-free-plan-account-service-limits-july-18-2026.md", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../../src/pipeline/pipeline.py"]
summary: "The pre-hardening dev baseline is captured: runtime paths work, security gaps are measured, and the Data-stack export rollback blocks an all-stack deploy."
---
# AWS security hardening Phase 0 baseline

## Confirmed

Phase 0 completed on July 12, 2026 using read-only AWS inspection plus one normal
API smoke request. It changed no AWS configuration and started no SageMaker
execution. The inspection identity was the existing `${AWS_ADMIN_USER_NAME}` break-glass
user; `${MLOPS_DEPLOYER_USER_NAME}` was used only for a CDK diff without a change set.

### Working runtime checkpoints

| Boundary | Evidence |
|---|---|
| Storage and ingestion | Raw and curated Telco objects are present with matching 977,501-byte sizes; all workload buckets are private, versioned, Bucket Owner Enforced, and encrypted with the AWS-managed S3 KMS key. |
| Pipeline | `churn-training-pipeline-dev` is Active. Execution `<pipeline-execution-id>` succeeded through Preprocess, Train, Evaluate, and BeatsChampion. |
| Evaluation | The successful version-8 run retains JSON, CSV, and all five PNG charts under its older execution prefix. |
| Registry | Approved package `churn-model-group/1` is Completed with test AUC `0.8398418749117607`. |
| Serving | `churn-serverless-dev` is InService with 2,048 MB memory, concurrency 5, and zero current instances. |
| API | An API-key request returned probability `0.3656342029571533` and `churn: false`. |

Pipeline version 9 contains the new
`evaluations/<timestamp>/<execution-id>/` destination but has not been executed.
The empty `evaluations/` prefix is therefore expected and is not a report
failure.

### Deployment blocker captured before hardening

Five stacks are `CREATE_COMPLETE` or `UPDATE_COMPLETE`. `Mlops-Dev-Data` is
`UPDATE_ROLLBACK_COMPLETE`. Its attempted update tried to remove the
artifacts-bucket CloudFormation export while `Mlops-Dev-Serving` still imports
that value. The buckets remain present and functional, but an all-stack deploy
would repeat this failure.

The no-change-set CDK diff confirmed the same export removal. It also showed
new Lambda asset hashes for Ingestion validation and the two Serving functions;
Registry, Training, and Monitoring had no differences. These differences are
baseline evidence, not Phase 0 deployments.

### Measured security starting point

- Workload buckets have all bucket-level public-access blocks, TLS-only bucket
  policies, versioning, AWS-managed SSE-KMS, and no public policy.
- Account-level S3 Block Public Access is absent.
- Pipeline and model execution roles attach `AmazonSageMakerFullAccess`.
- The deploy Lambda has a SageMaker `Resource: "*"` statement; its
  `iam:PassRole` is scoped correctly.
- The proxy can invoke only `churn-serverless-dev`.
- `/predict` uses `authorizationType: NONE` plus a required API key, reports a
  `TLS_1_0` policy, and has no stage tracing or method settings.
- CloudTrail customer trails, GuardDuty, Security Hub, Config recorders, Access
  Analyzer, and WAF are absent.
- The endpoint 5xx alarm has no notification action and is
  `INSUFFICIENT_DATA`.
- The healthy `$20` budget forecasts `$0.02` but has no notifications.

The complete template fingerprints, pipeline-definition fingerprint, role
documents, resource identifiers, and recovery commands are preserved in the
[immutable Phase 0 source](../sources/aws-security-hardening-phase-0-baseline-july-12-2026.md).

## Synthesis

The baseline probes that returned `SubscriptionRequiredException` for
GuardDuty and Security Hub were later explained on July 18: the account is on
the AWS Free account plan, which blocks those paid-only services at the
billing level (reads included), while AWS Config — which answered its
describe call normally — is plausibly inside the allowed set. See
[AWS Free-plan account service limits](../sources/aws-free-plan-account-service-limits-july-18-2026.md).

The platform is usable but not ready for a broad CDK deployment. Phase 0
success means that the baseline is trustworthy and later regressions have a
comparison point; it does not mean the recorded gaps are fixed.

Phase 1 repository and CI guardrails are now complete. Audit and detection
remain Phase 2 and require a separate go/no-go decision. Before any future
Data-stack or all-stack deployment, preserve the artifacts-bucket export or
update its consumer relationship in a separately reviewed change.

The rollback hierarchy is:

1. Compare against commit `3d59056` while preserving the pre-existing README
   worktree change.
2. Re-export the live processed CloudFormation template and compare its recorded
   SHA-256 fingerprint.
3. Re-export SageMaker pipeline version 9 and compare its recorded definition
   fingerprint.
4. Use successful execution `<pipeline-execution-id>`, model package `/1`, and endpoint
   config `churn-serverless-dev-config-<epoch>` as the last-known-good runtime
   checkpoints.
5. Never delete or rewrite retained bucket objects as part of a rollback audit.

## Tensions or open questions

- The Data export relationship must be resolved before a future `deploy --all`.
- Pipeline version 9 still requires a later billable run to prove its timestamped
  report destination; that is not part of Phase 0 or Phase 1.
- Detailed cost remains subject to AWS billing delay.
- Phase 9 eventually replaces long-lived administrator access, but disabling it
  before temporary Identity Center access is proven would risk lockout.
