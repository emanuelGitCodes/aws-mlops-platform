---
type: source
title: "AWS security hardening Phase 2D first Data deployment rollback — July 12, 2026"
created: "2026-07-12"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-2d-first-data-deploy-rollback-july-12-2026.md", "../../../infra/stacks/data_stack.py", "../../../tests/unit/test_data_stack.py"]
summary: "The first Data deployment rolled back cleanly after AWS revealed that notification API calls require budgets:ModifyBudget authorization."
---
# AWS security hardening Phase 2D first Data deployment rollback — July 12, 2026

## Outcome

The first scoped Data deployment failed at the budget-notification provider and
rolled back completely. No bucket or budget was replaced. Source-bucket logging
returned to its pre-deployment state, and the existing budget retained zero
notifications.

The cause was an IAM authorization-name mismatch: the Budgets notification API
methods require `budgets:ModifyBudget`. The correction grants only that action
on the exact budget ARN.

## Retry gate

Before a Data retry, the repository MUST pass the local gates, a scoped diff, a
new commit, and hosted CI. The already-deployed Security sink statement remains the
verified prerequisite.

Related pages:

- [Phase 2D implementation](aws-security-hardening-phase-2d-implementation-july-12-2026.md)
- [Phase 2D budget preservation](aws-security-hardening-phase-2d-budget-preservation-july-12-2026.md)
- [Phase 2 audit foundation](../architecture/security-phase-2-audit-foundation.md)

