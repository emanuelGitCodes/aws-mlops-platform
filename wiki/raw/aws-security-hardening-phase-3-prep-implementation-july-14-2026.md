# AWS security hardening Phase 3-prep implementation — July 14, 2026

## Gate from Phase 2D

The Phase 2D completion record (commit `b7d1294`) required at least 24 hours of
observation before Phase 3. Phase 2D deployment finished 2026-07-13 02:11 UTC;
the window has elapsed. Phase 3 sub-phases are executed strictly one at a time:
3-prep authorizes only the scaffold and deployer-policy preparation, with no
security service enabled.

## Phase 2 observation closure

- The first `artifacts/` server-access-log object was delivered
  2026-07-13 02:21 UTC, completing the delivery confirmation left open by the
  Phase 2D record (`raw/` 02:13, `curated/` 02:13, `cloudtrail/` 2026-07-12
  23:14 UTC).
- Daily unblended cost for 2026-07-11 through 2026-07-13 rounds to `$0.00`,
  well inside the `$20` budget.
- Five of six security alarms are `OK`. `unauthorized-api-calls` entered
  `ALARM` 2026-07-15 01:28 UTC from two attributed read-only sources: repeated
  `ce:GetCostAndUsage`/`GetCostForecast` denials for the known `${AWS_ADMIN_USER_NAME}`
  user (00:45–00:59 UTC, Cost Explorer console pattern), and
  `events:ListTagsForResource`/`s3:GetBucket*` describe denials for the scoped
  CloudFormation execution role during this session's read-only
  change-set-based `cdk diff` (01:26–01:27 UTC). No unknown principal
  appeared. Later diffs use `--no-change-set`, matching the Phase 2A
  convention, to avoid this noise class. The exact CIS filter is retained
  unchanged.

The Phase 2D observation window is closed and Phase 3 is a documented go.

## Recorded pre-state

- `Mlops-Dev-SecurityMonitoring` does not exist
  (`DescribeStacks` → `ValidationError`).
- IAM Access Analyzer: `list-analyzers` returns zero analyzers.
- GuardDuty and Security Hub: `SubscriptionRequiredException` (never enabled).
- AWS Config: zero configuration recorders.
- Account-level S3 Block Public Access:
  `NoSuchPublicAccessBlockConfiguration`.
- `MLOpsCloudFormationExecutionPolicy` holds versions `v2`–`v6` (five, the IAM
  maximum); `v6` is default. Live `v6` canonical JSON SHA-256
  `<redacted>` matches
  the pre-change repository document and the Phase 2A record. The oldest
  non-default version `v2` (2026-07-10, canonical SHA-256
  `<redacted>`) is the
  slot-freeing deletion candidate, mirroring the Phase 2A `v1` deletion.

## Implemented scope

1. `infra/config/dev.yaml` and `prod.yaml` gain
   `security.services` with exactly six boolean flags — `access_analyzer`,
   `guardduty`, `config_recorder`, `security_hub`, `account_bpa`,
   `eventbridge_alerts` — all `false`. One flag flips per sub-phase commit, so
   each sub-phase remains a single revertable unit.
2. New `infra/stacks/security_monitoring_stack.py` defines
   `SecurityMonitoringStack` (`Mlops-Dev-SecurityMonitoring`). It validates the
   flag set (exact keys, boolean values) and deploys **no resources** while all
   flags are false. It receives the Security stack's alert topic, access-log
   bucket, and audit key by construct reference for later sub-phases; no
   cross-stack export is created while they remain unused.
3. `infra/app.py` instantiates the stack after `Mlops-Dev-Security` and
   registers it with `apply_security_checks`. No cdk-nag acknowledgement was
   needed.
4. `infra/policies/mlops-cloudformation-execution-policy.json` extends
   `ApplicationServices` with the Phase 3 lifecycle actions
   (`access-analyzer:*Analyzer*`, `guardduty:*Detector*` + tags,
   `config:*ConfigurationRecorder*`/`*DeliveryChannel*`,
   `securityhub:*` enable/standards/tags, and `s3:PutLifecycleConfiguration`),
   and adds two scoped statements: `ConfigServiceLinkedRole`
   (`iam:CreateServiceLinkedRole` limited to the
   `config.amazonaws.com` service-linked-role path with an
   `iam:AWSServiceName` condition) and `ConfigServiceLinkedRoleCleanup`
   (delete/status on the same path). `PassOnlyApplicationRoles` is unchanged.
   New-document canonical JSON SHA-256:
   `<redacted>`.
5. Tests: `test_deployment_policy.py` gains Phase 3 required-action and
   service-linked-role scoping assertions; `test_stacks.py` builds the new
   stack in the shared fixture, asserts it stays a disabled shell, and records
   its empty IAM fingerprint.

## Validation

- Lock check: passed with 108 packages.
- Dependency audit: no known vulnerabilities.
- Ruff check and format check: passed across 45 files.
- Unit suite: 51 passed.
- Full CDK synthesis with cdk-nag: passed; the new template contains only
  `CDKMetadata`.
- `cdk diff` against the live account: `Mlops-Dev-Security`, `Mlops-Dev-Data`,
  `Mlops-Dev-Registry`, `Mlops-Dev-Training`, and `Mlops-Dev-Monitoring` show
  no differences; `Mlops-Dev-Ingestion` and `Mlops-Dev-Serving` retain only the
  previously recorded Lambda bundle-hash drift; `Mlops-Dev-SecurityMonitoring`
  is a new metadata-only stack.

## Boundary and next checkpoint

Phase 3-prep is implemented but not deployed, and no AWS state has changed.
Commit this checkpoint, require hosted CI, then: delete policy version `v2`,
create the repository document as `v7` (default, `v6` retained for rollback),
verify the live canonical hash, and deploy only
`Mlops-Dev-SecurityMonitoring`. Sub-phase 3A (IAM Access Analyzer) requires a
separate go decision after the 3-prep completion record.
