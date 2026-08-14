---
type: "source"
title: "AWS Free-plan account service limits — July 18, 2026"
created: "2026-07-18"
updated: "2026-08-14"
sources: ["../../raw/aws-free-plan-account-service-limits-july-18-2026.md", "https://aws.amazon.com/free/"]
summary: "The dev account is confirmed on the AWS Free account plan, which blocks GuardDuty and Security Hub at the billing level and resolves the Phase 3B SubscriptionRequiredException rollback."
---
# AWS Free-plan account service limits — July 18, 2026

## Confirmed

The Billing and Cost Management console showed the account on the AWS **Free
account plan** ("Your free plan account does not get charged"), with `$139.70`
of credits and `131` days remaining and an **Upgrade plan** action. The Free
plan restricts the account to a subset of services; paid-only security
services such as GuardDuty and Security Hub are outside it and return HTTP
403 `SubscriptionRequiredException` at the account level.

The AWS Config console rendered its full setup wizard, which was cancelled
without creating resources, because completing it would create a recorder,
delivery channel, service-linked role, and S3 bucket outside CloudFormation
ownership.

## Synthesis

This resolves the open root-cause question from the
[Phase 3B first deployment rollback](aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md):
the `CreateDetector` rejection was a billing-plan boundary, not an IAM denial,
template defect, or provider bug, and no retry can succeed while the account
stays on the Free plan. It also explains the
[Phase 0 baseline](../architecture/security-phase-0-baseline.md) probes, where
GuardDuty and Security Hub failed read-only calls with
`SubscriptionRequiredException` while AWS Config answered normally — a
plan-level block affects reads as well as writes, so Config is plausibly
inside the allowed set.

Roadmap consequences for the
[phased hardening roadmap](../architecture/phased-security-hardening.md):
Phase 3B and the later Security Hub sub-phase are hard-blocked pending a
deliberate paid-plan upgrade decision. The Config sub-phase MAY proceed, and
its gated CloudFormation deployment is also the availability test. An
upgrade keeps remaining credits but ends the cannot-be-charged guarantee; the
Phase 2 budget alerts and CIS alarms are the guardrails if it proceeds.

The July 19
[Phase 3 plan revision](phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md)
acts on these limits: it reorders Phase 3 around the Free plan and defers
GuardDuty and Security Hub behind an explicit upgrade gate.

## Tensions or open questions

- Whether AWS Config's first write (`CreateConfigurationRecorder`) succeeds on
  the Free plan is unproven until the gated Phase 3 deployment attempts it.
- The paid-plan upgrade decision (cost ownership, timing) remains open and
  blocks any Phase 3B retry.
