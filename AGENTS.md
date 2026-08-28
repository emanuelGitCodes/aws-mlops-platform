# AGENTS.md

Agent instructions for this repository. Follow these exactly.

This file is the single source. `CLAUDE.md` at the repo root is a symlink
to it, so both paths always serve the same content — edit here, never
there.

**This file holds only what an agent needs before its first tool call.**
Procedure and status live elsewhere, and the pointers below name the place.
Add a rule here only when an agent breaks something without it on the first
action. Everything else belongs in a skill under `.claude/skills/` or on a
wiki page.

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

## Status: read the wiki, not this file

**The wiki is the source of record.**
`wiki/pages/architecture/phased-security-hardening.md` holds the phase map,
the per-phase status, and every date. Read it before you start security or
phase work. This file states no phase status, because a copy here goes stale
and an agent trusts it.

Four invariants hold today, and each one costs money or breaks a boundary
when an agent misses it:

1. **The website work is ON HOLD, and its stack MUST NOT be deployed.**
   `make deploy` refuses whenever the environment builds it. No AWS resource
   exists for the stack. Read
   [the local-first rebuild](wiki/pages/decisions/website-local-first-rebuild.md)
   before any website work.
2. **The repository stays private.** It is prepared for public release, and
   it MUST stay private until the history choice is explicit: a clean public
   mirror, or a history rewrite. `make public-check` is the standing gate,
   and CI runs it.
3. **The execution boundary spans two managed policies. Add new grants to
   the extension.** AWS caps one managed policy at 6144 characters.
   `MLOpsCloudFormationExecutionPolicy` holds 5888 of its own, so it has no
   room. `MLOpsCloudFormationExecutionPolicyExtension` carries the overflow.
   Both attach to `cdk-hnb659fds-cfn-exec-role-*`, so the grants union. Size,
   not the version slots, is what blocks a change; `make test` measures both
   documents against the quota.
4. **Never commit account-specific literals** — account IDs, ARNs, endpoints,
   IAM user names, API Gateway ids. Use the `.env.example` placeholders in
   code and docs. Real values live only in the local gitignored `.env`.

Phase work follows two rules: one phase per change set, and the wiki record
ships with the phase. The `phase-change-set` skill holds the full gate.

## Commands

Use the Makefile targets — do not invent your own invocations.

| Command | What it does |
|---|---|
| `make install` | `uv sync --locked --extra dev --extra pipeline` |
| `make lock-check` | `uv lock --check` |
| `make lint` | ruff check + format check |
| `make typecheck` | mypy over `src/`, `website/backend/`, `infra/`, `scripts/` |
| `make test` | pytest `tests/unit` with coverage, enforced against the floor |
| `make check` | lint + typecheck + test + docs-sync + public-check + wiki-lint |
| `make agent-hooks` | Install the agent hooks into `.claude/settings.json` |
| `make pr-size` | Measure the branch against the 150-line cap |
| `make docs-sync` | Asserts `CLAUDE.md` is still a git symlink to `AGENTS.md` |
| `make public-check` | Rejects tracked account metadata and private filenames |
| `make audit` | pip-audit over the locked dependencies |
| `make synth` | CDK synth (`ENV=dev` default; CLI version pinned in the Makefile) |
| `make synth-all` | CDK synth for **both** `dev` and `prod` — the cdk-nag gate |
| `make diagrams` | Render PNG, SVG, and DOT CDK diagrams; requires Graphviz |
| `make security` | lock-check + audit + synth-all |
| `make frontend-check` | `npm ci`, type check, and tests for `website/frontend/` |
| `make bootstrap` | `cdk bootstrap`, once per account/region before the first deploy |
| `make diff-stack STACK=…` / `make deploy-stack STACK=…` | Diff/deploy one stack **and its dependencies** |
| `make deploy` / `make destroy` | CDK deploy/destroy all stacks |
| `make verify-deploy` | What a deploy actually changed, per resource |
| `make smoke` | `tests/integration` against the deployed API |
| `make wiki-init` / `wiki-index` / `wiki-search Q=…` / `wiki-ingest SOURCE=…` / `wiki-lint` | Wiki toolkit |
| `make graph` / `graph-query Q=…` / `graph-explain NODE=…` / `graph-hooks` | graphify code graph |

`ENV=dev|prod` selects the environment for every CDK target.

Always run Python through `uv run --locked ...`. Never use bare `python`
or `pip` for project code.

**`deploy-stack` is not a single-stack deploy.** CDK deploys the named stack
and every stack it depends on, so a pending change anywhere in that chain
ships with it. The diff announces this on every run — `Including dependency
stacks: …` — and it is easy to read past. Read that line before you deploy.
The `phase-change-set` and `deploy-verify` skills hold the rest.

`.github/workflows/ci.yml` calls these same targets on every PR and push to
`main`: `install`, `lint`, `typecheck`, `test`, `docs-sync`, `wiki-lint`,
`public-check`, `audit`, `synth-all`, plus a Gitleaks job. All are blocking.
`deploy.yml` is `workflow_dispatch` only and has never run. `codeql.yml`
starts only after the repository becomes public.

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
| `infra/policies/` | The repository-owned CloudFormation execution boundary, split across `mlops-cloudformation-execution-policy.json` and `-extension.json`. Version-pinned and fingerprint-tested |
| `scripts/` | Operational CLIs: `evaluate_api.py`, `verify_deployment.py`, `send_drift_traffic.py`, `wiki.py`. Plus the CLIs that back a Make gate: `check_public_release.py` (`make public-check`) and `prepare_cdk_diagrams.py` (`make diagrams`) |
| `website/` | The demo website, and the one place its code lives. `backend/` is the FastAPI service; `frontend/` is React and TypeScript built by Vite; `local/compose.yaml` runs both beside `amazon/dynamodb-local` and `minio/minio`. The backend imports the feature contract from `src/common/` and MUST NOT restate it. **On hold; see the wiki before any website work.** |
| `tests/unit/` | Mirrors source modules as `test_<module>.py` — including one per CDK stack; `conftest.py` holds the session-scoped synthesized CDK app and reads the shared sample record from `sample.json` |
| `tests/integration/` | `make smoke` only — skips itself unless `API_URL` is set |
| `sample.json`, `sample-high-risk.json` | The canonical request payloads, shared by the unit fixtures and by hand-run `curl` calls — change them together, never restate one in a test |
| `telco/` | `telco.csv`, the raw dataset |
| `wiki/` | Knowledge base — governed by `wiki/AGENTS.md` and the `wiki-record` skill |
| `.claude/skills/` | The project skills. Read the one that matches your task. `.agents/skills/` serves the same skills to a non-Claude harness, and every host-neutral skill there is a symlink to this directory — add a new one the same way |
| `graphify-out/` | The generated code graph — build output, untracked. `make graph` rebuilds it |

The wiki and the graph answer different questions. The wiki is the source of
record: cite it for "why", "when", and "what is the state". The graph is a
derived index: use it for "where" and "what connects to what". A stale graph
is silent, so check the commit line in `graphify-out/GRAPH_REPORT.md` against
`git rev-parse HEAD` before you trust an answer.

## Skills — read the one that matches your task

| Skill | Read it before you |
|---|---|
| `house-style` | Write any comment, docstring, Markdown file, wiki page, or commit message |
| `no-duplicate-code` | Add a function, class, constant, helper, or module |
| `phase-change-set` | Start security-hardening or any other phase work |
| `deploy-verify` | Report what a deploy changed |
| `stacked-prs` | Open a pull request, or plan work that will not fit in one |
| `wiki-record` | Write or edit anything under `wiki/` |
| `graphify` | Query the code graph |

Two rules from `house-style` bind every line you write, so they are here too:
**ASD-STE100** governs the prose — short, plain, active sentences. **RFC 2119**
governs the requirement words — MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in
uppercase, and no other synonym.

One rule from `no-duplicate-code` binds every line you write: **search before
you write**, and state what you found or confirmed absent before you add code.
Logic needed by two modules belongs in `src/common/`.

## One pull request, 150 lines of code

**A pull request MUST NOT add more than 150 lines of code.** A feature that
needs more MUST ship as a stack: several pull requests, each based on the one
below it, merged in order. A large review is a shallow review.

The count covers `src/`, `infra/`, `scripts/`, and `website/`, and it counts
added lines only. Tests, Markdown, `wiki/`, lockfiles, and build output do not
count — the cap MUST NOT discourage a test or the wiki record.

`make pr-size` measures the branch, and the completion gate runs the same
check first. The base comes from the pull request itself, so a stacked branch
measures against the branch below it. State the merge order in every pull
request body.

`AGENT_PR_SIZE_OK=1` releases a branch that cannot split — a rename, a move, a
generated file — and the pull request body MUST say why. Read the
`stacked-prs` skill before you split anything.

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
  with `make test`. Coverage is enforced against `fail_under` in
  `pyproject.toml`. That floor is a ratchet: raise it when a phase lands,
  never lower it to make a red run green. Take a new floor from the printed
  total rounded down — the comparison uses the unrounded value.
- `infra/cdk.out/` and `graphify-out/` are build output, never source. Keep
  them out of any new tooling config, and never commit a generated file.

## Report at the granularity your evidence supports (mandatory)

A claim that work is complete MUST name the command that produced its
evidence, and the claim MUST NOT be broader than that command's output.
Asserting a result from a summary status has already produced two incorrect
reports.

| Claim | Evidence that settles it |
|---|---|
| "the tests pass" | `make test` exit 0, and the printed total against the floor |
| "the change is clean" | `make lint` and `make typecheck`, both exit 0 |
| "CI will be green" | every CI target, and nothing less |
| "the deploy changed X" | `make verify-deploy SINCE=…` resource lines — see the `deploy-verify` skill |
| "I added no duplicate" | the searches from `no-duplicate-code`, quoted |
| "the phase is done" | the go/no-go entry in `wiki/log.md` |

Never report a command you did not run. When you skip a check, say which one
and why. A failing check is a result to report, not a step to repeat until it
passes.

### The completion gate

`scripts/agent_gate.py` enforces this rule, because prose does not. A `Stop`
hook runs it at the end of every turn. It reads `git status`, selects the Make
targets that the changed files need, and runs them. A failure exits 2, and the
output returns to the agent instead of ending the turn.

Two hooks come with it. `SessionStart` prints whether the code graph matches
`HEAD` and whether this is a worktree. A `PreToolUse` hook on Bash asks the
operator before any `deploy`, `destroy`, or `bootstrap` target runs, and it
repeats the dependency-stack warning.

Git does not track `.claude/settings.json`, so a fresh clone has no hook until
someone runs `make agent-hooks`. The tracked source is `.claude/hooks.json`.
The target replaces the `hooks` key and leaves `permissions` alone.

The gate does not run `make synth-all` or `make frontend-check`, which take
minutes. When your change touches `infra/` or `website/frontend/`, it names
them, and you MUST run them before you open a pull request.
`AGENT_GATE_FULL=1` adds them to the gate. `AGENT_GATE_SKIP=1` turns the gate
off for a deliberate handoff of unfinished work — say so when you use it.

## How to work and respond

- **Be brief.** Spend the response on the answer. Keep caveats short. Give a
  high-level summary unless the request asks for depth.
- **Narrate lightly.** Say in one sentence what you are about to do. Report a
  find or a change of direction. Lead the final response with the outcome.
- **Match the scope asked.** Make routine judgment calls yourself. Check in
  only when two readings of the request produce different work. Say so in one
  sentence when the request looks mistaken, then continue as asked.
- **Delegate rarely.** Use a subagent only for wide, parallel investigation.
  Never use a subagent to verify your own work — a check that can pass or fail
  on its own is the verifier.
