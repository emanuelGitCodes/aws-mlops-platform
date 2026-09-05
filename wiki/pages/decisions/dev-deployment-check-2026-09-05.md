---
type: decision
title: Dev deployment check on 2026-09-05
created: "2026-09-05"
updated: "2026-09-05"
sources: ["../../log.md", "../../../Makefile", "../../../scripts/verify_deployment.py", "../../../tests/integration/test_api_smoke.py", "audit-repair-readiness.md"]
summary: "Five dev stacks updated successfully and six API checks passed; pipeline publication and baseline migration remain blocked."
---
# Dev deployment check on 2026-09-05

## Confirmed

The user authorized a dev infrastructure deployment and log inspection.
The source commit was `1072db9`. The website remained dormant. No production
stack, account execution policy, or model-package metadata was changed.

The operator used `${MLOPS_DEPLOYER_USER_NAME}` for deployment and
`${AWS_SECURITY_AUDITOR_USER_NAME}` for CloudFormation verification in
`us-east-1`. `${AWS_ADMIN_USER_NAME}` provided application-log reads and
the signed API smoke calls. No identity policy was widened.

`make test` passed 649 tests at 96.14% coverage, above the 95.17% floor.
`make synth-all` passed for dev and prod. Named stack diffs were reviewed
before deployment, including all dependency stacks.

These commands exited zero, in this order:

1. `make deploy-stack STACK=Mlops-Dev-Security ENV=dev`
2. `make deploy-stack STACK=Mlops-Dev-Training ENV=dev`
3. `make deploy-stack STACK=Mlops-Dev-Serving ENV=dev`
4. `make deploy-stack STACK=Mlops-Dev-Ingestion ENV=dev`

Training also deployed Registry retention. Data had no pending change.
Post-deploy `make diff-stack` checks for Cicd and SecurityMonitoring found
zero differences, including their dependencies. Neither needed deployment.
`make verify-deploy PREFIX=Mlops-Dev- SINCE=2026-09-05` exited zero.
It reported 30 resource changes across five stacks:

| Stack | Resource evidence |
|---|---|
| Security | Audit key and operations topic policies; seven metric filters and seven alarms updated. |
| Registry | `UPDATE_COMPLETE ChurnModelGroup`; the reviewed change adds retention policies. |
| Training | `UPDATE_COMPLETE PipelineExecutionRoleDefaultPolicy6A228648`. |
| Serving | Deploy and proxy functions and deploy-role policy updated; two alarms and the endpoint-failure rule created. |
| Ingestion | Validator and its policy updated; queue policy updated; DLQ policy and two alarms created. |

The live training policy includes `sagemaker:ListModelPackages` on the configured
model-package group. This confirms policy installation, not a training execution.

`make smoke ENV=dev` passed all six integration checks with the admin inference
identity and separate auditor discovery identity. The checks cover probability,
classification, invalid schema, invalid JSON, unsigned requests, and changed
signed bodies. They do not test least-privilege caller provisioning.

The first smoke command stopped at a local jsii cache permission error.
Setting `JSII_RUNTIME_PACKAGE_CACHE_ROOT` to a writable scratch directory
resolved that local error. The corrected command passed.

A post-deploy proxy-log query found no `ERROR`, `Exception`, or `capture_failed`
matches in the inspected deployment window. The older drift reader logged
`drift_window_too_small` with zero records in the inspected window.
The audit identity could not read application logs; the admin read succeeded.

The IAM-policy-change alarm moved from `OK` to `ALARM` at 18:57:54 UTC.
Its history reported a datapoint of two in the deployment window and a
successful SNS action. Email receipt and subsequent recovery were not verified.
New ingestion alarms initially reported `INSUFFICIENT_DATA`.

## Synthesis

The independent infrastructure changes deployed without CloudFormation failure.
The API works with an authorized identity. Full MLOps release remains a no-go.

The SDK pipeline command, without `--start`, failed before upsert with
`AccessDeniedException` on `sagemaker:ListModelPackages` under the deployment
identity. AWS named the model-package version resource in the denial.
The pipeline definition before and after the attempt compared equal.
No fresh training execution was started.

The serving endpoint remained `InService`. Its approved package still has
`test_auc` metadata and no `baseline_uri`. Monitoring was deliberately not
deployed: the new reader requires verified serving-model baseline metadata.
The existing Monitoring functions and schedule remain active at their old version.

## Tensions or open questions

- Resolve the pipeline operator's registry permissions and verify the required
  resource scope with a real call. Then publish and inspect the new definition.
- Verify legacy training provenance before baseline backfill, or serve a
  compatible package through the normal approval gate. Do not force promotion.
- Deploy Monitoring after baseline readiness. Complete a real training,
  promotion or rejection, drift, retrain, and recovery exercise.
- Exercise ingestion replacement behavior with isolated keys and cleanup.
- Verify alarm delivery and recovery. An alarm existing in AWS is insufficient.
- The SageMaker SDK advisory remains tracked in the
  [advisory decision](sagemaker-sdk-advisory-triage.md).

The readiness judgment is 80/100 for the operational MLOps portfolio scope,
excluding the website. This is an engineering estimate, not a coverage metric.
Core infrastructure and inference work; the repaired lifecycle lacks live proof.
