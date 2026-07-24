"""Buckets + budget tripwire. Stable stack — never torn down with serving/training."""

from typing import Any

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import custom_resources as cr
from constructs import Construct

from infra.stacks.shared import PlatformConfig


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
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
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

        monthly_budget = budgets.CfnBudget(
            self,
            "MonthlyBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=config["budget_usd"], unit="USD"
                ),
            ),
        )

        # CloudFormation replaces AWS::Budgets::Budget when notifications are added.
        # Manage each notification through the Budgets API so the existing $20 budget
        # keeps its physical name and history.
        budget_arn = self.format_arn(
            service="budgets",
            region="",
            resource="budget",
            resource_name=monthly_budget.ref,
        )
        budget_policy = cr.AwsCustomResourcePolicy.from_statements(
            [
                iam.PolicyStatement(
                    # Budgets maps both notification API calls to this IAM action.
                    actions=["budgets:ModifyBudget"],
                    resources=[budget_arn],
                )
            ]
        )
        for threshold in config["security"]["budget_thresholds"]:
            notification = {
                "ComparisonOperator": "GREATER_THAN",
                "NotificationType": "ACTUAL",
                "Threshold": threshold,
                "ThresholdType": "PERCENTAGE",
            }
            resource = cr.AwsCustomResource(
                self,
                f"BudgetAlert{threshold}Percent",
                install_latest_aws_sdk=False,
                on_create=cr.AwsSdkCall(
                    service="Budgets",
                    action="createNotification",
                    parameters={
                        "AccountId": self.account,
                        "BudgetName": monthly_budget.ref,
                        "Notification": notification,
                        "Subscribers": [
                            {
                                "Address": alert_topic.topic_arn,
                                "SubscriptionType": "SNS",
                            }
                        ],
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        f"actual-greater-than-{threshold}-percent"
                    ),
                ),
                on_delete=cr.AwsSdkCall(
                    service="Budgets",
                    action="deleteNotification",
                    parameters={
                        "AccountId": self.account,
                        "BudgetName": monthly_budget.ref,
                        "Notification": notification,
                    },
                ),
                policy=budget_policy,
            )
            resource.node.add_dependency(monthly_budget)
