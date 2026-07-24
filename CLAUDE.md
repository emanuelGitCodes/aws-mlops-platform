# CLAUDE.md

Agent instructions for this repository. Follow these exactly.

## Project overview

Portfolio-grade MLOps reference platform on AWS: SageMaker Pipelines for
training/evaluation, serverless inference behind API Gateway, and a
drift→retrain loop — all defined in CDK. Python 3.12, dependencies managed
with `uv`. The model (Telco churn, XGBoost) is deliberately simple; the
engineering is the deliverable.

## Commands

Use the Makefile targets — do not invent your own invocations.

| Command | What it does |
|---|---|
| `make install` | `uv sync --locked --extra dev` |
| `make lint` | ruff check + format check |
| `make typecheck` | mypy over `src/`, `infra/`, `scripts/` |
| `make test` | pytest `tests/unit` |
| `make synth` | CDK synth (`npx aws-cdk@2.1130.0`, `ENV=dev` default) |
| `make security` | lock-check + pip-audit + synth |
| `make deploy` / `make destroy` | CDK deploy/destroy all stacks |
| `make verify-deploy` | What a deploy actually changed, per resource |

Always run Python through `uv run --locked ...`. Never use bare `python`
or `pip` for project code.

## Code map — where things live

Look here **before** writing anything new:

| Path | Contents |
|---|---|
| `src/common/` | Shared code. `schema.py` (`CustomerRecord`), `features.py` (`FEATURE_COLUMNS`, `LABEL_COLUMN`). The **only** place for cross-module shared logic. |
| `src/ingestion/` | Schema-validation Lambda (`validate_handler.py`) |
| `src/serving/` | Endpoint-deploy Lambda (`deploy_handler.py`), inference proxy Lambda (`proxy_handler.py`) |
| `src/pipeline/` | Preprocess, evaluate, and pipeline definition for SageMaker |
| `infra/stacks/` | One CDK stack per file (data, ingestion, training, registry, serving, monitoring, security) |
| `infra/config/` | `dev.yaml` / `prod.yaml` environment config |
| `scripts/` | Operational CLIs (`evaluate_api.py`, `verify_deployment.py`, `wiki.py`, ...) |
| `tests/unit/` | Mirrors source modules as `test_<module>.py` |
| `wiki/` | Knowledge base — governed by `wiki/AGENTS.md`; follow it for any wiki work |

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
5. **Pre-finish duplication check.** Before declaring a task done, re-read
   your diff. For every new function or constant you added, verify no
   existing equivalent exists anywhere in the repo. If a duplicate slipped
   in, consolidate before finishing.
6. **Modify, don't fork.** When changing behavior, update the existing
   function and its call sites. Do not leave the old path in place and add
   a parallel `_v2`/`_new`/`foo2` variant.

## Conventions

- Line length: target 80–90 characters (ruff's hard limit is 100, but
  stay under 90). Python 3.12; ruff rules E, F, I, W, UP, B, ANN.
- **Every function in `src/`, `infra/`, and `scripts/` must be fully
  annotated** — parameters and return. Enforced by `make typecheck`
  (mypy, `disallow_untyped_defs`) and ruff's ANN rules, both blocking in
  CI. Prefer builtin generics and PEP 604 unions (`list[dict[str, Any]]`,
  `str | None`); never `typing.List`/`typing.Optional`. Parameterize
  generics — bare `dict` is as good as unannotated. `tests/` is exempt.
- The shape of `infra/config/*.yaml` is defined once, as `PlatformConfig`
  in `infra/stacks/shared.py`. Thread that type through; do not re-type a
  config parameter as a bare `dict`.
- `src/pipeline/` runs in the SageMaker managed image on an **older Python
  than 3.12**. Those modules keep `from __future__ import annotations` and
  must not use PEP 604 unions in runtime-evaluated positions.
- Tests go in `tests/unit/` and mirror the source module they cover; run
  with `make test`.
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
   explicitly when a stack changed nothing.
2. **`cdk diff` is intent, not outcome.** CloudFormation resolves
   intrinsics such as `Ref: AWS::Partition` and then skips resources whose
   resolved form is unchanged. A diff hunk does **not** mean the resource
   was modified.
3. **In the console, the stack list's default `Created time` column never
   changes on update.** It cannot tell you whether a stack was deployed
   today. Use the `Updated time` column or the per-stack Events tab.

The general rule: report at the granularity your evidence supports. If
the claim is about resources, the evidence must be resource-level.
