"""COREX linking-feature concept gallery (standalone, throwaway).

Run:        python mockups/linking_feature_prototype.py
Self-test:  python mockups/linking_feature_prototype.py --selftest   (offscreen, auto-quits)

Needs only PyQt6 (already a project dependency). Nothing here touches the app.
Purpose: explore 5 different link-creation UX ideas (P0) before committing to a
production design. Use the top-bar tabs to switch concepts and the Dark/Light
toggle to check both themes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine


QML_DIR = Path(__file__).with_name("linking_feature")
QML_ENTRY = QML_DIR / "Main.qml"


def main() -> int:
    selftest = "--selftest" in sys.argv
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.load(QUrl.fromLocalFile(str(QML_ENTRY)))
    if not engine.rootObjects():
        print(f"QML load FAILED: {QML_ENTRY}", file=sys.stderr)
        return 1
    if selftest:
        QTimer.singleShot(900, app.quit)
        rc = app.exec()
        print("SELFTEST OK")
        return rc
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
