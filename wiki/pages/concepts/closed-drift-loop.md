---
type: concept
title: Closed drift-to-retrain loop
created: "2026-07-10"
updated: "2026-09-05"
sources: ["../../log.md", "../decisions/drift-capture-design.md", "../../../README.md", "../../../infra/stacks/monitoring_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/security_stack.py", "../../../src/common/drift.py", "../../../src/common/registry.py", "../../../src/monitoring/drift_handler.py", "../../../src/monitoring/retrain_handler.py", "../../../src/serving/deploy_handler.py", "../../../src/serving/proxy_handler.py", "../../../src/pipeline/pipeline.py", "../../../src/pipeline/evaluate.py", "../../../src/pipeline/preprocess.py", "../../../scripts/evaluate_api.py"]
summary: "A repository-owned drift loop captures live inputs, compares models on common held-out rows, binds baselines to the serving package, and gates promotion."
---
# Closed drift-to-retrain loop

## Confirmed

The proxy Lambda writes each validated request and score to an hour-partitioned
S3 capture prefix. The preprocessing step writes one baseline per pipeline
execution under `monitor/baselines/<pipeline-execution-id>/baseline.json`. Model
registration stores that URI as `baseline_uri` metadata.

The drift Lambda resolves the endpoint's current endpoint configuration, model,
and model package. It reads the baseline named by that package. It accepts only
the artifacts bucket and the versioned baseline prefix. It validates the
baseline before scoring. A missing or invalid package URI fails closed.

The Lambda skips an endpoint that is not `InService`. It checks the endpoint
status and endpoint configuration again after comparison. A configuration
change discards the result. A result carries the endpoint configuration, model,
model package, and baseline URI that produced it.

The pipeline evaluates the challenger and the current champion on the same
held-out rows. `Evaluate` loads the latest approved package named by the current
execution when that step runs. The `ConditionStep` reads the champion AUC
computed by that evaluation. The retrain Lambda resolves current registry
values when it starts an execution. The CLI refreshes those values after it
upserts the pipeline.

An approved package invokes the deployment Lambda. The source defines 16
CloudWatch alarms: seven Security alarms, five Monitoring alarms, two
Ingestion alarms, and two Serving alarms. Pipeline and endpoint failure paths
use EventBridge rules. They are separate from the alarm count.

The repair set is local. It has no deployment evidence. A read-only dev query
on 2026-09-05 found that the current serving package has `test_auc` metadata
but no `baseline_uri`. The reader MUST stay inactive until a compatible package
or a verified migration supplies the metadata.

## Synthesis

The source flow is:

```text
traffic -> capture -> drift reader -> violation -> retrain -> pipeline
                                      -> challenger -> same holdout -> AUC gate
                                                        -> registry -> approval
                                                        -> endpoint
```

The baseline flow is separate:

```text
train split -> execution baseline -> registered baseline_uri
endpoint -> endpoint config -> model -> serving package -> baseline_uri
```

This separation binds drift to the model that serves traffic. A rejected
challenger cannot replace the serving reference. A package without metadata
cannot use the old fixed baseline as a substitute.

### Quality and sample limits

The drift job reads one complete prior hour. It skips a window with fewer than
`MIN_RECORDS=100` records. It also skips a window with fewer than
`MIN_DISTINCT_RECORDS=25` distinct records. These gates prevent sparse or
point-mass traffic from producing a false signal.

The job emits a violation when at least 30% of the 19 feature columns reach PSI
`0.2`, or when one column reaches PSI `1.0`. The job detects input drift. It
does not measure model quality against an observed outcome.

The held-out evaluation uses the fixed canonical splits: 4,930 training rows,
1,056 validation rows, and 1,057 test rows. The API evaluator uses the same
raw labeled fixture. Its default selection is a deterministic, class-balanced
sample of 25 rows. The `--all` option evaluates the full fixture.

### Failure signals

`mlops-<env>-retrain-loop-stalled` reports the structured
`retrain_loop_stalled` event. The alarm uses a metric filter on the retrain
Lambda log group and publishes to the operational SNS topic.

`mlops-<env>-ops-pipeline-failed` matches failed or stopped SageMaker pipeline
executions. `mlops-<env>-ops-endpoint-failed` matches the configured endpoint
ARN and the `FAILED`, `ROLLING_BACK`, and `UPDATE_ROLLBACK_FAILED` endpoint
states. Both rules publish to the operational topic. Neither is a CloudWatch
alarm.

## Tensions or open questions

- The current dev serving package lacks `baseline_uri`. Before activating the
  reader, verify the legacy training provenance and bind its corresponding
  versioned baseline. A compatible approved package is the other valid path.
- A metadata migration can emit an approval event regardless of the caller's
  permission boundary. The operator MUST plan for that event, use an explicit
  reviewed plan, and use the locally implemented serving retry protection. It
  is tested but not deployed. Metadata migration remains pending.
- The training role MUST have `sagemaker:ListModelPackages` on the package-group
  ARN before an updated SDK pipeline definition is used. The
  `DescribeModelPackage` grant uses package-version ARNs.
- A CDK diff describes desired state. It does not prove IAM authorization. A
  future deployment MUST inspect the read-only policy versions and a named
  dev resource diff. Security owns the alert topics and audit key. Data owns
  the buckets.
- Capture records contain inputs and scores without churn labels. Real labels
  remain external input. The platform MUST NOT train from predicted labels.
- The website hold and production service flags remain unchanged.

The serving deployment handler rechecks package approval before writes. It
reuses exact matching current and legacy model/config resources. A matching
`InService` endpoint returns a no-op. An expected in-flight endpoint with the
same pending configuration returns `in_progress`. Mismatched pending or
unhealthy states fail closed. A `ResourceInUse` race rechecks the resource
before continuing, so matching resources receive no duplicate writes. This
retry protection is implemented and tested locally, but is not deployed.

## Dated history

- **2026-07-10:** The first pipeline run exposed missing package imports in the
  Processing job. The packaging path was fixed. A later execution completed
  preprocessing, training, evaluation, and model registration with test AUC
  `0.8398`. The approval path then reached the serverless endpoint and API.
- **2026-08-07:** Live drift traffic exercised the count, uniformity, clean,
  and violation branches. The AUC gate rejected the shifted challenger, so the
  endpoint stayed on its prior model. The run also exposed the cached fixed-
  baseline defect recorded in the decision page. A live retrain showed that
  cached `Preprocess` and `Train` steps did not rewrite the fixed baseline.
  The former reset claim was removed.
  The current source uses execution-specific baseline outputs and disables the
  mutable data-step cache.
- **2026-09-05:** The baseline reader and same-holdout comparison were prepared
  locally. No AWS deployment or observation window followed those changes.
