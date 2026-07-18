# AWS security hardening Phase 3B implementation — July 18, 2026

## Boundary and refreshed feature contract

Phase 3B is limited to one regional GuardDuty detector in `us-east-1`.
Phase 3A remains deployed and accepted. AWS Config, Security Hub,
account-level S3 Block Public Access, security-finding EventBridge routing,
application wiring, workload IAM, data paths, and `/predict` remain outside
this change.

The current AWS CLI GuardDuty model was checked before implementation. In
addition to the five optional protection plans named in the original Phase 3B
plan, the create-detector API now exposes `AI_ANALYST`. Because GuardDuty
enables unspecified optional features by default, the implementation disables
all six currently expressible optional paid features. Runtime Monitoring and
legacy EKS Runtime Monitoring remain omitted; this phase enables only
foundational detection.

## Read-only live pre-state

The live stop gate passed before any mutation:

- `Mlops-Dev-SecurityMonitoring` was `UPDATE_COMPLETE` with only the accepted
  Phase 3A analyzer and CDK metadata.
- GuardDuty returned the never-enabled subscription response, and the
  GuardDuty service-linked role was absent.
- The account external-access analyzer was active with zero active findings.
- AWS Config, Security Hub, account S3 Block Public Access, and Phase 3
  EventBridge routing remained absent.
- Execution-policy `v8` matched the merged Phase 3A repository policy, was
  default, and was attached to one role and zero users or groups. Versions
  `v4`–`v8` occupied the five policy slots.
- All six security alarms were `OK`. The existing `$20` budget showed `$0`
  actual spend and retained the 50%, 80%, and 100% actual-spend alerts.

No detector, role, policy version, stack, finding, filter, sample finding, or
other AWS resource was created or changed during this checkpoint.

## Implemented scope

1. The existing flag-gated `SecurityMonitoringStack` now creates one
   `AWS::GuardDuty::Detector` when `guardduty` is true. The detector is enabled,
   publishes updated findings every 15 minutes, and carries exact project,
   environment, and `SecurityPhase=3B` tags.
2. `S3_DATA_EVENTS`, `EKS_AUDIT_LOGS`, `EBS_MALWARE_PROTECTION`,
   `RDS_LOGIN_EVENTS`, `LAMBDA_NETWORK_LOGS`, and `AI_ANALYST` are explicitly
   `DISABLED`. The template contains no `DataSources`, filters, IP sets,
   threat-intelligence sets, publishing destinations, or other GuardDuty
   resources.
3. Dev enables the already accepted Access Analyzer plus GuardDuty. Production
   remains all-false, and Phase 3C–3F flags remain false.
4. The CloudFormation execution policy gains one independent
   `iam:CreateServiceLinkedRole` statement limited to the exact
   `AWSServiceRoleForAmazonGuardDuty` path and
   `iam:AWSServiceName=guardduty.amazonaws.com`. Existing GuardDuty lifecycle
   and role-policy lifecycle permissions are unchanged.
5. Focused tests lock the detector contract, complete disabled-feature list,
   resource boundary, production shell, and service-linked-role permission.

## Local verification

- Clean baseline: `make lint`, 53 tests, and eight-stack synthesis passed.
- Updated implementation: `make lint` passed and 54 tests passed.
- `make security`: the 108-package lock check passed, dependency audit found no
  known vulnerabilities, and all eight dev stacks synthesized with cdk-nag.
- Named `diff-stack` and `deploy-stack` dry runs rendered only
  `Mlops-Dev-SecurityMonitoring`.
- A clean temporary synth of merged `main` proved Data, Monitoring, Registry,
  Security, and Training templates byte-identical. Ingestion and Serving
  differed only in generated Lambda asset hashes. The only infrastructure
  template change is the SecurityMonitoring detector.
- The existing IAM template fingerprints passed unchanged. Diff checks and the
  pre-finish duplication search were clean.

## Rollout and rollback checkpoint

This record claims implementation and read-only pre-state, not deployment.
Next, commit the isolated change, require green hosted validation and secret
scanning, rotate the execution policy from `v8` to verified default `v9` while
retaining `v8`, review a named no-change-set diff, and deploy only
`Mlops-Dev-SecurityMonitoring`.

Rollback is a revert of the Phase 3B implementation followed by the named
SecurityMonitoring deployment. Do not delete the detector manually. If the
execution permission must be reverted, make `v8` default and delete `v9`.
The GuardDuty service-linked role may remain after detector deletion and must
not be manually removed. Do not begin Phase 3C before a separate Phase 3B
completion review.

## External references

- GuardDuty `CreateDetector` API:
  https://docs.aws.amazon.com/guardduty/latest/APIReference/API_CreateDetector.html
- GuardDuty detector feature configuration:
  https://docs.aws.amazon.com/guardduty/latest/APIReference/API_DetectorFeatureConfiguration.html
- CloudFormation `AWS::GuardDuty::Detector`:
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-guardduty-detector.html
- GuardDuty service-linked role:
  https://docs.aws.amazon.com/guardduty/latest/ug/slr-permissions.html
- GuardDuty pricing:
  https://aws.amazon.com/guardduty/pricing/
