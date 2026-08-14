---
type: source
title: "AWS security hardening Phase 3A first deployment rollback — July 18, 2026"
created: "2026-07-18"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3a-first-deployment-rollback-july-18-2026.md", "../../../infra/policies/mlops-cloudformation-execution-policy.json", "../../../tests/unit/test_deployment_policy.py", "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-using-service-linked-roles.html", "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create-service-linked-role.html"]
summary: "The first Phase 3A deployment rolled back cleanly because the CloudFormation execution role lacked scoped permission to create the Access Analyzer service-linked role."
---
# AWS security hardening Phase 3A first deployment rollback — July 18, 2026

## Confirmed

The implementation passed hosted CI, and its named diff contained only the
external-access analyzer. The deployment then failed on
`iam:CreateServiceLinkedRole` and reached `UPDATE_ROLLBACK_COMPLETE`. The
SecurityMonitoring stack is metadata-only again, and the account has zero
account analyzers.

The correction adds a dedicated statement for the exact Access Analyzer
service-linked role and service principal. It does not widen the deployment
identity or application roles.

## Synthesis

This is a CloudFormation execution-role boundary, not an auditor or deployment
user failure. Access Analyzer creates its service-linked role automatically
when the first analyzer is enabled, so the execution policy needs the narrow
indirect IAM permission before CloudFormation can create the analyzer.

Related pages:

- [Phase 3A implementation](aws-security-hardening-phase-3a-implementation-july-18-2026.md)
- [Phased AWS security hardening roadmap](../architecture/phased-security-hardening.md)
- [CDK deployment identity and bootstrap boundary](../architecture/cdk-deployment-iam.md)

## Tensions or open questions

- The corrected repository policy MUST pass the local gates and the hosted
  gates. An administrator MUST then install and verify a new live default policy
  version.
- A fresh named diff is required before retrying the SecurityMonitoring stack.
- Analyzer activation, initial-analysis completion, complete finding review,
  alarm health, and application health remain unverified.
- GuardDuty and every later Phase 3 service remain outside this checkpoint.
