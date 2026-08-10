"""Define the flag-gated threat detection and configuration services."""

from typing import Any

from aws_cdk import ArnFormat, Stack, Tags
from aws_cdk import aws_accessanalyzer as accessanalyzer
from aws_cdk import aws_config as config_
from aws_cdk import aws_events as events
from aws_cdk import aws_guardduty as guardduty
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import custom_resources as cr
from constructs import Construct

from infra.stacks.shared import (
    CONFIG_DELIVERY_PREFIX,
    PlatformConfig,
    github_deploy_role_name,
)

PHASE_3_SERVICE_FLAGS = (
    "access_analyzer",
    "guardduty",
    "config_recorder",
    "security_hub",
    "account_bpa",
    "eventbridge_alerts",
)

# This set lists service flags with CDK implementations.
# Enabling any other service flag raises `ValueError`.
# Add a flag only with its implementation.
IMPLEMENTED_SERVICE_FLAGS = frozenset(
    {
        "access_analyzer",
        "guardduty",
        "account_bpa",
        "config_recorder",
        "eventbridge_alerts",
    }
)

# Config records only the resource types used by the security detections.
# Continuous recording bills for each configuration item.
CONFIG_RECORDED_TYPES = (
    "AWS::CloudTrail::Trail",
    "AWS::IAM::Group",
    "AWS::IAM::Policy",
    "AWS::IAM::Role",
    "AWS::IAM::User",
    "AWS::KMS::Key",
    "AWS::Lambda::Function",
    "AWS::S3::Bucket",
    "AWS::SNS::Topic",
    "AWS::SQS::Queue",
)

# Account-level Block Public Access applies to every bucket in the account.
# Keep all four public-access settings enabled together.
ACCOUNT_BPA_CONFIGURATION = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}

# Access Analyzer emits events for finding creation, changes, and deletion.
# This pattern selects active findings that are not deleted.
ACCESS_ANALYZER_FINDING_PATTERN = {
    "source": ["aws.access-analyzer"],
    "detail-type": ["Access Analyzer Finding"],
    "detail": {"status": ["ACTIVE"], "isDeleted": [False]},
}

# Config writes configuration history and snapshots to the audit bucket.
# A delivery failure does not stop the recorder.
#
# Config emits one item-change event for each recorded resource change.
# Compliance events require Config rules. This stack defines no Config rules.
CONFIG_DELIVERY_FAILURE_PATTERN = {
    "source": ["aws.config"],
    "detail-type": [
        "Config Configuration History Delivery Status",
        "Config Configuration Snapshot Delivery Status",
    ],
    "detail": {
        "messageType": [
            "ConfigurationHistoryDeliveryFailed",
            "ConfigurationSnapshotDeliveryFailed",
        ]
    },
}

GUARDDUTY_DISABLED_FEATURES = (
    "S3_DATA_EVENTS",
    "EKS_AUDIT_LOGS",
    "EBS_MALWARE_PROTECTION",
    "RDS_LOGIN_EVENTS",
    "LAMBDA_NETWORK_LOGS",
    "AI_ANALYST",
)


class SecurityMonitoringStack(Stack):
    """Each service builds only when its own flag is true."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        alert_topic: sns.ITopic,
        access_log_bucket: s3.IBucket,
        audit_bucket: s3.IBucket,
        audit_key: kms.IKey,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = config["env_name"]
        self.alert_topic = alert_topic
        self.access_log_bucket = access_log_bucket
        self.audit_bucket = audit_bucket
        self.audit_key = audit_key

        services = config["security"]["services"]
        if set(services) != set(PHASE_3_SERVICE_FLAGS):
            raise ValueError("Phase 3 requires exactly the six service enablement flags")
        non_boolean = sorted(
            name for name, value in services.items() if not isinstance(value, bool)
        )
        if non_boolean:
            raise ValueError(f"Phase 3 service flags must be booleans: {non_boolean}")
        unimplemented = sorted(
            name
            for name, enabled in services.items()
            if enabled and name not in IMPLEMENTED_SERVICE_FLAGS
        )
        if unimplemented:
            raise ValueError(
                "Phase 3 service flags enabled with no stack implementation: "
                f"{unimplemented}. Implement the sub-phase before enabling its flag."
            )
        self.services = services

        if services["access_analyzer"]:
            # Access Analyzer reports this federated role as external access.
            # The exact ARN keeps all other external-access findings active.
            # Access Analyzer reports `condition: {}` for OIDC claim conditions.
            ci_deploy_role_arn = self.format_arn(
                service="iam",
                region="",
                resource="role",
                resource_name=github_deploy_role_name(self.env_name),
            )
            analyzer = accessanalyzer.CfnAnalyzer(
                self,
                "ExternalAccessAnalyzer",
                analyzer_name=f"mlops-{self.env_name}-external-access",
                type="ACCOUNT",
                archive_rules=[
                    accessanalyzer.CfnAnalyzer.ArchiveRuleProperty(
                        rule_name="ArchiveCiDeployRoleFederation",
                        filter=[
                            accessanalyzer.CfnAnalyzer.FilterProperty(
                                property="resource",
                                eq=[ci_deploy_role_arn],
                            )
                        ],
                    )
                ],
            )
            for key, value in (
                ("Project", "aws-mlops-platform"),
                ("Environment", self.env_name),
                ("SecurityPhase", "3A"),
            ):
                Tags.of(analyzer).add(key, value)

        if services["guardduty"]:
            detector = guardduty.CfnDetector(
                self,
                "FoundationalDetector",
                enable=True,
                finding_publishing_frequency="FIFTEEN_MINUTES",
                features=[
                    guardduty.CfnDetector.CFNFeatureConfigurationProperty(
                        name=name,
                        status="DISABLED",
                    )
                    for name in GUARDDUTY_DISABLED_FEATURES
                ],
            )
            for key, value in (
                ("Project", "aws-mlops-platform"),
                ("Environment", self.env_name),
                ("SecurityPhase", "3B"),
            ):
                Tags.of(detector).add(key, value)

        if services["account_bpa"]:
            # CloudFormation has no account-level Block Public Access resource.
            # This custom resource calls the S3 Control API.
            # The account id remains a pseudo-parameter. `Custom::AWS` is not taggable.
            bpa_resource_id = f"mlops-{self.env_name}-account-bpa"
            put_account_bpa = cr.AwsSdkCall(
                service="S3Control",
                action="putPublicAccessBlock",
                parameters={
                    "AccountId": self.account,
                    "PublicAccessBlockConfiguration": ACCOUNT_BPA_CONFIGURATION,
                },
                physical_resource_id=cr.PhysicalResourceId.of(bpa_resource_id),
            )
            cr.AwsCustomResource(
                self,
                "AccountPublicAccessBlock",
                install_latest_aws_sdk=False,
                on_create=put_account_bpa,
                # Apply all four settings during each update.
                on_update=put_account_bpa,
                # Delete the account-level configuration during stack deletion.
                on_delete=cr.AwsSdkCall(
                    service="S3Control",
                    action="deletePublicAccessBlock",
                    parameters={"AccountId": self.account},
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    [
                        iam.PolicyStatement(
                            # Grant only the two account-level API actions.
                            # AWS requires `"*"` as their resource.
                            actions=[
                                "s3:PutAccountPublicAccessBlock",
                                "s3:DeleteAccountPublicAccessBlock",
                            ],
                            resources=["*"],
                        )
                    ]
                ),
            )

        if services["config_recorder"]:
            # Config uses its AWS-owned service-linked role.
            # The CloudFormation execution policy grants scoped role creation.
            service_linked_role = iam.CfnServiceLinkedRole(
                self,
                "ConfigServiceLinkedRole",
                aws_service_name="config.amazonaws.com",
            )
            recorder = config_.CfnConfigurationRecorder(
                self,
                "ConfigurationRecorder",
                name=f"mlops-{self.env_name}-recorder",
                role_arn=self.format_arn(
                    service="iam",
                    region="",
                    # Use the IAM path `aws-service-role`.
                    # `CreateServiceLinkedRole` rejects `aws-service-linked-role`.
                    resource="role/aws-service-role/config.amazonaws.com",
                    resource_name="AWSServiceRoleForConfig",
                    arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                ),
                recording_group=config_.CfnConfigurationRecorder.RecordingGroupProperty(
                    all_supported=False,
                    include_global_resource_types=False,
                    resource_types=list(CONFIG_RECORDED_TYPES),
                ),
            )
            recorder.add_dependency(service_linked_role)

            # Do not order this resource against the recorder.
            # `PutDeliveryChannel` retries until a recorder exists.
            # `StartConfigurationRecorder` retries until a channel exists.
            # Concurrent creation lets both retries complete.
            config_.CfnDeliveryChannel(
                self,
                "ConfigDeliveryChannel",
                name=f"mlops-{self.env_name}-delivery",
                s3_bucket_name=audit_bucket.bucket_name,
                s3_key_prefix=CONFIG_DELIVERY_PREFIX,
                config_snapshot_delivery_properties=(
                    config_.CfnDeliveryChannel.ConfigSnapshotDeliveryPropertiesProperty(
                        delivery_frequency="TwentyFour_Hours"
                    )
                ),
            )

        if services["eventbridge_alerts"]:
            # Route events only for enabled source services.
            routed_sources = (
                (
                    "AccessAnalyzerFindingRule",
                    "access-analyzer-findings",
                    services["access_analyzer"],
                    "Active external-access findings",
                    ACCESS_ANALYZER_FINDING_PATTERN,
                ),
                (
                    "ConfigDeliveryFailureRule",
                    "config-delivery-failures",
                    services["config_recorder"],
                    "Config history or snapshot delivery failures",
                    CONFIG_DELIVERY_FAILURE_PATTERN,
                ),
            )
            for construct_id, slug, source_enabled, description, pattern in routed_sources:
                if not source_enabled:
                    continue
                rule = events.CfnRule(
                    self,
                    construct_id,
                    description=f"{description} to the {self.env_name} alert topic",
                    event_pattern=pattern,
                    # The topic policy and audit key grant this rule-name prefix.
                    name=f"mlops-{self.env_name}-security-{slug}",
                    state="ENABLED",
                    targets=[
                        events.CfnRule.TargetProperty(
                            arn=alert_topic.topic_arn,
                            id="SecurityAlertsTopic",
                        )
                    ],
                )
                for key, value in (
                    ("Project", "aws-mlops-platform"),
                    ("Environment", self.env_name),
                    ("SecurityPhase", "3F"),
                ):
                    Tags.of(rule).add(key, value)
