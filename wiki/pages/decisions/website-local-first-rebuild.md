---
type: decision
title: Website rebuild, local application before deployment
created: "2026-08-14"
updated: "2026-08-14"
sources: ["./website-stack-plan.md", "../../../infra/stacks/website_stack.py", "../../../src/website/app.py", "../../../src/website/services.py", "../../../frontend/src/App.tsx", "../../../frontend/src/api.ts", "../../../frontend/vite.config.ts", "../../../local/compose.yaml", "../architecture/cdk-deployment-iam.md", "../architecture/generated-cdk-diagrams.md", "./platform-design.md"]
summary: "The website work stops at the deploy boundary and restarts as a three-container local application, because the infrastructure was designed before the application it carries."
---
# Website rebuild, local application before deployment

## Confirmed

- **The work stopped on purpose, before any deploy.** `Mlops-Dev-Website` is
  written, tested, and merged to a branch. No AWS resource exists for it.
- **The order was wrong.** The stack was designed and built first, and the
  application inside it was written to fit the stack. The stated goal was a
  website with a planned design, deployed to AWS. Infrastructure came first
  instead, so the application became whatever one container could hold.
- **The new order is application first.** Build and run the website locally,
  settle its shape, then deploy a known-good application.
- **The planned local shape is a React and TypeScript frontend, a FastAPI
  backend, and containers that answer the AWS APIs the backend calls.** The
  backing services are `amazon/dynamodb-local` for the mailing list and
  `minio/minio` for the evaluation reports in S3. `local/compose.yaml` runs
  both today, with volumes, and is proved against the current backend code.
- **The frontend is scaffolded and runs.** `frontend/` holds a React 19 and
  TypeScript application built by Vite. `App.tsx` composes four components,
  `api.ts` is the one place that calls the backend, and `types.ts` states the
  response shapes. `npm run typecheck` and `npm test` pass, and
  `make frontend-check` runs both.
- **The form builds itself from `/api/schema`.** `PredictForm` reads
  `feature_columns` and `categorical_values` at run time and renders a control
  for each. A new feature column needs no frontend change, and the vocabulary
  is never restated in TypeScript.
- **The dev server proxies `/api` to the backend.** `vite.config.ts` reads
  `BACKEND_ORIGIN`, so the browser sends same-origin requests and the backend
  needs no CORS configuration. The deployed shape routes `/api/*` through
  CloudFront to the same origin, so no build carries a backend URL.
- **The FastAPI backend is scaffolded and runs.** `src/website/` now holds
  `app.py` (routes), `services.py` (every AWS call), `settings.py` (the
  environment contract), and `rate_limit.py`. The standard-library
  `server.py` is deleted; git history holds it at commit `1cf62ee`.
  `local/compose.yaml` builds and runs the backend beside the two stand-ins.

## Synthesis

### What carries forward

These decisions cost real analysis and stay valid:

- **CloudFront in place of an Application Load Balancer.** An ALB costs about
  $16.50 each month against a $20 account budget. This holds for any container
  count.
- **DynamoDB in place of RDS.** About $0 against $12 to $15 each month.
- **The SigV4 proxy boundary.** The backend signs `/predict` calls with its own
  role, and a visitor never holds AWS credentials. The FastAPI backend MUST
  keep this. `src/common/signing.py` already holds the shared helpers.
- **The mailing-list write rule.** `UpdateItem` with
  `if_not_exists(created_at, :now)` keeps the first signup time. `PutItem`
  replaces the whole item and destroys it.
- **`src/common` is the single source of the feature and schema contract.** The
  FastAPI backend MUST import `FEATURE_COLUMNS`, `FEATURE_VOCABULARY`, and
  `CustomerRecord` rather than restate them. Pydantic is already the schema
  library, so FastAPI fits this contract without a translation layer.
- **The three defects found by running the container.** A failed S3 read MUST
  degrade to one page section. Every request MUST get a response. botocore
  reads `AWS_DEFAULT_REGION` and ignores `AWS_REGION`.
- **The execution-boundary grants.** `MLOpsCloudFormationExecutionPolicy
  Extension` v3 is **live in the account** and permits EC2, CloudFront,
  DynamoDB, the instance profile, and the AMI parameter read. A three-container
  deploy on one instance needs no new grant. A move to ECS or Fargate does.

### What changes

- **One container becomes three.** The single `DockerImageAsset` and the
  `docker run` line in the user data no longer describe the application. The
  instance MUST run a compose file, or the platform MUST move to a container
  service.
- **The image count changes the asset story.** `DockerImageAsset` builds one
  image. Three images mean three assets, or one compose file that the instance
  pulls.
- **The frontend becomes a build artifact.** `frontend/Dockerfile` carries two
  targets. `dev` runs the Vite server with hot reload, and compose uses it.
  `runtime` serves the built bundle from nginx. The deployed shape MAY skip
  `runtime`: a static bundle in S3 behind the existing CloudFront distribution
  costs less than a container that serves it.
- **`t4g.small` holds 2 GiB.** One Python container fits comfortably. The local
  set does not, and it never needs to: `dynamodb` and `minio` are development
  stand-ins. The deployed backend talks to the real DynamoDB and S3, so the
  deployed instance runs the backend alone, or the backend beside a frontend.

### The local backing services

`local/compose.yaml` holds them. Two containers stand in for two AWS services,
and both keep their data in a named volume:

- **`amazon/dynamodb-local`** answers the DynamoDB API and holds the mailing
  list.
- **`minio/minio`** answers the S3 API and holds the evaluation reports.
  LocalStack was the alternative. MinIO is smaller, and it emulates the one
  service this application reads.

A third container, `amazon/aws-cli`, creates the bucket and the table, then
exits. One image covers both services, so the file needs no second init.

This session ran the whole file against the real backend code. Four facts came
out of it, and each one costs time to find:

1. **DynamoDB Local needs `-sharedDb`.** Without it the emulator keys each
   table to the caller's access key and region. A table created by one identity
   raises `ResourceNotFoundException` for another, while a scan under the first
   identity shows the same table `ACTIVE`.
2. **DynamoDB Local needs `-dbPath` and `user: root`.** The default is memory
   only, so a restart loses the data. The image runs as `dynamodblocal`, which
   cannot write a fresh named volume, so the write fails until root owns it.
3. **boto3 needs no code change for either service.** Recent botocore reads
   `AWS_ENDPOINT_URL_S3` and `AWS_ENDPOINT_URL_DYNAMODB`, so the application
   holds no endpoint argument and no local branch. The deployed backend sets
   neither variable and reaches the real services. MinIO needed no path-style
   addressing setting; boto3 chose it for a non-AWS host on its own.
4. **`docker compose down` keeps the data. `down -v` deletes it.** The volumes
   survive an ordinary stop.

Proven behavior: the application read a seeded evaluation report from MinIO and
wrote a signup to DynamoDB Local, then a full `down` and `up` cycle returned
both the row and the object unchanged.

The deployed backend talks to the real DynamoDB and S3. Neither container ever
reaches AWS.

## Tensions or open questions

- **The deployed container topology is undecided.** Three containers on one
  EC2 instance with compose is the cheapest path and keeps the current stack
  close. ECS on Fargate is cleaner and costs more. This decision MUST come
  after the local application works, not before.
- **The frontend may not need a container in AWS.** A static React bundle in S3
  behind the existing CloudFront distribution removes a container and some
  cost. That choice changes the CDK stack more than it changes the local
  compose file.
- **CI does not run the frontend checks.** `make frontend-check` exists and
  passes, and `.github/workflows/ci.yml` does not call it. CI would need a Node
  setup step. The website work is on hold, so that stays open.
- **The frontend has no component test.** `frontend/src/api.test.ts` covers the
  client and its error shapes. Rendering tests need a DOM environment and a
  testing library, which this scaffold does not install.
- **TypeScript is pinned to 5.x.** Version 7 is released and is the native
  port. The ecosystem around Vite and React types has not settled on it.
- **`fastapi` and `httpx` are in the dev extra, not only in the image.**
  `tests/unit/test_website_app.py` drives the routes through `TestClient`, so
  the lockfile carries both. `uvicorn` stays in the image alone, because no
  test starts a server.
- **A test MUST import the backend through `import_with_stubbed_boto3`.**
  Importing `src.website.services` directly builds real boto3 clients at
  collection time, and `test_pipeline.py` then reaches S3 through the live
  default session. That mistake broke thirteen unrelated tests once.
- **Nothing about the branch is deployed, and one account change is live.**
  The policy rotation to v3 stands whether or not this work resumes. It grants
  permissions for resources that do not exist, which is inert but untidy.
