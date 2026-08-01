"""The shared Lambda asset must be fingerprinted on `src/` and nothing else.

`Code.from_asset` hashes its source directory, and the source directory here is
the repository root -- bundling needs `src/` to be reachable from it. So every
file the exclude list fails to filter out joins the Lambda code hash, even
though bundling only ever copies `src/`. Under the previous denylist a README
or Makefile edit changed the hash and redeployed all four functions, and each
new top-level file silently joined the fingerprint.
"""

import contextlib
import pathlib

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.app import build_app, load_config
from tests.unit.conftest import REPO_ROOT

PROBE_NAME = "_fingerprint_probe.tmp"


def _serving_asset_key() -> str:
    """The S3 key of the shared asset, as the Serving stack would deploy it."""
    app = cdk.App(
        context={
            "aws:cdk:bundling-stacks": [],
            "@aws-cdk/aws-s3:serverAccessLogsUseBucketPolicy": True,
        }
    )
    stacks = build_app(app, load_config("dev"), "AssetProbe")
    app.synth()
    resources = Template.from_stack(stacks["serving"]).to_json()["Resources"]
    return next(
        resource["Properties"]["Code"]["S3Key"]
        for resource in resources.values()
        if resource["Type"] == "AWS::Lambda::Function"
    )


@contextlib.contextmanager
def _temporary_file(path: pathlib.Path):
    """Create a file for the duration of the test, then remove it."""
    path.write_text("fingerprint probe\n")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def baseline() -> str:
    return _serving_asset_key()


def test_a_new_repository_root_file_does_not_change_the_lambda_asset(baseline):
    """Docs, Makefile and config edits must not redeploy every Lambda."""
    with _temporary_file(REPO_ROOT / PROBE_NAME):
        assert _serving_asset_key() == baseline


def test_a_change_under_src_does_change_the_lambda_asset(baseline):
    """The other half of the contract: real code changes must still ship."""
    with _temporary_file(REPO_ROOT / "src" / PROBE_NAME):
        assert _serving_asset_key() != baseline


def test_the_probe_files_are_cleaned_up():
    """A leaked probe would silently poison every later asset comparison."""
    assert not (REPO_ROOT / PROBE_NAME).exists()
    assert not (REPO_ROOT / "src" / PROBE_NAME).exists()
