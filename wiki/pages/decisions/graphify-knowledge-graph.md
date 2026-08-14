---
type: decision
title: graphify code graph beside the wiki
created: "2026-08-14"
updated: "2026-08-14"
sources: ["https://github.com/Graphify-Labs/graphify", "../../../AGENTS.md", "../../../Makefile", "../../../.graphifyignore", "../../../.gitignore", "../../SCHEMA.md", "../../AGENTS.md", "../architecture/generated-cdk-diagrams.md", "../answers/repo-walkthrough.md"]
summary: "graphify indexes the tree into a disposable, untracked code graph, and the wiki keeps its role as the source of record for history, decisions, and status."
---
# graphify code graph beside the wiki

## Confirmed

- **The repository holds graphify, and the first graph exists.** `uv` installs
  the `graphifyy` package (version 0.9.42) as a tool, so the package stays out
  of `uv.lock` and out of the project environment. The skill bundle sits in the
  project at `.claude/skills/graphify/`, as `SKILL.md` and a `references/`
  directory.
- **The first build covers the code and the wiki together.** The build of
  2026-08-14, from commit `90dc79d`, read 176 files and about 368,850 words.
  It produced 2141 nodes, 2953 edges, and 209 communities. The extraction
  reports 100% EXTRACTED edges and 12 INFERRED edges, at an average confidence
  of 0.53. It cost 0 input and 0 output tokens.
- **Those counts describe one build, not a fixed size.** Every rebuild moves
  them with the tree. The wiki rewrite of the same day took the graph to 2169
  nodes and 220 communities at commit `21f1129`. Read the current number from
  `GRAPH_REPORT.md`. Do not treat a number on this page as the live size.
- **The extraction is local and deterministic.** `graphify update .` parses
  each file with tree-sitter. It calls no model and no network service. An
  LLM backend is optional, and this repository does not configure one.
- **Three files come out of a build.** `graphify-out/` holds `graph.json`
  (the queryable graph), `graph.html` (an interactive view), and
  `GRAPH_REPORT.md` (communities, hubs, and suggested questions). A
  `cache/` directory and a `manifest.json` hold the per-file extraction state.
- **`graphify-out/` is untracked.** `.gitignore` excludes it, for the reason it
  excludes `infra/cdk.out/`: any clone can rebuild this output in about one
  minute. The 2 MB `graph.json` and the 1.8 MB `graph.html` therefore never
  enter the history of a repository that the team prepares for public release.
- **`.graphifyignore` narrows the corpus.** It excludes `graphify-out/`,
  `infra/cdk.out/`, the third-party `diagrams/cdk-dia-icons/`
  icon set, and `uv.lock`. graphify merges this file with `.gitignore`, and
  the patterns here win on a conflict. `.env` and `telco/` are already
  excluded through `.gitignore`.
- **Three Make targets front the tool.** `make graph` rebuilds the graph,
  `make graph-query Q=…` runs a traversal for a question, and
  `make graph-explain NODE=…` describes one node and its neighbours.
- **Three git hooks rebuild the graph automatically.** `graphify hook install`
  wrote a `post-commit` hook and a `post-checkout` hook into `.git/hooks/` on
  2026-08-14. The repository adds a third, `scripts/git-hooks/post-merge`, for
  the pull and merge case that graphify does not cover. `make graph-hooks`
  installs all three. Each one starts a detached rebuild, so no hook holds the
  shell. The installer also offers a union merge driver for
  `graphify-out/graph.json`. The target removes that registration, because this
  repository never tracks the file the driver would merge.

## Synthesis

- **The two systems answer different questions, and the split MUST hold.**
  The wiki holds history, decisions, phase status, dates, and the reasoning
  behind them, and a human approves every page. The graph holds structure:
  which symbol calls which, which file defines what, and which files cluster
  together. Ask the wiki "why", "when", and "what is the state". Ask the graph
  "where" and "what connects to what".
- **The graph is evidence about the tree, not about AWS.** It is built from
  source files. It cannot show a deployed resource, an alarm state, or a
  policy version in the account. This is the same limit that
  [generated CDK diagrams](../architecture/generated-cdk-diagrams.md) carry:
  a synthesized view is not live state.
- **A wiki page MUST NOT cite a generated file as evidence.** `graphify-out/` is
  disposable and untracked, so a `sources:` entry that points into it cannot
  resolve for the next reader. Cite the repository path that the graph led you
  to instead.
- **The graph goes stale without warning.** `GRAPH_REPORT.md` names the commit
  it was built from. A query against an old graph answers about old code and
  looks correct. Read that line before you trust an answer.
- **The hooks narrow the staleness window. They do not close it.** Two cases
  still produce no rebuild. The hooks exit at once inside a linked worktree, and
  this repository works in `.claude/worktrees/`, so a commit there changes
  nothing. Git does not track a hook, so a fresh clone starts without one until
  someone runs `make graph-hooks`. `make graph` stays the reliable rebuild in
  both cases, and `GRAPHIFY_SKIP_HOOK=1` disables every hook for one command.
- **The `post-merge` wrapper drops exactly one guard, and the reason is not
  obvious.** `post-commit` exits when `MERGE_HEAD` is present, which stops it
  from firing inside a merge that a later commit finishes. Git keeps
  `MERGE_HEAD` in place while it runs `post-merge`, so that guard would skip
  every true merge. The wrapper removes those lines and keeps every other guard,
  including the worktree exit. A test proved both halves: a non-fast-forward
  merge rebuilt only after the guard was dropped, and a commit in a linked
  worktree still wrote no graph.
- **The corpus includes the wiki, which makes the two layers navigable
  together.** Wiki pages appear as nodes and cluster with the code they
  describe. This helps a search start from a page and reach a module. It does
  not make the graph authoritative over the page.

## Tensions or open questions

- **The graph indexes no YAML file.** A search of `graph.json` on 2026-08-14
  found zero hits for `infra/config/dev.yaml`, `.github/workflows/ci.yml`, and
  `website/local/compose.yaml`, while `infra/app.py` had 270. The extractor
  reads code and Markdown. Configuration is absent, and a query about a
  service, a schedule, or a container MUST read the file or the wiki instead.
  `GRAPH_REPORT.md` names some JSON files that produce zero nodes; the same
  limit covers YAML without naming it.

- **The upstream project suggests committing `graphify-out/` for teammates.**
  This repository declines that, because size and public-release discipline
  outrank a one-minute rebuild for a single author. Revisit the choice if a
  second contributor joins.
- **Community names come from a heuristic, not from a model.** The repository
  configures no LLM backend, so `graphify label` has never run. The names are
  readable, and no human curated them. Do not quote a community name as a
  project term.
- **The graph is not in CI.** No gate proves that a build still succeeds or
  that the graph matches the tree. A stale or broken graph is a local problem
  today. A CI target is possible later, and it MUST stay non-blocking if it
  arrives, because the tool is a convenience and not a boundary.
- **The repository installs no `PreToolUse` hook.** That agent hook is separate
  from the two git hooks above. It would send a search or a read through the
  graph before the agent reads a file. Without it, every graph query stays
  explicit.
