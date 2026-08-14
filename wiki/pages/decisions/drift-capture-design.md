---
type: decision
title: Drift capture design for a serverless endpoint
created: "2026-08-07"
updated: "2026-08-14"
sources: ["https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html", "https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor.html", "https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor-availability-change.html", "https://github.com/aws-samples/sample-aiops-on-amazon-sagemakerai/tree/main/monitoring", "../../../infra/stacks/monitoring_stack.py", "../../../src/monitoring/retrain_handler.py", "../../../src/serving/proxy_handler.py", "../../../src/serving/deploy_handler.py", "../../../src/common/drift.py", "../../../src/monitoring/drift_handler.py", "../../../infra/config/prod.yaml", "../concepts/closed-drift-loop.md", "../architecture/phased-security-hardening.md"]
summary: "Model Monitor is closed to new customers, so the deferred capture leg is rebuilt as a repository-owned drift job rather than restored; the serverless endpoint and its zero idle cost stay."
---
# Drift capture design for a serverless endpoint

## Confirmed

- **Serverless Inference excludes both halves of the original design.** The
  documented feature exclusions for Serverless Inference name data capture and
  Model Monitor separately, alongside GPUs, multi-model endpoints, VPC
  configuration, network isolation, multiple production variants, and inference
  pipelines. `src/serving/deploy_handler.py` already omits `DataCaptureConfig`
  for this reason. The exclusion is therefore not a gap to work around at the
  endpoint; it removes the endpoint as a capture source entirely.
- **A serverless endpoint cannot be converted back.** The same page records
  that a real-time endpoint cannot become serverless, and that the reverse
  conversion — serverless to real-time — cannot be rolled back once made. Any
  option that moves to provisioned inference is a one-way door for
  `churn-serverless-dev`.
- **Model Monitor is no longer open to new customers.** Every Model Monitor
  documentation page now carries the same notice: existing customers continue
  as normal, AWS continues security and availability investment, and no new
  features are planned. AWS names the replacement explicitly — the open-source
  SageMaker AI monitoring solutions in the `aws-samples` organization, built on
  Evidently AI and MLflow, combined with CloudWatch and QuickSight.
- **This platform has never been a Model Monitor customer.**
  `scripts/setup_monitor.py` exists and is correct, but its
  `create_monitoring_schedule` call has never run against `churn-serverless-dev`,
  because Model Monitor does not support that endpoint type. The README already
  instructs the reader not to run it. No `CreateMonitoringSchedule` call appears
  anywhere in this platform's history.
- **Model Monitor does support batch transform inputs.** It offers continuous
  monitoring against a real-time endpoint, continuous monitoring against a
  regularly running batch transform job, and on-schedule monitoring for
  asynchronous batch transform. A capture-format S3 prefix is therefore a
  legitimate Model Monitor input, independent of the endpoint type.
- **The retrain half of the loop is deployed and unused.**
  `infra/stacks/monitoring_stack.py` creates `DriftViolationRule` on the
  `SageMaker Model Monitor Execution Status Change` detail type, filtered to
  `MonitoringExecutionStatus: CompletedWithViolations` and a schedule name
  prefixed with the endpoint name. It invokes `RetrainTriggerFn`, which holds
  `sagemaker:StartPipelineExecution` on exactly one pipeline ARN.
  `retrain_handler.VIOLATION_STATUS` MUST equal the literal in the stack.
  `tests/unit/test_monitoring_stack.py` pins that agreement.
- **The original schedule was the budget event, not the endpoint.** The comment
  on `monitor.schedule_cron` in `infra/config/prod.yaml` already records it: an
  hourly Model Monitor schedule is a SageMaker processing job on `ml.m5.large`,
  roughly 720 jobs a month, and it dominates the `$20` budget. The serverless
  endpoint it would have monitored costs about nothing while idle.

## Synthesis

The decision was framed as a choice between proxy-side capture and provisioned
inference. The Model Monitor availability change collapses that framing: the
service both options were aiming at is closed to new customers, and this account
has no standing as an existing one. What follows evaluates all three options
against that constraint rather than around it.

### Option A — provisioned real-time endpoint with built-in capture

Restores the textbook architecture exactly: `DataCaptureConfig` on the endpoint,
a Model Monitor schedule against it, and the deployed EventBridge rule firing
unchanged.

Rejected, on three independent grounds. It surrenders the property the serving
decision was built on — scale to zero, no standing instance, about zero
idle cost — for a platform whose entire cost story is that property. It is a
one-way conversion on the deployed endpoint. And it still lands on Model
Monitor, so the onboarding gate below applies to it as much as to Option B.

### Option B — keep serverless, capture in Model Monitor's format, schedule against S3

The proxy writes request and response records to S3 in the capture format, and
a monitoring schedule reads that prefix as a batch input rather than an
endpoint input. This is the most attractive option on paper, because a genuine
Model Monitor execution still emits the status-change event, which means
`DriftViolationRule`, `RetrainTriggerFn`, and their pinned literal all keep
working with no change at all.

Rejected, because that attraction is exactly the exposure. It is the only
option whose value comes entirely from Model Monitor being available to this
account, and the account's standing is unproven. Even if a pre-flight proved
eligibility, the option builds the platform's newest component on a service
with no planned features — and then owes a second migration later. Deferring
to Option C now costs one EventBridge contract change; deferring to Option C
after building Option B costs that same change plus the capture-format work.

### Option C — keep serverless, capture to S3, own the drift job — recommended

The proxy writes each validated record and its score to a capture prefix. A
scheduled job in this repository compares a recent window against the training
baseline, and emits its own violation event when the comparison breaches a
threshold. `RetrainTriggerFn` reacts to that event instead of SageMaker's.

This is what AWS now recommends, arrived at from this platform's own
constraints rather than adopted on authority. It keeps the serverless endpoint
and its zero idle cost. It has no dependency on a closed service. It removes the
processing-job cost line entirely: the Telco dataset is small enough that a
window comparison fits inside a Lambda, so the schedule that was going to
dominate the `$20` budget as 720 `ml.m5.large` jobs a month costs about
nothing instead.

The cost is that drift statistics become repository-owned code with tests
behind them, and that the EventBridge contract changes. That contract change is
the real work in this option, and it is small and well-pinned.

### What Option C changed

Implemented on 2026-08-07, not yet deployed. The list below is what the change
set did, and the parenthetical notes record where the design met something it
had not anticipated.

- `src/serving/proxy_handler.py` writes the validated record and the returned
  score to the capture prefix. **The write MUST NOT fail a prediction.** The handler's current failure semantics are deliberate — every
  SageMaker error is mapped to a 503 or 502 with no operator detail leaked — and
  a capture failure is not a prediction failure.
- **Capture goes to S3 directly, not through the log group.** Routing it through
  `log_event` and a CloudWatch Logs subscription would be cheaper and would
  reuse the deployed one-JSON-line-per-event convention, but Phase 7's
  checkpoint in the [hardening roadmap](../architecture/phased-security-hardening.md)
  requires that observability work without logging customer inputs. A capture
  stream in the proxy's log group is precisely customer inputs in a log group.
  The two are incompatible, and the roadmap wins.
- The proxy execution role gains `s3:PutObject` on one capture prefix. This is
  an IAM change to the role Phase 5A scoped down to `sagemaker:InvokeEndpoint`
  plus its own log group, so it belongs in a change set that re-verifies that
  scoping rather than a drive-by grant.
- A new drift job under `src/monitoring/`, with **its own execution role**. This
  answers the Phase 5D follow-up about Model Monitor and the shared pipeline
  role. The new design never creates the shared-role condition.
- `infra/stacks/monitoring_stack.py` changes `DriftViolationRule` from the
  SageMaker detail type to the job's own event, and `retrain_handler` changes
  the status literal it matches. `tests/unit/test_monitoring_stack.py` pins the
  agreement between them, and it MUST move in the same change set.
- `scripts/setup_monitor.py` retires. `scripts/send_drift_traffic.py` survives
  unchanged: it drives the public API, and the API is still the capture source.
- The statistic is **PSI computed directly**, not Evidently. The open question
  below resolved on module size: `src/common/drift.py` is standard-library only,
  so the SageMaker processing image installs nothing extra for it and the Lambda
  bundle does not grow. Ten quantile bins per numeric column, a 0.2 per-column
  threshold, and a 0.3 drifted-column fraction.
- The **minimum-sample rule is `MIN_RECORDS`**, and a short window returns
  `skipped: insufficient_records` rather than a no-drift result. The two
  readings stay distinguishable in the log, which is the whole point of the
  rule.
- The baseline comes from the **train split alone**, not the whole curated
  dataset. Validation and test rows are data the model never learned.
- The drift job MUST derive the baseline statistics from the existing
  preprocess output of the pipeline. `src/common/features.py` stays the single
  source of the raw-value contract. The drift job MUST NOT re-implement the
  encoding or the column order to compute a distribution.

## Tensions or open questions

- **Existing-customer standing is unverified, and cheaply verifying it is not
  possible.** `list-monitoring-schedules` returning empty proves nothing about
  eligibility. The only conclusive test is a `CreateMonitoringSchedule` call,
  which is mutating. If anyone wants to reopen Option B, that pre-flight is its
  own gated step under the roadmap's operating rule — not a quick check.
- **Ground truth never arrives.** Churn labels are not observed after a
  prediction in this platform, so model-quality monitoring — accuracy, F1, AUC
  against reality — is unreachable by any of the three options. Only input data
  drift is achievable. The loop this closes detects that the traffic changed,
  never that the model got worse. Every description of the closed loop MUST
  state that limit, including the README.
- **An hourly schedule over near-zero traffic reports noise.** `schedule_cron`
  is hourly in both environments, which suited a job reading live production
  traffic. This platform's endpoint is idle most of the time, so most windows
  will hold few records or none. Without a minimum-sample rule the job either
  fires on noise or reports nothing and cannot distinguish that from healthy —
  the same defect class as `mlops-dev-endpoint-5xx` leaving `TreatMissingData`
  unset. The sample-size rule is part of the design, not a refinement of it.
- **Resolved: the drift statistic is PSI, computed directly.** Evidently AI's
  presets compute PSI and KS per feature, and Evidently is what AWS's
  replacement solutions use, but a direct implementation over the
  nineteen-column contract needs no dependency in either the Lambda bundle or
  the SageMaker processing image. KS is not implemented; only PSI is.
- **Binning is left-open, and that was a defect the tests caught.** A
  right-open bin puts a low-cardinality numeric column entirely in one bucket.
  `SeniorCitizen` holds 0 and 1, so its only quantile edge is `0.0`, and every
  shift in that column would have been invisible. `bucket_of` uses
  `bisect_left` for this reason.
- **Corrected 2026-08-07: the baseline does *not* reliably reset, and the
  retrain-storm protection claimed here does not exist.** The original claim
  was that every preprocessing run overwrites the fixed baseline key, so a
  rejected challenger resets it and a shift the model cannot beat stops firing
  every hour. The first drift-triggered retrain disproved it. `Preprocess` and
  `Train` are cached with `expire_after="P30D"`, and on unchanged curated data
  both were **cache hits of one second each**. A cached step does not re-run,
  so it wrote no baseline: the object still carries its original timestamp.

  The consequence is the opposite of the claim. While drifted traffic keeps
  arriving, the loop can retrain every hour, hit the cache, fail the AUC gate,
  and never move the reference it is measuring against. A cooldown after a
  retrain, or an uncached baseline refresh, is the fix. Neither is implemented.
- **Nothing is deployed.** This change set is code, tests, and documentation
  only. The loop has never run end to end in AWS, so `MIN_RECORDS`, the
  thresholds, and the hourly cadence are all unvalidated against real traffic.
- **The threshold conversation is separate.** The 0.50 cutoff and its
  `0.5370` recall, raised in the [closed drift loop](../concepts/closed-drift-loop.md),
  concern the classification rule rather than drift detection. Do not fold the
  two together.
