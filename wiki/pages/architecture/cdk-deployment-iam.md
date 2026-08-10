---
type: architecture
title: CDK deployment identity and bootstrap boundary
created: "2026-07-10"
updated: "2026-08-09"
sources: ["../../../infra/app.py", "../../../infra/cdk.json", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/policies/mlops-cloudformation-execution-policy-extension.json", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/mlops-cloudformation-execution-policy-v1-2026-07-10.json", "https://docs.aws.amazon.com/cdk/v2/guide/deploy.html", "https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-bootstrap.html"]
summary: "A break-glass administrator bootstraps CDK, while ${MLOPS_DEPLOYER_USER_NAME} assumes narrowly scoped CDK roles and CloudFormation applies the application execution policy."
---
# CDK deployment identity and bootstrap boundary

## Confirmed

### Identities

The account uses separate identities for separate levels of authority:

| Identity | Intended use | Authority |
|---|---|---|
| Root user | Account recovery and account-level setup only | Highest account authority; not for routine deployment. |
| `${AWS_ADMIN_USER_NAME}` | Break-glass administration | Can repair IAM or infrastructure access when the deployment identity is blocked. |
| `${MLOPS_DEPLOYER_USER_NAME}` | Normal CDK deployment | Member of `MLOps-Deployers`; receives only the CDK deployment policy. |

The `${AWS_ADMIN_USER_NAME}` profile remains available in a separate terminal so removing temporary administrator access from `${MLOPS_DEPLOYER_USER_NAME}` cannot lock the account out.

### What CDK bootstrap created

The command below bootstrapped the `us-east-1` environment:

```bash
cdk bootstrap aws://${AWS_ACCOUNT_ID}/us-east-1 \
  --profile ${MLOPS_DEPLOYER_USER_NAME} \
  --cloudformation-execution-policies \
  arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCloudFormationExecutionPolicy
```

The result was `CDKToolkit: CREATE_COMPLETE`. The bootstrap stack provides CDK asset storage and the roles CDK uses during deployment. The created roles were:

- `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`: assumed by CloudFormation to create or update application resources.
- `cdk-hnb659fds-deploy-role-${AWS_ACCOUNT_ID}-us-east-1`: used by the CDK CLI for CloudFormation deployment operations.
- `cdk-hnb659fds-file-publishing-role-${AWS_ACCOUNT_ID}-us-east-1`: used by the CDK CLI to upload synthesized assets to the bootstrap S3 bucket.
- `cdk-hnb659fds-lookup-role-${AWS_ACCOUNT_ID}-us-east-1`: used by the CDK CLI for environment lookups.
- `cdk-hnb659fds-image-publishing-role-${AWS_ACCOUNT_ID}-us-east-1`: available for container assets, but not needed by this repository's zip-based Lambda assets.

`cdk bootstrap` does not deploy the six application stacks. It prepares the environment that a later `cdk deploy --all` will use.

### Two policy layers

The deployment uses two different policy layers:

| Policy or role | Attached to | What it allows | Why it exists |
|---|---|---|---|
| `MLOpsCdkDeploymentPolicy` | Group `MLOps-Deployers` | `sts:GetCallerIdentity`, `sts:AssumeRole`, `sts:TagSession`, and SSM reads for the CDK bootstrap version. Role assumption is limited to the lookup, deploy, and file-publishing roles. | Lets the human or CI identity use CDK without direct S3, Lambda, SageMaker, or CloudFormation permissions. |
| `MLOpsCloudFormationExecutionPolicy` | CDK CloudFormation execution role | The S3, IAM, Lambda, Logs, SQS, EventBridge, API Gateway, CloudWatch, Budgets, SageMaker registry, SSM, and KMS actions needed by the synthesized application templates. `iam:PassRole` is restricted to application roles and service principals. | Gives CloudFormation the permissions needed to create the application resources. |
| Runtime policies | Application Lambda and SageMaker roles | Only the storage, invocation, pipeline, or deployment actions needed by each runtime component. | Separates deployment authority from runtime authority. |

The important distinction is that `${MLOPS_DEPLOYER_USER_NAME}` does not directly create the application resources. It assumes CDK bootstrap roles. CDK uses the deploy role and file-publishing role, then CloudFormation assumes the CloudFormation execution role to apply the synthesized templates.

### The command-line lifecycle

1. `cdk synth` runs locally and produces CloudFormation templates in `cdk.out`. It does not change AWS resources.
2. `cdk diff` compares the synthesized templates with the deployed stack state. It may publish synthesized templates to the CDK bootstrap S3 bucket and create read-only CloudFormation change sets for an accurate comparison, but it does not create or update the application resources.
3. `cdk deploy --all` publishes assets, submits CloudFormation changesets, asks for approval when configured, and then lets CloudFormation create or update the six application stacks.
4. The six stacks in `infra/app.py` are Data, Ingestion, Registry, Training, Serving, and Monitoring. The pipeline document and Model Monitor setup remain SDK-driven operations described in the [platform design decisions](../decisions/platform-design.md).

### Verification and expected failure

The completed checkpoints were:

- `CDKToolkit` returned `CREATE_COMPLETE`.
- The CloudFormation execution role had `MLOpsCloudFormationExecutionPolicy` attached.
- All five standard bootstrap roles were present.
- `MLOpsCdkDeploymentPolicy` was created and attached to `MLOps-Deployers`.
- `AdministratorAccess` was detached from `MLOps-Deployers`.
- Using the `${AWS_ADMIN_USER_NAME}` profile, IAM inspection showed that `MLOps-Deployers` contains only `MLOpsCdkDeploymentPolicy`.

After the administrator policy was removed, this command failed when run with the `${MLOPS_DEPLOYER_USER_NAME}` profile:

```text
iam:ListAttachedGroupPolicies on resource: group MLOps-Deployers
```

That failure is intentional. IAM inspection belongs to `${AWS_ADMIN_USER_NAME}`; the deployment identity should not be able to enumerate or modify group policies. The deployment identity can still authenticate and assume its three CDK roles.

The administrator verification confirmed the intended final group state. The next verification is to authenticate as `${MLOPS_DEPLOYER_USER_NAME}` and run `cdk diff`; that test checks the deployment path rather than IAM inspection authority.

The restricted `cdk diff` then completed with `Number of stacks with differences: 6`. It published all six synthesized templates and displayed the six application stacks as new because they have not been deployed. No role-assumption or `AccessDenied` error appeared.

The first deployment then exposed a missing execution-policy action. CloudFormation successfully assumed `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`, but all three Data stack buckets failed when CloudFormation called `s3:PutEncryptionConfiguration`. The failure was repeated for `RawBucket`, `CuratedBucket`, and `ArtifactsBucket`, then `Mlops-Dev-Data` rolled back to `ROLLBACK_COMPLETE`.

This is a useful distinction: the `${MLOPS_DEPLOYER_USER_NAME}` policy and CDK bootstrap-role path worked, while the CloudFormation execution policy was incomplete. The missing action is required because `infra/stacks/data_stack.py` requests KMS-managed default encryption for each bucket.

The execution policy was then updated to version `v2` with the missing S3 action. The failed `Mlops-Dev-Data` stack was deleted successfully, so the stack name is available for a clean deployment retry.

On the retry, the three encrypted buckets and their bucket policies reached `CREATE_COMPLETE`, confirming that version `v2` fixed the original S3 failure. The next failure occurred while CloudFormation managed the CDK-generated `BucketNotificationsHandler` inline policy: the execution role lacked `iam:GetRolePolicy` on the handler role. The stack rolled back again. Because the data buckets use `RemovalPolicy.RETAIN`, their `DELETE_SKIPPED` events should be checked for retained empty buckets before the failed stack is deleted again.

On the next retry, version `v3` allowed the generated inline policy and handler Lambda to complete. The custom resource `RawBucket/Notifications` then failed because the CloudFormation execution role lacked `lambda:InvokeFunction` on the generated `BucketNotificationsHandler` Lambda. This permission is needed for CloudFormation to invoke the helper that configures the S3 notification. The stack rolled back again.

The three buckets retained by that third failed attempt were verified empty and deleted successfully after policy version `v4` was created. A final bucket-prefix check remains before the next deployment retry.

The AWS account currently shows six matching `mlops-dev-data-` buckets: two Raw, two Curated, and two Artifacts buckets. The two sets correspond to the first and second deployment attempts. They are retained cleanup candidates, not proof that two Data stacks are active.

All six retained buckets were inspected with `s3api list-object-versions`; each returned zero object versions and zero delete markers. They are empty cleanup candidates from the failed deployments.

The six empty retained buckets were then cleaned up: one Raw bucket had already been deleted, one Curated bucket was already missing, and the remaining four buckets were deleted successfully. A final prefix query returned no `mlops-dev-data-` buckets.

The final deployment completed all six application stacks. The later pipeline and API checks confirmed that the CDK resource boundary was working: the API reached the proxy Lambda, and the pipeline could be upserted and started. The remaining failure was inside SageMaker Processing, not the CDK deployment path. See the [deployment and pipeline troubleshooting checkpoint](deployment-and-pipeline-troubleshooting.md) for the end-to-end evidence.

Phase 2A introduced a repository-owned copy of the execution policy and rotated
the live managed policy from archived non-default `v1` to default `v6`. The
exact live `v1` document was fingerprinted before deletion, and `v5` remains
available for rollback. The Phase 2 additions cover only the KMS, CloudTrail,
SNS, encrypted Logs, metric-filter, and alarm lifecycle required by the audit
plan. `cloudtrail.amazonaws.com` was added to the existing `iam:PassRole`
service condition without changing its `Mlops-Dev-*` role-resource boundary.
The managed policy remains attached only to the CDK CloudFormation execution
role. See the [Phase 2A completion record](../sources/aws-security-hardening-phase-2a-completion-july-12-2026.md).

## Synthesis

This setup separates three trust boundaries that are easy to confuse:

1. **Who starts CDK:** `${MLOPS_DEPLOYER_USER_NAME}` authenticates with an access key and is allowed to assume specific bootstrap roles.
2. **Who applies infrastructure:** CloudFormation assumes the CDK CloudFormation execution role and uses its customer-managed execution policy.
3. **Who runs the application:** Lambda and SageMaker service roles receive runtime permissions such as S3 access, endpoint invocation, or pipeline execution.

The deployment identity is therefore a control-plane identity, not an application runtime identity. An interview explanation should mention both the permission granted and the permission deliberately absent: the user can assume the deploy path, but cannot directly call the application services or inspect IAM groups.

The ingestion path follows the same failure-isolation principle. S3 emits an event to EventBridge, EventBridge places it on SQS, and the validation Lambda consumes one message at a time. SQS provides buffering and retry behavior; after the configured receive limit, the message moves to the DLQ for inspection instead of blocking the rest of the queue.

## Applying the execution policy

**The execution boundary spans two managed policies, and the split is a size
limit rather than a design preference.** AWS caps one managed policy at 6144
characters. The main document reached 5888 on 2026-08-08, and a rotation adding
one eight-action statement failed with `LimitExceeded: Cannot exceed quota for
PolicySize: 6144`.

| Document | Live policy |
|---|---|
| `mlops-cloudformation-execution-policy.json` | `MLOpsCloudFormationExecutionPolicy` |
| `mlops-cloudformation-execution-policy-extension.json` | `MLOpsCloudFormationExecutionPolicyExtension` |

Both attach to `cdk-hnb659fds-cfn-exec-role-*`, so CloudFormation evaluates the
union. **Add a new grant to the extension.** The main document has 256 bytes
free and cannot take one. The extension holds the OIDC provider lifecycle and
the exact Access Analyzer archive-rule lifecycle. It does not grant
`ApplyArchiveRule`; that action changes finding status and remains an operator
step. A test measures both documents against the quota, so the next size
failure arrives in CI rather than at the AWS API.

The extension is live at `v2`. Version `v1` remains the rollback document. The
rotation used two of the five policy-version slots and required no cleanup.

Statement ids are unique across both files, and a test asserts it. A duplicated
`Sid` would leave a reader unsure which file owns a grant.

The repository copy of the execution policy
(`infra/policies/mlops-cloudformation-execution-policy.json`) parameterizes
account-specific values such as `${AWS_ACCOUNT_ID}` using the `.env.example`
placeholder convention. Before creating a new IAM policy version, substitute
the placeholders from a populated local `.env`, for example:

```bash
set -a && source .env && set +a
envsubst < infra/policies/mlops-cloudformation-execution-policy.json > /tmp/policy.json
aws iam create-policy-version --policy-arn <policy-arn> \
  --policy-document file:///tmp/policy.json --set-as-default
```

Any hash comparison between the live document and the repository applies to
the substituted output, not the raw parameterized file.

## Tensions or open questions

- `MLOpsCloudFormationExecutionPolicy` is scoped by service and action, but the current document uses `Resource: "*"` for many management actions because generated CloudFormation names are not all known before deployment. It is narrower than `AdministratorAccess`, but it is not complete resource-level least privilege.
- The training (pipeline) role still uses AWS-managed `AmazonSageMakerFullAccess`; Phase 5B removed it from the model execution role. That runtime policy is a separate hardening task from the IAM user and CDK bootstrap work.
- A failed `cdk diff` or deployment should be diagnosed from the denied action and CloudFormation event, then the custom policy should be amended explicitly. Reattaching `AdministratorAccess` should remain a break-glass recovery step, not the normal fix.

## Related pages

- [AWS resource and permission boundaries](permissions.md)
- [Data and ingestion path](data-and-ingestion.md)
- [How to explain this repo in an interview](../answers/repo-walkthrough.md)
