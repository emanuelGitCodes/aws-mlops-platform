# Security policy

## Supported version

Security fixes target the current `main` branch. Older commits and deployed
environments are not supported releases.

## Report a vulnerability

Use the repository's **Report a vulnerability** link under **Security**.
GitHub sends that report privately to the maintainer.

Do not include vulnerability details, credentials, account identifiers, or
customer data in a public issue. If private reporting is unavailable, open an
issue that asks the maintainer to enable a private channel. Include no security
details in that issue.

## Secrets and account metadata

Never commit credentials, tokens, private keys, AWS account IDs, account-bearing
ARNs, API Gateway hosts, generated bucket names, or IAM identity names. Use the
placeholders from `.env.example`. Run `make public-check` and the full-history
Gitleaks job before a release.
