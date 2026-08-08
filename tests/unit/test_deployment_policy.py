"""Regression tests for the CDK CloudFormation execution boundary."""

import json

import pytest

from tests.unit.conftest import REPO_ROOT

POLICY_DIR = REPO_ROOT / "infra" / "policies"
POLICY_PATH = POLICY_DIR / "mlops-cloudformation-execution-policy.json"
# The execution boundary spans two managed policies. AWS caps one managed
# policy at 6144 characters, and the first reached that ceiling on 2026-08-08.
# Both attach to the same CloudFormation execution role, so the grants union.
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
    """CloudFormation re-reads what it writes, and every denial pages.

    The CloudTrail event name and the IAM action name differ. `s3:GetBucket*`
    does not authorize `GetBucketEncryption`, which is
    `s3:GetEncryptionConfiguration`. A missing read-back produces an
    AccessDenied burst that trips the 3-of-3 unauthorized-api-calls alarm.
    """
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
    """GuardDuty is not enabled, and a standing grant for a service nobody can
    create is authority for nothing.

    Re-adding them costs something. The live default version filled the last of
    the five IAM policy version slots, so the next rotation must delete an old
    version first.
    """
    document = json.loads(POLICY_PATH.read_text())

    assert "guardduty" not in json.dumps(document).lower()
    assert not [s for s in document["Statement"] if s["Sid"] == "GuardDutyServiceLinkedRole"]


def test_config_service_linked_role_stays_scoped():
    document = json.loads(POLICY_PATH.read_text())
    # Use `aws-service-role`, not `aws-service-linked-role`.
    # CreateServiceLinkedRole is denied on the second path and rolls the deploy
    # back.
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
    """Config validates that the caller may pass the role. An ungranted
    recorder create fails with AccessDeniedException. PassOnlyApplicationRoles
    is scoped to Mlops-Dev-* and never covered it."""
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
    """Return the size IAM measures: compact JSON with the account filled in.

    IAM ignores whitespace, so an indented file is not what counts. The
    placeholder is longer than a real account id, so substituting it keeps the
    measurement honest rather than pessimistic.
    """
    document = path.read_text().replace("${AWS_ACCOUNT_ID}", "123456789012")
    return len(json.dumps(json.loads(document), separators=(",", ":")))


@pytest.mark.parametrize("path", [POLICY_PATH, EXTENSION_PATH])
def test_each_policy_document_fits_the_aws_size_quota(path):
    """A rotation that exceeds 6144 fails with LimitExceeded, and the failure
    arrives at the AWS API rather than in CI. Measure it here instead."""
    size = _rendered_size(path)

    assert size <= POLICY_SIZE_QUOTA, (
        f"{path.name} is {size} of {POLICY_SIZE_QUOTA} bytes. Move a statement "
        "to the other document rather than trimming a grant to fit."
    )


def test_no_statement_id_is_reused_across_the_two_documents():
    """Two documents, one boundary. A duplicated Sid makes it ambiguous which
    file owns a grant, and a reader can then edit the wrong one."""
    main = {statement["Sid"] for statement in json.loads(POLICY_PATH.read_text())["Statement"]}
    extension = {
        statement["Sid"] for statement in json.loads(EXTENSION_PATH.read_text())["Statement"]
    }

    assert main and extension
    assert main.isdisjoint(extension)


def test_the_extension_carries_the_oidc_provider_lifecycle():
    """CicdStack creates an AWS::IAM::OIDCProvider. Without these actions the
    stack fails at create, and the grants do not fit in the main document."""
    statement = _statement(json.loads(EXTENSION_PATH.read_text()), "GitHubOidcProviderLifecycle")

    assert {"iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider"} <= set(
        statement["Action"]
    )
    assert statement["Resource"] == (
        "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    )
