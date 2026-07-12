"""CDK assertion tests: synth each stack and verify the security-critical wiring.

Asset bundling is stubbed via the `aws:cdk:bundling-stacks` context so tests
don't need pip/Docker.
"""

import hashlib
import json
import pathlib

import aws_cdk as cdk
import pytest
import yaml
from aws_cdk.assertions import Match, Template

from infra.security_checks import ACKNOWLEDGEMENTS, apply_security_checks
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
def stack_constructs() -> dict:
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
    stacks = {
        "data": data,
        "ingestion": ingestion,
        "registry": registry,
        "training": training,
        "serving": serving,
        "monitoring": monitoring,
    }
    apply_security_checks(app, stacks)
    app.synth()
    return stacks


@pytest.fixture(scope="module")
def stacks(stack_constructs) -> dict:
    return {name: Template.from_stack(stack) for name, stack in stack_constructs.items()}


def test_buckets_are_locked_down(stacks):
    template = stacks["data"]
    template.resource_count_is("AWS::S3::Bucket", 3)
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                }
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


def test_security_acknowledgements_are_exact_and_expiring(stack_constructs):
    """Every accepted finding is attached to one real construct and a future phase."""
    assert ACKNOWLEDGEMENTS
    for acknowledgement in ACKNOWLEDGEMENTS:
        stack = stack_constructs[acknowledgement.stack]
        expected_path = f"{stack.node.path}/{acknowledgement.construct_path}"
        matches = [node for node in stack.node.find_all() if node.node.path == expected_path]
        assert len(matches) == 1, expected_path
        assert "Phase " in acknowledgement.reason
        target = matches[0].node.default_child or matches[0]
        finding_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        metadata_key = f"annotation::{finding_id}"
        assert any(
            entry.type == cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY
            and entry.data.get(metadata_key) == acknowledgement.reason
            for entry in target.node.metadata
        ), metadata_key


def test_broad_sagemaker_managed_policy_baseline_has_not_grown(stacks):
    """Phase 5 owns these two known roles; Phase 1 rejects a third attachment."""
    roles = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Role":
                continue
            policies = resource.get("Properties", {}).get("ManagedPolicyArns", [])
            if any("AmazonSageMakerFullAccess" in str(policy) for policy in policies):
                roles.append((stack_name, logical_id))

    assert roles == [
        ("training", "PipelineExecutionRoleF9B1F2D0"),
        ("serving", "ModelExecutionRole3247A550"),
    ]


def test_literal_wildcard_resource_baseline_has_not_grown(stacks):
    """Reject new Resource '*' statements while known generated debt awaits Phases 5 and 7."""
    wildcard_policies = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Policy":
                continue
            statements = resource["Properties"]["PolicyDocument"]["Statement"]
            if any(statement.get("Resource") == "*" for statement in statements):
                wildcard_policies.append((stack_name, logical_id))

    assert wildcard_policies == [
        (
            "ingestion",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
        ("serving", "DeployFnServiceRoleDefaultPolicy7D43372B"),
        (
            "serving",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
        (
            "monitoring",
            "LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8aServiceRoleDefaultPolicyADDA7DEB",
        ),
    ]


def test_iam_policy_baseline_has_not_changed(stacks):
    """Any role or policy change requires an explicit Phase 1 baseline review."""
    fingerprints = {}
    for stack_name, template in stacks.items():
        iam_resources = {
            logical_id: resource
            for logical_id, resource in template.to_json().get("Resources", {}).items()
            if resource.get("Type") in {"AWS::IAM::Policy", "AWS::IAM::Role"}
        }
        fingerprints[stack_name] = hashlib.sha256(
            json.dumps(iam_resources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert fingerprints == {
        "data": "defc965af9288dbbb5f4d03319208bdff311cfd5b5cdaf3215308525464f9b35",
        "ingestion": "6af42bd809ed5eaa65a19802ba43e8f0a49ece99ca0677631106d7ad6ac515b1",
        "registry": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "training": "50fdc90cdba074ca7631fae914e3db8aca36aaa4769202c46f9900ae0f4f208e",
        "serving": "328918c0afed63f269823e274edac9b0d200b58154624f6b127fc1386b485952",
        "monitoring": "df4b29739738a1c9144ad38b844336ea4b9729340e1a6f01955efc337e675fc6",
    }

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
