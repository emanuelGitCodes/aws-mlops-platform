---
type: source
title: "AWS security hardening Phase 3-prep implementation — July 14, 2026"
created: "2026-07-14"
updated: "2026-07-14"
sources: ["../../raw/aws-security-hardening-phase-3-prep-implementation-july-14-2026.md", "../../../infra/app.py", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/config/dev.yaml", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../tests/unit/test_security_monitoring_stack.py", "../../../tests/unit/test_deployment_policy.py"]
summary: "Phase 2 observation closes as a documented go; Phase 3 gains six enablement flags, an empty SecurityMonitoring stack, and pre-granted deployer permissions with no service enabled."
---
# AWS security hardening Phase 3-prep implementation — July 14, 2026

## Confirmed

The immutable implementation record closes the Phase 2D observation window
(first `artifacts/` access-log object delivered, ~zero daily cost, all alarm
noise attributed to known principals) and records the Phase 3 pre-state: no
Phase 3 service is enabled and no `Mlops-Dev-SecurityMonitoring` stack exists.
The repository gains six all-false `security.services` flags, a flag-gated
`SecurityMonitoringStack` that synthesizes to a metadata-only shell, and the
Phase 3 lifecycle actions plus scoped Config service-linked-role statements in
the CloudFormation execution policy. 51 unit tests, cdk-nag synthesis, and
live diffs (no unexpected differences) passed.

## Synthesis

Phase 3 repeats the Phase 2 sub-phase discipline with a configuration twist:
instead of adding constructs stack-by-stack, one boolean flag flips per
sub-phase commit, making each service a single `git revert`-able unit while
the stack wiring, tests, and deployer permissions stay fixed from this
checkpoint onward. Keeping the new services out of `Mlops-Dev-Security`
protects the retained CloudTrail foundation from any Phase 3 rollback, which
is exactly the boundary the phased plan's rollback contract requires.

Related pages:

- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)
- [Phase 2D completion](aws-security-hardening-phase-2d-completion-july-12-2026.md)

## Tensions or open questions

- The read-only change-set `cdk diff` itself generates `AccessDenied` noise
  from the scoped execution role; later sub-phases must diff with
  `--no-change-set` to keep the unauthorized-call alarm meaningful.
- Deployment of the shell stack and rotation of the execution policy to `v7`
  are pending the hosted CI gate for this commit.
