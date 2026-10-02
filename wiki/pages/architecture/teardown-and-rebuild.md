---
type: architecture
title: Complete teardown and rebuild
created: "2026-08-14"
updated: "2026-10-02"
sources: ["../../../Makefile", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/registry_stack.py", "../../../infra/stacks/serving_stack.py", "../../../src/serving/deploy_handler.py", "../../../scripts/setup_account.sh", "cdk-deployment-iam.md"]
summary: "make destroy removes the nine stacks but leaves retained buckets, the audit key and log group, the model package group, and every SDK-created SageMaker resource; the dev teardown of 2026-10-02 executed this page."
---
# Complete teardown and rebuild

## Confirmed

`make destroy ENV=dev` runs `cdk destroy --all`. It deletes the nine
CloudFormation stacks. It does not return the account to a clean state,
because three classes of resource survive it.

`make destroy` needs an interactive terminal. Without one, the CDK CLI stops
before it deletes anything:

```text
Destroying stacks is an irreversible action, but terminal (TTY) is not attached so we are unable to get a confirmation from the user
```

An agent shell has no terminal. Run the Makefile command with `--force`
from `infra/`:
`uv run --locked npx aws-cdk@<pinned> destroy --all --force -c env=dev`.
Take `<pinned>` from `CDK_CLI` in the `Makefile`.

### Retained by CloudFormation

These resources carry `RemovalPolicy.RETAIN`, so stack deletion skips them:

| Resource | Stack | Note |
|---|---|---|
| `${RAW_BUCKET}`, `${CURATED_BUCKET}`, `${ARTIFACTS_BUCKET}` | Data | Versioned, with the AWS-managed S3 KMS key. They hold the uploaded CSV, curated rows, model artifacts, evaluation bundles, the drift baseline, and the capture prefix. |
| `${ACCESS_LOG_BUCKET}`, `${AUDIT_BUCKET}` | Security | Versioned. The audit bucket holds CloudTrail and Config history, encrypted with the audit KMS key. |
| Audit KMS key | Security | The key stays. Its alias does not: `alias/mlops-<env>-audit` is a separate `AWS::KMS::Alias` resource without a retain policy, and CloudFormation deletes it. |
| Log group `/aws/cloudtrail/mlops-<env>-audit` | Security | Fixed name. |
| Model package group (`model_package_group` in the config) | Registry | Fixed name. `RemovalPolicy.RETAIN` keeps the model lineage. |

### Never in CloudFormation

The SDK creates these resources, so no stack delete can touch them:

- The SageMaker endpoint (`ENDPOINT_NAME`), plus every endpoint config and
  model that `src/serving/deploy_handler.py` created. Each deploy adds a new
  config and model, so several accumulate.
- The endpoint log group `/aws/sagemaker/Endpoints/<endpoint name>`.
- The SageMaker pipeline (`PIPELINE_NAME`).
- Every model package inside the model package group.
- Auto-created `/aws/lambda/*` log groups for every stack function. This
  covers the CDK helper functions, such as the bucket-notifications handler
  and the custom-resource handlers, and the application functions.

### Outside the application stacks

- The `CDKToolkit` bootstrap stack and its versioned staging bucket. The
  bucket delete fails until every object version is removed. Another project
  MAY share the bootstrap stack in the same account. Check the other stacks
  before you delete it.
- The IAM objects from `scripts/setup_account.sh`: both execution policies,
  `MLOpsCdkDeploymentPolicy`, the `MLOps-Deployers` group, and the
  `${MLOPS_DEPLOYER_USER_NAME}` user with its access key. The script is
  idempotent, so a rebuild reuses them as they are.
- The activated cost-allocation tag in Billing. Activation is account-level
  and survives everything.
- The GitHub environments and secrets from `scripts/setup_github_deploy.sh`,
  when that script ran.

One resource reverts rather than survives: the account-level S3 Block Public
Access custom resource calls `DeletePublicAccessBlock` in its `on_delete`,
so destroying SecurityMonitoring **removes the account-level block**. The
2026-10-02 teardown confirmed this: `GetPublicAccessBlock` then returned
`NoSuchPublicAccessBlockConfiguration`.

### The redeploy collisions

A redeploy fails on each fixed name that a retained resource still holds:

1. **The audit log group.** The retained `/aws/cloudtrail/mlops-<env>-audit`
   group blocks the new stack's create of the same name.
2. **The model package group.** The retained group blocks the new Registry
   stack's create of the same name.

The KMS alias does not collide, because CloudFormation deletes it. The
buckets do not collide, because CDK generates their physical names.

## Synthesis

### Teardown order

1. **Empty the SageMaker serving plane and the registry first.** Delete the
   endpoint, the endpoint configs, the models, the pipeline, and every model
   package in the group.
2. Run the destroy. Use `--force` when no terminal is attached.
3. **Remove the retained fixed names.** Delete the model package group and
   the log group `/aws/cloudtrail/mlops-<env>-audit`. Without this step the
   next deploy fails.
4. **Decide on the audit key.** The audit bucket stays readable only while
   the key exists. Keep the key while you keep that bucket. To remove it,
   schedule the key deletion (`schedule-key-deletion`; the minimum window
   is 7 days).
5. **Empty and delete the five retained buckets**, when the data is not
   needed. Each is versioned, so remove every object version and delete
   marker before the bucket delete. `s3api list-object-versions` proves a
   bucket empty; the [CDK deployment page](cdk-deployment-iam.md) records
   this exact procedure from the first-deploy cleanups.
6. Delete the leftover `/aws/lambda/Mlops-<Env>-*` log groups and the
   endpoint log group.
7. Restore the account-level S3 Block Public Access setting, unless the next
   deploy follows at once.
8. For a full account reset, also delete the `CDKToolkit` stack (empty its
   staging bucket first) and the `setup_account.sh` IAM objects. Keep them
   when the goal is a rebuild in the same account.

### Cost after a teardown

With the buckets and the audit key kept, the standing cost is the KMS key
(about USD 1 a month) plus S3 storage for the five buckets. A key scheduled
for deletion costs nothing during its window.

### What a rebuild does not share with a fresh account

- The cost-allocation tag stays activated, so the budget filter works on
  the first deploy instead of after the manual Billing step.
- The IAM identities and policies already exist; `setup_account.sh` leaves
  them unchanged.
- The new Security stack creates a new audit key. The old key stays, and
  the old audit history in the retained bucket stays encrypted with it.

The new SNS topic sends a fresh confirmation email. Confirm it again; the
old confirmation died with the old topic.

## Tensions or open questions

- **The teardown half ran once; the rebuild half has never run.** The dev
  teardown of 2026-10-02 executed steps 1, 2, 3, and 6, and kept the buckets
  and the audit key. It corrected two claims on this page: the alias does
  not survive, and the model package group does. A rebuild test MUST
  still execute a deploy from the torn-down state before anyone treats the
  rebuild half as verified.
- `cdk destroy` deletes in dependency order, but a mid-sequence failure
  leaves a partial state. Re-run after fixing the cause; `cdk destroy` is
  safe to repeat.
- Whether Config and Access Analyzer leave service-linked roles behind is
  harmless either way: AWS manages those roles and they hold no standing
  resources.

## Related pages

- [CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md)
- [Dataset provenance and the untracked CSV](../decisions/dataset-provenance.md)
- [Phased AWS security hardening roadmap](phased-security-hardening.md)
