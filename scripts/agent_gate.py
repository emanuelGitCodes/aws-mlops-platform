#!/usr/bin/env python3
"""Prove an agent turn before it ends, and brief a session before it starts.

A model that checks its own work can report success it did not earn. These
checks cannot: each one is a Make target that passes or fails on its own.

`stop` runs the targets that the changed files need. A failure exits 2, which
returns the output to the agent instead of ending the turn. `session-start`
prints the two facts a session otherwise spends tool calls on. `deploy-guard`
asks the operator before a deploy target runs.

`pr-size` measures the branch against the 150-line cap. `make pr-size` runs
it, and the `stop` gate runs it first, because the size decides what happens
to the whole branch.

`install-hooks` copies `.claude/hooks.json` into `.claude/settings.json`. Run
it yourself with `make agent-hooks`. It replaces the `hooks` key and touches
no other key, so it is safe to run again.

Set `AGENT_GATE_SKIP=1` to hand back unfinished work on purpose. Set
`AGENT_GATE_FULL=1` to add the slow targets that the gate otherwise names but
does not run.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_ENV = "AGENT_GATE_SKIP"
FULL_ENV = "AGENT_GATE_FULL"

GRAPH_REPORT = Path("graphify-out/GRAPH_REPORT.md")
HOOKS_FILE = Path(".claude/hooks.json")
SETTINGS_FILE = Path(".claude/settings.json")
# `GRAPH_REPORT.md` records the commit that produced the graph.
_GRAPH_COMMIT = re.compile(r"Built from commit: `([0-9a-fA-F]+)`")
# Match a Make target that creates or destroys an AWS resource.
_DEPLOY_TARGET = re.compile(r"\bmake\s+\S*\b(deploy|deploy-stack|destroy|bootstrap)\b")

# Run the target in this order. A cheap target fails before an expensive one.
_TARGET_ORDER = ("lint", "typecheck", "test", "docs-sync", "wiki-lint", "public-check")

# A pull request MUST NOT add more than this many lines of code.
PR_SIZE_LIMIT = 150
SIZE_OK_ENV = "AGENT_PR_SIZE_OK"
BASE_ENV = "AGENT_PR_BASE"
DEFAULT_BASE = "origin/main"

# The cap measures code. Tests live under `tests/`, so no prefix reaches them.
_COUNTED_PREFIXES = ("src/", "infra/", "scripts/", "website/")
_UNCOUNTED_PREFIXES = (
    "infra/cdk.out/",
    "website/frontend/dist/",
    "website/frontend/node_modules/",
)

Runner = Callable[[str], tuple[int, str]]
Settings = dict[str, object]


def changed_paths(porcelain: str) -> list[str]:
    """Return the paths in `git status --porcelain` output.

    A rename reports `old -> new`. Keep the new path.
    """
    paths: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip().strip('"')
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip().strip('"')
        if entry:
            paths.append(entry)
    return paths


def _is_project_python(path: str) -> bool:
    """Report whether the path is Python that the checks measure."""
    if not path.endswith(".py"):
        return False
    return not path.startswith(("infra/cdk.out/", "graphify-out/"))


def select_targets(paths: list[str], full: bool = False) -> list[str]:
    """Return the Make targets that prove the changed paths.

    `full` adds the slow targets that `unproved_targets` otherwise names.
    """
    if not paths:
        return []
    targets: set[str] = {"public-check"}
    for path in paths:
        if _is_project_python(path):
            targets.update(("lint", "typecheck", "test"))
        if path in ("AGENTS.md", "CLAUDE.md"):
            targets.add("docs-sync")
        if path.startswith("wiki/"):
            targets.add("wiki-lint")
    ordered = [target for target in _TARGET_ORDER if target in targets]
    if full:
        ordered.extend(unproved_targets(paths))
    return ordered


def unproved_targets(paths: list[str]) -> list[str]:
    """Return the required targets that the gate does not run itself.

    Each one needs minutes or a network call. The gate names them so the
    report can say which check did not run.
    """
    named: list[str] = []
    if any(path.startswith("infra/") for path in paths):
        named.append("synth-all")
    if any(path.startswith("website/frontend/") for path in paths):
        named.append("frontend-check")
    return named


def make_runner(target: str) -> tuple[int, str]:
    """Run one Make target and return its exit code with its combined output."""
    completed = subprocess.run(
        ["make", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def run_targets(targets: list[str], runner: Runner) -> list[tuple[str, str]]:
    """Run each target in order and return the failures with their output."""
    failures: list[tuple[str, str]] = []
    for target in targets:
        code, output = runner(target)
        if code != 0:
            failures.append((target, output))
    return failures


def failure_message(failures: list[tuple[str, str]]) -> str:
    """Return the text that the agent reads instead of ending its turn."""
    names = ", ".join(f"make {target}" for target, _ in failures)
    lines = [
        f"The completion gate failed: {names}.",
        "",
        "Fix the failure and finish the turn again. Do not report success, and",
        "do not report a check you did not run. To hand back unfinished work on",
        f"purpose, set {SKIP_ENV}=1.",
        "",
    ]
    for target, output in failures:
        lines.append(f"--- make {target} ---")
        lines.append(_tail(output))
    return "\n".join(lines)


def _tail(output: str, limit: int = 60) -> str:
    """Return the last lines of the output, which hold the failure."""
    lines = output.strip().splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join([f"[{len(lines) - limit} earlier lines omitted]", *lines[-limit:]])


def graph_line(head: str, report: str | None) -> str:
    """Return one line on whether the code graph matches the checkout."""
    if report is None:
        return "code graph: not built. Run `make graph` in the primary checkout."
    found = _GRAPH_COMMIT.search(report)
    if found is None:
        return "code graph: built, but the report names no commit. Rebuild it."
    built = found.group(1)
    if head.startswith(built) or built.startswith(head):
        return f"code graph: fresh at {built}."
    return (
        f"code graph: STALE. Built from {built}, HEAD is {head[:8]}. "
        "Run `make graph`, or do not cite the graph."
    )


def session_lines(head: str, report: str | None, worktree: bool) -> list[str]:
    """Return the briefing that a session would otherwise spend calls on."""
    lines = [graph_line(head, report)]
    if worktree:
        lines.append(
            "worktree: the graphify hooks do not run here. `make graph` rebuilds "
            "the primary checkout only."
        )
        lines.append("worktree: the stash stack is shared. Do not `git stash`.")
    return lines


def deploy_decision(command: str) -> Settings | None:
    """Return the hook decision for a Bash command, or None to allow it.

    `deploy-stack` deploys the named stack and every stack it depends on.
    The website stack creates real monthly cost. Both cases want an operator.
    """
    if not _DEPLOY_TARGET.search(command):
        return None
    reason = (
        "This target changes AWS. `deploy-stack` also deploys every stack the "
        "named stack depends on — read the `Including dependency stacks:` line "
        "first. The website stack MUST NOT be deployed. After the deploy, run "
        "`make verify-deploy SINCE=<YYYY-MM-DD>` and report resources, not "
        "stack status."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def is_counted_path(path: str) -> bool:
    """Report whether the path counts against the pull-request size cap.

    The cap measures the code that is hard to review. A test, a wiki page, a
    Markdown file, a lockfile, and build output do not count. Never let the
    cap discourage a test or the wiki record.
    """
    if path.endswith((".md", ".lock")) or path.endswith("package-lock.json"):
        return False
    if path.startswith(_UNCOUNTED_PREFIXES):
        return False
    return path.startswith(_COUNTED_PREFIXES)


def counted_insertions(numstat: str) -> tuple[int, list[tuple[str, int]]]:
    """Return the added code lines, and the per-file counts, from `--numstat`.

    Count an insertion only. A deletion makes a branch easier to review, not
    harder. Git writes `-` for a binary file, which carries no line count.
    """
    total = 0
    files: list[tuple[str, int]] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, _, path = parts
        if added == "-" or not is_counted_path(path):
            continue
        count = int(added)
        if count:
            files.append((path, count))
            total += count
    return total, sorted(files, key=lambda item: -item[1])


def size_message(total: int, files: list[tuple[str, int]], base: str) -> str:
    """Return the text that tells the agent to split the branch."""
    lines = [
        f"This branch adds {total} lines of code against {base}.",
        f"The cap is {PR_SIZE_LIMIT}. Split it into stacked pull requests.",
        "Each one MUST stand on its own and base on the branch below it, not",
        "on main. State the merge order when you report.",
        "",
        "The count covers src/, infra/, scripts/, and website/. It excludes",
        "tests, Markdown, lockfiles, and build output. For a change that",
        f"cannot split, set {SIZE_OK_ENV}=1 and say why in the pull request.",
        "",
    ]
    lines.extend(f"  {count:>5}  {path}" for path, count in files)
    return "\n".join(lines)


def resolve_base(explicit: str | None, pr_base: str | None) -> str:
    """Return the ref that the branch is measured against.

    A stacked branch bases on the branch below it. Measuring it against main
    counts the whole stack, so the pull request's own base wins.
    """
    if explicit:
        return explicit
    if pr_base:
        return pr_base
    return DEFAULT_BASE


def merge_hooks(settings: Settings, hooks: Settings) -> Settings:
    """Return the settings with the `hooks` key replaced.

    Replace rather than append. A second run then produces one hook, not two.
    Every other key stays as the operator wrote it, including `permissions`.
    """
    merged: Settings = dict(settings)
    merged["hooks"] = hooks
    return merged


def _pr_base() -> str | None:
    """Return the base branch of the open pull request, when `gh` knows it.

    A stacked branch bases on the branch below it. `gh` is the only source
    that knows which one.
    """
    completed = subprocess.run(
        ["gh", "pr", "view", "--json", "baseRefName", "--jq", ".baseRefName"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    name = completed.stdout.strip()
    return f"origin/{name}" if name else None


def branch_totals(base: str) -> tuple[int, list[tuple[str, int]]]:
    """Return the added code lines on this branch, against the merge base.

    Measure from the merge base to the working tree. A commit and an
    uncommitted edit both count, because both reach the pull request.
    """
    merge_base = _git("merge-base", base, "HEAD") or base
    return counted_insertions(_git("diff", "--numstat", merge_base))


def size_check() -> tuple[int, str]:
    """Return the exit code and message for the pull-request size cap."""
    if os.environ.get(SIZE_OK_ENV):
        return 0, ""
    base = resolve_base(os.environ.get(BASE_ENV), _pr_base())
    total, files = branch_totals(base)
    if total <= PR_SIZE_LIMIT:
        return 0, ""
    return 2, size_message(total, files, base)


def _git(*args: str) -> str:
    """Return the stripped stdout of a git command, or an empty string."""
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _read_payload(stream: object) -> Settings:
    """Return the hook payload. A hook may send nothing."""
    read = getattr(stream, "read", None)
    if read is None:
        return {}
    try:
        raw = read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def stop_gate(payload: Settings, runner: Runner) -> tuple[int, str]:
    """Return the exit code and the message for the `Stop` hook."""
    if payload.get("stop_hook_active"):
        return 0, ""
    if os.environ.get(SKIP_ENV):
        return 0, ""
    code, message = size_check()
    if code != 0:
        return code, message
    paths = changed_paths(_git("status", "--porcelain"))
    targets = select_targets(paths, full=bool(os.environ.get(FULL_ENV)))
    if not targets:
        return 0, ""
    failures = run_targets(targets, runner)
    if failures:
        return 2, failure_message(failures)
    return 0, ""


def _cmd_stop(runner: Runner = make_runner) -> int:
    payload = _read_payload(sys.stdin)
    code, message = stop_gate(payload, runner)
    if message:
        print(message, file=sys.stderr)
    return code


def _cmd_session_start() -> int:
    report_path = REPO_ROOT / GRAPH_REPORT
    report = report_path.read_text() if report_path.is_file() else None
    worktree = ".claude/worktrees/" in str(REPO_ROOT)
    for line in session_lines(_git("rev-parse", "HEAD"), report, worktree):
        print(line)
    return 0


def _cmd_deploy_guard() -> int:
    payload = _read_payload(sys.stdin)
    tool_input = payload.get("tool_input")
    command = ""
    if isinstance(tool_input, dict):
        command = str(tool_input.get("command", ""))
    decision = deploy_decision(command)
    if decision is not None:
        print(json.dumps(decision))
    return 0


def _cmd_install_hooks() -> int:
    hooks_path = REPO_ROOT / HOOKS_FILE
    settings_path = REPO_ROOT / SETTINGS_FILE
    if not hooks_path.is_file():
        print(f"{HOOKS_FILE} is missing", file=sys.stderr)
        return 2
    hooks = json.loads(hooks_path.read_text())
    settings: Settings = {}
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text())
    merged = merge_hooks(settings, hooks)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n")
    names = ", ".join(sorted(hooks))
    print(f"agent-hooks: wrote {SETTINGS_FILE} with {names}")
    return 0


def _cmd_pr_size() -> int:
    code, message = size_check()
    if message:
        print(message, file=sys.stderr)
        return code
    base = resolve_base(os.environ.get(BASE_ENV), _pr_base())
    total, _ = branch_totals(base)
    print(f"pr-size: {total} of {PR_SIZE_LIMIT} lines of code against {base}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch the hook subcommand."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "stop",
            "session-start",
            "deploy-guard",
            "install-hooks",
            "pr-size",
        ),
    )
    args = parser.parse_args(argv)
    if args.command == "stop":
        return _cmd_stop()
    if args.command == "session-start":
        return _cmd_session_start()
    if args.command == "install-hooks":
        return _cmd_install_hooks()
    if args.command == "pr-size":
        return _cmd_pr_size()
    return _cmd_deploy_guard()


if __name__ == "__main__":
    raise SystemExit(main())
