---
type: "source"
title: "AWS security hardening Phase 5A proxy execution role — August 5, 2026"
created: "2026-08-05"
updated: "2026-08-05"
sources: ["../../raw/aws-security-hardening-phase-5a-proxy-execution-role-august-5-2026.md", "../../../infra/stacks/shared.py", "../../../infra/stacks/serving_stack.py", "../../../infra/security_checks.py", "../../../tests/unit/test_serving_stack.py"]
summary: "The proxy is the first of four roles off AWSLambdaBasicExecutionRole, trading account-wide log permissions for writes to its own group, verified by the log event a wrong scope would have silently lost."
---
# AWS security hardening Phase 5A proxy execution role — August 5, 2026

## Confirmed

- **Phase 5 has started.** 5A converts the proxy Lambda's execution role, the
  first of the four the phase map takes one at a time: proxy, model, deploy,
  then pipeline.
- **The proxy no longer carries `AWSLambdaBasicExecutionRole`.** That AWS
  managed policy grants `logs:CreateLogGroup`, `CreateLogStream` and
  `PutLogEvents` on `Resource: "*"`. The replacement role carries no managed
  policy at all and grants writes to the function's own log group plus the one
  business permission the proxy already had, `sagemaker:InvokeEndpoint` on a
  single endpoint ARN. `iam list-attached-role-policies` on the live role
  returns no rows.
- **The deployment replaced the role one-for-one.** A template diff against the
  pre-change synthesis shows `ProxyFnServiceRole` and its default policy removed,
  `ProxyFnRole` and its default policy added, and nothing else changed. The
  serving IAM fingerprint was rebaselined only after that comparison.
- **The component check passed live.** `make smoke` returned 6 passed, and the
  proxy's `inference_response` event still appears in its log group afterwards.
  The six `mlops-dev-security-*` alarms stayed `OK` and none fired for this
  deployment.
- **Acknowledgements fell from 46 to 45**, and the pre-flight inventory recorded
  that 25 of the original 46 name Phase 5.

## Synthesis

The proxy was the right role to start with for two reasons that have nothing to
do with difficulty. It is the public entry point, so the blast radius of
account-wide log permissions is widest there; and its business permission was
already exact, which left the managed policy as the only variable and made the
change a clean test of the pattern the remaining three roles will follow.

The check that carries the weight is the log event, not the HTTP 200. The new
policy is what authorizes `PutLogEvents`, so a scope that was too narrow would
have failed logging **silently** while `/predict` kept returning 200 — the
platform would have looked healthy and stopped recording inference events. That
is why the component check reads the log group after the smoke run rather than
trusting the API response alone.

Two phases composed here without being designed to. Phase K gave each function
an owned `logs.LogGroup`, which is what makes `logs:CreateLogGroup` unnecessary:
the function never creates a group, so the permission can be dropped entirely
rather than merely narrowed. Had 5A come first, the role would still have needed
group-creation rights against the generated `/aws/lambda/` name.

`least_privilege_logs` is deliberately opt-in rather than the default. The
roadmap converts one role per change set with its own component check, and a
default would have flipped all four Lambdas at once — exactly the batch change
the operating rule exists to prevent.

The gate proved itself mid-change. Removing the CDK-generated role left the
`ProxyFn/ServiceRole` acknowledgement matching zero constructs, and
`_construct_at` failed synthesis rather than letting a stale suppression sit
unnoticed against a construct that no longer exists.

## Tensions or open questions

- **The acknowledgement count fell, but not because a wildcard was removed.**
  The prediction before implementing was that `AwsSolutions-IAM4` would trade
  for `AwsSolutions-IAM5`, since a log-stream ARN needs a `:*` suffix. It did
  not, because `grant_write` emits the group ARN as an `Fn::GetAtt` and cdk-nag
  does not read an intrinsic as a literal wildcard. **A log group's
  CloudFormation `Arn` attribute resolves with a `:*` stream suffix at deploy
  time**, which is precisely why `PutLogEvents` works. The wildcard is real and
  necessary; the linter cannot see it. The gain is one log group instead of
  every log group — not the elimination of a wildcard, and the count should not
  be read as if it were.
- **Three managed-log-policy acknowledgements can never be resolved by Phase 5.**
  They sit on CDK-generated provider Lambdas — the S3 notification handler, the
  budget custom-resource provider, the account-BPA provider — whose roles this
  repository does not create. Their reasons promise a Phase 5 replacement that
  will not come. Recorded during the 5A pre-flight, deliberately not corrected
  in that change set.
- **No observation window has been opened for 5A.** The runtime evidence is a
  single smoke run immediately after deployment; nothing yet shows the proxy
  logging correctly over a period, or during an endpoint update.
- **5B is a step up in risk.** `ModelExecutionRole` governs the model's S3
  access, so a wrong scope breaks inference rather than logging, and unlike 5A
  that failure would not be visible in a smoke test asserting only that
  `/predict` returns 200.
