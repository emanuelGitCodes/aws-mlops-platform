"""Threat detection and configuration monitoring, one flag-gated service at a time."""

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

from infra.stacks.shared import CONFIG_DELIVERY_PREFIX, PlatformConfig

PHASE_3_SERVICE_FLAGS = (
    "access_analyzer",
    "guardduty",
    "config_recorder",
    "security_hub",
    "account_bpa",
    "eventbridge_alerts",
)

# The flags this stack builds resources for. The other flags keep the config
# contract stable, but have no CDK behind them. Enabling one of those must fail
# loudly. A silent no-op deploy looks like an enabled security service. Add a
# flag here in the change that implements it.
IMPLEMENTED_SERVICE_FLAGS = frozenset(
    {
        "access_analyzer",
        "guardduty",
        "account_bpa",
        "config_recorder",
        "eventbridge_alerts",
    }
)

# Config records history for the resource types the metric detections alarm
# on, and no others. It bills per configuration item, so an all-types recorder
# pays to version resources no control reads, and it grows when EC2 arrives.
# Recording is continuous: at $0.003 an item against about 100 resources, the
# periodic rate costs more for less.
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

# Account-level Block Public Access is the backstop under every per-bucket
# setting. It covers buckets this repository does not create, and it survives a
# bucket-level mistake. All four settings move together. A partial block leaves
# one route to public exposure open.
ACCOUNT_BPA_CONFIGURATION = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}

# Route a finding only while it is live. A deleted finding and a resolved one
# both describe work that is already done.
ACCESS_ANALYZER_FINDING_PATTERN = {
    "source": ["aws.access-analyzer"],
    "detail-type": ["Access Analyzer Finding"],
    "detail": {"status": ["ACTIVE"], "isDeleted": [False]},
}

# Config writes its history and snapshots to the audit bucket. A failed
# delivery breaks that evidence trail without stopping the recorder, so no
# other control reports it.
#
# Configuration item changes are not routed. Continuous recording emits one
# event per change across about 100 resources, and the target is an email
# topic. Compliance events are not routed either, because this account
# deploys no Config rules for them to come from.
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
            analyzer = accessanalyzer.CfnAnalyzer(
                self,
                "ExternalAccessAnalyzer",
                analyzer_name=f"mlops-{self.env_name}-external-access",
                type="ACCOUNT",
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
            # CloudFormation has no resource type for the account-level
            # setting, so this calls the S3 Control API directly. The account id
            # stays a pseudo-parameter, never a literal. The Custom::AWS
            # resource is not taggable, so it carries no tags.
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
                # Repeat the call on update. Otherwise a later change to the
                # four settings synthesizes but never reaches the account.
                on_update=put_account_bpa,
                # Delete restores the pre-state, which is no account-level
                # configuration. A failed phase rolls back to where it began.
                on_delete=cr.AwsSdkCall(
                    service="S3Control",
                    action="deletePublicAccessBlock",
                    parameters={"AccountId": self.account},
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    [
                        iam.PolicyStatement(
                            # Only the two actions the calls above make. These
                            # account-level actions are not bucket-scoped, and
                            # AWS accepts only "*" as their resource. A third
                            # grant would be unused wildcard debt.
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
            # Config authorizes itself through the service-linked role, not a
            # role this stack writes. AWS owns that policy, so the recorder
            # cannot receive more than the service needs. The CloudFormation
            # execution policy grants the scoped CreateServiceLinkedRole.
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
                    # Use `aws-service-role`. `aws-service-linked-role` is not
                    # a real IAM path, and CreateServiceLinkedRole fails on it.
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

            # Do not order this against the recorder. The two depend on each
            # other at the API. PutDeliveryChannel fails until a recorder
            # exists. The recorder calls StartConfigurationRecorder, which
            # fails until a channel exists. Either order deadlocks, and
            # CloudFormation retries both errors rather than failing, so the
            # deploy hangs until it is cancelled. Left concurrent, the retries
            # converge.
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
            # A source routes only while its own service runs. A rule for a
            # service this account has switched off matches nothing, and a
            # silent rule reads the same as a working one.
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
                    # The topic policy and the audit key grant publication to
                    # this name prefix. A rule named outside it matches its
                    # events and then fails to deliver them.
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
