"""Buckets + budget tripwire. Stable stack — never torn down with serving/training."""

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from constructs import Construct


def _bucket(
    scope: Construct,
    name: str,
    *,
    access_log_bucket: s3.IBucket,
    access_log_prefix: str,
    event_bridge: bool = False,
) -> s3.Bucket:
    bucket = s3.Bucket(
        scope,
        name,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.KMS_MANAGED,
        enforce_ssl=True,
        event_bridge_enabled=event_bridge,
        versioned=True,
        removal_policy=RemovalPolicy.RETAIN,
    )
    cfn_bucket = bucket.node.default_child
    if not isinstance(cfn_bucket, s3.CfnBucket):
        raise TypeError(f"{bucket.node.path} must synthesize through AWS::S3::Bucket")
    cfn_bucket.logging_configuration = s3.CfnBucket.LoggingConfigurationProperty(
        destination_bucket_name=access_log_bucket.bucket_name,
        log_file_prefix=access_log_prefix,
    )
    return bucket


class DataStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        access_log_bucket: s3.IBucket,
        alert_topic: sns.ITopic,
        config: dict,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.raw_bucket = _bucket(
            self,
            "RawBucket",
            access_log_bucket=access_log_bucket,
            access_log_prefix="raw/",
            event_bridge=True,
        )
        self.curated_bucket = _bucket(
            self,
            "CuratedBucket",
            access_log_bucket=access_log_bucket,
            access_log_prefix="curated/",
        )
        self.artifacts_bucket = _bucket(
            self,
            "ArtifactsBucket",
            access_log_bucket=access_log_bucket,
            access_log_prefix="artifacts/",
        )

        budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=config["budget_usd"], unit="USD"
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        comparison_operator="GREATER_THAN",
                        notification_type="ACTUAL",
                        threshold=threshold,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            address=alert_topic.topic_arn,
                            subscription_type="SNS",
                        )
                    ],
                )
                for threshold in config["security"]["budget_thresholds"]
            ],
        )
