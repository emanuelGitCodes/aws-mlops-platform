import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]


def _executable(directory: Path, name: str, content: str) -> None:
    path = directory / name
    path.write_text(content)
    path.chmod(0o755)


def _run_smoke(tmp_path: Path, *make_args: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir, "uv", "#!/bin/sh\nexit 0\n")
    _executable(
        bin_dir,
        "aws",
        '#!/bin/sh\nprintf \'%s\\n\' "${AWS_PROFILE-}" > "$AWS_STUB_MARKER"\nexit 1\n',
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["AWS_STUB_MARKER"] = str(tmp_path / "aws-profile")
    return subprocess.run(
        ["make", "--no-print-directory", "smoke", *make_args],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke_uses_supplied_api_url_without_cloudformation_discovery(tmp_path):
    result = _run_smoke(tmp_path, "API_URL=https://example.test/predict")

    assert result.returncode == 0, result.stderr
    assert "smoke testing https://example.test/predict" in result.stdout
    assert not (tmp_path / "aws-profile").exists()


def test_smoke_keeps_discovery_profile_separate_from_inference_profile(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(
        bin_dir,
        "uv",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *stack_prefix*) printf '%s\\n' Mlops-Dev ;;\n"
        '  *) printf \'%s\\n\' "${AWS_PROFILE-}" >> "$UV_STUB_MARKER" ;;\n'
        "esac\n",
    )
    _executable(
        bin_dir,
        "aws",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "${AWS_PROFILE-}" > "$AWS_STUB_MARKER"\n'
        "printf '%s\\n' https://example.test/predict\n",
    )
    environment = os.environ.copy()
    environment.pop("API_URL", None)
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["AWS_PROFILE"] = "inference"
    environment["AWS_STUB_MARKER"] = str(tmp_path / "aws-profile")
    environment["UV_STUB_MARKER"] = str(tmp_path / "uv-profile")

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "smoke",
            "DISCOVERY_PROFILE=reader",
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "aws-profile").read_text().strip() == "reader"
    assert (tmp_path / "uv-profile").read_text().splitlines() == ["inference"]
