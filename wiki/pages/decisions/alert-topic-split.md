---
type: decision
title: Two alert topics, operational and security
created: "2026-08-14"
updated: "2026-08-14"
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

## Tensions or open questions

- **No AWS resource carries this change.** It is implemented and reviewed in
  the repository. The account still routes both endpoint alarms to the security
  topic. Read this page as an implementation record until a deployment record
  says otherwise.
- **The new topic needs its own email confirmation.** AWS sends a fresh
  subscription request at the first deploy. Until a human accepts it, the
  endpoint 5xx alarm and the endpoint silence alarm deliver nowhere. No CDK code
  can do this step.
- **The deploy pulls in two stacks.** `Mlops-Dev-Monitoring` imports the topic
  from `Mlops-Dev-Security`, so a Monitoring deploy also ships any pending
  Security change. Read the `Including dependency stacks:` line on the diff, and
  run `make verify-deploy` after.
- **This is an alarm-behavior change, so it takes the Phase 2E gate.**
  Sub-phases 2F and 2G set the precedent: a pre-flight baseline of the live
  alarm state, a reviewed named diff, a scoped dev deploy, resource-level
  verification, an observation window, and an explicit go/no-go. The window MUST
  show one endpoint alarm arriving on the new topic and MUST confirm that the
  seven security alarms still reach the old one.
- **Whether dev needs a silence alarm at all is a separate question.** This
  change assumes it does and corrects only the destination.
