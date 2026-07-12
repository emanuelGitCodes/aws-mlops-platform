---
type: source
title: "AWS security hardening Phase 2A completion — July 12, 2026"
created: "2026-07-12"
updated: "2026-07-12"
sources: ["../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/mlops-cloudformation-execution-policy-v1-2026-07-10.json", "../../../infra/policies/mlops-cloudformation-execution-policy.json"]
summary: "The Data export drift is reconciled and execution-policy v6 is installed with an exact v1 archive and v5 rollback path."
---
# AWS security hardening Phase 2A completion — July 12, 2026

## Confirmed

The immutable completion record documents the scoped Data-stack reconciliation,
unchanged bucket identities and object counts, unchanged `$20` budget, exact
policy fingerprints, and controlled `v1` to `v6` version-slot rotation.

Live policy `v6` matches the repository-owned document and is attached only to
the CDK CloudFormation execution role. `v5` remains available for rollback.

## Synthesis

Phase 2A removes the known deployment prerequisite without deploying audit
resources. It preserves the separation between the restricted deployment
identity and the CloudFormation execution role: Phase 2 permissions were added
to the latter, while `iam:PassRole` remains scoped to `Mlops-Dev-*` roles and an
explicit service list.

Related pages:

- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)
- [Phase 0 AWS security baseline](../architecture/security-phase-0-baseline.md)

## Tensions or open questions

- Phase 2B still requires a scoped Security-stack diff, deployment, live audit
  verification, and manual confirmation of its email subscription.
- `v5` must remain available until the Security stack has passed its rollback
  and live-verification checkpoints.
