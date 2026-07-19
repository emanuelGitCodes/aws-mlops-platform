---
type: source
title: "AWS security hardening Phase 3B first deployment rollback — July 18, 2026"
created: "2026-07-18"
updated: "2026-07-18"
sources: ["../../raw/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-guardduty-detector.html", "https://docs.aws.amazon.com/guardduty/latest/APIReference/API_CreateDetector.html"]
summary: "The first Phase 3B deployment rolled back cleanly because the GuardDuty resource provider returned SubscriptionRequiredException before a detector or service-linked role was created."
---
# AWS security hardening Phase 3B first deployment rollback — July 18, 2026

## Confirmed

Hosted validation and secret scanning passed, verified execution-policy `v9`
was installed with `v8` retained, and the named diff showed exactly one
GuardDuty detector addition. The named CloudFormation deployment then failed
with GuardDuty `SubscriptionRequiredException` and automatically reached
`UPDATE_ROLLBACK_COMPLETE`.

CloudTrail later confirmed that CloudFormation sent the exact expected
`CreateDetector` request and GuardDuty rejected it before any service-linked-
role call. No detector or GuardDuty role remains. The stack again contains only
the accepted Phase 3A analyzer and metadata. Execution policy `v8` is verified
default, `v9` is deleted, and attachment scope remains one role and zero users
or groups. Access Analyzer, later-service absence, all six alarms, budget, and
`/predict` passed post-rollback verification.

## Synthesis

The reported failure is a GuardDuty service-subscription boundary, not an IAM
`AccessDenied`. Current evidence is insufficient to claim why the
CloudFormation provider could not bootstrap the account's never-enabled state.
Manually creating the detector would evade the approved ownership and rollback
contract, so the draft PR remains open while the prerequisite is resolved.

Related pages:

- [Phase 3B implementation](aws-security-hardening-phase-3b-implementation-july-18-2026.md)
- [Phase 3A completion](aws-security-hardening-phase-3a-completion-july-18-2026.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)

## Tensions or open questions

- Determine the AWS-supported first-subscription path that remains compatible
  with CloudFormation ownership and explicit disabling of paid features.
- Phase 3B has no completion record; findings, trial days, and usage estimates
  remain unavailable until a detector exists.
