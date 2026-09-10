"""COREX — QML feature showcase (standalone, throwaway mockup).

Run:        python mockups/qml_features_showcase_prototype.py
Self-test:  python mockups/qml_features_showcase_prototype.py --selftest   (offscreen, auto-quits, prints QML warnings)
Screenshot: python mockups/qml_features_showcase_prototype.py --shot out.png  (renders one frame to PNG, then quits)

Needs PyQt6 (project dep) + PyQt6-Graphs (for the live chart node). Nothing here
touches the real app — it's a visual showcase of candidate QML canvas features:

  (1) animated data-flow wires      (2) inline data preview on a node
  (3) in-node sparkline (Shapes)    (4) live chart node (Qt Graphs)
  (5) 3D preview node (Quick3D)     (6) execution timeline scrubber
  (7) traffic-light node states     (8) bypass / mute node visual
  (9) node breakpoint + watch panel + completion glow / particle burst
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

QML_DIR = Path(__file__).with_name("qml_features_showcase")
QML_ENTRY = QML_DIR / "Main.qml"


def main() -> int:
    argv = sys.argv
    selftest = "--selftest" in argv
    shot = None
    if "--shot" in argv:
        i = argv.index("--shot")
        shot = argv[i + 1] if i + 1 < len(argv) else str(QML_DIR / "showcase.png")
    if selftest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QGuiApplication(argv)
    engine = QQmlApplicationEngine()

    warnings: list[str] = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.addImportPath(str(QML_DIR))
    engine.load(QUrl.fromLocalFile(str(QML_ENTRY)))

    if not engine.rootObjects():
        print(f"QML load FAILED: {QML_ENTRY}", file=sys.stderr)
        return 2
    win = engine.rootObjects()[0]

    if selftest:
        def done() -> None:
            if warnings:
                print("QML WARNINGS:\n  " + "\n  ".join(warnings), file=sys.stderr)
            app.quit()
        QTimer.singleShot(1400, done)
        app.exec()
        print("SELFTEST OK")
        return 0

    if shot:
        # optional deterministic state so the captured frame is interesting
        if "--at" in argv:
            win.setProperty("breakpointArmed", False)
            win.setProperty("runProgress", float(argv[argv.index("--at") + 1]))
        if "--bp" in argv:
            win.setProperty("breakpointArmed", True)
            win.setProperty("paused", True)
            win.setProperty("pausedNodeId", "B")
            win.setProperty("runProgress", 0.30)

        def grab() -> None:
            img = win.grabWindow()
            ok = bool(img) and not img.isNull() and img.save(shot)
            print(("SAVED " if ok else "SAVE FAILED ") + str(shot), file=sys.stderr)
            if warnings:
                print("QML WARNINGS:\n  " + "\n  ".join(warnings), file=sys.stderr)
            app.quit()
        QTimer.singleShot(1600, grab)
        return app.exec()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
