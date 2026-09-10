"""COREX node-creation-wizard mockups -- launcher.

    python mockups/run_all.py            # themed launcher
    python mockups/run_all.py --selftest # offscreen: build all 4 in both flows

From the launcher: pick the flow (Python Script / Generic), open any design, or
"Compare" to tile all four side by side. Mockups are visual only.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

if "--selftest" in sys.argv or "--shots" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mockups import (  # noqa: E402
    design1_stepped_wizard,
    design2_single_page_preview,
    design3_sidebar_sections,
    design4_canvas_inline,
)
from mockups._theme import apply_corex_theme, apply_window_icon  # noqa: E402
from mockups._widgets import FlowSwitch, hint, title_label  # noqa: E402

DESIGNS = [
    ("1 · Stepped wizard",
     "Guided step rail (Identity → Ports → … → Review), Back/Next/Create.",
     design1_stepped_wizard),
    ("2 · Single page + live preview",
     "One form + a live COREX node card that updates as you type.",
     design2_single_page_preview),
    ("3 · Sidebar-section dialog",
     "Subclasses the real SectionedSettingsDialog — most native to COREX.",
     design3_sidebar_sections),
    ("4 · Canvas-inline create",
     "Double-click the canvas; an inline card morphs into a placed node.",
     design4_canvas_inline),
]


class Launcher(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("COREX — Node Creation Wizard Mockups")
        apply_window_icon(self)
        self.resize(720, 560)
        self._flow = "python"
        self._open: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        root.addWidget(title_label("Node Creation Wizard — design mockups"))
        root.addWidget(hint(
            "Four faithful, runnable designs using COREX's real stitch_dark "
            "theme. Pick a flow, then open a design or compare them all."))

        flow_row = QHBoxLayout()
        flow_row.addWidget(QLabel("Scenario:"))
        self._switch = FlowSwitch(self._flow)
        self._switch.flowChanged.connect(self._set_flow)
        flow_row.addWidget(self._switch)
        root.addLayout(flow_row)

        for name, desc, mod in DESIGNS:
            root.addWidget(self._card(name, desc, mod))

        foot = QHBoxLayout()
        compare = QPushButton("⊞  Compare all four")
        compare.clicked.connect(self._compare)
        quit_b = QPushButton("Quit")
        quit_b.clicked.connect(self.close)
        foot.addWidget(compare)
        foot.addStretch(1)
        foot.addWidget(quit_b)
        root.addStretch(1)
        root.addLayout(foot)

    def _set_flow(self, flow_id: str) -> None:
        self._flow = flow_id

    def _card(self, name: str, desc: str, mod) -> QFrame:
        c = QFrame()
        c.setProperty("settingsCard", True)
        cl = QHBoxLayout(c)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(12)
        txt = QWidget()
        tv = QVBoxLayout(txt)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(3)
        nm = QLabel(name)
        nm.setStyleSheet("font-weight:600;font-size:13px;")
        tv.addWidget(nm)
        tv.addWidget(hint(desc))
        cl.addWidget(txt, 1)
        btn = QPushButton("Open ▸")
        btn.clicked.connect(lambda _=False, m=mod: self._open_design(m))
        cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return c

    def _open_design(self, mod, *, modal=False, geom=None) -> QWidget:
        w = mod.make(self._flow, None)
        try:
            w.setModal(False)
        except AttributeError:
            pass
        if geom:
            w.setGeometry(*geom)
        w.show()
        w.raise_()
        self._open.append(w)
        return w

    def _compare(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        cols, rows = 2, 2
        w = screen.width() // cols - 30
        h = screen.height() // rows - 60
        for i, (_n, _d, mod) in enumerate(DESIGNS):
            gx = screen.x() + 15 + (i % cols) * (w + 20)
            gy = screen.y() + 30 + (i // cols) * (h + 30)
            self._open_design(mod, geom=(gx, gy, w, h))


def _selftest() -> int:
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    ok = True
    for name, _d, mod in DESIGNS:
        for flow in ("python", "generic"):
            try:
                w = mod.make(flow, None)
                w.adjustSize()
                # exercise the flow toggle path too
                if hasattr(w, "_set_flow"):
                    w._set_flow("generic" if flow == "python" else "python")
                w.deleteLater()
                print(f"  OK  {name:<34} [{flow}]")
            except Exception as exc:  # noqa: BLE001
                ok = False
                print(f"  FAIL {name:<34} [{flow}]: {exc!r}")
    print("\nSELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def _shots() -> int:
    """Render every design (both flows) to PNGs under mockups/_shots/."""
    from mockups._theme import Port
    from mockups.design4_canvas_inline import PlacedNode

    app = QApplication(sys.argv)
    apply_corex_theme(app)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_shots")
    os.makedirs(out, exist_ok=True)
    for idx, (name, _d, mod) in enumerate(DESIGNS, 1):
        for flow in ("python", "generic"):
            w = mod.make(flow, None)
            if mod is design4_canvas_inline:
                w._placed.append(PlacedNode(
                    120, 130, "My Solver", "Custom › Python", "{ }",
                    [Port("payload")], [Port("result")]))
                w._open_card(470, 150)
            w.show()
            for _ in range(8):
                app.processEvents()
            path = os.path.join(out, f"design{idx}_{flow}.png")
            w.grab().save(path)
            print(f"  saved {path}")
            w.deleteLater()
    print("\nSHOTS WRITTEN to", out)
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    if "--shots" in sys.argv:
        return _shots()
    app = QApplication(sys.argv)
    apply_corex_theme(app)
    win = Launcher()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
