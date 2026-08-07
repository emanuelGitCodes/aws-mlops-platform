from pathlib import Path

import pytest

from scripts.wiki import Wiki, WikiError, main
from tests.unit.conftest import REPO_ROOT


def test_add_source_is_copy_once_and_scaffolds_page(tmp_path: Path):
    source = tmp_path / "notes.md"
    source.write_text("A source about drift and retraining.\n", encoding="utf-8")
    wiki = Wiki(tmp_path / "wiki")

    raw_path, page_path = wiki.add_source(source, title="Drift notes")

    assert raw_path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert page_path.exists()
    assert "Drift notes" in wiki.index_path.read_text(encoding="utf-8")
    assert "ingest | Drift notes" in wiki.log_path.read_text(encoding="utf-8")

    source.write_text("changed after registration\n", encoding="utf-8")
    assert raw_path.read_text(encoding="utf-8") == "A source about drift and retraining.\n"

    with pytest.raises(WikiError, match="already exists"):
        wiki.add_source(source, title="Drift notes")


def test_search_ranks_matching_pages(tmp_path: Path):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    page = wiki.page_root / "concepts" / "drift.md"
    page.write_text(
        (
            "---\n"
            "type: concept\n"
            "title: Drift\n"
            'created: "2026-07-10"\n'
            'updated: "2026-07-10"\n'
            'sources: ["../../README.md"]\n'
            'summary: "Drift and retraining"\n'
            "---\n"
            "# Drift\n\nDrift triggers retraining.\n"
        ),
        encoding="utf-8",
    )
    wiki.rebuild_index()

    results = wiki.search("drift retraining")

    assert results[0].path == page
    assert results[0].score >= 2


def test_lint_reports_broken_links_and_orphans(tmp_path: Path):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    page = wiki.page_root / "concepts" / "broken.md"
    page.write_text(
        (
            "---\n"
            "type: concept\n"
            "title: Broken\n"
            'created: "2026-07-10"\n'
            'updated: "2026-07-10"\n'
            'sources: ["../../missing.md"]\n'
            'summary: "Broken page"\n'
            "---\n"
            "# Broken\n\n[missing](../nope.md)\n"
        ),
        encoding="utf-8",
    )

    errors = wiki.lint()

    assert any("missing source reference" in error for error in errors)
    assert any("broken link" in error for error in errors)
    assert any("stale" in error for error in errors)


def test_successful_lint_does_not_append_to_log(tmp_path: Path):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    before = wiki.log_path.read_text(encoding="utf-8")

    assert main(["--wiki-root", str(wiki.root), "lint"]) == 0

    assert wiki.log_path.read_text(encoding="utf-8") == before


def test_repo_wiki_is_healthy():
    errors = Wiki(REPO_ROOT / "wiki").lint()
    assert errors == []


# `main` is the dispatch behind `make wiki-lint`, a blocking CI gate. These
# tests cover each subcommand's target method and the exit codes that separate
# "the wiki is broken" from "the command failed".


def _run(wiki: Wiki, *argv: str) -> int:
    return main(["--wiki-root", str(wiki.root), *argv])


def test_init_creates_the_wiki(tmp_path: Path, capsys):
    wiki = Wiki(tmp_path / "wiki")

    assert _run(wiki, "init") == 0

    assert wiki.index_path.exists() and wiki.page_root.is_dir()
    assert str(wiki.root) in capsys.readouterr().out


def test_index_rebuilds_from_page_frontmatter(tmp_path: Path, capsys):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    _write_page(wiki, "indexed.md", title="Indexed", summary="Indexed page")

    assert _run(wiki, "index") == 0

    assert "Indexed" in wiki.index_path.read_text(encoding="utf-8")
    assert str(wiki.index_path) in capsys.readouterr().out


def test_add_source_registers_and_scaffolds(tmp_path: Path, capsys):
    wiki = Wiki(tmp_path / "wiki")
    source = tmp_path / "notes.md"
    source.write_text("Notes about drift.\n", encoding="utf-8")

    assert _run(wiki, "add-source", str(source), "--title", "Drift notes") == 0

    out = capsys.readouterr().out
    assert "Registered" in out and "scaffolded" in out
    assert "ingest | Drift notes" in wiki.log_path.read_text(encoding="utf-8")


def test_search_prints_ranked_hits_and_records_the_query(tmp_path: Path, capsys):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    _write_page(wiki, "drift.md", title="Drift", summary="Drift and retraining")
    wiki.rebuild_index()

    assert _run(wiki, "search", "drift") == 0

    assert "drift.md" in capsys.readouterr().out
    # A search is a recorded operation, even though it changes no page.
    assert "query | drift" in wiki.log_path.read_text(encoding="utf-8")


def test_search_without_matches_says_so(tmp_path: Path, capsys):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()

    assert _run(wiki, "search", "nonexistent-term") == 0

    assert "No matches." in capsys.readouterr().out


def test_log_appends_the_named_operation(tmp_path: Path):
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()

    assert _run(wiki, "log", "lint", "--title", "Manual", "--details", "checked by hand") == 0

    log = wiki.log_path.read_text(encoding="utf-8")
    assert "lint | Manual" in log and "checked by hand" in log


def test_failing_lint_exits_1_and_prints_each_error(tmp_path: Path, capsys):
    """Exit 1 is what makes `make wiki-lint` block; a broken wiki must not exit 0."""
    wiki = Wiki(tmp_path / "wiki")
    wiki.init()
    _write_page(wiki, "broken.md", title="Broken", summary="Broken", sources="../../missing.md")

    assert _run(wiki, "lint") == 1

    assert "ERROR:" in capsys.readouterr().out


def test_a_wiki_error_exits_2_not_1(tmp_path: Path, capsys):
    """Exit 2 separates "the command failed" from lint's "the wiki is unhealthy"."""
    wiki = Wiki(tmp_path / "wiki")

    assert _run(wiki, "add-source", str(tmp_path / "absent.md")) == 2

    assert "ERROR:" in capsys.readouterr().err


def _write_page(
    wiki: Wiki, name: str, *, title: str, summary: str, sources: str = "../../README.md"
):
    page = wiki.page_root / "concepts" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        (
            "---\n"
            "type: concept\n"
            f"title: {title}\n"
            'created: "2026-07-10"\n'
            'updated: "2026-07-10"\n'
            f'sources: ["{sources}"]\n'
            f'summary: "{summary}"\n'
            "---\n"
            f"# {title}\n\n{summary}\n"
        ),
        encoding="utf-8",
    )
    return page
