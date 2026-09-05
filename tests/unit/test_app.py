"""Test the CDK application stack dependency graph."""

from infra.app import stack_prefix
from tests.unit.conftest import synth_env


def test_registry_precedes_stacks_that_use_the_model_package_group():
    stacks = synth_env("dev", stack_prefix("dev"))
    registry = stacks["registry"]

    for consumer_name in ("training", "serving", "monitoring"):
        assert registry in stacks[consumer_name].dependencies
