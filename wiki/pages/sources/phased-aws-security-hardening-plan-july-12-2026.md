---
type: "source"
title: "Phased AWS security hardening plan — July 12, 2026"
created: "2026-07-12"
updated: "2026-07-12"
sources: ["../../raw/phased-aws-security-hardening-plan-july-12-2026.md"]
summary: "Evidence and implementation checkpoints for the approved phase-by-phase AWS security-hardening roadmap."
---
# Phased AWS security hardening plan — July 12, 2026

## Key claims

- Security changes must be isolated into separately implemented, tested,
  committed, deployed, and observed phases.
- The target is AWS Foundational Security Best Practices for the dev workload,
  not a claim of formal regulatory compliance.
- Auditability and detection precede encryption, IAM, authentication, and WAF
  changes so later failures have CloudTrail and alert evidence.
- Customer-managed encryption and least-privilege IAM are migrated incrementally
  to preserve the working ingestion, pipeline, registry, deployment, and API
  paths.
- The API will deliberately move from an API key to IAM/SigV4 only after clients
  are ready; WAF is a later, independent phase.

## Entities and concepts

- [Phased security hardening roadmap](../architecture/phased-security-hardening.md)
- [AWS resource and permission boundaries](../architecture/permissions.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)
- CloudTrail, GuardDuty, Security Hub CSPM, AWS Config, IAM Access Analyzer,
  customer-managed KMS keys, API Gateway IAM authorization, and AWS WAF.

## Tensions or open questions

- The security-alert email must be supplied and its SNS subscription confirmed
  before the notification phase can pass acceptance.
- GuardDuty, Config, Security Hub, WAF, CloudWatch Logs, and KMS introduce
  recurring charges; dev enables them incrementally in `us-east-1` and measures
  cost before expanding coverage.
- Phase 5 validation includes a billable SageMaker pipeline execution.
