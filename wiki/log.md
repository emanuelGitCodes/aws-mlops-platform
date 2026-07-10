# Wiki log

Append-only record of ingests, queries, and lint passes.

## [2026-07-10] update | CDK deployment IAM walkthrough

Documented the CDK bootstrap roles, the two-policy deployment boundary, the break-glass administrator pattern, the completed `CDKToolkit` bootstrap checkpoints, and the expected IAM inspection denial after removing `AdministratorAccess`.

## [2026-07-10] query | SageMaker permissions

Found 7 matching page(s).

## [2026-07-10] lint

Wiki health check passed.

## [2026-07-10] lint

Wiki health check passed.

## [2026-07-10] query | closed drift

Found 5 matching page(s).

## [2026-07-10] lint

Wiki health check passed.

## [2026-07-10] lint

Wiki health check passed.

## [2026-07-10] lint

Wiki health check passed.

## [2026-07-10] query | SageMaker permissions

Found 7 matching page(s).

## [2026-07-10] query | IAM CDK bootstrap deployment policy

Found 5 matching page(s).
## [2026-07-10] lint

Wiki health check passed.

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
