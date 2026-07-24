"""Phase 3 threat detection and configuration monitoring, one flag-gated service at a time."""

from typing import Any

from aws_cdk import Stack, Tags
from aws_cdk import aws_accessanalyzer as accessanalyzer
from aws_cdk import aws_guardduty as guardduty
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import custom_resources as cr
from constructs import Construct

from infra.stacks.shared import PlatformConfig

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
IMPLEMENTED_SERVICE_FLAGS = frozenset({"access_analyzer", "guardduty", "account_bpa"})

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
        audit_key: kms.IKey,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = config["env_name"]
        self.alert_topic = alert_topic
        self.access_log_bucket = access_log_bucket
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
                            # The account-level actions are not bucket-scoped and
                            # AWS accepts only "*" as their resource.
                            actions=[
                                "s3:GetAccountPublicAccessBlock",
                                "s3:PutAccountPublicAccessBlock",
                                "s3:DeleteAccountPublicAccessBlock",
                            ],
                            resources=["*"],
                        )
                    ]
                ),
            )
