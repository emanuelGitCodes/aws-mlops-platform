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
