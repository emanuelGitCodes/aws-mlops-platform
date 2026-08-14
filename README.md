# aws-mlops-platform

> **Portfolio review only.** All rights are reserved. This project is not open
> source. No license is granted to copy, use, modify, distribute, or deploy it
> beyond GitHub's required public-repository rights.

A portfolio-grade **MLOps reference platform** on AWS where the *infrastructure is the deliverable*. The model is deliberately simple (Telco customer churn with XGBoost); the engineering lives in ingestion, reproducible evaluation, champion/challenger promotion, infrastructure as code, CI/CD, and low-cost serverless inference.

`make deploy ENV=dev` creates the nine infrastructure stacks. The SageMaker Pipeline is then upserted through the SDK-driven pipeline command because its definition depends on live Model Registry state. The current dev environment has completed ingestion, training, held-out evaluation, model registration, serverless deployment, API inference, and the audit-and-detection half of the security roadmap.

## Architecture

```mermaid
flowchart TB
    subgraph Ingest["Ingestion"]
        RAW[(S3 raw)] -->|ObjectCreated| EB1[EventBridge]
        EB1 --> Q[SQS ingest queue]
        Q -. after 3 failed receives .-> DLQ[SQS dead-letter queue]
        Q --> LV[Lambda: validate schema]
        LV -->|valid rows| CUR[(S3 curated/telco)]
        LV -->|invalid rows + reason| QUAR[(S3 curated/quarantine)]
    end

    subgraph Train["SageMaker training and evaluation"]
        CUR -->|pipeline input| PIPE[SageMaker Pipeline]
        RUN[Operator command] -->|upsert and start| PIPE
        PIPE --> PRE[Preprocess]
        PRE -->|encoded train + validation| TR[Train XGBoost]
        PRE -->|encoded held-out test| EV[Evaluate challenger]
        TR -->|model artifact| EV
        PRE -->|raw labeled fixture| FIX[(S3 api_test.jsonl)]
        EV --> REPORTS[(S3 evaluation bundle<br/>metrics, predictions, 5 PNG charts)]
        EV -->|test AUC| GATE{AUC beats champion?}
        GATE -->|yes| REG[Model Registry]
        GATE -->|no| STOP[End without registration]
    end

    subgraph Serve["Current serving path"]
        REG -->|Approved event| DEP[Lambda: update endpoint]
        DEP --> EP[SageMaker Serverless Endpoint]
        CLIENT[Client] -->|POST /predict + SigV4| APIGW[API Gateway]
        APIGW --> LI[Lambda: validate + encode]
        LI --> EP
        FIX --> CHECK[API evaluator]
        CHECK -->|representative sample or full test| APIGW
    end

    subgraph Ops["Operations"]
        EP --> CW[CloudWatch metrics, dashboard + 5xx alarm]
        LI -->|one object per prediction| CAP[(S3 capture<br/>hour-partitioned)]
        PRE -->|training distribution| BASE[(S3 baseline)]
        CAP --> DRIFT[Lambda: PSI drift job<br/>hourly, min-sample gated]
        BASE --> DRIFT
        DRIFT -->|violation event| RETRAIN[EventBridge + retrain Lambda]
        RETRAIN -->|StartPipelineExecution| PIPE
    end

    subgraph Security["Security and delivery status"]
        S1[CloudTrail + audit KMS<br/>CIS and deploy-role alarms to SNS] --> S1B[Access Analyzer + Config<br/>account S3 block + EventBridge alerts]
        S1B --> S2[Least-privilege runtime roles]
        S2 --> S3[SigV4 on /predict<br/>live in dev]
        S2 --> CICD[GitHub OIDC deploy role<br/>live; workflow not run]
        S2 --> S4[Data KMS + WAF<br/>not started]
        S2 --> S5[GuardDuty + Security Hub<br/>paid-plan gate]
    end

    S2 -. scopes runtime roles .-> PIPE
    S3 -. changes authorization .-> APIGW
    S4 -. hardens storage .-> RAW
    S4 -. protects .-> APIGW

    classDef planned fill:#fff4cc,stroke:#b7791f,stroke-dasharray:5 5,color:#1a202c
    classDef done fill:#d5f5e3,stroke:#1e8449,color:#1a202c
    class S4,S5 planned
    class S1,S1B,S2,S3,CICD,CAP,BASE,DRIFT,RETRAIN done
```

The ingestion, training, serving, and operations groups show implemented
behavior. The security group shows delivery status, not event flow. Green nodes
have live dev evidence. Yellow nodes are deferred. The GitHub OIDC role is live,
but `deploy.yml` has not run.

### Generated CDK views

`make diagrams ENV=dev` renders the complete CDK app, the ML platform stacks,
and the security plus CI/CD stacks. These diagrams show synthesized desired
state, not live AWS state. Each view includes a PNG preview, a self-contained
editable SVG, and a Graphviz DOT source. See the
[generated CDK infrastructure diagrams](wiki/pages/architecture/generated-cdk-diagrams.md).

## Current operational loop

1. A raw CSV upload is validated before accepted rows are written to curated S3.
2. The pipeline creates deterministic training, validation, held-out test, and raw API-verification fixtures.
3. `Evaluate` scores the challenger on unseen test data, writes the JSON/CSV/PNG report bundle, and exposes test AUC to the promotion gate.
4. A `ConditionStep` registers the challenger only when its test AUC is strictly greater than the current approved champion's AUC.
5. Registry approval (automatic in dev, manual in prod) triggers the deployment Lambda, which creates or updates the SageMaker serverless endpoint.
6. API Gateway and the proxy Lambda validate and encode `/predict` requests before invoking the endpoint. The API evaluator can replay the labeled held-out fixture through this deployed serving path.

The drift-to-retrain leg is closed, and the platform owns both ends of it.
SageMaker Model Monitor supports neither serverless endpoints nor new customers,
so nothing here depends on it. The proxy Lambda writes each served record and
its score to an hour-partitioned S3 capture prefix; the preprocessing step
writes the training distribution as a baseline; and an hourly Lambda scores the
previous hour against that baseline using the Population Stability Index in
`src/common/drift.py`. When enough columns move it emits the platform's own
violation event, which starts a training run.

Two limits are deliberate and worth stating. A window holding fewer than
`MIN_RECORDS` captured predictions is **skipped rather than scored**: a
serverless endpoint is idle most of the time, and PSI over a handful of rows
reports sampling noise. And because churn labels are never observed after a
prediction, this loop detects that the input traffic changed — it cannot detect
that the model got worse. See the
[capture-design decision](wiki/pages/decisions/drift-capture-design.md).

## Repo map

| Path | What |
|---|---|
| `infra/` | CDK app: nine stacks split by lifecycle and blast radius, including security monitoring and CI/CD identity |
| `infra/config/` | `dev.yaml` / `prod.yaml`; the shape is typed once as `PlatformConfig` in `infra/stacks/shared.py` |
| `infra/security_checks.py` | cdk-nag gate: every acknowledgement is bound to one construct and names the phase that removes it |
| `src/common/` | Single source of truth: `schema.py` (pydantic contract shared by ingestion and the inference API) and `features.py` (column order, accepted vocabulary, and encoding) |
| `src/pipeline/` | SageMaker Pipeline definition + preprocess/evaluate scripts |
| `src/ingestion/`, `src/serving/`, `src/monitoring/` | Lambda handlers (validate, proxy with capture, endpoint deploy, drift evaluation, drift retrain) |
| `scripts/` | API evaluation, deployment verification, and the drift-traffic demo helper |
| `wiki/` | LLM-maintained, interlinked knowledge base for the platform |
| `.github/workflows/` | CI, full-history secret scanning, and manual OIDC-federated deployment |

## Prerequisites

Install these before starting. Everything below is what a fresh checkout
actually needs — the Quickstart does not restate it.

- An AWS account and an admin-capable credential (the account root user, or
  an existing IAM administrator). `scripts/setup_account.sh` uses this once
  to create the narrower deployment identity; nothing after that needs
  admin access.
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
  configured with a profile (`aws configure`).
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for Python
  dependency management.
- Python 3.12 (`uv` will provision it if it is not already on your machine).
- `envsubst` (part of `gettext`; `brew install gettext` on macOS) — used by
  `scripts/setup_account.sh`.
- [Graphviz](https://graphviz.org/download/) — only needed for
  `make diagrams` (`brew install graphviz`).
- [`gh` CLI](https://cli.github.com/), authenticated — only needed for
  `scripts/setup_github_deploy.sh`, which is optional.

## Dataset

The training data is the public IBM Telco Customer Churn dataset, published
on Kaggle as
[`blastchar/telco-customer-churn`](https://www.kaggle.com/datasets/blastchar/telco-customer-churn)
(`WA_Fn-UseC_-Telco-Customer-Churn.csv`, 7,043 rows). The repository does not
track the CSV — `telco/` is gitignored — so fetch it once before the first
pipeline run. IBM hosts a byte-identical mirror that needs no login:

```bash
mkdir -p telco && curl -sL -o telco/telco.csv \
  https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv
```

Verify the file before you upload it:

```bash
shasum -a 256 telco/telco.csv
```

The expected SHA-256 is
`16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`. A copy
saved with CRLF line endings instead hashes to
`88be4b93fbe0cc83421af1c503794c97c342eca914c1576db7c276e61d61358a`; the two
normalize to the same rows in the same order, and either reproduces the same
splits. Any other hash means a different file. **The exact file matters**:
`src/pipeline/preprocess.py` shuffles the rows with a fixed seed, so the
train, validation, and held-out test splits — and therefore the reported
AUC — are deterministic only for this exact row order. See the
[dataset provenance decision](wiki/pages/decisions/dataset-provenance.md).

## Quickstart

Fork or clone the repository first. Before the first deploy, set the values
that identify *your* account and repository, not this one:

| Value | File | Why it must change |
|---|---|---|
| `cicd.github_repository` | `infra/config/<env>.yaml` | The OIDC role trusts this exact string. CI cannot authenticate until it names your repository. |
| `model_package_group` | `infra/config/<env>.yaml` | Account-scoped. `dev.yaml` and `prod.yaml` must not share it. |
| `account_budget` | `infra/config/<env>.yaml` | AWS Budgets is account-level. Exactly one environment may set it `true`. |
| `owns_oidc_provider` | `infra/config/<env>.yaml` | One OIDC provider per account. Exactly one environment may set it `true`. |

Deploying outside `us-east-1` also needs the two Access Analyzer ARNs in
`infra/policies/mlops-cloudformation-execution-policy-extension.json` retargeted.
That file is the only place a region is hardcoded.

```bash
cp .env.example .env         # fill in AWS_ACCOUNT_ID, AWS_REGION,
                             # MLOPS_DEPLOYER_USER_NAME, SECURITY_ALERT_EMAIL
set -a && source .env && set +a
make install                 # deps

# 0. One-time per fresh AWS account, run with an admin-capable AWS_PROFILE:
#    creates the scoped CloudFormation execution policy, the
#    MLOps-Deployers group, and the MLOPS_DEPLOYER_USER_NAME deploy user.
#    See wiki/pages/architecture/cdk-deployment-iam.md for what this builds.
./scripts/setup_account.sh

# From here on, switch AWS_PROFILE to the deploy user this script created.
make lint test                        # local checks
make bootstrap ENV=dev                # once per account/region; uses the scoped policy above
make deploy ENV=dev                   # all nine stacks
make diagrams ENV=dev                 # PNG, SVG, and DOT desired-state diagrams

# Fill the remaining .env values (RAW_BUCKET, CURATED_BUCKET, ARTIFACTS_BUCKET,
# ACCESS_LOG_BUCKET, AUDIT_BUCKET, AUDIT_KEY_ID, PIPELINE_ROLE_ARN, API_URL,
# API_GATEWAY_ID) from the CloudFormation stack outputs of the stacks just
# deployed, then re-source .env.

# 1. Ingest: drop the Telco CSV (see "Dataset" above) into the raw bucket
#    -> validated rows land curated
aws s3 cp telco/telco.csv s3://${RAW_BUCKET}/telco.csv

# 2. Train: upsert + run the pipeline (registers the first champion).
# Module form (-m), not a file path: pipeline.py imports src.common.features,
# which is only importable with the repository root on sys.path.
# --model-package-group must match infra/config/<env>.yaml's
# model_package_group and be globally unique per environment.
uv run --locked --extra pipeline python -m src.pipeline.pipeline \
  --pipeline-name ${PIPELINE_NAME} \
  --role-arn ${PIPELINE_ROLE_ARN} --curated-bucket ${CURATED_BUCKET} \
  --artifacts-bucket ${ARTIFACTS_BUCKET} --model-package-group ${MODEL_PACKAGE_GROUP} --start

# 3. Serve: approval auto-deploys the endpoint. The smoke test uses SigV4.
AWS_PROFILE=<profile> make smoke ENV=dev

# 4. Inspect the execution's report bundle in the artifacts bucket, then run
# the API verification command shown in the next section.
```

Capture starts as soon as the Serving stack is deployed, and the drift job needs
a baseline, so run the pipeline at least once before expecting a drift
evaluation to score anything. `scripts/send_drift_traffic.py` sends
distribution-shifted traffic through the API when you want to see the loop
close on demand.

## Manual one-time AWS console steps

CDK does not — and in some cases cannot — automate these. Do them once per
account, at the point noted:

- **Confirm the security-alert SNS subscription.** `make deploy` passes
  `SECURITY_ALERT_EMAIL` to the Security stack, and AWS then emails that
  address. Click the confirmation link, or CIS and detection alarms have
  nowhere to deliver. CloudFormation stores the value, so later deploys
  reuse it and AWS does not re-send the confirmation.
- **Activate the budget's cost allocation tag.** The per-environment budget
  filters on a tag (`security.account_budget`, true in exactly one
  environment). In Billing → Cost allocation tags, activate that tag.
  Before it is activated the filter matches nothing and the budget never
  alarms.
- **Decide on GuardDuty / Security Hub.** Both sit behind a deliberate
  paid-plan upgrade — enabling GuardDuty starts a 30-day trial, then bills
  monthly. After you opt in, flip `security.services.guardduty` and
  `security_hub` to `true` in `infra/config/<env>.yaml` yourself and
  redeploy the Security stack.
- **Wire up `deploy.yml` (optional).** `.github/workflows/deploy.yml` is
  `workflow_dispatch`-only and needs GitHub `dev`/`prod` environments each
  holding the matching `AWS_<ENV>_DEPLOY_ROLE_ARN` secret. After the `Cicd`
  stack deploys, run `ENV=dev ./scripts/setup_github_deploy.sh` (and again
  with `ENV=prod`) to create the environment and set the secret from the
  stack's `GitHubDeployRoleArn` output.

## Teardown

`make destroy ENV=dev` deletes the nine stacks, but retained buckets, the
audit KMS key and log group, and every SDK-created SageMaker resource survive
it — and two of the retained names block the next deploy. Follow the
[complete teardown and rebuild](wiki/pages/architecture/teardown-and-rebuild.md)
page for the order that works.

## Model evaluation reports

Each `Evaluate` ProcessingStep scores a model on the held-out test split. It
stores an execution-scoped report bundle under
`s3://<artifacts-bucket>/evaluations/<UTC-start-timestamp>/<execution-id>/`:
the existing `evaluation.json` (AUC and Model Registry input), `metrics.json`,
`predictions.csv`, and PNG confusion-matrix, ROC, precision-recall,
calibration, and score-distribution charts. The confusion matrix uses the same
`0.50` cutoff as the `/predict` API: a probability of `0.50` or above is
classified as churn.

After an endpoint deployment, validate the deployed serving path against the
same raw, labeled held-out records. The default is a deterministic,
class-balanced sample of 25 records; use `--all` for the full test split.

```bash
API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/predict \
uv run --locked --extra dev python scripts/evaluate_api.py \
  --pipeline-execution-arn <pipeline-execution-arn> \
  --profile <profile> --region us-east-1

# Full held-out test-set API evaluation (more endpoint invocations):
API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/predict \
uv run --locked --extra dev python scripts/evaluate_api.py \
  --pipeline-execution-arn <pipeline-execution-arn> --all \
  --profile <profile> --region us-east-1
```

The evaluator discovers the `api_test` fixture output of that execution,
checks that every API response obeys the probability and `0.50` classification
contract, and prints labeled endpoint metrics. The offline `Evaluate` report
remains the source of truth for model promotion.

## LLM Wiki

The repository also includes a local-first LLM Wiki. `wiki/raw/` stores immutable source material; `wiki/pages/` stores the maintained synthesis; `wiki/index.md` and `wiki/log.md` provide navigation and history; and `wiki/SCHEMA.md` defines the agent's operating contract.

```bash
make wiki-search Q="SageMaker permissions"
make wiki-ingest SOURCE=/path/to/article.md TITLE="Article title"
make wiki-lint
```

The helper is intentionally deterministic and does not call an LLM. It handles source registration, page scaffolding, index rebuilding, full-text search, operation logging, and health checks so an LLM can focus on reading, synthesis, and cross-referencing.

## Code graph

[graphify](https://github.com/Graphify-Labs/graphify) indexes the source tree
and the wiki into a queryable graph. The extraction is local AST parsing, so it
calls no model and no network service.

```bash
make graph                                  # rebuild graphify-out/
make graph-query Q="what writes the capture record?"
make graph-explain NODE=proxy_handler
```

`graphify-out/` holds `graph.json`, an interactive `graph.html`, and
`GRAPH_REPORT.md`. It is build output and stays untracked, like `infra/cdk.out/`.
`.graphifyignore` narrows the corpus. The graph answers "where" and "what
connects to what"; the wiki remains the record of why, when, and what state.
See [the decision page](wiki/pages/decisions/graphify-knowledge-graph.md).

## Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Serving | SageMaker Serverless Inference | Scales to zero (~$0 idle); registry-native; cold-start latency accepted and named |
| Managed vs. primitive | Mix | SageMaker where ML lineage matters (training and registry); primitives (S3/SQS/Lambda) for transport and integration |
| Orchestration | SageMaker Pipelines | Step lineage + caching for free vs. hand-rolled Step Functions |
| Promotion | ConditionStep vs. champion AUC | Challenger must beat champion; no silent regressions |
| IaC | CDK (Python) | Type-checked infra, same language as the ML code |
| CI auth | GitHub OIDC | No long-lived keys in secrets |
| Pipeline via SDK | Not CloudFormation | SageMaker Pipelines are versioned documents and resolve live champion state; CDK owns the supporting IAM |
| Drift capture | Proxy-side capture + own PSI job | Model Monitor supports neither serverless endpoints nor new customers; owning it keeps the endpoint at near-zero idle cost and removes the hourly processing job |
| Security rollout | Phase-by-phase | Audit and guardrails precede KMS, least privilege, IAM/SigV4, TLS, and WAF changes so failures stay attributable |

## Security and cost posture

Current dev baseline:

- Raw, curated, and artifact buckets block public access, enforce TLS, use
  AWS-managed SSE-KMS encryption, retain versions, and deliver server access
  logs to a dedicated log bucket. Moving these three to a customer-managed key
  is phase 4; the audit bucket already uses one.
- Runtime responsibilities use separate validation, pipeline, proxy, deployment,
  and model roles. Phase 5 replaces the broad ones one at a time: the proxy is
  scoped to invoke only the configured endpoint and write its own log group, the
  model role reads only the training prefix of the artifacts bucket, the deploy
  role names the endpoint and model package group it may touch, and the pipeline
  role names each bucket prefix, job pattern, and log group a training run
  uses. Phase 5 is complete: no role attaches `AmazonSageMakerFullAccess`, and
  the only remaining wildcard resource is account-level S3 Block Public Access,
  where AWS accepts nothing else.
- `/predict` requires IAM authorization and SigV4. The account has no API key
  or usage plan. The API stage retains rate 10 and burst 20 throttles.
- Audit and detection are deployed. A multi-region CloudTrail with log-file
  validation writes to a retained, customer-managed-KMS-encrypted bucket and to
  a 90-day CloudWatch log group. Six CIS metric filters cover root activity,
  unauthorized API calls, IAM policy changes, trail changes, KMS key
  disable/delete, and bucket policy changes. A seventh security detection
  alarms on each production deploy-role assumption. All seven alarms publish
  to the security SNS topic. The endpoint 5xx and endpoint silence alarms use a
  separate operational topic, because an idle dev endpoint is the expected state
  and its silence alarm would otherwise add routine noise to the security
  channel. IAM Access Analyzer, AWS Config, account-level S3
  Block Public Access, and security event routing are enabled in dev through
  the `security.services` flags. GuardDuty and Security Hub remain behind the
  paid-plan gate. WAF is not enabled.
- Serverless inference has no configured provisioned concurrency, so endpoint
  compute has no standing instance while idle. S3, logs, and other retained AWS
  resources still incur small ongoing charges. The monthly budget is `$20` and
  alerts at 50/80/100%. It is account-scoped and owned by exactly one
  environment (`security.account_budget`, true in dev only): AWS Budgets is an
  account-level service, so a budget per environment would re-measure the same
  dollars and alarm twice on them. Scoping a budget to one environment needs a
  `CostFilters` tag filter, which reports zero until that tag is activated as a
  cost allocation tag in Billing — a manual step, and a budget matching nothing
  never alarms at all.

The [phased security hardening roadmap](wiki/pages/architecture/phased-security-hardening.md)
runs 0-9: baseline, repository guardrails, audit and detection, threat
detection services, customer-managed KMS encryption, least-privilege IAM,
IAM/SigV4 API authorization, TLS/logging, WAF, and operator-identity cleanup.
Phases 0-2, 5, and 6 are complete. Phase 3 is partial: Access Analyzer, AWS
Config, account S3 blocking, and alert routing are live in dev. GuardDuty and
Security Hub remain behind the paid-plan gate. Phases 4 and 7-9 are not
started. The per-phase
records live in `wiki/pages/sources/`.

## Copyright and security

Copyright 2026 Emanuel J. Cortes-Lugo. All rights are reserved. This repository
is available for portfolio review only. It is not open source. No license is
granted to copy, use, modify, distribute, or deploy the project. Third-party
asset notices are in [NOTICE](NOTICE).
Report vulnerabilities through GitHub's private reporting flow as described in
[SECURITY.md](SECURITY.md). Do not include security details in a public issue.
