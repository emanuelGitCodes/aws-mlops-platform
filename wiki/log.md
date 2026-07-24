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
Mlops-Dev-Data-BucketNotificationsHandler050a0587b-9dkMqJlLvXCL
```

CloudFormation then rolled the stack back to `ROLLBACK_COMPLETE`. The buckets again emitted `DELETE_SKIPPED` because they use `RemovalPolicy.RETAIN`; their empty state must be checked and cleaned after the stack failure.

### Interpretation

The CDK `Custom::S3BucketNotifications` resource uses a helper Lambda to configure the raw bucket's notification. The CloudFormation execution role therefore needs permission to invoke that helper. This is another execution-policy gap, not a failure of the `${MLOPS_DEPLOYER_USER_NAME}` role-assumption policy and not a failure of the application proxy Lambda.

### Recovery decision

Add only `lambda:InvokeFunction` to the Lambda actions in the local `MLOpsCloudFormationExecutionPolicy` document, validate it, and create policy version `v4` with `${AWS_ADMIN_USER_NAME}`. Then delete the failed stack, inspect and remove only the new confirmed-empty retained buckets, and retry.

## [2026-07-10] cleanup | Third-attempt retained buckets removed

### Result

The three buckets retained by the third failed Data-stack attempt were confirmed empty with zero object versions and zero delete markers. They were deleted with `${AWS_ADMIN_USER_NAME}`:

- `mlops-dev-data-rawbucket0c3ee094-9dn8m844frun`
- `mlops-dev-data-curatedbucket6a59c97e-lxdysi6zkqtx`
- `mlops-dev-data-artifactsbucket2aac5544-fxrncmav2v0j`

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
- SageMaker execution `tsjaspu5m480` failed in `Preprocess` with `ModuleNotFoundError: No module named 'src'`, before the `Train` step. The training log group is therefore expected to be empty for this execution.

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

1. The prior execution `tsjaspu5m480` failed before training because a
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
   `pipelines-nntqc422p0p1-Train-beG0CsQiXC`. CloudWatch confirmed a 4,930-row,
   19-feature training matrix and 1,056 validation rows; validation AUC reached
   `0.80610` during the logged rounds.
5. The first evaluation run failed with `ModuleNotFoundError: No module named
   'xgboost'`. Evaluation was moved to its own `FrameworkProcessor` bundle with
   `xgboost==1.7.6` in `evaluation_runtime/requirements.txt`.
6. CloudWatch for `pipelines-nntqc422p0p1-Evaluate-kij0xE0MAF` confirmed the
   wheel downloaded and installed, then printed `test AUC: 0.8398`.
7. Pipeline execution `nntqc422p0p1` succeeded and registered approved model
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
- Artifacts bucket execution prefix for retry `53ww289tjhoz`.
- Deployment checkpoint, closed-loop concept, overview, and new immutable
  rollout source.

### Identity and environment

The normal `${MLOPS_DEPLOYER_USER_NAME}` identity could use the CDK deployment path but is
not allowed to call `sagemaker:ListModelPackages`, which SDK pipeline upsert
uses to resolve the champion. The existing `${AWS_ADMIN_USER_NAME}` break-glass profile
therefore upserted only the SDK-managed pipeline; no IAM policy was widened.

### Commands and observed results

1. The first post-update execution `3sg58t1vx4uv` reached `Evaluate`, wrote
   `evaluation.json`, `metrics.json`, and `predictions.csv`, then failed with
   Python 3.9 `TypeError: zip() takes no keyword arguments` before PNG output.
2. The error came from `zip(..., strict=True)` in the report writer. The loops
   were changed to index-based access, focused evaluation tests passed, and the
   pipeline was upserted again.
3. Retry execution `53ww289tjhoz` succeeded and wrote the full metrics,
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
   `53ww289tjhoz` succeeded through all steps and retains the complete report
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

Dev account, `us-east-1`, using the least-privilege `mlops-security-auditor`
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

Dev account, `us-east-1`, `mlops-security-auditor` profile, read-only.
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

Dev account, `us-east-1`, `mlops-deployer` profile, which assumes the CDK
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
account using the `mlops-security-auditor` profile in `us-east-1`. The tool
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
least-privilege `mlops-security-auditor` profile and were read-only. The single
mutating step, `make deploy-stack`, used `mlops-deployer`.

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
