"""Phase 2 audit foundation: retained evidence, CloudTrail, and alert delivery."""

from aws_cdk import ArnFormat, CfnOutput, CfnParameter, RemovalPolicy, Stack, Tags
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct


class SecurityStack(Stack):
    """Durable audit storage and alert transport for the dev account."""

    def __init__(self, scope: Construct, construct_id: str, *, config: dict, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        env_name = config["env_name"]
        security_config = config["security"]
        if security_config["audit_log_retention_days"] != 90:
            raise ValueError("Phase 2 requires exactly 90 days of CloudWatch audit retention")

        trail_name = f"mlops-{env_name}-audit"
        log_group_name = f"/aws/cloudtrail/{trail_name}"
        key_alias = f"alias/{trail_name}"
        topic_name = f"mlops-{env_name}-security-alerts"

        trail_arn = self.format_arn(
            service="cloudtrail",
            resource="trail",
            resource_name=trail_name,
        )
        log_group_arn = self.format_arn(
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
            service="logs",
            resource="log-group",
            resource_name=log_group_name,
        )
        alarm_arn = self.format_arn(
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
            service="cloudwatch",
            resource="alarm",
            resource_name="*",
        )
        budget_arn = self.format_arn(
            service="budgets",
            region="",
            resource="budget",
            resource_name="*",
        )

        audit_key = kms.Key(
            self,
            "AuditKey",
            alias=key_alias,
            description=f"{env_name} CloudTrail, audit logs, and security alerts",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        self.audit_key = audit_key

        audit_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowCloudTrailAuditEncryption",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["kms:GenerateDataKey*", "kms:DescribeKey"],
                resources=["*"],
                conditions={
                    "StringEquals": {"aws:SourceArn": trail_arn},
                    "StringLike": {
                        "kms:EncryptionContext:aws:cloudtrail:arn": trail_arn,
                    },
                },
            )
        )
        audit_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowRegionalCloudWatchLogsEncryption",
                principals=[iam.ServicePrincipal(f"logs.{self.region}.amazonaws.com")],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=["*"],
                conditions={
                    "ArnEquals": {
                        "kms:EncryptionContext:aws:logs:arn": log_group_arn,
                    }
                },
            )
        )
        for sid, service, source_arn in (
            ("AllowCloudWatchEncryptedAlerts", "cloudwatch.amazonaws.com", alarm_arn),
            ("AllowBudgetsEncryptedAlerts", "budgets.amazonaws.com", budget_arn),
        ):
            audit_key.add_to_resource_policy(
                iam.PolicyStatement(
                    sid=sid,
                    principals=[iam.ServicePrincipal(service)],
                    actions=["kms:Decrypt", "kms:GenerateDataKey*"],
                    resources=["*"],
                    conditions={
                        "StringEquals": {"aws:SourceAccount": self.account},
                        "ArnLike": {"aws:SourceArn": source_arn},
                    },
                )
            )

        access_log_bucket = s3.Bucket(
            self,
            "AccessLogBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            minimum_tls_version=1.2,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.RETAIN,
            versioned=True,
        )
        self.access_log_bucket = access_log_bucket

        audit_bucket = s3.Bucket(
            self,
            "AuditBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            bucket_key_enabled=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=audit_key,
            enforce_ssl=True,
            minimum_tls_version=1.2,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.RETAIN,
            server_access_logs_bucket=access_log_bucket,
            server_access_logs_prefix="cloudtrail/",
            versioned=True,
        )
        self.audit_bucket = audit_bucket

        audit_log_group = logs.LogGroup(
            self,
            "AuditLogGroup",
            encryption_key=audit_key,
            log_group_name=log_group_name,
            removal_policy=RemovalPolicy.RETAIN,
            retention=logs.RetentionDays.THREE_MONTHS,
        )
        self.audit_log_group = audit_log_group

        trail_role = iam.Role(
            self,
            "CloudTrailLogsRole",
            assumed_by=iam.ServicePrincipal("cloudtrail.amazonaws.com"),
            description=f"Writes {trail_name} management events to its CloudWatch log group",
        )
        trail_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[f"{log_group_arn}:log-stream:*"],
            )
        )

        for statement in (
            iam.PolicyStatement(
                sid="CloudTrailBucketAclCheck",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:GetBucketAcl"],
                resources=[audit_bucket.bucket_arn],
                conditions={"StringEquals": {"aws:SourceArn": trail_arn}},
            ),
            iam.PolicyStatement(
                sid="CloudTrailLogDelivery",
                principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{audit_bucket.bucket_arn}/AWSLogs/{self.account}/*"],
                conditions={
                    "StringEquals": {
                        "aws:SourceArn": trail_arn,
                        "s3:x-amz-acl": "bucket-owner-full-control",
                    }
                },
            ),
        ):
            audit_bucket.add_to_resource_policy(statement)

        trail = cloudtrail.CfnTrail(
            self,
            "AuditTrail",
            cloud_watch_logs_log_group_arn=f"{log_group_arn}:*",
            cloud_watch_logs_role_arn=trail_role.role_arn,
            enable_log_file_validation=True,
            event_selectors=[
                cloudtrail.CfnTrail.EventSelectorProperty(
                    include_management_events=True,
                    read_write_type="All",
                )
            ],
            include_global_service_events=True,
            is_logging=True,
            is_multi_region_trail=True,
            is_organization_trail=False,
            kms_key_id=audit_key.key_arn,
            s3_bucket_name=audit_bucket.bucket_name,
            trail_name=trail_name,
        )
        trail.add_dependency(audit_bucket.node.find_child("Policy").node.default_child)
        trail.add_dependency(audit_log_group.node.default_child)
        trail.add_dependency(trail_role.node.default_child)
        self.trail = trail

        for key, value in (
            ("Project", "aws-mlops-platform"),
            ("Environment", env_name),
            ("SecurityPhase", "2B"),
        ):
            Tags.of(trail).add(key, value)

        alert_email = CfnParameter(
            self,
            "SecurityAlertEmail",
            description="Email endpoint for dev security and budget alerts",
            type="String",
        )
        alert_topic = sns.Topic(
            self,
            "SecurityAlertsTopic",
            enforce_ssl=True,
            master_key=audit_key,
            topic_name=topic_name,
        )
        self.alert_topic = alert_topic
        alert_topic.add_subscription(subscriptions.EmailSubscription(alert_email.value_as_string))

        for sid, service, source_arn in (
            ("AllowCloudWatchAlarmPublish", "cloudwatch.amazonaws.com", alarm_arn),
            ("AllowBudgetsPublish", "budgets.amazonaws.com", budget_arn),
        ):
            alert_topic.add_to_resource_policy(
                iam.PolicyStatement(
                    sid=sid,
                    principals=[iam.ServicePrincipal(service)],
                    actions=["sns:Publish"],
                    resources=[alert_topic.topic_arn],
                    conditions={
                        "StringEquals": {"aws:SourceAccount": self.account},
                        "ArnLike": {"aws:SourceArn": source_arn},
                    },
                )
            )

        CfnOutput(self, "TrailName", value=trail_name)
        CfnOutput(self, "AuditBucketName", value=audit_bucket.bucket_name)
        CfnOutput(self, "AccessLogBucketName", value=access_log_bucket.bucket_name)
        CfnOutput(self, "AuditLogGroupName", value=log_group_name)
        CfnOutput(self, "SecurityAlertsTopicArn", value=alert_topic.topic_arn)
        CfnOutput(self, "AuditKeyAlias", value=key_alias)
