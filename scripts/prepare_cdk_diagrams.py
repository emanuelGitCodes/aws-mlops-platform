#!/usr/bin/env python3
"""Prepare portable DOT and SVG files from cdk-dia output.

`cdk-dia` writes workstation-specific icon paths into its DOT output. This
script copies the required icons. It embeds them in each SVG file.
"""

import argparse
import base64
import hashlib
import mimetypes
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path
from typing import cast

ICON_DIR_NAME = "cdk-dia-icons"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
XLINK_HREF = f"{{{XLINK_NAMESPACE}}}href"
DOT_IMAGE_PATTERN = re.compile(r'(?P<start>\bimage\s*=\s*")(?P<path>[^"]+)(?P<end>"\s*;)')

ET.register_namespace("", SVG_NAMESPACE)
ET.register_namespace("xlink", XLINK_NAMESPACE)


def _portable_icon_path(source: Path) -> Path:
    """Return a stable path for one source icon."""
    parts = source.parts
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == ("cdk-dia", "icons"):
            return Path(*parts[index + 2 :])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return Path("external") / f"{digest}-{source.name}"


def _normalize_icon(
    raw_path: str,
    dot_path: Path,
    copied: dict[str, str],
) -> str:
    """Copy an absolute icon. Return its portable DOT path."""
    if raw_path in copied:
        return copied[raw_path]

    source = Path(raw_path)
    if not source.is_absolute():
        if not (dot_path.parent / source).is_file():
            raise FileNotFoundError(f"The diagram icon does not exist: {raw_path}")
        copied[raw_path] = source.as_posix()
        return copied[raw_path]

    if not source.is_file():
        raise FileNotFoundError(f"The diagram icon does not exist: {raw_path}")

    icon_dir = dot_path.parent / ICON_DIR_NAME
    target = icon_dir / _portable_icon_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    portable_path = Path(os.path.relpath(target, dot_path.parent)).as_posix()
    copied[raw_path] = portable_path
    return portable_path


def normalize_dot(dot_path: Path) -> int:
    """Replace workstation icon paths in one DOT file."""
    dot_path = dot_path.resolve()
    source_text = dot_path.read_text(encoding="utf-8")
    copied: dict[str, str] = {}

    def replace_image(match: re.Match[str]) -> str:
        portable_path = _normalize_icon(match.group("path"), dot_path, copied)
        return f"{match.group('start')}{portable_path}{match.group('end')}"

    portable_text, image_count = DOT_IMAGE_PATTERN.subn(replace_image, source_text)
    dot_path.write_text(portable_text, encoding="utf-8")
    return image_count


def render_svg(dot_path: Path) -> Path:
    """Render one DOT file as SVG from its own directory."""
    dot_path = dot_path.resolve()
    svg_path = dot_path.with_suffix(".svg")
    subprocess.run(
        ["dot", "-Tsvg", dot_path.name, "-o", svg_path.name],
        cwd=dot_path.parent,
        check=True,
    )
    return svg_path


def _data_uri(source: Path) -> tuple[str, str]:
    """Return an icon digest and its data URI."""
    media_type = mimetypes.guess_type(source.name)[0]
    if media_type is None:
        raise ValueError(f"The diagram icon has no media type: {source}")
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()[:16]
    encoded = base64.b64encode(content).decode("ascii")
    return digest, f"data:{media_type};base64,{encoded}"


def embed_svg_images(svg_path: Path) -> int:
    """Embed external SVG images once. Replace their references."""
    svg_path = svg_path.resolve()
    tree = ET.parse(svg_path)
    root = tree.getroot()
    image_tag = f"{{{SVG_NAMESPACE}}}image"
    symbol_tag = f"{{{SVG_NAMESPACE}}}symbol"
    use_tag = f"{{{SVG_NAMESPACE}}}use"
    images = list(root.iter(image_tag))
    parents = {child: parent for parent in root.iter() for child in parent}
    definitions = ET.Element(f"{{{SVG_NAMESPACE}}}defs")
    symbols: dict[str, str] = {}
    embedded_count = 0

    for image in images:
        href = image.get(XLINK_HREF) or image.get("href")
        if href is None or href.startswith(("data:", "#")):
            continue
        source = Path(href)
        if not source.is_absolute():
            source = svg_path.parent / source
        if not source.is_file():
            raise FileNotFoundError(f"The SVG image does not exist: {href}")

        digest, data_uri = _data_uri(source)
        symbol_id = symbols.get(digest)
        if symbol_id is None:
            symbol_id = f"cdk-dia-icon-{digest}"
            symbols[digest] = symbol_id
            symbol = ET.SubElement(
                definitions,
                symbol_tag,
                {
                    "id": symbol_id,
                    "viewBox": "0 0 1 1",
                    "preserveAspectRatio": image.get("preserveAspectRatio", "xMidYMid meet"),
                },
            )
            ET.SubElement(
                symbol,
                image_tag,
                {
                    "x": "0",
                    "y": "0",
                    "width": "1",
                    "height": "1",
                    XLINK_HREF: data_uri,
                },
            )

        use_attributes = dict(image.attrib)
        use_attributes.pop(XLINK_HREF, None)
        use_attributes.pop("href", None)
        use_attributes[XLINK_HREF] = f"#{symbol_id}"
        use = ET.Element(use_tag, use_attributes)
        parent = parents[image]
        position = list(parent).index(image)
        parent.remove(image)
        parent.insert(position, use)
        embedded_count += 1

    if embedded_count == 0:
        return 0
    root.insert(0, definitions)
    ET.indent(tree, space="  ")
    tree.write(svg_path, encoding="utf-8", xml_declaration=True)
    return embedded_count


def prepare_diagram(dot_path: Path) -> Path:
    """Prepare one DOT file and its self-contained SVG file."""
    normalize_dot(dot_path)
    svg_path = render_svg(dot_path)
    embed_svg_images(svg_path)
    return svg_path


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Prepare portable DOT and self-contained SVG diagrams."
    )
    parser.add_argument("dot_paths", nargs="+", type=Path, help="DOT files to prepare")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare every requested diagram."""
    args = build_parser().parse_args(argv)
    dot_paths = cast(list[Path], args.dot_paths)
    for dot_path in dot_paths:
        svg_path = prepare_diagram(dot_path)
        print(f"Prepared editable diagram: {dot_path} and {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
