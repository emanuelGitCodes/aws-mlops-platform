"""Define the SageMaker execution role for the training pipeline.

`src/pipeline/pipeline.py` owns the versioned pipeline definition. The SageMaker
SDK upserts that definition. This stack owns the pipeline execution role.
The role uses explicit policies. It does not attach `AmazonSageMakerFullAccess`.
"""

from typing import Any

from aws_cdk import ArnFormat, CfnOutput, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from infra.stacks.shared import (
    EVALUATION_REPORT_PREFIX,
    MODEL_ARTIFACT_PREFIX,
    MONITOR_OUTPUT_PREFIX,
    PlatformConfig,
    sagemaker_execution_role,
)


class TrainingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        curated_bucket: s3.IBucket,
        artifacts_bucket: s3.IBucket,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # This role carries no managed policy. Update it in place.
        # The deployed pipeline definition pins its ARN.
        self.pipeline_role = sagemaker_execution_role(
            self,
            "PipelineExecutionRole",
            least_privilege=True,
        )

        # Read training data only under the `telco/` prefix.
        # `InputDataUri` is an overridable pipeline parameter.
        # `retrain_handler` uses the default parameter.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[curated_bucket.arn_for_objects("telco/*")],
            )
        )
        # Grant step I/O only under the named artifact prefixes.
        # The SDK session also uses this bucket for code bundles.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"],
                resources=[
                    artifacts_bucket.arn_for_objects(f"{prefix}/*")
                    for prefix in (
                        config["pipeline_name"],
                        MODEL_ARTIFACT_PREFIX,
                        EVALUATION_REPORT_PREFIX,
                        MONITOR_OUTPUT_PREFIX,
                    )
                ],
            )
        )
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[curated_bucket.bucket_arn, artifacts_bucket.bucket_arn],
            )
        )

        # SageMaker names each step job `pipelines-<execution-id>-<Step>-<suffix>`.
        # Limit job actions to the `pipelines-*` ARN pattern.
        #
        # Scope `AddTags` to each created job ARN.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateProcessingJob",
                    "sagemaker:DescribeProcessingJob",
                    "sagemaker:AddTags",
                ],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="processing-job",
                        resource_name="pipelines-*",
                    )
                ],
            )
        )
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateTrainingJob",
                    "sagemaker:DescribeTrainingJob",
                    "sagemaker:AddTags",
                ],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="training-job",
                        resource_name="pipelines-*",
                    )
                ],
            )
        )
        # Register challenger models only in this platform model package group.
        # The SDK calls `CreateModelPackageGroup` before package registration.
        # A duplicate group returns `ValidationException` to that call.
        package_group_name = config["model_package_group"]
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateModelPackage",
                    "sagemaker:DescribeModelPackage",
                    "sagemaker:AddTags",
                ],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package",
                        resource_name=f"{package_group_name}/*",
                    )
                ],
            )
        )
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateModelPackageGroup", "sagemaker:AddTags"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package-group",
                        resource_name=package_group_name,
                    )
                ],
            )
        )
        # Each pipeline step passes this role to SageMaker.
        # Limit `iam:PassRole` to the SageMaker service.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[self.pipeline_role.role_arn],
                conditions={"StringEquals": {"iam:PassedToService": "sagemaker.amazonaws.com"}},
            )
        )
        # SageMaker owns the processing and training job log groups.
        # The container agent calls `CreateLogGroup` for each job.
        job_log_group_arns = [
            self.format_arn(
                service="logs",
                resource="log-group",
                resource_name=f"/aws/sagemaker/{job_type}Jobs",
                arn_format=ArnFormat.COLON_RESOURCE_NAME,
            )
            for job_type in ("Processing", "Training")
        ]
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=[arn for base in job_log_group_arns for arn in (base, f"{base}:*")],
            )
        )

        CfnOutput(self, "PipelineRoleArn", value=self.pipeline_role.role_arn)
