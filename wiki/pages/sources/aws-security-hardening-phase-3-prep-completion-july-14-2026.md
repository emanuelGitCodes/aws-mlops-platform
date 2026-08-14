---
type: source
title: "AWS security hardening Phase 3-prep completion — July 14, 2026"
created: "2026-07-14"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3-prep-completion-july-14-2026.md", "../../../infra/policies/mlops-cloudformation-execution-policy.json"]
summary: "Execution policy v7 is live and hash-verified, the empty SecurityMonitoring shell is deployed, no Phase 3 service is enabled, and /predict is unchanged."
---
# AWS security hardening Phase 3-prep completion — July 14, 2026

## Confirmed

The immutable completion record captures the green hosted CI gate for commit
`dbe6578`, the operator-approved rotation of the CloudFormation execution
policy to `v7` (live canonical hash matches the repository; `v6` kept for
rollback; attachment scope unchanged), the `CREATE_COMPLETE` metadata-only
`Mlops-Dev-SecurityMonitoring` deployment, re-verified disabled state of all
six Phase 3 services, and an unchanged `/predict` response.

## Synthesis

Phase 3's fixed surfaces — stack wiring, tests, deployer permissions — are now
all live while every service flag stays false. From 3A onward each sub-phase
holds its minimal form: one flag flip and one service's constructs,
one named deploy, one verification. The deploy-before-rotation ordering was
acceptable only because the shell template exercises no new permission; later
sub-phases depend on `v7` already being live.

Related pages:

- [Phase 3-prep implementation](aws-security-hardening-phase-3-prep-implementation-july-14-2026.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)

## Post-completion observation

Two `unauthorized-api-calls` alarm emails arrived during and after the 3-prep
deployment window, and both were attributed from the audit log group with no
unknown principal:

- 01:28 UTC, datapoint `11.0`: the scoped CloudFormation execution role was
  denied read-only describe calls during this session's change-set-based
  `cdk diff` (already recorded in the implementation record; later diffs use
  `--no-change-set`).
- 01:54 UTC, datapoint `3.0`: exactly two `ce:GetCostAndUsage` and one
  `ce:GetCostForecast` denials for the known `${AWS_ADMIN_USER_NAME}` user at
  01:51:56 UTC, repeating the 00:45/00:53/00:59 UTC trio pattern — consistent
  with an AWS Console cost widget or Cost Explorer page auto-refresh in an
  operator browser session.

The alarm returned to `OK` at 01:59 UTC once the denied datapoints aged out.

## Tensions or open questions

- Sub-phase 3A awaits an explicit go decision.
- The `${AWS_ADMIN_USER_NAME}` console session is repeatedly denied Cost Explorer reads;
  each trio that lands in a fresh five-minute window re-fires the exact CIS
  alarm. Either grant `${AWS_ADMIN_USER_NAME}` the `ce:Get*` read actions or accept the
  recurring noise — deliberately left undecided and unchanged.
