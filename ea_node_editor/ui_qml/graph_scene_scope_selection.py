from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF

from ea_node_editor.graph.hierarchy import (
    ScopePath,
    breadcrumb_scope_path,
    is_node_in_scope,
    node_scope_path,
    normalize_scope_path,
    scope_node_ids,
    subnode_scope_path,
)
from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.nodes.builtins.subnode import is_subnode_shell_type
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.ui_qml.edge_routing import node_size, port_scene_pos

if TYPE_CHECKING:
    from ea_node_editor.ui_qml.graph_scene_bridge import _GraphSceneContext

_MINIMAP_EMPTY_BOUNDS = QRectF(-1600.0, -900.0, 3200.0, 1800.0)
_MINIMAP_PADDING = 220.0
_MINIMAP_MIN_WIDTH = 3200.0
_MINIMAP_MIN_HEIGHT = 1800.0


@dataclass(slots=True)
class _SelectedNodeProxy:
    node: NodeInstance


class _NodeItemProxy:
    def __init__(
        self,
        node: NodeInstance,
        spec: NodeTypeSpec,
        workspace_nodes: dict[str, NodeInstance],
    ) -> None:
        self.node = node
        self.spec = spec
        self.workspace_nodes = workspace_nodes

    def sceneBoundingRect(self) -> QRectF:
        width, height = node_size(self.node, self.spec, self.workspace_nodes)
        return QRectF(self.node.x, self.node.y, width, height)

    def port_scene_pos(self, port_key: str) -> QPointF:
        return port_scene_pos(self.node, self.spec, port_key, self.workspace_nodes)


class GraphSceneScopeSelection:
    def __init__(self, scene_context: _GraphSceneContext) -> None:
        self._scene_context = scene_context

    @property
    def workspace_id(self) -> str:
        return self._scene_context.workspace_id

    @workspace_id.setter
    def workspace_id(self, value: str) -> None:
        self._scene_context.workspace_id = str(value or "")

    @property
    def scope_path(self) -> ScopePath:
        return self._scene_context.scope_path

    @scope_path.setter
    def scope_path(self, value: ScopePath) -> None:
        self._scene_context.scope_path = tuple(str(node_id) for node_id in tuple(value or ()))

    @property
    def selected_node_ids(self) -> list[str]:
        return self._scene_context.selected_node_ids

    @selected_node_ids.setter
    def selected_node_ids(self, value: list[str]) -> None:
        self._scene_context.selected_node_ids = [str(node_id) for node_id in list(value or [])]

    @property
    def selected_node_lookup(self) -> dict[str, bool]:
        return self._scene_context.selected_node_lookup

    @selected_node_lookup.setter
    def selected_node_lookup(self, value: dict[str, bool]) -> None:
        self._scene_context.selected_node_lookup = {
            str(node_id): bool(selected) for node_id, selected in dict(value or {}).items()
        }

    @property
    def comment_peek_node_id(self) -> str:
        return self._scene_context.comment_peek_node_id

    @comment_peek_node_id.setter
    def comment_peek_node_id(self, value: str) -> None:
        self._scene_context.comment_peek_node_id = str(value or "").strip()

    @property
    def interact_with_locked_objects(self) -> bool:
        return bool(self._scene_context.interact_with_locked_objects)

    def set_interact_with_locked_objects(self, enabled: bool) -> bool:
        normalized = bool(enabled)
        if self.interact_with_locked_objects == normalized:
            return False
        self._scene_context.interact_with_locked_objects = normalized
        workspace = self.workspace_or_none()
        if workspace is not None:
            self.set_selected_node_ids(self.selected_node_ids, workspace=workspace)
        self._scene_context._bridge.interact_with_locked_objects_changed.emit()
        return True

    def workspace_or_none(self) -> WorkspaceData | None:
        return self._scene_context.workspace_or_none()

    @staticmethod
    def _is_group_backdrop_spec(spec: NodeTypeSpec) -> bool:
        return str(spec.surface_family or "").strip() == "group_backdrop"

    def _is_collapsed_group_backdrop(self, workspace: WorkspaceData, node_id: str) -> bool:
        registry = self._scene_context.registry
        if registry is None:
            return False
        node = workspace.nodes.get(node_id)
        if node is None or not bool(node.collapsed):
            return False
        spec = registry.spec_or_none(node.type_id)
        return spec is not None and self._is_group_backdrop_spec(spec)

    def _can_open_comment_peek_in_workspace(self, workspace: WorkspaceData, node_id: str) -> bool:
        normalized = str(node_id or "").strip()
        if not normalized or normalized not in workspace.nodes:
            return False
        if not is_node_in_scope(workspace, normalized, self.scope_path):
            return False
        return self._is_collapsed_group_backdrop(workspace, normalized)

    def can_open_comment_peek(self, node_id: str) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        return self._can_open_comment_peek_in_workspace(workspace, node_id)

    def _comment_peek_payload(self, node_id: str) -> dict[str, object] | None:
        normalized = str(node_id or "").strip()
        if not normalized:
            return None
        for payload in self._scene_context.backdrop_nodes_payload:
            if str(payload.get("node_id", "")).strip() == normalized:
                return payload
        return None

    @staticmethod
    def _payload_node_id_list(payload: dict[str, object] | None, key: str) -> list[str]:
        if payload is None:
            return []
        value = payload.get(key)
        if value is None:
            return []
        if isinstance(value, (str, bytes)):
            values = [value]
        else:
            try:
                values = list(value)  # type: ignore[arg-type]
            except TypeError:
                values = [value]
        return [str(item).strip() for item in values if str(item).strip()]

    def _comment_peek_visible_node_set(self, workspace: WorkspaceData) -> set[str]:
        peek_node_id = self.comment_peek_node_id
        if not self._can_open_comment_peek_in_workspace(workspace, peek_node_id):
            return set(scope_node_ids(workspace, self.scope_path))
        payload = self._comment_peek_payload(peek_node_id)
        visible_ids = {peek_node_id}
        visible_ids.update(self._payload_node_id_list(payload, "member_node_ids"))
        visible_ids.update(self._payload_node_id_list(payload, "member_backdrop_ids"))
        scope_ids = set(scope_node_ids(workspace, self.scope_path))
        return {node_id for node_id in visible_ids if node_id in workspace.nodes and node_id in scope_ids}

    def visible_node_ids(self, workspace: WorkspaceData) -> list[str]:
        scoped_ids = scope_node_ids(workspace, self.scope_path)
        if not self.comment_peek_node_id:
            return scoped_ids
        visible_set = self._comment_peek_visible_node_set(workspace)
        return [node_id for node_id in scoped_ids if node_id in visible_set]

    def validated_comment_peek_node_id(self) -> str:
        workspace = self.workspace_or_none()
        if workspace is None or not self.comment_peek_node_id:
            return ""
        if self._can_open_comment_peek_in_workspace(workspace, self.comment_peek_node_id):
            return self.comment_peek_node_id
        self.comment_peek_node_id = ""
        return ""

    def open_comment_peek(self, node_id: str) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        normalized = str(node_id or "").strip()
        if not self._can_open_comment_peek_in_workspace(workspace, normalized):
            return False
        if self.comment_peek_node_id == normalized:
            return True
        self.comment_peek_node_id = normalized
        self.set_selected_node_ids([normalized], workspace=workspace)
        self._scene_context.rebuild_models()
        return True

    def close_comment_peek(self) -> bool:
        if not self.comment_peek_node_id:
            return False
        workspace = self.workspace_or_none()
        self.comment_peek_node_id = ""
        if workspace is not None:
            self.set_selected_node_ids(self.selected_node_ids, workspace=workspace)
        self._scene_context.rebuild_models()
        return True

    @staticmethod
    def active_view_state(workspace: WorkspaceData) -> ViewState | None:
        workspace.ensure_default_view()
        if not workspace.active_view_id:
            return None
        return workspace.views.get(workspace.active_view_id)

    def normalized_selected_node_ids(
        self,
        workspace: WorkspaceData | None,
        node_ids: list[str],
    ) -> list[str]:
        if workspace is None:
            return []
        peek_visible_ids: set[str] | None = None
        if self.comment_peek_node_id and self._can_open_comment_peek_in_workspace(
            workspace,
            self.comment_peek_node_id,
        ):
            payload = self._comment_peek_payload(self.comment_peek_node_id)
            peek_visible_ids = {self.comment_peek_node_id}
            peek_visible_ids.update(self._payload_node_id_list(payload, "member_node_ids"))
            peek_visible_ids.update(self._payload_node_id_list(payload, "member_backdrop_ids"))
        normalized: list[str] = []
        seen: set[str] = set()
        for node_id in node_ids:
            normalized_node_id = str(node_id).strip()
            if not normalized_node_id or normalized_node_id in seen:
                continue
            if not is_node_in_scope(workspace, normalized_node_id, self.scope_path):
                continue
            node = workspace.nodes.get(normalized_node_id)
            if node is None or (bool(node.locked) and not self.interact_with_locked_objects):
                continue
            if peek_visible_ids is not None and normalized_node_id not in peek_visible_ids:
                continue
            seen.add(normalized_node_id)
            normalized.append(normalized_node_id)
        return normalized

    @staticmethod
    def selected_node_lookup_for_ids(node_ids: list[str]) -> dict[str, bool]:
        return {node_id: True for node_id in node_ids}

    def set_selected_node_ids(
        self,
        node_ids: list[str],
        *,
        workspace: WorkspaceData | None = None,
        emit_signals: bool = True,
    ) -> bool:
        resolved_workspace = workspace if workspace is not None else self.workspace_or_none()
        normalized_node_ids = self.normalized_selected_node_ids(resolved_workspace, node_ids)
        selected_lookup = self.selected_node_lookup_for_ids(normalized_node_ids)
        selection_changed = normalized_node_ids != self.selected_node_ids
        lookup_changed = selected_lookup != self.selected_node_lookup
        if not selection_changed and not lookup_changed:
            return False
        self.selected_node_ids = normalized_node_ids
        self.selected_node_lookup = selected_lookup
        if emit_signals:
            primary_node_id = normalized_node_ids[-1] if normalized_node_ids else ""
            self._scene_context.emit_selection_changed(primary_node_id)
        return True

    def apply_scope_path(
        self,
        workspace: WorkspaceData,
        scope_path: ScopePath,
        *,
        persist: bool = True,
        emit_scope_changed: bool = True,
        emit_selection_changed: bool = True,
    ) -> bool:
        normalized_scope = normalize_scope_path(workspace, scope_path)
        changed = normalized_scope != self.scope_path
        if changed:
            self.comment_peek_node_id = ""
        self.scope_path = normalized_scope
        if persist:
            view_state = self.active_view_state(workspace)
            if view_state is not None:
                view_state.scope_path = list(normalized_scope)
        selection_changed = self.set_selected_node_ids(
            self.selected_node_ids,
            workspace=workspace,
            emit_signals=emit_selection_changed,
        )
        if changed:
            self._scene_context.rebuild_models()
            if emit_scope_changed:
                self._scene_context.emit_scope_changed()
        elif selection_changed and emit_selection_changed:
            # Selection no longer lives in the node payload, so no model rebuild is needed here.
            pass
        return changed

    def restore_scope_path_from_view(self, workspace: WorkspaceData) -> None:
        view_state = self.active_view_state(workspace)
        scope_path: ScopePath = ()
        if view_state is not None:
            scope_path = normalize_scope_path(workspace, view_state.scope_path)
            if list(scope_path) != view_state.scope_path:
                view_state.scope_path = list(scope_path)
        self.scope_path = scope_path

    def sync_scope_with_active_view(self) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        view_state = self.active_view_state(workspace)
        target_scope: ScopePath = ()
        if view_state is not None:
            target_scope = normalize_scope_path(workspace, view_state.scope_path)
        return self.apply_scope_path(workspace, target_scope)

    def open_subnode_scope(self, node_id: str) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        normalized_node_id = str(node_id).strip()
        if not normalized_node_id:
            return False
        node = workspace.nodes.get(normalized_node_id)
        if node is None or not is_subnode_shell_type(node.type_id):
            return False
        if not is_node_in_scope(workspace, normalized_node_id, self.scope_path):
            return False
        return self.apply_scope_path(workspace, subnode_scope_path(workspace, normalized_node_id))

    def open_scope_for_node(self, node_id: str) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        normalized_node_id = str(node_id).strip()
        if not normalized_node_id or normalized_node_id not in workspace.nodes:
            return False
        return self.apply_scope_path(workspace, node_scope_path(workspace, normalized_node_id))

    def navigate_scope_parent(self) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None or not self.scope_path:
            return False
        return self.apply_scope_path(workspace, self.scope_path[:-1])

    def navigate_scope_root(self) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None or not self.scope_path:
            return False
        return self.apply_scope_path(workspace, ())

    def navigate_scope_to(self, node_id: str) -> bool:
        workspace = self.workspace_or_none()
        if workspace is None:
            return False
        next_scope = breadcrumb_scope_path(workspace, self.scope_path, node_id)
        return self.apply_scope_path(workspace, next_scope)

    def set_workspace(self, workspace_id: str) -> None:
        self.workspace_id = str(workspace_id)
        model = self._scene_context.model
        if model is None:
            return
        workspace = model.project.workspaces[self.workspace_id]
        self.comment_peek_node_id = ""
        self.restore_scope_path_from_view(workspace)
        self.set_selected_node_ids([], workspace=workspace)
        self._scene_context.rebuild_models()
        self._scene_context.emit_workspace_changed()
        self._scene_context.emit_scope_changed()

    def refresh_workspace_from_model(self, workspace_id: str) -> None:
        model = self._scene_context.model
        if model is None:
            return
        normalized_workspace_id = str(workspace_id).strip()
        if not normalized_workspace_id or normalized_workspace_id != self.workspace_id:
            return
        workspace = model.project.workspaces.get(self.workspace_id)
        if workspace is None:
            return
        normalized_scope = normalize_scope_path(workspace, self.scope_path)
        if normalized_scope != self.scope_path:
            self.apply_scope_path(
                workspace,
                normalized_scope,
                persist=True,
                emit_scope_changed=False,
            )
            self._scene_context.emit_scope_changed()
        else:
            self.validated_comment_peek_node_id()
            self.set_selected_node_ids(self.selected_node_ids, workspace=workspace)
            self._scene_context.rebuild_models()

    def selected_node_id(self) -> str | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        visible_ids = set(self.visible_node_ids(workspace))
        for node_id in reversed(self.selected_node_ids):
            if node_id in workspace.nodes and node_id in visible_ids:
                return node_id
        return None

    def selected_items(self) -> list[_SelectedNodeProxy]:
        workspace = self._scene_context.current_workspace()
        selected: list[_SelectedNodeProxy] = []
        visible_ids = set(self.visible_node_ids(workspace))
        for node_id in self.selected_node_ids:
            node = workspace.nodes.get(node_id)
            if node is not None and node_id in visible_ids:
                selected.append(_SelectedNodeProxy(node=node))
        return selected

    def workspace_scene_bounds(self) -> QRectF | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        visible_node_ids = self.visible_node_ids(workspace)
        if not visible_node_ids:
            return None
        return self.bounds_for_node_ids(visible_node_ids)

    def workspace_scene_bounds_with_fallback(self) -> QRectF:
        bounds = self.workspace_scene_bounds()
        if bounds is None:
            return QRectF(_MINIMAP_EMPTY_BOUNDS)
        normalized = QRectF(bounds).normalized()
        if not normalized.isValid() or normalized.width() <= 0.0 or normalized.height() <= 0.0:
            return QRectF(_MINIMAP_EMPTY_BOUNDS)
        padded = normalized.adjusted(-_MINIMAP_PADDING, -_MINIMAP_PADDING, _MINIMAP_PADDING, _MINIMAP_PADDING)
        width = max(float(padded.width()), _MINIMAP_MIN_WIDTH)
        height = max(float(padded.height()), _MINIMAP_MIN_HEIGHT)
        center = padded.center()
        return QRectF(
            float(center.x()) - (width * 0.5),
            float(center.y()) - (height * 0.5),
            width,
            height,
        )

    @staticmethod
    def rect_payload(rect: QRectF) -> dict[str, float]:
        normalized = QRectF(rect).normalized()
        return {
            "x": float(normalized.x()),
            "y": float(normalized.y()),
            "width": float(max(0.0, normalized.width())),
            "height": float(max(0.0, normalized.height())),
        }

    def workspace_scene_bounds_map(self) -> dict[str, float]:
        return self.rect_payload(self.workspace_scene_bounds_with_fallback())

    def selection_bounds(self) -> QRectF | None:
        workspace = self.workspace_or_none()
        if workspace is None:
            return None
        selected_node_ids = self.selected_node_ids_in_workspace(workspace)
        if not selected_node_ids:
            return None
        return self.bounds_for_node_ids(selected_node_ids)

    def clear_selection(self) -> None:
        self.set_selected_node_ids([])

    def select_node(self, node_id: str, additive: bool = False) -> None:
        if not node_id:
            self.clear_selection()
            return
        workspace = self.workspace_or_none()
        if workspace is None:
            return
        if self._scene_context.node(node_id) is None:
            return
        if not is_node_in_scope(workspace, node_id, self.scope_path):
            return
        if additive:
            if node_id in self.selected_node_ids:
                next_selected = [value for value in self.selected_node_ids if value != node_id]
            else:
                next_selected = [*self.selected_node_ids, node_id]
        else:
            next_selected = [node_id]
        self.set_selected_node_ids(next_selected, workspace=workspace)

    def select_nodes_in_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        additive: bool = False,
    ) -> None:
        if self._scene_context.model is None or self._scene_context.registry is None or not self.workspace_id:
            return

        workspace = self._scene_context.current_workspace()
        visible_node_ids = set(self.visible_node_ids(workspace))
        # Keep the horizontal drag direction before normalizing the rectangle.
        select_enclosed_only = float(x2) >= float(x1)
        min_x = min(float(x1), float(x2))
        max_x = max(float(x1), float(x2))
        min_y = min(float(y1), float(y2))
        max_y = max(float(y1), float(y2))

        hit_ids: list[str] = []
        for node_id, node in workspace.nodes.items():
            if node_id not in visible_node_ids:
                continue
            spec = self._scene_context.registry.get_spec(node.type_id)
            width, height = node_size(node, spec, workspace.nodes)
            node_min_x = float(node.x)
            node_max_x = node_min_x + width
            node_min_y = float(node.y)
            node_max_y = node_min_y + height
            if select_enclosed_only:
                node_matches = (
                    node_min_x >= min_x
                    and node_max_x <= max_x
                    and node_min_y >= min_y
                    and node_max_y <= max_y
                )
            else:
                node_matches = not (
                    node_max_x < min_x
                    or node_min_x > max_x
                    or node_max_y < min_y
                    or node_min_y > max_y
                )
            if node_matches:
                hit_ids.append(node_id)

        if additive:
            next_selected = [
                node_id
                for node_id in self.selected_node_ids
                if node_id in workspace.nodes and node_id in visible_node_ids
            ]
            for node_id in hit_ids:
                if node_id not in next_selected:
                    next_selected.append(node_id)
        else:
            next_selected = hit_ids

        if next_selected == self.selected_node_ids:
            return

        self.set_selected_node_ids(next_selected, workspace=workspace)

    def node_item(self, node_id: str) -> _NodeItemProxy | None:
        model = self._scene_context.model
        registry = self._scene_context.registry
        if model is None or registry is None:
            return None
        workspace = model.project.workspaces.get(self.workspace_id)
        if workspace is None:
            return None
        node = workspace.nodes.get(node_id)
        if node is None:
            return None
        if node_id not in set(self.visible_node_ids(workspace)):
            return None
        spec = registry.get_spec(node.type_id)
        return _NodeItemProxy(node=node, spec=spec, workspace_nodes=workspace.nodes)

    def node_bounds(self, node_id: str) -> QRectF | None:
        item = self.node_item(node_id)
        if item is None:
            return None
        bridge = self._scene_context._bridge
        bridge._ensure_payload_cache_current()
        cache = bridge._payload_cache
        if not cache.indexes_valid:
            cache.rebuild_indexes()
        status, location = cache.resolve_node_payload_slot(str(node_id or "").strip())
        if status == "ok" and location is not None:
            collection_name, index = location
            collection = cache.nodes if collection_name == "nodes" else cache.backdrop_nodes
            payload = collection[index]
            try:
                payload_bounds = QRectF(
                    float(payload["x"]),
                    float(payload["y"]),
                    float(payload["width"]),
                    float(payload["height"]),
                )
            except (KeyError, TypeError, ValueError):
                pass
            else:
                if payload_bounds.width() > 0.0 and payload_bounds.height() > 0.0:
                    return payload_bounds
        return QRectF(item.sceneBoundingRect())

    def bounds_for_node_ids(self, node_ids: list[str]) -> QRectF | None:
        bounds: QRectF | None = None
        for node_id in node_ids:
            node_bounds = self.node_bounds(node_id)
            if node_bounds is None:
                continue
            if bounds is None:
                bounds = QRectF(node_bounds)
                continue
            bounds = bounds.united(node_bounds)
        return bounds

    def selected_node_ids_in_workspace(self, workspace: WorkspaceData) -> list[str]:
        selected_node_ids: list[str] = []
        selected_node_set: set[str] = set()
        for node_id in self.selected_node_ids:
            if node_id not in workspace.nodes or node_id in selected_node_set:
                continue
            if node_id not in set(self.visible_node_ids(workspace)):
                continue
            selected_node_set.add(node_id)
            selected_node_ids.append(node_id)
        return selected_node_ids


__all__ = [
    "GraphSceneScopeSelection",
    "_NodeItemProxy",
    "_SelectedNodeProxy",
]
