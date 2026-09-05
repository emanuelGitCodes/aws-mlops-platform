---
type: decision
title: Audit repair readiness and dev release gate
created: "2026-09-05"
updated: "2026-09-05"
sources: ["../../log.md", "../../../README.md", "../concepts/closed-drift-loop.md", "drift-capture-design.md", "../../../src/common/drift.py", "../../../src/monitoring/drift_handler.py", "../../../src/pipeline/pipeline.py", "../../../src/pipeline/evaluate.py", "../../../src/monitoring/retrain_handler.py", "../../../src/serving/deploy_handler.py", "../../../infra/stacks/monitoring_stack.py", "../../../infra/stacks/serving_stack.py", "../../../infra/stacks/security_stack.py", "../../../infra/stacks/training_stack.py", "../../../scripts/evaluate_api.py", "../../../scripts/verify_deployment.py"]
summary: "The audit repairs and serving retry protection pass local gates, but dev release waits for serving-package baseline metadata and provenance checks."
---
# Audit repair readiness and dev release gate

## Confirmed

The original audit recorded six defects, F1 through F6:

1. **F1 — stale curated data:** A readable upload with no valid rows could
   leave stale curated training data. The validation path now removes that
   object. An unreadable upload still preserves the last validated object.
2. **F2 — invalid baseline:** Drift accepted malformed or incomplete baselines.
   The shared validator now checks the full feature contract, bucket totals,
   numeric edges, and category values.
3. **F3 — credential profile mix-up:** Smoke and evaluation paths could use one
   credential profile for both discovery and inference. The paths now accept
   separate authorized profiles.
4. **F4 — single-class split:** A split could omit one churn class. The
   preprocessing path now preserves both classes before artifact writes.
5. **F5 — tiny split:** A dataset could produce unusable train, validation, or
   test splits. The preprocessing path now rejects inputs below the split
   minimum.
6. **F6 — custom threshold drift:** Evaluation and API checks could use
   different classification thresholds. The shared `0.50` threshold now
   controls both paths.

## Additional lifecycle repairs

1. A champion lookup at pipeline build time could control a later execution.
   The retrain Lambda reads the registry when it starts. The CLI refreshes
   champion parameters after an upsert.
2. The challenger and champion could use different score sources. `Evaluate`
   loads the latest approved package named by the current execution when the
   step runs, then scores both models on the same held-out rows. The gate reads
   the computed champion AUC.
3. A rejected candidate could leave the drift reference unrelated to the
   model in service. Baselines now use an execution-specific path and a
   `baseline_uri` package property. The reader follows the serving endpoint to
   its package.
4. Stalled retraining and endpoint failure now have operator notifications.

The source repair passes local tests and CDK synthesis. The
[2026-09-05 deployment check](dev-deployment-check-2026-09-05.md) deployed
Security, Registry, Training, Serving, and Ingestion changes. Monitoring and
pipeline publication remain blocked. The current dev serving package has
`test_auc` metadata and no `baseline_uri`.

## Synthesis

The pipeline writes a train-split baseline to:

```text
s3://${ARTIFACTS_BUCKET}/monitor/baselines/<pipeline-execution-id>/baseline.json
```

The registration step records that URI under `baseline_uri`. The drift reader
then follows this chain:

```text
endpoint -> endpoint config -> model -> model package -> baseline_uri
```

It accepts only the configured artifacts bucket and the versioned baseline
prefix. It validates the object before comparison. It rechecks endpoint status
and configuration before publishing a result. A missing package property,
untrusted URI, malformed object, or observed model switch fails closed.

The reader MUST remain inactive until the current serving package has a
compatible baseline property. Release has two valid paths:

- Verify legacy training provenance. Bind the corresponding versioned baseline
  to the package.
- Serve an approved package that already carries compatible metadata.

Do not force a promotion. Do not bypass the strict AUC gate on a tie. Do not
pretend that the current shared baseline proves the serving model's provenance.

### Release checks

The operator MUST complete these checks before a future dev release:

1. Read the current serving package, endpoint configuration, and model with the
   read-only verification identity. Confirm `baseline_uri` and its training
   provenance.
2. A metadata migration can emit an approval event regardless of the caller's
   permission boundary. The operator MUST plan for that event, use an explicit
   reviewed plan, and use the locally implemented serving retry protection. It
   deployed on 2026-09-05. Metadata migration remains pending.
3. Confirm the training role has `sagemaker:ListModelPackages` on the
   model-package group before using an updated SDK pipeline definition.
   `DescribeModelPackage` uses package-version ARNs.
4. Before any future execution-policy installation, list policy versions and
   attachments. Read the current default document. Compare it with the
   reviewed repository document. Inspect a named CDK diff after that review.
5. Treat a CDK diff as desired state. It does not prove permission. Security
   owns the alert topics and audit key. Data owns the data buckets.
6. Treat a metric namespace update as a destination change. It does not replace
   the `AWS::Logs::MetricFilter` resources.
7. Verify resource changes with the explicit read profile and dev prefix:

   ```bash
   AWS_PROFILE=${AWS_SECURITY_AUDITOR_USER_NAME} make verify-deploy \
     PREFIX=Mlops-Dev- SINCE=<YYYY-MM-DD>
   ```

Use this rollout order:

1. Review execution policies and verification identities. Install only approved
   changes. Review Registry retention and Security namespace changes separately.
2. Review Data's own diff, exports, and resource identities. Deploy and verify
   pending Data changes explicitly. Security does not deploy Data.
3. Confirm the Training role's `ListModelPackages` grant. Then upsert the SDK
   pipeline and verify the definition's same-held-out comparison wiring.
4. Deploy and verify Serving retry protection before metadata backfill.
5. Deploy Ingestion's permissions and validation changes. Use isolated test
   keys and a cleanup plan for replacement tests.
6. Migrate metadata for the approved serving package. Plan for approval events
   that may occur during migration.
7. Activate the Monitoring reader only after migration readiness passes. The
   serving retry protection deployed on 2026-09-05. Monitoring deployment and
   metadata migration remain pending.
8. Complete approved smoke, failure, notification, and recovery checks. Record
   resource evidence and a go/no-go decision for each observation window.

### Serving retry behavior

The deployment handler rechecks `ModelApprovalStatus` with
`DescribeModelPackage` before it writes a model or endpoint configuration. A
stale approval event is skipped.

It reuses an exact current serving model and configuration. This includes a
matching legacy resource name. A matching `InService` endpoint returns a
no-op. An expected `Creating`, `Updating`, or `SystemUpdating` endpoint with
the same pending configuration returns `in_progress` without a second update.

The handler rejects a pending configuration mismatch and rejects
`Failed`, `RollingBack`, `UpdateRollbackFailed`, and `Deleting` states. A
`ResourceInUse` race triggers a describe-and-match check before the handler
continues. Tests cover these paths and confirm no duplicate create or update
writes for matching resources. This behavior deployed on 2026-09-05. Live
approval-event replay remains unverified.

## Operational contract

The source defines 16 CloudWatch alarms:

| Stack | Alarms | Signal |
|---|---:|---|
| Security | 7 | Account and detection findings |
| Monitoring | 5 | Handler errors, stalled retraining, endpoint errors and silence |
| Ingestion | 2 | Validation errors and dead-letter backlog |
| Serving | 2 | Deployment and proxy errors |

Pipeline failure and endpoint failure use EventBridge rules. They do not add
CloudWatch alarms to this count.

The drift job reads one complete prior hour. It skips fewer than 100 records or
fewer than 25 distinct records. It emits a violation at 30% of 19 feature
columns or at one PSI value of `1.0`. Capture records contain inputs and scores
without labels. Real churn labels remain external input. The platform MUST NOT
train from predicted labels.

The monthly budget is `$20` with 50/80/100% alerts. These alerts notify the
operator. They do not cap spending. The website hold and production service
flags remain unchanged.

## Tensions or open questions

- The local repair set has no AWS deployment evidence. Local tests and syntheses
  do not prove package metadata, permissions, notification delivery, or live
  endpoint behavior.
- Metadata migration needs verified training provenance. Live retry and
  notification outcomes remain unverified.
- The README architecture diagram describes repository source and desired
  wiring. It does not describe a fully deployed system.
