"""Serving: API Gateway -> proxy Lambda -> serverless endpoint, plus the
registry-approval -> endpoint-update automation."""

from typing import Any

from aws_cdk import ArnFormat, CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

from infra.stacks.lambda_code import src_code
from infra.stacks.shared import (
    MODEL_ARTIFACT_PREFIX,
    PlatformConfig,
    platform_lambda,
    sagemaker_event_rule,
    sagemaker_execution_role,
)


class ServingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifacts_bucket: s3.IBucket,
        package_group_name: str,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        code = src_code()

        # Role the endpoint's model container runs as. Phase 5B: no managed
        # policy, and every permission below is one the container demonstrably
        # uses at start-up. Updated in place, never replaced -- the deployed
        # `AWS::SageMaker::Model` pins this role's ARN.
        model_exec_role = sagemaker_execution_role(
            self,
            "ModelExecutionRole",
            least_privilege=True,
        )
        # Read the one thing the container downloads: the training step's
        # `model.tar.gz`. Replaces `grant_read_write`, which granted the write
        # and delete actions a hosted model never performs -- serverless
        # inference has no data capture, so nothing writes back.
        model_exec_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[
                    artifacts_bucket.arn_for_objects(f"{MODEL_ARTIFACT_PREFIX}/*"),
                ],
            )
        )
        model_exec_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[artifacts_bucket.bucket_arn],
            )
        )
        # Container start-up and inference logs. SageMaker owns this group, not
        # CDK, so unlike the Phase 5A Lambda roles this one does need
        # `CreateLogGroup` -- scoped to the single group it may create.
        endpoint_log_group_arn = self.format_arn(
            service="logs",
            resource="log-group",
            resource_name=f"/aws/sagemaker/Endpoints/{endpoint_name}",
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
        )
        model_exec_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=[endpoint_log_group_arn, f"{endpoint_log_group_arn}:*"],
            )
        )

        # Registry approval -> update/create the serverless endpoint.
        deploy_fn = platform_lambda(
            self,
            "DeployFn",
            config=config,
            handler="src.serving.deploy_handler.handler",
            code=code,
            timeout=Duration.minutes(5),
            environment={
                "ENDPOINT_NAME": endpoint_name,
                "EXECUTION_ROLE_ARN": model_exec_role.role_arn,
                "MEMORY_MB": str(config["serverless"]["memory_mb"]),
                "MAX_CONCURRENCY": str(config["serverless"]["max_concurrency"]),
            },
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateModel",
                    "sagemaker:CreateEndpointConfig",
                    "sagemaker:CreateEndpoint",
                    "sagemaker:UpdateEndpoint",
                    "sagemaker:DescribeEndpoint",
                    "sagemaker:DescribeModelPackage",
                ],
                resources=["*"],
            )
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["iam:PassRole"], resources=[model_exec_role.role_arn])
        )

        sagemaker_event_rule(
            self,
            "ModelApprovedRule",
            detail_type="SageMaker Model Package State Change",
            detail={
                "ModelPackageGroupName": [package_group_name],
                "ModelApprovalStatus": ["Approved"],
            },
            handler=deploy_fn,
        )

        # Public surface: API Gateway (API key) -> thin proxy Lambda.
        proxy_fn = platform_lambda(
            self,
            "ProxyFn",
            config=config,
            # Phase 5A: first role off the managed log policy.
            least_privilege_logs=True,
            handler="src.serving.proxy_handler.handler",
            code=code,
            timeout=Duration.seconds(29),
            memory_size=256,
            environment={"ENDPOINT_NAME": endpoint_name},
        )
        proxy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="endpoint",
                        resource_name=endpoint_name,
                    )
                ],
            )
        )

        api = apigw.RestApi(
            self,
            "ChurnApi",
            rest_api_name=f"churn-api-{config['env_name']}",
            deploy_options=apigw.StageOptions(stage_name=config["env_name"]),
        )
        predict = api.root.add_resource("predict")
        predict.add_method("POST", apigw.LambdaIntegration(proxy_fn), api_key_required=True)

        key = api.add_api_key("ClientKey")
        plan = api.add_usage_plan(
            "UsagePlan",
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=20),
        )
        plan.add_api_key(key)
        plan.add_api_stage(stage=api.deployment_stage)

        CfnOutput(self, "ApiUrl", value=api.url_for_path("/predict"))
        CfnOutput(self, "EndpointName", value=endpoint_name)
        # Id only — the key value is never a stack output. `make smoke` and
        # operators resolve it with `apigateway get-api-key --include-value`.
        CfnOutput(self, "ApiKeyId", value=key.key_id)
