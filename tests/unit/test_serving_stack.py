"""Serving stack: API authorization and proxy least privilege."""

from aws_cdk.assertions import Match

from infra.stacks.shared import MODEL_ARTIFACT_PREFIX
from tests.unit.conftest import CONFIG


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


def test_the_model_role_carries_no_managed_policy(stacks):
    """Phase 5B: the model container's role off `AmazonSageMakerFullAccess`.

    What replaces it is read-only and specific: the training prefix of the
    artifacts bucket, plus the endpoint's own log group. The write and delete
    actions `grant_read_write` used to add are the ones that matter -- a hosted
    serverless model has no data capture, so nothing it runs ever writes back to
    the bucket its own artifacts come from.
    """
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
    # The deployed AWS::SageMaker::Model pins this role's ARN, so a generated
    # name is what keeps an update from replacing the role out from under a
    # running endpoint.
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
    # The object grant reaches only the prefix the training step writes to.
    get_object = next(s for s in statements if s["Action"] == "s3:GetObject")
    assert get_object["Resource"]["Fn::Join"][1][-1] == f"/{MODEL_ARTIFACT_PREFIX}/*"


def test_the_proxy_role_carries_no_managed_policy(stacks):
    """Phase 5A: the proxy is the first role off `AWSLambdaBasicExecutionRole`.

    That managed policy grants the three log actions on `Resource: "*"` -- every
    log group in the account. The replacement grants writes to this function's
    own group and nothing else, so a compromised proxy cannot write into, or
    create, log groups belonging to the audit trail.
    """
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
    # Exactly the two log actions plus the one business permission. Notably no
    # logs:CreateLogGroup: CDK creates the group, so the function never needs it.
    assert actions == {"logs:CreateLogStream", "logs:PutLogEvents", "sagemaker:InvokeEndpoint"}
    for statement in statements:
        assert statement["Resource"] != "*"
