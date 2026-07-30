---
type: "source"
title: "AWS security hardening Phase 2E implementation and deployment — July 30, 2026"
created: "2026-07-30"
updated: "2026-07-30"
sources: ["../../raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md"]
summary: "Phase 2E moved unauthorized-api-calls to 3-of-3 evaluation and granted the auditor scoped read access to the audit log, both verified live."
---
# AWS security hardening Phase 2E implementation and deployment — July 30, 2026

## Key claims

- The `mlops-dev-security-unauthorized-api-calls` alarm had produced ten
  fire/auto-resolve cycles between 2026-07-28 and 2026-07-30, each a single
  five-minute datapoint resolving within 5–12 minutes — worse than the three
  07-24 fires that opened GitHub issue 10.
- A new frozen `SecurityDetection` dataclass in
  `infra/stacks/security_stack.py` gives each CIS detection its own alarm
  evaluation; only `UnauthorizedApiCalls` moved to `evaluation_periods=3`,
  `datapoints_to_alarm=3`. Thresholds, periods, filter patterns, and the
  other five detections are unchanged, and the IAM fingerprint baseline
  passed unmodified.
- The reviewed diff, the deployment by `${MLOPS_DEPLOYER_USER_NAME}`
  (`UPDATE_COMPLETE` 23:49:42 UTC), and resource-level `make verify-deploy`
  all attribute the change to exactly one resource,
  `UnauthorizedApiCallsAlarmDEEEB676`; the post-deploy diff was empty.
- The pre-flight denial artifact (23:46:17 UTC) tripped the old 1-of-1
  alarm; the new 3-of-3 evaluation resolved it 32 seconds after deployment,
  and no unauthorized-api-calls fire followed.
- An out-of-band `${AWS_ADMIN_USER_NAME}` action attached inline policy
  `mlops-dev-auditor-audit-log-read` to the hand-managed auditor user:
  `logs:FilterLogEvents` on the audit log group plus `kms:Decrypt` on
  `${AUDIT_KEY_ID}` confined by the log-group encryption context. The
  `PutUserPolicy` paged `IamPolicyChanges` exactly once (23:52:21 UTC),
  live-proving that detection.
- The auditor then read the audit log successfully, closing the
  self-diagnosis gap; `/predict`, CloudTrail delivery, the six alarms, and
  the `$20` budget with 50/80/100 alerts all verified intact.

## Entities and concepts

- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)
  — the detection contract this phase revises.
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
  — the gated operating rule Phase 2E followed.
- [AWS resource and permission boundaries](../architecture/permissions.md)
  — gains the auditor's audit-log read boundary.

## Tensions or open questions

- The Phase 2E observation window is open: closure requires demonstrated
  silence on routine auditor activity with no missed sustained-burst
  detection, plus healthy alarms, auditor read access, and budget.
- `budgets:ViewBudget` remains outside the auditor scope; budget checks
  still require `${AWS_ADMIN_USER_NAME}`.
