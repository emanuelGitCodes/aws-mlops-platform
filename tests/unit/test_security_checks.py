"""The cdk-nag gate: acknowledgements and the IAM debt baselines."""

import hashlib
import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match

from infra.app import load_config, stack_prefix
from infra.security_checks import acknowledgement_metadata_key, resolved_acknowledgements
from tests.unit.conftest import CONFIG, synth_env


def test_security_acknowledgements_are_exact_and_expiring(stack_constructs):
    """Every accepted finding binds to one real construct and names the phase
    that removes it."""
    acknowledgements = resolved_acknowledgements(CONFIG, "Test")
    assert acknowledgements
    for acknowledgement in acknowledgements:
        stack = stack_constructs[acknowledgement.stack]
        expected_path = f"{stack.node.path}/{acknowledgement.construct_path}"
        matches = [node for node in stack.node.find_all() if node.node.path == expected_path]
        assert len(matches) == 1, expected_path
        assert "Phase " in acknowledgement.reason
        target = matches[0].node.default_child or matches[0]
        metadata_key = acknowledgement_metadata_key(acknowledgement.finding_id)
        assert any(
            entry.type == cdk.Validations.ACKNOWLEDGED_RULES_METADATA_KEY
            and entry.data.get(metadata_key) == acknowledgement.reason
            for entry in target.node.metadata
        ), metadata_key


def test_acknowledgement_keys_keep_the_namespace_cdk_matches_on():
    """Plain rule ids keep the namespace. Granular ids drop it.

    aws-cdk-lib 2.262 matches only the namespaced form, and it records an
    unmatched key without complaint. A bare id lapses every plain
    acknowledgement and reopens 13 findings, with no error.
    """
    plain, granular = [], []
    for acknowledgement in resolved_acknowledgements(CONFIG, "Test"):
        # Classify from the id, not from the derived key. Otherwise this test
        # only restates acknowledgement_metadata_key back to itself.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        key = acknowledgement_metadata_key(acknowledgement.finding_id)
        (granular if "::" in bare_id else plain).append(key)

    assert plain and granular, "both id shapes must stay exercised"
    assert all(key.startswith("AwsSolutions::AwsSolutions-") for key in plain), plain
    assert all(key.startswith("annotation::AwsSolutions-") for key in granular), granular


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_every_environment_builds_under_its_real_prefix(env_name):
    """Both environments must build under the prefix the app uses.

    An acknowledgement that hardcodes one stage name makes the other
    environment unbuildable and blocks the CI promotion path.

    This test covers `construct_path`, which `_construct_at` fails on loudly.
    It does not cover `finding_id`. cdk-nag reports unacknowledged findings
    through the CLI validation report, and an in-process `app.synth()` returns
    cleanly even when five of them are wrong. `make synth-all` is the gate for
    those, and CI synthesizes both environments.
    """
    synth_env(env_name, stack_prefix(env_name))


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_acknowledgements_leave_no_unresolved_tokens(env_name):
    """A mistyped token would silently stop matching instead of failing loudly."""
    config = load_config(env_name)
    for acknowledgement in resolved_acknowledgements(config, stack_prefix(env_name)):
        assert "{" not in acknowledgement.construct_path, acknowledgement
        assert "{" not in acknowledgement.finding_id, acknowledgement


def test_broad_sagemaker_managed_policy_baseline_has_not_grown(stacks):
    """No role carries this policy, and the list must stay empty.

    A role that needs one more permission takes an explicit statement, never
    this managed policy.
    """
    roles = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Role":
                continue
            policies = resource.get("Properties", {}).get("ManagedPolicyArns", [])
            if any("AmazonSageMakerFullAccess" in str(policy) for policy in policies):
                roles.append((stack_name, logical_id))

    assert roles == []


def test_literal_wildcard_resource_baseline_has_not_grown(stacks):
    """Reject any new `Resource: "*"` statement."""
    wildcard_policies = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Policy":
                continue
            statements = resource["Properties"]["PolicyDocument"]["Statement"]
            if any(statement.get("Resource") == "*" for statement in statements):
                wildcard_policies.append((stack_name, logical_id))

    assert wildcard_policies == [
        # The only literal `Resource: "*"` policy this repository writes. The
        # account-BPA actions are account-level, and AWS accepts only "*" as
        # their resource.
        ("security_monitoring", "AccountPublicAccessBlockCustomResourcePolicy3665E1EC"),
    ]


def test_iam_policy_baseline_has_not_changed(stacks):
    """Any role or policy change requires an explicit baseline review."""
    fingerprints = {}
    for stack_name, template in stacks.items():
        iam_resources = {
            logical_id: resource
            for logical_id, resource in template.to_json().get("Resources", {}).items()
            # ServiceLinkedRole belongs here. It is an IAM principal this
            # repository creates, so the baseline must cover it.
            if resource.get("Type")
            in {"AWS::IAM::Policy", "AWS::IAM::Role", "AWS::IAM::ServiceLinkedRole"}
        }
        fingerprints[stack_name] = hashlib.sha256(
            json.dumps(iam_resources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert fingerprints == {
        "security": "9925908b0ff292a103399b71a26a17717dccd31daf542493a0723645d056dd24",
        "security_monitoring": "9815f466b4c436c348c80a636d5099b644e77e52c2d0f5c8041df0f35d89a17a",
        "data": "2939699d4ec8219e7af89d0bc03ac579b55c02c28f638d251fe25296fd6b67c1",
        "ingestion": "c8b076e8f8204d2bd8934a16fd3a5908676338b6e39b62181beb204ef3486f90",
        "registry": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        # Keep the training logical IDs unchanged. The deployed pipeline
        # definition pins `PipelineExecutionRole`'s ARN, so a replacement
        # strands it.
        "training": "38c16b61765d1ad0a1f8dede12c2af664eb508af0cdcc5fd97e38780154a4574",
        # Keep `ModelExecutionRole` unchanged. The deployed
        # `AWS::SageMaker::Model` pins its ARN, so a replacement strands the
        # endpoint at its next cold start.
        "serving": "df36151514116565e7ad6d73e8185b530945a329fa1c3454273da7d0bbc04eb3",
        # `DriftEvaluationFnRole` is new and carries no managed policy.
        # `RetrainTriggerFnServiceRole` keeps its logical ID.
        "monitoring": "3444854868fba5e089e04e4e55706b51c947cf883cc435e5a759831869a5b243",
        # `GitHubDeployRole` is the only role in this repository a principal
        # outside the account can assume. Review its trust conditions, not only
        # its permissions: the `sub` claim is what limits the federation to one
        # GitHub environment.
        "cicd": "be2d2b8e312922d7d95d8dbaad98188374376f098b90fe8fb396df7c8fdc9d4e",
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
