---
type: "source"
title: "AWS security hardening Phase 3F alert routing — August 8, 2026"
created: "2026-08-08"
updated: "2026-08-10"
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

**The analyzer rule is proved live.** A throwaway SQS queue carried a public
`sqs:GetQueueAttributes` grant from 13:15:26Z. Access Analyzer created finding
`<finding-id>` at **13:17:08Z** — about two minutes, against a documented estimate
of up to an hour. In the same five-minute window the rule recorded
`MatchedEvents` 1, `Invocations` 1, and `FailedInvocations` **0**, and the
topic recorded two publishes and two deliveries. The queue and an unused
throwaway bucket were both deleted at 13:18:21Z.

`FailedInvocations` 0 is the load-bearing number. It proves both new grants at
once: EventBridge could publish to the topic, and it could use the KMS key the
topic encrypts with. A missing key grant fails the invocation rather than
degrading quietly.

**The subscriber received the finding.** On aligned five-minute boundaries the
topic shows one publish and one delivery in the 13:15 bucket, with nothing else
happening in that window, and `NumberOfNotificationsFailed` 0 across the whole
period. The delivered email carries finding id `<finding-id>` — the same id the
analyzer created — with `"detail-type":"Access Analyzer Finding"`,
`"status":"ACTIVE"`, `"isDeleted":false`, and `"isPublic":true`. The delivered
event satisfies the rule's own predicate, so the pattern filtered rather than
merely passed traffic. Every link from finding to inbox is confirmed.

The Config rule remains unexercised. The recorder reports `recording: true`
and `lastStatus: SUCCESS`, and both delivery channels report `SUCCESS`.

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

- **The Config rule still has no live proof that it fires.** Proving that
  needs a deliberately broken delivery, which interrupts the compliance
  evidence trail for as long as it runs. That was judged too invasive for the
  value. The rule's pattern is pinned by tests; its firing path is not. The
  observation window did supply the negative half: a history delivery
  succeeded at 11:47Z with the rules live, and the rule matched nothing.
- **S3 rejects a bucket policy naming an account that does not exist**
  (`MalformedPolicy: Invalid principal in policy`). The first attempt used
  AWS's documentation placeholder `111122223333` and failed. Any future
  external-access test needs either a real second account or a resource type
  with no such validation — SQS worked, and it has no Block Public Access
  equivalent standing in the way.
- Finding `<finding-id>` stayed `ACTIVE` immediately after the queue was deleted.
  Access Analyzer resolves findings for deleted resources on a later pass, so
  a short-lived `ACTIVE` finding for a resource that no longer exists is
  expected, not a leak. **Closed.** The observation window recorded the finding
  `RESOLVED` at 13:19:35Z, about one minute after the delete, and the analyzer
  now reports zero active findings.
- `${AWS_SECURITY_AUDITOR_USER_NAME}` cannot read CloudWatch metrics —
  `cloudwatch:GetMetricStatistics` is ungranted, so this evidence needed
  `${AWS_ADMIN_USER_NAME}`. It sits alongside the known `config:ListConfigurationRecorders`
  gap.
- The Phase 2E precedent held: `mlops-dev-security-s3-bucket-policy-changes`
  went to `ALARM` on the test's own bucket-policy writes. A true positive on
  this work, like 3C's six.
- Full 3F — routing GuardDuty and Security Hub findings — stays behind the
  paid-plan decision in
  [paid Phase 3 security services](../decisions/phase-3-paid-security-services.md).
