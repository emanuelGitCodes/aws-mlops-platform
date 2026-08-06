"""The training stack's pipeline execution role.

Its own module rather than a few more cases in `test_registry_stack.py`, which
covered the training stack only because the two stacks were one line each:
Phase 5D gave this stack real policy logic -- nine statements naming every
bucket prefix, job ARN, model package group, and log group the pipeline
touches -- and that is worth the mirror the convention asks for.
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
    """Phase 5D: the last role off `AmazonSageMakerFullAccess`.

    That policy let the training pipeline read and write every SageMaker
    resource in the account -- endpoints, models, and model packages belonging
    to work this platform has nothing to do with.
    """
    role, _ = _role_and_policy(stacks)
    assert "ManagedPolicyArns" not in role["Properties"]
    assert role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Principal"] == {
        "Service": "sagemaker.amazonaws.com"
    }


def test_the_pipeline_role_names_every_resource_it_touches(stacks):
    """The action set is exactly what the 2026-08-06 CloudTrail baseline shows.

    Every action but `AddTags` was observed under this role during a full
    pipeline run, and the notable absences were observed *not* to be needed.
    No `ecr:` -- SageMaker pulls the first-party images with its own
    credentials. No `kms:` -- the role calls `GenerateDataKey` and `Decrypt`
    today while holding no KMS permission at all, because the AWS-managed
    `aws/s3` key policy authorizes it. No `s3:DeleteObject*`, which
    `grant_read_write` used to supply and no step performs. No
    `cloudwatch:PutMetricData`, which takes no ARN and would put the wildcard
    back.
    """
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
        # Not in the CloudTrail baseline, and it could not have been: Pipelines
        # tags each resource inside the create call, so the check never surfaces
        # as its own event. The first run under this policy failed on it.
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
    """`iam:PassRole` is the grant that would otherwise widen the whole phase.

    Every step hands this role to SageMaker when it creates its job, so the
    grant is unavoidable -- but unconditioned it would let a compromised
    credential hand the role to any service that accepts one.
    """
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
    """`InputDataUri` is a pipeline parameter, so this is a real narrowing.

    A crafted `StartPipelineExecution` can override the URI; scoping the
    curated-bucket read to `telco/` stops it walking the pipeline onto another
    prefix, the same shape of fix Phase 5C applied to the deploy Lambda's model
    package ARN.
    """
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
