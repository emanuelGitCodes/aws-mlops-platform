"""The shared Lambda asset must be fingerprinted on `src/` and nothing else.

`Code.from_asset` hashes its source directory. Here that directory is the
repository root, because bundling must reach `src/` from it. Every file the
exclude list fails to filter joins the Lambda code hash, even though bundling
copies only `src/`. Under a denylist, a README edit changes the hash and
redeploys all four functions.
"""

import contextlib
import pathlib
import subprocess
import sys
from unittest import mock

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infra.app import build_app, load_config
from infra.stacks.lambda_code import _LocalPipBundling
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
    """The other half of the contract. A real code change must still ship."""
    with _temporary_file(REPO_ROOT / "src" / PROBE_NAME):
        assert _serving_asset_key() != baseline


def test_the_probe_files_are_cleaned_up():
    """A leaked probe poisons every later asset comparison."""
    assert not (REPO_ROOT / PROBE_NAME).exists()
    assert not (REPO_ROOT / "src" / PROBE_NAME).exists()


# `try_bundle` builds every Lambda package on the host. It returns False to
# hand off to the Docker image. A broken local path falls back silently and
# slowly. A local path that stops cross-installing ships the host's wheels,
# which fails at runtime on the pydantic_core import.


def _bundle(output_dir: pathlib.Path, pip_result=None):
    """Run try_bundle with pip stubbed. Return the result, the run mock, and
    the copytree mock."""
    with (
        mock.patch("subprocess.run", side_effect=pip_result) as run,
        mock.patch("shutil.copytree") as copytree,
    ):
        result = _LocalPipBundling().try_bundle(str(output_dir), image=mock.Mock())
    return result, run, copytree


def test_local_bundling_cross_installs_for_the_lambda_runtime(tmp_path):
    """The wheels must match Lambda, not the machine running the synth."""
    result, run, copytree = _bundle(tmp_path)

    assert result is True
    command = run.call_args.args[0]
    assert command[:3] == [sys.executable, "-m", "pip"]
    for flag in ("--platform", "manylinux2014_x86_64", "--only-binary=:all:", "3.12"):
        assert flag in command, flag
    assert command[-2:] == ["-t", str(tmp_path)]
    assert any(dep.startswith("pydantic") for dep in command)
    # check=True turns a failed install into the Docker fallback below.
    assert run.call_args.kwargs["check"] is True
    assert copytree.call_args.args[0] == REPO_ROOT / "src"


def test_local_bundling_does_not_copy_pycache_into_the_package(tmp_path):
    """Compiled bytecode from the host must not enter the deployed asset."""
    _, _, copytree = _bundle(tmp_path)

    ignore = copytree.call_args.kwargs["ignore"]
    assert ignore("src", ["common", "__pycache__"]) == {"__pycache__"}


def test_a_failed_local_install_falls_back_to_docker(tmp_path):
    """Returning False is the handoff. Raising would abort the synth."""
    error = subprocess.CalledProcessError(1, "pip")
    result, _, copytree = _bundle(tmp_path, pip_result=error)

    assert result is False
    # No half-populated output directory remains for CDK to zip.
    copytree.assert_not_called()


def test_compiled_bytecode_does_not_change_the_lambda_asset(baseline):
    """A `.pyc` under src/ must not move the hash.

    Re-including `src/**` pulls `__pycache__` into the fingerprint. A `.pyc`
    header embeds the source file mtime, so a test run moves the Lambda code
    hash with no source change, and the next deploy updates all four functions.
    Bundling never copies these files, so the fault is invisible.
    """
    probe = REPO_ROOT / "src" / "common" / "__pycache__" / f"{PROBE_NAME}.cpython-312.pyc"
    probe.parent.mkdir(parents=True, exist_ok=True)
    with _temporary_file(probe):
        assert _serving_asset_key() == baseline
