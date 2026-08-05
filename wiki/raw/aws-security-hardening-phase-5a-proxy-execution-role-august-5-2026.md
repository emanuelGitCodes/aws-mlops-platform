# AWS security hardening Phase 5A — proxy execution role, August 5, 2026

Raw evidence for the first of the four roles Phase 5 converts one at a time.
All timestamps UTC. Account identifiers are `${AWS_ACCOUNT_ID}` placeholders.

## Pre-flight inventory, 2026-08-05

46 cdk-nag acknowledgements in dev, of which **25 name Phase 5**:

```
 15  CDK-generated S3 grant wildcards (Action::)
       ingestion/ValidateFn/ServiceRole/DefaultPolicy
       serving/ModelExecutionRole/DefaultPolicy
       training/PipelineExecutionRole/DefaultPolicy
  7  AWSLambdaBasicExecutionRole (managed log policy)
       data/AWS679f53fac002430cb0da5b7982bd2287/ServiceRole        <- CDK provider
       data/BucketNotificationsHandler050a...834/Role               <- CDK provider
       security_monitoring/AWS679f53fac002430cb0da5b7982bd2287/...  <- CDK provider
       ingestion/ValidateFn/ServiceRole
       monitoring/RetrainTriggerFn/ServiceRole
       serving/DeployFn/ServiceRole
       serving/ProxyFn/ServiceRole
  5  Imported-bucket object wildcards (Resource::)
  2  AmazonSageMakerFullAccess (training and serving roles)
  1  Resource::* on serving/DeployFn/ServiceRole/DefaultPolicy
```

Three of the seven managed-log-policy entries sit on **CDK-generated provider
Lambdas** whose roles this repository does not create. Their recorded reason
says "replace managed log policy during Phase 5 IAM work", which Phase 5 cannot
do. Recorded here; not corrected in this change set.

The proxy role's only IAM debt was the managed policy. Its business permission
was already exact: `sagemaker:InvokeEndpoint` on a single endpoint ARN.

## Change

`platform_lambda` gained an opt-in `least_privilege_logs` flag. When set it
builds an explicit `iam.Role` with no managed policies and grants write on the
log group the same call creates, then passes it as `role=` so CDK does not
attach `AWSLambdaBasicExecutionRole`. Only `ProxyFn` sets it.

Synthesized policy for `ProxyFnRole/DefaultPolicy`:

```
logs:CreateLogStream, logs:PutLogEvents -> Fn::GetAtt ProxyFnLogs.Arn
sagemaker:InvokeEndpoint                -> arn:aws:sagemaker:<region>:<account>:endpoint/churn-serverless-dev
```

No `logs:CreateLogGroup`: Phase K made the log group an owned resource, so the
function never creates one.

The gate fired during the change. Removing the CDK-generated role left the
`ProxyFn/ServiceRole` acknowledgement matching zero constructs, and
`_construct_at` failed synthesis:

```
ValueError: security acknowledgement path 'Mlops-Dev-Serving/ProxyFn/ServiceRole'
matched 0 constructs
```

Acknowledgements 46 -> 45.

## Template diff against the pre-change synthesis

```
REMOVED: ProxyFnServiceRoleD85A4747, ProxyFnServiceRoleDefaultPolicyA893A255
ADDED  : ProxyFnRole8FBA0101, ProxyFnRoleDefaultPolicyB82222DF
CHANGED: (none)
```

A one-for-one replacement. The serving IAM fingerprint was rebaselined only
after this comparison.

## Deployment, 2026-08-05T01:29Z

```
UPDATE_COMPLETE  AWS::Lambda::Function  DeployFn
CREATE_COMPLETE  AWS::IAM::Role         ProxyFnRole
CREATE_COMPLETE  AWS::IAM::Policy       ProxyFnRole/DefaultPolicy
UPDATE_COMPLETE  AWS::Lambda::Function  ProxyFn
DELETE_COMPLETE  AWS::IAM::Policy       ProxyFnServiceRoleDefaultPolicy
DELETE_COMPLETE  AWS::IAM::Role         ProxyFnServiceRole
UPDATE_COMPLETE  AWS::CloudFormation::Stack  Mlops-Dev-Serving
```

Both Lambda functions show a code update. That is the one-time asset-hash
change from the `__pycache__` fingerprint fix, not a source change.

## Component check

- `make smoke`: 6 passed against the live endpoint.
- `filter-log-events` on the proxy's log group after the smoke run returns the
  `inference_response` event and fresh `START RequestId` lines. This is the
  check that matters: the new policy is what authorizes `PutLogEvents`, and a
  wrong scope would have failed logging silently while `/predict` kept
  returning 200.
- `iam list-attached-role-policies` on the live role returns **no rows**.
- `make verify-deploy SINCE=2026-08-05` reports exactly the six resources above.
- Six `mlops-dev-security-*` alarms `OK`; none fired for this deployment.

## Note on the acknowledgement count

The prediction before implementing was that `AwsSolutions-IAM4` would simply
trade for `AwsSolutions-IAM5`, because a log-stream ARN requires a `:*` suffix.
That did not happen, and the reason is worth stating precisely rather than
claiming a wildcard was eliminated. `grant_write` emits the log group ARN as an
`Fn::GetAtt`, and cdk-nag does not treat an intrinsic as a literal wildcard.
**The CloudFormation `Arn` attribute of a log group resolves with a `:*` stream
suffix at deploy time**, which is exactly why `PutLogEvents` is authorized. The
wildcard is real; the linter cannot see it. The gain is one log group instead of
every log group in the account, not the removal of a wildcard.

## Repository gates

lint, mypy (36 files), 230 unit tests at 92.52% coverage, `synth-all` for dev
and prod through cdk-nag.
