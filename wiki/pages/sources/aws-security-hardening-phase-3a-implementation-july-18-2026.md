---
type: source
title: "AWS security hardening Phase 3A implementation — July 18, 2026"
created: "2026-07-18"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3a-implementation-july-18-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/config/dev.yaml", "../../../tests/unit/test_security_monitoring_stack.py", "https://aws.amazon.com/iam/access-analyzer/pricing/", "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-accessanalyzer-analyzer.html"]
summary: "Phase 3A is implemented and locally validated as one dev account external-access analyzer; live diff, deployment, and finding review remain pending credentials and hosted CI."
---
# AWS security hardening Phase 3A implementation — July 18, 2026

## Confirmed

The immutable implementation record captures the dev-only `ACCOUNT` analyzer,
its deterministic name and Phase 3A tags, the absence of archive rules and
paid analyzer configuration, the still-disabled production shell, and green
local validation: lint, 52 tests, lock check, dependency audit, and eight-stack
cdk-nag synthesis. The generated SecurityMonitoring template adds only the
analyzer alongside CDK metadata and introduces no IAM resources.

No AWS deployment or live verification is claimed. The configured session had
no credentials, and the temporary-login flow was cancelled before
authorization.

## Synthesis

Phase 3A follows the one-flag, one-resource, one-stack rollback boundary
established during Phase 3-prep. Omitting archive rules keeps every initial
public or cross-account finding visible until it is explained. Omitting
`AnalyzerConfiguration` avoids the paid internal-access and unused-access
analyzer modes; AWS lists external-access analysis at no additional charge.

Related pages:

- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [Phase 3-prep completion](aws-security-hardening-phase-3-prep-completion-july-14-2026.md)
- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)

## Tensions or open questions

- Live pre-state, no-change-set diff, hosted CI, named-stack deployment,
  initial analysis completion, and finding review remain required.
- The deployment MUST stop for an ownership decision when a live account
  analyzer exists. This implementation neither deletes such an analyzer nor
  adopts it without a record.
- A separate completion source MUST record the live evidence before Phase 3B.
