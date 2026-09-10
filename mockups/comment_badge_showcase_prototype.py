"""COREX node comment-badge concept gallery (standalone, throwaway).

Run:        python mockups/comment_badge_showcase_prototype.py
Self-test:  python mockups/comment_badge_showcase_prototype.py --selftest
            (offscreen; cycles all five concept tabs so every QML compiles)
Screenshot: python mockups/comment_badge_showcase_prototype.py
            --shot out.png [--concept a|b|c|d|e] [--light]
            (poses hover/peek states deterministically before grabbing)

Needs only PyQt6 (already a project dependency). Nothing here touches the app.
Purpose: explore 5 lower-right comment-badge designs on graph nodes (P0)
before committing to a production design. Use the top-bar tabs to switch
concepts and the Dark/Light toggle to check both themes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if "--selftest" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine

# Imported for the side effect of registering the QQuickWindow wrapper type:
# without it, rootObjects()[0] is wrapped as plain QWindow and grabWindow()
# resolves into a native crash (0xC0000409) instead of an AttributeError.
from PyQt6.QtQuick import QQuickWindow


QML_DIR = Path(__file__).with_name("comment_badge_showcase")
QML_ENTRY = QML_DIR / "Main.qml"
CONCEPTS = ("a", "b", "c", "d", "e")


def _flag_value(flag: str) -> str | None:
    if flag not in sys.argv:
        return None
    idx = sys.argv.index(flag)
    if idx + 1 >= len(sys.argv):
        print(f"{flag} requires a value", file=sys.stderr)
        raise SystemExit(2)
    return sys.argv[idx + 1]


def main() -> int:
    selftest = "--selftest" in sys.argv
    shot_path = _flag_value("--shot")
    concept = (_flag_value("--concept") or "a").lower()
    if concept not in CONCEPTS:
        print(f"--concept must be one of: {' '.join(CONCEPTS)}", file=sys.stderr)
        return 2

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(
        lambda errs: warnings.extend(e.toString() for e in errs)
    )
    engine.addImportPath(str(QML_DIR))
    # Poses must be live BEFORE the root loads: each concept checks `posed`
    # in Component.onCompleted, which runs during load — setProperty
    # afterwards would miss it.
    engine.setInitialProperties({
        "currentIndex": CONCEPTS.index(concept),
        "darkMode": "--light" not in sys.argv,
        "posed": shot_path is not None,
    })
    engine.load(QUrl.fromLocalFile(str(QML_ENTRY)))
    if not engine.rootObjects():
        print(f"QML load FAILED: {QML_ENTRY}", file=sys.stderr)
        return 1
    win = engine.rootObjects()[0]

    if shot_path:
        Path(shot_path).parent.mkdir(parents=True, exist_ok=True)

        def grab() -> None:
            window = engine.rootObjects()[0]
            if not isinstance(window, QQuickWindow):
                print(f"SHOT FAILED: root object is {type(window).__name__}", file=sys.stderr)
                app.exit(1)
                return
            image = window.grabWindow()
            ok = not image.isNull() and image.save(shot_path)
            print(f"SHOT {'SAVED' if ok else 'FAILED'}: {shot_path}")
            if ok:
                app.quit()
            else:
                app.exit(1)

        QTimer.singleShot(1400, grab)
        return app.exec()

    if selftest:
        # Cycle every tab so all five concept files compile in the smoke run;
        # any QML warning fails the selftest.
        def cycle(i: int) -> None:
            if i >= len(CONCEPTS):
                app.quit()
                return
            win.setProperty("currentIndex", i)
            QTimer.singleShot(150, lambda: cycle(i + 1))

        QTimer.singleShot(150, lambda: cycle(0))
        rc = app.exec()
        if warnings:
            print("QML WARNINGS:\n  " + "\n  ".join(warnings), file=sys.stderr)
            return 1
        print("SELFTEST OK")
        return rc

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
