"""Regression tests for the CDK CloudFormation execution boundary."""

import json

from tests.unit.conftest import REPO_ROOT

POLICY_PATH = REPO_ROOT / "infra" / "policies" / "mlops-cloudformation-execution-policy.json"


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

    Three stacks of deploys produced 105 AccessDenied events in fifteen
    minutes and tripped the 3-of-3 unauthorized-api-calls alarm. The cause is
    that the CloudTrail event name and the IAM action name differ:
    `s3:GetBucket*` never authorized `GetBucketEncryption`, which is
    `s3:GetEncryptionConfiguration`. Pin the read-backs so the burst cannot
    silently return.
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
    """v10 removed them: 3B is deferred to the planned EC2 work, and a standing
    grant for a service that cannot be created is authority for nothing.

    Re-adding them is a deliberate act with a cost: the live default v10 filled
    the last of the five IAM policy version slots, so the next rotation must
    delete an old version first.
    """
    document = json.loads(POLICY_PATH.read_text())

    assert "guardduty" not in json.dumps(document).lower()
    assert not [s for s in document["Statement"] if s["Sid"] == "GuardDutyServiceLinkedRole"]


def test_config_service_linked_role_stays_scoped():
    document = json.loads(POLICY_PATH.read_text())
    # `aws-service-role`, not `aws-service-linked-role`. Phase 3-prep granted
    # the latter and this test pinned it, so the mistake was locked in rather
    # than caught: CreateServiceLinkedRole would have been denied and rolled
    # back the 3C deploy. Corrected in v10.
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
    """Config validates that the caller may pass the role, and the recorder create
    fails with AccessDeniedException without this -- PassOnlyApplicationRoles is
    scoped to Mlops-Dev-* and never covered it."""
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
