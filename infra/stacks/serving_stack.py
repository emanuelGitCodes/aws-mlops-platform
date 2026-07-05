"""Serving: API Gateway -> proxy Lambda -> serverless endpoint, plus the
registry-approval -> endpoint-update automation."""

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from infra.stacks.lambda_code import src_code


class ServingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifacts_bucket: s3.IBucket,
        package_group_name: str,
        config: dict,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        code = src_code()

        # Role the endpoint's model container runs as.
        model_exec_role = iam.Role(
            self,
            "ModelExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess")
            ],
        )
        artifacts_bucket.grant_read_write(model_exec_role)

        # Registry approval -> update/create the serverless endpoint.
        deploy_fn = lambda_.Function(
            self,
            "DeployFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.serving.deploy_handler.handler",
            code=code,
            timeout=Duration.minutes(5),
            environment={
                "ENDPOINT_NAME": endpoint_name,
                "EXECUTION_ROLE_ARN": model_exec_role.role_arn,
                "MEMORY_MB": str(config["serverless"]["memory_mb"]),
                "MAX_CONCURRENCY": str(config["serverless"]["max_concurrency"]),
                "CAPTURE_BUCKET": artifacts_bucket.bucket_name,
            },
            log_retention=logs.RetentionDays.TWO_WEEKS,
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

        events.Rule(
            self,
            "ModelApprovedRule",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=["SageMaker Model Package State Change"],
                detail={
                    "ModelPackageGroupName": [package_group_name],
                    "ModelApprovalStatus": ["Approved"],
                },
            ),
            targets=[targets.LambdaFunction(deploy_fn)],
        )

        # Public surface: API Gateway (API key) -> thin proxy Lambda.
        proxy_fn = lambda_.Function(
            self,
            "ProxyFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.serving.proxy_handler.handler",
            code=code,
            timeout=Duration.seconds(29),
            memory_size=256,
            environment={"ENDPOINT_NAME": endpoint_name},
            log_retention=logs.RetentionDays.TWO_WEEKS,
        )
        proxy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{endpoint_name}"
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
