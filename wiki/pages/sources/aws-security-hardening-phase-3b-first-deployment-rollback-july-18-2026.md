---
type: source
title: "AWS security hardening Phase 3B first deployment rollback — July 18, 2026"
created: "2026-07-18"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-guardduty-detector.html", "https://docs.aws.amazon.com/guardduty/latest/APIReference/API_CreateDetector.html"]
summary: "The first Phase 3B deployment rolled back cleanly because the GuardDuty resource provider returned SubscriptionRequiredException before a detector or service-linked role was created."
---
# AWS security hardening Phase 3B first deployment rollback — July 18, 2026

## Confirmed

Hosted validation and secret scanning passed. The install put the verified
execution policy `v9` in place and retained `v8`. The named diff showed exactly
one addition: the GuardDuty detector. The named CloudFormation deployment then failed
with GuardDuty `SubscriptionRequiredException` and automatically reached
`UPDATE_ROLLBACK_COMPLETE`.

CloudTrail later confirmed that CloudFormation sent the exact expected
`CreateDetector` request and GuardDuty rejected it before any service-linked-
role call. No detector and no GuardDuty role remains. The stack again holds only
the accepted Phase 3A analyzer and the metadata. A check verified `v8` as the
default execution policy. `v9` no longer exists. The attachment scope stays one
role, zero users, and zero groups. The post-rollback verification passed for
Access Analyzer, the absence of the later services, all six alarms, the budget,
and `/predict`.

## Synthesis

The reported failure is a GuardDuty service-subscription boundary, not an IAM
`AccessDenied`. A check later the same day confirmed the cause: the account is on
the AWS Free account plan, which blocks paid-only services such as GuardDuty
entirely, so the provider could never bootstrap the subscription. See
[AWS Free-plan account service limits](aws-free-plan-account-service-limits-july-18-2026.md).
Manually creating the detector would evade the approved ownership and rollback
contract, so the draft PR remains open while the paid-plan upgrade decision is
pending.

Related pages:

- [Phase 3B implementation](aws-security-hardening-phase-3b-implementation-july-18-2026.md)
- [Phase 3A completion](aws-security-hardening-phase-3a-completion-july-18-2026.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)

## Tensions or open questions

- ~~Determine the AWS-supported first-subscription path~~ — resolved July 18:
  the account's AWS Free plan forbids GuardDuty; the remaining decision is the
  paid-plan upgrade, recorded in
  [AWS Free-plan account service limits](aws-free-plan-account-service-limits-july-18-2026.md).
- Phase 3B has no completion record; findings, trial days, and usage estimates
  remain unavailable until a detector exists.
