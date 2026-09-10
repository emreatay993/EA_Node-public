"""Export Mermaid diagrams from ARCHITECTURE.md to SVG and PNG files.

Output directory:
    docs/architecture_diagrams/
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_MD = ROOT / "ARCHITECTURE.md"
OUTPUT_DIR = ROOT / "docs" / "architecture_diagrams"
KROKI_BASE_URL = "https://kroki.io/mermaid"
_APP: QGuiApplication | None = None

# Order matches Mermaid blocks in ARCHITECTURE.md.
DIAGRAM_BASENAMES = [
    "component_map",
    "runtime_pipeline",
    "run_sequence",
]


def _extract_mermaid_blocks(markdown_text: str) -> list[str]:
    pattern = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
    return [match.strip() for match in pattern.findall(markdown_text)]


def _render_with_kroki(diagram_source: str, fmt: str) -> bytes:
    url = f"{KROKI_BASE_URL}/{fmt}"
    request = urllib.request.Request(
        url=url,
        data=diagram_source.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "text/plain",
            "User-Agent": "corex-node-editor-architecture-export/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _render_png_from_svg(svg_bytes: bytes) -> bytes:
    global _APP
    if QGuiApplication.instance() is None:
        _APP = QGuiApplication([])

    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        raise RuntimeError("QtSvg could not load the generated SVG data.")

    size = renderer.defaultSize()
    width = max(1, size.width())
    height = max(1, size.height())

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(0)

    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Qt could not encode PNG output.")
    return bytes(buffer.data())


def main() -> int:
    if not ARCHITECTURE_MD.exists():
        print(f"ERROR: File not found: {ARCHITECTURE_MD}")
        return 1

    markdown_text = ARCHITECTURE_MD.read_text(encoding="utf-8")
    mermaid_blocks = _extract_mermaid_blocks(markdown_text)

    if len(mermaid_blocks) < len(DIAGRAM_BASENAMES):
        print(
            "ERROR: Not enough Mermaid blocks found in ARCHITECTURE.md. "
            f"Expected at least {len(DIAGRAM_BASENAMES)}, found {len(mermaid_blocks)}."
        )
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for basename, source in zip(DIAGRAM_BASENAMES, mermaid_blocks):
        mmd_path = OUTPUT_DIR / f"{basename}.mmd"
        mmd_path.write_text(source + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {mmd_path.relative_to(ROOT)}")

        try:
            svg_bytes = _render_with_kroki(source, "svg")
        except urllib.error.HTTPError as err:
            print(f"ERROR: HTTP {err.code} while rendering {basename}.svg")
            return 1
        except urllib.error.URLError as err:
            print(f"ERROR: Network error while rendering {basename}.svg: {err}")
            return 1

        svg_path = OUTPUT_DIR / f"{basename}.svg"
        svg_path.write_bytes(svg_bytes)
        print(f"Wrote {svg_path.relative_to(ROOT)}")

        try:
            png_bytes = _render_png_from_svg(svg_bytes)
        except RuntimeError as err:
            print(f"ERROR: Could not render {basename}.png locally: {err}")
            return 1

        png_path = OUTPUT_DIR / f"{basename}.png"
        png_path.write_bytes(png_bytes)
        print(f"Wrote {png_path.relative_to(ROOT)}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
