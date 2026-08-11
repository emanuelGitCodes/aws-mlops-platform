# AWS security hardening Phase 3C — implementation and deployment, August 3, 2026

Raw evidence for enabling AWS Config in the dev account. All timestamps UTC.
Account identifiers are written as `${AWS_ACCOUNT_ID}` placeholders.

## Pre-flight, 2026-08-03 ~00:00Z

Read-only, administrator profile:

```
aws configservice describe-configuration-recorders      -> {"ConfigurationRecorders": []}
aws configservice describe-delivery-channels            -> {"DeliveryChannels": []}
aws configservice describe-configuration-recorder-status -> {"ConfigurationRecordersStatus": []}
```

The API answers. It does not raise `SubscriptionRequiredException`, which
`guardduty list-detectors` still does on this account. Config is therefore
usable on the AWS Free plan.

Baseline, auditor profile: eight dev stacks `UPDATE_COMPLETE`/`CREATE_COMPLETE`,
six `mlops-dev-security-*` alarms `OK`, analyzer `mlops-dev-external-access`
`ACTIVE`, zero Config resources.

Cost sizing: 101 resources across the eight dev stacks; AWS Config lists
$0.003 per configuration item for continuous recording in us-east-1.

## Execution policy rotations

Version numbering on an IAM managed policy is monotonic, not slot-based: the
create returned **v10**, not v9, because a v9 had previously existed.

- **v10** — removed the eight `guardduty:*` actions and the
  `GuardDutyServiceLinkedRole` statement; corrected the Config
  service-linked-role path (below); added the CloudFormation read-back grants
  `s3:GetEncryptionConfiguration`, `GetLifecycleConfiguration`,
  `GetAccelerateConfiguration`, `GetAnalyticsConfiguration`,
  `GetIntelligentTieringConfiguration`, `GetInventoryConfiguration`,
  `GetMetricsConfiguration`, `GetReplicationConfiguration`,
  `logs:ListTagsForResource`, `logs:DescribeIndexPolicies`. `v5` deleted to
  free a slot.
- **v11** — added `PassConfigServiceLinkedRole`. `v6` deleted to free a slot.

Live versions after the work: `v7`, `v8`, `v10`, `v11` (default). `v8` is the
rollback target. Live `v11` was diffed against the `envsubst`-rendered
repository document and is identical.

## Defect 1 — wrong service-linked-role path (pre-existing)

Phase 3-prep granted, and `test_config_service_linked_role_stays_scoped`
asserted:

```
arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-linked-role/config.amazonaws.com/*
```

`aws-service-linked-role` is not an IAM path. The sibling Access Analyzer and
GuardDuty statements in the same document correctly use `aws-service-role`.
Because the test pinned the wrong value, the error was locked in rather than
caught. Corrected in v10 and in the recorder's `role_arn`.

## Defect 2 — iam:PassRole on the service-linked role

Deployment attempt at 00:24:35Z:

```
CREATE_FAILED  AWS::Config::ConfigurationRecorder  ConfigurationRecorder
  User: ...cdk-hnb659fds-cfn-exec-role.../AWSCloudFormation is not authorized
  to perform: iam:PassRole on resource:
  arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig
  (Service: AmazonConfig; Status Code: 400; Error Code: AccessDeniedException)
```

`PassOnlyApplicationRoles` is scoped to `role/Mlops-Dev-*` and never covered
it. Rolled back cleanly. Fixed by the v11 `PassConfigServiceLinkedRole`
statement, scoped to the exact role ARN with
`iam:PassedToService = config.amazonaws.com`.

## Defect 3 — the recorder and delivery channel are mutually dependent

Two orderings were deployed and both deadlocked. CloudTrail, 00:26–00:37Z:

```
   7  StartConfigurationRecorder    NoAvailableDeliveryChannelException
   2  ListConfigurationRecorders    AccessDenied
   2  DescribeConfigurationRecorders NoSuchConfigurationRecorderException
   1  PutConfigurationRecorder      AccessDenied
   1  PutConfigurationRecorder      (success)
```

- Channel ordered first: `PutDeliveryChannel` returns
  `NoAvailableConfigurationRecorderException` until a recorder exists.
- Recorder ordered first: the recorder's own creation calls
  `StartConfigurationRecorder`, which returns
  `NoAvailableDeliveryChannelException` until a channel exists.

CloudFormation **retries** both errors instead of failing, so each attempt sat
in `CREATE_IN_PROGRESS` — roughly ten minutes each — and had to be stopped with
`cancel-update-stack` rather than rolling back on its own. Note that
`${MLOPS_DEPLOYER_USER_NAME}` lacks `cloudformation:CancelUpdateStack`; the administrator
profile issued it.

With no dependency between the two resources, the retries converge.

## Successful deployment, 00:40:13Z–00:41:24Z

```
CREATE_COMPLETE  AWS::IAM::ServiceLinkedRole        ConfigServiceLinkedRole   00:40:49
CREATE_COMPLETE  AWS::Config::DeliveryChannel       ConfigDeliveryChannel     00:41:17
CREATE_COMPLETE  AWS::Config::ConfigurationRecorder ConfigurationRecorder     00:41:23
UPDATE_COMPLETE  AWS::CloudFormation::Stack         Mlops-Dev-SecurityMonitoring
```

## Verification

```
describe-configuration-recorder-status
  mlops-dev-recorder   recording=True   lastStatus=SUCCESS

describe-configuration-recorders
  allSupported=false, includeGlobalResourceTypes=false,
  recordingStrategy.useOnly=INCLUSION_BY_RESOURCE_TYPES,
  resourceTypes=[CloudTrail::Trail, IAM::Group, IAM::Policy, IAM::Role,
                 IAM::User, KMS::Key, Lambda::Function, S3::Bucket,
                 SNS::Topic, SQS::Queue]

describe-delivery-channels
  mlops-dev-delivery   prefix=config   deliveryFrequency=TwentyFour_Hours
```

`make verify-deploy SINCE=2026-08-03`:

```
Mlops-Dev-SecurityMonitoring [UPDATE_COMPLETE]  last updated 2026-08-03T00:40:09Z
    CREATE_COMPLETE  ConfigDeliveryChannel
    CREATE_COMPLETE  ConfigServiceLinkedRole
    CREATE_COMPLETE  ConfigurationRecorder
Mlops-Dev-Security [UPDATE_COMPLETE]  last updated 2026-08-03T00:08:24Z
    UPDATE_COMPLETE  AuditBucketPolicy...
    UPDATE_COMPLETE  AuditKey...
```

All six `mlops-dev-security-*` alarms `OK` afterwards.

## Alarm activity during the work

Six SNS emails, all true positives attributable to this work:

- `iam-policy-changes` fired 00:09:21Z (v10 `CreatePolicyVersion`) and
  00:27:21Z (`DeletePolicyVersion` v5 plus v11 `CreatePolicyVersion`).
- `unauthorized-api-calls` fired 00:14:14Z, 00:22:14Z, 00:27:14Z and 00:32:14Z.
  Datapoints were 1.0–2.0 per five-minute period sustained across many
  consecutive periods, not a spike: pre-v11 deploy read-backs, the denied
  `PutConfigurationRecorder`, `ListConfigurationRecorders`, and the deployer's
  own denied `CancelUpdateStack`.

All self-cleared; every alarm was `OK` by ~00:35Z.

## Read-back grant effectiveness

Denials during the final successful deployment, 00:39–00:46Z: **1**
(`config:ListConfigurationRecorders`). The comparable Phase K deployment on
2026-08-02 produced **105**. The `s3:Get*Configuration` family and the
`logs:ListTagsForResource` / `DescribeIndexPolicies` pair no longer appear.

`config:ListConfigurationRecorders` was deliberately not granted: it is
non-fatal — the recorder is created and reaches `SUCCESS` regardless — and
granting it would have required a third rotation and a third version deletion.

## Repository gates at the deployed commit

lint, mypy (36 files), 228 unit tests at 92.50% coverage, `synth-all` for dev
and prod through cdk-nag, `docs-sync`, `wiki-lint`.
