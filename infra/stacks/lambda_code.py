"""Shared Lambda asset: bundles src/ plus pydantic.

Local bundling runs first. It uses pip on the host, which is fast and needs no
Docker in CI. If local pip fails, bundling falls back to the SAM build image in
Docker. Every function reuses this one asset, so each deployed handler imports
the same src.common.schema the pipeline uses.
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

# The wheels must match the Lambda runtime, not the host that builds the asset.
# The host's native wheels cause a pydantic_core import failure at runtime.
# Both bundling paths below share these flags.
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


# This is an allowlist, not a denylist. CDK computes the asset fingerprint over
# the whole source directory, so anything reachable here moves the Lambda code
# hash. Bundling copies only `src/`. Under a denylist, a README edit redeploys
# all four functions, and every new top-level file joins the fingerprint.
#
# The last two patterns exclude `__pycache__`, which re-including `src/**`
# pulls back in. A `.pyc` header embeds the source mtime, so a test run moves
# the code hash with no source change. Bundling already skips `__pycache__`, so
# the shipped package is unaffected.
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
