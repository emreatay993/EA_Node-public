from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.dialogs.third_party_notices_dialog import (
    ThirdPartyNoticesDialog,
    load_third_party_notices,
)


def test_load_third_party_notices_uses_first_readable_candidate(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"
    notice = tmp_path / "THIRD_PARTY_NOTICES.md"
    notice.write_text("# Packaged notices\n\nOCCT", encoding="utf-8")

    with patch(
        "ea_node_editor.ui.dialogs.third_party_notices_dialog._notice_file_candidates",
        return_value=(missing, notice),
    ):
        assert load_third_party_notices() == "# Packaged notices\n\nOCCT"


def test_third_party_notices_dialog_displays_packaged_notice(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    notice = tmp_path / "THIRD_PARTY_NOTICES.md"
    notice.write_text("# Third-Party Notices\n\nOCCT 7.9.3", encoding="utf-8")

    with patch(
        "ea_node_editor.ui.dialogs.third_party_notices_dialog._notice_file_candidates",
        return_value=(notice,),
    ):
        dialog = ThirdPartyNoticesDialog()
    try:
        app.processEvents()
        assert dialog.windowTitle() == "Third-Party Notices"
        assert "OCCT 7.9.3" in dialog.notice_browser.toPlainText()
    finally:
        dialog.close()
