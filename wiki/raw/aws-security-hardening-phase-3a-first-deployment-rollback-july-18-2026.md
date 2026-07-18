# AWS security hardening Phase 3A first deployment rollback — July 18, 2026

## Deployment gate and attempt

The isolated Phase 3A implementation commit passed both hosted validation jobs.
A named SecurityMonitoring diff showed exactly one new
`AWS::AccessAnalyzer::Analyzer` and no unrelated stack change. Read-only live
inventory then confirmed that the SecurityMonitoring stack was healthy and
metadata-only, no account analyzer existed, and the later Phase 3 services
remained disabled.

The named SecurityMonitoring deployment attempted to create the external-access
analyzer. AWS rejected the request because the CloudFormation execution role
could not call `iam:CreateServiceLinkedRole` for the Access Analyzer
service-linked role.

## Rollback evidence

CloudFormation reached `UPDATE_ROLLBACK_COMPLETE`. The stable stack again
contains only `AWS::CDK::Metadata`, and a fresh read-only inventory reports zero
account analyzers. No analyzer or service-linked role was deleted, adopted, or
created manually.

## Cause and correction

The prepared execution policy covered the Access Analyzer resource lifecycle,
but its service-linked-role authorization was limited to the later AWS Config
sub-phase. Creating the first account analyzer causes Access Analyzer to create
`AWSServiceRoleForAccessAnalyzer` automatically.

The repository policy now grants only `iam:CreateServiceLinkedRole` on:

```text
arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/access-analyzer.amazonaws.com/AWSServiceRoleForAccessAnalyzer
```

The statement also requires
`iam:AWSServiceName=access-analyzer.amazonaws.com`. A focused unit test locks
the exact action, resource, and condition. The deployment identity and all
application runtime roles remain unchanged.

## Retry gate

Before another deployment, the corrected repository policy must pass local and
hosted gates. An administrator must then install it as a new default version of
the existing CloudFormation execution policy and verify that the live document
matches the sanitized repository source. The named diff must be reviewed again
before retrying only the SecurityMonitoring stack.

Phase 3A remains incomplete until the analyzer is active, its initial analysis
has completed, and every active public or cross-account finding is explained.
GuardDuty remains disabled, and Phase 3B must not begin.

## External references

- AWS IAM Access Analyzer service-linked role documentation:
  https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-using-service-linked-roles.html
- AWS IAM service-linked role permission documentation:
  https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create-service-linked-role.html
