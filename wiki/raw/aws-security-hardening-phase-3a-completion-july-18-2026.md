# AWS security hardening Phase 3A completion — July 18, 2026

## Hosted gates and execution-policy correction

The isolated analyzer implementation and the follow-up least-privilege
execution-policy correction passed the hosted validation and secret-scan jobs
in draft pull request 4. The pull request remains draft and unmerged.

The first named deployment rolled back because the CloudFormation execution
role lacked permission to create the Access Analyzer service-linked role. The
correction grants only `iam:CreateServiceLinkedRole` on the exact
`AWSServiceRoleForAccessAnalyzer` path and requires the
`access-analyzer.amazonaws.com` service principal.

Read-only inventory before policy rotation found that the CloudFormation
execution policy was unexpectedly attached to one zero-member IAM group as
well as the intended execution role. With explicit operator approval, only the
execution-policy attachment was removed from that group. The group and its
other policy were preserved. No analyzer or service-linked role was created or
deleted manually.

The oldest non-default managed-policy version was deleted to free the IAM
version slot. The corrected repository document was installed as `v8` and made
default; `v7` remains available for rollback. Canonical comparison confirmed
that live `v8` matches the substituted repository document. The policy is now
attached to exactly one role and no users or groups.

## Named deployment and analyzer verification

The post-correction named diff contained exactly one addition:
`AWS::AccessAnalyzer::Analyzer`. The named SecurityMonitoring deployment then
reached `UPDATE_COMPLETE`. Its resources are the account external-access
analyzer and `AWS::CDK::Metadata` only.

Live analyzer checks confirmed:

- one `ACCOUNT` analyzer named `mlops-dev-external-access`;
- status `ACTIVE` and a populated most-recent-resource analysis timestamp;
- project, dev-environment, and `SecurityPhase=3A` tags;
- no paid analyzer configuration and zero archive rules;
- zero active findings, including zero public, cross-account, or error
  findings; and
- the automatically created `AWSServiceRoleForAccessAnalyzer` exists.

GuardDuty has zero detectors, AWS Config has zero recorders, Security Hub is
disabled, account-level S3 Block Public Access is absent, and Phase 3 security
EventBridge rules remain absent. Phase 3B was not started.

## Health, alarms, and cost boundary

One normal `/predict` request returned HTTP 200 with a finite probability and
a Boolean classification consistent with the unchanged `score >= 0.50`
contract. No endpoint, key, request, or response details are recorded.

The existing cost budget remains `$20` with calculated actual spend `$0` and
the existing 50%, 80%, and 100% notifications. AWS documents account
external-access analysis as available at no additional charge; no paid
internal-access or unused-access configuration is present.

The policy rotation produced the expected IAM-policy-change alarm. Six known
read-only denials contributed to the unauthorized-call alarm: one Access
Analyzer discovery call from the scoped CloudFormation execution role, one
Cloud Control discovery call from an AWS service-linked role, the previously
recorded three-call Cost Explorer console pattern from the administrative
identity, and one log-content read attempted by the security auditor. Every
event was attributed to a known action and identity category, with no unknown
principal or write denial. All six security alarms returned to `OK` naturally;
no state override was applied.

## Rollback and phase boundary

Analyzer rollback remains stack-owned: revert the Phase 3A implementation and
redeploy only `Mlops-Dev-SecurityMonitoring`. Do not delete the analyzer
manually. The policy can be rolled back separately by making `v7` default and
deleting `v8`; the corrected attachment boundary should remain in place.

Phase 3A is complete. Phase 3B requires a separate review and must not begin as
part of this checkpoint.

## External references

- AWS IAM Access Analyzer pricing:
  https://aws.amazon.com/iam/access-analyzer/pricing/
- AWS IAM Access Analyzer service-linked roles:
  https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-using-service-linked-roles.html
- AWS IAM Access Analyzer findings review:
  https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-findings-view.html
