---
type: "source"
title: "Phase 3 plan revision under the AWS Free plan — July 19, 2026"
created: "2026-07-19"
updated: "2026-07-19"
sources: ["../../raw/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md", "../../../infra/config/dev.yaml", "../../../infra/stacks/security_monitoring_stack.py", "../../../tests/unit/test_security_monitoring_stack.py"]
summary: "Phase 3 is reordered for the Free plan: 3E BPA next, then gated 3C Config and partial 3F routing, with 3B GuardDuty and 3D Security Hub deferred behind an explicit paid-plan upgrade gate."
---
# Phase 3 plan revision under the AWS Free plan — July 19, 2026

## Confirmed

The revision amends the immutable
[July 12 plan](phased-aws-security-hardening-plan-july-12-2026.md) without
replacing it: sub-phase letters, the six `security.services` flags, and the
flag-gated stack are unchanged; only Phase 3 execution order, gates, and
acceptance change. The revised order is 3A (complete) → 3E account S3 Block
Public Access → 3C AWS Config (gated deployment doubles as the Free-plan
availability test, minimally scoped recording) → 3F partial EventBridge
routing → explicit paid-plan upgrade gate → deferred 3B GuardDuty and
3D Security Hub with their full gate sequences.

With the revision, `dev.yaml` sets `guardduty: false` so no repository
deployment can retry the create the Free plan rejects; the detector code
stays flag-gated and inert; the stack tests assert zero GuardDuty resources
in dev while a config-override test keeps the exact detector contract locked
for the future retry; and draft pull request 5 is repurposed to carry the
deferral.

## Synthesis

The reorder follows the roadmap's own risk logic: the free,
subscription-independent control (account BPA) moves first, the
unproven-availability service (Config) is tested only through the gated
CloudFormation path with automatic rollback, and the billing-blocked services
wait behind a human upgrade decision guarded by the Phase 2 budget alerts and
alarms. The known interim divergence — repository execution policy retaining
GuardDuty actions while live default is `v8` — is deliberate and reconciles
at the next sub-phase's rotation. Root cause context lives in
[AWS Free-plan account service limits](aws-free-plan-account-service-limits-july-18-2026.md)
and the
[Phase 3B rollback record](aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md);
the maintained sequencing lives in the
[phased hardening roadmap](../architecture/phased-security-hardening.md).

## Tensions or open questions

- AWS Config availability on the Free plan remains unproven until the gated
  3C deployment attempts the first recorder create.
- Account-level BPA interaction with the CDK bootstrap asset bucket must be
  verified during 3E preparation before its deployment.
- The paid-plan upgrade decision has no deadline; 3B/3D and full 3F remain
  open-ended deferrals until it is made.
