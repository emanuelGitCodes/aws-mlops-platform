"""SageMaker execution role for the training pipeline.

The pipeline definition lives in src/pipeline/pipeline.py. The SageMaker SDK
upserts it, because Pipelines are versioned documents and not CloudFormation
resources. This stack owns only the IAM role the pipeline runs as.

Phase 5D replaced `AmazonSageMakerFullAccess` with the policy below. Each
omission was checked against CloudTrail for the 2026-08-06 run:

- ECR: SageMaker pulls the first-party images with its own credentials.
- KMS: the buckets use the `aws/s3` key. Its key policy authorizes the call.
- `cloudwatch:PutMetricData`: published service-side, and it takes no ARN.
- `s3:DeleteObject*`: no step deletes.
- Lineage calls: CloudTrail attributes them to `sagemaker.amazonaws.com`.

`sagemaker:AddTags` is the exception. Pipelines tags each resource inside the
create call, so CloudTrail never logs it as its own event. Two runs had to fail
to find the four ARNs that need it.
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

        # Phase 5D: the last role off `AmazonSageMakerFullAccess`. Update this
        # role in place. Never replace it. The deployed pipeline definition and
        # `scripts/setup_monitor.py` both pin its ARN.
        self.pipeline_role = sagemaker_execution_role(
            self,
            "PipelineExecutionRole",
            least_privilege=True,
        )

        # Read the one dataset the pipeline trains on. `InputDataUri` is a
        # pipeline parameter, so a crafted `StartPipelineExecution` can override
        # it. The `telco/` prefix stops that call reading another bucket.
        # `retrain_handler` uses default parameters only.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[curated_bucket.arn_for_objects("telco/*")],
            )
        )
        # Step I/O on the artifacts bucket, which is also the SDK session
        # bucket: code bundles, `model.tar.gz`, evaluation reports, and the
        # Model Monitor baseline. This replaces `grant_read_write`, which
        # covered the whole bucket with ten actions.
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

        # The jobs each step creates. SageMaker names them
        # `pipelines-<execution-id>-<Step>-<suffix>`, so `pipelines-*` is the
        # tightest wildcard available. It still excludes every job this
        # pipeline did not start.
        #
        # `AddTags` accompanies every create below, scoped to the ARN of the
        # resource being created. It adds no reach the create does not have.
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
        # Register the challenger model. The policy pins this platform's own
        # group, which stops the pipeline writing lineage into a foreign group.
        # `CreateModelPackageGroup` is granted because the SDK always calls it
        # first. The group exists, so the call returns `ValidationException`.
        # Without the grant it returns `AccessDenied` and the step fails.
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
        # Every step hands this role to SageMaker, so the role passes itself.
        # The condition limits the receiving service. A stolen credential
        # cannot pass the role to anything else.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[self.pipeline_role.role_arn],
                conditions={"StringEquals": {"iam:PassedToService": "sagemaker.amazonaws.com"}},
            )
        )
        # Job logs. SageMaker owns these two groups, not CDK. The container
        # agent calls `CreateLogGroup` on every job. The call returns
        # `ResourceAlreadyExistsException`, which succeeds only while the
        # permission exists.
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
