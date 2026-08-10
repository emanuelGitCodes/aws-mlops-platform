# AWS security hardening Phase 0 baseline

Date: 2026-07-12
Environment: `dev`
AWS Region: `us-east-1`
AWS account: `${AWS_ACCOUNT_ID}`

## Objective and mutation boundary

Capture a reproducible repository and AWS baseline before any security-hardening
change. Phase 0 used AWS read APIs plus one normal `/predict` invocation. It did
not update IAM, KMS, S3, API Gateway, SageMaker, CloudFormation, monitoring, or
security-service configuration. No training execution was started.

The AWS inspection identity was
`arn:aws:iam::${AWS_ACCOUNT_ID}:user/${AWS_ADMIN_USER_NAME}`. The restricted `${MLOPS_DEPLOYER_USER_NAME}`
profile was used only for `cdk diff --no-change-set`.

## Repository checkpoint

- Baseline commit: `3d59056` (`Document phased AWS security hardening roadmap`).
- The worktree already contained an uncommitted `README.md` architecture update
  from the preceding documentation task. Phase 0 preserved it and did not include
  it in the security baseline change set.
- The current source synthesizes six stacks: Data, Ingestion, Training, Registry,
  Serving, and Monitoring.

## CloudFormation state

| Stack | Live status | Termination protection | Important observation |
|---|---|---:|---|
| `Mlops-Dev-Data` | `UPDATE_ROLLBACK_COMPLETE` | Off | The attempted update tried to delete the artifacts-bucket export while Serving still imports it. |
| `Mlops-Dev-Ingestion` | `UPDATE_COMPLETE` | Off | Current validation Lambda is deployed. |
| `Mlops-Dev-Training` | `CREATE_COMPLETE` | Off | Owns the pipeline execution role; the SDK owns the pipeline definition. |
| `Mlops-Dev-Registry` | `CREATE_COMPLETE` | Off | Model package group is available. |
| `Mlops-Dev-Serving` | `UPDATE_COMPLETE` | Off | Endpoint deployment and proxy Lambdas are current. |
| `Mlops-Dev-Monitoring` | `CREATE_COMPLETE` | Off | Dashboard, alarm, and violation-event wiring exist. |

The Data rollback reason was:

```text
Delete canceled. Cannot delete export
Mlops-Dev-Data:ExportsOutputRefArtifactsBucket2AAC55442DB5E6C9
as it is in use by Mlops-Dev-Serving.
```

All three Data-stack buckets and their policies remain `CREATE_COMPLETE`; the
rollback did not delete data.

### Deployed processed-template fingerprints

The live processed templates were exported through `get-template` and
fingerprinted instead of committing full generated CloudFormation documents.
The exact live document can be re-exported with the recovery command below.

| Stack | SHA-256 |
|---|---|
| Data | `5ed72b31b76389efdf9c47ef29193fc513f16853ffc59fb54536168b2bd13f48` |
| Ingestion | `37d5ab2fca07b9b836c93ef3a3dbd639a04724dce2f18dcb7560ba82e4ce1739` |
| Training | `5aca45d7e71a7a4a071ef480e29d2ce145166fa5031518d9e863de0a86340899` |
| Registry | `9c6a921664a521fc4bedf73d786c5136607c0a72b79828588a2238c71675b8ec` |
| Serving | `ee3ae57226a6aae77f88e19702d5224ac1cf0b8bb83cef697ee398b61fc043a1` |
| Monitoring | `ceb1cb4c602a00689aea98fb37c35a27229aa209d3584640a94940a82faabd45` |

### Repository-to-live CDK diff

`cdk diff --no-change-set` reported differences in three stacks:

- Data: remove the artifacts-bucket export. This is the exact change that the
  live stack cannot apply while Serving imports the export.
- Ingestion: replace the `ValidateFn` Lambda asset hash.
- Serving: replace the `DeployFn` and `ProxyFn` Lambda asset hashes.
- Registry, Training, and Monitoring: no differences.

The diff also reported the deprecated CDK `logRetention` API and recommended
explicitly configuring the cross-stack-reference-strength feature flag. Neither
warning was changed in Phase 0.

Do not run `cdk deploy --all` from this checkpoint. Resolve and test the Data to
Serving export relationship before any future Data-stack deployment.

## Storage and ingestion evidence

All raw, curated, and artifacts buckets have:

- all four bucket-level S3 Block Public Access flags enabled;
- `IsPublic: false` policy status;
- Bucket Owner Enforced ownership;
- versioning enabled;
- default `aws:kms` encryption;
- SSE-C blocked.

The encryption key is the enabled AWS-managed S3 key (`KeyManager: AWS`), not a
customer-managed key. S3 Bucket Keys are not enabled.

The ingestion artifacts remain present:

| Object | Size | Evidence |
|---|---:|---|
| Raw `telco.csv` | 977,501 bytes | KMS-encrypted, versioned, modified 2026-07-11 02:49:18 UTC. |
| Curated `telco/telco.csv` | 977,501 bytes | KMS-encrypted, versioned, modified 2026-07-11 02:49:22 UTC. |

Their presence and matching size confirm the existing data checkpoint without
rewriting either object.

Account-level S3 Block Public Access is not configured. The protection currently
comes from each workload bucket's configuration.

## SageMaker pipeline and model evidence

- Pipeline `churn-training-pipeline-dev` is `Active`.
- Current pipeline version is 9, created 2026-07-11 20:42:43 ET.
- Version 9 contains the timestamped evaluation-output destination but has never
  been executed.
- Current pipeline-definition SHA-256:
  `0c7c29c017a1ae4ca37fbefdbe34e0f4afa0936d4146af01aa8e36b43cb11a19`.
- Latest execution `<pipeline-execution-id>` used version 8 and succeeded.
- Its `Preprocess`, `Train`, `Evaluate`, and `BeatsChampion` steps all succeeded.
- The successful execution retained eight report objects: the two JSON files,
  predictions CSV, and five PNG charts.
- Those objects remain under the older SageMaker-managed prefix because version
  8 predated the timestamped destination.
- The new top-level `evaluations/` prefix is empty until version 9 is executed.

The approved champion is model package `churn-model-group/1`, status
`Completed`, with customer metadata `test_auc=0.8398418749117607`. Its model
artifact is in the artifacts bucket under the successful training execution.

## Endpoint and API evidence

- Endpoint `churn-serverless-dev` is `InService`.
- It uses 2,048 MB serverless memory, maximum concurrency 5, and current instance
  count 0.
- Endpoint config is `churn-serverless-dev-config-<epoch>`.
- No `DataCaptureConfig` is present; built-in Model Monitor capture remains
  unavailable for this serverless endpoint.
- Network isolation is disabled; detailed observability is enabled.

API Gateway `${API_GATEWAY_ID}` is an available edge REST API. At this checkpoint:

- `POST /predict` has `authorizationType: NONE` and `apiKeyRequired: true`;
- the API reports security policy `TLS_1_0`;
- stage tracing is disabled and method settings are empty;
- the default execute-api endpoint is enabled.

A normal API-key request with `sample.json` returned:

```json
{"churn_probability": 0.3656342029571533, "churn": false}
```

This verifies the serving path without changing its configuration.

## IAM evidence

- Pipeline execution role: AWS-managed `AmazonSageMakerFullAccess` plus inline
  curated-bucket read and artifacts-bucket read/write permissions.
- Model execution role: AWS-managed `AmazonSageMakerFullAccess` plus inline
  artifacts-bucket read/write permissions.
- Deployment Lambda role: the expected Lambda basic role plus an inline
  SageMaker statement with `Resource: "*"`; `iam:PassRole` is correctly scoped
  to the exact model execution role.
- Proxy Lambda role: the expected Lambda basic role plus one scoped
  `sagemaker:InvokeEndpoint` permission for `churn-serverless-dev`.

These are evidence for the later role-by-role least-privilege phase. Phase 0 did
not modify them.

## Audit, detection, and cost baseline

At this checkpoint:

- CloudTrail customer trails: none;
- GuardDuty: not subscribed/enabled;
- Security Hub: not subscribed/enabled;
- AWS Config recorders: none;
- IAM Access Analyzer analyzers: none;
- regional WAFv2 web ACLs: none.

The endpoint 5xx alarm exists but is `INSUFFICIENT_DATA` and has no alarm action.
The `$20` monthly budget is healthy, reports actual spend `$0.00` and forecast
`$0.02`, and has no notifications. Cost Explorer results are estimated and may
lag usage.

## Recovery and comparison commands

All commands below are read-only unless a later operator deliberately passes the
output to a deployment command.

```zsh
# Re-export a deployed processed template.
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws cloudformation get-template \
  --stack-name Mlops-Dev-Data --template-stage Processed \
  --region us-east-1 --output json

# Re-check the failed Data update without retrying it.
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws cloudformation describe-stack-events \
  --stack-name Mlops-Dev-Data --region us-east-1

# Compare source to live without creating a CloudFormation change set.
AWS_PROFILE=${MLOPS_DEPLOYER_USER_NAME} cdk diff -c env=dev --no-change-set

# Re-export the current SDK-managed pipeline definition.
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-pipeline \
  --pipeline-name churn-training-pipeline-dev --region us-east-1 \
  --query PipelineDefinition --output text

# Re-check the last known-good pipeline execution and endpoint.
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-pipeline-execution \
  --pipeline-execution-arn \
  arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:pipeline/churn-training-pipeline-dev/execution/<pipeline-execution-id> \
  --region us-east-1
AWS_PROFILE=${AWS_ADMIN_USER_NAME} aws sagemaker describe-endpoint \
  --endpoint-name churn-serverless-dev --region us-east-1
```

## Phase 0 decision

Phase 0 is complete with one pre-existing deployment blocker recorded:
`Mlops-Dev-Data` cannot accept the current synthesized export removal while
Serving consumes that export. The runtime remains functional, and Phase 0 made
no configuration change.

The next allowed work is Phase 1, repository-only security guardrails. Do not
start Phase 2 or deploy all stacks until Phase 1 passes and the Data export diff
has an explicit remediation plan. Do not start a new billable pipeline execution
as part of Phase 1.
