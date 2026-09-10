from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QGuiApplication

from ea_node_editor.text_style import normalize_text_annotation_style_payload
from ea_node_editor.ui_qml.bridge_runtime import (
    variant_value as _variant_value,
)

if TYPE_CHECKING:
    pass

_TEXT_ANNOTATION_STYLE_CLIPBOARD_KIND = "text-annotation-style"


_STYLE_CLIPBOARD_APP_PROPERTY = "eaNodeEditorStyleClipboard"


class AnnotationStyleOps:
    """Text-annotation style clipboard (internal app/session clipboard, not the OS clipboard)."""

    def _text_annotation_style_clipboard_property(self) -> str:
        return f"{_STYLE_CLIPBOARD_APP_PROPERTY}:{_TEXT_ANNOTATION_STYLE_CLIPBOARD_KIND}"

    def _write_text_annotation_style_clipboard(self, style: dict[str, Any]) -> None:
        payload = json.dumps(
            {
                "kind": _TEXT_ANNOTATION_STYLE_CLIPBOARD_KIND,
                "version": 1,
                "style": dict(style),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        app = QGuiApplication.instance()
        if app is not None:
            app.setProperty(self._text_annotation_style_clipboard_property(), payload)
        self._text_annotation_style_clipboard = payload

    def _read_text_annotation_style_clipboard(self) -> dict[str, Any]:
        app = QGuiApplication.instance()
        raw_payload = (
            app.property(self._text_annotation_style_clipboard_property())
            if app is not None
            else self._text_annotation_style_clipboard
        )
        if isinstance(raw_payload, str):
            raw_payload = raw_payload.strip()
            if not raw_payload:
                return {}
            try:
                raw_payload = json.loads(raw_payload)
            except ValueError:
                return {}
        if (
            not isinstance(raw_payload, Mapping)
            or str(raw_payload.get("kind", "")).strip() != _TEXT_ANNOTATION_STYLE_CLIPBOARD_KIND
        ):
            return {}
        return normalize_text_annotation_style_payload(raw_payload.get("style"))

    @pyqtSlot("QVariantMap", result=bool)
    def copy_text_annotation_style(self, style: dict[str, Any]) -> bool:
        normalized = normalize_text_annotation_style_payload(_variant_value(dict(style or {})))
        if not normalized:
            return False
        self._write_text_annotation_style_clipboard(normalized)
        return True

    @pyqtSlot(result="QVariantMap")
    def paste_text_annotation_style(self) -> dict[str, Any]:
        return self._read_text_annotation_style_clipboard()

    @pyqtSlot(result=bool)
    def has_text_annotation_style(self) -> bool:
        return bool(self._read_text_annotation_style_clipboard())

