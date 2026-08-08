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
    CAPTURE_PREFIX,
    MODEL_ARTIFACT_PREFIX,
    PlatformConfig,
    lambda_event_rule,
    platform_lambda,
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

        # Role the model container runs as. It carries no managed policy. The
        # container uses every permission below at start-up. Update this role
        # in place. The deployed `AWS::SageMaker::Model` pins its ARN.
        model_exec_role = sagemaker_execution_role(
            self,
            "ModelExecutionRole",
            least_privilege=True,
        )
        # Read the one object the container downloads: `model.tar.gz`.
        # Serverless inference has no data capture, so the container never
        # writes back.
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
        # CDK, so this role needs `CreateLogGroup`, scoped to the single
        # group it may create. The Lambda roles do not need it.
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

        # The one endpoint this stack owns, named by both Lambdas below.
        endpoint_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint",
            resource_name=endpoint_name,
        )

        # Registry approval -> update/create the serverless endpoint.
        deploy_fn = platform_lambda(
            self,
            "DeployFn",
            config=config,
            least_privilege_logs=True,
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
        # Each action is scoped to the resources `deploy_handler` names. The
        # two trailing wildcards are unavoidable, because the handler suffixes
        # each model and endpoint-config name with the epoch second.
        #
        # Omitted: `Delete*`, because the handler never removes a superseded
        # revision. `List*`. And `kms:Decrypt`, because the `aws/lambda` key
        # policy already authorizes the cold-start decrypt.
        endpoint_config_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint-config",
            resource_name=f"{endpoint_name}-config-*",
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateModel"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model",
                        resource_name=f"{endpoint_name}-model-*",
                    )
                ],
            )
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateEndpointConfig"],
                resources=[endpoint_config_arn],
            )
        )
        # Create and Update take the endpoint and the config it points at, so
        # this statement needs both resource types.
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateEndpoint", "sagemaker:UpdateEndpoint"],
                resources=[endpoint_arn, endpoint_config_arn],
            )
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeEndpoint"],
                resources=[endpoint_arn],
            )
        )
        # The package ARN arrives in the EventBridge detail. Pin it to this
        # platform's own group, so a crafted event cannot point the Lambda at a
        # foreign model package.
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:DescribeModelPackage"],
                resources=[
                    self.format_arn(
                        service="sagemaker",
                        resource="model-package",
                        resource_name=f"{package_group_name}/*",
                    )
                ],
            )
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["iam:PassRole"], resources=[model_exec_role.role_arn])
        )

        lambda_event_rule(
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
            least_privilege_logs=True,
            handler="src.serving.proxy_handler.handler",
            code=code,
            timeout=Duration.seconds(29),
            memory_size=256,
            environment={
                "ENDPOINT_NAME": endpoint_name,
                "CAPTURE_BUCKET": artifacts_bucket.bucket_name,
                "CAPTURE_PREFIX": CAPTURE_PREFIX,
            },
        )
        proxy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=[endpoint_arn],
            )
        )
        # A serverless endpoint has no data capture, so the proxy is the
        # capture point. Write only, and only under the capture prefix: this
        # role must not be able to read the model artifact it serves, or to
        # replace a captured record once written.
        proxy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[artifacts_bucket.arn_for_objects(f"{CAPTURE_PREFIX}/*")],
            )
        )

        api = apigw.RestApi(
            self,
            "ChurnApi",
            rest_api_name=f"churn-api-{config['env_name']}",
            # The rate and burst limits were attached to the usage plan that
            # carried the API key. The key is gone, so they belong to the stage.
            # Without this the API keeps only the account-wide default.
            deploy_options=apigw.StageOptions(
                stage_name=config["env_name"],
                throttling_rate_limit=10,
                throttling_burst_limit=20,
            ),
        )
        predict = api.root.add_resource("predict")
        # The caller signs with SigV4 and needs `execute-api:Invoke` on this
        # method. An unsigned call fails at API Gateway and never reaches the
        # proxy Lambda.
        predict.add_method(
            "POST",
            apigw.LambdaIntegration(proxy_fn),
            authorization_type=apigw.AuthorizationType.IAM,
        )

        CfnOutput(self, "ApiUrl", value=api.url_for_path("/predict"))
        CfnOutput(self, "EndpointName", value=endpoint_name)
