---
type: decision
title: Website rebuild, local application before deployment
created: "2026-08-14"
updated: "2026-08-14"
sources: ["./website-stack-plan.md", "../../../infra/stacks/website_stack.py", "../../../src/website/server.py", "../architecture/cdk-deployment-iam.md", "../architecture/generated-cdk-diagrams.md", "./platform-design.md"]
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
- **The planned local shape is three containers**: a React and TypeScript
  frontend, a FastAPI backend, and a database container that answers the
  DynamoDB API.
- **The current backend does not survive.** `src/website/server.py` is a
  standard-library `http.server` application. It was written to keep the image
  small and add no repository dependency. FastAPI replaces it.

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
- **The frontend becomes a build artifact.** React and TypeScript need a build
  step. A static bundle behind CloudFront costs less than a container that
  serves it, so the frontend MAY not need a container in the deployed shape at
  all, even though it needs one locally.
- **`t4g.small` holds 2 GiB.** One Python container fits comfortably. Three
  containers, one of them a JVM database emulator, do not. The local database
  container MUST NOT reach the deployed instance; the deployed backend talks to
  the real DynamoDB service.

### The database container

`amazon/dynamodb-local` is the image. It is the AWS-published DynamoDB
emulator, and this session ran it end to end against the real backend code.
Two facts came out of that run and both cost time to find:

1. **Pass `-sharedDb`.** Without it, DynamoDB Local keys each table to the
   caller's access key and region. A table created with one credential is
   invisible to another, and the error is `ResourceNotFoundException` on a
   table that the console-equivalent scan shows as `ACTIVE`.
2. **Point boto3 at it with `AWS_ENDPOINT_URL_DYNAMODB`.** Recent botocore
   reads this environment variable, so the application code needs no endpoint
   argument and no local branch. The deployed backend sets nothing and reaches
   the real service.

The container start that worked:

```bash
docker run -d --name dynamodb-local -p 8000:8000 \
  amazon/dynamodb-local:latest \
  -jar DynamoDBLocal.jar -inMemory -sharedDb
```

`-inMemory` drops the data when the container stops. A compose file SHOULD use
a volume and drop that flag when the data must survive a restart.

LocalStack is the alternative. It emulates many AWS services rather than one,
which helps when the local stack later needs S3 as well. It is heavier, and
DynamoDB Local is enough for a mailing list.

## Tensions or open questions

- **The deployed container topology is undecided.** Three containers on one
  EC2 instance with compose is the cheapest path and keeps the current stack
  close. ECS on Fargate is cleaner and costs more. This decision MUST come
  after the local application works, not before.
- **The frontend may not need a container in AWS.** A static React bundle in S3
  behind the existing CloudFront distribution removes a container and some
  cost. That choice changes the CDK stack more than it changes the local
  compose file.
- **`src/website/server.py` has no future in its current form.** It stays on
  the branch as a working reference for the four routes and their behavior. It
  MUST NOT gain features.
- **The repository dependency set grows.** FastAPI and its server are new
  runtime dependencies. The backend image owns them, the way
  `src/website/requirements.txt` already owns boto3 and pydantic. The
  repository `uv.lock` SHOULD stay free of them unless a test imports them.
- **Nothing about the branch is deployed, and one account change is live.**
  The policy rotation to v3 stands whether or not this work resumes. It grants
  permissions for resources that do not exist, which is inert but untidy.
