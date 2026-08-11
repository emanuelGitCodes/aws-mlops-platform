---
type: architecture
title: Phased AWS security hardening roadmap
created: "2026-07-12"
updated: "2026-08-10"
sources: ["../../raw/aws-security-hardening-phase-5d-pipeline-execution-role-august-6-2026.md", "../../raw/aws-security-hardening-phase-5c-deploy-execution-role-august-5-2026.md", "../../raw/aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md", "../../raw/aws-security-hardening-phase-3e-implementation-and-deployment-july-24-2026.md", "../../raw/phased-aws-security-hardening-plan-july-12-2026.md", "../../raw/aws-security-hardening-phase-0-baseline-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-1-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2a-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-3a-implementation-july-18-2026.md", "../../raw/aws-security-hardening-phase-3b-implementation-july-18-2026.md", "../../raw/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md", "../../raw/aws-free-plan-account-service-limits-july-18-2026.md", "../../raw/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md", "../../../infra/cdk.json", "../../../infra/security_checks.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/data_stack.py", "../../../infra/stacks/training_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/monitoring_stack.py"]
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
| 3 | Access Analyzer, AWS Config, account S3 blocking, and alert routing live in dev; GuardDuty and Security Hub remain behind the paid-plan gate | Enable one service at a time; each is healthy and credit burn remains acceptable. Revised July 19 for the AWS Free plan. |
| 4A | Create the data KMS key and pre-grant roles | Every workload role passes controlled KMS access tests before bucket changes. |
| 4B | Change bucket encryption defaults | Migrate artifacts, curated, then raw; verify each bucket before continuing. |
| 4C | Re-encrypt existing objects and add lifecycle rules | Checksums, metadata, readability, key IDs, and retention are verified. |
| 5 | Replace broad IAM one role at a time — **complete** | Proxy, model, deploy, then pipeline roles pass their component checks; a billable pipeline run succeeds. All met by 2026-08-06. |
| 6 | Replace API keys with IAM/SigV4 — **deployed to dev; observation open** | Signed authorized calls succeed; unsigned and unauthorized calls fail; response contract is unchanged. |
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
- **Phase 2E: complete; observation closed as a go 2026-08-02.** The
  `unauthorized-api-calls`
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
- **Phase 2F: the 5xx half closed as a go. The silence half failed, was
  refixed, and its detection is now proved live.**
  `mlops-<env>-endpoint-5xx` now sets `TreatMissingData` to `NOT_BREACHING`.
  It defaulted to `missing` and read `INSUFFICIENT_DATA` while the serverless
  endpoint was idle. **The sub-phase took the second signal rather than
  accepting the limit**, because `NOT_BREACHING` reads `OK` both when the
  endpoint is idle and when it is silent. `mlops-<env>-endpoint-silent` carries
  that signal: `Invocations` `Sum` under 1, on an hourly period, over
  `monitor.silence_alarm_hours` periods. SageMaker publishes no `Invocations`
  datapoint for an idle hour rather than a zero. **The claim that `BREACHING`
  is therefore sufficient was wrong, and the window proved it.**

  **The window is configuration, not a constant, because the alarm is only
  meaningful where traffic is expected.** Dev has no traffic floor, so its
  window is 24 hours and an idle endpoint reaches `ALARM` there on its own.
  Prod is 6. Two consequences follow for anyone closing a later observation
  window. **Dev now has seven alarms, not six**, and `endpoint-silent` in
  `ALARM` there means "nobody called it", not a fault. The alarm also pages the
  same topic as the security alarms, so it is a standing noise source in that
  inbox.

  **The 5xx half passed.** The alarm left `INSUFFICIENT_DATA` 48 seconds after
  the deploy, with CloudWatch naming the cause — one missing datapoint `treated
  as [NonBreaching]` — and then held `OK` across 24 unbroken hours of an idle
  endpoint. Before 2F it read `INSUFFICIENT_DATA` for that whole period.

  **The silence half failed, and cannot fire as deployed.** After 25 hours with
  zero invocations the alarm was still `OK`, and its history held two entries
  in that span: the creation, and the initial `INSUFFICIENT_DATA → OK`. It had
  not re-evaluated once. Measured on the same window, the raw `Invocations`
  metric returns **0** datapoints with status `Complete`, while `FILL(m1, 0)`
  over the identical range returns **6 of 6**, all zero.

  **`TreatMissingData` decides how a gap counts inside an evaluation that
  already runs. It does not cause an evaluation to run.** A metric that
  publishes nothing produces no datapoint, nothing drives the alarm, and it
  holds its last state forever. The general rule for this platform: **an alarm
  over a sparse AWS metric needs `FILL`**, and `Invocations` on a serverless
  endpoint is the sparsest of them. Sub-phase 2G reached the same conclusion
  from the opposite direction, on a metric with occasional gaps rather than
  total silence.

  **The fix is deployed and proved itself in 44 seconds.** The alarm moved to a
  `FILL(m1, 0)` math expression, mirroring 2G, and went `OK → ALARM` at
  2026-08-09T17:39:14Z, 44 seconds after the stack update. CloudWatch reported
  `24 datapoints were less than the threshold`, listing filled zeros at 12:37,
  13:37, 14:37, 15:37, and 16:37. The SNS action executed. Same endpoint, same
  silence, same 24-hour window as the 25 hours that produced nothing — the only
  difference is `FILL`.

  **The clearing half is proved too.** One `/predict` call at 17:51Z returned
  `200`, and the alarm went `ALARM → OK` at 17:57:24Z on
  `1 datapoint [1.0] was not less than the threshold`. Fire and clear are both
  demonstrated, so this detector is fully exercised — unlike 3F's Config rule,
  which stays unproved by choice.
- **Phase 2G: merged 2026-08-08, deployed 2026-08-09 without a scoped change
  set of its own.** It reached the account as a dependency of the
  `Mlops-Dev-Monitoring` deploy, not by a deliberate `Mlops-Dev-Security`
  deploy. See the transitive-deploy entry in `wiki/log.md`: `cdk deploy
  <stack>` also deploys that stack's dependencies, and Monitoring depends on
  Security for the alert topic. The change was reviewed and tested before it
  landed; what it never got was its own window.
  `mlops-<env>-security-unauthorized-api-calls` evaluates `FILL(m1, 0)` over
  the metric-filter metric. `FILL` is metric math, so the alarm moves from a
  plain `cloudwatch.Metric` to a math expression, which rewrites the alarm
  resource rather than changing one property. The five sibling detections keep
  the plain form, gated by a `fill_missing` field that defaults to `False`, and
  a test asserts that exactly one alarm carries a `Metrics` array.

  **The premise was re-measured before the code was written, and it survived a
  correction.** Every metric filter already sets `default_value=0`, and has
  since Phase 2C on 2026-07-12 — before the 2E observation that produced this
  sub-phase. The metric is therefore dense in principle. It is not dense in
  fact: over the 24 hours to 2026-08-08T17:00Z the raw metric returned 283
  datapoints against 288 periods, and `FILL(m1, 0)` returned 288. **The
  `default_value` publishes a zero only for a period the log group received
  events in**, and CloudTrail delivers nothing in some five-minute periods. Five
  real gaps in a day, each one a place alarm evaluation can skip and reach back
  past.

  The correction this closes is narrow. The alarm reports its true positives
  correctly today and always did. What was imprecise is the claimed meaning of
  `3 of 3` under lagging delivery.

  Both sub-phases revise a detection contract, so both follow the Phase 2E
  gate in full: a pre-flight baseline of the live alarm state, tests, a
  reviewed named diff, its own commit, a scoped dev deploy, `make verify-deploy`
  at resource level, live checks, an observation window, and an explicit
  go/no-go. Each window must cover one idle period and one real fire, and must
  confirm that the other alarms, `/predict`, and the `$20` budget are
  unchanged. Neither sub-phase rotates the execution policy, so neither
  consumes an IAM version slot.
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
  and its locked contract tests remain for the retry. The execution policy no
  longer carries the GuardDuty actions, so the retry must add them to the
  extension policy recorded below. See the
  [implementation record](../sources/aws-security-hardening-phase-3b-implementation-july-18-2026.md),
  [first deployment rollback](../sources/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md),
  [Free-plan service limits](../sources/aws-free-plan-account-service-limits-july-18-2026.md),
  and the
  [Phase 3 plan revision](../sources/phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md).
- **Phase 3E: complete; observation closed as a go 2026-07-30.** Account-level
  S3 Block Public Access
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
- **Phase 3C: complete; observation closed.** AWS Config is live in dev with a
  ten-type recorder (`mlops-dev-recorder`, `recording=true`,
  `lastStatus=SUCCESS`) delivering 24-hour snapshots into the existing audit
  bucket under a `config/` prefix. The gated deployment doubled as the
  Free-plan availability test and **passed**: the Config API answers where
  GuardDuty still raises `SubscriptionRequiredException`. Recording is scoped
  to the resource classes the Phase 2C detections already alarm on, because
  Config bills per configuration item. Three defects were found on the way,
  two of them pre-existing: the Phase 3-prep service-linked-role grant used
  the non-existent `aws-service-linked-role` path (and its test pinned the
  same wrong value), Config needs `iam:PassRole` on that role, and the
  recorder and delivery channel are mutually dependent so neither may depend
  on the other. The execution policy rotated twice and is live as `v11` with
  the GuardDuty actions removed and the CloudFormation read-back grants added;
  `v5` was deleted to free a version slot and `v8` remains the
  rollback target. See the
  [implementation and deployment record](../sources/aws-security-hardening-phase-3c-implementation-and-deployment-august-3-2026.md).
- **Phase 5B: complete; observation closed as a go 2026-08-05.** The model
  execution role is off
  `AmazonSageMakerFullAccess` and off `grant_read_write`, which had let a hosted
  model write to and delete from the bucket its own artifacts come from. It now
  reads `s3:GetObject` under the training prefix, lists that one bucket, and
  writes to the endpoint's own log group. Deployed 2026-08-05T02:49Z as an
  **in-place** role update — the deployed `AWS::SageMaker::Model` pins the role
  ARN, so a replacement would have stranded the endpoint at its next cold start.
  The component check forced that cold start rather than trusting a warm
  `/predict`: re-approving the model package drove the registry → `DeployFn` →
  `UpdateEndpoint` path to `InService` on a new config, with fresh endpoint log
  streams and container metrics after it. ECR and `cloudwatch:PutMetricData` were
  deliberately not granted — 90 days of CloudTrail record no ECR call, the image
  is first-party, and container metrics still publish — so the policy contains no
  `Resource: "*"` at all. Acknowledgements fell 45 → 40. The window then closed
  on a **natural** cold start: after twenty hours idle the endpoint scaled to
  zero, and an ordinary smoke run built a fresh container that served correctly,
  with no operator action in the loop.
- **Phase 5C: complete; observation closed as a go 2026-08-06 on 5D's run.**
  Rather than sit idle, 5C's window closed on strictly better evidence: 5D's
  successful pipeline run registered a model package, auto-approval fired, and
  the endpoint went to `Updating` **six seconds later** — the full
  registry-approval → `DeployFn` → `UpdateEndpoint` path under the 5C role,
  with no operator in the loop. The deploy role is off `AmazonSageMakerFullAccess`'s Lambda
  equivalent — `AWSLambdaBasicExecutionRole` — and off the six-action
  `Resource: "*"` SageMaker statement recorded in Phase 0, which let the role
  that reacts to a registry approval point any endpoint in the account at any
  model. Each action now names what `deploy_handler` builds: the endpoint's own
  generated model and endpoint-config names, the one endpoint, and model
  packages under this platform's own group. That last scoping is the one that
  matters — the package ARN arrives in the EventBridge detail, so pinning it to
  our group stops a crafted event walking the Lambda onto a foreign package.
  **The repository's last real literal wildcard is gone**; only Phase 3E's
  account-level Block Public Access remains, where AWS accepts nothing else.
  Deployed 2026-08-05T23:58Z as a one-for-one role replacement, safe here
  because nothing pins this role's ARN. The component check was a full
  end-to-end run rather than a warm `/predict`, which exercises the proxy and
  says nothing about this role: 1,200 new customer rows went raw → validate →
  curated → preprocess → train → evaluate → register, the auto-approval fired
  `DeployFn`, and it logged `approved_challenger_deployed` with no
  `AccessDenied`. That run also settled the one scoping guess static analysis
  could not: `CreateModel` needs **no** permission on the model package named in
  `Containers[]`, so the deliberate omission was correct. Acknowledgements rose
  40 → 41, two coarse entries traded for three naming exact ARNs. See the
  [Phase 5C record](../sources/aws-security-hardening-phase-5c-deploy-execution-role-august-5-2026.md).
- **Phase 5D: complete; observation closed as a go 2026-08-06. Phase 5 closes
  here.** The window ran about 21 hours from the first deploy and recorded
  **zero `AccessDenied` under the new policy** — the only errors in the role's
  CloudTrail are the expected `ResourceAlreadyExistsException` on
  `logs:CreateLogGroup`. Six alarms `OK`, `iam-policy-changes` self-cleared
  eight minutes after the last deploy, endpoint `InService` and unmodified,
  `$20` budget intact at `$0.00` actual against a `$1.11` forecast, hosted CI
  green. The pipeline execution role is off `AmazonSageMakerFullAccess`
  — the last attachment in the repository — and off the two CDK bucket grants
  that gave it delete rights over the whole artifacts bucket. Nine statements
  name what a run touches: `telco/` on curated; the four artifacts prefixes;
  `pipelines-*` processing and training jobs; this environment's own model
  package group; the two SageMaker job log groups; and `PassRole` on itself,
  conditioned to `sagemaker.amazonaws.com`. Scoping the curated read to
  `telco/` is a narrowing rather than tidier IAM — `InputDataUri` is a pipeline
  *parameter*, so a crafted `StartPipelineExecution` could otherwise train the
  model on data of the caller's choosing. Updated **in place**: the deployed
  pipeline definition is upserted out of band with `--role-arn` and
  `scripts/setup_monitor.py` takes the same ARN, and the template diff confirms
  exactly two resources changed with none added, removed, or renamed.

  The phase's real finding is about method. `sagemaker:AddTags` appears
  **nowhere** in CloudTrail for this role, and that absence is genuine but
  misleading: Pipelines tags each resource it creates *inside* the create call,
  so the authorization check never surfaces as its own event. Two successive
  runs failed on it — first the processing job, then the model package group —
  before all four create statements carried it. Static analysis had the API
  surface right and the *authorization* surface wrong, which is the strongest
  case yet for the operating rule's insistence on a live component check.

  Two further calls were granted for a related reason: `logs:CreateLogGroup`
  and `sagemaker:CreateModelPackageGroup` are both called unconditionally and
  both return a *service* error today (`ResourceAlreadyExistsException`,
  `ValidationException`) — success paths only while the permission exists.
  Deliberately not granted, each checked against that same baseline: ECR (5B's
  live precedent), `kms:` (see below), `cloudwatch:PutMetricData`,
  `s3:DeleteObject*`, and the lineage calls CloudTrail attributes to
  `sagemaker.amazonaws.com` itself. The **KMS question is now settled
  positively**: the role makes 39 `GenerateDataKey`/`Decrypt` calls per run and
  succeeds while holding no KMS permission at all, so the AWS-managed `aws/s3`
  key policy is what authorizes it. Acknowledgements rose 41 → 43, eight coarse
  training entries traded for ten naming a single prefix, job pattern, or log
  group. Coverage floor 92.57 → 92.63. See the
  [Phase 5D record](../sources/aws-security-hardening-phase-5d-pipeline-execution-role-august-6-2026.md).
- **Phase 5: complete. All four roles converted, 5A–5D, 2026-08-05 → 08-06.**
  The phase converted
  four roles one at a time — proxy, model, deploy, then pipeline. No role
  attaches `AmazonSageMakerFullAccess` any more, and the only wildcard resource
  the repository writes is Phase 3E's account-level Block Public Access, where
  AWS accepts nothing else. `AWSLambdaBasicExecutionRole` is separate residue
  and is **not** finished: 5A and 5C took the proxy and deploy Lambdas off it,
  but `ValidateFn`, `RetrainTriggerFn`, and the CDK provider Lambdas still
  carry it, each with its own acknowledgement. **5A took the proxy off
  `AWSLambdaBasicExecutionRole`**, whose three log actions
  applied to `Resource: "*"`. Its replacement role carries no managed policy and
  grants writes to the function's own log group plus the single
  `sagemaker:InvokeEndpoint` it already had. Deployed 2026-08-05T01:29Z as a
  one-for-one role replacement; `/predict` and the proxy's log delivery both
  verified live, and acknowledgements fell 46 → 45. `least_privilege_logs` is
  opt-in so DeployFn, RetrainTriggerFn and ValidateFn keep the managed policy
  until their own change sets. Its window closed on 5B's evidence: the record's
  one open gap was that nothing showed the proxy logging over a period or during
  an endpoint update, and 5B supplied both. See the
  [Phase 5A record](../sources/aws-security-hardening-phase-5a-proxy-execution-role-august-5-2026.md).
- **Phase 3F: partial, deployed to dev 2026-08-08, observation closed as a
  go.** Two
  EventBridge rules route active external-access findings and Config history
  or snapshot delivery failures to the Phase 2 alert topic. The audit key and
  the topic each grant `events.amazonaws.com`, scoped to the
  `mlops-<env>-security-*` rule prefix. The execution policy needed no
  rotation, so both freed version slots stay banked. Configuration item
  changes and compliance events are deliberately unrouted. **The analyzer rule
  is proved live**: a manufactured public-access finding routed to the topic
  with `FailedInvocations` 0, which proves the topic grant and the key grant
  together. The Config rule never fired, but it was **observed staying silent
  through a healthy delivery**, which is the negative half of its contract.
  See the
  [Phase 3F record](../sources/aws-security-hardening-phase-3f-alert-routing-august-8-2026.md).
- **Phase 6: deployed to dev 2026-08-09, observation open.** `POST /predict` takes
  `AWS_IAM` authorization. The caller signs with SigV4 and needs
  `execute-api:Invoke` on the method, so an unsigned call fails at API Gateway
  and never reaches the proxy Lambda. `evaluate_api.py` and
  `send_drift_traffic.py` sign with botocore `SigV4Auth` and keep their urllib
  transport, so no dependency arrives; both take `--profile` and `--region` in
  place of `--api-key`.

  **The response contract is unchanged, and the reason is structural.** The
  proxy reads one field from the event, `event.get("body")`, and composes every
  response itself. Under `AWS_PROXY` integration API Gateway returns that dict
  verbatim, so 200, 400, 422, 502, and 503 are byte-identical. Only API
  Gateway's own auth-failure bodies differ.

  **Deleting the API key removes the throttle unless the change moves it.** The
  usage plan carried rate 10 and burst 20 and existed only to hold the key. The
  limits move to the stage in the same change set, and a test pins both the
  stage values and the absence of the key and the plan.

  `execute-api:Invoke` authorizes the caller at request time, not CloudFormation
  at deploy time, so it never belongs in the execution policy. That policy
  already grants every `apigateway:` action this deploy needs. **Phase 6 spends
  no IAM policy version slot.**

  **The live boundary moved, and the throttle survived it.** The method reports
  `AWS_IAM` with `apiKeyRequired: false`; the account holds **zero** API keys
  and **zero** usage plans; the stage carries rate 10 and burst 20. An unsigned
  call returns `403 {"message":"Forbidden"}` and a signed one returns `200`.
  `make smoke` passes 6 while signing each request. The usage plan existed only
  to hold the key, so deleting the key without moving the limits would have
  dropped the throttle silently — this is the trap the phase carried, and the
  stage settings are the evidence it did not fire.

  **A 403 immediately after this deploy is expected.** The first `make smoke`
  failed all four signed tests, and a hand-signed call failed too, then
  succeeded about a minute later with nothing changed. The stage was already
  serving the newest deployment, so the configuration was correct and the API
  Gateway edge had not caught up. Switching a method's authorization type
  propagates on its own schedule. Do not read an immediate 403 as a failed
  deployment.
- **Phases 4 and 7–9: not started.** No Security Hub, KMS data-key work, WAF,
  or identity change is deployed by this checkpoint. Full 3F — GuardDuty and
  Security Hub findings — follows the deferred services.

### Stable interfaces and deliberate breakpoints

- The `/predict` JSON request, JSON response, and `score >= 0.50` churn rule do
  not change.
- S3 data and evaluation paths do not change.
- Phase 6 breaks the `x-api-key` calling convention. API tooling takes AWS
  profile and Region selection and signs requests with temporary credentials.
  There is no permanent legacy API-key route. The break is merged and reaches
  callers at the Serving deploy, not at the merge.
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
- **The analyzer has zero unexpected active findings.** The CI deploy role is
  assumable by GitHub's OIDC provider, so the analyzer reports it as external
  access on every recreation. `ArchiveCiDeployRoleFederation` matches that one
  role ARN and automatically archives new matching findings. The rule deployed
  to dev on 2026-08-09 after the execution-policy extension moved to `v2` with
  its exact lifecycle actions. Resource-level verification reports only
  `ExternalAccessAnalyzer` changed. `apply-archive-rule` archived the existing
  finding once, so the active count is zero and any other external access still
  reports. Earlier windows recorded "zero active findings" against an account
  that had no federated role; read those against their own date.
  Access Analyzer does not treat the role's OIDC claim conditions as access
  restrictions, so a finding for it carries `condition: {}` — that is the
  analyzer's blind spot, not a loose trust.
- The Phase 2C detection contract is a stable interface, and Phase 2E is the
  precedent for revising one: the change went through the full gated
  sub-phase — pre-flight baseline, tests, reviewed named diff, scoped
  deployment, resource-level verification, live checks, and an observation
  window — rather than a drive-by edit, exactly as the 07-24 finding
  required. Sub-phases 2F and 2G used that precedent and closed as a go.

### Next checkpoint

The 3E observation window closed on 2026-07-30 with every criterion met:
access-log objects delivered on 07-28 and 07-30 after the deployment,
CloudTrail delivery advancing without error, the six security alarms still
`OK`, the analyzer still `ACTIVE` with zero active findings, and the `$20`
budget confirmed intact with its three 50/80/100 alerts unexceeded at
`$0.00` actual spend. Provenance was already settled: CloudTrail attributes
the single `PutAccountPublicAccessBlock` call to the provider role, not a
human. Sub-phase 3E is therefore clear for its go decision.

The Phase 2E observation window opened on 2026-07-30 and closed on
2026-08-02 with every criterion met: no `unauthorized-api-calls` fire across
114 isolated denial events in roughly 50 hours, a longest run of only two
consecutive breaching periods so no sustained burst went undetected, the six
alarms `OK`, the auditor's audit-log read working, and the `$20` budget
intact at `$0.00` actual spend. The positive half of the claim was proven by
a deliberate synthetic burst on 2026-08-02 (73 denied read-only calls,
02:30:50Z–02:55:59Z) which fired the 3-of-3 alarm at 02:42:14Z, delivered its
SNS email, and self-cleared at ~03:03Z.

Two corrections came out of that closure. The 2026-07-31T00:13Z fire recorded
as the first 3-of-3 true positive was a late-datapoint artifact, not a
sustained burst — CloudWatch reached back past an undelivered datapoint to
assemble three. Consequently `3 of 3` does not strictly mean fifteen
consecutive minutes under lagging delivery; closing that edge with a metric
`Fill` is a detection-contract change, and it is now open as sub-phase 2G.

Sub-phase 3C's observation window **closed on 2026-08-05 as a go**, roughly 48
hours after deployment, with all four criteria met: snapshots delivered on
2026-08-03 and 2026-08-04 plus a refreshed writability check — the first real
writes to exercise the audit bucket policy and its KMS grant — AWS Config cost
at `$0.00` through 2026-08-04, the six alarms `OK`, and the `$20` budget intact
at `$0.00` actual against a `$1.156` account-wide forecast.

The window also corrected a claim. **The inclusion list governs ongoing
recording, not initial discovery**: the recorder's first day delivered 40
`ConfigHistory` objects for types it was never configured for, alongside 10
in-scope ones, and none since. The recorder was never modified. The cost effect
is a bounded one-off rather than a recurring one, but "minimally scoped" should
not be read as "nothing outside the ten types was ever recorded".

Phase 5 ran **two observation windows at once**, and both **closed on
2026-08-05 as a go**. 5B was the step up in risk the 5A record predicted — a
wrong scope there breaks inference rather than logging, invisibly to a smoke
test that only asserts `/predict` returns 200 — and it was answered by forcing a
cold container start through the registry-approval path instead of trusting the
warm response. That same forced `UpdateEndpoint` supplied the endpoint-update
evidence 5A's window was still missing.

A single later check closed both, because both were short the same thing: a
**natural** cold start. After twenty hours idle the serverless endpoint had
scaled to zero, and an ordinary `make smoke` built a fresh container — new
endpoint log stream, 6 passed — under the least-privilege role with no operator
action in the loop. In the twenty hours since deployment no denial was recorded
under either the model or the proxy role; the nineteen that were recorded all
belong to AWS service-linked roles probing services the account does not use,
and were spread thinly enough that the Phase 2E three-datapoint rule never
assembled a page from them.

That closure also recorded a gap it deliberately did not fix.
**`mlops-dev-endpoint-5xx` leaves `TreatMissingData` unset**, so it defaults to
`missing` and sits in `INSUFFICIENT_DATA` whenever the endpoint is idle — most of
the time, on a serverless endpoint — while the six security alarms all set
`notBreaching`. The inference tripwire therefore cannot distinguish "healthy and
idle" from "not reporting". Changing it is a detection-contract change, so under
the Phase 2E precedent it takes its own gated sub-phase, now open as 2F.

5C (`DeployFn`) landed on 2026-08-06 and took both its managed log policy and
its `Resource: "*"` SageMaker statement in one change set, leaving Phase 3E's
account-level Block Public Access as the only literal wildcard the repository
writes.

**5D landed the same day and closed Phase 5.** Its component check was a full
pipeline run under the new role, and it took three attempts to pass — the two
failures are the phase's most useful output. Both were `sagemaker:AddTags`,
which appears nowhere in CloudTrail for this role because Pipelines tags each
resource *inside* the create call, so the authorization check never becomes an
event. The first run failed on the processing job, the second on the model
package group, and only the third had all four create statements carrying it.

That generalises past this phase: **CloudTrail enumerates a role's API surface,
not its authorization surface.** Implicit tagging, and any other permission
checked as part of another call, is invisible to it. A least-privilege change
set derived from trail evidence alone should expect exactly this class of
failure, which is the argument for the component check being a real workload
run rather than a smoke test. The corollary also held: `logs:CreateLogGroup`
and `sagemaker:CreateModelPackageGroup` both come back as *service* errors
today, and that is a success path only while the permission exists.

The third run then closed 5C's window as a side effect — model package
registered, auto-approved, endpoint `Updating` six seconds later.

Three findings came out of 5C that belong to other change sets. **Seven orphaned
log groups** survive in dev, and every platform Lambda has a superseded
`/aws/lambda/<function>` twin beside its Phase K `*Logs*` group.

**The third 5C finding is withdrawn.** It claimed the bundled Lambda asset hash
was not reproducible, because vendored `__pycache__/*.pyc` embed mtimes that
`pip install -t` rewrites, so a cold `cdk.out` republished all four functions
with no source change. A measurement on 2026-08-08 refutes it. Two builds into
fresh output directories produce identical asset hashes. Deleting every
`src/**/__pycache__` does not move the hash, and neither does adding a stray
top-level file, so both the exclusion and the allowlist work. Six historical
`src/` states each rebuild to their own stable hash.

The finding mistook the hash input. **CDK fingerprints the source directory,
not the bundled output.** The `.pyc` files do differ between builds — that part
was right — but they live only in the output, so they never reach the hash. The
practical effect is the reverse of the one recorded: two builds produce the same
S3 key with different bytes inside, and the first upload wins. That is a byte
reproducibility gap, not a spurious-republish one.

The third 5C finding no longer holds. **The drift → retrain edge fired for the
first time on 2026-08-08 at 02:00:40Z.** A `drift_violation` over 200 captured
records (`tenure`, `MonthlyCharges`, and `TotalCharges` at PSI ≈ 12.4) produced
`retrain_started`, and pipeline execution `<pipeline-execution-id>` reached `Succeeded`.
The challenger scored 0.8535 test AUC against the champion's 0.8679 and was
rejected, so the champion stands. A second violation at 02:11:07Z logged
`retrain_suppressed` on the six-hour cooldown. The closing edge of the drift
loop, the promotion gate, and the retrain throttle are all now exercised in
this account. Only the superseded `/aws/lambda/RetrainTriggerFn` twin still
reports no events; the Phase K `*Logs*` group holds the run.

**Partial 3F's observation window closed on 2026-08-08 as a go**, about eleven
hours after the `Mlops-Dev-SecurityMonitoring` update completed at 04:00:37Z.
Every criterion was met: both rules `ENABLED`, the analyzer rule at
`MatchedEvents` 1 / `Invocations` 1 / `FailedInvocations` 0, the Config rule at
0/0/0, the topic at four published and four delivered with
`NumberOfNotificationsFailed` 0, the recorder `recording: true` and
`lastStatus: SUCCESS`, the analyzer `ACTIVE` with zero active findings, the six
security alarms `OK`, `make smoke` at 6 passed, month-to-date cost at `$0.00`,
and the `$20` budget intact at `$0.00` actual against a `$1.823` forecast.

**That window is shorter than the 48-hour precedent, and the reason it still
closes is that its load-bearing proof does not accumulate over time.** The risk
3F carried was that the two new grants — the topic policy and the audit key —
would fail at the moment a rule tried to publish. `FailedInvocations` 0 on a
real routed finding settles that in one event. A longer window would have added
cost data the budget already reports as zero.

**The Config rule gained its negative half.** A Config history delivery
succeeded at 11:47Z, inside the window and after the rules went live, and the
rule recorded no match against it. So the rule is now known to stay silent
through a healthy delivery, which is not the same as knowing it fires on a
broken one. Snapshot delivery is on a 24-hour frequency and its last success
predates the deploy, so no post-deploy snapshot was observed.

**The analyzer finding resolved on its own**, at 13:19:35Z, which settles the
open question about short-lived `ACTIVE` findings for deleted resources. The
rule's match count stayed at 1 across that transition. Read that as consistent
with the pattern's `status ACTIVE` predicate rather than as proof of filtering:
metrics cannot show whether a resolution event was emitted and rejected, or
never emitted at all.

Two constraints continue past it. First, **the main execution policy is out of
room, and the constraint is size rather than version slots.** This roadmap has
tracked slots since Phase 2A: `v6` and `v7` were deleted on 2026-08-07, leaving
`v8`, `v10`, and the default `v11` in three of five. That count is still
correct and no longer the binding limit. A rotation attempted on 2026-08-08
failed with `LimitExceeded: Cannot exceed quota for PolicySize: 6144`.

| Document | Bytes |
|---|---|
| Live `v11`, seven statements | 5888 |
| Live plus one OIDC statement | 6337 |
| AWS quota | 6144 |

**Read "two grants fit" as withdrawn.** The main policy carries 256 bytes of
headroom, and a single eight-action statement needs 448. No grant fits that
document. `MLOpsCloudFormationExecutionPolicyExtension` resolved this on
2026-08-08 and holds the overflow at 492 of 6144 bytes. The next phase to need
a grant — Phase 4's KMS actions, or Security Hub's return at 3D — adds it
there. The version slots are a real limit that has simply not been the first
one reached. The 2026-08-08 `wiki/log.md` entry holds the per-statement sizes.

Second, expect the `iam-policy-changes` and `unauthorized-api-calls`
alarms to fire during a gated deploy; 3C produced six such emails, all true
positives on its own work.
**Sub-phases 2F and 2G are deployed and closed as a go.** Phase 6 is deployed
to dev with its observation window open. `POST /predict` requires `AWS_IAM`,
the account has no API key or usage plan, and `make smoke` signs each request.

The next checkpoint closes the Phase 6 observation window. CI/CD activation is
separate: both environments allow only `main`, and dev holds its role ARN as an
environment secret. The manual workflow still needs its first run.

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
  As of 2026-08-02 the GuardDuty half of that decision is no longer only a
  billing block: measured against this account's own event volume the service
  would cost about a dollar a month, and it is **approved in principle**,
  waiting on a workload trigger rather than on price. See
  [paid Phase 3 security services](../decisions/phase-3-paid-security-services.md).
- ~~The repository execution policy retains the GuardDuty actions.~~ **Closed
  and stale.** The policy holds zero `guardduty:` actions today, and the live
  default is `v11`, not `v8`. Enabling GuardDuty therefore needs its actions
  added, not reconciled — and they belong in the extension policy, because the
  main document has no room.
- ~~The execution policy has no room for another grant.~~ **Closed on
  2026-08-08 by the split.** Size, not version slots, was the limit: the main
  document holds 5888 of 6144 bytes, with 256 free. The two alternatives costed
  in the 2026-08-08 log entry — trim the new statement, or drop the ten unused
  `securityhub:` actions — left two bytes and 123 bytes, so each bought one
  deploy and re-raised the failure at the next phase.
  `MLOpsCloudFormationExecutionPolicyExtension` now carries the overflow at 492
  of 6144 bytes, and attaches to the same `cdk-hnb659fds-cfn-exec-role-*`, so
  the grants union. **Add every new grant to the extension; the main document
  cannot take one.** `make test` measures both documents against the quota and
  rejects a `Sid` reused across the two files.
- ~~The account has no GitHub OIDC provider and no role trusting GitHub.~~
  **Closed on 2026-08-09.** `CicdStack` is deployed: the provider exists and
  `${GITHUB_DEPLOY_ROLE_NAME}` carries the four-claim trust. Dev and prod GitHub
  environments allow only `main`, and dev holds `AWS_DEV_DEPLOY_ROLE_ARN`.
  **The workflow still has not run.** Prod has no role ARN until its stack is
  deployed. Required environment reviewers remain unavailable while the
  repository uses its current private-repository plan. Every deployment to
  date still came from a workstation.
- **Production has never been deployed.** Nine stacks exist, all
  `Mlops-Dev-*`. The two-environment design is proven at synthesis only, which
  means the shared-account collisions this page warns about — the model package
  group, the account budget, and now the OIDC provider — have never been tested
  against a live second environment.
- **`${AWS_SECURITY_AUDITOR_USER_NAME}` cannot read budgets.** `budgets:ViewBudget` is
  denied for that identity, exposed when 5D's observation window tried to check
  the budget and had to fall back to `${AWS_ADMIN_USER_NAME}`. Every prior window reported
  budget state, so each one quietly did the same — the auditor is meant to be
  the identity that closes a window without administrator access, and on this
  one criterion it never was. Phase 2E is the precedent for the fix: an
  out-of-band grant of exactly the read required, in its own gated step.
- The SNS alert destination requires an email value and manual subscription
  confirmation; no address is stored in this plan.
- Security-service, WAF, CloudWatch, CloudTrail data-event, and KMS usage charges
  must be observed after each phase against the existing dev budget.
- Phase 5 required a billable pipeline run to prove that least-privilege access
  still supports the full ML workflow. **Closed on 2026-08-06.** 5C's run
  supplied the baseline under the unchanged role; 5D's third run supplied the
  proof, reaching `Succeeded` on all five steps under the scoped role and
  driving the registry → deploy → endpoint path behind it.
- The 5D follow-up about Model Monitor sharing the pipeline role is closed.
  Model Monitor is no longer part of the platform, and the drift loop that
  replaced it has its own execution role. See
  [drift capture design](../decisions/drift-capture-design.md).
- Existing objects do not automatically adopt a new default KMS key. Phase 4C
  must preserve and verify object versions before lifecycle expiration.
- Disabling long-lived administrator credentials is intentionally last so the
  roadmap cannot lock the operator out before temporary access is proven.
