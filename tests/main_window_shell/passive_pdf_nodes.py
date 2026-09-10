from __future__ import annotations

import gc
import os
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QMarginsF, QMetaObject, QRectF, Qt, Q_ARG
from PyQt6.QtGui import QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtQml import QJSValue
from PyQt6.QtQuick import QQuickItem

from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.qt_wait import wait_for_condition_or_raise

_DIRECT_ENV = "EA_NODE_EDITOR_PASSIVE_PDF_NODES_DIRECT"


def _write_pdf(path: Path, *, page_count: int = 2) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        painter.drawText(QRectF(80.0, 120.0, 420.0, 120.0), f"PDF page {page_index + 1}")
    painter.end()
    del painter
    del writer
    gc.collect()


class MainWindowShellPassivePdfNodesTests(SharedMainWindowShellTestBase):
    __test__ = os.environ.get(_DIRECT_ENV) == "1"

    def setUp(self) -> None:
        super().setUp()
        self._held_qml_refs: list[QQuickItem] = []

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            self._held_qml_refs = []
            gc.collect()

    def _hold_qml_ref(self, item: QQuickItem) -> QQuickItem:
        self._held_qml_refs.append(item)
        return item

    def _graph_node_media_surface(self, node_id: str) -> QQuickItem:
        surface = self._graph_node_card(node_id).findChild(QQuickItem, "graphNodeMediaSurface")
        self.assertIsNotNone(surface)
        assert surface is not None
        return self._hold_qml_ref(surface)

    def _create_browse_media_panel(self) -> str:
        return self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=False,
            exposed_port_overrides={"source": False},
        )

    def _selected_property_items(self) -> dict[str, dict]:
        return {item["key"]: item for item in self.window.selected_node_property_items}

    def test_pdf_panel_path_editor_browse_commits_external_path_by_default(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-preview.pdf"
        _write_pdf(picked_path, page_count=2)

        path_editor = self._inspector_property_object("inspectorPathEditor", "source")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "source")

        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName", return_value=(str(picked_path), "")):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        preview_info = self.window.describe_pdf_preview(node.properties["source"], node.properties["page_number"])
        self.assertEqual(node.properties["source"], str(picked_path))
        self.assertEqual(str(path_editor.property("text")), node.properties["source"])
        self.assertEqual(preview_info["state"], "ready")
        self.assertEqual(preview_info["page_count"], 2)

    def test_pdf_panel_path_editor_storage_combo_can_choose_internal_copy(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-internal-preview.pdf"
        _write_pdf(picked_path, page_count=2)

        items = self._selected_property_items()
        self.assertTrue(items["source"]["path_supports_managed_copy"])
        self.assertTrue(items["source"]["path_supports_external_link"])

        path_editor = self._inspector_property_object("inspectorPathEditor", "source")
        storage_combo = self._inspector_property_object("inspectorPathSourceStorageComboBox", "source")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "source")
        self.assertEqual(str(storage_combo.property("currentText")), "External")
        storage_combo.setProperty("currentIndex", 1)
        self.app.processEvents()

        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName", return_value=(str(picked_path), "")):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        preview_info = self.window.describe_pdf_preview(node.properties["source"], node.properties["page_number"])
        self.assertTrue(str(node.properties["source"]).startswith("temp://"))
        self.assertEqual(str(path_editor.property("text")), node.properties["source"])
        wait_for_condition_or_raise(
            lambda: str(storage_combo.property("currentText")) == "Internal",
            app=self.app,
            timeout_message=lambda: f"Expected Internal source storage, got {storage_combo.property('currentText')!r}.",
        )
        items = self._selected_property_items()
        self.assertEqual(items["source"]["path_current_source_mode"], "managed_copy")
        staged_path = self.window.project_session_controller.project_artifact_store().resolve_staged_path(
            node.properties["source"]
        )
        self.assertIsNotNone(staged_path)
        assert staged_path is not None
        self.assertEqual(staged_path.name, picked_path.name)
        self.assertEqual(preview_info["state"], "ready")
        self.assertEqual(preview_info["page_count"], 2)

    def test_pdf_panel_toolbar_browse_action_commits_without_node_drag(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "graph-inline-picked.pdf"
        _write_pdf(picked_path, page_count=2)

        surface = self._graph_node_media_surface(node_id)
        actions_value = surface.property("surfaceActions")
        if isinstance(actions_value, QJSValue):
            actions_value = actions_value.toVariant()
        actions = list(actions_value or [])
        edit_source_action = next(
            action for action in actions if dict(action).get("id") == "editSource"
        )
        self.assertEqual(dict(edit_source_action).get("icon"), "search")
        self.assertTrue(bool(dict(edit_source_action).get("enabled")))

        workspace = self.window.model.project.workspaces[workspace_id]
        initial_x = float(workspace.nodes[node_id].x)
        initial_y = float(workspace.nodes[node_id].y)

        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName", return_value=(str(picked_path), "")):
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Qt.ConnectionType.DirectConnection,
                Q_ARG("QVariant", "editSource"),
            )
            self.app.processEvents()

        node = workspace.nodes[node_id]
        preview_info = self.window.describe_pdf_preview(node.properties["source"], node.properties["page_number"])
        self.assertEqual(self.window.scene.selected_node_id(), node_id)
        self.assertEqual(node.properties["source"], str(picked_path))
        self.assertEqual(preview_info["state"], "ready")
        self.assertEqual(preview_info["page_count"], 2)
        self.assertAlmostEqual(float(node.x), initial_x, places=6)
        self.assertAlmostEqual(float(node.y), initial_y, places=6)

    def test_media_panel_pdf_preview_clamps_without_rewriting_authored_page(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        pdf_path = Path(self._env.temp_path) / "clamped-preview.pdf"
        _write_pdf(pdf_path, page_count=2)

        self.window.set_selected_node_property("source", str(pdf_path))
        self.app.processEvents()
        self.window.set_selected_node_property("page_number", "99")
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        items = self._selected_property_items()
        preview_info = self.window.describe_pdf_preview(node.properties["source"], node.properties["page_number"])

        self.assertEqual(node.properties["page_number"], 99)
        self.assertEqual(set(items), {"source"})
        self.assertEqual(preview_info["requested_page_number"], 99)
        self.assertEqual(preview_info["resolved_page_number"], 2)
        self.assertEqual(preview_info["page_count"], 2)
