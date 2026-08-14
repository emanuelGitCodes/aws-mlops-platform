---
type: "source"
title: "AWS security hardening Phase 5D pipeline execution role — August 6, 2026"
created: "2026-08-06"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-5d-pipeline-execution-role-august-6-2026.md", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/shared.py", "../../../infra/security_checks.py", "../../../src/pipeline/pipeline.py", "../../../tests/unit/test_training_stack.py", "../../../tests/unit/test_security_checks.py"]
summary: "The last role off AmazonSageMakerFullAccess, and the phase that showed CloudTrail enumerates a role's API surface but not its authorization surface."
---
# AWS security hardening Phase 5D pipeline execution role — August 6, 2026

## Confirmed

- **No role in the repository attaches `AmazonSageMakerFullAccess`.**
  `PipelineExecutionRole` was the last holder. It also carried CDK's
  `grant_read` and `grant_read_write`, whose ten generated actions covered two
  whole buckets and included the `s3:DeleteObject*` no pipeline step performs.
- **Nine statements replace both.** `telco/` on curated; four artifacts
  prefixes (`{pipeline_name}/`, `training/`, `evaluations/`, `monitor/`);
  `pipelines-*` processing and training jobs; this environment's own model
  package group; the two SageMaker job log groups; and `iam:PassRole` on itself
  conditioned to `sagemaker.amazonaws.com`. No statement carries
  `Resource: "*"`.
- **Scoping the curated read to `telco/` is a narrowing, not tidier IAM.**
  `InputDataUri` is a pipeline *parameter*, so a crafted
  `StartPipelineExecution` could otherwise point the pipeline at any prefix of
  the curated bucket and train the model on data of the caller's choosing.
  `retrain_handler` starts the pipeline with default parameters only.
- **The role was updated in place.** The deployed SageMaker Pipeline definition
  is upserted out of band with `--role-arn` and `scripts/setup_monitor.py`
  takes the same ARN, so a replacement would strand both. The template diff
  confirms it: two resources changed, none added, removed, or renamed.
- **The component check was a real workload run, and it took three attempts.**
  Execution `<pipeline-execution-id>` reached `Succeeded` on all five steps at
  2026-08-06T02:18Z, registered model package version 3, and the endpoint
  reached `InService` at 02:21Z with `make smoke` passing 6 tests.

## Synthesis

### CloudTrail enumerates the API surface, not the authorization surface

This is the phase's transferable finding. Two runs failed on
`sagemaker:AddTags` — first the processing job, then the model package group —
and the action appears **nowhere** in CloudTrail for this role. The absence is
genuine: Pipelines tags each resource it creates *as part of the create call*,
so the authorization check happens inside `CreateProcessingJob` and never
becomes an event of its own.

A least-privilege policy built from trail evidence alone meets this class of
failure. It is the concrete argument for the operating rule's
insistence that each phase's component check be a real workload run rather than
a smoke test: static analysis had the API surface right and the authorization
surface wrong, and only a live `CreateProcessingJob` could tell the difference.

### Success-by-error is a permission you still need

The same baseline produced two correct catches of a related kind.
`logs:CreateLogGroup` and `sagemaker:CreateModelPackageGroup` are both called
unconditionally on every run and both come back with a *service* error today —
`ResourceAlreadyExistsException` and `ValidationException`. Reading those as
"the caller does not need this" inverts the truth: they are success paths only
while the permission exists, and removing it turns the same call into
`AccessDenied`.

### The KMS argument, now proven rather than assumed

5B and 5C both reasoned that the AWS-managed key's own policy authorizes the
call, so no IAM grant is needed. 5D can prove it. The role makes 39
`GenerateDataKey`/`Decrypt` calls per run and succeeds while holding **no** KMS
permission at all: `AmazonSageMakerFullAccess` grants only `DescribeKey` and
`ListAliases`, and the buckets are `KMS_MANAGED`, so `bucket.encryptionKey` is
undefined and CDK emits no key grant. The `aws/s3` key policy is the only thing
that can be authorizing it.

### Also deliberately not granted

ECR — the XGBoost and SKLearn images are first-party, pulled by SageMaker with
its own credentials, as 5B proved live. `cloudwatch:PutMetricData` — takes no
resource ARN, so granting it would restore the wildcard. `s3:DeleteObject*` —
no step deletes, and its removal is most of the phase's point. The lineage
calls (`AddAssociation`, `CreateArtifact`, `CreateTrialComponent`,
`CreateExperiment`, `CreateTrial`) — CloudTrail attributes every one to
`sagemaker.amazonaws.com` itself.

### Phase 5C closed on this run

5C was deployed and component-checked but its observation window was never
opened. It closed here on better evidence than an idle window would have given:
5D's successful run registered a model package, auto-approval fired, and the
endpoint went to `Updating` six seconds later — the full registry-approval →
`DeployFn` → `UpdateEndpoint` path, unattended.

## Tensions or open questions

- **`monitor/*` was granted without evidence.** `scripts/setup_monitor.py` runs
  Model Monitor under this same pipeline role, and the drift loop has never run
  in this account, so no CloudTrail record exists or could. The prefix is
  pinned to the script in `tests/unit/test_pipeline.py` so the two cannot drift
  apart silently. The cleaner fix — Model Monitor gets its own execution role —
  is out of scope for a one-role phase and is open work.
- **`AWSLambdaBasicExecutionRole` is not finished.** Phase 5 completing means
  no role attaches `AmazonSageMakerFullAccess`; `ValidateFn`,
  `RetrainTriggerFn`, and the CDK provider Lambdas still carry the managed log
  policy, each with its own acknowledgement.
- Acknowledgements rose 41 → 43. Eight coarse training entries — one of them
  the managed policy itself, two covering whole buckets — traded for ten each
  naming a single prefix, job pattern, or log group. A rising count is the
  expected shape when a broad grant is decomposed.
- Ten stale `sagemaker-scikit-learn-*` prefixes survive on the artifacts
  bucket, last written 2026-07-11 by a superseded code path. They are now
  unreachable by any role: a cleanup, not a risk.
