---
type: source
title: "AWS security hardening Phase 2D budget preservation — July 12, 2026"
created: "2026-07-12"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-2d-budget-preservation-july-12-2026.md", "../../../infra/stacks/data_stack.py", "../../../infra/security_checks.py", "../../../tests/unit/test_data_stack.py"]
summary: "The pre-deployment diff caught a budget replacement and the corrected implementation preserves the existing budget through scoped Budgets API calls."
---
# AWS security hardening Phase 2D budget preservation — July 12, 2026

## Confirmed

The immutable implementation record documents a pre-deployment safety catch:
CloudFormation would replace the existing budget if notifications were added
inline. No AWS mutation occurred with that unsafe diff.

The corrected implementation keeps the existing budget resource unchanged and
uses three lifecycle-managed Budgets API attachments for the 50, 80, and 100
percent alerts. Each custom resource deletes only its own notification during
rollback.

## Deployment gate

Phase 2D deployment is allowed only after a new scoped Data diff confirms there
is no budget replacement. The live verification MUST show the same budget name
and the same limit, with exactly three SNS notifications.

The first Data attempt preserved the budget but exposed the Budgets IAM action
mapping and rolled back cleanly. See the rollback record for the corrected
`budgets:ModifyBudget` authorization.

Related pages:

- [Phase 2D implementation](aws-security-hardening-phase-2d-implementation-july-12-2026.md)
- [Phase 2D first Data deployment rollback](aws-security-hardening-phase-2d-first-data-deploy-rollback-july-12-2026.md)
- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
