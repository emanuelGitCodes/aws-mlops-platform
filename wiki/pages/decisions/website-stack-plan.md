---
type: decision
title: Website stack plan, CloudFront over an ALB
created: "2026-08-14"
updated: "2026-08-14"
sources: ["../../../infra/app.py", "../../../infra/stacks/website_stack.py", "../../../infra/stacks/shared.py", "../../../infra/stacks/serving_stack.py", "../../../infra/security_checks.py", "../../../infra/policies/mlops-cloudformation-execution-policy-extension.json", "../../../website/backend/app.py", "../../../src/common/signing.py", "../../../tests/unit/test_website_stack.py", "../../../tests/unit/test_backend_app.py", "../architecture/phased-security-hardening.md", "../architecture/cdk-deployment-iam.md", "./phase-3-paid-security-services.md", "./platform-design.md"]
summary: "A tenth stack serves a public demo website from one EC2 container behind CloudFront, with a DynamoDB mailing list, because an ALB or RDS alone consumes most of the $20 monthly budget."
---
# Website stack plan, CloudFront over an ALB

**This stack is ON HOLD as of 2026-08-14, and it MUST NOT be deployed in its
current shape.** The website moves to a local-first rebuild with three
containers. Read [the local-first rebuild](website-local-first-rebuild.md)
first; it holds the current direction and says which decisions on this page
survive.

`Mlops-Dev-Website` is written and tested, and not deployed. Both environments
synthesize, every gate passes, and no AWS resource exists. The single-container
design below is what the rebuild replaces. The cost decisions, the SigV4 proxy
boundary, and the execution-policy grants all carry forward.

## Confirmed

- **The goal.** A public website shows the model schema, shows the latest
  evaluation report from the artifacts bucket, lets a visitor test the model,
  and stores a mailing list of people who opt in. Function comes before UI.
- **The budget constraint drives the shape.** The account budget is $20 per
  month (`budget_usd` in `infra/config/dev.yaml`), account-wide and
  unfiltered, so every website dollar lands in it automatically.
- **An ALB costs about $16.50 per month before traffic.** That is most of
  the budget. The decision: no ALB. CloudFront fronts the EC2 origin
  instead. The CloudFront free tier covers 1 TB and 10 M requests per
  month, gives HTTPS on the default certificate, and hides the instance
  address.
- **The cheapest RDS instance costs about $12 to $15 per month.** The
  decision: no RDS. One DynamoDB on-demand table
  (`mlops-<env>-website-mailing-list`, partition key `email`) holds the
  mailing list at effectively zero cost.
- **The model demo reuses the Phase 6 boundary.** `/predict` requires
  SigV4. The website backend signs requests with the instance-role
  credentials and applies an app-level rate limit. Visitors never hold AWS
  credentials. The signing code moves from `scripts/evaluate_api.py`
  (`sign_headers`, `post_prediction`) into `src/common/signing.py`, and
  both callers import it.
- **The stack is dev-only behind a flag.** A new `website.enabled` key in
  `infra/config/*.yaml` (dev `true`, prod `false`) gates construction in
  `build_app`. Prod never pays for a second instance.
- **Instance and pricing.** `t4g.small` (2 GiB) runs the site as one Docker
  container on Amazon Linux 2023 ARM. A 1-year no-upfront Standard Reserved
  Instance covers it at about $7.74 per month against $12.26 on-demand,
  with no upfront charge, so the monthly budget never spikes. The RI
  purchase is a console action by the account owner, outside CDK. A Linux
  regional RI is size-flexible inside the t4g family.
- **Estimated added cost is about $12 per month.** Instance ~$7.74 (RI),
  public IPv4 ~$3.65, EBS 8 GiB gp3 ~$0.64, CloudFront/DynamoDB/flow log
  near zero. Until the RI purchase the instance bills on-demand and the
  total is about $16.60.

## Synthesis

Planned architecture, in dependency order. **This section records the plan as
written on 2026-08-14 and does not describe the tree today.** The backend is
now FastAPI under `website/backend/`, and the paths below name files that
moved. See [the local-first rebuild](website-local-first-rebuild.md) for the
current layout.

- **VPC**: public subnets only across two AZs, no NAT gateway, no
  endpoints. A REJECT-only flow log goes to CloudWatch Logs at the platform
  retention, which avoids the `AwsSolutions-VPC7` acknowledgement.
- **Security group**: ingress 80 only from the CloudFront origin-facing
  managed prefix list (`com.amazonaws.global.cloudfront.origin-facing`),
  pinned as `website.cloudfront_prefix_list_id` in config. No port 22 and
  no key pair; SSM Session Manager is the only shell path.
- **Instance role**: `AmazonSSMManagedInstanceCore` plus scoped statements
  — ECR pull on the bootstrap container-assets repository,
  `s3:GetObject`/`ListBucket` on the evaluation-report prefix,
  `dynamodb:PutItem` on the table, and `execute-api:Invoke` on the predict
  ARN. `ecr:GetAuthorizationToken` accepts only `*` and becomes the second
  entry in the wildcard baseline test.
- **Image path**: `aws_ecr_assets.DockerImageAsset` (LINUX_ARM64) builds
  from `src/` so the image copies `src/common` and the raw-value contract
  stays single-source. User data pulls and runs the image;
  `user_data_causes_replacement=True` rolls the instance when the image
  changes. The backend is a stdlib `http.server` app in `src/website/`, so
  the repository gains no new dependency.
- **CloudFront**: `HttpOrigin` over HTTP 80 at the EIP public DNS name. The
  default behavior caches; `/api/*` disables caching and forwards
  `X-Forwarded-For` for the rate limiter. The EIP survives instance
  replacement, so the distribution never churns.
- **Execution boundary**: all new grants go to
  `mlops-cloudformation-execution-policy-extension.json` (the main document
  is full at 5888 of 6144 bytes). Seven planned statements cover EC2
  network and instance lifecycle, CloudFront, DynamoDB, the instance
  profile, `iam:PassRole` to `ec2.amazonaws.com`, and the public AMI SSM
  parameter. The estimate is 2.6 to 3.0 KB against 5113 bytes free.
- **cdk-nag**: acknowledgements ride the existing `requires_flag`
  mechanism with a new `website` flag value, so a prod synth with the stack
  absent stays clean.

## What the build settled

- **`Stack.bundling_required` reads the test context.** A spike measured it:
  the value is false under `aws:cdk:bundling-stacks: []` and true otherwise.
  The stack gates `DockerImageAsset` on it, so no unit test builds an image.
  The IAM output does not change with the gate, because the ECR grant uses a
  built ARN rather than the asset repository.
- **The instance DNS attribute was the wrong source.** CloudFormation
  resolves `PublicDnsName` before the Elastic IP attaches, so the name would
  point at an address AWS then releases. The stack builds the origin name
  from the address instead.
- **A Python region comparison cannot pick the DNS suffix.** These stacks
  carry no `env`, so `self.region` is a token and every comparison is false.
  A `CfnCondition` on `AWS::Region` resolves the `compute-1` special case at
  deploy time.
- **The container cannot bind port 80.** It runs as UID 10001, listens on
  8080, and the host publishes 8080 as port 80.
- **The prefix list id is real.** `aws ec2 describe-managed-prefix-lists`
  returned `pl-3b927c52` for us-east-1 with state `create-complete`.
- **The execution boundary has room.** The seven new statements bring the
  extension to 3664 of 6144 bytes, so 2480 remain. The main document keeps
  its 256 free bytes and its unchanged `PassOnlyApplicationRoles` statement.
- **Coverage rose.** The floor moved from 94.14 to 94.57. The comparison
  uses the unrounded total, so the floor is the printed 94.58 rounded down.

## Tensions or open questions

- **Nothing is deployed.** Every claim above comes from synthesis, tests, or
  a local run. No AWS resource exists.
- **The EIP-to-DNS name is unproven against AWS.** The rendered name MUST
  resolve before CloudFront accepts it. The fallback is
  `instance_public_dns_name`, which accepts origin churn on replacement.
- **The image has never been built.** The local Docker daemon was not
  running, so the first `docker build` happens at deploy. The server itself
  ran under Python 3.12 and answered every route.
- **The prefix-list id is region-pinned config.** A region move silently
  breaks it; the yaml comment says how to re-derive it.
- **Instance replacement serves errors for one to three minutes.** Accepted
  for a dev demo site.
- **GuardDuty was approved with EC2 as the trigger.** This stack is that
  trigger. Enabling `security.services.guardduty` stays a separate change
  set after the website observation window closes — see
  [phase-3-paid-security-services](phase-3-paid-security-services.md).
- **The RI bills for its full year.** An early teardown keeps paying about
  $7.74 per month until the term ends, though the RI then covers any other
  t4g usage.
