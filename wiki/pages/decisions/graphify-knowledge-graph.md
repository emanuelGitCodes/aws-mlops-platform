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

- **graphify is installed and the first graph is built.** The `graphifyy`
  package (version 0.9.42) is installed as a `uv` tool, so it stays out of
  `uv.lock` and out of the project environment. The skill bundle is installed
  project-scoped at `.claude/skills/graphify/`, as `SKILL.md` plus a
  `references/` directory.
- **The first build covers the code and the wiki together.** The build of
  2026-08-14, from commit `90dc79d`, read 176 files and about 368,850 words.
  It produced 2141 nodes, 2953 edges, and 209 communities. The extraction
  reports 100% EXTRACTED edges and 12 INFERRED edges, at an average confidence
  of 0.53. It cost 0 input and 0 output tokens.
- **The extraction is local and deterministic.** `graphify update .` parses
  each file with tree-sitter. It calls no model and no network service. An
  LLM backend is optional, and this repository does not configure one.
- **Three files come out of a build.** `graphify-out/` holds `graph.json`
  (the queryable graph), `graph.html` (an interactive view), and
  `GRAPH_REPORT.md` (communities, hubs, and suggested questions). A
  `cache/` directory and a `manifest.json` hold the per-file extraction state.
- **`graphify-out/` is untracked.** `.gitignore` excludes it, for the same
  reason `infra/cdk.out/` is excluded: it is build output that any clone can
  regenerate in about one minute. The 2 MB `graph.json` and the 1.8 MB
  `graph.html` therefore never enter the history of a repository that is
  being prepared for public release.
- **`.graphifyignore` narrows the corpus.** It excludes `graphify-out/`,
  `infra/cdk.out/`, the third-party `wiki/assets/architecture/cdk-dia-icons/`
  icon set, and `uv.lock`. graphify merges this file with `.gitignore`, and
  the patterns here win on a conflict. `.env` and `telco/` are already
  excluded through `.gitignore`.
- **Three Make targets front the tool.** `make graph` rebuilds the graph,
  `make graph-query Q=…` runs a traversal for a question, and
  `make graph-explain NODE=…` describes one node and its neighbours.

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
- **A generated file MUST NOT be cited as wiki evidence.** `graphify-out/` is
  disposable and untracked, so a `sources:` entry that points into it cannot
  resolve for the next reader. Cite the repository path that the graph led you
  to instead.
- **The graph goes stale without warning.** `GRAPH_REPORT.md` names the commit
  it was built from. A query against an old graph answers about old code and
  looks correct. Run `make graph` after a change, and read that line before
  you trust an answer.
- **The corpus includes the wiki, which makes the two layers navigable
  together.** Wiki pages appear as nodes and cluster with the code they
  describe. This helps a search start from a page and reach a module. It does
  not make the graph authoritative over the page.

## Tensions or open questions

- **The upstream project suggests committing `graphify-out/` for teammates.**
  This repository declines that, because size and public-release discipline
  outrank a one-minute rebuild for a single author. Revisit the choice if a
  second contributor joins.
- **Community names come from a heuristic, not from a model.** No LLM backend
  is configured, so `graphify label` has never run. The names are readable but
  they are not curated. Do not quote a community name as a project term.
- **The graph is not in CI.** No gate proves that a build still succeeds or
  that the graph matches the tree. A stale or broken graph is a local problem
  today. A CI target is possible later, and it MUST stay non-blocking if it
  arrives, because the tool is a convenience and not a boundary.
- **The `PreToolUse` hooks are not installed.** graphify can register hooks
  that route a search or a read through the graph first. This repository does
  not install them, so every graph query stays explicit.
