"""Shared unit-test setup: handler env stubs, boto3-stubbed imports, the
canonical valid sample record, the repo root path, and the synthesized CDK app.

The CDK fixtures are session-scoped rather than module-scoped: the per-stack
test modules all assert against the same dev synthesis, and re-synthesizing the
whole app once per module would multiply the suite's slowest step by eight.
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
# Read from sample.json rather than restated here: the two were byte-identical
# copies, so a schema change could be applied to the fixture while the payload
# operators actually curl with went stale, or the reverse.
SAMPLE_PATH = REPO_ROOT / "sample.json"
VALID = json.loads(SAMPLE_PATH.read_text())


def import_with_stubbed_boto3(module_name: str):
    """Import a handler module with its module-level boto3 clients mocked."""
    with mock.patch("boto3.client"):
        return importlib.import_module(module_name)


CONFIG = load_config("dev")


def synth_env(env_name: str, prefix: str) -> dict:
    """Build and synth every stack for one environment.

    The single place the test app context is configured, so a test can never
    synthesize under different assumptions than the rest of the suite.
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
    """Stands in for botocore's ClientError, which carries a `response` dict.

    Shared: both the deploy handler and the proxy handler branch on the error
    code, and a second copy could drift from the shape botocore actually
    raises.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}
