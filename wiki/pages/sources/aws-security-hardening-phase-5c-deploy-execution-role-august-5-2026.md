---
type: "source"
title: "AWS security hardening Phase 5C deploy execution role — August 5-6, 2026"
created: "2026-08-05"
updated: "2026-08-06"
sources: ["../../raw/aws-security-hardening-phase-5c-deploy-execution-role-august-5-2026.md", "../../../infra/stacks/serving_stack.py", "../../../infra/security_checks.py", "../../../src/serving/deploy_handler.py", "../../../tests/unit/test_serving_stack.py", "../../../tests/unit/test_security_checks.py"]
summary: "The deploy role loses both the managed log policy and the repository's last real Resource '*', proven by a full data-to-endpoint run rather than a warm smoke test."
---
# AWS security hardening Phase 5C deploy execution role — August 5-6, 2026

## Confirmed

- **`DeployFn` carries no managed policy and no wildcard resource.** It held two
  broad grants: `AWSLambdaBasicExecutionRole`, whose three log actions applied to
  every log group in the account including the audit trail's, and a hand-written
  six-action SageMaker statement on `Resource: "*"`. The replacement grants
  writes to the function's own log group and names each SageMaker resource the
  handler builds.
- **The repository's last real literal wildcard is gone.** What remains in
  `test_literal_wildcard_resource_baseline_has_not_grown` is Phase 3E's
  account-level Block Public Access, where AWS accepts only `"*"` as the
  resource for the `s3:*AccountPublicAccessBlock` actions.
- **The deployment replaced the role one-for-one.** A template diff against the
  pre-change synthesis shows `DeployFnServiceRole` and its default policy
  removed, `DeployFnRole` and its default policy added, and no other IAM
  resource modified. `make verify-deploy` reported six changed resources: those
  four, the function's re-pointed `Role`, and `ProxyFn`.
- **The component check was a full end-to-end run, not a warm `/predict`.** 1,200
  new customer rows went raw → validate → curated → preprocess → train →
  evaluate → register. Training read 5,770 train and 1,236 validation rows,
  confirming the new data reached the model. The auto-approval fired EventBridge
  → `DeployFn`, which logged `approved_challenger_deployed` with
  `action: "updated"` and a populated `test_auc`, then the endpoint reached
  `InService` and `make smoke` returned 6 passed.
- **Acknowledgements rose 40 → 41 in dev.** Two coarse entries were replaced by
  three naming exact ARNs.
- **The deploy set off one alarm, and it is fully attributed.**
  `mlops-dev-security-iam-policy-changes` fired at 2026-08-06T00:00:53Z on three
  events and self-cleared five minutes later. All three were the deploy's own IAM
  writes by the CDK CloudFormation execution role: `PutRolePolicy` onto the new
  role, `DeleteRolePolicy` off the old one, and the `DetachRolePolicy` that
  removed `AWSLambdaBasicExecutionRole`. `unauthorized-api-calls` stayed `OK`
  through both the deployment and the component check.
- **A billable pipeline run succeeded.** Phase 5 has required one since the
  roadmap was written; it is now on record.

## Synthesis

5C is the first Phase 5 role where the managed policy was *not* the interesting
part. 5A's proxy had an already-exact business permission, so removing
`AWSLambdaBasicExecutionRole` was the whole change. `DeployFn` also held the
repository's worst hand-written grant: six SageMaker actions on `Resource: "*"`
in the role that reacts to a model-registry approval. That combination means a
compromised deploy Lambda could point *any* endpoint in the account at *any*
model — a far larger blast radius than over-broad logging.

The scoping that carries the most security weight is `DescribeModelPackage` on
`model-package/<group>/*`. The package ARN arrives inside the EventBridge event
detail, so it is the one input to this handler that an attacker might influence.
Pinning it to the platform's own group is what stops a crafted event walking the
Lambda onto a foreign package.

The check design follows 5B's lesson rather than 5A's. A warm `/predict`
exercises the proxy, so it says nothing about this role; only a real registry
approval drives `create_model` → `create_endpoint_config` → `describe_endpoint`
→ `update_endpoint` → `describe_model_package`. Rather than force an approval
by re-approving an existing package as 5B did, 5C pushed genuinely new data
through the whole platform, which validated the ingestion and training paths as
a by-product and produced the billable run 5D was blocked on.

One deliberate omission was proven correct by that run. The plan recorded an
unresolvable guess: whether `CreateModel` also authorizes against the model
package named in `Containers[]`. It does not — `CreateModel` succeeded against a
package the role has no `CreateModel` grant on. Following 5B's precedent of
granting only what evidence requires, rather than pre-emptively widening, cost
nothing and kept the policy honest.

The `{group}` token forced a small interface decision. Acknowledgement strings
now need the model package group, which differs per environment, and
`resolved_acknowledgements` was already taking `(env_name, prefix)`. Taking the
whole `PlatformConfig` instead means the next token costs no signature change.

## Tensions or open questions

- **No observation window has been opened for 5C.** The runtime evidence is one
  end-to-end run immediately after deployment. Unlike 5B, no *natural* cold start
  has been observed under the new role — though that matters less here, since a
  cold container exercises the model role, not the deploy role.
- **One hedge in the policy is untested.** `CreateEndpoint`/`UpdateEndpoint` name
  both the endpoint and the endpoint-config, chosen as the safe direction because
  omitting a required resource breaks the deploy path. This run does not
  determine whether the endpoint-config entry is required; if it is not, it is an
  inert over-grant that a later pass should trim.
- **The bundled Lambda asset hash is not reproducible**, so a deploy from a cold
  `cdk.out` republishes all four functions' code with no source change. Traced to
  vendored `__pycache__/*.pyc` whose headers embed mtimes that `pip install -t`
  rewrites. `lambda_code.py` fixes this on the source side only. It undermines
  resource-level deploy reporting and needs its own change set.
- **Seven orphaned log groups survive in dev**, and every platform Lambda has a
  superseded `/aws/lambda/<function>` twin alongside its Phase K `*Logs*` group.
  Verified non-CloudFormation-managed; deletion was handed to the operator rather
  than performed. An eighth candidate is noted but unconfirmed.
- **The drift → retrain edge has never fired.** Both `RetrainTriggerFn` log
  groups report no events ever, and this run started the pipeline by hand rather
  than through `retrain_handler`. The closing edge of the drift loop is
  unexercised in this account, which no Phase 5 record had previously stated.
- **Three managed-log-policy acknowledgements still promise a Phase 5 fix that
  cannot come**, on CDK-generated provider Lambdas this repository does not
  create. Carried forward from the 5A pre-flight, still uncorrected.
