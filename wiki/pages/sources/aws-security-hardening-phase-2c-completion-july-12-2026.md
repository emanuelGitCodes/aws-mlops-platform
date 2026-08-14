---
type: source
title: "AWS security hardening Phase 2C completion — July 12, 2026"
created: "2026-07-12"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-2c-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-implementation-july-12-2026.md", "../../../infra/stacks/security_stack.py", "https://docs.aws.amazon.com/securityhub/latest/userguide/cloudwatch-controls.html"]
summary: "Six exact detections are deployed, and a controlled IAM denial proved the metric, alarm, and received-email path."
---
# AWS security hardening Phase 2C completion — July 12, 2026

## Confirmed

The immutable completion record captures the green hosted gate, exact scoped
diff, named deployment, live filter and alarm configuration, controlled denied
IAM call, matching CloudTrail event, alarm transition, and received email.

## Synthesis

Phase 2C proves the complete near-real-time chain:

`Denied API call -> CloudTrail -> CloudWatch Logs -> metric filter -> metric -> alarm -> encrypted SNS -> email`

The controlled call was read-only and remained denied, so the test validated
detection without widening the deployment identity or changing an application
resource.

Related pages:

- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [Phase 2C implementation](aws-security-hardening-phase-2c-implementation-july-12-2026.md)

## Tensions or open questions

- The unauthorized-call alarm returns to `OK` on its own, after the five-minute
  datapoint that fired it ages out.
- Phase 2D MUST preserve the physical Data buckets and the single existing
  budget.
- The full Phase 2 cost observation begins after Phase 2D completes.
