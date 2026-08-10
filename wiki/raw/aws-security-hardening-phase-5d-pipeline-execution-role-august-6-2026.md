# AWS security hardening Phase 5D — pipeline execution role, August 6, 2026

Raw evidence for the last of the four roles Phase 5 converts one at a time.
All timestamps UTC. Account identifiers are `${AWS_ACCOUNT_ID}` placeholders and
generated resource suffixes are written `<suffix>`.

## Pre-flight inventory, 2026-08-06

Repository green state before any edit:

```
make lint       clean
make typecheck  clean (36 source files)
make test       233 passed, coverage 92.58% (floor 92.57)
make synth-all  dev and prod both clean
```

41 cdk-nag acknowledgements in dev. Eight were bound to the pipeline role:

```
training  PipelineExecutionRole                AwsSolutions-IAM4[...AmazonSageMakerFullAccess]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Action::s3:GetObject*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Action::s3:GetBucket*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Action::s3:List*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Action::s3:DeleteObject*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Action::s3:Abort*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Resource::<curated bucket>/*]
training  PipelineExecutionRole/DefaultPolicy  IAM5[Resource::<artifacts bucket>/*]
```

Live policy attachment before the change — one managed policy, one inline:

```
attached  AmazonSageMakerFullAccess
inline    PipelineExecutionRoleDefaultPolicy<suffix>
```

Role ARN, which must survive the change unchanged:

```
${PIPELINE_ROLE_ARN}
```

## Empirical scope of the role

### S3 — read from the live buckets, security-auditor identity

The artifacts bucket's top-level prefixes:

```
churn-training-pipeline-dev/   code bundles + per-execution step outputs
training/                      training-job output and debug-output
evaluations/                   the evaluate step's explicit destination
sagemaker-scikit-learn-*/      ten prefixes, all last written 2026-07-11
```

The `sagemaker-scikit-learn-*` prefixes are residue from a superseded code
path — the SDK now puts framework bundles under
`{pipeline_name}/code/<hash>/`. Nothing current writes there, so they were not
granted.

The curated bucket holds exactly one prefix, `telco/`.

`monitor/` does not exist: `scripts/setup_monitor.py` has never been run in
this account, consistent with the 5C finding that the drift → retrain edge has
never fired. It was granted anyway — see "Deliberate departures" below.

### CloudTrail — the 5C pipeline run, 2026-08-05T23:50Z → 2026-08-06T02:00Z

Every management event attributed to the pipeline role's session:

```
29  kms:GenerateDataKey
10  kms:Decrypt
 3  logs:CreateLogStream          /aws/sagemaker/{Processing,Training}Jobs
 3  logs:CreateLogGroup           ResourceAlreadyExistsException
 2  sagemaker:CreateProcessingJob
 2  sagemaker:DescribeProcessingJob
 2  sagemaker:DescribeTrainingJob
 1  sagemaker:CreateTrainingJob
 1  sagemaker:CreateModelPackage
 1  sagemaker:DescribeModelPackage
 1  sagemaker:CreateModelPackageGroup   ValidationException
```

Job names confirm the ARN pattern:
`pipelines-<pipeline-execution-id>-{Preprocess,Train,Evaluate}-<suffix>`.

Two of those are **success-by-error paths**, which is the finding that changed
the policy. `CreateLogGroup` and `CreateModelPackageGroup` are both called
unconditionally and both come back with a service error rather than a denial —
`ResourceAlreadyExistsException` and `ValidationException`. Remove the
permission and the same call returns `AccessDenied`, which is not a path either
caller tolerates. Both were granted.

The lineage calls in the same window (`AddAssociation` ×29, `CreateArtifact`
×9, `CreateAction` ×4, `CreateTrialComponent` ×3, `CreateExperiment`,
`CreateTrial`) all carry `invokedBy: sagemaker.amazonaws.com`. They are the
service's own, not the role's, and were not granted.

### The KMS question, settled positively

The role calls `GenerateDataKey` and `Decrypt` 39 times per run and succeeds
**while holding no KMS permission at all**. `AmazonSageMakerFullAccess` grants
only `kms:DescribeKey` and `kms:ListAliases`, the CDK bucket grants add none
(the buckets are `KMS_MANAGED`, so `bucket.encryptionKey` is undefined and CDK
emits no key grant), and the role has no other policy. The AWS-managed `aws/s3`
key policy is therefore what authorizes the call, and an IAM grant would add
nothing. This is the same argument 5B and 5C made for `aws/lambda`, but proven
rather than assumed.

## The change

`least_privilege=True` on the existing `sagemaker_execution_role` helper — the
one 5B added — plus nine inline statements replacing `grant_read` and
`grant_read_write`:

| Statement | Actions | Resource |
|---|---|---|
| 1 | `s3:GetObject` | curated `telco/*` |
| 2 | `s3:GetObject`, `PutObject`, `AbortMultipartUpload` | artifacts `{pipeline_name}/*`, `training/*`, `evaluations/*`, `monitor/*` |
| 3 | `s3:ListBucket` | both bucket ARNs |
| 4 | `sagemaker:CreateProcessingJob`, `DescribeProcessingJob`, `AddTags` | `processing-job/pipelines-*` |
| 5 | `sagemaker:CreateTrainingJob`, `DescribeTrainingJob`, `AddTags` | `training-job/pipelines-*` |
| 6 | `sagemaker:CreateModelPackage`, `DescribeModelPackage`, `AddTags` | `model-package/churn-model-group/*` |
| 7 | `sagemaker:CreateModelPackageGroup`, `AddTags` | `model-package-group/churn-model-group` |
| 8 | `iam:PassRole` | its own ARN, `iam:PassedToService = sagemaker.amazonaws.com` |
| 9 | `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents`, `DescribeLogStreams` | `/aws/sagemaker/{Processing,Training}Jobs` and `:*` |

No statement carries `Resource: "*"`. Phase 3E's account-level Block Public
Access remains the only literal wildcard the repository writes.

### The narrowing that matters

`InputDataUri` is a pipeline *parameter*. Scoping statement 1 to `telco/` is
not tidier IAM: without it, a crafted `StartPipelineExecution` could point the
pipeline at any prefix of the curated bucket and train on data of the caller's
choosing. `retrain_handler` starts the pipeline with default parameters only,
so nothing legitimate reads outside `telco/`. This is the same shape of fix 5C
applied to the deploy Lambda's model package ARN, where the ARN likewise
arrived from outside.

### In place, not replaced

The construct id and both logical ids are unchanged on purpose. The deployed
SageMaker Pipeline definition is upserted out of band with `--role-arn`, and
`scripts/setup_monitor.py` takes the same ARN, so a replacement would strand
both. The helper docstring was widened from 5B's model-role-specific wording to
cover both roles it builds.

Template diff against the pre-change synthesis:

```
added:    none
removed:  none
renamed:  none
changed:  PipelineExecutionRoleF9B1F2D0                (loses ManagedPolicyArns, nothing else)
          PipelineExecutionRoleDefaultPolicy<suffix>   (PolicyDocument)
```

## Deliberate departures from evidence-only scoping

Two grants are not backed by CloudTrail, and both are recorded here rather than
buried:

- **`monitor/*`** was granted on the documented operational path in
  `scripts/setup_monitor.py`, which runs Model Monitor under this same role.
  The drift loop has never run in this account, so there is no trail evidence
  and could not be. `tests/unit/test_pipeline.py` now pins the prefix to the
  script so the two cannot drift apart silently. The cleaner fix — Model
  Monitor gets a role of its own — is out of scope for a one-role phase and is
  recorded as follow-up work.
- **`sagemaker:AddTags`** was added *after* the first run failed on it. See
  below.

## Deployment and component check

```
2026-08-06T01:49:23Z  deploy 1   two resources UPDATE_COMPLETE, none replaced
2026-08-06T01:50:01Z  stack UPDATE_COMPLETE
```

`make verify-deploy SINCE=2026-08-06`, security-auditor identity, resource
level:

```
Mlops-Dev-Training  [UPDATE_COMPLETE]  last updated 2026-08-06T01:49:23Z
    UPDATE_COMPLETE  PipelineExecutionRoleDefaultPolicy<suffix>
    UPDATE_COMPLETE  PipelineExecutionRoleF9B1F2D0
```

No other stack reports a change.

### First run: the finding

Execution `<pipeline-execution-id>`, started 2026-08-06T01:50Z, **Failed** at Preprocess:

```
ClientError: Failed to invoke sagemaker:CreateProcessingJob.
User: .../PipelineExecutionRoleF9B1F2D0-<suffix>/sagemaker-pipeline-<pipeline-execution-id>-Preprocess
is not authorized to perform: sagemaker:AddTags
on resource: .../processing-job/pipelines-<pipeline-execution-id>-Preprocess-<suffix>
because no identity-based policy allows the sagemaker:AddTags action
```

`AddTags` was omitted precisely because it appeared nowhere in the trail. The
absence was real and the inference from it was wrong: **Pipelines tags each
resource it creates as part of the create call**, so the authorization check
happens inside `CreateProcessingJob` and never surfaces as its own event. No
amount of CloudTrail reading would have found it.

This is the strongest argument the phase produced for the operating rule's
insistence on a live component check. Static analysis had the API surface
right; it had the *authorization* surface wrong, and only a real
`CreateProcessingJob` could tell the difference.

Granted first on the three job and package creates.

```
2026-08-06T01:54:09Z  deploy 2   one resource UPDATE_COMPLETE (the policy only)
```

### Second run: the same finding, one statement short

Execution `<pipeline-execution-id>`, 2026-08-06T01:54Z → 02:10Z. Four of five steps
**Succeeded** — Preprocess, Train, Evaluate, BeatsChampion — and
`RegisterChallenger` failed:

```
ClientError: Failed to invoke sagemaker:CreateModelPackageGroup.
User: .../sagemaker-pipeline-<pipeline-execution-id>-RegisterChallenger-R
is not authorized to perform: sagemaker:AddTags
on resource: .../model-package-group/churn-model-group
```

Same mechanism, a different ARN: the group, not the package. `AddTags` belongs
on **all four** create statements, each scoped to the ARN of the thing being
created. It took two runs to enumerate them because each failure stops at the
first step that needs one, and nothing in CloudTrail lists them ahead of time.

```
2026-08-06T02:12:40Z  deploy 3   one resource UPDATE_COMPLETE (the policy only)
```

### Third run: clean

Execution `<pipeline-execution-id>`, 2026-08-06T02:12Z → 02:18Z, **Succeeded**:

```
Preprocess                      Succeeded   cache hit from <pipeline-execution-id>
Train                           Succeeded   cache hit from <pipeline-execution-id>
Evaluate                        Succeeded
BeatsChampion                   Succeeded
RegisterChallenger-RegisterModel Succeeded
```

Preprocess and Train were 30-day cache hits, so this execution did not itself
re-run them. It does not need to: **both ran live under the least-privilege
policy in `<pipeline-execution-id>`**, whose policy differs from this one only by the
model-package-group `AddTags` — an ARN neither step touches. The union of the
two runs exercises every statement.

The registry path then fired on its own:

```
02:18:16Z  model package version 3 registered, ModelApprovalStatus Approved
02:18:22Z  endpoint churn-serverless-dev -> Updating, config churn-serverless-dev-config-<epoch>
```

Six seconds from auto-approval to `UpdateEndpoint`. That is the
registry-approval → `DeployFn` → endpoint path, which is the evidence Phase 5C's
unopened observation window was short. **5C closes on this run.**

### Denial sweep

CloudTrail for the pipeline role from 2026-08-06T01:49Z, read with the
security-auditor identity:

```
55  kms:GenerateDataKey
14  kms:Decrypt
 4  logs:CreateLogStream
 4  logs:CreateLogGroup   ResourceAlreadyExistsException
```

No `AccessDenied`. Read with the caveat that CloudTrail delivery lags roughly
fifteen minutes, so the sweep trails the run — the load-bearing evidence is the
execution reaching `Succeeded` with every step green, not the absence in this
window.

## Alarms and cost

```
mlops-dev-security-iam-policy-changes         ALARM   true positive on this phase's own deploys
mlops-dev-security-unauthorized-api-calls     OK
mlops-dev-security-cloudtrail-configuration-changes  OK
mlops-dev-security-kms-key-disable-or-deletion       OK
mlops-dev-security-root-user-activity                OK
mlops-dev-security-s3-bucket-policy-changes          OK
mlops-dev-endpoint-5xx                        INSUFFICIENT_DATA
```

`iam-policy-changes` is `1 of 1` and fires on any gated deploy that touches a
role — the standing expectation recorded after 5C. `endpoint-5xx` sitting in
`INSUFFICIENT_DATA` is the unfixed gap from the 5B/5C window closure, not a new
finding: it leaves `TreatMissingData` unset, so it cannot distinguish a healthy
idle serverless endpoint from one that stopped reporting.

Notably, the first run's `AddTags` denial did **not** page
`unauthorized-api-calls`. That is the Phase 2E three-datapoint rule behaving as
designed: a single denial in one five-minute period cannot assemble three
consecutive breaching datapoints.

## Follow-up work this phase did not do

Recorded, deliberately out of scope for a one-role change set:

- Model Monitor should have its own execution role rather than reusing the
  pipeline role; `scripts/setup_monitor.py`'s documented invocation would
  change with it.
- The ten stale `sagemaker-scikit-learn-*` prefixes on the artifacts bucket are
  orphaned output from a superseded code path and are now unreachable by any
  role. They are a cleanup, not a risk.
- Carried forward from 5C and unchanged: the non-reproducible bundled Lambda
  asset hash, seven orphaned dev log groups, the never-fired drift → retrain
  edge, `endpoint-5xx`'s unset `TreatMissingData`, and the 3-of-3
  late-datapoint `Fill` fix.
