"""Render the saved design SVGs to PNG without starting COREX or Mechanical."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def main() -> None:
    root = Path(__file__).resolve().parent
    app = QGuiApplication.instance() or QGuiApplication([])
    for font in ("arial.ttf", "arialbd.ttf"):
        font_path = Path("C:/Windows/Fonts") / font
        if font_path.is_file():
            assert QFontDatabase.addApplicationFont(str(font_path)) >= 0
    app.setFont(QFont("Arial"))
    for source in sorted(root.glob("*.svg")):
        renderer = QSvgRenderer(str(source))
        assert renderer.isValid(), source
        size = renderer.defaultSize()
        assert size.width() > 0 and size.height() > 0, source
        target = source.with_suffix(".png")
        bitmap = QImage(size, QImage.Format.Format_ARGB32)
        bitmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(bitmap)
        renderer.render(painter)
        painter.end()
        assert bitmap.save(str(target), "PNG"), target
        print(f"Rendered {target.name}: {size.width()} x {size.height()}")
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".svg", ".png", ".json", ".py"} and p.name != "manifest.json")
    manifest = {
        "kind": "planning-visual-references",
        "production_qml_proof": False,
        "files": [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
