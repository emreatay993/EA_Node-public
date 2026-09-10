# Purpose: Store shell session state, including workspace-scoped execution
#          caches and selected-run projections.
# Map: feature_routes/run_controller_selected_workspace_state
# Tests: tests/test_run_projection_controller.py, tests/test_run_controller_unit.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import NodeSolutionFact


ScopeCameraKey: TypeAlias = tuple[str, str, tuple[str, ...]]
ScopeCameraState: TypeAlias = tuple[float, float, float]
GraphSearchScopeId: TypeAlias = Literal["title", "type", "content", "port"]
SolutionMode: TypeAlias = Literal["auto", "manual"]

GRAPH_SEARCH_SCOPE_IDS: tuple[GraphSearchScopeId, ...] = ("title", "type", "content", "port")


def normalize_graph_search_scope_id(value: object) -> GraphSearchScopeId | None:
    normalized = str(value or "").strip().lower()
    if normalized in GRAPH_SEARCH_SCOPE_IDS:
        return normalized  # type: ignore[return-value]
    return None


def normalize_graph_search_scopes(values: Iterable[object] | None) -> list[GraphSearchScopeId]:
    if values is None:
        return list(GRAPH_SEARCH_SCOPE_IDS)
    seen: set[GraphSearchScopeId] = set()
    for candidate in values:
        scope_id = normalize_graph_search_scope_id(candidate)
        if scope_id is not None:
            seen.add(scope_id)
    if not seen:
        return list(GRAPH_SEARCH_SCOPE_IDS)
    return [scope_id for scope_id in GRAPH_SEARCH_SCOPE_IDS if scope_id in seen]


@dataclass(slots=True)
class ShellProjectSessionState:
    project_path: str = ""
    recent_project_paths: list[str] = field(default_factory=list)
    last_manual_save_ts: float = 0.0
    last_autosave_fingerprint: str = ""
    autosave_recovery_deferred: bool = False


@dataclass(slots=True)
class ShellLibraryFilterState:
    library_query: str = ""
    library_category: str = ""
    library_data_type: str = ""
    library_direction: str = ""


@dataclass(slots=True)
class ShellRunState:
    solution_mode_by_workspace_id: dict[str, SolutionMode] = field(default_factory=dict)
    pending_auto_run_workspace_id: str = ""
    pending_auto_run_target_node_ids: set[str] = field(default_factory=set)
    latest_trigger_inputs_by_workspace_id: dict[str, dict[str, SettledPortResult]] = field(default_factory=dict)
    trigger_publications_by_workspace_id: dict[str, dict[str, SettledPortResult]] = field(default_factory=dict)
    current_trigger_capture_node_ids_by_workspace_id: dict[str, set[str]] = field(default_factory=dict)
    active_run_id: str = ""
    active_run_workspace_id: str = ""
    node_execution_workspace_id: str = ""
    running_node_ids: set[str] = field(default_factory=set)
    completed_node_ids: set[str] = field(default_factory=set)
    empty_node_ids: set[str] = field(default_factory=set)
    failed_node_ids: set[str] = field(default_factory=set)
    blocked_node_ids: set[str] = field(default_factory=set)
    root_errors_by_node_id: dict[str, tuple[RootExecutionError, ...]] = field(default_factory=dict)
    warning_node_ids: set[str] = field(default_factory=set)
    running_node_started_at_epoch_ms_by_node_id: dict[str, float] = field(default_factory=dict)
    cached_node_elapsed_ms_by_workspace_id: dict[str, dict[str, float]] = field(default_factory=dict)
    cached_node_output_records_by_workspace_id: dict[str, dict[str, dict[str, dict[str, Any]]]] = (
        field(default_factory=dict)
    )
    node_output_run_counts_by_workspace_id: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    node_output_cache_sequence: int = 0
    solution_project_id: str = ""
    solution_revision_by_workspace_id: dict[str, int] = field(default_factory=dict)
    node_solution_facts_by_workspace_id: dict[str, dict[str, NodeSolutionFact]] = field(
        default_factory=dict
    )
    runtime_warning_messages_by_workspace_id: dict[str, dict[str, tuple[str, ...]]] = field(
        default_factory=dict
    )
    selected_run_preview_workspace_id: str = ""
    selected_run_preview_target_node_ids: tuple[str, ...] = ()
    selected_run_preview_rows: list[dict[str, Any]] = field(default_factory=list)
    selected_run_preview_node_lookup: dict[str, str] = field(default_factory=dict)
    selected_run_preview_revision: int = 0
    node_execution_revision: int = 0
    engine_state_value: Literal["ready", "running", "paused", "error"] = "ready"
    failed_node_id: str = ""
    failed_workspace_id: str = ""
    failed_node_title: str = ""
    developer_mode_active: bool = False


@dataclass(slots=True)
class GraphSearchState:
    open: bool = False
    query: str = ""
    enabled_scopes: list[GraphSearchScopeId] = field(default_factory=lambda: list(GRAPH_SEARCH_SCOPE_IDS))
    results: list[dict[str, Any]] = field(default_factory=list)
    highlight_index: int = -1


@dataclass(slots=True)
class ConnectionQuickInsertState:
    open: bool = False
    query: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    highlight_index: int = -1
    context: dict[str, Any] | None = None


@dataclass(slots=True)
class ShellWindowSearchScopeState:
    graph_search: GraphSearchState = field(default_factory=GraphSearchState)
    connection_quick_insert: ConnectionQuickInsertState = field(default_factory=ConnectionQuickInsertState)
    graph_hint_message: str = ""
    graphics_minimap_expanded: bool = False
    snap_to_grid_enabled: bool = False
    runtime_scope_camera: dict[ScopeCameraKey, ScopeCameraState] = field(default_factory=dict)


@dataclass(slots=True)
class ShellState:
    project_session: ShellProjectSessionState = field(default_factory=ShellProjectSessionState)
    library_filters: ShellLibraryFilterState = field(default_factory=ShellLibraryFilterState)
    run: ShellRunState = field(default_factory=ShellRunState)
    search_scope: ShellWindowSearchScopeState = field(default_factory=ShellWindowSearchScopeState)
