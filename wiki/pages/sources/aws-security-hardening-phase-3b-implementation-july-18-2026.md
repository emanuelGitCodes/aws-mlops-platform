---
type: source
title: "AWS security hardening Phase 3B implementation — July 18, 2026"
created: "2026-07-18"
updated: "2026-07-18"
sources: ["../../raw/aws-security-hardening-phase-3b-implementation-july-18-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/config/dev.yaml", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../tests/unit/test_security_monitoring_stack.py", "../../../tests/unit/test_deployment_policy.py", "https://docs.aws.amazon.com/guardduty/latest/APIReference/API_CreateDetector.html", "https://docs.aws.amazon.com/guardduty/latest/APIReference/API_DetectorFeatureConfiguration.html", "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-guardduty-detector.html", "https://docs.aws.amazon.com/guardduty/latest/ug/slr-permissions.html", "https://aws.amazon.com/guardduty/pricing/"]
summary: "Phase 3B is implemented and locally validated as one foundational GuardDuty detector with every current optional paid feature explicitly disabled; hosted gates, policy rotation, deployment, and live verification remain pending."
---
# AWS security hardening Phase 3B implementation — July 18, 2026

## Confirmed

The immutable implementation record captures a clean read-only AWS pre-state,
the dev-only foundational detector, 15-minute publishing, exact Phase 3B tags,
and six explicitly disabled optional features, including the newly expressible
`AI_ANALYST` feature. Runtime-monitoring features, legacy data-source
configuration, filters, IP sets, threat-intelligence sets, publishing
destinations, and sample findings are absent.

Local validation passed with 54 tests, lint, lock checking, dependency audit,
eight-stack cdk-nag synthesis, named-target dry runs, unchanged IAM
fingerprints, and a clean-main template comparison. The CloudFormation
execution-policy addition is limited to GuardDuty's exact service-linked role
and service name.

No AWS mutation or GuardDuty deployment is claimed by this checkpoint.

## Synthesis

Phase 3B preserves the one-flag, one-service, one-stack rollback boundary.
Foundational CloudTrail management, VPC flow, and DNS detection can start
without silently accepting optional protection-plan charges. The refreshed
API enumeration matters because the create-detector contract enables omitted
optional features by default; an exact deny-by-configuration list prevents a
newly launched feature from changing rollout scope.

Related pages:

- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [Phase 3A completion](aws-security-hardening-phase-3a-completion-july-18-2026.md)
- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)

## Tensions or open questions

- Hosted validation, secret scanning, execution-policy `v9` rotation, named
  diff, named deployment, finding review, free-trial and usage inspection,
  budget/alarm checks, and `/predict` verification remain required.
- If the live feature list changes again before deployment, refresh it and
  stop if CloudFormation cannot explicitly disable a newly default-on paid
  feature.
- A separate completion source must record live evidence before Phase 3C.
