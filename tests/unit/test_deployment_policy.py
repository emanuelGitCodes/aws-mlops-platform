"""Regression tests for the CDK deployment boundaries."""

import hashlib
import json
from fnmatch import fnmatchcase

import aws_cdk as cdk
import pytest
from aws_cdk import aws_sqs as sqs
from aws_cdk.assertions import Template

from infra.security_checks import apply_security_checks
from tests.unit.conftest import REPO_ROOT, synth_env

POLICY_DIR = REPO_ROOT / "infra" / "policies"
POLICY_PATH = POLICY_DIR / "mlops-cloudformation-execution-policy.json"
EXTENSION_PATH = POLICY_DIR / "mlops-cloudformation-execution-policy-extension.json"
DEPLOYMENT_PATH = POLICY_DIR / "mlops-cdk-deployment-policy.json"
POLICY_PATHS = (POLICY_PATH, EXTENSION_PATH, DEPLOYMENT_PATH)
# AWS limits each managed policy document to 6144 characters.
POLICY_SIZE_QUOTA = 6144
POLICY_SHA256 = {
    "mlops-cloudformation-execution-policy.json": (
        "f559c575d8d6826e6613969368501c8af5d157f55240d91ed7f976a32fd2fd9a"
    ),
    "mlops-cloudformation-execution-policy-extension.json": (
        "f5981c6317618679383440b7458141457b73949d7236512f105e94b63d9d5042"
    ),
    "mlops-cdk-deployment-policy.json": (
        "b564f53035616e1ed8a680857f4467cb8787cf7f97637c91616e8733ebeb6b39"
    ),
}
WILDCARD_ACTION_ALLOWLIST: set[str] = set()


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


def test_application_role_lifecycle_stays_scoped_to_mlops_roles():
    document = json.loads(POLICY_PATH.read_text())
    statement = _statement(document, "ApplicationRoleLifecycle")

    assert statement["Resource"] == "arn:aws:iam::${AWS_ACCOUNT_ID}:role/Mlops-*"
    assert statement["Resource"] != "*"


def test_website_ec2_grants_cover_the_stack_resources():
    """Grant the network and instance actions the website stack creates."""
    document = json.loads(EXTENSION_PATH.read_text())
    network = set(_statement(document, "WebsiteEc2Network")["Action"])
    instances = set(_statement(document, "WebsiteEc2Instances")["Action"])

    assert {
        "ec2:CreateVpc",
        "ec2:CreateSubnet",
        "ec2:CreateInternetGateway",
        "ec2:CreateRouteTable",
        "ec2:CreateSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateFlowLogs",
        "ec2:AllocateAddress",
        "ec2:AssociateAddress",
    } <= network
    assert {"ec2:RunInstances", "ec2:TerminateInstances", "ec2:Describe*"} <= instances


def test_website_data_grants_stay_scoped():
    """Scope the CloudFront and DynamoDB grants to the website resources."""
    document = json.loads(EXTENSION_PATH.read_text())

    distribution = _statement(document, "WebsiteCloudFront")
    assert distribution["Resource"] == "arn:aws:cloudfront::${AWS_ACCOUNT_ID}:distribution/*"
    assert "cloudfront:CreateDistribution" in distribution["Action"]

    table = _statement(document, "WebsiteDynamoDb")
    assert table["Resource"] == (
        "arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/mlops-*-website-mailing-list"
    )
    # The boundary creates the table. It never reads a stored address.
    assert not [action for action in table["Action"] if action.endswith(("GetItem", "Scan"))]


def test_website_pass_role_is_separate_and_scoped():
    """Keep the website pass-role grant out of the full main document."""
    main = json.loads(POLICY_PATH.read_text())
    document = json.loads(EXTENSION_PATH.read_text())

    # `PassOnlyApplicationRoles` stays unchanged; the main document is full.
    assert "ec2.amazonaws.com" not in json.dumps(
        _statement(main, "PassOnlyApplicationRoles")["Condition"]
    )

    statement = _statement(document, "PassWebsiteInstanceRole")
    assert statement["Action"] == "iam:PassRole"
    assert statement["Resource"] == "arn:aws:iam::${AWS_ACCOUNT_ID}:role/Mlops-*-Website-*"
    assert set(statement["Condition"]["StringEquals"]["iam:PassedToService"]) == {
        "ec2.amazonaws.com",
        "vpc-flow-logs.amazonaws.com",
    }

    profile = _statement(document, "WebsiteInstanceProfileLifecycle")
    assert profile["Resource"] == (
        "arn:aws:iam::${AWS_ACCOUNT_ID}:instance-profile/Mlops-*-Website-*"
    )


def test_website_ami_parameter_read_is_scoped_to_the_public_ami_path():
    """Read only the public Amazon Linux AMI parameters."""
    document = json.loads(EXTENSION_PATH.read_text())
    statement = _statement(document, "WebsiteAmiParameterRead")

    assert statement["Resource"] == (
        "arn:aws:ssm:us-east-1::parameter/aws/service/ami-amazon-linux-latest/*"
    )
    assert set(statement["Action"]) == {"ssm:GetParameter", "ssm:GetParameters"}


def test_audit_bucket_objects_are_protected_from_deletion():
    document = json.loads(EXTENSION_PATH.read_text())
    statement = _statement(document, "ProtectAuditBucketObjects")

    assert statement["Effect"] == "Deny"
    assert set(statement["Action"]) == {
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
    }
    assert statement["Resource"] == "arn:aws:s3:::mlops-*-security-auditbucketb01e0ae8-*/*"
    assert "s3:PutBucketPolicy" not in statement["Action"]
    assert "cloudtrail:DeleteTrail" not in statement["Action"]


def test_audit_trail_cannot_be_stopped_by_the_deploy_boundary():
    document = json.loads(EXTENSION_PATH.read_text())
    statement = _statement(document, "ProtectAuditTrail")

    assert statement["Effect"] == "Deny"
    assert statement["Action"] == "cloudtrail:StopLogging"
    assert statement["Resource"] == (
        "arn:aws:cloudtrail:us-east-1:${AWS_ACCOUNT_ID}:trail/mlops-*-audit"
    )
    assert "s3:PutBucketPolicy" not in statement["Action"]
    assert "cloudtrail:DeleteTrail" not in statement["Action"]


def test_audit_deny_patterns_match_synthesized_security_resources():
    document = json.loads(EXTENSION_PATH.read_text())
    bucket_statement = _statement(document, "ProtectAuditBucketObjects")
    trail_statement = _statement(document, "ProtectAuditTrail")
    security_stack = synth_env("dev", "Mlops-Dev")["security"]
    resources = Template.from_stack(security_stack).to_json()["Resources"]
    stack_name = security_stack.stack_name.lower()

    audit_logical_id = "AuditBucketB01E0AE8"
    access_logical_id = "AccessLogBucketDA470295"
    audit_bucket = resources[audit_logical_id]
    access_log_bucket = resources[access_logical_id]
    trail_type = "AWS::CloudTrail::Trail"
    trail = next(
        filter(
            lambda resource: resource["Type"] == trail_type,
            resources.values(),
        )
    )
    assert audit_bucket["Type"] == "AWS::S3::Bucket"
    assert access_log_bucket["Type"] == "AWS::S3::Bucket"
    assert "BucketName" not in audit_bucket["Properties"]
    assert "BucketName" not in access_log_bucket["Properties"]

    trail_name = trail["Properties"]["TrailName"]
    assert trail_name == "mlops-dev-audit"
    audit_bucket_name = f"{stack_name}-{audit_logical_id.lower()}-random"
    access_log_bucket_name = f"{stack_name}-{access_logical_id.lower()}-random"
    bucket_pattern = bucket_statement["Resource"].removeprefix("arn:aws:s3:::")
    bucket_pattern = bucket_pattern.removesuffix("/*")
    trail_pattern = trail_statement["Resource"].rsplit("/", maxsplit=1)[-1]

    assert fnmatchcase(audit_bucket_name, bucket_pattern)
    assert not fnmatchcase(access_log_bucket_name, bucket_pattern)
    assert fnmatchcase(trail_name, trail_pattern)


def _rendered_size(path):
    """Return the compact policy size with a documentation account id."""
    document = path.read_text()
    document = document.replace("${AWS_ACCOUNT_ID}", "123456789012")
    document = document.replace("${AWS_REGION}", "us-east-1")
    return len(json.dumps(json.loads(document), separators=(",", ":")))


@pytest.mark.parametrize("path", POLICY_PATHS)
def test_each_policy_document_fits_the_aws_size_quota(path):
    """Reject a policy document above the 6144-byte AWS quota."""
    size = _rendered_size(path)

    assert size <= POLICY_SIZE_QUOTA, (
        f"{path.name} is {size} of {POLICY_SIZE_QUOTA} bytes. Move a statement "
        "to the other document rather than trimming a grant to fit."
    )


@pytest.mark.parametrize("path", POLICY_PATHS)
def test_policy_fingerprint_is_pinned(path):
    """Require an explicit review when a policy document changes."""
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()

    assert fingerprint == POLICY_SHA256[path.name]


@pytest.mark.parametrize("path", POLICY_PATHS)
def test_broad_action_wildcards_are_allowlisted(path):
    """Reject broad action wildcards outside the named allowlist."""
    document = json.loads(path.read_text())
    wildcard_actions = set()
    for statement in document["Statement"]:
        actions = statement["Action"]
        if isinstance(actions, str):
            actions = [actions]
        wildcard_actions.update(action for action in actions if action.endswith(":*"))

    assert wildcard_actions <= WILDCARD_ACTION_ALLOWLIST


def test_no_statement_id_is_reused_across_policy_documents():
    """Require unique statement ids across all policy documents."""
    statement_ids = [
        statement["Sid"]
        for path in POLICY_PATHS
        for statement in json.loads(path.read_text())["Statement"]
    ]

    assert statement_ids
    assert len(statement_ids) == len(set(statement_ids))


def test_cdk_nag_gate_rejects_non_compliant_construct(monkeypatch):
    """Require synthesis to reject a queue without the cdk-nag controls."""
    app = cdk.App()
    stack = cdk.Stack(app, "NonCompliantStack")
    sqs.Queue(stack, "NonCompliantQueue")
    monkeypatch.setattr(
        "infra.security_checks.resolved_acknowledgements",
        lambda *_args: (),
    )
    config = {
        "security": {"services": {}, "account_budget": False},
        "website": {"enabled": False},
    }
    apply_security_checks(app, {}, config, "Test")

    with pytest.raises(Exception) as error:
        app.synth()

    assert "AwsSolutions-SQS3" in str(error.value)
    assert "AwsSolutions-SQS4" in str(error.value)


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
