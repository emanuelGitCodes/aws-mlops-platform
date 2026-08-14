---
type: architecture
title: Complete teardown and rebuild
created: "2026-08-14"
updated: "2026-08-14"
sources: ["../../../Makefile", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/registry_stack.py", "../../../infra/stacks/serving_stack.py", "../../../src/serving/deploy_handler.py", "../../../scripts/setup_account.sh", "cdk-deployment-iam.md"]
summary: "make destroy removes the nine stacks but leaves retained buckets, the audit key and log group, and every SDK-created SageMaker resource; two fixed names then block a naive redeploy."
---
# Complete teardown and rebuild

## Confirmed

`make destroy ENV=dev` runs `cdk destroy --all`. It deletes the nine
CloudFormation stacks. It does not return the account to a clean state,
because three classes of resource survive it.

### Retained by CloudFormation

These resources carry `RemovalPolicy.RETAIN`, so stack deletion skips them:

| Resource | Stack | Note |
|---|---|---|
| `${RAW_BUCKET}`, `${CURATED_BUCKET}`, `${ARTIFACTS_BUCKET}` | Data | Versioned. They hold the uploaded CSV, curated rows, model artifacts, evaluation bundles, the drift baseline, and the capture prefix. |
| `${ACCESS_LOG_BUCKET}`, `${AUDIT_BUCKET}` | Security | Versioned. The audit bucket holds CloudTrail and Config history. |
| Audit KMS key, `alias/mlops-<env>-audit` | Security | The alias stays bound to the retained key. |
| Log group `/aws/cloudtrail/mlops-<env>-audit` | Security | Fixed name. |

### Never in CloudFormation

The SDK creates these resources, so no stack delete can touch them:

- The SageMaker endpoint (`ENDPOINT_NAME`), plus every endpoint config and
  model that `src/serving/deploy_handler.py` created. Each deploy adds a new
  config and model, so several accumulate.
- The SageMaker pipeline (`PIPELINE_NAME`).
- Every model package inside the model package group. The group itself is a
  CloudFormation resource, and **its deletion fails while it holds a model
  package**, which fails the whole Registry stack delete.
- Auto-created `/aws/lambda/*` log groups for the CDK helper functions, such
  as the bucket-notifications handler and the custom-resource handlers.

### Outside the application stacks

- The `CDKToolkit` bootstrap stack and its versioned staging bucket. The
  bucket delete fails until every object version is removed.
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
so destroying SecurityMonitoring **removes the account-level block**.

### The two redeploy collisions

A redeploy after a plain `make destroy` fails on two fixed names:

1. **The KMS alias.** The retained key keeps `alias/mlops-<env>-audit`. The
   new Security stack creates a new key with the same alias and fails with
   `AlreadyExistsException`.
2. **The audit log group.** The retained `/aws/cloudtrail/mlops-<env>-audit`
   group blocks the new stack's create of the same name.

The buckets do not collide, because CDK generates their physical names.

## Synthesis

### Teardown order

1. **Empty the SageMaker registry and serving plane first.** Delete every
   model package in the group, the endpoint, the endpoint configs, the
   models, and the pipeline. Skipping the packages fails the Registry stack
   delete later.
2. Run `make destroy ENV=dev`.
3. **Remove the retained security names.** Delete the alias
   `alias/mlops-<env>-audit`, schedule the key deletion
   (`schedule-key-deletion`; the minimum window is 7 days), and delete the
   log group `/aws/cloudtrail/mlops-<env>-audit`. Without this step the next
   deploy fails.
4. **Empty and delete the five retained buckets.** Each is versioned, so
   remove every object version and delete marker before the bucket delete.
   `s3api list-object-versions` proves a bucket empty; the
   [CDK deployment page](cdk-deployment-iam.md) records this exact
   procedure from the first-deploy cleanups.
5. Delete the leftover `/aws/lambda/*` helper log groups.
6. For a full account reset, also delete the `CDKToolkit` stack (empty its
   staging bucket first) and the `setup_account.sh` IAM objects. Keep them
   when the goal is a rebuild in the same account.

### What a rebuild does not share with a fresh account

- The cost-allocation tag stays activated, so the budget filter works on
  the first deploy instead of after the manual Billing step.
- The IAM identities and policies already exist; `setup_account.sh` leaves
  them unchanged.
- A scheduled-for-deletion KMS key still appears in listings for the length
  of its deletion window. It does not conflict once its alias is gone.

The new SNS topic sends a fresh confirmation email. Confirm it again; the
old confirmation died with the old topic.

## Tensions or open questions

- **This procedure has never run.** Every step above comes from reading the
  stack code and the retention policies, not from an executed teardown. The
  same unproven status covers the setup scripts, per the
  [CDK deployment page](cdk-deployment-iam.md). A rebuild test MUST execute
  this page start to finish before anyone treats it as verified, and the
  run SHOULD correct this page where reality disagrees.
- `make destroy` prompts per stack and deletes in dependency order, but a
  mid-sequence failure (for example the Registry stack with packages still
  in the group) leaves a partial state. Re-run after fixing the cause;
  `cdk destroy` is safe to repeat.
- Whether Config and Access Analyzer leave service-linked roles behind is
  harmless either way: AWS manages those roles and they hold no standing
  resources.

## Related pages

- [CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md)
- [Dataset provenance and the untracked CSV](../decisions/dataset-provenance.md)
- [Phased AWS security hardening roadmap](phased-security-hardening.md)
