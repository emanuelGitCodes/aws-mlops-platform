# AWS security hardening Phase 2C implementation — July 12, 2026

## Gate from Phase 2B

GitHub Actions run 11 for closeout commit `6e11405` passed `validate` and
`secret-scan`, with no leaks. The deployed Phase 2B audit and alert foundation
therefore authorized the Phase 2C detection implementation.

## Implemented scope

Added exactly six CloudWatch Logs metric filters and six CloudWatch alarms to
`Mlops-Dev-Security`:

| Metric | AWS Security Hub control |
|---|---|
| `RootUserActivity` | CloudWatch.1 |
| `UnauthorizedApiCalls` | CloudWatch.2 |
| `IamPolicyChanges` | CloudWatch.4 |
| `CloudTrailConfigurationChanges` | CloudWatch.5 |
| `KmsKeyDisableOrDeletion` | CloudWatch.7 |
| `S3BucketPolicyChanges` | CloudWatch.8 |

Each filter preserves the exact filter pattern from the current AWS Security
Hub remediation instructions. No term, event source, or additional field was
added. Each filter publishes `1` with default `0` into namespace
`MLOps/Security`.

Each alarm uses:

- statistic `Sum`;
- period 300 seconds;
- threshold greater than or equal to `1`;
- one evaluation period;
- missing data treated as `notBreaching`;
- actions enabled;
- the existing encrypted `mlops-dev-security-alerts` topic as its only action.

## Validation

- Lock check: passed with 108 packages.
- Dependency audit: no known vulnerabilities.
- Ruff check and format check: passed across 43 files.
- Unit suite: 48 passed.
- Normal Security-only CDK synthesis and cdk-nag validation: passed.
- Tests assert all six exact pattern strings, metric transformations, alarm
  periods, thresholds, comparison operators, missing-data treatment, and SNS
  actions.
- The Security-stack IAM fingerprint remains unchanged from Phase 2B.

## Boundary and next checkpoint

Phase 2C is implemented but not deployed. No audit-foundation resource, Data
stack, bucket logging, budget, API, or SageMaker pipeline changed. Commit this
checkpoint separately, require hosted CI, review a Security-only diff, and then
deploy only `Mlops-Dev-Security`.
