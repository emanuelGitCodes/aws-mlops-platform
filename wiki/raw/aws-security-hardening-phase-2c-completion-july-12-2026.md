# AWS security hardening Phase 2C completion — July 12, 2026

## Deployment gate and diff

GitHub Actions run 12 for commit `2ce324b` passed `validate` and `secret-scan`
with no leaks. The scoped Security diff contained exactly six new metric filters
and six new alarms. It did not modify the trail, KMS key, buckets, log group,
SNS topic, subscription, or IAM role.

The existing-stack check again found no Data, Registry, Training, or Monitoring
differences. Ingestion and Serving retained only their previously recorded
Lambda bundle-hash drift, which was excluded by the named Security-only deploy.

## Deployment result

Only `Mlops-Dev-Security` was deployed through `${MLOPS_DEPLOYER_USER_NAME}`. CloudFormation
created the 12 detection resources and reached `UPDATE_COMPLETE` in 31 seconds.

Live AWS reads confirmed:

- exactly six metric filters on `/aws/cloudtrail/mlops-dev-audit`;
- exact AWS Security Hub patterns for CloudWatch.1, .2, .4, .5, .7, and .8;
- namespace `MLOps/Security`, metric value `1`, and default `0`;
- exactly six alarms with `Sum`, 300 seconds, one evaluation period, threshold
  `>= 1`, missing data `notBreaching`, actions enabled, and only the encrypted
  security topic as the alarm action;
- `Mlops-Dev-Security` at `UPDATE_COMPLETE`.

## Controlled alarm test

The restricted `${MLOPS_DEPLOYER_USER_NAME}` identity intentionally attempted the read-only
`iam:ListUsers` operation. AWS denied the call with exit code 254 and
`AccessDenied`, as required by the deployment identity boundary.

CloudTrail recorded the exact controlled event:

- Event ID: `fc5c1610-af9e-4c6b-b7ac-0c7d7020bc61`
- Identity: `arn:aws:iam::${AWS_ACCOUNT_ID}:user/${MLOPS_DEPLOYER_USER_NAME}`
- Event source/name: `iam.amazonaws.com` / `ListUsers`
- Error code: `AccessDenied`
- Read-only management event: `true`

The `UnauthorizedApiCalls` metric reported a sum of 8 for the five-minute
period, and `mlops-dev-security-unauthorized-api-calls` transitioned from OK to
ALARM at 00:38:16 UTC. The confirmed recipient supplied evidence that the alarm
email arrived and contained the correct namespace, metric, period, threshold,
missing-data setting, account, and SNS alarm action.

The other five alarms reached OK after their first non-breaching evaluation.
The unauthorized-call alarm remains in ALARM until the triggering datapoint
ages out; no manual state override is applied.

## Decision and next checkpoint

Phase 2C is complete. The go/no-go decision is GO for Phase 2D after this
completion record is committed and its hosted CI passes. Phase 2D must update
only the existing Data buckets and existing `$20` budget through explicit
Security-to-Data imports.
