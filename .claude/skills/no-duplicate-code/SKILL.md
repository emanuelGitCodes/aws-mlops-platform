---
name: no-duplicate-code
description: "The mandatory anti-duplication workflow for this repository. Read it before adding any function, class, constant, helper, or new module, and before declaring a code change done. Holds the search recipes, the reuse-before-write order, and the rule that shared logic lives only in src/common/."
---

# No duplicate code

This codebase must not accumulate duplicate code. These rules are a
required workflow, not suggestions.

1. **Search before you write.** Before creating any function, class,
   constant, or helper, search the repo for an existing implementation —
   by likely names *and* by domain keywords. State what you found (or
   confirmed absent) before adding new code.
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

## Search recipes

Search by name and by domain keyword. One search is not enough — the
existing implementation rarely carries the name you were about to use.

| You are about to write | Search first |
|---|---|
| Feature encoding or a column list | `FEATURE_COLUMNS`, `FEATURE_VOCABULARY`, `encode`, `feature` |
| A request or record shape | `CustomerRecord`, `schema`, `pydantic`, `BaseModel` |
| Structured logging | `log_event`, `events`, `json.dumps` |
| A drift or distribution statistic | `psi`, `drift`, `bins` |
| A cross-stack CDK helper or a config type | `infra/stacks/shared.py`, `PlatformConfig` |
| A stack name or an env prefix | `stack_prefix`, `load_config` |
| An AWS call in the website backend | `website/backend/services.py` |
| A sample payload for a test | `sample.json`, `sample-high-risk.json` |

Run the search two ways, and read the hits rather than the counts:

```bash
grep -rn "<keyword>" src infra scripts website tests --include='*.py'
```

The code graph answers the same question by structure when it is fresh:

```bash
make graph-query Q='what already computes the PSI statistic?'
```

Check the commit line in `graphify-out/GRAPH_REPORT.md` against
`git rev-parse HEAD` first. A stale graph is silent, and the hooks do not
rebuild it inside a worktree.

## Before you finish

Re-read the diff and list every symbol you added:

```bash
git diff -U0 main -- '*.py' | grep -E '^\+(def |class |[A-Z_]+ ?=)'
```

For each one, name the search that proved no equivalent exists. If you
cannot name it, you have not done rule 1.
