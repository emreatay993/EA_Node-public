from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget


def _notice_file_candidates() -> tuple[Path, ...]:
    roots: list[Path] = []
    bundle_root = str(getattr(sys, "_MEIPASS", "")).strip()
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.extend((Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[3]))
    return tuple(root / "THIRD_PARTY_NOTICES.md" for root in dict.fromkeys(roots))


def load_third_party_notices() -> str:
    for path in _notice_file_candidates():
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return "Third-party notices are unavailable in this installation."


class ThirdPartyNoticesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Third-Party Notices")
        self.resize(760, 620)

        self.notice_browser = QTextBrowser(self)
        self.notice_browser.setOpenExternalLinks(True)
        self.notice_browser.setMarkdown(load_third_party_notices())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.notice_browser)
        layout.addWidget(buttons)
