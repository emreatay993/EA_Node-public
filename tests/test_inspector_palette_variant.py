from __future__ import annotations

import os
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtWidgets import QApplication

from ea_node_editor.ui.icon_registry import UiIconRegistryBridge
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHELL_COMPONENTS_DIR = (
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "shell"
)
_PALETTE_BODY_QML_PATH = _SHELL_COMPONENTS_DIR / "InspectorPaletteBody.qml"


class _StubPane(QObject):
    """Minimal stand-in for ShellInspectorPane used purely by the palette body."""

    changed = pyqtSignal()

    def __init__(self, palette: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._palette = dict(palette)

    @pyqtProperty("QVariantMap", notify=changed)
    def themePalette(self):  # type: ignore[override]
        return self._palette

    @pyqtProperty(bool, notify=changed)
    def isPinInspector(self) -> bool:
        return False

    @pyqtProperty("QVariantList", notify=changed)
    def pinDataTypeOptions(self):
        return []

    @pyqtProperty(QObject, notify=changed)
    def inspectorBridgeRef(self):
        return None


class InspectorPaletteBodyQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def _walk(self, item):
        yield item
        child_items = getattr(item, "childItems", None)
        if not callable(child_items):
            return
        for child in child_items():
            yield from self._walk(child)

    def _find_by_name(self, root, object_name: str):
        for node in self._walk(root):
            if node.objectName() == object_name:
                return node
        return None

    def _find_all_with_prefix(self, root, prefix: str):
        return [
            node
            for node in self._walk(root)
            if node.objectName().startswith(prefix)
        ]

    def _load_component(self, initial_property_items: list[dict]):
        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_dark")
        ui_icons = UiIconRegistryBridge()
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("uiIcons", ui_icons)
        engine.addImportPath(str(_SHELL_COMPONENTS_DIR.parent))

        pane = _StubPane(palette=theme_bridge.palette)

        component = QQmlComponent(
            engine, QUrl.fromLocalFile(str(_PALETTE_BODY_QML_PATH))
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(
                f"Failed to load InspectorPaletteBody.qml:\n{errors}"
            )
        initial_properties = {
            "pane": pane,
            "propertyItems": list(initial_property_items),
        }
        obj = component.createWithInitialProperties(initial_properties)
        if obj is None:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(
                f"Failed to instantiate InspectorPaletteBody.qml:\n{errors}"
            )
        self._app.processEvents()
        return obj, engine, pane, theme_bridge, ui_icons

    def _dispose(self, body, engine, pane, theme_bridge, ui_icons) -> None:
        body.deleteLater()
        engine.deleteLater()
        pane.deleteLater()
        theme_bridge.deleteLater()
        ui_icons.deleteLater()
        self._app.processEvents()

    def test_component_renders_filter_bar_and_rows(self) -> None:
        items = [
            {"key": "alpha", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "bravo", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "charlie", "label": "Charlie", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorPaletteHeader"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorPaletteFilterBar"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorPaletteList"))
            for key in ("alpha", "bravo", "charlie"):
                self.assertIsNotNone(
                    self._find_by_name(body, f"inspectorPaletteRow_{key}"),
                    f"expected row for {key}",
                )
            empty_state = self._find_by_name(body, "inspectorPaletteEmptyState")
            self.assertIsNotNone(empty_state)
            self.assertFalse(empty_state.property("visible"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_filter_query_narrows_visible_rows(self) -> None:
        items = [
            {"key": "alpha", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "bravo", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "charlie", "label": "Charlie", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.setProperty("filterQuery", "alpha")
            self._app.processEvents()

            self.assertIsNotNone(self._find_by_name(body, "inspectorPaletteRow_alpha"))
            self.assertIsNone(self._find_by_name(body, "inspectorPaletteRow_bravo"))
            self.assertIsNone(self._find_by_name(body, "inspectorPaletteRow_charlie"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_filter_query_zero_matches_shows_empty_state(self) -> None:
        items = [
            {"key": "alpha", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "bravo", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.setProperty("filterQuery", "zzz_no_match_zzz")
            self._app.processEvents()

            empty_state = self._find_by_name(body, "inspectorPaletteEmptyState")
            self.assertIsNotNone(empty_state)
            self.assertTrue(empty_state.property("visible"))

            rows = self._find_all_with_prefix(body, "inspectorPaletteRow_")
            self.assertEqual(rows, [])
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_move_active_wraps_across_rows(self) -> None:
        items = [
            {"key": "alpha", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "bravo", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "charlie", "label": "Charlie", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertEqual(body.property("activeIndex"), 0)

            body.moveActive(1)
            self._app.processEvents()
            self.assertEqual(body.property("activeIndex"), 1)

            body.moveActive(1)
            self._app.processEvents()
            self.assertEqual(body.property("activeIndex"), 2)

            body.moveActive(1)
            self._app.processEvents()
            self.assertEqual(body.property("activeIndex"), 0)

            body.moveActive(-1)
            self._app.processEvents()
            self.assertEqual(body.property("activeIndex"), 2)
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_footer_is_present(self) -> None:
        items = [
            {"key": "alpha", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorPaletteFooter"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)


if __name__ == "__main__":
    unittest.main()
