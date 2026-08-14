---
type: "source"
title: "AWS security hardening Phase 3E implementation and deployment — July 24, 2026"
created: "2026-07-24"
updated: "2026-08-14"
sources: ["../../raw/aws-security-hardening-phase-3e-implementation-and-deployment-july-24-2026.md", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/security_checks.py", "../../../infra/config/dev.yaml", "../../../tests/unit/test_security_monitoring_stack.py"]
summary: "Account-level S3 Block Public Access is live in dev via a flag-gated custom resource, with a clean pre-flight, a four-resource deploy, and resource-level verification."
---
# AWS security hardening Phase 3E implementation and deployment — July 24, 2026

## Confirmed

Sub-phase 3E enabled account-level S3 Block Public Access in the dev account,
`us-east-1`, with all four settings true. The account previously reported
`NoSuchPublicAccessBlockConfiguration`.

The mandatory read-only pre-flight passed on evidence rather than assumption. All
six buckets — the CDK bootstrap asset bucket and the five workload buckets —
already carried all four bucket-level settings, reported `IsPublic: false`, and
used `BucketOwnerEnforced` ownership. Every wildcard-principal bucket statement
proved to be a TLS-enforcing **Deny**, not a public grant; the only `Allow`
statements to non-account principals go to `logging.s3.amazonaws.com` and
`cloudtrail.amazonaws.com` under conditions. Both log-delivery paths are
therefore bucket-policy based, and `BucketOwnerEnforced` disables ACLs outright,
so the two ACL-related settings could not affect them.

CloudFormation has no resource type for the account-level setting, so the phase
reuses the `AwsCustomResource` pattern already proven by the budget notifications
in the Data stack. The deployment created four resources in 48.6 seconds and
modified nothing else. Live checks confirmed all four settings true, the Phase 3A
analyzer still `ACTIVE`, the six security alarms still `OK`, every bucket still
listable, `/predict` unchanged, and a later `cdk diff` reporting no
differences.

No execution-policy rotation was required. The provider Lambda holds the
account-level actions itself, and the live default `v8` already covers the
Lambda, role, and `PassRole` lifecycle CloudFormation performs. The deliberate
divergence in which the repository retains the `GuardDutyServiceLinkedRole`
statement therefore survives intact for the 3C rotation, and the last IAM policy
version slot stays free.

## Synthesis

Three findings are worth carrying forward beyond this sub-phase.

**A flag-gated acknowledgement MUST carry the same gate as its flag.** The first
implementation registered its two cdk-nag acknowledgements unconditionally, but
their constructs exist only where `account_bpa` is true, and `_construct_at`
deliberately raises when a path matches no construct. The consequence was not
cosmetic: flipping the flag back to false would have left dev unable to
synthesize its own revert, so the control could only be removed by reverting the
whole change. `Acknowledgement` now carries an optional `requires_service`, and
`apply_security_checks` receives the [`PlatformConfig`](../architecture/permissions.md)
to skip those entries elsewhere. Sub-phases 3C and 3F will need the same
treatment. This is separate from the pre-existing failure of `make synth
ENV=prod`, which was verified to predate Phase 3E: a serving acknowledgement
hardcodes the dev deployment-stage name, and hosted CI synthesizes `env=dev` only,
so nothing surfaced it.

**Account BPA was safe here precisely because it was redundant.** Every bucket
already enforced locally what the account setting now enforces globally, which is
why the pre-flight could predict a no-op for existing access paths. The value is
prospective: buckets this repository does not create, and future bucket-level
mistakes, are now covered.

**An unverifiable risk was closed by the deployment itself rather than by
argument.** Whether the `nodejs24.x` runtime bundles the s3-control client could
not be established from the repository, and the mitigation would have been
`install_latest_aws_sdk=True` — which trades a create-time npm-registry
dependency for reproducibility. The custom resource reaching `CREATE_COMPLETE`
settled it without that trade.

Sequencing and root-cause context live in the
[Phase 3 plan revision](phase-3-plan-revision-under-the-aws-free-plan-july-19-2026.md)
and the [Free-plan service limits](aws-free-plan-account-service-limits-july-18-2026.md);
the maintained roadmap is the
[phased hardening plan](../architecture/phased-security-hardening.md).

## Tensions or open questions

- The CloudTrail provenance gap is now closed. A re-run of `lookup-events` after
  the initial lag returned a single `PutAccountPublicAccessBlock` event at the
  deployment timestamp, attributed to the CloudFormation-created provider role
  rather than to any human identity. The setting was therefore applied through
  the gated path, not the console.
- Both verification gaps are now closed, and the observation window with them.
  The budget was confirmed on 2026-07-30 from the Billing console under an
  identity that holds `budgets:ViewBudget`, since the auditor profile does not:
  `${MONTHLY_BUDGET_NAME}` is a `$20.00` monthly cost budget with exactly the
  three 50/80/100 percent actual-cost alerts, all reporting not exceeded. Spend
  was `$0.00` actual against a `$0.08` month-to-date forecast, which also settles
  the unchanged-cost criterion — account BPA is a free control.
- The remaining observation criteria were satisfied by elapsed evidence rather
  than by a single check: access-log objects delivered on 2026-07-28 and
  2026-07-30, well after the deployment; CloudTrail delivery advancing with no
  error; the six security alarms still `OK`; and the analyzer still `ACTIVE`
  with zero active findings.
- The custom resource's physical id embeds the environment name while the
  setting it manages is account-wide, so a future prod rollout in the same
  account would put two CloudFormation resources in contention over one setting.
- `make synth ENV=prod` remains broken for the pre-existing stage-name reason
  above, tracked separately from this phase.
