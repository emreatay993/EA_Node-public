from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from weakref import ReferenceType, ref as weakref_ref

from ea_node_editor.graph.workspace_state import WorkspaceData, WorkspaceSnapshot

ACTION_ADD_NODE = "add-node"
ACTION_REMOVE_NODE = "remove-node"
ACTION_ADD_EDGE = "add-edge"
ACTION_REMOVE_EDGE = "remove-edge"
ACTION_RENAME_NODE = "rename-node"
ACTION_TOGGLE_COLLAPSED = "toggle-collapsed"
ACTION_TOGGLE_SETTINGS_GROUP = "toggle-settings-group"
ACTION_TOGGLE_NODE_LOCKED = "toggle-node-locked"
ACTION_TOGGLE_EXPOSED_PORT = "toggle-exposed-port"
ACTION_EDIT_NODE_PROPERTY = "edit-node-property"
ACTION_EDIT_NODE_STYLE = "edit-node-style"
ACTION_EDIT_NODE_LINK = "edit-node-link"
ACTION_EDIT_NODE_COMMENT = "edit-node-comment"
ACTION_EDIT_EDGE_LABEL = "edit-edge-label"
ACTION_EDIT_EDGE_STYLE = "edit-edge-style"
ACTION_TOGGLE_EDGE_ENABLED = "toggle-edge-enabled"
ACTION_EDIT_PORT_LABEL = "edit-port-label"
ACTION_EDIT_PORT_MODIFIERS = "edit-port-modifiers"
ACTION_SET_PRINCIPAL_INPUT = "set-principal-input"
ACTION_INSERT_DYNAMIC_PORT = "insert-dynamic-port"
ACTION_REMOVE_DYNAMIC_PORT = "remove-dynamic-port"
ACTION_RENAME_DYNAMIC_PORT = "rename-dynamic-port"
ACTION_DUPLICATE_SUBGRAPH = "duplicate-subgraph"
ACTION_PASTE_SUBGRAPH = "paste-subgraph"
ACTION_GROUP_SELECTED_NODES = "group-selected-nodes"
ACTION_UNGROUP_SELECTED_SUBNODE = "ungroup-selected-subnode"
ACTION_WRAP_GROUP = "wrap-group"
ACTION_EDIT_PROPERTY = ACTION_EDIT_NODE_PROPERTY
ACTION_DELETE_SELECTED = "delete-selected"
ACTION_MOVE_NODE = "move-node"
ACTION_RESIZE_NODE = "resize-node"
_EXECUTION_PRESERVING_ACTION_TYPES = frozenset(
    {
        ACTION_RENAME_NODE,
        ACTION_TOGGLE_COLLAPSED,
        ACTION_TOGGLE_SETTINGS_GROUP,
        ACTION_TOGGLE_NODE_LOCKED,
        ACTION_EDIT_NODE_STYLE,
        ACTION_EDIT_NODE_LINK,
        ACTION_EDIT_NODE_COMMENT,
        ACTION_EDIT_EDGE_LABEL,
        ACTION_EDIT_EDGE_STYLE,
        ACTION_EDIT_PORT_LABEL,
        ACTION_MOVE_NODE,
        ACTION_RESIZE_NODE,
        ACTION_WRAP_GROUP,
    }
)


@dataclass(frozen=True, slots=True)
class HistoryExecutionChange:
    affects_execution: bool
    changed_root_node_ids: tuple[str, ...] = ()
    removed_node_ids: tuple[str, ...] = ()


def classify_history_execution_change(
    action_type: str,
    *,
    registry: object,
    before_snapshot: WorkspaceSnapshot | None = None,
    after_snapshot: WorkspaceSnapshot | None = None,
) -> HistoryExecutionChange:
    normalized_action_type = str(action_type or "").strip()
    if not normalized_action_type:
        return HistoryExecutionChange(False)
    if normalized_action_type in _EXECUTION_PRESERVING_ACTION_TYPES:
        return HistoryExecutionChange(False)
    if not isinstance(before_snapshot, WorkspaceSnapshot) or not isinstance(
        after_snapshot, WorkspaceSnapshot
    ):
        return HistoryExecutionChange(True)
    if (
        before_snapshot.nodes == after_snapshot.nodes
        and before_snapshot.edges == after_snapshot.edges
    ):
        return HistoryExecutionChange(False)

    def is_active(node: object | None) -> bool:
        if node is None:
            return False
        get_spec = getattr(registry, "get_spec", None)
        if not callable(get_spec):
            return False
        try:
            spec = get_spec(str(getattr(node, "type_id", "") or ""))
        except (KeyError, TypeError, ValueError):
            return False
        return str(getattr(spec, "runtime_behavior", "") or "").strip() == "active"

    changed_roots: set[str] = set()
    removed: set[str] = set()
    for node_id in set(before_snapshot.nodes) | set(after_snapshot.nodes):
        before_node = before_snapshot.nodes.get(node_id)
        after_node = after_snapshot.nodes.get(node_id)
        if before_node == after_node:
            continue
        if is_active(after_node):
            changed_roots.add(str(node_id))
        elif is_active(before_node):
            removed.add(str(node_id))

    for edge_id in set(before_snapshot.edges) | set(after_snapshot.edges):
        before_edge = before_snapshot.edges.get(edge_id)
        after_edge = after_snapshot.edges.get(edge_id)
        if before_edge == after_edge:
            continue
        for edge in (before_edge, after_edge):
            if edge is None:
                continue
            target_node_id = str(edge.target_node_id or "").strip()
            if target_node_id and is_active(after_snapshot.nodes.get(target_node_id)):
                changed_roots.add(target_node_id)

    ordered_roots = tuple(
        node_id for node_id in after_snapshot.nodes if node_id in changed_roots
    )
    ordered_removed = tuple(
        node_id for node_id in before_snapshot.nodes if node_id in removed
    )
    return HistoryExecutionChange(
        bool(ordered_roots or ordered_removed),
        ordered_roots,
        ordered_removed,
    )


@dataclass(slots=True)
class HistoryEntry:
    action_type: str
    before: WorkspaceSnapshot
    after: WorkspaceSnapshot


@dataclass(slots=True)
class _OpenGroup:
    action_type: str
    before: WorkspaceSnapshot
    after: WorkspaceSnapshot


@dataclass(slots=True)
class GroupedHistoryResult:
    entry: HistoryEntry | None = None


@dataclass(slots=True)
class _WorkspaceCaptureMemo:
    revision: int
    snapshot: WorkspaceSnapshot
    workspace_ref: ReferenceType[WorkspaceData]


class RuntimeGraphHistory:
    def __init__(self) -> None:
        self._undo_stacks: dict[str, list[HistoryEntry]] = {}
        self._redo_stacks: dict[str, list[HistoryEntry]] = {}
        self._groups: dict[str, list[_OpenGroup]] = {}
        self._last_applied_entries: dict[str, HistoryEntry] = {}
        self._workspace_capture_memos: dict[tuple[str, int], _WorkspaceCaptureMemo] = {}

    def capture_workspace(self, workspace: WorkspaceData) -> WorkspaceSnapshot:
        workspace_id = str(getattr(workspace, "workspace_id", "") or "").strip()
        if not workspace_id:
            return workspace.capture_snapshot()
        revision = int(getattr(workspace, "mutation_revision", 0) or 0)
        memo_key = (workspace_id, id(workspace))
        memo = self._workspace_capture_memos.get(memo_key)
        if (
            memo is not None
            and memo.revision == revision
            and memo.workspace_ref() is workspace
        ):
            return memo.snapshot
        snapshot = workspace.capture_snapshot()
        self._workspace_capture_memos[memo_key] = _WorkspaceCaptureMemo(
            revision=revision,
            snapshot=snapshot,
            workspace_ref=weakref_ref(workspace),
        )
        return snapshot

    def clear_all(self) -> None:
        self._undo_stacks.clear()
        self._redo_stacks.clear()
        self._groups.clear()
        self._last_applied_entries.clear()
        self._workspace_capture_memos.clear()

    def clear_workspace(self, workspace_id: str) -> None:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return
        self._undo_stacks.pop(normalized_id, None)
        self._redo_stacks.pop(normalized_id, None)
        self._groups.pop(normalized_id, None)
        self._last_applied_entries.pop(normalized_id, None)
        self._workspace_capture_memos = {
            key: memo
            for key, memo in self._workspace_capture_memos.items()
            if key[0] != normalized_id
        }

    def undo_depth(self, workspace_id: str) -> int:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return 0
        return len(self._undo_stacks.get(normalized_id, []))

    def redo_depth(self, workspace_id: str) -> int:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return 0
        return len(self._redo_stacks.get(normalized_id, []))

    def can_undo(self, workspace_id: str) -> bool:
        return self.undo_depth(workspace_id) > 0

    def can_redo(self, workspace_id: str) -> bool:
        return self.redo_depth(workspace_id) > 0

    @contextmanager
    def grouped_action(
        self,
        workspace_id: str,
        action_type: str,
        workspace: WorkspaceData,
        *,
        before_snapshot: WorkspaceSnapshot | None = None,
    ) -> Iterator[GroupedHistoryResult]:
        result = GroupedHistoryResult()
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            yield result
            return
        initial_snapshot = (
            before_snapshot
            if before_snapshot is not None
            else self.capture_workspace(workspace)
        )
        stack = self._groups.setdefault(normalized_id, [])
        stack.append(
            _OpenGroup(
                action_type=str(action_type).strip() or "grouped-action",
                before=initial_snapshot,
                after=initial_snapshot,
            )
        )
        try:
            yield result
        finally:
            completed = stack.pop()
            completed.after = self.capture_workspace(workspace)
            if stack:
                stack[-1].after = completed.after
            else:
                self._groups.pop(normalized_id, None)
                result.entry = self._commit(
                    normalized_id,
                    completed.action_type,
                    completed.before,
                    completed.after,
                )

    def record_action(
        self,
        workspace_id: str,
        action_type: str,
        before_snapshot: WorkspaceSnapshot,
        workspace_after: WorkspaceData,
    ) -> bool:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return False
        after_snapshot = self.capture_workspace(workspace_after)
        return self._record_with_snapshots(
            normalized_id, action_type, before_snapshot, after_snapshot
        )

    def record_action_from_snapshots(
        self,
        workspace_id: str,
        action_type: str,
        before_snapshot: WorkspaceSnapshot,
        after_snapshot: WorkspaceSnapshot,
    ) -> HistoryEntry | None:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return None
        return self._record_with_snapshots_entry(
            normalized_id, action_type, before_snapshot, after_snapshot
        )

    def undo_workspace(
        self, workspace_id: str, workspace: WorkspaceData
    ) -> HistoryEntry | None:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return None
        undo_stack = self._undo_stacks.get(normalized_id)
        if not undo_stack:
            return None
        entry = undo_stack.pop()
        workspace.restore_snapshot(entry.before)
        self._redo_stacks.setdefault(normalized_id, []).append(entry)
        self._last_applied_entries[normalized_id] = entry
        return entry

    def redo_workspace(
        self, workspace_id: str, workspace: WorkspaceData
    ) -> HistoryEntry | None:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return None
        redo_stack = self._redo_stacks.get(normalized_id)
        if not redo_stack:
            return None
        entry = redo_stack.pop()
        workspace.restore_snapshot(entry.after)
        self._undo_stacks.setdefault(normalized_id, []).append(entry)
        self._last_applied_entries[normalized_id] = entry
        return entry

    def consume_last_applied_entry(self, workspace_id: str) -> HistoryEntry | None:
        normalized_id = str(workspace_id).strip()
        if not normalized_id:
            return None
        return self._last_applied_entries.pop(normalized_id, None)

    def _record_with_snapshots(
        self,
        workspace_id: str,
        action_type: str,
        before_snapshot: WorkspaceSnapshot,
        after_snapshot: WorkspaceSnapshot,
    ) -> bool:
        return (
            self._record_with_snapshots_entry(
                workspace_id, action_type, before_snapshot, after_snapshot
            )
            is not None
        )

    def _record_with_snapshots_entry(
        self,
        workspace_id: str,
        action_type: str,
        before_snapshot: WorkspaceSnapshot,
        after_snapshot: WorkspaceSnapshot,
    ) -> HistoryEntry | None:
        if before_snapshot == after_snapshot:
            return None
        open_groups = self._groups.get(workspace_id)
        if open_groups:
            open_groups[-1].after = after_snapshot
            return HistoryEntry(
                action_type=str(action_type).strip() or "mutation",
                before=before_snapshot,
                after=after_snapshot,
            )
        return self._commit(workspace_id, action_type, before_snapshot, after_snapshot)

    def _commit(
        self,
        workspace_id: str,
        action_type: str,
        before_snapshot: WorkspaceSnapshot,
        after_snapshot: WorkspaceSnapshot,
    ) -> HistoryEntry | None:
        if before_snapshot == after_snapshot:
            return None
        self._last_applied_entries.pop(workspace_id, None)
        entry = HistoryEntry(
            action_type=str(action_type).strip() or "mutation",
            before=before_snapshot,
            after=after_snapshot,
        )
        self._undo_stacks.setdefault(workspace_id, []).append(entry)
        self._redo_stacks[workspace_id] = []
        return entry


def history_entry_title_only_node_id(entry: HistoryEntry | None) -> str | None:
    if entry is None or str(entry.action_type or "").strip() != ACTION_RENAME_NODE:
        return None
    if entry.before.edges != entry.after.edges:
        return None
    if set(entry.before.nodes) != set(entry.after.nodes):
        return None
    changed_node_ids = [
        node_id
        for node_id in entry.before.nodes
        if entry.before.nodes[node_id] != entry.after.nodes[node_id]
    ]
    if len(changed_node_ids) != 1:
        return None
    node_id = changed_node_ids[0]
    before_node = entry.before.nodes[node_id]
    after_node = entry.after.nodes[node_id]
    if before_node.title == after_node.title and before_node.properties.get(
        "title"
    ) == after_node.properties.get("title"):
        return None
    before_normalized = before_node.clone()
    after_normalized = after_node.clone()
    before_normalized.title = ""
    after_normalized.title = ""
    before_normalized.properties = dict(before_normalized.properties)
    after_normalized.properties = dict(after_normalized.properties)
    before_normalized.properties.pop("title", None)
    after_normalized.properties.pop("title", None)
    if before_normalized != after_normalized:
        return None
    return node_id


__all__ = [
    "ACTION_ADD_EDGE",
    "ACTION_ADD_NODE",
    "ACTION_DELETE_SELECTED",
    "ACTION_DUPLICATE_SUBGRAPH",
    "ACTION_EDIT_EDGE_LABEL",
    "ACTION_EDIT_EDGE_STYLE",
    "ACTION_TOGGLE_EDGE_ENABLED",
    "ACTION_EDIT_NODE_PROPERTY",
    "ACTION_EDIT_NODE_STYLE",
    "ACTION_EDIT_PROPERTY",
    "ACTION_EDIT_PORT_LABEL",
    "ACTION_EDIT_PORT_MODIFIERS",
    "ACTION_GROUP_SELECTED_NODES",
    "ACTION_INSERT_DYNAMIC_PORT",
    "ACTION_MOVE_NODE",
    "ACTION_PASTE_SUBGRAPH",
    "ACTION_REMOVE_DYNAMIC_PORT",
    "ACTION_RESIZE_NODE",
    "ACTION_REMOVE_EDGE",
    "ACTION_REMOVE_NODE",
    "ACTION_RENAME_DYNAMIC_PORT",
    "ACTION_RENAME_NODE",
    "ACTION_SET_PRINCIPAL_INPUT",
    "ACTION_TOGGLE_COLLAPSED",
    "ACTION_TOGGLE_SETTINGS_GROUP",
    "ACTION_TOGGLE_NODE_LOCKED",
    "ACTION_TOGGLE_EXPOSED_PORT",
    "ACTION_UNGROUP_SELECTED_SUBNODE",
    "ACTION_WRAP_GROUP",
    "HistoryEntry",
    "GroupedHistoryResult",
    "HistoryExecutionChange",
    "RuntimeGraphHistory",
    "WorkspaceSnapshot",
    "history_entry_title_only_node_id",
    "classify_history_execution_change",
]
