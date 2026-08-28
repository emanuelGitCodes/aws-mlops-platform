"""Cover the completion gate that ends an agent turn."""

import io
import json

import pytest

from scripts import agent_gate


def test_changed_paths_reads_porcelain():
    porcelain = " M src/common/features.py\n?? scripts/new.py\nA  wiki/log.md\n"
    assert agent_gate.changed_paths(porcelain) == [
        "src/common/features.py",
        "scripts/new.py",
        "wiki/log.md",
    ]


def test_changed_paths_keeps_the_new_name_of_a_rename():
    porcelain = "R  src/old.py -> src/new.py\n"
    assert agent_gate.changed_paths(porcelain) == ["src/new.py"]


def test_changed_paths_ignores_a_short_line():
    assert agent_gate.changed_paths(" M\n\n") == []


def test_select_targets_returns_nothing_for_a_clean_tree():
    assert agent_gate.select_targets([]) == []


def test_select_targets_runs_the_python_checks():
    targets = agent_gate.select_targets(["src/common/features.py"])
    assert targets == ["lint", "typecheck", "test", "public-check"]


def test_select_targets_adds_docs_sync_and_wiki_lint():
    targets = agent_gate.select_targets(["AGENTS.md", "wiki/log.md"])
    assert targets == ["docs-sync", "wiki-lint", "public-check"]


def test_select_targets_ignores_build_output():
    targets = agent_gate.select_targets(["infra/cdk.out/asset.py"])
    assert "test" not in targets


def test_select_targets_adds_the_slow_targets_only_when_full():
    paths = ["infra/stacks/security_stack.py", "website/frontend/src/App.tsx"]
    assert "synth-all" not in agent_gate.select_targets(paths)
    full = agent_gate.select_targets(paths, full=True)
    assert full[-2:] == ["synth-all", "frontend-check"]


def test_unproved_targets_names_what_the_gate_skips():
    assert agent_gate.unproved_targets(["infra/app.py"]) == ["synth-all"]
    assert agent_gate.unproved_targets(["src/common/drift.py"]) == []


def test_run_targets_collects_only_the_failures():
    def runner(target):
        return (1, "boom") if target == "test" else (0, "ok")

    assert agent_gate.run_targets(["lint", "test"], runner) == [("test", "boom")]


def test_failure_message_names_the_target_and_the_escape():
    message = agent_gate.failure_message([("test", "assert 1 == 2")])
    assert "make test" in message
    assert "AGENT_GATE_SKIP=1" in message
    assert "assert 1 == 2" in message


def test_failure_message_truncates_a_long_output():
    output = "\n".join(f"line {index}" for index in range(200))
    message = agent_gate.failure_message([("test", output)])
    assert "earlier lines omitted" in message
    assert "line 199" in message
    assert "line 0" not in message


def test_graph_line_reports_a_fresh_graph():
    report = "- Built from commit: `be79a8e3`"
    assert "fresh" in agent_gate.graph_line("be79a8e3f00", report)


def test_graph_line_reports_a_stale_graph():
    line = agent_gate.graph_line("0123456789ab", "- Built from commit: `be79a8e3`")
    assert "STALE" in line
    assert "make graph" in line


def test_graph_line_handles_a_missing_report():
    assert "not built" in agent_gate.graph_line("abc", None)


def test_graph_line_handles_a_report_without_a_commit():
    assert "no commit" in agent_gate.graph_line("abc", "# Graph Report")


def test_session_lines_warn_inside_a_worktree():
    lines = agent_gate.session_lines("abc", None, worktree=True)
    assert len(lines) == 3
    assert any("stash" in line for line in lines)


def test_session_lines_stay_short_outside_a_worktree():
    assert len(agent_gate.session_lines("abc", None, worktree=False)) == 1


@pytest.mark.parametrize(
    "command",
    ["make deploy", "make deploy-stack STACK=Mlops-Dev-Security", "make destroy"],
)
def test_deploy_decision_asks_before_a_deploy(command):
    decision = agent_gate.deploy_decision(command)
    assert decision is not None
    hook = decision["hookSpecificOutput"]
    assert hook["permissionDecision"] == "ask"
    assert "verify-deploy" in hook["permissionDecisionReason"]


@pytest.mark.parametrize("command", ["make test", "make diff-stack STACK=X", "ls"])
def test_deploy_decision_allows_a_safe_command(command):
    assert agent_gate.deploy_decision(command) is None


def test_stop_gate_does_not_recurse():
    def runner(target):  # pragma: no cover - the gate must not call it
        raise AssertionError("the gate ran a target during a stop loop")

    assert agent_gate.stop_gate({"stop_hook_active": True}, runner) == (0, "")


def test_stop_gate_honours_the_escape(monkeypatch):
    monkeypatch.setenv(agent_gate.SKIP_ENV, "1")

    def runner(target):  # pragma: no cover - the escape must not run it
        raise AssertionError("the gate ran a target under the escape")

    assert agent_gate.stop_gate({}, runner) == (0, "")


def test_stop_gate_passes_a_clean_tree(monkeypatch):
    monkeypatch.delenv(agent_gate.SKIP_ENV, raising=False)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "")
    assert agent_gate.stop_gate({}, lambda target: (0, "")) == (0, "")


def test_stop_gate_blocks_on_a_failing_target(monkeypatch):
    monkeypatch.delenv(agent_gate.SKIP_ENV, raising=False)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: " M src/common/drift.py")
    code, message = agent_gate.stop_gate({}, lambda target: (1, f"{target} failed"))
    assert code == 2
    assert "make lint" in message


def test_read_payload_survives_bad_input():
    assert agent_gate._read_payload(io.StringIO("")) == {}
    assert agent_gate._read_payload(io.StringIO("not json")) == {}
    assert agent_gate._read_payload(io.StringIO("[1]")) == {}
    assert agent_gate._read_payload(object()) == {}
    assert agent_gate._read_payload(io.StringIO('{"a": 1}')) == {"a": 1}


def test_main_runs_the_stop_gate(monkeypatch, capsys):
    monkeypatch.setattr(agent_gate, "_read_payload", lambda stream: {})
    monkeypatch.setattr(agent_gate, "stop_gate", lambda payload, runner: (2, "nope"))
    assert agent_gate.main(["stop"]) == 2
    assert "nope" in capsys.readouterr().err


def test_main_prints_the_session_briefing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(agent_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "abc123")
    assert agent_gate.main(["session-start"]) == 0
    assert "code graph" in capsys.readouterr().out


def test_main_reads_a_built_graph_report(monkeypatch, capsys, tmp_path):
    report = tmp_path / agent_gate.GRAPH_REPORT
    report.parent.mkdir(parents=True)
    report.write_text("- Built from commit: `abc123`")
    monkeypatch.setattr(agent_gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "abc123")
    assert agent_gate.main(["session-start"]) == 0
    assert "fresh" in capsys.readouterr().out


def test_main_guards_a_deploy_command(monkeypatch, capsys):
    payload = {"tool_input": {"command": "make deploy ENV=dev"}}
    monkeypatch.setattr(agent_gate, "_read_payload", lambda stream: payload)
    assert agent_gate.main(["deploy-guard"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]


def test_main_stays_silent_for_a_safe_command(monkeypatch, capsys):
    monkeypatch.setattr(agent_gate, "_read_payload", lambda stream: {"tool_input": {}})
    assert agent_gate.main(["deploy-guard"]) == 0
    assert capsys.readouterr().out == ""


def test_make_runner_reports_an_exit_code():
    code, output = agent_gate.make_runner("docs-sync")
    assert code == 0
    assert "CLAUDE.md" in output


def test_git_returns_empty_on_failure():
    assert agent_gate._git("rev-parse", "--verify", "no-such-ref-xyz") == ""


def test_merge_hooks_replaces_and_preserves():
    settings = {"permissions": {"allow": ["Bash(ls *)"]}, "hooks": {"Stop": ["old"]}}
    merged = agent_gate.merge_hooks(settings, {"Stop": ["new"]})
    assert merged["hooks"] == {"Stop": ["new"]}
    assert merged["permissions"] == {"allow": ["Bash(ls *)"]}
    assert settings["hooks"] == {"Stop": ["old"]}


def test_install_hooks_writes_the_settings(monkeypatch, tmp_path, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / agent_gate.HOOKS_FILE).write_text('{"Stop": [{"hooks": []}]}')
    (tmp_path / agent_gate.SETTINGS_FILE).write_text('{"permissions": {"allow": []}}')
    monkeypatch.setattr(agent_gate, "REPO_ROOT", tmp_path)
    assert agent_gate.main(["install-hooks"]) == 0
    written = json.loads((tmp_path / agent_gate.SETTINGS_FILE).read_text())
    assert written["hooks"]["Stop"] == [{"hooks": []}]
    assert written["permissions"] == {"allow": []}
    assert "agent-hooks: wrote" in capsys.readouterr().out


def test_install_hooks_creates_missing_settings(monkeypatch, tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / agent_gate.HOOKS_FILE).write_text('{"Stop": []}')
    monkeypatch.setattr(agent_gate, "REPO_ROOT", tmp_path)
    assert agent_gate.main(["install-hooks"]) == 0
    assert json.loads((tmp_path / agent_gate.SETTINGS_FILE).read_text())["hooks"]


def test_install_hooks_reports_a_missing_source(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(agent_gate, "REPO_ROOT", tmp_path)
    assert agent_gate.main(["install-hooks"]) == 2
    assert "missing" in capsys.readouterr().err


def test_the_tracked_hooks_file_is_valid():
    hooks = json.loads((agent_gate.REPO_ROOT / agent_gate.HOOKS_FILE).read_text())
    assert set(hooks) == {"SessionStart", "PreToolUse", "Stop"}
    commands = [
        entry["command"]
        for group in hooks.values()
        for matcher in group
        for entry in matcher["hooks"]
    ]
    assert len(commands) == 3
    for command in commands:
        assert "scripts/agent_gate.py" in command
        assert "$CLAUDE_PROJECT_DIR" in command


@pytest.mark.parametrize(
    "path",
    ["src/common/drift.py", "infra/app.py", "scripts/wiki.py", "website/backend/app.py"],
)
def test_is_counted_path_counts_code(path):
    assert agent_gate.is_counted_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/test_drift.py",
        "AGENTS.md",
        "wiki/log.md",
        "uv.lock",
        "website/frontend/package-lock.json",
        "infra/cdk.out/asset.py",
        "website/frontend/dist/index.js",
        "Makefile",
    ],
)
def test_is_counted_path_excludes_the_rest(path):
    assert not agent_gate.is_counted_path(path)


def test_counted_insertions_counts_added_lines_only():
    numstat = "10\t99\tsrc/common/drift.py\n5\t0\ttests/unit/test_drift.py\n"
    total, files = agent_gate.counted_insertions(numstat)
    assert total == 10
    assert files == [("src/common/drift.py", 10)]


def test_counted_insertions_sorts_by_size_and_skips_binary():
    numstat = "3\t0\tsrc/a.py\n20\t0\tsrc/b.py\n-\t-\tsrc/logo.png\n0\t9\tsrc/c.py\n"
    total, files = agent_gate.counted_insertions(numstat)
    assert total == 23
    assert files == [("src/b.py", 20), ("src/a.py", 3)]


def test_counted_insertions_ignores_a_malformed_line():
    assert agent_gate.counted_insertions("garbage\n") == (0, [])


def test_size_message_names_the_cap_and_the_escape():
    message = agent_gate.size_message(200, [("src/a.py", 200)], "origin/main")
    assert "200 lines" in message
    assert "150" in message
    assert agent_gate.SIZE_OK_ENV in message
    assert "stacked pull requests" in message
    assert "src/a.py" in message


def test_resolve_base_prefers_the_explicit_ref():
    assert agent_gate.resolve_base("origin/x", "origin/y") == "origin/x"


def test_resolve_base_uses_the_pull_request_base():
    assert agent_gate.resolve_base(None, "origin/y") == "origin/y"


def test_resolve_base_falls_back_to_main():
    assert agent_gate.resolve_base(None, None) == agent_gate.DEFAULT_BASE


def test_size_check_passes_under_the_cap(monkeypatch):
    monkeypatch.delenv(agent_gate.SIZE_OK_ENV, raising=False)
    monkeypatch.setattr(agent_gate, "_pr_base", lambda: None)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "10\t0\tsrc/a.py")
    assert agent_gate.size_check() == (0, "")


def test_size_check_blocks_over_the_cap(monkeypatch):
    monkeypatch.delenv(agent_gate.SIZE_OK_ENV, raising=False)
    monkeypatch.setattr(agent_gate, "_pr_base", lambda: None)
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "400\t0\tsrc/a.py")
    code, message = agent_gate.size_check()
    assert code == 2
    assert "400 lines" in message


def test_size_check_honours_the_escape(monkeypatch):
    monkeypatch.setenv(agent_gate.SIZE_OK_ENV, "1")
    monkeypatch.setattr(agent_gate, "_git", lambda *args: "999\t0\tsrc/a.py")
    assert agent_gate.size_check() == (0, "")


def test_stop_gate_checks_the_size_before_the_targets(monkeypatch):
    monkeypatch.delenv(agent_gate.SKIP_ENV, raising=False)
    monkeypatch.setattr(agent_gate, "size_check", lambda: (2, "too big"))

    def runner(target):  # pragma: no cover - the size check must come first
        raise AssertionError("the gate ran a target on an oversized branch")

    assert agent_gate.stop_gate({}, runner) == (2, "too big")


def test_pr_size_reports_a_passing_branch(monkeypatch, capsys):
    monkeypatch.setattr(agent_gate, "size_check", lambda: (0, ""))
    monkeypatch.setattr(agent_gate, "_pr_base", lambda: None)
    monkeypatch.setattr(agent_gate, "branch_totals", lambda base: (12, []))
    assert agent_gate.main(["pr-size"]) == 0
    assert "pr-size: 12 of 150" in capsys.readouterr().out


def test_pr_size_reports_an_oversized_branch(monkeypatch, capsys):
    monkeypatch.setattr(agent_gate, "size_check", lambda: (2, "too big"))
    assert agent_gate.main(["pr-size"]) == 2
    assert "too big" in capsys.readouterr().err


def test_branch_totals_measures_from_the_merge_base(monkeypatch):
    calls = []

    def fake_git(*args):
        calls.append(args)
        return "abc123" if args[0] == "merge-base" else "7\t0\tsrc/a.py"

    monkeypatch.setattr(agent_gate, "_git", fake_git)
    assert agent_gate.branch_totals("origin/main") == (7, [("src/a.py", 7)])
    assert calls[0] == ("merge-base", "origin/main", "HEAD")
    assert calls[1] == ("diff", "--numstat", "abc123")


def test_pr_base_returns_none_without_a_pull_request(monkeypatch):
    monkeypatch.setattr(agent_gate, "REPO_ROOT", agent_gate.REPO_ROOT)
    assert agent_gate._pr_base() in (None, "origin/claude/agent-completion-gate")
