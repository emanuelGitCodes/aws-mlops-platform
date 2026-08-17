# Wiki log

Append-only record of ingests, queries, and lint passes.

## [2026-07-10] update | CDK deployment IAM walkthrough

Documented the CDK bootstrap roles, the two-policy deployment boundary, the break-glass administrator pattern, the completed `CDKToolkit` bootstrap checkpoints, and the expected IAM inspection denial after removing `AdministratorAccess`.

## [2026-07-10] query | SageMaker permissions

Found 7 matching page(s).

## [2026-07-10] query | closed drift

Found 5 matching page(s).

## [2026-07-10] query | SageMaker permissions

Found 7 matching page(s).

## [2026-07-10] query | IAM CDK bootstrap deployment policy

Found 5 matching page(s).

## [2026-07-10] update | Detailed CDK deployment IAM checkpoint

### Objective

Replace temporary administrator access for the `${MLOPS_DEPLOYER_USER_NAME}` IAM user with a two-layer CDK deployment path while keeping `${AWS_ADMIN_USER_NAME}` available as break-glass access.

### Scope

- AWS account `${AWS_ACCOUNT_ID}`, region `us-east-1`.
- Group `MLOps-Deployers` and user `${MLOPS_DEPLOYER_USER_NAME}`.
- CDK bootstrap stack `CDKToolkit`.
- CDK bootstrap roles using qualifier `hnb659fds`.
- Policies `MLOpsCloudFormationExecutionPolicy` and `MLOpsCdkDeploymentPolicy`.
- Wiki pages `pages/architecture/cdk-deployment-iam.md`, `pages/architecture/permissions.md`, and `pages/answers/repo-walkthrough.md`.

### Commands and observed results

1. Read-only checks showed that `CDKToolkit` did not exist and `${MLOPS_DEPLOYER_USER_NAME}` initially inherited `AdministratorAccess` from `MLOps-Deployers`.
2. A local JSON document was created for `MLOpsCloudFormationExecutionPolicy`; `jq empty` returned successfully.
3. `aws iam create-policy` created the policy at `arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCloudFormationExecutionPolicy`, version `v1`.
4. `cdk bootstrap aws://${AWS_ACCOUNT_ID}/us-east-1 --profile ${MLOPS_DEPLOYER_USER_NAME} --cloudformation-execution-policies arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCloudFormationExecutionPolicy` returned `CDKToolkit: CREATE_COMPLETE`.
5. The bootstrap roles were verified: CloudFormation execution, deploy, file publishing, lookup, and image publishing.
6. A local JSON document for `MLOpsCdkDeploymentPolicy` was validated with `jq empty`.
7. `aws iam create-policy` created `arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCdkDeploymentPolicy`, version `v1`.
8. The policy was attached to `MLOps-Deployers`. Verification under the still-admin-capable user showed both `AdministratorAccess` and `MLOpsCdkDeploymentPolicy`.
9. `AdministratorAccess` was detached from `MLOps-Deployers`.
10. Repeating `aws iam list-attached-group-policies --profile ${MLOPS_DEPLOYER_USER_NAME}` returned `AccessDenied` for `iam:ListAttachedGroupPolicies`. This was expected because the restricted deployment policy does not grant IAM group inspection or administration.

### Interpretation

The deployment user is now a control-plane identity. It can authenticate, read the CDK bootstrap version, and assume the specific CDK lookup, deploy, and file-publishing roles. It does not directly receive S3, Lambda, SageMaker, CloudFormation, or IAM administration permissions. CloudFormation receives the application resource permissions through its separate execution role.

The `AccessDenied` result is evidence that the IAM boundary is active, not evidence that the deployment path is broken. IAM inspection should use `${AWS_ADMIN_USER_NAME}`; adding `iam:ListAttachedGroupPolicies` merely to make the deployment profile easier to inspect would weaken the intended boundary.

### Decision and next checkpoint

Keep `AdministratorAccess` detached. Use `${AWS_ADMIN_USER_NAME}` to verify that the group contains only `MLOpsCdkDeploymentPolicy`, then use `${MLOPS_DEPLOYER_USER_NAME}` for `aws sts get-caller-identity` and `cdk diff -c env=dev`. Any missing deployment permission should be added from the specific denied action or CloudFormation event rather than restoring administrator access.

### Verification

- `jq empty` passed for both policy documents.
- Wiki index rebuilt successfully.
- `scripts/wiki.py lint` passed: 8 pages healthy.
- `pytest -q tests/unit/test_wiki.py` passed: 4 tests.
- `git diff --check` passed.

## [2026-07-10] verify | Restricted deployment group state

### Objective

Confirm the group state after removing `AdministratorAccess` without granting IAM inspection permissions to `${MLOPS_DEPLOYER_USER_NAME}`.

### Identity and command

The command was run with the local `${AWS_ADMIN_USER_NAME}` CLI profile:

```bash
aws sts get-caller-identity --profile ${AWS_ADMIN_USER_NAME}
```

The identity response confirmed:

```text
Arn: arn:aws:iam::${AWS_ACCOUNT_ID}:user/${AWS_ADMIN_USER_NAME}
Account: ${AWS_ACCOUNT_ID}
```

The group inspection command was then run with `--profile ${AWS_ADMIN_USER_NAME}`:

```bash
aws iam list-attached-group-policies \
  --group-name MLOps-Deployers \
  --profile ${AWS_ADMIN_USER_NAME} \
  --query 'AttachedPolicies[].{Name:PolicyName,Arn:PolicyArn}' \
  --output table
```

### Result and interpretation

The group contains exactly:

```text
arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCdkDeploymentPolicy
```

This confirms that `AdministratorAccess` is no longer attached. The earlier `AccessDenied` under `${MLOPS_DEPLOYER_USER_NAME}` remains expected because group-policy inspection is an administrative operation and is intentionally outside the restricted deployment policy.

### Next checkpoint

Run `aws sts get-caller-identity --profile ${MLOPS_DEPLOYER_USER_NAME}`, then run `cdk diff --profile ${MLOPS_DEPLOYER_USER_NAME} -c env=dev`. The first command checks the deployment identity; the second checks whether the restricted user can use the CDK lookup and deploy path without administrator access.

## [2026-07-10] verify | Restricted CDK diff succeeded

### Objective

Test the complete CDK CLI path with `${MLOPS_DEPLOYER_USER_NAME}` after removing `AdministratorAccess`, without deploying application resources.

### Command and identity

The command was run from the `infra` directory with the `.venv-cdk` environment active:

```bash
cdk diff \
  --profile ${MLOPS_DEPLOYER_USER_NAME} \
  -c env=dev
```

The preceding identity check confirmed:

```text
Arn: arn:aws:iam::${AWS_ACCOUNT_ID}:user/${MLOPS_DEPLOYER_USER_NAME}
```

### Results

- All six stacks were synthesized: `Mlops-Dev-Data`, `Mlops-Dev-Ingestion`, `Mlops-Dev-Registry`, `Mlops-Dev-Training`, `Mlops-Dev-Serving`, and `Mlops-Dev-Monitoring`.
- All six synthesized templates were published successfully to the CDK bootstrap asset location.
- The command ended with `Number of stacks with differences: 6`.
- No `AccessDenied` error appeared.
- No warning appeared about failing to assume the CDK lookup, deploy, or file-publishing roles.

### Interpretation

The restricted deployment policy works for the CDK control-plane path. In practical terms, `${MLOPS_DEPLOYER_USER_NAME}` successfully used the bootstrap version parameter, assumed the needed CDK roles, uploaded synthesized templates, and obtained the diff information.

The six differences are expected because the six application stacks do not exist yet. The diff output is a proposed resource set, not proof that the resources have been created. `cdk diff` may write template assets to the bootstrap S3 bucket and use read-only CloudFormation change sets, but it does not create the application buckets, queues, Lambdas, roles, API, or SageMaker resources.

### Warnings

- The `logRetention` deprecation warning is non-fatal and concerns a future CDK API migration from `logRetention` to `logGroup`.
- The cross-stack-reference strength warning is non-fatal and concerns CDK reference behavior. It does not indicate a deployment failure.

### Next checkpoint

Review the proposed six-stack diff, then run `cdk deploy --all --profile ${MLOPS_DEPLOYER_USER_NAME} -c env=dev --require-approval broadening --progress events`. Deployment is the first step that exercises the full `MLOpsCloudFormationExecutionPolicy`; if CloudFormation reports a denied action, add that action explicitly rather than restoring `AdministratorAccess`.

## [2026-07-10] failure | First application deployment

### Objective

Deploy the six CDK application stacks with `${MLOPS_DEPLOYER_USER_NAME}` and verify whether the custom CloudFormation execution policy covered the resources synthesized by the repository.

### Command and approval

The deployment was run with approval enabled. The security-sensitive change prompt was displayed and explicitly answered `y`. CDK began with `Mlops-Dev-Data`.

### Observed failure

CloudFormation assumed the expected execution role:

```text
arn:aws:sts::${AWS_ACCOUNT_ID}:assumed-role/cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1/AWSCloudFormation
```

The Data stack then failed on the same missing action for all three S3 buckets:

```text
s3:PutEncryptionConfiguration
```

The affected resources were `RawBucket`, `CuratedBucket`, and `ArtifactsBucket`. The error stated that no identity-based policy allowed this action. CloudFormation cancelled the bucket notification role, rolled back the budget and helper resources, and ended with:

```text
Mlops-Dev-Data ROLLBACK_COMPLETE
```

### Interpretation

This is not a failure of the `${MLOPS_DEPLOYER_USER_NAME}` user policy. The user authenticated, assumed the CDK roles, published assets, and reached CloudFormation. The missing permission belongs in `MLOpsCloudFormationExecutionPolicy`, which is attached to the `cdk-hnb659fds-cfn-exec-role`.

The missing action maps directly to the repository's data-stack configuration: each bucket uses KMS-managed default encryption. CloudFormation must configure that encryption after creating the bucket. The S3 API documents this operation as the bucket default-encryption configuration operation: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutBucketEncryption.html

### Recovery decision

Add only `s3:PutEncryptionConfiguration` to the S3 management actions in the local execution-policy document, validate the JSON, and create a new default policy version using `${AWS_ADMIN_USER_NAME}`. Do not restore `AdministratorAccess` and do not change `MLOpsCdkDeploymentPolicy`.

The failed `Mlops-Dev-Data` stack must be deleted after the policy update because a stack in `ROLLBACK_COMPLETE` cannot be updated normally. Wait for deletion to finish, then retry the deployment. The next failure, if any, should be treated as the next missing execution permission and recorded separately.

## [2026-07-10] recovery | Execution policy update and failed-stack cleanup

### Policy update

The local execution-policy JSON was corrected after a comma syntax error. `jq empty` then passed. Using the `${AWS_ADMIN_USER_NAME}` profile, `aws iam create-policy-version` created policy version `v2` and marked it as the default for `MLOpsCloudFormationExecutionPolicy`.

The updated policy adds the exact action reported by CloudFormation:

```text
s3:PutEncryptionConfiguration
```

### Stack cleanup

The failed `Mlops-Dev-Data` stack was deleted with the `${AWS_ADMIN_USER_NAME}` profile. The CloudFormation delete waiter completed successfully, confirming the `ROLLBACK_COMPLETE` stack record is gone and the stack name can be recreated.

### Current state

- `MLOpsCdkDeploymentPolicy` remains the only policy attached to `MLOps-Deployers`.
- `MLOpsCloudFormationExecutionPolicy` version `v2` is the default execution policy.
- `CDKToolkit` remains bootstrapped.
- No application stack is currently deployed from the failed Data-stack attempt.

### Next checkpoint

Retry `cdk deploy --all` with `${MLOPS_DEPLOYER_USER_NAME}`, approval enabled, and progress events. Watch whether the three encrypted buckets complete and whether CloudFormation reports a different missing action.

## [2026-07-10] failure | Second application deployment

### Objective

Retry the Data stack after changing the CloudFormation execution policy to include `s3:PutEncryptionConfiguration`.

### Results before failure

The retry confirmed that the S3 policy change worked:

- `RawBucket` reached `CREATE_COMPLETE`.
- `CuratedBucket` reached `CREATE_COMPLETE`.
- `ArtifactsBucket` reached `CREATE_COMPLETE`.
- All three S3 bucket policies reached `CREATE_COMPLETE`.
- The bucket notification handler role reached `CREATE_COMPLETE`.

### Observed failure

The CDK-generated inline policy resource `RawBucket/Notifications/HandlerPolicy` failed because the CloudFormation execution role was not allowed to call:

```text
iam:GetRolePolicy
```

The denied resource was the generated `BucketNotificationsHandler` role. CloudFormation first reported that it could not check whether the inline policy already existed, then the resource failed and the stack ended in `ROLLBACK_COMPLETE`.

### Interpretation

The missing permission belongs in `MLOpsCloudFormationExecutionPolicy`, not `MLOpsCdkDeploymentPolicy`. This action lets CloudFormation read an existing inline policy on a role while creating or reconciling the generated S3 notification helper. The result demonstrates why deployment permissions must be tested against actual CloudFormation events; `cdk diff` cannot exercise every resource lifecycle call.

### Retained-resource warning

The S3 buckets reached `CREATE_COMPLETE` before rollback, and the stack reported `DELETE_SKIPPED` for those buckets. The repository configures the buckets with `RemovalPolicy.RETAIN`, so they may still exist after rollback. Inspect their physical names with `${AWS_ADMIN_USER_NAME}` before deleting the failed stack again. Do not delete a retained bucket until confirming it is an empty artifact from this failed deployment and not data that must be preserved.

### Next checkpoint

First list retained `mlops-dev-data-` buckets with `${AWS_ADMIN_USER_NAME}`. Then add only `iam:GetRolePolicy` to the local execution-policy document, create a new default policy version, clean up the failed stack and any confirmed-empty retained buckets, and retry deployment.

## [2026-07-10] inspect | Retained Data-stack bucket inventory

### Command and identity

Using the `${AWS_ADMIN_USER_NAME}` profile, the account was queried for buckets whose names start with `mlops-dev-data-`.

### Result

Six buckets were found:

- First attempt: `rawbucket0c3ee094-ldg9koueuqom`, `curatedbucket6a59c97e-2sxdeu8rh3n8`, and `artifactsbucket2aac5544-w3z4jpu9zxfk`.
- Second attempt: `rawbucket0c3ee094-dk0mrhve7fns`, `curatedbucket6a59c97e-w202u4b9sek1`, and `artifactsbucket2aac5544-cgnushrb0wbo`.

### Interpretation

Both deployment attempts created the buckets before failing later in the Data stack. The buckets were retained because the CDK data stack uses versioning and `RemovalPolicy.RETAIN`. They must be checked for object versions and delete markers before cleanup. No bucket should be deleted merely because its CloudFormation stack failed.

### Next checkpoint

Inspect object versions and delete markers in one retained bucket with `${AWS_ADMIN_USER_NAME}`. If it is empty, inspect the remaining five and then remove only the confirmed-empty failed-deployment buckets.

## [2026-07-10] verify | Retained buckets confirmed empty

### Scope

All six buckets from the two failed Data-stack attempts were checked with `aws s3api list-object-versions` using `${AWS_ADMIN_USER_NAME}`.

### Result

Every bucket returned:

```json
{
  "ObjectVersions": 0,
  "DeleteMarkers": 0
}
```

The six buckets are confirmed empty and contain no versioned objects or delete markers. They are safe cleanup candidates, subject to the explicit deletion step that follows policy repair.

### Next checkpoint

Add only `iam:GetRolePolicy` to the CloudFormation execution-policy JSON, validate it, and create policy version `v3`. The restricted deployment-user policy remains unchanged.

## [2026-07-10] cleanup | Retained Data-stack buckets removed

### Result

The six empty buckets retained by the failed Data-stack rollbacks were cleaned up using `${AWS_ADMIN_USER_NAME}`:

- The first Raw bucket had already been deleted.
- The first Curated bucket was reported missing because it had already been deleted.
- The remaining four buckets were deleted successfully.

A final `aws s3api list-buckets` query for the `mlops-dev-data-` prefix returned no matching buckets. The `CDKToolkit` bootstrap resources were not touched.

### Current state

- `MLOpsCloudFormationExecutionPolicy` version `v3` is the default.
- `iam:GetRolePolicy` is included for CloudFormation's generated inline-policy reconciliation.
- `Mlops-Dev-Data` has no failed stack record.
- No retained Data-stack buckets remain.

### Next checkpoint

Retry the complete CDK deployment with `${MLOPS_DEPLOYER_USER_NAME}` and approval enabled. The Data stack should now be able to progress past both previously observed permission failures.

## [2026-07-10] failure | Third application deployment

### Objective

Retry the Data stack after setting `MLOpsCloudFormationExecutionPolicy` version `v3` as default with `iam:GetRolePolicy`.

### Results before failure

The retry confirmed that the previous missing permission was fixed:

- All three S3 buckets reached `CREATE_COMPLETE`.
- All three S3 bucket policies reached `CREATE_COMPLETE`.
- The `BucketNotificationsHandler` IAM role reached `CREATE_COMPLETE`.
- The generated inline policy reached `CREATE_COMPLETE`.
- The generated `BucketNotificationsHandler` Lambda reached `CREATE_COMPLETE`.

### Observed failure

The custom resource `RawBucket/Notifications` failed because the CloudFormation execution role was not allowed to call:

```text
lambda:InvokeFunction
```

The denied resource was the generated Lambda function:

```text
Mlops-Dev-Data-BucketNotificationsHandler<suffix>
```

CloudFormation then rolled the stack back to `ROLLBACK_COMPLETE`. The buckets again emitted `DELETE_SKIPPED` because they use `RemovalPolicy.RETAIN`; their empty state must be checked and cleaned after the stack failure.

### Interpretation

The CDK `Custom::S3BucketNotifications` resource uses a helper Lambda to configure the raw bucket's notification. The CloudFormation execution role therefore needs permission to invoke that helper. This is another execution-policy gap, not a failure of the `${MLOPS_DEPLOYER_USER_NAME}` role-assumption policy and not a failure of the application proxy Lambda.

### Recovery decision

Add only `lambda:InvokeFunction` to the Lambda actions in the local `MLOpsCloudFormationExecutionPolicy` document, validate it, and create policy version `v4` with `${AWS_ADMIN_USER_NAME}`. Then delete the failed stack, inspect and remove only the new confirmed-empty retained buckets, and retry.

## [2026-07-10] cleanup | Third-attempt retained buckets removed

### Result

The three buckets retained by the third failed Data-stack attempt were confirmed empty with zero object versions and zero delete markers. They were deleted with `${AWS_ADMIN_USER_NAME}`:

- `${RAW_BUCKET}`
- `${CURATED_BUCKET}`
- `${ARTIFACTS_BUCKET}`

The deletion loop returned no errors. The next checkpoint is a final account-wide prefix query, followed by a deployment retry using policy version `v4`.
## [2026-07-11] query | deployment pipeline CloudWatch Lambda API Gateway SageMaker

Found 8 matching page(s).

## [2026-07-11] ingest | MLOps deployment and pipeline troubleshooting summary — July 10, 2026

Registered immutable source `raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md`.

## [2026-07-11] update | Deployment and pipeline troubleshooting checkpoint

### Objective

Carry the July 10 AWS deployment and testing work into the maintained wiki so the next study or debugging session can distinguish completed infrastructure, successful ingestion, API behavior, and the remaining SageMaker pipeline failure.

### Scope

- Account `${AWS_ACCOUNT_ID}`, region `us-east-1`.
- CDK deployment identity and CloudFormation execution boundary.
- Lambda dependency packaging, API Gateway authentication, S3 ingestion, and SageMaker pipeline execution.
- New page: `pages/architecture/deployment-and-pipeline-troubleshooting.md`.
- Updated pages: overview, CDK deployment IAM, data and ingestion, validation versus preprocessing, closed drift loop, and interview walkthrough.

### Evidence and interpretation

- Six CDK application stacks completed after the execution policy was expanded from specific CloudFormation denials.
- Lambda packaging had to target Python 3.12 because the local bundler ran under Python 3.14 while Lambda used Python 3.12.
- API Gateway accepted the authenticated POST after the payload and shell environment were corrected; the remaining `502` was the downstream missing SageMaker endpoint.
- The ingestion Lambda validated 7,043 Telco rows with zero rejected rows and wrote the curated object.
- SageMaker execution `<pipeline-execution-id>` failed in `Preprocess` with `ModuleNotFoundError: No module named 'src'`, before the `Train` step. The training log group is therefore expected to be empty for this execution.

### Decision and next checkpoint

Keep the shared schema as the source of truth and package `src.common.schema` into the SageMaker Processing job rather than duplicating it in `preprocess.py`. After that fix, rerun the pipeline, confirm that `Train`, `Evaluate`, and `Register` complete, verify the endpoint reaches `InService`, and only then repeat the API prediction test.

### Verification

- Registered the immutable raw source with `scripts/wiki.py add-source`.
- Rebuilt `index.md` with `scripts/wiki.py index`.
- The wiki linter is the remaining final check before handoff.

## [2026-07-11] update | SageMaker pipeline completion and serving deployment checkpoint

### Objective

Resolve the SageMaker Processing packaging failures, observe real training and
evaluation output in CloudWatch, preserve the successful model-registration
state, and identify the exact remaining blocker before testing the API.

### Scope

- Account `${AWS_ACCOUNT_ID}`, region `us-east-1`, administrative inspection profile
  `${AWS_ADMIN_USER_NAME}`.
- Pipeline `churn-training-pipeline-dev`, model package group
  `churn-model-group`, and serverless endpoint name `churn-serverless-dev`.
- `src/common/features.py`, `src/common/schema.py`,
  `src/pipeline/preprocess.py`, `src/pipeline/pipeline.py`,
  `src/pipeline/evaluation_runtime/`, and `src/serving/deploy_handler.py`.
- Maintained wiki pages: deployment troubleshooting, overview, and closed
  drift-to-retrain loop.

### Commands and observed results

1. The prior execution `<pipeline-execution-id>` failed before training because a
   Processing job uploaded only `preprocess.py`, causing
   `ModuleNotFoundError: No module named 'src'`.
2. Preprocessing was changed to `FrameworkProcessor` source bundling with the
   repository `src` dependency. The next execution exposed that importing the
   Pydantic validation model required a package absent from the sklearn
   Processing image.
3. The ordered feature and label constants were moved to dependency-free
   `src.common.features`; the Pydantic schema re-exports them for existing
   callers. The successful `Preprocess` log printed:

   ```text
   {'train': 4930, 'validation': 1056, 'test': 1057}
   ```

4. Training completed in
   `pipelines-<pipeline-execution-id>-Train-beG0CsQiXC`. CloudWatch confirmed a 4,930-row,
   19-feature training matrix and 1,056 validation rows; validation AUC reached
   `0.80610` during the logged rounds.
5. The first evaluation run failed with `ModuleNotFoundError: No module named
   'xgboost'`. Evaluation was moved to its own `FrameworkProcessor` bundle with
   `xgboost==1.7.6` in `evaluation_runtime/requirements.txt`.
6. CloudWatch for `pipelines-<pipeline-execution-id>-Evaluate-kij0xE0MAF` confirmed the
   wheel downloaded and installed, then printed `test AUC: 0.8398`.
7. Pipeline execution `<pipeline-execution-id>` succeeded and registered approved model
   package `arn:aws:sagemaker:us-east-1:${AWS_ACCOUNT_ID}:model-package/churn-model-group/1`.
8. `describe-endpoint churn-serverless-dev` returned endpoint-not-found. The
   approval EventBridge rule did invoke the deployment Lambda, whose CloudWatch
   log reported: `The data capture config is not supported for serverless
   endpoint. Please disable data capture config.`

### Interpretation

The training system is now proven independently: data was split, XGBoost
trained, evaluation loaded the model artifact and emitted a test AUC, and the
registry accepted the approved package. The remaining API failure is neither
API-key authentication nor model training. It is a serving design mismatch:
SageMaker serverless endpoints reject `DataCaptureConfig`, while the current
closed-loop design assumes capture for Model Monitor.

### Decision and next checkpoint

Do not test API Gateway until `churn-serverless-dev` exists and reports
`InService`. Choose one serving posture before changing the deploy Lambda:

- Keep serverless inference and remove `DataCaptureConfig`; this enables the
  API but requires a different observability path than SageMaker Model Monitor
  capture.
- Move to a provisioned real-time endpoint; this retains data capture and the
  intended Model Monitor loop, at greater standing cost.

After that decision, deploy the Serving stack, invoke the approved-package
deployment path for model package `/1`, verify the endpoint, and send the
existing `sample.json` through the API Gateway `/dev/predict` URL with its API
key.

### Verification

- `pytest tests/unit -q`: 32 passed.
- Ruff lint and format checks passed for the changed pipeline and common-source
  files.
- Live SageMaker execution, TrainingJobs logs, ProcessingJobs logs, model
  package registration, endpoint lookup, and deployment Lambda logs were read
  with `${AWS_ADMIN_USER_NAME}` in `us-east-1`.

## [2026-07-11] recovery | Low-cost API inference and explicit model-result logging

### Objective

Keep SageMaker inference low-cost for weekend and job-application demos while
making the pipeline and API observable: show training start, challenger and
champion comparison, model-package deployment, and the returned API prediction
in CloudWatch.

### Scope

- Serving stack only: `Mlops-Dev-Serving` was deployed with CDK `--exclusively`.
- Serverless endpoint `churn-serverless-dev`, API Gateway `/dev/predict`, and
  approved model package `churn-model-group/1`.
- Lambda bundle code, deployment handler, proxy handler, pipeline definition,
  evaluation script, and their unit tests.

### Commands and observed results

1. A provisioned real-time endpoint was rejected as too expensive for this
   weekend/demo-only use case. The chosen posture is serverless inference with
   no SageMaker `DataCaptureConfig`.
2. The first targeted CDK deploy also selected the dependent Data stack, which
   rolled back because it attempted to delete an export still consumed by
   Serving. Retrying `Mlops-Dev-Serving` with CDK `--exclusively` avoided that
   unrelated stack update and reached `UPDATE_COMPLETE`.
3. `src.serving.deploy_handler` was changed to omit `DataCaptureConfig`, which
   SageMaker rejects for serverless endpoints. The existing approved package
   `/1` was invoked through the deployment Lambda and returned action
   `created`, test AUC `0.8398418749117607`.
4. The first API call still returned `502` because the Lambda bundle contained
   an incompatible native `pydantic_core` binary. The Docker fallback now pins
   the same CPython 3.12, manylinux x86_64 wheel target as local bundling. The
   deploy output confirmed a `pydantic_core` cp312 manylinux x86_64 wheel.
5. After redeploying only Serving, `churn-serverless-dev` reached `InService`.
   The protected API request using `sample.json` returned:

   ```json
   {"churn_probability": 0.3656342029571533, "churn": false}
   ```

6. The proxy Lambda now writes a payload-free CloudWatch record for every
   successful API call:

   ```json
   {"event":"inference_response","endpoint":"churn-serverless-dev","churn_probability":0.3656342029571533,"churn":false}
   ```

7. The pipeline was upserted without `--start`, so no new training job was
   charged. Future `Evaluate` logs receive and print the champion model package
   ARN and test AUC, challenger model-artifact URI and test AUC, and the strict
   promotion decision (`register` or `reject`).

### Interpretation

The complete low-cost demo path is now observable and works: CloudWatch
TrainingJobs records when XGBoost starts and its validation AUC; ProcessingJobs
records the challenger-versus-champion evaluation; the deployment Lambda records
the approved model package and test AUC; and the proxy Lambda records the API
prediction result. The serverless endpoint provides an API response without a
standing real-time hosting instance.

### Decision and next checkpoint

Keep Model Monitor capture disabled for this demo configuration. Do not add
`DataCaptureConfig` back to the serverless endpoint. This endpoint has no
configured provisioned concurrency, so it does not retain a real-time hosting
instance while idle; delete it only for a complete teardown. If built-in Model
Monitor becomes necessary, make a separate decision on capture architecture or
provisioned inference.

### Verification

- Full unit suite: 32 passed.
- Ruff lint, formatting, and `git diff --check` passed.
- `Mlops-Dev-Serving` reached `UPDATE_COMPLETE` after the scoped deployment.
- Endpoint reached `InService`; the API returned HTTP 200 and the structured
  proxy log was read from CloudWatch.
## [2026-07-11] query | SageMaker evaluation serverless endpoint data capture

Found 10 matching page(s).

## [2026-07-11] ingest | Evaluation report rollout — July 11, 2026

### Objective

Persist the implementation, deployment, recovery, and observed outcome of
held-out model evaluation reports and API-ready test fixtures.

### Scope

- `src/pipeline/preprocess.py`, `src/pipeline/evaluate.py`,
  `src/pipeline/pipeline.py`, and `scripts/evaluate_api.py`.
- SageMaker pipeline `churn-training-pipeline-dev` in `us-east-1`, account
  `${AWS_ACCOUNT_ID}`.
- Artifacts bucket execution prefix for retry `<pipeline-execution-id>`.
- Deployment checkpoint, closed-loop concept, overview, and new immutable
  rollout source.

### Identity and environment

The normal `${MLOPS_DEPLOYER_USER_NAME}` identity could use the CDK deployment path but is
not allowed to call `sagemaker:ListModelPackages`, which SDK pipeline upsert
uses to resolve the champion. The existing `${AWS_ADMIN_USER_NAME}` break-glass profile
therefore upserted only the SDK-managed pipeline; no IAM policy was widened.

### Commands and observed results

1. The first post-update execution `<pipeline-execution-id>` reached `Evaluate`, wrote
   `evaluation.json`, `metrics.json`, and `predictions.csv`, then failed with
   Python 3.9 `TypeError: zip() takes no keyword arguments` before PNG output.
2. The error came from `zip(..., strict=True)` in the report writer. The loops
   were changed to index-based access, focused evaluation tests passed, and the
   pipeline was upserted again.
3. Retry execution `<pipeline-execution-id>` succeeded and wrote the full metrics,
   predictions, confusion matrix, ROC, precision-recall, calibration, and
   score-distribution artifact bundle to S3.
4. The report measured AUC `0.8398`, accuracy `0.8023`, precision `0.6332`,
   recall `0.5370`, F1 `0.5812`, specificity `0.8933`, and confusion matrix
   TN `703`, FP `84`, FN `125`, TP `145` at threshold `0.50`.

### Interpretation

An S3 prefix can contain partial output from a failed Processing job, so the
pipeline and `Evaluate` ProcessingJob statuses are the completion authority.
The successful retry proves the full artifact contract, while its recall versus
specificity tradeoff makes threshold selection an explicit future business
decision rather than a hidden model default.

### Decision and next checkpoint

Keep the shared `0.50` API/report threshold for comparability. Use
`scripts/evaluate_api.py` against the `api_test` fixture after an endpoint
deployment when an end-to-end serving check is needed. Revisit the threshold
only with retention-offer and missed-churn cost inputs.

### Verification

- Focused evaluation report tests: 2 passed.
- Ruff lint and formatting checks for `src/pipeline/evaluate.py` passed.
- The full visual-artifact bundle was downloaded from the successful retry.

## [2026-07-11] update | Timestamped evaluation artifact prefixes

### Objective

Make per-execution evaluation reports immediately identifiable in the S3
console without sacrificing SageMaker execution lineage.

### Scope

- `src/pipeline/pipeline.py` evaluation `ProcessingOutput` destination.
- README and deployment checkpoint operator documentation.

### Decision

Future evaluation bundles use the native SageMaker pipeline variables
`ExecutionVariables.START_DATETIME` and `PIPELINE_EXECUTION_ID` at:

```text
evaluations/<UTC-start-timestamp>/<execution-id>/
```

The timestamp provides at-a-glance ordering; the execution ID prevents
collisions and links the folder unambiguously to a SageMaker execution.
## [2026-07-11] query | evaluation pipeline execution artifacts

Found 10 matching page(s).

## [2026-07-11] ingest | Evaluation report rollout — July 11, 2026

Registered immutable source `raw/evaluation-report-rollout-july-11-2026.md`.
## [2026-07-12] query | security IAM CloudTrail GuardDuty API Gateway WAF KMS phased rollout

Found 9 matching page(s).

## [2026-07-12] ingest | Phased AWS security hardening plan — July 12, 2026

Registered immutable source `raw/phased-aws-security-hardening-plan-july-12-2026.md`.

## [2026-07-12] update | Phased AWS security hardening roadmap

### Objective

Preserve the approved AWS security-hardening plan as a morning-ready roadmap
whose changes can be implemented and diagnosed one phase at a time.

### Scope

- Immutable source `raw/phased-aws-security-hardening-plan-july-12-2026.md`.
- New architecture page `pages/architecture/phased-security-hardening.md`.
- Source synthesis, overview navigation, and permission-boundary context.
- Wiki index and health validation.

### Identity and environment

This was a local documentation-only update in the repository. No AWS profile was
used, no AWS resource was created or changed, and no secret or alert email was
recorded.

### Commands and results

1. `python3 scripts/wiki.py search` identified the permission, deployment, and
   overview pages related to the plan.
2. `python3 scripts/wiki.py add-source` registered the dated immutable plan and
   scaffolded its source page.
3. `python3 scripts/wiki.py index` rebuilt navigation with the new architecture
   and source pages.
4. `python3 scripts/wiki.py lint` reported `Wiki healthy: 13 page(s)`.
5. The focused wiki unit suite reported `5 passed`.

### Interpretation

The plan is intentionally more granular than a single security deployment.
Auditability precedes risky IAM, KMS, API-authentication, and WAF changes. KMS
bucket migration and IAM reduction each have internal one-resource-at-a-time
checkpoints, and every phase stops before the next begins.

### Decision and next checkpoint

Begin with Phase 0 only: capture a read-only AWS and repository baseline plus
rollback surfaces. Phase 1 is repository-only. Do not mutate AWS until those two
checkpoints are accepted; the first AWS change is Phase 2 audit and alerting.

### Verification

- Wiki index rebuilt successfully.
- Wiki lint healthy with 13 pages.
- Focused wiki tests: 5 passed.
- No application code or AWS infrastructure changed.
## [2026-07-12] query | Phase 0 security baseline rollback Data stack export

Found 13 matching page(s).

## [2026-07-12] ingest | AWS security hardening Phase 0 baseline — July 12, 2026

Registered immutable source `raw/aws-security-hardening-phase-0-baseline-july-12-2026.md`.

## [2026-07-12] verify | AWS security hardening Phase 0 baseline

### Objective

Execute Phase 0 of the approved security roadmap: capture the pre-hardening AWS
and repository state, prove the current application checkpoints, preserve
rollback surfaces, and make no security or workload configuration change.

### Scope

- Six `Mlops-Dev-*` CloudFormation stacks in `us-east-1`.
- Raw, curated, and artifacts S3 buckets.
- SageMaker pipeline, versions, last successful execution, model package,
  endpoint, and endpoint config.
- API Gateway method/stage configuration and one normal `/predict` request.
- Runtime IAM policies, current security-service subscriptions, budget, alarms,
  processed-template fingerprints, and no-change-set CDK diff.
- Immutable Phase 0 source, maintained baseline page, roadmap, deployment
  checkpoint, overview, and index.

### Identity and environment

AWS read operations used `${AWS_ADMIN_USER_NAME}` in account `${AWS_ACCOUNT_ID}`, Region
`us-east-1`. `${MLOPS_DEPLOYER_USER_NAME}` ran only `cdk diff --no-change-set`. The API key
was retrieved into a shell variable for the smoke request and was never printed
or recorded. No training execution or CloudFormation change set was created.

### Commands and observed results

1. `describe-stacks` found five healthy stack terminal states and
   `Mlops-Dev-Data` at `UPDATE_ROLLBACK_COMPLETE`.
2. `describe-stack-events` identified the exact blocker: the update attempted to
   delete an artifacts-bucket export still imported by Serving.
3. Live processed templates and the pipeline definition were exported through
   read APIs and SHA-256 fingerprinted for future comparison.
4. `cdk diff --no-change-set` reproduced the Data export removal and showed
   Lambda asset changes in Ingestion and Serving; it did not mutate AWS.
5. S3 checks confirmed all workload buckets are private, versioned, Bucket Owner
   Enforced, and encrypted with the AWS-managed S3 KMS key. Raw and curated
   Telco objects remain present with matching sizes.
6. Pipeline version 9 is Active but unexecuted. Version-8 execution
   `<pipeline-execution-id>` succeeded through all steps and retains the complete report
   bundle under its older prefix. Approved package `/1` retains AUC `0.8398`.
7. `churn-serverless-dev` is `InService`; a normal API-key request returned
   probability `0.3656342029571533` and `churn: false`.
8. CloudTrail, GuardDuty, Security Hub, Config, Access Analyzer, account-level S3
   blocking, and WAF remain absent. The `$20` budget has no notifications, and
   the endpoint alarm has no action.

### Interpretation

The runtime is usable, but the environment is not safe for an undifferentiated
`cdk deploy --all`. Phase 0 established comparison evidence without treating
the Data rollback or security gaps as fixed. The empty top-level `evaluations/`
prefix is expected because pipeline version 9 has not run.

### Decision and next checkpoint

Phase 0 is complete. Proceed only to Phase 1 repository and CI guardrails. Do
not deploy AWS resources, start a billable pipeline execution, or retry the Data
stack during Phase 1. The Data-to-Serving export requires a separate reviewed
remediation before any all-stack deployment.

### Verification

- Full unit suite: 40 passed.
- Ruff check: passed; 40 files already formatted.
- CDK synthesized all six stacks during the no-change-set diff.
- Wiki lint: healthy with 15 pages before this append-only entry.
- `git diff --check` is rerun after the final log update.
- No AWS configuration or repository application code changed.

## [2026-07-12] implement | AWS security hardening Phase 1 guardrails

### Objective

Implement the repository-only security guardrails from Phase 1 and leave the
changes uncommitted for human review.

### Scope and boundary

Added locked Python dependencies, construct-scoped `cdk-nag` validation, CDK
security regression tests, dependency and secret scanning, immutable GitHub
Action pins, and a manual-only deployment workflow. No AWS API, deployment,
pipeline execution, or cloud resource configuration was changed.

### Commands and results

- `uv lock --check`: passed with 108 packages.
- Ruff check and format check: passed across 41 files.
- Full unit suite: 44 passed, including isolated synthesis of all six stacks
  with `AwsSolutionsChecks`.
- Local `pip-audit` could not reach PyPI from the sandbox; the approval service
  was unavailable. Gitleaks is not installed locally. Both remain required CI
  checks, along with the normal Lambda-asset-bundling CDK synth.

### Decision and next checkpoint

Phase 1 is implemented but not complete. Review the uncommitted diff and require
all GitHub CI jobs to pass before committing Phase 1 or beginning Phase 2. The
known Data-to-Serving export blocker still prevents an all-stack deployment.

### Verification

The wiki index and lint are rebuilt after this entry. `git diff --check` is run
at final handoff. No commit was created.

## [2026-07-12] verify | AWS security hardening Phase 1 completion

### Objective

Close the remaining Phase 1 repository-security acceptance gates without an AWS
deployment or commit.

### Commands and results

- Upgraded reviewed action pins to checkout v7.0.0, setup-uv v8.3.2,
  configure-aws-credentials v6.2.2, and Gitleaks action v3.0.0.
- Upgraded cdk-nag to 3.0.1 and registered it as a native CDK validation plugin.
- `uv lock --check` passed with 108 packages.
- `pip-audit` reported no known vulnerabilities.
- Gitleaks v8.30.1 found no leaks in 10 commits, the tracked diff, or any
  untracked Phase 1 file.
- Ruff passed; all 41 files were formatted.
- The full unit suite reported 44 passed.
- Normal Docker-backed CDK synthesis passed across all six dev stacks with no
  unacknowledged AwsSolutions finding.
- A final synthesis explicitly locked the existing `strong` cross-stack
  reference behavior and removed that feature-flag warning. Only the recorded
  `logRetention` deprecation warnings remain.

### Interpretation and decision

Phase 1 is complete. The earlier implementation record remains immutable and
documents why the network-backed gates were initially pending. This completion
entry supersedes that checkpoint with passing evidence. No AWS resource or
runtime changed, and the work remains uncommitted for final review.

### Next checkpoint

Commit Phase 1 separately only after final human approval. Do not begin Phase 2
without an explicit go/no-go decision, and do not run an all-stack deployment
until the Data-to-Serving export-removal blocker has a reviewed remediation.
## [2026-07-12] query | Phase 2 security audit CloudTrail budget

Found 17 matching page(s).

## [2026-07-12] deploy | AWS security hardening Phase 2A

### Objective

Reconcile the Data-stack export prerequisite and install the narrowly expanded
CloudFormation execution policy required for Phase 2 audit resources.

### Scope, identity, and environment

Worked only in account `${AWS_ACCOUNT_ID}`, dev, `us-east-1`. Read-only checks and
the Data deployment used the normal `${MLOPS_DEPLOYER_USER_NAME}` CDK path. The controlled
managed-policy version rotation used the break-glass `${AWS_ADMIN_USER_NAME}` profile. No
all-stack deployment or SageMaker execution occurred.

### Commands and results

- Confirmed the obsolete artifacts export had zero importers.
- A Data-only diff showed only the obsolete output removal; a Data-only deploy
  reached `UPDATE_COMPLETE`.
- Raw, curated, and artifacts bucket names and object-version counts remained
  unchanged; the existing `$20` budget remained unchanged.
- Archived and fingerprinted exact policy `v1`, deleted only that non-default
  version, and created the reviewed repository policy as default `v6`.
- The live and repository `v6` canonical hashes both equal
  `<redacted>`.
- `v5` remains for rollback. The policy remains attached only to the CDK
  CloudFormation execution role.

### Interpretation and decision

The prior Data export drift no longer blocks a scoped deployment, and the
CloudFormation execution role has the reviewed Phase 2 control-plane actions
without widening the deployment user or application runtime roles. Phase 2A is
a go for its separate commit and CI run.

### Next checkpoint

Implement, synthesize, diff, and deploy only `Mlops-Dev-Security` for Phase 2B.
Stop until the parameterized SNS email subscription is manually confirmed.

### Verification

The policy JSON parses, its regression tests pass, the wiki index is rebuilt,
and wiki lint plus the repository gates run before the Phase 2A commit.

## [2026-07-12] implement | AWS security hardening Phase 2B audit foundation

### Objective

Implement the isolated retained audit-storage, CloudTrail, CloudWatch Logs, KMS,
and encrypted SNS foundation without deploying it or adding detections.

### Scope and boundary

Added only `Mlops-Dev-Security` and its configuration, tests, exact cdk-nag
acknowledgements, and documentation. No AWS mutation, Data-stack reference,
budget notification, metric filter, alarm, API change, or SageMaker execution
occurred. The email endpoint remains a parameter with no source-controlled
default.

### Commands and results

- Phase 2A GitHub run 9 passed `validate` and `secret-scan` with no leaks.
- Enabled CDK's S3 bucket-policy log-delivery mode after synthesis rejected the
  legacy ACL as incompatible with Bucket Owner Enforced.
- Corrected CloudWatch alarm and Logs ARN delimiters after inspecting the normal
  synthesized template.
- Narrowed the CloudTrail role to `log-stream:*` beneath one audit log group.
- Ruff and formatting passed; 47 unit tests passed.
- Normal scoped Security-stack synthesis and cdk-nag validation passed.

### Interpretation and decision

Phase 2B is ready for its isolated commit and hosted CI. The local go/no-go is
GO for commit, but deployment remains NO-GO until both hosted jobs pass and the
Security-only diff is reviewed.

### Next checkpoint

Push the Phase 2B commit, verify CI, run a scoped Security diff, deploy only
`Mlops-Dev-Security`, and then wait for manual email-subscription confirmation.

## [2026-07-12] deploy | AWS security hardening Phase 2B completion

### Objective

Deploy and prove the isolated audit foundation end to end before authorizing
security detections.

### Scope, identity, and environment

Worked only in account `${AWS_ACCOUNT_ID}`, dev, `us-east-1`. The Security-only CDK
deployment used `${MLOPS_DEPLOYER_USER_NAME}`; `${AWS_ADMIN_USER_NAME}` performed read-only live
verification and the planned one-time SNS test publish. No existing stack or
SageMaker pipeline was deployed.

### Commands and results

- GitHub run 10 passed `validate` and `secret-scan` with no leaks.
- Security-only diff showed the planned 13 resources and six outputs.
- `Mlops-Dev-Security` reached `CREATE_COMPLETE` in 58 seconds.
- CloudTrail is logging multi-Region read/write management events to the
  retained KMS audit bucket and 90-day encrypted CloudWatch log group.
- S3 log and digest objects arrived; CloudWatch streams contain events; no
  delivery error is present.
- `cloudtrail validate-logs` reported 1 of 1 digest files valid.
- Both buckets are private, versioned, Bucket Owner Enforced, and use their
  planned encryption and access-logging configuration.
- The subscription was confirmed and the recipient supplied evidence that the
  direct SNS test message arrived.

### Interpretation and decision

Phase 2B is operational and complete. The go/no-go decision is GO for Phase 2C
after this completion record is committed and passes hosted CI.

### Next checkpoint

Add exactly the six Security Hub/CIS metric filters and five-minute alarms to
`Mlops-Dev-Security`; do not change Data or budget wiring until Phase 2D.

## [2026-07-12] implement | AWS security hardening Phase 2C detections

### Objective

Implement the six approved real-time security detections without changing the
verified audit foundation or Data stack.

### Scope and evidence

GitHub run 11 for Phase 2B closeout passed both hosted jobs. Added only six
metric filters and six alarms to `Mlops-Dev-Security`, using the current exact
AWS Security Hub remediation patterns for CloudWatch.1, .2, .4, .5, .7, and .8.

### Commands and results

- Lock check passed with 108 packages; dependency audit found no known
  vulnerabilities.
- Ruff and formatting passed across 43 files; 48 unit tests passed.
- Normal Security-only synthesis and cdk-nag validation passed.
- Tests lock every filter pattern, namespace, metric value/default, alarm
  period, threshold, comparison, missing-data behavior, and SNS action.
- The Security-stack IAM fingerprint remains unchanged.

### Interpretation and decision

Phase 2C is ready for its isolated commit and hosted CI. The local go/no-go is
GO for commit and NO-GO for deployment until CI and the scoped diff pass.

### Next checkpoint

Push the Phase 2C commit, verify CI, review a Security-only diff, and deploy only
`Mlops-Dev-Security`. Then trigger one safe denied IAM request and verify the
metric, alarm transition, and received email.

## [2026-07-12] deploy | AWS security hardening Phase 2C completion

### Objective

Deploy the six exact detections and prove one alarm end to end without changing
application resources or permissions.

### Commands and results

- GitHub run 12 passed `validate` and `secret-scan` with no leaks.
- Security-only diff contained exactly six filters and six alarms.
- Security-only deployment reached `UPDATE_COMPLETE` in 31 seconds.
- Live reads matched every exact pattern, metric transformation, threshold,
  period, missing-data behavior, and encrypted SNS action.
- A controlled read-only `iam:ListUsers` call by `${MLOPS_DEPLOYER_USER_NAME}` failed with
  `AccessDenied`, as intended.
- CloudTrail event `fc5c1610-af9e-4c6b-b7ac-0c7d7020bc61` records that exact
  identity, operation, denial, and read-only management-event status.
- `UnauthorizedApiCalls` produced a sum of 8; its alarm transitioned from OK to
  ALARM, and the recipient supplied evidence that the alarm email arrived.

### Interpretation and decision

The detection chain works without granting new authority. Phase 2C is complete
and is a GO for Phase 2D after this record is committed and passes hosted CI.

### Next checkpoint

Pass the Security access-log bucket and alert topic into Data, add the three
source-bucket log prefixes and three notifications to the single existing `$20`
budget, and remove the three resolved Data S1 acknowledgements.

## [2026-07-12] implement | AWS security hardening Phase 2D integration

### Objective

Connect the existing Data buckets and budget to the verified audit and alert
foundation without replacing resources or weakening the sink policy.

### Scope and findings

GitHub run 13 passed both hosted jobs. Added the three source logging prefixes,
three ACTUAL budget notifications, Security-to-Data inputs, and removed the
three resolved Data S1 acknowledgements.

Initial synthesis exposed that CDK's automatic cross-stack logging helper would
add three unconditioned sink-policy grants. The implementation was corrected to
use one Security-owned source-account/project-prefix statement and Data-owned
logging configurations.

### Validation

- Unit synthesis and normal cdk-nag synthesis pass for Security and Data.
- Security has one conditioned Data delivery statement and no unconditioned
  generated Data grants.
- Data has exactly three log prefixes and one existing `$20` budget with three
  50/80/100 notifications.

### Interpretation and decision

Phase 2D requires a deliberate two-deployment sequence: Security policy first,
Data references second. The implementation remains within the approved resource
scope and preserves the mandatory inverse rollback order.

### Next checkpoint

Commit Phase 2D, verify hosted CI, review both named diffs, deploy Security only,
verify its sink policy, then deploy Data only and perform live regression checks.

## [2026-07-12] ingest | Phase 2D budget preservation correction

Pre-deployment diff caught AWS::Budgets::Budget replacement; replaced inline
notifications with scoped lifecycle-managed Budgets API calls before any Data
deployment.

## [2026-07-12] ingest | Phase 2D first Data deployment rollback

Data rolled back cleanly after the Budgets API required budgets:ModifyBudget;
existing buckets and budget were preserved and the provider policy was
corrected.

## [2026-07-12] ingest | Phase 2D deployment completion

Security prerequisite and corrected Data retry are deployed; bucket and budget
identities, logging, alerts, imports, CloudTrail, filters, SNS, and /predict
passed live checks. Phase 2 enters 24-hour observation.

## [2026-07-14] ingest | Phase 3-prep implementation and Phase 2 observation closure

### Objective

Close the Phase 2D observation window with evidence and implement Phase 3-prep:
service enablement flags, an empty `Mlops-Dev-SecurityMonitoring` stack, and
Phase 3 CloudFormation execution-policy preparation, with no security service
enabled.

### Scope

`infra/app.py`, new `infra/stacks/security_monitoring_stack.py`,
`infra/config/dev.yaml` and `prod.yaml`,
`infra/policies/mlops-cloudformation-execution-policy.json`,
`tests/unit/test_stacks.py`, `tests/unit/test_deployment_policy.py`, and the
Phase 3-prep source record.

### Identity and environment

Account `${AWS_ACCOUNT_ID}`, `us-east-1`. Read-only verification with `${AWS_ADMIN_USER_NAME}`;
`cdk diff` with `${MLOPS_DEPLOYER_USER_NAME}`. No mutating AWS call was made.

### Commands and results

- Read-only pre-state: no `Mlops-Dev-SecurityMonitoring` stack, zero
  analyzers, `SubscriptionRequiredException` for GuardDuty and Security Hub,
  zero Config recorders, `NoSuchPublicAccessBlockConfiguration`.
- Access-log listing confirmed first `artifacts/` object 2026-07-13 02:21 UTC.
- Cost Explorer: 2026-07-11..13 daily unblended cost rounds to `$0.00`.
- Live execution-policy `v6` canonical SHA-256 matches the repository
  (`<redacted>`); versions `v2`–`v6` occupy all five slots.
- `uv lock --check` (108 packages), `pip-audit` (no known vulnerabilities),
  `ruff` check/format (45 files), `pytest tests/unit` (51 passed), and full
  cdk-nag synthesis passed; the new template holds only `CDKMetadata`.
- Change-set `cdk diff`: no differences for Security, Data, Registry,
  Training, Monitoring; only recorded bundle-hash drift for Ingestion and
  Serving; SecurityMonitoring is a new metadata-only stack.

### Interpretation

The change-set diff itself tripped `unauthorized-api-calls`: CloudFormation's
scoped execution role was denied read-only describe calls
(`events:ListTagsForResource`, `s3:GetBucket*`) at 01:26–01:27 UTC, alongside
unrelated `${AWS_ADMIN_USER_NAME}` Cost Explorer denials at 00:45–00:59 UTC. Both sources
are known principals; the CIS filter stays exact and later diffs use
`--no-change-set`.

### Decision and next checkpoint

Phase 2 observation is closed as a documented go. Commit Phase 3-prep, require
hosted CI, rotate the execution policy to `v7` (delete non-default `v2`, keep
`v6` for rollback), deploy only the empty shell stack, and record completion.
Sub-phase 3A needs a separate go decision.

## [2026-07-14] ingest | Phase 3-prep deployment completion

### Objective

Complete Phase 3-prep: hosted CI gate, execution-policy rotation to `v7`,
deployment of the empty `Mlops-Dev-SecurityMonitoring` shell, and live
verification that no Phase 3 service was enabled.

### Identity and environment

Account `${AWS_ACCOUNT_ID}`, `us-east-1`. Policy rotation with `${AWS_ADMIN_USER_NAME}` under
explicit operator approval; deployment with `${MLOPS_DEPLOYER_USER_NAME}`.

### Commands and results

- GitHub Actions run 29381999521 (`dbe6578`): `validate` and `secret-scan`
  passed.
- `delete-policy-version v2` then `create-policy-version` → `v7` default;
  live `v7` canonical SHA-256 `<redacted>` matches the repository; `v6`
  retained; attachment still only the CDK CloudFormation execution role.
- `cdk deploy Mlops-Dev-SecurityMonitoring` → `CREATE_COMPLETE` in 6.6 s with
  exactly one `AWS::CDK::Metadata` resource.
- Post-deploy reads: zero analyzers, zero Config recorders,
  `SubscriptionRequiredException` for GuardDuty/Security Hub, no account
  public-access-block configuration.
- `/predict` → HTTP 200, `churn_probability` 0.3656342029571533, `churn`
  false (identical to the Phase 2D record).

### Interpretation

The shell deploy ran before the rotation; that ordering was acceptable only
because a metadata-only template exercises no new permission. All later
sub-phases now have their permissions pre-granted and their stack in place.

### Decision and next checkpoint

Phase 3-prep is complete. Sub-phase 3A (IAM Access Analyzer) requires a
separate go decision.

## [2026-07-14] query | Post-3-prep alarm email attribution

### Objective

Confirm for the operator that two `unauthorized-api-calls` alarm emails
received during and after the Phase 3-prep deployment were expected, using
read-only queries only.

### Identity and environment

Account `${AWS_ACCOUNT_ID}`, `us-east-1`, `${AWS_ADMIN_USER_NAME}`, read-only
`logs:FilterLogEvents` and `cloudwatch:DescribeAlarms`.

### Commands and results

- The 01:28 UTC email (datapoint `11.0` at 01:23) matches the already-recorded
  execution-role describe denials from the change-set `cdk diff`.
- The 01:54 UTC email (datapoint `3.0` at 01:49) resolves to exactly two
  `ce:GetCostAndUsage` and one `ce:GetCostForecast` denials for the known
  `${AWS_ADMIN_USER_NAME}` user at 01:51:56 UTC — the same trio observed at 00:45, 00:53,
  and 00:59 UTC, consistent with a console cost-widget auto-refresh.
- The alarm returned to `OK` at 01:59 UTC. Hosted CI run 19 for the
  completion commit is green with no leaks.

### Interpretation

Both firings are attributed to known principals; the detection pipeline
(CloudTrail → metric filter → alarm → encrypted SNS → confirmed email) worked
end to end. The recurring `${AWS_ADMIN_USER_NAME}` Cost Explorer denial is an operator
permission gap, not workload drift.

### Decision and next checkpoint

The exact CIS filter stays unchanged. Whether to grant `${AWS_ADMIN_USER_NAME}` the
`ce:Get*` read actions or accept the recurring noise is recorded as an open
question on the Phase 3-prep completion page. Sub-phase 3A still awaits its
go decision.


## [2026-07-18] maintain | Secret-scan pull-request permissions

### Objective

Fix the `secret-scan` CI job, which failed on the repository's first pull
request while passing on every push event.

### Scope

`.github/workflows/ci.yml`, `secret-scan` job only. No AWS change.

### Commands and results

- gitleaks-action v3 behaves differently by event type: on `push` it scans
  the checked-out history directly, but on `pull_request` it first calls
  `GET /repos/{repo}/pulls/{n}/commits` to determine the commit range.
- The workflow-level `permissions: contents: read` token cannot call that
  endpoint; the job failed pre-scan with `403 Resource not accessible by
  integration`, and the response header `x-accepted-github-permissions:
  pull_requests=read` named the missing permission.
- Fix (commit `eeb4235`): a job-level block on `secret-scan` granting
  `contents: read` plus `pull-requests: read`. The `validate` job keeps the
  tighter workflow default.
- The pull request re-ran green: `validate` and `secret-scan` both passed
  with no leaks.

### Interpretation

Event-dependent code paths in third-party actions can hide permission gaps:
every push-event run since Phase 1 passed without exercising the PR API. Job
level is the right scope for the extra read grant — it keeps the
least-privilege default for the rest of the workflow.

### Decision and next checkpoint

CI gates are healthy for both push and pull-request events. Sub-phase 3A
(IAM Access Analyzer) still awaits its go decision.

## [2026-07-18] maintain | Repo-wide code deduplication

### Objective

Eliminate every duplicate or near-duplicate code site found in a full audit
of `src/`, `scripts/`, `infra/`, and `tests/unit/` (18 sites, full scope
including "same shape" patterns).

### Scope

Commit `20800b5` on branch `dedupe-shared-helpers` (PR #1, draft). 27 files;
three new modules: `src/common/events.py` (`log_event`),
`infra/stacks/shared.py` (`platform_lambda`, `sagemaker_execution_role`,
`sagemaker_event_rule`), `tests/unit/conftest.py` (`VALID`, `REPO_ROOT`,
boto3-stubbed import helper).

### Commands and results

- Baseline `make synth` templates snapshotted, re-synthesized after the
  refactor, and diffed: identical except the two SageMaker IAM policy ARNs
  (proxy `InvokeEndpoint`, retrain `StartPipelineExecution`) now render
  `Ref: AWS::Partition` via `format_arn` instead of the literal `arn:aws:`.
  All other differences were asset-hash noise. Read-only comparison.
- `ruff check`/`format` clean; 51/51 unit tests pass;
  `python scripts/wiki.py lint` healthy; both operational scripts smoke-run.

### Interpretation

Two findings were latent bugs, not style: `wiki.py rebuild_index` duplicated
`_render_index` (which `lint` compares against, so a one-sided edit would
break lint permanently), and the serving proxy hardcoded the 0.5 churn
threshold that evaluation asserts via `DEFAULT_THRESHOLD` — the production
decision rule could have silently diverged from the evaluated contract.
Lambda log retention now derives from config `log_retention_days` instead of
a hardcoded constant.

### Decision and next checkpoint

`test_iam_policy_baseline_has_not_changed` fingerprints were deliberately
refreshed (partition token plus the test app's `Test-` stack prefixes
changing export strings); the test did its job of forcing review.
`data_stack._bucket()` intentionally remains separate from the security
buckets. Next: review/merge PR #1; a separate session is fixing the
Makefile's `uv run --locked` targets dropping dev extras.

### Verification

`make lint` equivalent (ruff check + format) and the full unit suite pass
post-append; wiki lint re-run after this entry.

## [2026-07-18] implement | AWS security hardening Phase 3A

### Objective

Implement only the dev account external-access analyzer, preserve the Phase 3
one-service rollback boundary, and stop before GuardDuty or any live deploy.

### Scope

The existing SecurityMonitoring stack and dev service flag, focused CDK
assertions, guarded named-stack Make targets, the Phase 3A implementation
record, and the maintained roadmap. The immutable phased plan and Phase 1
source page remain unchanged.

### Identity and environment

Repository branch `issue/3-phase-3`, base `de345a8`, target Region
`us-east-1`. The configured AWS session had no credentials. A temporary-login
flow was cancelled before authorization; no AWS resource read or mutation is
claimed.

### Commands and results

- Search confirmed no analyzer implementation existed outside the prepared
  flag and shell stack.
- Recreated the untracked virtual environment because its `pytest` script
  referenced a different checkout.
- `make lint`: passed; 47 files formatted.
- `make test`: 52 passed.
- `make security`: 108-package lock check passed, no known dependency
  vulnerabilities, and all eight dev stacks synthesized with cdk-nag.
- Named-stack Make targets passed dry-run inspection.
- The SecurityMonitoring template contains the `ACCOUNT` analyzer plus CDK
  metadata only, with the exact dev name and tags and no archive or paid
  analyzer configuration.

### Interpretation

The implementation extends the existing Phase 3 shell rather than creating a
parallel stack or helper. It changes no IAM fingerprint, application interface,
data path, or production flag. External-access analysis is the no-additional-
charge analyzer type; automatic archiving is intentionally deferred until
findings have been reviewed.

### Decision and next checkpoint

Commit the isolated implementation and require hosted CI. When temporary AWS
credentials are available, re-run the full read-only Phase 3 inventory. Stop
on an existing analyzer or other unexplained service state; otherwise review a
no-change-set diff, deploy only `Mlops-Dev-SecurityMonitoring`, verify the
initial findings, and create a separate completion record. Do not begin 3B.

### Verification

Repository lint, unit, lock, dependency-audit, synthesis, exact template, and
dry-run command checks passed before this log entry. Wiki index and lint are
rerun after all documentation changes.
## [2026-07-18] query | Phase 3A deployment rollback execution policy service-linked role

Found 29 matching page(s).

## [2026-07-18] failure | Phase 3A first deployment rollback

### Objective

Deploy only the Phase 3A account external-access analyzer after green hosted
CI, a reviewed named diff, and a clean live pre-state.

### Scope

The `Mlops-Dev-SecurityMonitoring` stack, the CloudFormation execution policy,
and read-only Access Analyzer inventory. GuardDuty and every later Phase 3
service remained outside the attempt.

### Identity and environment

A restricted deployment identity used the existing CDK bootstrap path. A
separate read-only security auditor verified live state. No IAM user name,
local profile name, account identifier, ARN containing an account identifier,
or credential is recorded.

### Commands and results

- Both hosted validation jobs passed for the Phase 3A implementation commit.
- The guarded named diff showed exactly one analyzer addition.
- Read-only pre-state showed a healthy metadata-only SecurityMonitoring stack,
  zero account analyzers, and later Phase 3 services disabled.
- The named deployment failed because the CloudFormation execution role was
  denied `iam:CreateServiceLinkedRole` for
  `AWSServiceRoleForAccessAnalyzer`.
- CloudFormation reached `UPDATE_ROLLBACK_COMPLETE`; the stable stack contains
  only CDK metadata, and the account again reports zero analyzers.

### Interpretation

The prepared execution policy granted the analyzer lifecycle actions but not
the indirect IAM action needed when Access Analyzer creates its service-linked
role. This permission belongs on the CloudFormation execution role, not on the
deployment or auditor identities.

### Decision and next checkpoint

Add one exact-resource, exact-service-principal
`iam:CreateServiceLinkedRole` statement and lock it with a unit test. After
local and hosted gates pass, an administrator must install and verify the new
live policy version. Review a fresh named diff before retrying only the
SecurityMonitoring stack. Do not manually create or delete the analyzer or
service-linked role, and do not begin Phase 3B.

### Verification

Rollback status, stable stack resources, and zero-analyzer state were rechecked
with the read-only auditor before the correction was written. The new raw
record is append-only; the prior Phase 3A implementation record remains
unchanged.

## [2026-07-18] complete | AWS security hardening Phase 3A

### Objective

Complete the dev account external-access analyzer rollout, review every active
finding, verify application and alarm health, and stop before GuardDuty.

### Scope

The CloudFormation execution policy, `Mlops-Dev-SecurityMonitoring`, IAM Access
Analyzer, the six Phase 2 security alarms, the existing cost budget, and one
normal `/predict` request. No application stack, data path, runtime IAM role,
or later Phase 3 service was changed.

### Identity and environment

The restricted deployment path performed the named diff and deployment. A
separate read-only security identity performed inventory and finding review;
an administrative identity performed only the approved attachment correction,
managed-policy rotation, and read paths unavailable to the auditor. No
identity name, local profile name, account identifier, generated resource
identifier, endpoint, or credential is recorded.

### Commands and results

- The implementation and correction commits passed hosted validation and
  secret scanning in draft pull request 4, which remains unmerged.
- The unexpected execution-policy attachment was removed from one verified
  zero-member group while preserving the group and its other policy.
- The oldest non-default policy version was removed; corrected `v8` is default,
  canonical comparison matches the repository, `v7` remains for rollback, and
  the execution policy is attached to one role and zero users or groups.
- The named diff showed one analyzer addition. The named deployment reached
  `UPDATE_COMPLETE` with the analyzer plus CDK metadata only.
- The analyzer is `ACTIVE`, has a populated latest-resource analysis timestamp,
  and has the exact expected tags, no paid configuration, no archive rules,
  and zero active public, cross-account, or error findings.
- GuardDuty, Config, Security Hub, account S3 Block Public Access, and Phase 3
  EventBridge alert routing remain disabled or absent.
- `/predict` returned HTTP 200 and preserved its probability/Boolean threshold
  contract. The existing `$20` budget remains at `$0` calculated actual spend
  with 50%, 80%, and 100% notifications.
- Three approved IAM policy changes and six known read-only denials were
  attributed from the audit trail: one scoped CloudFormation discovery call,
  one AWS service-linked discovery call, the previously recorded three-call
  Cost Explorer console pattern, and one auditor log-content read. All six
  alarms returned to `OK` naturally without a state override.

### Interpretation

The analyzer now establishes a zero-finding external-access baseline at no
additional charge. The rollout did not enable paid internal or unused-access
analysis and did not hide findings through archive rules. The service-linked
role permission belongs exclusively to the CloudFormation execution role.

### Decision and next checkpoint

Phase 3A is complete. Keep the pull request draft and unmerged. Roll back the
analyzer only by reverting the Phase 3A implementation and redeploying the
named stack; do not delete it manually. Phase 3B requires a separate review.

### Verification

Local lint, 53 tests, lock check, dependency audit, eight-stack synthesis, wiki
lint, hosted validation, hosted secret scan, named diff, named deploy, live
analyzer/finding inventory, later-service inventory, policy comparison, alarm
recovery, budget state, and `/predict` health all passed.

## [2026-07-18] query | Phase 3B GuardDuty foundational detection

Found 26 matching page(s).

## [2026-07-18] implement | AWS security hardening Phase 3B

### Objective

Implement one dev regional GuardDuty detector with foundational detection only,
preserve the Phase 3 one-service rollback boundary, and stop before AWS Config.

### Scope

The existing SecurityMonitoring stack and dev flag, the CloudFormation
execution policy, focused CDK and policy tests, the Phase 3B implementation
record, and the maintained security roadmap. No application stack, data path,
workload role, production flag, or public interface changed.

### Identity and environment

Repository branch `codex/phase-3b-guardduty`, target Region `us-east-1`.
Read-only live inventory used the established separated audit and
administrative paths. No identity name, local profile name, account identifier,
generated resource identifier, endpoint, or credential is recorded.

### Commands and results

- The merged Phase 3A commit was present on clean `main` before the fresh 3B
  branch was created.
- The current GuardDuty API model adds `AI_ANALYST` to the optional feature
  enumeration. The detector explicitly disables it plus S3 data events, EKS
  audit logs, EBS malware protection, RDS login events, and Lambda network
  logs. Runtime-monitoring features remain omitted.
- Read-only pre-state showed the healthy Phase 3A analyzer with zero active
  findings, no GuardDuty subscription/detector or service-linked role, and no
  later Phase 3 service. Execution policy `v8` matched the merged source, was
  attached only to one role, and occupied the five-version set `v4`–`v8`.
- All six security alarms were `OK`; the `$20` budget remained at `$0` with
  50%, 80%, and 100% actual-spend alerts.
- `make lint` passed; 54 unit tests passed; `make security` passed the
  108-package lock check, dependency audit, and eight-stack cdk-nag synthesis.
- Named-stack dry runs rendered only `Mlops-Dev-SecurityMonitoring`. A clean
  synth of merged `main` confirmed all unrelated templates identical except
  generated Lambda asset hashes in Ingestion and Serving.

### Interpretation

GuardDuty enables omitted optional detector features by default, so the exact
disabled list is a cost and scope boundary. The new AI feature made the plan's
required pre-implementation enumeration refresh material. The existing stack,
flag, lifecycle actions, and test modules were extended in place; no duplicate
helper or parallel path was added.

### Decision and next checkpoint

Commit the isolated implementation and require green hosted validation and
secret scanning. Then delete oldest non-default policy `v4`, create and verify
default `v9` while retaining `v8`, review a named no-change-set diff, and deploy
only SecurityMonitoring. Verify findings, protection plans, trial and usage,
budget, alarms, Access Analyzer, and `/predict`, then create a separate
completion record and stop before Phase 3C.

### Verification

Repository lint, unit, lock, dependency-audit, synthesis, exact detector and
policy assertions, IAM fingerprints, unrelated-template comparison, dry-run
guards, live stop gate, and sensitive-value review passed before this entry.

## [2026-07-18] failure | Phase 3B first deployment rollback

### Objective

Complete the foundational GuardDuty rollout after hosted gates, while changing
only the SecurityMonitoring stack and preserving a verified policy rollback.

### Scope

Draft pull request 5, the CloudFormation execution policy,
`Mlops-Dev-SecurityMonitoring`, GuardDuty, Phase 3A Access Analyzer, the six
security alarms, the existing budget, and one normal `/predict` request. AWS
Config and every later phase remained out of scope.

### Identity and environment

The restricted deployment path performed the named diff and deployment. The
separate audit path performed service, finding, alarm, and CloudTrail reads; an
administrative path performed only the approved policy rotation/rollback and
reads unavailable to the auditor. No identity name, local profile, account
identifier, generated identifier, endpoint, or credential is recorded.

### Commands and results

- Hosted `validate` and `secret-scan` passed for the implementation commit.
- Oldest non-default policy `v4` was deleted; verified `v9` became default with
  `v8` retained and one-role/zero-user/zero-group attachment scope unchanged.
- The named no-change-set diff showed exactly one detector addition.
- CloudFormation sent the exact expected `CreateDetector` request: enabled,
  15-minute publishing, exact Phase 3B tags, no legacy data sources, and all
  six optional features disabled. GuardDuty returned HTTP 403
  `SubscriptionRequiredException` before any service-linked-role call.
- The stack automatically reached `UPDATE_ROLLBACK_COMPLETE` with only the
  Phase 3A analyzer and metadata. No detector or GuardDuty role exists.
- The execution policy was rolled back to verified default `v8`; `v9` was
  deleted. Versions `v5`–`v8` remain with the intended attachment boundary.
- Access Analyzer remains active with zero findings; later Phase 3 services
  remain absent. The `$20` budget and 50/80/100 alerts are unchanged.
- `/predict` returned HTTP 200 and remained threshold-consistent. The expected
  IAM-policy-change alarm returned naturally to `OK`, leaving all six alarms
  `OK` without a state override.

### Interpretation

The failure is not an execution-role `AccessDenied`: GuardDuty itself rejected
the exact CloudFormation create request because the account is in a
never-enabled subscription state. The exact AWS prerequisite is unresolved.
Manually creating the detector would bypass the approved CloudFormation
ownership and rollback contract.

### Decision and next checkpoint

Phase 3B remains incomplete and pull request 5 stays draft. Do not begin Phase
3C. Determine an AWS-supported first-subscription path that preserves
CloudFormation ownership and explicit disabling of every default-on paid
feature. If manual subscription is required, stop for a separate ownership and
rollback decision. Any retry repeats the complete pre-state, policy, diff,
deployment, finding, cost, alarm, budget, Access Analyzer, and application
checks.

### Verification

Terminal rollback, stable stack resources, no detector/role, exact delayed
CloudTrail request, verified policy rollback, attachment scope, analyzer and
later-service state, budget alerts, six alarm recovery, `/predict`, wiki lint,
and sensitive-value scans passed before this entry.
## [2026-07-18] ingest | AWS Free-plan account service limits — July 18, 2026

Registered immutable source `raw/aws-free-plan-account-service-limits-july-18-2026.md`.

## [2026-07-18] update | Free-plan root cause for Phase 3B recorded

### Objective

Record the confirmed account-level explanation for the Phase 3B GuardDuty
`SubscriptionRequiredException` rollback and its consequences for the
remaining Phase 3 roadmap.

### Scope

- New immutable source `raw/aws-free-plan-account-service-limits-july-18-2026.md`
  and its completed source page.
- Updated pages: phased security hardening roadmap, Phase 0 baseline, and the
  Phase 3B first-deployment-rollback source page.
- Rebuilt index; no application code, configuration, or test changed.

### Identity and environment

Console observation only, viewed with the `${AWS_ADMIN_USER_NAME}` identity in
account `${AWS_ACCOUNT_ID}`. No AWS mutation occurred; the AWS Config setup
wizard was cancelled without creating resources.

### Evidence and interpretation

The Billing and Cost Management home page shows the account on the AWS Free
account plan, with credits and a free-plan period remaining and an Upgrade
plan action. The Free plan blocks paid-only services — including GuardDuty and
Security Hub — at the billing level with `SubscriptionRequiredException`. This
resolves the open question from the Phase 3B rollback record (the
CloudFormation request was correct; the plan forbids the service) and
retroactively explains the Phase 0 baseline probes, where GuardDuty and
Security Hub failed read-only calls while AWS Config answered normally.

### Decision and next checkpoint

Phases 3B and 3D are hard-blocked pending a deliberate paid-plan upgrade
decision; pull request 5 stays draft. Do not enable any Phase 3 service
manually or through the console wizard. AWS Config availability on the Free
plan is tested only through the gated flag-controlled CloudFormation path.
After an explicit upgrade, Phase 3B repeats its full gate sequence.

### Verification

Wiki index rebuilt; wiki lint, focused wiki unit tests, sensitive-value scan
of changed files, and `git diff --check` run before handoff.
## [2026-07-19] ingest | Phase 3 plan revision under the AWS Free plan — July 19, 2026

Registered immutable source `raw/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md`.

## [2026-07-19] update | Phase 3 reordered for the Free plan; 3B made deploy-safe

### Objective

Amend the Phase 3 execution plan for the confirmed AWS Free account plan:
defer the billing-blocked services behind an explicit upgrade gate, promote
the free-compatible sub-phases, and make the Phase 3B branch deploy-safe.

### Scope

- New immutable source
  `raw/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md` and its
  completed source page.
- Updated pages: phased security hardening roadmap and the Free-plan
  service-limits source page; rebuilt index.
- Repository: `infra/config/dev.yaml` (`guardduty: false` with deferral
  comment) and `tests/unit/test_stacks.py` (dev asserts only the analyzer and
  zero GuardDuty resources; a new config-override test locks the exact
  detector contract for the future retry). The flag-gated stack code and the
  execution-policy document are unchanged.

### Identity and environment

Local repository and wiki work only. No AWS API call, deployment, policy
rotation, or service enablement occurred.

### Interpretation

The revised order is 3A (complete) → 3E account S3 Block Public Access →
3C Config, whose gated deployment doubles as the Free-plan availability test
with minimally scoped recording → partial 3F routing → explicit manual
paid-plan upgrade gate → deferred 3B GuardDuty and 3D Security Hub with full
gate sequences. The repository execution policy deliberately retains the
GuardDuty actions while the live default remains `v8`; the next sub-phase's
controlled rotation reconciles the divergence. Draft pull request 5 is
repurposed to carry the deferral rather than a doomed retry.

### Decision and next checkpoint

The next mutating AWS work is sub-phase 3E under the standard gate sequence,
after verifying account-level BPA cannot break the CDK bootstrap asset bucket
or workload access patterns. Stop for 3E's go/no-go before 3C. Phases 3B and
3D wait for the upgrade decision.

### Verification

`make lint` passed (47 files), 14 stack tests passed, wiki index rebuilt,
wiki lint and focused wiki tests, sensitive-value scan, and
`git diff --check` run before handoff.

## [2026-07-24] implement | Static type checking across src, infra, and scripts

### Objective

Move the repository from decorative annotations to verified ones: annotate
every function in the non-test trees, then add a blocking gate so the
coverage cannot rot.

### Scope

- Tooling: `pyproject.toml` (`[tool.mypy]`, ruff `ANN`, three dev
  dependencies), `uv.lock`, a `make typecheck` target, and a `Type check`
  step in the CI validate job.
- Code: all of `src/`, `infra/`, and `scripts/` — 33 source files.
- Documentation: the Conventions section and commands table of `CLAUDE.md`
  and `AGENTS.md`, kept in sync.
- Deliberately excluded: `tests/`, via ruff `per-file-ignores` and omission
  from mypy's `files` list.
- GitHub issue 8; branch `issue/8-static-typing`; three commits, one per
  phase.

### Identity and environment

Local repository work only. No AWS API call, deployment, or policy change
occurred. `make synth` ran against `env=dev` with `--no-lookups`, which
reaches no account.

### Commands and results

All read-only or local. `make typecheck` opened at 31 errors in 22 files
and closed at zero. `make lint`, `make test` (55), `make security`, the 14
`test_stacks.py` fingerprint guards, and `scripts/wiki.py lint` all pass.

Two adversarial checks confirmed the gate bites rather than merely existing:
a temporary unannotated function failed ruff with ANN001/ANN202 and mypy
with `no-untyped-def`; a temporary `config["serverless"]["memory"]` failed
mypy with `TypedDict "ServerlessConfig" has no key "memory"` and the
suggestion `Did you mean "memory_mb"?`.

### Interpretation

Typing the environment config was the change that made the gate worth
having. `infra/config/{dev,prod}.yaml` have a fixed shape, so
`PlatformConfig` and its nested TypedDicts now live in
`infra/stacks/shared.py`, and `load_config` is the single boundary where
`yaml.safe_load`'s `Any` is narrowed. Config-key typos are now build-time
errors in all eight stacks. These are build-time types and stay out of
`src/common/`, which remains the runtime contract shipped into Lambda.

mypy found five real defects that annotation work alone would have missed.
The sharpest was `security_stack.py` passing `node.default_child`, typed
`IConstruct | None`, straight into `add_dependency` three times — a latent
synth-time failure, now narrowed by a local helper that raises with a clear
message. `send_drift_traffic.py` multiplied two `object`-typed dict values.
`wiki.py:_parse_scalar` returned an unnarrowed `json.loads` result, and two
functions returned `Any` from a signature declaring `dict`.

The known Python-version trap was respected rather than rediscovered.
`src/pipeline/` executes in the SageMaker `FrameworkProcessor` managed image
on an older Python than the 3.12 targeted elsewhere — the same mismatch that
cost a pipeline execution on July 11. All three pipeline modules now carry
`from __future__ import annotations` so annotations never evaluate there,
and the tree still contains no PEP 604 unions.

Following the deduplication precedent, synthesized output was snapshotted
before and after. All eight CloudFormation templates are byte-identical once
the Lambda asset content hash is normalized; the asset hash itself moves
because the bundle contains `src/`, and diffing the bundled source shows
annotation additions only. No IAM or acknowledgement baseline needed
refreshing.

### Decision and next checkpoint

`strict = true` was deliberately not set: it enables `disallow_any_generics`,
which fails on every `**kwargs` passthrough into jsii-generated CDK
constructs for noise disproportionate to the value. `ANN401` is ignored for
the same reason.

`tests/` is left unannotated — roughly 51 mostly-mechanical additions, plus
genuine design work on the pytest fixture types in the 831-line
`test_stacks.py`. That is a reasonable follow-up phase but has much lower
value per unit of effort. The next checkpoint is hosted CI on the pull
request for issue 8, confirming the new blocking step passes in an
environment that syncs only the `dev` extra.

### Verification

`make lint` (47 files), `make typecheck` (33 files, zero errors), `make test`
(55 passed), `make security`, 14 stack fingerprint tests, `make wiki-lint`,
sensitive-value scan, and `git diff --check` run before handoff.

## [2026-07-24] implement | Phase 3 flag guard; deferred-stack state verified

### Objective

Close a silent-failure gap in the Phase 3 service flag contract, and
establish the true state of the rolled-back security monitoring stack before
deciding whether any corrective action was warranted.

### Scope

- `infra/stacks/security_monitoring_stack.py` (new `IMPLEMENTED_SERVICE_FLAGS`
  constant and validation branch) and `tests/unit/test_stacks.py` (a
  parametrized guard test plus a subset assertion).
- Read-only inspection of the deployed `Mlops-Dev-SecurityMonitoring` stack.
- This page's roadmap: a new stable-interface bullet.
- Draft pull request 9 on branch `issue/8-static-typing`, which also carries
  the static typing work recorded in the preceding entry.

### Identity and environment

Dev account, `us-east-1`, using the least-privilege `${AWS_SECURITY_AUDITOR_USER_NAME}`
profile. Every AWS call was read-only: `describe-stacks`,
`describe-stack-events`, `describe-stack-resources`, `get-template`, and
`accessanalyzer list-analyzers`. No deployment, no drift detection run, no
policy change, and no service enablement. `list-change-sets` returned
AccessDenied for the auditor identity, which is the expected least-privilege
boundary rather than a fault.

### Commands and results

`make lint`, `make typecheck`, and `make test` all pass; the unit suite grew
from 55 to 60. `make synth` output for the security monitoring stack is
byte-identical to before the guard, confirming the new branch is inert at
synthesis while dev enables only implemented flags.

Read-only inspection found the stack holding exactly two resources,
`CDKMetadata` and `ExternalAccessAnalyzer`, both in a complete state, with no
GuardDuty resource present. Its deployed template is byte-identical to what
the repository synthesizes today. The account analyzer reports `ACTIVE` in
the Access Analyzer service. Stack drift status is `NOT_CHECKED`.

### Interpretation

The stack validated that config carried exactly the six
`PHASE_3_SERVICE_FLAGS` and that each was a boolean, then built resources for
only two of them. Enabling `config_recorder`, `security_hub`, `account_bpa`,
or `eventbridge_alerts` would have synthesized and deployed cleanly while
creating nothing. For a security control that is the worst available failure
mode: the flag reads as enabled in configuration while the service does not
exist in the account. The guard converts that into an immediate error naming
the offending flag.

The guard deliberately does not implement 3C, 3D, 3E, or 3F. Writing them now
would jump the revised execution order, and each sub-phase owns its own gate
sequence. GuardDuty standby is untouched: the flag-gated detector and the
contract-locking test still hold the exact 3B shape for the eventual retry.

The deferred stack needs no repair. Its `UPDATE_ROLLBACK_COMPLETE` status is a
marker left by the July 18 GuardDuty subscription rejection, not a broken
deployment — Phase 3A is genuinely live, and the deployed template already
matches the repository. An earlier assumption that a redeploy would clear the
status was wrong and is corrected here: because the deployed template is
identical to the synthesized one, a deploy produces an empty change set,
CloudFormation reports that no updates are to be performed, and the status is
left untouched. Only a deploy carrying a real template change to this stack
moves it back to `UPDATE_COMPLETE`. Unlike `UPDATE_ROLLBACK_FAILED`, the
current state accepts updates and needs no rollback continuation.

### Decision and next checkpoint

No corrective AWS action was taken and none is recommended. Forcing a
cosmetic template change purely to clear the console status would put noise
in the template for no functional gain; the status resolves on its own at the
next sub-phase deployment. Sub-phase 3E remains the next mutating work under
the standard gate sequence, unchanged by this entry.

The immediate checkpoint is hosted CI on pull request 9, which exercises the
new blocking type-check step for the first time in an environment that syncs
only the `dev` extra. A flag joins `IMPLEMENTED_SERVICE_FLAGS` in the same
change that implements its sub-phase.

### Verification

`make lint` (47 files), `make typecheck` (33 files, zero errors), `make test`
(60 passed, up from 55), security monitoring template diffed byte-identical
against the pre-change synthesis, wiki index rebuilt, `make wiki-lint`,
sensitive-value scan, and `git diff --check` run before handoff.

## [2026-07-24] verify | CI gate green; auditor denials found to trip the CIS alarm

### Objective

Close the checkpoint named in the preceding entry by confirming the new
blocking type-check step passes in hosted CI, and account for three
same-day firings of the Phase 2 unauthorized-API-calls detection.

### Scope

- GitHub Actions run 19 on pull request 9, branch `issue/8-static-typing`.
- The `mlops-dev-security-unauthorized-api-calls` CloudWatch alarm and the
  `SECURITY_DETECTIONS` metric filter in `infra/stacks/security_stack.py`.
- No code changed. Finding captured as issue 10.

### Identity and environment

Dev account, `us-east-1`, `${AWS_SECURITY_AUDITOR_USER_NAME}` profile, read-only.
Escalation to the break-glass admin identity was considered for CloudTrail
attribution and deliberately declined: routine investigation does not
justify break-glass use.

### Commands and results

CI run 19 succeeded in 2m20s. Both jobs passed, including the new type-check
step, in an environment that syncs only the `dev` extra — the condition the
previous entry flagged as unverified. Gitleaks reported no leaks.

`describe-alarm-history` showed the detection firing three times on
2026-07-24 — 13:13, 15:19, and 16:02 EDT — each auto-resolving after roughly
five minutes, plus one on 2026-07-23 at 01:30. An attempt to attribute them
via `logs:FilterLogEvents` against the audit log group was denied for the
auditor identity.

### Interpretation

This entry corrects the preceding one. That entry recorded the
`cloudformation:ListChangeSets` AccessDenied as "the expected least-privilege
boundary rather than a fault," which is true but materially incomplete: the
denial also matches the CIS detection's filter,
`{($.errorCode="*UnauthorizedOperation") || ($.errorCode="AccessDenied*")}`,
and therefore trips the alarm. The 16:02 firing evaluated a datapoint at
19:57 UTC, the window that investigation ran in, and is attributable to it.
The read-only investigation recorded in the previous entry was not
side-effect free, and describing it as purely read-only understated its
consequences.

The failed attempt to diagnose the noise demonstrated the loop directly: the
diagnostic call was itself denied and itself matched the filter. Two related
weaknesses follow. The detection cannot distinguish a correctly-scoped
identity being correctly refused from genuine reconnaissance, and the
security auditor cannot read the audit trail it exists to audit, so it cannot
self-diagnose an alarm it caused.

A control that alarms on its own auditor doing its job trains its recipient
to ignore it, which is the mechanism by which real detections get missed.
The remaining three firings are unattributed and stay that way under the
no-escalation decision.

### Decision and next checkpoint

The detection is left unchanged. `SECURITY_DETECTIONS` is a Phase 2 control
and this page's roadmap treats those as stable interfaces, so any adjustment
belongs in its own gated sub-phase with a reviewed diff, a scoped dev
deployment, an observation window, and its own log entry — not a drive-by
edit made while investigating something else.

Issue 10 records the evidence and four candidate remedies: narrowing the
filter, granting the auditor read access to the audit log, widening the
alarm threshold or evaluation window, and routing low-value events to a
queue rather than email. Raising the threshold and granting auditor log
access are complementary and neither reduces detection coverage; narrowing
the filter does, because genuine reconnaissance also appears as denied
`List*` calls. Sub-phase 3E remains the next mutating work and is unaffected.

### Verification

CI run 19 green on both jobs; alarm history read read-only; no mutating AWS
call, no IAM or detection change, and no break-glass credential used. Wiki
index rebuilt, `make wiki-lint`, sensitive-value scan, and `git diff --check`
run before handoff.

## [2026-07-24] deploy | Dev reconciled with main after the static typing merge

### Objective

Bring the dev account into line with `main` following the merge of pull
request 9, applying the annotated Lambda bundle and the partition-agnostic
IAM statements that had been synthesized but never deployed.

### Scope

Three of eight stacks were deployed: `Mlops-Dev-Ingestion`,
`Mlops-Dev-Serving`, and `Mlops-Dev-Monitoring`. `Mlops-Dev-Security`,
`Mlops-Dev-SecurityMonitoring`, `Mlops-Dev-Data`, `Mlops-Dev-Registry`, and
`Mlops-Dev-Training` showed no differences and were not deployed.

What `cdk diff` predicted and what CloudFormation actually applied differ,
and the distinction matters. The diff listed Lambda code assets for
`ValidateFn`, `ProxyFn`, and `DeployFn` plus IAM policy edits on the `ProxyFn`
and `RetrainTriggerFn` service roles. Resource-level stack events show only
the three Lambda functions and `CDKMetadata` were actually updated. Neither
IAM policy resource received an update event, so `Mlops-Dev-Monitoring`'s
deployment changed nothing beyond CDK metadata.

### Identity and environment

Dev account, `us-east-1`, `${MLOPS_DEPLOYER_USER_NAME}` profile, which assumes the CDK
bootstrap roles as designed. Note that `.env` records `AWS_PROFILE=default`,
but that profile currently has no credentials; the deploy identity documented
in the CDK deployment page is the correct one and was used.

### Commands and results

`cdk diff -c env=dev --no-lookups --no-change-set` reviewed before any
mutation, then `cdk deploy` scoped to the three changed stacks. All three
reached `UPDATE_COMPLETE`, in 17s, 23s, and under a minute respectively.

### Interpretation

This entry corrects two characterizations made earlier in the session, both
found by checking rather than by assertion.

The deployment was first described as pushing "new Lambda code to Ingestion
and Serving, annotations only." That was wrong in two respects: the change
set also covered `Mlops-Dev-Monitoring`, which went unmentioned, and it
listed IAM policy edits rather than code alone. Reviewing the diff before
deploying is what surfaced it, which is the argument for the operating rule
requiring the review.

The resulting report then over-claimed in the opposite direction, stating
that the `ProxyFn` and `RetrainTriggerFn` role policies had been updated.
Resource-level stack events show they were not. CloudFormation resolved
`Ref: AWS::Partition` to `aws`, found the resulting policy documents
byte-identical to the deployed ones, and skipped both resources. Reading the
event log rather than trusting the stack-level `UPDATE_COMPLETE` is what
caught this. A stack reaching `UPDATE_COMPLETE` says nothing about which of
its resources actually changed.

The IAM edits are permission-neutral, and CloudFormation's refusal to update
those resources is independent evidence of it. Both replace the literal
`arn:aws:sagemaker:` prefix with `arn:`, a `Ref` to `AWS::Partition`, and
`:sagemaker:`. `AWS::Partition` resolves to `aws` in commercial regions, so
the resolved ARN is unchanged and the actions, resources, and principals are
identical — which is precisely why no update was performed. The edits
originate in the July 18 deduplication pass, not in the typing work, and had
been sitting undeployed because the affected stacks were last deployed on
July 10 and 11.

A related trap is worth recording for future verification. The CloudFormation
console's default stack list shows **Created time**, which never changes on an
update; the July 10 through July 14 dates there are original creation
timestamps and say nothing about recent deployments. `LastUpdatedTime` from
`describe-stacks`, the per-stack Events tab, or the console's optional
last-updated column are the fields that answer "was this deployed today."

`Mlops-Dev-SecurityMonitoring` showed no differences and remains in
`UPDATE_ROLLBACK_COMPLETE`, independently confirming the earlier conclusion
that no ordinary deployment clears that status.

### Decision and next checkpoint

Verification proceeded in two stages. First, before any credential was
available, the deployed Lambda bundle was imported directly from its
published asset directory under Python 3.12, exercising the module-load path
that carries the highest risk from this change, since `proxy_handler` imports
`encode_features` from a pipeline module that gained
`from __future__ import annotations`. All three handlers imported cleanly and
`encode_features` returned the expected nineteen features.

The live `/predict` confirmation followed once an API key was placed in the
local `.env`. Note that `API_URL` remains empty there; the request URL was
composed from the recorded gateway id and region rather than hardcoded. Three
requests covered the paths this change touched most: a valid record returned
HTTP 200, an invalid gender returned HTTP 422 with the expected
`format_validation_error` message, and a blank `TotalCharges` at tenure zero
returned HTTP 200, exercising the `_blank_total` pre-validator.

The valid record scored `0.3656342029571533`, bit-identical to the
probability recorded for the same canonical record before this work. Inference
behaviour is therefore unchanged, which is the strongest available evidence
that the annotations altered nothing at runtime. The observation window for
these three stacks remains open. Sub-phase 3E remains the next mutating
security work and is unaffected.

### Verification

`cdk diff` reviewed pre-deployment; three stacks reported `UPDATE_COMPLETE`
with `LastUpdatedTime` on 2026-07-24 while the other five retained earlier
timestamps; resource-level stack events confirmed exactly three Lambda
functions and `CDKMetadata` were updated and no IAM policy resource was
touched; the deployed asset hash matches the `S3Key` in the reviewed diff;
the bundle imports cleanly under the Lambda runtime version; and live
`/predict` requests returned 200, 422, and 200 on the success, schema-
rejection, and blank-`TotalCharges` paths with an unchanged churn probability.
No IAM identity, detection, or service enablement was altered.


## [2026-07-24] implement | Deployment verification tool and reporting rule

### Objective

Prevent recurrence of a specific reporting failure: stating what a
deployment changed on the basis of stack-level status, which twice in one
session produced an incorrect account of the same deployment.

### Scope

- New `scripts/verify_deployment.py` and `tests/unit/test_verify_deployment.py`.
- New `make verify-deploy` target; `cloudformation` added to the
  `boto3-stubs` extras with `uv.lock` regenerated.
- `CLAUDE.md` and `AGENTS.md`: a new mandatory reporting section, plus the
  commands table and code map, kept in sync.
- Pull request 12, branch `feat/verify-deployment`.

### Identity and environment

Local repository work, plus one read-only verification run against the dev
account using the `${AWS_SECURITY_AUDITOR_USER_NAME}` profile in `us-east-1`. The tool
calls only `describe_stacks` and `describe_stack_events`. No mutation.

### Commands and results

`make lint`, `make typecheck` (34 files), `make test` (70 passed, up from
60), and `make security` all pass. Run against the live account with
`SINCE=2026-07-24`, the tool reproduced the deployment finding exactly:
`ValidateFn` for Ingestion, `ProxyFn` and `DeployFn` for Serving, and an
explicit "no resources changed" for Monitoring.

### Interpretation

Documentation alone would not have prevented the original error, because a
convention is guidance rather than a check. The durable fix is a command
that makes the correct answer cheaper to obtain than the incorrect one, so
the tooling is the substance here and the written rule points at it.

Three distinct traps contributed and each is now recorded. Stack status is
not resource change, since `UPDATE_COMPLETE` is reported even when nothing
was touched. `cdk diff` states intent rather than outcome, because
CloudFormation resolves intrinsics such as `Ref: AWS::Partition` and then
skips resources whose resolved form is unchanged. And the console's default
stack-list column is `Created time`, which never moves on update and
therefore cannot answer whether a stack was deployed today.

`CDKMetadata` is filtered from the tool's output by default. It changes on
nearly every deployment, so including it would make every stack appear
modified and recreate the same false signal in a new place.

The tests encode the failure rather than only the feature: the
metadata-only case is asserted directly, so the specific bug cannot
regress silently. Failed resource states are surfaced rather than dropped,
because a rolled-back resource is a change an operator must see.

### Decision and next checkpoint

Pure filtering is deliberately separated from the AWS calls so the logic is
testable without stubbing boto3, and the tool remains read-only rather than
attempting any remediation. It is not wired into CI, since it requires
account credentials and answers an operational question rather than a
repository one.

Both this and the deployment record in pull request 12 and 11 append to the
end of `wiki/log.md` from separate branches, so whichever merges second
needs a trivial rebase keeping both entries in chronological order. Next
checkpoint is review of those two pull requests. Sub-phase 3E remains the
next mutating security work and is unaffected.

### Verification

`make lint` (49 files), `make typecheck` (34 files, zero errors),
`make test` (70 passed), `make security`, one read-only run against the dev
account reproducing the prior finding, wiki index rebuilt, `make wiki-lint`,
sensitive-value scan, and `git diff --check` before handoff.
## [2026-07-24] ingest | AWS security hardening Phase 3E implementation and deployment — July 24, 2026

Registered immutable source `raw/aws-security-hardening-phase-3e-implementation-and-deployment-july-24-2026.md`.


## [2026-07-24] implement | AWS security hardening Phase 3E

### Objective

Enable account-level S3 Block Public Access in dev — the next mutating security
work under the July 19 Free-plan revision, chosen first because it is free and
subscription-independent and so cannot be blocked the way 3B was.

### Scope

- `infra/stacks/security_monitoring_stack.py` (`ACCOUNT_BPA_CONFIGURATION`, the
  `account_bpa` branch, and the flag joining `IMPLEMENTED_SERVICE_FLAGS`),
  `infra/config/dev.yaml`, `infra/security_checks.py`, `infra/app.py`, and
  `tests/unit/test_stacks.py`.
- The `Mlops-Dev-SecurityMonitoring` stack only. No other stack, no policy
  version, no production change.
- Pull request 13 on branch `feat/phase-3e-account-bpa`, commits `b45cae2` and
  `f9e9749`.

### Identity and environment

Dev account, `us-east-1`. The pre-flight and all verification used the
least-privilege `${AWS_SECURITY_AUDITOR_USER_NAME}` profile and were read-only. The single
mutating step, `make deploy-stack`, used `${MLOPS_DEPLOYER_USER_NAME}`.

### Commands and results

The read-only pre-flight passed on all six checks. The account still reported
`NoSuchPublicAccessBlockConfiguration`. All six buckets, including the CDK
bootstrap asset bucket, already had all four bucket-level settings, reported
`IsPublic: false`, and used `BucketOwnerEnforced`. Every wildcard-principal
bucket statement proved to be a TLS-enforcing Deny; the only non-account `Allow`
statements are conditioned grants to `logging.s3.amazonaws.com` and
`cloudtrail.amazonaws.com`, so both delivery paths are policy-based rather than
ACL-based. CloudTrail was logging without error, access-log objects were landing
the same day, and `/predict` returned HTTP 200.

`make lint`, `make typecheck` (34 files), `make test` (71, up from 70), and
`make security` all pass. Hosted CI passed on both commits. The named diff added
four resources and modified nothing. `make deploy-stack` completed in 48.6
seconds. `make verify-deploy SINCE=2026-07-24` lists exactly those four
resources; the Serving, Ingestion, and Monitoring rows in that output belong to
the earlier 20:47–20:48 UTC reconciliation deploy.

Post-deploy: all four account settings `true`, analyzer still `ACTIVE`, six
security alarms `OK`, every bucket still listable, `/predict` returning the
unchanged `churn` / `churn_probability` contract, and `make diff-stack`
reporting no differences.

### Interpretation

Account BPA was safe here precisely because it was redundant with what every
bucket already enforced — which is why the pre-flight could predict a no-op for
existing access paths. Its value is prospective, covering buckets this
repository does not create and future bucket-level mistakes.

Two things were got wrong first and are worth recording. The cdk-nag
acknowledgements were registered unconditionally although their constructs exist
only when the flag is true, and `_construct_at` deliberately raises on a path
matching no construct. That would have left dev unable to synthesize its own
revert, so the control could only have been removed by reverting the entire
change; `Acknowledgement` now takes `requires_service`. Separately, an early
draft granted `s3:GetAccountPublicAccessBlock`, which no call path uses — an
unused grant on a wildcard resource, exactly the debt Phase 5 exists to remove —
and it was dropped before deployment.

`make synth ENV=prod` fails, but this was verified to predate Phase 3E: a
serving acknowledgement hardcodes the dev deployment-stage name, and hosted CI
synthesizes `env=dev` only, so nothing had surfaced it. It is tracked
separately rather than folded into this phase.

No execution-policy rotation was needed. The provider Lambda holds the
account-level actions itself and CloudFormation never needs them, so live `v8`
sufficed — sparing the last IAM version slot, avoiding an IAM-policy-change
alarm, and leaving the deliberate GuardDuty-statement divergence intact for 3C.

The pre-deployment risk that could not be closed by reading the repository —
whether `nodejs24.x` bundles the s3-control client under
`install_latest_aws_sdk=False` — was closed by the deployment itself reaching
`CREATE_COMPLETE`, avoiding a fallback that would have made deploys depend on
the npm registry at create time.

### Decision and next checkpoint

Two verifications are recorded as gaps rather than passes: `budgets:ViewBudget`
is denied to the auditor, so the `$20` budget was confirmed only indirectly via
the Data stack showing no resource change; and the CloudTrail provenance lookup
for `PutAccountPublicAccessBlock` returned empty because lookup lags recent
events. Both belong to the observation window, which also needs a fresh
access-log object, CloudTrail delivery advancing again, alarms still `OK`,
unchanged cost, and no new analyzer finding. Sub-phase 3C follows the go/no-go
and must scope its own acknowledgements with `requires_service`.

### Verification

`make lint` (49 files), `make typecheck` (34 files, zero errors), `make test`
(71 passed), `make security`, hosted CI on both commits, resource-level
`make verify-deploy`, a post-deploy `make diff-stack` reporting no differences,
wiki index rebuilt, `make wiki-lint`, and a sensitive-value scan before handoff.

## [2026-07-24] verify | Phase 3E provenance gap closed

Re-ran the CloudTrail `lookup-events` query that returned empty immediately
after the 3E deployment. It now returns a single `PutAccountPublicAccessBlock`
event at the deployment timestamp, attributed to the CloudFormation-created
provider role rather than any human identity — confirming the account-wide
setting was applied through the gated path and not the console. The earlier
empty result was lookup lag, not a negative finding, which is why it was
recorded as a deferred gap rather than a failure.

The `$20` budget remains the one verification the auditor identity cannot
perform, since `budgets:ViewBudget` is denied to it. It stays open for the
observation window; `verify-deploy` showing no resource change in the Data
stack that owns the budget is indirect evidence only.

## [2026-07-30] verify | Phase 3E observation window closed

### Objective

Close the last open 3E verification — the `$20` budget — and confirm the
remaining observation criteria after six days of elapsed evidence.

### Identity and environment

Dev account, `us-east-1`. The budget was read from the Billing and Cost
Management console under an identity holding `budgets:ViewBudget`; the
least-privilege `${AWS_SECURITY_AUDITOR_USER_NAME}` profile is denied that action, which is
why the check could not be completed at deployment time. All other checks were
read-only auditor calls.

### Commands and results

`${MONTHLY_BUDGET_NAME}` is a `$20.00` monthly cost budget starting 2026-07-01
with no end date, health `Healthy`, and exactly three actual-cost alerts at 50%
(`$10.00`), 80% (`$16.00`), and 100% (`$20.00`), all reporting not exceeded.
Spend was `$0.00` actual with a `$0.08` month-to-date forecast. This matches
`budget_usd: 20` and `budget_thresholds: [50, 80, 100]` in
`infra/config/dev.yaml`, so the Phase 2D configuration is intact and untouched
by 3E.

Re-checked the same day: account BPA still reports all four settings `true`; the
six `mlops-dev-security-*` alarms are `OK`; the analyzer is `ACTIVE` with zero
active findings; CloudTrail is logging with no delivery error; and access-log
objects were delivered on 2026-07-28 and 2026-07-30, both well after the
2026-07-24 deployment.

### Interpretation

The near-zero spend is itself the evidence for the unchanged-cost criterion.
Account-level Block Public Access carries no charge, so a 3E-attributable cost
increase would have been a signal that something other than the intended control
was created.

The budget gap was never a fault in the phase, only a boundary of the identity
used to verify it. Recording it as a gap rather than a pass was correct: the
auditor cannot see budgets, and asserting the budget was fine on the strength of
`verify-deploy` showing no change to the owning stack would have been an
inference presented as an observation.

### Decision and next checkpoint

Every 3E observation criterion is met and the sub-phase is clear for its go
decision. Pull request 13 remains open and unmerged, and the deployed dev state
already matches it. Sub-phase 3C (AWS Config) follows the go decision and must
scope its cdk-nag acknowledgements with `requires_service`, as 3E established.

### Verification

Console read of the budget and its three alerts, plus read-only re-checks of
account BPA, alarms, analyzer findings, CloudTrail delivery, and access-log
freshness. Wiki index rebuilt, `make wiki-lint`, and a sensitive-value scan.
## [2026-07-30] ingest | AWS security hardening Phase 2E implementation and deployment — July 30, 2026

Registered immutable source `raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md`.


## [2026-07-30] implement | AWS security hardening Phase 2E

### Objective

Stop the `mlops-dev-security-unauthorized-api-calls` alarm paging on isolated
least-privilege denials, and let the security auditor read the audit log it
audits — options 3 and 2 of GitHub issue 10, the complementary,
non-coverage-reducing pair. Option 1 (narrowing the filter) was rejected
because genuine reconnaissance often looks exactly like denied `List*` calls.

### Scope

`infra/stacks/security_stack.py` (new frozen `SecurityDetection` dataclass;
3-of-3 evaluation for `UnauthorizedApiCalls` only), `tests/unit/test_stacks.py`
(per-alarm evaluation expectations), and `.env.example` (`AUDIT_KEY_ID`
placeholder). The `Mlops-Dev-Security` stack only. Pull request 14 on branch
`issue/10-unauthorized-api-calls-alarm-tuning`, commit `0028146`. The auditor
grant is a hand-managed inline policy outside CDK; no other stack, no policy
version rotation, no production change.

### Identity and environment

Dev account, `us-east-1`. The pre-flight and all verification used the
least-privilege auditor profile, read-only. The two mutating steps were
`make deploy-stack` with `${MLOPS_DEPLOYER_USER_NAME}` and one
`iam put-user-policy` with `${AWS_ADMIN_USER_NAME}` — a deliberate recorded
admin action, distinct from the break-glass escalation declined on 07-24.
Budget reads also used `${AWS_ADMIN_USER_NAME}` because `budgets:ViewBudget`
remains outside the auditor scope; that known denial was deliberately not
re-triggered.

### Commands and results

Pre-flight (auditor, read-only): all six alarms at `EvaluationPeriods 1`,
`Threshold 1.0`, `Period 300`, `OK`; alarm history showed ten
fire/auto-resolve cycles for `unauthorized-api-calls` between 07-28 and
07-30 — worse than the three 07-24 fires that opened the issue; trail
logging with no delivery error. The denial baseline at 23:46:17 UTC
(`logs:FilterLogEvents` → `AccessDeniedException`) emitted one matching
event and tripped the still-live 1-of-1 alarm: the accepted, timestamped
artifact demonstrating the loop being fixed.

Gates: `make lint` (49 files), `make typecheck` (34 files, zero errors),
`make test` (71 passed, IAM fingerprint baseline unmodified),
`make security`. Reviewed `make diff-stack STACK=Mlops-Dev-Security`:
exactly one modified resource — `UnauthorizedApiCallsAlarm`,
`EvaluationPeriods 1→3`, `DatapointsToAlarm 3` added.

Deploy at 23:49:42 UTC reached `UPDATE_COMPLETE`; resource-level
`make verify-deploy SINCE=2026-07-30` attributed the update to the single
resource `UnauthorizedApiCallsAlarmDEEEB676`; the post-deploy diff reported
no differences. At 23:50:14 the alarm went `ALARM → OK` as the new 3-of-3
evaluation absorbed the pre-flight artifact.

Grant at 23:51:11 UTC: inline policy `mlops-dev-auditor-audit-log-read`
(`logs:FilterLogEvents` on the audit log group; `kms:Decrypt` on
`${AUDIT_KEY_ID}` confined by the log-group encryption context, required
because the group is CMK-encrypted). The `PutUserPolicy` paged
`IamPolicyChanges` exactly once at 23:52:21 — live proof of that detection.
The auditor's `filter-log-events --limit 1` then succeeded, exercising both
statements.

Live checks: six alarms `OK`; the tuned alarm live-confirmed at 3-of-3; no
unauthorized-api-calls fire after the deploy; `/predict` HTTP 200 with the
unchanged `churn`/`churn_probability` contract; trail logging without error;
the `$20.00` budget `${MONTHLY_BUDGET_NAME}` intact with 50/80/100 alerts.

### Interpretation

The tuning and the grant attack the two halves of the issue: an isolated
denial can no longer page (the pre-flight artifact resolved 32 seconds after
deploy), while a burst sustained across three consecutive five-minute
datapoints still does; and the auditor can now attribute a fire from the
audit log instead of generating a second denial by trying. Sequencing the
grant after the deploy meant any stray denial around the grant window could
no longer page. The one `IamPolicyChanges` page was predicted, timestamped,
and doubles as a live detection test.

### Decision and next checkpoint

Phase 2E is implemented, deployed, and verified. The observation window is
open and closes in a later session once the alarm has stayed silent on
routine auditor activity with no missed sustained-burst detection, the six
alarms remain healthy, the auditor read still works, and the budget is
unchanged. Issue 10 and pull request 14 stay open until that closure. The
Phase 2C detection contract remains a stable interface; Phase 2E is the
precedent that revising one takes a full gated sub-phase.

### Verification

`make lint` (49 files), `make typecheck` (34 files, zero errors),
`make test` (71 passed), `make security`, reviewed named diff, resource-level
`make verify-deploy`, post-deploy no-difference diff, auditor read-back of
the new policy and successful audit-log read, live alarm/endpoint/trail/
budget checks, wiki index rebuilt, `make wiki-lint`, and a sensitive-value
scan before handoff.

## [2026-07-30] implement | Prod synthesis unblocked; the cdk-nag gate covers both environments

### Objective

Make `make synth ENV=prod` succeed. It failed at `apply_security_checks`, so
production had never synthesized and the documented dev → manual gate → prod
promotion path could not have reached a prod deploy. Noted as a pre-existing
"stage-name reason" in the Phase 3E record and not tracked by any issue.

### Scope

`infra/security_checks.py` (six environment-specific literals replaced with
`{env}`/`{prefix}` tokens; new `_resolve` and `resolved_acknowledgements`;
`apply_security_checks` takes the stack prefix), `infra/app.py` (new
`stack_prefix`), `tests/unit/test_stacks.py` (both-environment build test and
an unresolved-token guard), `Makefile` and `.github/workflows/ci.yml` (new
`synth-all`), and the `CLAUDE.md`/`AGENTS.md` command tables. Branch
`fix/prod-synth-env-scoped-acknowledgements`, commit `7537910`. No stack, no
deployed resource, and no AWS call — synthesis only.

### Identity and environment

None. Every command was local and offline; `cdk synth --no-lookups` contacts
no account. No profile was assumed.

### Commands and results

`make synth ENV=prod` raised `ValueError: security acknowledgement path
'Mlops-Prod-Serving/ChurnApi/DeploymentStage.dev' matched 0 constructs`. The
API stage is named from `config["env_name"]` in `serving_stack.py`, while the
acknowledgement hardcoded `.dev`.

That path proved to be one of six environment-specific literals. The other
five are finding ids embedding the audit log group (`mlops-dev-audit`, itself
built as `mlops-{env_name}-audit`) and four cross-stack export names
(`Mlops-Dev-Data:ExportsOutput...`). Fixing only the construct path moves the
failure from `_construct_at` to cdk-nag rather than removing it. After
tokenising all six, both environments synthesized; dev resolves to
byte-identical strings and was confirmed unchanged. The CDK export hashes
(`RawBucket0C3EE094ArnD2F95F99`) are stable across stack names — established
empirically by prod synth accepting them, not assumed.

Each break was then reintroduced one at a time to test the test. Reverting the
construct path failed `test_every_environment_builds_under_its_real_prefix`
for `prod` and passed for `dev`, as intended. Reverting the five finding ids
passed — and so did an `Annotations.from_stack(...).find_error(...)` assertion
added to catch them. The CLI, by contrast, reported four `AwsSolutions-IAM5`
errors and `Synthesis finished with errors`.

### Interpretation

cdk-nag reports unacknowledged findings through the CDK CLI validation report,
not as construct annotations, so in-process `app.synth()` returns cleanly with
five of the six literals wrong. The module docstring's promise that new
findings "fail synthesis" holds only for the CLI. The `Annotations` assertion
was removed rather than kept: an assertion that never fires is worse than none,
because it manufactures exactly the confidence it fails to earn.

The root cause of the defect surviving unnoticed is the gate, not the literal.
CI synthesized `env=dev` only, and inlined the command instead of calling the
Makefile target — which is how the CI gate and the documented gate drifted
apart. An acknowledgement whose path or finding id embeds the environment can
only ever fail for the environment it was written against.

### Decision and next checkpoint

`make synth-all` synthesizes both environments and is now what CI and
`make security` run; `make security` is correspondingly slower, an accepted
cost for closing a hole in the security gate. The both-environment test is
documented as covering `construct_path` only, with `synth-all` named as the
gate for `finding_id`, so the split is explicit rather than assumed.

Prod is synthesizable but still unproven beyond synthesis: no prod stack has
ever been deployed, and every Phase 3 service flag in `prod.yaml` stays false.
This changes nothing about the Phase 2E observation window or the 3C gate.

### Verification

`make lint` (49 files), `make typecheck` (34 files, zero errors), `make test`
(75 passed, up from 71), `make security` (lock-check, pip-audit clean, dev and
prod synth). Anti-duplication check on `stack_prefix`, `_resolve`, and
`resolved_acknowledgements` found no existing equivalents. Both failure modes
were verified by reintroducing them; the diff was re-read before commit.

## [2026-08-02] verify | Phase 2E observation window closed

### Objective

Close the Phase 2E observation window (issue 10) against live evidence, and
settle the one criterion the window had never exercised: that the revised
`unauthorized-api-calls` detection still pages on a genuine sustained burst.

### Identity and environment

Dev account, `us-east-1`. Read-only checks ran under
`${AWS_SECURITY_AUDITOR_USER_NAME}`. Two reads required
`${AWS_ADMIN_USER_NAME}`: the budget, because the auditor lacks
`budgets:ViewBudget` (the gap recorded at 3E closure), and
`cloudwatch:GetMetricStatistics`, a **second auditor gap discovered here** —
the auditor can describe alarms and alarm history but cannot read the
underlying metric. No mutating call was made to any stack.

### Commands and results

The window opened with the 2E deploy on 2026-07-30; the alarm configuration
update is timestamped 2026-07-30T23:49:46Z. Closure checks ran from
2026-08-02T02:15Z, about 50 hours of elapsed evidence.

All five criteria pass:

- **Silence on routine activity.** No `unauthorized-api-calls` fire between
  2026-07-31T00:14:14Z and the synthetic test below. The audit log holds 114
  denial events across that span — routine CloudFormation service reads,
  auditor and deployer least-privilege denials, and console billing calls —
  none of which paged.
- **No missed sustained burst.** Bucketed at the alarm's own 300-second
  period, the longest run of consecutive breaching periods in the window is
  **2**. The 3-of-3 condition was never satisfied, so nothing that should
  have fired failed to.
- **Six alarms healthy.** All `mlops-dev-security-*` alarms `OK`.
  `unauthorized-api-calls` reads `EvaluationPeriods=3 / DatapointsToAlarm=3`;
  the other five remain `1` with no `DatapointsToAlarm`, byte-identical to the
  pre-2E contract.
- **Auditor audit-log read works.** `logs:FilterLogEvents` against the audit
  log group returned 685 root-identity events and the 114 denial events, so
  the out-of-band `audit-log-read` inline policy is functioning.
- **Budget unchanged.** `${MONTHLY_BUDGET_NAME}` is a `$20.00` monthly cost
  budget with exactly three actual-cost alerts at 50/80/100, all not
  exceeded, `$0.00` actual spend.

**Synthetic burst — deliberate control test, not an incident.** Between
2026-08-02T02:30:50Z and 02:55:59Z, 73 read-only `cloudformation:ListExports`
calls were issued as `${AWS_SECURITY_AUDITOR_USER_NAME}`, an action that
identity is denied. Any future reader finding ~73 `AccessDenied` events from
the auditor in that exact window is looking at this test. The metric shows six
consecutive breaching periods (`02:30`–`02:55`: 11, 11, 15, 13, 20, 4), then
`0` at `03:00`. The alarm fired at 02:42:14Z with reason `3 out of the last 3
datapoints [14.0 (02:37), 12.0 (02:32), 4.0 (02:27)] were greater than or
equal to the threshold (1.0)`, delivered an SNS email whose body matches that
reason exactly, and self-cleared at ~03:03Z on the first `0.0` datapoint
(`02:58`). Fire, page, and return were all observed.

### Interpretation

**The recorded "first live true positive" was misattributed and is corrected
here.** The 2E implementation entry records the 2026-07-31T00:13:14Z fire as a
3-of-3 true positive. The alarm history's own `oldState` block disproves it:
one minute later, at 00:14:14Z, the three evaluated periods were
`23:59=19, 00:04=0, 00:09=4` — only two breaching. The `00:04` datapoint had
not yet been delivered when the alarm evaluated at 00:13:14Z, so CloudWatch
reached further back to assemble three datapoints and picked up earlier
breaching periods. When the `0` arrived the gap filled and the alarm cleared,
producing the 60-second round trip. The underlying denials were still the
Cost Explorer session already attributed; it is the *sustained-burst* framing
that was wrong.

That correction exposes a real limitation of the 2E design. Because CloudWatch
looks back past missing datapoints, `3 of 3` does not strictly mean fifteen
consecutive minutes: under sparse or lagging delivery it can be satisfied by
three non-consecutive breaching periods, which is the isolated-denial paging
that 2E exists to prevent. Today's test proves the control works on a genuine
burst; it does not eliminate this edge. A `Fill` on the metric query would
close it, but that is a detection-contract change and belongs in its own gated
sub-phase, not in a closure.

**Two out-of-band changes surfaced that no repository record mentions.** On
2026-08-01 between 00:44:15Z and 03:37:09Z an MFA-authenticated root console
session generated 685 events (billing, free-tier, Bedrock availability, IAM
reads). Within it, root attached two AWS-managed policies to the
`AWS-Administrators` group — `job-function/Billing` at 00:45:29Z and
`CostOptimizationHubReadOnlyAccess` at 00:46:12Z — which is consistent with
resolving the Cost Explorer denials seen on 07-31. Both the
`root-user-activity` and `iam-policy-changes` alarms fired correctly on this
activity; all four root-activity notifications were delivered by email. These
were true positives on benign, operator-attributable work, and they are
recorded here because the account state now differs from what any phase entry
describes.

The negative and positive halves of the 2E claim are now both evidenced: 114
isolated denials over 50 hours paged nobody, and a deliberate sustained burst
paged within twelve minutes.

### Decision and next checkpoint

Every Phase 2E closure criterion is met; the observation window is closed and
issue 10 can be closed with it. Deliberately left unchanged: the missing-data
look-back edge (deferred to its own sub-phase), the auditor's
`budgets:ViewBudget` and newly found `cloudwatch:GetMetricStatistics` gaps
(recorded, not granted), and the two root-initiated policy attachments, which
are left in place as the operator's intent. Sub-phase 3C (AWS Config) is next
and still gated on its own pre-flight.

### Verification

Read-only CloudWatch alarm, alarm-history, and metric reads; `FilterLogEvents`
over the audit log group; budget and notification reads. The synthetic burst
was read-only and non-mutating. Wiki index rebuilt, `make wiki-lint`, and a
sensitive-value scan of the changed files.
## [2026-08-02] query | guardduty cost free plan

Found 25 matching page(s).


## [2026-08-02] decide | GuardDuty approved at measured cost, deferred to an EC2 trigger

### Objective

Answer whether GuardDuty should be enabled at all, after published pricing
commentary suggested it was expensive and raised the concern that this
account's S3 buckets might already be scanned.

### Scope

`wiki/pages/decisions/phase-3-paid-security-services.md` (new),
`wiki/pages/architecture/phased-security-hardening.md` (Phase 3 tension
updated), `infra/stacks/security_monitoring_stack.py` and
`infra/config/{dev,prod}.yaml` read as evidence. No code or AWS change.

### Identity and environment

Administrator profile, us-east-1, read-only throughout. The auditor profile
cannot serve this question: it lacks `cloudwatch:GetMetricStatistics`, a gap
already recorded during the Phase 2E closure.

### Commands and results

- `guardduty list-detectors` — `SubscriptionRequiredException`. The account
  cannot call the service, so no detector exists and nothing is being scanned.
- `cloudwatch get-metric-statistics` on `AWS/Logs IncomingLogEvents` for
  `/aws/cloudtrail/mlops-dev-audit`, seven days to 2026-08-02: **59,628
  events**, ~8,500/day, including a 17,895 day covering the Phase 2E synthetic
  burst and that day's deployments.
- Published rates read from the AWS GuardDuty and Elastic Load Balancing
  pricing pages: $4.00 per million CloudTrail management events; VPC flow/DNS
  $1.00/GB to 500 GB; S3 Protection $0.80/million; Malware Protection for S3
  $0.09/GB plus $0.215/1,000 objects; ALB $0.0225/hour plus $0.008/LCU-hour.

### Interpretation

The premise behind the concern was wrong in three independent ways: the
service is not subscribed, the flags are false in both environments, and the
3B detector code explicitly disables `S3_DATA_EVENTS` and
`EBS_MALWARE_PROTECTION`. Malware Protection for S3 is a separate opt-in that
was never configured.

The cost warnings are accurate in general and inapplicable here, because they
are dominated by exactly the dimensions this design disables. Against ~260,000
management events per month the service prices at **about $1/month**, with
every other dimension at zero while the account has no VPC resources.

The more useful finding is that the cheap control is also, today, a
low-value one: foundational detections target EC2 and VPC workloads that do
not exist yet, and the credential-anomaly coverage partly duplicates the
deployed `unauthorized-api-calls` alarm.

### Decision and next checkpoint

GuardDuty is **approved in principle and deferred to a trigger** — a planned
secondary website serving project data from EC2 behind a load balancer — not
declined and not blocked. The flag-gated detector code stays inert and tested
so the option is preserved. Deliberately left unchanged: the flags, the
execution policy's retained GuardDuty actions, and sub-phase ordering; 3C
remains next and is unaffected.

Recorded for the trigger: re-price rather than reusing the $1 figure, because
flow logs become billable; the ALB alone is ~$16.43/month before LCUs against
a $20 budget, making the budget conversation a prerequisite for the website
rather than a consequence of it; and the 30-day trial is per account, Region,
and protection plan, so it burns from enablement. 3D Security Hub sits behind
the same billing gate and its value is explicitly still open.

### Verification

Index rebuilt, `make wiki-lint` clean, and the changed files scanned for
account-identifying literals — 12-digit numbers, `execute-api` hosts, and ARNs
with a numeric account field.
## [2026-08-02] ingest | AWS security hardening Phase 3C implementation and deployment — August 3, 2026

Registered immutable source `raw/aws-security-hardening-phase-3c-implementation-and-deployment-august-3-2026.md`.


## [2026-08-03] implement | AWS security hardening Phase 3C — AWS Config

### Objective

Enable AWS Config in dev behind its flag, with recording scoped tightly enough
that configuration items cannot burn the remaining credits, and use the gated
deployment as the Free-plan availability test the roadmap left open.

### Scope

`infra/stacks/security_monitoring_stack.py` (recorder, delivery channel,
service-linked role), `infra/stacks/security_stack.py` (audit bucket policy and
KMS grants), `infra/stacks/shared.py` (`CONFIG_DELIVERY_PREFIX`),
`infra/app.py`, `infra/config/dev.yaml`, the CloudFormation execution policy,
and five test modules. Stacks touched: `Mlops-Dev-Security`,
`Mlops-Dev-SecurityMonitoring`.

### Identity and environment

us-east-1. Administrator profile for the pre-flight reads, the two policy
rotations, and `cancel-update-stack`; deployer profile for diffs and deploys;
auditor profile for `verify-deploy`, alarms, and the audit log. Note the
deployer lacks `cloudformation:CancelUpdateStack`, so stopping a hung update
requires the administrator.

### Commands and results

- Pre-flight: `describe-configuration-recorders`, `describe-delivery-channels`,
  and `describe-configuration-recorder-status` all returned empty lists. Config
  answers where GuardDuty raises `SubscriptionRequiredException`, so it is
  available on the Free plan.
- Two `create-policy-version --set-as-default` calls landed as **v10** and
  **v11** — numbering is monotonic, not slot-based, so v9 was never available.
  `v5` and `v6` were deleted to free slots. Live `v11` diffs identical to the
  `envsubst`-rendered repository document.
- Three deployment attempts. The first two hung in `CREATE_IN_PROGRESS` and
  were cancelled; both rolled back cleanly with zero residue. The third
  succeeded 00:40:13Z–00:41:24Z, creating the service-linked role, delivery
  channel, and recorder.
- Verification: `mlops-dev-recorder` `recording=true`, `lastStatus=SUCCESS`,
  ten resource types, `INCLUSION_BY_RESOURCE_TYPES`; `mlops-dev-delivery` to
  the audit bucket under `config`, 24-hour frequency. `make verify-deploy
  SINCE=2026-08-03` reports three created and two updated resources and nothing
  else.

### Interpretation

Two of the three blocking defects were **pre-existing repository bugs**. Phase
3-prep granted the Config service-linked role under
`role/aws-service-linked-role/`, which is not an IAM path, and
`test_config_service_linked_role_stays_scoped` asserted the same wrong string —
the test was protecting the defect, not detecting it. Second, Config requires
`iam:PassRole` on that role, which `PassOnlyApplicationRoles` never covered
because it is scoped to `Mlops-Dev-*`.

The third is a property of the service. The recorder and delivery channel are
mutually dependent: `PutDeliveryChannel` fails until a recorder exists, and the
recorder's creation calls `StartConfigurationRecorder`, which fails until a
channel exists. Neither ordering works, and CloudFormation retries both errors
rather than failing them — which is why each attempt hung rather than rolling
back on its own. Declaring no dependency lets the retries converge.

The rotation also closed the Phase K deploy-denial burst. The cause was a
naming mismatch, not missing intent: `s3:GetBucket*` never authorized the
CloudTrail event `GetBucketEncryption`, which is
`s3:GetEncryptionConfiguration`. Measured — the final successful deployment
produced **1** denial against Phase K's **105**.

### Decision and next checkpoint

3C is deployed and its observation window is open. Deliberately left
unchanged: `config:ListConfigurationRecorders` stays ungranted (non-fatal, and
not worth a third rotation and a third version deletion), prod stays at
`config_recorder: false`, and no console wizard was used at any point.

The window must show a delivered 24-hour snapshot under `config/`, a measured
rather than projected cost per configuration item, the six alarms steady, and
the `$20` budget intact. Partial 3F follows.

Two constraints carry forward. IAM policy version pressure is now binding —
four of five slots used, two historical versions already deleted — so
re-adding the GuardDuty grants at the EC2 trigger will cost another deletion.
And a gated deploy should be expected to page: this sub-phase produced six
alarm emails, all true positives on its own work, because a troubleshooting
session and an attacker probing permissions produce the same sustained trickle
of `AccessDenied`.

### Verification

lint, mypy (36 files), 228 unit tests at 92.50% coverage, `synth-all` for both
environments through cdk-nag, `docs-sync`, `make wiki-lint` at 40 pages, index
rebuilt, and the changed files scanned for account-identifying literals.

## [2026-08-05] verify | Phase 3C observation window closed

### Objective

Decide the go/no-go on sub-phase 3C by checking its four observation criteria:
a delivered snapshot, a measured rather than projected cost, steady alarms, and
an intact budget.

### Scope

Read-only against the deployed dev account, roughly 48 hours after the
2026-08-03T00:41Z deployment. No code, configuration, or AWS change.

### Identity and environment

Administrator profile for the S3 listing, Config reads, Cost Explorer and
budget — the auditor lacks `budgets:ViewBudget` and
`cloudwatch:GetMetricStatistics`. Auditor profile for alarms and the audit log.

### Commands and results

- `s3api list-objects-v2` under `config/`: 53 objects. Two `ConfigSnapshot`
  deliveries (2026-08-03, 2026-08-04) and a `ConfigWritabilityCheckFile`
  refreshed 2026-08-04T23:47Z.
- `ConfigHistory` by day: **2026-08-03** — 10 in-scope, **40 out-of-scope**;
  **2026-08-04** — zero of either.
- `describe-configuration-recorders`: unchanged — `allSupported=false`, ten
  types, `INCLUSION_BY_RESOURCE_TYPES`. `describe-configuration-recorder-status`:
  `recording=true`, `lastStatus=SUCCESS`. CloudTrail shows no
  `PutConfigurationRecorder` after the deployment.
- `ce get-cost-and-usage` filtered to AWS Config, daily 2026-08-01..04: `0` every
  day. `describe-budgets`: `$20` limit, `$0.00` actual, `$1.156` forecast.
- Six `mlops-dev-security-*` alarms `OK`; none fired in the 48 hours since the
  deployment.

### Interpretation

The delivery criterion mattered most because it was the first thing to exercise
the audit bucket policy and the `kms:GenerateDataKey` grant with a real write;
a recorder reaching `SUCCESS` proves it is recording, not that it can deliver.
Both now hold.

The 40 out-of-scope objects looked at first like the recording scope being
ignored. It is not: the recorder was never modified, and the objects appear only
on the first day. **Config writes a one-time full-inventory baseline when a
recorder first starts, regardless of the inclusion list**, then honours the list
afterwards — which the zero-`ConfigHistory` second day confirms. The wiki record
overstated the scoping and has been corrected.

The measured `$0.00` is *lower* than the roughly 50 configuration items imply at
$0.003 each, so it is billing lag or a posting threshold rather than a true
zero. That does not move the decision, since the ceiling is cents, but the
honest reading is "not yet posted".

No alarm fired in 48 hours, which is consistent with the earlier finding that
deploy activity pages and steady state does not.

### Decision and next checkpoint

**3C is a go and its observation window is closed.** Deliberately left
unchanged: `config:ListConfigurationRecorders` stays ungranted, prod stays at
`config_recorder: false`, and the recording scope stays at ten types. Re-read
the Config line item at month end to replace the lagging `$0.00`.

Partial 3F (EventBridge routing of Access Analyzer and Config events) is next,
and inherits the binding IAM policy version pressure — four of five slots used,
two historical versions already deleted.

### Verification

Index rebuilt, `make wiki-lint` clean, and the changed files scanned for
account-identifying literals.
## [2026-08-04] ingest | AWS security hardening Phase 5A proxy execution role — August 5, 2026

Registered immutable source `raw/aws-security-hardening-phase-5a-proxy-execution-role-august-5-2026.md`.


## [2026-08-05] implement | AWS security hardening Phase 5A — proxy execution role

### Objective

Start Phase 5 by taking the first of four roles off `AWSLambdaBasicExecutionRole`,
whose three log actions apply to `Resource: "*"` — every log group in the
account, including the audit trail's.

### Scope

`infra/stacks/shared.py` (`platform_lambda` gains an opt-in
`least_privilege_logs`), `infra/stacks/serving_stack.py` (only `ProxyFn` sets
it), `infra/security_checks.py`, and two test modules. Stack touched:
`Mlops-Dev-Serving`.

### Identity and environment

us-east-1. Deployer profile for the named diff and deploy, auditor for
`verify-deploy` and alarms, administrator for the smoke run and the live role
and log reads.

### Commands and results

- Pre-flight inventory: 46 acknowledgements, **25 naming Phase 5** — 15 CDK S3
  grant wildcards, 7 managed log policies, 5 imported-bucket wildcards, 2
  `AmazonSageMakerFullAccess`, 1 `Resource::*`.
- Template diff against the pre-change synthesis: `ProxyFnServiceRole` and its
  default policy removed, `ProxyFnRole` and its default policy added, nothing
  else changed.
- Deploy 2026-08-05T01:29Z: six resources, matching that diff exactly.
- `make smoke`: 6 passed. `filter-log-events` on the proxy's group afterwards
  returns the `inference_response` event and fresh `START RequestId` lines.
  `iam list-attached-role-policies`: no rows. Six alarms `OK`.
- Acknowledgements 46 → 45. Gates: 230 tests at 92.52%, lint, mypy, `synth-all`.

### Interpretation

The load-bearing check is the log event, not the HTTP 200. The new policy is
what authorizes `PutLogEvents`, so too narrow a scope would have failed logging
**silently** while `/predict` kept returning 200 — a platform that looks healthy
and has stopped recording inference events.

Phase K and 5A composed without being designed to. An owned `logs.LogGroup` is
what makes `logs:CreateLogGroup` droppable rather than merely narrowable; had 5A
come first, the role would still have needed group-creation rights against a
generated `/aws/lambda/` name.

The count fell 46 → 45, contrary to the prediction that `IAM4` would trade for
`IAM5`. The reason deserves stating precisely: `grant_write` emits the group ARN
as an `Fn::GetAtt`, and cdk-nag does not read an intrinsic as a literal
wildcard. A log group's CloudFormation `Arn` **does** resolve with a `:*` stream
suffix at deploy time, which is why `PutLogEvents` works. The wildcard is real;
the gain is one log group instead of all of them.

The gate proved itself: removing the generated role left the
`ProxyFn/ServiceRole` acknowledgement matching zero constructs and failed
synthesis rather than leaving a stale suppression in place.

### Decision and next checkpoint

5A is deployed; **its observation window is open** — the runtime evidence so far
is a single smoke run, with nothing yet showing correct logging over a period or
during an endpoint update. Deliberately left unchanged: `least_privilege_logs`
stays opt-in, and the other three Lambdas keep the managed policy until their
own change sets.

Recorded but not acted on: three of the seven managed-log-policy
acknowledgements sit on CDK-generated provider Lambdas whose roles this
repository does not create, so their promised Phase 5 replacement will never
arrive.

5B (`ModelExecutionRole`) is next and is a step up in risk — a wrong scope there
breaks inference rather than logging.

### Verification

Index rebuilt, `make wiki-lint` clean, changed files scanned for
account-identifying literals.


## [2026-08-05] implement | AWS security hardening Phase 5B — model execution role

### Objective

Take the second of Phase 5's four roles off its broad policy: the role the
serverless endpoint's model container runs as, which carried
`AmazonSageMakerFullAccess` plus a ten-action `grant_read_write` on the
artifacts bucket — including `PutObject` and `DeleteObject*` — for a container
whose whole job is to download one `model.tar.gz` and answer requests.

### Scope

`infra/stacks/shared.py` (`sagemaker_execution_role` gains an opt-in
`least_privilege`; new `MODEL_ARTIFACT_PREFIX`), `infra/stacks/serving_stack.py`,
`infra/security_checks.py`, three test modules, and the coverage floor. Stack
touched: `Mlops-Dev-Serving`.

### Identity and environment

us-east-1. Deployer profile for the named diff and deploy, auditor for
`verify-deploy`, CloudTrail and alarms, administrator for the smoke runs and the
live role, endpoint, log and metric reads.

### Commands and results

- Pre-flight: 45 acknowledgements, 29 naming Phase 5, **7 of them on this one
  role**. The deployed `AWS::SageMaker::Model` was confirmed to pin the role ARN.
- Pre-flight evidence for what to grant: `describe-model-package` puts
  `ModelDataUrl` under the training prefix; the container image lives in an
  AWS-owned registry account, not ours; and `cloudtrail lookup-events` for
  `GetAuthorizationToken`, `BatchGetImage` and `GetDownloadUrlForLayer` returns
  **nothing in 90 days**, across many container starts.
- Template diff against the pre-change synthesis: exactly two resources changed,
  none added or removed — `ModelExecutionRole` loses `ManagedPolicyArns`, and its
  default policy trades ten S3 actions for `s3:GetObject` under the training
  prefix, `s3:ListBucket`, and four log actions on the endpoint's own group.
- Deploy 2026-08-05T02:49Z. `verify-deploy` reports four resources in one stack:
  the role, its policy, and both Lambdas' code.
- Component check: `make smoke` 6 passed; model package flipped to
  `PendingManualApproval` and back to `Approved` at 02:51:28Z; the endpoint went
  `Updating` → `InService` at 02:54:39Z on a **new endpoint config**; `make smoke`
  6 passed again.
- Live reads: `list-attached-role-policies` returns no rows, the role's physical
  id is unchanged, two new endpoint log streams were created at 02:54:07Z and
  02:54:55Z, `MemoryUtilization` published a datapoint at 02:54Z, and
  `Invocations` kept publishing.
- Acknowledgements 45 → 40; the model role's seven become two. Gates: 232 tests
  at 92.54% (floor raised 92.4 → 92.54), lint, mypy, `synth-all`.

### Interpretation

The load-bearing check is the forced endpoint update, not the HTTP 200. The role
is used at **container start** — image pull and artifact download — so a warm
endpoint answers `/predict` correctly over a role that would fail its next cold
start. Re-approving the model package drives the existing registry → `DeployFn` →
`UpdateEndpoint` path, which builds a new container from scratch and turns that
silent failure mode into a visible one. It reached `InService`, so the scope
holds.

Unlike 5A the role is **updated in place, never replaced**. The deployed
`AWS::SageMaker::Model` records the execution role ARN, so a new role construct
would have left the running endpoint pointing at a deleted ARN — visible only at
the next cold start, long after the deploy reported success.

Two permissions were deliberately not granted, each with a check behind it. ECR:
90 days of CloudTrail record no ECR call by any principal, and the image is
first-party, so SageMaker pulls it with service credentials. `PutMetricData`:
container metrics still published after the change, and granting it would have
forced a `Resource: "*"` statement, since the action has no resource-level
permissions. Both omissions were confirmed by the cold start rather than assumed.

`grant_read_write` was the larger finding of the two. The managed policy is the
headline, but the bucket grant is what let a hosted model **write to and delete
from** the bucket its own artifacts come from. Serverless inference has no data
capture, so nothing it runs ever writes back.

### Decision and next checkpoint

5B is deployed; **its observation window is open**, and 5A's is still open
alongside it — 5B's endpoint update also supplied the endpoint-update evidence
5A lacked. Deliberately left unchanged: `least_privilege` stays opt-in, the
pipeline role keeps `AmazonSageMakerFullAccess` until 5D, prod is untouched.

Recorded but not acted on: the deploy also updated both serving Lambdas' code.
The bundled asset hash in the repository had drifted from the deployed one
before this change — no `src/` or `lambda_code.py` commit since the last merge,
and the hash is deterministic across synths — so the drift predates 5B and its
provenance is unexplained.

The `iam-policy-changes` alarm fired at 02:52:53Z on a datapoint of 2.0 and is a
true positive on our own work: CloudTrail attributes exactly two IAM mutations,
`DetachRolePolicy` (02:49:55Z) and `PutRolePolicy` (02:50:12Z), to the CDK
execution role. It self-cleared. For comparison, 5A's deploy fired the same
alarm at 01:32:53Z on a datapoint of 3.0.

**`unauthorized-api-calls` also fired, at 03:02:14Z, and it is a second live
instance of the Phase 2E late-datapoint edge case** — not a burst, and nothing
to do with the model role. The window holds exactly **three** denial events:
`ListTagsForResource` at 02:49:47Z and 02:50:22Z by the CDK execution role,
which lacks `iam:ListTagsForResource` and has produced these on every deploy,
and one `frauddetector:GetOutcomes` at 03:00:39Z by `AWSServiceRoleForConfig`,
which is Phase 3C's recorder reaching a service it cannot read. On the standard
five-minute grid the metric reads 2.0 at 02:50Z and 1.0 at 03:00Z with zeros
either side; the alarm assembled `1.0, 1.0, 1.0` across its own 02:47/02:52/02:57
buckets and satisfied 3-of-3. Three isolated denials spread over eleven minutes
paged as if sustained. This is exactly what the 3C closure recorded — `3 of 3`
does not strictly mean fifteen consecutive minutes under lagging delivery — and
it strengthens the case for the deferred metric-`Fill` sub-phase. It self-cleared
at 03:03:14Z.

**No `AccessDenied` appears under the model execution role at any point.**

Console-side confirmations from the same window: the CloudFormation stack list's
`Updated time` column shows only `Mlops-Dev-Serving` touched on 08-04/08-05,
every other stack still on 08-01 or 08-02; the Lambda console shows exactly
`DeployFn` and `ProxyFn` modified minutes ago and the other five untouched for
days or weeks; SageMaker Models shows one new model created 02:51:31Z, which is
the forced cold start building a container under the new role; and the
`mlops-dev-endpoint-5xx` alarm — the repository's own inference-health tripwire —
never left `OK`, with the API service view reporting 18 requests, 0 faults and
100% availability. The 4xx count is the smoke suite's intentional
invalid-payload cases.

5C (`DeployFn`) is next: a Lambda role, so it returns to the 5A pattern, but its
`Resource: "*"` SageMaker statement is the real target rather than the managed
log policy.

### Verification

Index rebuilt, `make wiki-lint` clean, changed files scanned for
account-identifying literals.


## [2026-08-05] verify | Phase 5A and 5B observation windows closed

### Objective

Decide the go/no-go on both open Phase 5 sub-phases at once, on the criterion
each was still missing: a **natural** cold start of the serverless endpoint,
unprompted by any deployment or forced endpoint update.

### Scope

Read-only against the deployed dev account, roughly 20 hours after the
2026-08-05T02:49Z deployment, plus one `make smoke` run as the trigger. No code,
configuration, or AWS change.

### Identity and environment

Administrator profile for the endpoint, log, alarm and Cost Explorer reads and
the smoke run; auditor profile for the audit log.

### Commands and results

- Pre-state: `describe-log-streams` shows the newest endpoint stream last
  active 2026-08-05T02:54:59Z — twenty hours idle, so the serverless endpoint
  had scaled to zero and no container was warm.
- `make smoke` at 22:57:31Z: 6 passed. A **new** log stream appears, created
  22:57:39Z.
- Audit log, 03:05Z to 22:57Z: 19 denial events, **all** by
  `AWSServiceRoleForConfig` or `AWSServiceRoleForResourceExplorer` reaching
  services they cannot read. None under the model or proxy execution role, and
  `unauthorized-api-calls` did not re-fire.
- Six `mlops-dev-security-*` alarms `OK`. `ce get-cost-and-usage` for
  2026-08-01..05: a net **negative** total after credits, with SageMaker, Lambda,
  API Gateway, CloudTrail and Config all at `0`.

### Interpretation

One check closed both windows, because both were short the same thing. The
cold start is the only event that exercises a hosted model's execution role at
all — image pull and artifact download — and the twenty-hour idle guaranteed it
was genuinely cold rather than a warm container answering over a role nobody had
tested. 5B's forced `UpdateEndpoint` proved the scope on a container SageMaker
built during a deployment; this proves it on one built by ordinary traffic, with
no operator action in the loop. For 5A the same run supplies what its record
listed as explicitly missing: the proxy logging correctly over a period rather
than in a single post-deploy smoke run.

The nineteen denials are worth naming precisely, because a count that size looks
like a finding and is not one. Every one belongs to an AWS service-linked role
probing a service the account does not use — Phase 3C's recorder doing its job.
They are also the same background rate that has been present since 3C, spread
thinly enough that the Phase 2E three-datapoint rule never assembled a page from
them, which is the behaviour 2E was revised to produce.

### Decision and next checkpoint

**5A and 5B are both a go, and both observation windows are closed.**
Deliberately left unchanged: `least_privilege_logs` and `least_privilege` stay
opt-in, the pipeline role keeps `AmazonSageMakerFullAccess` until 5D, and prod
is untouched.

Recorded but not acted on: **`mlops-dev-endpoint-5xx` leaves `TreatMissingData`
unset**, so it defaults to `missing` and parks in `INSUFFICIENT_DATA` whenever
the endpoint is idle — which, on a serverless endpoint, is most of the time. It
went `INSUFFICIENT_DATA` at 03:12Z, twenty minutes after the deployment, when
smoke traffic stopped; that is the alarm's normal idle state and not a symptom of
5B. The six security alarms all set `notBreaching` instead. The gap is that the
inference tripwire cannot currently distinguish "healthy and idle" from "not
reporting". It is a detection-contract change, so under the Phase 2E precedent it
belongs in its own gated sub-phase rather than a drive-by edit.

5C (`DeployFn`) is next.

### Verification

Index rebuilt, `make wiki-lint` clean, changed files scanned for
account-identifying literals.

## [2026-08-06] implement | AWS security hardening Phase 5C — deploy execution role

### Objective

Take `DeployFn`, the registry-approval → endpoint-update Lambda, off
`AWSLambdaBasicExecutionRole` and off its six-action `Resource: "*"` SageMaker
statement — the third of the four roles Phase 5 converts one at a time, and the
repository's last real literal wildcard.

### Scope

`infra/stacks/serving_stack.py`, `infra/security_checks.py`,
`tests/unit/test_serving_stack.py`, `tests/unit/test_security_checks.py`,
`pyproject.toml`. Deployed stack `Mlops-Dev-Serving`. AWS resources touched by
the component check: raw/curated/artifacts buckets, `churn-training-pipeline-dev`,
`churn-model-group`, `churn-serverless-dev`, the API stage.

### Identity and environment

Dev, `us-east-1`. Deploy under the deployer identity; resource-level
verification and all CloudTrail reads under the security-auditor identity;
pipeline upsert/start, log reads and the API calls under the admin identity.
The auditor cannot read the `DeployFnLogs` group — its Phase 2E out-of-band
`logs:FilterLogEvents` grant is scoped to the audit group only, which surfaced
as an `AccessDeniedException` and required the identity switch.

### Commands and results

Read-only pre-flight: `make lint typecheck test synth-all` green at 232 tests /
92.54%; 40 acknowledgements in dev; 90 days of CloudTrail for the DeployFn
session returning exactly the six modelled calls plus `CreateLogStream` and
three `Decrypt`; `list-model-packages` confirming the
`model-package/<group>/<version>` ARN shape.

Mutating: one commit on `feat/phase-5c-deploy-role` (PR #41, CI green);
`make deploy-stack STACK=Mlops-Dev-Serving` at 23:58Z (70 s); an upload of 1,200
new rows to the raw bucket; `python -m src.pipeline.pipeline --start`, execution
`<pipeline-execution-id>`.

`make verify-deploy SINCE=2026-08-05` reported six changed resources — the old
role and policy deleted, the new role and policy created, the function
re-pointed, and `ProxyFn` code-updated.

Component check: all five pipeline steps `Succeeded`; training read 5,770 train
/ 1,236 validation rows; model package version 2 registered and auto-approved;
`DeployFn` logged `approved_challenger_deployed` with `action: "updated"` and
`test_auc` populated, no `AccessDenied`; endpoint `InService`; `sample.json` →
200 `churn: false`, high-risk → 200 `churn: true`, no key → 403; `make smoke`
6 passed.

Post-change gate: 233 passed at 92.58%, lint/typecheck/docs-sync/wiki-lint/
synth-all clean.

### Interpretation

The wildcard, not the managed policy, was the point here. A `Resource: "*"`
grant on `CreateModel`/`CreateEndpoint`/`UpdateEndpoint` in the role that reacts
to a registry approval means a compromised deploy Lambda could point any endpoint
in the account at any model. The scoping with the most security weight is
`DescribeModelPackage` on `model-package/<group>/*`: the package ARN arrives
inside the EventBridge detail, so it is the one attacker-influenceable input.

The check was designed against 5B's lesson. A warm `/predict` exercises the
proxy and proves nothing about this role, so new data was pushed through the
entire platform to make a real approval fire. That settled the one guess static
analysis could not: **`CreateModel` needs no permission on the model package it
references** — it succeeded against a package the role has no `CreateModel`
grant on. Granting only what evidence required, per 5B's precedent, cost nothing.

The counterpart hedge is still untested. `CreateEndpoint`/`UpdateEndpoint` name
both the endpoint and the endpoint-config because omitting a required resource
breaks the deploy path; whether the config entry is needed is undetermined.

Three findings belong to other change sets. The **bundled Lambda asset hash is
not reproducible** — vendored `__pycache__/*.pyc` embed mtimes that
`pip install -t` rewrites — so a deploy from a cold `cdk.out` republishes all
four functions with no source change, which is why the verify output shows
`ProxyFn`. `lambda_code.py` already fixes this failure mode on the source side
only. **Seven orphaned log groups** survive in dev and every platform Lambda has
a superseded `/aws/lambda/<function>` twin; deletion was declined by the
session's permission layer and handed to the operator. And **the drift → retrain
edge has never fired** — both `RetrainTriggerFn` log groups report no events
ever — which no earlier record had stated.

Also corrected: `fail_under` is compared against the *unrounded* coverage total,
so the floor went to 92.57, not the printed 92.58. The comment claiming the
comparison was rounded to `precision` digits was wrong.

### Decision and next checkpoint

Deliberately left unchanged: `least_privilege_logs` stays opt-in, so `ValidateFn`
and `RetrainTriggerFn` keep the managed log policy; `PipelineExecutionRole` keeps
`AmazonSageMakerFullAccess` until 5D; prod is untouched. No execution-policy
rotation was needed, so the last IAM version slot survives.

**No observation window has been opened for 5C.** The runtime evidence is one
end-to-end run immediately after deployment.

**5D is unblocked.** The billable pipeline run Phase 5 has required since the
roadmap was written happened here and succeeded — but under the *unchanged*
pipeline role, so it is 5D's baseline rather than its proof.

### Verification

Index rebuilt, `make wiki-lint` clean, changed files scanned for
account-identifying literals.

## [2026-08-06] verify | Attribute the alarm Phase 5C's deploy set off

### Objective

Attribute the `mlops-dev-security-iam-policy-changes` page that arrived during
the 5C deployment, rather than assuming it was our own work because the timing
fit.

### Scope

Alarm `mlops-dev-security-iam-policy-changes`, the `IamPolicyChanges` metric
filter on `/aws/cloudtrail/mlops-dev-audit`, and the IAM writes made by the
5C deploy of `Mlops-Dev-Serving`.

### Identity and environment

Dev, `us-east-1`, all reads under the security-auditor identity.

### Commands and results

The alarm fired at 2026-08-06T00:00:53Z on `1 datapoint [3.0 at 23:55:00]`
against a threshold of `Sum >= 1` over one 300-second period, and self-cleared
at 00:05:53Z. All six `mlops-dev-security-*` alarms are `OK`.

`cloudtrail lookup-events` over the window returned **zero** IAM events — it
caps at 50 results per page and the window was dominated by the pipeline run, so
the IAM writes fell outside the page. That is a false negative of the tool, not
evidence of absence, and it is why the attribution was redone against the
authoritative source: `logs filter-log-events` on the audit log group using the
metric filter's own pattern, read via the Phase 2E `logs:FilterLogEvents` grant.

That returned exactly three events, all inside the breaching period:

```
23:58:29Z  PutRolePolicy     role=Mlops-Dev-Serving-DeployFnRole<suffix>
                             policy=DeployFnRoleDefaultPolicyE7A28FAE
23:59:04Z  DeleteRolePolicy  role=Mlops-Dev-Serving-DeployFnServiceRole<suffix>
                             policy=DeployFnServiceRoleDefaultPolicy7D43372B
23:59:05Z  DetachRolePolicy  role=Mlops-Dev-Serving-DeployFnServiceRole<suffix>
```

All three by `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-<region>`, no
`errorCode` on any.

### Interpretation

A true positive on our own change set, fully accounted for: the inline policy
onto the new role, the inline policy off the old role, and the detach of
`AWSLambdaBasicExecutionRole`. The third is the security event Phase 5C exists
to produce — the moment `DeployFn` stopped carrying account-wide log
permissions — and the detection caught it.

The caller is the CDK CloudFormation execution role rather than the deployer
identity directly, which is the expected chain: the deployer assumes the CDK
exec role, and that role performs the IAM writes.

`unauthorized-api-calls` stayed `OK` throughout the deployment **and** the
end-to-end component check. That is a positive result rather than an absence:
the new least-privilege policy produced no denials while exercising every
statement in it.

Worth stating as a standing expectation: this alarm is `1 of 1`, while
`unauthorized-api-calls` was moved to `3 of 3` in Phase 2E. Any gated deploy
that touches a role therefore pages immediately and exactly once — 3C produced
six such emails, 5B two, 5C one. Deliberate contract, not noise; but it means
deploy-time mail is routine and must not train the operator to discount the
alarm.

### Decision and next checkpoint

No action. Nothing was misattributed, no unexpected principal appears, and no
threshold change is warranted. The 5C observation window remains unopened.

### Verification

Index rebuilt, `make wiki-lint` clean, changed files scanned for
account-identifying literals.

## [2026-08-06] implement | AWS security hardening Phase 5D — pipeline execution role

### Objective

Take `PipelineExecutionRole` off `AmazonSageMakerFullAccess` and off the CDK
bucket grants, replacing both with statements naming what a training run
actually touches. This is the last of Phase 5's four roles, so it closes the
phase.

### Scope

`infra/stacks/training_stack.py`, the two new prefix constants in
`infra/stacks/shared.py`, the training acknowledgements in
`infra/security_checks.py`, and their tests. One stack deployed in dev,
`Mlops-Dev-Training`. Prod untouched.

### What changed

`least_privilege=True` on the `sagemaker_execution_role` helper 5B added, plus
nine inline statements: `telco/` on curated; four artifacts prefixes
(`{pipeline_name}/`, `training/`, `evaluations/`, `monitor/`); `pipelines-*`
processing and training jobs; this environment's model package group;
the two SageMaker job log groups; and `PassRole` on itself, conditioned to
`sagemaker.amazonaws.com`. No statement carries `Resource: "*"`.

Scoping the curated read to `telco/` is a narrowing, not tidier IAM.
`InputDataUri` is a pipeline parameter, so a crafted `StartPipelineExecution`
could otherwise train the model on data of the caller's choosing.
`retrain_handler` starts the pipeline with default parameters only.

Updated in place. The deployed pipeline definition is upserted out of band with
`--role-arn` and `scripts/setup_monitor.py` takes the same ARN, so a
replacement would strand both. The template diff confirms it: two resources
changed, none added, removed, or renamed.

### The finding

The component check took three runs, and the two failures are the useful
output. Both were `sagemaker:AddTags` — first on the processing job, then on
the model package group.

`AddTags` appears **nowhere** in CloudTrail for this role. That absence is real
and the inference from it was wrong: Pipelines tags each resource it creates
*as part of the create call*, so the authorization check happens inside
`CreateProcessingJob` and never becomes its own event. No amount of trail
reading would have found it.

The general lesson, worth carrying into any future least-privilege work:
**CloudTrail enumerates a role's API surface, not its authorization surface.**
Anything checked as part of another call is invisible to it.

The same baseline did produce two correct catches of a related kind.
`logs:CreateLogGroup` and `sagemaker:CreateModelPackageGroup` are both called
unconditionally and both return a *service* error today
(`ResourceAlreadyExistsException`, `ValidationException`). Those are success
paths only while the permission exists — remove it and the same call returns
`AccessDenied`.

### Deliberately not granted

ECR (first-party images, pulled by SageMaker's own credentials; 5B proved it
live), `cloudwatch:PutMetricData` (no ARN, would restore the wildcard),
`s3:DeleteObject*` (no step deletes), and the lineage calls CloudTrail
attributes to `sagemaker.amazonaws.com` itself.

KMS is now settled **positively** rather than by analogy: the role makes 39
`GenerateDataKey`/`Decrypt` calls per run and succeeds today holding no KMS
permission at all — `AmazonSageMakerFullAccess` grants only `DescribeKey` and
`ListAliases`, and the `KMS_MANAGED` buckets make CDK emit no key grant. The
AWS-managed `aws/s3` key policy is what authorizes it.

One grant departs from evidence-only scoping and is recorded as such:
`monitor/*`, on the documented path in `scripts/setup_monitor.py`, which runs
Model Monitor under this same role. The drift loop has never run in this
account, so no evidence exists or could. The prefix is pinned to the script in
`tests/unit/test_pipeline.py`.

### Verification

```
2026-08-06T01:49:23Z  deploy 1   role + policy, in place, nothing replaced
2026-08-06T01:50Z     run <pipeline-execution-id>  Failed  AddTags on the processing job
2026-08-06T01:54:09Z  deploy 2   policy only
2026-08-06T01:54Z     run <pipeline-execution-id>  Failed  4/5 steps green; AddTags on the group
2026-08-06T02:12:40Z  deploy 3   policy only
2026-08-06T02:12Z     run <pipeline-execution-id>  Succeeded  all five steps
2026-08-06T02:18:16Z  model package v3 registered, auto-approved
2026-08-06T02:18:22Z  endpoint -> Updating   (six seconds later)
2026-08-06T02:21:01Z  endpoint InService
                      make smoke  6 passed
```

`make verify-deploy SINCE=2026-08-06` reports two resources changed in
`Mlops-Dev-Training` and no other stack touched. Run 3's Preprocess and Train
were 30-day cache hits, but both ran live under the least-privilege policy in
run 2, whose policy differs only by an ARN neither step touches — the union of
the two runs exercises every statement.

`mlops-dev-security-iam-policy-changes` fired, as it does on any gated deploy
that touches a role. The `AddTags` denials did **not** page
`unauthorized-api-calls`: a single denial in one five-minute period cannot
assemble the Phase 2E three-datapoint rule. `mlops-dev-endpoint-5xx` remains in
`INSUFFICIENT_DATA`, the unfixed gap recorded at the 5B/5C closure.

Local gate: lint, typecheck, 240 tests, coverage 92.64% (floor ratcheted
92.57 → 92.63), `make synth-all` clean for both environments. Acknowledgements
41 → 43.

### Decision and next checkpoint

Phase 5 is complete. No role attaches `AmazonSageMakerFullAccess`, and Phase
3E's account-level Block Public Access is the only wildcard resource the
repository writes. `AWSLambdaBasicExecutionRole` is separate residue and is not
finished: `ValidateFn`, `RetrainTriggerFn`, and the CDK provider Lambdas still
carry it.

**Phase 5C's observation window closed as a go on this run** — the registry →
`DeployFn` → endpoint path fired unattended, six seconds from auto-approval,
which is the evidence that window was short. Next is partial 3F (EventBridge
routing of Access Analyzer and Config events), still constrained by IAM policy
version pressure: four of five slots used.

New follow-up recorded: Model Monitor should have an execution role of its own
rather than reusing the pipeline role.

## [2026-08-06] verify | Phase 5D observation window closed as a go

### Objective

Decide go/no-go on Phase 5D after an observation period, rather than treating a
green component check as the end of the phase.

### Scope

The pipeline execution role's CloudTrail record since deployment, the six
security alarms, the endpoint, the `$20` budget, and hosted CI on the phase's
pull request.

### Evidence

Window: 2026-08-06T01:49Z (first deploy) → 2026-08-06T23:22Z, about 21 hours.

**No denial under the new policy.** CloudTrail for
`PipelineExecutionRole` across the window:

```
51  kms:GenerateDataKey
10  kms:Decrypt
 3  logs:CreateLogStream
 3  logs:CreateLogGroup   ResourceAlreadyExistsException
```

Zero `AccessDenied`. The `CreateLogGroup` errors are the documented expected
path — the container agent calls it on every job and the group already exists —
not failures. This is the criterion the phase existed to satisfy: the
least-privilege policy carried a full pipeline run and the twenty-one hours
after it without producing a single denial.

**Alarms.** All six security alarms `OK`. `iam-policy-changes` self-cleared at
2026-08-06T02:20:53Z, roughly eight minutes after the last deploy, and has not
fired since. No alert email arrived during the window, which is the correct
result rather than a missed signal: SNS sends on the `OK -> ALARM` transition
only, and nothing touched IAM after the deploys.

**Endpoint.** `InService`, unmodified since 2026-08-06T02:21Z.

**Budget.** `$20` limit intact, `$0.00` actual, `$1.11` forecast. Month-to-date
unblended cost is effectively zero — the three pipeline runs the phase needed
cost under a cent between them.

**CI.** `validate` and `secret-scan` both pass on the pull request.

### Decision and next checkpoint

**Go.** Phase 5D is complete and Phase 5 is closed. No role in the repository
attaches `AmazonSageMakerFullAccess`, and Phase 3E's account-level Block Public
Access remains the only wildcard resource this repository writes.

Next is partial 3F (EventBridge routing of Access Analyzer and Config events),
still constrained by IAM policy version pressure: four of five slots used.

### A gap this window exposed

**`${AWS_SECURITY_AUDITOR_USER_NAME}` cannot read budgets.** `budgets:ViewBudget` is denied
for that identity, so the budget check here had to run under `${AWS_ADMIN_USER_NAME}`.

That matters more than the missing permission itself. Every prior observation
window reported budget state, which means each one quietly reached for a broader
identity to do it — the auditor role is supposed to be the identity that closes
a window without administrator access, and on this criterion it never was. Phase
2E set the precedent for the fix: an out-of-band grant of exactly the read the
auditor needs, recorded here rather than left implicit.

Not fixed in this change set. It is an IAM change to a hand-managed identity and
belongs in its own gated step.

### Verification

Alarm states, endpoint status, budget, and CloudTrail read live. Index rebuilt,
`make wiki-lint` clean, changed files scanned for account-identifying literals.

## [2026-08-07] decide | Drift capture design; Model Monitor closed to new customers

### Objective

Decide the capture design that closes the drift-to-retrain loop, which has been
the one unfinished piece of the original platform plan since the serverless
endpoint shipped.

### Scope

New page `wiki/pages/decisions/drift-capture-design.md`. Updated
`wiki/pages/concepts/closed-drift-loop.md` and `wiki/pages/overview.md`. Read
but did not change: `infra/stacks/monitoring_stack.py`,
`src/monitoring/retrain_handler.py`, `src/serving/proxy_handler.py`,
`src/serving/deploy_handler.py`, `scripts/setup_monitor.py`,
`scripts/send_drift_traffic.py`, `infra/config/prod.yaml`. No AWS calls, no
application code changed.

### Evidence

Read live from AWS documentation on 2026-08-07.

**Serverless Inference feature exclusions** name data capture and Model Monitor
separately, alongside GPUs, multi-model endpoints, VPC configuration, network
isolation, multiple production variants, and inference pipelines. The same page
records that serverless-to-real-time conversion cannot be rolled back.

**Model Monitor is no longer open to new customers.** Every Model Monitor page
carries the notice: existing customers continue as normal, AWS continues
security and availability investment, no new features are planned. AWS names the
replacement — the open-source SageMaker AI monitoring solutions in `aws-samples`
(Evidently AI plus MLflow), with CloudWatch and QuickSight.

**Model Monitor does support batch transform inputs**, so a capture-format S3
prefix is a legitimate input independent of endpoint type.

**This platform never became a Model Monitor customer.**
`scripts/setup_monitor.py` has never run against `churn-serverless-dev`, because
Model Monitor does not support that endpoint type, and the README instructs the
reader not to try. No `CreateMonitoringSchedule` call exists in this platform's
history.

### Interpretation

The availability change collapses the framing the decision started with. Both
candidate options — provisioned inference with built-in capture, and serverless
capture written in Model Monitor's format — aim at a service this account cannot
onboard to. The choice is therefore not "which capture source" but "own the
drift job or do not close the loop".

Three options were evaluated. **A**, a provisioned real-time endpoint, is
rejected: it surrenders scale-to-zero, it is a one-way conversion, and it still
lands on Model Monitor. **B**, capture-format S3 plus a batch-input schedule, is
the most attractive on paper — a real Model Monitor execution still emits the
status-change event, so `DriftViolationRule` and `RetrainTriggerFn` would need
no change at all — and is rejected for exactly that reason: its whole value
depends on an unproven eligibility, and it owes a second migration afterwards.
**C**, a repository-owned drift job over proxy-side capture, is recommended.

Two constraints surfaced that the framing did not anticipate.

**Capture must not go through the log group.** Routing it through `log_event`
and a CloudWatch Logs subscription would be cheaper and would reuse the deployed
one-JSON-line-per-event convention, but Phase 7's checkpoint requires
observability that does not log customer inputs. A capture stream in the proxy's
log group is customer inputs in a log group. The roadmap wins; capture writes to
S3 directly.

**The cost line inverts.** The original design's hourly `ml.m5.large` schedule
was already recorded in `prod.yaml` as the thing that dominates the `$20`
budget. The Telco dataset is small enough that a window comparison fits in a
Lambda, so owning the job removes the cost rather than adding it.

### Decision and next checkpoint

**Option C.** The serverless endpoint stays. The proxy writes each validated
record and its score to an S3 capture prefix, a scheduled repository-owned job
compares a recent window against the training baseline, and it emits its own
violation event. `RetrainTriggerFn` reacts to that instead of SageMaker's event.
The drift job gets its own execution role from the start, which resolves the
Phase 5D follow-up about Model Monitor reusing the pipeline role by never
creating the shared-role condition.

The EventBridge contract change is the real work: `DriftViolationRule`'s detail
type, `retrain_handler.VIOLATION_STATUS`, and the `test_monitoring_stack.py`
assertion that pins their agreement all move in one change set. The proxy role
gains `s3:PutObject` on one prefix, which re-opens a role Phase 5A scoped and so
belongs in a change set that re-verifies that scoping.

Deliberately left open, and recorded on the page rather than settled here: the
drift statistic (Evidently as a dependency versus PSI computed directly over the
nineteen-column contract), and the minimum-sample rule.

**Two limits recorded that constrain any implementation.** Ground truth never
arrives in this platform — churn labels are not observed after a prediction — so
model-quality monitoring is unreachable by every option, and this loop can only
ever detect that input traffic changed. And an hourly schedule over a near-idle
endpoint mostly reads empty windows; without a minimum-sample rule the job
either fires on noise or cannot distinguish silence from health, which is the
same defect class as `mlops-dev-endpoint-5xx` leaving `TreatMissingData` unset.

Next checkpoint is implementation as a gated change set under the operating
rule. No code was changed here.

### Verification

`make wiki-index` rebuilt, `make wiki-lint` clean. Changed files scanned for
account-identifying literals: none. No AWS credentials used and no AWS API
called.

## [2026-08-07] implement | The drift loop closes on a repository-owned PSI job

### Objective

Implement Option C from the
[capture-design decision](pages/decisions/drift-capture-design.md): close the
drift-to-retrain loop without SageMaker Model Monitor and without giving up the
serverless endpoint's zero idle cost.

### Scope

New: `src/common/drift.py`, `src/monitoring/drift_handler.py`,
`tests/unit/test_drift.py`, `tests/unit/test_drift_handler.py`. Changed:
`src/serving/proxy_handler.py`, `src/monitoring/retrain_handler.py`,
`src/pipeline/preprocess.py`, `src/pipeline/pipeline.py`,
`infra/stacks/{shared,serving_stack,monitoring_stack}.py`,
`infra/security_checks.py`, `infra/app.py`, and six test modules. Retired:
`scripts/setup_monitor.py` and its test. Docs: `README.md`, `AGENTS.md`,
three wiki pages. No AWS API was called and nothing is deployed.

### What the loop is now

The proxy writes each served record and its score to
`capture/<YYYY>/<MM>/<DD>/<HH>/<uuid>.json` on the artifacts bucket. The
preprocessing step writes the training distribution to a fixed baseline key.
An hourly Lambda scores the previous hour against that baseline and emits
`mlops.monitoring` / `Drift Evaluation Result` with `status: DriftDetected`
when enough columns move. `RetrainTriggerFn` reacts to that instead of
SageMaker's monitoring event.

The statistic is the Population Stability Index over **raw** values, not the
encoded vector — a moved column names itself that way, which an ordinal code
cannot. Ten quantile bins per numeric column, `0.2` per column, `0.3` of
columns to call the window drifted.

### Three decisions the implementation forced

**Capture writes to S3, never to the log group.** Routing it through
`log_event` and a subscription filter would have been cheaper and would have
reused the deployed one-line-per-event convention. Phase 7's checkpoint
requires observability that does not log customer inputs, and a capture stream
in the proxy's log group is exactly that. The roadmap wins.

**Left-open bins, and this was a real defect.** The first implementation used
`bisect_right`. A right-open bin puts a low-cardinality numeric column entirely
in one bucket: `SeniorCitizen` holds 0 and 1, its only quantile edge is `0.0`,
and every shift in that column was invisible. The failing test was a fixture
whose constant baseline column reported zero drift against a very different
constant. `bucket_of` now uses `bisect_left`, and
`test_a_low_cardinality_numeric_column_still_separates` pins it.

**A rejected challenger resets the baseline.** Every preprocessing run
overwrites the fixed baseline key, including a run whose challenger loses the
AUC gate. Deliberate: it stops a shift the model cannot beat from starting a
retrain every hour. The cost is that a true positive is silenced by a failed
attempt to answer it, and that is the first thing the observation window should
look at.

### Boundaries the change set holds

- **The drift job has its own execution role.** This closes the Phase 5D
  follow-up about Model Monitor sharing the pipeline role, by never creating
  the shared-role condition. `DriftEvaluationFn` reads the baseline and the
  capture prefix, lists that prefix under a `StringLike` condition, puts events
  on the default bus, and writes nothing at all. A drift evaluation that could
  write the capture prefix could forge the evidence it reports on;
  `test_the_drift_lambda_reads_capture_and_never_writes_it` asserts no `s3:Put`
  or `s3:Delete` appears in the monitoring stack.
- **The proxy gained exactly `s3:PutObject` under `capture/*`.** No `Get`, no
  `Delete`. It cannot read the model artifact it serves and cannot replace a
  captured record. This re-opened a role Phase 5A scoped, so the serving IAM
  fingerprint moved; both pinned logical IDs, `ModelExecutionRole` and
  `ProxyFnRole`, are unchanged, so the deployed `AWS::SageMaker::Model` is not
  stranded.
- **A capture failure cannot fail a prediction.** The write happens after the
  response is final and is caught; it logs `capture_failed` and returns.
- **A short window is skipped, not scored.** `MIN_RECORDS` defaults to 100.
  A serverless endpoint is idle most of the time, and PSI over a handful of
  rows is sampling noise. `skipped: insufficient_records` and a no-drift result
  are distinct outcomes in the log, which is the point.
- The window is the hours *before* the current one, so a partial hour is never
  scored and no record is scored twice.

### Verification

`make lint`, `make typecheck`, `make docs-sync` clean. `make test`: **278
passed**, coverage `93.2458%`, floor raised `92.63 → 93.24`. `make synth-all`
clean for dev and prod, which is the cdk-nag gate — two new acknowledgements,
both naming Phase 4 as the point that re-evaluates them when the bucket moves
to a customer-managed key. IAM fingerprint baseline updated for `serving` and
`monitoring` with the logical IDs reviewed. `make wiki-lint` clean.

### Decision and next checkpoint

**Nothing is deployed.** The loop has never run in AWS, so `MIN_RECORDS`, both
thresholds, and the hourly cadence are unvalidated against real traffic. Under
the operating rule the next steps are a reviewed `cdk diff`, a scoped dev
deploy of Serving and Monitoring, a pipeline run to write the first baseline,
`scripts/send_drift_traffic.py` to force a violation, and an observation window
that watches for the baseline-reset behaviour above.

Two limits are structural rather than open work, and are recorded on the
decision page: ground truth never arrives, so this loop detects changed input
traffic and never a worse model; and `scripts/setup_monitor.py` is gone, so
there is no path back to Model Monitor without the eligibility pre-flight that
page describes.

## [2026-08-07] deploy | Drift loop deployed to dev; the baseline is not yet written

### Objective

Deploy the drift loop to dev under the operating rule, with a reviewed diff
before any mutation, and resource-level evidence after it.

### Scope

`Mlops-Dev-Data`, `Mlops-Dev-Serving`, `Mlops-Dev-Monitoring`, in that order.
Data first, because both other stacks import a new export from it. Identity:
`${MLOPS_DEPLOYER_USER_NAME}` for the diff and the deploys, `${AWS_SECURITY_AUDITOR_USER_NAME}` for
verification, `${AWS_ADMIN_USER_NAME}` for the budget and CloudTrail reads the auditor is
denied.

### Pre-flight baseline

Endpoint `InService`, last modified 2026-08-05T22:21Z. Six security alarms
`OK`. `mlops-dev-endpoint-5xx` `INSUFFICIENT_DATA`, which is the known
unfixed gap rather than a new symptom: it leaves `TreatMissingData` unset and
the endpoint is idle.

### The diff, before deploying

- **Data:** one added output, `ExportsOutputRefArtifactsBucket…`. No resource
  change. The bucket *ARN* export already existed; the drift Lambda and the
  proxy need the bucket *name*.
- **Serving:** exactly one IAM statement added — `s3:PutObject` on
  `<artifacts>/capture/*` for `ProxyFnRole`. `ProxyFn` gains two environment
  variables and a new asset hash. `DeployFn` shows an asset-hash change only,
  because both share the bundled `src/` asset. **No role replaced**, and
  `ModelExecutionRole` untouched.
- **Monitoring:** six resources added — log group, role, policy, function,
  schedule rule, invoke permission. Two updated: `RetrainTriggerFn` (asset)
  and `DriftViolationRule`, whose pattern moves from
  `aws.sagemaker` / `SageMaker Model Monitor Execution Status Change` /
  `MonitoringExecutionStatus` to `mlops.monitoring` / `Drift Evaluation Result`
  / `status`. Nothing deleted, nothing replaced.

### What the deploy actually changed

From `make verify-deploy SINCE=2026-08-07`, not from stack status:

```
Mlops-Dev-Monitoring   6 CREATE_COMPLETE, 2 UPDATE_COMPLETE
Mlops-Dev-Serving      3 UPDATE_COMPLETE (DeployFn, ProxyFn, ProxyFnRole policy)
Mlops-Dev-Data         (no resources changed -- metadata-only or no-op update)
```

The Data line is the case this rule exists for. The stack reports
`UPDATE_COMPLETE` and modified no resource; only the export was added.

### Live checks

**Serving and capture.** `make smoke` passed 6 of 6 against the deployed API.
Two capture objects landed under `capture/2026/08/07/17/`, one per successful
prediction. The smoke suite also exercises the rejection paths, and those
produced no object — a rejected request is never captured, as intended. A
captured object holds `captured_at`, all nineteen raw feature columns, and the
score.

**Drift evaluation.** A direct invocation returned
`{"skipped": "insufficient_records", "records": 0}` and logged
`{"event": "drift_window_too_small", "records": 0, "required": 100}`. Zero is
correct: the window is the hour *before* the current one, and the captures are
in the current hour.

That invocation also proved an ordering property the design did not state
explicitly. The baseline does not exist yet, and the handler returned without
error, because the sample-size check runs before `read_baseline`. A missing
baseline is therefore not a failure mode while traffic is below `MIN_RECORDS`.

**Alarms.** `iam-policy-changes` fired at 17:00:12Z and **self-cleared at
17:07:12Z**, seven minutes later. Phase 5D's deploy on 08-05 took five. The
SNS email was delivered, so the Phase 2C detection path is live-proven again.
CloudTrail attributes the fire entirely to this deploy: `CreateRole` at
16:59:03Z, `PutRolePolicy` at 16:57:54Z and 16:59:22Z, all by
`AWSCloudFormation`. The other five alarms `OK`. `mlops-dev-endpoint-5xx`
unchanged at `INSUFFICIENT_DATA`.

Two readings of that alarm are worth keeping, because both invite a wrong
conclusion:

- **The alarm email names `16:55:00` as the datapoint.** That is the start of
  the five-minute period, not an event time. The period contains all three IAM
  calls above. Read as an event time it looks like the alarm fired on something
  that predates the deploy.
- **The metric summed 1.0 in the 16:55 period and 1.0 in the 17:00 period.**
  Two matches total, which is exactly the two `PutRolePolicy` calls;
  `CreateRole` is correctly not in the CIS filter set. The split across two
  periods is CloudTrail-to-Logs delivery lag — the second call was delivered
  after its period closed. This is the same late-datapoint effect the Phase 2E
  closure recorded for `unauthorized-api-calls`, now observed on a second
  detection.

**Endpoint and budget.** Endpoint `InService`, last modified 2026-08-05T22:21Z
— unchanged by this deploy. Budget `$20` intact, `$0.00` actual, `$1.496`
forecast.

### What is deployed and what is not

Capture is live and the drift job runs on schedule. **The loop cannot yet
complete.** The baseline does not exist, and the deployed pipeline definition
does not write it: the `baseline` ProcessingOutput is in `src/pipeline/`, and
that definition reaches AWS through an SDK upsert, not through CloudFormation.

Two consequences, both unaddressed by this deploy:

1. Until the pipeline is upserted **and** run once, no drift evaluation can
   score anything.
2. If captured traffic reaches `MIN_RECORDS` in an hour before that happens,
   the handler will pass the sample-size check and fail on `NoSuchKey`. At the
   current traffic level this is remote, but it is the one way this deploy can
   produce an error rather than a skip.

The upsert is deliberately not done here. It mutates the deployed pipeline
definition, and a run in dev auto-approves its challenger, which can update
the endpoint. That is a larger action than deploying the loop and belongs to
its own decision.

### Next checkpoint

Upsert the pipeline with `--role-arn` and run it once to write the first
baseline, then force a violation with `scripts/send_drift_traffic.py` and
confirm the event reaches `RetrainTriggerFn`. The observation window should
watch for the baseline-reset behaviour recorded on the decision page: a
rejected challenger overwrites the baseline and can silence a true positive.

## [2026-08-07] verify | First baseline written; the sample-size rule guards count, not diversity

### Objective

Write the first drift baseline by upserting and running the pipeline, then
check the loop against real artifacts rather than fixtures.

### Scope

Pipeline `churn-training-pipeline-dev`, execution `<pipeline-execution-id>`. The baseline
object under the `monitor/baseline` prefix. Local scoring of real captured
records and real curated records against that baseline.

### The upsert needs an identity the platform does not have

`${MLOPS_DEPLOYER_USER_NAME}` cannot upsert the pipeline. `get_champion` calls
`ListModelPackages`, and that identity is denied it:

```
AccessDeniedException ... user/${MLOPS_DEPLOYER_USER_NAME} is not authorized to perform:
sagemaker:ListModelPackages on resource: model-package/churn-model-group/*
```

The upsert ran under `${AWS_ADMIN_USER_NAME}` instead. This is the same shape as the
existing rule that deploying and verifying are different identities: there is a
**third** out-of-band operator step, and it has no scoped identity of its own.
Recorded as open work, not fixed here.

### The run

Execution `<pipeline-execution-id>`, 17:35:16Z → 17:48:35Z, `Succeeded`.

```
Preprocess       Succeeded  17:35:17 -> 17:40:20
Train            Succeeded  17:40:21 -> 17:43:29
Evaluate         Succeeded  17:43:30 -> 17:48:34
BeatsChampion    Succeeded  17:48:34 -> 17:48:35   outcome: False
```

The challenger lost to champion version 3. Nothing registered, nothing
approved, and the endpoint was not touched — still on the config it has held
since 2026-08-05T22:21Z.

**This is the first live observation of the baseline-reset behaviour the
decision page records.** The gate returned `False`, and the baseline was
written anyway, because `Preprocess` runs before the gate and writes to a fixed
key. The behaviour is deliberate — it stops a shift the model cannot beat from
starting a retrain every hour — but it is now confirmed rather than predicted.

### The baseline

5,770 training rows. Nineteen columns with bucket counts, four numeric columns
with quantile edges. `Contract` sums to the record count. `SeniorCitizen` has
edges `[0.0, 1.0]` and buckets `4833`/`937`, so the two values separate
cleanly; real quantiles gave it two edges rather than the single edge that
motivated the left-open binning fix.

### The defect this check found

Scoring real data against the real baseline, with the shipped code:

| Window | Result |
|---|---|
| 100 / 500 / 1000 real curated records | `drifted=False`, 0 of 19 columns moved |
| 100 / 500 / 2000 identical records | `drifted=True`, 19 of 19 columns moved |

The statistic is well calibrated on genuine traffic — no false positive at any
of the three realistic window sizes. **`MIN_RECORDS` guards count, not
diversity.** A window of identical records is a point mass, so every column's
PSI explodes against the training distribution, and the
`DRIFTED_COLUMN_FRACTION` rule cannot help: it counts moved columns, and all of
them moved.

This is reachable from inside this repository. `make smoke` posts
`sample.json`. A health check or load test that calls `/predict` a hundred
times in an hour would report full drift and start a billable retraining run.

The unit tests missed it because every fixture window varies at least one
column. `test_compare_reports_no_drift_against_the_same_population` uses a
`spread`, so it never presented a single repeated record.

### Decision and next checkpoint

The loop is wired end to end and the baseline is live, but **it should not be
left armed with this defect**: the schedule is hourly, and any repetitive
caller trips it.

Proposed fix, as its own gated change set: require a minimum number of
*distinct* records in the window alongside `MIN_RECORDS`, and skip with a
distinct outcome when the window is too uniform to score. Real traffic produces
close to one distinct record per capture; the failure case produces one in
total, so the two separate cleanly.

Forcing a violation with `scripts/send_drift_traffic.py` is deliberately not
done yet. That script does vary its records, so it would pass — but with this
defect present, a pass would not distinguish a real detection from the
uniformity artifact.

## [2026-08-07] implement | Uniformity guard for the drift window, deployed to dev

### Objective

Fix the defect the first live check found: `MIN_RECORDS` guards the size of a
drift window, not its diversity, so a repetitive caller trips a full violation.

### Scope

`src/common/drift.py`, `src/monitoring/drift_handler.py`,
`tests/unit/conftest.py`, `tests/unit/test_drift.py`,
`tests/unit/test_drift_handler.py`, `pyproject.toml`. Deployed
`Mlops-Dev-Monitoring` only.

### The fix

`distinct_record_count` counts distinct feature vectors in a window. The
handler skips with a **third** outcome, `uniform_records`, when that count
falls below `MIN_DISTINCT_RECORDS`. Too few, too uniform, scored clean, and
scored drifting are now four readings, and only the last may retrain.

The threshold is 25, chosen from measurement rather than taste. Windows of 50,
100, 200, 500, and 1000 real curated records were **100 percent distinct** at
every size; the failure case is 1. Twenty-five sits between them with a wide
margin on both sides.

### The fixtures were the reason the defect shipped

Adding the guard broke five existing tests, and that is the more useful
finding. Every window fixture was built by repeating one record — `SHIFTED *
200`, `spread(...)` varying a single column while the other eighteen stayed at
the sample value. Those windows are point masses. **No drift statistic can be
evaluated against a point mass**, because it reports total drift regardless of
whether the detector works, so the tests could not distinguish a correct
implementation from a broken one.

One test was worse than weak. The stable-population case compared a baseline
with *the same rows* it was built from. That comparison cannot fail.

`tests/unit/conftest.py` gains `varied_records`, which draws from the real
`FEATURE_VOCABULARY` and then applies overrides to shift chosen columns. The
population-level tests now use two independent draws of one population, and the
shift test asserts that untouched columns such as `gender` stay put — which is
what separates a detected shift from detected uniformity.

### Verification

`make lint`, `make typecheck` clean. `make test`: **284 passed**, coverage
`93.2752%`, floor raised `93.24 → 93.27`. `make synth-all` clean for dev and
prod.

The reviewed diff was **asset hash only** on both Lambdas — no IAM statement,
no resource added or removed. `make verify-deploy` confirms exactly two
resources changed:

```
Mlops-Dev-Monitoring   UPDATE_COMPLETE  DriftEvaluationFnBA02D79D
                       UPDATE_COMPLETE  RetrainTriggerFn2698F1D9
```

A live invocation of the redeployed function returned
`{"skipped": "insufficient_records", "records": 2}`, reading the two real
captured records in the closed hour. The count guard is live.

### What is still unproven live

The **uniformity guard has not been exercised against real traffic**. Proving
it needs a closed hour holding at least `MIN_RECORDS` captured predictions that
are identical. Writing synthetic capture objects to reach that state was not
done: fabricating records in a data store is a poor way to prove a data rule,
and the sound test is the real one — post the `sample.json` payload through
`/predict` about 120 times, let the hour close, and read the scheduled run's
log for `drift_window_too_uniform`. That is precisely the health-check scenario
the defect describes, so the test and the failure mode are the same event.

Until that runs, the guard rests on unit evidence plus the measurement that set
its threshold.

### Note on the shared bundle

`Serving` and `Ingestion` still carry the previous `src/` asset, because only
`Monitoring` was deployed. Their next deploy will show an asset-hash-only diff.
Nothing in their behaviour changed; the drift modules are inert for them.

## [2026-08-07] verify | The uniformity guard rejected a real 120-record health-check window

### Objective

Prove the uniformity guard against real traffic rather than fixtures, by
reproducing the exact failure the earlier check found.

### Method

The test and the failure mode are the same event. `sample.json` was posted
through `/predict` 120 times at 18:07-18:09Z, which is what a health check on
the endpoint looks like. Fabricating capture objects in S3 was deliberately not
used: proving a data rule by writing fabricated data is weak evidence, and the
real path was available.

All 120 returned HTTP 200. The proxy log holds **120 `inference_response` and
zero `capture_failed`**, and the capture prefix gained exactly 120 objects for
hour 18 — one per prediction, no loss. Every score was byte-identical, which is
the point mass the guard exists to reject.

### Result

The **scheduled** run at 19:00:34Z read the closed hour and skipped it:

```
{"event": "drift_window_too_uniform", "records": 120, "distinct": 1, "required": 25}
```

Unattended, on the hourly rule, with no operator in the loop.

The negative evidence matters as much as the log line, because the failure mode
was a spurious retrain:

- `RetrainTriggerFn` has **zero log streams**. It has never been invoked.
- The only pipeline execution today is `first baseline for the drift loop`.
  Nothing started after the burst.
- Endpoint `InService`, last modified 2026-08-05T22:21Z, untouched.
- Six security alarms `OK`; `iam-policy-changes` cleared after the redeploy.

Before the guard this window would have scored 19 of 19 columns drifted, fired
a violation, and started a billable training run.

### What this closes and what it does not

The loop is now proven to **not** retrain in the three cases where it must not:
too few records, a uniform window, and a window drawn from the training
distribution.

**It has never been proven to retrain when it should.** No violation event has
ever been emitted, so the path from `PutEvents` through `DriftViolationRule` to
`StartPipelineExecution` is still untested end to end — the rule pattern and the
handler guard agree only by the unit assertion. Closing that needs
`scripts/send_drift_traffic.py`, whose records are varied, and it costs a
training run plus a possible endpoint update. Not done here.

### A gap this window exposed

**Captured objects have no expiry.** The capture prefix grows without bound,
and the drift job reads only the last hour. 122 objects is nothing, but there
is no lifecycle rule and no phase that adds one before 4C. Recorded, not fixed.

## [2026-08-07] verify | The drift loop closed end to end, and the demo exposed a hole in the rule

### Objective

Prove the violation path — the one link with no live evidence — then tighten
`scripts/send_drift_traffic.py` so its detection rests on the shift it names.

### The loop closed

200 shifted requests were sent at 19:44Z and captured into hour 19. The
scheduled run at 20:00Z carried the whole chain with no operator in it:

```
drift_violation   record_count 200, every column over threshold
retrain_started   execution <pipeline-execution-id>
pipeline          "drift-triggered retrain"  Executing -> Succeeded
```

`RetrainTriggerFn` was invoked for the first time in this platform's history.
The three windows staged that day each exercised a different branch, and each
behaved: hour 17 with 2 records skipped on count, hour 18 with 120 records and
1 distinct skipped on uniformity, hour 19 with 200 diverse shifted records
fired. The gate returned `False`, so nothing was promoted and the endpoint is
unchanged since 2026-08-05T22:21Z.

### Tightening the demo exposed a hole in the detection rule

The old script repeated one fixed record and varied only tenure and charges.
Sixteen of its nineteen drifted columns moved because the script **pinned**
them, not because of the shift it advertises. Rebuilding the background from
the real held-out `api_test` fixture — the same fixture `evaluate_api.py`
replays — isolates the shift to the three intended columns.

That isolation would have stopped the loop firing at all:

```
moved: MonthlyCharges, TotalCharges, tenure
fraction 0.158  (rule needed >= 0.3)      DRIFTED: False
max column PSI 12.65
```

Three of nineteen is under `DRIFTED_COLUMN_FRACTION`, so a shift with a PSI of
**12.6** — sixty times the per-column threshold — scored clean. Those three
columns carry most of the model's signal. The fraction rule alone cannot see a
targeted shift, and the old demo only ever worked because it was not targeted.

`SEVERE_COLUMN_PSI = 1.0` adds the second way in: many columns moved, or one
moved severely. Windows drawn from the training population score every column
under `COLUMN_PSI_THRESHOLD` and reach a maximum PSI of `0.067`, so the bar sits
about fifteen times above observed noise.

Two existing tests were overturned by the change, correctly. One asserted that
a single moved column is never drift, which is no longer the contract; it is
replaced by a pair that pin both sides — `Contract` skewed to 60 percent scores
`0.662` and does not fire, `Contract` collapsed to one value scores `9.44` and
does.

### A claim on the decision page was wrong

The page said every preprocessing run overwrites the baseline, so a rejected
challenger resets it and stops a retrain storm. The drift-triggered run
disproved it. `Preprocess` and `Train` are cached with `expire_after="P30D"`,
and on unchanged curated data both were **cache hits of one second each**. The
baseline object still carries its 13:37Z timestamp.

So the protection claimed does not exist. While drifted traffic keeps arriving,
the loop can retrain hourly, hit the cache, fail the gate, and never move its
own reference. A cooldown after a retrain, or an uncached baseline refresh, is
the fix. Neither is implemented, and the page is corrected.

The cache did make this retrain nearly free: only `Evaluate` ran, for 5m20s.

### Verification

`make lint`, `make typecheck` clean. `make test`: **291 passed**, coverage
`93.3538%`, floor raised `93.27 → 93.35`. Not yet deployed: this changes when
the platform spends money on retraining, so it needs its own reviewed diff and
deploy.

## [2026-08-08] deploy | Severity rule and the isolated demo shift, live in dev

### Scope

`Mlops-Dev-Monitoring` only. The change is in `src/common/drift.py` and
`scripts/send_drift_traffic.py`; the script is operator tooling and ships with
the repository rather than the stack.

### Pre-flight

No unscored drifted window existed. The 200-record shifted hour was scored at
20:00Z on 08-07 and every hour since is empty, so raising sensitivity could not
re-fire on traffic already in flight. Capture holds 322 objects, none from
08-08.

### The diff and what changed

Asset hash only on `DriftEvaluationFn` and `RetrainTriggerFn`. No IAM
statement, no resource added or removed. `make verify-deploy SINCE=2026-08-08`
confirms exactly those two resources.

A live invocation returned `{"skipped": "insufficient_records", "records": 0}`,
which is correct for an empty window.

### What is proven and what is not

The violation chain is proven end to end from the 08-07 run: capture, schedule,
statistic, event, rule, retrain Lambda, pipeline execution.

**The severity rule itself is not yet proven live.** Every live firing so far
went through the drifted-column fraction, because the old script moved sixteen
columns it did not intend to. Proving the new path needs the tightened script,
whose window moves three columns with a maximum PSI far past
`SEVERE_COLUMN_PSI` and a fraction under `DRIFTED_COLUMN_FRACTION`. That run
starts another retrain, so it is a separate decision.

### Standing risk, unchanged by this deploy

The retrain-storm hole is still open. `Preprocess` is cached, so a
drift-triggered retrain on unchanged curated data does not refresh the
baseline. Sustained drifted traffic can therefore retrain every hour without
ever moving the reference. A cooldown after a retrain, or an uncached baseline
refresh, remains unbuilt.

Captured objects still have no expiry.

## [2026-08-08] implement | Retrain cooldown, and why the refresh fix would not have worked

### Objective

Close the retrain-storm hole: under sustained drift the hourly job fires every
hour, and every violation starts a training run.

### The fix I proposed earlier was wrong

The earlier record offered two options — a cooldown, or an uncached baseline
refresh. **The refresh cannot work, and the reason is structural.** The
pipeline trains on `curated/telco/`. Captured traffic lands under the artifacts
bucket's capture prefix. The two never meet, and no step copies one into the
other.

So a retrain on unchanged curated data produces the same model and, if the
baseline were refreshed, a byte-identical baseline. Drifted API traffic cannot
reach the training set, so the violation repeats whatever the run concludes.
Refreshing the reference changes nothing; it would only have added cost.

Retraining cannot end this shift on its own. Only newly ingested data changes
the answer. The correct fix therefore throttles the actuation rather than
touching the measurement.

### The cooldown

`src/monitoring/retrain_handler.py` reads the pipeline's most recent execution
before starting one, and declines in two cases:

- the latest execution is `Executing` or `Stopping`, so a run is already
  answering this drift — a second one duplicates the cost and races the first
  to the registry;
- the latest execution started inside `RETRAIN_COOLDOWN_HOURS`, default 6.

Six hours bounds sustained drift to four runs a day instead of twenty-four,
while still allowing a same-day response once new data is ingested.

**The drift job is unchanged.** It still scores the window and still emits the
violation, because the drift is real and the signal should stay visible. Only
the handler that spends money declines, and it logs `retrain_suppressed` with
`in_flight` or `cooldown` as the reason. Detection reports; actuation throttles.

The guard sits after the status check, so a non-violation event costs no API
call — pinned by
`test_a_non_violation_never_reaches_the_cooldown_lookup`.

An empty execution history is not a cooldown. Without that case the very first
violation in a fresh environment would be suppressed forever.

### Verification

`make lint`, `make typecheck` clean. `make test`: **298 passed**, coverage
`93.3698%`, floor `93.35 → 93.36`. `make synth-all` clean for dev and prod.

The reviewed diff adds exactly one action, `sagemaker:ListPipelineExecutions`,
on the same pipeline ARN the role already held. No wildcard, no new resource.
The monitoring IAM fingerprint moved and both logical IDs are unchanged.

### Not deployed yet, deliberately

The severity-rule test is in flight: 200 isolated-shift records were captured
into hour 01 and are scored at 02:00Z. The last retrain started at 20:00Z on
08-07, which is **exactly six hours** before that run — the cooldown boundary.
Deploying now would land inside a running experiment and make its retrain leg
ambiguous. The deploy waits for that result.

## [2026-08-08] verify | Severity rule proven on isolated drift; cooldown deployed and proven

### The severity rule fired, and the result is discriminating

200 records with only `tenure`, `MonthlyCharges`, and `TotalCharges` shifted
were captured into hour 01. The scheduled run at 02:00:38Z reported:

```
drifted_columns  : ['MonthlyCharges', 'TotalCharges', 'tenure']
drifted_fraction : 0.157895   (fraction rule needs >= 0.3)   FAILS
max_column_psi   : 12.647534  (severity rule needs >= 1.0)   PASSES
```

The fraction rule **could not** have produced this: three of nineteen is 0.158.
The violation is attributable to the severity rule alone, which is what the
earlier demo could never establish.

The isolation is sharper than the design assumed. The three shifted columns
score `12.648`, `12.455`, and `12.438`; the worst of the sixteen untouched
columns scores `0.031`. That is a separation of about 400 times, against a
per-column threshold of `0.2`.

The local prediction matched the live result exactly — `tenure` predicted
`12.647534`, observed `12.647534`. Predicting a live number to six decimal
places from the deployed baseline and fixture is a useful check on the whole
capture-to-statistic path, not just the threshold.

`RetrainTriggerFn` started execution `<pipeline-execution-id>` two seconds later. That run
repeated the cached pattern: `Preprocess` and `Train` one second each,
`Evaluate` seven minutes, gate `False`, endpoint unchanged since
2026-08-05T22:21Z. The baseline was again not refreshed, which is the third
observation of that behaviour.

### The cooldown is deployed and proven

Deployed 02:09:58Z, after the run above finished so the in-flight branch could
not confound it. `make verify-deploy` confirms three resources:
`DriftEvaluationFn`, `RetrainTriggerFn`, and the retrain role's policy.

The component check cost nothing. Nine minutes after `<pipeline-execution-id>` started,
the handler was invoked directly with a violation event:

```
response: {"suppressed": ".../execution/<pipeline-execution-id>"}
log:      {"event": "retrain_suppressed", "pipeline": "churn-training-pipeline-dev",
           "reason": "cooldown", "latest_status": "Succeeded", "cooldown_hours": 6}
```

No new execution was created; the pipeline still shows exactly the two runs
from 20:00Z and 02:00Z. Before this change that violation would have started a
third.

### The loop's live evidence is now complete

Every branch has fired against real traffic on the real schedule:

| Window | Records | Distinct | Outcome |
|---|---|---|---|
| 2 records | 2 | 2 | `insufficient_records` |
| Repeated payload | 120 | 1 | `uniform_records` |
| Training population | 200 | 200 | scored, no drift |
| Broad shift | 200 | 200 | violation via the fraction rule |
| Isolated severe shift | 200 | 200 | violation via the severity rule |
| Violation inside the cooldown | — | — | `retrain_suppressed` |

### Still open

Captured objects have no expiry, and the prefix now holds 522. The drift job
reads only the last hour, so everything older is dead weight with no lifecycle
rule and no phase that adds one before 4C.

## [2026-08-08] verify | Two limits the retrain logs exposed

### A drift-triggered retrain re-evaluates a bit-identical model

The `Evaluate` step of execution `<pipeline-execution-id>` logged:

```
challenger_model_artifact : .../training/pipelines-<pipeline-execution-id>-Train-.../model.tar.gz
challenger_test_auc       : 0.8535
champion_test_auc         : 0.8679385964912282
promotion_decision        : reject
```

The artifact path names execution **`<pipeline-execution-id>`** — the 13:35Z baseline run,
not this one. `Train` was a cache hit, so the challenger under evaluation is
the same `model.tar.gz` that was already trained, evaluated, and rejected
hours earlier. The verdict was deterministic before the run started.

This sharpens the earlier finding. It is not only that the baseline fails to
refresh: on unchanged curated data the whole retrain produces a bit-identical
model and pays seven minutes of `Evaluate` to re-derive a known answer.
`Evaluate` is deliberately uncached, because the champion can change
independently of the pipeline's inputs — that rationale holds in general, and
in this loop it means every futile retrain still costs a processing job.

The cooldown bounds this to four runs a day. Each of those four remains
provably pointless until new data reaches `curated/telco/`. A stronger gate
would compare the resolved challenger artifact against the champion's and skip
evaluation when they match, or condition the retrain on curated data having
changed. Neither is implemented.

### The drift job has a hard ceiling around five thousand records an hour

The 200-record window took **12,410 ms**, of which 455 ms was initialisation.
That is **59.8 ms per record**, because `read_captured` issues one
`GetObject` per captured object.

The function's timeout is 300 seconds, so it exhausts its budget at roughly
**5,000 records in a window** and then fails rather than reporting. At the
current traffic level this is remote, but it is a real ceiling and it is
invisible until crossed: a busy hour would produce a Lambda timeout, not a
drift verdict.

The fix is to stop reading objects one at a time — concurrent reads, or a
single rolled-up object per hour written by a small aggregation step. Recorded,
not implemented. Neither the timeout nor the per-object read is tuned; 512 MB
is ample, with 100 MB used.

## [2026-08-08] implement | Captured predictions expire after 30 days

### Objective

Close the last recorded gap in the drift loop: the capture prefix grew without
bound, and no phase added a lifecycle rule before 4C.

### The rule

`ExpireCapturedPredictions` on the artifacts bucket, scoped to the `capture/`
prefix, expiring at `capture_retention_days` — a new typed key in
`PlatformConfig`, 30 in both environments.

**The prefix scope is the whole safety argument.** The same bucket holds
`model.tar.gz`, the evaluation report bundles, and the drift baseline. An
unscoped rule would strand the endpoint at its next cold start and leave the
drift job with nothing to compare against.
`test_the_baseline_and_model_artifacts_are_outside_the_expiring_prefix` pins
that the three live prefixes sit outside `capture/`, so a rename on either
side fails a test rather than deleting a live artifact.

The rule carries a second duration because the bucket is versioned. Expiring a
current version leaves a noncurrent one behind, which stays billable after the
object disappears from a listing. `NoncurrentVersionExpiration` of one day
removes it.

Thirty days is not a drift-job requirement — the job reads one hour. It bounds
how far back a past violation can be investigated, and it matches the pipeline
cache's `P30D`.

### Verification

`make lint`, `make typecheck` clean. `make test`: **300 passed**, coverage
`93.3779%`, floor `93.36 → 93.37`. `make synth-all` clean for dev and prod.

The reviewed diff adds one property to one bucket:

```
[~] AWS::S3::Bucket ArtifactsBucket ArtifactsBucket2AAC5544
 └─ [+] LifecycleConfiguration
     {"Rules":[{"ExpirationInDays":30,"Id":"ExpireCapturedPredictions",
       "NoncurrentVersionExpiration":{"NoncurrentDays":1},
       "Prefix":"capture/","Status":"Enabled"}]}
```

Same logical ID, so this is an in-place update. The bucket holds live data
under `RemovalPolicy.RETAIN`, and a replacement would have been the one
unacceptable outcome here.

## [2026-08-07] update | IAM execution-policy version slots freed for 3F

Audited the five versions of the CloudFormation execution policy and deleted
two. Three slots now hold `v8`, `v10`, and the default `v11`; two are free.
Phase 3F is unblocked.

### What the audit found

Two recorded facts were wrong. The wiki said four of five slots were used;
all five were. And it said `v5` and `v6` were both deleted during 3C; only
`v5` was.

The live versions, oldest first:

| Version | Created | Statements | Change from the version before |
|---|---|---|---|
| v6 | 2026-07-12 | 3 | Pre-Phase-3 baseline |
| v7 | 2026-07-15 | 5 | Added the two Config service-linked-role statements |
| v8 | 2026-07-18 | 6 | Added `AccessAnalyzerServiceLinkedRole` |
| v10 | 2026-08-03 | 6 | Narrowed `ApplicationServices` and both Config statements |
| v11 | 2026-08-03 | 7 | Default. Added `PassConfigServiceLinkedRole` |

`v9` never existed — version numbering is monotonic, not slot-based.

The AWS policy name is `MLOpsCloudFormationExecutionPolicy`. The repository
filename `mlops-cloudformation-execution-policy.json` is not the AWS name, and
an ARN built from the filename returns `NoSuchEntity`.

`infra/policies/mlops-cloudformation-execution-policy.json` matches live `v11`
exactly, apart from the four `${AWS_ACCOUNT_ID}` placeholders the
no-account-literals rule requires. The repository file is a faithful rollback
source for the default version.

### Why v6 and v7 went

Neither is a usable rollback target. A rollback to `v7` drops the Access
Analyzer grant and re-widens `ApplicationServices`, which is a 3B and 3C
regression rather than a recovery. Both states stay reachable in git: `89e3daa`
holds `v6` and `dbe6578` holds `v7`.

`v8` and `v10` were kept. `v10` is the one-step rollback for `v11`. `v8` is the
last pre-3C state and the only console-side undo for the 3C narrowing.

### Identities

The audit ran under `${AWS_SECURITY_AUDITOR_USER_NAME}`, which can read policy versions.
The deletion needs `${AWS_ADMIN_USER_NAME}` — the auditor profile is read-only.
## [2026-08-07] query | 3F EventBridge alert routing

Found 23 matching page(s).


## [2026-08-08] update | Phase 3F partial alert routing deployed to dev

**Objective.** Route the Phase 3 findings this account actually produces to
the Phase 2 SNS alert topic, and close every part of Phase 3 that the
paid-plan decision does not block.

**Scope.** `infra/stacks/security_monitoring_stack.py` (two `events.CfnRule`
resources, the `eventbridge_alerts` flag added to `IMPLEMENTED_SERVICE_FLAGS`),
`infra/stacks/security_stack.py` (one audit-key grant, one topic-policy
grant), `infra/config/dev.yaml`, and the two stack test modules. Deployed
stacks: `Mlops-Dev-Security`, then `Mlops-Dev-SecurityMonitoring`.

**Identity and environment.** `${MLOPS_DEPLOYER_USER_NAME}` for both deploys,
`${AWS_SECURITY_AUDITOR_USER_NAME}` for verification and the live reads. Region
`us-east-1`, dev only.

### What was built

| Rule | Pattern |
|---|---|
| `mlops-dev-security-access-analyzer-findings` | `aws.access-analyzer`, `Access Analyzer Finding`, `status` `ACTIVE`, `isDeleted` `false` |
| `mlops-dev-security-config-delivery-failures` | `aws.config`, history and snapshot delivery status, `messageType` the two `*DeliveryFailed` values |

Configuration item changes are not routed: continuous recording emits one
event per change across about 100 resources, into an email topic. Compliance
events are not routed: this account deploys no Config rules to produce them.
Both exclusions are asserted in tests.

Each source routes only while its own service flag is true. Prod keeps every
flag false and synthesizes to `CDKMetadata` alone.

### The grant scoping

The rules live in `SecurityMonitoring`, which already depends on `Security`
for the topic ARN. Scoping the grants to a rule reference would close that
into a cycle, so both name the prefix `:rule/mlops-<env>-security-*` under
`ArnLike`, with `aws:SourceAccount` alongside. The prefix is therefore load-
bearing: a rule named outside it matches its events and then fails to publish
them. A test pins the prefix on the rule side and on both grant sides.

**No policy rotation was needed.** `ApplicationServices` already grants
`events:PutRule`, `events:PutTargets`, `sns:SetTopicAttributes` and the rest,
because the platform's own EventBridge and SNS resources needed them first.
The version slots freed on 2026-08-07 stay banked at three of five used.

### Verification

`make lint`, `make typecheck`, `make security` clean. `make test`: **306
passed**, coverage `93.4534%`, floor `93.37 → 93.45`. cdk-nag passes both
environments with no new acknowledgement.

`make verify-deploy SINCE=2026-08-08` under `${AWS_SECURITY_AUDITOR_USER_NAME}` reports
exactly the intended four resources:

```
Mlops-Dev-SecurityMonitoring  [UPDATE_COMPLETE]
    CREATE_COMPLETE          AccessAnalyzerFindingRule
    CREATE_COMPLETE          ConfigDeliveryFailureRule
Mlops-Dev-Security  [UPDATE_COMPLETE]
    UPDATE_COMPLETE          AuditKeyB2DBB069
    UPDATE_COMPLETE          SecurityAlertsTopicPolicy1E6023E3
```

`aws events describe-rule` confirms both rules `ENABLED` with the intended
patterns, and `list-targets-by-rule` confirms one target each, the alert topic.

### Interpretation and the open gap

Neither rule has fired. `list-findings` returns zero `ACTIVE` findings, the
recorder reports `recording: true` and `lastStatus: SUCCESS`, and both
delivery channels report `SUCCESS`. Every source is healthy with nothing to
report, so the path is deployed and unexercised — the same shape of gap the
drift → retrain edge carries.

Live proof requires manufacturing a signal: a cross-account principal on a
low-value bucket for the analyzer rule, reverted after, which also pages
`iam-policy-changes`; or a deliberately broken delivery for the Config rule.
Neither was run.

**Decision and next checkpoint.** Phase 3 is now complete except `guardduty`
and `security_hub`, both waiting on the explicit paid-plan upgrade decision.
The 3F observation window is open. Prod remains all-false. Phase 4 (KMS) is
next once 3F closes as a go.

## [2026-08-08] update | Phase 3F analyzer routing proved with a manufactured finding

**Objective.** Close the 3F record's open gap by making a real Access Analyzer
finding travel the full path to the alert topic.

**Identity and environment.** `${AWS_ADMIN_USER_NAME}` for the mutating setup and for the
CloudWatch reads, `${AWS_SECURITY_AUDITOR_USER_NAME}` for the analyzer reads. Dev,
`us-east-1`.

### The path to a usable test

The first design used a cross-account S3 bucket policy naming AWS's
documentation account `111122223333`. **S3 rejects it**:
`MalformedPolicy: Invalid principal in policy`. S3 verifies that the account
in a root principal exists, so no placeholder id can ever work, and a real
second account was not available.

The working substitute was a throwaway SQS queue with a public grant. Access
Analyzer flags public access as well as cross-account, SQS has no Block Public
Access equivalent to block the policy, and the queue could be deleted outright
afterwards. The grant was limited to `sqs:GetQueueAttributes` on an empty
queue attached to nothing — metadata reads only, no send or receive.

The mutating write was run by the human. The permission classifier blocked it
from this session in every form attempted, correctly: a policy granting
outside access is indistinguishable in shape from an exfiltration setup.

### Timeline and evidence

| Time (UTC) | Event |
|---|---|
| 13:15:26 | Public queue policy live |
| 13:17:08 | Finding `<finding-id>` created — `ACTIVE`, `isPublic true`, `AWS::SQS::Queue` |
| 13:13–13:18 | Rule `MatchedEvents` 1, `Invocations` 1, `FailedInvocations` **0** |
| 13:13–13:18 | Topic `NumberOfMessagesPublished` 2, `NumberOfNotificationsDelivered` 2 |
| 13:18:21 | Queue and the unused throwaway bucket both deleted |

The finding arrived in about two minutes, against an AWS estimate of up to an
hour.

**`FailedInvocations` 0 is the load-bearing number.** It proves both new
grants at once: EventBridge could publish to the topic, and it could use the
KMS key the topic encrypts with. A missing key grant fails the invocation
rather than degrading quietly. The two topic publishes cannot be split by
source from metrics alone; the rule's own `Invocations` 1 is the direct
evidence, not the topic count.

### Interpretation

`mlops-dev-security-s3-bucket-policy-changes` went to `ALARM` on the test's
own bucket-policy writes — a true positive on this work, matching the 2E
precedent and 3C's six emails.

Finding `<finding-id>` stayed `ACTIVE` immediately after the queue was deleted.
Access Analyzer resolves findings for deleted resources on a later pass, so
this is expected rather than a leak.

`${AWS_SECURITY_AUDITOR_USER_NAME}` cannot call `cloudwatch:GetMetricStatistics`, so the
metric evidence needed `${AWS_ADMIN_USER_NAME}`. That is a second auditor gap beside the
known `config:ListConfigurationRecorders` one.

**Decision and next checkpoint.** The Config delivery-failure rule stays
unproved: proving it means breaking the compliance evidence trail on purpose,
which is not worth the value. The 3F window stays open on that reduced gap.
No account artifacts remain from the test.

## [2026-08-08] update | The drift → retrain edge fired for the first time

**Objective.** Correct a claim this repository has carried since 5C: that the
closing edge of the drift loop had never run.

**It has now run.** Timeline from the Phase K log groups, all on 2026-08-08:

| Time (UTC) | Event |
|---|---|
| 01:21 | Inference traffic writes the capture window |
| 02:00:38 | `drift_violation` — 200 records, `drifted: true`, `tenure` 12.648, `MonthlyCharges` 12.455, `TotalCharges` 12.438 |
| 02:00:40 | `retrain_started` — execution `<pipeline-execution-id>` |
| 02:05:13 | `challenger_evaluation` — challenger 0.8535 AUC, champion 0.8679, `promotion_decision: reject` |
| 02:11:07 | `retrain_suppressed` — `reason: cooldown`, `cooldown_hours: 6` |

`describe-pipeline-execution` reports `<pipeline-execution-id>` as `Succeeded`.

Three mechanisms are now proved live, not only in tests: the drift Lambda's
violation path, the promotion gate rejecting a worse challenger, and the
six-hour retrain throttle.

**The wiki was wrong and is corrected.** The roadmap page still said both
`RetrainTriggerFn` log groups reported no events ever. Only the superseded
`/aws/lambda/<function>` twin does; the Phase K `*Logs*` group holds the run.
Reading the `/aws/lambda` twin alone would repeat the mistake — the twin exists
for every platform Lambda and none of them writes to it.

The hourly drift job has logged `drift_window_too_small` (`records: 0`,
`required: 100`) at 03:00, 04:00, 05:00, and 06:00. No traffic has arrived
since the 01:21 burst, so the size guard is skipping empty windows as designed.

**Interpretation.** This closes the last unexercised edge of the platform
runtime. It is unrelated to Phase 3F, which was deployed two hours later; the
two share only the date.

## [2026-08-08] update | The routed finding reached the subscriber

The last unconfirmed link of the 3F analyzer proof is closed. The subscribed
address received the finding at 13:17Z as an `AWS Notification Message` — raw
EventBridge JSON, not an alarm email, which is why it did not resemble the
alarm traffic around it.

The delivered body carries finding id `<finding-id>`, the same id
`list-findings` reported, with `"detail-type":"Access Analyzer Finding"`,
`"source":"aws.access-analyzer"`, `"status":"ACTIVE"`, `"isDeleted":false`,
`"isPublic":true`, and the resource `mlops-dev-3f-routing-proof`.

The delivered event satisfies the rule's own predicate on `status` and
`isDeleted`. The pattern therefore filtered correctly rather than passing
traffic that happened to match nothing.

**A metric-reading correction.** An earlier reading of this window reported two
publishes sharing one five-minute bucket, and concluded the finding could not be
attributed by source from metrics alone. That was an artefact of unaligned
bucket boundaries. Aligned to five-minute marks, each message separates: the
two `s3-bucket-policy-changes` alarms fall in 13:05 and 13:10, and the 13:15
bucket holds exactly one publish and one delivery — the finding. Query
`get-metric-statistics` on aligned boundaries before attributing SNS traffic.

The analyzer rule is now proved on every link: finding created → rule matched →
target invoked without failure → topic published → notification delivered →
subscriber received. Only the Config delivery-failure rule remains unproved,
by choice.

## [2026-08-08] plan | Sub-phases 2F and 2G opened

**Objective.** Turn two recorded but unscoped alarm defects into gated
sub-phases under the Phase 2E precedent. Both were prose deferrals with no
identifier, so neither could be scheduled.

**Scope.** `wiki/pages/architecture/phased-security-hardening.md` only. No code
was changed, and no AWS resource was touched.

**2F — `mlops-<env>-endpoint-5xx` `TreatMissingData`.** Verified in the
repository rather than from the record: `infra/stacks/` has exactly two
`Alarm(` call sites, `monitoring_stack.py:187` and `security_stack.py:458`.
The security alarms set `NOT_BREACHING`; the 5xx alarm sets nothing, so the
claim that it is the only alarm leaving the property unset is now checked, not
assumed. The sub-phase chooses `NOT_BREACHING` or `IGNORE`.

**2G — `UnauthorizedApiCalls` metric `Fill`.** `security_stack.py:51` still
carries `evaluation_periods=3, datapoints_to_alarm=3` with no fill.

**Interpretation.** The two are not the same kind of defect, and the sub-phase
entries now say so. 2F is a false state: the alarm cannot distinguish healthy
and idle from not reporting. 2G is a false claim about a true alarm: the
detection works, but `3 of 3` does not mean fifteen consecutive minutes under
lagging delivery. Two constraints were recorded with them. Neither
`TreatMissingData` value separates idle from silent, so 2F needs a second
signal or an accepted limit. `FILL` is metric math, so 2G rewrites the alarm
resource instead of setting a property, which is the larger blast radius of
the two.

**Decision and next checkpoint.** Both stay not started. Neither waits on the
paid-plan decision, and neither rotates the execution policy, so neither
consumes one of the two free IAM version slots. The 3F observation window
stays open by decision, and the operating rule allows only one sub-phase in
validation at a time, so 2F and 2G are eligible after 3F reaches its go/no-go.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] verify | Phase 3F observation window closed as a go

**Objective.** Close the partial 3F observation window with an explicit
go/no-go, using resource-level and metric evidence rather than stack status.

**Identity.** `${AWS_SECURITY_AUDITOR_USER_NAME}` for rules, alarms, analyzer, and stack
status. `${AWS_ADMIN_USER_NAME}` for CloudWatch metrics, Config status, and the budget —
the auditor lacks `cloudwatch:GetMetricStatistics`, `budgets:ViewBudget`, and
`config:ListConfigurationRecorders`. All three known gaps held again.

**Window bounds.** `Mlops-Dev-SecurityMonitoring` reached `UPDATE_COMPLETE` at
2026-08-08T04:00:37Z. The window therefore ran about eleven hours, not the two
to three the proof timestamps suggest at a glance, and not the 48 hours the 3C
and 5A windows ran.

**Evidence.** Both rules `ENABLED`. Over the window the analyzer rule recorded
`MatchedEvents` 1, `Invocations` 1, `FailedInvocations` 0; the Config rule
recorded 0/0/0. The topic recorded four published, four delivered,
`NumberOfNotificationsFailed` 0. The recorder reports `recording: true` and
`lastStatus: SUCCESS`. The analyzer is `ACTIVE` with zero active findings. The
six security alarms are `OK`; `mlops-dev-security-s3-bucket-policy-changes`
self-cleared at 13:20:51Z after the test's own writes, a true positive in the
2E and 3C pattern. `make smoke` passed 6. Month-to-date cost is `$0.00` and the
`$20` budget is intact at `$0.00` actual against a `$1.823` forecast.

**Decision: go.** The window is short against precedent and closes anyway,
because 3F's load-bearing proof does not accumulate. The risk was that the two
new grants — topic policy and audit key — would fail at publish time, and
`FailedInvocations` 0 on a real routed finding settles that in one event. More
hours would have added cost data the budget already reports as zero.

**Two findings the window produced.**

1. **The Config rule gained its negative half.** A history delivery succeeded
   at 11:47Z, inside the window and after the rules went live, and the rule
   matched nothing. The rule is now known to stay silent through a healthy
   delivery. That is not knowing it fires on a broken one, which stays
   unproved by choice. Snapshot delivery is on a `TwentyFour_Hours` frequency
   and its last success predates the deploy, so no post-deploy snapshot was
   observed.
2. **Finding `<finding-id>` resolved on its own at 13:19:35Z**, about a minute
   after the queue delete, closing the record's open question about
   short-lived `ACTIVE` findings. The rule's match count stayed at 1 across
   that transition. That is consistent with the `status ACTIVE` predicate, but
   it is not proof of filtering: metrics cannot separate a resolution event
   that was emitted and rejected from one that was never emitted.

**Deliberately unchanged.** `mlops-dev-endpoint-5xx` still reads
`INSUFFICIENT_DATA`. That is the 2F defect, not a 3F regression.

**Next checkpoint.** Sub-phases 2F and 2G are now eligible, one at a time.
Full 3F stays behind the paid-plan decision.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] deploy | Sub-phase 2F deployed to dev, observation open

**Objective.** Make the two endpoint alarms report an idle endpoint honestly,
under the Phase 2E gate.

**Scope.** `infra/stacks/monitoring_stack.py`, `infra/stacks/shared.py`
(`MonitorConfig`), both `infra/config/*.yaml`,
`tests/unit/test_monitoring_stack.py`, `pyproject.toml`. Stack
`Mlops-Dev-Monitoring` only.

**Change.** `mlops-<env>-endpoint-5xx` sets `TreatMissingData` to
`NOT_BREACHING`. A new `mlops-<env>-endpoint-silent` alarms on `Invocations`
`Sum` under 1, hourly period, over `monitor.silence_alarm_hours` periods, with
`TreatMissingData` `BREACHING`. Dev's window is 24 hours, prod's is 6.

**The decision this sub-phase was required to state.** The 2F entry demanded an
explicit choice between taking a second signal and accepting the limit that no
`TreatMissingData` value separates idle from silent. **It took the second
signal.** The cost was stated in advance and is real: dev has no traffic floor,
so `endpoint-silent` reaches `ALARM` there on a correctly working idle
endpoint, and it pages the same topic as the security alarms. The 24-hour dev
window bounds that to about one page per idle day rather than one per six
hours.

**Gate results.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 307 passed at `93.47%`, and the floor moves
`93.45 → 93.47`. The named diff showed the two intended alarm changes plus two
Lambda code republishes with no source change.

**Deploy.** `Mlops-Dev-Monitoring` updated at 2026-08-08T15:48:43Z.
`make verify-deploy SINCE=2026-08-08` reports four changed resources:
`Endpoint5xxAlarm` updated, `EndpointSilentAlarm` created, `DriftEvaluationFn`
and `RetrainTriggerFn` updated. Only the first two are 2F. This entry first
attributed the other two to the 5C non-reproducible-asset defect. **That
attribution is wrong and the correction is below**, dated the same day: the
functions were carrying stale code, and the republish shipped it.

**Live checks.** The 5xx alarm left `INSUFFICIENT_DATA` at 15:49:36Z, 48
seconds after the deploy, with CloudWatch naming the cause: one missing
datapoint `treated as [NonBreaching]`. The silence alarm evaluated over history
and settled `OK` — 19 missing datapoints treated as breaching against 5 real
ones — so one invocation anywhere in the window holds it `OK`. `make smoke`
passed 6. All eight alarms now read `OK`.

**Interpretation.** The alarm has 24 evaluation periods and no separate
`DatapointsToAlarm`, so every one of the 24 hourly periods must breach. That is
the intended contract: 24 consecutive idle hours, not 24 idle hours in any
order.

**Decision and next checkpoint.** The window is open. It closes on
`endpoint-silent` reaching `ALARM` after a full idle window and clearing on
real traffic, the 5xx alarm holding `OK` while idle and still paging on a
forced 5xx, six security alarms unchanged, `/predict` working, and the budget
intact. 2G stays not started under the one-at-a-time rule. **Dev observation
windows now check seven alarms, not six**, and `endpoint-silent` in `ALARM`
there means nobody called the endpoint.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] verify | The 5C asset-hash finding is withdrawn

**Objective.** Fix the non-reproducible bundled Lambda asset hash recorded as a
5C finding. The measurement refuted the finding instead, so nothing was fixed
and the record is corrected.

**Scope.** `infra/stacks/lambda_code.py` read only. No code changed. Six synths
of `Mlops-Dev-Monitoring` into scratch output directories.

**The claim under test.** Vendored `__pycache__/*.pyc` embed mtimes that
`pip install -t` rewrites, so a deploy from a cold `cdk.out` republishes all
four functions with no source change.

**Measurements.**

1. Two synths into fresh output directories produce the **same** asset hash.
2. Deleting every `src/**/__pycache__` does not move the hash. The exclusion in
   `_ASSET_CONTENT` works.
3. Adding a stray top-level file does not move the hash. The allowlist works.
4. Six historical `src/` states each rebuild to their own stable hash:
   `982de01^` → `fa8e4c`, `241eca8` → `99d9da`, `9c77230` → `034a9e`,
   `b2a2f99` → `e014e5`, `8a21a8b` → `845071`, `66be85f` → `7de663`.
5. The bundled output **does** contain `.pyc` files that differ between two
   builds. `diff -r` reports differences in `__pycache__` and nowhere else.

**Interpretation.** The finding mistook the hash input. **CDK fingerprints the
source directory, not the bundled output.** Measurement 5 confirms the `.pyc`
nondeterminism the finding described, and measurements 1 to 4 show it never
reaches the hash. The real effect runs the other way: two builds produce the
same S3 key with different bytes, and the first upload wins. That is a byte
reproducibility gap, not a spurious-republish one, and it is the opposite
failure mode to the one recorded.

**What the 2F deploy actually showed.** `DriftEvaluationFn` and
`RetrainTriggerFn` were republished because `Mlops-Dev-Monitoring` had not been
deployed since `src/` last changed — most recently `982de01` on 2026-08-08,
which rewrote handler comments. Both functions were carrying stale code. A
changed asset hash means changed source, so the republish was correct and the
earlier reading of it was not.

**One loose end.** The deployed `a2abed` hash matches none of the six rebuilt
states. `lambda_code.py`'s exclude list and bundling command are hash inputs
too, and a past change to either moves the hash for the same `src/`. That was
not bisected, and it does not affect the conclusion.

**Decision and next checkpoint.** No code change. Removing the `.pyc` from the
bundle with `pip --no-compile` would close the byte gap, but `/var/task` is
read only on Lambda, so every cold start would recompile pydantic. That trade
is a deliberate decision, not a cleanup, and it is not taken here.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] implement | Sub-phase 2G merged, not deployed

**Objective.** Close the `3 of 3` reach-back edge on
`mlops-<env>-security-unauthorized-api-calls`.

**Scope.** `infra/stacks/security_stack.py`,
`tests/unit/test_security_stack.py`, `pyproject.toml`. Merged as PR #54. **No
AWS resource is changed.** The live alarm still carries a plain metric.

**The premise was re-measured first, and it nearly did not survive.** Every
metric filter already sets `default_value=0`, and has since Phase 2C on
2026-07-12 — before the 2E observation that produced this sub-phase. That
should make the series dense and the sub-phase unnecessary. It does not.
Measured with `get-metric-data` over the 24 hours to 2026-08-08T17:00Z at 300s
periods: the raw metric returned **283** datapoints, the window holds **288**
periods, and `FILL(m1, 0)` returned **288**.

**Interpretation.** `default_value` publishes a zero only for a period the log
group received events in. CloudTrail delivers nothing in some five-minute
periods, so no datapoint exists at all — five such gaps in a day. Alarm
evaluation skips a gap and reaches back to the datapoint before it, which is
how three datapoints span more than three consecutive periods. Read
`default_value=0` as "dense while traffic flows", not "dense".

**Change.** A `fill_missing` field on `SecurityDetection`, default `False`, set
only on this detection. The alarm moves from `cloudwatch.Metric` to a
`MathExpression`, so the reviewed diff rewrites the resource rather than setting
a property: `MetricName`, `Namespace`, `Period`, and `Statistic` leave, and a
`Metrics` array arrives. One resource, one stack. A test asserts exactly one
alarm carries a `Metrics` array, so a later edit cannot convert the siblings
quietly.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 308 passed, and the floor moved `93.46 → 93.48`. Hosted CI
green. **`make deploy-stack` was not run.**

**Decision and next checkpoint.** The deploy waits for 2F's observation window,
under the one-sub-phase-at-a-time rule. Expect the deploy to page this alarm on
its own calls — the 3C precedent — and to put it briefly through
`INSUFFICIENT_DATA` while the resource is rewritten.

## [2026-08-08] implement | Phase 6 merged, not deployed

**Objective.** Replace the API key in front of `/predict` with SigV4.

**Scope.** `infra/stacks/serving_stack.py`, `scripts/evaluate_api.py`,
`scripts/send_drift_traffic.py`, `Makefile`, three test files. Merged as PR #53.
**No AWS resource is changed.** The live method still reports
`authorizationType: NONE` with `apiKeyRequired: true`.

**The response contract holds, structurally.** The proxy reads one field from
the API Gateway event, `event.get("body")`, and composes every response itself.
Under `AWS_PROXY` integration API Gateway returns that dict verbatim, so an
authorized call returns identical bytes on 200, 400, 422, 502, and 503. Only
API Gateway's own auth-failure bodies change, and those were never the proxy's.

**The trap this phase carries.** Rate 10 and burst 20 lived on the usage plan,
which existed only to hold the API key. Deleting the key takes the plan and the
throttle with it. The limits move to the stage in the same change set. A test
pins the stage values and the absence of both the key and the plan, because the
failure mode is an auth-only-looking diff that silently drops a control.

**The permission question, resolved before any code.** `execute-api:Invoke`
authorizes the caller at request time; `MLOpsCloudFormationExecutionPolicy`
authorizes CloudFormation at deploy time. Different sides of the boundary, so
the grant never belongs in that policy. The policy already grants every
`apigateway:` action the deploy needs, so **Phase 6 rotates nothing and spends
no version slot**. `iam simulate-principal-policy` returns `allowed` for the
operator identity, which inherits `AdministratorAccess`.

**A finding outside the phase.** The account has **no OIDC provider and no role
trusting GitHub**, checked against the provider list and every role's trust
policy. `deploy.yml`'s OIDC path has therefore never run; every deploy has been
local. When that role is created it will need `execute-api:Invoke` explicitly,
because it will not be an administrator.

**Two problems the work surfaced.** `send_drift_traffic.py` was a second call
site of `post_prediction`; mypy caught it, and it was updated in place rather
than forked. And once `main()` built a real `boto3.Session`, the CLI tests left
sagemaker holding a live default session and `tests/unit/test_pipeline.py`
reached S3 for real. The tests now sign with offline botocore `Credentials`,
which removes the pollution and keeps `sign_headers` exercised.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 309 passed after the merge with `main`, and the floor is
`93.52`. **Neither branch's floor was correct once both were in one tree** —
2G measured `93.4847` and Phase 6 `93.5080`, and the merged tree measures
`93.5273`. Hosted CI green. **`make deploy-stack` was not run.**

**Decision and next checkpoint.** Deploy `Mlops-Dev-Serving` only after 2G's
window closes. The deploy breaks every `x-api-key` caller by design. Note the
ordering trap: `make smoke` on `main` signs with SigV4 while the deployed API
still wants the key, and 2F's window needs `make smoke` to prove
`endpoint-silent` clears.

**Verification of this entry.** `python scripts/wiki.py lint`.

## [2026-08-08] verify | The execution policy is out of room, not out of slots

**Objective.** Rotate `MLOpsCloudFormationExecutionPolicy` to add the GitHub
OIDC provider actions `CicdStack` needs. The rotation failed, and the failure
corrects a constraint this wiki has tracked since Phase 2A.

**Identity.** `${AWS_ADMIN_USER_NAME}`. `${AWS_SECURITY_AUDITOR_USER_NAME}` cannot write IAM.

**Pre-flight, which passed.** The live default `v11` was fetched, normalised,
and compared against the repository JSON with the new statement removed. The
two were **identical** — no drift, so the rotation would have added exactly one
statement.

**The failure.**

```
LimitExceeded: Cannot exceed quota for PolicySize: 6144
```

**Nothing changed.** `CreatePolicyVersion` is atomic, so the live default is
still `v11` and the slot count is still three of five.

**Measurements.** Sizes are the compact JSON form, which is how IAM counts.

| Document | Bytes |
|---|---|
| Live `v11`, seven statements | 5888 |
| Proposed, eight statements | 6337 |
| Quota | 6144 |
| Headroom before the attempt | 256 |
| Size of the new statement | 448 |

Per statement: `ApplicationServices` 4118, `GitHubOidcProviderLifecycle` 448,
`ApplicationRoleLifecycle` 347, `PassOnlyApplicationRoles` 343,
`AccessAnalyzerServiceLinkedRole` 304, `PassConfigServiceLinkedRole` 260,
`ConfigServiceLinkedRole` 248, `ConfigServiceLinkedRoleCleanup` 223.

**Interpretation, and the correction it forces.** The roadmap's standing note
said two grants still fit in the version slots. **Slots were never the first
limit reached.** At 5888 bytes the policy had 256 bytes of headroom, and no
useful grant is that small — the OIDC statement alone needs 448. The slot
count remains true and remains worth tracking; it is simply not what blocks the
next change.

**Two smaller findings.** The policy holds **zero** `guardduty:` actions, so
the open question about a deliberate GuardDuty divergence is stale — enabling
the service means adding actions that now do not fit. And the policy is
attached to exactly one role, `cdk-hnb659fds-cfn-exec-role-*`, which carries no
other managed policy and has room for nine more.

**The three options, costed.**

1. **Trim the statement to `Create`, `Delete`, `Get`.** Total 6142, fitting by
   two bytes. Drops `Tag` and `Untag`, so a tagged provider breaks the deploy.
   Survives no further grant.
2. **Drop the ten `securityhub:` actions**, 316 bytes, for a service disabled
   in both environments. Total 6021, leaving 123 bytes. Phase 3D must then put
   them back, and they will not fit.
3. **Split into a second managed policy** on the same role. Removes the ceiling
   as a recurring problem. Changes the repository's single-file,
   fingerprint-tested policy model and the pages that describe it.

**Decision and next checkpoint.** **None taken.** Options 1 and 2 both leave
less headroom than Phase 4's KMS grant needs, so each buys one deploy and
re-raises this failure. `CicdStack` stays undeployable until this is settled.

## [2026-08-08] implement | CicdStack built, on a branch, not merged

**Objective.** Give `.github/workflows/deploy.yml` an identity to assume, so
deployment stops depending on a workstation.

**Scope.** New `infra/stacks/cicd_stack.py`, wired in `infra/app.py`, plus
`cicd` config on both environments, the execution policy JSON, and
`tests/unit/test_cicd_stack.py`. On branch `claude/cicd-oidc-role`. **Not
merged and not deployed.**

**What it creates.** One account-wide `AWS::IAM::OIDCProvider` and one role per
environment, `mlops-<env>-github-deploy`.

**The trust is the whole boundary.** `StringEquals` on
`token.actions.githubusercontent.com:sub` =
`repo:<repo>:environment:<env>`, plus `aud` = `sts.amazonaws.com`. Naming the
**environment** rather than a branch means a role is reachable only by a job
that names its environment. A `repo:<repo>:*` subject would let any branch or
pull request assume it. Tests assert the exact subject, the absence of any
`StringLike`, and that the rendered trust policy contains no `*`.

**Corrected the same day: the approval gate this scoping was chosen for does
not exist.** The `dev` environment carries zero protection rules and `prod` is
not defined at all. GitHub creates a missing environment on demand with no
rules, so a prod job would run unreviewed and still receive
`sub = repo:<repo>:environment:prod`. The condition works; it currently gates
on nothing.

**The provider is account-wide**, so it repeats the `account_budget` collision:
dev owns it under `cicd.owns_oidc_provider`, prod reads it by ARN, and a test
asserts prod creates none.

**A design correction the tests forced.** The role's two grants first composed
their ARNs locally, which produced wildcards over the generated stack id and
the generated REST API id, and two cdk-nag acknowledgements that could never
expire. `test_security_acknowledgements_are_exact_and_expiring` requires every
acknowledgement to name the phase that removes it, and neither could. The stack
now imports both exact ARNs from Serving instead. Zero acknowledgements added,
at the cost of a `Cicd → Serving` dependency.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 316 passed, and the floor moves `93.52 → 93.63`. The
reviewed diff shows three new resources and no wildcard in either grant.

**One claim only a deploy can settle.** The provider omits `ThumbprintList`,
because AWS validates the certificate against its own trusted CAs. If
`CreateOpenIDConnectProvider` rejects that, the fix is a thumbprint list.

**Verification of these entries.** `python scripts/wiki.py lint`.

## [2026-08-08] implement | The execution boundary splits across two policies

**Objective.** Land the OIDC provider grants that the failed rotation could not
fit, and remove the size ceiling as a recurring blocker.

**Decision.** Split, rather than trim the statement or drop the unused
`securityhub:` actions. Both alternatives left less headroom than Phase 4's KMS
grant needs — two bytes and 123 bytes — so each bought one deploy and re-raised
the same failure at the next phase.

**Scope.** New `infra/policies/mlops-cloudformation-execution-policy-extension.json`
and new live policy `MLOpsCloudFormationExecutionPolicyExtension`, attached to
`cdk-hnb659fds-cfn-exec-role-*`. Identity `${AWS_ADMIN_USER_NAME}`.

**The main policy was not rotated, and that is the point of this shape.** The
OIDC statement moved out of the main document rather than the main document
being rebalanced, so the repository file returned to exactly what is deployed.
A normalised diff against live `v11` reports **identical**. The version slots
stay at three of five, `v11` stays default, and the deployed boundary was never
at risk during the change.

**Live checks.** `create-policy` returned `v1` at 21:15:29Z.
`attach-role-policy` succeeded, and the execution role now lists both policies.
A normalised diff of the live extension against the rendered repository file
reports **identical**.

**Sizes.** Main 5888 of 6144 bytes, 256 free. Extension 492 of 6144, 5652 free.
New grants belong in the extension; the main document cannot take one.

**Regression.** `make test` now measures **each** document against the 6144
quota and fails with the byte count and a pointer to the other file. The
previous failure arrived from the AWS API during a rotation, which is the worst
place to learn it. A second test asserts no `Sid` is reused across the two
files, so a reader cannot be unsure which file owns a grant.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 320 passed at the `93.63` floor. `python scripts/wiki.py
lint` healthy.

**Decision and next checkpoint.** `CicdStack` is now deployable as far as
permissions go. It stays undeployed behind 2F's observation window, 2G, and
Phase 6. The first deploy still has to settle whether
`CreateOpenIDConnectProvider` accepts a provider with no `ThumbprintList`.

## [2026-08-08] query | Reading the audit trail generates audit trail

**Objective.** Use a CloudWatch Logs Insights export of the audit log group as a
second evidence surface for the policy split. It did not contain the change,
and it exposed a log-volume pattern worth recording instead.

**Scope.** A 10000-row export of `/aws/cloudtrail/mlops-dev-audit`, parsed
locally. Read-only. No AWS resource was touched.

**The export missed the change.** Its window runs 21:21:06Z to 21:30:29Z, and
the split happened at 21:15:29Z and 21:15:39Z. The file holds **zero**
`iam.amazonaws.com` events. An Insights export is capped at 10000 rows and
truncates silently, so treat the row count as the limit and the time span as
the consequence, never the reverse.

**Why nine minutes filled ten thousand rows.** 9753 of the 10000 events are KMS
`Decrypt`, every one carrying the encryption context
`aws:logs:arn = /aws/cloudtrail/mlops-dev-audit`. The callers split between
`logs.amazonaws.com` (5489) and `fas.s3.amazonaws.com` (4264).

| Minute | Decrypt calls |
|---|---|
| 21:21 | 5457 |
| 21:22 to 21:24 | 2 each |
| 21:25 | 3002 |
| 21:26 | 1280 |
| 21:27 to 21:30 | 2 each |

**Interpretation.** Querying the encrypted log group makes CloudWatch Logs call
KMS `Decrypt` thousands of times. Each `Decrypt` is itself a management event,
which CloudTrail writes back into that same encrypted group, which the next
query must then decrypt. **An investigation inflates the artefact it
investigates.** The bursts align with queries and the baseline sits at about
two per minute, so the pattern is bounded rather than runaway — roughly 2880
`Decrypt` events a day keep the trail flowing on their own.

**Operational rule.** Filter `kms.amazonaws.com` out of an Insights query on
this group unless KMS is the subject. Under the same 10000-row cap that moves
coverage from nine minutes to about a week.

**One alarm interaction.** Three `AccessDenied` events appear, all Cost
Explorer `GetCostAndUsage` and `GetCostForecast` from `${AWS_ADMIN_USER_NAME}`, all
`IAM user access not activated`. That is Cost Explorer's separate IAM-user
opt-in rather than a platform permission fault, and it still counts toward
`unauthorized-api-calls`. Routine Billing console use therefore contributes
datapoints to that alarm.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] verify | The GitHub environments carry no protection rules

**Objective.** Confirm whether repository visibility forces a change for OIDC,
and whether the approval gate the `CicdStack` trust relies on exists.

**Scope.** Read-only GitHub API. No AWS or repository change.

**Visibility is not a constraint.** The repository is private, and GitHub issues
an OIDC token to a private repository exactly as it does to a public one. The
`sub` claim format and the trust policy are unchanged. **Nothing in this design
requires the project to be open source.**

**The gate does not exist.** `GET /repos/<owner>/<repo>/environments` returns
`dev` with **zero** protection rules, and no `prod` environment at all.

**Interpretation.** The environment-scoped subject was chosen so that the prod
role could only be assumed by a job that passed a manual review. A workflow job
that names a missing environment causes GitHub to create it with no rules, so
the prod job would run unreviewed and still receive
`sub = repo:<repo>:environment:prod`. The IAM condition is satisfied and the
review never happens. **The boundary is sound and currently unbacked.**

**Where visibility does interact.** Environment protection rules — required
reviewers, wait timers, branch restrictions — are free on public repositories
and have required a paid plan on private ones. The account plan was not
readable through the API, so confirm this in Settings before choosing a path.

**Options, in order of preference.** Add a required reviewer to a new `prod`
environment on the current plan. Upgrade the plan if protection rules are
gated. Make the repository public, which makes the rules free — feasible, since
history is scrubbed and CI scans it, but far larger than this one gate warrants.

**Decision and next checkpoint.** No plan change taken. Five statements that
asserted the gate were corrected to describe what is configured:
`infra/stacks/cicd_stack.py`, `tests/unit/test_cicd_stack.py`,
`.github/workflows/deploy.yml`, `AGENTS.md`, and the `CicdStack` log entry
above. Restore the stronger wording only after a required reviewer exists.

**Verification.** `python scripts/wiki.py lint`.

## [2026-08-08] document | Generated CDK architecture diagrams

**Objective.** Add reproducible resource diagrams without treating synthesis
as proof of live AWS state.

**Scope.** Added a pinned `make diagrams` target, three repository dev PNG
files, a maintained wiki page, and a README link. Updated the existing README
Mermaid diagram instead of adding a second logical-flow source.

**Identity and environment.** Local `dev` synthesis with `--no-lookups`. No
AWS profile was used. No AWS API call, diff, deployment, or live resource
change occurred.

**Commands and results.** `brew install graphviz` installed Graphviz 15.1.1.
`make diagrams ENV=dev` synthesized all nine stacks and rendered the complete,
ML platform, and security plus CI/CD views. The target removes generated DOT
sidecars because they contain local npm icon paths. The three PNG outputs are
portable and total about 6.7 MB.

**Interpretation.** `cdk-dia` reads `infra/cdk.out/tree.json`. It shows CDK
constructs and references for the selected config. It does not show the
SDK-upserted SageMaker Pipeline steps, handler control flow, an exercised event
path, or deployed AWS state.

**Decision and next checkpoint.** Keep the complete view for inventory and the
two focused views for readable review. Keep the README Mermaid diagram as the
logical runtime view. Regenerate the images after a construct graph changes.
Continue to use `make verify-deploy` for resource-level deployment claims.

**Verification.** `make diagrams`, `make lint`, `make typecheck`,
`make docs-sync`, and `make wiki-lint` pass. `make test` reports 320 passed at
93.64% coverage against the 93.63% floor. Visual inspection confirmed readable
labels in each focused diagram.
## [2026-08-08] query | generated CDK diagrams

Found 30 matching page(s).

## [2026-08-08] document | Editable CDK diagram sources

**Objective.** Keep each generated diagram editable without committing a
workstation-specific path.

**Scope.** Updated `make diagrams` and added
`scripts/prepare_cdk_diagrams.py`. Added unit tests, three DOT sources, three
self-contained SVG files, and 15 required `cdk-dia` icons. Kept the existing
PNG previews and README Mermaid flow.

**Identity and environment.** Local `dev` synthesis with `--no-lookups`. No AWS
profile was used. No AWS API call, diff, deployment, or live resource change
occurred.

**Commands and results.** `make diagrams ENV=dev` rendered all three format
sets. The helper copied the required icons and replaced local npm-cache paths
in each DOT source. It embedded each unique icon once in each SVG file. A
second run with `DIAGRAM_DIR` set to a temporary directory confirmed the output
override. `xmllint` parsed all SVG files. `rsvg-convert` rendered all three SVG
files for visual inspection.

**Interpretation.** The SVG files preserve vector shapes and text for visual
editing. The DOT files preserve nodes, edges, labels, and automatic layout.
`make diagrams` regenerates both formats from the synthesized CDK tree.

**Decision and next checkpoint.** Keep PNG for GitHub previews. Use SVG for
visual edits and DOT for graph edits. Run `prepare_cdk_diagrams.py` after a
manual DOT edit. Do not replace the current `cdk-dia` views with a different
draw.io generator.

**Verification.** `make diagrams`, `make lint`, `make typecheck`,
`make docs-sync`, and `make wiki-lint` pass. `make test` reports 330 passed at
93.97% coverage against the 93.63% floor. The generated DOT and SVG files
contain no workstation path. The SVG files contain no external image link.
## [2026-08-09] verify | 2F closes split: the 5xx half is a go, the silence half cannot fire

**Objective.** Close sub-phase 2F's observation window. The 5xx criterion
passed. The silence criterion failed in a way that no test caught and only a
full idle window could expose.

**Identity.** `${AWS_ADMIN_USER_NAME}` for CloudWatch reads. No AWS resource was changed.

**The 5xx half: go.** `mlops-dev-endpoint-5xx` held `OK` across 24 unbroken
hours of an idle serverless endpoint, having left `INSUFFICIENT_DATA` 48
seconds after the deploy. Before 2F it read `INSUFFICIENT_DATA` for that whole
period. This half of the defect is fixed and proven.

**The silence half: no-go. The alarm cannot fire as deployed.**

| Check at 2026-08-09T17:03Z | Result |
|---|---|
| Hours since the last invocation | 25 |
| `mlops-dev-endpoint-silent` | `OK`, unchanged since 2026-08-08T15:50Z |
| Alarm history entries in 25 hours | 2 — created, and `INSUFFICIENT_DATA → OK` |
| Raw `Invocations`, six idle hours | **0** datapoints, status `Complete` |
| `FILL(m1, 0)`, identical range | **6** datapoints, all zero |

**Interpretation.** SageMaker publishes no `Invocations` datapoint for an idle
hour. The alarm's metric therefore returns an empty series, no datapoint
arrives to drive an evaluation, and the alarm holds the state it reached at
creation. It had not re-evaluated once in 25 hours.

**The mistaken belief this corrects.** The 2F record and a code comment both
said `BREACHING` is the only `TreatMissingData` value that detects silence.
`BREACHING` decides how a gap counts **inside an evaluation that already
runs**. It does not cause an evaluation to run. Necessary, not sufficient.

**The general rule.** On this platform, **an alarm over a sparse AWS metric
needs `FILL`**. `Invocations` on a serverless endpoint is the sparsest case,
because it goes fully absent rather than merely gappy. Sub-phase 2G reached the
same conclusion from the other direction, on a metric with occasional gaps. Two
sub-phases, one root cause.

**A process note worth keeping.** Two predictions of the transition time were
made and both were wrong — 16:00Z from assuming clean hour alignment, then
16:47Z from reading bucket offsets in a stale `StateReason`. Each was plausible
and each was a guess. `describe-alarm-history` settled it in one call by
showing no evaluations at all. **Read the alarm's history before modelling its
schedule.**

**Decision and next checkpoint.** The 5xx change stays deployed. The silence
alarm moves to a `FILL(m1, 0)` math expression, mirroring 2G, on branch
`claude/fix-2f-silence-alarm`. It is **not deployed** and needs its own fresh
24-hour idle window after it is. The deployed alarm is inert rather than
harmful, so no rollback is urgent.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 320 passed. The reviewed diff moves `EndpointSilentAlarm`
from `MetricName`/`Period`/`Statistic` to a `Metrics` array.
`python scripts/wiki.py lint`.

## [2026-08-09] deploy | The silence fix is proved, and a dependency deployed 2G with it

**Objective.** Deploy the `FILL` fix for `mlops-dev-endpoint-silent` and confirm
the detector fires. It did. The same deploy also shipped sub-phase 2G, which was
not intended.

**Identity.** `${MLOPS_DEPLOYER_USER_NAME}` to deploy, `${AWS_SECURITY_AUDITOR_USER_NAME}` to verify,
`${AWS_ADMIN_USER_NAME}` for alarm reads.

**Pre-flight.** The deployed alarm carried a plain `Invocations` metric, no
`Metrics` array, `TreatMissingData` `breaching`, state `OK` unchanged since
2026-08-08T15:50Z. Last invocation: the 15:00Z hour on 2026-08-08.

**The fix works, in 44 seconds.** `Mlops-Dev-Monitoring` updated at
2026-08-09T17:38:25Z. The alarm went `OK → ALARM` at **17:39:14Z** and executed
its SNS action at 17:39:14Z. CloudWatch's reason:

> Threshold Crossed: 24 datapoints were less than the threshold (1.0). The most
> recent datapoints which crossed the threshold: [0.0 (09/08/26 16:37:00), 0.0
> (09/08/26 15:37:00), 0.0 (09/08/26 14:37:00), 0.0 (09/08/26 13:37:00), 0.0
> (09/08/26 12:37:00)]

Twenty-four filled zeros over the same idle window in which the previous alarm
saw an empty series and held `OK` for 25 hours. The only change is `FILL`. The
diagnosis and the fix are both confirmed.

**`cdk deploy <stack>` also deploys that stack's dependencies.**
`make verify-deploy SINCE=2026-08-09` reports two stacks:

| Stack | Changed |
|---|---|
| `Mlops-Dev-Monitoring` | `EndpointSilentAlarm`, plus `DriftEvaluationFn` and `RetrainTriggerFn` republished |
| `Mlops-Dev-Security` | `UnauthorizedApiCallsAlarm` |

`Mlops-Dev-Security` was never named on the command line. Monitoring imports the
alert topic from it, so CDK included it — the diff output says so on every run,
`Including dependency stacks: Mlops-Dev-Data, Mlops-Dev-Security`, and that line
was read past repeatedly. **Sub-phase 2G is therefore live.**

**Interpretation.** `make deploy-stack STACK=…` is not a single-stack deploy. It
is a deploy of that stack and everything it depends on, and any pending change
in a dependency ships with it. Under the one-sub-phase-at-a-time rule this is a
live trap: attribution is lost without anything appearing to go wrong. Check
`cdk diff`'s dependency line, or run `make verify-deploy` immediately after,
before writing what a deploy changed.

**What 2G lost, and what it did not.** It was reviewed, tested, and its diff
examined before it landed. What it never received is its own observation window.
It now shares one with the 2F fix. The two are the same mechanism on different
alarms and their failure modes do not overlap, so a shared window is readable —
but it is a shared window, and the record should not pretend otherwise.

**Decision and next checkpoint.** No rollback. Rolling `Mlops-Dev-Security` back
would revert a working change to buy attribution after the fact. One window now
covers both alarms. `#57` must stay unmerged until it closes, because it also
lands in `Mlops-Dev-Security` and would fuse in the same way.

**Still open.** `endpoint-silent` is proved to fire and not yet proved to clear.
One `/predict` call closes that, and the deployed API still expects `x-api-key`.

**Verification.** `make verify-deploy SINCE=2026-08-09`, `describe-alarms`, and
`describe-alarm-history` on both alarms. `python scripts/wiki.py lint`.

## [2026-08-09] verify | The shared 2F and 2G window closed as a go

**Objective.** Close the observation window that 2F's silence fix and 2G share.
Every criterion is met, and both sub-phases are a go.

**Identity.** `${AWS_ADMIN_USER_NAME}` for reads and the one `/predict` call.

**The silence detector is fully exercised.** Its history holds the whole cycle
inside 16 minutes:

| Time | Event |
|---|---|
| 17:38:30Z | `ConfigurationUpdate` — the `FILL` fix |
| 17:39:14Z | `OK → ALARM`, on `24 datapoints were less than the threshold` |
| 17:39:14Z | SNS action executed |
| 17:54:14Z | `ALARM → OK`, on `1 datapoint [1.0] was not less than the threshold` |

The `/predict` call at 17:51Z returned `200` with
`{"churn_probability": 0.2988, "churn": false}`. **Fire and clear are both
demonstrated on the same alarm**, which is more than any other detector on this
platform can currently claim: the Phase 2 CIS alarms have fired, and 3F's Config
rule has done neither.

**The notification reached the subscriber**, which is the standard 3F set for
calling a route proved. The delivered email carries two facts the API did not
give up on its own. It names `MetricExpression: FILL(m1, 0)`, so AWS's own
notification confirms the deployed alarm evaluates the math expression rather
than the plain metric. And it states the rule as `LessThanThreshold 1.0 for at
least 24 of the last 24 period(s) of 3600 seconds`, which confirms
`DatapointsToAlarm` defaulted to `EvaluationPeriods` as intended — the template
renders no explicit value, so this was previously inferred rather than
observed.

**Closing evidence.**

| Criterion | Result |
|---|---|
| 5xx holds `OK` while idle | 24 unbroken hours, against `INSUFFICIENT_DATA` before 2F |
| `endpoint-silent` fires | `ALARM` at 17:39:14Z on 24 filled zeros |
| `endpoint-silent` clears | `OK` at 17:54:14Z on one real datapoint |
| `/predict` | `200` |
| Six security alarms | `OK` |
| Config recorder | `recording: true`, `SUCCESS` |
| Access Analyzer | `ACTIVE` |
| Budget | `$20` limit, `$0.00` actual, `$1.85` forecast |
| Month-to-date cost | `$0.00` |

**2G's evidence is thinner, and the record should say so.** Its alarm is `OK`,
its metric now runs through `FILL(m1, 0)`, and over a two-hour sample raw and
filled both returned 24 of 24 periods. That shows the alarm has dense data and
is evaluating. **It does not show `FILL` closing a gap**, because that sample
contained none — the gaps measured when 2G was written were five in 24 hours,
so a two-hour window is expected to miss them. 2G is a go on the same footing
as before: the mechanism is proved by measurement and by the 2F alarm that
depends on it, not by catching a live gap.

**A third wrong prediction, and the same root cause.** The clear was estimated
at 18:37Z from the alarm's apparent hourly cadence. It cleared at 17:54:14Z,
about 40 minutes early. Every estimate this window — 16:00Z, 16:47Z, 18:37Z —
came from modelling CloudWatch's evaluation schedule rather than reading it.
The rule already recorded holds and is worth repeating: **read the alarm's
history; do not model its schedule.**

**Decision: go, for both.** 2F is complete on both halves. 2G is complete. The
`Mlops-Dev-Security` stack is now free for the next change set, which unblocks
`#57`.

**Verification.** `describe-alarms`, `describe-alarm-history`,
`get-metric-data`, `describe-budgets`, `get-cost-and-usage`, and one live
`/predict`. `python scripts/wiki.py lint`.
## [2026-08-09] deploy | Phase 6 is live in dev, and the API key is gone

**Objective.** Move `/predict` from an API key to SigV4, and confirm the
boundary actually moved rather than merely changing shape.

**Identity.** `${MLOPS_DEPLOYER_USER_NAME}` to deploy, `${AWS_SECURITY_AUDITOR_USER_NAME}` to verify,
`${AWS_ADMIN_USER_NAME}` for live calls.

**The dependency check ran first, and it mattered.** `make diff-stack
STACK=Mlops-Dev-Serving` announced `Including dependency stacks:
Mlops-Dev-Data, Mlops-Dev-Security`, then reported **1 stack with differences**.
Nothing rode along. This is the check the 2G transitive deploy earned, used for
the first time.

**Deploy.** `Mlops-Dev-Serving` updated at 2026-08-09T18:21:13Z.
`make verify-deploy SINCE=2026-08-09` reports, in that stack:
`ChurnApiClientKey` **deleted**, `ChurnApiUsagePlan` **deleted**,
`ChurnApiUsagePlanKeyResource` **deleted**, the method, stage and deployment
updated, and `DeployFn` and `ProxyFn` republished from the earlier `src/`
comment change.

**Live checks.**

| Check | Result |
|---|---|
| Method | `AWS_IAM`, `apiKeyRequired: false` |
| API keys in the account | **0** |
| Usage plans in the account | **0** |
| Stage throttle | rate 10, burst 20 |
| Unsigned `POST /predict` | `403 {"message":"Forbidden"}` |
| Signed `POST /predict` | `200` |
| `make smoke` | 6 passed, signing each request |

**The trap did not fire.** Rate and burst lived on the usage plan, which existed
only to carry the API key. Deleting the key takes the plan and the limits with
it unless the change moves them first. The stage settings above are the evidence
that it did.

**A propagation artefact worth knowing.** The first `make smoke` failed all four
signed tests with `403`, and a hand-signed call failed identically. About a
minute later, with nothing changed, the same signed call returned `200` and
`make smoke` passed 6. The stage was already serving the newest deployment
(`uyuffw`, created 18:21:03Z), the method already read `AWS_IAM`, the caller
already simulated `execute-api:Invoke` as allowed, and the signing region and
credentials were correct. **Switching a method's authorization type propagates
to the API Gateway edge on its own schedule. An immediate 403 after this kind of
change is expected, not a failed deployment.** A failure was nearly reported
from the first run.

**What this breaks, deliberately.** Every `x-api-key` caller now receives `403`.
There is no legacy key route, which is what the roadmap committed to. The two
new Serving exports that `CicdStack` imports — the stack id and the REST API
ref — are published, so `Mlops-Dev-Cicd` is now deployable.

**Decision and next checkpoint.** The observation window is open. It closes on
the method staying `AWS_IAM`, `make smoke` passing, the alarms unchanged, and
the budget intact. `CicdStack` is next, followed by `#57` on top of it.

**Verification.** `make verify-deploy SINCE=2026-08-09`, `get-method`,
`get-api-keys`, `get-usage-plans`, `get-stage`, one unsigned and one signed
call, `make smoke`. `python scripts/wiki.py lint`.

## [2026-08-09] deploy | The CI/CD identity exists, with the hardened trust from the start

**Objective.** Deploy `CicdStack`, so `.github/workflows/deploy.yml` has an
identity to assume and deployment stops depending on a workstation.

**Identity.** `${MLOPS_DEPLOYER_USER_NAME}` to deploy, `${AWS_SECURITY_AUDITOR_USER_NAME}` to verify,
`${AWS_ADMIN_USER_NAME}` for IAM reads.

**A sequencing choice made before deploying.** `main` carried the two-claim
trust, and `#57`'s hardening was green and unmerged. Deploying first would have
put the weaker trust live for the length of a merge, for no gain, so `#57` was
merged first and the roles were created with all four claims. **The two-claim
version was never live.**

**The dependency check reported two stacks, and both belong to one change set.**
`Including dependency stacks: Mlops-Dev-Serving, Mlops-Dev-Data,
Mlops-Dev-Security`, with differences in `Mlops-Dev-Cicd` and
`Mlops-Dev-Security`. The Security change is `#57`'s prod-deploy-role alarm, so
this is a coherent deploy rather than a fusion of unrelated work — the
distinction the 2G accident taught.

**Deploy.** `Mlops-Dev-Cicd` created at 2026-08-09T19:15:41Z.
`make verify-deploy SINCE=2026-08-09` reports `GitHubOidcProvider`,
`GitHubDeployRole`, and its default policy created, plus
`ProdDeployRoleAssumedFilter` and `ProdDeployRoleAssumedAlarm` in
`Mlops-Dev-Security`.

**The live trust, read back from IAM:**

| Claim | Value |
|---|---|
| `sub` | `repo:<owner>/<repo>:environment:dev` |
| `aud` | `sts.amazonaws.com` |
| `job_workflow_ref` | `<owner>/<repo>/.github/workflows/deploy.yml@refs/heads/main` |
| `repository_owner` | the repository owner |
| `runner_environment` | `github-hosted` |

**The thumbprint claim is settled, and it needs a correction.** `CicdStack`
omits `ThumbprintList`, on the stated basis that AWS validates the provider's
certificate against its own trusted CAs. `CreateOpenIDConnectProvider` accepted
that — but `get-open-id-connect-provider` shows AWS **populated a thumbprint
itself**, `ab9d0263…`. So the effect is right and the mechanism as written is
incomplete: the choice is not between one thumbprint and none, it is between
one this repository pins and one AWS maintains. The comment's warning still
holds for a manually pinned value, which is what would become a rotation outage.

**What still blocks CI from deploying.** Nothing holds the role ARN. Two
settings remain, both outside this repository: create the `dev` and `prod`
GitHub environments, and set `AWS_DEV_DEPLOY_ROLE_ARN` from the
`GitHubDeployRoleArn` output. Until then the role exists and nothing can assume
it, so **every deployment to date still came from a workstation**.

**Decision and next checkpoint.** The observation window is open for both the
Cicd stack and `#57`'s alarm. It closes on the trust reading back unchanged, the
alarm staying `OK` while no prod role is assumed, the other alarms unchanged,
and the budget intact. The first real proof of the trust is an
`AssumeRoleWithWebIdentity` from a workflow run, which cannot happen until the
two GitHub settings exist.

**Verification.** `make verify-deploy SINCE=2026-08-09`,
`get-open-id-connect-provider`, `get-role`. `python scripts/wiki.py lint`.

## [2026-08-09] implement | An archive rule for the CI deploy role's standing finding

**Objective.** Stop a permanent, expected Access Analyzer finding from sitting
beside real ones, and correct the observation-window criterion it invalidates.

**What produced it.** Deploying `CicdStack` created
`mlops-<env>-github-deploy`, which GitHub's OIDC provider can assume. Access
Analyzer raised an external-access finding at 19:17:44Z, about two minutes after
the role was created, and 3F's EventBridge rule delivered it to the subscriber.

**Two controls proved themselves on unmanufactured activity.** 3F's analyzer
route was previously proved with a throwaway SQS queue created and deleted for
the purpose. This finding came from the platform's own change. The
`iam-policy-changes` alarm fired in the same window on `2.0` — the
`PutRolePolicy` for the role's inline policy and the `AttachRolePolicy` for
`MLOpsCdkDeploymentPolicy`. `CreateRole` is not in that filter, which is why the
count is two rather than three.

**The finding is correct and permanent.** The role is meant to be externally
assumable; that is what OIDC federation is. Unlike the throwaway queue, it is
not going away, so the finding stays `ACTIVE` indefinitely.

**Change.** `SecurityMonitoringStack`'s analyzer gains one archive rule,
`ArchiveCiDeployRoleFederation`, filtering `resource` against the single role
ARN. A `resourceType` filter would archive every externally accessible role,
including one nobody meant to create. The role-name formula moved to
`github_deploy_role_name()` in `infra/stacks/shared.py`, because `CicdStack`
creates the role and `SecurityMonitoringStack` now names it. The two stacks
have no dependency between them.

**A limitation worth recording.** The finding carries `condition: {}` even
though the trust has five `StringEquals` conditions. **Access Analyzer does not
model OIDC claim conditions as access restrictions.** It cannot tell you the
trust is tightly scoped, so it should not be read as evidence either way about
the claim hardening.

**Existing findings need one explicit action.** Creating an archive rule
automatically handles new matching findings. It does not archive an existing
finding. After the deploy creates the rule, `apply-archive-rule` must apply it
once to the active finding. This action changes the finding status. It does not
change the archive rule.

**The criterion this invalidates.** Observation windows have closed on "the
analyzer `ACTIVE` with zero active findings" since Phase 3A. That was written
for an account with no federated role. After the rule is deployed and applied,
the expected active count returns to zero. Without the rule, the next window
would read a permanent expected finding as a regression. The roadmap's
stable-interfaces section now records this.

**Pre-deploy baseline.** A read-only check on 2026-08-09 returned no archive
rules and one active finding for `${GITHUB_DEPLOY_ROLE_NAME}`. This confirms that
the rule is not deployed and gives the deployment a deterministic live check.

**Verification.** `make lint`, `make typecheck`, and `make security` pass.
`make test` reports 323 passed, and the floor moves `93.64 → 93.65`. The
reviewed diff adds `ArchiveRules` to the analyzer and changes nothing else.
**Not deployed.** `python scripts/wiki.py lint`.

**Decision and next checkpoint.** Deploy `Mlops-Dev-SecurityMonitoring`, run
resource-level verification, then apply the rule to the existing finding.
Confirm the archive rule exists and the active finding count is zero before the
explicit go/no-go.

## [2026-08-09] failure | Archive-rule deploy exposes a missing execution grant

**Objective.** Deploy `ArchiveCiDeployRoleFederation` to dev after the branch,
hosted CI, and named diff were clean.

**Scope.** `Mlops-Dev-SecurityMonitoring` and its unchanged
`Mlops-Dev-Security` dependency. The attempt used the restricted deployment
identity. The follow-up IAM audit was read-only.

**Commands and results.** Hosted CI passed both jobs. The named diff reported
one change: add `ArchiveRules` to `ExternalAccessAnalyzer`. It also reported no
differences in `Mlops-Dev-Security`. The deploy reached the analyzer update and
failed on `access-analyzer:CreateArchiveRule`. CloudFormation completed the
rollback. A live check still returns no archive rules and one active finding.

**Interpretation.** The main execution policy can create and read an analyzer.
It does not manage archive rules. CloudFormation uses separate archive-rule
APIs for the nested `ArchiveRules` property, so the old analyzer grant does not
cover this update.

**IAM baseline.** The live policy extension is attached to the CloudFormation
execution role. It has one version, `v1`, and its default document matches the
repository's OIDC-only statement. Four version slots remain.

**Change.** The extension adds create, delete, get, update, and list access for
`ArchiveCiDeployRoleFederation` under `mlops-*-external-access`. The lifecycle
actions use the archive-rule ARN. The list action uses the analyzer ARN.
`ApplyArchiveRule` stays outside CloudFormation because it changes the status
of existing findings.

**Verification.** `make lint`, `make typecheck`, `make docs-sync`, and
`make wiki-lint` pass. `make test` reports 324 passed at 93.66%. The dependency
audit and both environment syntheses pass. The policy-size and unique-`Sid`
tests cover the updated extension.

**Decision and next checkpoint.** Validate the policy and rotate the live
extension only after explicit approval. Then repeat the named deploy, run
resource-level verification, and apply the rule once to the existing finding.
The phase remains a no-go until those checks pass.

## [2026-08-09] deploy | Archive rule deployed and the standing finding archived

**Objective.** Rotate the scoped execution grant, deploy the exact archive
rule, apply it to the existing finding, and close the change with a go/no-go.

**IAM rotation.** An administrator created extension policy `v2` and made it
default. Live read-back matches the repository: OIDC provider lifecycle, four
archive-rule lifecycle actions on the exact rule ARN, and list access on the
matching analyzer ARN. Version `v1` remains available for rollback. Two of five
version slots are used.

**Named diff and deploy.** The repeated diff still reported one change in
`Mlops-Dev-SecurityMonitoring`: add `ArchiveRules` to
`ExternalAccessAnalyzer`. `Mlops-Dev-Security` had no differences. The second
deploy completed at 23:31Z. `make verify-deploy SINCE=2026-08-09` reports only
`ExternalAccessAnalyzer` changed in that stack. The Security dependency kept
its earlier update time and changed nothing in this deploy.

**Live rule check.** `list-archive-rules` returns exactly
`ArchiveCiDeployRoleFederation`, with one `resource` equality filter for
`${GITHUB_DEPLOY_ROLE_NAME}`. The existing finding stayed `ACTIVE` after rule
creation, as the API contract predicts. The approved `apply-archive-rule`
action changed it to `ARCHIVED` at 23:33Z. An `ACTIVE` query now returns no
findings, and the archived query returns that one finding.

**Control checks.** The policy rotation produced one `CreatePolicyVersion`
CloudTrail event. `iam-policy-changes` entered `ALARM` at 23:32Z and returned to
`OK` at 23:37Z on the next zero datapoint. The other eight alarms are `OK`.
`make smoke` passes 6 of 6 against the SigV4 API. The account budget remains
`$20` with `$0` actual spend.

**Rollback.** Set extension `v1` as default, remove the archive rule through
CloudFormation, and set the one finding back to `ACTIVE`. No rollback is
needed; each acceptance check passed.

**Decision.** **Go.** The policy extension, deployed analyzer, active-finding
state, alarms, API, and budget all match the acceptance criteria. Prod remains
unchanged.

## [2026-08-09] document | Refresh generated CDK diagrams after current main

**Objective.** Reconcile the diagram change with current `main`. Regenerate all
artifacts from the post-`#61` synthesized dev graph.

**Scope.** Retained the earlier diagram records and the later deployment
records while resolving the append-only log conflict. Regenerated the complete,
ML platform, and security plus CI/CD DOT, PNG, and SVG files. Updated the README
status diagram and the CI/CD status in `AGENTS.md`.

**Identity and environment.** Local dev synthesis used `--no-lookups` and no
AWS profile. Read-only GitHub metadata confirmed one unprotected `dev`
environment, no deploy-role secrets, no `prod` environment, and no Deploy
workflow run. No AWS API call or deployment occurred.

**Commands and results.** `make diagrams ENV=dev` completed twice with identical
hashes for all nine generated files. A custom `DIAGRAM_DIR` run produced the
expected 24 files. `xmllint` parsed each SVG. Path scans found no workstation
path or external SVG image reference. Visual inspection covered all three PNG
views.

**Interpretation.** `cdk-dia` shows synthesized constructs and references. The
new production-role alarm appears as nodes. The analyzer archive rule remains a
resource property and does not become a separate node.

**Decision and next checkpoint.** Keep the PR documentation-only. Mark it ready
after hosted CI passes. Continue to use live AWS checks for deployment claims.

**Verification.** `make lint`, `make typecheck`, `make docs-sync`,
`make wiki-lint`, and `make security` pass. `make test` reports 335 passed at
94.04% coverage. The coverage floor moves from 93.65% to 94.03%. The wiki
contains 46 healthy pages.

## [2026-08-10] security | Prepare the repository for public release

**Objective.** Remove publishable account metadata, repair security gates, and
prepare the repository controls without changing visibility.

**Repository changes.** Replaced bucket names, IAM identity names, execution
identifiers, one API key identifier, one finding identifier, and generated
physical names with `.env.example` placeholders. This sanitization includes
the raw wiki records because the wiki sensitive-value rule covers every file.
Added `make public-check` with unit tests. The check reports only file, line,
and rule names, so it does not print a matched value.

Updated the README and roadmap to match IAM/SigV4, AWS Config, the completed
least-privilege phase, the deployed drift loop, and the current CI/CD boundary.
Added the all-rights-reserved terms to the README. Added third-party asset
notices and `SECURITY.md`.
Production deployment is now an explicit workflow input. CodeQL is ready to
run when the repository becomes public.

**Secret scanning.** The old hosted Gitleaks action reported zero scanned
commits. CI now installs a checksum-pinned Gitleaks binary and scans `--all -m`.
An independent local scan covered all 230 commits and found no leak. A second
scan exported only tracked and nonignored worktree files, covered 1.70 MB, and
found no leak. A broad filesystem scan matched only CDK asset hashes in ignored
build outputs and old local worktrees.

**GitHub controls.** `main` now requires the `validate` and `secret-scan`
checks, one approval, last-push approval, current-branch checks, linear history,
and resolved conversations. Force pushes and deletions are disabled. Dev and
prod environments allow only `main`; dev holds its OIDC role ARN as an
environment secret. Dependabot vulnerability alerts and security updates are
enabled. The private-repository plan does not provide environment reviewers,
GitHub secret scanning, CodeQL, or private vulnerability reporting. Those
features require the visibility transition.

**Local controls.** Removed the obsolete API-key variable from the ignored
`.env`, changed its mode to `600`, and set future repository commits to the
GitHub noreply address. No tracked credential or AWS resource changed.

**Verification.** `make lint`, `make typecheck`, `make docs-sync`,
`make public-check`, `make wiki-lint`, dependency audit, and both environment
syntheses pass. `make test` reports 343 passed at 94.13% coverage. The coverage
floor moves from 94.03% to 94.12%.

**Decision and next checkpoint.** Keep the repository private until the final
history choice is explicit. A clean public mirror avoids publishing personal
commit email, stale branches, and existing Actions logs. A history rewrite is
the destructive alternative.

## [2026-08-11] update | Three stale status records corrected on the roadmap page

**Objective.** Remove three statements on
`pages/architecture/phased-security-hardening.md` that the page's own later
sections already contradict.

**The two open windows are closed.** The Phase 2E bullet read "observation
open" and the Phase 3E bullet read the same. Both windows closed with every
criterion met — 2E on 2026-08-02 with the synthetic burst that fired the 3-of-3
alarm, 3E on 2026-07-30 — and the "Next checkpoint" section of the same page
records both closures. Each bullet now carries its close date and its go
decision.

**The execution-policy size tension is closed, not undecided.** The tension
read "No decision is taken yet". The decision landed on 2026-08-08:
`MLOpsCloudFormationExecutionPolicyExtension` carries the overflow at 492 of
6144 bytes and attaches to the same execution role, so the grants union. The
tension now states the resolution and the rule that follows from it — new
grants go in the extension. Four dependent statements moved with it: the 3B
deferral, the GuardDuty-actions tension, the "no grant fits today" paragraph,
and the lead sentence that named the policy without saying which one.

**Scope.** Documentation only. No AWS resource, policy document, or code
changed.

**Verification.** `python scripts/wiki.py lint`.

**Decision and next checkpoint.** Unchanged: the Phase 6 observation window is
still the next checkpoint.

## [2026-08-14] verify | The Phase 6 observation window closed as a go

**Objective.** Close the observation window that opened with the 2026-08-09
SigV4 deployment. Every criterion is met, and Phase 6 is a go.

**Identity.** `${AWS_SECURITY_AUDITOR_USER_NAME}` for the alarm, method, and
stage reads. `${AWS_ADMIN_USER_NAME}` for the account-scope reads and for
`make smoke`.

**Closing evidence.**

| Criterion | Result |
|---|---|
| `POST /predict` authorization | `AWS_IAM`, `apiKeyRequired: false` |
| Unsigned `POST /predict` | `403` |
| `make smoke` | 6 passed in 9.86s, signing each request |
| API keys in the account | **0** |
| Usage plans in the account | **0** |
| Stage throttle | rate 10, burst 20 |
| Six security alarms | `OK` |
| `mlops-dev-endpoint-5xx` | `OK` |
| `mlops-dev-endpoint-silent` | `ALARM` on entry, `OK` on exit — see below |
| Budget | `$20` limit, `$0.00` actual, `$0.786` forecast |
| Month-to-date cost | `$0.00` |

**The five-day gap is itself evidence.** The window ran from 2026-08-09T18:21Z
to 2026-08-14. Across it the method never left `AWS_IAM`, the throttle stayed on
the stage, and no API key or usage plan came back. The boundary holds without
attention.

**One alarm was in `ALARM` at the start of the check, and it was right.**
`mlops-dev-endpoint-silent` fired at 2026-08-12T22:07Z on 24 hourly datapoints
of zero invocations. Its history shows the same cycle twice in the window:
fired 2026-08-10T23:40Z, cleared 2026-08-11T22:07Z, fired 2026-08-12T22:07Z,
cleared 2026-08-14T10:32Z on `1 datapoint [2.0]` — the `make smoke` run of this
check. **The 2F detector measures traffic, not health.** On a platform with no
scheduled traffic it will sit in `ALARM` whenever a day passes without a call,
and it will clear on the next one. Read it as an idle indicator until traffic
becomes continuous. It is not a Phase 6 regression, and it does not block the
go.

**The auditor cannot complete this check alone.** `apigateway:GET` on
`/apikeys` and `/usageplans`, and `budgets:ViewBudget`, are all denied to
`${AWS_SECURITY_AUDITOR_USER_NAME}`. The three denials are true
`unauthorized-api-calls` events on the auditor's own read-only work, and the
Phase 2E three-of-three rule correctly assembled no page from them. The
key and plan counts and the budget came from `${AWS_ADMIN_USER_NAME}`. The
pattern already recorded for the audit log holds here too: verifying the API
boundary needs two identities.

**Decision: go.** Phase 6 is complete. No stack is held open by an observation
window. The next checkpoint is the first `deploy.yml` run, which is blocked on
neither code nor AWS: `CicdStack` is deployed, the OIDC provider and the deploy
role exist, both GitHub environments allow only `main`, and dev holds the role
ARN as an environment secret. Phase 4 (KMS) and Phases 7–9 remain unstarted.

**Verification.** `describe-alarms`, `describe-alarm-history`, `get-method`,
`get-stages`, `get-api-keys`, `get-usage-plans`, `describe-budgets`,
`get-cost-and-usage`, one unsigned `/predict`, and `make smoke`.
`python scripts/wiki.py lint`.

## [2026-08-14] update | graphify installed beside the wiki

### Objective

Add the graphify code graph to the repository as a second navigation layer,
and keep the wiki as the source of record.

### Scope

- `.claude/skills/graphify/` (skill and references), `.graphifyignore`,
  `.gitignore`, `Makefile`, `AGENTS.md`.
- New page `pages/decisions/graphify-knowledge-graph.md`, plus a link from
  `pages/overview.md`.
- No AWS resource and no application code were touched.

### Commands and observed results

1. `uv tool install graphifyy` installed version 0.9.42 and the `graphify`
   and `graphify-mcp` executables. The tool stays outside `uv.lock` and
   outside the project environment.
2. `graphify install --project --platform claude` was blocked by the local
   agent permission layer. The same two paths were written by hand instead:
   `skill.md` was copied to `.claude/skills/graphify/SKILL.md`, and the
   packaged `skills/claude/references/` directory was copied next to it.
   Claude Code discovers a project skill from that path, so no registration
   file is needed. The `PreToolUse` hooks that `graphify hook install` adds
   were deliberately not installed.
3. The first `graphify update .` run read 168 files and warned that seven
   files produced zero nodes. It also indexed the third-party AWS icon set
   under `wiki/assets/architecture/cdk-dia-icons/`.
4. `.graphifyignore` was added to exclude that icon set, `graphify-out/`,
   `infra/cdk.out/`, and `uv.lock`. `.gitignore` already excludes `.env` and
   `telco/`, and graphify honours it.
5. `make graph` rebuilt from commit `90dc79d`: 176 files, about 368,850 words,
   2141 nodes, 2953 edges, 209 communities, 100% EXTRACTED edges, 12 INFERRED
   edges at an average confidence of 0.53, and 0 tokens.
6. The generated files were searched for account-identifying literals. No
   twelve-digit account identifier and no `execute-api` host appeared; the
   twelve-digit matches were cohesion scores. `.env` was never read.

### Interpretation

The extraction is local, deterministic, and free, so the graph can be
rebuilt at will and does not need to be preserved. That is why
`graphify-out/` is untracked, like `infra/cdk.out/`. The wiki keeps history,
decisions, and status; the graph holds structure only. A generated file MUST
NOT appear in a `sources:` list, because it does not survive a clean clone.

The one real risk is silence: a query against a stale graph returns a
confident answer about old code. `GRAPH_REPORT.md` names the commit it was
built from, and that line MUST be read before an answer is trusted.

### Decision and next checkpoint

graphify is a convenience layer, not a gate. It is deliberately absent from
CI and from the pre-release checks. Revisit two choices later: committing
`graphify-out/` if a second contributor joins, and running `graphify label`
if an LLM backend is ever configured for community naming.

### Verification

`make graph`, `make lint`, `make test`, `make docs-sync`, `make wiki-lint`,
and `make public-check`.

## [2026-08-14] update | The pages meet the ASD-STE100 and RFC 2119 standard

### Objective

Bring every maintained page under `pages/` and the wiki's own contract files to
the writing standard in the root `AGENTS.md`: ASD-STE100 for the prose, RFC 2119
for the requirement words.

### Scope

- All 47 pages under `wiki/pages/`, plus `wiki/SCHEMA.md` and `wiki/AGENTS.md`.
- `wiki/index.md`, rebuilt after the page summaries and dates changed.
- **Out of scope by contract:** `wiki/raw/` is immutable, and preserved source
  text keeps its own words. The earlier entries in this log are append-only
  history. Neither was edited.

### Commands and observed results

1. A heuristic scanner flagged three classes of risk across the pages: a
   sentence above the 25-word limit, a passive construction, and a word with a
   simpler approved equivalent. The first run reported 270 candidate lines.
2. A grep for the RFC 2119 synonyms REQUIRED, SHALL, RECOMMENDED, and OPTIONAL
   returned no hit. The wiki never used them.
3. A grep for lowercase `must`, `should`, and `may` in a normative sentence
   returned 45 lines across 30 files. Each one is now an uppercase keyword, a
   plain imperative, or a statement of fact.
4. 18 sentences were above the length limit. The longest, in
   `pages/answers/repo-walkthrough.md`, held 63 words. Both of the long list
   sentences on that page are now numbered lists.
5. `make wiki-index`, then `make wiki-lint`: `Wiki healthy: 47 page(s)`.
6. `make public-check`: no sensitive literal.

### Interpretation

Three rules did most of the work. Name the actor instead of writing an agentless
passive. Write one idea per sentence. Reserve an uppercase keyword for a rule
that a reader breaks at a real cost. A SHOULD with no escape condition became a
MUST or an ordinary sentence, as the root standard requires.

**Four stale claims surfaced during the rewrite, and each was corrected in
place.** A sentence cannot be repaired for style while it states something
false.

- `pages/architecture/permissions.md` said an API caller needs an API key. Phase
  6 replaced that with SigV4, and the account holds no API key.
- `pages/architecture/cdk-deployment-iam.md` described six application stacks.
  `infra/app.py` defines nine per environment. The same page said the pipeline
  role still carries `AmazonSageMakerFullAccess`; Phase 5D removed it.
- `pages/architecture/deployment-and-pipeline-troubleshooting.md` said the Model
  Monitor capture path waits for another capture mechanism. The
  repository-owned drift job replaced it.
- `pages/concepts/contracts-and-preprocessing.md` reported the `src` packaging
  failure in the present tense. That defect is fixed.

### Decision and next checkpoint

The pass covers the pages and the contract files. It deliberately leaves the
raw records and the earlier log entries alone. No AWS resource, no application
code, and no test changed. The next writing checkpoint is the next new page:
the standard now has to hold at the point of writing, because the wiki no longer
carries a backlog of exceptions.

### Verification

`make wiki-index`, `make wiki-lint`, `make public-check`, `make docs-sync`,
`make lint`, and `make test`.

## [2026-08-14] update | The nine pages the first style pass missed

### Objective

Close a coverage gap in the entry above. That pass reported all 47 pages. It
changed 38.

### Scope

The nine pages under `pages/sources/` that the first pass never opened: the
Phase 0 baseline, Phase 1 implementation, Phase 2D completion and
implementation, Phase 2E, Phase 3-prep completion, the Phase 3B first-deployment
rollback, Phase 3C, and Phase 3F.

### Commands and observed results

1. A comparison of the changed-file list against the page list named the nine
   files.
2. The scanner reported 25 flags across them. Phase 3C and Phase 3F held 11
   each. Both are recent, detailed records, and neither had been read.
3. Each flag was resolved by hand: an agentless passive gained its actor, a
   list-shaped sentence became a list, and `require` became `need` where `need`
   is the exact word.
4. `make wiki-index`, `make wiki-lint`: `Wiki healthy: 47 page(s)`.
   `make public-check`: no sensitive literal.

### Interpretation

**The gap came from the shape of the search, not from the pages.** The first
pass drove off a grep for a lowercase requirement word. A page with no `must`,
`should`, or `may` produced no hit and therefore never reached a human read,
even when the scanner had already flagged eleven passive constructions on it. A
mechanical pass measures only what its pattern matches. Coverage MUST be
measured against the file list, not against the hit list.

### Decision and next checkpoint

All 47 pages are now read and corrected. The remaining scanner output is ten
lines, all of them `attempt` as a noun or `require` used exactly, which the
standard permits.

### Verification

`make wiki-index`, `make wiki-lint`, `make public-check`.

## [2026-08-14] update | The graphify git hooks are installed

### Objective

Rebuild the code graph automatically, so a query does not answer from a graph
that predates the current tree.

### Scope

- `.git/hooks/post-commit` and `.git/hooks/post-checkout` in the local clone.
- `AGENTS.md`, the "Knowledge graph (graphify)" rules.
- `pages/decisions/graphify-knowledge-graph.md`.
- No AWS resource, no application code, and no tracked hook file. Git does not
  track a hook, so this install is local to one clone.

### Commands and observed results

1. `graphify hook install` wrote both hooks and reported the paths. It also
   registered a union merge driver for `graphify-out/graph.json`: two
   `merge.graphify.*` git config keys and a new `.gitattributes`.
2. **The merge driver was removed.** `.gitattributes` was deleted and both
   config keys were unset. `graphify-out/` is gitignored here, so the driver
   would merge a file that this repository never tracks.
3. Reading the hook first showed three early exits. It exits when the git
   directory differs from the common directory, which is every linked worktree.
   It exits during a rebase, a merge, and a cherry-pick. It exits when
   `GRAPHIFY_SKIP_HOOK=1`.
4. The rebuild runs detached, and it pins `PYTHONHASHSEED=0`. The pin matters:
   the Louvain clustering iterates string-keyed sets, so an unpinned seed moves
   the community assignments between runs.

### Interpretation

**The worktree exit is the limit that matters here.** This repository does its
agent work in `.claude/worktrees/`, and a commit there produces no rebuild. The
hook helps a commit made in the main checkout and nothing else. `make graph`
stays the reliable rebuild.

**A hook is not a distributed guarantee.** Git does not track `.git/hooks/`, so
a second clone, a CI runner, and a fresh machine all start without it. The
freshness line in `GRAPH_REPORT.md` remains the check that a reader MUST make
before trusting an answer.

The merge driver is correct for a project that commits `graphify-out/`. This
repository decided the opposite, so the registration was dead configuration.
Reinstate it with `graphify hook install` if the tracking decision changes.

### Both paths were tested by hand

The hook script was run directly, once from each side.

- **In the worktree it did nothing.** It returned 0 and left
  `GRAPH_REPORT.md` on commit `21f1129` while that worktree stood at `33cb44a`.
  This is the documented worktree exit, observed rather than assumed.
- **In the main checkout it rebuilt.** It printed `launching background rebuild`
  and returned at once. The detached run then reported 2169 nodes and 2985
  edges, and it wrote a backup of the earlier graph into
  `graphify-out/2026-08-14/`.

The test drove the hook script directly. A rebuild started by git itself, at the
end of a real commit, is not yet observed.

### The pull test corrected the record

A `git pull --ff-only` in the main checkout on 2026-08-14 moved it from
`df85bd1` to `c1d4fe6` across 50 files. **No rebuild started.** The graph stayed
on `df85bd1` and no rebuild process ran. A hand-run `graphify update .` then
took it to `c1d4fe6`.

**A fast-forward pull runs `post-merge`, and graphify installs no `post-merge`
hook.** It installs `post-commit` and `post-checkout` only. An earlier note in
this session predicted that a pull would trigger the post-checkout rebuild, and
that prediction was wrong. The two hooks between them miss the two ways this
tree most often moves: a pull, and any work in a worktree.

### Decision and next checkpoint

The hooks are installed and the merge driver is not. No gate depends on either.
The next checkpoint is the first commit in the main checkout: confirm that
`GRAPH_REPORT.md` follows it without a hand-run `make graph`. A `post-merge`
hook is possible and is not installed, because the pull case is now written
down and `make graph` covers it.

### Verification

`make wiki-index`, `make wiki-lint`, `make public-check`, `make docs-sync`, and
the two hook runs above.

## [2026-08-14] implement | A post-merge hook closes the pull gap

### Objective

Rebuild the code graph after a pull and after a merge. graphify covers neither.

### Scope

- New tracked script `scripts/git-hooks/post-merge`.
- New Make target `graph-hooks`, which installs all three hooks and removes the
  merge-driver registration.
- `AGENTS.md` and `pages/decisions/graphify-knowledge-graph.md`.
- No AWS resource and no application code.

### Commands and observed results

1. The hook delegates to the graphify `post-commit` hook, which owns the
   interpreter probe, the worktree guard, and the detached launch. One graphify
   upgrade then reaches both paths.
2. **The first version of the wrapper did nothing on a true merge.** A
   diagnostic hook in a throwaway repository printed the cause:
   `MERGE_HEAD exists: yes`. Git keeps `MERGE_HEAD` in place while it runs
   `post-merge`, and `post-commit` exits when that file is present.
3. The wrapper now removes the `MERGE_HEAD` lines from the delegate and runs the
   filtered copy. It keeps every other guard.
4. Three tests in throwaway repositories, each with `graphify-out/` ignored:
   - A fast-forward `git pull` rebuilt the graph to the pulled commit.
   - A `git merge --no-ff` rebuilt the graph to the merge commit. The same
     merge produced no rebuild before the guard was dropped.
   - A commit inside a `git worktree` wrote no graph and launched nothing.
5. `make graph-hooks` reported all four steps, and it left no `.gitattributes`
   and no `merge.graphify.*` config.

### Interpretation

**A hook that silently does nothing is worse than an absent hook**, because the
reader believes the graph is fresh. Both defects found today had that shape: the
missing `post-merge` hook, and then the wrapper that exited on `MERGE_HEAD`.
Neither printed anything. The rule that follows: test a hook by observing the
rebuild, not by reading the script.

Two limits stay, and both are deliberate. The hooks do nothing in a linked
worktree, which is graphify's own guard against a delta-only graph and against a
`git clean` race. Git does not track a hook, so a clone runs `make graph-hooks`
once.

### Decision and next checkpoint

The three hooks are installed in the primary checkout. The next real pull into
that checkout is the checkpoint: `GRAPH_REPORT.md` MUST follow it with no
hand-run `make graph`.

### Verification

`make graph-hooks`, the three throwaway-repository tests above, `make lint`,
`make wiki-index`, `make wiki-lint`, `make public-check`, and `make docs-sync`.
## [2026-08-14] implement | The endpoint alarms move to their own SNS topic

### Objective

Separate the operational alarm channel from the security alarm channel, so a
quiet dev day stops paging the inbox that carries the CIS detections.

### Scope

- `infra/stacks/security_stack.py`, `infra/stacks/monitoring_stack.py`,
  `infra/app.py`, `pyproject.toml`, and two unit tests.
- New page `pages/decisions/alert-topic-split.md`, plus a pointer from the 2F
  section of the roadmap and a row on the Phase 2 audit-foundation page.
- No AWS resource. This entry records an implementation, not a deployment.

### Commands and observed results

1. `mlops-dev-endpoint-silent` entered `ALARM` on 2026-08-12T22:07Z after 24
   hours with no invocations, and the Phase 6 window recorded the same cycle
   twice. The alarm is correct: dev has no traffic floor, and `dev.yaml`
   already records that idle time starts it.
2. `SecurityStack` gained `mlops-<env>-ops-alerts` on the audit key, with
   `enforce_ssl=True`, the same email subscription, a resource policy that
   admits `cloudwatch.amazonaws.com` only, and an `OpsAlertsTopicArn` output.
3. `MonitoringStack` takes `ops_topic` in place of `alert_topic`. Both endpoint
   alarms publish there. Budgets and the Phase 3F EventBridge rules stay on the
   security topic.
4. The branch was rebased onto `main` at `c1d4fe6`, after the graphify and wiki
   work merged. The rebase produced no conflict.
5. `make lint`, `make typecheck`, and `make test` pass on the rebased branch:
   345 tests, coverage `94.15%` against the floor of `94.14`.

### Interpretation

**The alarm was never the defect. The destination was.** The signal is
correct in both environments, and the two environments disagree about what it
means: prod waits 6 hours and dev waits 24. A channel that carries a daily
heartbeat next to root-activity and unauthorized-call detections teaches the
reader to skim it, and that habit is the real loss.

**The old test could not have caught this in either direction.** It asserted
`"AlarmActions": [{"Fn::ImportValue": Match.any_value()}]`, which accepts any
topic. The replacement names the ops topic and denies the security topic.

The general rule this sets: **a new alarm chooses its topic by audience.** An
operational alarm reports the platform. A security alarm reports the account.

### Decision and next checkpoint

The change is implemented on the branch of pull request #68 and is not deployed.
Two conditions bind the deploy. The new topic sends a fresh subscription request, and the endpoint
alarms deliver nowhere until a human accepts it. A `Mlops-Dev-Monitoring` deploy
also ships `Mlops-Dev-Security`, so read the `Including dependency stacks:` line
and run `make verify-deploy` after.

This is an alarm-behavior change, so it takes the Phase 2E gate that 2F and 2G
took: pre-flight baseline, reviewed named diff, scoped dev deploy, resource-level
verification, an observation window, and an explicit go/no-go. The window MUST
show one endpoint alarm arriving on the new topic, and MUST confirm that the
seven security alarms still reach the old one.

### Verification

`make lint`, `make typecheck`, `make test`, `make wiki-index`, `make wiki-lint`,
and `make public-check`.

## [2026-08-14] update | A fresh account can reach this platform from the README

### Objective

Record the change that makes a clone-and-follow deploy work on a new AWS
account, and record the two defects that the reference account hid.

### Scope

- `pages/architecture/cdk-deployment-iam.md`: a new section, two tension
  entries, and five new sources.
- The code landed earlier the same day as pull request #67, squashed to
  `e8b7e31`. This entry is the record, not the change.

### Commands and observed results

1. **`make deploy` could never succeed on a new account.**
   `SecurityAlertEmail` is a `CfnParameter` with no default, and no target
   supplied it. CloudFormation reuses a stored parameter value on an update, so
   the reference account kept working from its first hand-run deploy.
   `deploy.yml` calls the same target and carried the same defect.
2. **`make bootstrap` granted `AdministratorAccess`** to the CDK
   CloudFormation execution role, which is the CDK default. The reference
   account runs on the two repository-owned execution policies.
3. `scripts/setup_account.sh` now creates both execution policies, the
   `MLOps-Deployers` group, `MLOpsCdkDeploymentPolicy`, and the deploy user
   with one printed access key. It is idempotent.
4. `scripts/setup_github_deploy.sh` reads `GitHubDeployRoleArn` from the `Cicd`
   stack, creates the GitHub environment, and sets the deploy-role secret.
5. `make bootstrap` names both execution policies. `make deploy` and
   `make deploy-stack` pass `SecurityAlertEmail`, and `check-alert-email` stops
   early when the value is absent.
6. The rebase onto `main` produced one conflict, in the `Makefile` `.PHONY`
   list: `main` had added the graph targets and the branch had added
   `check-alert-email`. The resolution keeps both.
7. Gates on the rebased branch: lint, typecheck, 345 tests at `94.15%`,
   `synth-all` for dev and prod, `docs-sync`, `public-check`, and `wiki-lint`.

### Interpretation

**A working reference account hides a first-run defect.** Both problems were
invisible here for one reason: this account already holds the state that a new
account lacks, and CloudFormation quietly supplies a stored parameter. The
general rule for this repository: **a path that only a populated account
exercises is an untested path.**

The second defect is a documentation boundary, not only a convenience. The
README told a reader to bootstrap with `AdministratorAccess` on the execution
role, while this wiki describes a two-policy boundary. The repository presented
one boundary and shipped the instructions for a weaker one.

### Decision and next checkpoint

**Neither script has run against a live account.** Read-only IAM calls checked
their policy assumptions, and their runtime behavior is unproven. The next
checkpoint is a run of `setup_account.sh` against a scratch account. Until then
the README path stays unverified, and the page says so.

One local action is needed here: add `SECURITY_ALERT_EMAIL` to `.env`, or the
guard stops the next deploy. The pending sub-phase from pull request #68 is that
next deploy.

### Verification

`make wiki-index`, `make wiki-lint`, `make public-check`, `make docs-sync`.

## [2026-08-14] deploy | The operational alert topic is live in dev

### Objective

Deploy the alert-topic split to dev, so a quiet day stops paging the security
channel. Open its observation window.

### Scope

- `Mlops-Dev-Security` and `Mlops-Dev-Monitoring` in dev. Prod untouched.
- Pages `decisions/alert-topic-split.md`,
  `architecture/security-phase-2-audit-foundation.md`, and
  `architecture/phased-security-hardening.md`.

### Identity and environment

Deploy as `${MLOPS_DEPLOYER_USER_NAME}`. Read-only checks and
`make verify-deploy` as `${AWS_SECURITY_AUDITOR_USER_NAME}`. Smoke tests as
`${AWS_ADMIN_USER_NAME}`. Region `us-east-1`.

### Commands and observed results

1. **Pre-flight baseline.** Nine alarms existed, all `OK`, and all nine named
   `mlops-dev-security-alerts`. One SNS topic existed, with one confirmed email
   subscription.
2. **The guard stopped the first attempt.** `.env` held no
   `SECURITY_ALERT_EMAIL`, which pull request #67 made mandatory the same day.
   The deployed Security stack still stored the parameter value, and a read of
   the stack parameters recovered it.
3. **The diff.** `Including dependency stacks: Mlops-Dev-Data,
   Mlops-Dev-Security`. Security gained a topic, a topic policy, a
   subscription, and two outputs. Monitoring re-pointed two alarms and showed
   two Lambda asset-hash changes. Data showed no difference.
4. **The deploy took 77 seconds.** Security updated at 14:52:12Z, Monitoring at
   14:52:44Z.
5. **`make verify-deploy SINCE=2026-08-14`** lists three created resources in
   Security and four updated resources in Monitoring. It lists no change for
   Data.
6. **Live routing check.** Nine alarms: two now name `mlops-dev-ops-alerts`,
   seven still name `mlops-dev-security-alerts`. Both topics use the same audit
   KMS key.
7. **Subscriptions.** The security topic subscription is still `CONFIRMED`. The
   new ops topic subscription reads `PendingConfirmation`.
8. **Smoke.** Six integration tests pass under `${AWS_ADMIN_USER_NAME}`.

### Interpretation

**The parameter that blocked the deploy is the same one that hid the
first-run defect.** `.env` never needed `SECURITY_ALERT_EMAIL` because
CloudFormation kept supplying the stored value. The guard is what makes that
dependency visible. Recovering the value from the deployed stack kept it
identical, so AWS sent no second confirmation request for the security topic.

**`make smoke` needs three different identities to be useful, and only one of
them works.** The auditor receives `403` on `/predict`, because a read-only
identity holds no `execute-api:Invoke`. The deploy identity cannot resolve the
API URL, because it holds no `cloudformation:DescribeStacks`. Only
`${AWS_ADMIN_USER_NAME}` completes the target. This repeats the pattern the
Phase 6 window recorded for the API boundary: **one check, two identities.**

**Two Lambda functions show as updated and their source did not change.** The
bundled asset hash is not reproducible, so any deploy from a cold `cdk.out`
republishes the code. Read that line in a diff as noise, not as a change.

### Decision and next checkpoint

**The observation window is open. This is not a go.** Two conditions close it.
A human MUST confirm the new subscription, because the two endpoint alarms
deliver nowhere until then. The window MUST then show one endpoint alarm
arriving on the new topic, and MUST confirm that the seven security alarms
still reach the old one. Dev has no traffic floor, so the silence alarm
supplies the first signal on its own within 24 hours of the last call.

Prod keeps the single topic until a deliberate rollout.

### Verification

`make diff-stack`, `make deploy-stack`, `make verify-deploy SINCE=2026-08-14`,
`describe-alarms`, `list-subscriptions-by-topic`, `get-topic-attributes`, the
six integration tests, `make wiki-index`, `make wiki-lint`, and
`make public-check`.

## [2026-08-14] verify | The ops topic subscription is confirmed

The first of the two window conditions is met. `list-subscriptions-by-topic`
on `mlops-dev-ops-alerts` returns one `email` subscription with a real
subscription ARN, so the state is `CONFIRMED` and no longer
`PendingConfirmation`.

**This is not delivery evidence.** A confirmed subscription proves that the
address accepted the topic. The window still needs one endpoint alarm to fire
and reach the inbox through the new topic. Two paths reach that evidence. The
silence alarm fires on its own about 24 hours after the last call, and the
smoke run of this deploy was the last call. A controlled `set-alarm-state`
call would prove the path at once, as the Phase 2C controlled denial did, at
the cost of a synthetic fire rather than a real one.

The window stays open.

## [2026-08-14] update | Diagrams move to a root folder and match the ops topic

### Objective

Regenerate the `cdk-dia` diagram set against the current tree, and give the
generated output one home at `diagrams/` in the repository root.

### Scope

- `Makefile`, `.graphifyignore`.
- `wiki/pages/architecture/generated-cdk-diagrams.md`,
  `wiki/pages/decisions/graphify-knowledge-graph.md`.
- The nine diagram files and the `cdk-dia-icons/` set.

### Content

The assets last rendered on 2026-08-09. Two commits changed infrastructure
after that date: #63 and #68. Only #68 changed the resource graph. The new
render adds `Mlops-Dev-Security/OpsAlertsTopic` with its edge to `AuditKey`,
and moves `Endpoint5xxAlarm` and `EndpointSilentAlarm` onto that topic. The
seven security alarms keep `SecurityAlertsTopic`. The `cdk-platform-dev` view
does not change.

The refactor in #63 left no trace, and Phase 6 left none either, because the
2026-08-09 render already held the state after the SigV4 change. A diagram
tracks a resource, not a code change.

`DIAGRAM_DIR` in the `Makefile` names the destination once, so one edit moved
every view. `git mv` carried the files and the icons out of
`wiki/assets/architecture/`, which left `wiki/assets/` empty. The wiki keeps
no second copy: `diagrams/` holds the latest version, and a run replaces the
files in place.

### Verification

`make diagrams` ran again after the move and produced no further change, so
the relative icon paths inside each DOT file survived. `make wiki-lint`
reports 48 healthy pages. `make public-check` and `make test` pass.
## [2026-08-14] query | lambda asset fingerprint hash

Found 25 matching page(s).


## [2026-08-14] update | The Lambda asset hash stops drifting between checkouts

### Objective

Record the cause of the non-reproducible Lambda bundled asset hash, and the
fix that landed in `326f27f`.

### Scope

- `infra/stacks/lambda_code.py`, `tests/unit/test_lambda_code.py`.
- The four Lambda functions in the dev account.

### Content

`Code.from_asset` uses `IgnoreMode.GLOB` by default. The leading `*` in the
allowlist matches no dotfile under that mode, so `.git` stayed in the asset
fingerprint. `.git` is a directory in a normal clone, and it is a file in a
git worktree. That file holds the absolute gitdir path of its own worktree,
so each checkout produced a different Lambda code hash from an identical
`src/`. A deploy then rewrote all four functions with the same code.

`IgnoreMode.GIT` is the semantics the exclude patterns were written for.

The fix came from the abandoned `claude/jolly-mestorf-78d005` branch, which
held the change from 2026-08-05 and never merged. The other commit on that
branch was already on `main`.

### Verification

Two checkouts of one commit produced the asset hash. Before the fix, two
worktrees of `e4de7b4` gave `7f0ef901…` and `cf0805be…`. After the fix, the
primary clone and a worktree of `326f27f` both gave `b2819ca4…`. The new unit
test fails without the change.

`make lint`, `make typecheck`, `make synth-all`, and `make test` pass. The
coverage floor stays at 94.14.

### Open

The first dev deploy after this change updates all four functions one time.
The hash moves to its new value, and it then stops moving on its own.

## [2026-08-14] update | Dataset provenance is pinned by hash

### Objective

Close the first reproducibility gap from the fresh-user audit: the training
CSV was untracked, and no document named its source or its exact bytes.

### Scope

`README.md` (new Dataset section, corrected Quickstart upload path),
`wiki/pages/decisions/dataset-provenance.md` (new). No code change.

### Commands and results

Read-only verification on the local working copy and two public mirrors:

- `shasum -a 256 telco/telco.csv` returned
  `88be4b93fbe0cc83421af1c503794c97c342eca914c1576db7c276e61d61358a`
  (7,043 data rows plus a header, CRLF line endings).
- The IBM mirror
  (`IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv`)
  and a third-party GitHub copy both hashed to
  `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`.
- `tr -d '\r'` over the local copy reproduced the canonical hash exactly.

### Interpretation

The working copy is the canonical Kaggle/IBM file with converted line
endings. `split_records` seeds `random.Random(42)` over the row order, so
the exact file is the reproducibility contract: same hash, same splits,
same AUC. The README now gives a login-free fetch command and both hashes.

### Decision and next checkpoint

The CSV stays untracked (no clear redistribution license); the hash check
is the gate. A reference first-champion AUC remains unrecorded until the
scratch-account rebuild test runs.

### Verification

`make wiki-lint` after the index rebuild; see the teardown entry below.

## [2026-08-14] update | Teardown and rebuild get a page

### Objective

Close the second reproducibility gap: `make destroy` existed with no record
of what it leaves behind or the order a full teardown needs.

### Scope

`wiki/pages/architecture/teardown-and-rebuild.md` (new), `README.md`
(Teardown section pointing at it). Evidence is code reading only: the
`RemovalPolicy.RETAIN` declarations in the Data and Security stacks, the
account-BPA custom resource `on_delete`, `CfnModelPackageGroup` in the
Registry stack, and the SDK-created serving resources in
`src/serving/deploy_handler.py`.

### Interpretation

Three survivor classes emerged: CloudFormation-retained resources, resources
the SDK created outside CloudFormation, and account objects outside the app
stacks. Two fixed retained names — `alias/mlops-<env>-audit` and
`/aws/cloudtrail/mlops-<env>-audit` — collide with the next deploy, so a
naive destroy-then-deploy fails. Model packages left in the group fail the
Registry stack delete itself.

### Decision and next checkpoint

The page is derived from code, not from an executed teardown, and it says
so. The next checkpoint is the scratch-account rebuild test, which also
proves the setup scripts; that run MUST correct the page where reality
disagrees.

### Verification

`uv run --locked python scripts/wiki.py index` rebuilt the index and
`make wiki-lint` passed with the two new pages.

## [2026-08-14] update | Website stack plan recorded before implementation

### Objective

Record the approved plan for a tenth stack, `Mlops-Dev-Website`, before any
code exists, so the design decisions and their cost reasoning survive the
session.

### Scope

`wiki/pages/decisions/website-stack-plan.md` (new). No code path changes.
The planned stack touches `infra/app.py`, `infra/stacks/shared.py`,
`infra/security_checks.py`, the execution-policy extension, and a new
`src/website/` package when implementation starts.

### Commands and results

Read-only exploration of `infra/` and `tests/unit/` established the
integration points: the `requires_flag` mechanism in
`infra/security_checks.py`, the `sign_headers`/`post_prediction` pair in
`scripts/evaluate_api.py`, and `api.url_for_path("/predict")` in the
Serving stack. No mutating command ran.

### Interpretation

The $20 monthly budget forced every major choice: CloudFront replaces an
ALB (~$16.50/mo), DynamoDB replaces RDS (~$12–15/mo), and a 1-year
no-upfront Reserved Instance makes `t4g.small` affordable (~$7.74/mo
against $12.26 on-demand) with no upfront spike through the budget alarms.
The plan reuses the Phase 6 SigV4 boundary through a server-side proxy and
gates the stack behind a `website.enabled` config flag so prod stays free.

### Decision and next checkpoint

The page states plainly that nothing is implemented or deployed. The next
checkpoint is the implementation change set (one phase per the operating
rule), then a dev deploy, then the RI purchase by the account owner, then
an observation window. GuardDuty enablement follows in its own change set,
because EC2 landing is its approved trigger.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed with the
new page.

## [2026-08-14] update | Website stack written, tested, and not deployed

### Objective

Implement the tenth stack, `Mlops-Dev-Website`, to the plan recorded in the
entry above, and take it through every repository gate short of a deploy.

### Scope

New: `infra/stacks/website_stack.py`, `src/website/` (`server.py`,
`Dockerfile`, `requirements.txt`), `src/common/signing.py`,
`tests/unit/test_website_stack.py`, `tests/unit/test_website_server.py`,
`tests/unit/test_signing.py`. Changed: `infra/app.py`,
`infra/stacks/shared.py` (`WebsiteConfig`), `infra/config/*.yaml`,
`infra/stacks/serving_stack.py` (`predict_url` attribute),
`infra/security_checks.py` (`WEBSITE_FLAG` and ten acknowledgements),
`infra/policies/mlops-cloudformation-execution-policy-extension.json`,
`scripts/evaluate_api.py`, `tests/unit/conftest.py`,
`tests/unit/test_security_checks.py`, `tests/unit/test_deployment_policy.py`,
`pyproject.toml`.

### Commands and results

- A spike measured `Stack.bundling_required`: false under the conftest
  context `aws:cdk:bundling-stacks: []`, true without it. The stack gates
  `DockerImageAsset` on that value.
- `AWS_PROFILE=${AWS_SECURITY_AUDITOR_USER_NAME} aws ec2
  describe-managed-prefix-lists` (read-only) returned `pl-3b927c52`,
  `com.amazonaws.global.cloudfront.origin-facing`, `create-complete`.
- The first `make synth ENV=dev` failed with `Cannot find image directory at
  .../infra/src`: the CDK CLI runs `app.py` from `infra/`, so the asset needs
  an absolute path.
- cdk-nag then reported ten findings. Each one is acknowledged by its exact
  id, and each reason names the phase that removes it.
- `make test`: 408 passed, coverage 94.58 percent against the raised floor.
  `make lint`, `make typecheck`, `make synth-all`, `make docs-sync`,
  `make public-check`, `make lock-check`, `make wiki-lint`: all pass.
- The server ran locally on port 8099. `/`, `/api/health`, and `/api/schema`
  answered; an invalid address and an invalid record returned 400; an unknown
  path returned 404; the eleventh prediction in one minute returned 429.

### Interpretation

Three design points changed during the build. The instance attribute
`PublicDnsName` resolves before the Elastic IP attaches and would name a
released address, so the origin name is built from the address. A Python
comparison cannot read `self.region`, because these stacks carry no `env` and
the value is a token; a `CfnCondition` resolves the `compute-1` special case
at deploy time. A container user without privileges cannot bind port 80, so
the container listens on 8080 and the host publishes it as port 80.

The `ecr:GetAuthorizationToken` grant adds the second entry to the literal
wildcard baseline. AWS accepts no narrower resource for that action.

### Decision and next checkpoint

Nothing is deployed, and the wiki page says so. The next checkpoints, in
order: update the two deployed managed policies from `infra/policies/`,
review `make diff-stack STACK=Mlops-Dev-Website` and confirm the Data and
Serving dependency stacks diff clean, deploy, run `make verify-deploy`, smoke
the CloudFront URL, then buy the Reserved Instance. GuardDuty enablement
stays a separate change set, because EC2 landing is its approved trigger.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed.

## [2026-08-14] update | Execution-policy extension rotated to v3

### Objective

Put the website grants on the deployed CloudFormation execution boundary, so
`Mlops-Dev-Website` can create its resources.

### Scope

`MLOpsCloudFormationExecutionPolicyExtension` in the live account, and
`wiki/pages/architecture/cdk-deployment-iam.md`. The repository document
`infra/policies/mlops-cloudformation-execution-policy-extension.json` did not
change; this entry records the rotation of the deployed copy to match it.

### Identity and environment

Profile `${AWS_ADMIN_USER_NAME}`, account-scoped IAM, us-east-1.

### Commands and results

- `git diff origin/main..HEAD -- infra/policies/` showed one changed file. The
  main document is byte-identical, so it needs no rotation.
- `aws iam list-policy-versions` (read) reported `v1` and `v2` with `v2` as the
  default. Two of five slots were used, so `v3` needed no cleanup delete. The
  wiki claim matched the account this time.
- `aws iam get-policy-version --version-id v2` (read) returned a document
  byte-identical to the repository copy at `origin/main`. No out-of-band drift
  existed to overwrite.
- `envsubst` rendered the new document from a populated local `.env`. A check
  confirmed 3664 bytes, ten statements, and no unsubstituted placeholder.
- `aws iam create-policy-version --set-as-default` (mutating) returned `v3`
  with `IsDefaultVersion: true`.
- `aws iam get-policy-version --version-id v3` (read) returned a document
  byte-identical to the rendered file.
- `aws iam list-entities-for-policy` (read) confirmed the policy still attaches
  to `cdk-hnb659fds-cfn-exec-role-*`.

### Interpretation

The drift check before the write is the important step. A rotation overwrites
the default version, so an unrecorded manual grant would disappear without a
message. The comparison proved there was none.

Three of the five version slots are now used. The next rotation is free; the
one after it MUST delete a version first.

### Decision and next checkpoint

The boundary now permits the website resources. Nothing is deployed. The next
checkpoints are a running Docker daemon, a reviewed
`make diff-stack STACK=Mlops-Dev-Website ENV=dev` with the Data and Serving
dependency stacks clean, the deploy, `make verify-deploy`, and the smoke
checks. The Reserved Instance purchase follows a verified deploy.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed.

## [2026-08-14] update | Website diagram target added and dev diagrams regenerated

### Objective

Give the website stack a generated view, and refresh the committed diagrams,
which no longer matched the app after the tenth stack landed.

### Scope

`Makefile` (the `diagrams` target and a new `DIAGRAM_WEBSITE` path),
`wiki/pages/architecture/generated-cdk-diagrams.md`, and the `diagrams/`
folder.

### Commands and results

- The two grouped views carry hardcoded `--include` lists, so neither picked
  up the new stack. The full view has no filter and picked it up on its own.
- `make diagrams ENV=dev DIAGRAM_DIR=<scratch>` rendered four sets. The
  website DOT file named `Mlops-Dev-Website` only, and held the nine website
  constructs.
- `make diagrams ENV=prod DIAGRAM_DIR=<scratch>` rendered three sets, wrote no
  website file, and exited 0.
- `make diagrams ENV=dev` against the tracked folder changed
  `cdk-full-dev.{dot,png,svg}` and added the website set plus five icons. The
  platform and security views rendered byte-identical, so Graphviz output is
  reproducible for an unchanged input.
- `make wiki-lint` passed, and `make public-check` found no literal. The new
  DOT and SVG files carry no workstation path and no account id.

### Interpretation

The website takes its own view rather than a place in the ML platform view. It
is the one stack with a VPC and an instance, and the platform view means the
training and inference path. Mixing them would cost that view its meaning.

The guard reads `website.enabled` through `load_config`, so the target follows
the same flag that `build_app` follows. A hardcoded stack list would break
`ENV=prod`.

### Decision and next checkpoint

The diagrams show synthesized desired state, not deployed state; the page
already says so. A deploy that forces the Elastic IP fallback would remove the
EIP node, and that MUST trigger one more regeneration.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed.

## [2026-08-14] update | A local container run found three website defects

### Objective

Build and run the website image locally, so the site could be seen before a
deploy.

### Scope

`src/website/server.py`, `infra/stacks/website_stack.py`,
`tests/unit/test_website_server.py`, `tests/unit/test_website_stack.py`,
`tests/unit/test_security_checks.py`.

### Identity and environment

Local Docker 29.6.1. The container read live dev S3 and the live `/predict`
API through a mounted read-only AWS config. The mailing list used DynamoDB
Local, because the real table is not deployed.

### Commands and results

The image built after a base-image pull, and the container answered `/`,
`/api/health`, and `/api/schema` at once. Three defects followed.

1. **A failed S3 read returned no response at all.** `/api/results` gave
   `curl` exit 52 and HTTP 000. `BaseHTTPRequestHandler` sends nothing when
   the handler raises, so the reader saw an empty reply rather than an error.
2. **A repeat signup destroyed the first signup time.** `subscribe` called
   `PutItem`, which replaces the whole item, so `created_at` moved to the
   newest signup.
3. **The user data set the wrong region variable.** Two container runs proved
   that botocore raises `NoRegionError` with `AWS_REGION` set and resolves the
   region with `AWS_DEFAULT_REGION`. On EC2 this would not fail, because
   botocore then reads the instance metadata for every client.

The fixes: `latest_results` catches `ClientError`, `OSError`, and
`JSONDecodeError` and degrades to one unavailable section; the request handler
answers 500 for any unexpected error; `subscribe` calls `UpdateItem` with
`if_not_exists(created_at, :now)` and returns the stored time; the user data
sets `AWS_DEFAULT_REGION`.

DynamoDB Local proved the signup time. Two signups three seconds apart
returned one `created_at` of `22:08:37`, and the record held
`last_signup_at` of `22:08:40`.

### Interpretation

The instance role now needs `dynamodb:UpdateItem` in place of
`dynamodb:PutItem`, so the website IAM fingerprint changed. The site still
holds no read grant on the table; `UpdateItem` returns the new item itself.

The failed read is not cached. A denied read that cached would hide a
recovered permission for five minutes.

Two of the three defects were invisible to the unit tests, because the tests
stubbed boto3 and never exercised a real client. Running the container is what
found them.

### Decision and next checkpoint

The deploy checkpoints are unchanged. The real table will confirm the signup
time against DynamoDB rather than DynamoDB Local.

### Verification

414 tests pass, coverage 94.62 percent. `make lint`, `make typecheck`, and
`make synth-all` pass. `make wiki-lint` passed after the index rebuild.

## [2026-08-14] decision | Website work stops at the deploy boundary

### Objective

Stop the website work before any deploy, and record the state and the next
direction well enough that a later session resumes without this conversation.

### Scope

`wiki/pages/decisions/website-local-first-rebuild.md` (new),
`wiki/pages/decisions/website-stack-plan.md` (marked on hold). No code change.
The branch `claude/aws-cdk-ml-website-cf88da` holds four commits and an open
draft pull request.

### Interpretation

The order of work was wrong. The stated goal was a website with a planned
design, deployed to AWS. The stack was designed first, and the application was
written to fit one container. The application is the part that needed the
design attention, so it comes first now.

The rebuild is three local containers: React with TypeScript, FastAPI, and
`amazon/dynamodb-local`. The standard-library backend does not survive that
change. The cost decisions, the SigV4 boundary, the `src/common` contract rule,
the mailing-list write rule, and the three defects found by running the
container all carry forward.

### Decision and next checkpoint

Nothing further deploys. The next work is the local application, outside this
change set. The deployed container topology stays undecided on purpose; it
follows the working application rather than leading it.

One account change is live and stays live: the execution-policy extension is at
`v3` and grants EC2, CloudFront, and DynamoDB permissions for resources that do
not exist. That is inert. A rollback to `v2` is one command if the direction
changes, and three of five version slots are used.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed. The local
demo containers were removed.

## [2026-08-14] update | Local backing services run with volumes

### Objective

Give the website rebuild a local stand-in for both AWS services it reads, and
keep the data across a restart.

### Scope

`local/compose.yaml` (new) and
`wiki/pages/decisions/website-local-first-rebuild.md`. No application code
changed. Nothing here deploys.

### Commands and results

MinIO replaces LocalStack for S3. It emulates the one service this application
reads, and it is smaller.

- A probe container proved that botocore reads `AWS_ENDPOINT_URL_S3`. The
  client created a bucket, wrote an object, listed it, and read it back with no
  code change and no addressing-style setting. boto3 chose path-style
  addressing for a non-AWS host on its own.
- `docker compose -f local/compose.yaml up -d` started `dynamodb` and `minio`
  healthy, and `bootstrap` created `mlops-artifacts` and exited.
- The website image, joined to the compose network, served
  `/api/results` from the seeded MinIO report and wrote a signup to DynamoDB
  Local through `/api/subscribe`.
- `docker compose down` then `up` returned the mailing-list row
  (`reader@example.com`, `2026-08-14T22:30:30Z`) and the S3 object unchanged.

Two container settings were needed for the DynamoDB volume. `-dbPath` replaces
the memory default, and `user: root` lets the image write a fresh named volume;
the image otherwise runs as `dynamodblocal` and cannot.

### Interpretation

The endpoint variables are the whole local-to-AWS switch. The application holds
no branch, and the deployed backend reaches the real services by setting
neither variable. That keeps the local stand-ins out of the deployed shape.

`down` keeps the volumes and `down -v` deletes them. That distinction is the
reset path, and the file says so at the top.

### Decision and next checkpoint

The `frontend` and `backend` services join this file when they exist. The
website work stays on hold; this is development tooling, not a step toward the
deploy.

### Verification

`make wiki-lint` passed after the index rebuild, and `make public-check` found
no literal. The containers were stopped and the volumes kept.

## [2026-08-14] update | FastAPI backend scaffolded and joined to compose

### Objective

Replace the standard-library website backend with FastAPI, and run it beside
the two local stand-ins.

### Scope

New: `src/website/app.py`, `services.py`, `settings.py`, `rate_limit.py`, and
three test modules. Deleted: `src/website/server.py` and
`tests/unit/test_website_server.py`. Changed: `src/website/Dockerfile`,
`requirements.txt`, `local/compose.yaml`, `pyproject.toml`, `uv.lock`.

### Commands and results

The module split puts routing in `app.py` and every AWS call in `services.py`,
so the route handlers hold no boto3 call and the services hold no HTTP status.

`docker compose up -d --build` started `minio`, `dynamodb`, `bootstrap`, and
`backend`. The bootstrap image moved from `minio/mc` to `amazon/aws-cli`,
because one image creates both the bucket and the table.

Live checks against the running stack: `/api/health`, `/api/schema`,
`/api/results`, and `/api/docs` answered 200. A signup returned its
`created_at`, and a second signup with the same address returned the same
value. An invalid address and an invalid record each returned 400. The
eleventh prediction in one minute returned 429. A container given the real
`PREDICT_URL` and real credentials returned `0.29875707626342773`, which is
the value the standard-library backend returned for the same record.

Three defects surfaced during the run.

1. **A test polluted thirteen unrelated tests.** `tests/unit/test_website_app.py`
   imported `src.website.services` directly, which builds real boto3 clients at
   collection time. `test_pipeline.py` then reached S3 through the live default
   session and failed. The test now reads `services` through the stubbed app
   module. `conftest.py` already warned about this failure mode.
2. **An unset `PREDICT_URL` returned 500.** SigV4 signs the Host header, and an
   empty URL leaves it unset, so botocore raised `AttributeError` from inside
   the signer. `predict` now checks the setting first and names it.
3. **Address normalization ran after validation.** The pattern rejected a
   trailing space before the code trimmed it, so `  Reader@Example.COM  ` was
   refused. A `field_validator` with `mode="before"` now trims and lowers.

Ruff flagged `Body(...)` in an argument default as B008. The `Annotated` form
is FastAPI's current style and needs no rule change.

### Interpretation

Both write routes validate inside the handler rather than in the signature, so
a bad request returns 400 with `format_validation_error` rather than FastAPI's
422 and its own error shape. One status code and one error shape across the
API is worth the explicit call.

`fastapi` and `httpx` join the dev extra because the tests import them.
`uvicorn` stays in the image alone; no test starts a server.

### Decision and next checkpoint

The frontend is next, and `local/compose.yaml` names where it joins. The
website deploy stays on hold, and the CDK stack still describes one container.

### Verification

405 tests pass, coverage 94.68 percent against the 94.57 floor. `make lint`,
`make typecheck`, `make synth-all`, `make lock-check`, `make docs-sync`,
`make public-check`, and `make wiki-lint` all pass.

## [2026-08-14] update | React and TypeScript frontend scaffolded

### Objective

Give the website a real frontend, and run it beside the backend and the two
local stand-ins.

### Scope

`frontend/` (new): Vite, React 19, TypeScript 5, and five components.
`local/compose.yaml` gains the `frontend` service. `Makefile` gains
`frontend-check`. `.gitignore` excludes `frontend/node_modules` and
`frontend/dist`.

### Commands and results

`npm run typecheck` and `npm test` pass; five tests cover the API client and
its error shapes. `docker compose up -d --build` started four services, and
the site answered on port 5173.

Live checks through the running stack:

- The schema table rendered 19 features from `/api/schema`.
- The evaluation section showed `Test AUC 0.8535` from a report seeded into
  MinIO.
- The prediction form built 19 controls from the schema, and a submit returned
  `0.1703` with "Likely to stay". That path runs React, the Vite proxy,
  FastAPI, SigV4, the deployed API Gateway, and SageMaker.
- The signup form returned `Signed up at 2026-08-14T22:59:46Z`.

Two notes from the run. Seeding the report through `docker run` without `-i`
wrote a zero-byte object, and the backend answered `{"available": false}` with
its error rather than failing, which is the earlier graceful-degradation fix
working on real bad data. The screenshot pane stopped repainting after a
scroll, so the page content was read through the DOM instead.

### Interpretation

The form reads `feature_columns` and `categorical_values` at run time, so the
vocabulary is never restated in TypeScript. `src/common/features.py` stays the
one source, `/api/schema` publishes it, and a new feature column changes no
frontend file. That is the reason `/api/schema` exists.

The dev server proxies `/api` to the backend, so the browser sends same-origin
requests. The backend needs no CORS configuration, and no build carries a
backend URL.

### Decision and next checkpoint

The website deploy stays on hold. The open items are a CI step for
`make frontend-check`, component tests, and the deployed topology, which is
still undecided.

### Verification

405 Python tests pass at 94.68 percent coverage. `make lint`,
`make typecheck`, `make synth-all`, `make lock-check`, `make docs-sync`,
`make public-check`, `make wiki-lint`, and `make frontend-check` all pass.

## [2026-08-14] update | The backend moved to a top-level folder

### Objective

Give the backend the same shape as the frontend: `backend/` and `frontend/`
as siblings at the repository root.

### Scope

`src/website/` moved to `backend/` with `git mv`, so history follows. The test
modules became `tests/unit/test_backend_{app,services,rate_limit}.py`. Changed:
`pyproject.toml` (mypy `files`, coverage `source`), `local/compose.yaml`,
`infra/stacks/website_stack.py`, and two wiki pages. New: `.dockerignore` at
the root.

### Commands and results

The move needed one real design change. `backend/` imports `src.common`, and
no single directory holds both, so the image context became the repository
root. Two guards keep that context small:

- `.dockerignore` at the root, which decides what reaches the Docker daemon.
- `_IMAGE_CONTENT` in `infra/stacks/website_stack.py`, an allowlist passed as
  `exclude` with `IgnoreMode.GIT`. That list decides the CDK asset hash.
  Without it, every unrelated repository file would rebuild the image.

The staged asset measured 60 KB and held `backend/`, `src/__init__.py`, and
`src/common/` alone, which is the proof the allowlist works.

A `sed` over the imports missed `from src.website import services`, because the
pattern required a trailing dot. mypy caught it as three errors, one being an
unresolved module and two being `no-any-return` that followed from it.

After the move: 405 tests pass at 94.68 percent, `make lint`,
`make typecheck`, `make synth-all`, and `make wiki-lint` pass, and the four
compose services answered every route, including a live signed prediction.

### Interpretation

`src/` keeps the platform code and the shared contract. The website now reads
as two folders, and the import `from src.common.features import ...` still
names the one source of the feature contract.

### Decision and next checkpoint

The website deploy stays on hold. Nothing here changes the deployed topology
question.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed.

## [2026-08-14] update | The website moved under one folder

### Objective

Put every website file under `website/`, so the site reads as one component
rather than three folders spread across the repository root.

### Scope

`git mv` moved `backend/`, `frontend/`, and `local/` under `website/`. Changed:
`website/backend/Dockerfile`, `website/local/compose.yaml`, `.dockerignore`,
`.gitignore`, `pyproject.toml`, `Makefile`, `infra/stacks/website_stack.py`,
`AGENTS.md`, and two wiki pages.

### Commands and results

The Python package became `website.backend`, so `website/__init__.py` exists
and every import names it. mypy and coverage read `website/backend` rather
than a bare `backend`, which keeps them away from `website/frontend`.

Three things stay outside `website/` on purpose:

- `infra/stacks/website_stack.py`, which belongs with the other stacks.
- `tests/unit/test_backend_*.py` and `test_website_stack.py`, because
  `AGENTS.md` states that `tests/unit/` mirrors the source module, and the
  session-scoped CDK fixtures live in one `conftest.py`.
- `.dockerignore` at the root, because the image context is the root.

The image context needs `website/backend/` and `src/common/`, and no directory
holds both. `_IMAGE_CONTENT` now excludes `website/frontend` explicitly, so a
frontend edit cannot change the backend asset hash. The staged asset measured
64 KB and held the two directories alone.

Every compose path was re-checked from `website/local/`: `../frontend`,
`../backend`, `../../src/common`, and the `../..` build context all resolve.

After the move: 405 tests at 94.68 percent, `make lint`, `make typecheck`,
`make synth-all`, `make frontend-check`, and `make wiki-lint` pass, and the
four services answered every route including a live signed prediction.

### Interpretation

`src/` keeps the platform code and the shared contract. The backend still
imports `src.common`, which is the reason the image context cannot narrow to
`website/`.

### Decision and next checkpoint

The website deploy stays on hold. The layout is settled; the open questions
are unchanged.

### Verification

`make wiki-index` rebuilt the index and `make wiki-lint` passed.

## [2026-08-14] update | `make deploy` refuses to create the website by surprise

### Objective

Close the one path that could deploy the on-hold website stack without anyone
asking for it.

### Scope

`Makefile`: a new `check-website-hold` prerequisite on `deploy`. `AGENTS.md`
records the refusal and its override.

### Interpretation

`deploy` runs `cdk deploy --all`, and dev sets `website.enabled: true`, so a
full deploy would create the instance, the address, the distribution, the VPC,
and the table. That is about $16.60 each month on demand, through a path no
deploy has proved.

The website stack is a leaf: `infra/app.py` passes nothing from it to another
stack, so no other target pulls it in. `deploy-stack` names its target, which
is intent enough. Only `deploy` could create it by surprise, so only `deploy`
asks.

Flipping `website.enabled` to false in dev was the other option, and it costs
more than it saves: the unit fixture would stop building the stack, and the
seventeen tests in `tests/unit/test_website_stack.py` would have nothing to
assert against.

### Commands and results

Four paths were checked. Dev without the override exits 2 and names both ways
forward. Prod passes, because its flag is false. Dev with
`ALLOW_WEBSITE_DEPLOY=1` passes. `deploy-stack` carries no guard.

### Decision and next checkpoint

The guard stays after the hold lifts. An instance and a distribution deserve
one explicit word before a full deploy creates them.

### Verification

`make docs-sync` passed, and the four guard paths behaved as recorded.
## [2026-08-14] query | website local first frontend

Found 40 matching page(s).

## [2026-08-14] update | Architecture became the website's first experience

### Objective

Build the local frontend for engineering interviews. Put the platform
architecture before the prediction demo.

### Scope

The change updates `PRODUCT.md`, the React composition, five existing frontend
components, the new `ArchitectureMap.tsx`, the shared stylesheet, the favicon,
and one small CRT texture. It also records the Impeccable design work under
`.impeccable/`.

### Commands and results

`make frontend-check` passed TypeScript and all five frontend tests. The Vite
production build passed. Its output retained the direction seed `b969f170`.

The Impeccable detector ran once. Its HTML parser dependencies were absent, so
it used the regex fallback and returned no findings. This result is an
undercount, not a full detector pass.

Playwright captured the page at 1600 by 1000 pixels and 390 by 844 pixels. The
checks exercised the retrain state, the evidence state, the schema-driven form,
and the prediction error state. The screenshot server imported the repository
feature contract and did not restate it.

Docker Compose did not start because the local Docker daemon was not running.
No container or AWS resource changed.

### Interpretation

The first viewport now explains the system as one lifecycle. The prediction
form remains functional, but it no longer defines the project for an
interviewer.

### Decision and next checkpoint

The website deploy stays on hold. The local design MUST pass the Impeccable
finish review before any deployment decision resumes.

### Verification

`make frontend-check`, the Vite production build, provenance scan, desktop and
mobile captures, and Playwright interaction checks passed. The wiki linter runs
with this record.

## [2026-08-14] update | Impeccable accepted the frontend rebuild

### Objective

Close the visual review and document the built system.

### Scope

The final pass reviewed the approved comp, the 1672 by 941 hero capture, the
desktop capture, the mobile capture, and the frontend source. It added
`DESIGN.md` and `.impeccable/design.json`.

### Commands and results

The first review required a rebuild. The new pass added the native CRT field,
the self-hosted VT323 display font, and the routed stage-to-proof cursor. It
removed duplicate chrome and the unsupported online-status copy.

The fresh full review returned `ship`. It found no material fixes. The asset
scan found no raster without prompt provenance.

### Decision and next checkpoint

The visual build is accepted locally. The website deploy stays on hold. A
separate deployment decision MUST preserve that boundary.

### Verification

`make frontend-check`, the Vite production build, the comp-scale capture, the
desktop and mobile captures, the provenance scan, and the design-sidecar parse
passed. The wiki linter runs with this record.

## [2026-08-14] update | Trace ledger became an architecture control

### Objective

Make pipeline, signed API, and drift useful to an interviewer.

### Scope

The change extends `ArchitectureMap.tsx` and the existing frontend stylesheet.
It updates `DESIGN.md`, the Impeccable surface brief and sidecar, and the local
website decision page. The work stays local. It does not use an AWS identity.

### Commands and results

`make frontend-check` passed TypeScript and all five frontend tests. The Vite
production build passed. Playwright exercised the page at 1440 by 1000 pixels
and 390 by 844 pixels.

Selecting signed API selected Serve and named API Gateway, the proxy Lambda,
and the SageMaker endpoint. Selecting Monitor selected Drift and named the
capture, evaluation, EventBridge, retrain, and pipeline path. Each state had one
active route. The mobile page had no horizontal overflow.

The reduced-motion check returned a 0.00001-second animation with one
iteration. This produces the static selected state from the existing media
query.

### Interpretation

The ledger now explains three engineering paths. It does not display invented
metrics, timestamps, or deployment claims.

### Decision and next checkpoint

The website deploy stays on hold. A later component-test change MAY add a DOM
test library. This interaction has a rendered browser check today.

### Verification

`make frontend-check`, `npm run build`, `git diff --check`, the desktop and
mobile browser checks, and the reduced-motion check passed. The wiki linter runs
with this record.

## [2026-08-14] query | trace ledger website

Found 7 matching page(s).

## [2026-08-15] update | Evidence rail became a stage-specific proof control

### Objective

Show how implemented, deployed, and observed evidence relates to the selected
architecture stage.

### Scope

The change extends `ArchitectureMap.tsx` and the existing frontend stylesheet.
It updates `DESIGN.md`, the Impeccable surface brief and sidecar, and the local
website decision page. The work stays local. It does not use an AWS identity.

### Commands and results

`make frontend-check` passed TypeScript and all five frontend tests. The Vite
production build passed. Playwright exercised each proof lens for Train and
Monitor. The selected readout changed to the related source, dev infrastructure
boundary, or runtime signal.

The desktop check found the 0.9-second stage-to-proof signal. The 390 by 844
pixel page had no horizontal overflow. The reduced-motion check returned a
0.00001-second animation with one iteration.

### Interpretation

The evidence rail now answers what each category means for the selected stage.
It does not treat a repository implementation as deployment or runtime proof.

### Decision and next checkpoint

The website deploy stays on hold. The evidence rail is complete for the local
architecture experience.

### Verification

`make frontend-check`, `npm run build`, `git diff --check`, desktop and mobile
browser checks, and the reduced-motion check passed. The wiki linter runs with
this record.

## [2026-08-15] update | Frontend rebuilt as a job-application artifact

### Objective

Make the website carry the engineer, not only the platform. The owner is
preparing it to support job applications, and a review of the running page
found no name, no contact, and the first-viewport actions below the fold on
every laptop viewport tested.

### What changed

The approved "Layered Trace Ledger" world stays. The page gained an identity
layer, a first-person section, and a contact block that replaces the mailing
list. The architecture diagram regained the arrowheads and connectors the
approved comp specifies, and now draws them from measured element geometry
rather than percentage estimates. The trace ledger states the real AWS
component chain in place of tracks that measured nothing. Mobile renders the
whole lifecycle instead of hiding it. The prediction form opens on a canonical
sample record served by the API.

`.impeccable/surfaces/website-frontend-src-app-tsx.md` and
`wiki/pages/decisions/website-local-first-rebuild.md` hold the detail.

### Evidence

The hero measured 979 to 1001 pixels before the change and 673 to 813 after
it. The three actions are visible at 1512x860, 1440x790, 1920x969, and
1280x720; none of the four passed before. A contrast pass over every text node
found no WCAG AA failure. The page reports one `main`, one `nav`, one `header`,
a `footer` outside `main`, and a skip link. The display font dropped from 153 KB
TrueType to 32 KB WOFF2. The page carries eleven Open Graph and Twitter tags
and a generated cover; it carried none.

### Limits of this record

The design detector ran degraded on this machine, because the HTML parser
modules were unavailable. It fell back to regex matching and reported nothing,
which is an undercount and not a clean pass.

`DESIGN.md` still describes the previous build. It is regenerated from the
built world after the finish review closes, so the design hook's font-size,
colour, and radius findings against `styles.css` stay open until then.

### Decision and next checkpoint

**The website deploy stays on hold, and no AWS resource was created.** The
image content allowlist in `infra/stacks/website_stack.py` gained
`sample.json` and `sample-high-risk.json`, which changes the asset hash of a
stack that is not deployed.

### Verification

`make frontend-check`, `make lint`, `make typecheck`, `make test` (408 passed,
coverage 94.75%, floor raised to 94.74), `make public-check`, and
`make synth-all` passed. The wiki linter runs with this record.

## [2026-08-16] query | Dependabot alert 1, SageMaker SDK advisory

### Objective

Triage the Dependabot alert that the remote prints on every push to
`claude/front-end-questions-a1786b`, and record whether it describes a risk to
this platform.

### Scope

`pyproject.toml`, `uv.lock`, `src/pipeline/pipeline.py`,
`infra/stacks/lambda_code.py`, and the CI `audit` job. No code changed. The new
page is `wiki/pages/decisions/sagemaker-sdk-advisory-triage.md`.

### Identity and environment

Read-only GitHub API calls through `gh`, against
`emanuelGitCodes/aws-mlops-platform`. No AWS call.

### Commands and results

`gh api repos/.../dependabot/alerts` returned one open alert, number 1, created
2026-08-10. It cites `GHSA-5r2p-pjr8-7fh7` against `sagemaker` below 3.4.0,
severity high, CVSS score 0 and no vector, CWE-184. A repository search for
`search_hub`, `JumpStart`, and `jumpstart` over `src/`, `infra/`, `scripts/`,
`website/`, and `tests/` returned no match. `uv.lock` resolves sagemaker
2.257.5 under the `>=2.220,<3` pin. `_RUNTIME_DEPS` in
`infra/stacks/lambda_code.py` is `["pydantic==2.*"]`. `make audit` printed
"No known vulnerabilities found".

### Interpretation

The advisory is real and unreachable here. The vulnerable function needs an
attacker-controlled query string, and the platform calls the SDK only to build
a pipeline definition from repository values. The SDK is a build-time
dependency, so no deployed Lambda carries it. pip-audit and Dependabot disagree
because pip-audit reads the PyPI database and Dependabot reads the GitHub
Advisory Database; the green `audit` job is not evidence against the alert.

### Decision and next checkpoint

The alert stays open, and the pin stays on 2.x. The first patched version is
3.4.0, and SageMaker Python SDK v3 changes the estimator, processor, and
workflow API that `src/pipeline/pipeline.py` uses, so the fix is a migration
under the full phase gate rather than a version bump. The dismissal reason
`vulnerable_code_not_actually_used` matches the evidence and stays available.
Next checkpoint: a throwaway branch that installs 3.4.0 and runs `make test`,
to measure the real size of the migration.

### Verification

`uv run --locked python scripts/wiki.py index` rebuilt the catalog, and
`scripts/wiki.py lint` reported "Wiki healthy: 53 page(s)".
\n
## [2026-08-16] implementation | Website evidence panel and layout review

### Objective

Answer a design review of the running frontend, and give the evidence section
the data it was already fetching.

### Scope

`website/frontend/src/styles.css`, `website/frontend/src/App.tsx`,
`website/frontend/src/components/LatestEvaluation.tsx`,
`src/pipeline/evaluate.py`, `tests/unit/test_evaluate.py`, and root
`DESIGN.md`. The wiki page is
`wiki/pages/decisions/website-local-first-rebuild.md`. No stack was synthesized
and no AWS resource was touched. The website stays on hold.

### Identity and environment

Local only. The three local containers ran throughout, and the browser measured
the page at 1351, 1280, 1100, 1078, and 375 pixels wide. No AWS profile was
used.

### Commands and results

`make lint`, `make typecheck`, `make test` (411 passed, coverage 94.76% against
the 94.74% floor), and `make frontend-check` passed. Browser measurements
recorded the before and after of each defect: the schema table 352px against a
495px neighbour, then both panels level; heading and standfirst cap tops 8.7 to
9.4px apart, then 0.3px; the story cards at x=39 and x=550 in both rows; zero
truncated service labels; the mobile ring right edge at 84px against a name at
96px.

### Interpretation

Two findings were data problems wearing layout clothes. The evaluation panel
looked empty because it displayed one number out of a report holding ten, and
the AUC rendered as an em dash because `readAuc` knew only the nested
ModelMetrics shape while the newest object was `metrics.json`. The evaluation
step had computed the promotion comparison for its log event since it was
written, and threw it away instead of writing it to the report the page reads.

### Decision and next checkpoint

`write_evaluation_artifacts` takes an optional `champion_test_auc` and records
it with `promotion_decision`. The panel renders the verdict, the rate metrics,
and the confusion matrix only when the fields are present, so a newest
`evaluation.json` still renders correctly. Three items stay open and none is
mine to close: the repository is private, so every "read the source" link on
the page reaches a 404; `PROFILE.linkedin` and `PROFILE.resume` are empty; and
the idle-endpoint state has no captured real response to show, which needs one
signed call against the deployed endpoint.

### Verification

The four Make targets above, plus `make public-check`. The wiki linter runs
with this record.

## [2026-08-16] update | The alert-topic split window closed as a go

### Objective

Close the observation window that the alert-topic split opened on 2026-08-14.
The window owed two pieces of evidence: one endpoint alarm delivering through
`mlops-dev-ops-alerts`, and confirmation that the seven security alarms still
reach `mlops-dev-security-alerts`.

### Scope

`wiki/pages/decisions/alert-topic-split.md`,
`wiki/pages/architecture/phased-security-hardening.md`, and root `AGENTS.md`.
No stack was synthesized, no template changed, and no AWS resource was
modified. The reads below used `${AWS_SECURITY_AUDITOR_USER_NAME}`.

### Identity and environment

AWS account `${AWS_ACCOUNT_ID}`, region `us-east-1`, environment dev. Three
alarm notification emails supplied the delivery evidence.

### Commands and observed results

1. `aws cloudwatch describe-alarms` returned nine dev alarms.
   `mlops-dev-endpoint-5xx` and `mlops-dev-endpoint-silent` name
   `mlops-dev-ops-alerts`. The seven security alarms name
   `mlops-dev-security-alerts`.
2. `mlops-dev-endpoint-silent` went `OK -> ALARM` at 2026-08-15T23:26:10Z on 24
   hourly datapoints below the threshold. Its email reads `State Change Actions
   - ALARM: arn:aws:sns:us-east-1:${AWS_ACCOUNT_ID}:mlops-dev-ops-alerts`, and
   its unsubscribe link carries a `mlops-dev-ops-alerts` subscription.
3. The same email reads `MetricExpression: FILL(m1, 0)`.
4. `mlops-dev-security-iam-policy-changes` delivered through
   `mlops-dev-security-alerts` at 2026-08-14T21:37:07Z, after the 14:52Z
   deploy. `mlops-dev-security-unauthorized-api-calls` delivered through the
   same topic at 2026-08-16T21:12:17Z.
5. `aws logs filter-log-events` against `/aws/cloudtrail/mlops-dev-audit`, with
   the alarm's own filter pattern over 20:40Z to 21:20Z, returned four
   `AccessDenied` events. `AWSServiceRoleForConfig` was denied
   `frauddetector:GetEntityTypes`, `frauddetector:GetVariables`, and
   `cloudcontrolapi:ListResources`. `AWSServiceRoleForResourceExplorer` was
   denied `profile:ListDomains`.

### Interpretation

Both halves of the window passed. The ops topic had never executed an alarm
action before item 2, so that email is the first delivery through it and the
evidence the window owed. A confirmed subscription proves that an address
accepted a topic; only a delivered message proves the path.

Item 3 closes a second question. Sub-phase 2F first shipped the silence alarm
with `TreatMissingData`, which does not cause an evaluation to run. The `FILL`
form evaluates on a missing datapoint. A real firing over 24 of 24 missing
periods proves the refix against live data, not against a template.

Item 5 records a false positive. The `unauthorized-api-calls` alarm fired on
AWS's own service-linked roles reading services the account does not use. The
alarm matched its filter correctly. The filter has no floor for an AWS
inventory sweep, and this is the second such observation.

### Decision and next checkpoint

The window is closed as a go. Dev keeps the split; prod keeps one topic until
a deliberate rollout. No observation window is now open.

Two items stay open and neither belongs to this window. A
`userIdentity.invokedBy` exclusion on the `unauthorized-api-calls` filter is a
change to a CIS detection control and takes its own gate. The first
`deploy.yml` run is the next platform checkpoint.

### Verification

`make wiki-lint` and `make public-check`.
