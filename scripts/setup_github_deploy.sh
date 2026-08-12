#!/usr/bin/env bash
# One-time GitHub Actions wiring for `.github/workflows/deploy.yml`.
#
# Run once, after the Cicd stack has been deployed for the given ENV. Reads
# the deploy role ARN from the stack output and stores it as the environment
# secret deploy.yml expects. Requires the `gh` CLI, authenticated with a
# token that can manage this repository's environments and secrets.
#
# Usage: ENV=dev ./scripts/setup_github_deploy.sh
set -euo pipefail

ENV_NAME="${ENV:-dev}"
if [[ "${ENV_NAME}" != "dev" && "${ENV_NAME}" != "prod" ]]; then
  echo "ENV must be dev or prod, got '${ENV_NAME}'" >&2
  exit 2
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

stack_prefix="$(uv run --locked --extra dev python -c \
  "from infra.app import stack_prefix; print(stack_prefix('${ENV_NAME}'))")"
stack_name="${stack_prefix}-Cicd"

role_arn="$(aws cloudformation describe-stacks --stack-name "${stack_name}" \
  --query "Stacks[0].Outputs[?OutputKey=='GitHubDeployRoleArn'].OutputValue" \
  --output text)"
if [[ -z "${role_arn}" || "${role_arn}" == "None" ]]; then
  echo "${stack_name}: no GitHubDeployRoleArn output. Deploy the Cicd stack first." >&2
  exit 1
fi

if gh api "repos/{owner}/{repo}/environments/${ENV_NAME}" >/dev/null 2>&1; then
  echo "GitHub environment '${ENV_NAME}' already exists"
else
  gh api --method PUT "repos/{owner}/{repo}/environments/${ENV_NAME}" >/dev/null
  echo "created GitHub environment '${ENV_NAME}'"
fi

secret_name="AWS_$(echo "${ENV_NAME}" | tr '[:lower:]' '[:upper:]')_DEPLOY_ROLE_ARN"
gh secret set "${secret_name}" --env "${ENV_NAME}" --body "${role_arn}"
echo "set ${secret_name} on environment '${ENV_NAME}' to ${role_arn}"

cat <<SUMMARY

Done. deploy.yml can now assume ${role_arn} via OIDC when dispatched for
ENV=${ENV_NAME}. This repo's environments currently allow deployments only
from 'main'; adjust environment protection rules in GitHub if that changes.
SUMMARY
