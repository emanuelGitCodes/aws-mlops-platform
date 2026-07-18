# AWS security hardening Phase 2B implementation — July 12, 2026

## Gate from Phase 2A

GitHub Actions run 9 for commit `89e3daa` completed successfully in 57 seconds.
Both `validate` and `secret-scan` passed, and the Gitleaks summary reported no
leaks. This evidence authorized the Phase 2B implementation checkpoint.

## Implemented scope

- Registered the new `Mlops-Dev-Security` stack in the CDK app and cdk-nag map.
- Added a retained, rotating symmetric KMS key with alias
  `alias/mlops-dev-audit`.
- Added a retained private SSE-S3 access-log sink with versioning, Bucket Owner
  Enforced, TLS 1.2 enforcement, and no recursive server-access logging.
- Added a retained private KMS-encrypted CloudTrail bucket with S3 Bucket Keys,
  versioning, Bucket Owner Enforced, TLS 1.2 enforcement, and access logging to
  the sink under `cloudtrail/`.
- Added retained log group `/aws/cloudtrail/mlops-dev-audit`, encrypted by the
  audit key with 90-day retention.
- Added multi-Region trail `mlops-dev-audit` for global read and write
  management events, log-file validation, S3 delivery, and CloudWatch Logs
  delivery. No data events, Insights, or organization-trail behavior exist.
- Added encrypted SNS topic `mlops-dev-security-alerts` and a required
  `SecurityAlertEmail` CloudFormation parameter with no default value.
- Added source-account and source-ARN restrictions for CloudWatch alarm and AWS
  Budgets publishing in both topic and KMS policies.
- Added CloudFormation outputs for the trail, buckets, log group, topic, and key
  alias.

The email address is not present in Git. It will be supplied only to the scoped
Security-stack deployment.

## Important implementation decision

CDK's legacy S3 access-log behavior attempted to use the `LogDeliveryWrite` ACL,
which is incompatible with Bucket Owner Enforced. The repository now enables
`@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy`, causing the S3 log-delivery
service to receive a source-account and source-bucket-restricted bucket policy
instead of an ACL.

CloudTrail is represented with an explicit `AWS::CloudTrail::Trail` resource so
the KMS, bucket, and CloudWatch role policies remain inspectable and narrowly
scoped. The role can write only log streams beneath the one audit log group.

## Validation

- Ruff check: passed.
- Ruff format check: passed across 43 files.
- Unit suite: 47 passed.
- Normal scoped `cdk synth Mlops-Dev-Security -c env=dev --no-lookups`: passed.
- cdk-nag: no unacknowledged findings.
- The access-log sink has one exact S1 acknowledgement because recursively
  logging that destination is prohibited by the design.
- The CloudTrail role has one exact IAM5 acknowledgement for the required
  wildcard log-stream suffix beneath one fixed log group.

## Boundary and next checkpoint

No Phase 2B AWS resource has been deployed yet. No metric filter, alarm, bucket
integration, budget notification, API change, or SageMaker execution is part of
this checkpoint. Commit and push Phase 2B separately, require both GitHub CI
jobs to pass, review a Security-only diff, and then deploy only
`Mlops-Dev-Security` with the email parameter.
