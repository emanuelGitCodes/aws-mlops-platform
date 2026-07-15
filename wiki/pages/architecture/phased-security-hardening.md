---
type: architecture
title: Phased AWS security hardening roadmap
created: "2026-07-12"
updated: "2026-07-12"
sources: ["../../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-completion-july-12-2026.md", "../../../infra/cdk.json", "../../../infra/security_checks.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py"]
summary: "A gated, rollback-friendly roadmap for adding AWS audit, detection, encryption, least privilege, IAM API authentication, and WAF controls."
---
# Phased AWS security hardening roadmap

## Confirmed

The project already has useful storage and application controls: its ML data
buckets block public access, enforce TLS, use KMS encryption, retain versions,
and are not publicly readable. The proxy Lambda validates the request schema and
is scoped to invoke the configured SageMaker endpoint.

The approved July 12 plan treats the following as hardening gaps rather than
evidence that the existing dev platform is unsafe to study: account audit and
threat-detection services were not enabled at assessment time, API Gateway used
an API key as its access boundary, and the pipeline and model execution roles
used `AmazonSageMakerFullAccess`. The target is AWS Foundational Security Best
Practices for this workload, not formal SOC 2, HIPAA, or PCI DSS compliance.

The complete implementation details and acceptance criteria are preserved in
the [immutable planning source](../sources/phased-aws-security-hardening-plan-july-12-2026.md).

## Synthesis

### Operating rule

Every phase is a separate change set. Before moving forward, it must have a
baseline, tests, CDK synthesis, reviewed `cdk diff`, its own commit, a scoped dev
deployment, live checks, an observation window, a wiki log entry, and an explicit
go/no-go checkpoint. Production is not changed while this roadmap is being
validated in dev.

Retained S3 data, KMS keys, audit logs, model packages, and model artifacts are
never part of an automatic rollback. When a phase fails, revert only the most
recent behavior change and use its CloudTrail or CloudWatch evidence to diagnose
the boundary.

### Phase map

| Phase | Isolated change | Required checkpoint |
|---|---|---|
| 0 | Read-only baseline and rollback preparation | Existing ingestion, pipeline, endpoint, and API behavior are recorded and unchanged. |
| 1 | Repository and CI security guardrails | Tests, lint, synth, dependency scan, and secret scan pass without an AWS deployment. |
| 2 | CloudTrail, audit storage, SNS email, security alarms, and budget alerts | Trail is logging and a controlled alarm reaches the confirmed email. |
| 3 | Access Analyzer, GuardDuty, Config, Security Hub, and account S3 blocking | Enable one service at a time; each is healthy and cost remains acceptable. |
| 4A | Create the data KMS key and pre-grant roles | Every workload role passes controlled KMS access tests before bucket changes. |
| 4B | Change bucket encryption defaults | Migrate artifacts, curated, then raw; verify each bucket before continuing. |
| 4C | Re-encrypt existing objects and add lifecycle rules | Checksums, metadata, readability, key IDs, and retention are verified. |
| 5 | Replace broad IAM one role at a time | Proxy, model, deploy, then pipeline roles pass their component checks; a billable pipeline run succeeds. |
| 6 | Replace API keys with IAM/SigV4 | Signed authorized calls succeed; unsigned and unauthorized calls fail; response contract is unchanged. |
| 7 | TLS 1.2, API logs, metrics, tracing, and alarms | TLS and observability work without logging credentials or customer inputs. |
| 8 | WAF in count mode, then rule-by-rule blocking | Legitimate evaluation traffic passes and controlled malicious/rate traffic is blocked. |
| 9 | Identity Center, long-lived-key retirement, finding review, and final docs | Temporary access works before old keys are disabled; no high finding is unexplained. |

### Current phase status

- **Phase 0: complete.** The
  [read-only baseline](security-phase-0-baseline.md) records the working runtime,
  template and pipeline fingerprints, security gaps, costs, and rollback
  surfaces.
- **Phase 1: complete.** Locked dependencies, construct-scoped `cdk-nag` 3
  acknowledgements, IAM/S3 regression tests, dependency and secret scanning,
  current immutable action pins, and a manual-only deployment workflow are in
  place. The lock check, dependency audit, full-history and worktree secret
  scans, lint, 44 tests, and normal asset-bundling CDK synthesis pass. See the
  [completion record](../sources/aws-security-hardening-phase-1-completion-july-12-2026.md).
  CDK's existing producer-protecting cross-stack reference behavior is now
  explicitly locked to `strong`.
- **Phase 2A: complete.** The obsolete Data export is reconciled with a scoped
  Data-only deployment, and the repository-owned CloudFormation execution
  policy is installed as `v6`. Live and repository policy fingerprints match;
  `v5` remains the rollback version. See the
  [Phase 2A completion record](../sources/aws-security-hardening-phase-2a-completion-july-12-2026.md).
- **Phase 2B: complete.** The isolated Security audit foundation passed 47
  tests, cdk-nag, hosted CI, a reviewed Security-only diff, deployment, live
  CloudTrail delivery, first-digest validation, and confirmed SNS test email.
  See the [completion record](../sources/aws-security-hardening-phase-2b-completion-july-12-2026.md)
  and [audit architecture](security-phase-2-audit-foundation.md).
- **Phase 2C: complete.** Six exact Security Hub/CIS metric filters and
  five-minute SNS alarms passed 48 tests, hosted CI, a Security-only diff,
  deployment, live configuration checks, and a controlled denial that produced
  a received alarm email. See the
  [completion record](../sources/aws-security-hardening-phase-2c-completion-july-12-2026.md).
- **Phase 2D: complete; observation closed.** Raw, curated, and artifacts
  now log to the centralized sink, and the existing `$20` budget has exact
  50/80/100 SNS alerts. Bucket identities, object counts, budget identity,
  CloudTrail, filters, subscription, and `/predict` passed live checks. The
  observation window closed with the first `artifacts/` access-log object
  delivered, ~zero daily cost, and all alarm noise attributed to known
  principals. See the
  [completion record](../sources/aws-security-hardening-phase-2d-completion-july-12-2026.md)
  and the
  [Phase 3-prep record](../sources/aws-security-hardening-phase-3-prep-implementation-july-14-2026.md).
- **Phase 3-prep: implemented; deployment pending CI.** Six all-false
  `security.services` enablement flags, an empty flag-gated
  `Mlops-Dev-SecurityMonitoring` stack, and the Phase 3 execution-policy
  extension (lifecycle actions plus scoped Config service-linked-role
  statements) are in the repository. One flag flips per sub-phase
  (3A Access Analyzer → 3B GuardDuty → 3C Config → 3D Security Hub →
  3E account S3 Block Public Access → 3F EventBridge alert routing), each with
  its own commit, named deploy, and verification. See the
  [Phase 3-prep record](../sources/aws-security-hardening-phase-3-prep-implementation-july-14-2026.md).
- **Phases 3A–9: not started.** No Phase 3 threat-detection service,
  API-authentication change, WAF, or identity change is deployed yet.

### Stable interfaces and deliberate breakpoints

- The `/predict` JSON request, JSON response, and `score >= 0.50` churn rule do
  not change.
- S3 data and evaluation paths do not change.
- Phase 6 deliberately breaks the `x-api-key` calling convention. API tooling
  gains AWS profile/Region selection and signs requests with temporary
  credentials. There is no permanent legacy API-key route.
- Paid security services remain limited to `us-east-1` during dev. Production
  and multi-Region expansion require a later manual decision.
- WAF begins in count mode. Each managed rule moves to blocking independently
  after sampled legitimate requests are reviewed.

### Next checkpoint

Pass hosted CI for the Phase 3-prep commit, rotate the execution policy to
`v7` (keeping `v6` for rollback), deploy only the empty
`Mlops-Dev-SecurityMonitoring` shell, and record the completion. Sub-phase 3A
(IAM Access Analyzer) requires its own go decision afterward.

Related runtime and human authority boundaries are documented in
[AWS resource and permission boundaries](permissions.md) and
[CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md).

## Tensions or open questions

- The SNS alert destination requires an email value and manual subscription
  confirmation; no address is stored in this plan.
- Security-service, WAF, CloudWatch, CloudTrail data-event, and KMS usage charges
  must be observed after each phase against the existing dev budget.
- Phase 5 requires a billable pipeline run to prove that least-privilege access
  still supports the full ML workflow.
- Existing objects do not automatically adopt a new default KMS key. Phase 4C
  must preserve and verify object versions before lifecycle expiration.
- Disabling long-lived administrator credentials is intentionally last so the
  roadmap cannot lock the operator out before temporary access is proven.
