import subprocess
from pathlib import Path
from unittest import mock

from scripts import check_public_release


def test_repository_files_reads_git_file_list(tmp_path: Path):
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=b"README.md\0scripts/check.py\0"
    )

    with mock.patch.object(subprocess, "run", return_value=completed) as run:
        paths = check_public_release.repository_files(tmp_path)

    assert paths == [tmp_path / "README.md", tmp_path / "scripts/check.py"]
    run.assert_called_once_with(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_scan_text_rejects_sensitive_metadata(tmp_path: Path):
    path = tmp_path / "notes.md"
    text = "\n".join(
        [
            "arn:aws:iam::" + "999988" + "887777:role/example",
            "https://abcdefghij." + "execute-api.us-east-1.amazonaws.com/dev",
            "execution `" + "abcdefghij`",
            "s3://" + "mlops-dev-data-" + "rawbucket1234-abcdefghij/file.csv",
            "profile=" + "mlops-" + "deployer",
        ]
    )

    findings = check_public_release.scan_text(path, text)

    assert {finding.rule for finding in findings} == {
        "AWS account identifier",
        "API Gateway host",
        "pipeline execution identifier",
        "generated S3 bucket name",
        "IAM identity name",
    }


def test_scan_text_allows_placeholders_and_test_accounts(tmp_path: Path):
    path = tmp_path / "notes.md"
    text = "\n".join(
        [
            "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${PIPELINE_ROLE_NAME}",
            "arn:aws:iam::123456789012:role/test",
            "https://${API_GATEWAY_ID}.execute-api.us-east-1.amazonaws.com/dev",
            "execution `<pipeline-execution-id>`",
            "s3://${RAW_BUCKET}/file.csv",
        ]
    )

    assert check_public_release.scan_text(path, text) == []


def test_scan_text_ignores_numeric_lock_hashes(tmp_path: Path):
    path = tmp_path / "uv.lock"

    assert check_public_release.scan_text(path, "hash = " + "999988" + "887777") == []


def test_scan_paths_rejects_private_files_and_skips_binary(tmp_path: Path):
    private = tmp_path / ".env.prod"
    private.write_text("VALUE=example")
    binary = tmp_path / "image.png"
    binary.write_bytes(b"\xff\xfe\x00")

    findings = check_public_release.scan_paths([private, binary])

    assert findings == [check_public_release.Finding(path=private, line=1, rule="private filename")]


def test_scan_paths_skips_missing_paths_and_directories(tmp_path: Path):
    assert check_public_release.scan_paths([tmp_path / "missing", tmp_path]) == []


def test_main_reports_success(monkeypatch, capsys):
    monkeypatch.setattr(check_public_release, "repository_files", lambda root: [])

    assert check_public_release.main() == 0
    assert capsys.readouterr().out == "public-check: no sensitive literals found\n"


def test_main_reports_safe_finding_location(monkeypatch, capsys):
    root = Path(check_public_release.__file__).resolve().parents[1]
    finding = check_public_release.Finding(path=root / "notes.md", line=7, rule="example rule")
    monkeypatch.setattr(check_public_release, "repository_files", lambda root: [])
    monkeypatch.setattr(check_public_release, "scan_paths", lambda paths: [finding])

    assert check_public_release.main() == 1
    assert capsys.readouterr().out == (
        "notes.md:7: example rule\npublic-check: 1 sensitive literal(s) found\n"
    )
