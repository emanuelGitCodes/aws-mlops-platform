"""Define audit storage, CIS metric detections, and alert delivery."""

from dataclasses import dataclass
from typing import Any

from aws_cdk import (
    ArnFormat,
    CfnOutput,
    CfnParameter,
    CfnResource,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct, IConstruct

from infra.stacks.shared import (
    CONFIG_DELIVERY_PREFIX,
    PlatformConfig,
    github_deploy_role_name,
)


@dataclass(frozen=True)
class SecurityDetection:
    """One CIS metric filter and the alarm evaluation applied to it."""

    metric_name: str
    alarm_slug: str
    filter_pattern: str
    # One five-minute datapoint at one or more starts an alarm.
    # `None` omits the `DatapointsToAlarm` property.
    evaluation_periods: int = 1
    datapoints_to_alarm: int | None = None
    # The filter default publishes zero only during periods with log events.
    # `FILL` replaces metric gaps with zero before alarm evaluation.
    fill_missing: bool = False


SECURITY_DETECTIONS = (
    SecurityDetection(
        "RootUserActivity",
        "root-user-activity",
        '{$.userIdentity.type="Root" && $.userIdentity.invokedBy NOT EXISTS && '
        '$.eventType !="AwsServiceEvent"}',
    ),
    SecurityDetection(
        "UnauthorizedApiCalls",
        "unauthorized-api-calls",
        '{($.errorCode="*UnauthorizedOperation") || ($.errorCode="AccessDenied*")}',
        # Require denials in three consecutive five-minute periods.
        evaluation_periods=3,
        datapoints_to_alarm=3,
        fill_missing=True,
    ),
    SecurityDetection(
        "IamPolicyChanges",
        "iam-policy-changes",
        "{($.eventSource=iam.amazonaws.com) && "
        "(($.eventName=DeleteGroupPolicy) || ($.eventName=DeleteRolePolicy) || "
        "($.eventName=DeleteUserPolicy) || ($.eventName=PutGroupPolicy) || "
        "($.eventName=PutRolePolicy) || ($.eventName=PutUserPolicy) || "
        "($.eventName=CreatePolicy) || ($.eventName=DeletePolicy) || "
        "($.eventName=CreatePolicyVersion) || ($.eventName=DeletePolicyVersion) || "
        "($.eventName=AttachRolePolicy) || ($.eventName=DetachRolePolicy) || "
        "($.eventName=AttachUserPolicy) || ($.eventName=DetachUserPolicy) || "
        "($.eventName=AttachGroupPolicy) || ($.eventName=DetachGroupPolicy))}",
    ),
    SecurityDetection(
        "CloudTrailConfigurationChanges",
        "cloudtrail-configuration-changes",
        "{($.eventName=CreateTrail) || ($.eventName=UpdateTrail) || "
        "($.eventName=DeleteTrail) || ($.eventName=StartLogging) || "
        "($.eventName=StopLogging)}",
    ),
    SecurityDetection(
        "KmsKeyDisableOrDeletion",
        "kms-key-disable-or-deletion",
        "{($.eventSource=kms.amazonaws.com) && (($.eventName=DisableKey) || "
        "($.eventName=ScheduleKeyDeletion))}",
    ),
    # Detect each prod deploy-role assumption. Exclude the dev CI role.
    SecurityDetection(
        "ProdDeployRoleAssumed",
        "prod-deploy-role-assumed",
        '{($.eventSource="sts.amazonaws.com") && '
        '($.eventName="AssumeRoleWithWebIdentity") && '
        f'($.requestParameters.roleArn="*:role/{github_deploy_role_name("prod")}")}}',
    ),
    SecurityDetection(
        "S3BucketPolicyChanges",
        "s3-bucket-policy-changes",
        "{($.eventSource=s3.amazonaws.com) && (($.eventName=PutBucketAcl) || "
        "($.eventName=PutBucketPolicy) || ($.eventName=PutBucketCors) || "
        "($.eventName=PutBucketLifecycle) || ($.eventName=PutBucketReplication) || "
        "($.eventName=DeleteBucketPolicy) || ($.eventName=DeleteBucketCors) || "
        "($.eventName=DeleteBucketLifecycle) || ($.eventName=DeleteBucketReplication))}",
    ),
)


def _default_cfn_resource(construct: IConstruct) -> CfnResource:
    """Return the L1 child for `CfnResource.add_dependency`."""
    resource = construct.node.default_child
    if not isinstance(resource, CfnResource):
        raise TypeError(f"{construct.node.path} has no CfnResource default child")
    return resource


class SecurityStack(Stack):
    """Durable audit storage and alert transport for the dev account."""

    def __init__(
        self, scope: Construct, construct_id: str, *, config: PlatformConfig, **kwargs: Any
    ) -> None:
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
        # Every security event rule uses this name prefix.
        # Do not add a cross-stack rule reference here.
        security_rule_arn = self.format_arn(
            service="events",
            resource="rule",
            resource_name=f"mlops-{env_name}-security-*",
        )
        route_findings_to_alerts = security_config["services"]["eventbridge_alerts"]

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

        def _alert_service_statement(
            sid: str, service: str, source_arn: str, actions: list[str], resources: list[str]
        ) -> iam.PolicyStatement:
            """Grant an alerting service scoped by this account and source ARN."""
            return iam.PolicyStatement(
                sid=sid,
                principals=[iam.ServicePrincipal(service)],
                actions=actions,
                resources=resources,
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": source_arn},
                },
            )

        encrypted_alert_publishers = [
            ("AllowCloudWatchEncryptedAlerts", "cloudwatch.amazonaws.com", alarm_arn),
            ("AllowBudgetsEncryptedAlerts", "budgets.amazonaws.com", budget_arn),
        ]
        if route_findings_to_alerts:
            encrypted_alert_publishers.append(
                (
                    "AllowEventBridgeEncryptedAlerts",
                    "events.amazonaws.com",
                    security_rule_arn,
                )
            )
        for sid, service, source_arn in encrypted_alert_publishers:
            audit_key.add_to_resource_policy(
                _alert_service_statement(
                    sid,
                    service,
                    source_arn,
                    actions=["kms:Decrypt", "kms:GenerateDataKey*"],
                    resources=["*"],
                )
            )

        def _hardened_bucket(bucket_id: str, **overrides: Any) -> s3.Bucket:
            """Retained, versioned, TLS-enforced private bucket."""
            props: dict[str, Any] = {
                "block_public_access": s3.BlockPublicAccess.BLOCK_ALL,
                "encryption": s3.BucketEncryption.S3_MANAGED,
                "enforce_ssl": True,
                "minimum_tls_version": 1.2,
                "object_ownership": s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
                "removal_policy": RemovalPolicy.RETAIN,
                "versioned": True,
            }
            props.update(overrides)
            return s3.Bucket(self, bucket_id, **props)

        access_log_bucket = _hardened_bucket("AccessLogBucket")
        self.access_log_bucket = access_log_bucket

        audit_bucket = _hardened_bucket(
            "AuditBucket",
            bucket_key_enabled=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=audit_key,
            server_access_logs_bucket=access_log_bucket,
            server_access_logs_prefix="cloudtrail/",
        )
        self.audit_bucket = audit_bucket

        data_bucket_arn_pattern = self.format_arn(
            account="",
            region="",
            service="s3",
            resource=f"mlops-{env_name}-data-*",
        )
        access_log_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowDataBucketAccessLogs",
                principals=[iam.ServicePrincipal("logging.s3.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[
                    f"{access_log_bucket.bucket_arn}/{prefix}*"
                    for prefix in ("raw/", "curated/", "artifacts/")
                ],
                conditions={
                    "ArnLike": {"aws:SourceArn": data_bucket_arn_pattern},
                    "StringEquals": {"aws:SourceAccount": self.account},
                },
            )
        )

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

        # Grant Config access to the audit bucket and key in this stack.
        # The recorder flag removes these principals when Config is disabled.
        if config["security"]["services"]["config_recorder"]:
            for statement in (
                iam.PolicyStatement(
                    sid="ConfigBucketAclCheck",
                    principals=[iam.ServicePrincipal("config.amazonaws.com")],
                    actions=["s3:GetBucketAcl", "s3:ListBucket"],
                    resources=[audit_bucket.bucket_arn],
                    conditions={"StringEquals": {"aws:SourceAccount": self.account}},
                ),
                iam.PolicyStatement(
                    sid="ConfigSnapshotDelivery",
                    principals=[iam.ServicePrincipal("config.amazonaws.com")],
                    actions=["s3:PutObject"],
                    resources=[
                        f"{audit_bucket.bucket_arn}/{CONFIG_DELIVERY_PREFIX}"
                        f"/AWSLogs/{self.account}/Config/*"
                    ],
                    conditions={
                        "StringEquals": {
                            "aws:SourceAccount": self.account,
                            "s3:x-amz-acl": "bucket-owner-full-control",
                        }
                    },
                ),
            ):
                audit_bucket.add_to_resource_policy(statement)

            # Config encrypts each snapshot with the audit key.
            audit_key.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AllowConfigSnapshotEncryption",
                    principals=[iam.ServicePrincipal("config.amazonaws.com")],
                    actions=["kms:GenerateDataKey", "kms:Decrypt"],
                    resources=["*"],
                    conditions={"StringEquals": {"aws:SourceAccount": self.account}},
                )
            )

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
        trail.add_dependency(_default_cfn_resource(audit_bucket.node.find_child("Policy")))
        trail.add_dependency(_default_cfn_resource(audit_log_group))
        trail.add_dependency(_default_cfn_resource(trail_role))
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

        alert_publishers = [
            ("AllowCloudWatchAlarmPublish", "cloudwatch.amazonaws.com", alarm_arn),
            ("AllowBudgetsPublish", "budgets.amazonaws.com", budget_arn),
        ]
        if route_findings_to_alerts:
            alert_publishers.append(
                ("AllowEventBridgePublish", "events.amazonaws.com", security_rule_arn)
            )
        for sid, service, source_arn in alert_publishers:
            alert_topic.add_to_resource_policy(
                _alert_service_statement(
                    sid,
                    service,
                    source_arn,
                    actions=["sns:Publish"],
                    resources=[alert_topic.topic_arn],
                )
            )

        for detection in SECURITY_DETECTIONS:
            logs.MetricFilter(
                self,
                f"{detection.metric_name}Filter",
                default_value=0,
                filter_pattern=logs.FilterPattern.literal(detection.filter_pattern),
                log_group=audit_log_group,
                metric_name=detection.metric_name,
                metric_namespace="MLOps/Security",
                metric_value="1",
            )
            filtered_metric = cloudwatch.Metric(
                metric_name=detection.metric_name,
                namespace="MLOps/Security",
                period=Duration.minutes(5),
                statistic="Sum",
            )
            alarm_metric: cloudwatch.IMetric = filtered_metric
            if detection.fill_missing:
                alarm_metric = cloudwatch.MathExpression(
                    expression="FILL(m1, 0)",
                    period=Duration.minutes(5),
                    using_metrics={"m1": filtered_metric},
                )
            alarm = cloudwatch.Alarm(
                self,
                f"{detection.metric_name}Alarm",
                actions_enabled=True,
                alarm_name=f"mlops-{env_name}-security-{detection.alarm_slug}",
                comparison_operator=(
                    cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
                ),
                datapoints_to_alarm=detection.datapoints_to_alarm,
                evaluation_periods=detection.evaluation_periods,
                metric=alarm_metric,
                threshold=1,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            alarm.add_alarm_action(cloudwatch_actions.SnsAction(alert_topic))

        CfnOutput(self, "TrailName", value=trail_name)
        CfnOutput(self, "AuditBucketName", value=audit_bucket.bucket_name)
        CfnOutput(self, "AccessLogBucketName", value=access_log_bucket.bucket_name)
        CfnOutput(self, "AuditLogGroupName", value=log_group_name)
        CfnOutput(self, "SecurityAlertsTopicArn", value=alert_topic.topic_arn)
        CfnOutput(self, "AuditKeyAlias", value=key_alias)
