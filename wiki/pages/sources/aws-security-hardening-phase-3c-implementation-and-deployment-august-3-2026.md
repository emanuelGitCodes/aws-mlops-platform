---
type: "source"
title: "AWS security hardening Phase 3C implementation and deployment — August 3, 2026"
created: "2026-08-03"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3c-implementation-and-deployment-august-3-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/stacks/security_stack.py", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../infra/config/dev.yaml", "../../../tests/unit/test_deployment_policy.py"]
summary: "AWS Config is live in dev with a ten-type recorder delivering into the audit bucket, after a pre-flight proved Free-plan availability and three defects — two of them pre-existing — blocked the first attempts."
---
# AWS security hardening Phase 3C implementation and deployment — August 3, 2026

## Confirmed

- **AWS Config is available on the AWS Free plan.** The pre-flight
  `describe-configuration-recorders`, `describe-delivery-channels`, and
  `describe-configuration-recorder-status` all returned empty lists rather
  than the `SubscriptionRequiredException` that `guardduty list-detectors`
  still raises on this account. This is the question the
  [Phase 3 plan revision](phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md)
  left open, and the gated deployment was the test.
- **The recorder is live and recording.** `mlops-dev-recorder` reports
  `recording=true`, `lastStatus=SUCCESS`, `allSupported=false`, and
  `recordingStrategy.useOnly=INCLUSION_BY_RESOURCE_TYPES` over exactly ten
  types: CloudTrail trails, IAM groups/policies/roles/users, KMS keys, Lambda
  functions, S3 buckets, SNS topics, and SQS queues.
- **Delivery goes to the existing audit bucket** under the `config` prefix at
  a 24-hour snapshot frequency, through `mlops-dev-delivery`.
- **The deployment changed five resources and nothing else.**
  `make verify-deploy SINCE=2026-08-03` reports three created in
  SecurityMonitoring (service-linked role, delivery channel, recorder) and two
  updated in Security (audit bucket policy, audit key). All six
  `mlops-dev-security-*` alarms were `OK` afterwards.
- **The execution policy is live as `v11`**, verified identical to the
  `envsubst`-rendered repository document. `v5` and `v6` were deleted to free
  version slots; `v7`, `v8`, and `v10` remain, with `v8` as the rollback
  target.
- **Delivery is proven, 2026-08-05.** Two `ConfigSnapshot` objects (one on
  2026-08-03, one on 2026-08-04) and a `ConfigWritabilityCheckFile` refreshed
  2026-08-04T23:47Z are present under `config/AWSLogs/<account>/Config/`.
  Because the audit bucket is KMS-encrypted, these are the first real writes to
  exercise both the bucket policy and the `kms:GenerateDataKey` grant added in
  the Security stack.
- **Recording honours the inclusion list after an initial full-inventory
  baseline.** On 2026-08-03 the recorder delivered 10 in-scope `ConfigHistory`
  objects and **40 out-of-scope ones**, which cover types the recorder never held
  for — API Gateway, Athena, CloudWatch alarms, CodeDeploy, Access Analyzer and
  others. On 2026-08-04 it delivered **zero** `ConfigHistory` objects of either
  kind. The recorder itself was unchanged throughout: still
  `allSupported=false` over exactly ten types with
  `INCLUSION_BY_RESOURCE_TYPES`, and CloudTrail records no
  `PutConfigurationRecorder` after the deployment.
- **Cost is $0.00 through 2026-08-04** for AWS Config, read from Cost Explorer
  daily granularity. The `$20` budget shows `$0.00` actual against a `$1.156`
  forecast for the whole account, with no alert threshold crossed. All six
  `mlops-dev-security-*` alarms `OK`, and `mlops-dev-recorder` still
  `recording=true`, `lastStatus=SUCCESS`.

## Synthesis

Three defects surfaced, and two of them were **pre-existing repository bugs
that no gate had caught**.

The first is the more instructive. Phase 3-prep pre-granted the Config
service-linked role at `role/aws-service-linked-role/config.amazonaws.com/*`,
which is not an IAM path — service-linked roles live under
`role/aws-service-role/`, as the Access Analyzer and GuardDuty statements in
the same document always did correctly. The reason it survived a review and a
test suite is that `test_config_service_linked_role_stays_scoped` asserted the
same wrong string: the test was protecting the defect rather than detecting
it. A test that pins a value copied from the implementation can only catch
drift, never an error present in both.

The second is that AWS Config requires `iam:PassRole` on its own
service-linked role. `PassOnlyApplicationRoles` is scoped to `Mlops-Dev-*`, so
the recorder's creation failed with `AccessDeniedException`. Both defects were
invisible until a real deployment attempted them, which is the argument for
the gated sub-phase pattern rather than a console wizard.

The third is a property of the service rather than a mistake. The recorder and
the delivery channel are **mutually dependent at the API**:
`PutDeliveryChannel` fails until a recorder exists, and the recorder's own
creation calls `StartConfigurationRecorder`, which fails until a channel
exists. Neither ordering can work. What made this expensive to diagnose is
that CloudFormation *retries* both errors rather than failing them, so each
attempt sat in `CREATE_IN_PROGRESS` for around ten minutes and had to be
stopped with `cancel-update-stack` — a call `${MLOPS_DEPLOYER_USER_NAME}` is not authorized
to make, so the administrator profile issued it. Declaring no dependency
between the two resources lets the retries converge, and a test now pins that
absence, because the failure mode is a hang rather than an error and would not
otherwise announce itself.

The recording scope is deliberately narrow. Config bills per configuration
item, so an all-types recorder would pay to version resource classes no
control in this platform reads, and would grow silently when the planned EC2
work lands.

That claim needs one qualification the observation window supplied. **The
inclusion list governs ongoing recording, not initial discovery.** When a
recorder starts for the first time, Config writes a one-time inventory across
resource types it finds in the account regardless of the list — 40 such objects
here, against 10 in-scope ones, all on the first day and none since. The effect
is a bounded one-off charge rather than a recurring one, but a reader comparing
the ten configured types against the delivered objects would otherwise conclude
the scope was not being honoured. It is.

The ten recorded types are the classes the Phase 2C detections already alarm
on changes to, which makes Config the configuration *history* behind alarms
that only report change events. Snapshots deliver into the
audit bucket rather than a new one because they are the same evidence class as
the trail's, inheriting its KMS key, versioning, and RETAIN policy. Those
grants live in the Security stack, which owns the bucket and key; adding them
from SecurityMonitoring would have closed a dependency cycle.

The rotation also closed the deploy-time denial burst recorded during the
Phase K deployment. The cause was never a missing intent but a naming
mismatch: the CloudTrail event `GetBucketEncryption` is authorized by
`s3:GetEncryptionConfiguration`, so the existing `s3:GetBucket*` wildcard
never covered CloudFormation's read-backs. Measured effect — the final
successful deployment produced **1** denial against Phase K's **105**.

## Tensions or open questions

- **Routine operator work still pages.** Six alarm emails fired during this
  sub-phase, all true positives attributable to it: `iam-policy-changes` twice
  for the two policy rotations, and `unauthorized-api-calls` four times. The
  datapoints were 1.0–2.0 per period sustained across many consecutive
  periods — which is indistinguishable from an attacker probing permissions.
  Phase 2E's `3 of 3` correctly suppresses *isolated* denials and did so; it
  cannot separate authorized-but-failing from unauthorized-and-failing. The
  conclusion is to document "expect alarms during a gated deploy" as operator
  guidance, not to weaken the detection. Related:
  [Phase 2E](aws-security-hardening-phase-2e-implementation-and-deployment-july-30-2026.md).
- **`config:ListConfigurationRecorders` is still denied**, twice per
  deployment. It is non-fatal — the recorder is created and reaches `SUCCESS`
  regardless — and granting it would have cost a third rotation and a third
  version deletion. It is the only denial standing between this account and a
  zero-denial deployment.
- **IAM policy version pressure is now the binding constraint.** Four of five
  slots are used and two historical versions were deleted to reach this state.
  Re-adding the GuardDuty grants at the trigger described in
  [paid Phase 3 security services](../decisions/phase-3-paid-security-services.md)
  will require deleting another version.
- **The observation window closed 2026-08-05 as a go**, roughly 48 hours after
  the deployment, with all four criteria met: snapshots delivered, cost
  measured, alarms steady, budget intact.
- **The measured $0.00 is lower than the item count implies.** Roughly 50
  configuration items at $0.003 works out to about $0.15, so the reading is
  either billing lag or a posting threshold rather than a true zero. It does
  not change the go decision — the ceiling is cents — but the honest figure is
  "not yet posted", and it is worth re-reading at month end.
