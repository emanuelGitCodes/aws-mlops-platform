"""Test the cdk-nag acknowledgements and IAM baselines."""

import hashlib
import json
import re
from unittest import mock

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match
from cdk_nag import AwsSolutionsChecks

from infra.app import build_app, load_config, stack_prefix
from infra.security_checks import acknowledgement_metadata_key, resolved_acknowledgements
from tests.unit.conftest import CONFIG, synth_env


def test_acknowledgements_match_live_cdk_nag_findings():
    """Require each active acknowledgement to match a live cdk-nag finding."""
    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    with mock.patch("infra.app.apply_security_checks"):
        stacks = build_app(app, CONFIG, "Test")

    app.synth()
    report = AwsSolutionsChecks(app, verbose=False).validate_scope(app)

    def canonical_finding_id(finding_id: str) -> str:
        finding_id = finding_id.removeprefix("AwsSolutions::")
        return re.sub(
            r"Test-Data:ExportsOutputFnGetAtt([A-Za-z0-9]+)Arn[A-F0-9]+",
            r"<\1.Arn>",
            finding_id,
        )

    live_pairs = {
        (resource.construct_path, canonical_finding_id(violation.rule_name))
        for violation in report.violations
        for resource in violation.violating_resources
    }
    service_flags = CONFIG["security"]["services"]
    enabled_flags = {name for name, enabled in service_flags.items() if enabled}
    if CONFIG["security"]["account_budget"]:
        enabled_flags.add("account_budget")
    if CONFIG["website"]["enabled"]:
        enabled_flags.add("website")

    expected_pairs = set()
    for acknowledgement in resolved_acknowledgements(CONFIG, "Test"):
        if acknowledgement.requires_flag and acknowledgement.requires_flag not in enabled_flags:
            continue
        stack = stacks[acknowledgement.stack]
        expected_path = f"{stack.node.path}/{acknowledgement.construct_path}"
        matches = [node for node in stack.node.find_all() if node.node.path == expected_path]
        assert len(matches) == 1, expected_path
        target = matches[0].node.default_child or matches[0]
        pair = target.node.path, canonical_finding_id(acknowledgement.finding_id)
        expected_pairs.add(pair)

    missing_pairs = sorted(expected_pairs - live_pairs)
    assert not missing_pairs, missing_pairs


def test_security_acknowledgements_are_exact_and_expiring(stack_constructs):
    """Bind each acknowledgement to one construct and removal condition."""
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
    """Keep namespaces on plain ids and remove them from granular ids."""
    plain, granular = [], []
    for acknowledgement in resolved_acknowledgements(CONFIG, "Test"):
        # Classify each acknowledgement from its finding id.
        bare_id = acknowledgement.finding_id.removeprefix("AwsSolutions::")
        key = acknowledgement_metadata_key(acknowledgement.finding_id)
        (granular if "::" in bare_id else plain).append(key)

    assert plain and granular, "both id shapes must stay exercised"
    assert all(key.startswith("AwsSolutions::AwsSolutions-") for key in plain), plain
    assert all(key.startswith("annotation::AwsSolutions-") for key in granular), granular


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_every_environment_builds_under_its_real_prefix(env_name):
    """Build each environment with the prefix from `stack_prefix`."""
    synth_env(env_name, stack_prefix(env_name))


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_acknowledgements_leave_no_unresolved_tokens(env_name):
    """Require all acknowledgement tokens to resolve."""
    config = load_config(env_name)
    for acknowledgement in resolved_acknowledgements(config, stack_prefix(env_name)):
        assert "{" not in acknowledgement.construct_path, acknowledgement
        assert "{" not in acknowledgement.finding_id, acknowledgement


def test_broad_sagemaker_managed_policy_baseline_has_not_grown(stacks):
    """Keep `AmazonSageMakerFullAccess` off every role."""
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
        # AWS requires `Resource: "*"` for the account-level BPA actions.
        ("security_monitoring", "AccountPublicAccessBlockCustomResourcePolicy3665E1EC"),
        # AWS requires `Resource: "*"` for `ecr:GetAuthorizationToken`.
        ("website", "WebsiteInstanceRoleDefaultPolicy1C852E27"),
    ]


def test_iam_policy_baseline_has_not_changed(stacks):
    """Any role or policy change requires an explicit baseline review."""
    fingerprints = {}
    for stack_name, template in stacks.items():
        iam_resources = {
            logical_id: resource
            for logical_id, resource in template.to_json().get("Resources", {}).items()
            # Include every repository-managed IAM principal.
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
        "ingestion": "564dd6a14d4daa9e28c43c51b408dd33813e11bcdbaa6b51732bae3dc1dda4b2",
        "registry": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        # Keep the pipeline role logical id unchanged.
        "training": "69aa221901f5836abed23335c0cad335c49182053310f72e3a64a28f5b92c4f5",
        # Keep the model role logical id unchanged.
        "serving": "fcb7f599b4b0fff119999d1897761dc1088d1b8268761bc19a5c9c4ef048a2d9",
        # Track both monitoring Lambda roles.
        "monitoring": "4b38f1c4825eddf344b48b8ca962af2847c8fe53d4f08162e53d459d6619c459",
        # Track the deploy role permissions and OIDC trust conditions.
        "cicd": "7a803ee795eea06da566236a0a25ed949c54dcd570d3cb33b8ebcea10ef4b81d",
        # Track the website instance role and its scoped grants.
        "website": "1db80084caba5194ff5d989cb90f29e3882c105565ffc23dd23c802c03b72914",
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
