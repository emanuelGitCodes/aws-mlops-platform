# Phase 2D completion — July 12, 2026

## Hosted gate and deployments

Corrective commit `0deb381` passed GitHub Actions run 16: `validate` and
`secret-scan` succeeded with no leaks.

The named `Mlops-Dev-Data` retry completed at 2026-07-13 02:11:40 UTC. CDK
evaluated the Security dependency and reported no changes. Data reached
`UPDATE_COMPLETE`.

## Live verification

- Raw, curated, and artifacts retained their original physical bucket names.
- Object-version counts remained 1, 1, and 156, with zero delete markers.
- Logging targets the retained Security sink under `raw/`, `curated/`, and
  `artifacts/` respectively.
- The audit bucket continues to log under `cloudtrail/`.
- Access-log objects were already delivered under `raw/` and `curated/` during
  immediate verification. S3 had not yet delivered the first `artifacts/`
  object; delivery is asynchronous and remains part of the observation check.
- The existing budget name
  `${MONTHLY_BUDGET_NAME}` remains one `$20` monthly
  COST budget.
- Its ACTUAL `GREATER_THAN` notifications are exactly 50, 80, and 100 percent.
- Every notification has exactly one SNS subscriber:
  `arn:aws:sns:us-east-1:${AWS_ACCOUNT_ID}:mlops-dev-security-alerts`.
- Data is the only importer of both the Security access-log bucket and alert
  topic exports.
- The SNS email subscription remains confirmed.
- CloudTrail remains logging to S3 and CloudWatch Logs, and all six security
  metric filters remain present.
- `/predict` returned HTTP 200 with `churn_probability` 0.3656342029571533 and
  `churn` false. The schema, probability bounds, and `score >= 0.50` rule match.

## Alarm interpretation

An additional unauthorized-call alarm email was traced to the AWS Resource
Explorer service-linked role receiving `AccessDenied` while inventorying
CloudControl and IoT FleetWise resources. It was not an unknown principal or an
application caller. Exact CIS filters are intentionally retained; service-role
noise should be assessed during the observation window before any filtering
exception is proposed.

## Phase boundary

Phase 2 implementation is complete. Phase 3 is not authorized. Observe
CloudTrail, CloudWatch Logs, S3, SNS, KMS, alarm noise, and total cost for at
least 24 hours against the existing `$20` budget. Confirm the first
`artifacts/` access-log object during that window.

