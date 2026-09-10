from __future__ import annotations

import unittest
from types import SimpleNamespace

from ea_node_editor.ui.shell.controllers.mutation_ui_effects import MutationUiEffects


class _SignalProbe:
    def __init__(self) -> None:
        self.count = 0

    def emit(self) -> None:
        self.count += 1


class _SceneProbe:
    def __init__(self) -> None:
        self.refreshed_workspace_ids: list[str] = []

    def refresh_workspace_from_model(self, workspace_id: str) -> None:
        self.refreshed_workspace_ids.append(str(workspace_id))


class _ScriptEditorProbe:
    def __init__(self, current_node_id: str = "") -> None:
        self.current_node_id = current_node_id
        self.nodes: list[object] = []

    def set_node(self, node: object) -> None:
        self.nodes.append(node)


class _ViewerSessionBridgeProbe:
    def __init__(self) -> None:
        self.property_option_syncs: list[tuple[str, str, object, dict[str, object]]] = []

    def sync_node_property_option(
        self,
        node_id: str,
        key: str,
        value: object,
        payload: dict[str, object],
    ) -> None:
        self.property_option_syncs.append((node_id, key, value, dict(payload)))


class _MutationEffectsHostProbe:
    def __init__(self) -> None:
        self.selected_node_changed = _SignalProbe()
        self.scene = _SceneProbe()
        self.script_editor = _ScriptEditorProbe()
        self.invalidated_history_entries: list[tuple[object, ...]] = []
        self.graph_hints: list[tuple[str, int]] = []

    def invalidate_solution_for_history_action(
        self,
        workspace_id: str,
        action_type: str,
        *,
        before_snapshot: object,
        after_snapshot: object,
    ) -> None:
        self.invalidated_history_entries.append(
            (workspace_id, action_type, before_snapshot, after_snapshot)
        )

    def show_graph_hint(self, message: str, timeout_ms: int = 3600) -> None:
        self.graph_hints.append((message, timeout_ms))


class MutationUiEffectsTests(unittest.TestCase):
    def _effects(self, host: _MutationEffectsHostProbe) -> tuple[MutationUiEffects, list[str]]:
        refreshed_tabs: list[str] = []
        return MutationUiEffects(
            host=host,
            refresh_workspace_tabs=lambda: refreshed_tabs.append("refresh"),
        ), refreshed_tabs

    def test_property_change_can_refresh_scene_sync_script_editor_and_refresh_shell(self) -> None:
        host = _MutationEffectsHostProbe()
        host.script_editor.current_node_id = "node-script"
        effects, refreshed_tabs = self._effects(host)
        script_node = object()
        workspace = SimpleNamespace(workspace_id="workspace-1", nodes={"node-script": script_node})

        effects.after_selected_node_property_changed(
            "node-script",
            "script",
            workspace=workspace,
            refresh_scene_payload=True,
        )

        self.assertEqual(host.scene.refreshed_workspace_ids, ["workspace-1"])
        self.assertEqual(host.script_editor.nodes, [script_node])
        self.assertEqual(host.selected_node_changed.count, 1)
        self.assertEqual(refreshed_tabs, ["refresh"])
        self.assertEqual(host.invalidated_history_entries, [])

    def test_property_change_offers_viewer_session_option_sync(self) -> None:
        host = _MutationEffectsHostProbe()
        viewer_session_bridge = _ViewerSessionBridgeProbe()
        host.viewer_session_bridge = viewer_session_bridge
        effects, _refreshed_tabs = self._effects(host)
        workspace = SimpleNamespace(workspace_id="workspace-1", nodes={})

        effects.after_selected_node_property_changed(
            "node-viewer",
            "show_mesh_edges",
            True,
            workspace=workspace,
            refresh_scene_payload=False,
        )

        self.assertEqual(
            viewer_session_bridge.property_option_syncs,
            [
                (
                    "node-viewer",
                    "show_mesh_edges",
                    True,
                    {"workspace_id": "workspace-1"},
                )
            ],
        )

    def test_history_replay_refreshes_scene_invalidates_runtime_history_and_tabs_only(self) -> None:
        host = _MutationEffectsHostProbe()
        effects, refreshed_tabs = self._effects(host)
        entry = SimpleNamespace(action_type="edit-node-property", before="before", after="after")

        effects.after_history_replayed("workspace-1", entry)

        self.assertEqual(host.scene.refreshed_workspace_ids, ["workspace-1"])
        self.assertEqual(
            host.invalidated_history_entries,
            [("workspace-1", "edit-node-property", "before", "after")],
        )
        self.assertEqual(refreshed_tabs, ["refresh"])
        self.assertEqual(host.selected_node_changed.count, 0)

    def test_connection_effects_refresh_tabs_without_selected_node_notification(self) -> None:
        host = _MutationEffectsHostProbe()
        effects, refreshed_tabs = self._effects(host)

        effects.after_connected_ports_request()
        effects.after_edge_removed()

        self.assertEqual(refreshed_tabs, ["refresh", "refresh"])
        self.assertEqual(host.selected_node_changed.count, 0)
        self.assertEqual(host.scene.refreshed_workspace_ids, [])

    def test_layout_action_can_publish_graph_hint_then_refresh_selected_node_and_tabs(self) -> None:
        host = _MutationEffectsHostProbe()
        effects, refreshed_tabs = self._effects(host)

        effects.after_layout_action(created_overlap_pairs=2, normalized_action="left")

        self.assertEqual(
            host.graph_hints,
            [("2 overlaps created. Press Distribute Vertically to tidy.", 3600)],
        )
        self.assertEqual(host.selected_node_changed.count, 1)
        self.assertEqual(refreshed_tabs, ["refresh"])


__all__ = ["MutationUiEffectsTests"]
