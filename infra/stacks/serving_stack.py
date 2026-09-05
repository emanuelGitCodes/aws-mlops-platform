"""Define the inference API and model approval deployment."""

from typing import Any

from aws_cdk import ArnFormat, CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from constructs import Construct

from infra.stacks.lambda_code import src_code
from infra.stacks.shared import (
    CAPTURE_PREFIX,
    MODEL_ARTIFACT_PREFIX,
    PlatformConfig,
    handler_error_alarm,
    lambda_event_rule,
    platform_lambda,
    sagemaker_execution_role,
)

# SageMaker sends endpoint state events with uppercase underscore values.
ENDPOINT_EVENT_DETAIL_TYPE = "SageMaker Endpoint State Change"
ENDPOINT_FAILURE_STATES = ["FAILED", "ROLLING_BACK", "UPDATE_ROLLBACK_FAILED"]


class ServingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifacts_bucket: s3.IBucket,
        package_group_name: str,
        ops_topic: sns.ITopic,
        config: PlatformConfig,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        endpoint_name = config["endpoint_name"]
        code = src_code()

        # The model container uses this role at start-up.
        # The role has no managed policy. Update it in place.
        # The deployed `AWS::SageMaker::Model` pins its ARN.
        model_exec_role = sagemaker_execution_role(
            self,
            "ModelExecutionRole",
            least_privilege=True,
        )
        # Read the `model.tar.gz` object under the model artifact prefix.
        # Serverless inference does not write capture data from the container.
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
        # SageMaker creates this log group for start-up and inference logs.
        # Scope `CreateLogGroup` to this group. Lambda roles do not use it.
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

        # Both serving Lambdas use this endpoint ARN.
        endpoint_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint",
            resource_name=endpoint_name,
        )

        # Registry approval invokes the endpoint deployment function.
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
        # Scope each action to resources named by `deploy_handler`.
        # Generated model and endpoint-config names end with a package hash.
        #
        # The handler does not call `Delete*` or `List*` actions.
        # The `aws/lambda` key policy authorizes the cold-start decrypt.
        endpoint_config_arn = self.format_arn(
            service="sagemaker",
            resource="endpoint-config",
            resource_name=f"{endpoint_name}-config-*",
        )
        deploy_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateModel", "sagemaker:DescribeModel"],
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
                actions=["sagemaker:CreateEndpointConfig", "sagemaker:DescribeEndpointConfig"],
                resources=[endpoint_config_arn],
            )
        )
        # Create and update actions use the endpoint and endpoint-config resources.
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
        # EventBridge supplies the package ARN in the event detail.
        # Limit package reads to this platform model package group.
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

        # Notify operators when the configured endpoint enters a failed state.
        events.Rule(
            self,
            "EndpointFailureRule",
            rule_name=f"mlops-{config['env_name']}-ops-endpoint-failed",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=[ENDPOINT_EVENT_DETAIL_TYPE],
                resources=[endpoint_arn],
                detail={
                    "EndpointName": [endpoint_name],
                    "EndpointStatus": ENDPOINT_FAILURE_STATES,
                },
            ),
            targets=[
                targets.SnsTopic(
                    sns.Topic.from_topic_arn(self, "OpsTopicRef", ops_topic.topic_arn),
                    message=events.RuleTargetInput.from_text(
                        f"The {endpoint_name} SageMaker endpoint entered state "
                        + events.EventField.from_path("$.detail.EndpointStatus")
                    ),
                )
            ],
        )

        # API Gateway sends signed prediction requests to the proxy Lambda.
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
        # The proxy writes capture data for the serverless endpoint.
        # Grant `PutObject` only under the capture prefix.
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
            # The stage applies the route rate and burst limits.
            deploy_options=apigw.StageOptions(
                stage_name=config["env_name"],
                throttling_rate_limit=10,
                throttling_burst_limit=20,
            ),
        )
        predict = api.root.add_resource("predict")
        # Require SigV4 and `execute-api:Invoke` for this method.
        # API Gateway rejects unsigned calls before Lambda invocation.
        predict.add_method(
            "POST",
            apigw.LambdaIntegration(proxy_fn),
            authorization_type=apigw.AuthorizationType.IAM,
        )

        # The CI deploy role grants `execute-api:Invoke` on this route.
        # The route ARN contains the generated REST API id.
        self.predict_execute_api_arn = api.arn_for_execute_api(
            method="POST", path="/predict", stage=config["env_name"]
        )

        # `WebsiteStack` signs its proxied calls against this URL.
        self.predict_url = api.url_for_path("/predict")

        CfnOutput(self, "ApiUrl", value=self.predict_url)
        # A deploy handler that throws leaves the endpoint on the old model.
        handler_error_alarm(
            self, "DeployErrors", handler=deploy_fn, slug="deploy", config=config, topic=ops_topic
        )
        handler_error_alarm(
            self, "ProxyErrors", handler=proxy_fn, slug="proxy", config=config, topic=ops_topic
        )

        CfnOutput(self, "EndpointName", value=endpoint_name)
