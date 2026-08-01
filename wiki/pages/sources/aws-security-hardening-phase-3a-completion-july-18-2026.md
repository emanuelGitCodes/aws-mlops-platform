---
type: source
title: "AWS security hardening Phase 3A completion — July 18, 2026"
created: "2026-07-18"
updated: "2026-07-18"
sources: ["../../raw/aws-security-hardening-phase-3a-completion-july-18-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../tests/unit/test_security_monitoring_stack.py", "../../../tests/unit/test_deployment_policy.py", "https://aws.amazon.com/iam/access-analyzer/pricing/", "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-using-service-linked-roles.html", "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-findings-view.html"]
summary: "Phase 3A is complete: the account external-access analyzer is active after a scoped policy correction, its initial analysis has zero active findings, and application, alarm, budget, and later-service boundaries are healthy."
---
# AWS security hardening Phase 3A completion — July 18, 2026

## Confirmed

The analyzer and corrective execution-policy commits passed hosted validation
and secret scanning. The final named diff added only the external-access
analyzer, and the SecurityMonitoring stack reached `UPDATE_COMPLETE`.

Live verification found one active `ACCOUNT` analyzer with the expected name
and tags, a populated resource-analysis timestamp, no paid configuration, no
archive rules, and zero active public, cross-account, or error findings. The
Access Analyzer service-linked role exists. Later Phase 3 services remain
disabled.

The corrected execution policy is live as default `v8`, matches the repository,
retains `v7` for rollback, and is attached only to the intended CloudFormation
role. An unexpected zero-member group attachment was removed with explicit
approval without deleting the group or changing its other policy.

Application and operational checks passed: `/predict` returned HTTP 200 with
the unchanged threshold contract; the existing `$20` budget retains three
threshold notifications and reports `$0` calculated actual spend; and all six
security alarms returned to `OK` after the fully attributed IAM-change and
read-only-denial datapoints aged out.

## Synthesis

Phase 3A establishes a free external-access finding baseline without enabling
paid internal or unused-access analysis and without hiding findings through
archive rules. Zero active findings means the initial baseline contains no
unexplained public or cross-account access. Future active findings are
therefore new review work rather than accepted historical noise.

Related pages:

- [Phase 3A implementation](aws-security-hardening-phase-3a-implementation-july-18-2026.md)
- [Phase 3A first deployment rollback](aws-security-hardening-phase-3a-first-deployment-rollback-july-18-2026.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)

## Tensions or open questions

- The draft pull request remains intentionally unmerged.
- Analyzer rollback must remain CloudFormation-owned; do not delete the live
  analyzer manually.
- Phase 3B GuardDuty requires a separate implementation and review.
