"""Shared Lambda asset: bundles src/ plus pydantic.

Tries local bundling first (pip on the host — fast, no Docker needed in CI);
falls back to the SAM build image in Docker if local pip fails. One asset is
reused by every function so the deployed handlers import the same
src.common.schema the pipeline uses.
"""

import pathlib
import shlex
import shutil
import subprocess
import sys
from typing import Any

import jsii
from aws_cdk import BundlingOptions, DockerImage, ILocalBundling
from aws_cdk import aws_lambda as lambda_

_RUNTIME_DEPS = ["pydantic==2.*"]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# The wheels must match the Lambda runtime, not the host building the asset --
# installing the host's native wheels once produced a pydantic_core import
# failure at runtime. Defined once and shared by both bundling paths below:
# they were previously two hand-maintained spellings of the same command, one
# as an argv list and one as a shell string, free to drift apart.
_PIP_TARGET_FLAGS = [
    "--platform",
    "manylinux2014_x86_64",
    "--implementation",
    "cp",
    "--python-version",
    "3.12",
    "--only-binary=:all:",
]


@jsii.implements(ILocalBundling)
class _LocalPipBundling:
    def try_bundle(self, output_dir: str, *, image: DockerImage, **kwargs: Any) -> bool:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-q",
                    *_RUNTIME_DEPS,
                    *_PIP_TARGET_FLAGS,
                    "-t",
                    output_dir,
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            return False
        shutil.copytree(
            _REPO_ROOT / "src",
            pathlib.Path(output_dir) / "src",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        return True


def src_code() -> lambda_.Code:
    return lambda_.Code.from_asset(
        str(_REPO_ROOT),
        exclude=["infra", "tests", ".git", "cdk.out", ".venv", "*.egg-info", "data", "scripts"],
        bundling=BundlingOptions(
            image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12"),
            command=[
                "bash",
                "-c",
                f"pip install {shlex.join([*_RUNTIME_DEPS, *_PIP_TARGET_FLAGS])}"
                " -t /asset-output && cp -r src /asset-output/",
            ],
            local=_LocalPipBundling(),
        ),
    )
