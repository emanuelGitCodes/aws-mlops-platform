"""Buckets + budget tripwire. Stable stack — never torn down with serving/training."""

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_s3 as s3
from constructs import Construct


def _bucket(scope: Construct, name: str, event_bridge: bool = False) -> s3.Bucket:
    return s3.Bucket(
        scope,
        name,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.KMS_MANAGED,
        enforce_ssl=True,
        event_bridge_enabled=event_bridge,
        versioned=True,
        removal_policy=RemovalPolicy.RETAIN,
    )


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, config: dict, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.raw_bucket = _bucket(self, "RawBucket", event_bridge=True)
        self.curated_bucket = _bucket(self, "CuratedBucket")
        self.artifacts_bucket = _bucket(self, "ArtifactsBucket")

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
        )
