"""Define shared unit-test data, stubs, and synthesized CDK fixtures."""

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

# Set handler environment values before module imports.
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ.setdefault("EXECUTION_ROLE_ARN", "arn:aws:iam::123456789012:role/test")
os.environ.setdefault("CURATED_BUCKET", "test-curated")
os.environ.setdefault("PIPELINE_NAME", "test-pipeline")

# Read the shared valid request from `sample.json`.
SAMPLE_PATH = REPO_ROOT / "sample.json"
VALID = json.loads(SAMPLE_PATH.read_text())


def import_with_stubbed_boto3(module_name: str):
    """Import a handler module with its module-level boto3 clients mocked."""
    with mock.patch("boto3.client"):
        return importlib.import_module(module_name)


CONFIG = load_config("dev")


def synth_env(env_name: str, prefix: str) -> dict:
    """Build and synthesize every stack with the test app context."""
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
    """Build all stack constructs once for the test session."""
    return synth_env("dev", "Test")


@pytest.fixture(scope="session")
def stacks(stack_constructs) -> dict:
    return {name: Template.from_stack(stack) for name, stack in stack_constructs.items()}


class ClientError(Exception):
    """Represent a botocore client error with a `response` dictionary."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}


def varied_records(count: int, seed: int = 0, **overrides):
    """Generate `count` vocabulary records and apply `overrides`."""
    import random

    from src.common.features import FEATURE_VOCABULARY

    rng = random.Random(seed)
    records = []
    for _ in range(count):
        record = dict(VALID)
        for column, values in FEATURE_VOCABULARY.items():
            record[column] = rng.choice(sorted(values))
        record["SeniorCitizen"] = rng.choice([0, 0, 0, 1])
        record["tenure"] = rng.randint(0, 72)
        record["MonthlyCharges"] = round(rng.uniform(18.0, 120.0), 2)
        record["TotalCharges"] = round(record["tenure"] * record["MonthlyCharges"], 2)
        record.update(overrides)
        records.append(record)
    return records
