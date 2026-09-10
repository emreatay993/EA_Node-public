from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtQuick import QQuickView
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.icon_registry import (
    UI_ICON_PROVIDER_ID,
    UiIconImageProvider,
    UiIconRegistryBridge,
)

MOCKUP_ROOT = Path(__file__).resolve().parent
GALLERY_QML_PATH = MOCKUP_ROOT / "SelectionToolbarGallery.qml"
VARIANT_IDS = ("1", "2", "3", "4")
THEME_IDS = ("dark", "light")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch selection envelope toolbar QML mockups.",
    )
    parser.add_argument(
        "--variant",
        choices=("all", *VARIANT_IDS),
        default="all",
        help="Variant to display.",
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
        help="Write PNG screenshots for the requested variant/theme combinations.",
    )
    return parser.parse_args(argv)


def _requested_variants(value: str) -> tuple[str, ...]:
    return VARIANT_IDS if value == "all" else (value,)


def _requested_themes(value: str) -> tuple[str, ...]:
    return THEME_IDS if value == "both" else (value,)


def _register_mockup_context(view: QQuickView, *, variant: str, theme: str, screenshot_mode: bool) -> None:
    engine = view.engine()
    engine.addImageProvider(UI_ICON_PROVIDER_ID, UiIconImageProvider())
    context = engine.rootContext()
    context.setContextProperty("uiIcons", UiIconRegistryBridge())
    context.setContextProperty("mockupVariantFilter", variant)
    context.setContextProperty("mockupThemeFilter", theme)
    context.setContextProperty("mockupScreenshotMode", screenshot_mode)


def _create_view(*, variant: str, theme: str, screenshot_mode: bool) -> QQuickView:
    view = QQuickView()
    view.setTitle("COREX Selection Envelope Toolbar Mockups")
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setColor(QColor("#1d1f24"))
    view.setWidth(1280 if screenshot_mode else 1460)
    view.setHeight(860 if screenshot_mode else 960)
    _register_mockup_context(view, variant=variant, theme=theme, screenshot_mode=screenshot_mode)
    view.setSource(QUrl.fromLocalFile(str(GALLERY_QML_PATH)))
    if view.status() == QQuickView.Status.Error:
        errors = "\n".join(error.toString() for error in view.errors())
        raise RuntimeError(f"Failed to load {GALLERY_QML_PATH.name}:\n{errors}")
    return view


def _pump_events(app: QApplication, count: int = 8) -> None:
    for _ in range(max(1, count)):
        app.processEvents()


def _capture_screenshots(app: QApplication, args: argparse.Namespace) -> int:
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    for variant in _requested_variants(args.variant):
        for theme in _requested_themes(args.theme):
            view = _create_view(variant=variant, theme=theme, screenshot_mode=True)
            view.show()
            _pump_events(app, 12)
            image = view.grabWindow()
            output_path = screenshot_dir / f"selection_toolbar_variant_{variant}_{theme}.png"
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

    view = _create_view(
        variant=args.variant,
        theme=args.theme,
        screenshot_mode=False,
    )
    view.show()
    if args.quit_after_ms > 0:
        QTimer.singleShot(int(args.quit_after_ms), app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
