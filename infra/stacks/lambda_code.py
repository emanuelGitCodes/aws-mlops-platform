"""Shared Lambda asset: bundles src/ plus pydantic.

Tries local bundling first (pip on the host — fast, no Docker needed in CI);
falls back to the SAM build image in Docker if local pip fails. One asset is
reused by every function so the deployed handlers import the same
src.common.schema the pipeline uses.
"""

import pathlib
import shutil
import subprocess
import sys

import jsii
from aws_cdk import BundlingOptions, DockerImage, ILocalBundling
from aws_cdk import aws_lambda as lambda_

_RUNTIME_DEPS = ["pydantic==2.*"]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@jsii.implements(ILocalBundling)
class _LocalPipBundling:
    def try_bundle(self, output_dir: str, *, image, **kwargs) -> bool:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-q",
                    *_RUNTIME_DEPS,
                    "--platform",
                    "manylinux2014_x86_64",
                    "--only-binary=:all:",
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
                f"pip install {' '.join(repr(d) for d in _RUNTIME_DEPS)} -t /asset-output"
                " && cp -r src /asset-output/",
            ],
            local=_LocalPipBundling(),
        ),
    )
