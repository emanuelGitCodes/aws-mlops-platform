---
type: "source"
title: "AWS security hardening Phase 3F alert routing — August 8, 2026"
created: "2026-08-08"
updated: "2026-08-08"
sources: ["../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/security_stack.py", "../../../infra/config/dev.yaml", "../../../tests/unit/test_security_monitoring_stack.py", "../../../tests/unit/test_security_stack.py"]
summary: "Partial 3F routes active Access Analyzer findings and Config delivery failures to the Phase 2 alert topic, deployed to dev with both rules live and neither yet fired."
---
# AWS security hardening Phase 3F alert routing — August 8, 2026

## Confirmed

Two EventBridge rules are deployed in `Mlops-Dev-SecurityMonitoring`, both
`ENABLED`, both targeting the Phase 2 topic
`mlops-dev-security-alerts` as their single target:

| Rule | Pattern |
|---|---|
| `mlops-dev-security-access-analyzer-findings` | `aws.access-analyzer`, `Access Analyzer Finding`, `status` `ACTIVE`, `isDeleted` `false` |
| `mlops-dev-security-config-delivery-failures` | `aws.config`, history and snapshot delivery status, `messageType` the two `*DeliveryFailed` values |

`Mlops-Dev-Security` gained one statement on the audit key
(`AllowEventBridgeEncryptedAlerts`) and one on the topic policy
(`AllowEventBridgePublish`). Both carry `aws:SourceAccount` and an `ArnLike`
on `:rule/mlops-<env>-security-*`.

The `eventbridge_alerts` flag is true in `dev.yaml` and false in `prod.yaml`.
Prod synthesizes to `CDKMetadata` alone and carries neither grant.

`make verify-deploy SINCE=2026-08-08` reports exactly four resources across
the two stacks: `AccessAnalyzerFindingRule` and `ConfigDeliveryFailureRule`
created, `AuditKeyB2DBB069` and `SecurityAlertsTopicPolicy1E6023E3` updated.

Neither rule has fired. The analyzer reports zero `ACTIVE` findings. The
recorder reports `recording: true` and `lastStatus: SUCCESS`, and both
delivery channels report `SUCCESS`. Every source is healthy and has nothing
to report, so the routing is deployed and unexercised.

`make lint`, `make typecheck`, and `make security` pass. `make test` reports
306 passed at `93.45%`, and the floor moves `93.37 → 93.45`.

## Synthesis

The execution policy needed no rotation. `ApplicationServices` already grants
`events:PutRule`, `events:PutTargets`, `sns:SetTopicAttributes`, and the rest
of the set these rules use, because the platform's own EventBridge and SNS
resources needed them first. The version-slot cleanup that preceded this
phase was owed for its own reasons and stays banked for the next grant.

The grants name the rule prefix rather than a rule reference. The rules live
in `SecurityMonitoring`, which already depends on `Security` for the topic;
a reference in the other direction would close that into a cycle. The prefix
is the coupling, so a rule named outside `mlops-<env>-security-*` matches its
events and then fails to publish them. A test pins the prefix on both sides
for that reason.

Two sources are deliberately not routed. Configuration item changes would
emit one event per change across about 100 recorded resources into an email
topic. Compliance events have no producer, because this account deploys no
Config rules. Both exclusions are asserted in tests, so removing one is a
visible decision rather than a quiet edit.

A source routes only while its own service is on. This keeps the deployed
rule set an honest picture of what is being watched: a rule for a switched-off
service matches nothing and reads exactly like a working rule that has found
nothing.

## Tensions or open questions

- **Neither rule has live proof.** Both source services are healthy, so
  nothing has exercised the path end to end. Proving the analyzer rule needs
  a deliberately generated finding — a cross-account principal on a low-value
  bucket, reverted after — which also pages the `iam-policy-changes` alarm.
  Proving the Config rule needs a deliberately broken delivery. Neither test
  has been run.
- The Phase 2E precedent is that a gated deploy pages
  `iam-policy-changes` and `unauthorized-api-calls`; 3C produced six such
  emails, all true positives. This deploy changed a key policy and a topic
  policy, so the same alarms may fire on its own work.
- Full 3F — routing GuardDuty and Security Hub findings — stays behind the
  paid-plan decision in
  [paid Phase 3 security services](../decisions/phase-3-paid-security-services.md).
