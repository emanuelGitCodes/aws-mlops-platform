"""Shared unit-test setup: handler env stubs, boto3-stubbed imports, the
canonical valid sample record, and the repo root path."""

import importlib
import json
import os
import pathlib
from unittest import mock

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


class ClientError(Exception):
    """Stands in for botocore's ClientError, which carries a `response` dict.

    Shared: both the deploy handler and the proxy handler branch on the error
    code, and a second copy could drift from the shape botocore actually
    raises.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}
