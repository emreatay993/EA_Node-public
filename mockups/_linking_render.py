"""Throwaway: render a posed linking-concept QML to a PNG for visual diffing.

Usage:
    python mockups/_linking_render.py <out.png> <_RenderX.qml> [dark|light]

The entry QML is resolved inside mockups/linking_feature/. Each _RenderX.qml is a
plain Rectangle root that poses one concept in an "open" state (grabWindow() is a
single static frame and can't drive interaction). The 3rd arg selects the theme
(default dark) and is exposed to QML as the `themeDark` context property.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_SCALE_FACTOR", "2")

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQuick import QQuickView

QML_DIR = Path(__file__).with_name("linking_feature")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else QML_DIR / "_RenderA.png"
    entry = QML_DIR / (sys.argv[2] if len(sys.argv) > 2 else "_RenderA.qml")
    dark = True
    if len(sys.argv) > 3:
        dark = sys.argv[3].lower() not in ("light", "0", "false")
    app = QGuiApplication(sys.argv)
    view = QQuickView()
    view.engine().addImportPath(str(QML_DIR))
    view.rootContext().setContextProperty("themeDark", dark)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setSource(QUrl.fromLocalFile(str(entry)))
    if view.status() != QQuickView.Status.Ready:
        for err in view.errors():
            print("QML ERROR:", err.toString(), file=sys.stderr)
        return 1
    view.show()

    def grab_and_quit():
        img = view.grabWindow()
        img.save(str(out))
        print("WROTE", out, img.width(), "x", img.height())
        app.quit()

    QTimer.singleShot(600, grab_and_quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
