"""Phase 3 threat detection and configuration monitoring, one flag-gated service at a time."""

from typing import Any

from aws_cdk import ArnFormat, Stack, Tags
from aws_cdk import aws_accessanalyzer as accessanalyzer
from aws_cdk import aws_config as config_
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

# The subset of PHASE_3_SERVICE_FLAGS this stack actually builds resources for.
# The rest are declared in config so the flag contract stays stable across
# sub-phases, but have no CDK behind them yet. Enabling one of those must fail
# loudly: a silent no-op deploy would look like a security service was turned
# on when nothing was created. Add a flag here in the same change that
# implements its sub-phase.
IMPLEMENTED_SERVICE_FLAGS = frozenset(
    {"access_analyzer", "guardduty", "account_bpa", "config_recorder"}
)

# Phase 3C records configuration history for the resource classes the Phase 2C
# detections already alarm on changes to, and nothing else. Config bills per
# configuration item, so an all-types recorder would pay to version resources
# no control here reads -- and would grow silently when EC2 arrives. Recording
# is continuous: at $0.003 an item against ~100 resources the periodic rate
# would cost more for less.
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
# setting: it applies to buckets this repository does not create and survives a
# bucket-level misconfiguration. All four settings move together; a partial
# block would leave one public-exposure route open.
ACCOUNT_BPA_CONFIGURATION = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
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
    """Phase 3 services; every flag stays false until its own sub-phase enables it."""

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
            # CloudFormation has no resource type for the account-level setting,
            # so the S3 Control API is called directly and the account id stays a
            # pseudo-parameter rather than a literal. The synthesized Custom::AWS
            # resource is not taggable, so unlike the analyzer and the detector
            # this one carries no tags.
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
                # Repeating the call on update stops a later change to the four
                # settings from synthesizing without ever reaching the account.
                on_update=put_account_bpa,
                # Deleting restores the recorded pre-state (no account-level
                # configuration), so a failed phase rolls back to where it began.
                on_delete=cr.AwsSdkCall(
                    service="S3Control",
                    action="deletePublicAccessBlock",
                    parameters={"AccountId": self.account},
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    [
                        iam.PolicyStatement(
                            # Only the two actions the calls above make: the
                            # account-level actions are not bucket-scoped and AWS
                            # accepts only "*" as their resource, so an unused
                            # third grant would be wildcard debt for nothing.
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
            # role this stack writes: AWS owns its policy, so the recorder
            # cannot be granted more than the service needs. The execution
            # policy was pre-granted the scoped CreateServiceLinkedRole in
            # Phase 3-prep for exactly this.
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
                    # `aws-service-role`, not `aws-service-linked-role`: the
                    # latter is not a real IAM path. Phase 3-prep pre-granted
                    # the wrong one, which would have failed this deploy on
                    # CreateServiceLinkedRole; v10 corrects both statements.
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

            # Deliberately NOT ordered against the recorder. The two are
            # mutually dependent at the API: PutDeliveryChannel fails with
            # NoAvailableConfigurationRecorderException until a recorder
            # exists, and the recorder's own creation calls
            # StartConfigurationRecorder, which fails with
            # NoAvailableDeliveryChannelException until a channel exists.
            # Ordering either way deadlocks -- both were tried, and because
            # CloudFormation retries these two errors instead of failing, each
            # attempt hung until it was cancelled rather than rolling back on
            # its own. Left concurrent, the retries converge.
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
