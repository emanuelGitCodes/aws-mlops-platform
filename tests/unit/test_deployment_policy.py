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
        "guardduty:CreateDetector",
        "guardduty:UpdateDetector",
        "config:PutConfigurationRecorder",
        "config:PutDeliveryChannel",
        "config:StartConfigurationRecorder",
        "securityhub:EnableSecurityHub",
        "securityhub:BatchEnableStandards",
        "s3:PutLifecycleConfiguration",
    }
    assert required <= service_actions


def test_config_service_linked_role_stays_scoped():
    document = json.loads(POLICY_PATH.read_text())
    slr_arn = "arn:aws:iam::${AWS_ACCOUNT_ID}:role/aws-service-linked-role/config.amazonaws.com/*"

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
