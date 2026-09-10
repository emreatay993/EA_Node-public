from __future__ import annotations

import os
import struct
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "ea_node_editor" / "assets" / "app_icon"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
CANVAS_SIZE = 1024.0

DEEP_SPACE = "#0B0F1A"
CORE_BLUE = "#2F6BFF"
ELECTRIC_CYAN = "#00D1FF"
SOFT_GLOW = "#6FA8FF"
GRAPH_GRAY = "#2A2F3A"
NODE_FILL = "#1A2130"


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _svg_prefix(*, transparent: bool, minimal: bool) -> str:
    if minimal:
        return "corex_app_minimal"
    if transparent:
        return "corex_app_transparent"
    return "corex_app"


def _svg_filename(*, transparent: bool, minimal: bool) -> str:
    return f"{_svg_prefix(transparent=transparent, minimal=minimal)}.svg"


def _png_filename(size: int, *, transparent: bool, minimal: bool) -> str:
    return f"{_svg_prefix(transparent=transparent, minimal=minimal)}_{size}.png"


def _build_svg(*, transparent: bool, minimal: bool) -> str:
    cx = cy = CANVAS_SIZE * 0.5
    spread = CANVAS_SIZE * 0.22
    x_pad = CANVAS_SIZE * 0.08
    outer_radius = CANVAS_SIZE * 0.045
    core_radius = CANVAS_SIZE * 0.075
    ring_radius = CANVAS_SIZE * 0.105
    glow_outer_radius = CANVAS_SIZE * 0.14
    glow_inner_radius = CANVAS_SIZE * 0.1
    background_margin = CANVAS_SIZE / 40.0
    background_radius = CANVAS_SIZE / 7.0
    border_width = 8.0
    connection_width = CANVAS_SIZE / 36.0
    x_width = CANVAS_SIZE / 90.0
    node_stroke_width = CANVAS_SIZE / 64.0
    ring_width = CANVAS_SIZE / 96.0

    points = (
        ("tl", (cx - spread, cy - spread)),
        ("tr", (cx + spread, cy - spread)),
        ("bl", (cx - spread, cy + spread)),
        ("br", (cx + spread, cy + spread)),
    )

    gradient_defs: list[str] = []
    connection_lines: list[str] = []
    outer_nodes: list[str] = []
    for gradient_name, (px, py) in points:
        gradient_defs.append(
            f"""
    <linearGradient id="conn-{gradient_name}" x1="{_fmt(px)}" y1="{_fmt(py)}" x2="{_fmt(cx)}" y2="{_fmt(cy)}" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="{CORE_BLUE}"/>
      <stop offset="100%" stop-color="{ELECTRIC_CYAN}"/>
    </linearGradient>""".rstrip()
        )
        connection_lines.append(
            f"""
  <line x1="{_fmt(px)}" y1="{_fmt(py)}" x2="{_fmt(cx)}" y2="{_fmt(cy)}"
        stroke="url(#conn-{gradient_name})"
        stroke-width="{_fmt(connection_width)}"
        stroke-linecap="round"/>""".rstrip()
        )
        node_fill = "none" if minimal else NODE_FILL
        outer_nodes.append(
            f"""
  <circle cx="{_fmt(px)}" cy="{_fmt(py)}" r="{_fmt(outer_radius)}"
          fill="{node_fill}"
          stroke="{CORE_BLUE}"
          stroke-width="{_fmt(node_stroke_width)}"/>""".rstrip()
        )

    background_markup = ""
    if not transparent:
        background_markup = f"""
  <rect x="{_fmt(background_margin)}" y="{_fmt(background_margin)}"
        width="{_fmt(CANVAS_SIZE - background_margin * 2.0)}"
        height="{_fmt(CANVAS_SIZE - background_margin * 2.0)}"
        rx="{_fmt(background_radius)}"
        fill="{DEEP_SPACE}"/>
  <rect x="{_fmt(background_margin + border_width * 0.5)}" y="{_fmt(background_margin + border_width * 0.5)}"
        width="{_fmt(CANVAS_SIZE - (background_margin + border_width * 0.5) * 2.0)}"
        height="{_fmt(CANVAS_SIZE - (background_margin + border_width * 0.5) * 2.0)}"
        rx="{_fmt(background_radius - border_width * 0.5)}"
        fill="none"
        stroke="{GRAPH_GRAY}"
        stroke-width="{_fmt(border_width)}"/>""".rstrip()

    x1 = cx - spread + x_pad
    y1 = cy - spread + x_pad
    x2 = cx + spread - x_pad
    y2 = cy + spread - x_pad

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
{"".join(gradient_defs)}
    <radialGradient id="core-gradient" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{ELECTRIC_CYAN}"/>
      <stop offset="100%" stop-color="{CORE_BLUE}"/>
    </radialGradient>
  </defs>
{background_markup}
  <circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(glow_outer_radius)}" fill="{SOFT_GLOW}" fill-opacity="0.10"/>
  <circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(glow_inner_radius)}" fill="{SOFT_GLOW}" fill-opacity="0.22"/>
{"".join(connection_lines)}
  <line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}"
        stroke="{SOFT_GLOW}"
        stroke-opacity="0.92"
        stroke-width="{_fmt(x_width)}"
        stroke-linecap="round"/>
  <line x1="{_fmt(x2)}" y1="{_fmt(y1)}" x2="{_fmt(x1)}" y2="{_fmt(y2)}"
        stroke="{SOFT_GLOW}"
        stroke-opacity="0.92"
        stroke-width="{_fmt(x_width)}"
        stroke-linecap="round"/>
{"".join(outer_nodes)}
  <circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(core_radius)}" fill="url(#core-gradient)"/>
  <circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(ring_radius)}"
          fill="none"
          stroke="{SOFT_GLOW}"
          stroke-opacity="0.35"
          stroke-width="{_fmt(ring_width)}"/>
</svg>
"""


def _render_svg(svg_path: Path, size: int, output_path: Path) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Failed to load SVG: {svg_path}")

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0.0, 0.0, float(size), float(size)))
    painter.end()

    if not image.save(str(output_path), "PNG"):
        raise RuntimeError(f"Failed to save PNG: {output_path}")


def _write_ico(ico_path: Path, png_paths: tuple[Path, ...]) -> None:
    entries: list[bytes] = []
    payloads: list[bytes] = []
    offset = 6 + 16 * len(png_paths)

    for png_path in png_paths:
        size = int(png_path.stem.rsplit("_", 1)[-1])
        data = png_path.read_bytes()
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                width,
                height,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        payloads.append(data)
        offset += len(data)

    header = struct.pack("<HHH", 0, 1, len(png_paths))
    ico_path.write_bytes(header + b"".join(entries) + b"".join(payloads))


def _write_variant(*, transparent: bool, minimal: bool) -> tuple[Path, ...]:
    svg_path = OUTPUT_DIR / _svg_filename(transparent=transparent, minimal=minimal)
    svg_path.write_text(_build_svg(transparent=transparent, minimal=minimal), encoding="utf-8")

    png_paths: list[Path] = []
    for size in ICON_SIZES:
        png_path = OUTPUT_DIR / _png_filename(size, transparent=transparent, minimal=minimal)
        _render_svg(svg_path, size, png_path)
        png_paths.append(png_path)
    return tuple(png_paths)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    app = QGuiApplication.instance() or QGuiApplication([])
    _ = app

    opaque_pngs = _write_variant(transparent=False, minimal=False)
    _write_variant(transparent=True, minimal=False)
    _write_variant(transparent=True, minimal=True)

    ico_sources = tuple(path for path in opaque_pngs if int(path.stem.rsplit("_", 1)[-1]) in ICO_SIZES)
    _write_ico(OUTPUT_DIR / "corex_app.ico", ico_sources)

    generated = sorted(path.name for path in OUTPUT_DIR.iterdir())
    print(f"Wrote {len(generated)} files to {OUTPUT_DIR}")
    for name in generated:
        print(f" - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
