"""Bundle `src/` and Pydantic into the shared Lambda asset.

Local pip bundling runs first. The SAM build image handles local bundling
failures. Every platform function uses this asset.
"""

import pathlib
import shlex
import shutil
import subprocess
import sys
from typing import Any

import jsii
from aws_cdk import BundlingOptions, DockerImage, IgnoreMode, ILocalBundling
from aws_cdk import aws_lambda as lambda_

_RUNTIME_DEPS = ["pydantic==2.*"]
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Install wheels for the Lambda runtime platform.
# Host-native wheels fail to import `pydantic_core` in Lambda.
# Both bundling paths use these flags.
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


# Use an allowlist for the CDK asset fingerprint.
# CDK fingerprints every included file in the source directory.
# Bundling copies only `src/`.
#
# `IgnoreMode.GIT` gives the patterns below gitignore semantics. The default
# `IgnoreMode.GLOB` leaves the leading `*` unable to match a dotfile, so `.git`
# joins the fingerprint. `.git` is a file in a git worktree, and it holds an
# absolute path, so each checkout gets its own Lambda code hash.
#
# Exclude `__pycache__` after re-including `src/**`.
# A `.pyc` header contains the source modification time and changes the asset hash.
_ASSET_CONTENT = [
    "*",
    "!src",
    "!src/**",
    "src/**/__pycache__",
    "src/**/__pycache__/**",
]


def src_code() -> lambda_.Code:
    return lambda_.Code.from_asset(
        str(_REPO_ROOT),
        exclude=_ASSET_CONTENT,
        ignore_mode=IgnoreMode.GIT,
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
