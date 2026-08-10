# AWS security hardening Phase 3E implementation — July 24, 2026

## Boundary and pre-state

Phase 3E is limited to account-level S3 Block Public Access in the dev account,
`us-east-1`. AWS Config, Security Hub, security-finding EventBridge routing, and
the deferred GuardDuty retry remain outside this change. Production is untouched.

The repository began clean on `main` at `b5df151`; work is on branch
`feat/phase-3e-account-bpa` as commits `b45cae2` (implementation) and `f9e9749`
(acknowledgement scoping and policy tightening).

A complete read-only pre-flight ran first with the least-privilege
`${AWS_SECURITY_AUDITOR_USER_NAME}` profile, as the roadmap requires before any account-wide
control is applied:

1. The account still reported `NoSuchPublicAccessBlockConfiguration`, matching the
   Phase 3-prep baseline. No account-level configuration existed to overwrite.
2. All six buckets — the CDK bootstrap asset bucket and the five workload buckets
   — already report all four bucket-level BPA settings true, `IsPublic: false`,
   and `BucketOwnerEnforced` ownership.
3. Every wildcard-principal statement in every bucket policy is a **Deny**: the
   TLS enforcement (`Bool` on `aws:SecureTransport`) and the minimum TLS version
   (`NumericLessThan`). No policy grants public access.
4. The only `Allow` statements to non-account principals are to
   `logging.s3.amazonaws.com` (`s3:PutObject`) and `cloudtrail.amazonaws.com`
   (`s3:GetBucketAcl`, `s3:PutObject`), each condition-scoped. Both delivery paths
   are therefore bucket-policy based, not ACL based — and `BucketOwnerEnforced`
   disables ACLs entirely, so the two ACL-related BPA switches cannot affect them.
5. CloudTrail reported `IsLogging: true` with no delivery error, and access-log
   objects were landing the same day under both the `artifacts/` and
   `cloudtrail/` prefixes.
6. `/predict` returned HTTP 200 with the unchanged response contract.

The gate therefore passed on evidence rather than assumption: account BPA is
expected to be a no-op for every existing access path, because each bucket
already enforces locally what the account setting will enforce globally.

## Implemented scope

1. `infra/stacks/security_monitoring_stack.py` creates one
   `AwsCustomResource` when the existing `account_bpa` flag is true.
   CloudFormation has no resource type for the account-level setting, so the
   S3 Control API is called directly. This reuses the pattern already proven by
   the budget notifications in the Data stack rather than introducing a new one.
2. All four settings — `BlockPublicAcls`, `IgnorePublicAcls`,
   `BlockPublicPolicy`, `RestrictPublicBuckets` — are set together in a module
   constant. A partial block would leave one public-exposure route open.
3. `on_update` repeats the `putPublicAccessBlock` call, so a later change to the
   four settings cannot synthesize without reaching the account. `on_delete`
   calls `deletePublicAccessBlock`, so a failed deployment rolls back to the
   exact recorded pre-state instead of orphaning an account-wide control the
   repository no longer manages.
4. The account id is threaded as the `AWS::AccountId` pseudo-parameter; no
   account literal reaches the template. A unit test asserts this directly.
5. The custom resource carries no tags. `Custom::AWS` is not a taggable
   CloudFormation type, so a `Tags.of()` block matching the analyzer and detector
   would have silently done nothing; it was written, observed to produce no
   template output, and removed rather than left as misleading dead code.
6. `account_bpa` joins `IMPLEMENTED_SERVICE_FLAGS` in this same change, honoring
   the flag contract added on July 24. The parametrized guard test consequently
   covers three remaining unimplemented flags instead of four.
7. `infra/config/dev.yaml` enables `account_bpa`. Production and the other four
   deferred flags remain false.
8. The provider role receives only the two actions the calls actually make,
   `s3:PutAccountPublicAccessBlock` and `s3:DeleteAccountPublicAccessBlock`. An
   initial draft also granted `s3:GetAccountPublicAccessBlock`, which no call
   path uses; on a wildcard resource that is precisely the unused-grant debt
   Phase 5 exists to remove, so it was dropped before deployment.

## A flag-gated acknowledgement must be scoped to its flag

The first implementation added the two cdk-nag acknowledgements unconditionally.
Their constructs exist only where `account_bpa` is true, and `_construct_at`
deliberately raises when a path matches no construct, so any environment with the
flag disabled could no longer synthesize.

The rollback path is what made this material rather than cosmetic: flipping
`account_bpa` back to false would have left dev unable to synthesize its own
revert, so the control could only have been removed by reverting the entire
commit. `Acknowledgement` therefore gained an optional `requires_service` naming
the flag its construct depends on, and `apply_security_checks` now receives the
`PlatformConfig` and skips those entries elsewhere. Acknowledgements without the
field keep raising on a stale path, which is the tripwire that catches a
construct removed without its acknowledgement. A regression test synthesizes dev
with `account_bpa` forced false and asserts the custom resource is absent.

This is the first config-conditional acknowledgement in the repository, and
sub-phases 3C and 3F will need the same treatment.

Separately, and **not** caused by this phase: `make synth ENV=prod` already
failed on `main` before Phase 3E, because a serving acknowledgement hardcodes
`ChurnApi/DeploymentStage.dev`, which matches no construct under the prod stage
name. Verified by running the target on `main`. CI synthesizes `env=dev` only, so
it never surfaced. That defect is left for its own change rather than widened
into this one.

## No execution-policy rotation

The repository execution policy is deliberately **not** touched, and this was
verified rather than assumed, because a rotation would consume the last of five
IAM version slots and trip the CIS IAM-policy-change alarm.

The provider Lambda holds the `s3:*AccountPublicAccessBlock` actions in its own
inline policy and makes the API call itself; CloudFormation never needs them.
The live policy already grants the Lambda lifecycle, the role and inline-policy
lifecycle, and `iam:PassRole` for `Mlops-Dev-*` roles to `lambda.amazonaws.com`.
The decisive evidence is that the identical custom-resource pattern is already
deployed and working in this account under the same live default `v8`.

The known divergence — the repository retaining the `GuardDutyServiceLinkedRole`
statement while live `v8` lacks it — therefore remains intact and still
reconciles at the next sub-phase rotation, now 3C.

## Local verification

- `make lint`: passed, 49 files formatted.
- `make typecheck`: passed, 34 source files, zero errors.
- `make test`: 71 passed, up from 70. Implementing `account_bpa` removed one
  parametrized guard case, and the account-BPA contract test and the
  flag-disabled synthesis regression test added two.
- `make security`: lock check resolved 121 packages, dependency audit found no
  known vulnerabilities, and all eight dev stacks synthesized with cdk-nag.
- Two new cdk-nag acknowledgements were required and were taken from the actual
  synth failures rather than predicted: `AwsSolutions-IAM4` for the provider
  role's `AWSLambdaBasicExecutionRole`, and `AwsSolutions-IAM5[Resource::*]` for
  the custom-resource policy. The account-level actions are not bucket-scoped and
  AWS accepts only `*` as their resource.
- The synthesized call was inspected directly to confirm CDK resolves
  `service="S3Control"` to the `@aws-sdk/client-s3-control` package: the bundled
  provider normalizes the service name through a lookup table containing
  `s3control: "s3-control"`. A silently wrong package name was the more likely
  failure mode and is now ruled out.
- Two security tripwires were updated deliberately after reading what changed:
  the `security_monitoring` IAM fingerprint, previously the SHA-256 of `{}`, and
  the literal-wildcard baseline. The stack's IAM consists of exactly the provider
  role — assumed only by `lambda.amazonaws.com`, carrying only the basic
  execution managed policy, with no inline policies — and the two-action
  custom-resource policy attached only to that role.

## Named diff

`make diff-stack STACK=Mlops-Dev-SecurityMonitoring` adds four resources and
modifies or deletes nothing: the `Custom::AWS` resource, its custom-resource
policy, the provider role, and the provider Lambda. The Phase 3A analyzer does
not appear in the diff, and no GuardDuty resource appears.

## Deployment

`make deploy-stack STACK=Mlops-Dev-SecurityMonitoring` completed in 48.6 seconds
after hosted CI passed on both commits. Four resources were created — the
provider role, the custom-resource policy, the provider Lambda, and the
`Custom::AWS` resource — and `CDKMetadata` was updated. Nothing was modified or
deleted, and no other stack was touched.

The pre-deployment risk that could not be closed locally is now closed
empirically: with `install_latest_aws_sdk=False` the provider loads the
s3-control client dynamically from the Lambda runtime's bundled AWS SDK v3, and
whether that client ships in `nodejs24.x` was not establishable from the
repository. The custom resource reached `CREATE_COMPLETE`, so the client is
present. No fallback to `install_latest_aws_sdk=True` was needed, which matters
because that setting would have made deployment depend on the npm registry at
create time.

As predicted, the deployment carried a real template change and therefore moved
the stack off the leftover `UPDATE_ROLLBACK_COMPLETE` marker left by the July 18
GuardDuty subscription rejection. It now reports `UPDATE_COMPLETE`.

## Live verification

Reported at resource granularity, per the repository's reporting rule.

- `make verify-deploy SINCE=2026-07-24` lists exactly the four created resources
  under `Mlops-Dev-SecurityMonitoring`. The Serving, Ingestion, and Monitoring
  entries in the same output belong to the earlier reconciliation deploy at
  20:47–20:48 UTC and are unrelated.
- `get-public-access-block` for the account returns all four settings `true`,
  where the pre-flight recorded `NoSuchPublicAccessBlockConfiguration`.
- The Phase 3A analyzer is still `ACTIVE`, `ACCOUNT` type.
- All six `mlops-dev-security-*` alarms remain `OK`. The unrelated
  `Endpoint5xxAlarm` in the Monitoring stack sits at `INSUFFICIENT_DATA`, which
  is its pre-existing state and not a consequence of this phase.
- CloudTrail reports `IsLogging: true` with a delivery timestamp inside the
  deployment window and no delivery error.
- All six buckets, including the CDK bootstrap asset bucket, remain listable by
  their workload identities. Nothing became unreadable.
- `/predict` returns HTTP 200 with the unchanged response contract: exactly the
  keys `churn` and `churn_probability`.
- `make diff-stack STACK=Mlops-Dev-SecurityMonitoring` now reports no
  differences, so the deployed template matches the repository.

Two verifications could not be completed with the least-privilege auditor
identity and are recorded as gaps rather than passes. `budgets:ViewBudget` is
denied, so the `$20` budget was confirmed only indirectly — the Data stack that
owns it shows no resource change in `verify-deploy`. And the CloudTrail
`lookup-events` query for `PutAccountPublicAccessBlock`, intended to prove the
call came from the provider role rather than a human in the console, returned
empty; CloudTrail lookup lags recent events by up to roughly fifteen minutes, so
this should be re-run during the observation window rather than treated as a
negative result.

The auditor denial itself is expected to trip the CIS unauthorized-API-call
alarm, which is the known and previously recorded behavior of this identity.

## Rollback and next checkpoint

Rollback is a revert of both commits followed by a redeploy of the single stack:
CloudFormation deletes the custom resource, which fires
`deletePublicAccessBlock` and restores the recorded pre-state. No policy version,
analyzer, key, or bucket is involved. The revert must cover the whole change
rather than only flipping the flag — that is the point of the `requires_service`
work above, without which the flag-off state could not synthesize.

The observation window is open. Before the 3E go/no-go it should confirm a fresh
server-access-log object delivered after the deployment, CloudTrail delivery
advancing at least once more, the six alarms still `OK`, unchanged daily cost
(account BPA is free), no new Access Analyzer finding, and the deferred
provenance lookup above. Sub-phase 3C, whose gated deployment doubles as the
Free-plan availability test for AWS Config, follows the go/no-go.
