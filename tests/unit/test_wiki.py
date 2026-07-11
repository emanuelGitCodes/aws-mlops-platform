from pathlib import Path

import pytest

from scripts.wiki import Wiki, WikiError, main


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
    repo_root = Path(__file__).resolve().parents[2]
    errors = Wiki(repo_root / "wiki").lint()
    assert errors == []
