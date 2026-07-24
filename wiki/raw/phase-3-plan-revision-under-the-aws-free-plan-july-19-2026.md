# Phase 3 plan revision under the AWS Free plan — July 19, 2026

## Relationship to the original plan

This revision amends — and does not replace — the immutable July 12 phased
security hardening plan. Phases 0–2 and 4–9 are unchanged. Only the Phase 3
execution order, gates, and acceptance criteria change, because the account is
confirmed on the AWS Free account plan, which blocks GuardDuty and Security
Hub at the billing level (see the July 18 Free-plan service-limits source).
The decision recorded here is to **stay on the Free plan** and reorder Phase 3
rather than upgrade now.

## Revised execution order

The six sub-phase letters, the six `security.services` flags, and the
flag-gated `Mlops-Dev-SecurityMonitoring` stack are unchanged. Only the order
in which flags flip, and the gates between them, change:

1. **3A IAM Access Analyzer — complete.** Unchanged.
2. **3E account-level S3 Block Public Access — next.** Free, requires no
   service subscription, lowest risk, and independent of every other
   sub-phase.
3. **3C AWS Config — after 3E.** Config availability on the Free plan is
   unproven. The gated flag-controlled CloudFormation deployment doubles as
   the availability test: if the recorder create is rejected like GuardDuty
   was, automatic rollback leaves no orphaned resources. Recording is scoped
   minimally — workload resource types plus global IAM resources, with daily
   recording where acceptable — because configuration-item charges consume
   the remaining Free-plan credits. The Config console wizard is never used.
4. **3F EventBridge alert routing — partial.** Route only what exists on the
   Free plan: Access Analyzer findings and, if 3C succeeds, Config compliance
   changes to the Phase 2 SNS topic. GuardDuty and Security Hub routing is
   added only after those services exist.
5. **Paid-plan upgrade gate — explicit stop.** Upgrading is a deliberate
   manual billing decision by the account owner in the console, never an
   agent action and never part of a sub-phase. Credits carry over, but the
   cannot-be-charged guarantee ends. The Phase 2 budget alerts (50/80/100% of
   the `$20` budget) and six CIS alarms are the standing guardrails.
6. **3B GuardDuty, then 3D Security Hub — deferred behind that gate.** Each
   retains its full gate sequence: live stop gate, execution-policy rotation,
   named diff, named deployment, and finding/cost/application verification.
   3F is then completed for their findings.

## Revised acceptance criteria

Phase 3 on the Free plan is accepted when 3A, 3E, 3C, and partial 3F are
healthy and credit burn is acceptable. The original criterion "findings reach
Security Hub" is explicitly re-scoped as post-upgrade, alongside 3B and 3D
acceptance.

## Repository changes made with this revision

- `infra/config/dev.yaml` sets `guardduty: false` with a deferral comment, so
  no deployment from the repository can retry the create that the Free plan
  rejects. `prod.yaml` was already all-false.
- The flag-gated detector code in
  `infra/stacks/security_monitoring_stack.py` is retained unchanged and inert.
- The stack tests now assert that dev enables only the analyzer and
  synthesizes zero GuardDuty resources, while a separate test synthesizes the
  stack with a guardduty-enabled config override to keep the exact Phase 3B
  detector contract (enabled state, 15-minute publishing, six explicitly
  disabled paid features, tags) locked for the future retry.
- Draft pull request 5 is repurposed: retitled to describe the deferral, made
  ready for review, and merged only by human decision. Its branch carries
  this revision.

## Known interim divergence

The repository execution-policy document retains the GuardDuty lifecycle
actions installed as live `v9` during the failed 3B rollout and rolled back
to `v8`. The live default therefore differs from the repository document
until the next sub-phase's controlled rotation reinstalls the repository
content. This divergence is deliberate: the GuardDuty statements are inert
without a GuardDuty resource in any template, and rotating twice would burn a
policy-version slot without a deployment to justify it.

## Decision and next checkpoint

The next mutating AWS work is sub-phase 3E (account-level S3 Block Public
Access) under the standard gate sequence. Before its deployment, verify that
account-level BPA does not break the CDK bootstrap asset bucket or the
workload buckets' existing access patterns; all workload buckets are already
private with bucket-level blocks. Stop after 3E for its verification and
go/no-go before 3C.
