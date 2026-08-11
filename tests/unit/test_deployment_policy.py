"""Regression tests for the CDK CloudFormation execution boundary."""

import json

import pytest

from tests.unit.conftest import REPO_ROOT

POLICY_DIR = REPO_ROOT / "infra" / "policies"
POLICY_PATH = POLICY_DIR / "mlops-cloudformation-execution-policy.json"
# The execution boundary uses two managed policies on one CloudFormation role.
# AWS limits each managed policy document to 6144 characters.
EXTENSION_PATH = POLICY_DIR / "mlops-cloudformation-execution-policy-extension.json"
POLICY_SIZE_QUOTA = 6144


def _statement(document, sid):
    return next(statement for statement in document["Statement"] if statement["Sid"] == sid)


def test_phase_2_execution_policy_actions_are_recorded():
    document = json.loads(POLICY_PATH.read_text())
    service_actions = set(_statement(document, "ApplicationServices")["Action"])

    required = {
        "cloudtrail:CreateTrail",
        "cloudtrail:PutEventSelectors",
        "cloudtrail:StartLogging",
        "kms:CreateKey",
        "kms:EnableKeyRotation",
        "kms:PutKeyPolicy",
        "logs:AssociateKmsKey",
        "logs:PutMetricFilter",
        "sns:CreateTopic",
        "sns:Subscribe",
        "sns:SetTopicAttributes",
    }
    assert required <= service_actions


def test_phase_3_execution_policy_actions_are_recorded():
    document = json.loads(POLICY_PATH.read_text())
    service_actions = set(_statement(document, "ApplicationServices")["Action"])

    required = {
        "access-analyzer:CreateAnalyzer",
        "config:PutConfigurationRecorder",
        "config:PutDeliveryChannel",
        "config:StartConfigurationRecorder",
        "securityhub:EnableSecurityHub",
        "securityhub:BatchEnableStandards",
        "s3:PutLifecycleConfiguration",
    }
    assert required <= service_actions


def test_cloudformation_read_backs_are_granted():
    """Grant every CloudFormation read-back action used during deployment."""
    document = json.loads(POLICY_PATH.read_text())
    service_actions = set(_statement(document, "ApplicationServices")["Action"])

    assert {
        "s3:GetEncryptionConfiguration",
        "s3:GetLifecycleConfiguration",
        "s3:GetAccelerateConfiguration",
        "s3:GetAnalyticsConfiguration",
        "s3:GetIntelligentTieringConfiguration",
        "s3:GetInventoryConfiguration",
        "s3:GetMetricsConfiguration",
        "s3:GetReplicationConfiguration",
        "logs:ListTagsForResource",
        "logs:DescribeIndexPolicies",
    } <= service_actions


def test_access_analyzer_service_linked_role_stays_scoped():
    document = json.loads(POLICY_PATH.read_text())
    slr_arn = (
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/"
        "access-analyzer.amazonaws.com/AWSServiceRoleForAccessAnalyzer"
    )

    create = _statement(document, "AccessAnalyzerServiceLinkedRole")
    assert create["Action"] == "iam:CreateServiceLinkedRole"
    assert create["Resource"] == slr_arn
    assert create["Condition"] == {
        "StringEquals": {"iam:AWSServiceName": "access-analyzer.amazonaws.com"}
    }


def test_guardduty_grants_are_absent_until_its_sub_phase_returns():
    """Keep GuardDuty actions out of the current execution policy."""
    document = json.loads(POLICY_PATH.read_text())

    assert "guardduty" not in json.dumps(document).lower()
    assert not [s for s in document["Statement"] if s["Sid"] == "GuardDutyServiceLinkedRole"]


def test_config_service_linked_role_stays_scoped():
    document = json.loads(POLICY_PATH.read_text())
    # Require the valid `aws-service-role` IAM path.
    slr_arn = "arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/config.amazonaws.com/*"

    create = _statement(document, "ConfigServiceLinkedRole")
    assert create["Action"] == "iam:CreateServiceLinkedRole"
    assert create["Resource"] == slr_arn
    assert create["Condition"] == {"StringEquals": {"iam:AWSServiceName": "config.amazonaws.com"}}

    cleanup = _statement(document, "ConfigServiceLinkedRoleCleanup")
    assert set(cleanup["Action"]) == {
        "iam:DeleteServiceLinkedRole",
        "iam:GetServiceLinkedRoleDeletionStatus",
    }
    assert cleanup["Resource"] == slr_arn


def test_pass_role_stays_scoped_to_application_roles_and_services():
    document = json.loads(POLICY_PATH.read_text())
    statement = _statement(document, "PassOnlyApplicationRoles")

    assert statement["Resource"] == "arn:aws:iam::${AWS_ACCOUNT_ID}:role/Mlops-Dev-*"
    assert set(statement["Condition"]["StringEquals"]["iam:PassedToService"]) == {
        "lambda.amazonaws.com",
        "sagemaker.amazonaws.com",
        "events.amazonaws.com",
        "apigateway.amazonaws.com",
        "cloudformation.amazonaws.com",
        "cloudtrail.amazonaws.com",
    }


def test_config_recorder_can_pass_only_its_own_service_linked_role():
    """Limit the Config pass-role grant to its service-linked role."""
    document = json.loads(POLICY_PATH.read_text())
    statement = _statement(document, "PassConfigServiceLinkedRole")

    assert statement["Action"] == "iam:PassRole"
    assert statement["Resource"] == (
        "arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-role/"
        "config.amazonaws.com/AWSServiceRoleForConfig"
    )
    assert statement["Condition"] == {
        "StringEquals": {"iam:PassedToService": "config.amazonaws.com"}
    }


def _rendered_size(path):
    """Return the compact policy size with a documentation account id."""
    document = path.read_text().replace("${AWS_ACCOUNT_ID}", "123456789012")
    return len(json.dumps(json.loads(document), separators=(",", ":")))


@pytest.mark.parametrize("path", [POLICY_PATH, EXTENSION_PATH])
def test_each_policy_document_fits_the_aws_size_quota(path):
    """Reject a policy document above the 6144-byte AWS quota."""
    size = _rendered_size(path)

    assert size <= POLICY_SIZE_QUOTA, (
        f"{path.name} is {size} of {POLICY_SIZE_QUOTA} bytes. Move a statement "
        "to the other document rather than trimming a grant to fit."
    )


def test_no_statement_id_is_reused_across_the_two_documents():
    """Require unique statement ids across both policy documents."""
    main = {statement["Sid"] for statement in json.loads(POLICY_PATH.read_text())["Statement"]}
    extension = {
        statement["Sid"] for statement in json.loads(EXTENSION_PATH.read_text())["Statement"]
    }

    assert main and extension
    assert main.isdisjoint(extension)


def test_the_extension_carries_the_oidc_provider_lifecycle():
    """Grant the OIDC provider lifecycle in the extension policy."""
    statement = _statement(json.loads(EXTENSION_PATH.read_text()), "GitHubOidcProviderLifecycle")

    assert {"iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider"} <= set(
        statement["Action"]
    )
    assert statement["Resource"] == (
        "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    )


def test_the_extension_scopes_archive_rule_lifecycle():
    """CloudFormation manages the rule. The operator changes finding status."""
    document = json.loads(EXTENSION_PATH.read_text())
    lifecycle = _statement(document, "AccessAnalyzerArchiveRuleLifecycle")
    listing = _statement(document, "AccessAnalyzerArchiveRuleList")

    assert set(lifecycle["Action"]) == {
        "access-analyzer:CreateArchiveRule",
        "access-analyzer:DeleteArchiveRule",
        "access-analyzer:GetArchiveRule",
        "access-analyzer:UpdateArchiveRule",
    }
    assert lifecycle["Resource"] == (
        "arn:aws:access-analyzer:us-east-1:${AWS_ACCOUNT_ID}:"
        "analyzer/mlops-*-external-access/archive-rule/ArchiveCiDeployRoleFederation"
    )
    analyzer_prefix = "arn:aws:access-analyzer:us-east-1:${AWS_ACCOUNT_ID}:analyzer/"
    analyzer_arn = f"{analyzer_prefix}mlops-*-external-access"
    assert listing == {
        "Sid": "AccessAnalyzerArchiveRuleList",
        "Effect": "Allow",
        "Action": "access-analyzer:ListArchiveRules",
        "Resource": analyzer_arn,
    }
    assert "access-analyzer:ApplyArchiveRule" not in json.dumps(document)
