"""Model Package Group. Stable stack — holds model lineage across redeploys."""

from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_sagemaker as sagemaker
from constructs import Construct

from infra.stacks.shared import PlatformConfig


class RegistryStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, config: PlatformConfig, **kwargs: Any
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.package_group_name = config["model_package_group"]
        sagemaker.CfnModelPackageGroup(
            self,
            "ChurnModelGroup",
            model_package_group_name=self.package_group_name,
            model_package_group_description="Telco churn challengers, gated on test AUC.",
        )
