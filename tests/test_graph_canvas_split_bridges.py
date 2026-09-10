from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.records import NodeLinkRecord
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.ui.shell.state import ShellRunState
from ea_node_editor.settings import DEFAULT_GRAPHICS_SETTINGS
from ea_node_editor.ui.shell.tooltip_policy import (
    default_tooltip_category_preferences,
)
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_canvas_state import graphics_preferences_props as graphics_preferences_module

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")


class _WorkspaceLinkController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def switch_workspace(self, workspace_id: str) -> None:
        self.calls.append(("switch_workspace", (workspace_id,)))

    def jump_to_graph_node(self, workspace_id: str, node_id: str) -> bool:
        self.calls.append(("jump_to_graph_node", (workspace_id, node_id)))
        return True


class _CanvasRewireSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.result = True

    def request_rewire_edges(
        self,
        edge_ids: list[object],
        endpoint: str,
        node_id: str,
        port_key: str,
        copy_requested: bool,
        append_requested: bool,
    ) -> bool:
        self.calls.append(
            (
                "request_rewire_edges",
                (
                    list(edge_ids),
                    endpoint,
                    node_id,
                    port_key,
                    copy_requested,
                    append_requested,
                ),
            )
        )
        return self.result


class _RewireEndpointPolicy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.result: object = {
            "candidate_role": "target",
            "compatible_endpoint_ids": [{"node_id": "sink", "port_key": "payload"}],
        }

    def compatible_rewire_endpoint_snapshot(
        self,
        edge_ids: list[object],
        endpoint: str,
        copy_requested: bool,
        append_requested: bool,
    ) -> object:
        self.calls.append(
            (
                "compatible_rewire_endpoint_snapshot",
                (list(edge_ids), endpoint, copy_requested, append_requested),
            )
        )
        return self.result


class _GraphCanvasShellHostStub(QObject):
    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()
    run_failure_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.graphics_minimap_expanded = True
        self.graphics_show_grid = True
        self.graphics_canvas_background_variant = "theme"
        self.graphics_grid_style = "lines"
        self.graphics_edge_crossing_style = "none"
        self.graphics_graph_label_pixel_size = 10
        self.graphics_graph_node_icon_pixel_size_override = None
        self.graphics_node_title_icon_pixel_size = 10
        self.graphics_recent_text_colors: list[str] = []
        self.graphics_media_panel_defaults = {
            "show_title": True,
            "show_frame": True,
            "autoplay_animations": True,
            "source_input_exposed": True,
        }
        self.graphics_media_panel_default_show_title = True
        self.graphics_media_panel_default_show_frame = True
        self.graphics_media_panel_autoplay_animations = True
        self.graphics_media_panel_source_input_exposed = True
        self.graphics_show_minimap = True
        self.graphics_show_canvas_options_button = True
        self.graphics_show_port_labels = True
        self.graphics_node_elapsed_time_unit = "seconds"
        self.graphics_node_elapsed_time_visibility = "always"
        self.graphics_node_comment_editor_default = "canvas_popover"
        self.graphics_notched_ports = True
        self.graphics_node_floating_toolbar_opens_on_hover = False
        self.selected_run_preview_before_run = True
        self.graphics_show_tooltips = True
        self.graphics_tooltip_categories = default_tooltip_category_preferences()
        self.graphics_tooltip_category_visibility = {
            **self.graphics_tooltip_categories,
            "critical": True,
        }
        self.graphics_folder_explorer_column_widths: dict[str, int] = {}
        self.graphics_node_shadow = True
        self.graphics_shadow_strength = 70
        self.graphics_shadow_softness = 50
        self.graphics_shadow_offset = 4
        self.graphics_status_bar_layout = "option_1"
        self.graphics_show_fps_telemetry = True
        self.graphics_floating_toolbar_style = "compact_pill"
        self.graphics_floating_toolbar_size = "small"
        self.graphics_selection_toolbar_mode = "minimal_ghost_menu"
        self.graphics_selection_toolbar_minimal_menu_trigger = "click_affordance"
        self.graphics_expand_collision_avoidance = {"enabled": True}
        self.graphics_lightweight_canvas = False
        self.graphics_plot_default_backend_per_type: dict[str, str] = {}
        self.active_theme_id = "stitch_dark"
        self.graphics_graph_follow_shell_theme = False
        self.graphics_selected_graph_theme_id = "graph_stitch_dark"
        self.snap_to_grid_enabled = True
        self.snap_grid_size = 24.0
        self.run_state = ShellRunState()
        self._return_values: dict[str, object] = {
            "request_open_subnode_scope": True,
            "browse_node_property_path": "C:/temp/from-canvas-bridge.txt",
            "internalize_node_property_path": "temp://from-canvas-internalized",
            "open_local_file_source": {
                "success": True,
                "path": "C:/temp/message.eml",
                "error": {},
            },
            "pick_node_property_color": "#AA5500",
            "request_drop_node_from_library": True,
            "request_drop_node_from_library_with_properties": True,
            "request_connect_ports": True,
            "video_frame_capture_path": "C:/temp/corex-video-frame.png",
            "request_save_image_crop_replace": {
                "success": True,
                "created_node_id": "image-node-1",
                "created_type_id": "media.panel",
                "source_ref": "project-staged://image_crop_1",
                "link_id": "",
                "error": {},
            },
            "request_create_video_frame_image_node": {
                "success": True,
                "created_node_id": "image-node-1",
                "created_type_id": "media.panel",
                "source_ref": "project-staged://video_frame_1",
                "link_id": "",
                "error": {},
            },
            "request_trim_video_clip_replace": {
                "success": True,
                "created_node_id": "",
                "created_type_id": "media.panel",
                "source_ref": "project-staged://video_clip_1",
                "link_id": "",
                "error": {},
                "request_id": "trim-replace-1",
            },
            "request_trim_video_clip_copy": {
                "success": True,
                "created_node_id": "video-copy-1",
                "created_type_id": "media.panel",
                "source_ref": "project-staged://video_clip_2",
                "link_id": "",
                "error": {},
                "request_id": "trim-copy-1",
            },
            "request_create_video_timestamp_annotation": {
                "success": True,
                "created_node_id": "text-node-1",
                "created_type_id": "passive.annotation.text",
                "source_ref": "",
                "link_id": "link-video-1",
                "error": {},
            },
            "request_open_connection_quick_insert": True,
            "request_delete_selected_graph_items": True,
            "request_navigate_scope_parent": True,
            "request_navigate_scope_root": True,
            "request_edit_flow_edge_style": True,
            "request_edit_flow_edge_label": True,
            "request_reset_flow_edge_style": True,
            "request_copy_flow_edge_style": True,
            "request_paste_flow_edge_style": True,
            "request_remove_edge": True,
            "request_publish_custom_workflow_from_node": True,
            "request_edit_passive_node_style": True,
            "request_reset_passive_node_style": True,
            "request_copy_passive_node_style": True,
            "request_paste_passive_node_style": True,
            "request_propagate_passive_node_style": True,
            "request_rename_node": True,
            "request_ungroup_node": True,
            "request_remove_node": True,
        }

    def _record(self, name: str, *args: object) -> object:
        self.calls.append((name, args))
        return self._return_values.get(name)

    def set_graphics_minimap_expanded(self, expanded: bool) -> None:
        self.graphics_minimap_expanded = bool(expanded)
        self._record("set_graphics_minimap_expanded", bool(expanded))

    def set_graphics_canvas_background_variant(self, variant: str) -> None:
        self.graphics_canvas_background_variant = str(variant)
        self._record("set_graphics_canvas_background_variant", str(variant))

    def set_graphics_show_port_labels(self, show_port_labels: bool) -> None:
        self.graphics_show_port_labels = bool(show_port_labels)
        self._record("set_graphics_show_port_labels", bool(show_port_labels))

    def set_graphics_node_elapsed_time_unit(self, unit: str) -> None:
        self.graphics_node_elapsed_time_unit = str(unit)
        self._record("set_graphics_node_elapsed_time_unit", str(unit))

    def set_graphics_node_elapsed_time_visibility(self, visibility: str) -> None:
        self.graphics_node_elapsed_time_visibility = str(visibility)
        self._record("set_graphics_node_elapsed_time_visibility", str(visibility))

    def set_graphics_node_comment_editor_default(self, value: str) -> None:
        self.graphics_node_comment_editor_default = str(value)
        self._record("set_graphics_node_comment_editor_default", str(value))

    def set_folder_explorer_column_widths(self, widths: dict[str, object]) -> None:
        self.graphics_folder_explorer_column_widths = dict(widths)
        self._record("set_folder_explorer_column_widths", dict(widths))

    def set_graphics_selection_toolbar_mode(self, mode: str) -> None:
        self.graphics_selection_toolbar_mode = str(mode)
        self._record("set_graphics_selection_toolbar_mode", str(mode))

    def set_graphics_selection_toolbar_minimal_menu_trigger(self, trigger: str) -> None:
        self.graphics_selection_toolbar_minimal_menu_trigger = str(trigger)
        self._record(
            "set_graphics_selection_toolbar_minimal_menu_trigger",
            str(trigger),
        )

    def tooltip_category_enabled(self, category: str) -> bool:
        return bool(self.graphics_tooltip_category_visibility.get(str(category), False))

    def __getattr__(self, name: str):  # noqa: ANN204
        if name.startswith(
            (
                "browse_",
                "clear_",
                "internalize_",
                "pick_",
                "record_",
                "request_",
                "set_",
                "video_",
            )
        ):
            return lambda *args: self._record(name, *args)
        raise AttributeError(name)

    def describe_pdf_preview(self, source: str, page_number: object) -> dict[str, object]:
        self._record("describe_pdf_preview", source, page_number)
        return {"source": source, "page_number": int(page_number), "valid": True}

    def describe_mail_preview(self, source: str) -> dict[str, object]:
        self._record("describe_mail_preview", source)
        return {
            "source": source,
            "state": "ready",
            "preview_url": "file:///C:/temp/mail-preview.html",
        }

    def open_local_file_source(self, source: str, chooser: bool = False) -> dict[str, object]:
        self._record("open_local_file_source", source, chooser)
        return dict(self._return_values["open_local_file_source"])

    def describe_tabular_preview(
        self,
        properties_or_source: dict[str, object] | str,
        request: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self._record("describe_tabular_preview", properties_or_source, request)
        properties = (
            properties_or_source
            if isinstance(properties_or_source, dict)
            else {"path": properties_or_source}
        )
        return {
            "state": "ready",
            "content_kind": "tabular",
            "preview_kind": "table",
            "source": {"path": str(properties.get("path", "")), "format_id": "csv"},
            "window": {
                "columns": ["station", "temp"],
                "rows": [{"station": "S0", "temp": "20.0"}],
                "request": dict(request or {}),
            },
        }


class _GraphCanvasTooltipCanvasSourceStub(QObject):
    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()


class _GraphCanvasSceneBridgeStub(QObject):
    workspace_changed = pyqtSignal(str)
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.workspace_id = "ws-1"
        self.nodes_model = [{"node_id": "node-1", "selected": True}]
        self.backdrop_nodes_model = [{"node_id": "backdrop-1", "selected": False}]
        self.minimap_nodes_model = [{"node_id": "node-1", "x": 10.0, "y": 15.0}]
        self.workspace_scene_bounds_payload = {
            "x": 0.0,
            "y": 0.0,
            "width": 640.0,
            "height": 360.0,
        }
        self.edges_model = [{"edge_id": "edge-1"}]
        self.selected_node_ids = ["node-1"]
        self.selected_node_lookup = {"node-1": True}
        self._return_values: dict[str, object] = {
            "are_port_kinds_compatible": True,
            "are_data_types_compatible": True,
            "move_nodes_by_delta": True,
            "consume_pending_surface_action": True,
            "set_node_properties": True,
            "upsert_node_link": "link-1",
            "remove_node_link": True,
            "move_node_link": True,
            "open_node_link": True,
            "upsert_node_comment": "comment-1",
            "remove_node_comment": True,
            "set_node_comment_resolved": True,
            "set_node_comment_pinned": True,
            "resolve_all_node_comments": True,
            "mark_node_comments_read": True,
            "wrap_selected_nodes_in_group_backdrop": True,
        }

    def _record(self, name: str, *args: object) -> object:
        self.calls.append((name, args))
        return self._return_values.get(name)

    def __getattr__(self, name: str):  # noqa: ANN204
        if name.startswith(
            (
                "are_",
                "clear_",
                "consume_",
                "mark_",
                "move_",
                "open_",
                "remove_",
                "resize_",
                "resolve_",
                "select_",
                "set_",
                "upsert_",
                "wrap_",
            )
        ):
            return lambda *args: self._record(name, *args)
        raise AttributeError(name)

    def normalize_edge_label(self, label: object) -> str:
        self._record("normalize_edge_label", label)
        return str(label or "").strip()

    def normalize_edge_visual_style(self, visual_style: object) -> dict[str, object]:
        self._record("normalize_edge_visual_style", visual_style)
        return dict(visual_style) if isinstance(visual_style, dict) else {}


class _GraphCanvasViewBridgeStub(QObject):
    view_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.center_x = 18.5
        self.center_y = -42.0
        self.zoom_value = 1.75
        self.visible_scene_rect_payload = {
            "x": -120.0,
            "y": -80.0,
            "width": 240.0,
            "height": 160.0,
        }

    def _record(self, name: str, *args: object) -> None:
        self.calls.append((name, args))

    def adjust_zoom(self, factor: float) -> None:
        self._record("adjust_zoom", factor)

    def pan_by(self, delta_x: float, delta_y: float) -> None:
        self._record("pan_by", delta_x, delta_y)

    def set_viewport_size(self, width: float, height: float) -> None:
        self._record("set_viewport_size", width, height)

    def center_on_scene_point(self, x: float, y: float) -> None:
        self._record("center_on_scene_point", x, y)


class GraphCanvasSplitBridgeTests(unittest.TestCase):
    __test__ = True

    def test_trigger_node_routes_directly_to_run_controller(self) -> None:
        run_controller = mock.Mock()
        run_controller.trigger_node.return_value = True
        bridge = GraphCanvasCommandBridge(run_controller=run_controller)

        self.assertTrue(bridge.trigger_node("node-1"))
        run_controller.trigger_node.assert_called_once_with("node-1")

    def test_media_action_fallbacks_keep_shape_and_use_neutral_message(self) -> None:
        bridge = GraphCanvasCommandBridge()
        results = (
            (
                bridge.request_save_image_crop_replace("image-1", {}),
                {"success", "created_node_id", "created_type_id", "source_ref", "request_id", "error"},
            ),
            (
                bridge.request_create_video_frame_image_node(
                    "video-1",
                    "missing.png",
                    0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ),
                {"success", "created_node_id", "created_type_id", "source_ref", "error"},
            ),
            (
                bridge.request_create_video_timestamp_annotation(
                    "video-1",
                    0,
                    0.0,
                    0.0,
                ),
                {"success", "created_node_id", "created_type_id", "link_id", "error"},
            ),
            (
                bridge.request_trim_video_clip_replace("video-1", 0, 1, {}),
                {"success", "created_node_id", "created_type_id", "source_ref", "request_id", "error"},
            ),
            (
                bridge.request_trim_video_clip_copy(
                    "video-1",
                    0,
                    1,
                    0.0,
                    0.0,
                    {},
                ),
                {"success", "created_node_id", "created_type_id", "source_ref", "request_id", "error"},
            ),
        )

        for result, expected_keys in results:
            with self.subTest(result=result):
                self.assertFalse(result["success"])
                self.assertEqual(result["error"]["code"], "mutation_unavailable")
                self.assertEqual(
                    result["error"]["message"],
                    "Media Panel actions are unavailable.",
                )
                self.assertEqual(set(result), expected_keys)

    def test_command_bridge_text_annotation_style_clipboard_is_internal(self) -> None:
        app = QApplication.instance() or QApplication([])
        app.setProperty("eaNodeEditorStyleClipboard:text-annotation-style", "")
        clipboard = app.clipboard()
        clipboard.setText("external clipboard text")
        bridge = GraphCanvasCommandBridge()

        self.assertFalse(bridge.has_text_annotation_style())
        self.assertEqual(bridge.paste_text_annotation_style(), {})
        self.assertTrue(
            bridge.copy_text_annotation_style(
                {
                    "text": "Do not copy content",
                    "format": "plain",
                    "font_family": "  Segoe UI  ",
                    "font_size": 999,
                    "text_color": "#aabbcc",
                    "horizontal_alignment": "right",
                    "line_height": 9,
                    "opacity": -2,
                }
            )
        )

        self.assertEqual(clipboard.text(), "external clipboard text")
        self.assertTrue(bridge.has_text_annotation_style())
        self.assertEqual(
            bridge.paste_text_annotation_style(),
            {
                "font_family": "Segoe UI",
                "font_size": 144,
                "text_color": "#AABBCC",
                "horizontal_alignment": "right",
                "line_height": 4.0,
                "opacity": 0,
            },
        )

    def test_command_bridge_opens_workspace_node_link_through_shell_navigation(self) -> None:
        controller = _WorkspaceLinkController()
        active_workspace = SimpleNamespace(
            nodes={
                "node-1": SimpleNamespace(
                    links=[
                        NodeLinkRecord(
                            link_id="link-workspace",
                            kind="workspace",
                            title="Target workspace",
                            target="ws-target",
                        )
                    ]
                )
            }
        )
        shell = SimpleNamespace(
            model=SimpleNamespace(
                project=SimpleNamespace(
                    workspaces={
                        "ws-active": active_workspace,
                        "ws-target": SimpleNamespace(nodes={}),
                    }
                )
            ),
            workspace_manager=SimpleNamespace(active_workspace_id=lambda: "ws-active"),
            workspace_navigation_controller=controller,
        )
        scene = _GraphCanvasSceneBridgeStub()
        scene._return_values["open_node_link"] = False
        command_bridge = GraphCanvasCommandBridge(
            scene_bridge=scene,
            model_provider=lambda: shell.model,
            active_workspace_id_provider=shell.workspace_manager.active_workspace_id,
            workspace_navigation_controller=controller,
        )

        self.assertTrue(command_bridge.open_node_link("node-1", "link-workspace"))
        self.assertEqual(controller.calls, [("switch_workspace", ("ws-target",))])
        self.assertNotIn(("open_node_link", ("node-1", "link-workspace")), scene.calls)

    def test_command_bridge_opens_cross_workspace_node_link_through_graph_jump(self) -> None:
        controller = _WorkspaceLinkController()
        active_workspace = SimpleNamespace(
            nodes={
                "node-source": SimpleNamespace(
                    links=[
                        NodeLinkRecord(
                            link_id="link-cross-node",
                            kind="node",
                            title="Target node",
                            target="node-target",
                            target_workspace_id="ws-target",
                            target_node_id="node-target",
                        )
                    ]
                )
            }
        )
        target_workspace = SimpleNamespace(nodes={"node-target": SimpleNamespace(links=[])})
        shell = SimpleNamespace(
            model=SimpleNamespace(
                project=SimpleNamespace(
                    workspaces={
                        "ws-active": active_workspace,
                        "ws-target": target_workspace,
                    }
                )
            ),
            workspace_manager=SimpleNamespace(active_workspace_id=lambda: "ws-active"),
            workspace_navigation_controller=controller,
        )
        scene = _GraphCanvasSceneBridgeStub()
        scene._workspace_id = "ws-active"
        scene._return_values["open_node_link"] = False
        command_bridge = GraphCanvasCommandBridge(
            scene_bridge=scene,
            model_provider=lambda: shell.model,
            active_workspace_id_provider=shell.workspace_manager.active_workspace_id,
            workspace_navigation_controller=controller,
        )

        self.assertTrue(command_bridge.open_node_link("node-source", "link-cross-node"))
        self.assertEqual(controller.calls, [("jump_to_graph_node", ("ws-target", "node-target"))])
        self.assertNotIn(("open_node_link", ("node-source", "link-cross-node")), scene.calls)

    def test_command_bridge_routes_canvas_commands_to_explicit_canvas_host_scene_and_view_sources(self) -> None:
        host = _GraphCanvasShellHostStub()
        presenter = _GraphCanvasShellHostStub()
        host_source = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        scene._return_values["open_subnode_scope"] = True
        scene._return_values["set_node_collapsed"] = True
        view = _GraphCanvasViewBridgeStub()
        bridge = GraphCanvasCommandBridge(
            host,
            search_scope_controller=SimpleNamespace(navigate_scope=lambda callback: callback()),
            app_preferences_source=presenter,
            graphics_preferences_changed_signal=presenter.graphics_preferences_changed,
            run_controller=presenter,
            show_graph_hint=lambda message, timeout: presenter._record(
                "show_graph_hint", message, timeout
            ),
            inspector_source=presenter,
            library_source=presenter,
            workspace_edit_controller=presenter,
            workspace_drop_connect_controller=presenter,
            media_action_source=presenter,
            host_source=host_source,
            scene_bridge=scene,
            view_bridge=view,
        )

        self.assertIs(bridge.parent(), host)
        self.assertIs(bridge._run_controller, presenter)
        self.assertIs(bridge._workspace_edit_controller, presenter)
        self.assertIs(bridge.media_action_source, presenter)
        self.assertIs(bridge.host_source, host_source)
        self.assertIs(bridge.scene_bridge, scene)
        self.assertIs(bridge.view_bridge, view)

        bridge.set_graphics_minimap_expanded(False)
        bridge.adjust_zoom(1.15)
        bridge.pan_by(-12.0, 8.0)
        bridge.set_viewport_size(1280.0, 720.0)
        bridge.center_on_scene_point(96.0, 144.0)
        self.assertTrue(bridge.request_open_subnode_scope("subnode-1"))
        self.assertEqual(
            bridge.browse_node_property_path("node-1", "source_path", "C:/temp/current.txt"),
            "C:/temp/from-canvas-bridge.txt",
        )
        self.assertEqual(
            bridge.internalize_node_property_path("node-1", "source_path", "C:/temp/current.txt"),
            "temp://from-canvas-internalized",
        )
        self.assertEqual(
            bridge.pick_node_property_color("node-1", "accent_color", "#336699"),
            "#AA5500",
        )
        self.assertEqual(
            bridge.request_save_image_crop_replace(
                "image-1",
                {"x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8},
            )["source_ref"],
            "project-staged://image_crop_1",
        )
        self.assertTrue(
            bridge.request_drop_node_from_library(
                "core.logger",
                120.0,
                240.0,
                "port",
                "node-1",
                "payload",
                "edge-1",
            )
        )
        self.assertTrue(bridge.request_connect_ports("node-1", "value", "node-2", "payload"))
        self.assertTrue(
            bridge.request_open_connection_quick_insert(
                "node-1",
                "value",
                20.0,
                30.0,
                400.0,
                300.0,
            )
        )
        bridge.request_open_canvas_quick_insert(15.0, 25.0, 115.0, 215.0)
        self.assertTrue(bridge.request_delete_selected_graph_items(["edge-1"]))
        self.assertTrue(bridge.request_navigate_scope_parent())
        self.assertTrue(bridge.request_navigate_scope_root())
        bridge.select_node("node-1", True)
        bridge.clear_selection()
        bridge.select_nodes_in_rect(1.0, 2.0, 3.0, 4.0, True)
        bridge.set_node_property("node-1", "message", "hello")
        bridge.set_pending_surface_action("node-1")
        self.assertTrue(bridge.consume_pending_surface_action("node-1"))
        self.assertTrue(bridge.set_node_properties("node-1", {"message": "bridge"}))
        self.assertTrue(bridge.set_node_collapsed("node-1", True))
        self.assertEqual(
            bridge.upsert_node_link(
                "node-1",
                "",
                "url",
                "Docs",
                "https://example.com/docs",
                "Reference",
            ),
            "link-1",
        )
        self.assertTrue(bridge.remove_node_link("node-1", "link-1"))
        self.assertTrue(bridge.move_node_link("node-1", "link-1", -1))
        self.assertTrue(bridge.open_node_link("node-1", "link-1"))
        self.assertTrue(bridge.are_port_kinds_compatible("data", "data"))
        self.assertTrue(bridge.are_data_types_compatible("text", "text"))
        self.assertTrue(bridge.move_nodes_by_delta(["node-1", "node-2"], 10.0, -5.0))
        bridge.move_node("node-1", 160.0, 220.0)
        bridge.resize_node("node-1", 320.0, 180.0)
        bridge.set_node_geometry("node-1", 150.0, 210.0, 340.0, 190.0)
        self.assertEqual(bridge.normalize_edge_label("  Primary path  "), "Primary path")
        self.assertTrue(bridge.set_edge_label("edge-1", "Loop branch"))
        self.assertTrue(bridge.clear_edge_label("edge-1"))
        self.assertEqual(
            bridge.normalize_edge_visual_style({"stroke_color": "#E06C75", "stroke_pattern": "dashed"}),
            {"stroke_color": "#E06C75", "stroke_pattern": "dashed"},
        )
        self.assertTrue(bridge.set_edge_visual_style("edge-1", {"stroke_color": "#E06C75"}))
        self.assertTrue(bridge.clear_edge_visual_style("edge-1"))
        bridge.set_graph_cursor_shape(13)
        bridge.clear_graph_cursor_shape()
        self.assertEqual(
            bridge.describe_pdf_preview("C:/temp/preview.pdf", 2),
            {
                "source": "C:/temp/preview.pdf",
                "page_number": 2,
                "valid": True,
            },
        )
        self.assertEqual(
            bridge.describe_mail_preview("C:/temp/message.eml"),
            {
                "source": "C:/temp/message.eml",
                "state": "ready",
                "preview_url": "file:///C:/temp/mail-preview.html",
            },
        )
        self.assertEqual(
            bridge.open_local_file_source("C:/temp/message.eml", True),
            {"success": True, "path": "C:/temp/message.eml", "error": {}},
        )

        self.assertEqual(
            presenter.calls,
            [
                ("browse_node_property_path", ("node-1", "source_path", "C:/temp/current.txt")),
                ("internalize_node_property_path", ("node-1", "source_path", "C:/temp/current.txt")),
                ("pick_node_property_color", ("node-1", "accent_color", "#336699")),
                (
                    "request_save_image_crop_replace",
                    ("image-1", {"x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8}),
                ),
                (
                    "request_drop_node_from_library",
                    ("core.logger", 120.0, 240.0, "port", "node-1", "payload", "edge-1"),
                ),
                ("request_connect_ports", ("node-1", "value", "node-2", "payload", False)),
                (
                    "request_open_connection_quick_insert",
                    ("node-1", "value", 20.0, 30.0, 400.0, 300.0, False),
                ),
                ("request_open_canvas_quick_insert", (15.0, 25.0, 115.0, 215.0)),
            ],
        )
        self.assertEqual(
            host_source.calls,
            [
                ("request_delete_selected_graph_items", (["edge-1"],)),
                ("request_navigate_scope_parent", ()),
                ("request_navigate_scope_root", ()),
                ("set_graph_cursor_shape", (13,)),
                ("clear_graph_cursor_shape", ()),
                ("describe_pdf_preview", ("C:/temp/preview.pdf", 2)),
                ("describe_mail_preview", ("C:/temp/message.eml",)),
                ("open_local_file_source", ("C:/temp/message.eml", True)),
            ],
        )
        self.assertEqual(
            scene.calls,
            [
                ("open_subnode_scope", ("subnode-1",)),
                ("select_node", ("node-1", True)),
                ("clear_selection", ()),
                ("select_nodes_in_rect", (1.0, 2.0, 3.0, 4.0, True)),
                ("set_node_property", ("node-1", "message", "hello")),
                ("set_pending_surface_action", ("node-1",)),
                ("consume_pending_surface_action", ("node-1",)),
                ("set_node_properties", ("node-1", {"message": "bridge"})),
                ("set_node_collapsed", ("node-1", True)),
                (
                    "upsert_node_link",
                    ("node-1", "", "url", "Docs", "https://example.com/docs", "Reference"),
                ),
                ("remove_node_link", ("node-1", "link-1")),
                ("move_node_link", ("node-1", "link-1", -1)),
                ("open_node_link", ("node-1", "link-1")),
                ("are_port_kinds_compatible", ("data", "data")),
                ("are_data_types_compatible", ("text", "text")),
                ("move_nodes_by_delta", (["node-1", "node-2"], 10.0, -5.0)),
                ("move_node", ("node-1", 160.0, 220.0)),
                ("resize_node", ("node-1", 320.0, 180.0)),
                ("set_node_geometry", ("node-1", 150.0, 210.0, 340.0, 190.0)),
                ("normalize_edge_label", ("  Primary path  ",)),
                ("set_edge_label", ("edge-1", "Loop branch")),
                ("clear_edge_label", ("edge-1",)),
                (
                    "normalize_edge_visual_style",
                    ({"stroke_color": "#E06C75", "stroke_pattern": "dashed"},),
                ),
                ("set_edge_visual_style", ("edge-1", {"stroke_color": "#E06C75"})),
                ("clear_edge_visual_style", ("edge-1",)),
            ],
        )
        self.assertEqual(
            view.calls,
            [
                ("adjust_zoom", (1.15,)),
                ("pan_by", (-12.0, 8.0)),
                ("set_viewport_size", (1280.0, 720.0)),
                ("center_on_scene_point", (96.0, 144.0)),
            ],
        )

    def test_graphics_commands_use_their_declared_owner(self) -> None:
        canvas = _GraphCanvasShellHostStub()
        graphics = _GraphCanvasShellHostStub()
        bridge = GraphCanvasCommandBridge(
            search_scope_controller=canvas,
            app_preferences_source=canvas,
            graphics_preferences_changed_signal=canvas.graphics_preferences_changed,
            graphics_source=graphics,
        )
        cases = (
            (canvas, "set_snap_to_grid_enabled", (False,)),
            (canvas, "set_graphics_minimap_expanded", (False,)),
            (canvas, "set_selected_run_preview_before_run", (False,)),
            (graphics, "set_graphics_show_grid", (False,)),
            (graphics, "set_graphics_canvas_background_variant", ("white",)),
            (graphics, "set_graphics_grid_style", ("points",)),
            (graphics, "set_graphics_show_port_labels", (False,)),
            (graphics, "set_graphics_node_elapsed_time_unit", ("milliseconds",)),
            (graphics, "set_graphics_node_elapsed_time_visibility", ("during_run",)),
            (graphics, "set_graphics_node_comment_editor_default", ("inspector",)),
            (graphics, "set_graphics_node_shadow", (False,)),
            (graphics, "set_graphics_floating_toolbar_style", ("segmented_bar",)),
            (graphics, "set_graphics_floating_toolbar_size", ("large",)),
            (graphics, "set_graphics_selection_toolbar_mode", ("side_rail",)),
            (graphics, "set_graphics_selection_toolbar_minimal_menu_trigger", ("right_click",)),
            (graphics, "set_folder_explorer_column_widths", ({"name": 240},)),
            (graphics, "record_recent_text_color", ("#112233",)),
            (graphics, "set_graphics_shell_theme", ("stitch_light",)),
            (graphics, "set_graphics_graph_follow_shell_theme", (False,)),
            (graphics, "set_graphics_graph_theme", ("graph_stitch_light",)),
            (graphics, "request_open_graphics_settings", ()),
        )

        for _owner, method_name, args in cases:
            getattr(bridge, method_name)(*args)

        self.assertEqual(
            [name for name, _args in canvas.calls],
            [name for owner, name, _args in cases if owner is canvas],
        )
        self.assertEqual(
            [name for name, _args in graphics.calls],
            [name for owner, name, _args in cases if owner is graphics],
        )

    def test_command_bridge_exposes_tabular_preview_slot_for_qml_inline_surfaces(self) -> None:
        host_source = _GraphCanvasShellHostStub()
        bridge = GraphCanvasCommandBridge(host_source=host_source)

        meta_object = bridge.metaObject()
        self.assertGreaterEqual(
            meta_object.indexOfMethod(b"describe_tabular_preview(QVariantMap,QVariantMap)"),
            0,
        )

        payload = bridge.describe_tabular_preview(
            {"path": "C:/temp/stations.csv"},
            {"row_limit": 50, "column_limit": 50},
        )

        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["preview_kind"], "table")
        self.assertEqual(payload["source"]["path"], "C:/temp/stations.csv")
        self.assertEqual(
            host_source.calls,
            [
                (
                    "describe_tabular_preview",
                    (
                        {"path": "C:/temp/stations.csv"},
                        {"row_limit": 50, "column_limit": 50},
                    ),
                )
            ],
        )

    def test_canvas_command_bridge_forwards_batch_rewire_and_preserves_boolean_failure(self) -> None:
        source = _CanvasRewireSource()
        bridge = GraphCanvasCommandBridge(workspace_edit_controller=source)

        self.assertTrue(
            bridge.request_rewire_edges(
                ["edge-a", "edge-b"],
                "target",
                "sink-node",
                "payload",
                True,
                False,
            )
        )
        source.result = False
        self.assertFalse(
            bridge.request_rewire_edges(["edge-a"], "target", "", "", False, False)
        )
        self.assertEqual(
            source.calls,
            [
                (
                    "request_rewire_edges",
                    (
                        ["edge-a", "edge-b"],
                        "target",
                        "sink-node",
                        "payload",
                        True,
                        False,
                    ),
                ),
                (
                    "request_rewire_edges",
                    (["edge-a"], "target", "", "", False, False),
                ),
            ],
        )

    def test_state_bridge_forwards_compatible_rewire_snapshot_and_rejects_non_map(self) -> None:
        scene = _GraphCanvasSceneBridgeStub()
        policy = _RewireEndpointPolicy()
        scene.policy_bridge = policy
        bridge = GraphCanvasStateBridge(scene_bridge=scene)

        self.assertEqual(
            bridge.compatible_rewire_endpoint_snapshot(
                ["edge-a", "edge-b"], "target", True, False
            ),
            policy.result,
        )
        policy.result = ["not", "a", "map"]
        self.assertEqual(
            bridge.compatible_rewire_endpoint_snapshot(["edge-a"], "source", False, True),
            {},
        )
        self.assertEqual(
            policy.calls,
            [
                (
                    "compatible_rewire_endpoint_snapshot",
                    (["edge-a", "edge-b"], "target", True, False),
                ),
                (
                    "compatible_rewire_endpoint_snapshot",
                    (["edge-a"], "source", False, True),
                ),
            ],
        )

    def test_split_canvas_bridges_use_explicit_sources_without_legacy_wrapper(self) -> None:
        host = _GraphCanvasShellHostStub()
        graphics = _GraphCanvasShellHostStub()
        for name, value in vars(graphics).items():
            if not name.startswith("graphics_") or name == "graphics_minimap_expanded":
                continue
            if isinstance(value, bool):
                setattr(host, name, not value)
            elif isinstance(value, int):
                setattr(host, name, value + 7)
            elif isinstance(value, str):
                setattr(host, name, "canvas-owned-sentinel")
            elif isinstance(value, list):
                setattr(host, name, ["#010203"])
            elif isinstance(value, dict):
                setattr(host, name, {"canvas-owned-sentinel": True})
            elif value is None:
                setattr(host, name, 12)
        graphics.selected_run_preview_before_run = False
        graphics.graphics_minimap_expanded = False
        graphics.snap_to_grid_enabled = False
        graphics.snap_grid_size = 99.0
        graphics.graphics_plot_default_backend_per_type = dict(
            DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"]
        )
        host.active_theme_id = "canvas-owned-sentinel"
        host_source = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        scene._return_values["open_subnode_scope"] = True
        view = _GraphCanvasViewBridgeStub()
        state_bridge = GraphCanvasStateBridge(
            host,
            session_state=host,
            snap_to_grid_changed_signal=host.snap_to_grid_changed,
            snap_grid_size=host.snap_grid_size,
            app_preferences_source=host,
            graphics_source=graphics,
            scene_bridge=scene,
            view_bridge=view,
        )
        command_bridge = GraphCanvasCommandBridge(
            host,
            search_scope_controller=SimpleNamespace(navigate_scope=lambda callback: callback()),
            app_preferences_source=host,
            graphics_preferences_changed_signal=host.graphics_preferences_changed,
            run_controller=host,
            show_graph_hint=lambda message, timeout: host._record(
                "show_graph_hint", message, timeout
            ),
            inspector_source=host,
            library_source=host,
            workspace_edit_controller=host,
            workspace_drop_connect_controller=host,
            media_action_source=host,
            graphics_source=graphics,
            host_source=host_source,
            scene_bridge=scene,
            view_bridge=view,
        )

        self.assertIs(state_bridge.scene_bridge, scene)
        self.assertIs(state_bridge.view_bridge, view)
        self.assertIs(command_bridge._run_controller, host)
        self.assertIs(command_bridge.media_action_source, host)
        self.assertIs(command_bridge.graphics_source, graphics)
        self.assertIs(command_bridge.host_source, host_source)
        self.assertIs(command_bridge.scene_bridge, scene)
        self.assertIs(command_bridge.view_bridge, view)
        graphics_expectations = {
            "graphics_show_grid": True,
            "graphics_canvas_background_variant": "theme",
            "graphics_grid_style": "lines",
            "graphics_edge_crossing_style": "none",
            "graphics_graph_label_pixel_size": 10,
            "graphics_graph_node_icon_pixel_size_override": None,
            "graphics_node_title_icon_pixel_size": 10,
            "graphics_recent_text_colors": [],
            "graphics_media_panel_defaults": {
                "show_title": True,
                "show_frame": True,
                "autoplay_animations": True,
                "source_input_exposed": True,
            },
            "graphics_media_panel_default_show_title": True,
            "graphics_media_panel_default_show_frame": True,
            "graphics_media_panel_autoplay_animations": True,
            "graphics_media_panel_source_input_exposed": True,
            "graphics_folder_explorer_column_widths": {},
            "graphics_show_minimap": True,
            "graphics_show_canvas_options_button": True,
            "graphics_show_port_labels": True,
            "graphics_notched_ports": True,
            "graphics_node_elapsed_time_unit": "seconds",
            "graphics_node_elapsed_time_visibility": "always",
            "graphics_node_comment_editor_default": "canvas_popover",
            "graphics_show_tooltips": True,
            "graphics_tooltip_categories": default_tooltip_category_preferences(),
            "graphics_tooltip_category_visibility": {
                **default_tooltip_category_preferences(),
                "critical": True,
            },
            "graphics_node_shadow": True,
            "graphics_shadow_strength": 70,
            "graphics_shadow_softness": 50,
            "graphics_shadow_offset": 4,
            "graphics_status_bar_layout": "option_1",
            "graphics_show_fps_telemetry": True,
            "graphics_floating_toolbar_style": "compact_pill",
            "graphics_floating_toolbar_size": "small",
            "graphics_node_floating_toolbar_opens_on_hover": False,
            "graphics_selection_toolbar_mode": "minimal_ghost_menu",
            "graphics_selection_toolbar_minimal_menu_trigger": "click_affordance",
            "graphics_expand_collision_avoidance": {"enabled": True},
            "graphics_lightweight_canvas": False,
            "graphics_plot_default_backend_per_type": dict(
                DEFAULT_GRAPHICS_SETTINGS["plot"]["plot_default_backend_per_type"]
            ),
            "active_theme_id": "stitch_dark",
            "graphics_graph_follow_shell_theme": False,
            "graphics_selected_graph_theme_id": "graph_stitch_dark",
        }
        canvas_expectations = {
            "graphics_minimap_expanded": True,
            "selected_run_preview_before_run": True,
            "snap_to_grid_enabled": True,
            "snap_grid_size": 24.0,
        }
        self.assertEqual(len(graphics_expectations), 41)
        self.assertEqual(len(canvas_expectations), 4)
        for name, expected in (*graphics_expectations.items(), *canvas_expectations.items()):
            with self.subTest(property_name=name):
                self.assertEqual(getattr(state_bridge, name), expected)

        notifications = {"graphics": 0, "snap": 0}
        state_bridge.graphics_preferences_changed.connect(
            lambda: notifications.__setitem__(
                "graphics", notifications["graphics"] + 1
            )
        )
        state_bridge.snap_to_grid_changed.connect(
            lambda: notifications.__setitem__("snap", notifications["snap"] + 1)
        )
        graphics.graphics_preferences_changed.emit()
        self.assertEqual(notifications, {"graphics": 1, "snap": 0})
        host.snap_to_grid_changed.emit()
        self.assertEqual(notifications, {"graphics": 1, "snap": 1})
        host.graphics_preferences_changed.emit()
        graphics.snap_to_grid_changed.emit()
        self.assertEqual(notifications, {"graphics": 1, "snap": 1})
        self.assertEqual(state_bridge.center_x, 18.5)
        self.assertEqual(state_bridge.center_y, -42.0)
        self.assertEqual(state_bridge.zoom_value, 1.75)
        self.assertEqual(state_bridge.nodes_model, scene.nodes_model)
        self.assertEqual(state_bridge.edges_model, scene.edges_model)
        self.assertEqual(state_bridge.selected_node_ids, scene.selected_node_ids)
        self.assertEqual(state_bridge.selected_node_lookup, scene.selected_node_lookup)

        graphics.graphics_notched_ports = False
        self.assertFalse(state_bridge.graphics_notched_ports)

        command_bridge.set_graphics_minimap_expanded(False)
        command_bridge.set_graphics_canvas_background_variant("white")
        command_bridge.set_graphics_show_port_labels(False)
        command_bridge.set_graphics_node_elapsed_time_unit("milliseconds")
        command_bridge.set_graphics_node_elapsed_time_visibility("during_run")
        command_bridge.set_graphics_node_comment_editor_default("inspector")
        self.assertFalse(state_bridge.graphics_show_port_labels)
        self.assertEqual(state_bridge.graphics_node_elapsed_time_unit, "milliseconds")
        self.assertEqual(state_bridge.graphics_node_elapsed_time_visibility, "during_run")
        self.assertEqual(state_bridge.graphics_node_comment_editor_default, "inspector")
        graphics.graphics_node_floating_toolbar_opens_on_hover = True
        self.assertTrue(state_bridge.graphics_node_floating_toolbar_opens_on_hover)
        self.assertEqual(state_bridge.graphics_canvas_background_variant, "white")
        command_bridge.set_folder_explorer_column_widths({"name": 240})
        self.assertEqual(state_bridge.graphics_folder_explorer_column_widths, {"name": 240})
        command_bridge.set_graphics_selection_toolbar_mode("side_rail")
        command_bridge.set_graphics_selection_toolbar_minimal_menu_trigger("right_click")
        self.assertEqual(state_bridge.graphics_selection_toolbar_mode, "side_rail")
        self.assertEqual(
            state_bridge.graphics_selection_toolbar_minimal_menu_trigger,
            "right_click",
        )
        command_bridge.adjust_zoom(1.15)
        command_bridge.pan_by(-12.0, 8.0)
        command_bridge.set_viewport_size(1280.0, 720.0)
        self.assertTrue(command_bridge.request_open_subnode_scope("subnode-1"))
        self.assertEqual(
            command_bridge.browse_node_property_path("node-1", "source_path", "C:/temp/current.txt"),
            "C:/temp/from-canvas-bridge.txt",
        )
        self.assertEqual(
            command_bridge.internalize_node_property_path("node-1", "source_path", "C:/temp/current.txt"),
            "temp://from-canvas-internalized",
        )
        self.assertEqual(
            command_bridge.pick_node_property_color("node-1", "accent_color", "#336699"),
            "#AA5500",
        )
        self.assertTrue(
            command_bridge.request_drop_node_from_library(
                "core.logger",
                120.0,
                240.0,
                "port",
                "node-1",
                "payload",
                "edge-1",
            )
        )
        self.assertEqual(command_bridge.video_frame_capture_path("video-1", 4567), "C:/temp/corex-video-frame.png")
        self.assertEqual(
            command_bridge.request_save_image_crop_replace(
                "image-1",
                {"x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8},
            )["source_ref"],
            "project-staged://image_crop_1",
        )
        self.assertEqual(
            command_bridge.request_create_video_frame_image_node(
                "video-1",
                "C:/temp/captured-frame.png",
                4567,
                320.0,
                180.0,
                512.0,
                384.0,
            )["created_node_id"],
            "image-node-1",
        )
        self.assertEqual(
            command_bridge.request_create_video_timestamp_annotation(
                "video-1",
                4567,
                340.0,
                220.0,
            )["link_id"],
            "link-video-1",
        )
        self.assertEqual(
            command_bridge.request_trim_video_clip_replace(
                "video-1",
                1000,
                4000,
                {"clip_enabled": True, "clip_start_ms": 1000, "clip_end_ms": 4000},
            )["request_id"],
            "trim-replace-1",
        )
        self.assertEqual(
            command_bridge.request_trim_video_clip_copy(
                "video-1",
                1000,
                4000,
                360.0,
                240.0,
                {"clip_enabled": True, "clip_start_ms": 1000, "clip_end_ms": 4000},
            )["created_node_id"],
            "video-copy-1",
        )
        self.assertTrue(command_bridge.request_connect_ports("node-1", "value", "node-2", "payload"))
        command_bridge.select_node("node-1", True)
        command_bridge.set_node_property("node-1", "message", "hello")
        self.assertEqual(
            command_bridge.upsert_node_link("node-1", "", "url", "Docs", "https://example.com/docs", ""),
            "link-1",
        )
        self.assertEqual(
            command_bridge.upsert_node_link(
                "node-1",
                "",
                "node",
                "PDF2",
                "node-target",
                "Target Workspace - Media - ID 2",
                "workspace-target",
                "node-target",
            ),
            "link-1",
        )
        self.assertTrue(command_bridge.remove_node_link("node-1", "link-1"))
        self.assertTrue(command_bridge.move_node_link("node-1", "link-1", 1))
        self.assertTrue(command_bridge.open_node_link("node-1", "link-1"))
        self.assertEqual(
            command_bridge.upsert_node_comment(
                "node-1",
                "",
                "Check this node.",
                "",
                "",
                False,
                True,
                False,
            ),
            "comment-1",
        )
        self.assertTrue(command_bridge.remove_node_comment("node-1", "comment-1"))
        self.assertTrue(command_bridge.set_node_comment_resolved("node-1", "comment-1", True))
        self.assertTrue(command_bridge.set_node_comment_pinned("node-1", "comment-1", True))
        self.assertTrue(command_bridge.resolve_all_node_comments("node-1"))
        self.assertTrue(command_bridge.mark_node_comments_read("node-1"))
        self.assertTrue(command_bridge.are_port_kinds_compatible("data", "data"))
        self.assertTrue(command_bridge.are_data_types_compatible("text", "text"))
        self.assertTrue(command_bridge.move_nodes_by_delta(["node-1", "node-2"], 10.0, -5.0))
        command_bridge.move_node("node-1", 160.0, 220.0)
        command_bridge.resize_node("node-1", 320.0, 180.0)
        command_bridge.set_node_geometry("node-1", 150.0, 210.0, 340.0, 190.0)

        self.assertEqual(
            host.calls,
            [
                ("browse_node_property_path", ("node-1", "source_path", "C:/temp/current.txt")),
                ("internalize_node_property_path", ("node-1", "source_path", "C:/temp/current.txt")),
                ("pick_node_property_color", ("node-1", "accent_color", "#336699")),
                (
                    "request_drop_node_from_library",
                    ("core.logger", 120.0, 240.0, "port", "node-1", "payload", "edge-1"),
                ),
                ("video_frame_capture_path", ("video-1", 4567)),
                (
                    "request_save_image_crop_replace",
                    ("image-1", {"x": 0.25, "y": 0.1, "width": 0.5, "height": 0.8}),
                ),
                (
                    "request_create_video_frame_image_node",
                    ("video-1", "C:/temp/captured-frame.png", 4567, 320.0, 180.0, 512.0, 384.0),
                ),
                (
                    "request_create_video_timestamp_annotation",
                    ("video-1", 4567, 340.0, 220.0),
                ),
                (
                    "request_trim_video_clip_replace",
                    ("video-1", 1000, 4000, {"clip_enabled": True, "clip_start_ms": 1000, "clip_end_ms": 4000}),
                ),
                (
                    "request_trim_video_clip_copy",
                    (
                        "video-1",
                        1000,
                        4000,
                        360.0,
                        240.0,
                        {"clip_enabled": True, "clip_start_ms": 1000, "clip_end_ms": 4000},
                    ),
                ),
                ("request_connect_ports", ("node-1", "value", "node-2", "payload", False)),
            ],
        )
        self.assertEqual(
            graphics.calls,
            [
                ("set_graphics_canvas_background_variant", ("white",)),
                ("set_graphics_show_port_labels", (False,)),
                ("set_graphics_node_elapsed_time_unit", ("milliseconds",)),
                ("set_graphics_node_elapsed_time_visibility", ("during_run",)),
                ("set_graphics_node_comment_editor_default", ("inspector",)),
                ("set_folder_explorer_column_widths", ({"name": 240},)),
                ("set_graphics_selection_toolbar_mode", ("side_rail",)),
                ("set_graphics_selection_toolbar_minimal_menu_trigger", ("right_click",)),
            ],
        )
        self.assertEqual(host_source.calls, [])
        self.assertEqual(
            scene.calls,
            [
                ("open_subnode_scope", ("subnode-1",)),
                ("select_node", ("node-1", True)),
                ("set_node_property", ("node-1", "message", "hello")),
                (
                    "upsert_node_link",
                    ("node-1", "", "url", "Docs", "https://example.com/docs", ""),
                ),
                (
                    "upsert_node_link",
                    (
                        "node-1",
                        "",
                        "node",
                        "PDF2",
                        "node-target",
                        "Target Workspace - Media - ID 2",
                        "workspace-target",
                        "node-target",
                    ),
                ),
                ("remove_node_link", ("node-1", "link-1")),
                ("move_node_link", ("node-1", "link-1", 1)),
                ("open_node_link", ("node-1", "link-1")),
                ("upsert_node_comment", ("node-1", "", "Check this node.", "", "", False, True, False)),
                ("remove_node_comment", ("node-1", "comment-1")),
                ("set_node_comment_resolved", ("node-1", "comment-1", True)),
                ("set_node_comment_pinned", ("node-1", "comment-1", True)),
                ("resolve_all_node_comments", ("node-1",)),
                ("mark_node_comments_read", ("node-1",)),
                ("are_port_kinds_compatible", ("data", "data")),
                ("are_data_types_compatible", ("text", "text")),
                ("move_nodes_by_delta", (["node-1", "node-2"], 10.0, -5.0)),
                ("move_node", ("node-1", 160.0, 220.0)),
                ("resize_node", ("node-1", 320.0, 180.0)),
                ("set_node_geometry", ("node-1", 150.0, 210.0, 340.0, 190.0)),
            ],
        )

    def test_split_canvas_bridges_expose_canvas_contract_extensions(self) -> None:
        host = _GraphCanvasShellHostStub()
        host_source = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        view = _GraphCanvasViewBridgeStub()
        state_bridge = GraphCanvasStateBridge(
            session_state=host,
            snap_to_grid_changed_signal=host.snap_to_grid_changed,
            snap_grid_size=host.snap_grid_size,
            app_preferences_source=host,
            scene_bridge=scene,
            view_bridge=view,
        )
        command_bridge = GraphCanvasCommandBridge(
            library_source=host,
            host_source=host_source,
            scene_bridge=scene,
            view_bridge=view,
        )

        self.assertEqual(state_bridge.visible_scene_rect_payload, view.visible_scene_rect_payload)
        self.assertEqual(state_bridge.minimap_nodes_model, scene.minimap_nodes_model)
        self.assertEqual(
            state_bridge.workspace_scene_bounds_payload,
            {"x": -1600.0, "y": -900.0, "width": 3200.0, "height": 1800.0},
        )

        command_bridge.center_on_scene_point(96.0, 144.0)
        command_bridge.request_open_canvas_quick_insert(15.0, 25.0, 115.0, 215.0)
        self.assertTrue(command_bridge.request_delete_selected_graph_items(["edge-1"]))
        self.assertTrue(command_bridge.request_navigate_scope_parent())
        self.assertTrue(command_bridge.request_navigate_scope_root())
        command_bridge.clear_selection()
        command_bridge.select_nodes_in_rect(1.0, 2.0, 3.0, 4.0, True)
        command_bridge.set_pending_surface_action("node-1")
        self.assertTrue(command_bridge.consume_pending_surface_action("node-1"))
        self.assertTrue(command_bridge.set_node_properties("node-1", {"message": "bridge"}))
        command_bridge.set_graph_cursor_shape(13)
        command_bridge.clear_graph_cursor_shape()
        self.assertEqual(
            command_bridge.describe_pdf_preview("C:/temp/preview.pdf", 2),
            {
                "source": "C:/temp/preview.pdf",
                "page_number": 2,
                "valid": True,
            },
        )
        self.assertEqual(
            command_bridge.describe_mail_preview("C:/temp/message.eml"),
            {
                "source": "C:/temp/message.eml",
                "state": "ready",
                "preview_url": "file:///C:/temp/mail-preview.html",
            },
        )
        self.assertEqual(
            command_bridge.open_local_file_source("C:/temp/message.eml", False),
            {"success": True, "path": "C:/temp/message.eml", "error": {}},
        )

        self.assertEqual(host.calls, [("request_open_canvas_quick_insert", (15.0, 25.0, 115.0, 215.0))])
        self.assertEqual(
            host_source.calls,
            [
                ("request_delete_selected_graph_items", (["edge-1"],)),
                ("request_navigate_scope_parent", ()),
                ("request_navigate_scope_root", ()),
                ("set_graph_cursor_shape", (13,)),
                ("clear_graph_cursor_shape", ()),
                ("describe_pdf_preview", ("C:/temp/preview.pdf", 2)),
                ("describe_mail_preview", ("C:/temp/message.eml",)),
                ("open_local_file_source", ("C:/temp/message.eml", False)),
            ],
        )
        self.assertEqual(
            scene.calls,
            [
                ("clear_selection", ()),
                ("select_nodes_in_rect", (1.0, 2.0, 3.0, 4.0, True)),
                ("set_pending_surface_action", ("node-1",)),
                ("consume_pending_surface_action", ("node-1",)),
                ("set_node_properties", ("node-1", {"message": "bridge"})),
            ],
        )
        self.assertEqual(view.calls, [("center_on_scene_point", (96.0, 144.0))])

    def test_canvas_tooltip_projections_reuse_graphics_source_cache(self) -> None:
        host = _GraphCanvasShellHostStub()
        canvas_source = _GraphCanvasTooltipCanvasSourceStub()
        state_bridge = GraphCanvasStateBridge(
            host,
            session_state=canvas_source,
            snap_to_grid_changed_signal=host.snap_to_grid_changed,
            snap_grid_size=getattr(canvas_source, "snap_grid_size", 20.0),
            app_preferences_source=canvas_source,
            graphics_source=host,
            scene_bridge=_GraphCanvasSceneBridgeStub(),
            view_bridge=_GraphCanvasViewBridgeStub(),
        )
        original_normalize = graphics_preferences_module.normalize_tooltip_category_preferences
        original_visibility = graphics_preferences_module._tooltip_category_visibility_payload

        with (
            mock.patch.object(
                graphics_preferences_module,
                "normalize_tooltip_category_preferences",
                wraps=original_normalize,
            ) as normalize_categories,
            mock.patch.object(
                graphics_preferences_module,
                "_tooltip_category_visibility_payload",
                wraps=original_visibility,
            ) as project_visibility,
        ):
            categories = state_bridge.graphics_tooltip_categories
            categories["general"] = False
            self.assertTrue(state_bridge.graphics_tooltip_categories["general"])
            _ = state_bridge.graphics_tooltip_category_visibility
            _ = state_bridge.graphics_tooltip_category_visibility
            self.assertTrue(state_bridge.tooltip_category_enabled("general"))
            self.assertEqual(normalize_categories.call_count, 0)
            self.assertEqual(project_visibility.call_count, 0)

            host.graphics_tooltip_categories["general"] = False
            host.graphics_tooltip_category_visibility["general"] = False
            host.graphics_preferences_changed.emit()

            self.assertFalse(state_bridge.tooltip_category_enabled("general"))
            self.assertEqual(normalize_categories.call_count, 0)
            self.assertEqual(project_visibility.call_count, 0)

    def test_graph_typography_state_bridge_baseline_without_legacy_wrapper(self) -> None:
        host = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        view = _GraphCanvasViewBridgeStub()
        state_bridge = GraphCanvasStateBridge(
            host,
            session_state=host,
            snap_to_grid_changed_signal=host.snap_to_grid_changed,
            snap_grid_size=host.snap_grid_size,
            app_preferences_source=host,
            graphics_source=host,
            scene_bridge=scene,
            view_bridge=view,
        )
        seen = {
            "graphics_preferences_changed": 0,
        }
        state_bridge.graphics_preferences_changed.connect(
            lambda: seen.__setitem__(
                "graphics_preferences_changed",
                seen["graphics_preferences_changed"] + 1,
            )
        )

        self.assertEqual(state_bridge.graphics_graph_label_pixel_size, 10)

        host.graphics_graph_label_pixel_size = 15
        host.graphics_preferences_changed.emit()

        self.assertEqual(state_bridge.graphics_graph_label_pixel_size, 15)
        self.assertEqual(seen, {"graphics_preferences_changed": 1})

    def test_graph_node_icon_size_state_bridge_baseline_without_legacy_wrapper(self) -> None:
        host = _GraphCanvasShellHostStub()
        host.graphics_graph_label_pixel_size = 16
        host.graphics_graph_node_icon_pixel_size_override = None
        host.graphics_node_title_icon_pixel_size = 16
        presenter = _GraphCanvasShellHostStub()
        presenter.graphics_graph_label_pixel_size = 16
        scene = _GraphCanvasSceneBridgeStub()
        view = _GraphCanvasViewBridgeStub()
        state_bridge = GraphCanvasStateBridge(
            host,
            session_state=presenter,
            snap_to_grid_changed_signal=presenter.snap_to_grid_changed,
            snap_grid_size=presenter.snap_grid_size,
            app_preferences_source=presenter,
            graphics_source=host,
            scene_bridge=scene,
            view_bridge=view,
        )

        self.assertIsNone(state_bridge.graphics_graph_node_icon_pixel_size_override)
        self.assertEqual(state_bridge.graphics_node_title_icon_pixel_size, 16)

        host.graphics_graph_node_icon_pixel_size_override = 13
        host.graphics_node_title_icon_pixel_size = 13
        host.graphics_preferences_changed.emit()

        self.assertEqual(state_bridge.graphics_graph_node_icon_pixel_size_override, 13)
        self.assertEqual(state_bridge.graphics_node_title_icon_pixel_size, 13)

    def test_graphics_state_node_execution_bridge_filters_lookup_to_scene_workspace_and_re_emits(self) -> None:
        host = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        bridge = GraphCanvasStateBridge(
            host,
            execution_source=host,
            scene_bridge=scene,
        )
        seen = {"node_execution_state_changed": 0}
        bridge.node_execution_state_changed.connect(
            lambda: seen.__setitem__(
                "node_execution_state_changed",
                seen["node_execution_state_changed"] + 1,
            )
        )

        host.run_state.node_execution_workspace_id = "ws-1"
        host.run_state.running_node_ids.add("node_running")
        host.run_state.completed_node_ids.add("node_completed")
        host.run_state.warning_node_ids.add("node_warning")
        host.run_state.node_solution_facts_by_workspace_id = {
            "ws-1": {
                "node_fresh": NodeSolutionFact(
                    project_id="project",
                    workspace_id="ws-1",
                    node_id="node_fresh",
                    freshness=SolutionFreshness.CURRENT,
                    revision=1,
                    retained_record_id="record_fresh",
                    retained_solution_key="a" * 64,
                    residency=SolutionResidency.SESSION,
                    last_disposition=SolutionDisposition.RECOMPUTED,
                )
            }
        }
        host.run_state.node_execution_revision = 8
        host.node_execution_state_changed.emit()

        self.assertEqual(bridge.running_node_lookup, {"node_running": True})
        self.assertEqual(bridge.completed_node_lookup, {"node_completed": True})
        self.assertEqual(bridge.warning_node_lookup, {"node_warning": True})
        self.assertEqual(bridge.fresh_run_node_lookup, {"node_fresh": True})
        self.assertEqual(
            bridge.node_solution_freshness_lookup, {"node_fresh": "current"}
        )
        self.assertEqual(bridge.node_execution_revision, 8)

        scene.workspace_id = "ws-2"
        scene.workspace_changed.emit("ws-2")

        self.assertEqual(bridge.running_node_lookup, {})
        self.assertEqual(bridge.completed_node_lookup, {})
        self.assertEqual(bridge.warning_node_lookup, {})
        self.assertEqual(bridge.fresh_run_node_lookup, {})
        self.assertEqual(bridge.node_execution_revision, 8)
        self.assertEqual(seen["node_execution_state_changed"], 2)

    def test_persistent_node_elapsed_canvas_bridge_filters_running_and_cached_timing_to_active_workspace(
        self,
    ) -> None:
        host = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        bridge = GraphCanvasStateBridge(
            host,
            execution_source=host,
            scene_bridge=scene,
        )
        seen = {"node_execution_state_changed": 0}
        bridge.node_execution_state_changed.connect(
            lambda: seen.__setitem__(
                "node_execution_state_changed",
                seen["node_execution_state_changed"] + 1,
            )
        )

        host.run_state.node_execution_workspace_id = "ws-1"
        host.run_state.running_node_started_at_epoch_ms_by_node_id = {
            "node_running": 1234.5,
        }
        host.run_state.cached_node_elapsed_ms_by_workspace_id = {
            "ws-1": {"node_cached": 48.25},
            "ws-2": {"node_foreign": 99.0},
        }
        host.run_state.node_solution_facts_by_workspace_id = {
            workspace_id: {
                node_id: NodeSolutionFact(
                    project_id="project",
                    workspace_id=workspace_id,
                    node_id=node_id,
                    freshness=SolutionFreshness.CURRENT,
                    revision=1,
                    retained_record_id=f"record_{node_id}",
                    retained_solution_key="a" * 64,
                    residency=SolutionResidency.SESSION,
                    last_disposition=SolutionDisposition.RECOMPUTED,
                )
            }
            for workspace_id, node_id in (
                ("ws-1", "node_cached"),
                ("ws-2", "node_foreign"),
            )
        }
        host.run_state.node_execution_revision = 15
        host.node_execution_state_changed.emit()

        self.assertEqual(
            bridge.running_node_started_at_ms_lookup,
            {"node_running": 1234.5},
        )
        self.assertEqual(
            bridge.node_elapsed_ms_lookup,
            {"node_cached": 48.25},
        )
        self.assertEqual(bridge.fresh_run_node_lookup, {"node_cached": True})
        self.assertEqual(bridge.node_execution_revision, 15)

        scene.workspace_id = "ws-2"
        scene.workspace_changed.emit("ws-2")

        self.assertEqual(bridge.running_node_started_at_ms_lookup, {})
        self.assertEqual(
            bridge.node_elapsed_ms_lookup,
            {"node_foreign": 99.0},
        )
        self.assertEqual(bridge.fresh_run_node_lookup, {"node_foreign": True})
        self.assertEqual(bridge.node_execution_revision, 15)
        self.assertEqual(seen["node_execution_state_changed"], 2)

    def test_selected_run_preview_canvas_bridge_filters_rows_and_highlights_to_active_workspace(self) -> None:
        host = _GraphCanvasShellHostStub()
        scene = _GraphCanvasSceneBridgeStub()
        bridge = GraphCanvasStateBridge(
            host,
            execution_source=host,
            scene_bridge=scene,
        )

        host.run_state.selected_run_preview_workspace_id = "ws-1"
        host.run_state.selected_run_preview_rows = [
            {
                "section": "Will run",
                "tone": "run",
                "node_id": "node-1",
                "title": "Logger",
            }
        ]
        host.run_state.selected_run_preview_node_lookup = {"node-1": "run"}
        host.run_state.selected_run_preview_revision = 4
        host.node_execution_state_changed.emit()

        self.assertTrue(bridge.selected_run_preview_before_run)
        self.assertTrue(bridge.selected_run_preview_visible)
        self.assertEqual(bridge.selected_run_preview_revision, 4)
        self.assertEqual(bridge.selected_run_preview_node_lookup, {"node-1": "run"})
        self.assertEqual(bridge.selected_run_preview_rows[0]["title"], "Logger")

        scene.workspace_id = "ws-2"
        scene.workspace_changed.emit("ws-2")

        self.assertFalse(bridge.selected_run_preview_visible)
        self.assertEqual(bridge.selected_run_preview_rows, [])
        self.assertEqual(bridge.selected_run_preview_node_lookup, {})

__all__ = ["GraphCanvasSplitBridgeTests"]
