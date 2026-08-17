# AGENTS.md

Agent instructions for this repository. Follow these exactly.

This file is the single source. `CLAUDE.md` at the repo root is a symlink
to it, so both paths always serve the same content — edit here, never
there.

## Project overview

Portfolio-grade MLOps reference platform on AWS: SageMaker Pipelines for
training/evaluation, serverless inference behind API Gateway, and a
drift→retrain loop — all defined in CDK. Python 3.12, dependencies managed
with `uv`. The model (Telco churn, XGBoost) is deliberately simple; the
engineering is the deliverable.

Nine CDK stacks per environment, named `Mlops-<Env>-<Stack>` (the formula
lives once in `stack_prefix()` in `infra/app.py`). Both environments deploy
into the same account — stacks are environment-agnostic, with no
`env=cdk.Environment` — which is why `dev.yaml` and `prod.yaml` must not
share account-scoped names (model package group, budget, OIDC provider).

## Current status

The platform runtime is built and deployed in dev; the live work is the
phased security-hardening roadmap. **The wiki is the source of record** —
`wiki/pages/architecture/phased-security-hardening.md` holds the phase map
and the per-phase status. Read it before starting security work rather than
trusting this summary, which is coarse by design.

- Phases 0–2 are complete. Phase 3 is partial: the six enablement flags
  under `security.services` in `infra/config/*.yaml` flip one per sub-phase,
  and in dev `access_analyzer`, `config_recorder`, and `account_bpa` are
  true, and `eventbridge_alerts` is true after 3F closed as a go on
  2026-08-08. Prod stays all-false until a deliberate rollout. What remains is
  `guardduty` and `security_hub` behind the paid-plan decision — enabling
  GuardDuty starts a 30-day free trial and then bills monthly.
- Phase 5 (replace broad IAM one role at a time) is **complete**: the proxy,
  model, deploy, and pipeline roles all passed their component checks by
  2026-08-06. Its mechanisms stay in place — the opt-in `least_privilege`
  and `least_privilege_logs` kwargs in `infra/stacks/shared.py` — and the
  Lambda roles that still carry `AWSLambdaBasicExecutionRole` keep a
  `security_checks.py` acknowledgement naming Phase 5.
- Sub-phases 2F and 2G are deployed and closed as a go on 2026-08-09. 2F's
  silence half shipped broken — `TreatMissingData` does not cause an evaluation
  to run — and was refixed with `FILL`, which then fired and cleared inside 16
  minutes. 2G reached the account as a dependency of the Monitoring deploy
  rather than on its own, so the two shared one window.
- Phase 6 (SigV4 on `/predict`) is **complete**: deployed to dev on 2026-08-09,
  window closed as a go on 2026-08-14. The account holds no API key and no usage
  plan, and the stage carries
  the throttle they used to. `CicdStack` is deployed the same day, so the OIDC
  provider and `${GITHUB_DEPLOY_ROLE_NAME}` exist. **`deploy.yml` still has not
  run**: the `dev` and `prod` GitHub environments allow only `main`, and dev
  holds the role ARN. Environment reviewers remain unavailable on the current
  private-repository plan. Phase 4 (KMS) and Phases 7–9 are not started.
- **No observation window is open.** The alert-topic split deployed to dev on
  2026-08-14, and its window closed as a go on 2026-08-16.
  `mlops-<env>-ops-alerts` carries the two endpoint alarms, and the seven
  security alarms stay on `mlops-<env>-security-alerts`. Both topics have now
  delivered a real alarm email. `mlops-dev-endpoint-silent` fires on its own
  about 24 hours after the last `/predict` call, so an `ALARM` there means idle,
  not broken. Prod keeps the single topic. See
  [two alert topics](wiki/pages/decisions/alert-topic-split.md).
- **The website work is ON HOLD, and its stack MUST NOT be deployed.**
  `make deploy` refuses whenever the environment builds it, because that target
  deploys every stack and would create the instance, address, distribution,
  VPC, and table. `ALLOW_WEBSITE_DEPLOY=1` overrides the refusal, and
  `make deploy-stack STACK=…` is unguarded because it names its target. A tenth
  stack, `Mlops-Dev-Website`, is written, tested, and open as a draft pull
  request on `claude/aws-cdk-ml-website-cf88da`. **No AWS resource exists for
  it.** The infrastructure was designed before the application it carries, so
  the website restarts as a local three-container application — React with
  TypeScript, FastAPI, and `amazon/dynamodb-local` — and deploys after that
  works. One account change is live and inert: the CloudFormation execution
  policy extension is at `v3` with grants for resources that do not exist. Read
  [the local-first rebuild](wiki/pages/decisions/website-local-first-rebuild.md)
  before any website work.
- The repository is prepared for public release but stays **private**. `main`
  requires both CI checks, one approval, linear history, and resolved
  conversations. `make public-check` is the standing gate against tracked
  account metadata and private filenames, and CI runs it. The repository MUST
  stay private until the history choice is explicit: a clean public mirror, or
  a history rewrite. Going public is what turns on `codeql.yml`, GitHub secret
  scanning, and environment reviewers.

**The execution boundary spans two managed policies. Add new grants to the
extension.** AWS caps one managed policy at 6144 characters, and
`MLOpsCloudFormationExecutionPolicy` reached 5888 with 256 bytes free — too
little for any useful statement. `MLOpsCloudFormationExecutionPolicyExtension`
carries the overflow and holds 1031 bytes of its own 6144. Both attach
to `cdk-hnb659fds-cfn-exec-role-*`, so the grants union. The AWS policy names
differ from the `mlops-cloudformation-execution-policy*.json` filenames. Size,
not the three-of-five version slots, is what blocks a change; `make test`
measures both documents against the quota.

Two rules follow from the roadmap's operating rule and apply to any phase
work you do:

1. **One phase per change set.** Baseline, tests, synth, reviewed `cdk diff`,
   its own commit, scoped dev deploy, live checks, observation window,
   explicit go/no-go. Prod is not touched while a phase is being validated
   in dev.
2. **The wiki record ships with the phase.** Write the `wiki/log.md` entry
   and any page updates when the phase lands — do not wait to be asked.

## Commands

Use the Makefile targets — do not invent your own invocations.

| Command | What it does |
|---|---|
| `make install` | `uv sync --locked --extra dev --extra pipeline` |
| `make lock-check` | `uv lock --check` |
| `make lint` | ruff check + format check |
| `make typecheck` | mypy over `src/`, `website/backend/`, `infra/`, `scripts/` (both extras) |
| `make test` | pytest `tests/unit` with coverage, enforced against the floor |
| `make docs-sync` | Asserts `CLAUDE.md` is still a git symlink to `AGENTS.md` |
| `make public-check` | Rejects tracked account metadata and private filenames |
| `make audit` | pip-audit over the locked dependencies |
| `make synth` | CDK synth (`ENV=dev` default; CLI version pinned in the Makefile) |
| `make synth-all` | CDK synth for **both** `dev` and `prod` — the cdk-nag gate |
| `make diagrams` | Synth and render PNG, editable SVG, and DOT CDK diagrams; requires Graphviz |
| `make security` | lock-check + audit + synth-all |
| `make frontend-check` | `npm ci`, type check, and tests for `website/frontend/` (not in CI) |
| `make bootstrap` | `cdk bootstrap`, once per account/region before the first deploy |
| `make diff-stack STACK=…` / `make deploy-stack STACK=…` | Diff/deploy one stack **and its dependencies** — see the warning below |
| `make deploy` / `make destroy` | CDK deploy/destroy all stacks. `deploy` refuses while the website stack builds; see below |
| `make verify-deploy` | What a deploy actually changed, per resource |
| `make smoke` | `tests/integration` against the deployed API (resolves the URL from stack outputs; Phase 6 signs each request with SigV4) |
| `make wiki-init` / `wiki-index` / `wiki-search Q=…` / `wiki-ingest SOURCE=…` / `wiki-lint` | Wiki toolkit; see `wiki/AGENTS.md` |
| `make graph` / `graph-query Q=…` / `graph-explain NODE=…` / `graph-hooks` | graphify code graph; see "Knowledge graph" below |

`ENV=dev|prod` selects the environment for every CDK target.

**`deploy-stack` is not a single-stack deploy.** CDK deploys the named stack and
every stack it depends on, so a pending change anywhere in that chain ships with
it. On 2026-08-09 a `Mlops-Dev-Monitoring` deploy also shipped sub-phase 2G,
because Monitoring imports the alert topic from `Mlops-Dev-Security`. The diff
announces this on every run — `Including dependency stacks: …` — and it is easy
to read past. Under the one-phase-per-change-set rule, read that line before
deploying, and run `make verify-deploy` after to see which stacks actually
changed.

Always run Python through `uv run --locked ...`. Never use bare `python`
or `pip` for project code.

## CI

`.github/workflows/ci.yml` runs on every PR and push to `main`, and calls
the Make targets rather than restating them: `install`, `lint`, `typecheck`,
`test`, `docs-sync`, `wiki-lint`, `public-check`, `audit`, `synth-all` — plus a
Gitleaks scan of every commit in a separate job. All are blocking.

`.github/workflows/codeql.yml` runs only after the repository becomes public.
The current private plan does not provide code scanning.

`.github/workflows/deploy.yml` is `workflow_dispatch` only. It deploys and
smoke-tests dev. A boolean input can opt in to prod after dev succeeds. It
assumes a role through OIDC federation and uses no long-lived AWS key. **It has
never run.** Both GitHub environments allow deployments only from `main`, and
dev holds the live OIDC role ARN as an environment secret. Prod has no role ARN
until its stack is deployed. The current plan does not support required
environment reviewers while the repository is private. Every deployment so
far came from a workstation.

## Code map — where things live

Look here **before** writing anything new:

| Path | Contents |
|---|---|
| `src/common/` | Shared code — the **only** place for cross-module shared logic. `features.py` owns the whole raw-value contract (`FEATURE_COLUMNS`, `LABEL_COLUMN`, `FEATURE_VOCABULARY`, encoding); `schema.py` is the Pydantic runtime contract (`CustomerRecord`); `events.py` is `log_event`, the one-JSON-line-per-event convention; `drift.py` is the PSI drift statistic, shared by the preprocessing step and the drift Lambda. |
| `src/ingestion/` | Schema-validation Lambda (`validate_handler.py`) |
| `src/serving/` | Endpoint-deploy Lambda (`deploy_handler.py`), inference proxy Lambda (`proxy_handler.py`) |
| `src/monitoring/` | Drift Lambda (`drift_handler.py`) — scores a capture window and emits the violation event; retrain Lambda (`retrain_handler.py`) — violation → new pipeline execution. Together the closing edge of the drift loop |
| `src/pipeline/` | `preprocess.py`, `evaluate.py`, the pipeline definition (`pipeline.py`), and `evaluation_runtime/` (the FrameworkProcessor entrypoint) |
| `infra/app.py` | CDK entrypoint. `load_config()`, `stack_prefix()`, `build_app()` — the single source of the config loader, the stack-name formula, and the dependency graph; the tests import all three. |
| `infra/security_checks.py` | cdk-nag gate plus every acknowledgement, each bound to one construct and naming the phase that removes it |
| `infra/stacks/` | One CDK stack per file: data, ingestion, training, registry, serving, monitoring, security, security_monitoring, cicd. Plus `shared.py` (cross-stack helpers + the `PlatformConfig` TypedDicts) and `lambda_code.py` (the shared bundled Lambda asset). |
| `infra/config/` | `dev.yaml` / `prod.yaml` environment config |
| `infra/policies/` | The repository-owned CloudFormation execution boundary, split across `mlops-cloudformation-execution-policy.json` and `-extension.json` because AWS caps one managed policy at 6144 characters. Version-pinned and fingerprint-tested |
| `scripts/` | Operational CLIs: `evaluate_api.py`, `verify_deployment.py`, `send_drift_traffic.py`, `wiki.py`. Plus the two CLIs that back a Make gate: `check_public_release.py` (`make public-check`) and `prepare_cdk_diagrams.py` (`make diagrams`) |
| `website/` | The demo website, and the one place its code lives. `backend/` is the FastAPI service (`app.py` routes, `services.py` every AWS call, `settings.py` the environment contract, `rate_limit.py`); `frontend/` is React and TypeScript built by Vite; `local/compose.yaml` runs both beside `amazon/dynamodb-local` and `minio/minio`. The backend imports the feature contract from `src/common/` and MUST NOT restate it. Its CDK stack stays in `infra/stacks/website_stack.py`, and its tests stay in `tests/unit/`. **On hold; see the wiki before any website work.** |
| `tests/unit/` | Mirrors source modules as `test_<module>.py` — including one per CDK stack; `conftest.py` holds the session-scoped synthesized CDK app and reads the shared sample record from `sample.json` |
| `tests/integration/` | `make smoke` only — skips itself unless `API_URL` is set |
| `sample.json`, `sample-high-risk.json` | The canonical request payloads, shared by the unit fixtures and by hand-run `curl` calls — change them together, never restate one in a test |
| `telco/` | `telco.csv`, the raw dataset |
| `wiki/` | Knowledge base — governed by `wiki/AGENTS.md`; follow it for any wiki work |
| `.claude/skills/graphify/` | The graphify skill and its references, installed project-scoped |
| `.graphifyignore` | Paths graphify MUST NOT extract; it merges with `.gitignore` and wins on a conflict |
| `graphify-out/` | The generated graph — build output, untracked. See "Knowledge graph" below |

## Knowledge graph (graphify)

`graphify` builds a queryable graph of the repository with local AST parsing.
It reads code, Markdown, and config, and it writes `graph.json`, `graph.html`,
and `GRAPH_REPORT.md` into `graphify-out/`. The extraction needs no LLM and no
network call.

The wiki and the graph answer different questions. Keep the split:

- **The wiki is the source of record.** It holds history, decisions, phase
  status, dates, and the reasoning behind them. A human wrote or approved
  every page. Cite the wiki when the question is "why", "when", or "what is
  the state".
- **The graph is a derived index.** It holds structure — which symbol calls
  which, which file defines what, which files cluster together. Every node
  comes from a parse of the current tree. Use it when the question is "where"
  or "what connects to what".

Rules:

1. **`graphify-out/` is build output, never source.** It is untracked, the
   same as `infra/cdk.out/`. Rebuild it with `make graph`; do not commit it,
   and do not cite a generated file as evidence on a wiki page.
2. **A stale graph is silent.** `GRAPH_REPORT.md` records the commit it was
   built from. Check that line before you trust an answer, and run `make graph`
   when it does not match `git rev-parse HEAD`.
3. **`make graph-hooks` installs three hooks, and they still miss two cases.**
   `graphify hook install` writes `post-commit` and `post-checkout`. Neither
   one runs for a `git pull`, so the target also installs
   `scripts/git-hooks/post-merge`, which covers a pull and a merge. Every
   rebuild runs detached, so no hook holds the shell. Two limits remain:
   - **The hooks exit immediately in a linked worktree.** This repository uses
     worktrees, so a commit under `.claude/worktrees/` rebuilds nothing. The
     graph belongs to the primary checkout.
   - **Git does not track a hook.** A fresh clone has none until someone runs
     `make graph-hooks`.

   Run `make graph` by hand in both cases. `GRAPHIFY_SKIP_HOOK=1` turns every
   hook off for one command. The target also removes the union merge driver
   that `graphify hook install` registers for `graphify-out/graph.json`,
   because this repository never tracks that file.
4. **The graph MUST NOT become a second knowledge base.** When a query
   produces durable knowledge, file it on a wiki page under the SCHEMA.md
   contract. Do not hand-edit a file in `graphify-out/`.

## Anti-duplication rules (mandatory)

This codebase must not accumulate duplicate code. These rules are a
required workflow, not suggestions.

1. **Search before you write.** Before creating any function, class,
   constant, or helper, search the repo for an existing implementation —
   by likely names *and* by domain keywords. Example: before writing
   feature-encoding logic, grep for `encode`, `feature`, and
   `FEATURE_COLUMNS`. State what you found (or confirmed absent) before
   adding new code.
2. **Reuse > extend > write new.** In that order: call the existing
   function as-is; if it covers ~80% of the need, extend it with a
   parameter or branch; only write new code when nothing close exists.
   Never write a near-copy of an existing function.
3. **Single source of truth for shared logic.** Logic needed by two or
   more modules belongs in `src/common/` — never copy-pasted between
   handlers, pipeline steps, or stacks. Schema and feature definitions
   must only ever come from `src/common/schema.py` and
   `src/common/features.py`.
4. **No new files for code that fits an existing module.** Creating a new
   utility module requires a stated reason why no existing module fits.
   Existing new-module reasons are written into the module docstrings —
   match that bar.
5. **Pre-finish duplication check.** Before declaring a task done, re-read
   your diff. For every new function or constant you added, verify no
   existing equivalent exists anywhere in the repo. If a duplicate slipped
   in, consolidate before finishing.
6. **Modify, don't fork.** When changing behavior, update the existing
   function and its call sites. Do not leave the old path in place and add
   a parallel `_v2`/`_new`/`foo2` variant.

## Writing style (mandatory)

Two standards govern every comment, docstring, Markdown file, wiki page,
commit message, and response in this repository:

- **ASD-STE100** governs the prose. Write short, plain, active sentences.
- **RFC 2119** governs the requirement words. Write MUST, MUST NOT,
  SHOULD, SHOULD NOT, and MAY in uppercase when you state a rule.

The two standards do not conflict. RFC 2119 defines the strength of a
rule. ASD-STE100 defines every other word in the sentence.

### Requirement keywords, per RFC 2119

Use these five keywords, in uppercase, and only in a normative statement:

| Keyword | Meaning |
|---|---|
| **MUST** | An absolute requirement. Break it and the change is wrong. |
| **MUST NOT** | An absolute prohibition. |
| **SHOULD** | A strong recommendation. Deviate only with a stated reason. |
| **SHOULD NOT** | A strong recommendation against. The same reason rule applies. |
| **MAY** | A true option. Both choices are correct. |

Rules for the keywords:

1. **Uppercase marks the keyword.** Uppercase MUST carries the RFC 2119
   meaning. Lowercase "must" is ordinary prose and carries no strength.
2. **One word per strength.** Do not write REQUIRED, SHALL, SHALL NOT,
   RECOMMENDED, NOT RECOMMENDED, or OPTIONAL. RFC 2119 permits those
   synonyms; ASD-STE100 forbids two words for one meaning. The five
   keywords in the table are the whole set.
3. **State who the rule binds.** Write "The pipeline modules MUST keep
   `from __future__ import annotations`", not "annotations MUST be kept".
4. **Reserve the keywords for real requirements.** Use a keyword when a
   reader who ignores it breaks the build, the deploy, or the security
   boundary. Describe everything else in plain sentences.
5. **Give SHOULD an escape.** When you write SHOULD, name the condition
   that permits the deviation. A SHOULD with no stated escape is a MUST —
   write MUST instead.
6. **Do not stack keywords.** One requirement per sentence.

## Comments and docstrings (mandatory)

A comment earns its place by telling a reader something the code cannot.
Delete it otherwise. The ASD-STE100 rules below apply to every comment
and docstring; the RFC 2119 keywords apply when a comment states a rule
the next editor MUST obey.

**Sentences**

- Procedural sentences: 20 words maximum. Descriptive: 25 words maximum.
- One idea per sentence. Do not join two actions with "and".
- Use the active voice and name the actor: "SageMaker owns this group",
  not "this group is owned".
- Use the imperative for an instruction: "Update this role in place."
- Use the present tense. Describe what the code does now.

**Words**

- One word, one meaning. Use the simplest exact word: "use" over
  "utilize", "start" over "initiate", "before" over "prior to".
- Do not drop articles. Write "Read the file", not "Read file".
- Repeat the same term for the same thing. Do not vary it for style.
- No idioms, metaphors, or humor.
- Reproduce code identifiers, paths, commands, and AWS error names
  exactly. Never simplify one to read better.

**What a comment must not contain**

1. **No history.** Do not write what the code used to be, what a previous
   version did, or what a past incident was. Git and the wiki hold that.
   Write the rule that holds today. Not "the host's wheels once caused a
   pydantic_core failure" but "the host's wheels fail at runtime".
2. **No justification.** Do not argue for the code. Drop "that is the
   point", "deliberately", "worth it", "reviewed and diffed", "would have
   shipped", "this test pins". State the constraint and stop.
3. **No status or dates.** Do not write phase numbers as bookkeeping,
   enablement dates, or observation windows — "3C. Enabled 2026-08-02" is
   noise in the code. `wiki/pages/architecture/phased-security-hardening.md`
   is the status board. Name a phase only when it identifies work the code
   still owes, such as a cdk-nag acknowledgement `reason` string, which
   must name the phase that removes it.
4. **No coverage or test-debt narration.** Do not write that something
   had no test or sat at 0%.

**Keep a comment when it carries one of these**

- A constraint that fails at runtime rather than at synth or lint.
- A non-obvious AWS or SDK behaviour, and what breaks without the code.
- A rule the next editor MUST obey, such as "Update this role in place.
  You MUST NOT replace it — the deployed pipeline pins this ARN".
- Why an alternative was not taken, stated as a fact about the
  alternative, not as a defence of the choice.

**Maintenance.** When you change code, update or delete the comments
around it in the same change set. A comment that names a file, symbol, or
behaviour that no longer exists is a defect — fix it when you see it.

## Conventions

- Line length: target 80–90 characters (ruff's hard limit is 100, but
  stay under 90). Python 3.12; ruff rules E, F, I, W, UP, B, ANN, with
  only ANN401 ignored (`**kwargs: Any` is correct for CDK/jsii passthrough).
- **Every function in `src/`, `infra/`, and `scripts/` must be fully
  annotated** — parameters and return. Enforced by `make typecheck`
  (mypy, `disallow_untyped_defs`) and ruff's ANN rules, both blocking in
  CI. Prefer builtin generics and PEP 604 unions (`list[dict[str, Any]]`,
  `str | None`); never `typing.List`/`typing.Optional`. Parameterize
  generics — bare `dict` is as good as unannotated. `tests/` is exempt
  from ANN and from mypy's `files` list.
- The shape of `infra/config/*.yaml` is defined once, as `PlatformConfig`
  in `infra/stacks/shared.py`. Thread that type through; do not re-type a
  config parameter as a bare `dict`. `load_config()` in `infra/app.py` is
  the one boundary where `yaml.safe_load`'s `Any` is narrowed.
- `src/pipeline/` runs in the SageMaker managed image on an **older Python
  than 3.12**. Those modules keep `from __future__ import annotations` and
  must not use PEP 604 unions in runtime-evaluated positions.
- Tests go in `tests/unit/` and mirror the source module they cover; run
  with `make test`. Coverage is measured on every run and enforced against
  `fail_under` in `pyproject.toml` (currently **94.14**). That floor is a
  ratchet: raise it when a phase lands, never lower it to make a red run
  green. Take a new floor from the printed total rounded down — the
  comparison uses the unrounded value.
- `infra/cdk.out/` is build output, never source. It holds synthesized
  Lambda bundles with vendored third-party packages, and is excluded from
  mypy and from coverage — keep it out of any new tooling config too.
- Never commit account-specific literals (account IDs, ARNs, endpoints).
  Use placeholders in code and docs; real values live only in `.env`.

## Reporting what a deployment changed (mandatory)

**Never state what a deployment changed based on a summary status.** A
stack reaches `UPDATE_COMPLETE` even when CloudFormation resolved the
template to a no-op and modified no resource at all. Asserting resource
changes from stack status has already produced two incorrect reports.

1. **Run `make verify-deploy SINCE=<YYYY-MM-DD>` after any deploy, and
   report from its output.** It lists, per stack, the last-updated
   timestamp and the resources that actually changed — and says so
   explicitly when a stack changed nothing. Use a profile that can
   enumerate stacks: `AWS_PROFILE=${AWS_SECURITY_AUDITOR_USER_NAME}`. The
   deploy identity (`${MLOPS_DEPLOYER_USER_NAME}`) lacks
   `cloudformation:ListStacks` and fails here with AccessDenied. Deploying and
   verifying use different identities.
2. **`cdk diff` is intent, not outcome.** CloudFormation resolves
   intrinsics such as `Ref: AWS::Partition` and then skips resources whose
   resolved form is unchanged. A diff hunk does **not** mean the resource
   was modified.
3. **In the console, the stack list's default `Created time` column never
   changes on update.** It cannot tell you whether a stack was deployed
   today. Use the `Updated time` column or the per-stack Events tab.

The general rule: report at the granularity your evidence supports. If
the claim is about resources, the evidence must be resource-level.

## How to work and respond

- **Be brief.** Keep responses focused and concise. Keep disclaimers and
  caveats short, and spend most of the response on the main answer. When
  asked to explain something, give a high-level summary unless an in-depth
  explanation is specifically requested.
- **Narrate lightly.** Before your first tool call, say in one sentence
  what you're about to do. While working, give a brief update only when
  you find something important or change direction. When you finish, lead
  with the outcome: the first sentence answers "what happened" or "what
  did you find," with supporting detail after it.
- **Match the scope asked.** Make routine judgment calls yourself; check
  in only when different readings of the request would lead to materially
  different work. If the request seems mistaken or a better approach
  exists, say so in a sentence and continue with the task as asked rather
  than quietly narrowing, widening, or transforming it. Finish the whole
  task, and stop short of actions clearly beyond what was asked.
- **Delegate rarely.** Use a subagent only for large, genuinely
  independent and parallelizable work — a wide multi-file investigation,
  say. Do not delegate what you can finish yourself in a handful of tool
  calls, and never use a subagent to verify or double-check your own work.
  If one subagent can do it, use one; keep spawn counts low.
- **Correct only what matters.** Correct an earlier statement when the
  error would change the user's code, conclusions, or decisions. State the
  correction plainly and briefly, then continue. For slips that change
  nothing, make the fix and move on without noting it.
