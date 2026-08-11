# AWS security hardening Phase 2B completion — July 12, 2026

## Deployment gate

GitHub Actions run 10 for commit `161103d` completed successfully in 54
seconds. Both `validate` and `secret-scan` passed, and Gitleaks reported no
leaks.

The Security-only diff contained the 13 planned resources and six outputs. A
separate read of the six existing stacks found no Data, Registry, Training, or
Monitoring differences. Ingestion and Serving retained only the pre-existing
Lambda asset-hash drift recorded during Phase 0; the named Security-only deploy
could not apply those changes.

## Deployment result

Only `Mlops-Dev-Security` was deployed through the restricted
`${MLOPS_DEPLOYER_USER_NAME}` CDK bootstrap-role path. The required email address was passed
only as the `SecurityAlertEmail` CloudFormation parameter. The stack reached
`CREATE_COMPLETE` in 58 seconds.

Outputs:

- Trail: `mlops-dev-audit`
- Audit bucket: `${AUDIT_BUCKET}`
- Access-log bucket: `${ACCESS_LOG_BUCKET}`
- CloudWatch log group: `/aws/cloudtrail/mlops-dev-audit`
- Security topic: `arn:aws:sns:us-east-1:${AWS_ACCOUNT_ID}:mlops-dev-security-alerts`
- KMS alias: `alias/mlops-dev-audit`

## Live verification

- CloudFormation reports `CREATE_COMPLETE`.
- CloudTrail reports `IsLogging: true`, multi-Region and global-service events,
  read/write management events, log-file validation, no Insights, no data-event
  resources, and no organization-trail behavior.
- The trail, audit bucket, CloudWatch log group, and SNS topic use KMS key
  `29b692e1-fc49-4cdd-b8ea-f0d061b9599a` where required.
- Key rotation is enabled on a 365-day period.
- The audit bucket is KMS encrypted with S3 Bucket Keys; the access-log sink is
  SSE-S3 encrypted.
- Both buckets are private, versioned, and Bucket Owner Enforced.
- The audit bucket logs to the sink under `cloudtrail/`; the sink has no
  recursive logging configuration.
- CloudWatch Logs retention is 90 days and has no Phase 2C metric filters yet.
- CloudTrail delivered non-empty log objects and digest files to S3 and events
  to CloudWatch Logs without a delivery error.
- `cloudtrail validate-logs` validated the first available digest: 1 of 1 valid.
- The SNS subscription is confirmed. A direct encrypted-topic test publish was
  accepted as message `df3083ba-1152-5cba-b9f0-e174046d970e`, and the recipient
  supplied evidence that the test email arrived.

## Decision and next checkpoint

Phase 2B is complete and is a GO for Phase 2C after this completion record is
committed and its hosted CI passes. Phase 2C may add only the six approved
metric filters and alarms to `Mlops-Dev-Security`. Phase 2D Data references,
bucket logging, and budget notifications remain out of scope.
