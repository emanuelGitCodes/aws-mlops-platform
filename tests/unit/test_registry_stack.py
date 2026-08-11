"""Registry and training stacks, and the model package group per environment."""

import json

from aws_cdk.assertions import Template

from infra.app import stack_prefix
from tests.unit.conftest import CONFIG, synth_env


def test_registry_and_training(stacks):
    stacks["registry"].has_resource_properties(
        "AWS::SageMaker::ModelPackageGroup",
        {"ModelPackageGroupName": CONFIG["model_package_group"]},
    )


def _registry_group_name(stacks: dict) -> str:
    """The physical model package group name one environment synthesizes."""
    resources = Template.from_stack(stacks["registry"]).find_resources(
        "AWS::SageMaker::ModelPackageGroup"
    )
    assert len(resources) == 1
    name: str = next(iter(resources.values()))["Properties"]["ModelPackageGroupName"]
    return name


def _approval_rule_patterns(stacks: dict) -> list[dict]:
    """Every registry-approval EventBridge pattern in one environment's serving stack."""
    rules = Template.from_stack(stacks["serving"]).find_resources("AWS::Events::Rule")
    return [
        rule["Properties"]["EventPattern"]
        for rule in rules.values()
        if "ModelPackageGroupName" in json.dumps(rule["Properties"]["EventPattern"])
    ]


def test_environments_never_share_a_model_package_group():
    """Require a distinct model package group for each environment."""
    environments = {env: synth_env(env, stack_prefix(env)) for env in ("dev", "prod")}

    group_names = {env: _registry_group_name(stacks) for env, stacks in environments.items()}
    assert len(set(group_names.values())) == len(group_names), group_names

    # Require distinct approval-rule patterns for each environment.
    patterns = [
        json.dumps(pattern, sort_keys=True)
        for stacks in environments.values()
        for pattern in _approval_rule_patterns(stacks)
    ]
    assert len(patterns) == len(environments)
    assert len(set(patterns)) == len(patterns), patterns
