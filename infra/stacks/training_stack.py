"""SageMaker execution role for the training pipeline.

The pipeline definition itself lives in src/pipeline/pipeline.py and is
upserted with the SageMaker SDK (`make` target / CI step / retrain trigger),
because SageMaker Pipelines are versioned documents, not CloudFormation-native
resources. The stack owns the IAM the pipeline runs as.

Deliberately not granted by the Phase 5D policy below, each checked against
CloudTrail for this role over the 2026-08-06 pipeline run:

- **ECR.** `AmazonSageMakerFullAccess` did grant image pulls on `Resource: "*"`,
  so this is a real removal. The XGBoost and SKLearn images are first-party and
  live in AWS-owned registry accounts, which SageMaker pulls with its own
  credentials; Phase 5B proved the mechanism live when a cold container start
  succeeded under a model role holding no ECR rights.
- **KMS.** The role does call `GenerateDataKey` and `Decrypt` -- 39 times during
  that run -- and succeeds today while holding no `kms:` permission at all:
  `AmazonSageMakerFullAccess` grants only `DescribeKey` and `ListAliases`. The
  buckets use the AWS-managed `aws/s3` key, whose own key policy authorizes the
  call, so an IAM grant would add nothing.
- **`cloudwatch:PutMetricData`.** SageMaker publishes job metrics service-side,
  and the action takes no resource ARN, so granting it would reintroduce a
  `Resource: "*"` statement.
- **`s3:DeleteObject*`.** Supplied by `grant_read_write`; no step deletes.
- **`sagemaker:AddTags`** and the lineage calls (`CreateArtifact`,
  `AddAssociation`, `CreateTrialComponent`). CloudTrail attributes every one of
  those to `sagemaker.amazonaws.com` itself, not to this role.
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

        # Phase 5D: the last role off `AmazonSageMakerFullAccess`, which let the
        # training pipeline read and write every SageMaker resource in the
        # account. Updated in place, never replaced -- the deployed pipeline
        # definition and `scripts/setup_monitor.py` both pin this role's ARN.
        self.pipeline_role = sagemaker_execution_role(
            self,
            "PipelineExecutionRole",
            least_privilege=True,
        )

        # Read the one dataset the pipeline trains on. `InputDataUri` is a
        # pipeline parameter, so this is a real narrowing and not just tidier
        # IAM: a crafted `StartPipelineExecution` can override the URI, and
        # scoping the read to `telco/` stops it walking the pipeline onto
        # another bucket. `retrain_handler` starts the pipeline with default
        # parameters only, so nothing legitimate reads outside this prefix.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[curated_bucket.arn_for_objects("telco/*")],
            )
        )
        # Step I/O on the artifacts bucket, which is also the SDK's session
        # default bucket: code bundles and step outputs under the pipeline's own
        # name, the training step's `model.tar.gz` and debug output, the
        # evaluation reports, and Model Monitor's baseline and reports. Replaces
        # `grant_read_write`, whose ten generated actions covered the whole
        # bucket -- including the `s3:DeleteObject*` no pipeline step performs.
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

        # The jobs each step creates. SageMaker generates their names as
        # `pipelines-<execution-id>-<Step>-<suffix>`, so `pipelines-*` is the
        # tightest form a policy can express -- and it still excludes every job
        # in the account that this pipeline did not start.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateProcessingJob",
                    "sagemaker:DescribeProcessingJob",
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
                actions=["sagemaker:CreateTrainingJob", "sagemaker:DescribeTrainingJob"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="training-job",
                        resource_name="pipelines-*",
                    )
                ],
            )
        )
        # Registering the challenger. Pinned to this platform's own group for
        # the reason Phase 5C pinned the deploy role's `DescribeModelPackage`:
        # it stops the pipeline writing lineage into a foreign group.
        # `CreateModelPackageGroup` is on the list because the SDK calls it
        # unconditionally before registering and today gets back
        # `ValidationException` (the group exists); without the grant that same
        # call becomes `AccessDenied` and fails the step instead.
        package_group_name = config["model_package_group"]
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateModelPackage", "sagemaker:DescribeModelPackage"],
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
                actions=["sagemaker:CreateModelPackageGroup"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package-group",
                        resource_name=package_group_name,
                    )
                ],
            )
        )
        # Every step hands this same role to SageMaker when it creates its job,
        # so the role passes itself. Conditioned on the service that may receive
        # it, so a compromised credential cannot hand the role to anything else.
        self.pipeline_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[self.pipeline_role.role_arn],
                conditions={"StringEquals": {"iam:PassedToService": "sagemaker.amazonaws.com"}},
            )
        )
        # Job logs. SageMaker owns these two groups, not CDK, and the container
        # agent calls `CreateLogGroup` on every job -- it currently comes back
        # `ResourceAlreadyExistsException`, which is a success path only while
        # the permission exists. Scoped to the two groups SageMaker names.
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
