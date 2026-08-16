---
type: decision
title: Website rebuild, local application before deployment
created: "2026-08-14"
updated: "2026-08-16"
sources: ["./website-stack-plan.md", "../../../PRODUCT.md", "../../../DESIGN.md", "../../../infra/stacks/website_stack.py", "../../../website/backend/app.py", "../../../website/backend/services.py", "../../../website/frontend/src/App.tsx", "../../../website/frontend/src/components/LatestEvaluation.tsx", "../../../src/pipeline/evaluate.py", "../../../website/frontend/src/api.ts", "../../../website/frontend/src/components/ArchitectureMap.tsx", "../../../website/frontend/src/styles.css", "../../../website/frontend/vite.config.ts", "../../../website/local/compose.yaml", "../architecture/cdk-deployment-iam.md", "../architecture/generated-cdk-diagrams.md", "./platform-design.md"]
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
- **The frontend is designed and runs locally.** `frontend/` holds a React 19
  and TypeScript application built by Vite. `App.tsx` composes five components,
  `api.ts` is the one place that calls the backend, and `types.ts` states the
  response shapes. `npm run typecheck` and `npm test` pass, and
  `make frontend-check` runs both.
- **Architecture leads the page.** `ArchitectureMap.tsx` presents ingestion,
  training, evaluation, registration, serving, monitoring, and retraining as
  one interactive lifecycle. The evidence rail keeps implemented, deployed,
  and observed evidence distinct. The prediction form is a later section.
- **The evidence rail applies proof lenses to the selected stage.** Implemented
  names the source or test boundary. Deployed names the dev infrastructure
  boundary. Observed names the runtime signal. A one-shot path signal and the
  coupled readout show the relationship to the lifecycle diagram.
- **The trace ledger is an architecture control.** Pipeline, signed API, and
  drift select their related stages and animate one route. The selected readout
  names the AWS component chain. A stage selection also selects its related
  trace. Native buttons provide keyboard access, and reduced motion keeps a
  static selected route.
- **The approved visual direction is Layered Trace Ledger.** The page uses a
  near-black CRT surface, phosphor-green linework, a compact evidence rail,
  and a quiet trace ledger. One 1672 by 941 WebP supplies the CRT field. HTML,
  CSS, and authored SVG keep the architecture and controls accessible. VT323
  supplies the self-hosted bitmap display voice under the SIL Open Font License.
- **The current repository remains the source target.** Header and first-fold
  actions link to `emanuelGitCodes/aws-mlops-platform`. A public mirror can
  replace that target after the user publishes it.
- **The visual system is documented.** Root `DESIGN.md` records the built
  tokens and rules. `.impeccable/design.json` carries the extended component,
  motion, breakpoint, and color metadata.
- **The form builds itself from `/api/schema`.** `PredictForm` reads
  `feature_columns` and `categorical_values` at run time and renders a control
  for each. A new feature column needs no frontend change, and the vocabulary
  is never restated in TypeScript.
- **The dev server proxies `/api` to the backend.** `vite.config.ts` reads
  `BACKEND_ORIGIN`, so the browser sends same-origin requests and the backend
  needs no CORS configuration. The deployed shape routes `/api/*` through
  CloudFront to the same origin, so no build carries a backend URL.
- **The FastAPI backend is scaffolded and runs.** `backend/` holds `app.py`
  (routes), `services.py` (every AWS call), `settings.py` (the environment
  contract), and `rate_limit.py`. The standard-library `server.py` is deleted;
  git history holds it at commit `1cf62ee`. `local/compose.yaml` builds and
  runs the backend beside the two stand-ins.
- **`website/` holds the whole site.** `website/backend/` is the FastAPI
  service, `website/frontend/` is the React application, and
  `website/local/compose.yaml` runs both beside the two stand-ins. Two website
  things stay outside it on purpose: the CDK stack, which belongs with the
  other stacks in `infra/`, and the tests, which follow the repository rule
  that `tests/unit/` mirrors the source module. The root `.dockerignore` also
  stays at the root, because the image context is the root.
- **The backend image builds from the repository root.** It needs
  `website/backend/` and `src/common/`, which no single subdirectory holds. Two guards keep that
  context small: `.dockerignore` at the root, and `_IMAGE_CONTENT` in
  `infra/stacks/website_stack.py`, an allowlist that decides the CDK asset
  hash. The staged context measures 64 KB and holds those two directories
  alone. Without the allowlist every unrelated file would rebuild the image,
  and a frontend edit would rebuild the backend.

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

### The frontend became a job-application artifact

A review of the running frontend on 2026-08-15 found that the page presented
the platform and never presented the engineer. The work that followed keeps the
approved "Layered Trace Ledger" world and changes what the page carries.

- **The page states who built it.** `frontend/src/profile.ts` is the one source
  of the name, the role, and every contact link. `SiteHeader.tsx` and
  `SiteFooter.tsx` read it. An empty value renders nothing, so an unset link
  never ships as a dead link. `missingLinks()` names the empty ones in the
  footer during development only, because a link that silently disappears is
  how a site ships without its own contact details. **`linkedin` and `resume`
  are still empty, and `email` carries a personal address.**
- **The first viewport ends above the fold.** The hero measured 979 to 1001
  pixels on every viewport tested, so the three actions sat below the fold at
  1512x860, 1440x790, 1920x969, and 1280x720. It now measures 673 to 813, and
  the actions are visible at all four. A `max-height: 810px` block tightens the
  hero for short laptop viewports.
- **The routes are measured, not estimated.** `useNodeBoxes.ts` reads the real
  element boxes with a `ResizeObserver` and redraws after `document.fonts.ready`.
  The stage row is a grid with a `clamp()` gap, so no column centre is a fixed
  fraction of the width, and the bitmap font changes each node's height when it
  loads. One set of path builders now serves the horizontal desktop row and the
  stacked mobile column. Two defects came out of building it:
  1. **A ref callback MUST keep one identity.** Returning a new function per
     render made React detach and reattach every node ref, each reattach
     scheduled a measurement, and the page died with "Maximum update depth
     exceeded". The callbacks are cached per key.
  2. **A stacked column needs a different loop route.** The retrain return runs
     straight down into the node's edge on desktop. Stacked, the node it
     restarts is several nodes above it, so the path leaves sideways and climbs
     a left lane.
- **The mobile page carries the architecture.** `route-lines` was
  `display: none` below 760 pixels, so a phone showed seven words in a list and
  no system. Mobile now renders the whole connected vertical trace, retrain loop
  included.
- **The trace ledger states true values.** It drew dashed tracks with marks
  fixed at 22% and 88% that measured nothing. Each row now renders its real AWS
  component chain, one hop per component.
- **The form opens on a real customer.** `/api/schema` publishes `examples`,
  read from `sample.json` and `sample-high-risk.json`, and `numeric_bounds`,
  read from `CustomerRecord.model_json_schema()`. Neither restates the contract.
  The form seeds itself from the first example and offers both as presets.
  `SeniorCitizen` renders as a choice because its published bound is an integer
  from 0 to 1, not because the frontend knows its name.
- **A cold endpoint is not an error.** A 502 renders as a dormant state naming
  the hourly cost of a SageMaker endpoint. The alternative shows a visitor a
  failure for a cost decision.
- **The page can be shared.** It carried no Open Graph or Twitter tag, so it
  rendered as a grey rectangle wherever it was pasted. It now carries eleven,
  with a generated 1200x630 cover.
- **The display font dropped from 153 KB to 32 KB.** VT323 shipped as
  TrueType. It is WOFF2 now, and it sits in `public/` so `index.html` can
  preload it; a bundled asset carries a content hash the markup cannot name.

### The evidence section states the gate decision

A second review, on 2026-08-16, read the running page as a hiring reader. It
found one column of evidence carrying a single number, and it found six layout
defects. The work that followed changed both the data and the frame.

- **The report carries the decision, not the score alone.**
  `write_evaluation_artifacts` in `src/pipeline/evaluate.py` now records
  `champion_test_auc` and `promotion_decision` in `metrics.json`. The step
  already computed that comparison for its `challenger_evaluation` log event
  and then dropped it. `main()` reads the decision back from the metrics rather
  than repeating the comparison, so one expression owns the gate.
- **The panel reads either report shape.** The pipeline writes two reports per
  execution: `evaluation.json` in the SageMaker ModelMetrics shape, and
  `metrics.json` with the values beside each other. The backend serves whichever
  object is newest under the prefix, and `readAuc` understood only the nested
  shape, so a newest `metrics.json` rendered an em dash where the AUC belongs.
- **The panel shows the evidence it already fetched.** It held one number and
  hid the rest inside a JSON disclosure. It now states the verdict, five rate
  metrics with a track under each, and the confusion matrix with its sample
  line. Every added field is guarded: `evaluation.json` carries the AUC alone,
  and the extra blocks then render nothing.
- **A rate needs its threshold.** A note names the 0.5 serving threshold and
  the trade it makes, because the endpoint returns the probability and a caller
  picks its own cut. Recall at 0.5 is the first question a reader asks.
- **The approach band links the wiki.** The decision record was invisible from
  the page. The band also closes on what the rebuild produced rather than on
  the mistake that started it.

Six defects came out of the same review, and each was measured in the browser
before and after:

1. **The two evidence panels share one grid row**, so the taller one set the
   height and the schema table kept a fixed 22rem cap. The table now takes
   22rem as a flex basis and absorbs the height its neighbour opens.
2. **A display heading and its standfirst did not share a cap line.** VT323
   starts its capitals about 0.24em below the line box, so two boxes with the
   same top read 9 pixels apart. The standfirst trims its own leading with
   `text-box` and takes the heading's cap offset as padding.
3. **The page gutter opens with the viewport.** `min(100% - 2rem, 96rem)` left
   16 pixels between the content and the window. Every section runs to that one
   measure, so the gutter is the only place that can hold the page off the edge.
4. **Two columns moved the third story card to column one**, where it kept the
   padding meant for a second-column card.
5. **The mobile evidence rail sized its first column for the icon**, not for
   the ring that holds it, so each ring covered the name beside it. A stage
   service name wrapped rather than truncating to `Processing…`.
6. **A mobile trace chain scrolls**, and now says so with an edge fade and a
   thin bar. The chain carries right padding wider than the fade, so the end of
   the scroll reaches the fade with empty space and the last hop stays bright.

Two decisions went against the finish review, and both are recorded here rather
than argued twice:

- **The node brackets use two corners, not four.** The surface brief states the
  implementation MUST NOT copy the comp's decorative corner marks where they
  add no information. Two opposing corners frame the node and brighten with
  selection, so the device carries state. The other two would be decoration.
- **The body face stays the system monospace stack.** DESIGN.md's Two Voice
  Rule binds body text and data to it. Self-hosting a body face would
  contradict the design system this build follows. Changing that rule is a
  DESIGN.md decision, not a fix.

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
