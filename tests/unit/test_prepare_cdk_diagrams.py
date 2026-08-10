import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest

from scripts import prepare_cdk_diagrams as diagrams


def test_normalize_dot_copies_cdk_icon(tmp_path: Path) -> None:
    icon = tmp_path / "cache" / "cdk-dia" / "icons" / "aws" / "icon.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"icon")
    dot_path = tmp_path / "output" / "diagram.dot"
    dot_path.parent.mkdir()
    dot_path.write_text(f'digraph {{ node [image = "{icon}";] }}', encoding="utf-8")

    assert diagrams.normalize_dot(dot_path) == 1
    assert 'image = "cdk-dia-icons/aws/icon.png"' in dot_path.read_text()
    assert (dot_path.parent / "cdk-dia-icons" / "aws" / "icon.png").read_bytes() == b"icon"

    assert diagrams.normalize_dot(dot_path) == 1


def test_normalize_dot_copies_repeated_icon_once(tmp_path: Path) -> None:
    icon = tmp_path / "cache" / "cdk-dia" / "icons" / "aws" / "icon.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"icon")
    dot_path = tmp_path / "diagram.dot"
    dot_path.write_text(
        f'digraph {{ first [image = "{icon}";] second [image = "{icon}";] }}',
        encoding="utf-8",
    )

    with mock.patch.object(
        diagrams.shutil,
        "copyfile",
        wraps=diagrams.shutil.copyfile,
    ) as copyfile:
        assert diagrams.normalize_dot(dot_path) == 2

    assert copyfile.call_count == 1


def test_normalize_dot_hashes_external_icon(tmp_path: Path) -> None:
    icon = tmp_path / "source.png"
    icon.write_bytes(b"external")
    dot_path = tmp_path / "diagram.dot"
    dot_path.write_text(f'digraph {{ node [image = "{icon}";] }}', encoding="utf-8")

    diagrams.normalize_dot(dot_path)

    text = dot_path.read_text(encoding="utf-8")
    assert 'image = "cdk-dia-icons/external/' in text
    assert "-source.png" in text


@pytest.mark.parametrize("raw_path", ["missing.png", "/missing/icon.png"])
def test_normalize_dot_rejects_missing_icon(tmp_path: Path, raw_path: str) -> None:
    dot_path = tmp_path / "diagram.dot"
    dot_path.write_text(f'digraph {{ node [image = "{raw_path}";] }}', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="diagram icon does not exist"):
        diagrams.normalize_dot(dot_path)


def test_embed_svg_images_deduplicates_icons(tmp_path: Path) -> None:
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"icon")
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        f"""<svg xmlns="{diagrams.SVG_NAMESPACE}"
        xmlns:xlink="{diagrams.XLINK_NAMESPACE}">
        <g>
          <image xlink:href="icon.png" x="1" y="2" width="3" height="4" />
          <image href="icon.png" x="5" y="6" width="7" height="8" />
          <image xlink:href="data:image/png;base64,AA==" />
          <image xlink:href="#existing" />
          <image />
        </g>
        </svg>""",
        encoding="utf-8",
    )

    assert diagrams.embed_svg_images(svg_path) == 2

    root = ET.parse(svg_path).getroot()
    symbol_tag = f"{{{diagrams.SVG_NAMESPACE}}}symbol"
    use_tag = f"{{{diagrams.SVG_NAMESPACE}}}use"
    image_tag = f"{{{diagrams.SVG_NAMESPACE}}}image"
    symbols = list(root.iter(symbol_tag))
    uses = list(root.iter(use_tag))
    assert len(symbols) == 1
    assert len(uses) == 2
    assert uses[0].get(diagrams.XLINK_HREF) == uses[1].get(diagrams.XLINK_HREF)
    embedded_image = next(symbols[0].iter(image_tag))
    assert embedded_image.get(diagrams.XLINK_HREF, "").startswith("data:image/png;base64,")


def test_embed_svg_images_returns_zero_without_external_icons(tmp_path: Path) -> None:
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        f'<svg xmlns="{diagrams.SVG_NAMESPACE}"><path d="M 0 0" /></svg>',
        encoding="utf-8",
    )

    assert diagrams.embed_svg_images(svg_path) == 0


def test_embed_svg_images_rejects_missing_icon(tmp_path: Path) -> None:
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        f"""<svg xmlns="{diagrams.SVG_NAMESPACE}"
        xmlns:xlink="{diagrams.XLINK_NAMESPACE}">
        <image xlink:href="missing.png" />
        </svg>""",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="SVG image does not exist"):
        diagrams.embed_svg_images(svg_path)


def test_embed_svg_images_rejects_unknown_media_type(tmp_path: Path) -> None:
    icon = tmp_path / "icon.unknown-extension"
    icon.write_bytes(b"icon")
    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        f"""<svg xmlns="{diagrams.SVG_NAMESPACE}"
        xmlns:xlink="{diagrams.XLINK_NAMESPACE}">
        <image xlink:href="{icon.name}" />
        </svg>""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no media type"):
        diagrams.embed_svg_images(svg_path)


def test_prepare_diagram_runs_graphviz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dot_path = tmp_path / "diagram.dot"
    dot_path.write_text("digraph {}", encoding="utf-8")
    calls: list[tuple[list[str], Path, bool]] = []

    def run(args: list[str], *, cwd: Path, check: bool) -> None:
        calls.append((args, cwd, check))
        (cwd / "diagram.svg").write_text(
            f'<svg xmlns="{diagrams.SVG_NAMESPACE}" />', encoding="utf-8"
        )

    monkeypatch.setattr(diagrams.subprocess, "run", run)

    assert diagrams.prepare_diagram(dot_path) == dot_path.with_suffix(".svg")
    assert calls == [(["dot", "-Tsvg", "diagram.dot", "-o", "diagram.svg"], tmp_path, True)]


def test_main_prepares_each_diagram(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared: list[Path] = []

    def prepare(dot_path: Path) -> Path:
        prepared.append(dot_path)
        return dot_path.with_suffix(".svg")

    monkeypatch.setattr(diagrams, "prepare_diagram", prepare)
    first = tmp_path / "first.dot"
    second = tmp_path / "second.dot"

    assert diagrams.main([str(first), str(second)]) == 0
    assert prepared == [first, second]
    assert capsys.readouterr().out.count("Prepared editable diagram") == 2
