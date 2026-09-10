from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QWidget


def resolve_dialog_parent(host: Any) -> QWidget | None:
    """Return a real QWidget to parent dialogs on, or None.

    Shell controllers receive a host adapter, not a QWidget. Passing the adapter
    as a QMessageBox/QFileDialog/QInputDialog/QDialog parent raises TypeError, so
    resolve the adapter's real window via ``dialog_parent_host`` and fall back to
    None when no QWidget is available (e.g. a mock host in tests).
    """

    parent = getattr(host, "dialog_parent_host", host)
    return parent if isinstance(parent, QWidget) else None
