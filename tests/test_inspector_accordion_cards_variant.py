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
_ACCORDION_CARDS_BODY_QML_PATH = (
    _SHELL_COMPONENTS_DIR / "InspectorAccordionCardsBody.qml"
)


class _StubPane(QObject):
    """Minimal stand-in for ShellInspectorPane used purely by the accordion body."""

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


class InspectorAccordionCardsBodyQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
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

    def _load_component(self, initial_property_items: list[dict]):
        engine = QQmlEngine()
        theme_bridge = ThemeBridge(theme_id="stitch_dark")
        ui_icons = UiIconRegistryBridge()
        engine.rootContext().setContextProperty("themeBridge", theme_bridge)
        engine.rootContext().setContextProperty("uiIcons", ui_icons)
        engine.addImportPath(str(_SHELL_COMPONENTS_DIR.parent))

        pane = _StubPane(palette=theme_bridge.palette)

        component = QQmlComponent(
            engine, QUrl.fromLocalFile(str(_ACCORDION_CARDS_BODY_QML_PATH))
        )
        if component.status() != QQmlComponent.Status.Ready:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(
                f"Failed to load InspectorAccordionCardsBody.qml:\n{errors}"
            )
        initial_properties = {
            "pane": pane,
            "propertyItems": list(initial_property_items),
        }
        obj = component.createWithInitialProperties(initial_properties)
        if obj is None:
            errors = "\n".join(error.toString() for error in component.errors())
            raise AssertionError(
                f"Failed to instantiate InspectorAccordionCardsBody.qml:\n{errors}"
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

    def test_component_renders_one_card_per_group(self) -> None:
        items = [
            {"key": "a", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "b", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "c", "label": "Charlie", "group": "Post", "editor_mode": "text", "value": ""},
            {"key": "d", "label": "Delta", "group": "", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            self.assertIsNotNone(self._find_by_name(body, "inspectorAccordionCardsFilterBar"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorAccordionCardHeader_Source"))
            self.assertIsNotNone(self._find_by_name(body, "inspectorAccordionCardHeader_Post"))
            self.assertIsNotNone(
                self._find_by_name(body, "inspectorAccordionCardHeader_Properties")
            )
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_property_groups_start_collapsed_and_toggle_open(self) -> None:
        items = [
            {"key": "a", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            card_body = self._find_by_name(body, "inspectorAccordionCardBody_Source")
            self.assertIsNotNone(card_body)
            self.assertFalse(card_body.property("visible"))

            body.toggleGroup("Source")
            self._app.processEvents()
            self.assertTrue(card_body.property("visible"))

            body.toggleGroup("Source")
            self._app.processEvents()
            self.assertFalse(card_body.property("visible"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_per_group_filter_only_visible_when_group_has_more_than_three_items(self) -> None:
        items = [
            {"key": "a", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "b", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "c", "label": "Charlie", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "d", "label": "Delta", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "e", "label": "Echo", "group": "Post", "editor_mode": "text", "value": ""},
            {"key": "f", "label": "Foxtrot", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.toggleGroup("Source")
            body.toggleGroup("Post")
            self._app.processEvents()

            source_local_filter = self._find_by_name(
                body, "inspectorAccordionCardLocalFilter_Source"
            )
            post_local_filter = self._find_by_name(
                body, "inspectorAccordionCardLocalFilter_Post"
            )
            self.assertIsNotNone(source_local_filter)
            self.assertIsNotNone(post_local_filter)
            self.assertTrue(source_local_filter.property("visible"))
            self.assertFalse(post_local_filter.property("visible"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)

    def test_global_filter_hides_group_with_zero_matches_and_hides_local_filter(self) -> None:
        items = [
            {"key": "a", "label": "Alpha", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "b", "label": "Bravo", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "c", "label": "Charlie", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "d", "label": "Delta", "group": "Source", "editor_mode": "text", "value": ""},
            {"key": "e", "label": "Echo", "group": "Post", "editor_mode": "text", "value": ""},
        ]

        body, engine, pane, theme_bridge, ui_icons = self._load_component(items)
        try:
            body.toggleGroup("Source")
            self._app.processEvents()

            body.setProperty("filterQuery", "alpha")
            self._app.processEvents()

            self.assertIsNotNone(
                self._find_by_name(body, "inspectorAccordionCardHeader_Source")
            )
            self.assertIsNone(
                self._find_by_name(body, "inspectorAccordionCardHeader_Post")
            )

            source_local_filter = self._find_by_name(
                body, "inspectorAccordionCardLocalFilter_Source"
            )
            self.assertIsNotNone(source_local_filter)
            self.assertFalse(source_local_filter.property("visible"))
        finally:
            self._dispose(body, engine, pane, theme_bridge, ui_icons)


if __name__ == "__main__":
    unittest.main()
