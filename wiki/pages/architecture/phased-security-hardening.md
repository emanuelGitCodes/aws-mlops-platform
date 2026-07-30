---
type: architecture
title: Phased AWS security hardening roadmap
created: "2026-07-12"
updated: "2026-07-30"
sources: ["../../raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md", "../../raw/aws-security-hardening-phase-3e-implementation-and-deployment-july-24-2026.md", "../../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-3a-implementation-july-18-2026.md", "../../raw/aws-security-hardening-phase-3b-implementation-july-18-2026.md", "../../raw/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md", "../../raw/aws-free-plan-account-service-limits-july-18-2026.md", "../../raw/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md", "../../../infra/cdk.json", "../../../infra/security_checks.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py"]
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
| 3 | Access Analyzer and account S3 blocking done; Config and partial alert routing next; GuardDuty and Security Hub deferred behind the paid-plan upgrade gate | Enable one service at a time; each is healthy and credit burn remains acceptable. Revised July 19 for the AWS Free plan. |
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
- **Phase 2E: complete; observation open.** The `unauthorized-api-calls`
  alarm now requires three consecutive breaching five-minute datapoints
  (`EvaluationPeriods 3`, `DatapointsToAlarm 3`) after ten isolated-denial
  fire/auto-resolve cycles in three days — most from the security auditor's
  own correct least-privilege denials (issue 10). The gated deployment
  modified exactly one resource; filters, thresholds, and the other five
  alarms are unchanged, and the IAM fingerprint baseline passed unmodified.
  A companion out-of-band admin action granted the hand-managed auditor
  `logs:FilterLogEvents` on the audit log group plus encryption-context-scoped
  `kms:Decrypt`, closing the self-diagnosis gap; the `PutUserPolicy` paged
  `IamPolicyChanges` exactly once, live-proving that detection. See the
  [Phase 2E record](../sources/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md).
- **Phase 3-prep: complete.** Six all-false `security.services` enablement
  flags, an empty flag-gated `Mlops-Dev-SecurityMonitoring` stack
  (`CREATE_COMPLETE`, metadata only), and execution policy `v7` with the
  Phase 3 lifecycle actions plus scoped Config service-linked-role statements
  are live and hash-verified (`v6` retained for rollback). One flag flips per
  sub-phase (3A Access Analyzer → 3B GuardDuty → 3C Config → 3D Security Hub →
  3E account S3 Block Public Access → 3F EventBridge alert routing), each with
  its own commit, named deploy, and verification. See the
  [implementation](../sources/aws-security-hardening-phase-3-prep-implementation-july-14-2026.md)
  and
  [completion](../sources/aws-security-hardening-phase-3-prep-completion-july-14-2026.md)
  records.
- **Phase 3A: complete.** The dev account external-access analyzer is active
  with no archive rules or paid configuration. Its initial resource analysis
  completed with zero active public, cross-account, or error findings. The
  corrected execution policy is live as verified default `v8`, with `v7`
  retained for rollback and only the intended role attached. The named deploy,
  later-service checks, six security alarms, `/predict`, and the existing `$20`
  budget all passed. Production and all later Phase 3 flags remain disabled.
  See the
  [implementation record](../sources/aws-security-hardening-phase-3a-implementation-july-18-2026.md),
  [first deployment rollback](../sources/aws-security-hardening-phase-3a-first-deployment-rollback-july-18-2026.md),
  and [completion record](../sources/aws-security-hardening-phase-3a-completion-july-18-2026.md).
- **Phase 3B: deferred behind the paid-plan upgrade gate.** The dev-only
  foundational GuardDuty detector is locally validated with 15-minute
  publishing and every current optional paid feature explicitly disabled,
  including `AI_ANALYST`. Hosted gates passed and the named diff was exact, but
  the GuardDuty provider returned `SubscriptionRequiredException`. The stack,
  detector/role state, and execution policy rolled back cleanly. The root
  cause is confirmed: the account is on the AWS **Free account plan**, which
  blocks paid-only services such as GuardDuty (and Security Hub) at the
  billing level, so no retry can succeed before a paid-plan upgrade. The
  July 19 revision defers 3B and 3D behind an explicit manual upgrade
  decision; `dev.yaml` sets `guardduty: false`, the flag-gated detector code
  and its locked contract tests remain for the retry, and the repository
  execution policy deliberately retains the GuardDuty actions (live default
  `v8`) until the next sub-phase rotation. See the
  [implementation record](../sources/aws-security-hardening-phase-3b-implementation-july-18-2026.md),
  [first deployment rollback](../sources/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md),
  [Free-plan service limits](../sources/aws-free-plan-account-service-limits-july-18-2026.md),
  and the
  [Phase 3 plan revision](../sources/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md).
- **Phase 3E: complete; observation open.** Account-level S3 Block Public Access
  is live in dev with all four settings true, where the pre-flight recorded
  `NoSuchPublicAccessBlockConfiguration`. CloudFormation has no resource type for
  the account-level setting, so it is set through the `AwsCustomResource` pattern
  already proven by the Data stack's budget notifications, with `on_delete`
  restoring the pre-state so a failed phase rolls back cleanly. The deploy
  created four resources and modified nothing else; the analyzer, six alarms,
  bucket readability, and `/predict` all verified unchanged, and a subsequent
  diff reports none. No execution-policy rotation was needed, so the GuardDuty
  divergence and the last IAM version slot both survive for 3C. The phase also
  cleared the stack's leftover `UPDATE_ROLLBACK_COMPLETE` marker. See the
  [implementation and deployment record](../sources/aws-security-hardening-phase-3e-implementation-and-deployment-july-24-2026.md).
- **Phases 3C, 3F, and 4–9: not started.** No Config, Security Hub, Phase 3
  alert routing, KMS, API-authentication change, WAF, or identity change is
  deployed by this checkpoint. Under the July 19 revision the remaining Phase 3
  order is 3C Config (whose gated deployment doubles as the Free-plan
  availability test with minimally scoped recording), then partial 3F
  routing of Access Analyzer and Config events; full 3F follows the deferred
  services.

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
- The six Phase 3 service flags are a fixed configuration contract, but only
  the implemented subset may be enabled. `SecurityMonitoringStack` raises when
  a flag with no CDK behind it is set true, so a sub-phase cannot appear
  enabled in configuration while creating nothing in the account. A flag joins
  `IMPLEMENTED_SERVICE_FLAGS` in the same change that implements its
  sub-phase.
- The Phase 2C detection contract is a stable interface, and Phase 2E is the
  precedent for revising one: the change went through the full gated
  sub-phase — pre-flight baseline, tests, reviewed named diff, scoped
  deployment, resource-level verification, live checks, and an observation
  window — rather than a drive-by edit, exactly as the 07-24 finding
  required.

### Next checkpoint

The 3E observation window closed on 2026-07-30 with every criterion met:
access-log objects delivered on 07-28 and 07-30 after the deployment,
CloudTrail delivery advancing without error, the six security alarms still
`OK`, the analyzer still `ACTIVE` with zero active findings, and the `$20`
budget confirmed intact with its three 50/80/100 alerts unexceeded at
`$0.00` actual spend. Provenance was already settled: CloudTrail attributes
the single `PutAccountPublicAccessBlock` call to the provider role, not a
human. Sub-phase 3E is therefore clear for its go decision.

The Phase 2E observation window opened on 2026-07-30. It closes in a later
session once the `unauthorized-api-calls` alarm has stayed silent on routine
auditor activity with no missed sustained-burst detection, the six alarms
remain healthy, the auditor's audit-log read still works, and the `$20`
budget is unchanged. Issue 10 stays open until that closure.

Sub-phase 3C (AWS Config) follows the 3E go/no-go, and its gated deployment
doubles as the Free-plan availability test with minimally scoped recording.
It must also scope its cdk-nag acknowledgements with `requires_service`, as
3E established. Do not manually create a GuardDuty detector or role, and do
not complete the Config console wizard; Config availability on the Free plan
is tested only through the gated flag-controlled CloudFormation path.
Phases 3B and 3D wait for the explicit paid-plan upgrade decision, after
which each repeats its full pre-state gate, policy rotation, named diff and
deploy, and finding/trial/alarm/budget/`/predict` verification.

Related runtime and human authority boundaries are documented in
[AWS resource and permission boundaries](permissions.md) and
[CDK deployment identity and bootstrap boundary](cdk-deployment-iam.md).

## Tensions or open questions

- The account's AWS Free plan blocks GuardDuty and Security Hub until a
  paid-plan upgrade; that upgrade ends the cannot-be-charged guarantee and is
  an open billing decision, guarded by the Phase 2 budget alerts and alarms.
- AWS Config availability on the Free plan is unproven until the gated 3C
  deployment attempts the first recorder create; its recording scope must
  stay minimal because configuration items consume the remaining credits.
- The repository execution policy retains the GuardDuty actions while the
  live default is `v8`; this deliberate divergence reconciles at the next
  sub-phase's controlled rotation.
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
