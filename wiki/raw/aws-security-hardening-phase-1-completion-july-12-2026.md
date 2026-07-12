# AWS security hardening Phase 1 completion — July 12, 2026

## Objective

Close every repository-only Phase 1 acceptance gate without deploying AWS
resources or committing the work before the requested human review.

## Review corrections

- Updated `actions/checkout` to v7.0.0, `astral-sh/setup-uv` to v8.3.2,
  `aws-actions/configure-aws-credentials` to v6.2.2, and
  `gitleaks/gitleaks-action` to v3.0.0. Every action is pinned to the immutable
  full commit SHA and carries a human-readable release comment.
- Upgraded `cdk-nag` from 2.38.2 to 3.0.1 so it registers through CDK's native
  policy-validation plugin interface.
- Preserved individual granular IAM acknowledgements. CDK 2.261 rejects
  granular IDs containing an ARN or finding `::` delimiter through the public
  acknowledgement method, so those exact IDs use the equivalent
  `aws:cdk:acknowledged-rules` construct metadata. Ordinary rule IDs continue
  through `Validations.of(...).acknowledge()`.
- Extended the acknowledgement regression test to prove that every accepted
  finding exists on exactly one construct and is represented by its exact
  acknowledgement metadata and remediation phase.

## Completed acceptance evidence

- `uv lock --check`: passed with 108 locked packages.
- `pip-audit --skip-editable`: no known vulnerabilities found.
- Ruff check and format check: passed across 41 files.
- Unit suite: 44 passed.
- Normal `cdk synth -c env=dev --no-lookups`: passed for all six stacks with
  real Lambda asset bundling and the cdk-nag 3 policy-validation report.
- Gitleaks v8.30.1 full Git history scan: 10 commits and approximately 301 KB
  scanned; no leaks found.
- Gitleaks scans of the complete tracked diff and every untracked Phase 1 file:
  no leaks found.
- Workflow YAML parsing, wiki lint, and `git diff --check` are final handoff
  checks.

The normal synth emits non-blocking warnings for the deprecated CDK
`logRetention` property and the new cross-stack-reference-strength feature
flag. They are recorded for later phases and do not represent an unacknowledged
AwsSolutions failure.

## Boundary and next checkpoint

Phase 1 is complete. No AWS API, CloudFormation deployment, SageMaker pipeline
execution, IAM change, KMS change, API Gateway change, or security-service
subscription occurred. The repository remains uncommitted for final human
review. Phase 2 must not begin until the reviewer explicitly accepts this diff,
and the pre-existing Data-to-Serving export-removal blocker still prevents an
undifferentiated all-stack deployment.
