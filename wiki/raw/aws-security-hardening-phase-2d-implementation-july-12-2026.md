# AWS security hardening Phase 2D implementation — July 12, 2026

## Gate from Phase 2C

GitHub Actions run 13 for Phase 2C closeout commit `ce87620` passed `validate`
and `secret-scan` with no leaks. Phase 2D implementation was authorized.

## Implemented scope

`DataStack` now accepts the Security stack's access-log bucket and alert topic.
The existing physical Data resources are configured as follows:

- raw bucket -> access-log sink prefix `raw/`;
- curated bucket -> access-log sink prefix `curated/`;
- artifacts bucket -> access-log sink prefix `artifacts/`;
- existing single `$20` monthly budget -> ACTUAL percentage notifications at
  50, 80, and 100 percent, using `GREATER_THAN` and the encrypted security SNS
  topic.

The three resolved Data S1 acknowledgements were removed. No second budget was
created.

## Required deployment-order correction

Initial synthesis using CDK's high-level cross-stack S3 logging helper produced
three unconditioned `s3:PutObject` statements in the Security-owned sink bucket
policy. It also meant that deploying Data alone would reference a destination
policy that had not yet been updated.

The implementation was corrected before commit or deployment:

1. `SecurityStack` owns one explicit `AllowDataBucketAccessLogs` statement.
   It permits only `logging.s3.amazonaws.com`, only sink objects under `raw/`,
   `curated/`, and `artifacts/`, only source account `${AWS_ACCOUNT_ID}`, and only
   source bucket ARNs matching the dev project prefix `mlops-dev-data-*`.
2. `DataStack` writes each bucket's `LoggingConfiguration` through its own
   `AWS::S3::Bucket` resource. This creates only Data-to-Security imports and
   does not mutate the destination policy.

Phase 2D therefore requires two named deployments rather than the original
Data-only deployment:

- 2D.1: deploy only `Mlops-Dev-Security` to install the prerequisite sink
  policy while changing no Data resource.
- 2D.2: deploy only `Mlops-Dev-Data` to enable the three logging configurations
  and three notifications on the existing budget.

This split is required for both least privilege and successful S3 validation.
It remains inside the approved Phase 2 resource scope and is safer than an
all-stack deployment.

## Validation

- Unit synthesis passes with the Security-to-Data constructor boundary.
- Normal cdk-nag synthesis passes for both Security and Data.
- Synthesized Security policy contains exactly one conditioned Data-source
  statement and no generated unconditioned Data grants.
- Synthesized Data contains exactly three logging prefixes and imports one sink
  name.
- Synthesized Data contains exactly one `$20` budget and three SNS
  notifications at 50/80/100.
- The existing audit bucket continues to log under `cloudtrail/`.
- The three Data S1 acknowledgements are absent.

## Rollback

Rollback order remains mandatory. First remove the Data logging and budget
references and deploy only Data. Only afterward remove the Data-source statement
from Security. Retained audit buckets, access logs, KMS key, log group, and
objects are never deleted.

## Next checkpoint

Commit Phase 2D separately and require hosted CI. Review both scoped diffs.
Deploy Security first and verify the conditioned sink policy; then deploy Data
and verify bucket identities, object counts, logging, imports, and the single
budget's three notifications.
