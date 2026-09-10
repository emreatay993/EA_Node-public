from __future__ import annotations

import gc
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QMetaObject, QPoint, QPointF, Qt, Q_ARG
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtQml import QJSValue
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtTest import QSignalSpy, QTest

from tests.main_window_shell.base import *  # noqa: F401,F403
from tests.qt_wait import wait_for_condition_or_raise

_DIRECT_ENV = "EA_NODE_EDITOR_PASSIVE_IMAGE_NODES_DIRECT"


class MainWindowShellPassiveImageNodesTests(SharedMainWindowShellTestBase):
    __test__ = os.environ.get(_DIRECT_ENV) == "1"

    def setUp(self) -> None:
        super().setUp()
        self._held_qml_refs: list[QQuickItem] = []

    def _create_browse_media_panel(self) -> str:
        node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=False,
            exposed_port_overrides={"source": False},
        )
        self.assertFalse(
            self.window.model.project.workspaces[
                self.window.workspace_manager.active_workspace_id()
            ].nodes[node_id].exposed_ports["source"]
        )
        return node_id

    def tearDown(self) -> None:
        try:
            super().tearDown()
        finally:
            self._held_qml_refs = []
            gc.collect()

    def _hold_qml_ref(self, item: QQuickItem) -> QQuickItem:
        self._held_qml_refs.append(item)
        return item

    def _graph_node_child(self, node_id: str, object_name: str) -> QQuickItem:
        match: QQuickItem | None = None

        def _find() -> bool:
            nonlocal match
            card = self._graph_node_card(node_id)
            match = next(
                (
                    item
                    for item in self._walk_items(card)
                    if item.objectName() == object_name
                ),
                None,
            )
            return match is not None

        wait_for_condition_or_raise(
            _find,
            timeout_ms=5000,
            app=self.app,
            timeout_message=f"Could not find {object_name!r} for node {node_id!r}.",
        )
        assert match is not None
        return self._hold_qml_ref(match)

    def _graph_node_child_with_property(
        self,
        node_id: str,
        object_name: str,
        property_name: str,
        expected_value: str,
    ) -> QQuickItem:
        card = self._graph_node_card(node_id)
        for item in self._walk_items(card):
            if item.objectName() != object_name:
                continue
            if str(item.property(property_name)) == expected_value:
                return self._hold_qml_ref(item)
        self.fail(
            f"Could not find {object_name!r} for node {node_id!r} "
            f"with {property_name!r}={expected_value!r}."
        )

    @staticmethod
    def _item_scene_center(item: QQuickItem) -> QPoint:
        scene_point = item.mapToScene(QPointF(item.width() * 0.5, item.height() * 0.5))
        return QPoint(round(scene_point.x()), round(scene_point.y()))

    def _item_widget_center(self, item: QQuickItem) -> QPoint:
        item_window = item.window()
        self.assertIsNotNone(item_window)
        scene_point = self._item_scene_center(item)
        global_point = item_window.mapToGlobal(scene_point)
        return self.window.quick_widget.mapFromGlobal(global_point)

    def _wait_for_media_preview(self, surface: QQuickItem, timeout_ms: int = 5000) -> None:
        wait_for_condition_or_raise(
            lambda: str(surface.property("sourceState")) in {"ready", "invalid"},
            timeout_ms=timeout_ms,
            poll_interval_ms=25,
            app=self.app,
            timeout_message=lambda: (
                "Timed out waiting for media preview to settle: "
                f"sourceState={surface.property('sourceState')!r}, "
                f"sourceResolution={surface.property('sourceResolution')!r}."
            ),
        )
        self.assertEqual(str(surface.property("sourceState")), "ready")

    def test_image_panel_inspector_exposes_locked_editor_modes(self) -> None:
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        items = {item["key"]: item for item in self.window.selected_node_property_items}
        self.assertEqual(set(items), {"source"})
        self.assertEqual(items["source"]["editor_mode"], "path")

        self._inspector_property_object("inspectorPathEditor", "source")

    def test_image_panel_path_editor_browse_commits_external_path_by_default(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()
        initial_card = self._graph_node_card(node_id)
        initial_height = float(initial_card.height())

        picked_path = Path(self._env.temp_path) / "picked-image-node.png"
        image = QImage(12, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(picked_path)))

        path_editor = self._inspector_property_object("inspectorPathEditor", "source")
        browse_button = self._inspector_property_object("inspectorPathBrowseButton", "source")

        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName", return_value=(str(picked_path), "")):
            QMetaObject.invokeMethod(browse_button, "click")
            self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        node_payload = next(item for item in self.window.scene.nodes_model if item["node_id"] == node_id)
        updated_card = self._graph_node_card(node_id)
        self.assertEqual(node.properties["source"], str(picked_path))
        self.assertEqual(str(path_editor.property("text")), node.properties["source"])
        self.assertIsNone(node.custom_width)
        self.assertIsNone(node.custom_height)
        self.assertEqual(float(node_payload["height"]), initial_height)
        self.assertAlmostEqual(float(updated_card.height()), initial_height, places=3)

    def test_media_panel_browse_result_cannot_commit_after_source_input_is_exposed(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        old_path = str(Path(self._env.temp_path) / "old-media-source.png")
        picked_path = str(Path(self._env.temp_path) / "picked-media-source.png")
        self.window.scene.set_node_property(node_id, "source", old_path)
        self.window.runtime_history.clear_workspace(workspace_id)
        workspace = self.window.model.project.workspaces[workspace_id]
        before_edges = dict(workspace.edges)
        before_selection = tuple(self.window.scene.selected_node_ids)

        def _pick_and_expose(*_args, **_kwargs):  # noqa: ANN002, ANN003
            self.window.scene.set_exposed_port(node_id, "source", True)
            return picked_path, ""

        with patch(
            "ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName",
            side_effect=_pick_and_expose,
        ):
            selected = self.window.shell_inspector_presenter.browse_node_property_path(
                node_id,
                "source",
                old_path,
            )
        self.assertEqual(selected, picked_path)
        depth_after_exposure = self.window.runtime_history.undo_depth(workspace_id)

        self.window.scene.set_node_property(node_id, "source", selected)

        self.assertTrue(workspace.nodes[node_id].exposed_ports["source"])
        self.assertEqual(workspace.nodes[node_id].properties["source"], old_path)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), depth_after_exposure)
        self.assertEqual(workspace.edges, before_edges)
        self.assertEqual(tuple(self.window.scene.selected_node_ids), before_selection)

    def test_media_panel_internalize_result_cannot_commit_after_source_input_is_exposed(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        old_path = str(Path(self._env.temp_path) / "external-media-source.png")
        self.window.scene.set_node_property(node_id, "source", old_path)
        self.window.runtime_history.clear_workspace(workspace_id)
        workspace = self.window.model.project.workspaces[workspace_id]
        before_edges = dict(workspace.edges)
        before_selection = tuple(self.window.scene.selected_node_ids)

        def _internalize_and_expose(*_args, **_kwargs):  # noqa: ANN002, ANN003
            self.window.scene.set_exposed_port(node_id, "source", True)
            return "temp://internalized-media"

        with patch.object(
            self.window.shell_host_presenter,
            "internalize_property_path",
            side_effect=_internalize_and_expose,
        ):
            managed = self.window.shell_inspector_presenter.internalize_node_property_path(
                node_id,
                "source",
                old_path,
            )
        self.assertEqual(managed, "temp://internalized-media")
        depth_after_exposure = self.window.runtime_history.undo_depth(workspace_id)

        self.window.scene.set_node_property(node_id, "source", managed)

        self.assertTrue(workspace.nodes[node_id].exposed_ports["source"])
        self.assertEqual(workspace.nodes[node_id].properties["source"], old_path)
        self.assertEqual(self.window.runtime_history.undo_depth(workspace_id), depth_after_exposure)
        self.assertEqual(workspace.edges, before_edges)
        self.assertEqual(tuple(self.window.scene.selected_node_ids), before_selection)

    def test_image_panel_path_editor_storage_combo_can_choose_internal_copy(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-external-image-node.png"
        image = QImage(12, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(picked_path)))

        items = {item["key"]: item for item in self.window.selected_node_property_items}
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
        self.assertTrue(str(node.properties["source"]).startswith("temp://"))
        self.assertEqual(str(path_editor.property("text")), node.properties["source"])
        wait_for_condition_or_raise(
            lambda: str(storage_combo.property("currentText")) == "Internal",
            app=self.app,
            timeout_message=lambda: f"Expected Internal source storage, got {storage_combo.property('currentText')!r}.",
        )
        items = {item["key"]: item for item in self.window.selected_node_property_items}
        self.assertEqual(items["source"]["path_current_source_mode"], "managed_copy")
        staged_path = self.window.project_session_controller.project_artifact_store().resolve_staged_path(
            node.properties["source"]
        )
        self.assertIsNotNone(staged_path)
        assert staged_path is not None
        self.assertEqual(staged_path.name, picked_path.name)

    def test_video_panel_path_editor_storage_combo_can_choose_internal_copy(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "picked-video-panel-clip.mp4"
        picked_path.write_bytes(b"video fixture")

        items = {item["key"]: item for item in self.window.selected_node_property_items}
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
        self.assertTrue(str(node.properties["source"]).startswith("temp://"))
        self.assertEqual(str(path_editor.property("text")), node.properties["source"])
        wait_for_condition_or_raise(
            lambda: str(storage_combo.property("currentText")) == "Internal",
            app=self.app,
            timeout_message=lambda: f"Expected Internal source storage, got {storage_combo.property('currentText')!r}.",
        )
        items = {item["key"]: item for item in self.window.selected_node_property_items}
        self.assertEqual(items["source"]["path_current_source_mode"], "managed_copy")
        staged_path = self.window.project_session_controller.project_artifact_store().resolve_staged_path(
            node.properties["source"]
        )
        self.assertIsNotNone(staged_path)
        assert staged_path is not None
        self.assertEqual(staged_path.name, picked_path.name)

    def test_image_panel_toolbar_browse_action_commits_without_node_drag(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        picked_path = Path(self._env.temp_path) / "graph-inline-picked-image.png"
        image = QImage(18, 12, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(picked_path)))

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
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
        self.assertEqual(self.window.scene.selected_node_id(), node_id)
        self.assertEqual(node.properties["source"], str(picked_path))
        self.assertAlmostEqual(float(node.x), initial_x, places=6)
        self.assertAlmostEqual(float(node.y), initial_y, places=6)

    def test_media_panel_toolbar_source_input_toggle_round_trips(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        def source_input_exposed() -> bool:
            workspace = self.window.model.project.workspaces[workspace_id]
            return bool(workspace.nodes[node_id].exposed_ports["source"])

        button_name = "graphNodeFloatingToolbarAction_toggle_source_input"
        for expected_exposed in (True, False):
            button = self._find_qml_item(button_name)
            self.assertIsNotNone(button)
            assert button is not None
            self.assertTrue(bool(button.property("visible")))
            self.assertTrue(bool(button.property("enabled")))
            self.assertIs(bool(button.property("active")), not expected_exposed)
            item_window = button.window()
            self.assertIsNotNone(item_window)
            assert item_window is not None
            QTest.mouseClick(
                item_window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                self._item_scene_center(button),
            )
            wait_for_condition_or_raise(
                lambda: source_input_exposed() is expected_exposed,
                timeout_ms=5000,
                app=self.app,
            )
            updated_button = self._find_qml_item(button_name)
            self.assertIsNotNone(updated_button)
            assert updated_button is not None
            self.assertIs(bool(updated_button.property("active")), expected_exposed)

    def test_image_panel_toolbar_internalize_action_copies_file_and_flips_storage_mode(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        external_path = Path(self._env.temp_path) / "graph-inline-external-image.png"
        image = QImage(18, 12, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(external_path)))
        self.window.scene.set_node_property(node_id, "source", str(external_path))
        self.app.processEvents()

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        storage_combo = self._inspector_property_object("inspectorPathSourceStorageComboBox", "source")
        self.assertEqual(str(storage_combo.property("currentText")), "External")

        actions_value = surface.property("surfaceActions")
        if isinstance(actions_value, QJSValue):
            actions_value = actions_value.toVariant()
        actions = [dict(action) for action in list(actions_value or [])]
        internalize_action = next(action for action in actions if action.get("id") == "internalizeSource")
        self.assertEqual(internalize_action.get("icon"), "internalize-source")
        self.assertEqual(internalize_action.get("label"), "Copy into project")
        self.assertTrue(bool(internalize_action.get("enabled")))

        workspace = self.window.model.project.workspaces[workspace_id]
        with patch("ea_node_editor.ui.shell.window.QFileDialog.getOpenFileName") as dialog_mock:
            QMetaObject.invokeMethod(
                surface,
                "dispatchSurfaceAction",
                Qt.ConnectionType.DirectConnection,
                Q_ARG("QVariant", "internalizeSource"),
            )
            self.app.processEvents()
            dialog_mock.assert_not_called()

        node = workspace.nodes[node_id]
        self.assertTrue(str(node.properties["source"]).startswith("temp://"))
        wait_for_condition_or_raise(
            lambda: str(
                self._inspector_property_object("inspectorPathEditor", "source").property("text")
            ) == node.properties["source"],
            app=self.app,
            timeout_message=lambda: (
                "Expected path editor to show the staged source ref, got "
                f"{self._inspector_property_object('inspectorPathEditor', 'source').property('text')!r}."
            ),
        )
        staged_path = self.window.project_session_controller.project_artifact_store().resolve_staged_path(
            node.properties["source"]
        )
        self.assertIsNotNone(staged_path)
        assert staged_path is not None
        self.assertEqual(staged_path.name, external_path.name)
        self.assertEqual(staged_path.read_bytes(), external_path.read_bytes())
        wait_for_condition_or_raise(
            lambda: str(
                self._inspector_property_object("inspectorPathSourceStorageComboBox", "source").property(
                    "currentText"
                )
            ) == "Internal",
            app=self.app,
            timeout_message=lambda: (
                "Expected Internal source storage, got "
                f"{self._inspector_property_object('inspectorPathSourceStorageComboBox', 'source').property('currentText')!r}."
            ),
        )
        items = {item["key"]: item for item in self.window.selected_node_property_items}
        self.assertEqual(items["source"]["path_current_source_mode"], "managed_copy")

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        actions_value = surface.property("surfaceActions")
        if isinstance(actions_value, QJSValue):
            actions_value = actions_value.toVariant()
        actions = [dict(action) for action in list(actions_value or [])]
        self.assertNotIn("internalizeSource", {action.get("id") for action in actions})
        source_action = next(action for action in actions if action.get("id") == "editSource")
        storage_actions = [dict(action) for action in source_action["popoverActions"]]
        self.assertFalse(bool(storage_actions[0].get("checked", False)))
        self.assertTrue(bool(storage_actions[1].get("checked", False)))

    def test_media_panel_save_crop_action_replaces_browse_source_with_internal_png(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        image_path = Path(self._env.temp_path) / "image-crop-source.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))
        node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={
                "source": str(image_path),
                "crop_x": 0.25,
                "crop_y": 0.25,
                "crop_w": 0.5,
                "crop_h": 0.5,
            },
            exposed_port_overrides={"source": False},
        )
        self.window.scene.focus_node(node_id)
        self.app.processEvents()

        workspace = self.window.model.project.workspaces[workspace_id]
        metadata_spy = QSignalSpy(self.window.project_meta_changed)
        result = self.window.media_panel_action_service.request_save_image_crop_replace(
            node_id,
            {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
        )
        self.assertTrue(result["success"])

        node = workspace.nodes[node_id]
        self.assertTrue(str(node.properties["source"]).startswith("temp://"))
        self.assertAlmostEqual(float(node.properties["crop_x"]), 0.0)
        self.assertAlmostEqual(float(node.properties["crop_y"]), 0.0)
        self.assertAlmostEqual(float(node.properties["crop_w"]), 1.0)
        self.assertAlmostEqual(float(node.properties["crop_h"]), 1.0)

        store = self.window.project_session_controller.project_artifact_store()
        staged_entry = store.staged_entry(node.properties["source"])
        staged_path = store.resolve_staged_path(node.properties["source"])
        self.assertIsNotNone(staged_entry)
        self.assertIsNotNone(staged_path)
        assert staged_entry is not None and staged_path is not None
        staged_bytes = staged_path.read_bytes()
        self.assertEqual(staged_path.suffix.lower(), ".png")
        cropped = QImage(str(staged_path))
        self.assertFalse(cropped.isNull())
        self.assertEqual(cropped.width(), 20)
        self.assertEqual(cropped.height(), 10)
        self.assertEqual(staged_entry.extra["artifact_kind"], "image_crop_source")
        self.assertEqual(staged_entry.extra["mime_type"], "image/png")
        self.assertEqual(staged_entry.extra["size"], len(staged_bytes))
        self.assertEqual(
            staged_entry.extra["sha256"],
            hashlib.sha256(staged_bytes).hexdigest(),
        )
        self.assertEqual(staged_entry.extra["node_id"], node_id)
        self.assertEqual(len(metadata_spy), 1)

    def test_media_panel_video_frame_and_timestamp_actions_use_current_video_mode(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        video_path = Path(self._env.temp_path) / "media-action-source.mp4"
        video_path.write_bytes(b"video")
        video_node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={"source": str(video_path)},
            exposed_port_overrides={"source": False},
        )
        frame_path = Path(self._env.temp_path) / "captured-frame.png"
        frame = QImage(24, 12, QImage.Format.Format_ARGB32)
        frame.fill(QColor("#ba4d68"))
        self.assertTrue(frame.save(str(frame_path), "PNG"))
        metadata_spy = QSignalSpy(self.window.project_meta_changed)

        frame_result = self.window.media_panel_action_service.request_create_video_frame_image_node(
            video_node_id,
            str(frame_path),
            1200,
            360.0,
            80.0,
            240.0,
            120.0,
        )
        timestamp_result = self.window.media_panel_action_service.request_create_video_timestamp_annotation(
            video_node_id,
            1200,
            360.0,
            240.0,
        )

        workspace = self.window.model.project.workspaces[workspace_id]
        frame_node = workspace.nodes[str(frame_result["created_node_id"])]
        self.assertTrue(frame_result["success"])
        self.assertEqual(frame_node.type_id, "media.panel")
        self.assertFalse(frame_node.exposed_ports["source"])
        frame_ref = str(frame_node.properties["source"])
        self.assertTrue(frame_ref.startswith("temp://"))
        store = self.window.project_session_controller.project_artifact_store()
        frame_entry = store.staged_entry(frame_ref)
        staged_frame_path = store.resolve_staged_path(frame_ref)
        self.assertIsNotNone(frame_entry)
        self.assertIsNotNone(staged_frame_path)
        assert frame_entry is not None and staged_frame_path is not None
        staged_frame_bytes = staged_frame_path.read_bytes()
        self.assertEqual(frame_entry.extra["artifact_kind"], "video_frame_capture")
        self.assertEqual(frame_entry.extra["mime_type"], "image/png")
        self.assertEqual(frame_entry.extra["size"], len(staged_frame_bytes))
        self.assertEqual(
            frame_entry.extra["sha256"],
            hashlib.sha256(staged_frame_bytes).hexdigest(),
        )
        self.assertEqual(frame_entry.extra["node_id"], frame_node.node_id)
        self.assertTrue(timestamp_result["success"])
        note = workspace.nodes[str(timestamp_result["created_node_id"])]
        self.assertEqual(note.type_id, "passive.annotation.text")
        self.assertEqual(note.links[0].target_node_id, video_node_id)
        self.assertEqual(note.links[0].subtitle, "video_position_ms=1200")
        self.assertEqual(len(metadata_spy), 1)

    def test_media_panel_video_trim_copy_rejects_remote_effective_source(self) -> None:
        node_id = self.window.scene.create_node_from_type(
            type_id="media.panel",
            x=120.0,
            y=80.0,
            parent_node_id=None,
            select_node=True,
            property_overrides={"source": "https://example.test/clip.mp4"},
            exposed_port_overrides={"source": False},
        )

        result = self.window.media_panel_action_service.request_trim_video_clip_copy(
            node_id,
            1000,
            2000,
            360.0,
            80.0,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "source_unavailable")
        self.assertIn("ready local", result["error"]["message"])

    def test_image_panel_crop_apply_persists_hidden_normalized_rect(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)

        image_path = Path(self._env.temp_path) / "croppable-image-node.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))

        self.window.scene.set_node_property(node_id, "source", str(image_path))
        self.app.processEvents()

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        self._wait_for_media_preview(surface)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        apply_button = self._graph_node_child(node_id, "graphNodeMediaCropApplyButton")
        applied_viewport = self._graph_node_child(node_id, "graphNodeMediaAppliedImageViewport")
        applied_image = self._graph_node_child(node_id, "graphNodeMediaAppliedImage")
        initial_applied_width = float(applied_image.width())
        initial_applied_x = float(applied_image.x())

        image_renderer.setProperty("cropModeActive", True)
        image_renderer.setProperty("draftCropX", 0.1)
        image_renderer.setProperty("draftCropY", 0.2)
        image_renderer.setProperty("draftCropW", 0.5)
        image_renderer.setProperty("draftCropH", 0.6)
        self.app.processEvents()

        QMetaObject.invokeMethod(apply_button, "click")
        self.app.processEvents()

        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertAlmostEqual(float(node.properties["crop_x"]), 0.1)
        self.assertAlmostEqual(float(node.properties["crop_y"]), 0.2)
        self.assertAlmostEqual(float(node.properties["crop_w"]), 0.5)
        self.assertAlmostEqual(float(node.properties["crop_h"]), 0.6)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        applied_viewport = self._graph_node_child(node_id, "graphNodeMediaAppliedImageViewport")
        applied_image = self._graph_node_child(node_id, "graphNodeMediaAppliedImage")
        self.assertTrue(bool(image_renderer.property("hasEffectiveCrop")))
        self.assertGreater(float(applied_image.width()), initial_applied_width)
        self.assertLess(float(applied_image.x()), initial_applied_x)
        self.assertGreater(float(applied_viewport.width()), 0.0)
        self.assertEqual(
            {item["key"] for item in self.window.selected_node_property_items},
            {"source"},
        )

    def test_image_panel_crop_action_does_not_start_host_drag(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        other_node_id = self.window.scene.add_node_from_type("core.constant", x=420.0, y=80.0)

        image_path = Path(self._env.temp_path) / "clickable-crop-button.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))

        self.window.scene.set_node_property(node_id, "source", str(image_path))
        self.window.scene.focus_node(other_node_id)
        self.app.processEvents()

        card = self._graph_node_card(node_id)
        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        self._wait_for_media_preview(surface)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        workspace = self.window.model.project.workspaces[workspace_id]
        initial_x = float(workspace.nodes[node_id].x)
        initial_y = float(workspace.nodes[node_id].y)
        nodes_changed: list[str] = []

        def _record_nodes_changed() -> None:
            nodes_changed.append("nodes")

        self.window.scene.nodes_changed.connect(_record_nodes_changed)
        self.addCleanup(self.window.scene.nodes_changed.disconnect, _record_nodes_changed)

        self.assertFalse(bool(image_renderer.property("cropModeActive")))
        card = self._graph_node_card(node_id)
        crop_button_candidates = [
            item
            for item in self._walk_items(card)
            if item.objectName() == "graphNodeMediaCropButton"
        ]
        self.assertEqual(crop_button_candidates, [])
        self.assertNotEqual(self.window.scene.selected_node_id(), node_id)

        QTest.mouseMove(self.window.quick_widget, self._item_widget_center(card))
        self.app.processEvents()

        surface_actions_value = surface.property("surfaceActions")
        if isinstance(surface_actions_value, QJSValue):
            surface_actions_value = surface_actions_value.toVariant()
        surface_actions = list(surface_actions_value or [])
        crop_action = next(
            action for action in surface_actions if action["id"] == "crop"
        )
        self.assertTrue(bool(crop_action["enabled"]))

        nodes_count_before = len(nodes_changed)
        QMetaObject.invokeMethod(
            surface,
            "dispatchSurfaceAction",
            Q_ARG("QVariant", "crop"),
        )
        self.app.processEvents()

        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        node = workspace.nodes[node_id]
        self.assertEqual(len(nodes_changed), nodes_count_before)
        self.assertTrue(bool(image_renderer.property("cropModeActive")))
        self.assertAlmostEqual(float(node.x), initial_x, places=6)
        self.assertAlmostEqual(float(node.y), initial_y, places=6)

    def test_image_panel_crop_apply_closes_when_crop_is_unchanged(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)

        image_path = Path(self._env.temp_path) / "unchanged-crop-image-node.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))

        self.window.scene.set_node_property(node_id, "source", str(image_path))
        self.window.scene.set_node_property(node_id, "crop_x", 0.1)
        self.window.scene.set_node_property(node_id, "crop_y", 0.2)
        self.window.scene.set_node_property(node_id, "crop_w", 0.5)
        self.window.scene.set_node_property(node_id, "crop_h", 0.6)
        self.app.processEvents()

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        self._wait_for_media_preview(surface)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        apply_button = self._graph_node_child(node_id, "graphNodeMediaCropApplyButton")

        image_renderer.setProperty("cropModeActive", True)
        image_renderer.setProperty("draftCropX", 0.1)
        image_renderer.setProperty("draftCropY", 0.2)
        image_renderer.setProperty("draftCropW", 0.5)
        image_renderer.setProperty("draftCropH", 0.6)
        self.app.processEvents()
        self.assertTrue(bool(image_renderer.property("cropModeActive")))

        QMetaObject.invokeMethod(apply_button, "click")
        self.app.processEvents()

        self.assertFalse(bool(image_renderer.property("cropModeActive")))
        node = self.window.model.project.workspaces[workspace_id].nodes[node_id]
        self.assertAlmostEqual(float(node.properties["crop_x"]), 0.1)
        self.assertAlmostEqual(float(node.properties["crop_y"]), 0.2)
        self.assertAlmostEqual(float(node.properties["crop_w"]), 0.5)
        self.assertAlmostEqual(float(node.properties["crop_h"]), 0.6)

    def test_image_panel_crop_apply_and_cancel_clicks_bypass_host_drag(self) -> None:
        workspace_id = self.window.workspace_manager.active_workspace_id()
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)

        image_path = Path(self._env.temp_path) / "apply-cancel-crop-button.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))

        self.window.scene.set_node_property(node_id, "source", str(image_path))
        self.app.processEvents()

        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        self._wait_for_media_preview(surface)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        workspace = self.window.model.project.workspaces[workspace_id]
        initial_x = float(workspace.nodes[node_id].x)
        initial_y = float(workspace.nodes[node_id].y)

        image_renderer.setProperty("cropModeActive", True)
        image_renderer.setProperty("draftCropX", 0.1)
        image_renderer.setProperty("draftCropY", 0.2)
        image_renderer.setProperty("draftCropW", 0.5)
        image_renderer.setProperty("draftCropH", 0.6)
        self.app.processEvents()

        apply_button = self._graph_node_child(node_id, "graphNodeMediaCropApplyButton")
        self.assertTrue(bool(apply_button.property("visible")))

        QMetaObject.invokeMethod(apply_button, "click")
        self.app.processEvents()

        node = workspace.nodes[node_id]
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        self.assertFalse(bool(image_renderer.property("cropModeActive")))
        self.assertAlmostEqual(float(node.properties["crop_x"]), 0.1)
        self.assertAlmostEqual(float(node.properties["crop_y"]), 0.2)
        self.assertAlmostEqual(float(node.properties["crop_w"]), 0.5)
        self.assertAlmostEqual(float(node.properties["crop_h"]), 0.6)
        self.assertAlmostEqual(float(node.x), initial_x, places=6)
        self.assertAlmostEqual(float(node.y), initial_y, places=6)

        image_renderer.setProperty("cropModeActive", True)
        image_renderer.setProperty("draftCropX", 0.2)
        image_renderer.setProperty("draftCropY", 0.1)
        image_renderer.setProperty("draftCropW", 0.4)
        image_renderer.setProperty("draftCropH", 0.7)
        self.app.processEvents()

        cancel_button = self._graph_node_child(node_id, "graphNodeMediaCropCancelButton")
        self.assertTrue(bool(cancel_button.property("visible")))

        QMetaObject.invokeMethod(cancel_button, "click")
        self.app.processEvents()

        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )
        node = workspace.nodes[node_id]
        self.assertFalse(bool(image_renderer.property("cropModeActive")))
        self.assertAlmostEqual(float(node.properties["crop_x"]), 0.1)
        self.assertAlmostEqual(float(node.properties["crop_y"]), 0.2)
        self.assertAlmostEqual(float(node.properties["crop_w"]), 0.5)
        self.assertAlmostEqual(float(node.properties["crop_h"]), 0.6)
        self.assertAlmostEqual(float(node.x), initial_x, places=6)
        self.assertAlmostEqual(float(node.y), initial_y, places=6)

    def test_image_panel_crop_handles_expose_expected_cursor_and_hit_slop(self) -> None:
        node_id = self._create_browse_media_panel()
        self.window.scene.focus_node(node_id)

        image_path = Path(self._env.temp_path) / "draggable-crop-handles.png"
        image = QImage(40, 20, QImage.Format.Format_ARGB32)
        image.fill(QColor("#2c85bf"))
        self.assertTrue(image.save(str(image_path)))

        self.window.scene.set_node_property(node_id, "source", str(image_path))
        surface = self._graph_node_child(node_id, "graphNodeMediaSurface")
        self._wait_for_media_preview(surface)
        image_renderer = self._graph_node_child(
            node_id, "graphNodeMediaImageRenderer"
        )

        image_renderer.setProperty("cropModeActive", True)
        self.app.processEvents()

        top_left_handle = self._graph_node_child_with_property(
            node_id,
            "graphNodeMediaCropHandleMouseArea",
            "handleId",
            "top_left",
        )
        top_left_visual = self._graph_node_child_with_property(
            node_id,
            "graphNodeMediaCropHandle",
            "handleId",
            "top_left",
        )
        self.assertEqual(
            top_left_handle.property("cursorShape"),
            Qt.CursorShape.SizeFDiagCursor,
        )
        self.assertTrue(bool(top_left_handle.property("hoverEnabled")))
        self.assertGreater(float(top_left_handle.width()), float(top_left_visual.width()))
        self.assertGreater(float(top_left_handle.height()), float(top_left_visual.height()))
