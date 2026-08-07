"""Shared unit-test setup: handler env stubs, boto3-stubbed imports, the
canonical valid sample record, the repo root path, and the synthesized CDK app.

The CDK fixtures are session-scoped, not module-scoped. Every per-stack test
module asserts against the same dev synthesis. One synthesis per module would
multiply the slowest step in the suite by eight.
"""

import importlib
import json
import os
import pathlib
from unittest import mock

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.app import build_app, load_config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Handler modules read these at import time; set them before any test imports.
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/test")
os.environ.setdefault("CURATED_BUCKET", "test-curated")
os.environ.setdefault("PIPELINE_NAME", "test-pipeline")

# One valid CustomerRecord payload, shared by every test module that needs it.
# Read it from sample.json. The two were identical copies, so a schema change
# could reach the fixture while the payload operators curl with went stale.
SAMPLE_PATH = REPO_ROOT / "sample.json"
VALID = json.loads(SAMPLE_PATH.read_text())


def import_with_stubbed_boto3(module_name: str):
    """Import a handler module with its module-level boto3 clients mocked."""
    with mock.patch("boto3.client"):
        return importlib.import_module(module_name)


CONFIG = load_config("dev")


def synth_env(env_name: str, prefix: str) -> dict:
    """Build and synthesize every stack for one environment.

    This is the only place that configures the test app context, so no test
    can synthesize under different assumptions than the rest of the suite.
    """
    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stacks = build_app(app, load_config(env_name), prefix)
    app.synth()
    return stacks


@pytest.fixture(scope="session")
def stack_constructs() -> dict:
    """All stacks built once; the construct tree can't change after first synth."""
    return synth_env("dev", "Test")


@pytest.fixture(scope="session")
def stacks(stack_constructs) -> dict:
    return {name: Template.from_stack(stack) for name, stack in stack_constructs.items()}


class ClientError(Exception):
    """Stand-in for the botocore ClientError, which carries a `response` dict.

    The deploy handler and the proxy handler both branch on the error code, so
    they share this class. A second copy could drift from the shape botocore
    raises.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}
