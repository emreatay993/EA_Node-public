# Purpose: Node-scoped QML bridge for live viewer controls, saved camera views,
#          engineering selections, queries, and neutral exports.
# Map: feature_routes/viewer_session_overlay_fullscreen
# Tests: tests/test_viewer_control_bridge.py
from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ea_node_editor.app_preferences import normalize_engineering_viewer_settings
from ea_node_editor.common.scene_protocol import (
    ENGINEERING_SELECTION_SCHEMA,
    empty_engineering_selection_set,
    normalize_engineering_selection_set,
    normalize_scene_styles,
    normalize_viewer_background,
    normalize_viewer_colormap,
    normalize_viewer_deform_scale,
    normalize_viewer_representation,
    normalize_viewer_result_component,
    normalize_viewer_scalar_range_bound,
    normalize_viewer_scalar_range_mode,
)

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
    from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge


_ENGINEERING_SAVED_SELECTIONS_PROPERTY = "saved_selections"
_ENGINEERING_SELECTION_FILTERS = {
    "cad_vertex",
    "cad_edge",
    "cad_face",
    "cad_body",
    "fe_node",
    "fe_element_face",
    "fe_element",
}


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _finite_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _normalized_clip_axis(value: Any) -> str:
    normalized = str(value or "x").strip().casefold()
    return normalized if normalized in {"x", "y", "z"} else "x"


def _normalized_representation(value: Any) -> str:
    normalized = str(value or "surface").strip().casefold()
    if normalized == "wireframe_visible_edges":
        return normalized
    return normalize_viewer_representation(normalized)


def _normalized_selection_filter(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in _ENGINEERING_SELECTION_FILTERS else ""


def _normalized_camera_bookmarks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    bookmarks: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            continue
        camera_state = entry.get("camera_state")
        if not isinstance(camera_state, Mapping) or not camera_state:
            continue
        bookmarks.append(
            {
                "name": str(entry.get("name", "") or "").strip() or f"View {len(bookmarks) + 1}",
                "camera_state": copy.deepcopy(dict(camera_state)),
                "created_at": str(entry.get("created_at", "") or ""),
            }
        )
    return bookmarks


def _next_bookmark_name(bookmarks: Sequence[Mapping[str, Any]]) -> str:
    names = {str(bookmark.get("name", "")).strip().casefold() for bookmark in bookmarks}
    number = 1
    while f"view {number}" in names:
        number += 1
    return f"View {number}"


_VIEWER_OPTION_COERCERS: dict[str, Any] = {
    "show_mesh_edges": lambda value: _bool_value(value, False),
    "colormap": normalize_viewer_colormap,
    "result_component": normalize_viewer_result_component,
    "scalar_range_mode": normalize_viewer_scalar_range_mode,
    "scalar_range_min": normalize_viewer_scalar_range_bound,
    "scalar_range_max": normalize_viewer_scalar_range_bound,
    "show_scalar_bar": lambda value: _bool_value(value, True),
    "deform_scale": normalize_viewer_deform_scale,
    "hover_probe": lambda value: _bool_value(value, False),
    "show_minmax_markers": lambda value: _bool_value(value, False),
    "viewer_background": normalize_viewer_background,
    "representation": _normalized_representation,
    "scene_styles": normalize_scene_styles,
    "parallel_projection": lambda value: _bool_value(value, False),
    "clip_enabled": lambda value: _bool_value(value, False),
    "clip_axis": _normalized_clip_axis,
    "clip_offset": lambda value: _finite_float(value, 0.0),
    "show_attribute_colors": lambda value: _bool_value(value, False),
    "show_orientation_triad": lambda value: _bool_value(value, True),
    "show_view_cube": lambda value: _bool_value(value, True),
    "show_world_axes": lambda value: _bool_value(value, False),
    "selection_filter": _normalized_selection_filter,
}


class ViewerControlBridge(QObject):
    viewer_control_changed = pyqtSignal(str, name="viewerControlChanged")
    viewer_tangent_selection_angle_changed = pyqtSignal(
        float,
        name="viewerTangentSelectionAngleChanged",
    )
    viewer_query_completed = pyqtSignal(str, "QVariantMap", name="viewerQueryCompleted")

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        active_workspace_id_provider: Callable[[], str],
        workspace_provider: Callable[[str], Any],
        model_provider: Callable[[], Any],
        registry_provider: Callable[[], Any],
        app_preferences_controller: Any,
        save_file_dialog: Callable[..., str],
        viewer_host_service: Any,
        scene_bridge: "GraphSceneBridge | None" = None,
        viewer_session_bridge: "ViewerSessionBridge | None" = None,
    ) -> None:
        super().__init__(parent)
        self._active_workspace_id_provider: Callable[[], str] | None = (
            active_workspace_id_provider
        )
        self._workspace_provider: Callable[[str], Any] | None = workspace_provider
        self._model_provider: Callable[[], Any] | None = model_provider
        self._registry_provider: Callable[[], Any] | None = registry_provider
        self._app_preferences_controller = app_preferences_controller
        self._save_file_dialog: Callable[..., str] | None = save_file_dialog
        self._viewer_host_service = viewer_host_service
        self._scene_bridge = scene_bridge
        self._viewer_session_bridge = viewer_session_bridge
        self._bookmark_indices: dict[tuple[str, str], int] = {}
        self._bookmark_session_ids: dict[tuple[str, str], str] = {}
        if viewer_session_bridge is not None:
            viewer_session_bridge.viewer_query_completed.connect(self._on_viewer_query_completed)
            sessions_changed = getattr(viewer_session_bridge, "sessions_changed", None)
            if sessions_changed is not None and hasattr(sessions_changed, "connect"):
                sessions_changed.connect(self._sync_transient_sessions)
        if scene_bridge is not None:
            scene_bridge.workspace_changed.connect(self._clear_transient_state)
            scene_bridge.nodes_changed.connect(self._prune_transient_state)

    def shutdown(self) -> None:
        self._bookmark_indices.clear()
        self._bookmark_session_ids.clear()
        self._active_workspace_id_provider = None
        self._workspace_provider = None
        self._model_provider = None
        self._registry_provider = None
        self._app_preferences_controller = None
        self._save_file_dialog = None
        self._viewer_host_service = None
        self._scene_bridge = None
        self._viewer_session_bridge = None

    @pyqtSlot()
    @pyqtSlot(str)
    def _clear_transient_state(self, _value: str = "") -> None:
        self._bookmark_indices.clear()
        self._bookmark_session_ids.clear()

    @pyqtSlot()
    def _prune_transient_state(self) -> None:
        active = self._active_workspace()
        if active is None:
            return
        workspace_id, workspace = active
        nodes = getattr(workspace, "nodes", {})
        valid_keys = {(workspace_id, str(node_id)) for node_id in nodes}
        for key in set(self._bookmark_indices) | set(self._bookmark_session_ids):
            if key not in valid_keys:
                self._bookmark_indices.pop(key, None)
                self._bookmark_session_ids.pop(key, None)

    @pyqtSlot()
    def _sync_transient_sessions(self) -> None:
        self._prune_transient_state()
        for key, previous_session_id in list(self._bookmark_session_ids.items()):
            session_id = str(self._session_state(key[1]).get("session_id", "") or "")
            if previous_session_id != session_id:
                self._bookmark_indices.pop(key, None)
                self._bookmark_session_ids[key] = session_id

    def _on_viewer_query_completed(self, node_id: str, result: dict[str, Any]) -> None:
        self.viewer_query_completed.emit(str(node_id or ""), dict(result or {}))

    def _active_workspace(self) -> tuple[str, Any] | None:
        scene_bridge = self._scene_bridge
        scene_workspace_id = str(
            getattr(scene_bridge, "workspace_id", "") or ""
        ).strip()
        active_workspace_id_provider = self._active_workspace_id_provider
        manager_workspace_id = ""
        if active_workspace_id_provider is not None:
            try:
                manager_workspace_id = str(
                    active_workspace_id_provider() or ""
                ).strip()
            except Exception:  # noqa: BLE001
                return None
        if (
            scene_workspace_id
            and manager_workspace_id
            and scene_workspace_id != manager_workspace_id
        ):
            return None
        workspace_id = scene_workspace_id or manager_workspace_id
        model_provider = self._model_provider
        workspace_provider = self._workspace_provider
        if not workspace_id or model_provider is None or workspace_provider is None:
            return None
        try:
            model = model_provider()
            workspace = workspace_provider(workspace_id)
        except Exception:  # noqa: BLE001
            return None
        project = getattr(model, "project", None)
        workspaces = (
            getattr(project, "workspaces", {}) if project is not None else {}
        )
        if (
            not isinstance(workspaces, Mapping)
            or workspaces.get(workspace_id) is not workspace
        ):
            return None
        return (workspace_id, workspace) if workspace is not None else None

    def _node_properties(self, node_id: str) -> tuple[str, Any, dict[str, Any]] | None:
        active = self._active_workspace()
        if active is None:
            return None
        workspace_id, workspace = active
        node = workspace.nodes.get(str(node_id or "").strip())
        if node is None:
            return None
        registry_provider = self._registry_provider
        try:
            registry = registry_provider() if registry_provider is not None else None
        except Exception:  # noqa: BLE001
            registry = None
        spec_or_none = (
            getattr(registry, "spec_or_none", None)
            if registry is not None
            else None
        )
        if callable(spec_or_none):
            spec = spec_or_none(str(getattr(node, "type_id", "") or ""))
            if spec is None or str(getattr(spec, "surface_family", "") or "") != "viewer":
                return None
        return workspace_id, node, copy.deepcopy(dict(node.properties))

    def _set_node_property(self, node_id: str, key: str, value: Any) -> bool:
        scene_bridge = self._scene_bridge
        setter = getattr(scene_bridge, "set_node_property", None) if scene_bridge is not None else None
        if not callable(setter):
            command_bridge = getattr(scene_bridge, "command_bridge", None) if scene_bridge is not None else None
            setter = getattr(command_bridge, "set_node_property", None) if command_bridge is not None else None
        if not callable(setter):
            return False
        try:
            setter(str(node_id or ""), str(key or ""), copy.deepcopy(value))
        except Exception:  # noqa: BLE001
            return False
        return True

    def _sync_viewer_session_option(self, node_id: str, key: str, value: Any) -> None:
        bridge = self._viewer_session_bridge
        sync = getattr(bridge, "sync_node_property_option", None) if bridge is not None else None
        active = self._active_workspace()
        if not callable(sync) or active is None:
            return
        try:
            sync(str(node_id or ""), key, value, {"workspace_id": active[0]})
        except Exception:  # noqa: BLE001
            pass

    def _session_state(self, node_id: str) -> dict[str, Any]:
        bridge = self._viewer_session_bridge
        getter = getattr(bridge, "session_state", None) if bridge is not None else None
        if not callable(getter):
            return {}
        try:
            state = getter(str(node_id or ""))
        except Exception:  # noqa: BLE001
            return {}
        return copy.deepcopy(state) if isinstance(state, dict) else {}

    def _bookmark_key(self, node_id: str) -> tuple[str, str] | None:
        active = self._active_workspace()
        normalized_node_id = str(node_id or "").strip()
        if active is None or not normalized_node_id:
            return None
        key = active[0], normalized_node_id
        session_id = str(self._session_state(normalized_node_id).get("session_id", "") or "")
        previous_session_id = self._bookmark_session_ids.get(key)
        if previous_session_id is not None and previous_session_id != session_id:
            self._bookmark_indices.pop(key, None)
        self._bookmark_session_ids[key] = session_id
        return key

    @pyqtSlot(str, str, "QVariant", result=bool)
    def set_viewer_option(self, node_id: str, key: str, value: Any) -> bool:
        normalized_node_id = str(node_id or "").strip()
        option_key = str(key or "").strip()
        coercer = _VIEWER_OPTION_COERCERS.get(option_key)
        if not normalized_node_id or coercer is None:
            return False
        try:
            normalized_value = coercer(value)
        except (TypeError, ValueError):
            return False
        if option_key == "selection_filter":
            setter = getattr(
                self._viewer_host_service,
                "set_viewer_selection_filter",
                None,
            )
            if not normalized_value or not callable(setter):
                return False
            try:
                changed = bool(setter(normalized_node_id, normalized_value))
            except Exception:  # noqa: BLE001
                return False
            if changed:
                self.viewer_control_changed.emit(normalized_node_id)
            return changed
        if self._node_properties(normalized_node_id) is None:
            return False
        if not self._set_node_property(normalized_node_id, option_key, normalized_value):
            return False
        self._sync_viewer_session_option(normalized_node_id, option_key, normalized_value)
        self.viewer_control_changed.emit(normalized_node_id)
        return True

    @pyqtSlot(str, str, str, "QVariant", result=bool)
    def set_scene_style(self, node_id: str, scene_id: str, key: str, value: Any) -> bool:
        resolved = self._node_properties(node_id)
        if resolved is None or key not in {"opacity", "color"}:
            return False
        properties = resolved[2]
        if scene_id not in properties.get("scene_input_ids", ["scene_1"]):
            return False
        try:
            styles = normalize_scene_styles(properties.get("scene_styles", {}))
            styles.setdefault(scene_id, {})[key] = value
            return self.set_viewer_option(node_id, "scene_styles", styles)
        except (TypeError, ValueError):
            return False

    @pyqtSlot(result=float)
    def viewer_tangent_selection_angle_degrees(self) -> float:
        controller = self._app_preferences_controller
        getter = getattr(controller, "graphics_settings", None)
        if not callable(getter):
            return 5.0
        try:
            graphics = getter()
        except Exception:  # noqa: BLE001
            return 5.0
        settings = normalize_engineering_viewer_settings(
            graphics.get("engineering_viewer") if isinstance(graphics, Mapping) else None
        )
        return float(settings["tangent_selection_angle_degrees"])

    @pyqtSlot(float, result=bool)
    def set_viewer_tangent_selection_angle_degrees(self, value: float) -> bool:
        controller = self._app_preferences_controller
        update = getattr(controller, "update_graphics_settings", None)
        if not callable(update):
            return False
        angle = float(
            normalize_engineering_viewer_settings(
                {"tangent_selection_angle_degrees": value}
            )["tangent_selection_angle_degrees"]
        )
        try:
            update(
                {"engineering_viewer": {"tangent_selection_angle_degrees": angle}},
                host=self.parent(),
            )
        except Exception:  # noqa: BLE001
            return False
        self.viewer_tangent_selection_angle_changed.emit(angle)
        return True

    @pyqtSlot(str, result="QVariantList")
    def viewer_camera_bookmarks(self, node_id: str) -> list[dict[str, Any]]:
        resolved = self._node_properties(node_id)
        if resolved is None:
            return []
        return _normalized_camera_bookmarks(resolved[2].get("camera_bookmarks"))

    @pyqtSlot(str, result=int)
    def viewer_camera_bookmark_current_index(self, node_id: str) -> int:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        if not bookmarks:
            return -1
        key = self._bookmark_key(node_id)
        current = self._bookmark_indices.get(key) if key is not None else None
        if current is None or current < 0 or current >= len(bookmarks):
            if key is not None:
                self._bookmark_indices.pop(key, None)
            return -1
        return current

    @pyqtSlot(str, str, result=bool)
    def save_viewer_camera_bookmark(self, node_id: str, name: str) -> bool:
        host_service = self._viewer_host_service
        snapshot = getattr(host_service, "camera_state_snapshot", None)
        if not callable(snapshot):
            return False
        try:
            camera_state = dict(snapshot(str(node_id or "")) or {})
        except Exception:  # noqa: BLE001
            return False
        if not camera_state:
            return False
        resolved = self._node_properties(node_id)
        if resolved is not None:
            properties = resolved[2]
            camera_state.update(
                {
                    key: _VIEWER_OPTION_COERCERS[key](properties.get(key))
                    for key in ("clip_enabled", "clip_axis", "clip_offset")
                }
            )
        bookmarks = self.viewer_camera_bookmarks(node_id)
        bookmarks.append(
            {
                "name": str(name or "").strip() or _next_bookmark_name(bookmarks),
                "camera_state": camera_state,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if not self._set_node_property(node_id, "camera_bookmarks", bookmarks):
            return False
        key = self._bookmark_key(node_id)
        if key is not None:
            self._bookmark_indices[key] = len(bookmarks) - 1
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, result=bool)
    def apply_viewer_camera_bookmark(self, node_id: str, index: int) -> bool:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        normalized_index = int(index)
        if normalized_index < 0 or normalized_index >= len(bookmarks):
            return False
        host_service = self._viewer_host_service
        apply_state = getattr(host_service, "apply_overlay_camera_state", None)
        camera_state = dict(bookmarks[normalized_index]["camera_state"])
        if not callable(apply_state):
            return False
        resolved = self._node_properties(node_id)
        if resolved is None:
            return False
        properties = resolved[2]
        option_updates = {
            key: _VIEWER_OPTION_COERCERS[key](camera_state[key])
            for key in ("parallel_projection", "clip_enabled", "clip_axis", "clip_offset")
            if key in camera_state
        }
        previous_values = {key: copy.deepcopy(properties.get(key)) for key in option_updates}
        applied_properties: list[str] = []
        for key, value in option_updates.items():
            if not self._set_node_property(node_id, key, value):
                for rollback_key in reversed(applied_properties):
                    self._set_node_property(node_id, rollback_key, previous_values[rollback_key])
                return False
            applied_properties.append(key)
        try:
            applied = bool(apply_state(str(node_id or ""), camera_state))
        except Exception:  # noqa: BLE001
            applied = False
        if not applied:
            for key in reversed(applied_properties):
                self._set_node_property(node_id, key, previous_values[key])
            return False
        for key, value in option_updates.items():
            self._sync_viewer_session_option(node_id, key, value)
        key = self._bookmark_key(node_id)
        if key is not None:
            self._bookmark_indices[key] = normalized_index
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, str, result=bool)
    def rename_viewer_camera_bookmark(self, node_id: str, index: int, name: str) -> bool:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        normalized_index = int(index)
        normalized_name = str(name or "").strip()
        if normalized_index < 0 or normalized_index >= len(bookmarks) or not normalized_name:
            return False
        bookmarks[normalized_index]["name"] = normalized_name
        if not self._set_node_property(node_id, "camera_bookmarks", bookmarks):
            return False
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, int, result=bool)
    def move_viewer_camera_bookmark(self, node_id: str, index: int, delta: int) -> bool:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        source = int(index)
        target = source + int(delta)
        if source < 0 or source >= len(bookmarks) or target < 0 or target >= len(bookmarks):
            return False
        bookmarks[source], bookmarks[target] = bookmarks[target], bookmarks[source]
        if not self._set_node_property(node_id, "camera_bookmarks", bookmarks):
            return False
        key = self._bookmark_key(node_id)
        current = self._bookmark_indices.get(key) if key is not None else None
        if key is not None and current is not None:
            if current == source:
                self._bookmark_indices[key] = target
            elif current == target:
                self._bookmark_indices[key] = source
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, result=bool)
    def remove_viewer_camera_bookmark(self, node_id: str, index: int) -> bool:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        normalized_index = int(index)
        if normalized_index < 0 or normalized_index >= len(bookmarks):
            return False
        del bookmarks[normalized_index]
        if not self._set_node_property(node_id, "camera_bookmarks", bookmarks):
            return False
        key = self._bookmark_key(node_id)
        current = self._bookmark_indices.get(key) if key is not None else None
        if key is not None and current is not None:
            if not bookmarks:
                self._bookmark_indices.pop(key, None)
            elif current > normalized_index:
                self._bookmark_indices[key] = current - 1
            elif current == normalized_index:
                self._bookmark_indices.pop(key, None)
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, result=bool)
    def cycle_viewer_camera_bookmark(self, node_id: str, delta: int) -> bool:
        bookmarks = self.viewer_camera_bookmarks(node_id)
        if not bookmarks:
            return False
        key = self._bookmark_key(node_id)
        direction = -1 if int(delta) < 0 else 1
        current = self._bookmark_indices.get(key) if key is not None else None
        target = (len(bookmarks) - 1 if direction < 0 else 0) if current is None else (current + direction) % len(bookmarks)
        return self.apply_viewer_camera_bookmark(node_id, target)

    @pyqtSlot(str, result="QVariantMap")
    def viewer_saved_selections(self, node_id: str) -> dict[str, Any]:
        resolved = self._node_properties(node_id)
        if resolved is None:
            return empty_engineering_selection_set()
        summary = self._session_state(node_id).get("summary")
        summary = summary if isinstance(summary, Mapping) else {}
        fingerprint = str(summary.get("scene_fingerprint", "") or "").strip()
        raw_selections = resolved[2].get(_ENGINEERING_SAVED_SELECTIONS_PROPERTY)
        if (
            not isinstance(raw_selections, Mapping)
            or raw_selections.get("schema") != ENGINEERING_SELECTION_SCHEMA
        ):
            return empty_engineering_selection_set(scene_fingerprint=fingerprint)
        try:
            selections = normalize_engineering_selection_set(raw_selections)
        except (TypeError, ValueError):
            return empty_engineering_selection_set(scene_fingerprint=fingerprint)
        if fingerprint and selections["scene_fingerprint"] and selections["scene_fingerprint"] != fingerprint:
            return empty_engineering_selection_set(scene_fingerprint=fingerprint)
        return selections

    @pyqtSlot(str, str, result=bool)
    def save_current_viewer_selection(self, node_id: str, name: str) -> bool:
        host_service = self._viewer_host_service
        snapshot = getattr(host_service, "viewer_selection_snapshot", None)
        if not callable(snapshot):
            return False
        try:
            current = dict(snapshot(str(node_id or "")) or {})
        except Exception:  # noqa: BLE001
            return False
        entities = current.get("entities")
        if not isinstance(entities, (list, tuple)) or not entities:
            return False
        selections = self.viewer_saved_selections(node_id)
        fingerprint = str(current.get("scene_fingerprint", "")).strip()
        if selections["scene_fingerprint"] not in {"", fingerprint}:
            selections = empty_engineering_selection_set(scene_fingerprint=fingerprint)
        selections["scene_fingerprint"] = fingerprint
        selections["selections"].append(
            {
                "name": str(name or "").strip() or f"Selection {len(selections['selections']) + 1}",
                "entities": [copy.deepcopy(dict(value)) for value in entities if isinstance(value, Mapping)],
                "scene_fingerprint": fingerprint,
            }
        )
        try:
            selections = normalize_engineering_selection_set(selections)
        except (TypeError, ValueError):
            return False
        if not self._set_node_property(node_id, _ENGINEERING_SAVED_SELECTIONS_PROPERTY, selections):
            return False
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, str, result=bool)
    def rename_viewer_selection(self, node_id: str, index: int, name: str) -> bool:
        selections = self.viewer_saved_selections(node_id)
        normalized_index = int(index)
        normalized_name = str(name or "").strip()
        if normalized_index < 0 or normalized_index >= len(selections["selections"]) or not normalized_name:
            return False
        old_name = selections["selections"][normalized_index]["name"]
        selections["selections"][normalized_index]["name"] = normalized_name
        if selections["published_name"] == old_name:
            selections["published_name"] = normalized_name
        if not self._set_node_property(node_id, _ENGINEERING_SAVED_SELECTIONS_PROPERTY, selections):
            return False
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, result=bool)
    def publish_viewer_selection(self, node_id: str, index: int) -> bool:
        selections = self.viewer_saved_selections(node_id)
        normalized_index = int(index)
        if normalized_index < 0 or normalized_index >= len(selections["selections"]):
            return False
        selections["published_name"] = selections["selections"][normalized_index]["name"]
        if not self._set_node_property(node_id, _ENGINEERING_SAVED_SELECTIONS_PROPERTY, selections):
            return False
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(str, int, result=bool)
    def activate_viewer_selection(self, node_id: str, index: int) -> bool:
        selections = self.viewer_saved_selections(node_id)
        normalized_index = int(index)
        if normalized_index < 0 or normalized_index >= len(selections["selections"]):
            return False
        selection = selections["selections"][normalized_index]
        activate = getattr(self._viewer_host_service, "activate_viewer_selection", None)
        if not callable(activate):
            return False
        try:
            return bool(activate(str(node_id or ""), list(selection.get("entities", ()))))
        except Exception:  # noqa: BLE001
            return False

    @pyqtSlot(str, int, result=bool)
    def remove_viewer_selection(self, node_id: str, index: int) -> bool:
        selections = self.viewer_saved_selections(node_id)
        normalized_index = int(index)
        if normalized_index < 0 or normalized_index >= len(selections["selections"]):
            return False
        removed = selections["selections"].pop(normalized_index)
        if selections["published_name"] == removed["name"]:
            selections["published_name"] = ""
        if not self._set_node_property(node_id, _ENGINEERING_SAVED_SELECTIONS_PROPERTY, selections):
            return False
        self.viewer_control_changed.emit(str(node_id or ""))
        return True

    @pyqtSlot(result=bool)
    def viewer_query_available(self) -> bool:
        return callable(getattr(self._viewer_session_bridge, "query_session", None))

    @pyqtSlot(str, str, "QVariantMap", result="QVariantMap")
    def query_viewer(self, node_id: str, query_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._session_state(node_id)
        workspace_id = str(state.get("workspace_id", "") or "").strip()
        session_id = str(state.get("session_id", "") or "").strip()
        query = getattr(self._viewer_session_bridge, "query_session", None)
        if not callable(query) or not workspace_id or not session_id:
            return {
                "supported": False,
                "value": {},
                "explanation": "The active viewer session is not ready for engineering queries.",
            }
        try:
            result = query(
                workspace_id=workspace_id,
                node_id=str(node_id or ""),
                session_id=session_id,
                query_type=str(query_type or "").strip(),
                payload=dict(payload or {}),
            )
        except Exception as exc:  # noqa: BLE001
            return {"supported": False, "value": {}, "explanation": str(exc)}
        if isinstance(result, Mapping):
            return {
                "supported": bool(result.get("supported")),
                "value": dict(result.get("value") or {}),
                "explanation": str(result.get("explanation", "") or ""),
            }
        return {
            "supported": bool(getattr(result, "supported", False)),
            "value": dict(getattr(result, "value", {}) or {}),
            "explanation": str(getattr(result, "explanation", "") or ""),
        }

    @pyqtSlot(str, str, result="QVariantMap")
    def export_engineering_viewer(self, node_id: str, export_format: str) -> dict[str, Any]:
        normalized = str(export_format or "").strip().casefold()
        filters = {
            "step": (".step", "STEP CAD (*.step *.stp)"),
            "vtu": (".vtu", "VTK Unstructured Grid (*.vtu)"),
            "vtm": (".vtm", "VTK MultiBlock (*.vtm)"),
            "gltf": (".gltf", "glTF Scene (*.gltf)"),
            "glb": (".glb", "Binary glTF (*.glb)"),
        }
        if normalized not in filters:
            return {
                "supported": False,
                "value": {},
                "explanation": f"Neutral export format '{normalized}' is not supported.",
            }
        resolved = self._node_properties(node_id)
        if resolved is None:
            return {"supported": False, "value": {}, "explanation": "The viewer node is unavailable."}
        suffix, file_filter = filters[normalized]
        picker = self._save_file_dialog
        if not callable(picker):
            return {"supported": False, "value": {}, "explanation": "The export file picker is unavailable."}
        title = str(getattr(resolved[1], "title", "") or "engineering_viewer")
        safe_title = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in title).strip("_") or "engineering_viewer"
        try:
            output_path = str(
                picker(
                    title=f"Export {normalized.upper()}",
                    suggested_path=f"{safe_title}{suffix}",
                    file_filter=file_filter,
                    default_suffix=suffix,
                )
                or ""
            ).strip()
        except TypeError:
            output_path = str(picker(f"Export {normalized.upper()}", f"{safe_title}{suffix}", file_filter) or "").strip()
        if not output_path:
            return {"supported": False, "value": {}, "explanation": ""}
        stats_getter = getattr(self._viewer_host_service, "viewer_render_stats", None)
        stats = stats_getter(node_id) if callable(stats_getter) else {}
        display_state = stats.get("display_state", {}) if isinstance(stats, Mapping) else {}
        return self.query_viewer(node_id, "export", {
            "format": normalized,
            "path": output_path,
            "display_state": dict(display_state),
        })


__all__ = ["ViewerControlBridge"]
