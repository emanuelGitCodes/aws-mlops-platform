---
type: decision
title: Paid Phase 3 security services — GuardDuty cost and timing
created: "2026-08-02"
updated: "2026-08-02"
sources: ["https://aws.amazon.com/guardduty/pricing/", "https://aws.amazon.com/elasticloadbalancing/pricing/", "../../../infra/stacks/security_monitoring_stack.py", "../../../infra/config/dev.yaml", "../sources/aws-free-plan-account-service-limits-july-18-2026.md", "../sources/aws-security-hardening-phase-3b-first-deployment-rollback-july-18-2026.md"]
summary: "GuardDuty costs roughly a dollar a month here and is approved, but deliberately waits for the planned EC2 and load-balancer website, where its detections finally apply."
---
# Paid Phase 3 security services — GuardDuty cost and timing

## Confirmed

- **Nothing is being scanned today.** `guardduty: false` in both
  `infra/config/dev.yaml` and `infra/config/prod.yaml`, and a read-only
  `guardduty list-detectors` on 2026-08-02 returned
  `SubscriptionRequiredException` — the account cannot call the service at
  all, let alone have a detector. This is the same Free-plan block that rolled
  back sub-phase 3B.
- **The 3B design never included S3 scanning.** `GUARDDUTY_DISABLED_FEATURES`
  in `infra/stacks/security_monitoring_stack.py` explicitly disables
  `S3_DATA_EVENTS`, `EKS_AUDIT_LOGS`, `EBS_MALWARE_PROTECTION`,
  `RDS_LOGIN_EVENTS`, `LAMBDA_NETWORK_LOGS`, and `AI_ANALYST`. Malware
  Protection for S3 is a separate opt-in that was never configured.
- **Measured event volume, 2026-08-02.** The `IncomingLogEvents` metric for
  the `/aws/cloudtrail/mlops-dev-audit` log group over the preceding seven
  days totalled **59,628 events**, averaging ~8,500/day, including one 17,895
  spike from the Phase 2E synthetic burst and that day's deployments. Read
  with the administrator profile, because the auditor lacks
  `cloudwatch:GetMetricStatistics`.
- **Published rates (us-east-1, read 2026-08-02).** GuardDuty foundational
  detection is **$4.00 per million CloudTrail management events**; VPC Flow
  and DNS logs are $1.00/GB for the first 500 GB; S3 Protection is $0.80 per
  million data events; Malware Protection for S3 is $0.09/GB plus $0.215 per
  1,000 objects. The **30-day free trial is per account, per Region, and per
  protection plan.** An Application Load Balancer is **$0.0225/hour** plus
  $0.008 per LCU-hour.

## Synthesis

At roughly 260,000 management events per month, foundational GuardDuty would
cost this account **about $1/month**. Every other billing dimension is $0
today: there are no VPC resources, so no flow or DNS logs; S3 data events and
malware scanning are disabled by design. Published warnings that GuardDuty is
expensive describe accounts dominated by exactly those disabled dimensions,
which makes them true in general and inapplicable here.

The service is therefore **approved in principle**, but deliberately deferred
to a trigger rather than enabled now: a planned secondary website publishing
project data from **EC2 behind a load balancer**. The reasoning is that both
sides of the equation move at that point, and value moves further than cost.
GuardDuty's foundational detections — cryptomining, command-and-control
traffic, compromised instances — target the workload class this account does
not yet have. Enabling it today buys credential-anomaly detection that partly
duplicates the deployed `unauthorized-api-calls` alarm; enabling it once an
instance is internet-facing buys coverage nothing in the current stack
provides. See the [phased hardening roadmap](../architecture/phased-security-hardening.md).

Three consequences follow, and each is a checkpoint rather than a footnote:

- **Re-price at the trigger; do not reuse the $1 figure.** EC2 and an ALB
  produce VPC Flow Logs, which become billable. Small for a low-traffic site,
  but no longer zero.
- **The website, not GuardDuty, is the budget event.** An ALB alone is
  ~$16.43/month before LCUs, plus the instance, against the existing **$20**
  budget and its 50/80/100% alerts. Raising the budget is a prerequisite
  conversation for the website and is independent of any security service.
- **The trial burns from the moment of enablement**, so the service should not
  be switched on early to look around.

The Free-plan upgrade remains the real gate. It ends the account's
cannot-be-charged guarantee for every service at once, which is a materially
larger decision than a one-dollar subscription. Sub-phase 3D Security Hub sits
behind the same billing gate and inherits the same decision.

## Tensions or open questions

- The paid-plan upgrade still has no date, so the trigger is a condition
  rather than a schedule.
- The cost figures are a point-in-time reading. Management-event volume rises
  with deployment activity, and the seven-day window measured here included an
  unusually busy day.
- Whether 3D Security Hub is worth enabling at all is genuinely open: its CIS
  checks partly duplicate the six metric-filter alarms already deployed in
  Phase 2C, and unlike GuardDuty no equivalent cost measurement has been done.
