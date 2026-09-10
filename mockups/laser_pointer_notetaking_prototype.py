"""Laser Pointer + notetaking prototype (standalone, throwaway).

Run:        python mockups/laser_pointer_notetaking_prototype.py
Self-test:  python mockups/laser_pointer_notetaking_prototype.py --selftest   (offscreen, auto-quits)
Screenshot: python mockups/laser_pointer_notetaking_prototype.py --shot out.png
            (combine with --pen-popover [--pen-variant-ball|--pen-variant-brush]
            or --pen-gestures to capture the pen options flyout states)

Needs only PyQt6 (already a project dependency). Nothing here touches the app.
Purpose: feel the neon trail + whole-stroke fade-on-stop timing before integration.

Renderer: GPU-retained QtQuick.Shapes (the production technique), not Canvas/shadowBlur.
Defaults below are the locked line-laser behaviors signed off from the prototype.

Ctrl-to-pin: hold Ctrl while left-dragging to lay multiple discontinuous lines that do
not fade; release Ctrl to let them all dissolve together; Esc clears immediately.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
# Imported for the side effect of registering the QQuickWindow wrapper type:
# without it, rootObjects()[0] is wrapped as plain QWindow and grabWindow()
# resolves into a native crash (0xC0000409) instead of an AttributeError.
from PyQt6.QtQuick import QQuickWindow


QML_DIR = Path(__file__).with_name("laser_pointer_notetaking")
QML_ENTRY = QML_DIR / "Main.qml"


def main() -> int:
    selftest = "--selftest" in sys.argv
    shot_path: str | None = None
    if "--shot" in sys.argv:
        idx = sys.argv.index("--shot")
        if idx + 1 >= len(sys.argv):
            print("--shot requires an output path", file=sys.stderr)
            return 2
        shot_path = sys.argv[idx + 1]
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.load(QUrl.fromLocalFile(str(QML_ENTRY)))
    if not engine.rootObjects():
        print(f"QML load FAILED: {QML_ENTRY}", file=sys.stderr)
        return 1
    if "--win-size" in sys.argv:
        idx = sys.argv.index("--win-size")
        if idx + 1 < len(sys.argv) and "x" in sys.argv[idx + 1]:
            w, h = sys.argv[idx + 1].lower().split("x", 1)
            engine.rootObjects()[0].setProperty("width", int(w))
            engine.rootObjects()[0].setProperty("height", int(h))
    if shot_path:
        def grab() -> None:
            window = engine.rootObjects()[0]
            if not isinstance(window, QQuickWindow):
                print(f"SHOT FAILED: root object is {type(window).__name__}", file=sys.stderr)
                app.exit(1)
                return
            image = window.grabWindow()
            ok = not image.isNull() and image.save(shot_path)
            print(f"SHOT {'SAVED' if ok else 'FAILED'}: {shot_path}")
            app.quit()
        QTimer.singleShot(1400, grab)
        return app.exec()
    if selftest:
        window = engine.rootObjects()[0]
        toolbar = window.findChild(QObject, "writingToolsFloatingToolbar")
        if toolbar is None:
            print("SELFTEST FAILED: writing toolbar not found", file=sys.stderr)
            return 1
        toolbar_host = toolbar.parent()

        def toolbar_colors() -> list[str]:
            value = toolbar.property("toolbarColors")
            if hasattr(value, "toVariant"):
                value = value.toVariant()
            return [str(color) for color in value]

        def verify_laser_submenu_dismissal() -> None:
            getattr(toolbar_host, "activateTool")("laser", "laser")
            getattr(toolbar_host, "closeLaserSubmenu")()
            if (
                str(toolbar_host.property("activeTool")) != "laser"
                or str(toolbar_host.property("activePanelKind")) != ""
                or not bool(toolbar_host.property("laserActive"))
            ):
                print("SELFTEST FAILED: dismissing the laser submenu deactivated the laser", file=sys.stderr)
                app.exit(1)
                return
            select_pen()

        def select_pen() -> None:
            toolbar.setProperty("visible", True)
            getattr(toolbar, "chooseDrawingTool")("pen")
            QTimer.singleShot(150, capture_pen_geometry)

        def capture_pen_geometry() -> None:
            pen_x = float(toolbar.property("x"))
            pen_width = float(toolbar.property("width"))
            getattr(toolbar, "chooseDrawingTool")("highlighter")
            QTimer.singleShot(150, lambda: verify_highlighter_geometry(pen_x, pen_width))

        def verify_highlighter_geometry(pen_x: float, pen_width: float) -> None:
            highlighter_x = float(toolbar.property("x"))
            highlighter_width = float(toolbar.property("width"))
            if highlighter_width <= pen_width or abs(highlighter_x - pen_x) > 0.5:
                print(
                    "SELFTEST FAILED: writing toolbar must grow right without moving its left edge",
                    file=sys.stderr,
                )
                app.exit(1)
                return
            verify_add_color()

        def verify_add_color() -> None:
            before = toolbar_colors()
            duplicate = before[-1]
            getattr(toolbar, "toggleColorPanel")(False, "add")
            getattr(toolbar, "chooseColor")(duplicate)
            after = toolbar_colors()
            if after != before + [duplicate] or int(toolbar.property("selectedColorIndex")) != len(before):
                print("SELFTEST FAILED: Add Color must append and select a new slot", file=sys.stderr)
                app.exit(1)
                return

            getattr(toolbar, "toggleColorPanel")(True, "add")
            getattr(toolbar, "setHsv")(0.0, 1.0, 1.0)
            preview_colors = toolbar_colors()
            getattr(toolbar, "closeColorPanel")()
            if preview_colors != after or toolbar_colors() != after:
                print("SELFTEST FAILED: Add Color preview or cancel changed existing slots", file=sys.stderr)
                app.exit(1)
                return
            app.quit()

        QTimer.singleShot(300, verify_laser_submenu_dismissal)
        rc = app.exec()
        if rc == 0:
            print("SELFTEST OK")
        return rc
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
