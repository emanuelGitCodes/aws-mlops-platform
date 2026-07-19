"""Phase 3 threat detection and configuration monitoring, one flag-gated service at a time."""

from aws_cdk import Stack, Tags
from aws_cdk import aws_accessanalyzer as accessanalyzer
from aws_cdk import aws_guardduty as guardduty
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from constructs import Construct

PHASE_3_SERVICE_FLAGS = (
    "access_analyzer",
    "guardduty",
    "config_recorder",
    "security_hub",
    "account_bpa",
    "eventbridge_alerts",
)

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
        config: dict,
        **kwargs,
    ):
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
