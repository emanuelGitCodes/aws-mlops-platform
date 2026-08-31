---
name: wiki-record
description: "Rules for writing anything under wiki/ — the repository's source of record. Read it before creating or editing a wiki page, ingesting a raw source, or writing a wiki/log.md entry, and whenever a phase or observation window lands. Holds the sensitive-literal ban, the style exceptions, and the lint gate."
---

# Writing the wiki record

`wiki/AGENTS.md` and `wiki/SCHEMA.md` govern this directory. Read both. This
skill states what an agent gets wrong without them.

## The record ships with the work

The wiki is the source of record. It holds history, decisions, phase status,
dates, and the reasoning behind them. When a phase, a deploy, or an
observation window lands, write the `wiki/log.md` entry and the page updates
in the same change set. Do not wait to be asked.

Keep dates absolute. Write `2026-08-14`, never "today" or "last week".

## Search before you open pages

```bash
make wiki-search Q='alert topic split'
```

Read the hits before opening files by hand. Run the linter before you hand
work back:

```bash
make wiki-lint
```

CI runs `wiki-lint` on every PR, so a lint failure blocks the merge.

## Two style exceptions

The `house-style` skill governs the prose you write here, with two changes:

1. **Preserved source text keeps its own words.** Quoted material, console
   output, error text, and any content you ingest are data. Reproduce them
   exactly. The style rules apply to the prose you write around them.
2. **History and status belong here.** The root `AGENTS.md` forbids history,
   dates, and phase status *in code comments*, because this wiki holds them.
   Write them on the page.

## Sensitive values

The wiki MUST NOT hold an account-identifying literal, in any file. This rule
also covers the immutable `raw/` records. It applies to:

- AWS account IDs and any ARN or URL embedding one;
- IAM user and profile names;
- API Gateway REST API ids (`<id>.execute-api.…` hosts);
- physical resource names containing generated suffixes, such as S3 bucket
  names and budget names.

Write the matching `.env.example` placeholder instead: `${AWS_ACCOUNT_ID}`,
`${MLOPS_DEPLOYER_USER_NAME}`, `${AWS_ADMIN_USER_NAME}`, `${API_GATEWAY_ID}`,
and so on. Substitute the literals **before** you save a file that holds CLI
or console output. If a value has no placeholder yet, add one to
`.env.example` first. Real values live only in the local gitignored `.env`.

Additional rules:

- Never record credentials, API keys, tokens, or secrets in any form.
- Do not record a checksum computed over a document that contains a sensitive
  literal. Publishing the hash next to the placeholder version lets an
  attacker recover the literal by brute force. Write `<redacted>`, or omit
  the hash.
- Before handing work back, search your changed files for leak patterns —
  12-digit numbers, `execute-api` hosts, ARNs with a numeric account field.
  `make public-check` is the standing gate, and it runs in CI.
