# AWS security hardening Phase 2A completion — July 12, 2026

## Objective

Reconcile the pre-existing Data-stack export drift and prepare the CDK
CloudFormation execution role for the Phase 2 audit resources without changing
application data, the monthly budget, or any runtime stack.

## Data-stack reconciliation

- Account: `${AWS_ACCOUNT_ID}`; Region: `us-east-1`; environment: dev.
- The obsolete artifacts-bucket export reported no importing stacks.
- A scoped `cdk diff Mlops-Dev-Data -c env=dev --no-change-set` showed only
  removal of that output.
- Only `Mlops-Dev-Data` was deployed. The stack reached `UPDATE_COMPLETE`.
- Raw, curated, and artifacts bucket physical names remained unchanged.
- Object-version counts remained 1, 1, and 156 respectively, with zero delete
  markers before and after deployment.
- The existing monthly budget remained a single `$20` budget with no Phase 2
  notifications yet.
- The obsolete export is no longer present.

No all-stack deployment or SageMaker pipeline execution occurred.

## Execution-policy version rotation

The exact live `v1` document was archived as
`mlops-cloudformation-execution-policy-v1-2026-07-10.json`. Its file SHA-256 is
`<redacted>`.
After canonical JSON normalization, the archived and live documents both had
SHA-256 `<redacted>`.

Only non-default `v1` was deleted to free the IAM policy-version slot. The
repository-owned Phase 2 document was then created as `v6` and made default.
Its canonical JSON SHA-256 is
`<redacted>`,
matching the live `v6` document.

`v5` remains non-default for rollback. The managed policy remains attached only
to `cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`; it is attached to no
users or groups. The `iam:PassRole` resource remains
`arn:aws:iam::${AWS_ACCOUNT_ID}:role/Mlops-Dev-*`, with only
`cloudtrail.amazonaws.com` added to the prior service allowlist.

## Rollback

If the new permissions cause a deployment-path problem, make `v5` default and
delete `v6`. Do not broaden `${MLOPS_DEPLOYER_USER_NAME}` or attach this policy to another
principal.

## Decision and next checkpoint

Phase 2A is complete and is a go for repository commit and CI. Phase 2B may add
and deploy only `Mlops-Dev-Security` after this checkpoint passes. The security
alert email remains a deployment parameter and is not recorded in Git.
