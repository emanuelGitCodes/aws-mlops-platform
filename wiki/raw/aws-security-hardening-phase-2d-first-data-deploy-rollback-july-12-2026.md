# Phase 2D first Data deployment rollback — July 12, 2026

## Attempt

After corrective commit `2216a30` passed GitHub Actions run 15, the scoped
Security prerequisite deployment completed successfully. Its only live resource
change was the conditioned `AllowDataBucketAccessLogs` statement.

The subsequent named `Mlops-Dev-Data` deployment updated all three source bucket
logging configurations, then failed while creating the budget notification
custom resources.

## Cause

The provider policy allowed the Budgets API method names
`budgets:CreateNotification` and `budgets:DeleteNotification`. AWS IAM maps both
operations to the authorization action `budgets:ModifyBudget`. The provider
therefore received `AccessDenied` for the existing budget ARN.

## Rollback evidence

CloudFormation reached `UPDATE_ROLLBACK_COMPLETE`. The three custom resources,
their provider Lambda, role, and policies were removed. Each source bucket's
logging configuration was restored to its pre-deployment empty state. The
existing budget name and resource remained intact with zero notifications.

The Security sink statement remains deployed and is harmless until Data logging
is enabled. It is still required for the retry.

## Correction

The provider policy now grants only `budgets:ModifyBudget` on the exact existing
budget ARN. Tests assert the exact IAM action, budget-scoped resource, three
create calls, and three matching delete calls.

