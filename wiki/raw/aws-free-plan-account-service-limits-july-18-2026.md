# AWS Free-plan account service limits — July 18, 2026

## Objective and boundary

Record the confirmed account-level explanation for the Phase 3B GuardDuty
`SubscriptionRequiredException` rollback and its consequences for the rest of
the phased security roadmap. This is a console observation only: no AWS
configuration was changed, no wizard was completed, and no plan upgrade was
performed.

## Observed console evidence

The Billing and Cost Management home page for account `${AWS_ACCOUNT_ID}`,
viewed with the `${AWS_ADMIN_USER_NAME}` console identity, displayed the
banner "Your free plan account does not get charged" with an **Upgrade plan**
action, `$139.70 USD` of credits remaining, and `131` days remaining in the
free-plan period. This confirms the account is on the AWS **Free account
plan** introduced with the July 2025 free-tier revision, not a paid-plan
account using free-tier allowances.

Separately, the AWS Config console rendered its full three-step setup wizard
(recording strategy, service-linked role, delivery-channel bucket
`config-bucket-${AWS_ACCOUNT_ID}`). The wizard was cancelled without creating
any resource, because completing it would create a recorder, delivery channel,
service-linked role, and S3 bucket outside CloudFormation ownership.

## Interpretation

The Free account plan restricts the account to a subset of AWS services.
Paid-only security services — including GuardDuty and Security Hub — are
outside that subset, and calls to them are rejected at the account level with
HTTP 403 `SubscriptionRequiredException` ("The AWS Access Key Id needs a
subscription for the service"). This is a billing-plan boundary, not an IAM
denial and not a CloudFormation or template defect.

This resolves the question the Phase 3B first-deployment rollback record left
open: the CloudFormation GuardDuty provider sent a correct `CreateDetector`
request, and the service refused to bootstrap the subscription because the
plan forbids the service entirely. No retry can succeed while the account
remains on the Free plan.

The explanation is retroactively consistent with the Phase 0 baseline:
read-only probes returned `SubscriptionRequiredException` for both GuardDuty
and Security Hub (a plan-level block affects reads as well as writes), while
AWS Config answered its describe call normally with zero recorders. Config is
therefore plausibly inside the Free plan's allowed set, but only a first write
(`CreateConfigurationRecorder`) proves it, and that write must happen through
the gated flag-controlled CloudFormation path in the SecurityMonitoring
stack — never through the console wizard.

## Consequences for the roadmap

- Phase 3B (GuardDuty) is hard-blocked until the account is upgraded to the
  paid plan. Pull request 5 stays draft.
- The later Security Hub sub-phase is blocked by the same boundary.
- The AWS Config sub-phase may be possible on the Free plan; its scoped
  CloudFormation deployment doubles as the availability test, with automatic
  rollback as the safety net.
- Upgrading the plan is a deliberate billing decision, not a technical fix:
  remaining credits carry over and continue to offset charges, but the
  "cannot be charged" guarantee ends, and real billing begins once credits
  are exhausted. GuardDuty itself starts with a 30-day free trial, and the
  Phase 2 budget alerts (50/80/100% of the `$20` budget) and six CIS alarms
  are already live as guardrails if the upgrade proceeds.

## Decision and next checkpoint

Do not enable any Phase 3 service manually. Decide on the paid-plan upgrade
first; only after an explicit upgrade decision should Phase 3B repeat its
full gate sequence (live stop gate, execution-policy rotation, named diff,
named deployment, finding/cost/application verification).
