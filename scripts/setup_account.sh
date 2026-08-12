#!/usr/bin/env bash
# One-time AWS account setup, run once per fresh account before `make bootstrap`.
#
# Run this with an admin-capable identity (for example the account root user,
# or an existing administrator). It creates the narrow deployment boundary
# that `make bootstrap` and `make deploy` then use, so the CDK CloudFormation
# execution role never needs AdministratorAccess. See
# wiki/pages/architecture/cdk-deployment-iam.md for the identities this
# script creates.
#
# Idempotent: safe to re-run. Existing IAM objects are left as-is.
#
# The MLOpsCdkDeploymentPolicy document below reproduces the live policy in
# the reference account. Keep the two in step. The SSM grant names the single
# CDK bootstrap version parameter; a wildcard resource here would widen the
# control-plane identity beyond what it needs.
#
# Requires: aws CLI configured with an admin-capable profile, envsubst,
# and a populated .env (AWS_ACCOUNT_ID, AWS_REGION, MLOPS_DEPLOYER_USER_NAME).
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID in .env first}"
: "${AWS_REGION:?Set AWS_REGION in .env first}"
: "${MLOPS_DEPLOYER_USER_NAME:?Set MLOPS_DEPLOYER_USER_NAME in .env first}"
: "${AWS_PROFILE:?Set AWS_PROFILE to an admin-capable profile before running this script}"

POLICY_DIR="infra/policies"
EXEC_POLICY_NAME="MLOpsCloudFormationExecutionPolicy"
EXEC_EXTENSION_POLICY_NAME="MLOpsCloudFormationExecutionPolicyExtension"
DEPLOY_POLICY_NAME="MLOpsCdkDeploymentPolicy"
DEPLOY_GROUP_NAME="MLOps-Deployers"

exec_policy_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${EXEC_POLICY_NAME}"
exec_extension_policy_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${EXEC_EXTENSION_POLICY_NAME}"
deploy_policy_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${DEPLOY_POLICY_NAME}"

create_or_skip_policy() {
  local policy_name="$1" policy_arn="$2" document_path="$3"
  if aws iam get-policy --policy-arn "${policy_arn}" >/dev/null 2>&1; then
    echo "policy ${policy_name} already exists, skipping create"
    return
  fi
  aws iam create-policy \
    --policy-name "${policy_name}" \
    --policy-document "file://${document_path}" >/dev/null
  echo "created policy ${policy_name}"
}

echo "== CloudFormation execution policy (application boundary) =="
tmp_exec_policy="$(mktemp)"
envsubst <"${POLICY_DIR}/mlops-cloudformation-execution-policy.json" >"${tmp_exec_policy}"
create_or_skip_policy "${EXEC_POLICY_NAME}" "${exec_policy_arn}" "${tmp_exec_policy}"
rm -f "${tmp_exec_policy}"

tmp_exec_extension_policy="$(mktemp)"
envsubst <"${POLICY_DIR}/mlops-cloudformation-execution-policy-extension.json" \
  >"${tmp_exec_extension_policy}"
create_or_skip_policy "${EXEC_EXTENSION_POLICY_NAME}" "${exec_extension_policy_arn}" \
  "${tmp_exec_extension_policy}"
rm -f "${tmp_exec_extension_policy}"

echo "== CDK deployment policy (control-plane boundary) =="
# Lets a human or CI identity assume the CDK bootstrap roles without any
# direct S3/Lambda/SageMaker/CloudFormation permission of its own.
tmp_deploy_policy="$(mktemp)"
cat >"${tmp_deploy_policy}" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IdentifyAccount",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Sid": "AssumeCdkRoles",
      "Effect": "Allow",
      "Action": ["sts:AssumeRole", "sts:TagSession"],
      "Resource": [
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/cdk-hnb659fds-deploy-role-${AWS_ACCOUNT_ID}-${AWS_REGION}",
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/cdk-hnb659fds-file-publishing-role-${AWS_ACCOUNT_ID}-${AWS_REGION}",
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/cdk-hnb659fds-lookup-role-${AWS_ACCOUNT_ID}-${AWS_REGION}"
      ]
    },
    {
      "Sid": "ReadCdkBootstrapVersion",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters"],
      "Resource": "arn:aws:ssm:${AWS_REGION}:${AWS_ACCOUNT_ID}:parameter/cdk-bootstrap/hnb659fds/version"
    }
  ]
}
JSON
create_or_skip_policy "${DEPLOY_POLICY_NAME}" "${deploy_policy_arn}" "${tmp_deploy_policy}"
rm -f "${tmp_deploy_policy}"

if aws iam get-group --group-name "${DEPLOY_GROUP_NAME}" >/dev/null 2>&1; then
  echo "group ${DEPLOY_GROUP_NAME} already exists, skipping create"
else
  aws iam create-group --group-name "${DEPLOY_GROUP_NAME}" >/dev/null
  echo "created group ${DEPLOY_GROUP_NAME}"
fi
aws iam attach-group-policy --group-name "${DEPLOY_GROUP_NAME}" \
  --policy-arn "${deploy_policy_arn}"

echo "== Deployment user =="
if aws iam get-user --user-name "${MLOPS_DEPLOYER_USER_NAME}" >/dev/null 2>&1; then
  echo "user ${MLOPS_DEPLOYER_USER_NAME} already exists, skipping create"
else
  aws iam create-user --user-name "${MLOPS_DEPLOYER_USER_NAME}" >/dev/null
  echo "created user ${MLOPS_DEPLOYER_USER_NAME}"
fi
aws iam add-user-to-group --user-name "${MLOPS_DEPLOYER_USER_NAME}" \
  --group-name "${DEPLOY_GROUP_NAME}"

existing_keys="$(aws iam list-access-keys --user-name "${MLOPS_DEPLOYER_USER_NAME}" \
  --query 'AccessKeyMetadata[].AccessKeyId' --output text)"
if [[ -n "${existing_keys}" ]]; then
  echo "user ${MLOPS_DEPLOYER_USER_NAME} already has an access key, skipping key create"
else
  echo "creating an access key for ${MLOPS_DEPLOYER_USER_NAME} (printed once, store it now):"
  aws iam create-access-key --user-name "${MLOPS_DEPLOYER_USER_NAME}"
fi

cat <<SUMMARY

Done. Next steps:
1. Configure an AWS CLI profile for ${MLOPS_DEPLOYER_USER_NAME} with the
   access key printed above, if one was created.
2. Run: make bootstrap ENV=dev
   (this now targets the ${EXEC_POLICY_NAME} boundary this script created)
SUMMARY
