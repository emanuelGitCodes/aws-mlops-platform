# LLM Wiki

This is the repository's persistent, markdown-first knowledge base. It turns the code and design documents into an interlinked synthesis that can compound across study sessions.

Start with [index.md](index.md), then read [SCHEMA.md](SCHEMA.md) for the maintenance contract.

## Quick start

```bash
make wiki-init
make wiki-search Q="SageMaker permissions"
make wiki-lint

# Register a new article, paper, note, or transcript.
make wiki-ingest SOURCE=/path/to/source.md TITLE="Source title"
```

The CLI is intentionally local and deterministic. It does not call an LLM: it preserves sources and handles bookkeeping while the agent reads, synthesizes, cross-references, and edits the maintained pages.
