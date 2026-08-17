---
type: decision
title: Two alert topics, operational and security
created: "2026-08-14"
updated: "2026-08-16"
sources: ["../../../infra/stacks/security_stack.py", "../../../infra/stacks/monitoring_stack.py", "../../../infra/app.py", "../../../infra/config/dev.yaml", "../../../infra/config/prod.yaml", "../../../tests/unit/test_security_stack.py", "../../../tests/unit/test_monitoring_stack.py", "../architecture/phased-security-hardening.md", "../architecture/security-phase-2-audit-foundation.md"]
summary: "The endpoint alarms move to a separate operational topic, because an idle dev endpoint is the expected state and its silence alarm made routine noise on the security channel."
---
# Two alert topics, operational and security

## Confirmed

- **One topic carried two kinds of signal.** Before this change, nine alarms
  published to `mlops-<env>-security-alerts`: the seven CIS and detection
  alarms, plus `mlops-<env>-endpoint-5xx` and `mlops-<env>-endpoint-silent`.
- **The silence alarm fires on any quiet day in dev.**
  `monitor.silence_alarm_hours` is 24 in `dev.yaml` and 6 in `prod.yaml`. Dev
  has no traffic floor, so an idle endpoint reaches `ALARM` on its own. The
  Phase 6 observation window recorded the cycle twice: the alarm fired
  2026-08-10T23:40Z, cleared 2026-08-11T22:07Z, fired again 2026-08-12T22:07Z,
  and cleared 2026-08-14T10:32Z on a `make smoke` run.
- **The alarm is correct, and this change does not alter it.** An idle
  serverless endpoint is the desired state and the reason the idle cost is near
  zero. Sub-phase 2F proved that the detector fires and clears.
- **`SecurityStack` now creates `mlops-<env>-ops-alerts`.** The topic uses the
  same audit KMS key, sets `enforce_ssl=True`, and subscribes the same email
  address. Its resource policy admits `cloudwatch.amazonaws.com` only. The stack
  exports `OpsAlertsTopicArn`.
- **`MonitoringStack` takes `ops_topic` in place of `alert_topic`.** Both
  endpoint alarms publish there. The change replaces the parameter and does not
  add a second one, because no other use of the security topic remained in that
  stack.
- **Budgets and EventBridge findings stay on the security topic.** The Phase 2D
  budget notifications and the Phase 3F Access Analyzer and Config rules are
  unchanged.
- **Two tests pin the split.** One asserts that both endpoint alarms import the
  ops topic and not the security topic. The earlier assertion accepted any
  `Fn::ImportValue` and could not tell the two topics apart, so it would have
  missed this regression in either direction. The other asserts that the ops
  topic is encrypted and admits `cloudwatch.amazonaws.com` only.

## Synthesis

- **A channel that mixes a heartbeat with a security finding trains the reader
  to skim it.** The security topic carries root activity, unauthorized API
  calls, IAM policy changes, trail changes, KMS disable and delete, bucket
  policy changes, and production deploy-role assumption. A daily message that
  means "nobody called the endpoint" sits beside them. The cost is not the
  message. The cost is the attention the reader stops paying to the channel.
- **The configuration already stated the intent.** Dev waits 24 hours and prod
  waits 6. Six hours of prod silence is a fault. Twenty-four hours of dev
  silence is an ordinary day. The two environments already disagreed about what
  the signal means, so one shared destination was the wrong shape.
- **The split is by audience, not by severity.** An operational alarm reports
  the platform. A security alarm reports the account. A new alarm MUST choose
  its topic by that question, not by how urgent it feels.
- **The encryption boundary does not change.** Both topics use the audit key
  and enforce SSL, so the split adds no new key, no new grant, and no new
  cdk-nag acknowledgement.

## Deployed to dev, 2026-08-14

`make deploy-stack STACK=Mlops-Dev-Monitoring ENV=dev` shipped the change.
`make verify-deploy SINCE=2026-08-14` reports the resources that changed:

| Stack | Resource | Result |
|---|---|---|
| `Mlops-Dev-Security` | `OpsAlertsTopic` | `CREATE_COMPLETE` |
| `Mlops-Dev-Security` | `OpsAlertsTopic/Policy` | `CREATE_COMPLETE` |
| `Mlops-Dev-Security` | `OpsAlertsTopic` email subscription | `CREATE_COMPLETE` |
| `Mlops-Dev-Monitoring` | `Endpoint5xxAlarm` | `UPDATE_COMPLETE` |
| `Mlops-Dev-Monitoring` | `EndpointSilentAlarm` | `UPDATE_COMPLETE` |
| `Mlops-Dev-Monitoring` | `DriftEvaluationFn`, `RetrainTriggerFn` | `UPDATE_COMPLETE` |
| `Mlops-Dev-Data` | none | the stack changed nothing |

**The two Lambda updates carry no source change.** They are the
non-reproducible bundled asset hash. A deploy from a cold `cdk.out`
republishes the function code with an identical source tree. Commit
`326f27f` later found the cause and fixed it: `.git` joined the asset
fingerprint, and it holds a different value in each checkout. The first
deploy after that commit updates all four functions one time.

The live routing check confirms the split. Nine alarms exist. Two name
`mlops-dev-ops-alerts`: `mlops-dev-endpoint-5xx` and
`mlops-dev-endpoint-silent`. Seven name `mlops-dev-security-alerts`. Both
topics use the same audit KMS key.

**The subscription is confirmed.** The request arrived at the deploy, a human
accepted it the same day, and the topic reports one `CONFIRMED` email
subscription.

**The deploy needed a value that `.env` did not hold.** `make deploy-stack`
stopped at the `check-alert-email` guard, which pull request #67 added the same
day. The stored `SecurityAlertEmail` parameter on the deployed Security stack
held the address, and a read recovered it. The value is unchanged, so the
security topic subscription stayed `CONFIRMED` and AWS sent no second request
for it.

**`make smoke` needs an identity that can invoke the API.** The auditor gets
`403` on `/predict`, and the deploy identity cannot resolve the URL because it
holds no `cloudformation:DescribeStacks`. Under `${AWS_ADMIN_USER_NAME}` the
six integration tests pass. The API contract is unchanged by this phase.

## Window closed as a go, 2026-08-16

The window owed two pieces of evidence. Both arrived, and each one is an email
in the operator's inbox rather than a console state.

**One endpoint alarm reached the new topic.** `mlops-dev-endpoint-silent` went
`OK -> ALARM` at 2026-08-15T23:26:10Z after 24 hourly datapoints below the
threshold. The email names its destination on the `State Change Actions -
ALARM:` line, `arn:aws:sns:us-east-1:${AWS_ACCOUNT_ID}:mlops-dev-ops-alerts`,
and its unsubscribe link carries a `mlops-dev-ops-alerts` subscription. The
address had never received a message from that topic before. Delivery is
proved.

**The security topic kept delivering.** Two security alarms fired after the
split and both reached `mlops-dev-security-alerts`:
`mlops-dev-security-iam-policy-changes` at 2026-08-14T21:37:07Z, which is
after the 14:52Z deploy, and `mlops-dev-security-unauthorized-api-calls` at
2026-08-16T21:12:17Z. The split moved the endpoint alarms and left the seven
security alarms where they were.

**The live routing matches the design.** `aws cloudwatch describe-alarms`
under `${AWS_SECURITY_AUDITOR_USER_NAME}` returns nine alarms in dev. Two name
`mlops-dev-ops-alerts` and seven name `mlops-dev-security-alerts`.

| Alarm | Topic |
|---|---|
| `mlops-dev-endpoint-5xx` | `mlops-dev-ops-alerts` |
| `mlops-dev-endpoint-silent` | `mlops-dev-ops-alerts` |
| `mlops-dev-security-cloudtrail-configuration-changes` | `mlops-dev-security-alerts` |
| `mlops-dev-security-iam-policy-changes` | `mlops-dev-security-alerts` |
| `mlops-dev-security-kms-key-disable-or-deletion` | `mlops-dev-security-alerts` |
| `mlops-dev-security-prod-deploy-role-assumed` | `mlops-dev-security-alerts` |
| `mlops-dev-security-root-user-activity` | `mlops-dev-security-alerts` |
| `mlops-dev-security-s3-bucket-policy-changes` | `mlops-dev-security-alerts` |
| `mlops-dev-security-unauthorized-api-calls` | `mlops-dev-security-alerts` |

**The same email also proves the 2F silence refix.** It reports
`MetricExpression: FILL(m1, 0)` over 24 of 24 one-hour periods. The original
2F build used `TreatMissingData` and never re-evaluated. The `FILL` form
evaluates on a missing datapoint, which is what makes a silence detector work.

**The window found one thing worth carrying forward.** The
`unauthorized-api-calls` alarm of 2026-08-16 was not a true positive. A query
of `/aws/cloudtrail/mlops-dev-audit` with the alarm's own metric filter
returned four `AccessDenied` events in the window, and every one came from an
AWS service-linked role reading a service the account does not use:
`AWSServiceRoleForConfig` against `frauddetector` and `cloudcontrolapi`, and
`AWSServiceRoleForResourceExplorer` against `profile`. No human principal
appears, and no external address does. The alarm behaved correctly against its
filter. The filter has no floor for AWS's own inventory sweeps.

## Tensions or open questions

- **Prod still runs one topic.** Dev carries the split since 2026-08-14. Prod
  keeps `mlops-prod-security-alerts` for all nine alarms until a deliberate
  rollout. Prod waits 6 hours on silence rather than 24, so the noise the split
  corrects does not exist there in the same form.
- **The `unauthorized-api-calls` filter counts AWS's own denials.** Config's
  resource-composition sweep pages the security channel on a schedule, and it
  is the second such observation on record. The filter MAY gain a
  `userIdentity.invokedBy` exclusion. That is a change to a CIS detection
  control, so it takes its own gate and MUST NOT ride along with another
  phase.
- **Whether dev needs a silence alarm at all is a separate question.** This
  change assumes it does and corrects only the destination.
