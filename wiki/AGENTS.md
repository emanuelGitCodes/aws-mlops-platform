# LLM Wiki agent instructions

When working inside `wiki/`, read and follow [SCHEMA.md](SCHEMA.md). The wiki is a persistent knowledge artifact: preserve raw sources, update related pages, keep links and metadata valid, and record meaningful operations in [log.md](log.md).

Use `python scripts/wiki.py search "your terms"` before opening many pages and run `python scripts/wiki.py lint` before handing work back.

## Sensitive values

The wiki must never contain account-identifying literals — in any file,
including immutable `raw/` records. This applies to:

- AWS account IDs and any ARN or URL embedding one;
- IAM user and profile names;
- API Gateway REST API ids (`<id>.execute-api.…` hosts);
- physical resource names containing generated suffixes, such as S3 bucket
  names and budget names.

Write the matching `.env.example` placeholder instead: `${AWS_ACCOUNT_ID}`,
`${MLOPS_DEPLOYER_USER_NAME}`, `${AWS_ADMIN_USER_NAME}`, `${API_GATEWAY_ID}`,
`${ACCESS_LOG_BUCKET}`, `${MONTHLY_BUDGET_NAME}`, `${RAW_BUCKET}`,
`${CURATED_BUCKET}`, `${ARTIFACTS_BUCKET}`, and so on. When pasting CLI or
console output into a record, substitute the literals **before** saving the
file. If a value has no placeholder yet, add one to `.env.example` first;
real values live only in the local gitignored `.env`.

Additional rules:

- Never record credentials, API keys, tokens, or secrets in any form (this
  extends the SCHEMA.md log rule).
- Do not record checksums or hashes computed over a document that contains a
  sensitive literal: publishing the hash next to the placeholder version of
  the document lets the literal be recovered by brute force. Write
  `<redacted>` or omit the hash.
- Before handing work back, search your changed files for leak patterns —
  12-digit numbers, `execute-api` hosts, ARNs with a numeric account field —
  in addition to running the linter.
