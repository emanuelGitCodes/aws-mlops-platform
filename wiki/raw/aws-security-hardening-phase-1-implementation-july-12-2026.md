# AWS security hardening Phase 1 implementation — July 12, 2026

## Objective

Implement the repository-only security guardrails approved in Phase 1 without
deploying or changing any AWS resource, starting a pipeline execution, or
committing the work before human review.

## Repository changes

- Added a Python 3.12 project pin and a generated `uv.lock` dependency lockfile.
- Added `cdk-nag` and `pip-audit` to the development toolchain.
- Applied `AwsSolutionsChecks` to all six CDK stacks.
- Bound every accepted existing finding to one exact construct with a reason and
  the later remediation phase. There are no stack-wide acknowledgements.
- Strengthened S3 assertions to require all four public-access-block flags,
  encryption, versioning, and TLS-only bucket policies.
- Added regression tests for the two existing
  `AmazonSageMakerFullAccess` attachments, literal `Resource: "*"` policies, and
  a full fingerprint of every synthesized IAM role and policy.
- Changed CI to install locked dependencies, lint, run unit tests, audit Python
  dependencies, synthesize with `cdk-nag`, and scan Git history with Gitleaks.
- Pinned third-party GitHub Actions to immutable commit SHAs and reduced CI's
  token permission to read-only repository contents.
- Changed deployment automation from automatic pushes to a manual-only
  workflow. This prevents a merge from attempting the known-unsafe all-stack
  deployment while the Data-stack export conflict remains unresolved.

## Verification performed locally

- `uv lock --check`: passed with 108 resolved packages.
- `ruff check .`: passed.
- `ruff format --check .`: passed across 41 files.
- `pytest tests/unit -q`: 44 passed.
- The unit stack fixture synthesized all six stacks with `AwsSolutionsChecks`;
  all known findings were acknowledged at their exact resources and no unknown
  finding remained.
- `git diff --check`: passed before the documentation update and must be rerun
  during final handoff.

## Checks deferred to GitHub CI

- `pip-audit` is configured but its local run could not query PyPI because the
  execution sandbox denied outbound DNS and the approval service was
  unavailable. It must pass in CI before Phase 1 is accepted.
- Gitleaks is configured as a full-history CI job. The CLI is not installed in
  the local environment, so the CI result is the required secret-scan evidence.
- A normal CDK CLI synth requires Lambda asset bundling. The sandbox could not
  reach package indexes or the Docker socket, while the isolated six-stack test
  synthesis passed. CI must complete the normal synth before acceptance.

## Boundary and next checkpoint

No AWS API, CloudFormation deployment, security service, KMS key, IAM policy,
API Gateway configuration, or SageMaker execution changed. Phase 1 remains
**implemented and awaiting review**, not complete. Review the uncommitted diff,
then run CI. Only after all CI jobs pass should Phase 1 receive its own commit
and completion entry. Phase 2 remains blocked until that checkpoint and the
Data-to-Serving export-removal problem has a reviewed remediation.
