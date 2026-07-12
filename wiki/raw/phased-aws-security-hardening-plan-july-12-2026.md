# Phased AWS security hardening plan

Date: 2026-07-12

## Goal

Move the AWS MLOps platform from its current development baseline toward AWS
Foundational Security Best Practices without attempting every security change in
one deployment. Each phase must be implemented, tested, deployed, observed, and
accepted independently so failures remain attributable to a small change set.

This is an AWS best-practice hardening effort. It does not by itself establish
SOC 2, HIPAA, PCI DSS, or another formal compliance certification.

## Phase execution contract

For every phase:

1. Record the pre-change repository and AWS state.
2. Implement only that phase's changes.
3. Run unit tests, security checks, and CDK synthesis.
4. Review `cdk diff` and confirm that it contains only expected resources.
5. Commit the phase separately.
6. Deploy only the affected dev stack or resource group.
7. Run phase-specific live verification.
8. Observe logs, alarms, costs, and application health.
9. Record commands and results in the wiki deployment log.
10. Stop for review before beginning the next phase.

If a phase fails, roll back only that phase. Retained S3 buckets, KMS keys,
CloudTrail logs, model packages, and model artifacts must not be automatically
destroyed.

## Phase 0 — Baseline and recovery preparation

This phase is read-only.

- Capture the current IAM policies, S3 encryption, API configuration, AWS
  security-service status, costs, pipeline status, and endpoint health.
- Export current CloudFormation templates and the SageMaker pipeline definition.
- Verify the existing API-key request and normal S3 read paths.
- Document stack dependencies and rollback commands.
- Record the current disabled state of CloudTrail, GuardDuty, Security Hub, AWS
  Config, and IAM Access Analyzer.

Acceptance: the baseline is reproducible and ingestion, training, evaluation,
endpoint deployment, and API behavior remain unchanged.

## Phase 1 — Repository security guardrails

This phase changes the repository and CI only.

- Add CDK security assertions and `cdk-nag`.
- Add `pip-audit` dependency scanning and Gitleaks secret scanning.
- Install dependencies from the lockfile in frozen mode.
- Reject public buckets, missing encryption/TLS enforcement, and newly
  introduced unmanaged wildcard IAM permissions.
- Record existing IAM findings as temporary, justified suppressions and remove
  them during the least-privilege phase.

Acceptance: tests, lint, synthesis, dependency scanning, and secret scanning
pass without changing AWS.

## Phase 2 — Audit trail and notifications

- Add a dedicated security stack.
- Create a retained, rotating customer-managed audit KMS key.
- Create a private, versioned, TLS-only audit bucket.
- Enable a Multi-Region CloudTrail for management events with log-file
  validation and encrypted CloudWatch delivery.
- Create an encrypted SNS topic with a required email subscription.
- Detect root activity, authorization failures, IAM changes, CloudTrail
  modification, KMS disable/deletion attempts, and S3 policy changes.
- Add budget notifications at 50%, 80%, and 100% of the monthly budget.

Acceptance: CloudTrail is logging, a test event reaches CloudWatch, a test alarm
reaches the confirmed email, and the application remains healthy.

Rollback: disable the new trail and alarms while retaining the audit bucket,
logs, and KMS key.

## Phase 3 — Threat detection and configuration monitoring

Enable and verify these services one at a time in `us-east-1`:

1. IAM Access Analyzer.
2. GuardDuty.
3. AWS Config for workload resources and global IAM resources.
4. Security Hub CSPM with AWS Foundational Security Best Practices.
5. Account-level S3 Block Public Access.
6. EventBridge routing of high-severity findings to the Phase 2 SNS topic.

Do not enable additional Regions or Macie in the dev rollout.

Acceptance: every service is healthy, Config records a test change, findings
reach Security Hub, unexplained public/cross-account findings are absent, and
daily cost remains acceptable.

Rollback: disable only the service causing the problem; keep CloudTrail active.

## Phase 4 — Customer-managed data encryption

### Phase 4A — Create and pre-grant

- Create a retained, rotating customer-managed data KMS key with S3 Bucket Keys.
- Grant the existing ingestion, training, model, and deployment roles only their
  required key operations.
- Do not change bucket defaults until controlled KMS tests pass for every role.

### Phase 4B — Change bucket defaults individually

Migrate and verify in this order:

1. Artifacts bucket.
2. Curated bucket.
3. Raw bucket.

For each bucket, change the default KMS key, write and read a test object through
the real workload role, verify the KMS key ID, and rerun the dependent component.

### Phase 4C — Existing objects and retention

- Re-encrypt current object versions through controlled copies.
- Verify checksums, metadata, readability, and KMS key IDs before old versions
  expire.
- Retain noncurrent ML object versions for 90 days, evaluation artifacts for one
  year, and audit logs for 365 days.

Acceptance: active objects use the customer-managed key and the complete data,
pipeline, deployment, and inference paths still work.

## Phase 5 — IAM least privilege

Change and verify one role at a time:

1. Confirm the proxy Lambda can invoke only `churn-serverless-dev`.
2. Remove `AmazonSageMakerFullAccess` from the model execution role and grant
   only model-artifact, KMS, image-retrieval, and logging access.
3. Scope the deployment Lambda to `churn-model-group`, configured resource-name
   prefixes, and the exact model execution role for `iam:PassRole`.
4. Remove `AmazonSageMakerFullAccess` from the pipeline role and grant only the
   pipeline jobs, model group, images, logs, S3 prefixes, and KMS access it uses.

Actions that cannot use resource ARNs must live in isolated statements with
account, Region, naming, or tag conditions.

Acceptance: no workload role retains SageMaker full access; a billable dev
pipeline execution completes preprocessing, training, evaluation, gating,
registry action, and timestamped artifact output; the endpoint remains healthy.

Rollback: restore only the last role's previous policy and diagnose the matching
CloudTrail `AccessDenied` event.

## Phase 6 — IAM/SigV4 API authentication

- Update API evaluation and smoke-test clients to sign requests through the AWS
  credential chain, with optional `--profile` and `--region` arguments.
- Remove `API_KEY` and `--api-key` from scripts, tests, examples, and docs.
- Change `POST /predict` to API Gateway `AWS_IAM` authorization.
- Preserve the request/response schema and `score >= 0.50` decision rule.
- Keep stage throttling at 10 requests per second with a burst of 20.
- Use temporary credentials and GitHub OIDC for automation.
- Delete the API key and usage plan only after signed calls pass.

Acceptance: unsigned and invalidly signed calls return `403`, authorized callers
succeed, unauthorized IAM identities fail, and API evaluation results remain
unchanged.

This is an intentional breaking authentication change. A permanent legacy
API-key route will not be maintained.

## Phase 7 — API transport, logs, and tracing

- Require TLS 1.2.
- Enable API Gateway access logs, execution metrics, and X-Ray tracing.
- Retain application/API logs for 90 days in dev and 365 days in production.
- Exclude credentials, authorization headers, raw customer records, labels, and
  feature values from logs.
- Alarm on API 4XX/5XX responses, Lambda failures, and endpoint failures.

Acceptance: TLS 1.0 is rejected, TLS 1.2+ signed calls succeed, logs and traces
are produced without sensitive input, and test alarms reach email.

## Phase 8 — AWS WAF

- Associate an AWS WAFv2 web ACL with the API stage.
- Add AWS managed common, known-bad-input, and IP reputation protections.
- Add a per-IP rate rule of 1,000 requests per five minutes.
- Enable metrics and sampled requests without logging request bodies.
- Pace full-test-set API evaluation at no more than three requests per second.
- Deploy managed rules in count mode and promote each to block mode only after
  reviewing legitimate matches.

Acceptance: normal signed predictions pass, malformed traffic is blocked, the
representative evaluator is not throttled, and a controlled rate test triggers
the expected rule and alarm.

Rollback: return the problematic rule to count mode or detach the web ACL.

## Phase 9 — Operator identity and final review

- Configure IAM Identity Center for interactive administration.
- Validate temporary administrator and least-privilege deployment sessions.
- Verify root MFA and the absence of root access keys.
- Disable long-lived administrator/deployer keys only after temporary access is
  proven.
- Remediate or explicitly explain every critical/high Security Hub finding.
- Update operating documentation and complete the full dev acceptance suite.
- Produce a separate production rollout checklist; do not deploy production
  automatically.

## Interface changes

- `/predict` retains its JSON input/output and model threshold.
- Starting in Phase 6, `/predict` requires IAM/SigV4 and rejects `x-api-key`.
- API tooling gains `--profile` and `--region` and removes API-key arguments.
- Configuration gains a required alert email, service enablement flags,
  retention values, and a WAF rate threshold.
- CDK outputs expose audit, notification, WAF, and KMS ARNs without exposing
  credentials.
- Existing S3 data and evaluation paths remain unchanged.

## Overall completion criteria

- Every phase has its own commit, deployment record, verification result, and
  rollback point.
- CloudTrail, GuardDuty, Config, Security Hub, and Access Analyzer are healthy in
  `us-east-1`.
- Data buckets remain private and use the customer-managed data key.
- No runtime role retains SageMaker full-access policies.
- `/predict` requires IAM/SigV4, TLS 1.2+, and WAF inspection.
- Security alarms reach the confirmed email.
- The complete ingestion, pipeline, registry, deployment, evaluation-reporting,
  and signed API flow succeeds.
- No critical/high finding remains unexplained, and recurring security costs stay
  within the dev budget.

## Defaults and assumptions

- The target is AWS Foundational Security Best Practices, not formal compliance.
- Paid security services remain limited to `us-east-1` during dev.
- API callers are AWS identities using temporary credentials.
- Alerts use encrypted SNS email delivery.
- Production requires manual approval after all dev phases pass.
