"""SageMaker execution role for the training pipeline.

The pipeline definition itself lives in src/pipeline/pipeline.py and is
upserted with the SageMaker SDK (`make` target / CI step / retrain trigger),
because SageMaker Pipelines are versioned documents, not CloudFormation-native
resources. The stack owns the IAM the pipeline runs as.
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class TrainingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        curated_bucket: s3.IBucket,
        artifacts_bucket: s3.IBucket,
        config: dict,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.pipeline_role = iam.Role(
            self,
            "PipelineExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")
            ],
        )
        curated_bucket.grant_read(self.pipeline_role)
        artifacts_bucket.grant_read_write(self.pipeline_role)

        CfnOutput(self, "PipelineRoleArn", value=self.pipeline_role.role_arn)
