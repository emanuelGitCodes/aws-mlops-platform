# AWS security hardening Phase 3-prep completion — July 14, 2026

## Hosted gate

GitHub Actions run 29381999521 for commit `dbe6578` passed `validate` and
`secret-scan` with no leaks.

## Execution-policy rotation

With explicit operator approval, the oldest non-default version `v2`
(canonical SHA-256 `<redacted>`, recorded pre-deletion) was deleted to free the
IAM version slot, and the repository document was created as `v7` and made
default. Live `v7` canonical JSON SHA-256
`<redacted>` matches the
repository document exactly. `v6` remains non-default for rollback. The policy
remains attached only to
`cdk-hnb659fds-cfn-exec-role-${AWS_ACCOUNT_ID}-us-east-1`; no user or group
attachment was added.

## Deployment result

Only `Mlops-Dev-SecurityMonitoring` was deployed through `${MLOPS_DEPLOYER_USER_NAME}`.
The stack reached `CREATE_COMPLETE` in 6.6 seconds and contains exactly one
resource, `AWS::CDK::Metadata`. The deploy preceded the `v7` rotation, which
is safe because a metadata-only template exercises no new service permission;
`v7` was live before this record.

## Live verification

- `Mlops-Dev-SecurityMonitoring`: `CREATE_COMPLETE`, resources =
  `CDKMetadata` only.
- Phase 3 services remain disabled after the deploy: zero Access Analyzer
  analyzers, zero Config recorders, `SubscriptionRequiredException` for
  GuardDuty and Security Hub, `NoSuchPublicAccessBlockConfiguration` for the
  account-level S3 Block Public Access.
- No new cross-stack export was created; `Mlops-Dev-Security` was not
  deployed and shows no template difference.
- `/predict` returned HTTP 200 with `churn_probability` 0.3656342029571533
  and `churn` false — identical to the Phase 2D record; the schema and
  `score >= 0.50` rule are intact.

## Rollback points

- Policy: make `v6` default and delete `v7`.
- Stack: deleting `Mlops-Dev-SecurityMonitoring` removes only `CDKMetadata`;
  no retained resource exists yet.

## Phase boundary

Phase 3-prep is complete. Sub-phase 3A (IAM Access Analyzer: flip
`access_analyzer: true`, add the free account external-access analyzer,
tests, diff with `--no-change-set`, named deploy, and live verification)
requires a separate go decision.
