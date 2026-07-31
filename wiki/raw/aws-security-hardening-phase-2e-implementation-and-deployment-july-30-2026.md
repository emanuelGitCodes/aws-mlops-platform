# AWS security hardening Phase 2E implementation and deployment — July 30, 2026

Phase 2E revises the Phase 2C detection contract to stop the
`mlops-dev-security-unauthorized-api-calls` alarm paging on isolated
least-privilege denials, and closes the second-order gap that the security
auditor could not read the audit log it audits. It implements options 2 and 3
from GitHub issue 10 — the two remedies the issue's own analysis found
complementary and non-coverage-reducing. Option 1, narrowing the filter, was
rejected because genuine reconnaissance often looks exactly like denied
`List*` calls.

All work ran on 2026-07-30 against the dev account in `us-east-1`. The
pre-flight and all verification used the least-privilege
`${AWS_SECURITY_AUDITOR_USER_NAME}` profile, read-only. The two mutating
steps were `make deploy-stack` with `${MLOPS_DEPLOYER_USER_NAME}` and one
`iam put-user-policy` with `${AWS_ADMIN_USER_NAME}`. Timestamps below are
UTC.

## Pre-flight baseline (read-only, auditor profile)

1. `describe-alarms` with the `mlops-dev-security-` prefix: all six alarms
   present, `EvaluationPeriods 1`, no `DatapointsToAlarm`, `Threshold 1.0`,
   `Period 300`, `Statistic Sum`, all `OK` — matching the committed
   Phase 2C template.
2. `describe-alarm-history` for `unauthorized-api-calls`: ten
   fire/auto-resolve cycles between 2026-07-28 and 2026-07-30, five of them
   on 07-30 alone, every one resolving within 5–12 minutes. The noise had
   worsened since the three fires issue 10 documented for 07-24.
3. `get-trail-status` for `mlops-dev-audit`: `IsLogging true`, no delivery
   error, latest CloudWatch Logs delivery 23:45:25.
4. Denial baseline at 23:46:17: auditor `logs:FilterLogEvents` against
   `/aws/cloudtrail/mlops-dev-audit` returned `AccessDeniedException`, as
   first recorded on 07-24. This denial itself emitted one matching event
   and tripped the still-live 1-of-1 alarm — the accepted, timestamped
   artifact demonstrating the exact noise loop being fixed.

## Change 1 — sustained-burst evaluation for unauthorized-api-calls (CDK)

Commit `0028146` on branch `issue/10-unauthorized-api-calls-alarm-tuning`
(pull request 14) introduces a frozen `SecurityDetection` dataclass in
`infra/stacks/security_stack.py` so each of the six CIS detections carries
its own alarm evaluation. Defaults preserve the Phase 2C contract exactly;
only `UnauthorizedApiCalls` sets `evaluation_periods=3` and
`datapoints_to_alarm=3`. Threshold, period, statistic, missing-data
treatment, SNS action, alarm names, and all six filter patterns are
unchanged. An isolated denial can no longer page; a burst sustained across
three consecutive five-minute datapoints still does.

`tests/unit/test_stacks.py` now pins per-alarm evaluation settings keyed by
alarm slug and asserts the five untouched alarms render no
`DatapointsToAlarm` property at all. The IAM policy fingerprint baseline
passed unmodified — the change touches no IAM resource.

Gates before deployment: `make lint` (49 files), `make typecheck` (34
files, zero errors), `make test` (71 passed), `make security`. The
reviewed `make diff-stack STACK=Mlops-Dev-Security` showed exactly one
modified resource — `UnauthorizedApiCallsAlarm`: `EvaluationPeriods 1→3`,
`DatapointsToAlarm 3` added — and nothing else.

Deployment: `make deploy-stack STACK=Mlops-Dev-Security` with
`${MLOPS_DEPLOYER_USER_NAME}` reached `UPDATE_COMPLETE` at 23:49:42.
Resource-level `make verify-deploy SINCE=2026-07-30` attributed the update
to the single resource `UnauthorizedApiCallsAlarmDEEEB676`; a post-deploy
`make diff-stack` reported no differences. At 23:50:14 — 32 seconds after
the deployment — the alarm transitioned `ALARM → OK` as the new 3-of-3
evaluation absorbed the pre-flight denial artifact.

## Change 2 — auditor read access to the audit log (manual, out-of-band)

The `${AWS_SECURITY_AUDITOR_USER_NAME}` IAM user is managed by hand, not by
CDK; the repository deliberately keeps human identities out of the stacks.
The grant was therefore applied the same way the identity itself is
managed: a deliberate, recorded `${AWS_ADMIN_USER_NAME}` action — distinct
from the break-glass escalation that was declined for routine investigation
on 07-24.

Inline policy `mlops-dev-auditor-audit-log-read`, applied via
`aws iam put-user-policy` at 23:51:11, with two statements:

- `AuditorReadAuditLogGroup`: `logs:FilterLogEvents` on
  `arn:aws:logs:us-east-1:${AWS_ACCOUNT_ID}:log-group:/aws/cloudtrail/mlops-dev-audit:*`.
- `AuditorDecryptAuditLogGroup`: `kms:Decrypt` on
  `arn:aws:kms:us-east-1:${AWS_ACCOUNT_ID}:key/${AUDIT_KEY_ID}` (the key
  behind `alias/mlops-dev-audit`), conditioned on
  `kms:EncryptionContext:aws:logs:arn` equalling the audit log-group ARN,
  because the log group is CMK-encrypted and a reader must decrypt. The
  condition confines the key use to this one log group.

The `PutUserPolicy` call itself matched the `IamPolicyChanges` filter
(still 1-of-1) and paged exactly once at 23:52:21 — 70 seconds after the
grant — serving as live proof of that detection. Sequencing was deliberate:
the grant followed the alarm deployment so any stray denial around the
grant window could no longer page.

Read-back `get-user-policy` confirmed both statements. The auditor then ran
`logs filter-log-events --limit 1` successfully, returning one event —
exercising both statements and closing the self-diagnosis gap: the auditor
can now attribute an unauthorized-api-calls fire from the audit log
instead of generating a second denial by trying.

## Live checks

- All six `mlops-dev-security-*` alarms `OK`; `unauthorized-api-calls`
  live-confirmed at `EvaluationPeriods 3`, `DatapointsToAlarm 3`,
  `Threshold 1.0`, `Period 300`.
- Alarm history after the deployment shows only the 23:50:14 `ALARM → OK`
  resolution — no new unauthorized-api-calls fire.
- `/predict` returned HTTP 200 with the unchanged `churn` /
  `churn_probability` contract for the repository's high-risk sample
  record.
- `get-trail-status`: `IsLogging true`, no delivery error.
- The `$20.00` monthly budget `${MONTHLY_BUDGET_NAME}` is intact with its
  50/80/100 percent alerts, read with `${AWS_ADMIN_USER_NAME}` because
  `budgets:ViewBudget` remains outside the auditor scope (the open gap
  recorded on 07-24 and 07-30; deliberately not re-triggered as a denial).

## Decision

Phase 2E is implemented, deployed, and verified. The observation window is
open: it closes in a later session once the alarm has demonstrated silence
on routine auditor activity, no sustained-burst detection has been missed,
the auditor read still works, the six alarms remain healthy, and the
budget is unchanged. Issue 10 stays open until that closure.
