from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
if os.environ.get("QT_QPA_PLATFORM", "") == "offscreen":
    # The offscreen platform uses the freetype font database, which finds no
    # fonts on Windows unless pointed at the system font directory (text
    # otherwise renders as tofu boxes in --screenshot-dir captures).
    os.environ.setdefault("QT_QPA_FONTDIR", "C:\\Windows\\Fonts")

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtQuick import QQuickView
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.graph_theme.tokens import (
    GRAPH_PORT_KIND_TOKENS_V1,
    GRAPH_STITCH_DARK_NODE_TOKENS_V1,
    GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_NODE_TOKENS_V1,
    GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1,
)

MOCKUP_ROOT = Path(__file__).resolve().parent
GALLERY_QML_PATH = MOCKUP_ROOT / "NodeRestyleGallery.qml"
THEME_IDS = ("dark", "light")


def _theme_palettes() -> dict[str, dict[str, dict[str, object]]]:
    return {
        "dark": {
            "node": GRAPH_STITCH_DARK_NODE_TOKENS_V1.as_dict(),
            "port_kind": GRAPH_PORT_KIND_TOKENS_V1.as_dict(),
            "port_state": GRAPH_STITCH_DARK_PORT_STATE_TOKENS_V1.as_dict(),
        },
        "light": {
            "node": GRAPH_STITCH_LIGHT_NODE_TOKENS_V1.as_dict(),
            "port_kind": GRAPH_PORT_KIND_TOKENS_V1.as_dict(),
            "port_state": GRAPH_STITCH_LIGHT_PORT_STATE_TOKENS_V1.as_dict(),
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the node restyle review gallery (real token values + real surface controls).",
    )
    parser.add_argument(
        "--theme",
        choices=("both", *THEME_IDS),
        default="both",
        help="Theme to display.",
    )
    parser.add_argument(
        "--quit-after-ms",
        type=int,
        default=0,
        help="Close the mockup after the given number of milliseconds.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=None,
        help="Write PNG screenshots for the requested theme(s).",
    )
    return parser.parse_args(argv)


def _requested_themes(value: str) -> tuple[str, ...]:
    return THEME_IDS if value == "both" else (value,)


def _create_view(*, theme: str, screenshot_mode: bool) -> QQuickView:
    view = QQuickView()
    view.setTitle("COREX Node Restyle Gallery")
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setColor(QColor("#16181d" if theme != "light" else "#e9edf2"))
    view.setWidth(1180 if theme == "both" else 640)
    view.setHeight(860)
    context = view.engine().rootContext()
    context.setContextProperty("mockupPalettes", _theme_palettes())
    context.setContextProperty("mockupThemeFilter", theme)
    context.setContextProperty("mockupScreenshotMode", screenshot_mode)
    view.setSource(QUrl.fromLocalFile(str(GALLERY_QML_PATH)))
    if view.status() == QQuickView.Status.Error:
        errors = "\n".join(error.toString() for error in view.errors())
        raise RuntimeError(f"Failed to load {GALLERY_QML_PATH.name}:\n{errors}")
    return view


def _pump_events(app: QApplication, count: int = 8) -> None:
    for _ in range(max(1, count)):
        app.processEvents()


def _settle(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(ms), loop.quit)
    loop.exec()


def _capture_screenshots(app: QApplication, args: argparse.Namespace) -> int:
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    for theme in _requested_themes(args.theme):
        view = _create_view(theme=theme, screenshot_mode=True)
        view.show()
        _pump_events(app, 10)
        _settle(220)
        _pump_events(app, 4)
        image = view.grabWindow()
        output_path = screenshot_dir / f"node_restyle_{theme}.png"
        if image.isNull() or not image.save(str(output_path)):
            view.close()
            view.deleteLater()
            raise RuntimeError(f"Could not capture screenshot: {output_path}")
        view.close()
        view.deleteLater()
        _pump_events(app, 4)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    app = QApplication.instance() or QApplication(sys.argv)

    if args.screenshot_dir is not None:
        return _capture_screenshots(app, args)

    view = _create_view(theme=args.theme, screenshot_mode=False)
    view.show()
    if args.quit_after_ms > 0:
        QTimer.singleShot(int(args.quit_after_ms), app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
