"""The training stack's pipeline execution role.

The role carries nine policy statements, naming every bucket prefix, job ARN,
model package group, and log group the pipeline touches.
"""

from tests.unit.conftest import CONFIG


def _role_and_policy(stacks: dict) -> tuple[dict, dict]:
    resources = stacks["training"].to_json()["Resources"]
    role = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Role" and k.startswith("PipelineExecutionRole")
    )
    policy = next(
        v
        for k, v in resources.items()
        if v["Type"] == "AWS::IAM::Policy" and k.startswith("PipelineExecutionRoleDefaultPolicy")
    )
    return role, policy


def test_the_pipeline_role_carries_no_managed_policy(stacks):
    """Keep `AmazonSageMakerFullAccess` off the pipeline role."""
    role, _ = _role_and_policy(stacks)
    assert "ManagedPolicyArns" not in role["Properties"]
    assert role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "sagemaker.amazonaws.com"
    }


def test_the_pipeline_role_names_every_resource_it_touches(stacks):
    """Match the pipeline role actions to one full pipeline execution."""
    _, policy = _role_and_policy(stacks)
    statements = policy["Properties"]["PolicyDocument"]["Statement"]
    actions = {
        a
        for s in statements
        for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])
    }
    assert actions == {
        "s3:GetObject",
        "s3:PutObject",
        "s3:AbortMultipartUpload",
        "s3:ListBucket",
        "sagemaker:CreateProcessingJob",
        "sagemaker:DescribeProcessingJob",
        "sagemaker:CreateTrainingJob",
        "sagemaker:DescribeTrainingJob",
        "sagemaker:CreateModelPackage",
        "sagemaker:DescribeModelPackage",
        "sagemaker:CreateModelPackageGroup",
        # Pipelines adds tags inside each resource creation call.
        "sagemaker:AddTags",
        "iam:PassRole",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
    }
    for statement in statements:
        assert statement["Resource"] != "*"


def test_the_pipeline_role_may_only_pass_itself_to_sagemaker(stacks):
    """Limit `iam:PassRole` to this role and the SageMaker service."""
    _, policy = _role_and_policy(stacks)
    pass_role = next(
        s
        for s in policy["Properties"]["PolicyDocument"]["Statement"]
        if s["Action"] == "iam:PassRole"
    )
    assert pass_role["Condition"] == {
        "StringEquals": {"iam:PassedToService": "sagemaker.amazonaws.com"}
    }


def test_the_pipeline_role_reads_only_the_training_dataset(stacks):
    """Limit `InputDataUri` reads to the `telco/` prefix."""
    _, policy = _role_and_policy(stacks)
    curated_reads = [
        r
        for s in policy["Properties"]["PolicyDocument"]["Statement"]
        for r in (s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]])
        if "CuratedBucket" in str(r)
    ]
    assert all("telco/*" in str(r) or "/*" not in str(r) for r in curated_reads)


def test_the_pipeline_role_registers_only_into_this_platforms_group(stacks):
    """Model package writes are pinned to the environment's own group."""
    _, policy = _role_and_policy(stacks)
    package_resources = [
        r
        for s in policy["Properties"]["PolicyDocument"]["Statement"]
        for r in (s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]])
        if "model-package" in str(r)
    ]
    assert package_resources
    for resource in package_resources:
        assert CONFIG["model_package_group"] in str(resource)
