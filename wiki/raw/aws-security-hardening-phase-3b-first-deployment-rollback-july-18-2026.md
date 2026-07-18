# AWS security hardening Phase 3B first deployment rollback — July 18, 2026

## Objective and boundary

Deploy only the approved foundational GuardDuty detector after green hosted
validation, a verified execution-policy rotation, and an exact named
SecurityMonitoring diff. Preserve Phase 3A and stop before AWS Config.

## Gates and policy rotation

Draft pull request 5 passed both hosted validation and secret scanning. The
live execution policy was verified as default `v8`, attached to one role and
zero users or groups, with versions `v4`–`v8` occupying all five slots.

The oldest non-default `v4` was deleted. The repository policy was installed as
default `v9`, canonically matched the local parameterized policy, retained `v8`
for rollback, and preserved the one-role attachment boundary. The named
no-change-set diff then showed exactly one new
`AWS::GuardDuty::Detector` in `Mlops-Dev-SecurityMonitoring`.

## Failed deployment and automatic rollback

The named deployment reached the detector create operation, but the
CloudFormation GuardDuty resource provider returned HTTP 403
`SubscriptionRequiredException`: the account needed a subscription for the
service. No IAM denial was reported. The stack automatically rolled back to
`UPDATE_ROLLBACK_COMPLETE`.

A delayed audit lookup found the CloudFormation `CreateDetector` call with the
exact expected enablement, 15-minute publishing, tags, no legacy data sources,
and all six optional features disabled. GuardDuty rejected that request with
`SubscriptionRequiredException`. No GuardDuty `CreateServiceLinkedRole` event
occurred. This confirms that the detector API rejected the create request
before service-linked-role creation; the prepared IAM permission was not the
reported failure. The exact reason the API could not bootstrap the
never-enabled GuardDuty state remains unresolved.

## Rollback verification

The Phase 3B live changes were rolled back through their intended boundaries:

- The stable SecurityMonitoring stack contains only the accepted Phase 3A
  analyzer and CDK metadata.
- GuardDuty remains in the never-enabled subscription state with no detector,
  and `AWSServiceRoleForAmazonGuardDuty` is absent.
- The execution policy was restored to verified default `v8`; failed-rollout
  `v9` was deleted. Versions `v5`–`v8` remain, and the policy is attached to one
  role and zero users or groups.
- Access Analyzer remains active with zero active findings. AWS Config,
  Security Hub, account S3 Block Public Access, and Phase 3 EventBridge routing
  remain absent.
- The `$20` budget and 50%, 80%, and 100% alerts are unchanged.
- `/predict` returned HTTP 200 and preserved the probability/Boolean
  `score >= 0.5` contract.
- The IAM-policy-change alarm activated as expected from the approved `v9`
  rotation and rollback. It returned naturally to `OK` after one quiet metric
  period, leaving all six security alarms `OK`; no state override was used.

Because no detector exists, GuardDuty findings, protection-plan state, free
trial days, and usage estimates cannot be retrieved. No sample findings were
created.

## Decision and next checkpoint

Phase 3B is not complete. Keep pull request 5 draft and do not begin Phase 3C.
Do not manually create a detector or service-linked role, because that would
bypass the approved CloudFormation ownership and rollback path.

Before retrying, establish an AWS-supported way for
`AWS::GuardDuty::Detector` to create the first detector in this account while
retaining explicit control of every default-on optional paid feature. If a
manual console/API subscription is required, stop for a separate ownership and
rollback decision rather than silently adopting it. Any retry must repeat the
live stop gate, policy rotation, named diff, named deployment, and complete
finding/cost/application verification.
