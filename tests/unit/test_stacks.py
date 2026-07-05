"""CDK assertion tests: synth each stack and verify the security-critical wiring.

Asset bundling is stubbed via the `aws:cdk:bundling-stacks` context so tests
don't need pip/Docker.
"""

import pathlib

import aws_cdk as cdk
import pytest
import yaml
from aws_cdk.assertions import Match, Template

from infra.stacks.data_stack import DataStack
from infra.stacks.ingestion_stack import IngestionStack
from infra.stacks.monitoring_stack import MonitoringStack
from infra.stacks.registry_stack import RegistryStack
from infra.stacks.serving_stack import ServingStack
from infra.stacks.training_stack import TrainingStack

CONFIG = yaml.safe_load(
    (pathlib.Path(__file__).parents[2] / "infra" / "config" / "dev.yaml").read_text()
)


@pytest.fixture(scope="module")
def stacks() -> dict:
    """All stacks built once; the construct tree can't change after first synth."""
    app = cdk.App(context={"aws:cdk:bundling-stacks": []})
    data = DataStack(app, "TestData", config=CONFIG)
    ingestion = IngestionStack(
        app,
        "TestIngestion",
        raw_bucket=data.raw_bucket,
        curated_bucket=data.curated_bucket,
        config=CONFIG,
    )
    registry = RegistryStack(app, "TestRegistry", config=CONFIG)
    training = TrainingStack(
        app,
        "TestTraining",
        curated_bucket=data.curated_bucket,
        artifacts_bucket=data.artifacts_bucket,
        config=CONFIG,
    )
    serving = ServingStack(
        app,
        "TestServing",
        artifacts_bucket=data.artifacts_bucket,
        package_group_name=registry.package_group_name,
        config=CONFIG,
    )
    monitoring = MonitoringStack(app, "TestMonitoring", config=CONFIG)
    return {
        name: Template.from_stack(stack)
        for name, stack in {
            "data": data,
            "ingestion": ingestion,
            "registry": registry,
            "training": training,
            "serving": serving,
            "monitoring": monitoring,
        }.items()
    }


def test_buckets_are_locked_down(stacks):
    template = stacks["data"]
    template.resource_count_is("AWS::S3::Bucket", 3)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {"BlockPublicAcls": True, "RestrictPublicBuckets": True}
            ),
            "BucketEncryption": Match.any_value(),
            "VersioningConfiguration": {"Status": "Enabled"},
        },
    )
    # TLS-only: every bucket policy denies insecure transport
    template.all_resources_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": Match.object_like({"BudgetLimit": {"Amount": CONFIG["budget_usd"]}})},
    )


def test_ingestion_wiring(stacks):
    template = stacks["ingestion"]
    # queue + DLQ, with redrive between them
    template.resource_count_is("AWS::SQS::Queue", 2)
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {"RedrivePolicy": Match.object_like({"maxReceiveCount": 3})},
    )
    template.has_resource_properties(
        "AWS::Events::Rule",
        {"EventPattern": Match.object_like({"source": ["aws.s3"]})},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.ingestion.validate_handler.handler",
            "Runtime": "python3.12",
            "Environment": {"Variables": Match.object_like({"CURATED_BUCKET": Match.any_value()})},
        },
    )


def test_serving_endpoint_auth_and_least_privilege(stacks):
    template = stacks["serving"]

    # the public method requires an API key
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"HttpMethod": "POST", "ApiKeyRequired": True},
    )
    # proxy role can only invoke the one endpoint
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sagemaker:InvokeEndpoint",
                                    # arn is an Fn::Join over region/account tokens
                                    "Resource": {
                                        "Fn::Join": Match.array_with(
                                            [
                                                Match.array_with(
                                                    [
                                                        Match.string_like_regexp(
                                                            f".*endpoint/{CONFIG['endpoint_name']}"
                                                        )
                                                    ]
                                                )
                                            ]
                                        )
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
    # approval events from our package group trigger the deploy Lambda
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {
                    "detail": Match.object_like(
                        {"ModelPackageGroupName": [CONFIG["model_package_group"]]}
                    )
                }
            )
        },
    )


def test_monitoring_drift_loop_wiring(stacks):
    template = stacks["monitoring"]

    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": Match.object_like(
                {
                    "detail": Match.object_like(
                        {"MonitoringExecutionStatus": ["CompletedWithViolations"]}
                    )
                }
            )
        },
    )
    # retrain Lambda may only start the one pipeline
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "sagemaker:StartPipelineExecution",
                                    # arn is an Fn::Join over region/account tokens
                                    "Resource": {
                                        "Fn::Join": Match.array_with(
                                            [
                                                Match.array_with(
                                                    [
                                                        Match.string_like_regexp(
                                                            f".*pipeline/{CONFIG['pipeline_name']}"
                                                        )
                                                    ]
                                                )
                                            ]
                                        )
                                    },
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 1)


def test_registry_and_training(stacks):
    stacks["registry"].has_resource_properties(
        "AWS::SageMaker::ModelPackageGroup",
        {"ModelPackageGroupName": CONFIG["model_package_group"]},
    )

    stacks["training"].has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": Match.object_like(
                {
                    "Statement": Match.array_with(
                        [Match.object_like({"Principal": {"Service": "sagemaker.amazonaws.com"}})]
                    )
                }
            )
        },
    )
