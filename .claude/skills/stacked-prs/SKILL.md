---
name: stacked-prs
description: "The 150-line cap on a pull request, and how to split a larger feature into a stack of pull requests that merge in order. Read it before opening any pull request, when `make pr-size` blocks a branch, and when planning work that will not fit in one review."
---

# Stacked pull requests

**A pull request MUST NOT add more than 150 lines of code.** A feature that
needs more MUST ship as a stack: several pull requests, each based on the one
below it, merged in order.

A large review is a shallow review. The cap trades one unreadable pull request
for several that a human finishes.

## What the cap counts

`make pr-size` measures it, and the `Stop` hook runs the same check.

| Counted | Not counted |
|---|---|
| `src/`, `infra/`, `scripts/`, `website/` | `tests/` |
| Added lines only | Deleted lines |
| | Markdown, including `wiki/` |
| | `uv.lock`, `package-lock.json` |
| | `infra/cdk.out/`, `website/frontend/dist/` |

Tests and the wiki record do not count. The cap MUST NOT discourage either
one — the phase rule requires the wiki record, and the coverage floor requires
the tests.

The base is the pull request's own base branch, read from `gh`. A stacked
branch therefore measures against the branch below it, not against `main`.
`AGENT_PR_BASE=origin/<branch>` overrides it before the pull request exists.

## How to plan the split

Split along the axis that lets each piece stand on its own. In order of
preference:

1. **By layer.** The mechanism first, then what uses it.
2. **By stage.** The read path, then the write path.
3. **By flag.** The dormant code first behind a false flag, then the flip.

Each pull request in the stack MUST pass `make check` on its own. A piece that
only works once the next one lands is not a split — it is a broken commit.

Never split by file type. "All the code" then "all the tests" gives two pull
requests that neither reviews nor reverts cleanly.

## How to build the stack

```bash
git checkout -b feature-part-1 main
# … first change, then open the pull request against main
git checkout -b feature-part-2 feature-part-1
# … second change, then open the pull request against feature-part-1
gh pr create --base feature-part-1 --head feature-part-2
```

Rules for the stack:

- **State the merge order** in every pull request body, and name the parent.
  Write "Stacked on #91. Merge that first."
- **Merge bottom up.** After the parent merges, rebase the child onto `main`
  and force-push it. GitHub retargets the base, and it does not rebase the
  commits.
- **A fix belongs in the pull request that owns the line.** Do not patch a
  parent's bug in the child.

## The escape

Some changes do not split: a rename across many files, a file move, a
generated file, a vendored dependency. Set `AGENT_PR_SIZE_OK=1` for that
branch, and say in the pull request body why it does not split. The escape is
for a change that **cannot** split, never for one that is inconvenient to.
