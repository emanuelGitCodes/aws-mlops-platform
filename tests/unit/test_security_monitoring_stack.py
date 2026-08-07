"""SecurityMonitoring stack: the flag-gated Phase 3 services."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.app import build_app, load_config
from infra.stacks.security_monitoring_stack import (
    CONFIG_RECORDED_TYPES,
    IMPLEMENTED_SERVICE_FLAGS,
    PHASE_3_SERVICE_FLAGS,
    SecurityMonitoringStack,
)
from infra.stacks.shared import CONFIG_DELIVERY_PREFIX
from tests.unit.conftest import CONFIG


def test_security_monitoring_enables_only_phase_3a_3c_and_3e(stacks):
    """Dev enables the analyzer, Config, and account BPA. Phase 3B GuardDuty
    is deferred."""
    services = CONFIG["security"]["services"]
    assert services["access_analyzer"] is True
    assert services["account_bpa"] is True
    assert services["config_recorder"] is True
    assert services["guardduty"] is False
    assert {name for name, enabled in services.items() if enabled} == {
        "access_analyzer",
        "account_bpa",
        "config_recorder",
    }

    template = stacks["security_monitoring"]
    template.resource_count_is("AWS::AccessAnalyzer::Analyzer", 1)
    template.has_resource_properties(
        "AWS::AccessAnalyzer::Analyzer",
        {
            "AnalyzerName": "mlops-dev-external-access",
            "Type": "ACCOUNT",
        },
    )
    analyzer_properties = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::AccessAnalyzer::Analyzer"
    )
    assert set(analyzer_properties) == {"AnalyzerName", "Tags", "Type"}
    assert {tag["Key"]: tag["Value"] for tag in analyzer_properties["Tags"]} == {
        "Project": "aws-mlops-platform",
        "Environment": "dev",
        "SecurityPhase": "3A",
    }

    guardduty_types = {
        resource["Type"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"].startswith("AWS::GuardDuty::")
    }
    assert guardduty_types == set()


def test_guardduty_detector_contract_stays_locked_for_deferred_phase_3b():
    """The flag-gated detector keeps its Phase 3B shape for the later retry."""
    config = load_config("dev")
    config["security"]["services"]["guardduty"] = True
    # Isolate the detector. Phase 3C would dereference the stub audit bucket
    # below.
    config["security"]["services"]["config_recorder"] = False

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stack = SecurityMonitoringStack(
        app,
        "Test-SecurityMonitoring-GuardDutyRetry",
        alert_topic=None,
        access_log_bucket=None,
        audit_bucket=None,
        audit_key=None,
        config=config,
    )
    app.synth()
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::GuardDuty::Detector", 1)
    detector_properties = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::GuardDuty::Detector"
    )
    assert set(detector_properties) == {
        "Enable",
        "Features",
        "FindingPublishingFrequency",
        "Tags",
    }
    assert detector_properties["Enable"] is True
    assert detector_properties["FindingPublishingFrequency"] == "FIFTEEN_MINUTES"
    assert detector_properties["Features"] == [
        {"Name": name, "Status": "DISABLED"}
        for name in (
            "S3_DATA_EVENTS",
            "EKS_AUDIT_LOGS",
            "EBS_MALWARE_PROTECTION",
            "RDS_LOGIN_EVENTS",
            "LAMBDA_NETWORK_LOGS",
            "AI_ANALYST",
        )
    ]
    assert {tag["Key"]: tag["Value"] for tag in detector_properties["Tags"]} == {
        "Project": "aws-mlops-platform",
        "Environment": "dev",
        "SecurityPhase": "3B",
    }

    guardduty_types = {
        resource["Type"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"].startswith("AWS::GuardDuty::")
    }
    assert guardduty_types == {"AWS::GuardDuty::Detector"}


def _account_bpa_call(template, key):
    """Rebuild one SDK call from the custom resource. Resolve the account
    Ref."""
    resource = next(
        value
        for value in template.to_json()["Resources"].values()
        if value["Type"] == "Custom::AWS"
    )
    parts = resource["Properties"][key]["Fn::Join"][1]
    for part in parts:
        # The account pseudo-parameter must be the only intrinsic in the
        # payload. A literal account id must never reach the template.
        assert isinstance(part, str) or part == {"Ref": "AWS::AccountId"}
    rendered = "".join(part if isinstance(part, str) else "<ACCOUNT>" for part in parts)
    return json.loads(rendered)


def test_account_bpa_blocks_all_four_public_access_routes(stacks):
    """Phase 3E sets every account-level switch. Delete reverts to no
    configuration."""
    template = stacks["security_monitoring"]
    template.resource_count_is("Custom::AWS", 1)

    # Create and Update must be identical. Otherwise a later settings change
    # synthesizes but never reaches the account.
    for key in ("Create", "Update"):
        call = _account_bpa_call(template, key)
        assert call["service"] == "S3Control"
        assert call["action"] == "putPublicAccessBlock"
        assert call["parameters"]["AccountId"] == "<ACCOUNT>"
        assert call["parameters"]["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
        assert call["physicalResourceId"] == {"id": "mlops-dev-account-bpa"}

    delete = _account_bpa_call(template, "Delete")
    assert delete["service"] == "S3Control"
    assert delete["action"] == "deletePublicAccessBlock"
    assert delete["parameters"] == {"AccountId": "<ACCOUNT>"}

    custom_resource = next(
        value
        for value in template.to_json()["Resources"].values()
        if value["Type"] == "Custom::AWS"
    )
    assert custom_resource["Properties"]["InstallLatestAwsSdk"] is False

    # The provider role must gain nothing beyond the account-level actions.
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": [
                        {
                            "Action": [
                                "s3:PutAccountPublicAccessBlock",
                                "s3:DeleteAccountPublicAccessBlock",
                            ],
                            "Effect": "Allow",
                            "Resource": "*",
                        }
                    ]
                }
            )
        },
    )


@pytest.mark.parametrize(
    "flag",
    sorted(set(PHASE_3_SERVICE_FLAGS) - IMPLEMENTED_SERVICE_FLAGS),
)
def test_enabling_an_unimplemented_service_flag_fails_loudly(flag):
    """A flag with no CDK behind it must raise. It must not deploy nothing.

    Without this, flipping e.g. security_hub to true would synth and deploy
    cleanly while creating no resource at all -- the security service would
    look enabled and not be.
    """
    config = load_config("dev")
    config["security"]["services"][flag] = True

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    with pytest.raises(ValueError, match="no stack implementation") as excinfo:
        SecurityMonitoringStack(
            app,
            # Stack ids must match /^[A-Za-z][A-Za-z0-9-]*$/. Drop the
            # underscores, so CDK does not reject the name first.
            f"Test-SecurityMonitoring-Unimplemented-{flag.replace('_', '-')}",
            alert_topic=None,
            access_log_bucket=None,
            audit_bucket=None,
            audit_key=None,
            config=config,
        )
    assert flag in str(excinfo.value)


def test_implemented_service_flags_are_a_subset_of_the_declared_contract():
    """Catch a typo in IMPLEMENTED_SERVICE_FLAGS that would disable the
    guard."""
    assert IMPLEMENTED_SERVICE_FLAGS <= set(PHASE_3_SERVICE_FLAGS)


def test_prod_security_monitoring_stays_a_disabled_shell():
    """Production stays unchanged until its own approved rollout."""
    config = load_config("prod")
    assert set(config["security"]["services"].values()) == {False}

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stack = SecurityMonitoringStack(
        app,
        "Test-Prod-SecurityMonitoring",
        alert_topic=None,
        access_log_bucket=None,
        audit_bucket=None,
        audit_key=None,
        config=config,
    )
    app.synth()
    resources = Template.from_stack(stack).to_json().get("Resources", {})
    assert set(resources) <= {"CDKMetadata"}


def test_disabling_a_phase_3_flag_still_synthesizes():
    """Turning a sub-phase off must not break synthesis. Otherwise rollback
    is stuck.

    Acknowledgements are matched to real constructs, so one naming a flag-gated
    Phase 3 construct fails synthesis the moment that flag goes false -- which is
    exactly the rollback path. Without requires_flag, flipping account_bpa
    back off would leave the environment unable to synthesize the revert.
    """
    config = load_config("dev")
    config["security"]["services"]["account_bpa"] = False

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stacks = build_app(app, config, "Test-Rollback")
    app.synth()

    resources = Template.from_stack(stacks["security_monitoring"]).to_json()["Resources"]
    assert "Custom::AWS" not in {value["Type"] for value in resources.values()}


def test_config_recorder_records_only_the_named_security_types(stacks):
    """Phase 3C is not an all-types recorder. Config bills per item.

    `AllSupported` true would silently start versioning every resource class,
    including whatever the planned EC2 work adds, with no diff to review.
    """
    template = stacks["security_monitoring"]
    template.resource_count_is("AWS::Config::ConfigurationRecorder", 1)

    recorder = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::Config::ConfigurationRecorder"
    )
    assert recorder["Name"] == "mlops-dev-recorder"
    assert recorder["RecordingGroup"]["AllSupported"] is False
    assert recorder["RecordingGroup"]["IncludeGlobalResourceTypes"] is False
    assert recorder["RecordingGroup"]["ResourceTypes"] == list(CONFIG_RECORDED_TYPES)
    # The recorder authorizes through the AWS-owned service-linked role, so no
    # role in this repository can be over-granted on its behalf. The path is
    # `aws-service-role`. `aws-service-linked-role` is not a real IAM path. It
    # would be denied at CreateServiceLinkedRole and roll the deploy back.
    role_arn = json.dumps(recorder["RoleARN"])
    assert "role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig" in role_arn
    assert "aws-service-linked-role" not in role_arn
    template.resource_count_is("AWS::IAM::ServiceLinkedRole", 1)


def test_config_delivers_into_the_audit_bucket_under_its_own_prefix(stacks):
    """Snapshots are audit evidence. They land in the audit bucket and inherit
    its KMS key, its versioning, and its RETAIN policy."""
    template = stacks["security_monitoring"]
    template.resource_count_is("AWS::Config::DeliveryChannel", 1)

    channel = next(
        resource["Properties"]
        for resource in template.to_json()["Resources"].values()
        if resource["Type"] == "AWS::Config::DeliveryChannel"
    )
    assert channel["S3KeyPrefix"] == CONFIG_DELIVERY_PREFIX
    # This is imported from the Security stack, never a literal name.
    assert "Fn::ImportValue" in json.dumps(channel["S3BucketName"])


def test_disabling_config_leaves_no_recorder_and_no_bucket_grant():
    """The rollback path. Turning Phase 3C off must remove the principal."""
    config = load_config("dev")
    config["security"]["services"]["config_recorder"] = False

    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    built = build_app(app, config, "Test-ConfigOff")
    app.synth()

    monitoring = Template.from_stack(built["security_monitoring"]).to_json()["Resources"]
    assert not [r for r in monitoring.values() if r["Type"].startswith("AWS::Config::")]
    # The grant lives in the Security stack. Assert it disappears there too.
    security = json.dumps(Template.from_stack(built["security"]).to_json())
    assert "config.amazonaws.com" not in security


def test_the_recorder_and_channel_are_not_ordered_against_each_other(stacks):
    """The two Config resources depend on each other, so neither may depend on
    the other.

    PutDeliveryChannel fails until a recorder exists; the recorder's creation
    calls StartConfigurationRecorder, which fails until a channel exists. Both
    orderings were deployed and both deadlocked -- and because CloudFormation
    retries those two errors rather than failing, each hung in
    CREATE_IN_PROGRESS until it was cancelled by hand instead of rolling back.
    Left concurrent, the retries converge.
    """
    resources = stacks["security_monitoring"].to_json()["Resources"]
    recorder_id, recorder = next(
        (key, value)
        for key, value in resources.items()
        if value["Type"] == "AWS::Config::ConfigurationRecorder"
    )
    channel_id, channel = next(
        (key, value)
        for key, value in resources.items()
        if value["Type"] == "AWS::Config::DeliveryChannel"
    )

    assert recorder_id not in channel.get("DependsOn", [])
    assert channel_id not in recorder.get("DependsOn", [])
    # The recorder still waits on the service-linked role it uses.
    slr_id = next(
        key for key, value in resources.items() if value["Type"] == "AWS::IAM::ServiceLinkedRole"
    )
    assert slr_id in recorder["DependsOn"]
