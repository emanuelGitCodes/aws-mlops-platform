# AWS security hardening Phase 5C — deploy execution role, August 5-6, 2026

Raw evidence for the third of the four roles Phase 5 converts one at a time.
All timestamps UTC. Account identifiers are `${AWS_ACCOUNT_ID}` placeholders and
generated resource suffixes are written `<suffix>`.

## Pre-flight inventory, 2026-08-05

Repository green state before any edit:

```
make lint       clean
make typecheck  clean (36 source files)
make test       232 passed, coverage 92.54% (floor 92.54)
make synth-all  dev and prod both clean
```

40 cdk-nag acknowledgements in dev (24 name Phase 5), 37 in prod (22 name
Phase 5). The three bound to `DeployFn`:

```
serving  DeployFn/ServiceRole                AwsSolutions-IAM4[...AWSLambdaBasicExecutionRole]
serving  DeployFn/ServiceRole/DefaultPolicy  AwsSolutions-IAM5[Resource::*]
serving  DeployFn                            AwsSolutions::AwsSolutions-L1     <- function, not role
```

Live `DeployFn` resources before the change:

```
DeployFn0FE820C6                          Mlops-Dev-Serving-DeployFn<suffix>
DeployFnServiceRoleA27EDF94               Mlops-Dev-Serving-DeployFnServiceRole<suffix>
DeployFnServiceRoleDefaultPolicy7D43372B  Mlops-Deplo-<suffix>
DeployFnLogs7E53DC7A                      Mlops-Dev-Serving-DeployFnLogs<suffix>
```

### CloudTrail evidence, 90 days (2026-05-07 → 2026-08-05)

Read with the security-auditor identity. Every event attributed to the DeployFn
session, no errors:

| Count | Event | Resource shape observed |
|---|---|---|
| 5 | `CreateModel` | `churn-serverless-dev-model-<epoch>`; `containers[0].modelPackageName` = the registry ARN below |
| 5 | `CreateEndpointConfig` | `churn-serverless-dev-config-<epoch>` |
| 1 | `CreateEndpoint` | `churn-serverless-dev` (first deploy, 2026-07-11) |
| 1 | `UpdateEndpoint` | `churn-serverless-dev` (2026-08-05, the 5B forced cold start) |
| 2 | `DescribeEndpoint` | `churn-serverless-dev` |
| 2 | `DescribeModelPackage` | the registry ARN below |
| 3 | `CreateLogStream` | `/aws/lambda/…` pre-Phase-K, `Mlops-Dev-Serving-DeployFnLogs<suffix>` after |
| 3 | `Decrypt` | see below |

`list-model-packages` confirmed the ARN shape before it was scoped to:

```
arn:aws:sagemaker:<region>:${AWS_ACCOUNT_ID}:model-package/churn-model-group/1
```

**Not observed, therefore not granted:**

- No `CreateLogGroup`. CDK owns the group, so `log_group.grant_write`
  (`CreateLogStream` + `PutLogEvents`) is the whole need. `PutLogEvents` is a
  CloudTrail data event and is not recorded; delivered log streams are the
  evidence it works.
- No `DeleteModel` / `DeleteEndpointConfig`. The handler never removes
  superseded revisions.
- No `List*` of any kind.
- **`kms:Decrypt` deliberately not granted.** The three `Decrypt` calls are the
  Lambda service decrypting the function's environment variables at cold start:
  encryption context `{"aws:lambda:FunctionArn": "…:DeployFn…"}` against the
  AWS-managed `aws/lambda` key. The role carries no `kms:Decrypt` and all three
  succeeded — they are authorized by that key's own resource policy, not by this
  role's identity policy. Dropping `AWSLambdaBasicExecutionRole` cannot affect
  them; it never granted KMS either.

## Change

`DeployFn` sets the existing `least_privilege_logs=True` opt-in on
`platform_lambda`, so CDK attaches no managed policy and the only log grant is
writing to the group the same call creates. The six-action `Resource: "*"`
statement is replaced by five resource-scoped statements:

```
sagemaker:CreateModel                             -> model/churn-serverless-dev-model-*
sagemaker:CreateEndpointConfig                    -> endpoint-config/churn-serverless-dev-config-*
sagemaker:CreateEndpoint, sagemaker:UpdateEndpoint-> endpoint/churn-serverless-dev
                                                     endpoint-config/churn-serverless-dev-config-*
sagemaker:DescribeEndpoint                        -> endpoint/churn-serverless-dev
sagemaker:DescribeModelPackage                    -> model-package/churn-model-group/*
logs:CreateLogStream, logs:PutLogEvents           -> Fn::GetAtt DeployFnLogs.Arn
iam:PassRole                                      -> Fn::GetAtt ModelExecutionRole.Arn  (unchanged)
```

The two trailing wildcards are inherent: `deploy_handler` suffixes every model
and endpoint-config name with the epoch second.

`endpoint_arn` was hoisted above `DeployFn` and reused by the proxy's
`sagemaker:InvokeEndpoint` statement, which previously built the same ARN
inline. The template output is byte-identical.

### Acknowledgements: 40 → 41 in dev

Two coarse entries removed, three exact ARN-scoped entries added at
`DeployFnRole/DefaultPolicy`. The count rises, and honestly so.

Those strings embed the model package group, which differs per environment
(`churn-model-group` in dev, `churn-model-group-prod` in prod), so a third token
`{group}` was added. Rather than grow the signature again,
`resolved_acknowledgements` now takes the whole `PlatformConfig` instead of
`(env_name, prefix)`.

## Template delta, reviewed before rebaselining

Diff of IAM resources, pre-change synthesis vs post-change:

```
REMOVED:  DeployFnServiceRoleA27EDF94
          DeployFnServiceRoleDefaultPolicy7D43372B
ADDED:    DeployFnRole746E2D12
          DeployFnRoleDefaultPolicyE7A28FAE
MODIFIED: (none)
changed (non-IAM): DeployFn0FE820C6   -- Role, DependsOn, Code.S3Key
```

Old role `ManagedPolicyArns` held `AWSLambdaBasicExecutionRole`; the new role has
none. ProxyFn's policy is unchanged. The serving IAM fingerprint was rebaselined
only after this comparison.

Coverage rose 92.54% → 92.58%; the floor was ratcheted to **92.57**, not 92.58.
`fail_under` is compared against the *unrounded* total, so a printed 92.58 on a
true 92.5799 fails a floor of 92.58. The `[tool.coverage.report]` comment
claiming the comparison is rounded to `precision` digits was wrong and was
corrected in the same commit.

## Gate

```
make lint       clean
make typecheck  clean
make test       233 passed, coverage 92.58%
make docs-sync  clean
make wiki-lint  clean
make synth-all  dev and prod both clean
CI (PR #41)     validate pass, secret-scan pass
```

## Deployment, 2026-08-05T23:58Z

Deployed with the deployer identity, scoped to the serving stack. 70 s.
Resource-level verification with the auditor identity
(`make verify-deploy SINCE=2026-08-05`):

```
Mlops-Dev-Serving  [UPDATE_COMPLETE]  last updated 2026-08-05T23:58:07Z
    UPDATE_COMPLETE   DeployFn0FE820C6
    CREATE_COMPLETE   DeployFnRole746E2D12
    CREATE_COMPLETE   DeployFnRoleDefaultPolicyE7A28FAE
    DELETE_COMPLETE   DeployFnServiceRoleA27EDF94
    DELETE_COMPLETE   DeployFnServiceRoleDefaultPolicy7D43372B
    UPDATE_COMPLETE   ProxyFn0105D3E4
```

Six resources. Five are 5C. The sixth, `ProxyFn`, is a Lambda **code** update
with no source change — see the asset-hash finding below.

## Component check: a full end-to-end run, 2026-08-06

The check was deliberately not a warm `/predict`, which exercises the proxy
rather than this role. New data was pushed through the entire platform so the
registry approval would drive `DeployFn` down its real path.

**New data.** 1,200 rows sampled from `telco.csv` with every `customerID`
reassigned to an `NB20260805-*` identity, so the batch is new customers rather
than a re-upload. Churn rate 26.0%. Uploaded to `s3://${RAW_BUCKET}/`.

**Ingestion.** Validated and landed at
`s3://${CURATED_BUCKET}/telco/telco-batch-2026-08-05.csv` within ~10 s.
`quarantine/` stayed empty — all 1,200 rows passed `CustomerRecord`.

**Pipeline** `churn-training-pipeline-dev` execution `<pipeline-execution-id>`, started by
hand with the admin identity. All five steps `Succeeded`:

```
Preprocess  Train  Evaluate  BeatsChampion  RegisterChallenger-RegisterModel
```

The training container read the combined corpus, which is the proof the new rows
reached training:

```
[INFO] Train matrix has 5770 rows and 19 columns
[INFO] Validation matrix has 1236 rows
```

7,043 original + 1,200 new = 8,243. Validation AUC peaked ~0.8486 at round 13.
New artifacts under
`s3://${ARTIFACTS_BUCKET}/training/pipelines-<pipeline-execution-id>-Train-<suffix>/`,
including `output/model.tar.gz` (13,258 B).

**Registry.** Model package version 2 registered and auto-approved
(`model_approval_status: Approved` in dev config).

**The 5C check itself.** The approval fired EventBridge → `DeployFn` under the
new role. Its log group recorded a clean run, no `AccessDenied`:

```
{"event": "approved_challenger_deployed", "action": "updated",
 "endpoint": "churn-serverless-dev",
 "model_package_arn": "arn:aws:sagemaker:<region>:${AWS_ACCOUNT_ID}:model-package/churn-model-group/2",
 "test_auc": "0.853481835315526"}
Duration: 1968.70 ms   Init Duration: 601.53 ms   Max Memory Used: 99 MB
```

All six SageMaker calls plus `iam:PassRole` executed against resource-scoped
ARNs. `action: "updated"` proves `DescribeEndpoint` and `UpdateEndpoint`; the
populated `test_auc` proves `DescribeModelPackage` against the group-scoped ARN.

**Endpoint.** Reached `InService` on config `churn-serverless-dev-config-<epoch>`
at 2026-08-06T00:18Z.

**API.**

```
sample.json           -> 200  {"churn_probability": 0.3483, "churn": false}   1.69 s (cold)
sample-high-risk.json -> 200  {"churn_probability": 0.8434, "churn": true}    0.20 s (warm)
no x-api-key          -> 403  {"message":"Forbidden"}
make smoke            -> 6 passed
```

## The scoping question that was open before deploying, now answered

The plan recorded one guess that static analysis could not settle: `create_model`
passes `Containers[].ModelPackageName`, and the policy grants
`sagemaker:CreateModel` only on the `model/*` resource, not on the model package.
If SageMaker also authorized against the referenced package, the deploy path
would have failed at `create_model`.

**It does not.** `CreateModel` succeeded against a package it was not granted
`CreateModel` on. The omission was correct and no widening is needed.

The opposite hedge remains untested: `CreateEndpoint`/`UpdateEndpoint` name both
the endpoint and the endpoint-config, chosen as the safe direction. Whether the
endpoint-config resource is actually required by those two actions is not
determined by this run — if it is not, that entry is an inert over-grant.

## Finding: the bundled Lambda asset hash is not reproducible

Discovered while reviewing the named diff, which showed a Lambda **code** change
for `DeployFn` and `ProxyFn` despite no `src/` edit.

Not caused by 5C: the pre-change tree, re-synthesized, produces the same new
hash. Three hashes were in play — the deployed asset, the hash at the start of
the session, and the hash after. Comparing the two local bundle directories:

- identical file lists, identical `dist-info` versions (pydantic 2.13.4,
  pydantic_core 2.46.4), `diff -r` reports `src/` identical;
- the **only** differing files are vendored `__pycache__/*.pyc`.

A `.pyc` header embeds the source file's mtime, and `pip install -t`
byte-compiles with fresh mtimes on each real install. So any genuine rebundle
(cold `cdk.out`, CI, another machine) changes the Lambda code hash with no source
change, and every deploy from a fresh checkout republishes all four functions.

`infra/stacks/lambda_code.py` already documents and fixes exactly this failure
mode — but only on the **source** side, via the `_ASSET_CONTENT` allowlist
excluding `src/**/__pycache__`. The bundled **output** side, where pip compiles
the dependency tree, was never covered. Likely fix: `--no-compile` in
`_PIP_TARGET_FLAGS`, which both bundling paths share.

This matters beyond tidiness: it makes `make verify-deploy` report Lambda code
changes that are not code changes, against a repository rule that deploy
reporting be resource-level and evidence-backed. Deliberately not fixed in 5C —
it alters the deployed bundle for all four functions and needs its own change
set.

## Finding: orphaned log groups, and four duplicated per Lambda

An inventory of all 20 dev log groups by last event time found only six live:

```
00:00  Mlops-Dev-Ingestion-ValidateFnLogs<suffix>
00:10  /aws/sagemaker/TrainingJobs
00:13  /aws/sagemaker/ProcessingJobs
00:15  Mlops-Dev-Serving-DeployFnLogs<suffix>
00:18  /aws/sagemaker/Endpoints/churn-serverless-dev
00:19  Mlops-Dev-Serving-ProxyFnLogs<suffix>
       /aws/cloudtrail/mlops-dev-audit  (continuous, 65 MB)
```

Every platform Lambda appears **twice**: the CloudFormation-managed `*Logs*`
group Phase K introduced, and the runtime-created `/aws/lambda/<function>` group
it superseded. `LoggingConfig` on all four live functions points at the `*Logs*`
group, so the `/aws/lambda/` copies are frozen. Their last events date Phase K's
effect to **2026-08-01/02**, matching the three `LogRetention*` provider groups
falling silent at 03:53–03:56 on 08-02.

Seven confirmed orphans (three `LogRetention*` providers with no surviving
Lambda, four superseded `/aws/lambda/<function>` groups). Six hold 0 bytes; the
legacy ProxyFn group holds 5,642 B. None is CloudFormation-managed, so deleting
them causes no drift. An eighth candidate,
`/aws/lambda/Mlops-Dev-Data-AWS679…-8p77WxUA2GRx`, has no corresponding Lambda
and holds 11.4 KB from Phase 2 budget work — a replaced custom-resource provider,
noted but not confirmed.

Deletion was **not performed**: the session's permission layer declined the
destructive call and the commands were handed to the operator instead.

Three `/aws/lambda/` groups that look similar are **not** orphans — the
`BucketNotificationsHandler`, `SecurityMonitor` and `Data` custom-resource
provider Lambdas still exist and still log to them.

## Finding: the drift → retrain edge has never fired

Both `RetrainTriggerFn` log groups, the CloudFormation-managed one and the
legacy one, report **no events ever**. The closing edge of the drift loop has
not executed in this account. This run does not exercise it either: the pipeline
was started by hand, not by `retrain_handler`.

## Read-noise note

While watching the run, the CloudTrail audit group showed `Decrypt` calls whose
encryption context pairs `aws:logs:arn` = the audit log group with
`aws:s3:arn` = `facet-store-prod-iad` / `facet-extraction-results-prod-iad`.
These are AWS-owned internal CloudWatch Logs storage buckets in us-east-1
(`iad`), not a foreign destination: `userIdentity.type` is `AWSService`,
`invokedBy` is `logs.amazonaws.com`, the call is `readOnly`, the key is the
account's own audit CMK, and the encryption context binds the grant to that one
log group. Expected behaviour for a CMK-encrypted log group.

## State at the end of this record

- 5C code is committed on `feat/phase-5c-deploy-role`, PR #41, CI green.
- 5C is **deployed in dev and its component check has passed**. No observation
  window has been opened.
- The billable pipeline run 5D requires has now happened and succeeded.
- Prod is untouched; `least_privilege_logs` remains opt-in, so `ValidateFn` and
  `RetrainTriggerFn` still carry the managed log policy.
