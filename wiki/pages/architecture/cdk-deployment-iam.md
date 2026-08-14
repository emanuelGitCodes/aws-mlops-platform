---
type: architecture
title: CDK deployment identity and bootstrap boundary
created: "2026-07-10"
updated: "2026-08-14"
sources: ["../../../infra/app.py", "../../../infra/cdk.json", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/policies/mlops-cloudformation-execution-policy-extension.json", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/ingestion_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../raw/mlops-deployment-and-pipeline-troubleshooting-summary-july-10-2026.md", "../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/mlops-cloudformation-execution-policy-v1-2026-07-10.json", "https://docs.aws.amazon.com/cdk/v2/guide/deploy.html", "https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-bootstrap.html", "../../../scripts/setup_account.sh", "../../../scripts/setup_github_deploy.sh", "../../../Makefile", "../../../README.md", "../../../infra/stacks/security_stack.py"]
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

Keep the `${AWS_ADMIN_USER_NAME}` profile open in a separate terminal. The
removal of temporary administrator access from `${MLOPS_DEPLOYER_USER_NAME}`
then cannot lock the account out.

### What CDK bootstrap created

The command below bootstrapped the `us-east-1` environment:

```bash
cdk bootstrap aws://${AWS_ACCOUNT_ID}/us-east-1 \
  --profile ${MLOPS_DEPLOYER_USER_NAME} \
  --cloudformation-execution-policies \
  arn:aws:iam::${AWS_ACCOUNT_ID}:policy/MLOpsCloudFormationExecutionPolicy
```

The command returned `CDKToolkit: CREATE_COMPLETE`. The bootstrap stack holds
the CDK asset storage and the roles that CDK uses during a deployment. It
created five roles:

- `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`: CloudFormation assumes this role to create or update an application resource.
- `cdk-hnb659fds-deploy-role-${AWS_ACCOUNT_ID}-us-east-1`: the CDK CLI assumes this role for a CloudFormation deployment operation.
- `cdk-hnb659fds-file-publishing-role-${AWS_ACCOUNT_ID}-us-east-1`: the CDK CLI assumes this role to upload a synthesized asset to the bootstrap S3 bucket.
- `cdk-hnb659fds-lookup-role-${AWS_ACCOUNT_ID}-us-east-1`: the CDK CLI assumes this role for an environment lookup.
- `cdk-hnb659fds-image-publishing-role-${AWS_ACCOUNT_ID}-us-east-1`: CDK uses this role for a container asset. This repository ships zip-based Lambda assets, so the role stays unused.

`cdk bootstrap` deploys no application stack. It prepares the environment that a
later `cdk deploy --all` uses.

### Two policy layers

The deployment uses two different policy layers:

| Policy or role | Attached to | What it allows | Why it exists |
|---|---|---|---|
| `MLOpsCdkDeploymentPolicy` | Group `MLOps-Deployers` | `sts:GetCallerIdentity`, `sts:AssumeRole`, `sts:TagSession`, and SSM reads for the CDK bootstrap version. The policy permits assumption of the lookup, deploy, and file-publishing roles only. | The human identity or the CI identity can use CDK. It holds no direct S3, Lambda, SageMaker, or CloudFormation permission. |
| `MLOpsCloudFormationExecutionPolicy` | CDK CloudFormation execution role | The S3, IAM, Lambda, Logs, SQS, EventBridge, API Gateway, CloudWatch, Budgets, SageMaker registry, SSM, and KMS actions that the synthesized templates need. The policy limits `iam:PassRole` to the application roles and service principals. | CloudFormation needs these permissions to create the application resources. |
| Runtime policies | Application Lambda and SageMaker roles | Only the storage, invocation, pipeline, or deployment actions that each runtime component needs. | The platform separates deployment authority from runtime authority. |

One distinction matters most: `${MLOPS_DEPLOYER_USER_NAME}` creates no
application resource directly. It assumes the CDK bootstrap roles. CDK then uses
the deploy role and the file-publishing role. CloudFormation then assumes the
CloudFormation execution role and applies the synthesized templates.

### The command-line lifecycle

1. `cdk synth` runs locally and produces CloudFormation templates in `cdk.out`. It does not change AWS resources.
2. `cdk diff` compares the synthesized templates with the deployed stack state. For an accurate comparison it MAY publish a synthesized template to the CDK bootstrap S3 bucket and create a read-only CloudFormation change set. It creates and updates no application resource.
3. `cdk deploy --all` publishes the assets, submits the CloudFormation change sets, and asks for approval when the configuration requires it. CloudFormation then creates or updates the application stacks.
4. `infra/app.py` defines nine stacks per environment: Data, Ingestion, Registry, Training, Serving, Monitoring, Security, SecurityMonitoring, and Cicd. The pipeline document stays an SDK-driven operation. See the [platform design decisions](../decisions/platform-design.md).

### Verification and expected failure

The checkpoints below completed:

- `CDKToolkit` returned `CREATE_COMPLETE`.
- The CloudFormation execution role carried `MLOpsCloudFormationExecutionPolicy`.
- The account held all five standard bootstrap roles.
- `MLOpsCdkDeploymentPolicy` existed and attached to `MLOps-Deployers`.
- `MLOps-Deployers` no longer carried `AdministratorAccess`.
- An IAM inspection under the `${AWS_ADMIN_USER_NAME}` profile showed one policy on `MLOps-Deployers`: `MLOpsCdkDeploymentPolicy`.

After that detachment, this command failed under the
`${MLOPS_DEPLOYER_USER_NAME}` profile:

```text
iam:ListAttachedGroupPolicies on resource: group MLOps-Deployers
```

That failure is correct behavior. IAM inspection belongs to
`${AWS_ADMIN_USER_NAME}`. The deployment identity MUST NOT enumerate or change a
group policy. It can still authenticate and assume its three CDK roles.

The administrator verification confirmed the intended final group state. The
next verification authenticates as `${MLOPS_DEPLOYER_USER_NAME}` and runs
`cdk diff`. That test measures the deployment path, not the IAM inspection
authority.

The restricted `cdk diff` then reported `Number of stacks with differences: 6`.
It published all six synthesized templates. It showed the six application stacks
as new, because no deployment had created them. No role-assumption error and no
`AccessDenied` error appeared.

The first deployment then showed a missing execution-policy action.
CloudFormation assumed `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`
successfully. All three Data stack buckets then failed on the
`s3:PutEncryptionConfiguration` call. `RawBucket`, `CuratedBucket`, and
`ArtifactsBucket` each failed the same way, and `Mlops-Dev-Data` rolled back to
`ROLLBACK_COMPLETE`.

The failure separates two layers. The `${MLOPS_DEPLOYER_USER_NAME}` policy and
the CDK bootstrap-role path worked. The CloudFormation execution policy was
incomplete. `infra/stacks/data_stack.py` requests KMS-managed default encryption
for each bucket, so the execution policy MUST carry that S3 action.

Version `v2` of the execution policy added the missing S3 action. The delete of
the failed `Mlops-Dev-Data` stack succeeded, which released the stack name for a
clean retry.

On the retry, the three encrypted buckets and their bucket policies reached
`CREATE_COMPLETE`, so version `v2` fixed the S3 failure. The next failure came
from the CDK-generated `BucketNotificationsHandler` inline policy: the execution
role held no `iam:GetRolePolicy` on the handler role. The stack rolled back
again. The data buckets use `RemovalPolicy.RETAIN`, so read their
`DELETE_SKIPPED` events and find the retained empty buckets before you delete
the failed stack again.

On the next retry, version `v3` let the generated inline policy and the handler
Lambda complete. The custom resource `RawBucket/Notifications` then failed,
because the CloudFormation execution role held no `lambda:InvokeFunction` on the
generated `BucketNotificationsHandler` Lambda. CloudFormation needs that
permission to invoke the helper that configures the S3 notification. The stack
rolled back again.

That third attempt retained three buckets. A check proved each one empty, and
the delete succeeded after version `v4` of the policy. One bucket-prefix check
remained before the next retry.

The account then showed six `mlops-dev-data-` buckets: two Raw, two Curated, and
two Artifacts. The two sets came from the first and the second deployment
attempt. They are retained cleanup candidates. They do not prove that two Data
stacks are active.

An `s3api list-object-versions` call inspected all six retained buckets. Each
one returned zero object versions and zero delete markers. All six are empty
cleanup candidates from the failed deployments.

The cleanup then removed the six buckets. One Raw bucket and one Curated bucket
were already absent, and the delete of the remaining four succeeded. A final
prefix query returned no `mlops-dev-data-` bucket.

The final deployment completed all six application stacks of that time. The
later pipeline and API checks confirmed the CDK resource boundary: the API
reached the proxy Lambda, and the pipeline accepted an upsert and a start. The
remaining failure was inside SageMaker Processing, not in the CDK deployment
path. See the
[deployment and pipeline troubleshooting checkpoint](deployment-and-pipeline-troubleshooting.md)
for the end-to-end evidence.

Phase 2A added a repository-owned copy of the execution policy. It rotated the
live managed policy from the archived non-default `v1` to the default `v6`. A
fingerprint of the exact live `v1` document exists, and `v5` stays available for
a rollback. The Phase 2 additions cover only the KMS, CloudTrail, SNS, encrypted
Logs, metric-filter, and alarm lifecycle that the audit plan needs. Phase 2A
also added `cloudtrail.amazonaws.com` to the existing `iam:PassRole` service
condition, and it kept the `Mlops-Dev-*` role-resource boundary. The managed
policy attaches to the CDK CloudFormation execution role only. See the
[Phase 2A completion record](../sources/aws-security-hardening-phase-2a-completion-july-12-2026.md).

## Synthesis

This setup separates three trust boundaries. A reader confuses them easily:

1. **Who starts CDK:** `${MLOPS_DEPLOYER_USER_NAME}` authenticates with an access key. Its policy permits assumption of specific bootstrap roles.
2. **Who applies infrastructure:** CloudFormation assumes the CDK CloudFormation execution role and uses the customer-managed execution policy.
3. **Who runs the application:** each Lambda role and SageMaker service role holds only the runtime permissions it needs. Examples are S3 access, endpoint invocation, and pipeline execution.

The deployment identity is therefore a control-plane identity, not an
application runtime identity. An explanation of this boundary names the
permission granted and the permission deliberately absent: the user can assume
the deploy path, and it can neither call the application services directly nor
inspect an IAM group.

The ingestion path isolates a failure the same way. S3 sends an event to
EventBridge. EventBridge puts the event on SQS. The validation Lambda then reads
one message at a time. SQS gives the buffer and the retry behavior. After the
configured receive limit, the message moves to the DLQ for inspection, and it
does not block the rest of the queue.

## Reproducing this boundary on a new account

Everything above describes the reference account. That account holds state a
new account does not, and the state hid two defects until 2026-08-14.

### The two defects

- **`make deploy` could never succeed on a new account.**
  `infra/stacks/security_stack.py` declares `SecurityAlertEmail` as a
  `CfnParameter` with no default, and no target supplied a value.
  **CloudFormation reuses a stored parameter value on an update.** The
  reference account received the value at its first hand-run deploy and has
  reused it since, so no later deploy asked for it. A first deploy on a new
  account fails. `deploy.yml` calls the same target, so the workflow carried
  the same defect.
- **`make bootstrap` granted `AdministratorAccess`.** That is the CDK default
  for the CloudFormation execution role. The reference account runs on the two
  repository-owned execution policies instead. A reader who followed the README
  therefore built a weaker boundary than the one this repository presents as
  its own.

### The scripted path

`scripts/setup_account.sh` runs once per account, under an admin-capable
identity, before `make bootstrap`. It is idempotent and leaves an existing IAM
object as it is. It creates:

- both execution policies, from the repository JSON through `envsubst`;
- the `MLOps-Deployers` group and `MLOpsCdkDeploymentPolicy`;
- the deploy user, and one access key that the script prints once.

`make bootstrap` now names both execution policies, so the CDK execution role
never holds `AdministratorAccess`. `make deploy` and `make deploy-stack` pass
`SecurityAlertEmail` from `SECURITY_ALERT_EMAIL`, and the `check-alert-email`
guard stops early with a usable message when the value is absent. The stack
name for the parameter comes from `stack_prefix()`, so the formula stays in one
place.

`scripts/setup_github_deploy.sh` is optional and runs after the `Cicd` stack
deploys. It reads `GitHubDeployRoleArn` from the stack output, creates the
GitHub environment, and sets the deploy-role secret that `deploy.yml` expects.

**The `MLOpsCdkDeploymentPolicy` document lives in the script, and it MUST
match the live policy.** Its SSM grant names the single CDK bootstrap version
parameter. A wildcard resource there would widen the control-plane identity
beyond the access it needs.

### What no script can do

Three steps stay manual, and the README lists them:

- **Confirm the security-alert SNS subscription.** Without the click, the CIS
  and detection alarms deliver nowhere.
- **Activate the budget cost-allocation tag.** Before activation the budget
  filter matches nothing, and the budget never alarms.
- **Decide on GuardDuty and Security Hub.** Both wait behind the paid-plan
  upgrade.

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
free and cannot take one. The extension holds the OIDC provider lifecycle, the
exact Access Analyzer archive-rule lifecycle, and the website grants. It does
not grant `ApplyArchiveRule`; that action changes finding status and remains an
operator step. A test measures both documents against the quota, so the next
size failure arrives in CI rather than at the AWS API.

The extension is live at `v3`, created 2026-08-14 for the website stack. It
holds ten statements and 3664 of its 6144 bytes. Versions `v1` and `v2` remain
as rollback documents, so three of the five policy-version slots are used. The
next rotation still needs no cleanup delete; the one after it does.

Version `v3` adds seven statements: `WebsiteEc2Network` and
`WebsiteEc2Instances` (both `Resource: "*"`, because EC2 network actions take
no resource scope), `WebsiteCloudFront`, `WebsiteDynamoDb`,
`WebsiteInstanceProfileLifecycle`, `PassWebsiteInstanceRole`, and
`WebsiteAmiParameterRead`. `PassWebsiteInstanceRole` is a separate statement
rather than a change to `PassOnlyApplicationRoles`, because the main document
has no room. It passes only to `ec2.amazonaws.com` and
`vpc-flow-logs.amazonaws.com`.

**Read the live version before a rotation.** This page has misreported the slot
count before. `aws iam list-policy-versions` is the source.

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

- `MLOpsCloudFormationExecutionPolicy` limits each grant by service and action.
  It still uses `Resource: "*"` for many management actions, because CDK
  generates some CloudFormation names only at deployment time. The policy is
  narrower than `AdministratorAccess`. It is not complete resource-level least
  privilege.
- Phase 5 took the model, proxy, deploy, and pipeline roles off their broad
  managed policies. Those runtime policies are a separate task from the IAM user
  work and the CDK bootstrap work on this page.
- **Neither setup script has run against a live account.** Read-only IAM calls
  checked their policy assumptions. Their runtime behavior is unproven. A run
  against a scratch account is the only real test, and it MUST happen before
  anyone treats the README path as verified.
- **An existing `.env` needs `SECURITY_ALERT_EMAIL`.** Without it the
  `check-alert-email` guard stops `make deploy` and `make deploy-stack`. This is
  the deliberate trade: the guard is what protects a first deploy on a new
  account.
- Diagnose a failed `cdk diff` or a failed deployment from the denied action and
  the CloudFormation event. Then amend the custom policy explicitly.
  Reattachment of `AdministratorAccess` MUST stay a break-glass recovery step.
  It MUST NOT become the normal fix.

## Related pages

- [AWS resource and permission boundaries](permissions.md)
- [Data and ingestion path](data-and-ingestion.md)
- [How to explain this repo in an interview](../answers/repo-walkthrough.md)
