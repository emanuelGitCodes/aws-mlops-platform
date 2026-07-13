---
type: architecture
title: Phase 2 audit foundation
created: "2026-07-12"
updated: "2026-07-12"
sources: ["../../raw/aws-security-hardening-phase-2b-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2b-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-implementation-july-12-2026.md", "../../raw/aws-security-hardening-phase-2c-completion-july-12-2026.md", "../../raw/aws-security-hardening-phase-2d-implementation-july-12-2026.md", "../../../infra/stacks/security_stack.py", "../../../infra/config/dev.yaml", "../../../infra/security_checks.py", "https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html", "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-kms-key-policy-for-cloudtrail.html", "https://docs.aws.amazon.com/securityhub/latest/userguide/cloudwatch-controls.html"]
summary: "The deployed Security stack retains validated encrypted CloudTrail evidence and provides a confirmed encrypted alert path."
---
# Phase 2 audit foundation

## Confirmed

`Mlops-Dev-Security` owns the Phase 2 audit boundary:

| Resource | Contract |
|---|---|
| KMS key | Rotating, retained, alias `alias/mlops-dev-audit`; exact CloudTrail, regional Logs, CloudWatch, and Budgets service grants. |
| Access-log sink | Retained, private, versioned, Bucket Owner Enforced, TLS 1.2, SSE-S3, and intentionally not recursively logged. |
| CloudTrail bucket | Retained, private, versioned, Bucket Owner Enforced, TLS 1.2, audit-key encryption with Bucket Keys; access logs use `cloudtrail/`. |
| CloudWatch log group | `/aws/cloudtrail/mlops-dev-audit`, retained, audit-key encrypted, 90 days. |
| Trail | `mlops-dev-audit`, multi-Region, global read/write management events, integrity validation, S3 and Logs delivery. |
| SNS topic | `mlops-dev-security-alerts`, audit-key encrypted and TLS-only; email endpoint is a deployment parameter. |

The trail has no data-event selectors, Insights selectors, or organization-trail
mode. Those would change cost and scope and therefore require a separate phase.

The deployed foundation has passed live verification: CloudTrail is logging,
S3 and CloudWatch Logs receive records, the first digest validates, and a direct
SNS test reached the confirmed email subscription. See the
[Phase 2B completion record](../sources/aws-security-hardening-phase-2b-completion-july-12-2026.md).

## Synthesis

The two storage layers serve different purposes. The CloudTrail bucket contains
KMS-encrypted audit records and digest files. The access-log sink records access
to that bucket and uses SSE-S3 because S3 server-access logging does not reliably
support a customer-KMS destination. The sink itself cannot log recursively.

CloudTrail can generate data keys only when the source and encryption context
match the one trail ARN. Regional CloudWatch Logs can use the key only for the
one audit log-group ARN. CloudWatch alarms and AWS Budgets can publish only from
this account and their respective ARN namespaces.

The CloudTrail service role can create streams and put events only under the
one audit log group. Its wildcard is limited to the required `log-stream:*`
suffix rather than all log groups.

### Phase 2C detection contract

The deployed Phase 2C change adds one exact AWS
Security Hub/CIS metric filter and one alarm for root usage, unauthorized API
calls, IAM policy changes, CloudTrail configuration changes, KMS disable or
scheduled deletion, and S3 bucket-policy changes. Every filter writes to
`MLOps/Security`; every five-minute alarm notifies the confirmed encrypted topic
at `>= 1` and treats missing data as non-breaching.

A controlled read-only IAM denial proved the entire chain through received
email. See the [Phase 2C completion record](../sources/aws-security-hardening-phase-2c-completion-july-12-2026.md).

### Phase 2D sink-policy prerequisite

The implemented Phase 2D change adds a conditioned sink statement for the three
Data log prefixes. It restricts delivery to the S3 logging service, this account,
and source bucket ARNs matching `mlops-dev-data-*`. This Security-owned policy
must deploy before Data enables logging; see the
[Phase 2D implementation record](../sources/aws-security-hardening-phase-2d-implementation-july-12-2026.md).

## Tensions or open questions

- Phase 2D owns source-bucket logging and budget notifications.
- The full Phase 2 foundation requires the 24-hour cost observation checkpoint
  after Phase 2D.
