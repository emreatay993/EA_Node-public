from __future__ import annotations

# Purpose: Expose tooltip-copy lookups to QML through the shell context.
# Map: docs/agent_maps/feature_routes/tooltips_and_tiers.md
# Tests: tests/test_tooltip_copy_registry.py

from PyQt6.QtCore import QObject, pyqtSlot

from ea_node_editor.ui.shell.tooltip_policy import TOOLTIP_CATEGORY_GENERAL
from ea_node_editor.ui.tooltips.registry import tooltip_category, tooltip_text


class TooltipCopyBridge(QObject):
    @pyqtSlot(str, str, result=str)
    def text(self, key: str, fallback: str = "") -> str:
        return tooltip_text(key, fallback)

    @pyqtSlot(str, str, result=str)
    def category(self, key: str, fallback: str = TOOLTIP_CATEGORY_GENERAL) -> str:
        return tooltip_category(key, fallback)


__all__ = ["TooltipCopyBridge"]
