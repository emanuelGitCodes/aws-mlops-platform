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
    """Every accepted finding is attached to one real construct and a future phase."""
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
    """Plain rule ids stay namespaced; granular ids stay un-namespaced.

    aws-cdk-lib 2.261 matched a plain `AwsSolutions-S1` as readily as the
    namespaced form, so stripping the prefix looked redundant. 2.262 matches
    only the namespaced form, and an unmatched key is recorded without
    complaint -- so every plain acknowledgement lapsed at once, reopening 13
    findings with no error to point at. Pin both shapes against that silence.
    """
    plain, granular = [], []
    for acknowledgement in resolved_acknowledgements(CONFIG, "Test"):
        # Classify from the id itself, not from the derived key, so this does
        # not simply restate acknowledgement_metadata_key back to itself.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        key = acknowledgement_metadata_key(acknowledgement.finding_id)
        (granular if "::" in bare_id else plain).append(key)

    assert plain and granular, "both id shapes must stay exercised"
    assert all(key.startswith("AwsSolutions::AwsSolutions-") for key in plain), plain
    assert all(key.startswith("annotation::AwsSolutions-") for key in granular), granular


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_every_environment_builds_under_its_real_prefix(env_name):
    """Both environments must build under the stack prefix the app really uses.

    `prod` was unbuildable because an acknowledgement hardcoded dev's stage
    name, so the CI promotion path could never have reached a prod deploy.

    Scope: this covers `construct_path`, which `_construct_at` fails on
    loudly. It does NOT cover `finding_id` — cdk-nag reports unacknowledged
    findings through the CLI validation report, and in-process `app.synth()`
    returns cleanly even when five of them are wrong. `make synth-all` is the
    gate for those, which is why CI must synth both environments.
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
    """Phase 5 owns this role; Phase 1 rejects any new attachment.

    Phase 5B took the serving model role off the policy, leaving the pipeline
    role as the last holder until 5D.
    """
    roles = []
    for stack_name, template in stacks.items():
        for logical_id, resource in template.to_json().get("Resources", {}).items():
            if resource.get("Type") != "AWS::IAM::Role":
                continue
            policies = resource.get("Properties", {}).get("ManagedPolicyArns", [])
            if any("AmazonSageMakerFullAccess" in str(policy) for policy in policies):
                roles.append((stack_name, logical_id))

    assert roles == [("training", "PipelineExecutionRoleF9B1F2D0")]


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
        # The last literal `Resource: "*"` policy this repository writes. Phase
        # 3E's account-BPA actions are account-level, and AWS accepts only "*"
        # as their resource. Phase K removed three others (the CDK
        # log-retention provider's policy in ingestion, serving, and
        # monitoring), and Phase 5C removed the last real one -- the deploy
        # role's six-action SageMaker statement.
        ("security_monitoring", "AccountPublicAccessBlockCustomResourcePolicy3665E1EC"),
    ]


def test_iam_policy_baseline_has_not_changed(stacks):
    """Any role or policy change requires an explicit Phase 1 baseline review."""
    fingerprints = {}
    for stack_name, template in stacks.items():
        iam_resources = {
            logical_id: resource
            for logical_id, resource in template.to_json().get("Resources", {}).items()
            # ServiceLinkedRole joined the set in Phase 3C, which added the
            # first one: it is an IAM principal this repository creates, and it
            # slipped past a baseline whose docstring claims to cover any role.
            if resource.get("Type")
            in {"AWS::IAM::Policy", "AWS::IAM::Role", "AWS::IAM::ServiceLinkedRole"}
        }
        fingerprints[stack_name] = hashlib.sha256(
            json.dumps(iam_resources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert fingerprints == {
        "security": "9925908b0ff292a103399b71a26a17717dccd31daf542493a0723645d056dd24",
        # Phase 3E added the account-BPA custom resource provider role (basic
        # Lambda execution only) and its three-action policy. Phase 3C then
        # added the Config service-linked role -- AWS owns its policy, so this
        # repository cannot over-grant it -- and widened the fingerprint to
        # cover AWS::IAM::ServiceLinkedRole, which is what moved this hash.
        "security_monitoring": "9815f466b4c436c348c80a636d5099b644e77e52c2d0f5c8041df0f35d89a17a",
        "data": "2939699d4ec8219e7af89d0bc03ac579b55c02c28f638d251fe25296fd6b67c1",
        # Phase K rebaselined ingestion, serving, and monitoring. Reviewed
        # delta, template-diffed against the pre-change synthesis: each stack
        # loses exactly the CDK log-retention provider's role and its
        # `Resource: *` policy. No role was added or otherwise modified.
        "ingestion": "c8b076e8f8204d2bd8934a16fd3a5908676338b6e39b62181beb204ef3486f90",
        "registry": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        "training": "d5cc3390088645f797b05769e35bec78b3073ace00e81b8cfff2ecd42ad50b10",
        # Phase 5A, then 5B, then 5C rebaselined serving. Reviewed delta,
        # template-diffed against the pre-change synthesis: 5A replaced the
        # CDK-generated ProxyFn service role and its default policy one-for-one
        # with an explicit role carrying no managed policy. 5B then changed
        # exactly two resources and added or removed none --
        # `ModelExecutionRole` loses `ManagedPolicyArns`, and its default policy
        # trades the ten-action `grant_read_write` for `s3:GetObject` under one
        # prefix, `s3:ListBucket`, and the endpoint log group. No role was
        # added, removed, or renamed: the deployed `AWS::SageMaker::Model` pins
        # this role's ARN. 5C is 5A's shape again -- `DeployFnServiceRole*` and
        # its default policy out, `DeployFnRole*` and its default policy in,
        # one-for-one, with the function's `Role` and `DependsOn` re-pointed and
        # nothing else in the stack touched. The managed log policy is gone and
        # the six SageMaker actions moved off `Resource: "*"` onto five
        # resource-scoped statements. ProxyFn's policy is byte-identical:
        # hoisting the shared `endpoint_arn` changed no template output.
        "serving": "99e3a8909503bc789ce3b99ade5723efb41fa791b3025c1ef0fb611351c66de1",
        "monitoring": "cc859d169d0aea8460e12bc4adfb6131293ab5335b6eb0d092fd53a9260632b3",
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
