# LLM Wiki schema and operating contract

This directory is a local, Git-backed knowledge base for understanding and evolving the AWS MLOps platform. The LLM maintains the wiki; the human curates sources, directs emphasis, and reviews changes.

## Layers

- `raw/` contains immutable source material. Never edit or silently replace a file there. If a source changes, add a new dated/versioned source and explain the relationship.
- `pages/` holds the maintained synthesis. Each page is Markdown with frontmatter. A page SHOULD link to its evidence and to the related wiki pages; omit a link only when no page or source applies.
- `index.md` is the content-oriented catalog. Rebuild it with `python scripts/wiki.py index` after page changes.
- `log.md` is append-only and chronological. Use consistent headings such as `## [2026-07-10] ingest | Source title`.

## Log detail standard

A log entry for implementation work or infrastructure work MUST carry enough context for the next session. The next reader reproduces the reasoning from the entry alone:

- **Objective:** the change or the verification you set out to make.
- **Scope:** pages, code paths, stacks, or AWS resources involved.
- **Identity and environment:** AWS profile, account or region when relevant; never record credentials or secrets.
- **Commands and results:** the important commands, whether they were read-only or mutating, and the meaningful output or error.
- **Interpretation:** why you expected the result, why it surprised you, or why it is a security boundary.
- **Decision and next checkpoint:** what you deliberately left unchanged, and what happens next.
- **Verification:** lint, tests, or other checks and their result.

## Page contract

Every maintained page under `pages/` starts with frontmatter containing:

```yaml
---
type: concept | architecture | decision | source | answer | overview
title: Human-readable title
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [relative/path/to/evidence]
summary: One-line index summary
---
```

Use the body to distinguish evidence from interpretation:

- `## Confirmed` for claims directly supported by a source.
- `## Synthesis` for connections or explanations derived across sources.
- `## Tensions or open questions` for contradictions, missing evidence, or claims that need investigation.

Link page to page often. Do not add a link for decoration. A source citation MUST resolve to a file, a repository path, or a stable external URL.

## Workflows

### Ingest

1. Register one source with `python scripts/wiki.py add-source path/to/source --title "..."`. This copies the source once into `raw/` and scaffolds a source page.
2. Read the raw source and discuss the takeaways before treating them as settled knowledge.
3. Complete the source page, then update every affected concept, architecture, decision, and answer page. Record contradictions instead of overwriting an older claim without explanation.
4. Add new pages when a recurring entity or concept deserves a stable home.
5. Rebuild the index, append an ingest entry to the log, and run the linter.

### Query

1. Read `index.md`, search the wiki, and follow the most relevant pages.
2. Answer with citations to wiki pages and, where useful, the underlying raw or repository source.
3. If the answer contains durable synthesis, file it under `pages/answers/` with the same frontmatter contract and links to the concepts it updates.
4. Record a short query entry in `log.md` when the exploration changes or adds knowledge.

### Lint

Run `python scripts/wiki.py lint` periodically. Treat broken links, missing evidence, stale index entries, invalid frontmatter, and orphan pages as maintenance work. Look manually for stale claims, contradictions, concepts mentioned repeatedly without their own page, and evidence gaps that merit a new source.

## Boundaries

The wiki does not replace the repository's code, tests, or AWS documentation. It is a navigable synthesis layer. A wiki page is never more authoritative than the source it cites. Wiki maintenance MUST NOT change application code.
