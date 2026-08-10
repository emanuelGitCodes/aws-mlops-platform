"""Serving stack: API authorization and proxy least privilege."""

from aws_cdk.assertions import Match

from infra.stacks.shared import MODEL_ARTIFACT_PREFIX
from tests.unit.conftest import CONFIG


def test_serving_endpoint_auth_and_least_privilege(stacks):
    template = stacks["serving"]

    # The public method requires a SigV4 signature.
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"HttpMethod": "POST", "AuthorizationType": "AWS_IAM"},
    )
    # The API has no key and no usage plan. The stage carries the rate limit.
    template.resource_count_is("AWS::ApiGateway::ApiKey", 0)
    template.resource_count_is("AWS::ApiGateway::UsagePlan", 0)
    template.has_resource_properties(
        "AWS::ApiGateway::Stage",
        {
            "MethodSettings": Match.array_with(
                [
                    Match.object_like({"ThrottlingRateLimit": 10, "ThrottlingBurstLimit": 20}),
                ]
            )
        },
    )
    # The proxy role may invoke only the one endpoint.
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
                                    # The ARN is an Fn::Join over tokens.
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
    # An approval event from this package group triggers the deploy Lambda.
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


def test_the_model_role_carries_no_managed_policy(stacks):
    """Limit the model role to artifact reads and endpoint logging."""
    resources = stacks["serving"].to_json()["Resources"]
    role = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Role" and k.startswith("ModelExecutionRole")
    )
    assert "ManagedPolicyArns" not in role["Properties"]
    assert role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "sagemaker.amazonaws.com"
    }
    # The deployed AWS::SageMaker::Model pins this role's ARN. A generated
    # name stops an update from replacing the role under a running endpoint.
    assert "RoleName" not in role["Properties"]

    policy = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Policy" and k.startswith("ModelExecutionRoleDefaultPolicy")
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    actions = {
        a
        for s in statements
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }
    assert actions == {
        "s3:GetObject",
        "s3:ListBucket",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
    }
    for statement in statements:
        assert statement["Resource"] != "*"
    # Limit object reads to the model artifact prefix.
    get_object = next(s for s in statements if s["Action"] == "s3:GetObject")
    assert get_object["Resource"]["Fn::Join"][1][-1] == f"/{MODEL_ARTIFACT_PREFIX}/*"


def test_the_deploy_role_names_every_resource_it_touches(stacks):
    """Limit the deploy role to resources named by `deploy_handler`."""
    resources = stacks["serving"].to_json()["Resources"]
    role = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Role" and k.startswith("DeployFnRole")
    )
    assert "ManagedPolicyArns" not in role["Properties"]
    assert role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "lambda.amazonaws.com"
    }

    policy = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Policy" and k.startswith("DeployFnRoleDefaultPolicy")
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    actions = {
        a
        for s in statements
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }
    # Match the deploy handler and explicit log-group actions.
    assert actions == {
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "sagemaker:CreateModel",
        "sagemaker:CreateEndpointConfig",
        "sagemaker:CreateEndpoint",
        "sagemaker:UpdateEndpoint",
        "sagemaker:DescribeEndpoint",
        "sagemaker:DescribeModelPackage",
        "iam:PassRole",
    }
    for statement in statements:
        assert statement["Resource"] != "*"

    # Limit package reads to this platform model package group.
    describe = next(s for s in statements if s["Action"] == "sagemaker:DescribeModelPackage")
    assert (
        describe["Resource"]["Fn::Join"][1][-1]
        == f":model-package/{CONFIG['model_package_group']}/*"
    )


def test_the_proxy_role_carries_no_managed_policy(stacks):
    """Keep `AWSLambdaBasicExecutionRole` off the proxy role."""
    resources = stacks["serving"].to_json()["Resources"]
    role_id, role = next(
        (k, v)
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Role" and k.startswith("ProxyFnRole")
    )
    assert "ManagedPolicyArns" not in role["Properties"]
    assert role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "lambda.amazonaws.com"
    }

    policy = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Policy" and k.startswith("ProxyFnRoleDefaultPolicy")
    )
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    actions = {
        a
        for s in statements
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }
    # Match the proxy handler and explicit log-group actions.
    assert actions == {
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "sagemaker:InvokeEndpoint",
        "s3:PutObject",
    }
    for statement in statements:
        assert statement["Resource"] != "*"


def test_the_proxy_may_write_capture_and_read_nothing(stacks):
    """Grant capture writes without bucket reads."""
    template = stacks["serving"]
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "src.serving.proxy_handler.handler",
            "Environment": {"Variables": Match.object_like({"CAPTURE_PREFIX": "capture"})},
        },
    )

    proxy_policy = next(
        policy
        for policy in template.find_resources("AWS::IAM::Policy").values()
        if any(
            statement["Action"] == "sagemaker:InvokeEndpoint"
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        )
    )
    actions = [s["Action"] for s in proxy_policy["Properties"]["PolicyDocument"]["Statement"]]
    flat = [a for entry in actions for a in ([entry] if isinstance(entry, str) else entry)]
    assert "s3:PutObject" in flat
    assert not [a for a in flat if a.startswith("s3:Get") or a.startswith("s3:Delete")]
