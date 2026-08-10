"""Reject sensitive filenames and literals before a public release."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rule:
    """Define one public-release check."""

    name: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    """Identify one file and line that violate a rule."""

    path: Path
    line: int
    rule: str


_IDENTITIES = (
    "mlops-" + "security-auditor",
    "mlops-" + "deployer",
    "aws-" + "admin",
    "mlops-" + "admin",
    "mlops-dev-" + "github-deploy",
)

RULES = (
    Rule(
        "AWS account identifier",
        re.compile(r"(?<!\d)(\d{12})(?!\d)"),
    ),
    Rule("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    Rule("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    Rule("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    Rule("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    Rule("Stripe secret", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    Rule(
        "API Gateway host",
        re.compile(r"\b[a-z0-9]{10,}\.execute-api\.[a-z0-9-]+\.amazonaws\.com\b"),
    ),
    Rule(
        "generated S3 bucket name",
        re.compile(r"\bmlops-(?:dev|prod)-[a-z0-9-]*bucket[a-z0-9]*-[a-z0-9]{10,}"),
    ),
    Rule(
        "IAM identity name",
        re.compile(r"\b(?:" + "|".join(re.escape(value) for value in _IDENTITIES) + r")\b"),
    ),
    Rule(
        "pipeline execution identifier",
        re.compile(r"(?:execution/|execution `|pipelines-)[a-z0-9]{10,}(?:`|-|\b)"),
    ),
    Rule(
        "endpoint configuration identifier",
        re.compile(r"churn-serverless-(?:dev|prod)-config-\d{8,}"),
    ),
    Rule(
        "CloudFormation physical name",
        re.compile(
            r"\bMlops-(?:Dev|Prod)-[A-Za-z0-9-]+-"
            r"(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[a-z])"
            r"(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{10,}\b"
        ),
    ),
    Rule(
        "Access Analyzer finding identifier",
        re.compile(r"\bfinding (?:id )?`[a-f0-9]{8,}`", re.IGNORECASE),
    ),
    Rule("API key identifier", re.compile(r"\bAPI key ID: `[a-z0-9]{10,}`")),
)

_DOCUMENTATION_ACCOUNT_IDS = {"111122223333", "123456789012"}


def repository_files(root: Path) -> list[Path]:
    """Return tracked and untracked files that Git does not ignore."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def is_forbidden_filename(path: Path) -> bool:
    """Return true when a private environment or key file is publishable."""
    name = path.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    return path.suffix.lower() in {".key", ".p12", ".pfx", ".pem"}


def scan_text(path: Path, text: str) -> list[Finding]:
    """Return every public-release violation in one text file."""
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule in RULES:
            for match in rule.pattern.finditer(line):
                if rule.name == "AWS account identifier" and (
                    path.name == "uv.lock" or match.group(1) in _DOCUMENTATION_ACCOUNT_IDS
                ):
                    continue
                findings.append(Finding(path=path, line=line_number, rule=rule.name))
    return findings


def scan_paths(paths: list[Path]) -> list[Finding]:
    """Scan readable text files and reject private filenames."""
    findings: list[Finding] = []
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        if is_forbidden_filename(path):
            findings.append(Finding(path=path, line=1, rule="private filename"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(path, text))
    return findings


def main() -> int:
    """Scan the repository and print safe finding locations."""
    root = Path(__file__).resolve().parents[1]
    findings = scan_paths(repository_files(root))
    if not findings:
        print("public-check: no sensitive literals found")
        return 0
    for finding in findings:
        print(f"{finding.path.relative_to(root)}:{finding.line}: {finding.rule}")
    print(f"public-check: {len(findings)} sensitive literal(s) found")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
