# Phase 2D budget-preservation correction — July 12, 2026

## Finding

The pre-deployment Data diff showed that adding
`NotificationsWithSubscribers` to the existing `AWS::Budgets::Budget` requires
resource replacement. Deployment was stopped before AWS was changed because a
replacement would violate the Phase 2D requirement to retain the existing `$20`
budget, its physical name, and its history.

## Correction

The budget remains one unchanged `AWS::Budgets::Budget` without inline
notifications. Three `Custom::AWS` resources call the Budgets API to create the
50, 80, and 100 percent ACTUAL notifications and delete only their matching
notification during rollback. Each call uses `GREATER_THAN`, percentage
thresholds, the existing budget reference, and the encrypted Security SNS topic.

The provider role is limited to `budgets:CreateNotification` and
`budgets:DeleteNotification` on the existing budget ARN. Its generated Lambda
basic execution managed policy has one exact cdk-nag acknowledgement for later
Phase 5 IAM cleanup.

## Verification before deployment

- Focused Ruff and CDK unit tests pass.
- The budget template has no `NotificationsWithSubscribers` property.
- Exactly three create and three matching delete calls are synthesized.
- The corrected Data diff must show no `AWS::Budgets::Budget` replacement before
  deployment is authorized.

