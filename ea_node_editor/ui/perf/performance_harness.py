# Purpose: Graph performance harness — synthetic/fixture loading, interaction stress,
#          mutation and insertion latency, and display/offscreen regression evidence.
# Map: feature_routes/performance_harness_graph_stress
# Tests: tests/test_track_h_perf_harness.py
# Landmarks: BenchmarkConfig, SyntheticGraphConfig | entry: main(), run_benchmark()
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

_EARLY_QML_HOST_ENV = "EA_NODE_EDITOR_QML_HOST"
_EARLY_QSG_RHI_BACKEND_ENV = "EA_NODE_EDITOR_QSG_RHI_BACKEND"


def _early_cli_option_value(argv: list[str], option: str) -> str:
    prefix = f"{option}="
    for index, item in enumerate(argv):
        if item.startswith(prefix):
            return item[len(prefix) :].strip()
        if item == option and index + 1 < len(argv):
            return argv[index + 1].strip()
    return ""


def _apply_early_qtquick_cli_environment(argv: list[str]) -> None:
    qt_platform = _early_cli_option_value(argv, "--qt-platform")
    qml_host = _early_cli_option_value(argv, "--qml-host")
    qsg_rhi_backend = _early_cli_option_value(argv, "--qsg-rhi-backend")
    if qt_platform:
        os.environ["QT_QPA_PLATFORM"] = qt_platform
    if qml_host:
        os.environ[_EARLY_QML_HOST_ENV] = qml_host
    if qsg_rhi_backend:
        os.environ[_EARLY_QSG_RHI_BACKEND_ENV] = qsg_rhi_backend
    if "--capture-qsg-info" in argv:
        os.environ["QSG_INFO"] = "1"


# Force a deterministic non-interactive platform plugin for headless runs.
_apply_early_qtquick_cli_environment(sys.argv[1:])
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QMarginsF,
    QObject,
    QRectF,
    Qt,
    QUrl,
    pyqtProperty,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QImage, QPainter, QPageLayout, QPageSize, QPdfWriter
from PyQt6.QtQuick import QQuickItem, QQuickView
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.hierarchy import scope_parent_id
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.record_payloads import (
    edge_instance_to_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.media_panel import MEDIA_PANEL_TYPE_ID
from ea_node_editor.nodes.file_dialog_filters import media_kind_from_source
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.ui.media_preview_provider import (
    LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
    LocalMediaPreviewImageProvider,
    describe_local_image,
)
from ea_node_editor.ui.pdf_preview_provider import (
    LOCAL_PDF_PREVIEW_PROVIDER_ID,
    LocalPdfPreviewImageProvider,
    describe_pdf_preview,
)
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
from ea_node_editor.ui_qml.qml_host_factory import (
    QML_HOST_ENV,
    QML_HOST_QQUICKVIEW_CONTAINER,
    QML_HOST_QQUICKWIDGET,
    normalize_qml_host_kind,
    select_qml_host_kind_from_environment,
)
from ea_node_editor.ui_qml.qtquick_backend import (
    BACKEND_OVERRIDE_ENV,
    configure_qtquick_backend,
    normalize_qsg_rhi_backend_override,
    qtquick_backend_diagnostics,
    qtquick_environment_snapshot,
)
from ea_node_editor.ui_qml.theme_bridge import ThemeBridge
from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge

_DEFAULT_BENCHMARK_SCENARIO = "synthetic_exec"
_PROJECT_FIXTURE_SCENARIO = "project_fixture"
_STRESS_FIXTURE_SCENARIO = "stress_fixture"
_GRAPH_MUTATIONS_SCENARIO = "graph_mutations"
_NODE_INSERTIONS_SCENARIO = "node_insertions"
_ANIMATED_MEDIA_SCENARIO = "animated_media"
_ACTIVE_DATA_NODE_TYPE = "core.python_script"
_ACTIVE_DATA_SOURCE_PORT = "result"
_ACTIVE_DATA_TARGET_PORT = "payload"
_BENCHMARK_SCENARIOS = (
    _DEFAULT_BENCHMARK_SCENARIO,
    "heavy_media",
    _ANIMATED_MEDIA_SCENARIO,
    _PROJECT_FIXTURE_SCENARIO,
    _STRESS_FIXTURE_SCENARIO,
    _GRAPH_MUTATIONS_SCENARIO,
    _NODE_INSERTIONS_SCENARIO,
)
_NODE_INSERTION_PROFILES = (
    "ordinary_node",
    "group_backdrop",
    "small_custom_workflow",
    "nested_custom_workflow",
)
_NODE_INSERTION_P95_TARGET_MS = 100.0
_NODE_INSERTION_COMPLETION_SEMANTICS = (
    "confirmation/dispatch start until every inserted active-scope primary graphNodeCard delegate "
    "is visible with non-zero bounds and a later QQuickWindow.afterRendering callback completes"
)
_ANIMATED_MEDIA_FIXTURE_RELATIVE_PATHS = {
    "animated_small_gif": Path("tests/fixtures/media/animated-small.gif"),
    "animated_large_gif": Path("tests/fixtures/media/animated-large.gif"),
    "single_frame_gif": Path("tests/fixtures/media/single-frame.gif"),
    "corrupt_gif": Path("tests/fixtures/media/corrupt.gif"),
    "animated_webp": Path("tests/fixtures/media/animated.webp"),
}
_MUTATION_BENCHMARK_SCENARIOS = (
    "rename_node",
    "drag_node_commit",
    "drag_multi_selection_commit",
    "create_edge",
    "remove_edge",
    "delete_node_with_incident_edges",
    "undo_redo",
)
_CREATE_EDGE_MEASUREMENT_LIMITATION = (
    "create_edge measures programmatic production mutation dispatch through the first "
    "rendered frame; it does not measure pointer travel, port hit-testing, or the "
    "pointer gesture used to create an edge."
)
_MUTATION_BENCHMARK_REPORT_FIELD_GROUPS = {
    "identity": (
        "scenario",
        "operation_iteration",
    ),
    "wall_clock_samples": ("mutation_wall_clock_samples_ms",),
    "phase_timings": ("phase_timings_ms",),
    "phase_attribution": (
        "first_frame_phase_attribution_ms",
        "first_frame_phase_attribution_ratio",
        "first_frame_includes_readback",
        "first_frame_completion_semantics",
    ),
    "setup_evidence": (
        "setup_excluded_from_mutation_timing",
        "setup_wall_clock_samples_ms",
        "setup_phase_timings_ms",
        "setup_dirty_node_count",
        "setup_dirty_edge_count",
    ),
    "fixture_metadata": (
        "fixture_checksum_sha256",
        "graph_size",
    ),
    "dirty_counts": (
        "dirty_node_count",
        "dirty_edge_count",
    ),
    "model_delta_counts": (
        "model_delta_dirty_node_count",
        "model_delta_dirty_edge_count",
    ),
    "scene_publication": (
        "scene_publication_dirty_node_count",
        "scene_publication_dirty_edge_count",
        "scene_publication_paths",
    ),
    "mutation_counters": (
        "mutation_counters",
        "mutation_counter_reasons",
    ),
    "payload_sizes": (
        "command_payload_bytes",
        "graph_delta_payload_bytes",
        "scene_payload_bytes",
    ),
    "first_frame_after_mutation": ("first_frame_after_mutation_ms",),
}
_FIRST_FRAME_COMPLETION_SEMANTICS = (
    "first_frame_after_mutation_ms measures the graph mutation timing scope until the harness "
    "observes a non-empty GraphCanvas frame; the current Track H harness includes visible-model "
    "sync, render wait, grabWindow/QQuickWidget readback, and post-readback event drain."
)
_FIRST_FRAME_PHASE_BUCKET_DESCRIPTIONS = {
    "graph_mutation_or_history_apply_ms": (
        "Graph model mutation/history apply leaf timing plus only command-dispatch residual not "
        "covered by payload, publish, visible-model, render, or drain buckets."
    ),
    "python_scene_payload_rebuild_ms": "Python scene payload rebuild time recorded by GraphSceneContext.",
    "python_scene_publish_ms": (
        "Python scene publish signal emission time recorded by GraphSceneContext, exclusive of "
        "nested state-side visible model publication."
    ),
    "visible_model_sync_ms": "State-side visible model publication recorded by the scene state service.",
    "harness_force_exact_refresh_ms": "Harness-forced exact visible-scene refresh before render.",
    "qt_event_drain_ms": "Explicit harness QApplication.processEvents() drains outside frame readback.",
    "render_callback_wait_ms": "Harness render/update wait before the successful frame readback.",
    "readback_grab_ms": "grabWindow() or QQuickWidget.grab() readback elapsed time.",
    "post_readback_event_drain_ms": "Event processing after the successful frame readback.",
    "unattributed_first_frame_ms": "Remaining first-frame time not covered by the explicit phase buckets.",
}
_TARGETED_PROFILING_PHASES = ("pan", "zoom")
_TARGETED_TIMING_SUFFIXES = (
    "visible_model_query_ms",
    "edge_snapshot_build_ms",
    "edge_snapshot_refresh_ms",
    "edge_spatial_index_build_ms",
    "edge_paint_ms",
    "grid_update_ms",
    "grid_paint_ms",
    "overlay_sync_ms",
)
_TARGETED_COUNT_SUFFIXES = (
    "visible_model_query_count",
    "grid_update_count",
    "edge_snapshot_refresh_count",
    "total_node_count",
    "total_edge_count",
    "candidate_edge_count",
    "visible_edge_snapshot_count",
    "skipped_edge_count",
    "geometry_cache_hit_count",
    "geometry_cache_miss_count",
    "edge_spatial_index_query_cache_hit_count",
    "edge_spatial_index_query_cache_miss_count",
    "retained_model_entry_skip_count",
    "flow_label_model_sync_skip_count",
    "visible_node_delegate_count",
    "visible_backdrop_delegate_count",
    "visible_node_card_count",
    "delegate_create_count",
    "delegate_destroy_count",
    "active_node_surface_count",
    "visible_edge_label_count",
    "visible_edge_count",
    "frame_scheduler_requested_redraw_count",
    "frame_scheduler_view_state_redraw_request_count",
    "frame_scheduler_edge_redraw_request_count",
    "frame_scheduler_overlay_redraw_request_count",
    "frame_scheduler_flushed_frame_count",
    "frame_scheduler_coalesced_redraw_request_count",
    "live_drag_offset_update_count",
)
_PROJECT_LOAD_PHASE_KEYS = (
    "project_graph_load_serializer_parse_ms",
    "project_graph_load_migration_ms",
    "project_graph_load_registry_lookup_ms",
    "project_graph_load_project_conversion_ms",
    "project_graph_load_scene_bridge_population_ms",
    "project_graph_load_visible_index_build_ms",
    "project_graph_load_edge_index_build_ms",
    "project_graph_load_first_model_attach_ms",
)
_CANVAS_SETUP_PHASE_KEYS = (
    "canvas_setup_qml_load_ms",
    "canvas_setup_root_binding_ms",
    "canvas_setup_node_model_attach_ms",
    "canvas_setup_edge_model_attach_ms",
    "canvas_setup_initial_visible_model_ms",
    "canvas_setup_initial_edge_snapshot_ms",
    "canvas_setup_initial_edge_spatial_index_build_ms",
    "canvas_setup_grid_minimap_ms",
    "canvas_setup_first_rendered_frame_ms",
)


@dataclass(slots=True, frozen=True)
class SyntheticGraphConfig:
    node_count: int = 1000
    edge_count: int = 5000
    seed: int = 1337


@dataclass(slots=True, frozen=True)
class BenchmarkConfig:
    synthetic_graph: SyntheticGraphConfig = SyntheticGraphConfig()
    load_iterations: int = 5
    interaction_samples: int = 200
    interaction_zoom_min: float = 0.5
    interaction_zoom_max: float = 2.0
    scenario: str = _DEFAULT_BENCHMARK_SCENARIO
    interaction_warmup_samples: int = 3
    project_path: str = ""
    workspace_id: str = ""
    stress_fixture: str = ""
    qml_host: str = ""
    qsg_rhi_backend: str = ""
    node_insertion_samples: int = 40
    node_insertion_warmup_samples: int = 3
    mutation_scenarios: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class _MeasuredInteractionStep:
    elapsed_ms: float
    profiling_snapshot: dict[str, float]
    frame_timestamp_range: tuple[int, int]


@dataclass(slots=True, frozen=True)
class _NodeDragGestureMeasurement:
    first_offset_ms: float
    steady_offset_ms: tuple[float, ...]
    full_gesture_ms: float
    end_clear_ms: float
    membership_freeze_supported: bool
    membership_freeze_count: int | None
    drag_frame_timestamp_range: tuple[int, int]
    clear_frame_timestamp_range: tuple[int, int]


@dataclass(slots=True, frozen=True)
class _SelectedNodeDragGestureMeasurement:
    first_offset_ms: float
    steady_offset_ms: tuple[float, ...]
    full_gesture_ms: float
    end_clear_ms: float
    membership_freeze_supported: bool
    membership_freeze_count: int | None
    membership_size_supported: bool
    membership_size: int | None
    raw_input_count: int | None
    flushed_update_count: int | None
    incident_edge_count: int | None
    render_timings_ms: dict[str, float]
    clear_render_timings_ms: dict[str, float]
    drag_frame_timestamp_range: tuple[int, int]
    clear_frame_timestamp_range: tuple[int, int]


@dataclass(slots=True)
class _ScenarioProject:
    project: ProjectData
    scenario_details: dict[str, Any]
    workspace_id: str | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()
            self.temp_dir = None

    def __enter__(self) -> "_ScenarioProject":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()


@dataclass(slots=True, frozen=True)
class _ProjectGraphLoadBenchmarkSamples:
    phase_samples_ms: dict[str, list[float]]

    @property
    def total_ms(self) -> list[float]:
        return self.phase_samples_ms.get("project_graph_load_ms", [])

    def phase_timings_payload(self) -> dict[str, Any]:
        return _phase_timings_payload(self.phase_samples_ms)


@dataclass(slots=True, frozen=True)
class _InteractionBenchmarkSamples:
    setup_ms: list[float]
    setup_phase_timings_ms: dict[str, list[float]]
    warmup_ms: list[float]
    pan_ms: list[float]
    zoom_ms: list[float]
    node_drag_control_ms: list[float]
    node_drag_first_offset_ms: list[float]
    node_drag_steady_offset_ms: list[float]
    node_drag_full_gesture_ms: list[float]
    node_drag_end_clear_ms: list[float]
    node_drag_membership_freeze_supported: bool
    node_drag_membership_freeze_count: list[int | None]
    frame_interval_ms_without_readback: list[float]
    frame_timestamp_ranges: dict[str, Any]
    supplemental_selected_drag: dict[str, Any]
    targeted_profiling_samples: dict[str, list[float]]
    renderer_diagnostics: dict[str, Any]
    feature_parity: dict[str, Any]
    warmup_samples: int
    scenario: str
    media_surface_count: int

    def combined_ms(self) -> list[float]:
        return [pan + zoom for pan, zoom in zip(self.pan_ms, self.zoom_ms, strict=True)]

    def phase_timings_payload(self) -> dict[str, Any]:
        return {
            "canvas_setup_ms": {
                "samples": self.setup_ms,
                "summary": _metric_summary_ms(self.setup_ms),
            },
            **_phase_timings_payload(self.setup_phase_timings_ms),
            "canvas_warmup_ms": {
                "samples": self.warmup_ms,
                "summary": _metric_summary_ms(self.warmup_ms),
            },
            "pan_interaction_ms": {
                "samples": self.pan_ms,
                "summary": _metric_summary_ms(self.pan_ms),
            },
            "zoom_interaction_ms": {
                "samples": self.zoom_ms,
                "summary": _metric_summary_ms(self.zoom_ms),
            },
            "node_drag_control_ms": {
                "samples": self.node_drag_control_ms,
                "summary": _metric_summary_ms(self.node_drag_control_ms),
            },
            "node_drag_first_offset_ms": {
                "samples": self.node_drag_first_offset_ms,
                "summary": _metric_summary_ms(self.node_drag_first_offset_ms),
            },
            "node_drag_steady_offset_ms": {
                "samples": self.node_drag_steady_offset_ms,
                "summary": _metric_summary_ms(self.node_drag_steady_offset_ms),
            },
            "node_drag_full_gesture_ms": {
                "samples": self.node_drag_full_gesture_ms,
                "summary": _metric_summary_ms(self.node_drag_full_gesture_ms),
            },
            "node_drag_end_clear_ms": {
                "samples": self.node_drag_end_clear_ms,
                "summary": _metric_summary_ms(self.node_drag_end_clear_ms),
            },
            "frame_interval_ms_without_readback": {
                "samples": self.frame_interval_ms_without_readback,
                "summary": _metric_summary_ms(self.frame_interval_ms_without_readback),
            },
            **_targeted_profiling_payload(
                self.targeted_profiling_samples,
                suffixes=_TARGETED_TIMING_SUFFIXES,
            ),
        }

    def targeted_profiling_counts_payload(self) -> dict[str, Any]:
        return _targeted_profiling_payload(
            self.targeted_profiling_samples,
            suffixes=_TARGETED_COUNT_SUFFIXES,
        )

    def benchmark_payload(self) -> dict[str, Any]:
        membership_freeze_verified = (
            all(count == 1 for count in self.node_drag_membership_freeze_count)
            if self.node_drag_membership_freeze_supported
            else None
        )
        return {
            "kind": "graph_canvas_qml",
            "edge_renderer_kind": str(
                self.feature_parity.get("edge_renderer_kind", "")
            ),
            "edge_renderer_requested_kind": str(
                self.feature_parity.get("edge_renderer_requested_kind", "")
            ),
            "edge_renderer_canvas_fallback_active": bool(
                self.feature_parity.get("edge_renderer_canvas_fallback_active", False)
            ),
            "edge_renderer_fallback_reason": str(
                self.feature_parity.get("edge_renderer_fallback_reason", "")
            ),
            "render_path": _graph_canvas_qml_path()
            .relative_to(_repo_root_path())
            .as_posix(),
            "viewport": {
                "width": _CANVAS_BENCHMARK_WIDTH,
                "height": _CANVAS_BENCHMARK_HEIGHT,
            },
            "theme_id": _CANVAS_THEME_ID,
            "graph_theme_id": _CANVAS_GRAPH_THEME_ID,
            "measurement_driver": (
                "Single warmed GraphCanvas host using the configured Qt Quick host selection, "
                "begin/note/finish viewport interaction + "
                "ViewportBridge.centerOn/set_zoom, legacy single-offset drag control, and a "
                f"{_NODE_DRAG_GESTURE_OFFSET_COUNT}-offset GraphNodeHost gesture with "
                "host-appropriate final frame readback"
            ),
            "grab_window_readback_included": True,
            "frame_interval_metric": "frame_interval_ms_without_readback",
            "uses_actual_canvas_render_path": True,
            "steady_state_canvas_host_reused": True,
            "warmup_samples": self.warmup_samples,
            "node_drag_gesture_offset_count": _NODE_DRAG_GESTURE_OFFSET_COUNT,
            "membership_freeze_supported": self.node_drag_membership_freeze_supported,
            "node_drag_membership_freezes_per_gesture": (
                1 if self.node_drag_membership_freeze_supported else None
            ),
            "node_drag_membership_freeze_counts": list(
                self.node_drag_membership_freeze_count
            ),
            "node_drag_membership_freeze_verified": membership_freeze_verified,
            "node_drag_steady_state_gate_metric": "node_drag_steady_offset_ms",
            "node_drag_legacy_continuity_metric": "node_drag_control_ms",
            "frame_timestamp_ranges": self.frame_timestamp_ranges,
            "supplemental_selected_drag_metric": "supplemental_selected_drag",
            "scenario": self.scenario,
            "media_surface_count": self.media_surface_count,
            "animation_activity": self.feature_parity.get("animation_activity", {}),
            "renderer_diagnostics": self.renderer_diagnostics,
            "feature_parity": self.feature_parity,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "setup_ms": self.setup_ms,
            "warmup_ms": self.warmup_ms,
            "pan_ms": self.pan_ms,
            "zoom_ms": self.zoom_ms,
            "combined_ms": self.combined_ms(),
            "node_drag_control_ms": self.node_drag_control_ms,
            "node_drag_first_offset_ms": self.node_drag_first_offset_ms,
            "node_drag_steady_offset_ms": self.node_drag_steady_offset_ms,
            "node_drag_full_gesture_ms": self.node_drag_full_gesture_ms,
            "node_drag_end_clear_ms": self.node_drag_end_clear_ms,
            "membership_freeze_supported": self.node_drag_membership_freeze_supported,
            "node_drag_membership_freeze_count": self.node_drag_membership_freeze_count,
            "frame_interval_ms_without_readback": self.frame_interval_ms_without_readback,
            "supplemental_selected_drag": self.supplemental_selected_drag,
            "phase_timings_ms": self.phase_timings_payload(),
            "profiling_counts": self.targeted_profiling_counts_payload(),
            "benchmark": self.benchmark_payload(),
            "renderer_diagnostics": self.renderer_diagnostics,
            "feature_parity": self.feature_parity,
        }


_BASELINE_VARIANCE_THRESHOLDS = {
    "load_p95_ms": {
        "max_cv": 0.25,
        "max_range_ms": 500.0,
    },
    "pan_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "zoom_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "pan_zoom_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "node_drag_control_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "node_drag_first_offset_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "node_drag_steady_offset_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "node_drag_full_gesture_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 24.0,
    },
    "node_drag_end_clear_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
    "frame_interval_without_readback_p95_ms": {
        "max_cv": 0.20,
        "max_range_ms": 8.0,
    },
}

_CANVAS_BENCHMARK_WIDTH = 1280
_CANVAS_BENCHMARK_HEIGHT = 720
_NODE_DRAG_GESTURE_OFFSET_COUNT = 12
_CANVAS_THEME_ID = "stitch_dark"
_CANVAS_GRAPH_THEME_ID = "graph_stitch_dark"
_PASSIVE_MEDIA_TYPE_PREFIX = "passive.media."
_STRESS_FIXTURE_RELATIVE_PATH = Path("examples") / "stress_1200_nodes.cxproj"
_STRESS_FIXTURE_WORKSPACE_ID = "ws_perf_h"
_STRESS_FIXTURE_MODE_REAL = "real"
_STRESS_FIXTURE_MODES = (_STRESS_FIXTURE_MODE_REAL,)
_STRESS_FIXTURE_PRIOR_CLOSEOUT = {
    "packet": "GRAPH_CANVAS_STRESS_1200 P10",
    "packet_status": "PASS",
    "performance_status": "FAIL",
    "summary": (
        "Prior P10 accepted the packet/default selection but left REQ-PERF-002 "
        "and REQ-PERF-003 failing for stress-1200."
    ),
}


configure_qtquick_backend()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    fraction = rank - lower_index
    return float(lower_value + (upper_value - lower_value) * fraction)


def _metric_summary_ms(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "min": float(min(samples)),
        "max": float(max(samples)),
        "mean": float(statistics.fmean(samples)),
        "p50": _percentile(samples, 50.0),
        "p95": _percentile(samples, 95.0),
    }


def _phase_timings_payload(samples_by_phase: dict[str, list[float]]) -> dict[str, Any]:
    return {
        phase_key: {
            "samples": [float(value) for value in samples],
            "summary": _metric_summary_ms([float(value) for value in samples]),
        }
        for phase_key, samples in samples_by_phase.items()
    }


def _safe_nonnegative_float(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):
        return 0.0
    return max(0.0, numeric)


def _phase_timing_ms(phase_timings: dict[str, Any], phase_key: str) -> float:
    return _safe_nonnegative_float(phase_timings.get(phase_key, 0.0))


def _first_frame_phase_attribution_ms(sample: dict[str, Any]) -> dict[str, float]:
    phase_timings = sample.get("phase_timings_ms", {})
    if not isinstance(phase_timings, dict):
        phase_timings = {}
    first_frame_ms = max(
        _safe_nonnegative_float(sample.get("first_frame_after_mutation_ms", 0.0)),
        _phase_timing_ms(phase_timings, "first_frame_after_mutation_ms"),
    )
    command_dispatch_ms = min(
        _phase_timing_ms(phase_timings, "command_dispatch_ms"), first_frame_ms
    )
    visible_model_ms = _phase_timing_ms(phase_timings, "visible_node_model_update_ms")
    scene_publish_ms = max(
        0.0,
        _phase_timing_ms(phase_timings, "scene_publish_ms") - visible_model_ms,
    )
    buckets = {
        "graph_mutation_or_history_apply_ms": _phase_timing_ms(
            phase_timings, "graph_model_mutation_ms"
        )
        + _phase_timing_ms(phase_timings, "history_apply_ms"),
        "python_scene_payload_rebuild_ms": _phase_timing_ms(
            phase_timings, "payload_rebuild_ms"
        )
        + _phase_timing_ms(phase_timings, "edge_payload_update_ms"),
        "python_scene_publish_ms": scene_publish_ms,
        "visible_model_sync_ms": visible_model_ms,
        "harness_force_exact_refresh_ms": _phase_timing_ms(
            phase_timings,
            "harness_force_exact_refresh_ms",
        ),
        "qt_event_drain_ms": _phase_timing_ms(phase_timings, "qt_event_drain_ms"),
        "render_callback_wait_ms": _phase_timing_ms(
            phase_timings, "render_callback_wait_ms"
        ),
        "readback_grab_ms": _phase_timing_ms(phase_timings, "readback_grab_ms"),
        "post_readback_event_drain_ms": _phase_timing_ms(
            phase_timings, "post_readback_event_drain_ms"
        ),
    }
    command_nested_ms = sum(
        buckets[key]
        for key in (
            "graph_mutation_or_history_apply_ms",
            "python_scene_payload_rebuild_ms",
            "python_scene_publish_ms",
            "visible_model_sync_ms",
        )
    )
    command_dispatch_exclusive_ms = max(0.0, command_dispatch_ms - command_nested_ms)
    buckets["graph_mutation_or_history_apply_ms"] += command_dispatch_exclusive_ms
    attributed_ms = sum(buckets.values())
    buckets["unattributed_first_frame_ms"] = max(0.0, first_frame_ms - attributed_ms)
    return {key: float(value) for key, value in buckets.items()}


def _first_frame_phase_attribution_ratio(
    attribution_ms: dict[str, float],
    first_frame_ms: float,
) -> dict[str, float]:
    if first_frame_ms <= 0.0:
        return {key: 0.0 for key in attribution_ms}
    return {
        key: min(1.0, max(0.0, float(value) / first_frame_ms))
        for key, value in attribution_ms.items()
    }


def _annotate_graph_mutation_phase_attribution(
    sample: dict[str, Any],
) -> dict[str, Any]:
    first_frame_ms = _safe_nonnegative_float(
        sample.get("first_frame_after_mutation_ms", 0.0)
    )
    attribution_ms = _first_frame_phase_attribution_ms(sample)
    sample["first_frame_phase_attribution_ms"] = attribution_ms
    sample["first_frame_phase_attribution_ratio"] = (
        _first_frame_phase_attribution_ratio(
            attribution_ms,
            first_frame_ms,
        )
    )
    sample["first_frame_includes_readback"] = True
    sample["first_frame_completion_semantics"] = _FIRST_FRAME_COMPLETION_SEMANTICS
    return sample


def _targeted_profiling_metric_key(phase: str, suffix: str) -> str:
    return f"{phase}_{suffix}"


def _targeted_profiling_payload(
    samples_by_metric: dict[str, list[float]],
    *,
    suffixes: tuple[str, ...],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for phase in _TARGETED_PROFILING_PHASES:
        for suffix in suffixes:
            metric_key = _targeted_profiling_metric_key(phase, suffix)
            metric_samples = [
                float(value) for value in samples_by_metric.get(metric_key, [])
            ]
            payload[metric_key] = {
                "samples": metric_samples,
                "summary": _metric_summary_ms(metric_samples),
            }
    return payload


def _initialize_targeted_profiling_samples() -> dict[str, list[float]]:
    metric_keys = tuple(
        _targeted_profiling_metric_key(phase, suffix)
        for phase in _TARGETED_PROFILING_PHASES
        for suffix in (*_TARGETED_TIMING_SUFFIXES, *_TARGETED_COUNT_SUFFIXES)
    )
    return {metric_key: [] for metric_key in metric_keys}


def _append_targeted_profiling_sample(
    targeted_samples: dict[str, list[float]],
    *,
    phase: str,
    snapshot: dict[str, float],
) -> None:
    for suffix, value in snapshot.items():
        metric_key = _targeted_profiling_metric_key(phase, suffix)
        if metric_key not in targeted_samples:
            targeted_samples[metric_key] = []
        targeted_samples[metric_key].append(float(value))


def _stress_1200_metric_entry(
    source: dict[str, Any],
    metric_key: str,
    *,
    label: str,
    group: str,
    unit: str,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    entry = source.get(metric_key, {})
    samples = [float(value) for value in entry.get("samples", [])]
    if not samples:
        return {
            "group": group,
            "label": label,
            "metric_key": metric_key,
            "stat": "p95",
            "unit": unit,
            "value": None,
            "sample_count": 0,
            "available": False,
            "unavailable_reason": unavailable_reason
            or f"No samples captured for {metric_key}.",
        }

    summary = entry.get("summary", {})
    normalized_summary = {
        key: float(summary.get(key, 0.0))
        for key in ("min", "max", "mean", "p50", "p95")
    }
    return {
        "group": group,
        "label": label,
        "metric_key": metric_key,
        "stat": "p95",
        "unit": unit,
        "value": normalized_summary["p95"],
        "summary": normalized_summary,
        "sample_count": len(samples),
        "available": True,
        "unavailable_reason": "",
    }


def _stress_1200_bottleneck_breakdown(
    *,
    phase_timings_ms: dict[str, Any],
    profiling_counts: dict[str, Any],
    renderer_diagnostics: dict[str, Any],
    interaction_benchmark: dict[str, Any],
) -> dict[str, Any]:
    timing_specs = (
        (
            "bridge_model_copying",
            "pan_visible_model_query_ms",
            "Pan visible-model query",
            "ms",
        ),
        (
            "bridge_model_copying",
            "zoom_visible_model_query_ms",
            "Zoom visible-model query",
            "ms",
        ),
        (
            "edge_snapshot_work",
            "pan_edge_snapshot_build_ms",
            "Pan edge snapshot build",
            "ms",
        ),
        (
            "edge_snapshot_work",
            "zoom_edge_snapshot_build_ms",
            "Zoom edge snapshot build",
            "ms",
        ),
        (
            "edge_snapshot_work",
            "pan_edge_snapshot_refresh_ms",
            "Pan edge snapshot refresh",
            "ms",
        ),
        (
            "edge_snapshot_work",
            "zoom_edge_snapshot_refresh_ms",
            "Zoom edge snapshot refresh",
            "ms",
        ),
        ("edge_snapshot_work", "pan_edge_paint_ms", "Pan edge paint", "ms"),
        ("edge_snapshot_work", "zoom_edge_paint_ms", "Zoom edge paint", "ms"),
        ("canvas_grid_work", "pan_grid_update_ms", "Pan grid update", "ms"),
        ("canvas_grid_work", "zoom_grid_update_ms", "Zoom grid update", "ms"),
        ("canvas_grid_work", "pan_grid_paint_ms", "Pan grid paint", "ms"),
        ("canvas_grid_work", "zoom_grid_paint_ms", "Zoom grid paint", "ms"),
        ("overlay_sync", "pan_overlay_sync_ms", "Pan overlay sync", "ms"),
        ("overlay_sync", "zoom_overlay_sync_ms", "Zoom overlay sync", "ms"),
        (
            "host_composition_backend",
            "frame_interval_ms_without_readback",
            "Frame interval without readback",
            "ms",
        ),
    )
    count_specs = (
        (
            "bridge_model_copying",
            "pan_visible_model_query_count",
            "Pan visible-model queries",
            "count",
        ),
        (
            "bridge_model_copying",
            "zoom_visible_model_query_count",
            "Zoom visible-model queries",
            "count",
        ),
        (
            "qml_delegate_churn",
            "pan_delegate_create_count",
            "Pan delegate creates",
            "count",
        ),
        (
            "qml_delegate_churn",
            "zoom_delegate_create_count",
            "Zoom delegate creates",
            "count",
        ),
        (
            "qml_delegate_churn",
            "pan_delegate_destroy_count",
            "Pan delegate destroys",
            "count",
        ),
        (
            "qml_delegate_churn",
            "zoom_delegate_destroy_count",
            "Zoom delegate destroys",
            "count",
        ),
        (
            "qml_delegate_churn",
            "pan_visible_node_delegate_count",
            "Pan visible node delegates",
            "count",
        ),
        (
            "qml_delegate_churn",
            "zoom_visible_node_delegate_count",
            "Zoom visible node delegates",
            "count",
        ),
        (
            "edge_snapshot_work",
            "pan_edge_snapshot_refresh_count",
            "Pan edge snapshot refreshes",
            "count",
        ),
        (
            "edge_snapshot_work",
            "zoom_edge_snapshot_refresh_count",
            "Zoom edge snapshot refreshes",
            "count",
        ),
        (
            "edge_snapshot_work",
            "pan_visible_edge_snapshot_count",
            "Pan visible edge snapshots",
            "count",
        ),
        (
            "edge_snapshot_work",
            "zoom_visible_edge_snapshot_count",
            "Zoom visible edge snapshots",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_frame_scheduler_view_state_redraw_request_count",
            "Pan view redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_frame_scheduler_view_state_redraw_request_count",
            "Zoom view redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_frame_scheduler_edge_redraw_request_count",
            "Pan edge redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_frame_scheduler_edge_redraw_request_count",
            "Zoom edge redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_frame_scheduler_overlay_redraw_request_count",
            "Pan overlay redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_frame_scheduler_overlay_redraw_request_count",
            "Zoom overlay redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_frame_scheduler_flushed_frame_count",
            "Pan flushed frames",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_frame_scheduler_flushed_frame_count",
            "Zoom flushed frames",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_frame_scheduler_coalesced_redraw_request_count",
            "Pan coalesced redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_frame_scheduler_coalesced_redraw_request_count",
            "Zoom coalesced redraw requests",
            "count",
        ),
        (
            "input_redraw_churn",
            "pan_live_drag_offset_update_count",
            "Pan live-drag offset updates",
            "count",
        ),
        (
            "input_redraw_churn",
            "zoom_live_drag_offset_update_count",
            "Zoom live-drag offset updates",
            "count",
        ),
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    timing_entries: list[dict[str, Any]] = []
    for group, metric_key, label, unit in timing_specs:
        entry = _stress_1200_metric_entry(
            phase_timings_ms,
            metric_key,
            label=label,
            group=group,
            unit=unit,
        )
        grouped.setdefault(group, []).append(entry)
        if entry["available"]:
            timing_entries.append(entry)

    for group, metric_key, label, unit in count_specs:
        grouped.setdefault(group, []).append(
            _stress_1200_metric_entry(
                profiling_counts,
                metric_key,
                label=label,
                group=group,
                unit=unit,
            )
        )

    next_bottleneck = None
    if timing_entries:
        next_bottleneck = max(
            timing_entries, key=lambda item: float(item.get("value") or 0.0)
        )

    return {
        "section_name": "Stress 1200 Bottleneck Breakdown",
        "backend_state": {
            "graphics_api": str(renderer_diagnostics.get("graphics_api", "")),
            "graphics_api_label": str(
                renderer_diagnostics.get("graphics_api_label", "")
            ),
            "qml_host_kind": str(renderer_diagnostics.get("qml_host_kind", "")),
            "qml_host_env": str(renderer_diagnostics.get("qml_host_env", "")),
            "qml_host_kind_selected": str(
                renderer_diagnostics.get("qml_host_kind_selected", "")
            ),
            "qt_qpa_platform": str(renderer_diagnostics.get("qt_qpa_platform", "")),
            "qsg_rhi_backend": str(renderer_diagnostics.get("qsg_rhi_backend", "")),
            "qsg_rhi_backend_override": str(
                renderer_diagnostics.get("qsg_rhi_backend_override", "")
            ),
            "qtquick_backend_selected": str(
                renderer_diagnostics.get("qtquick_backend_selected", "")
            ),
            "qtquick_backend_selection_reason": str(
                renderer_diagnostics.get("qtquick_backend_selection_reason", "")
            ),
            "qsg_render_loop": str(renderer_diagnostics.get("qsg_render_loop", "")),
            "grab_window_readback_included": bool(
                interaction_benchmark.get("grab_window_readback_included", False)
            ),
        },
        "groups": [
            {"name": name, "metrics": metrics} for name, metrics in grouped.items()
        ],
        "next_measured_bottleneck": (
            {
                "group": str(next_bottleneck["group"]),
                "metric_key": str(next_bottleneck["metric_key"]),
                "label": str(next_bottleneck["label"]),
                "value": float(next_bottleneck["value"]),
                "unit": str(next_bottleneck["unit"]),
                "stat": str(next_bottleneck["stat"]),
            }
            if next_bottleneck
            else {
                "available": False,
                "unavailable_reason": "No timing samples captured for bottleneck routing.",
            }
        ),
    }


def _coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0.0:
        return 0.0
    return float(statistics.pstdev(values) / mean)


def _series_variance_eval(
    values: list[float], threshold: dict[str, float], *, enough_runs: bool
) -> dict[str, Any]:
    cv = _coefficient_of_variation(values)
    value_range = max(values) - min(values) if values else 0.0
    passed = (
        (cv <= threshold["max_cv"] and value_range <= threshold["max_range_ms"])
        if enough_runs
        else True
    )
    return {
        "pass": passed,
        "cv": cv,
        "range_ms": value_range,
        "requires_min_runs": 2,
        "details": (
            f"cv={cv:.4f} (<= {threshold['max_cv']:.2f}), "
            f"range={value_range:.3f} ms (<= {threshold['max_range_ms']:.1f} ms)"
        ),
    }


def _resolve_baseline_mode(requested_mode: str, qt_qpa_platform: str) -> str:
    mode = requested_mode.strip().lower()
    if mode in {"interactive", "offscreen"}:
        return mode
    if mode != "auto":
        return "offscreen"
    normalized_platform = qt_qpa_platform.strip().lower()
    if normalized_platform in {"", "offscreen"}:
        return "offscreen"
    return "interactive"


def _normalize_benchmark_scenario(
    value: Any, default: str = _DEFAULT_BENCHMARK_SCENARIO
) -> str:
    normalized = str(value).strip().lower()
    if normalized in _BENCHMARK_SCENARIOS:
        return normalized
    resolved_default = str(default).strip().lower()
    if resolved_default in _BENCHMARK_SCENARIOS:
        return resolved_default
    return _DEFAULT_BENCHMARK_SCENARIO


def _resolve_mutation_benchmark_scenarios(values: Any) -> tuple[str, ...]:
    if not values:
        return _MUTATION_BENCHMARK_SCENARIOS
    if isinstance(values, str):
        values = (values,)
    requested = {str(value).strip() for value in values if str(value).strip()}
    unknown = requested.difference(_MUTATION_BENCHMARK_SCENARIOS)
    if unknown:
        raise ValueError(
            "Unknown mutation scenarios: " + ", ".join(sorted(unknown))
        )
    return tuple(
        scenario
        for scenario in _MUTATION_BENCHMARK_SCENARIOS
        if scenario in requested
    )


def _mutation_benchmark_contract_payload() -> dict[str, Any]:
    field_groups = {
        group_name: list(field_names)
        for group_name, field_names in _MUTATION_BENCHMARK_REPORT_FIELD_GROUPS.items()
    }
    return {
        "kind": "graph_canvas_mutation_latency",
        "status": "contract_only",
        "threshold_policy": "baseline_evidence_only_no_pass_fail_thresholds",
        "scenarios": list(_MUTATION_BENCHMARK_SCENARIOS),
        "report_field_groups": field_groups,
        "required_report_fields": [
            field_name
            for field_names in field_groups.values()
            for field_name in field_names
        ],
        "units": {
            "mutation_wall_clock_samples_ms": "ms",
            "phase_timings_ms": "ms",
            "first_frame_phase_attribution_ms": "ms",
            "first_frame_phase_attribution_ratio": "ratio",
            "first_frame_includes_readback": "bool",
            "first_frame_completion_semantics": "text",
            "setup_wall_clock_samples_ms": "ms",
            "setup_phase_timings_ms": "ms",
            "first_frame_after_mutation_ms": "ms",
            "command_payload_bytes": "bytes",
            "graph_delta_payload_bytes": "bytes",
            "scene_payload_bytes": "bytes",
            "dirty_node_count": "count",
            "dirty_edge_count": "count",
            "model_delta_dirty_node_count": "count",
            "model_delta_dirty_edge_count": "count",
            "scene_publication_dirty_node_count": "count",
            "scene_publication_dirty_edge_count": "count",
            "scene_publication_paths": "labels",
            "setup_dirty_node_count": "count",
            "setup_dirty_edge_count": "count",
        },
    }


def _mutation_phase_instrumentation_payload() -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    registry = build_default_registry()
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    scene = GraphSceneBridge()
    state_bridge = GraphCanvasStateBridge(scene_bridge=scene)
    scene.set_workspace(model, registry, workspace_id)
    source_id = scene.add_node_from_type(_ACTIVE_DATA_NODE_TYPE, 0.0, 0.0)
    target_id = scene.add_node_from_type(_ACTIVE_DATA_NODE_TYPE, 240.0, 80.0)
    scene.add_edge(
        source_id,
        _ACTIVE_DATA_SOURCE_PORT,
        target_id,
        _ACTIVE_DATA_TARGET_PORT,
    )
    scene.bind_runtime_history(RuntimeGraphHistory())
    app.processEvents()

    command_payload = {"node_id": target_id, "title": "Logger Renamed"}
    scene.clear_mutation_timing_samples()
    scene.set_mutation_timing_enabled(True)
    try:
        with scene.mutation_timing_scope(
            "rename_node", command_payload=command_payload
        ):
            scene.set_node_title(target_id, "Logger Renamed")
            visible_before = _active_mutation_phase_ms(
                scene, "visible_node_model_update_ms"
            )
            refresh_started = time.perf_counter()
            state_bridge.force_visible_scene_models_exact()
            refresh_wall_ms = (time.perf_counter() - refresh_started) * 1000.0
            visible_after = _active_mutation_phase_ms(
                scene, "visible_node_model_update_ms"
            )
            scene.record_mutation_timing_phase(
                "harness_force_exact_refresh_ms",
                max(0.0, refresh_wall_ms - max(0.0, visible_after - visible_before)),
            )
            visible_before = visible_after
            drain_started = time.perf_counter()
            app.processEvents()
            drain_wall_ms = (time.perf_counter() - drain_started) * 1000.0
            visible_after = _active_mutation_phase_ms(
                scene, "visible_node_model_update_ms"
            )
            scene.record_mutation_timing_phase(
                "qt_event_drain_ms",
                max(0.0, drain_wall_ms - max(0.0, visible_after - visible_before)),
            )
    finally:
        scene.set_mutation_timing_enabled(False)

    samples = [
        _annotate_graph_mutation_phase_attribution(
            {
                **sample,
                **_empty_graph_mutation_setup_evidence(),
            }
        )
        for sample in scene.mutation_timing_samples()
    ]
    scene.deleteLater()
    state_bridge.deleteLater()
    return {
        "kind": "graph_canvas_mutation_latency",
        "status": "instrumentation_hooks_available",
        "threshold_policy": "baseline_evidence_only_no_pass_fail_thresholds",
        "scenarios": list(_MUTATION_BENCHMARK_SCENARIOS),
        "samples": samples,
        "sample_count": len(samples),
        "phase_keys": list(samples[0]["phase_timings_ms"]) if samples else [],
    }


def _record_canvas_refresh_phase_timings(
    canvas_host: "_GraphCanvasBenchmarkHost",
    phase_timings_ms: dict[str, float],
) -> None:
    recorder = getattr(canvas_host.scene, "record_mutation_timing_phase", None)
    if not callable(recorder):
        return
    for phase_key, elapsed_ms in phase_timings_ms.items():
        recorder(phase_key, elapsed_ms)


def _active_mutation_phase_ms(scene: GraphSceneBridge, phase_key: str) -> float:
    record = getattr(scene, "_active_mutation_timing_record", None)
    if not isinstance(record, dict):
        return 0.0
    phase_timings = record.get("phase_timings_ms", {})
    if not isinstance(phase_timings, dict):
        return 0.0
    return _phase_timing_ms(phase_timings, phase_key)


def _refresh_graph_mutation_canvas(
    canvas_host: "_GraphCanvasBenchmarkHost",
) -> dict[str, float]:
    phase_timings_ms = {
        "harness_force_exact_refresh_ms": 0.0,
        "qt_event_drain_ms": 0.0,
        "render_callback_wait_ms": 0.0,
        "readback_grab_ms": 0.0,
        "post_readback_event_drain_ms": 0.0,
    }
    force_exact = getattr(
        canvas_host.canvas_state_bridge, "force_visible_scene_models_exact", None
    )
    visible_before = _active_mutation_phase_ms(
        canvas_host.scene,
        "visible_node_model_update_ms",
    )
    refresh_started = time.perf_counter()
    if callable(force_exact):
        force_exact()
    refresh_wall_ms = (time.perf_counter() - refresh_started) * 1000.0
    visible_after = _active_mutation_phase_ms(
        canvas_host.scene,
        "visible_node_model_update_ms",
    )
    phase_timings_ms["harness_force_exact_refresh_ms"] = max(
        0.0,
        refresh_wall_ms - max(0.0, visible_after - visible_before),
    )
    visible_before = visible_after
    drain_started = time.perf_counter()
    canvas_host.app.processEvents()
    drain_wall_ms = (time.perf_counter() - drain_started) * 1000.0
    visible_after = _active_mutation_phase_ms(
        canvas_host.scene,
        "visible_node_model_update_ms",
    )
    phase_timings_ms["qt_event_drain_ms"] += max(
        0.0,
        drain_wall_ms - max(0.0, visible_after - visible_before),
    )
    try:
        render_timings = canvas_host.render_frame(capture_timings=True) or {}
    except TypeError:
        canvas_host.render_frame()
        render_timings = {}
    for phase_key in (
        "render_callback_wait_ms",
        "readback_grab_ms",
        "post_readback_event_drain_ms",
    ):
        phase_timings_ms[phase_key] += _safe_nonnegative_float(
            render_timings.get(phase_key, 0.0)
        )
    visible_before = _active_mutation_phase_ms(
        canvas_host.scene,
        "visible_node_model_update_ms",
    )
    drain_started = time.perf_counter()
    canvas_host.app.processEvents()
    drain_wall_ms = (time.perf_counter() - drain_started) * 1000.0
    visible_after = _active_mutation_phase_ms(
        canvas_host.scene,
        "visible_node_model_update_ms",
    )
    phase_timings_ms["qt_event_drain_ms"] += max(
        0.0,
        drain_wall_ms - max(0.0, visible_after - visible_before),
    )
    _record_canvas_refresh_phase_timings(canvas_host, phase_timings_ms)
    return phase_timings_ms


def _record_history_entry_model_delta(scene: GraphSceneBridge, entry: Any) -> None:
    before = getattr(entry, "before", None)
    after = getattr(entry, "after", None)
    before_nodes = getattr(before, "nodes", None)
    after_nodes = getattr(after, "nodes", None)
    before_edges = getattr(before, "edges", None)
    after_edges = getattr(after, "edges", None)
    if not isinstance(before_nodes, dict) or not isinstance(after_nodes, dict):
        return
    if not isinstance(before_edges, dict) or not isinstance(after_edges, dict):
        return
    dirty_node_ids = {
        node_id
        for node_id in set(before_nodes) | set(after_nodes)
        if before_nodes.get(node_id) != after_nodes.get(node_id)
    }
    dirty_edge_ids = {
        edge_id
        for edge_id in set(before_edges) | set(after_edges)
        if before_edges.get(edge_id) != after_edges.get(edge_id)
    }
    scene.record_mutation_payload_metrics(
        dirty_node_count=len(dirty_node_ids),
        dirty_edge_count=len(dirty_edge_ids),
        model_delta_dirty_node_count=len(dirty_node_ids),
        model_delta_dirty_edge_count=len(dirty_edge_ids),
        graph_delta_payload={
            "history_action": str(getattr(entry, "action_type", "") or ""),
            "model_delta_dirty_node_ids": sorted(dirty_node_ids),
            "model_delta_dirty_edge_ids": sorted(dirty_edge_ids),
        },
    )


def _capture_graph_mutation_model_delta_state(
    workspace: WorkspaceData,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return copy.deepcopy(dict(workspace.nodes)), copy.deepcopy(dict(workspace.edges))


def _record_graph_mutation_model_delta(
    scene: GraphSceneBridge,
    *,
    before_nodes: dict[str, Any],
    before_edges: dict[str, Any],
    workspace: WorkspaceData,
    operation: str,
) -> None:
    after_nodes = dict(workspace.nodes)
    after_edges = dict(workspace.edges)
    dirty_node_ids = {
        node_id
        for node_id in set(before_nodes) | set(after_nodes)
        if before_nodes.get(node_id) != after_nodes.get(node_id)
    }
    dirty_edge_ids = {
        edge_id
        for edge_id in set(before_edges) | set(after_edges)
        if before_edges.get(edge_id) != after_edges.get(edge_id)
    }
    scene.record_mutation_payload_metrics(
        dirty_node_count=len(dirty_node_ids),
        dirty_edge_count=len(dirty_edge_ids),
        model_delta_dirty_node_count=len(dirty_node_ids),
        model_delta_dirty_edge_count=len(dirty_edge_ids),
        graph_delta_payload={
            "operation": str(operation),
            "model_delta_dirty_node_ids": sorted(dirty_node_ids),
            "model_delta_dirty_edge_ids": sorted(dirty_edge_ids),
        },
    )


def _ordered_workspace_nodes(workspace: WorkspaceData) -> list[NodeInstance]:
    return sorted(
        workspace.nodes.values(),
        key=lambda node: (float(node.x), float(node.y), str(node.node_id)),
    )


def _select_mutation_node_ids(
    workspace: WorkspaceData, *, count: int, offset: int = 0
) -> list[str]:
    nodes = _ordered_workspace_nodes(workspace)
    if not nodes:
        return []
    selected: list[str] = []
    for index in range(max(1, count)):
        node = nodes[(offset + index) % len(nodes)]
        selected.append(str(node.node_id))
    return selected


def _temporary_connection_nodes(
    canvas_host: "_GraphCanvasBenchmarkHost",
    *,
    workspace_id: str,
    sample_index: int,
) -> tuple[str, str]:
    workspace = canvas_host.model.project.workspaces[workspace_id]
    _left, right, top, _bottom = _workspace_bounds(workspace)
    y = top + 120.0 + (float(sample_index) * 90.0)
    source_id = canvas_host.scene.add_node_from_type(
        _ACTIVE_DATA_NODE_TYPE, right + 240.0, y
    )
    target_id = canvas_host.scene.add_node_from_type(
        _ACTIVE_DATA_NODE_TYPE, right + 520.0, y
    )
    if not source_id or not target_id:
        raise RuntimeError(
            "Failed to prepare temporary nodes for graph mutation benchmark"
        )
    _refresh_graph_mutation_canvas(canvas_host)
    return source_id, target_id


def _prepare_temporary_edge(
    canvas_host: "_GraphCanvasBenchmarkHost",
    *,
    workspace_id: str,
    sample_index: int,
) -> tuple[str, str, str]:
    source_id, target_id = _temporary_connection_nodes(
        canvas_host,
        workspace_id=workspace_id,
        sample_index=sample_index,
    )
    edge_id = canvas_host.scene.add_edge(
        source_id,
        _ACTIVE_DATA_SOURCE_PORT,
        target_id,
        _ACTIVE_DATA_TARGET_PORT,
    )
    if not edge_id:
        raise RuntimeError(
            "Failed to prepare a temporary edge for graph mutation benchmark"
        )
    _refresh_graph_mutation_canvas(canvas_host)
    return source_id, target_id, edge_id


def _empty_graph_mutation_setup_evidence() -> dict[str, Any]:
    return {
        "setup_excluded_from_mutation_timing": True,
        "setup_wall_clock_samples_ms": [],
        "setup_phase_timings_ms": {},
        "setup_dirty_node_count": 0,
        "setup_dirty_edge_count": 0,
    }


def _graph_mutation_setup_evidence_from_sample(
    sample: dict[str, Any],
) -> dict[str, Any]:
    evidence = _empty_graph_mutation_setup_evidence()
    evidence["setup_wall_clock_samples_ms"] = [
        float(value) for value in sample.get("mutation_wall_clock_samples_ms", [])
    ]
    evidence["setup_phase_timings_ms"] = {
        str(phase_key): float(elapsed_ms)
        for phase_key, elapsed_ms in sample.get("phase_timings_ms", {}).items()
    }
    evidence["setup_dirty_node_count"] = int(sample.get("dirty_node_count", 0))
    evidence["setup_dirty_edge_count"] = int(sample.get("dirty_edge_count", 0))
    return evidence


def _base_graph_mutation_context(
    *,
    canvas_host: "_GraphCanvasBenchmarkHost",
    workspace_id: str,
    sample_index: int,
) -> dict[str, Any]:
    workspace = canvas_host.model.project.workspaces[workspace_id]
    selected_ids = _select_mutation_node_ids(workspace, count=3, offset=sample_index)
    primary_id = selected_ids[0] if selected_ids else ""
    if not primary_id:
        raise RuntimeError("Graph mutation benchmark requires at least one node")
    return {
        "workspace": workspace,
        "selected_ids": selected_ids,
        "primary_id": primary_id,
    }


def _prepare_graph_mutation_operation(
    *,
    canvas_host: "_GraphCanvasBenchmarkHost",
    workspace_id: str,
    scenario: str,
    sample_index: int,
) -> dict[str, Any]:
    setup_context = _base_graph_mutation_context(
        canvas_host=canvas_host,
        workspace_id=workspace_id,
        sample_index=sample_index,
    )

    if scenario == "create_edge":
        source_id, target_id = _temporary_connection_nodes(
            canvas_host,
            workspace_id=workspace_id,
            sample_index=sample_index,
        )
        setup_context.update({"source_id": source_id, "target_id": target_id})

    if scenario in {"remove_edge", "delete_node_with_incident_edges"}:
        source_id, target_id, edge_id = _prepare_temporary_edge(
            canvas_host,
            workspace_id=workspace_id,
            sample_index=sample_index,
        )
        setup_context.update(
            {"source_id": source_id, "target_id": target_id, "edge_id": edge_id}
        )

    if scenario == "undo_redo":
        title = f"Undo Redo Prep {sample_index}"
        canvas_host.scene.set_node_title(setup_context["primary_id"], title)
        _refresh_graph_mutation_canvas(canvas_host)
        setup_context["prepared_title"] = title

    return setup_context


def _record_graph_mutation_setup(
    *,
    canvas_host: "_GraphCanvasBenchmarkHost",
    workspace_id: str,
    scenario: str,
    sample_index: int,
    fixture_checksum_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if scenario not in {
        "create_edge",
        "remove_edge",
        "delete_node_with_incident_edges",
        "undo_redo",
    }:
        return (
            _prepare_graph_mutation_operation(
                canvas_host=canvas_host,
                workspace_id=workspace_id,
                scenario=scenario,
                sample_index=sample_index,
            ),
            _empty_graph_mutation_setup_evidence(),
        )

    setup_payload = {
        "scenario": scenario,
        "sample_index": sample_index,
        "workspace_id": workspace_id,
        "phase": "setup",
        "excluded_from_mutation_timing": True,
    }
    before_count = len(canvas_host.scene.mutation_timing_samples())
    with canvas_host.scene.mutation_timing_scope(
        f"{scenario}_setup",
        command_payload=setup_payload,
        fixture_checksum_sha256=fixture_checksum_sha256,
    ):
        setup_context = _prepare_graph_mutation_operation(
            canvas_host=canvas_host,
            workspace_id=workspace_id,
            scenario=scenario,
            sample_index=sample_index,
        )
    samples = canvas_host.scene.mutation_timing_samples()
    if len(samples) <= before_count:
        raise RuntimeError(
            f"Graph mutation scenario {scenario!r} did not record setup evidence"
        )
    return setup_context, _graph_mutation_setup_evidence_from_sample(samples[-1])


def _run_graph_mutation_operation(
    *,
    canvas_host: "_GraphCanvasBenchmarkHost",
    history: RuntimeGraphHistory,
    workspace_id: str,
    scenario: str,
    sample_index: int,
    setup_context: dict[str, Any],
) -> dict[str, Any]:
    workspace = setup_context["workspace"]
    selected_ids = list(setup_context["selected_ids"])
    primary_id = str(setup_context["primary_id"])

    if scenario == "rename_node":
        title = f"Mutation Baseline {sample_index}"
        canvas_host.scene.set_node_title(primary_id, title)
        return {"node_id": primary_id, "title": title}

    if scenario == "drag_node_commit":
        node = workspace.nodes[primary_id]
        x = float(node.x) + 12.0 + (sample_index % 3)
        y = float(node.y) + 8.0 + (sample_index % 2)
        canvas_host.scene.move_node(primary_id, x, y)
        return {"node_id": primary_id, "x": x, "y": y}

    if scenario == "drag_multi_selection_commit":
        moved = canvas_host.scene.move_nodes_by_delta(selected_ids, 10.0, 6.0)
        return {"node_ids": selected_ids, "dx": 10.0, "dy": 6.0, "moved": moved}

    if scenario == "create_edge":
        source_id = str(setup_context["source_id"])
        target_id = str(setup_context["target_id"])
        edge_id = canvas_host.scene.add_edge(
            source_id,
            _ACTIVE_DATA_SOURCE_PORT,
            target_id,
            _ACTIVE_DATA_TARGET_PORT,
        )
        if not edge_id:
            raise RuntimeError("Failed to create an edge for graph mutation benchmark")
        return {
            "source_node_id": source_id,
            "source_port": _ACTIVE_DATA_SOURCE_PORT,
            "target_node_id": target_id,
            "target_port": _ACTIVE_DATA_TARGET_PORT,
            "edge_id": edge_id,
        }

    if scenario == "remove_edge":
        source_id = str(setup_context["source_id"])
        target_id = str(setup_context["target_id"])
        edge_id = str(setup_context["edge_id"])
        canvas_host.scene.remove_edge(edge_id)
        return {
            "source_node_id": source_id,
            "target_node_id": target_id,
            "edge_id": edge_id,
        }

    if scenario == "delete_node_with_incident_edges":
        source_id = str(setup_context["source_id"])
        target_id = str(setup_context["target_id"])
        edge_id = str(setup_context["edge_id"])
        canvas_host.scene.remove_node(target_id)
        return {
            "source_node_id": source_id,
            "deleted_node_id": target_id,
            "incident_edge_id": edge_id,
        }

    if scenario == "undo_redo":
        undo_started = time.perf_counter()
        undone = history.undo_workspace(workspace_id, workspace)
        canvas_host.scene.record_mutation_timing_phase(
            "history_apply_ms",
            (time.perf_counter() - undo_started) * 1000.0,
        )
        _record_history_entry_model_delta(canvas_host.scene, undone)
        canvas_host.scene.refresh_workspace_from_model(workspace_id)
        _refresh_graph_mutation_canvas(canvas_host)
        redo_started = time.perf_counter()
        redone = history.redo_workspace(workspace_id, workspace)
        canvas_host.scene.record_mutation_timing_phase(
            "history_apply_ms",
            (time.perf_counter() - redo_started) * 1000.0,
        )
        _record_history_entry_model_delta(canvas_host.scene, redone)
        canvas_host.scene.refresh_workspace_from_model(workspace_id)
        return {
            "node_id": primary_id,
            "prepared_title": str(setup_context.get("prepared_title", "")),
            "undo_applied": undone is not None,
            "redo_applied": redone is not None,
        }

    raise ValueError(f"Unsupported graph mutation scenario: {scenario}")


def _record_graph_mutation_sample(
    *,
    canvas_host: "_GraphCanvasBenchmarkHost",
    history: RuntimeGraphHistory,
    workspace_id: str,
    scenario: str,
    sample_index: int,
    operation_iteration: int,
    fixture_checksum_sha256: str,
) -> dict[str, Any]:
    setup_context, setup_evidence = _record_graph_mutation_setup(
        canvas_host=canvas_host,
        workspace_id=workspace_id,
        scenario=scenario,
        sample_index=sample_index,
        fixture_checksum_sha256=fixture_checksum_sha256,
    )
    command_payload = {
        "scenario": scenario,
        "sample_index": sample_index,
        "operation_iteration": operation_iteration,
        "workspace_id": workspace_id,
        "setup_excluded_from_mutation_timing": True,
    }
    before_count = len(canvas_host.scene.mutation_timing_samples())
    with canvas_host.scene.mutation_timing_scope(
        scenario,
        command_payload=command_payload,
        fixture_checksum_sha256=fixture_checksum_sha256,
    ):
        before_nodes, before_edges = _capture_graph_mutation_model_delta_state(
            setup_context["workspace"]
        )
        operation_payload = _run_graph_mutation_operation(
            canvas_host=canvas_host,
            history=history,
            workspace_id=workspace_id,
            scenario=scenario,
            sample_index=sample_index,
            setup_context=setup_context,
        )
        _record_graph_mutation_model_delta(
            canvas_host.scene,
            before_nodes=before_nodes,
            before_edges=before_edges,
            workspace=setup_context["workspace"],
            operation=scenario,
        )
        canvas_host.scene.record_mutation_payload_metrics(
            graph_delta_payload=operation_payload
        )
        _refresh_graph_mutation_canvas(canvas_host)
    samples = canvas_host.scene.mutation_timing_samples()
    if len(samples) <= before_count:
        raise RuntimeError(
            f"Graph mutation scenario {scenario!r} did not record a timing sample"
        )
    sample = samples[-1]
    sample["operation_iteration"] = operation_iteration
    sample.update(setup_evidence)
    return _annotate_graph_mutation_phase_attribution(sample)


def _accumulate_count_map(target: dict[str, int], source: Any) -> None:
    if not isinstance(source, dict):
        return
    for raw_key, raw_value in source.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        target[key] = int(target.get(key, 0)) + value


def _accumulate_nested_count_map(
    target: dict[str, dict[str, int]], source: Any
) -> None:
    if not isinstance(source, dict):
        return
    for raw_key, raw_reasons in source.items():
        key = str(raw_key or "").strip()
        if not key or not isinstance(raw_reasons, dict):
            continue
        bucket = target.setdefault(key, {})
        _accumulate_count_map(bucket, raw_reasons)


def _graph_mutation_scenario_summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for sample in samples:
        if "first_frame_phase_attribution_ms" not in sample:
            sample = _annotate_graph_mutation_phase_attribution(sample)
        scenario = str(sample.get("scenario", "unspecified"))
        summary = grouped.setdefault(
            scenario,
            {
                "samples": [],
                "mutation_wall_clock_samples_ms": [],
                "first_frame_after_mutation_ms": [],
                "dirty_node_count": [],
                "dirty_edge_count": [],
                "model_delta_dirty_node_count": [],
                "model_delta_dirty_edge_count": [],
                "scene_publication_dirty_node_count": [],
                "scene_publication_dirty_edge_count": [],
                "scene_publication_paths": set(),
                "mutation_counters": {},
                "mutation_counter_reasons": {},
                "setup_wall_clock_samples_ms": [],
                "setup_dirty_node_count": [],
                "setup_dirty_edge_count": [],
                "phase_samples_ms": {},
                "first_frame_phase_attribution_samples_ms": {},
                "first_frame_phase_attribution_ratio_samples": {},
                "first_frame_includes_readback": [],
                "setup_phase_samples_ms": {},
            },
        )
        summary["samples"].append(sample)
        summary["mutation_wall_clock_samples_ms"].extend(
            float(value) for value in sample.get("mutation_wall_clock_samples_ms", [])
        )
        summary["first_frame_after_mutation_ms"].append(
            float(sample.get("first_frame_after_mutation_ms", 0.0))
        )
        summary["dirty_node_count"].append(float(sample.get("dirty_node_count", 0)))
        summary["dirty_edge_count"].append(float(sample.get("dirty_edge_count", 0)))
        summary["model_delta_dirty_node_count"].append(
            float(
                sample.get(
                    "model_delta_dirty_node_count", sample.get("dirty_node_count", 0)
                )
            )
        )
        summary["model_delta_dirty_edge_count"].append(
            float(
                sample.get(
                    "model_delta_dirty_edge_count", sample.get("dirty_edge_count", 0)
                )
            )
        )
        summary["scene_publication_dirty_node_count"].append(
            float(
                sample.get(
                    "scene_publication_dirty_node_count",
                    sample.get("dirty_node_count", 0),
                )
            )
        )
        summary["scene_publication_dirty_edge_count"].append(
            float(
                sample.get(
                    "scene_publication_dirty_edge_count",
                    sample.get("dirty_edge_count", 0),
                )
            )
        )
        for publication_path in sample.get("scene_publication_paths", []):
            normalized_path = str(publication_path or "").strip()
            if normalized_path:
                summary["scene_publication_paths"].add(normalized_path)
        _accumulate_count_map(
            summary["mutation_counters"], sample.get("mutation_counters", {})
        )
        _accumulate_nested_count_map(
            summary["mutation_counter_reasons"],
            sample.get("mutation_counter_reasons", {}),
        )
        summary["setup_wall_clock_samples_ms"].extend(
            float(value) for value in sample.get("setup_wall_clock_samples_ms", [])
        )
        summary["setup_dirty_node_count"].append(
            float(sample.get("setup_dirty_node_count", 0))
        )
        summary["setup_dirty_edge_count"].append(
            float(sample.get("setup_dirty_edge_count", 0))
        )
        for phase_key, elapsed_ms in sample.get("phase_timings_ms", {}).items():
            summary["phase_samples_ms"].setdefault(str(phase_key), []).append(
                float(elapsed_ms)
            )
        for phase_key, elapsed_ms in sample.get(
            "first_frame_phase_attribution_ms", {}
        ).items():
            summary["first_frame_phase_attribution_samples_ms"].setdefault(
                str(phase_key), []
            ).append(_safe_nonnegative_float(elapsed_ms))
        for phase_key, ratio in sample.get(
            "first_frame_phase_attribution_ratio", {}
        ).items():
            summary["first_frame_phase_attribution_ratio_samples"].setdefault(
                str(phase_key), []
            ).append(min(1.0, _safe_nonnegative_float(ratio)))
        summary["first_frame_includes_readback"].append(
            bool(sample.get("first_frame_includes_readback", False))
        )
        for phase_key, elapsed_ms in sample.get("setup_phase_timings_ms", {}).items():
            summary["setup_phase_samples_ms"].setdefault(str(phase_key), []).append(
                float(elapsed_ms)
            )

    result: dict[str, Any] = {}
    for scenario, summary in grouped.items():
        wall_clock_samples = [
            float(value) for value in summary["mutation_wall_clock_samples_ms"]
        ]
        first_frame_samples = [
            float(value) for value in summary["first_frame_after_mutation_ms"]
        ]
        dirty_node_count_samples = [
            float(value) for value in summary["dirty_node_count"]
        ]
        dirty_edge_count_samples = [
            float(value) for value in summary["dirty_edge_count"]
        ]
        model_dirty_node_count_samples = [
            float(value) for value in summary["model_delta_dirty_node_count"]
        ]
        model_dirty_edge_count_samples = [
            float(value) for value in summary["model_delta_dirty_edge_count"]
        ]
        scene_dirty_node_count_samples = [
            float(value) for value in summary["scene_publication_dirty_node_count"]
        ]
        scene_dirty_edge_count_samples = [
            float(value) for value in summary["scene_publication_dirty_edge_count"]
        ]
        setup_wall_clock_samples = [
            float(value) for value in summary["setup_wall_clock_samples_ms"]
        ]
        setup_dirty_node_count_samples = [
            float(value) for value in summary["setup_dirty_node_count"]
        ]
        setup_dirty_edge_count_samples = [
            float(value) for value in summary["setup_dirty_edge_count"]
        ]
        result[scenario] = {
            "sample_count": len(summary["samples"]),
            "mutation_wall_clock_samples_ms": {
                "samples": wall_clock_samples,
                "summary": _metric_summary_ms(wall_clock_samples),
            },
            "first_frame_after_mutation_ms": {
                "samples": first_frame_samples,
                "summary": _metric_summary_ms(first_frame_samples),
            },
            "dirty_node_count": {
                "samples": dirty_node_count_samples,
                "summary": _metric_summary_ms(dirty_node_count_samples),
            },
            "dirty_edge_count": {
                "samples": dirty_edge_count_samples,
                "summary": _metric_summary_ms(dirty_edge_count_samples),
            },
            "model_delta_dirty_node_count": {
                "samples": model_dirty_node_count_samples,
                "summary": _metric_summary_ms(model_dirty_node_count_samples),
            },
            "model_delta_dirty_edge_count": {
                "samples": model_dirty_edge_count_samples,
                "summary": _metric_summary_ms(model_dirty_edge_count_samples),
            },
            "scene_publication_dirty_node_count": {
                "samples": scene_dirty_node_count_samples,
                "summary": _metric_summary_ms(scene_dirty_node_count_samples),
            },
            "scene_publication_dirty_edge_count": {
                "samples": scene_dirty_edge_count_samples,
                "summary": _metric_summary_ms(scene_dirty_edge_count_samples),
            },
            "scene_publication_paths": sorted(summary["scene_publication_paths"]),
            "mutation_counters": dict(sorted(summary["mutation_counters"].items())),
            "mutation_counter_reasons": {
                counter_name: dict(sorted(reasons.items()))
                for counter_name, reasons in sorted(
                    summary["mutation_counter_reasons"].items()
                )
            },
            "setup_wall_clock_samples_ms": {
                "samples": setup_wall_clock_samples,
                "summary": _metric_summary_ms(setup_wall_clock_samples),
            },
            "setup_dirty_node_count": {
                "samples": setup_dirty_node_count_samples,
                "summary": _metric_summary_ms(setup_dirty_node_count_samples),
            },
            "setup_dirty_edge_count": {
                "samples": setup_dirty_edge_count_samples,
                "summary": _metric_summary_ms(setup_dirty_edge_count_samples),
            },
            "setup_excluded_from_mutation_timing": all(
                bool(sample.get("setup_excluded_from_mutation_timing", False))
                for sample in summary["samples"]
            ),
            "phase_timings_ms": _phase_timings_payload(summary["phase_samples_ms"]),
            "first_frame_phase_attribution_ms": _phase_timings_payload(
                summary["first_frame_phase_attribution_samples_ms"]
            ),
            "first_frame_phase_attribution_ratio": _phase_timings_payload(
                summary["first_frame_phase_attribution_ratio_samples"]
            ),
            "first_frame_includes_readback": all(
                summary["first_frame_includes_readback"]
            ),
            "first_frame_completion_semantics": _FIRST_FRAME_COMPLETION_SEMANTICS,
            "setup_phase_timings_ms": _phase_timings_payload(
                summary["setup_phase_samples_ms"]
            ),
        }
    return result


def _graph_mutation_dirty_blockers(
    scenario_summaries: dict[str, Any],
    *,
    fixture_node_count: int,
    fixture_edge_count: int,
) -> list[dict[str, Any]]:
    node_threshold = (
        max(1.0, float(fixture_node_count) * 0.5) if fixture_node_count > 0 else 1000.0
    )
    edge_threshold = (
        max(1.0, float(fixture_edge_count) * 0.5) if fixture_edge_count > 0 else 1000.0
    )
    blockers: list[dict[str, Any]] = []
    for scenario, summary in scenario_summaries.items():
        scene_dirty_node_summary = summary.get(
            "scene_publication_dirty_node_count"
        ) or summary.get("dirty_node_count", {})
        scene_dirty_edge_summary = summary.get(
            "scene_publication_dirty_edge_count"
        ) or summary.get("dirty_edge_count", {})
        dirty_node_p95 = float(
            scene_dirty_node_summary.get("summary", {}).get("p95", 0.0)
        )
        dirty_edge_p95 = float(
            scene_dirty_edge_summary.get("summary", {}).get("p95", 0.0)
        )
        if dirty_node_p95 < node_threshold and dirty_edge_p95 < edge_threshold:
            continue
        blockers.append(
            {
                "scenario": str(scenario),
                "dirty_node_count_p95": dirty_node_p95,
                "dirty_edge_count_p95": dirty_edge_p95,
                "node_threshold": node_threshold,
                "edge_threshold": edge_threshold,
                "handoff": "P02-P04 structural edge delta packets must reduce isolated mutation dirty publication.",
            }
        )
    return blockers


def benchmark_graph_mutations_ms(
    *,
    doc: dict[str, Any],
    workspace_id: str,
    samples: int,
    fixture_metadata: dict[str, Any],
    scenarios: tuple[str, ...] = (),
) -> dict[str, Any]:
    if samples <= 0:
        raise ValueError("samples must be > 0")
    selected_scenarios = _resolve_mutation_benchmark_scenarios(scenarios)

    app = QApplication.instance() or QApplication([])
    canvas_host: _GraphCanvasBenchmarkHost | None = None
    recorded_samples: list[dict[str, Any]] = []
    fixture_checksum = str(fixture_metadata.get("fixture_checksum_sha256", ""))
    try:
        canvas_host = _GraphCanvasBenchmarkHost(
            app=app,
            doc=doc,
            workspace_id=workspace_id,
        )
        history = RuntimeGraphHistory()
        canvas_host.scene.bind_runtime_history(history)
        canvas_host.scene.clear_mutation_timing_samples()
        canvas_host.scene.set_mutation_timing_enabled(True)
        try:
            for sample_index in range(samples):
                for scenario_index, scenario in enumerate(selected_scenarios, start=1):
                    recorded_samples.append(
                        _record_graph_mutation_sample(
                            canvas_host=canvas_host,
                            history=history,
                            workspace_id=workspace_id,
                            scenario=scenario,
                            sample_index=sample_index,
                            operation_iteration=len(recorded_samples),
                            fixture_checksum_sha256=fixture_checksum,
                        )
                    )
                    if sample_index == samples - 1:
                        print(
                            "progress mutation_scenario="
                            f"{scenario} completed={scenario_index}/{len(selected_scenarios)} "
                            f"samples={samples}",
                            flush=True,
                        )
        finally:
            canvas_host.scene.set_mutation_timing_enabled(False)
    finally:
        if canvas_host is not None:
            canvas_host.close()

    scenario_summaries = _graph_mutation_scenario_summaries(recorded_samples)
    fixture_node_count = int(fixture_metadata.get("node_count", 0) or 0)
    fixture_edge_count = int(fixture_metadata.get("edge_count", 0) or 0)
    return {
        "kind": "graph_canvas_mutation_latency",
        "status": "measured_baseline",
        "threshold_policy": "baseline_evidence_only_no_pass_fail_thresholds",
        "scenario": _GRAPH_MUTATIONS_SCENARIO,
        "render_path": _graph_canvas_qml_path()
        .relative_to(_repo_root_path())
        .as_posix(),
        "uses_actual_canvas_render_path": True,
        "samples_per_scenario": samples,
        "sample_count": len(recorded_samples),
        "scenarios": list(selected_scenarios),
        "fixture_checksum_sha256": fixture_checksum,
        "fixture_graph_size": {
            "nodes": fixture_node_count,
            "edges": fixture_edge_count,
        },
        "first_frame_phase_attribution_schema": {
            "version": 1,
            "first_frame_includes_readback": True,
            "completion_semantics": _FIRST_FRAME_COMPLETION_SEMANTICS,
            "phase_bucket_semantics": dict(_FIRST_FRAME_PHASE_BUCKET_DESCRIPTIONS),
        },
        "samples": recorded_samples,
        "scenario_summaries": scenario_summaries,
        "residual_mutation_dirty_blockers": _graph_mutation_dirty_blockers(
            scenario_summaries,
            fixture_node_count=fixture_node_count,
            fixture_edge_count=fixture_edge_count,
        ),
        "measurement_limitations": (
            [_CREATE_EDGE_MEASUREMENT_LIMITATION]
            if "create_edge" in selected_scenarios
            else []
        ),
    }


def _normalize_stress_fixture_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _STRESS_FIXTURE_MODES:
        return normalized
    return ""


def _fixture_source_requested(config: BenchmarkConfig) -> bool:
    return bool(
        _normalize_stress_fixture_mode(config.stress_fixture)
        or str(config.project_path).strip()
    )


def _default_stress_fixture_path() -> Path:
    return _repo_root_path() / _STRESS_FIXTURE_RELATIVE_PATH


def _resolve_project_path(path_value: str | Path) -> Path:
    raw_path = Path(path_value).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (_repo_root_path() / raw_path).resolve()


def _configured_fixture_project_path(config: BenchmarkConfig) -> Path | None:
    if str(config.project_path).strip():
        return _resolve_project_path(config.project_path)
    if (
        _normalize_stress_fixture_mode(config.stress_fixture)
        == _STRESS_FIXTURE_MODE_REAL
    ):
        return _default_stress_fixture_path()
    return None


def _scenario_label_for_config(config: BenchmarkConfig) -> str:
    scenario = _normalize_benchmark_scenario(config.scenario)
    if scenario in {_GRAPH_MUTATIONS_SCENARIO, _NODE_INSERTIONS_SCENARIO}:
        return scenario
    if _normalize_stress_fixture_mode(config.stress_fixture):
        return _STRESS_FIXTURE_SCENARIO
    if str(config.project_path).strip():
        return _PROJECT_FIXTURE_SCENARIO
    return scenario


def _relative_or_absolute_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_repo_root_path()).as_posix()
    except ValueError:
        return str(path)


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_environment_snapshot() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        **qtquick_environment_snapshot(),
        "cpu_count": os.cpu_count(),
        "hostname": uname.node,
        "system": uname.system,
        "release": uname.release,
        "machine": uname.machine,
        "processor": uname.processor,
    }


def _process_cpu_seconds(process: psutil.Process) -> float:
    cpu_times = process.cpu_times()
    return float(cpu_times.user) + float(cpu_times.system)


def _normalized_qt_platform_name(value: Any) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _is_display_attached_qt_platform(value: Any) -> bool:
    return _normalized_qt_platform_name(value) not in {"", "offscreen", "minimal"}


def _display_diagnostics_payload(
    *,
    renderer_diagnostics: dict[str, Any],
    interaction_benchmark: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    qt_platform = str(
        renderer_diagnostics.get("qt_qpa_platform")
        or environment.get("qt_qpa_platform")
        or ""
    )
    active_graphics_api = str(renderer_diagnostics.get("graphics_api", ""))
    active_graphics_api_label = str(renderer_diagnostics.get("graphics_api_label", ""))
    rhi_backend = str(
        renderer_diagnostics.get("qsg_rhi_backend")
        or renderer_diagnostics.get("qtquick_backend_selected")
        or environment.get("qsg_rhi_backend")
        or environment.get("qtquick_backend_selected")
        or ""
    )
    host_kind = str(
        renderer_diagnostics.get("qml_host_kind")
        or renderer_diagnostics.get("qml_host_kind_selected")
        or environment.get("qml_host_kind_selected")
        or ""
    )
    readback_included = bool(
        interaction_benchmark.get(
            "grab_window_readback_included",
            renderer_diagnostics.get("grab_window_readback_included", False),
        )
    )
    software_fallback_active = bool(
        renderer_diagnostics.get("software_fallback_active", False)
    )
    if not software_fallback_active:
        software_fallback_active = (
            rhi_backend.strip().lower() == "software"
            or active_graphics_api == "Software"
            or active_graphics_api_label == "Software"
            or bool(renderer_diagnostics.get("qtquick_backend_forced_software", False))
        )
    software_fallback_reason = str(
        renderer_diagnostics.get("software_fallback_reason", "")
    )
    if software_fallback_active and not software_fallback_reason:
        software_fallback_reason = str(
            renderer_diagnostics.get(
                "qtquick_backend_selection_reason", "software_backend"
            )
        )
    display_attached = _is_display_attached_qt_platform(qt_platform)
    acceptance_blockers: list[str] = []
    if not display_attached:
        acceptance_blockers.append(
            f"QT_QPA_PLATFORM={qt_platform or '<unset>'} is not display-attached"
        )
    if software_fallback_active:
        acceptance_blockers.append(
            f"Qt Quick software fallback is active ({software_fallback_reason or 'software_backend'})"
        )

    return {
        "qt_platform": qt_platform,
        "display_attached": display_attached,
        "active_graphics_api": active_graphics_api,
        "active_graphics_api_label": active_graphics_api_label,
        "rhi_backend": rhi_backend,
        "render_loop": str(
            renderer_diagnostics.get("qsg_render_loop")
            or environment.get("qsg_render_loop")
            or ""
        ),
        "host_kind": host_kind,
        "qml_host_env": str(
            renderer_diagnostics.get("qml_host_env")
            or environment.get("qml_host_env")
            or ""
        ),
        "screen_device_pixel_ratio": float(
            renderer_diagnostics.get("screen_device_pixel_ratio", 0.0) or 0.0
        ),
        "window_effective_device_pixel_ratio": float(
            renderer_diagnostics.get("window_effective_device_pixel_ratio", 0.0) or 0.0
        ),
        "software_fallback_active": software_fallback_active,
        "software_fallback_reason": software_fallback_reason,
        "readback_included": readback_included,
        "qsg_info_capture_enabled": bool(
            renderer_diagnostics.get(
                "qsg_info_capture_enabled",
                environment.get("qsg_info_capture_enabled", False),
            )
        ),
        "qsg_info": str(
            renderer_diagnostics.get("qsg_info") or environment.get("qsg_info") or ""
        ),
        "acceptance_allowed": display_attached and not software_fallback_active,
        "acceptance_blockers": acceptance_blockers,
    }


def _packet_verification_result_payload(
    display_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    required_keys = (
        "qt_platform",
        "active_graphics_api",
        "rhi_backend",
        "render_loop",
        "host_kind",
        "screen_device_pixel_ratio",
        "window_effective_device_pixel_ratio",
        "software_fallback_active",
        "readback_included",
    )
    missing_keys = [
        key
        for key in required_keys
        if key not in display_diagnostics or display_diagnostics.get(key) is None
    ]
    passed = not missing_keys
    return {
        "status": "PASS" if passed else "FAIL",
        "pass": passed,
        "scope": "packet_verification",
        "details": (
            "Report generated with required display diagnostics; performance acceptance is evaluated separately."
            if passed
            else "Missing required display diagnostics: " + ", ".join(missing_keys)
        ),
        "missing_display_diagnostics": missing_keys,
    }


def _performance_acceptance_result_payload(
    *,
    requirements_eval: dict[str, dict[str, Any]],
    display_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    required_requirement_ids = (
        "GRAPH-CANVAS-ZERO-LOSS",
        "GRAPH-CANVAS-DISPLAY-ACCEPTANCE-SOURCE",
        "GRAPH-CANVAS-DISPLAY-ATTACHED",
        "REQ-PERF-001",
        "REQ-PERF-002",
        "REQ-PERF-003",
    )
    failed_requirements = [
        requirement_id
        for requirement_id in required_requirement_ids
        if not bool(requirements_eval.get(requirement_id, {}).get("pass", False))
    ]
    blockers = list(display_diagnostics.get("acceptance_blockers", []))
    blockers.extend(failed_requirements)
    passed = not blockers
    return {
        "status": "PASS" if passed else "FAIL",
        "pass": passed,
        "scope": "performance_acceptance",
        "details": (
            "Display-attached performance acceptance criteria passed."
            if passed
            else "Performance acceptance blocked by: " + ", ".join(blockers)
        ),
        "blocked_by": blockers,
        "failed_requirements": failed_requirements,
    }


def _apply_config_qtquick_environment(config: BenchmarkConfig) -> None:
    qml_host = str(config.qml_host or "").strip()
    qsg_rhi_backend = str(config.qsg_rhi_backend or "").strip()
    if qml_host:
        os.environ[QML_HOST_ENV] = qml_host
    if qsg_rhi_backend:
        os.environ[BACKEND_OVERRIDE_ENV] = qsg_rhi_backend
    configure_qtquick_backend()


def _frame_intervals_ms_from_timestamps(timestamps: list[float]) -> list[float]:
    return [
        (current - previous) * 1000.0
        for previous, current in zip(timestamps, timestamps[1:])
    ]


def _find_quick_item_by_object_name(
    root: QQuickItem | None, object_name: str
) -> QQuickItem | None:
    for item in _iter_quick_item_tree(root):
        if str(item.objectName() or "") == object_name:
            return item
    return None


def _quick_item_bool_property(
    item: QQuickItem | None, property_name: str, default: bool = False
) -> bool:
    if item is None:
        return default
    value = item.property(property_name)
    if value is None:
        return default
    return bool(value)


def _quick_item_bool_property_any(
    item: QQuickItem | None,
    property_names: tuple[str, ...],
    default: bool = False,
) -> bool:
    if item is None:
        return default
    for property_name in property_names:
        value = item.property(property_name)
        if value is not None:
            return bool(value)
    return default


def _quick_item_source_loaded(item: QQuickItem) -> bool:
    source = item.property("source")
    if isinstance(source, QUrl):
        return not source.isEmpty()
    return bool(str(source or "").strip())


def _animation_activity_snapshot(
    *,
    items: list[QQuickItem],
    media_surfaces: list[QQuickItem],
) -> dict[str, Any]:
    animator_items = [
        item
        for item in items
        if str(item.objectName() or "")
        in {
            "graphNodeMediaAnimatedImage",
            "graphNodeMediaAppliedAnimatedImage",
            "contentFullscreenMediaAnimatedImage",
        }
    ]
    animated_surface_count = 0
    supported_surface_count = 0
    visible_animated_count = 0
    actively_playing_count = 0
    offscreen_paused_count = 0
    idle_paused_count = 0
    offscreen_active_count = 0
    inactive_active_count = 0
    unsupported_active_count = 0
    preview_state_counts: Counter[str] = Counter()

    for surface in media_surfaces:
        preview_state_counts[str(surface.property("previewState") or "unknown")] += 1
        surface_host = surface.property("host")
        host_in_visible_viewport = _quick_item_bool_property_any(
            surface_host,
            ("inVisibleViewport",),
        )
        is_animated = _quick_item_bool_property_any(
            surface,
            ("imageIsAnimated", "isAnimatedMedia", "isAnimated"),
        )
        supported = _quick_item_bool_property_any(
            surface,
            ("imageAnimationSupported", "animationSupported"),
        )
        in_visible_viewport = host_in_visible_viewport
        interaction_active = _quick_item_bool_property_any(
            surface,
            ("animationInteractionActive", "animationActive"),
        )
        playing = _quick_item_bool_property_any(
            surface,
            ("animationPlaying", "animationShouldPlay"),
        )

        animated_surface_count += int(is_animated)
        supported_surface_count += int(supported)
        visible_animated_count += int(supported and in_visible_viewport)
        actively_playing_count += int(playing)
        offscreen_paused_count += int(
            supported and not in_visible_viewport and not playing
        )
        idle_paused_count += int(
            supported and in_visible_viewport and not interaction_active and not playing
        )
        offscreen_active_count += int(playing and not in_visible_viewport)
        inactive_active_count += int(playing and not interaction_active)
        unsupported_active_count += int(playing and not supported)

    policy_violations = {
        "offscreen_active_count": offscreen_active_count,
        "inactive_active_count": inactive_active_count,
        "unsupported_active_count": unsupported_active_count,
    }
    return {
        "surface_count": len(media_surfaces),
        "animated_surface_count": animated_surface_count,
        "supported_surface_count": supported_surface_count,
        "animator_instance_count": len(animator_items),
        "animator_loaded_source_count": sum(
            _quick_item_source_loaded(item) for item in animator_items
        ),
        "visible_animated_count": visible_animated_count,
        "actively_playing_count": actively_playing_count,
        "offscreen_paused_count": offscreen_paused_count,
        "idle_paused_count": idle_paused_count,
        "preview_state_counts": dict(sorted(preview_state_counts.items())),
        "policy_violations": policy_violations,
        "policy_pass": not any(policy_violations.values()),
    }


def _quick_item_float_property(
    item: QQuickItem | None, property_name: str, default: float = 0.0
) -> float:
    if item is None:
        return default
    value = item.property(property_name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int_property(item: QObject | None, property_name: str) -> int | None:
    if item is None:
        return None
    value = item.property(property_name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _qml_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    converter = getattr(value, "toVariant", None)
    resolved = converter() if callable(converter) else value
    if isinstance(resolved, (list, tuple)):
        return list(resolved)
    return None


class _BenchmarkMainWindowBridge(QObject):
    @pyqtProperty(bool, constant=True)
    def graphics_minimap_expanded(self) -> bool:
        return True

    @pyqtProperty(bool, constant=True)
    def graphics_show_grid(self) -> bool:
        return True

    @pyqtProperty(bool, constant=True)
    def graphics_show_minimap(self) -> bool:
        return True

    @pyqtProperty(bool, constant=True)
    def graphics_show_port_labels(self) -> bool:
        return True

    @pyqtProperty(str, constant=True)
    def graphics_edge_crossing_style(self) -> str:
        return "none"

    @pyqtProperty(bool, constant=True)
    def graphics_node_shadow(self) -> bool:
        return True

    @pyqtProperty(bool, constant=True)
    def graphics_notched_ports(self) -> bool:
        return True

    @pyqtProperty(int, constant=True)
    def graphics_shadow_strength(self) -> int:
        return 70

    @pyqtProperty(int, constant=True)
    def graphics_shadow_softness(self) -> int:
        return 50

    @pyqtProperty(int, constant=True)
    def graphics_shadow_offset(self) -> int:
        return 4

    @pyqtProperty(bool, constant=True)
    def snap_to_grid_enabled(self) -> bool:
        return False

    @pyqtProperty(float, constant=True)
    def snap_grid_size(self) -> float:
        return 20.0

    @pyqtSlot(str, "QVariant", result="QVariantMap")
    def describe_pdf_preview(self, source: str, page_number: Any) -> dict[str, Any]:
        return describe_pdf_preview(source, page_number)

    @pyqtSlot(str, result="QVariantMap")
    def describe_image_preview(self, source: str) -> dict[str, Any]:
        return describe_local_image(source)


def _ordered_dataflow_connections(
    *, node_ids: list[str], edge_count: int, seed: int
) -> list[tuple[str, str, str, str]]:
    maximum_edge_count = len(node_ids) * (len(node_ids) - 1) // 2
    if edge_count < 0 or edge_count > maximum_edge_count:
        raise ValueError(
            f"edge_count must be between 0 and {maximum_edge_count} for an acyclic dataflow graph"
        )

    chain_edge_count = min(edge_count, max(0, len(node_ids) - 1))
    node_pairs = [
        (node_ids[index], node_ids[index + 1]) for index in range(chain_edge_count)
    ]
    seen = set(node_pairs)
    generator = random.Random(seed)
    while len(node_pairs) < edge_count:
        source_index, target_index = sorted(generator.sample(range(len(node_ids)), 2))
        pair = (node_ids[source_index], node_ids[target_index])
        if pair in seen:
            continue
        node_pairs.append(pair)
        seen.add(pair)

    return [
        (
            source_id,
            _ACTIVE_DATA_SOURCE_PORT,
            target_id,
            _ACTIVE_DATA_TARGET_PORT,
        )
        for source_id, target_id in node_pairs
    ]


def _add_dataflow_edges(
    workspace: WorkspaceData, connections: list[tuple[str, str, str, str]]
) -> None:
    input_orders: Counter[tuple[str, str]] = Counter()
    for index, (source_id, source_port, target_id, target_port) in enumerate(
        connections
    ):
        input_key = (target_id, target_port)
        edge_id = f"edge_{index:05d}"
        workspace.edges[edge_id] = EdgeInstance(
            edge_id=edge_id,
            source_node_id=source_id,
            source_port_key=source_port,
            target_node_id=target_id,
            target_port_key=target_port,
            enabled=True,
            input_order=input_orders[input_key],
        )
        input_orders[input_key] += 1


def generate_synthetic_project(config: SyntheticGraphConfig) -> ProjectData:
    if config.node_count < 3:
        raise ValueError("node_count must be at least 3")
    if config.edge_count < config.node_count - 1:
        raise ValueError(
            "edge_count must be at least node_count - 1 to keep baseline chain connectivity"
        )

    project = ProjectData(project_id="proj_perf_h", name="track_h_perf")
    workspace_id = "ws_perf_h"
    workspace = WorkspaceData(workspace_id=workspace_id, name="Perf Workspace")
    workspace.views["view_perf_h"] = ViewState(
        view_id="view_perf_h",
        name="V1",
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
    )
    workspace.active_view_id = "view_perf_h"

    node_ids: list[str] = []
    max_cols = 40
    spacing_x = 220.0
    spacing_y = 140.0
    for index in range(config.node_count):
        node_id = f"node_{index:04d}"
        node_ids.append(node_id)

        col = index % max_cols
        row = index // max_cols
        workspace.nodes[node_id] = NodeInstance(
            node_id=node_id,
            type_id=_ACTIVE_DATA_NODE_TYPE,
            title=f"Transform {index + 1}",
            x=col * spacing_x,
            y=row * spacing_y,
            properties={},
            exposed_ports={},
        )

    _add_dataflow_edges(
        workspace,
        _ordered_dataflow_connections(
            node_ids=node_ids,
            edge_count=config.edge_count,
            seed=config.seed,
        ),
    )

    project.workspaces[workspace_id] = workspace
    project.active_workspace_id = workspace_id
    project.metadata["workspace_order"] = [workspace_id]
    return project


def _minimum_active_nodes_for_edge_count(edge_count: int) -> int:
    required = 3
    while required * (required - 1) // 2 < edge_count:
        required += 1
    return required


def _write_fixture_image(
    path: Path,
    *,
    width: int,
    height: int,
    fill: str,
    accent: str,
    label: str,
) -> None:
    image = QImage(
        max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(QColor(fill))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.fillRect(0, 0, image.width(), image.height(), QColor(fill))
    painter.fillRect(
        0,
        int(image.height() * 0.74),
        image.width(),
        int(image.height() * 0.26),
        QColor(accent),
    )
    painter.setPen(QColor("#F4F8FC"))
    font = painter.font()
    font.setPixelSize(max(18, int(min(image.width(), image.height()) * 0.08)))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        QRectF(32.0, 24.0, float(image.width() - 64), float(image.height() - 48)),
        int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
        label,
    )
    painter.end()

    if not image.save(str(path)):
        raise RuntimeError(f"Failed to save fixture image: {path}")


def _write_fixture_pdf(path: Path, *, page_count: int = 3) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        painter.setPen(QColor("#31414F"))
        font = painter.font()
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(72.0, 96.0, 420.0, 64.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            f"Heavy Media Benchmark Page {page_index + 1}",
        )
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QRectF(72.0, 176.0, 420.0, 140.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
            "Generated local PDF fixture reused across passive media nodes for offscreen benchmark runs.",
        )
    painter.end()


def _create_heavy_media_fixtures(temp_dir: Path) -> dict[str, Any]:
    image_specs = (
        ("briefing-board.png", 800, 450, "#234C6D", "#2F89FF", "Site Briefing"),
        ("wiring-overview.png", 640, 480, "#5A3E2B", "#C98339", "Wiring Overview"),
        (
            "inspection-capture.png",
            720,
            540,
            "#3F4F38",
            "#5FB174",
            "Inspection Capture",
        ),
    )
    image_paths: list[Path] = []
    for filename, width, height, fill, accent, label in image_specs:
        image_path = temp_dir / filename
        _write_fixture_image(
            image_path,
            width=width,
            height=height,
            fill=fill,
            accent=accent,
            label=label,
        )
        image_paths.append(image_path)

    pdf_path = temp_dir / "heavy-media-reference.pdf"
    _write_fixture_pdf(pdf_path, page_count=3)

    return {
        "image_paths": image_paths,
        "pdf_path": pdf_path,
        "pdf_page_count": 3,
    }


def _create_animated_media_fixtures(temp_dir: Path) -> dict[str, Path]:
    fixture_paths = {
        role: (_repo_root_path() / relative_path).resolve()
        for role, relative_path in _ANIMATED_MEDIA_FIXTURE_RELATIVE_PATHS.items()
    }
    missing_paths = [
        _relative_or_absolute_path(path)
        for path in fixture_paths.values()
        if not path.is_file()
    ]
    if missing_paths:
        raise FileNotFoundError(
            "animated_media scenario requires committed fixtures: "
            + ", ".join(missing_paths)
        )

    static_path = temp_dir / "static-image.png"
    _write_fixture_image(
        static_path,
        width=800,
        height=450,
        fill="#234C6D",
        accent="#2F89FF",
        label="Static Control",
    )
    fixture_paths["static_png"] = static_path
    return fixture_paths


def _build_node_blueprints(
    *,
    active_data_nodes: int,
    image_nodes: int,
    pdf_nodes: int,
    fixtures: dict[str, Any],
) -> list[dict[str, Any]]:
    blueprints: list[dict[str, Any]] = [
        {
            "type_id": _ACTIVE_DATA_NODE_TYPE,
            "title": "Transform 1",
            "properties": {},
            "active_data": True,
        }
    ]
    active_data_titles = [
        f"Transform {index + 1}" for index in range(1, max(1, active_data_nodes - 1))
    ]
    media_blueprints: list[dict[str, Any]] = []
    image_paths: list[Path] = list(fixtures["image_paths"])
    pdf_path = Path(fixtures["pdf_path"])
    pdf_page_count = int(fixtures["pdf_page_count"])

    for index in range(image_nodes):
        image_path = image_paths[index % len(image_paths)]
        fit_mode = ("contain", "cover", "original")[index % 3]
        media_blueprints.append(
            {
                "type_id": "media.panel",
                "title": f"Media Panel Image {index + 1}",
                "properties": {
                    "source": str(image_path),
                    "fit_mode": fit_mode,
                },
                "exposed_ports": {"source": False},
                "active_data": False,
            }
        )
    for index in range(pdf_nodes):
        media_blueprints.append(
            {
                "type_id": "media.panel",
                "title": f"Media Panel PDF {index + 1}",
                "properties": {
                    "source": str(pdf_path),
                    "page_number": (index % pdf_page_count) + 1,
                },
                "exposed_ports": {"source": False},
                "active_data": False,
            }
        )

    body_active_data_blueprints = [
        {
            "type_id": _ACTIVE_DATA_NODE_TYPE,
            "title": title,
            "properties": {},
            "active_data": True,
        }
        for title in active_data_titles
    ]

    media_index = 0
    active_data_index = 0
    while media_index < len(media_blueprints) or active_data_index < len(
        body_active_data_blueprints
    ):
        if media_index < len(media_blueprints):
            blueprints.append(media_blueprints[media_index])
            media_index += 1
        if active_data_index < len(body_active_data_blueprints):
            blueprints.append(body_active_data_blueprints[active_data_index])
            active_data_index += 1
        if (
            media_index < len(media_blueprints)
            and len(media_blueprints) - media_index
            > len(body_active_data_blueprints) - active_data_index
        ):
            blueprints.append(media_blueprints[media_index])
            media_index += 1

    blueprints.append(
        {
            "type_id": _ACTIVE_DATA_NODE_TYPE,
            "title": f"Transform {active_data_nodes}",
            "properties": {},
            "active_data": True,
        }
    )
    return blueprints


def _build_synthetic_node_blueprints(total_nodes: int) -> list[dict[str, Any]]:
    return [
        {
            "type_id": _ACTIVE_DATA_NODE_TYPE,
            "title": f"Transform {index + 1}",
            "properties": {},
            "active_data": True,
        }
        for index in range(total_nodes)
    ]


def _project_from_blueprints(
    *,
    config: SyntheticGraphConfig,
    node_blueprints: list[dict[str, Any]],
    max_cols: int,
    spacing_x: float,
    spacing_y: float,
) -> tuple[ProjectData, list[str]]:
    project = ProjectData(project_id="proj_perf_h", name="track_h_perf")
    workspace_id = "ws_perf_h"
    workspace = WorkspaceData(workspace_id=workspace_id, name="Perf Workspace")
    workspace.views["view_perf_h"] = ViewState(
        view_id="view_perf_h",
        name="V1",
        zoom=1.0,
        pan_x=0.0,
        pan_y=0.0,
    )
    workspace.active_view_id = "view_perf_h"

    active_data_node_ids: list[str] = []
    for index, blueprint in enumerate(node_blueprints):
        node_id = f"node_{index:04d}"
        col = index % max_cols
        row = index // max_cols
        workspace.nodes[node_id] = NodeInstance(
            node_id=node_id,
            type_id=str(blueprint["type_id"]),
            title=str(blueprint["title"]),
            x=col * spacing_x,
            y=row * spacing_y,
            properties=dict(blueprint.get("properties", {})),
            exposed_ports=dict(blueprint.get("exposed_ports", {})),
        )
        if bool(blueprint.get("active_data", False)):
            active_data_node_ids.append(node_id)

    _add_dataflow_edges(
        workspace,
        _ordered_dataflow_connections(
            node_ids=active_data_node_ids,
            edge_count=config.edge_count,
            seed=config.seed,
        ),
    )

    project.workspaces[workspace_id] = workspace
    project.active_workspace_id = workspace_id
    project.metadata["workspace_order"] = [workspace_id]
    return project, active_data_node_ids


def _build_heavy_media_project(config: SyntheticGraphConfig) -> _ScenarioProject:
    if config.node_count < 5:
        raise ValueError("heavy_media scenario requires node_count >= 5")
    app = QApplication.instance() or QApplication([])
    _ = app

    minimum_active_nodes = _minimum_active_nodes_for_edge_count(config.edge_count)
    if minimum_active_nodes > config.node_count - 2:
        raise ValueError(
            "heavy_media scenario requires enough node budget for an active data backbone plus image/PDF panels"
        )

    target_media_nodes = min(
        config.node_count - minimum_active_nodes,
        6,
    )
    target_media_nodes = max(2, target_media_nodes)
    if target_media_nodes >= config.node_count:
        target_media_nodes = config.node_count - minimum_active_nodes
    if target_media_nodes < 2:
        raise ValueError(
            "heavy_media scenario requires at least one image panel and one PDF panel"
        )

    image_nodes = math.ceil(target_media_nodes / 2)
    pdf_nodes = target_media_nodes - image_nodes
    if pdf_nodes <= 0:
        pdf_nodes = 1
        image_nodes = target_media_nodes - 1
    active_data_nodes = config.node_count - target_media_nodes

    temp_dir = tempfile.TemporaryDirectory(prefix="track_h_heavy_media_")
    fixture_dir = Path(temp_dir.name)
    fixtures = _create_heavy_media_fixtures(fixture_dir)
    node_blueprints = _build_node_blueprints(
        active_data_nodes=active_data_nodes,
        image_nodes=image_nodes,
        pdf_nodes=pdf_nodes,
        fixtures=fixtures,
    )
    project, active_data_node_ids = _project_from_blueprints(
        config=config,
        node_blueprints=node_blueprints,
        max_cols=6,
        spacing_x=360.0,
        spacing_y=320.0,
    )

    return _ScenarioProject(
        project=project,
        temp_dir=temp_dir,
        scenario_details={
            "description": (
                "Generated local PNG/PDF fixtures reused across passive media nodes inside the real "
                "GraphCanvas.qml benchmark path."
            ),
            "fixture_strategy": "generated_local_media_reuse",
            "node_mix": {
                "execution_nodes": len(active_data_node_ids),
                "media_panel_nodes": image_nodes + pdf_nodes,
                "image_source_nodes": image_nodes,
                "pdf_source_nodes": pdf_nodes,
            },
            "generated_fixture_count": {
                "images": len(fixtures["image_paths"]),
                "pdfs": 1,
            },
            "expected_media_surface_count": image_nodes + pdf_nodes,
        },
    )


def _build_animated_media_project(config: SyntheticGraphConfig) -> _ScenarioProject:
    if config.node_count <= 0:
        raise ValueError("animated_media scenario requires node_count > 0")
    if config.edge_count != 0:
        raise ValueError("animated_media scenario requires --edges 0")

    app = QApplication.instance() or QApplication([])
    _ = app
    temp_dir = tempfile.TemporaryDirectory(prefix="track_h_animated_media_")
    try:
        fixtures = _create_animated_media_fixtures(Path(temp_dir.name))
        fixture_roles = tuple(fixtures)
        role_counts: Counter[str] = Counter()
        node_blueprints: list[dict[str, Any]] = []
        for index in range(config.node_count):
            role = fixture_roles[index % len(fixture_roles)]
            role_counts[role] += 1
            node_blueprints.append(
                {
                    "type_id": "media.panel",
                    "title": f"Animated Media {index + 1} ({role})",
                    "properties": {
                        "source": str(fixtures[role]),
                        "fit_mode": ("contain", "cover", "original")[index % 3],
                        "animation_playback_mode": "auto",
                    },
                    "exposed_ports": {"source": False},
                    "active_data": False,
                }
            )

        project, active_data_node_ids = _project_from_blueprints(
            config=config,
            node_blueprints=node_blueprints,
            max_cols=10,
            spacing_x=360.0,
            spacing_y=320.0,
        )
    except Exception:
        temp_dir.cleanup()
        raise

    committed_fixture_paths = {
        role: _relative_or_absolute_path(path)
        for role, path in fixtures.items()
        if role != "static_png"
    }
    candidate_animated_panel_count = sum(
        role_counts[role]
        for role in ("animated_small_gif", "animated_large_gif", "animated_webp")
    )
    return _ScenarioProject(
        project=project,
        temp_dir=temp_dir,
        scenario_details={
            "description": (
                "Committed animated, single-frame, and corrupt media fixtures plus a generated static "
                "control distributed across Media Panels in the real GraphCanvas.qml benchmark path."
            ),
            "fixture_strategy": "committed_animation_fixtures_plus_generated_static",
            "required_fixture_paths": committed_fixture_paths,
            "fixture_role_counts": dict(sorted(role_counts.items())),
            "node_mix": {
                "execution_nodes": len(active_data_node_ids),
                "media_panel_nodes": config.node_count,
                "image_source_nodes": config.node_count,
                "pdf_source_nodes": 0,
            },
            "generated_fixture_count": {
                "images": 1,
                "pdfs": 0,
            },
            "workspace_media_panel_count": config.node_count,
            "candidate_animated_panel_count": candidate_animated_panel_count,
            # The visible-node model intentionally leaves most 20-100 panel scenarios offscreen.
            "expected_media_surface_count": 1,
        },
    )


def _build_fixture_project(config: BenchmarkConfig) -> _ScenarioProject:
    stress_fixture_mode = _normalize_stress_fixture_mode(config.stress_fixture)
    project_path = _configured_fixture_project_path(config)
    if project_path is None:
        raise ValueError("Fixture benchmark requested without a project path")

    serializer = JsonProjectSerializer(build_default_registry())
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    effective_project_path = project_path
    project_path_exists = project_path.exists()
    fixture_strategy = "serializer_project_load"
    fixture_source_kind = (
        "real" if stress_fixture_mode == _STRESS_FIXTURE_MODE_REAL else "project"
    )
    fixture_acceptance_scope = (
        "real_fixture_baseline"
        if stress_fixture_mode == _STRESS_FIXTURE_MODE_REAL
        else "project_fixture_regression"
    )
    display_acceptance_eligible = stress_fixture_mode == _STRESS_FIXTURE_MODE_REAL

    if project_path_exists:
        project = serializer.load(str(project_path))
    elif stress_fixture_mode == _STRESS_FIXTURE_MODE_REAL:
        raise FileNotFoundError(
            "Real stress fixture not found: "
            f"{project_path}. The canonical stress fixture must be present for stress-1200 evidence."
        )
    else:
        raise FileNotFoundError(f"Project fixture not found: {project_path}")

    requested_workspace_id = str(config.workspace_id).strip()
    if not requested_workspace_id and stress_fixture_mode:
        requested_workspace_id = _STRESS_FIXTURE_WORKSPACE_ID
    workspace_id = (
        requested_workspace_id or str(project.active_workspace_id or "").strip()
    )
    if not workspace_id:
        raise ValueError(
            f"Project fixture {project_path} does not define an active workspace"
        )
    if workspace_id not in project.workspaces:
        available = ", ".join(sorted(project.workspaces))
        raise ValueError(
            f"Project fixture {project_path} does not contain workspace {workspace_id!r}; "
            f"available: {available}"
        )
    project.active_workspace_id = workspace_id
    workspace = project.workspaces[workspace_id]

    media_panel_nodes = [
        node
        for node in workspace.nodes.values()
        if str(node.type_id) == MEDIA_PANEL_TYPE_ID
    ]
    image_nodes = sum(
        media_kind_from_source(node.properties.get("source")) == "image"
        for node in media_panel_nodes
    )
    pdf_nodes = sum(
        media_kind_from_source(node.properties.get("source")) == "pdf"
        for node in media_panel_nodes
    )
    media_nodes = len(media_panel_nodes)
    fixture_metadata = _workspace_fixture_metadata(
        project_path=project_path,
        effective_project_path=effective_project_path,
        project_path_exists=project_path_exists,
        workspace_id=workspace_id,
        workspace=workspace,
        fixture_strategy=fixture_strategy,
        fixture_source_kind=fixture_source_kind,
        fixture_acceptance_scope=fixture_acceptance_scope,
        display_acceptance_eligible=display_acceptance_eligible,
    )
    return _ScenarioProject(
        project=project,
        workspace_id=workspace_id,
        temp_dir=temp_dir,
        scenario_details={
            "description": "Project fixture loaded through JsonProjectSerializer for the real GraphCanvas.qml path.",
            "fixture_strategy": fixture_strategy,
            "fixture_source_kind": fixture_source_kind,
            "fixture_acceptance_scope": fixture_acceptance_scope,
            "display_acceptance_eligible": display_acceptance_eligible,
            "prior_stress_closeout_status": (
                dict(_STRESS_FIXTURE_PRIOR_CLOSEOUT) if stress_fixture_mode else {}
            ),
            "node_mix": {
                "execution_nodes": max(0, len(workspace.nodes) - media_nodes),
                "media_panel_nodes": media_nodes,
                "image_source_nodes": image_nodes,
                "pdf_source_nodes": pdf_nodes,
            },
            "generated_fixture_count": {
                "images": 0,
                "pdfs": 0,
            },
            "expected_media_surface_count": media_nodes,
            "fixture_metadata": fixture_metadata,
        },
    )


def _build_scenario_project(config: BenchmarkConfig) -> _ScenarioProject:
    if _fixture_source_requested(config):
        return _build_fixture_project(config)

    scenario = _normalize_benchmark_scenario(config.scenario)
    if scenario == "heavy_media":
        return _build_heavy_media_project(config.synthetic_graph)
    if scenario == _ANIMATED_MEDIA_SCENARIO:
        return _build_animated_media_project(config.synthetic_graph)

    project = generate_synthetic_project(config.synthetic_graph)
    return _ScenarioProject(
        project=project,
        scenario_details={
            "description": "Synthetic acyclic dataflow graph using active Python transform nodes only.",
            "fixture_strategy": "none",
            "node_mix": {
                "execution_nodes": config.synthetic_graph.node_count,
                "media_panel_nodes": 0,
                "image_source_nodes": 0,
                "pdf_source_nodes": 0,
            },
            "generated_fixture_count": {
                "images": 0,
                "pdfs": 0,
            },
            "expected_media_surface_count": 0,
        },
    )


def _graph_canvas_qml_path() -> Path:
    return _package_root_path() / "ui_qml" / "components" / "GraphCanvas.qml"


def _package_root_path() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root_path() -> Path:
    return _package_root_path().parent


def _iter_quick_item_tree(root: QQuickItem | None) -> list[QQuickItem]:
    if root is None:
        return []
    items: list[QQuickItem] = []
    stack: list[QQuickItem] = [root]
    while stack:
        item = stack.pop()
        items.append(item)
        stack.extend(
            child for child in item.childItems() if isinstance(child, QQuickItem)
        )
    return items


class _GraphCanvasBenchmarkHost:
    def __init__(
        self,
        *,
        app: QApplication,
        doc: dict[str, Any],
        workspace_id: str,
        root_context_setup: Callable[["_GraphCanvasBenchmarkHost", Any], None] | None = None,
    ) -> None:
        self.app = app
        self._setup_phase_timings_ms = {
            phase_key: 0.0 for phase_key in _CANVAS_SETUP_PHASE_KEYS
        }
        registry = build_default_registry()
        self.registry = registry
        self.workspace_id = workspace_id
        serializer = JsonProjectSerializer(registry)
        project = serializer.from_document(doc)
        self.model = GraphModel(project)
        model_attach_started = time.perf_counter()
        self.scene, self.view = _bind_scene_for_workspace(
            app=app,
            model=self.model,
            registry=registry,
            workspace_id=workspace_id,
        )
        self._setup_phase_timings_ms["canvas_setup_node_model_attach_ms"] = (
            time.perf_counter() - model_attach_started
        ) * 1000.0
        self.view.set_viewport_size(
            float(_CANVAS_BENCHMARK_WIDTH), float(_CANVAS_BENCHMARK_HEIGHT)
        )

        self.qml_host_kind = select_qml_host_kind_from_environment()
        self.widget: QQuickWidget | None = None
        self.view_window: QQuickView | None = None
        if self.qml_host_kind == QML_HOST_QQUICKVIEW_CONTAINER:
            self.view_window = QQuickView()
            self.view_window.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            self.view_window.resize(_CANVAS_BENCHMARK_WIDTH, _CANVAS_BENCHMARK_HEIGHT)
            self.engine = self.view_window.engine()
        else:
            self.qml_host_kind = QML_HOST_QQUICKWIDGET
            self.widget = QQuickWidget()
            self.widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            self.widget.resize(_CANVAS_BENCHMARK_WIDTH, _CANVAS_BENCHMARK_HEIGHT)
            self.engine = self.widget.engine()

        self.engine.addImageProvider(
            LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider()
        )
        self.engine.addImageProvider(
            LOCAL_PDF_PREVIEW_PROVIDER_ID, LocalPdfPreviewImageProvider()
        )
        self.theme_bridge = ThemeBridge(self.engine, theme_id=_CANVAS_THEME_ID)
        self.graph_theme_bridge = GraphThemeBridge(
            self.engine, theme_id=_CANVAS_GRAPH_THEME_ID
        )
        self.main_window_bridge = _BenchmarkMainWindowBridge()
        self.canvas_state_bridge = GraphCanvasStateBridge(
            session_state=self.main_window_bridge,
            snap_grid_size=20.0,
            graphics_source=self.main_window_bridge,  # type: ignore[arg-type]
            scene_bridge=self.scene,
            view_bridge=self.view,
        )
        self.canvas_command_bridge = GraphCanvasCommandBridge(
            host_source=self.main_window_bridge,  # type: ignore[arg-type]
            scene_bridge=self.scene,
            view_bridge=self.view,
        )
        root_binding_started = time.perf_counter()
        root_context = self.engine.rootContext()
        root_context.setContextProperty("themeBridge", self.theme_bridge)
        root_context.setContextProperty("graphThemeBridge", self.graph_theme_bridge)
        root_context.setContextProperty("canvasStateBridge", self.canvas_state_bridge)
        root_context.setContextProperty(
            "canvasCommandBridge", self.canvas_command_bridge
        )
        if root_context_setup is not None:
            root_context_setup(self, root_context)

        qml_path = _graph_canvas_qml_path()
        initial_properties = {
            "canvasStateBridge": self.canvas_state_bridge,
            "canvasCommandBridge": self.canvas_command_bridge,
            "width": float(_CANVAS_BENCHMARK_WIDTH),
            "height": float(_CANVAS_BENCHMARK_HEIGHT),
        }
        self._setup_phase_timings_ms["canvas_setup_root_binding_ms"] = (
            time.perf_counter() - root_binding_started
        ) * 1000.0
        if self.widget is not None:
            qml_load_started = time.perf_counter()
            if hasattr(self.widget, "setInitialProperties"):
                self.widget.setInitialProperties(initial_properties)
            self.widget.setSource(QUrl.fromLocalFile(str(qml_path)))
            self.widget.show()
            self.window = self.widget.quickWindow()
            canvas = self.widget.rootObject()
            self._setup_phase_timings_ms["canvas_setup_qml_load_ms"] = (
                time.perf_counter() - qml_load_started
            ) * 1000.0
        else:
            assert self.view_window is not None
            qml_load_started = time.perf_counter()
            if hasattr(self.view_window, "setInitialProperties"):
                self.view_window.setInitialProperties(initial_properties)
            self.view_window.setSource(QUrl.fromLocalFile(str(qml_path)))
            self.view_window.show()
            self.window = self.view_window
            canvas = self.view_window.rootObject()
            self._setup_phase_timings_ms["canvas_setup_qml_load_ms"] = (
                time.perf_counter() - qml_load_started
            ) * 1000.0
        if canvas is not None:
            for key, value in initial_properties.items():
                canvas.setProperty(key, value)
        if self.window is None:
            raise RuntimeError(
                f"Failed to resolve benchmark quick window for {self.qml_host_kind}"
            )
        if canvas is None:
            errors = (
                self.widget.errors()
                if self.widget is not None
                else self.view_window.errors()
            )
            formatted_errors = "\n".join(error.toString() for error in errors)
            raise RuntimeError(
                f"Failed to instantiate GraphCanvas.qml in {self.qml_host_kind}:\n{formatted_errors}"
            )
        if not isinstance(canvas, QQuickItem):
            raise TypeError("GraphCanvas.qml did not create a QQuickItem root")
        self.canvas = canvas
        self._frame_render_timestamps: list[float] = []
        self.window.afterRendering.connect(
            self._record_frame_render_timestamp,
            Qt.ConnectionType.DirectConnection,
        )
        first_render_started = time.perf_counter()
        self.render_frame()
        self._setup_phase_timings_ms["canvas_setup_first_rendered_frame_ms"] = (
            time.perf_counter() - first_render_started
        ) * 1000.0
        initial_profile = self.collect_targeted_profiling_snapshot()
        self._setup_phase_timings_ms["canvas_setup_initial_visible_model_ms"] = float(
            initial_profile.get("visible_model_query_ms", 0.0)
        )
        self._setup_phase_timings_ms["canvas_setup_initial_edge_snapshot_ms"] = max(
            float(initial_profile.get("edge_snapshot_build_ms", 0.0)),
            float(initial_profile.get("edge_snapshot_refresh_ms", 0.0)),
        )
        self._setup_phase_timings_ms[
            "canvas_setup_initial_edge_spatial_index_build_ms"
        ] = float(initial_profile.get("edge_spatial_index_build_ms", 0.0))
        self._setup_phase_timings_ms["canvas_setup_grid_minimap_ms"] = float(
            initial_profile.get("grid_update_ms", 0.0)
        ) + float(initial_profile.get("grid_paint_ms", 0.0))

    def _record_frame_render_timestamp(self) -> None:
        self._frame_render_timestamps.append(time.perf_counter())

    def reset_frame_interval_capture(self) -> None:
        self._frame_render_timestamps.clear()

    def frame_render_timestamp_index(self) -> int:
        return len(self._frame_render_timestamps)

    def frame_interval_samples_without_readback_ms(self) -> list[float]:
        return _frame_intervals_ms_from_timestamps(list(self._frame_render_timestamps))

    def setup_phase_timings_ms(self) -> dict[str, float]:
        return dict(self._setup_phase_timings_ms)

    def grab_frame_image(self) -> QImage:
        if getattr(self, "widget", None) is not None:
            return self.widget.grab().toImage()
        return self.window.grabWindow()

    def renderer_diagnostics(self) -> dict[str, Any]:
        return qtquick_backend_diagnostics(
            self.window,
            qml_host_kind=self.qml_host_kind,
            grab_window_readback_included=True,
        )

    def apply_edge_renderer_policy(self, renderer_diagnostics: dict[str, Any]) -> None:
        edge_layer = _find_quick_item_by_object_name(
            self.canvas, "graphCanvasEdgeLayer"
        )
        if edge_layer is None:
            return
        qt_platform = str(
            renderer_diagnostics.get("qt_qpa_platform")
            or os.environ.get("QT_QPA_PLATFORM", "")
        )
        rhi_backend = str(
            renderer_diagnostics.get("qsg_rhi_backend")
            or renderer_diagnostics.get("qtquick_backend_selected")
            or ""
        )
        graphics_api = str(renderer_diagnostics.get("graphics_api", ""))
        graphics_api_label = str(renderer_diagnostics.get("graphics_api_label", ""))
        software_fallback_active = bool(
            renderer_diagnostics.get("software_fallback_active", False)
        )
        if not software_fallback_active:
            software_fallback_active = (
                rhi_backend.strip().lower() == "software"
                or graphics_api == "Software"
                or graphics_api_label == "Software"
                or bool(
                    renderer_diagnostics.get("qtquick_backend_forced_software", False)
                )
            )
        display_attached = _is_display_attached_qt_platform(qt_platform)
        preferred_renderer = (
            "retained_qml"
            if display_attached and not software_fallback_active
            else "canvas"
        )
        edge_layer.setProperty("edgeRendererPreference", preferred_renderer)
        if hasattr(edge_layer, "requestRedraw"):
            edge_layer.requestRedraw()
        self.app.processEvents()

    def collect_feature_parity_snapshot(
        self, *, expected_media_surface_count: int
    ) -> dict[str, Any]:
        canvas = self.canvas if getattr(self, "canvas", None) is not None else None
        items = _iter_quick_item_tree(canvas)
        media_surfaces = [
            item
            for item in items
            if str(item.objectName() or "") == "graphNodeMediaSurface"
        ]
        media_surface_count = len(media_surfaces)
        media_preview_states = [
            str(surface.property("previewState") or "") for surface in media_surfaces
        ]
        animation_activity = _animation_activity_snapshot(
            items=items,
            media_surfaces=media_surfaces,
        )
        visible_edge_label_count = sum(
            1
            for item in items
            if str(item.objectName() or "") == "graphEdgeFlowLabelItem"
            and bool(item.property("visible"))
        )
        minimap_overlay = _find_quick_item_by_object_name(
            canvas, "graphCanvasMinimapOverlay"
        )
        background_layer = _find_quick_item_by_object_name(
            canvas, "graphCanvasBackground"
        )
        edge_layer = _find_quick_item_by_object_name(canvas, "graphCanvasEdgeLayer")
        preference_facts = canvas.property("prefs") if canvas is not None else None
        snapshot: dict[str, Any] = {
            "zero_loss_enforced": True,
            "show_grid": _quick_item_bool_property(canvas, "showGrid", True),
            "grid_renderer_kind": str(
                background_layer.property("profileGridRendererKind") or ""
            )
            if background_layer is not None
            else "",
            "edge_renderer_kind": str(edge_layer.property("edgeRendererKind") or "")
            if edge_layer is not None
            else "",
            "edge_renderer_requested_kind": str(
                edge_layer.property("edgeRendererRequestedKind") or ""
            )
            if edge_layer is not None
            else "",
            "edge_renderer_canvas_fallback_active": _quick_item_bool_property(
                edge_layer,
                "edgeRendererCanvasFallbackActive",
                False,
            ),
            "edge_renderer_fallback_reason": str(
                edge_layer.property("edgeRendererFallbackReason") or ""
            )
            if edge_layer is not None
            else "",
            "minimap_visible": _quick_item_bool_property(
                canvas, "minimapVisible", True
            ),
            "minimap_overlay_visible": _quick_item_bool_property(
                minimap_overlay, "visible", True
            ),
            "node_shadows_enabled": _quick_item_bool_property(
                canvas, "nodeShadowEnabled", True
            ),
            "notched_ports_enabled": _quick_item_bool_property(
                canvas,
                "notchedPortsEnabled",
                _quick_item_bool_property(
                    preference_facts,
                    "notchedPortsEnabled",
                    True,
                ),
            ),
            "port_labels_visible": _quick_item_bool_property(
                canvas, "showPortLabels", True
            ),
            "edge_crossing_style": str(canvas.property("edgeCrossingStyle") or "")
            if canvas is not None
            else "",
            "embedded_media_count": media_surface_count,
            "expected_embedded_media_count": int(expected_media_surface_count),
            "embedded_media_ready_count": sum(
                state == "ready" for state in media_preview_states
            ),
            "embedded_media_preview_states": media_preview_states,
            "animation_activity": animation_activity,
            "visible_edge_label_count": visible_edge_label_count,
            "grid_simplification_active": _quick_item_bool_property(
                canvas, "gridSimplificationActive", False
            ),
            "minimap_simplification_active": _quick_item_bool_property(
                canvas, "minimapSimplificationActive", False
            ),
            "shadow_simplification_active": _quick_item_bool_property(
                canvas, "shadowSimplificationActive", False
            ),
            "edge_label_simplification_active": _quick_item_bool_property(
                canvas,
                "edgeLabelSimplificationActive",
                False,
            ),
        }
        failures: list[str] = []
        if not animation_activity["policy_pass"]:
            failures.append(
                "animation playback policy violations: "
                + ", ".join(
                    f"{key}={value}"
                    for key, value in animation_activity["policy_violations"].items()
                    if value
                )
            )
        if not snapshot["show_grid"]:
            failures.append("grid hidden")
        if not snapshot["minimap_visible"]:
            failures.append("minimap hidden")
        if not snapshot["node_shadows_enabled"]:
            failures.append("node shadows disabled")
        if not snapshot["notched_ports_enabled"]:
            failures.append("notched ports disabled")
        if not snapshot["port_labels_visible"]:
            failures.append("port labels hidden")
        if snapshot["grid_simplification_active"]:
            failures.append("grid simplification active")
        if snapshot["minimap_simplification_active"]:
            failures.append("minimap simplification active")
        if snapshot["shadow_simplification_active"]:
            failures.append("shadow simplification active")
        if snapshot["edge_label_simplification_active"]:
            failures.append("edge label simplification active")
        if (
            expected_media_surface_count > 0
            and media_surface_count < expected_media_surface_count
        ):
            failures.append(
                "embedded media hidden "
                f"({media_surface_count}/{int(expected_media_surface_count)} surfaces present)"
            )
        snapshot["pass"] = not failures
        snapshot["failures"] = failures
        return snapshot

    def begin_viewport_interaction(self) -> None:
        if getattr(self, "canvas", None) is None:
            return
        self.canvas.beginViewportInteraction()
        self.app.processEvents()

    def note_viewport_interaction(self) -> None:
        if getattr(self, "canvas", None) is None:
            return
        self.canvas.noteViewportInteraction()
        self.app.processEvents()

    def finish_viewport_interaction(self) -> None:
        if getattr(self, "canvas", None) is None:
            return
        self.canvas.finishViewportInteractionSoon()
        self.app.processEvents()

    def wait_for_viewport_interaction_idle(self, *, timeout_ms: int = 1000) -> None:
        if getattr(self, "canvas", None) is None:
            return
        deadline = time.perf_counter() + (float(timeout_ms) / 1000.0)
        while True:
            self.app.processEvents()
            if not bool(self.canvas.property("interactionActive")):
                self.app.processEvents()
                return
            if time.perf_counter() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for GraphCanvas viewport interaction to settle"
                )
            time.sleep(0.005)

    def wait_for_media_surfaces_ready(
        self,
        *,
        expected_count: int,
        timeout_ms: int = 6000,
        require_ready: bool = True,
    ) -> None:
        if expected_count <= 0 or getattr(self, "canvas", None) is None:
            return
        deadline = time.perf_counter() + (float(timeout_ms) / 1000.0)
        while True:
            self.app.processEvents()
            self.window.update()
            self.grab_frame_image()
            media_surfaces = [
                item
                for item in _iter_quick_item_tree(self.canvas)
                if str(item.objectName() or "") == "graphNodeMediaSurface"
            ]
            ready_count = sum(
                str(surface.property("previewState") or "") == "ready"
                for surface in media_surfaces
            )
            if len(media_surfaces) >= expected_count and (
                not require_ready or ready_count >= expected_count
            ):
                self.app.processEvents()
                return
            if time.perf_counter() >= deadline:
                states = [
                    str(surface.property("previewState") or "")
                    for surface in media_surfaces
                ]
                readiness_label = "ready state" if require_ready else "instantiation"
                raise RuntimeError(
                    f"Timed out waiting for heavy-media surfaces to reach {readiness_label} "
                    f"(expected={expected_count}, found={len(media_surfaces)}, ready={ready_count}, states={states})"
                )
            time.sleep(0.01)

    def render_frame(
        self, *, timeout_ms: int = 2000, capture_timings: bool = False
    ) -> dict[str, float] | None:
        deadline = time.perf_counter() + (float(timeout_ms) / 1000.0)
        timings_ms = {
            "render_callback_wait_ms": 0.0,
            "readback_grab_ms": 0.0,
            "post_readback_event_drain_ms": 0.0,
        }
        total_started = time.perf_counter()
        while True:
            wait_started = time.perf_counter()
            self.app.processEvents()
            self.window.update()
            timings_ms["render_callback_wait_ms"] += (
                time.perf_counter() - wait_started
            ) * 1000.0
            readback_started = time.perf_counter()
            image = self.grab_frame_image()
            timings_ms["readback_grab_ms"] += (
                time.perf_counter() - readback_started
            ) * 1000.0
            if not image.isNull() and image.width() > 0 and image.height() > 0:
                drain_started = time.perf_counter()
                self.app.processEvents()
                timings_ms["post_readback_event_drain_ms"] += (
                    time.perf_counter() - drain_started
                ) * 1000.0
                timings_ms["render_frame_total_ms"] = (
                    time.perf_counter() - total_started
                ) * 1000.0
                return timings_ms if capture_timings else None
            if time.perf_counter() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for GraphCanvas.qml to render a frame"
                )
            sleep_started = time.perf_counter()
            time.sleep(0.005)
            timings_ms["render_callback_wait_ms"] += (
                time.perf_counter() - sleep_started
            ) * 1000.0

    def visible_scene_rect(self) -> QRectF:
        return self.view.visible_scene_rect()

    def node_cards(self) -> list[QQuickItem]:
        if getattr(self, "canvas", None) is None:
            return []
        return [
            item
            for item in _iter_quick_item_tree(self.canvas)
            if str(item.objectName() or "") == "graphNodeCard"
        ]

    def group_backdrop_input_cards(self) -> list[QQuickItem]:
        if getattr(self, "canvas", None) is None:
            return []
        return [
            item
            for item in _iter_quick_item_tree(self.canvas)
            if str(item.objectName() or "") == "graphGroupBackdropInputCard"
        ]

    def _force_visible_node_cards_current(self) -> list[QQuickItem]:
        bridge = getattr(self, "canvas_state_bridge", None)
        force_exact = getattr(bridge, "force_visible_scene_models_exact", None)
        if force_exact is None:
            return self.node_cards()
        force_exact()
        self.app.processEvents()
        self.render_frame()
        self.app.processEvents()
        return self.node_cards()

    def collect_targeted_profiling_snapshot(self) -> dict[str, float]:
        if getattr(self, "canvas", None) is None:
            return {
                "visible_model_query_ms": 0.0,
                "edge_snapshot_build_ms": 0.0,
                "edge_snapshot_refresh_ms": 0.0,
                "edge_spatial_index_build_ms": 0.0,
                "edge_paint_ms": 0.0,
                "grid_update_ms": 0.0,
                "grid_paint_ms": 0.0,
                "overlay_sync_ms": 0.0,
                "visible_model_query_count": 0.0,
                "grid_update_count": 0.0,
                "edge_snapshot_refresh_count": 0.0,
                "total_node_count": 0.0,
                "total_edge_count": 0.0,
                "candidate_edge_count": 0.0,
                "visible_edge_snapshot_count": 0.0,
                "skipped_edge_count": 0.0,
                "geometry_cache_hit_count": 0.0,
                "geometry_cache_miss_count": 0.0,
                "visible_node_delegate_count": 0.0,
                "visible_backdrop_delegate_count": 0.0,
                "visible_node_card_count": 0.0,
                "delegate_create_count": 0.0,
                "delegate_destroy_count": 0.0,
                "active_node_surface_count": 0.0,
                "visible_edge_label_count": 0.0,
                "visible_edge_count": 0.0,
                "frame_scheduler_requested_redraw_count": 0.0,
                "frame_scheduler_view_state_redraw_request_count": 0.0,
                "frame_scheduler_edge_redraw_request_count": 0.0,
                "frame_scheduler_overlay_redraw_request_count": 0.0,
                "frame_scheduler_flushed_frame_count": 0.0,
                "frame_scheduler_coalesced_redraw_request_count": 0.0,
                "live_drag_offset_update_count": 0.0,
            }

        visible_rect = self.visible_scene_rect()
        items = _iter_quick_item_tree(self.canvas)
        root_layers = _find_quick_item_by_object_name(
            self.canvas, "graphCanvasRootLayers"
        )
        frame_scheduler = _find_quick_item_by_object_name(
            self.canvas, "graphCanvasFrameScheduler"
        )
        background_layer: QQuickItem | None = None
        edge_layer: QQuickItem | None = None
        visible_node_card_count = 0
        active_node_surface_count = 0
        visible_edge_label_count = 0
        total_node_count = _quick_item_float_property(
            root_layers, "profileTotalNodeCount"
        )
        visible_node_delegate_count = _quick_item_float_property(
            root_layers, "profileVisibleNodeDelegateCount"
        )
        visible_backdrop_delegate_count = _quick_item_float_property(
            root_layers, "profileVisibleBackdropDelegateCount"
        )
        visible_model_query_ms = _quick_item_float_property(
            root_layers, "profileLastVisibleModelQueryMs"
        )
        visible_model_query_count = _quick_item_float_property(
            root_layers, "profileVisibleModelQueryCount"
        )
        delegate_create_count = _quick_item_float_property(
            root_layers, "profileDelegateCreateCount"
        )
        delegate_destroy_count = _quick_item_float_property(
            root_layers, "profileDelegateDestroyCount"
        )

        for item in items:
            object_name = str(item.objectName() or "")
            if object_name == "graphCanvasBackground":
                background_layer = item
                continue
            if object_name == "graphCanvasEdgeLayer":
                edge_layer = item
                continue
            if object_name == "graphEdgeFlowLabelItem":
                if bool(item.property("visible")):
                    visible_edge_label_count += 1
                continue

            if object_name not in {"graphNodeCard", "graphNodeSurfaceLoader"}:
                continue

            node_data = item.property("nodeData") or {}
            node_rect = _node_payload_scene_rect(
                node_data,
                fallback_width=item.width(),
                fallback_height=item.height(),
            )
            if not visible_rect.intersects(node_rect):
                continue

            if object_name == "graphNodeCard":
                visible_node_card_count += 1
                continue

            if bool(item.property("renderActive")) and bool(
                item.property("surfaceLoaded")
            ):
                active_node_surface_count += 1

        edge_snapshot_build_ms = 0.0
        edge_snapshot_refresh_ms = 0.0
        edge_spatial_index_build_ms = 0.0
        edge_paint_ms = 0.0
        visible_edge_count = 0.0
        total_edge_count = 0.0
        candidate_edge_count = 0.0
        visible_edge_snapshot_count = 0.0
        skipped_edge_count = 0.0
        geometry_cache_hit_count = 0.0
        geometry_cache_miss_count = 0.0
        edge_snapshot_refresh_count = 0.0
        edge_spatial_index_query_cache_hit_count = 0.0
        edge_spatial_index_query_cache_miss_count = 0.0
        retained_model_entry_skip_count = 0.0
        flow_label_model_sync_skip_count = 0.0
        if edge_layer is not None:
            edge_snapshot_build_ms = float(
                edge_layer.property("profileLastSnapshotBuildMs") or 0.0
            )
            edge_snapshot_refresh_ms = float(
                edge_layer.property("profileSnapshotRefreshMs") or 0.0
            )
            edge_spatial_index_build_ms = float(
                edge_layer.property("profileSpatialIndexBuildMs") or 0.0
            )
            edge_paint_ms = float(edge_layer.property("profileLastEdgePaintMs") or 0.0)
            edge_snapshot_refresh_count = float(
                edge_layer.property("profileSnapshotRefreshCount") or 0.0
            )
            visible_edge_count = float(
                edge_layer.property("profileLastVisibleEdgeCount") or 0.0
            )
            total_edge_count = float(
                edge_layer.property("profileTotalEdgeCount") or 0.0
            )
            candidate_edge_count = float(
                edge_layer.property("profileLastCandidateEdgeCount") or 0.0
            )
            visible_edge_snapshot_count = float(
                edge_layer.property("profileLastVisibleEdgeSnapshotCount") or 0.0
            )
            skipped_edge_count = float(
                edge_layer.property("profileLastSkippedEdgeCount") or 0.0
            )
            geometry_cache_hit_count = float(
                edge_layer.property("profileGeometryCacheHitCount") or 0.0
            )
            geometry_cache_miss_count = float(
                edge_layer.property("profileGeometryCacheMissCount") or 0.0
            )
            edge_spatial_index_query_cache_hit_count = float(
                edge_layer.property("profileSpatialIndexQueryCacheHitCount") or 0.0
            )
            edge_spatial_index_query_cache_miss_count = float(
                edge_layer.property("profileSpatialIndexQueryCacheMissCount") or 0.0
            )
            retained_model_entry_skip_count = float(
                edge_layer.property("profileRetainedModelEntrySkipCount") or 0.0
            )
            flow_label_model_sync_skip_count = float(
                edge_layer.property("profileFlowLabelModelSyncSkipCount") or 0.0
            )
        grid_update_ms = 0.0
        grid_paint_ms = 0.0
        grid_update_count = 0.0
        if background_layer is not None:
            grid_update_ms = float(
                background_layer.property("profileLastGridUpdateMs") or 0.0
            )
            grid_paint_ms = float(
                background_layer.property("profileLastGridPaintMs") or 0.0
            )
            grid_update_count = float(
                background_layer.property("profileGridUpdateCount") or 0.0
            )

        overlay_sync_ms = float(self.canvas.property("profileOverlaySyncMs") or 0.0)
        live_drag_offset_update_count = _quick_item_float_property(
            self.canvas,
            "profileLiveDragOffsetUpdateCount",
        )
        frame_scheduler_requested_redraw_count = 0.0
        frame_scheduler_view_state_redraw_request_count = 0.0
        frame_scheduler_edge_redraw_request_count = 0.0
        frame_scheduler_overlay_redraw_request_count = 0.0
        frame_scheduler_flushed_frame_count = 0.0
        frame_scheduler_coalesced_redraw_request_count = 0.0
        if frame_scheduler is not None:
            frame_scheduler_requested_redraw_count = _quick_item_float_property(
                frame_scheduler,
                "requestedRedrawCount",
            )
            frame_scheduler_view_state_redraw_request_count = (
                _quick_item_float_property(
                    frame_scheduler,
                    "viewStateRedrawRequestCount",
                )
            )
            frame_scheduler_edge_redraw_request_count = _quick_item_float_property(
                frame_scheduler,
                "edgeRedrawRequestCount",
            )
            frame_scheduler_overlay_redraw_request_count = _quick_item_float_property(
                frame_scheduler,
                "overlayRedrawRequestCount",
            )
            frame_scheduler_flushed_frame_count = _quick_item_float_property(
                frame_scheduler,
                "flushedFrameCount",
            )
            frame_scheduler_coalesced_redraw_request_count = _quick_item_float_property(
                frame_scheduler,
                "coalescedRedrawRequestCount",
            )

        return {
            "visible_model_query_ms": visible_model_query_ms,
            "edge_snapshot_build_ms": edge_snapshot_build_ms,
            "edge_snapshot_refresh_ms": edge_snapshot_refresh_ms,
            "edge_spatial_index_build_ms": edge_spatial_index_build_ms,
            "edge_paint_ms": edge_paint_ms,
            "grid_update_ms": grid_update_ms,
            "grid_paint_ms": grid_paint_ms,
            "overlay_sync_ms": overlay_sync_ms,
            "visible_model_query_count": visible_model_query_count,
            "grid_update_count": grid_update_count,
            "edge_snapshot_refresh_count": edge_snapshot_refresh_count,
            "total_node_count": total_node_count,
            "total_edge_count": total_edge_count,
            "candidate_edge_count": candidate_edge_count,
            "visible_edge_snapshot_count": visible_edge_snapshot_count,
            "skipped_edge_count": skipped_edge_count,
            "geometry_cache_hit_count": geometry_cache_hit_count,
            "geometry_cache_miss_count": geometry_cache_miss_count,
            "edge_spatial_index_query_cache_hit_count": edge_spatial_index_query_cache_hit_count,
            "edge_spatial_index_query_cache_miss_count": edge_spatial_index_query_cache_miss_count,
            "retained_model_entry_skip_count": retained_model_entry_skip_count,
            "flow_label_model_sync_skip_count": flow_label_model_sync_skip_count,
            "visible_node_delegate_count": visible_node_delegate_count,
            "visible_backdrop_delegate_count": visible_backdrop_delegate_count,
            "visible_node_card_count": float(visible_node_card_count),
            "delegate_create_count": delegate_create_count,
            "delegate_destroy_count": delegate_destroy_count,
            "active_node_surface_count": float(active_node_surface_count),
            "visible_edge_label_count": float(visible_edge_label_count),
            "visible_edge_count": visible_edge_count,
            "frame_scheduler_requested_redraw_count": frame_scheduler_requested_redraw_count,
            "frame_scheduler_view_state_redraw_request_count": frame_scheduler_view_state_redraw_request_count,
            "frame_scheduler_edge_redraw_request_count": frame_scheduler_edge_redraw_request_count,
            "frame_scheduler_overlay_redraw_request_count": frame_scheduler_overlay_redraw_request_count,
            "frame_scheduler_flushed_frame_count": frame_scheduler_flushed_frame_count,
            "frame_scheduler_coalesced_redraw_request_count": frame_scheduler_coalesced_redraw_request_count,
            "live_drag_offset_update_count": live_drag_offset_update_count,
        }

    def media_node_scene_rect(self) -> QRectF:
        workspace = self.model.project.workspaces[
            self.model.project.active_workspace_id
        ]
        media_scene_rect = QRectF()
        found_media = False
        for node in workspace.nodes.values():
            if not str(node.type_id).startswith(_PASSIVE_MEDIA_TYPE_PREFIX):
                continue
            node_rect = QRectF(
                float(node.x),
                float(node.y),
                max(1.0, float(node.custom_width or 180.0)),
                max(1.0, float(node.custom_height or 120.0)),
            )
            media_scene_rect = (
                node_rect if not found_media else media_scene_rect.united(node_rect)
            )
            found_media = True
        if found_media:
            return media_scene_rect

        for node_card in self.node_cards():
            node_data = node_card.property("nodeData") or {}
            if not _node_payload_is_media(node_data):
                continue
            node_rect = _node_payload_scene_rect(
                node_data,
                fallback_width=node_card.width(),
                fallback_height=node_card.height(),
            )
            media_scene_rect = (
                node_rect if not found_media else media_scene_rect.united(node_rect)
            )
            found_media = True
        return media_scene_rect if found_media else QRectF()

    def frame_scene_rect(self, scene_rect: QRectF) -> bool:
        normalized = QRectF(scene_rect).normalized()
        if not normalized.isValid() or normalized.isEmpty():
            return False
        framed = bool(self.view.frame_scene_rect(normalized))
        self.app.processEvents()
        self.render_frame()
        return framed

    def prepare_media_ready_view(self) -> bool:
        media_scene_rect = self.media_node_scene_rect()
        if self.frame_scene_rect(media_scene_rect):
            return True
        workspace = self.model.project.workspaces[
            self.model.project.active_workspace_id
        ]
        left, right, top, bottom = _workspace_bounds(workspace)
        return self.frame_scene_rect(QRectF(left, top, right - left, bottom - top))

    def control_node_card(self) -> QQuickItem:
        fallback: QQuickItem | None = None
        visible_rect = self.visible_scene_rect()
        node_cards = self.node_cards()
        if not node_cards:
            node_cards = self._force_visible_node_cards_current()
        for node_card in node_cards:
            if fallback is None:
                fallback = node_card
            node_data = node_card.property("nodeData") or {}
            node_x = float(node_data.get("x", 0.0))
            node_y = float(node_data.get("y", 0.0))
            node_width = max(1.0, float(node_data.get("width", node_card.width())))
            node_height = max(1.0, float(node_data.get("height", node_card.height())))
            if visible_rect.intersects(QRectF(node_x, node_y, node_width, node_height)):
                return node_card
        if fallback is None:
            raise RuntimeError(
                "Failed to locate a graphNodeCard for node-drag control sampling"
            )
        return fallback

    def close(self) -> None:
        self.canvas = None
        if getattr(self, "widget", None) is not None:
            self.widget.setSource(QUrl())
            self.widget.close()
            self.widget.deleteLater()
            self.widget = None
            self.window = None
        if getattr(self, "view_window", None) is not None:
            self.view_window.setSource(QUrl())
            self.view_window.close()
            self.view_window.deleteLater()
            self.view_window = None
            self.window = None
        if getattr(self, "window", None) is not None:
            self.window.close()
            self.window = None
        if getattr(self, "scene", None) is not None:
            self.scene.deleteLater()
            self.scene = None
        if getattr(self, "view", None) is not None:
            self.view.deleteLater()
            self.view = None
        self.engine = None
        if getattr(self, "main_window_bridge", None) is not None:
            self.main_window_bridge.deleteLater()
            self.main_window_bridge = None
        self.app.processEvents()

    def __enter__(self) -> "_GraphCanvasBenchmarkHost":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()


def _bind_scene_for_workspace(
    *,
    app: QApplication,
    model: GraphModel,
    workspace_id: str,
    registry: Any | None = None,
) -> tuple[GraphSceneBridge, ViewportBridge]:
    registry = registry or build_default_registry()
    scene = GraphSceneBridge()
    view = ViewportBridge()
    view.set_viewport_size(1280.0, 720.0)
    scene.set_workspace(model, registry, workspace_id)
    app.processEvents()
    return scene, view


def _workspace_bounds(workspace: WorkspaceData) -> tuple[float, float, float, float]:
    if not workspace.nodes:
        return -5000.0, 5000.0, -5000.0, 5000.0
    xs = [float(node.x) for node in workspace.nodes.values()]
    ys = [float(node.y) for node in workspace.nodes.values()]
    margin_x = 800.0
    margin_y = 500.0
    return (
        min(xs) - margin_x,
        max(xs) + margin_x,
        min(ys) - margin_y,
        max(ys) + margin_y,
    )


def _workspace_scene_bounds_payload(workspace: WorkspaceData) -> dict[str, float]:
    if not workspace.nodes:
        return {
            "left": 0.0,
            "right": 0.0,
            "top": 0.0,
            "bottom": 0.0,
            "width": 0.0,
            "height": 0.0,
        }

    left = min(float(node.x) for node in workspace.nodes.values())
    top = min(float(node.y) for node in workspace.nodes.values())
    right = max(
        float(node.x) + float(node.custom_width or 180.0)
        for node in workspace.nodes.values()
    )
    bottom = max(
        float(node.y) + float(node.custom_height or 120.0)
        for node in workspace.nodes.values()
    )
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "width": max(0.0, right - left),
        "height": max(0.0, bottom - top),
    }


def _node_type_histogram(workspace: WorkspaceData) -> dict[str, int]:
    return dict(
        sorted(Counter(str(node.type_id) for node in workspace.nodes.values()).items())
    )


def _workspace_fixture_metadata(
    *,
    project_path: Path,
    effective_project_path: Path,
    project_path_exists: bool,
    workspace_id: str,
    workspace: WorkspaceData,
    fixture_strategy: str,
    fixture_source_kind: str,
    fixture_acceptance_scope: str,
    display_acceptance_eligible: bool,
) -> dict[str, Any]:
    project_checksum = _file_sha256(project_path) if project_path_exists else ""
    effective_checksum = _file_sha256(effective_project_path)
    return {
        "fixture_source_kind": fixture_source_kind,
        "fixture_acceptance_scope": fixture_acceptance_scope,
        "display_acceptance_eligible": bool(display_acceptance_eligible),
        "project_path": _relative_or_absolute_path(project_path),
        "project_path_absolute": str(project_path),
        "effective_project_path": _relative_or_absolute_path(effective_project_path),
        "effective_project_path_absolute": str(effective_project_path),
        "project_path_exists": bool(project_path_exists),
        "project_sha256": project_checksum,
        "effective_project_sha256": effective_checksum,
        "fixture_checksum_sha256": effective_checksum,
        "workspace_id": workspace_id,
        "node_count": len(workspace.nodes),
        "edge_count": len(workspace.edges),
        "node_type_histogram": _node_type_histogram(workspace),
        "scene_bounds": _workspace_scene_bounds_payload(workspace),
        "fixture_strategy": fixture_strategy,
    }


def _augment_fixture_metadata(
    fixture_metadata: dict[str, Any],
    *,
    renderer_diagnostics: dict[str, Any],
    interaction_benchmark: dict[str, Any],
) -> dict[str, Any]:
    if not fixture_metadata:
        return {}

    environment_keys = (
        "qt_qpa_platform",
        "qt_quick_backend",
        "qml_host_env",
        "qml_host_kind_selected",
        "qsg_rhi_backend",
        "qsg_rhi_backend_override",
        "qsg_render_loop",
        "qtquick_backend_selected",
        "qtquick_backend_selection_reason",
    )
    enriched = dict(fixture_metadata)
    enriched.update(
        {
            "active_graphics_api": renderer_diagnostics.get("graphics_api", ""),
            "active_graphics_api_label": renderer_diagnostics.get(
                "graphics_api_label", ""
            ),
            "qml_host_kind": renderer_diagnostics.get("qml_host_kind", ""),
            "qt_scenegraph_environment": {
                key: renderer_diagnostics.get(key, "") for key in environment_keys
            },
            "screen_device_pixel_ratio": float(
                renderer_diagnostics.get("screen_device_pixel_ratio", 0.0) or 0.0
            ),
            "window_effective_device_pixel_ratio": float(
                renderer_diagnostics.get("window_effective_device_pixel_ratio", 0.0)
                or 0.0
            ),
            "grab_window_readback_included": bool(
                interaction_benchmark.get("grab_window_readback_included", False)
            ),
            "frame_interval_metric": interaction_benchmark.get(
                "frame_interval_metric",
                "frame_interval_ms_without_readback",
            ),
        }
    )
    return enriched


def _node_payload_is_media(node_payload: Any) -> bool:
    if not isinstance(node_payload, dict):
        return False
    surface_family = str(node_payload.get("surface_family", "")).strip().lower()
    if surface_family == "media":
        return True
    type_id = str(node_payload.get("type_id", "")).strip().lower()
    return type_id.startswith(_PASSIVE_MEDIA_TYPE_PREFIX)


def _node_payload_scene_rect(
    node_payload: Any, *, fallback_width: float, fallback_height: float
) -> QRectF:
    payload = node_payload if isinstance(node_payload, dict) else {}
    node_x = float(payload.get("x", 0.0))
    node_y = float(payload.get("y", 0.0))
    node_width = max(1.0, float(payload.get("width", fallback_width)))
    node_height = max(1.0, float(payload.get("height", fallback_height)))
    return QRectF(node_x, node_y, node_width, node_height)


def benchmark_project_graph_load_ms(
    *,
    doc: dict[str, Any],
    workspace_id: str,
    iterations: int,
) -> _ProjectGraphLoadBenchmarkSamples:
    app = QApplication.instance() or QApplication([])
    registry = build_default_registry()
    serializer = JsonProjectSerializer(registry)
    document_text = json.dumps(doc, sort_keys=True, ensure_ascii=True)
    phase_samples = {
        "project_graph_load_ms": [],
        **{phase_key: [] for phase_key in _PROJECT_LOAD_PHASE_KEYS},
    }

    for _ in range(iterations):
        started = time.perf_counter()
        parse_started = time.perf_counter()
        raw_doc = json.loads(document_text)
        phase_samples["project_graph_load_serializer_parse_ms"].append(
            (time.perf_counter() - parse_started) * 1000.0
        )

        migration_started = time.perf_counter()
        migrated = serializer.migrate(raw_doc)
        phase_samples["project_graph_load_migration_ms"].append(
            (time.perf_counter() - migration_started) * 1000.0
        )

        conversion_started = time.perf_counter()
        project = serializer.from_migrated_document(migrated)
        conversion_elapsed_ms = (time.perf_counter() - conversion_started) * 1000.0
        codec_timings = serializer.last_load_phase_timings_ms
        phase_samples["project_graph_load_project_conversion_ms"].append(
            float(codec_timings.get("project_conversion_ms", conversion_elapsed_ms))
        )
        phase_samples["project_graph_load_registry_lookup_ms"].append(
            float(codec_timings.get("registry_lookup_ms", 0.0))
        )

        model_attach_started = time.perf_counter()
        model = GraphModel(project)
        model_attach_ms = (time.perf_counter() - model_attach_started) * 1000.0

        scene_population_started = time.perf_counter()
        scene, view = _bind_scene_for_workspace(
            app=app,
            model=model,
            registry=registry,
            workspace_id=workspace_id,
        )
        scene_bridge_population_ms = (
            time.perf_counter() - scene_population_started
        ) * 1000.0
        phase_samples["project_graph_load_scene_bridge_population_ms"].append(
            scene_bridge_population_ms
        )
        phase_samples["project_graph_load_visible_index_build_ms"].append(0.0)
        phase_samples["project_graph_load_edge_index_build_ms"].append(0.0)
        phase_samples["project_graph_load_first_model_attach_ms"].append(
            model_attach_ms + scene_bridge_population_ms
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        phase_samples["project_graph_load_ms"].append(elapsed_ms)
        view.deleteLater()
        scene.deleteLater()
        app.processEvents()

    return _ProjectGraphLoadBenchmarkSamples(phase_samples_ms=phase_samples)


def benchmark_load_times_ms(
    *, doc: dict[str, Any], workspace_id: str, iterations: int
) -> list[float]:
    return benchmark_project_graph_load_ms(
        doc=doc,
        workspace_id=workspace_id,
        iterations=iterations,
    ).total_ms


def _pan_zoom_target(
    *,
    current_center_x: float,
    current_center_y: float,
    current_zoom: float,
    left: float,
    right: float,
    top: float,
    bottom: float,
    random_gen: random.Random,
    index: int,
    zoom_min: float,
    zoom_max: float,
) -> tuple[float, float, float]:
    pan_x = max(
        left,
        min(right, current_center_x + random_gen.uniform(-180.0, 180.0)),
    )
    pan_y = max(
        top,
        min(bottom, current_center_y + random_gen.uniform(-120.0, 120.0)),
    )
    zoom_step = 1.05 if index % 2 == 0 else (1.0 / 1.05)
    zoom = max(zoom_min, min(zoom_max, current_zoom * zoom_step))
    return pan_x, pan_y, zoom


def _measure_pan_zoom_step(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    pan_to_x: float,
    pan_to_y: float,
    zoom_to: float,
) -> tuple[_MeasuredInteractionStep, _MeasuredInteractionStep]:
    canvas_host.begin_viewport_interaction()
    started = time.perf_counter()
    canvas_host.view.centerOn(pan_to_x, pan_to_y)
    canvas_host.note_viewport_interaction()
    pan_frame_start = _frame_timestamp_index(canvas_host)
    canvas_host.render_frame()
    pan_frame_end = _frame_timestamp_index(canvas_host)
    pan_elapsed_ms = (time.perf_counter() - started) * 1000.0
    pan_step = _MeasuredInteractionStep(
        elapsed_ms=pan_elapsed_ms,
        profiling_snapshot=canvas_host.collect_targeted_profiling_snapshot(),
        frame_timestamp_range=(pan_frame_start, pan_frame_end),
    )

    started = time.perf_counter()
    canvas_host.view.set_zoom(zoom_to)
    canvas_host.note_viewport_interaction()
    zoom_frame_start = _frame_timestamp_index(canvas_host)
    canvas_host.render_frame()
    zoom_frame_end = _frame_timestamp_index(canvas_host)
    zoom_elapsed_ms = (time.perf_counter() - started) * 1000.0
    zoom_step = _MeasuredInteractionStep(
        elapsed_ms=zoom_elapsed_ms,
        profiling_snapshot=canvas_host.collect_targeted_profiling_snapshot(),
        frame_timestamp_range=(zoom_frame_start, zoom_frame_end),
    )
    canvas_host.finish_viewport_interaction()
    canvas_host.wait_for_viewport_interaction_idle()
    return pan_step, zoom_step


def _node_drag_delta(sample_index: int) -> tuple[float, float]:
    sequence = (
        (16.0, 10.0),
        (-14.0, 8.0),
        (12.0, -9.0),
        (-18.0, -11.0),
    )
    return sequence[sample_index % len(sequence)]


def _measure_node_drag_control_step(
    canvas_host: _GraphCanvasBenchmarkHost, *, sample_index: int
) -> float:
    node_card = canvas_host.control_node_card()
    node_data = node_card.property("nodeData") or {}
    node_id = str(node_data.get("node_id", "")).strip()
    if not node_id:
        raise RuntimeError("Failed to resolve node id for node-drag control sampling")

    drag_offset_signal = getattr(node_card, "dragOffsetChanged", None)
    drag_canceled_signal = getattr(node_card, "dragCanceled", None)
    if drag_offset_signal is None or drag_canceled_signal is None:
        raise RuntimeError(
            "GraphNodeHost drag signals are unavailable for control sampling"
        )

    delta_x, delta_y = _node_drag_delta(sample_index)
    started = time.perf_counter()
    drag_offset_signal.emit(node_id, delta_x, delta_y)
    canvas_host.app.processEvents()
    canvas_host.render_frame()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    drag_canceled_signal.emit(node_id)
    canvas_host.app.processEvents()
    canvas_host.render_frame()
    return elapsed_ms


def _measure_node_drag_gesture(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    sample_index: int,
    offset_count: int = _NODE_DRAG_GESTURE_OFFSET_COUNT,
) -> _NodeDragGestureMeasurement:
    if offset_count < 2:
        raise ValueError("offset_count must be >= 2")
    node_card = canvas_host.control_node_card()
    node_data = node_card.property("nodeData") or {}
    node_id = str(node_data.get("node_id", "")).strip()
    if not node_id:
        raise RuntimeError("Failed to resolve node id for node-drag gesture sampling")

    drag_offset_signal = getattr(node_card, "dragOffsetChanged", None)
    drag_canceled_signal = getattr(node_card, "dragCanceled", None)
    if drag_offset_signal is None or drag_canceled_signal is None:
        raise RuntimeError(
            "GraphNodeHost drag signals are unavailable for gesture sampling"
        )

    freeze_before_value = canvas_host.canvas.property(
        "profileLiveDragMembershipFreezeCount"
    )
    membership_freeze_supported = freeze_before_value is not None
    freeze_before = int(freeze_before_value) if membership_freeze_supported else None
    final_dx, final_dy = _node_drag_delta(sample_index)
    first_offset_ms = 0.0
    steady_offset_ms: list[float] = []
    gesture_started = time.perf_counter()
    for offset_index in range(offset_count):
        progress = float(offset_index + 1) / float(offset_count)
        offset_started = time.perf_counter()
        drag_offset_signal.emit(node_id, final_dx * progress, final_dy * progress)
        canvas_host.app.processEvents()
        elapsed_ms = (time.perf_counter() - offset_started) * 1000.0
        if offset_index == 0:
            first_offset_ms = elapsed_ms
        else:
            steady_offset_ms.append(elapsed_ms)
    drag_frame_start = _frame_timestamp_index(canvas_host)
    canvas_host.render_frame()
    drag_frame_end = _frame_timestamp_index(canvas_host)
    full_gesture_ms = (time.perf_counter() - gesture_started) * 1000.0

    membership_freeze_count: int | None = None
    if membership_freeze_supported:
        freeze_after_value = canvas_host.canvas.property(
            "profileLiveDragMembershipFreezeCount"
        )
        if freeze_after_value is None:
            raise RuntimeError(
                "Node-drag membership-freeze counter disappeared during the gesture"
            )
        membership_freeze_count = int(freeze_after_value) - int(freeze_before)
        if membership_freeze_count != 1:
            raise RuntimeError(
                "Node-drag gesture must freeze membership exactly once; "
                f"observed {membership_freeze_count} freezes"
            )

    clear_started = time.perf_counter()
    drag_canceled_signal.emit(node_id)
    canvas_host.app.processEvents()
    clear_frame_start = _frame_timestamp_index(canvas_host)
    canvas_host.render_frame()
    clear_frame_end = _frame_timestamp_index(canvas_host)
    end_clear_ms = (time.perf_counter() - clear_started) * 1000.0
    if str(canvas_host.canvas.property("liveDragAnchorNodeId") or "").strip():
        raise RuntimeError("Node-drag gesture clear left live drag membership active")

    return _NodeDragGestureMeasurement(
        first_offset_ms=first_offset_ms,
        steady_offset_ms=tuple(steady_offset_ms),
        full_gesture_ms=full_gesture_ms,
        end_clear_ms=end_clear_ms,
        membership_freeze_supported=membership_freeze_supported,
        membership_freeze_count=membership_freeze_count,
        drag_frame_timestamp_range=(drag_frame_start, drag_frame_end),
        clear_frame_timestamp_range=(clear_frame_start, clear_frame_end),
    )


def _frame_timestamp_range_payload(value: tuple[int, int]) -> dict[str, int]:
    start_index, end_index = value
    return {
        "start_index": int(start_index),
        "end_index": int(end_index),
        "frame_count": max(0, int(end_index) - int(start_index)),
    }


def _frame_timestamp_index(canvas_host: Any) -> int:
    getter = getattr(canvas_host, "frame_render_timestamp_index", None)
    return int(getter()) if callable(getter) else 0


def _prepare_selected_drag_control(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    selection_size: int = 3,
) -> tuple[QQuickItem, tuple[str, ...]]:
    anchor_card = canvas_host.control_node_card()
    anchor_data = anchor_card.property("nodeData") or {}
    anchor_id = str(anchor_data.get("node_id", "")).strip()
    anchor_x = float(anchor_data.get("x", 0.0))
    anchor_y = float(anchor_data.get("y", 0.0))
    candidates: list[tuple[float, str, QQuickItem]] = []
    for node_card in canvas_host.node_cards():
        node_data = node_card.property("nodeData") or {}
        node_id = str(node_data.get("node_id", "")).strip()
        if not node_id or node_id == anchor_id:
            continue
        dx = float(node_data.get("x", 0.0)) - anchor_x
        dy = float(node_data.get("y", 0.0)) - anchor_y
        candidates.append((dx * dx + dy * dy, node_id, node_card))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if not anchor_id or len(candidates) < selection_size - 1:
        raise RuntimeError(
            "Supplemental selected-drag control requires "
            f"{selection_size} instantiated node cards; found {len(candidates) + bool(anchor_id)}"
        )
    selected = [
        (anchor_id, anchor_card),
        *[(item[1], item[2]) for item in candidates[: selection_size - 1]],
    ]
    selected_node_ids = tuple(item[0] for item in selected)
    canvas_host.scene.clear_selection()
    for index, node_id in enumerate(selected_node_ids):
        canvas_host.scene.select_node(node_id, index > 0)
    canvas_host.app.processEvents()
    canvas_host.render_frame()
    return selected[0][1], selected_node_ids


def _measure_selected_node_drag_gesture(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    node_card: QQuickItem,
    expected_membership_size: int,
    sample_index: int,
    offset_count: int = _NODE_DRAG_GESTURE_OFFSET_COUNT,
) -> _SelectedNodeDragGestureMeasurement:
    node_data = node_card.property("nodeData") or {}
    node_id = str(node_data.get("node_id", "")).strip()
    if not node_id:
        raise RuntimeError("Failed to resolve selected-drag anchor node id")
    drag_offset_signal = getattr(node_card, "dragOffsetChanged", None)
    drag_canceled_signal = getattr(node_card, "dragCanceled", None)
    if drag_offset_signal is None or drag_canceled_signal is None:
        raise RuntimeError(
            "GraphNodeHost drag signals are unavailable for selected-drag sampling"
        )

    scheduler = _find_quick_item_by_object_name(
        canvas_host.canvas, "graphCanvasFrameScheduler"
    )
    flush_scheduler = getattr(scheduler, "flushPendingRedraws", None)
    if not callable(flush_scheduler):
        raise RuntimeError(
            "Selected-drag control requires GraphCanvasFrameScheduler.flushPendingRedraws"
        )
    edge_layer = _find_quick_item_by_object_name(
        canvas_host.canvas, "graphCanvasEdgeLayer"
    )
    freeze_before = _optional_int_property(
        canvas_host.canvas, "profileLiveDragMembershipFreezeCount"
    )
    raw_before = _optional_int_property(scheduler, "rawLiveDragInputEventCount")
    flushed_before = _optional_int_property(scheduler, "flushedLiveDragUpdateCount")

    final_dx, final_dy = _node_drag_delta(sample_index)
    first_offset_ms = 0.0
    steady_offset_ms: list[float] = []
    gesture_started = time.perf_counter()
    for offset_index in range(offset_count):
        progress = float(offset_index + 1) / float(offset_count)
        offset_started = time.perf_counter()
        drag_offset_signal.emit(node_id, final_dx * progress, final_dy * progress)
        canvas_host.app.processEvents()
        elapsed_ms = (time.perf_counter() - offset_started) * 1000.0
        if offset_index == 0:
            first_offset_ms = elapsed_ms
        else:
            steady_offset_ms.append(elapsed_ms)

    flush_scheduler()
    membership_ids = _qml_list(canvas_host.canvas.property("liveDragNodeIds"))
    membership_size_supported = membership_ids is not None
    membership_size = len(membership_ids) if membership_ids is not None else None
    if membership_size_supported and membership_size != expected_membership_size:
        raise RuntimeError(
            "Selected-drag membership mismatch: "
            f"expected {expected_membership_size}, observed {membership_size}"
        )

    drag_frame_start = _frame_timestamp_index(canvas_host)
    render_timings_ms = canvas_host.render_frame(capture_timings=True) or {}
    drag_frame_end = _frame_timestamp_index(canvas_host)
    full_gesture_ms = (time.perf_counter() - gesture_started) * 1000.0

    freeze_after = _optional_int_property(
        canvas_host.canvas, "profileLiveDragMembershipFreezeCount"
    )
    membership_freeze_supported = freeze_before is not None and freeze_after is not None
    membership_freeze_count = (
        int(freeze_after) - int(freeze_before) if membership_freeze_supported else None
    )
    if membership_freeze_supported and membership_freeze_count != 1:
        raise RuntimeError(
            "Selected-drag gesture must freeze membership exactly once; "
            f"observed {membership_freeze_count} freezes"
        )
    raw_after = _optional_int_property(scheduler, "rawLiveDragInputEventCount")
    raw_input_count = (
        int(raw_after) - int(raw_before)
        if raw_before is not None and raw_after is not None
        else None
    )
    if raw_input_count is not None and raw_input_count != offset_count:
        raise RuntimeError(
            f"Selected-drag gesture expected {offset_count} raw inputs; observed {raw_input_count}"
        )
    flushed_after = _optional_int_property(scheduler, "flushedLiveDragUpdateCount")
    flushed_update_count = (
        int(flushed_after) - int(flushed_before)
        if flushed_before is not None and flushed_after is not None
        else None
    )
    incident_edge_count = _optional_int_property(
        edge_layer, "profileLastIncidentEdgeRefreshCount"
    )

    clear_started = time.perf_counter()
    drag_canceled_signal.emit(node_id)
    canvas_host.app.processEvents()
    flush_scheduler()
    clear_frame_start = _frame_timestamp_index(canvas_host)
    clear_render_timings_ms = canvas_host.render_frame(capture_timings=True) or {}
    clear_frame_end = _frame_timestamp_index(canvas_host)
    end_clear_ms = (time.perf_counter() - clear_started) * 1000.0
    if str(canvas_host.canvas.property("liveDragAnchorNodeId") or "").strip():
        raise RuntimeError("Selected-drag clear left live drag membership active")

    return _SelectedNodeDragGestureMeasurement(
        first_offset_ms=first_offset_ms,
        steady_offset_ms=tuple(steady_offset_ms),
        full_gesture_ms=full_gesture_ms,
        end_clear_ms=end_clear_ms,
        membership_freeze_supported=membership_freeze_supported,
        membership_freeze_count=membership_freeze_count,
        membership_size_supported=membership_size_supported,
        membership_size=membership_size,
        raw_input_count=raw_input_count,
        flushed_update_count=flushed_update_count,
        incident_edge_count=incident_edge_count,
        render_timings_ms={
            key: float(value) for key, value in render_timings_ms.items()
        },
        clear_render_timings_ms={
            key: float(value) for key, value in clear_render_timings_ms.items()
        },
        drag_frame_timestamp_range=(drag_frame_start, drag_frame_end),
        clear_frame_timestamp_range=(clear_frame_start, clear_frame_end),
    )


def _supplemental_selected_drag_payload(
    *,
    selected_node_ids: tuple[str, ...],
    measurements: list[_SelectedNodeDragGestureMeasurement],
    frame_interval_samples_ms: list[float],
) -> dict[str, Any]:
    membership_size_supported = bool(measurements) and all(
        measurement.membership_size_supported for measurement in measurements
    )
    membership_freeze_supported = bool(measurements) and all(
        measurement.membership_freeze_supported for measurement in measurements
    )
    membership_sizes = [measurement.membership_size for measurement in measurements]
    freeze_counts = [
        measurement.membership_freeze_count for measurement in measurements
    ]
    raw_input_counts = [measurement.raw_input_count for measurement in measurements]
    flushed_update_counts = [
        measurement.flushed_update_count for measurement in measurements
    ]
    render_phase_keys = (
        "render_callback_wait_ms",
        "readback_grab_ms",
        "post_readback_event_drain_ms",
        "render_frame_total_ms",
    )
    render_phase_timings_ms: dict[str, Any] = {}
    for prefix, attribute_name in (
        ("selected_drag", "render_timings_ms"),
        ("selected_clear", "clear_render_timings_ms"),
    ):
        for phase_key in render_phase_keys:
            samples = [
                float(getattr(measurement, attribute_name).get(phase_key, 0.0))
                for measurement in measurements
            ]
            render_phase_timings_ms[f"{prefix}_{phase_key}"] = {
                "samples": samples,
                "summary": _metric_summary_ms(samples),
            }
    first_offset_samples = [measurement.first_offset_ms for measurement in measurements]
    steady_offset_samples = [
        value for measurement in measurements for value in measurement.steady_offset_ms
    ]
    full_gesture_samples = [measurement.full_gesture_ms for measurement in measurements]
    end_clear_samples = [measurement.end_clear_ms for measurement in measurements]
    incident_edge_counts = [
        measurement.incident_edge_count for measurement in measurements
    ]
    expected_membership_size = len(selected_node_ids)
    return {
        "schema_version": 1,
        "kind": "selected_node_drag_supplemental",
        "supplemental_only": True,
        "formal_gate_metrics_unchanged": True,
        "offset_count": _NODE_DRAG_GESTURE_OFFSET_COUNT,
        "selected_node_ids": list(selected_node_ids),
        "expected_membership_size": expected_membership_size,
        "membership_size": {
            "supported": membership_size_supported,
            "samples": membership_sizes,
            "verified": (
                all(value == expected_membership_size for value in membership_sizes)
                if membership_size_supported
                else None
            ),
        },
        "membership_freeze": {
            "supported": membership_freeze_supported,
            "samples": freeze_counts,
            "verified": all(value == 1 for value in freeze_counts)
            if membership_freeze_supported
            else None,
        },
        "raw_input_count": {
            "supported": bool(measurements)
            and all(value is not None for value in raw_input_counts),
            "samples": raw_input_counts,
        },
        "flushed_update_count": {
            "supported": bool(measurements)
            and all(value is not None for value in flushed_update_counts),
            "samples": flushed_update_counts,
        },
        "incident_edge_count": {
            "supported": bool(measurements)
            and all(value is not None for value in incident_edge_counts),
            "samples": incident_edge_counts,
        },
        "metrics": {
            "first_offset_ms": {
                "samples": first_offset_samples,
                "summary": _metric_summary_ms(first_offset_samples),
            },
            "steady_offset_ms": {
                "samples": steady_offset_samples,
                "summary": _metric_summary_ms(steady_offset_samples),
            },
            "full_gesture_ms": {
                "samples": full_gesture_samples,
                "summary": _metric_summary_ms(full_gesture_samples),
            },
            "end_clear_ms": {
                "samples": end_clear_samples,
                "summary": _metric_summary_ms(end_clear_samples),
            },
            "frame_interval_ms_without_readback": {
                "samples": frame_interval_samples_ms,
                "summary": _metric_summary_ms(frame_interval_samples_ms),
            },
        },
        "render_phase_timings_ms": render_phase_timings_ms,
        "frame_timestamp_ranges": {
            "capture_scope": "supplemental_selected_drag",
            "selected_drag": [
                _frame_timestamp_range_payload(measurement.drag_frame_timestamp_range)
                for measurement in measurements
            ],
            "selected_clear": [
                _frame_timestamp_range_payload(measurement.clear_frame_timestamp_range)
                for measurement in measurements
            ],
        },
    }


def benchmark_pan_zoom_ms(
    *,
    doc: dict[str, Any],
    workspace_id: str,
    samples: int,
    warmup_samples: int,
    seed: int,
    zoom_min: float,
    zoom_max: float,
    scenario: str,
    expected_media_surface_count: int = 0,
) -> dict[str, Any]:
    if samples <= 0:
        raise ValueError("samples must be > 0")
    if warmup_samples < 0:
        raise ValueError("warmup_samples must be >= 0")
    app = QApplication.instance() or QApplication([])
    pan_samples_ms: list[float] = []
    zoom_samples_ms: list[float] = []
    node_drag_control_samples_ms: list[float] = []
    node_drag_first_offset_samples_ms: list[float] = []
    node_drag_steady_offset_samples_ms: list[float] = []
    node_drag_full_gesture_samples_ms: list[float] = []
    node_drag_end_clear_samples_ms: list[float] = []
    node_drag_membership_freeze_supported: bool | None = None
    node_drag_membership_freeze_samples: list[int | None] = []
    single_drag_frame_ranges: list[dict[str, int]] = []
    single_clear_frame_ranges: list[dict[str, int]] = []
    pan_frame_ranges: list[dict[str, int]] = []
    zoom_frame_ranges: list[dict[str, int]] = []
    setup_samples_ms: list[float] = []
    setup_phase_timings_ms = {phase_key: [] for phase_key in _CANVAS_SETUP_PHASE_KEYS}
    warmup_phase_samples_ms: list[float] = []
    frame_interval_samples_without_readback_ms: list[float] = []
    targeted_profiling_samples = _initialize_targeted_profiling_samples()
    renderer_diagnostics: dict[str, Any] = {}
    feature_parity: dict[str, Any] = {}
    supplemental_selected_drag: dict[str, Any] = {
        "schema_version": 1,
        "kind": "selected_node_drag_supplemental",
        "supplemental_only": True,
        "supported": False,
        "unavailable_reason": "GraphCanvas host was not initialized",
    }
    random_gen = random.Random(seed)
    left = right = top = bottom = 0.0
    current_center_x = 0.0
    current_center_y = 0.0
    current_zoom = 1.0

    canvas_host: _GraphCanvasBenchmarkHost | None = None
    try:
        setup_started = time.perf_counter()
        canvas_host = _GraphCanvasBenchmarkHost(
            app=app,
            doc=doc,
            workspace_id=workspace_id,
        )
        if expected_media_surface_count > 0 and scenario != _ANIMATED_MEDIA_SCENARIO:
            canvas_host.prepare_media_ready_view()
        canvas_host.wait_for_media_surfaces_ready(
            expected_count=expected_media_surface_count,
            require_ready=False,
        )
        setup_samples_ms.append((time.perf_counter() - setup_started) * 1000.0)
        for phase_key, elapsed_ms in canvas_host.setup_phase_timings_ms().items():
            setup_phase_timings_ms.setdefault(phase_key, []).append(float(elapsed_ms))
        renderer_diagnostics = canvas_host.renderer_diagnostics()
        canvas_host.apply_edge_renderer_policy(renderer_diagnostics)

        workspace = canvas_host.model.project.workspaces[workspace_id]
        left, right, top, bottom = _workspace_bounds(workspace)
        current_center_x = float(canvas_host.view.center_x)
        current_center_y = float(canvas_host.view.center_y)
        current_zoom = float(canvas_host.view.zoom)

        for index in range(warmup_samples):
            pan_x, pan_y, zoom = _pan_zoom_target(
                current_center_x=current_center_x,
                current_center_y=current_center_y,
                current_zoom=current_zoom,
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                random_gen=random_gen,
                index=index,
                zoom_min=zoom_min,
                zoom_max=zoom_max,
            )
            started = time.perf_counter()
            _measure_pan_zoom_step(
                canvas_host,
                pan_to_x=pan_x,
                pan_to_y=pan_y,
                zoom_to=zoom,
            )
            _measure_node_drag_control_step(canvas_host, sample_index=index)
            _measure_node_drag_gesture(canvas_host, sample_index=index)
            warmup_phase_samples_ms.append((time.perf_counter() - started) * 1000.0)
            current_center_x = pan_x
            current_center_y = pan_y
            current_zoom = zoom

        canvas_host.reset_frame_interval_capture()

        for index in range(samples):
            node_drag_control_samples_ms.append(
                _measure_node_drag_control_step(
                    canvas_host, sample_index=warmup_samples + index
                )
            )
            gesture = _measure_node_drag_gesture(
                canvas_host,
                sample_index=warmup_samples + index,
            )
            node_drag_first_offset_samples_ms.append(gesture.first_offset_ms)
            node_drag_steady_offset_samples_ms.extend(gesture.steady_offset_ms)
            node_drag_full_gesture_samples_ms.append(gesture.full_gesture_ms)
            node_drag_end_clear_samples_ms.append(gesture.end_clear_ms)
            single_drag_frame_ranges.append(
                _frame_timestamp_range_payload(gesture.drag_frame_timestamp_range)
            )
            single_clear_frame_ranges.append(
                _frame_timestamp_range_payload(gesture.clear_frame_timestamp_range)
            )
            if node_drag_membership_freeze_supported is None:
                node_drag_membership_freeze_supported = (
                    gesture.membership_freeze_supported
                )
            elif (
                node_drag_membership_freeze_supported
                != gesture.membership_freeze_supported
            ):
                raise RuntimeError(
                    "Node-drag membership-freeze counter support changed during sampling"
                )
            node_drag_membership_freeze_samples.append(gesture.membership_freeze_count)

        for index in range(samples):
            pan_x, pan_y, zoom = _pan_zoom_target(
                current_center_x=current_center_x,
                current_center_y=current_center_y,
                current_zoom=current_zoom,
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                random_gen=random_gen,
                index=warmup_samples + index,
                zoom_min=zoom_min,
                zoom_max=zoom_max,
            )
            pan_step, zoom_step = _measure_pan_zoom_step(
                canvas_host,
                pan_to_x=pan_x,
                pan_to_y=pan_y,
                zoom_to=zoom,
            )
            pan_samples_ms.append(pan_step.elapsed_ms)
            zoom_samples_ms.append(zoom_step.elapsed_ms)
            pan_frame_ranges.append(
                _frame_timestamp_range_payload(pan_step.frame_timestamp_range)
            )
            zoom_frame_ranges.append(
                _frame_timestamp_range_payload(zoom_step.frame_timestamp_range)
            )
            _append_targeted_profiling_sample(
                targeted_profiling_samples,
                phase="pan",
                snapshot=pan_step.profiling_snapshot,
            )
            _append_targeted_profiling_sample(
                targeted_profiling_samples,
                phase="zoom",
                snapshot=zoom_step.profiling_snapshot,
            )
            current_center_x = pan_x
            current_center_y = pan_y
            current_zoom = zoom

        frame_interval_samples_without_readback_ms = (
            canvas_host.frame_interval_samples_without_readback_ms()
        )
        feature_parity = canvas_host.collect_feature_parity_snapshot(
            expected_media_surface_count=expected_media_surface_count
        )

        try:
            selected_node_card, selected_node_ids = _prepare_selected_drag_control(
                canvas_host
            )
        except RuntimeError as exc:
            supplemental_selected_drag = {
                "schema_version": 1,
                "kind": "selected_node_drag_supplemental",
                "supplemental_only": True,
                "supported": False,
                "unavailable_reason": str(exc),
                "membership_size": {
                    "supported": False,
                    "samples": [None],
                    "verified": None,
                },
                "membership_freeze": {
                    "supported": False,
                    "samples": [None],
                    "verified": None,
                },
            }
        else:
            for index in range(warmup_samples):
                _measure_selected_node_drag_gesture(
                    canvas_host,
                    node_card=selected_node_card,
                    expected_membership_size=len(selected_node_ids),
                    sample_index=index,
                )
            canvas_host.reset_frame_interval_capture()
            selected_measurements = [
                _measure_selected_node_drag_gesture(
                    canvas_host,
                    node_card=selected_node_card,
                    expected_membership_size=len(selected_node_ids),
                    sample_index=warmup_samples + index,
                )
                for index in range(samples)
            ]
            supplemental_selected_drag = _supplemental_selected_drag_payload(
                selected_node_ids=selected_node_ids,
                measurements=selected_measurements,
                frame_interval_samples_ms=canvas_host.frame_interval_samples_without_readback_ms(),
            )
            supplemental_selected_drag["supported"] = True
            selected_node_card = None
            canvas_host.scene.clear_selection()
            canvas_host.app.processEvents()
            scheduler = _find_quick_item_by_object_name(
                canvas_host.canvas,
                "graphCanvasFrameScheduler",
            )
            flush_scheduler = getattr(scheduler, "flushPendingRedraws", None)
            if callable(flush_scheduler):
                flush_scheduler()
            canvas_host.render_frame()
            canvas_host.app.processEvents()
            flush_scheduler = None
            scheduler = None
    finally:
        if canvas_host is not None:
            canvas_host.close()

    return _InteractionBenchmarkSamples(
        setup_ms=setup_samples_ms,
        setup_phase_timings_ms=setup_phase_timings_ms,
        warmup_ms=warmup_phase_samples_ms,
        pan_ms=pan_samples_ms,
        zoom_ms=zoom_samples_ms,
        node_drag_control_ms=node_drag_control_samples_ms,
        node_drag_first_offset_ms=node_drag_first_offset_samples_ms,
        node_drag_steady_offset_ms=node_drag_steady_offset_samples_ms,
        node_drag_full_gesture_ms=node_drag_full_gesture_samples_ms,
        node_drag_end_clear_ms=node_drag_end_clear_samples_ms,
        node_drag_membership_freeze_supported=node_drag_membership_freeze_supported
        is True,
        node_drag_membership_freeze_count=node_drag_membership_freeze_samples,
        frame_interval_ms_without_readback=frame_interval_samples_without_readback_ms,
        frame_timestamp_ranges={
            "capture_scope": "aggregate_continuity_metric",
            "single_drag": single_drag_frame_ranges,
            "single_clear": single_clear_frame_ranges,
            "pan": pan_frame_ranges,
            "zoom": zoom_frame_ranges,
        },
        supplemental_selected_drag=supplemental_selected_drag,
        targeted_profiling_samples=targeted_profiling_samples,
        renderer_diagnostics=renderer_diagnostics,
        feature_parity=feature_parity,
        warmup_samples=warmup_samples,
        scenario=scenario,
        media_surface_count=(
            int(
                feature_parity.get("embedded_media_count", expected_media_surface_count)
            )
            if scenario == _ANIMATED_MEDIA_SCENARIO
            else expected_media_surface_count
        ),
    ).to_payload()


def _node_insertion_profile_contracts() -> list[dict[str, Any]]:
    return [
        {
            "profile": "ordinary_node",
            "dispatch_path": "GraphSceneBridge.add_node_from_type(core.logger)",
            "inserted_node_count": 1,
            "inserted_edge_count": 0,
            "expected_primary_delegate_count": 1,
        },
        {
            "profile": "group_backdrop",
            "dispatch_path": (
                "GraphSceneBridge.add_node_from_type(passive.annotation.group_backdrop)"
            ),
            "inserted_node_count": 1,
            "inserted_edge_count": 0,
            "expected_primary_delegate_count": 1,
            "group_backdrop_input_helper_is_diagnostic_only": True,
        },
        {
            "profile": "small_custom_workflow",
            "dispatch_path": "GraphSceneBridge.paste_subgraph_fragment",
            "inserted_node_count": 2,
            "inserted_edge_count": 1,
            "expected_primary_delegate_count": 2,
        },
        {
            "profile": "nested_custom_workflow",
            "dispatch_path": "GraphSceneBridge.paste_subgraph_fragment",
            "inserted_node_count": 2,
            "inserted_edge_count": 0,
            "expected_primary_delegate_count": 1,
            "nested_child_readiness_excluded": True,
        },
    ]


def _node_insertion_fragment_node_payload(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    ref_id: str,
    type_id: str,
    title: str,
    x: float,
    y: float,
    parent_node_id: str | None = None,
) -> dict[str, Any]:
    spec = canvas_host.registry.get_spec(type_id)
    node = NodeInstance(
        node_id=ref_id,
        type_id=type_id,
        title=title,
        x=float(x),
        y=float(y),
        properties=canvas_host.registry.default_properties(type_id),
        exposed_ports={port.key: port.exposed for port in spec.ports},
        parent_node_id=parent_node_id,
    )
    return node_instance_to_mapping(node, node_id_key="ref_id")


def _node_insertion_fragment_payload(
    canvas_host: _GraphCanvasBenchmarkHost,
    profile: str,
) -> dict[str, Any]:
    if profile == "small_custom_workflow":
        nodes = [
            _node_insertion_fragment_node_payload(
                canvas_host,
                ref_id="source",
                type_id=_ACTIVE_DATA_NODE_TYPE,
                title="Source Transform",
                x=0.0,
                y=0.0,
            ),
            _node_insertion_fragment_node_payload(
                canvas_host,
                ref_id="target",
                type_id=_ACTIVE_DATA_NODE_TYPE,
                title="Target Transform",
                x=260.0,
                y=0.0,
            ),
        ]
        edge = EdgeInstance(
            edge_id="",
            source_node_id="source",
            source_port_key=_ACTIVE_DATA_SOURCE_PORT,
            target_node_id="target",
            target_port_key=_ACTIVE_DATA_TARGET_PORT,
            enabled=True,
            input_order=0,
        )
        return build_graph_fragment_payload(
            nodes=nodes,
            edges=[
                edge_instance_to_mapping(
                    edge,
                    edge_id_key=None,
                    source_node_id_key="source_ref_id",
                    target_node_id_key="target_ref_id",
                )
            ],
        )
    if profile == "nested_custom_workflow":
        return build_graph_fragment_payload(
            nodes=[
                _node_insertion_fragment_node_payload(
                    canvas_host,
                    ref_id="subnode",
                    type_id="core.subnode",
                    title="Nested Workflow",
                    x=0.0,
                    y=0.0,
                ),
                _node_insertion_fragment_node_payload(
                    canvas_host,
                    ref_id="nested_logger",
                    type_id="core.logger",
                    title="Nested Logger",
                    x=120.0,
                    y=100.0,
                    parent_node_id="subnode",
                ),
            ],
            edges=[],
        )
    raise ValueError(f"Unsupported node insertion fragment profile: {profile}")


def _quick_item_node_id(item: Any) -> str:
    node_data = item.property("nodeData")
    if not isinstance(node_data, Mapping):
        return ""
    return str(node_data.get("node_id", "")).strip()


def _quick_item_is_presented(item: Any) -> bool:
    visible_getter = getattr(item, "isVisible", None)
    visible = (
        bool(visible_getter())
        if callable(visible_getter)
        else bool(item.property("visible"))
    )
    width_getter = getattr(item, "width", None)
    height_getter = getattr(item, "height", None)
    width = (
        float(width_getter())
        if callable(width_getter)
        else float(item.property("width") or 0.0)
    )
    height = (
        float(height_getter())
        if callable(height_getter)
        else float(item.property("height") or 0.0)
    )
    return visible and width > 0.0 and height > 0.0


def _wait_for_node_insertion_presented_frame(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    primary_node_ids: list[str],
    frame_start_index: int,
    group_backdrop_node_id: str = "",
    timeout_ms: int = 3000,
) -> dict[str, Any]:
    expected_ids = set(primary_node_ids)
    delegates_observed_frame_index: int | None = None
    presented_ids: set[str] = set()
    group_backdrop_helper_present = False
    deadline = time.perf_counter() + (float(timeout_ms) / 1000.0)
    while time.perf_counter() < deadline:
        canvas_host.app.processEvents()
        presented_ids = {
            node_id
            for card in canvas_host.node_cards()
            if (node_id := _quick_item_node_id(card)) and _quick_item_is_presented(card)
        }
        if group_backdrop_node_id:
            group_backdrop_helper_present = any(
                _quick_item_node_id(card) == group_backdrop_node_id
                for card in canvas_host.group_backdrop_input_cards()
            )
        if expected_ids.issubset(presented_ids):
            if delegates_observed_frame_index is None:
                delegates_observed_frame_index = _frame_timestamp_index(canvas_host)
                canvas_host.window.update()
            elif _frame_timestamp_index(canvas_host) > delegates_observed_frame_index:
                completion_frame_index = _frame_timestamp_index(canvas_host)
                return {
                    "presented_primary_node_ids": sorted(expected_ids),
                    "presented_primary_delegate_count": len(expected_ids),
                    "completion_frame_count": max(
                        0,
                        completion_frame_index - int(frame_start_index),
                    ),
                    "group_backdrop_input_helper_present_at_completion": group_backdrop_helper_present,
                }
        else:
            delegates_observed_frame_index = None
            canvas_host.window.update()
        time.sleep(0.001)
    missing_ids = sorted(expected_ids.difference(presented_ids))
    raise RuntimeError(
        "Timed out waiting for inserted primary delegates and a later afterRendering frame "
        f"(missing_node_ids={missing_ids}, frame_start_index={frame_start_index}, "
        f"frame_end_index={_frame_timestamp_index(canvas_host)})"
    )


def _dispatch_node_insertion_profile(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    profile: str,
    x: float,
    y: float,
) -> tuple[list[str], list[str]]:
    workspace = canvas_host.model.project.workspaces[canvas_host.workspace_id]
    before_node_ids = set(workspace.nodes)
    before_edge_ids = set(workspace.edges)
    if profile == "ordinary_node":
        node_id = canvas_host.scene.add_node_from_type(
            "core.logger", x=float(x), y=float(y)
        )
        if not node_id:
            raise RuntimeError("Ordinary node insertion returned no node id")
    elif profile == "group_backdrop":
        node_id = canvas_host.scene.add_node_from_type(
            "passive.annotation.group_backdrop",
            x=float(x),
            y=float(y),
        )
        if not node_id:
            raise RuntimeError("Group backdrop insertion returned no node id")
    elif profile in {"small_custom_workflow", "nested_custom_workflow"}:
        fragment = _node_insertion_fragment_payload(canvas_host, profile)
        if not canvas_host.scene.paste_subgraph_fragment(fragment, float(x), float(y)):
            raise RuntimeError(f"{profile} fragment insertion failed")
    else:
        raise ValueError(f"Unsupported node insertion profile: {profile}")

    inserted_node_ids = [
        node_id for node_id in workspace.nodes if node_id not in before_node_ids
    ]
    inserted_edge_ids = [
        edge_id for edge_id in workspace.edges if edge_id not in before_edge_ids
    ]
    return inserted_node_ids, inserted_edge_ids


def _cleanup_node_insertion_sample(
    canvas_host: _GraphCanvasBenchmarkHost,
    inserted_node_ids: list[str],
    history: RuntimeGraphHistory,
) -> None:
    workspace = canvas_host.model.project.workspaces[canvas_host.workspace_id]
    inserted_id_set = set(inserted_node_ids)

    def _inserted_depth(node_id: str) -> int:
        depth = 0
        parent_id = getattr(workspace.nodes.get(node_id), "parent_node_id", None)
        while parent_id in inserted_id_set:
            depth += 1
            parent_id = getattr(workspace.nodes.get(parent_id), "parent_node_id", None)
        return depth

    for node_id in sorted(inserted_node_ids, key=_inserted_depth, reverse=True):
        if node_id in workspace.nodes:
            canvas_host.scene.remove_workspace_node(node_id)
    canvas_host.app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    canvas_host.app.processEvents()
    remaining_ids = sorted(
        node_id for node_id in inserted_node_ids if node_id in workspace.nodes
    )
    if remaining_ids:
        raise RuntimeError(
            f"Node insertion benchmark cleanup left nodes behind: {remaining_ids}"
        )
    history.clear_workspace(canvas_host.workspace_id)


def _measure_node_insertion_profile(
    canvas_host: _GraphCanvasBenchmarkHost,
    *,
    history: RuntimeGraphHistory,
    profile: str,
    sample_index: int,
) -> dict[str, Any]:
    workspace = canvas_host.model.project.workspaces[canvas_host.workspace_id]
    expected_contract = next(
        item
        for item in _node_insertion_profile_contracts()
        if item["profile"] == profile
    )
    center = canvas_host.visible_scene_rect().center()
    frame_start_index = _frame_timestamp_index(canvas_host)
    started = time.perf_counter()
    inserted_node_ids, inserted_edge_ids = _dispatch_node_insertion_profile(
        canvas_host,
        profile=profile,
        x=float(center.x()),
        y=float(center.y()),
    )
    model_commit_ms = (time.perf_counter() - started) * 1000.0
    active_parent_id = scope_parent_id(canvas_host.scene.active_scope_path)
    primary_node_ids = [
        node_id
        for node_id in inserted_node_ids
        if workspace.nodes[node_id].parent_node_id == active_parent_id
    ]
    expected_node_count = int(expected_contract["inserted_node_count"])
    expected_edge_count = int(expected_contract["inserted_edge_count"])
    expected_primary_count = int(expected_contract["expected_primary_delegate_count"])
    observed_counts = (
        len(inserted_node_ids),
        len(inserted_edge_ids),
        len(primary_node_ids),
    )
    expected_counts = (expected_node_count, expected_edge_count, expected_primary_count)
    if observed_counts != expected_counts:
        _cleanup_node_insertion_sample(canvas_host, inserted_node_ids, history)
        raise RuntimeError(
            f"Node insertion profile {profile} inserted counts {observed_counts}; "
            f"expected {expected_counts}"
        )
    group_backdrop_node_id = inserted_node_ids[0] if profile == "group_backdrop" else ""
    completion = _wait_for_node_insertion_presented_frame(
        canvas_host,
        primary_node_ids=primary_node_ids,
        frame_start_index=frame_start_index,
        group_backdrop_node_id=group_backdrop_node_id,
    )
    presented_ms = (time.perf_counter() - started) * 1000.0
    undo_depth = history.undo_depth(canvas_host.workspace_id)
    if undo_depth != 1:
        _cleanup_node_insertion_sample(canvas_host, inserted_node_ids, history)
        raise RuntimeError(
            f"Node insertion profile {profile} recorded {undo_depth} undo entries; expected 1"
        )
    sample = {
        "profile": profile,
        "sample_index": int(sample_index),
        "dispatch_to_model_commit_ms": model_commit_ms,
        "all_primary_delegates_presented_ms": presented_ms,
        "inserted_node_count": len(inserted_node_ids),
        "inserted_edge_count": len(inserted_edge_ids),
        "expected_primary_delegate_count": len(primary_node_ids),
        "undo_entry_count": undo_depth,
        "group_backdrop_input_helper_expected": profile == "group_backdrop",
        **completion,
    }
    _cleanup_node_insertion_sample(canvas_host, inserted_node_ids, history)
    return sample


def _node_insertion_display_validity(
    *,
    renderer_diagnostics: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    qt_platform = str(
        renderer_diagnostics.get("qt_qpa_platform")
        or environment.get("qt_qpa_platform")
        or ""
    )
    normalized_platform = _normalized_qt_platform_name(qt_platform)
    graphics_api = str(renderer_diagnostics.get("graphics_api", ""))
    graphics_api_label = str(renderer_diagnostics.get("graphics_api_label", ""))
    rhi_backend = str(
        renderer_diagnostics.get("qsg_rhi_backend")
        or renderer_diagnostics.get("qtquick_backend_selected")
        or environment.get("qsg_rhi_backend")
        or environment.get("qtquick_backend_selected")
        or ""
    )
    api_facts = " ".join((graphics_api, graphics_api_label, rhi_backend)).lower()
    d3d11_active = any(
        token in api_facts for token in ("d3d11", "direct3d11", "direct3d 11")
    )
    software_fallback_active = bool(
        renderer_diagnostics.get("software_fallback_active", False)
    )
    if not software_fallback_active:
        software_fallback_active = "software" in api_facts
    blockers: list[str] = []
    if normalized_platform != "windows":
        blockers.append(
            f"QT_QPA_PLATFORM={qt_platform or '<unset>'} is not Windows display-attached"
        )
    if not d3d11_active:
        blockers.append(
            "active Qt Quick graphics API is not D3D11 "
            f"(graphics_api={graphics_api or '<unknown>'}, rhi_backend={rhi_backend or '<unknown>'})"
        )
    if software_fallback_active:
        blockers.append("Qt Quick software fallback is active")
    return {
        "valid": not blockers,
        "qt_platform": qt_platform,
        "windows_display_attached": normalized_platform == "windows",
        "graphics_api": graphics_api,
        "graphics_api_label": graphics_api_label,
        "rhi_backend": rhi_backend,
        "d3d11_active": d3d11_active,
        "software_fallback_active": software_fallback_active,
        "blockers": blockers,
    }


def _node_insertion_report_payload(
    *,
    samples: list[dict[str, Any]],
    sample_budget: int,
    warmup_samples_per_profile: int,
    renderer_diagnostics: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    display_validity = _node_insertion_display_validity(
        renderer_diagnostics=renderer_diagnostics,
        environment=environment,
    )
    profile_summaries: dict[str, Any] = {}
    expected_profile_counts = Counter(
        _NODE_INSERTION_PROFILES[index % len(_NODE_INSERTION_PROFILES)]
        for index in range(sample_budget)
    )
    for profile in _NODE_INSERTION_PROFILES:
        profile_samples = [
            sample for sample in samples if sample.get("profile") == profile
        ]
        dispatch_samples = [
            float(sample["dispatch_to_model_commit_ms"]) for sample in profile_samples
        ]
        presented_samples = [
            float(sample["all_primary_delegates_presented_ms"])
            for sample in profile_samples
        ]
        presented_summary = _metric_summary_ms(presented_samples)
        if not display_validity["valid"]:
            acceptance_status = "INVALID"
        elif len(profile_samples) != expected_profile_counts[profile]:
            acceptance_status = "FAIL"
        else:
            acceptance_status = (
                "PASS"
                if presented_summary["p95"] < _NODE_INSERTION_P95_TARGET_MS
                else "FAIL"
            )
        profile_summaries[profile] = {
            "sample_count": len(profile_samples),
            "expected_sample_count": expected_profile_counts[profile],
            "dispatch_to_model_commit_ms": {
                "samples": dispatch_samples,
                "summary": _metric_summary_ms(dispatch_samples),
            },
            "all_primary_delegates_presented_ms": {
                "samples": presented_samples,
                "summary": presented_summary,
            },
            "inserted_node_count": max(
                (
                    int(sample.get("inserted_node_count", 0))
                    for sample in profile_samples
                ),
                default=0,
            ),
            "inserted_edge_count": max(
                (
                    int(sample.get("inserted_edge_count", 0))
                    for sample in profile_samples
                ),
                default=0,
            ),
            "expected_primary_delegate_count": max(
                (
                    int(sample.get("expected_primary_delegate_count", 0))
                    for sample in profile_samples
                ),
                default=0,
            ),
            "undo_entry_count": max(
                (int(sample.get("undo_entry_count", 0)) for sample in profile_samples),
                default=0,
            ),
            "group_backdrop_input_helper_present_for_all_samples": (
                all(
                    bool(
                        sample.get("group_backdrop_input_helper_present_at_completion", False)
                    )
                    for sample in profile_samples
                )
                if profile == "group_backdrop" and profile_samples
                else None
            ),
            "acceptance": {
                "status": acceptance_status,
                "target_p95_ms": _NODE_INSERTION_P95_TARGET_MS,
                "strictly_less_than_target": True,
            },
        }
    if not display_validity["valid"]:
        overall_status = "INVALID"
    elif all(
        summary["acceptance"]["status"] == "PASS"
        for summary in profile_summaries.values()
    ):
        overall_status = "PASS"
    else:
        overall_status = "FAIL"
    return {
        "kind": "node_insertion_latency",
        "status": "measured",
        "scenario": _NODE_INSERTIONS_SCENARIO,
        "threshold_policy": "display_attached_windows_d3d11_p95_strictly_under_100ms",
        "target_p95_ms": _NODE_INSERTION_P95_TARGET_MS,
        "sample_budget": int(sample_budget),
        "warmup_samples_per_profile": int(warmup_samples_per_profile),
        "sample_count": len(samples),
        "profiles": list(_NODE_INSERTION_PROFILES),
        "profile_contracts": _node_insertion_profile_contracts(),
        "measurement_contract": {
            "completion_semantics": _NODE_INSERTION_COMPLETION_SEMANTICS,
            "primary_delegate_object_name": "graphNodeCard",
            "completion_callback": "QQuickWindow.afterRendering",
            "grab_window_readback_included": False,
            "screenshot_readback_included": False,
            "heavy_content_readiness_included": False,
            "nested_child_delegate_readiness_included": False,
            "group_backdrop_input_helper_gates_completion": False,
            "undo_history_included_in_dispatch_timing": True,
            "shell_drag_or_quick_insert_open_filter_time_included": False,
            "timed_entry_scope": "confirmed insertion dispatch through presented primary delegates",
        },
        "samples": samples,
        "profile_summaries": profile_summaries,
        "display_validity": display_validity,
        "acceptance_result": {
            "status": overall_status,
            "pass": overall_status == "PASS",
            "target_p95_ms": _NODE_INSERTION_P95_TARGET_MS,
        },
    }


def benchmark_node_insertions_ms(
    *,
    doc: dict[str, Any],
    workspace_id: str,
    samples: int = 40,
    warmup_samples: int = 3,
) -> dict[str, Any]:
    if samples <= 0:
        raise ValueError("node insertion samples must be > 0")
    if warmup_samples < 0:
        raise ValueError("node insertion warmup samples must be >= 0")
    app = QApplication.instance() or QApplication([])
    canvas_host: _GraphCanvasBenchmarkHost | None = None
    try:
        canvas_host = _GraphCanvasBenchmarkHost(
            app=app,
            doc=doc,
            workspace_id=workspace_id,
        )
        history = RuntimeGraphHistory()
        canvas_host.scene.bind_runtime_history(history)
        renderer_diagnostics = canvas_host.renderer_diagnostics()
        canvas_host.apply_edge_renderer_policy(renderer_diagnostics)
        canvas_host.render_frame()
        feature_parity = canvas_host.collect_feature_parity_snapshot(
            expected_media_surface_count=0
        )
        workspace = canvas_host.model.project.workspaces[workspace_id]
        fixture_graph_size = {
            "nodes": len(workspace.nodes),
            "edges": len(workspace.edges),
        }
        measured_samples: list[dict[str, Any]] = []
        for profile in _NODE_INSERTION_PROFILES:
            for warmup_index in range(warmup_samples):
                _measure_node_insertion_profile(
                    canvas_host,
                    history=history,
                    profile=profile,
                    sample_index=warmup_index - warmup_samples,
                )
        profile_sample_indices: Counter[str] = Counter()
        for profile in (
            _NODE_INSERTION_PROFILES[index % len(_NODE_INSERTION_PROFILES)]
            for index in range(samples)
        ):
            measured_samples.append(
                _measure_node_insertion_profile(
                    canvas_host,
                    history=history,
                    profile=profile,
                    sample_index=profile_sample_indices[profile],
                )
            )
            profile_sample_indices[profile] += 1
        report = _node_insertion_report_payload(
            samples=measured_samples,
            sample_budget=samples,
            warmup_samples_per_profile=warmup_samples,
            renderer_diagnostics=renderer_diagnostics,
            environment=_collect_environment_snapshot(),
        )
        report.update(
            {
                "render_path": _graph_canvas_qml_path()
                .relative_to(_repo_root_path())
                .as_posix(),
                "uses_actual_canvas_render_path": True,
                "fixture_graph_size": fixture_graph_size,
                "renderer_diagnostics": renderer_diagnostics,
                "edge_renderer_kind": feature_parity.get("edge_renderer_kind", ""),
            }
        )
        return report
    finally:
        if canvas_host is not None:
            canvas_host.close()


def _run_single_benchmark(config: BenchmarkConfig) -> dict[str, Any]:
    process = psutil.Process()
    process_wall_started = time.perf_counter()
    process_cpu_started = _process_cpu_seconds(process)
    process_rss_started = int(process.memory_info().rss)
    app = QApplication.instance() or QApplication([])
    _ = app
    scenario = _scenario_label_for_config(config)

    with _build_scenario_project(config) as scenario_project:
        project = scenario_project.project
        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_document(project)
        workspace_id = scenario_project.workspace_id or project.active_workspace_id

        load_benchmark = benchmark_project_graph_load_ms(
            doc=doc,
            workspace_id=workspace_id,
            iterations=config.load_iterations,
        )
        load_samples = load_benchmark.total_ms
        interaction_samples = benchmark_pan_zoom_ms(
            doc=doc,
            workspace_id=workspace_id,
            samples=config.interaction_samples,
            warmup_samples=config.interaction_warmup_samples,
            seed=config.synthetic_graph.seed,
            zoom_min=config.interaction_zoom_min,
            zoom_max=config.interaction_zoom_max,
            scenario=scenario,
            expected_media_surface_count=int(
                scenario_project.scenario_details["expected_media_surface_count"]
            ),
        )
        node_insertion_benchmark: dict[str, Any] = {}
        if scenario == _NODE_INSERTIONS_SCENARIO:
            node_insertion_benchmark = benchmark_node_insertions_ms(
                doc=doc,
                workspace_id=workspace_id,
                samples=config.node_insertion_samples,
                warmup_samples=config.node_insertion_warmup_samples,
            )

    pan_summary = _metric_summary_ms(interaction_samples["pan_ms"])
    zoom_summary = _metric_summary_ms(interaction_samples["zoom_ms"])
    combined_summary = _metric_summary_ms(interaction_samples["combined_ms"])
    node_drag_control_summary = _metric_summary_ms(
        interaction_samples["node_drag_control_ms"]
    )
    node_drag_first_offset_summary = _metric_summary_ms(
        interaction_samples["node_drag_first_offset_ms"]
    )
    node_drag_steady_offset_summary = _metric_summary_ms(
        interaction_samples["node_drag_steady_offset_ms"]
    )
    node_drag_full_gesture_summary = _metric_summary_ms(
        interaction_samples["node_drag_full_gesture_ms"]
    )
    node_drag_end_clear_summary = _metric_summary_ms(
        interaction_samples["node_drag_end_clear_ms"]
    )
    frame_interval_without_readback_summary = _metric_summary_ms(
        interaction_samples["frame_interval_ms_without_readback"]
    )
    load_summary = _metric_summary_ms(load_samples)
    mutation_benchmark_contract = _mutation_benchmark_contract_payload()
    mutation_phase_instrumentation = _mutation_phase_instrumentation_payload()
    interaction_frame_p95 = max(
        pan_summary["p95"],
        zoom_summary["p95"],
        node_drag_steady_offset_summary["p95"],
    )
    phase_timings_ms = {
        **load_benchmark.phase_timings_payload(),
        **interaction_samples["phase_timings_ms"],
    }
    renderer_diagnostics = interaction_samples.get("renderer_diagnostics", {})
    feature_parity = interaction_samples.get("feature_parity", {})
    feature_parity_pass = bool(feature_parity.get("pass", True))
    interaction_benchmark = interaction_samples["benchmark"]
    supplemental_selected_drag = interaction_samples.get(
        "supplemental_selected_drag", {}
    )
    fixture_metadata = _augment_fixture_metadata(
        scenario_project.scenario_details.get("fixture_metadata", {}),
        renderer_diagnostics=renderer_diagnostics,
        interaction_benchmark=interaction_benchmark,
    )
    if fixture_metadata:
        scenario_project.scenario_details["fixture_metadata"] = fixture_metadata
    graph_mutation_benchmark: dict[str, Any] = {}
    if scenario == _GRAPH_MUTATIONS_SCENARIO:
        graph_mutation_benchmark = benchmark_graph_mutations_ms(
            doc=doc,
            workspace_id=workspace_id,
            samples=config.interaction_samples,
            fixture_metadata=fixture_metadata,
            scenarios=config.mutation_scenarios,
        )
    current_baseline_metrics = _current_baseline_metrics_payload(
        load_summary=load_summary,
        pan_summary=pan_summary,
        zoom_summary=zoom_summary,
        combined_summary=combined_summary,
        node_drag_control_summary=node_drag_control_summary,
        node_drag_first_offset_summary=node_drag_first_offset_summary,
        node_drag_steady_offset_summary=node_drag_steady_offset_summary,
        node_drag_full_gesture_summary=node_drag_full_gesture_summary,
        node_drag_end_clear_summary=node_drag_end_clear_summary,
        frame_interval_without_readback_summary=frame_interval_without_readback_summary,
        fixture_metadata=fixture_metadata,
    )
    stress_1200_bottleneck_breakdown = _stress_1200_bottleneck_breakdown(
        phase_timings_ms=phase_timings_ms,
        profiling_counts=interaction_samples["profiling_counts"],
        renderer_diagnostics=renderer_diagnostics,
        interaction_benchmark=interaction_benchmark,
    )
    edge_renderer_ab = _edge_renderer_ab_payload(
        interaction_benchmark=interaction_benchmark,
        feature_parity=feature_parity,
        phase_timings_ms=phase_timings_ms,
        profiling_counts=interaction_samples["profiling_counts"],
    )
    fixture_source_kind = str(fixture_metadata.get("fixture_source_kind", "")).strip()
    display_source_pass = (
        not fixture_metadata
        or fixture_source_kind == "project"
        or bool(fixture_metadata.get("display_acceptance_eligible", False))
    )
    if not fixture_metadata:
        display_source_details = "No fixture-backed stress evidence selected"
    elif fixture_source_kind == "project":
        display_source_details = (
            "Project fixture regression source; stress display acceptance not requested"
        )
    elif display_source_pass:
        display_source_details = (
            "Real fixture source is eligible for display-attached acceptance"
        )
    else:
        display_source_details = (
            "Stress fixture evidence is not eligible for display acceptance"
        )

    environment = _collect_environment_snapshot()
    display_diagnostics = _display_diagnostics_payload(
        renderer_diagnostics=renderer_diagnostics,
        interaction_benchmark=interaction_benchmark,
        environment=environment,
    )
    if display_diagnostics["acceptance_allowed"]:
        display_attached_details = (
            "Display-attached Qt Quick GPU diagnostics allow performance acceptance"
        )
    else:
        display_attached_details = "Display acceptance refused: " + "; ".join(
            display_diagnostics.get("acceptance_blockers", [])
        )
    requirements_eval = {
        "GRAPH-CANVAS-ZERO-LOSS": {
            "pass": feature_parity_pass,
            "details": (
                "Full-fidelity feature parity retained"
                if feature_parity_pass
                else "Feature parity failures: "
                + ", ".join(feature_parity.get("failures", []))
            ),
        },
        "REQ-PERF-001": {
            "pass": (
                fixture_metadata.get("node_count", config.synthetic_graph.node_count)
                >= 1000
                and fixture_metadata.get(
                    "edge_count", config.synthetic_graph.edge_count
                )
                >= 1000
            ),
            "details": (
                f"Benchmark graph size "
                f"{fixture_metadata.get('node_count', config.synthetic_graph.node_count)} nodes / "
                f"{fixture_metadata.get('edge_count', config.synthetic_graph.edge_count)} edges"
            ),
        },
        "GRAPH-CANVAS-DISPLAY-ACCEPTANCE-SOURCE": {
            "pass": display_source_pass,
            "details": display_source_details,
        },
        "GRAPH-CANVAS-DISPLAY-ATTACHED": {
            "pass": bool(display_diagnostics["acceptance_allowed"]),
            "details": display_attached_details,
        },
        "REQ-PERF-002": {
            "pass": interaction_frame_p95 <= 33.0,
            "details": (
                f"Real GraphCanvas pan p95={pan_summary['p95']:.3f} ms, "
                f"zoom p95={zoom_summary['p95']:.3f} ms, "
                f"node-drag steady offset p95={node_drag_steady_offset_summary['p95']:.3f} ms, "
                f"legacy single-offset control p95={node_drag_control_summary['p95']:.3f} ms "
                f"(frame p95 target <= 33 ms)"
            ),
        },
        "REQ-PERF-003": {
            "pass": load_summary["p95"] < 3000.0,
            "details": f"Project+graph load p95={load_summary['p95']:.3f} ms (target < 3000 ms)",
        },
    }
    packet_verification_result = _packet_verification_result_payload(
        display_diagnostics
    )
    performance_acceptance_result = _performance_acceptance_result_payload(
        requirements_eval=requirements_eval,
        display_diagnostics=display_diagnostics,
    )
    limitations = [
        "Pan/zoom, legacy node-drag control, and multi-offset drag gesture timings reuse one warmed GraphCanvas.qml host selected by EA_NODE_EDITOR_QML_HOST; full-gesture and clear timings include host-appropriate final readback overhead.",
        "frame_interval_ms_without_readback is captured from QQuickWindow.afterRendering timestamps and excludes grabWindow() readback elapsed time.",
        "Project+graph load timing still measures serializer/model/bridge setup and does not instantiate GraphCanvas.qml.",
        "Offscreen/minimal or software-fallback runs are regression evidence only; performance_acceptance_result refuses display acceptance for those runs.",
        "Absolute timings are machine- and load-dependent; compare trends on the same hardware for regressions.",
    ]
    if node_insertion_benchmark:
        limitations.append(
            "Node insertion timing begins at confirmed dispatch; node-library drag travel and quick-insert open/filter/selection time require shell-level integration coverage and are intentionally outside this canvas benchmark."
        )
    if graph_mutation_benchmark and "create_edge" in graph_mutation_benchmark.get(
        "scenarios", []
    ):
        limitations.append(_CREATE_EDGE_MEASUREMENT_LIMITATION)
    process_wall_time_s = max(0.0, time.perf_counter() - process_wall_started)
    process_cpu_time_s = max(0.0, _process_cpu_seconds(process) - process_cpu_started)
    process_rss_end_bytes = int(process.memory_info().rss)
    process_resources = {
        "measurement_scope": "single benchmark process from run entry through report assembly",
        "wall_time_s": process_wall_time_s,
        "cpu_time_s": process_cpu_time_s,
        "cpu_percent": (
            (process_cpu_time_s / process_wall_time_s) * 100.0
            if process_wall_time_s > 0.0
            else 0.0
        ),
        "rss_start_bytes": process_rss_started,
        "rss_end_bytes": process_rss_end_bytes,
        "rss_delta_bytes": process_rss_end_bytes - process_rss_started,
    }
    current_baseline_metrics.update(
        {
            "process_cpu_percent": process_resources["cpu_percent"],
            "process_rss_end_bytes": process_resources["rss_end_bytes"],
        }
    )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "config": {
            "synthetic_graph": asdict(config.synthetic_graph),
            "load_iterations": config.load_iterations,
            "interaction_samples": config.interaction_samples,
            "interaction_warmup_samples": config.interaction_warmup_samples,
            "interaction_zoom_min": config.interaction_zoom_min,
            "interaction_zoom_max": config.interaction_zoom_max,
            "scenario": scenario,
            "project_path": fixture_metadata.get("project_path", ""),
            "workspace_id": workspace_id,
            "stress_fixture": _normalize_stress_fixture_mode(config.stress_fixture),
            "qml_host": str(config.qml_host or ""),
            "qsg_rhi_backend": str(config.qsg_rhi_backend or ""),
            "node_insertion_samples": config.node_insertion_samples,
            "node_insertion_warmup_samples": config.node_insertion_warmup_samples,
            "mutation_scenarios": list(
                _resolve_mutation_benchmark_scenarios(config.mutation_scenarios)
            ),
            "scenario_details": scenario_project.scenario_details,
        },
        "fixture_metadata": fixture_metadata,
        "mutation_benchmark_contract": mutation_benchmark_contract,
        "mutation_phase_instrumentation": mutation_phase_instrumentation,
        "graph_mutation_benchmark": graph_mutation_benchmark,
        "node_insertion_benchmark": node_insertion_benchmark,
        "current_baseline_metrics": current_baseline_metrics,
        "process_resources": process_resources,
        "interaction_benchmark": interaction_benchmark,
        "supplemental_selected_drag": supplemental_selected_drag,
        "renderer_diagnostics": renderer_diagnostics,
        "display_diagnostics": display_diagnostics,
        "packet_verification_result": packet_verification_result,
        "performance_acceptance_result": performance_acceptance_result,
        "feature_parity": feature_parity,
        "edge_renderer_ab": edge_renderer_ab,
        "phase_timings_ms": phase_timings_ms,
        "profiling_counts": interaction_samples["profiling_counts"],
        "stress_1200_bottleneck_breakdown": stress_1200_bottleneck_breakdown,
        "metrics": {
            "project_graph_load_ms": {
                "samples": load_samples,
                "summary": load_summary,
            },
            "pan_interaction_ms": {
                "samples": interaction_samples["pan_ms"],
                "summary": pan_summary,
            },
            "zoom_interaction_ms": {
                "samples": interaction_samples["zoom_ms"],
                "summary": zoom_summary,
            },
            "pan_zoom_combined_ms": {
                "samples": interaction_samples["combined_ms"],
                "summary": combined_summary,
            },
            "node_drag_control_ms": {
                "samples": interaction_samples["node_drag_control_ms"],
                "summary": node_drag_control_summary,
            },
            "node_drag_first_offset_ms": {
                "samples": interaction_samples["node_drag_first_offset_ms"],
                "summary": node_drag_first_offset_summary,
            },
            "node_drag_steady_offset_ms": {
                "samples": interaction_samples["node_drag_steady_offset_ms"],
                "summary": node_drag_steady_offset_summary,
            },
            "node_drag_full_gesture_ms": {
                "samples": interaction_samples["node_drag_full_gesture_ms"],
                "summary": node_drag_full_gesture_summary,
            },
            "node_drag_end_clear_ms": {
                "samples": interaction_samples["node_drag_end_clear_ms"],
                "summary": node_drag_end_clear_summary,
            },
            "frame_interval_ms_without_readback": {
                "samples": interaction_samples["frame_interval_ms_without_readback"],
                "summary": frame_interval_without_readback_summary,
            },
        },
        "requirements_eval": requirements_eval,
        "limitations": limitations,
    }


def _baseline_series_run(
    run_report: dict[str, Any],
    *,
    run_index: int,
    baseline_mode: str,
    baseline_tag: str,
) -> dict[str, Any]:
    metrics = run_report["metrics"]
    return {
        "run_id": f"run_{run_index:02d}",
        "generated_at_utc": run_report["generated_at_utc"],
        "mode": baseline_mode,
        "tag": baseline_tag,
        "scenario": str(run_report["config"]["scenario"]),
        "environment": run_report["environment"],
        "display_diagnostics": run_report.get("display_diagnostics", {}),
        "packet_verification_result": run_report.get("packet_verification_result", {}),
        "performance_acceptance_result": run_report.get(
            "performance_acceptance_result", {}
        ),
        "process_resources": run_report.get("process_resources", {}),
        "mutation_benchmark_contract": run_report.get(
            "mutation_benchmark_contract",
            _mutation_benchmark_contract_payload(),
        ),
        "mutation_phase_instrumentation": run_report.get(
            "mutation_phase_instrumentation", {}
        ),
        "graph_mutation_benchmark": run_report.get("graph_mutation_benchmark", {}),
        "node_insertion_benchmark": run_report.get("node_insertion_benchmark", {}),
        "edge_renderer_kind": str(
            run_report.get("interaction_benchmark", {}).get(
                "edge_renderer_kind",
                run_report.get("feature_parity", {}).get("edge_renderer_kind", ""),
            )
        ),
        "metrics": {
            "load_p95_ms": float(metrics["project_graph_load_ms"]["summary"]["p95"]),
            "pan_p95_ms": float(metrics["pan_interaction_ms"]["summary"]["p95"]),
            "zoom_p95_ms": float(metrics["zoom_interaction_ms"]["summary"]["p95"]),
            "pan_zoom_p95_ms": float(metrics["pan_zoom_combined_ms"]["summary"]["p95"]),
            "node_drag_control_p95_ms": float(
                metrics["node_drag_control_ms"]["summary"]["p95"]
            ),
            "node_drag_first_offset_p95_ms": float(
                metrics["node_drag_first_offset_ms"]["summary"]["p95"]
            ),
            "node_drag_steady_offset_p95_ms": float(
                metrics["node_drag_steady_offset_ms"]["summary"]["p95"]
            ),
            "node_drag_full_gesture_p95_ms": float(
                metrics["node_drag_full_gesture_ms"]["summary"]["p95"]
            ),
            "node_drag_end_clear_p95_ms": float(
                metrics["node_drag_end_clear_ms"]["summary"]["p95"]
            ),
            "frame_interval_without_readback_p95_ms": float(
                metrics["frame_interval_ms_without_readback"]["summary"]["p95"]
            ),
            "process_cpu_percent": float(
                run_report.get("process_resources", {}).get("cpu_percent", 0.0)
            ),
            "process_rss_end_bytes": float(
                run_report.get("process_resources", {}).get("rss_end_bytes", 0.0)
            ),
        },
    }


def _edge_renderer_ab_payload(
    *,
    interaction_benchmark: dict[str, Any],
    feature_parity: dict[str, Any],
    phase_timings_ms: dict[str, Any],
    profiling_counts: dict[str, Any],
) -> dict[str, Any]:
    active_kind = str(
        interaction_benchmark.get("edge_renderer_kind")
        or feature_parity.get("edge_renderer_kind")
        or "canvas"
    )
    requested_kind = str(
        interaction_benchmark.get("edge_renderer_requested_kind")
        or feature_parity.get("edge_renderer_requested_kind")
        or active_kind
    )
    fallback_active = bool(
        interaction_benchmark.get(
            "edge_renderer_canvas_fallback_active",
            feature_parity.get("edge_renderer_canvas_fallback_active", False),
        )
    )
    fallback_reason = str(
        interaction_benchmark.get("edge_renderer_fallback_reason")
        or feature_parity.get("edge_renderer_fallback_reason")
        or ""
    )
    pan_edge_paint = phase_timings_ms.get("pan_edge_paint_ms", {}).get("summary", {})
    zoom_edge_paint = phase_timings_ms.get("zoom_edge_paint_ms", {}).get("summary", {})
    visible_edges = max(
        float(
            profiling_counts.get("pan_visible_edge_count", {})
            .get("summary", {})
            .get("max", 0.0)
            or 0.0
        ),
        float(
            profiling_counts.get("zoom_visible_edge_count", {})
            .get("summary", {})
            .get("max", 0.0)
            or 0.0
        ),
    )
    active_variant = {
        "kind": active_kind,
        "role": "active",
        "measured": True,
        "pan_edge_paint_p95_ms": float(pan_edge_paint.get("p95", 0.0) or 0.0),
        "zoom_edge_paint_p95_ms": float(zoom_edge_paint.get("p95", 0.0) or 0.0),
        "visible_edge_count_max": visible_edges,
    }
    variants = [active_variant]
    if active_kind != "canvas":
        variants.append(
            {
                "kind": "canvas",
                "role": "fallback",
                "measured": False,
                "reason": "Canvas fallback remains available for unsupported edge sets and platforms.",
            }
        )
    return {
        "active_renderer_kind": active_kind,
        "requested_renderer_kind": requested_kind,
        "canvas_fallback_active": fallback_active,
        "fallback_reason": fallback_reason,
        "accepted_renderer_kind": active_kind,
        "accepted_renderer_rationale": (
            "Canvas fallback selected for this run: " + fallback_reason
            if fallback_active and fallback_reason
            else "Active edge renderer completed the benchmark path with Canvas fallback still available."
        ),
        "variants": variants,
    }


def _current_baseline_metrics_payload(
    *,
    load_summary: dict[str, float],
    pan_summary: dict[str, float],
    zoom_summary: dict[str, float],
    combined_summary: dict[str, float],
    node_drag_control_summary: dict[str, float],
    node_drag_first_offset_summary: dict[str, float],
    node_drag_steady_offset_summary: dict[str, float],
    node_drag_full_gesture_summary: dict[str, float],
    node_drag_end_clear_summary: dict[str, float],
    frame_interval_without_readback_summary: dict[str, float],
    fixture_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "fixture_source_kind": fixture_metadata.get("fixture_source_kind", ""),
        "fixture_acceptance_scope": fixture_metadata.get(
            "fixture_acceptance_scope", ""
        ),
        "display_acceptance_eligible": bool(
            fixture_metadata.get("display_acceptance_eligible", False)
        ),
        "load_p95_ms": float(load_summary["p95"]),
        "pan_p95_ms": float(pan_summary["p95"]),
        "zoom_p95_ms": float(zoom_summary["p95"]),
        "pan_zoom_p95_ms": float(combined_summary["p95"]),
        "node_drag_control_p95_ms": float(node_drag_control_summary["p95"]),
        "node_drag_first_offset_p95_ms": float(node_drag_first_offset_summary["p95"]),
        "node_drag_steady_offset_p95_ms": float(node_drag_steady_offset_summary["p95"]),
        "node_drag_full_gesture_p95_ms": float(node_drag_full_gesture_summary["p95"]),
        "node_drag_end_clear_p95_ms": float(node_drag_end_clear_summary["p95"]),
        "frame_interval_without_readback_p95_ms": float(
            frame_interval_without_readback_summary["p95"]
        ),
    }


def _baseline_metric_series(
    series_runs: list[dict[str, Any]],
) -> dict[str, list[float]]:
    return {
        "load_p95_ms": [float(run["metrics"]["load_p95_ms"]) for run in series_runs],
        "pan_p95_ms": [float(run["metrics"]["pan_p95_ms"]) for run in series_runs],
        "zoom_p95_ms": [float(run["metrics"]["zoom_p95_ms"]) for run in series_runs],
        "pan_zoom_p95_ms": [
            float(run["metrics"]["pan_zoom_p95_ms"]) for run in series_runs
        ],
        "node_drag_control_p95_ms": [
            float(run["metrics"]["node_drag_control_p95_ms"]) for run in series_runs
        ],
        "node_drag_first_offset_p95_ms": [
            float(run["metrics"]["node_drag_first_offset_p95_ms"])
            for run in series_runs
        ],
        "node_drag_steady_offset_p95_ms": [
            float(run["metrics"]["node_drag_steady_offset_p95_ms"])
            for run in series_runs
        ],
        "node_drag_full_gesture_p95_ms": [
            float(run["metrics"]["node_drag_full_gesture_p95_ms"])
            for run in series_runs
        ],
        "node_drag_end_clear_p95_ms": [
            float(run["metrics"]["node_drag_end_clear_p95_ms"]) for run in series_runs
        ],
        "frame_interval_without_readback_p95_ms": [
            float(run["metrics"]["frame_interval_without_readback_p95_ms"])
            for run in series_runs
        ],
    }


def _baseline_variance_eval(
    metric_series: dict[str, list[float]], *, enough_runs: bool
) -> dict[str, Any]:
    return {
        metric_key: _series_variance_eval(
            values,
            _BASELINE_VARIANCE_THRESHOLDS[metric_key],
            enough_runs=enough_runs,
        )
        for metric_key, values in metric_series.items()
    }


def _baseline_series_payload(
    latest_report: dict[str, Any],
    *,
    series_runs: list[dict[str, Any]],
    failed_runs: list[dict[str, Any]],
    run_report_paths: list[str],
    baseline_runs: int,
    baseline_mode: str,
    baseline_tag: str,
    execution_mode: str,
) -> dict[str, Any]:
    metric_series = _baseline_metric_series(series_runs)
    completed_run_count = len(series_runs)
    return {
        "mode": baseline_mode,
        "tag": baseline_tag,
        "scenario": str(latest_report["config"]["scenario"]),
        "run_count": baseline_runs,
        "runs": series_runs,
        "status": "partial_failure" if failed_runs else "complete",
        "execution_mode": execution_mode,
        "completed_run_count": completed_run_count,
        "failed_run_count": len(failed_runs),
        "failed_runs": failed_runs,
        "run_report_paths": run_report_paths,
        "mutation_benchmark_contract": latest_report.get(
            "mutation_benchmark_contract",
            _mutation_benchmark_contract_payload(),
        ),
        "mutation_phase_instrumentation": latest_report.get(
            "mutation_phase_instrumentation", {}
        ),
        "graph_mutation_benchmark": latest_report.get("graph_mutation_benchmark", {}),
        "node_insertion_benchmark": latest_report.get("node_insertion_benchmark", {}),
        "metric_series": metric_series,
        "variance_thresholds": _BASELINE_VARIANCE_THRESHOLDS,
        "variance_eval": _baseline_variance_eval(
            metric_series, enough_runs=completed_run_count >= 2
        ),
        "triage_policy": [
            "If variance check fails, first rerun 3x on the same machine with no background workloads.",
            "If variance remains high, classify by hardware tier (CPU/GPU/RAM/display) and keep separate baselines.",
            "Investigate regressions only when thresholds fail on at least two consecutive runs in the same hardware tier.",
        ],
        "notes": (
            "Variance checks are informative when run_count >= 2. "
            "Single-run captures still provide point-in-time regression evidence."
        ),
    }


def _write_json_atomic(payload: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _clear_baseline_run_artifacts(report_dir: Path) -> None:
    for path in report_dir.glob("baseline_run_*.json"):
        if path.is_file():
            path.unlink()
    (report_dir / "baseline_series_failure.json").unlink(missing_ok=True)


def run_benchmark(
    config: BenchmarkConfig,
    *,
    baseline_runs: int = 1,
    baseline_mode: str = "offscreen",
    baseline_tag: str = "local",
    report_dir: Path | None = None,
    isolate_baseline_runs: bool = True,
) -> dict[str, Any]:
    if baseline_runs <= 0:
        raise ValueError("baseline_runs must be > 0")

    _apply_config_qtquick_environment(config)
    full_runs: list[dict[str, Any]] = []
    series_runs: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []
    run_report_paths: list[str] = []
    isolate_repeated_runs = baseline_runs > 1 and isolate_baseline_runs
    persist_run_records = report_dir is not None and baseline_runs > 1
    if isolate_repeated_runs and persist_run_records and report_dir is not None:
        _clear_baseline_run_artifacts(report_dir)
    for run_index in range(1, baseline_runs + 1):
        try:
            if isolate_repeated_runs:
                run_report = _run_single_benchmark_subprocess(
                    config,
                    baseline_mode=baseline_mode,
                    baseline_tag=baseline_tag,
                )
            else:
                run_report = _run_single_benchmark(config)
        except Exception as exc:  # noqa: BLE001 - retain evidence and continue other runs
            failed_path = (
                report_dir / f"baseline_run_{run_index:02d}.failed.json"
                if persist_run_records and report_dir is not None
                else None
            )
            failed_run = {
                "run_id": f"run_{run_index:02d}",
                "status": "failed",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc)[:2000],
                "returncode": getattr(exc, "returncode", None),
                "output_tail": str(getattr(exc, "output", "") or "")[-4000:],
                "record_path": str(failed_path) if failed_path is not None else "",
            }
            failed_runs.append(failed_run)
            if failed_path is not None:
                _write_json_atomic(failed_run, failed_path)
            print(
                f"progress baseline_run={run_index}/{baseline_runs} status=failed",
                flush=True,
            )
            continue

        full_runs.append(run_report)
        series_runs.append(
            _baseline_series_run(
                run_report,
                run_index=run_index,
                baseline_mode=baseline_mode,
                baseline_tag=baseline_tag,
            )
        )
        if persist_run_records and report_dir is not None:
            run_path = report_dir / f"baseline_run_{run_index:02d}.json"
            _write_json_atomic(run_report, run_path)
            run_report_paths.append(str(run_path))
        print(
            f"progress baseline_run={run_index}/{baseline_runs} status=completed",
            flush=True,
        )

    if not full_runs:
        failure_manifest = {
            "status": "failed",
            "run_count": baseline_runs,
            "completed_run_count": 0,
            "failed_run_count": len(failed_runs),
            "failed_runs": failed_runs,
        }
        if report_dir is not None:
            _write_json_atomic(
                failure_manifest,
                report_dir / "baseline_series_failure.json",
            )
        raise RuntimeError("All benchmark baseline runs failed.")

    latest_report = dict(full_runs[-1])
    latest_report["baseline_series"] = _baseline_series_payload(
        latest_report,
        series_runs=series_runs,
        failed_runs=failed_runs,
        run_report_paths=run_report_paths,
        baseline_runs=baseline_runs,
        baseline_mode=baseline_mode,
        baseline_tag=baseline_tag,
        execution_mode="isolated_child" if isolate_repeated_runs else "in_process",
    )
    return latest_report


def _run_single_benchmark_subprocess(
    config: BenchmarkConfig,
    *,
    baseline_mode: str,
    baseline_tag: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="track_h_baseline_subprocess_") as temp_dir:
        report_dir = Path(temp_dir)
        command = [
            sys.executable,
            "-m",
            "ea_node_editor.ui.perf.performance_harness",
            "--nodes",
            str(config.synthetic_graph.node_count),
            "--edges",
            str(config.synthetic_graph.edge_count),
            "--seed",
            str(config.synthetic_graph.seed),
            "--load-iterations",
            str(config.load_iterations),
            "--interaction-samples",
            str(config.interaction_samples),
            "--interaction-warmup-samples",
            str(config.interaction_warmup_samples),
            "--interaction-zoom-min",
            str(config.interaction_zoom_min),
            "--interaction-zoom-max",
            str(config.interaction_zoom_max),
            "--node-insertion-samples",
            str(config.node_insertion_samples),
            "--node-insertion-warmup-samples",
            str(config.node_insertion_warmup_samples),
            "--scenario",
            str(config.scenario),
            "--baseline-runs",
            "1",
            "--baseline-mode",
            str(baseline_mode),
            "--baseline-tag",
            str(baseline_tag),
            "--report-dir",
            str(report_dir),
        ]
        if config.project_path:
            command.extend(["--project-path", str(config.project_path)])
        if config.workspace_id:
            command.extend(["--workspace-id", str(config.workspace_id)])
        stress_fixture_mode = _normalize_stress_fixture_mode(config.stress_fixture)
        if stress_fixture_mode:
            command.extend(["--stress-fixture", stress_fixture_mode])
        if config.qml_host:
            command.extend(["--qml-host", str(config.qml_host)])
        if config.qsg_rhi_backend:
            command.extend(["--qsg-rhi-backend", str(config.qsg_rhi_backend)])
        for mutation_scenario in config.mutation_scenarios:
            command.extend(["--mutation-scenario", str(mutation_scenario)])
        qt_qpa_platform = os.environ.get("QT_QPA_PLATFORM", "").strip()
        if qt_qpa_platform:
            command.extend(["--qt-platform", qt_qpa_platform])
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output_tail: deque[str] = deque(maxlen=40)
        if process.stdout is not None:
            for line in process.stdout:
                normalized_line = line.rstrip()
                if normalized_line:
                    output_tail.append(normalized_line)
                if normalized_line.startswith("progress ") and not normalized_line.startswith(
                    "progress baseline_run="
                ):
                    print(normalized_line, flush=True)
        returncode = process.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode,
                command,
                output="\n".join(output_tail),
            )
        json_path = report_dir / "track_h_benchmark_report.json"
        if not json_path.exists():
            output_text = "\n".join(output_tail)
            raise RuntimeError(
                "Benchmark subprocess did not produce track_h_benchmark_report.json\n"
                f"OUTPUT TAIL:\n{output_text}"
            )
        return json.loads(json_path.read_text(encoding="utf-8"))


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    metrics = report["metrics"]
    load = metrics["project_graph_load_ms"]["summary"]
    pan = metrics["pan_interaction_ms"]["summary"]
    zoom = metrics["zoom_interaction_ms"]["summary"]
    combined = metrics["pan_zoom_combined_ms"]["summary"]
    node_drag_control = metrics["node_drag_control_ms"]["summary"]
    node_drag_first_offset = metrics["node_drag_first_offset_ms"]["summary"]
    node_drag_steady_offset = metrics["node_drag_steady_offset_ms"]["summary"]
    node_drag_full_gesture = metrics["node_drag_full_gesture_ms"]["summary"]
    node_drag_end_clear = metrics["node_drag_end_clear_ms"]["summary"]
    frame_interval_without_readback = metrics["frame_interval_ms_without_readback"][
        "summary"
    ]
    phase_timings = report.get("phase_timings_ms", {})
    profiling_counts = report.get("profiling_counts", {})
    stress_breakdown = report.get("stress_1200_bottleneck_breakdown", {})
    baseline_series = report.get("baseline_series", {})
    interaction_benchmark = report.get("interaction_benchmark", {})
    supplemental_selected_drag = report.get("supplemental_selected_drag", {})
    renderer_diagnostics = report.get(
        "renderer_diagnostics", {}
    ) or interaction_benchmark.get(
        "renderer_diagnostics",
        {},
    )
    edge_renderer_ab = report.get("edge_renderer_ab", {})
    display_diagnostics = report.get("display_diagnostics", {})
    packet_verification_result = report.get("packet_verification_result", {})
    performance_acceptance_result = report.get("performance_acceptance_result", {})
    feature_parity = report.get("feature_parity", {}) or interaction_benchmark.get(
        "feature_parity", {}
    )
    mutation_benchmark_contract = report.get("mutation_benchmark_contract", {})
    graph_mutation_benchmark = report.get("graph_mutation_benchmark", {})
    node_insertion_benchmark = report.get("node_insertion_benchmark", {})

    lines: list[str] = []
    lines.append("# Track H Benchmark Report")
    lines.append("")
    lines.append(f"- Generated (UTC): `{report['generated_at_utc']}`")
    lines.append("- Command:")
    lines.append(
        "  `venv\\Scripts\\python -m ea_node_editor.ui.perf.performance_harness`"
    )
    lines.append(f"- Platform: `{report['environment']['platform']}`")
    lines.append(f"- Python: `{report['environment']['python_version']}`")
    lines.append(f"- Qt version: `{report['environment'].get('qt_version', '')}`")
    lines.append(f"- Qt platform: `{report['environment']['qt_qpa_platform']}`")
    lines.append(f"- QML host env: `{report['environment'].get('qml_host_env', '')}`")
    lines.append(
        f"- QML host selected: `{report['environment'].get('qml_host_kind_selected', '')}`"
    )
    lines.append(
        f"- Qt Quick backend: `{report['environment'].get('qt_quick_backend', '')}`"
    )
    lines.append(
        f"- QSG RHI backend: `{report['environment'].get('qsg_rhi_backend', '')}`"
    )
    lines.append(
        f"- EA backend override: `{report['environment'].get('qsg_rhi_backend_override', '')}`"
    )
    lines.append(
        "- QtQuick backend selection: "
        f"`{report['environment'].get('qtquick_backend_selection_reason', '')}` / "
        f"`{report['environment'].get('qtquick_backend_selected', '')}`"
    )
    lines.append(
        f"- QSG render loop: `{report['environment'].get('qsg_render_loop', '')}`"
    )
    lines.append(
        f"- Packet verification result: `{packet_verification_result.get('status', '')}`"
    )
    lines.append(
        f"- Performance acceptance result: `{performance_acceptance_result.get('status', '')}`"
    )
    lines.append("")
    lines.append("## Config")
    lines.append("")
    cfg = report["config"]
    graph_cfg = cfg["synthetic_graph"]
    lines.append(
        f"- Synthetic graph: `{graph_cfg['node_count']}` nodes / `{graph_cfg['edge_count']}` edges"
    )
    lines.append(f"- Seed: `{graph_cfg['seed']}`")
    lines.append(f"- Load iterations: `{cfg['load_iterations']}`")
    lines.append(f"- Warmup samples: `{cfg.get('interaction_warmup_samples', 0)}`")
    lines.append(f"- Pan/zoom samples: `{cfg['interaction_samples']}`")
    lines.append(
        f"- Node-drag gesture offsets: `{interaction_benchmark.get('node_drag_gesture_offset_count', 0)}`"
    )
    membership_freeze_supported = (
        interaction_benchmark.get("membership_freeze_supported") is True
    )
    lines.append(
        "- Node-drag membership-freeze counter supported: "
        f"`{str(membership_freeze_supported).lower()}`"
    )
    lines.append(
        "- Node-drag membership-freeze counts: "
        f"`{interaction_benchmark.get('node_drag_membership_freeze_counts') if membership_freeze_supported else 'unsupported'}`"
    )
    lines.append(
        "- Node-drag membership-freeze verification: "
        f"`{interaction_benchmark.get('node_drag_membership_freeze_verified') if membership_freeze_supported else 'unsupported'}`"
    )
    lines.append(f"- Scenario: `{cfg['scenario']}`")
    scenario_details = cfg.get("scenario_details", {})
    node_mix = scenario_details.get("node_mix", {})
    if node_mix:
        lines.append(
            "- Node mix: "
            f"`{node_mix.get('execution_nodes', 0)}` active data / "
            f"`{node_mix.get('media_panel_nodes', 0)}` media panels "
            f"(`{node_mix.get('image_source_nodes', 0)}` image / "
            f"`{node_mix.get('pdf_source_nodes', 0)}` PDF sources)"
        )
    fixture_counts = scenario_details.get("generated_fixture_count", {})
    if fixture_counts:
        lines.append(
            "- Generated fixtures: "
            f"`{fixture_counts.get('images', 0)}` images / "
            f"`{fixture_counts.get('pdfs', 0)}` PDFs"
        )
    scenario_description = str(scenario_details.get("description", "")).strip()
    if scenario_description:
        lines.append(f"- Scenario detail: {scenario_description}")
    required_fixture_paths = scenario_details.get("required_fixture_paths", {})
    if required_fixture_paths:
        lines.append(
            "- Required animation fixtures: `"
            + json.dumps(required_fixture_paths, sort_keys=True)
            + "`"
        )
    fixture_role_counts = scenario_details.get("fixture_role_counts", {})
    if fixture_role_counts:
        lines.append(
            "- Animation fixture role counts: `"
            + json.dumps(fixture_role_counts, sort_keys=True)
            + "`"
        )
    process_resources = report.get("process_resources", {})
    if process_resources:
        lines.append(
            f"- Process CPU: `{float(process_resources.get('cpu_percent', 0.0)):.2f}%`"
        )
        lines.append(
            f"- Process RSS: `{int(process_resources.get('rss_end_bytes', 0))}` bytes "
            f"(delta `{int(process_resources.get('rss_delta_bytes', 0))}` bytes)"
        )
    fixture_metadata = report.get("fixture_metadata", {})
    if fixture_metadata:
        bounds = fixture_metadata.get("scene_bounds", {})
        lines.append(
            f"- Fixture source kind: `{fixture_metadata.get('fixture_source_kind', '')}`"
        )
        lines.append(
            f"- Fixture acceptance scope: `{fixture_metadata.get('fixture_acceptance_scope', '')}`"
        )
        lines.append(
            "- Display acceptance eligible: "
            f"`{bool(fixture_metadata.get('display_acceptance_eligible', False))}`"
        )
        lines.append(
            f"- Fixture project path: `{fixture_metadata.get('project_path', '')}`"
        )
        lines.append(
            f"- Fixture effective path: `{fixture_metadata.get('effective_project_path', '')}`"
        )
        lines.append(
            f"- Fixture path exists: `{bool(fixture_metadata.get('project_path_exists', False))}`"
        )
        lines.append(
            f"- Fixture checksum (SHA-256): `{fixture_metadata.get('fixture_checksum_sha256', '')}`"
        )
        lines.append(
            f"- Fixture workspace: `{fixture_metadata.get('workspace_id', '')}`"
        )
        lines.append(
            "- Fixture graph: "
            f"`{int(fixture_metadata.get('node_count', 0))}` nodes / "
            f"`{int(fixture_metadata.get('edge_count', 0))}` edges"
        )
        lines.append(
            "- Fixture scene bounds: "
            f"left=`{float(bounds.get('left', 0.0)):.1f}`, "
            f"top=`{float(bounds.get('top', 0.0)):.1f}`, "
            f"width=`{float(bounds.get('width', 0.0)):.1f}`, "
            f"height=`{float(bounds.get('height', 0.0)):.1f}`"
        )
        lines.append(
            f"- Fixture node type histogram: `{fixture_metadata.get('node_type_histogram', {})}`"
        )
        lines.append(
            f"- Fixture active graphics API: `{fixture_metadata.get('active_graphics_api', '')}`"
        )
        lines.append(
            f"- Fixture QML host kind: `{fixture_metadata.get('qml_host_kind', '')}`"
        )
        lines.append(
            "- Fixture DPR: "
            f"screen=`{float(fixture_metadata.get('screen_device_pixel_ratio', 0.0)):.3f}`, "
            f"window=`{float(fixture_metadata.get('window_effective_device_pixel_ratio', 0.0)):.3f}`"
        )
        lines.append(
            f"- Fixture readback included: `{bool(fixture_metadata.get('grab_window_readback_included', False))}`"
        )
        lines.append(
            f"- Fixture no-readback frame interval: `{fixture_metadata.get('frame_interval_metric', '')}`"
        )
        prior_closeout = scenario_details.get("prior_stress_closeout_status", {})
        if prior_closeout:
            lines.append(
                "- Prior stress closeout: "
                f"`{prior_closeout.get('packet', '')}` packet="
                f"`{prior_closeout.get('packet_status', '')}`, performance="
                f"`{prior_closeout.get('performance_status', '')}`"
            )
    current_baseline_metrics = report.get("current_baseline_metrics", {})
    if current_baseline_metrics:
        lines.append(
            "- Current baseline p95 metrics: "
            f"load=`{float(current_baseline_metrics.get('load_p95_ms', 0.0)):.3f} ms`, "
            f"pan=`{float(current_baseline_metrics.get('pan_p95_ms', 0.0)):.3f} ms`, "
            f"zoom=`{float(current_baseline_metrics.get('zoom_p95_ms', 0.0)):.3f} ms`, "
            f"pan+zoom=`{float(current_baseline_metrics.get('pan_zoom_p95_ms', 0.0)):.3f} ms`, "
            f"drag legacy=`{float(current_baseline_metrics.get('node_drag_control_p95_ms', 0.0)):.3f} ms`, "
            f"drag steady=`{float(current_baseline_metrics.get('node_drag_steady_offset_p95_ms', 0.0)):.3f} ms`, "
            f"drag full gesture=`{float(current_baseline_metrics.get('node_drag_full_gesture_p95_ms', 0.0)):.3f} ms`, "
            f"frame(no readback)=`{float(current_baseline_metrics.get('frame_interval_without_readback_p95_ms', 0.0)):.3f} ms`"
        )
    lines.append("")
    if node_insertion_benchmark:
        lines.append("## Node Insertion Latency")
        lines.append("")
        lines.append(f"- Kind: `{node_insertion_benchmark.get('kind', '')}`")
        lines.append(
            f"- Acceptance: `{node_insertion_benchmark.get('acceptance_result', {}).get('status', '')}`"
        )
        lines.append(
            f"- Threshold policy: `{node_insertion_benchmark.get('threshold_policy', '')}`"
        )
        lines.append(
            f"- Measured sample budget / warmups per profile: "
            f"`{int(node_insertion_benchmark.get('sample_budget', 0))}` / "
            f"`{int(node_insertion_benchmark.get('warmup_samples_per_profile', 0))}`"
        )
        measurement_contract = node_insertion_benchmark.get("measurement_contract", {})
        lines.append(
            f"- Completion: {measurement_contract.get('completion_semantics', '')}"
        )
        lines.append(
            "- Timed readback / heavy-content readiness: "
            f"`{bool(measurement_contract.get('grab_window_readback_included', False))}` / "
            f"`{bool(measurement_contract.get('heavy_content_readiness_included', False))}`"
        )
        display_validity = node_insertion_benchmark.get("display_validity", {})
        lines.append(
            "- Windows D3D11 display validity: "
            f"`{bool(display_validity.get('valid', False))}` "
            f"(blockers=`{display_validity.get('blockers', [])}`)"
        )
        lines.append("")
        lines.append(
            "| Profile | Samples | Dispatch p50 (ms) | Dispatch p95 (ms) | "
            "Presented p50 (ms) | Presented p95 (ms) | Result |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for profile_name in node_insertion_benchmark.get("profiles", []):
            summary = node_insertion_benchmark.get("profile_summaries", {}).get(
                str(profile_name),
                {},
            )
            dispatch = summary.get("dispatch_to_model_commit_ms", {}).get("summary", {})
            presented = summary.get("all_primary_delegates_presented_ms", {}).get(
                "summary", {}
            )
            lines.append(
                "| "
                f"`{profile_name}` | "
                f"{int(summary.get('sample_count', 0))} | "
                f"{float(dispatch.get('p50', 0.0)):.3f} | "
                f"{float(dispatch.get('p95', 0.0)):.3f} | "
                f"{float(presented.get('p50', 0.0)):.3f} | "
                f"{float(presented.get('p95', 0.0)):.3f} | "
                f"`{summary.get('acceptance', {}).get('status', '')}` |"
            )
        lines.append("")
    if mutation_benchmark_contract:
        lines.append("## Mutation Benchmark Contract")
        lines.append("")
        lines.append(f"- Kind: `{mutation_benchmark_contract.get('kind', '')}`")
        lines.append(f"- Status: `{mutation_benchmark_contract.get('status', '')}`")
        lines.append(
            f"- Threshold policy: `{mutation_benchmark_contract.get('threshold_policy', '')}`"
        )
        scenarios = mutation_benchmark_contract.get("scenarios", [])
        if scenarios:
            lines.append(
                "- Scenarios: `" + "`, `".join(str(item) for item in scenarios) + "`"
            )
        field_groups = mutation_benchmark_contract.get("report_field_groups", {})
        if field_groups:
            lines.append("")
            lines.append("| Field group | Required fields |")
            lines.append("|---|---|")
            for group_name, field_names in field_groups.items():
                lines.append(
                    "| "
                    f"{group_name} | "
                    + "`"
                    + "`, `".join(str(item) for item in field_names)
                    + "` |"
                )
        lines.append("")
    if graph_mutation_benchmark:
        lines.append("## Graph Mutation Baseline")
        lines.append("")
        lines.append(f"- Kind: `{graph_mutation_benchmark.get('kind', '')}`")
        lines.append(f"- Status: `{graph_mutation_benchmark.get('status', '')}`")
        lines.append(
            f"- Threshold policy: `{graph_mutation_benchmark.get('threshold_policy', '')}`"
        )
        lines.append(
            f"- Render path: `{graph_mutation_benchmark.get('render_path', '')}`"
        )
        lines.append(
            "- Uses actual canvas render path: "
            f"`{bool(graph_mutation_benchmark.get('uses_actual_canvas_render_path', False))}`"
        )
        lines.append(
            f"- Samples per scenario: `{int(graph_mutation_benchmark.get('samples_per_scenario', 0))}`"
        )
        lines.append(
            f"- Fixture checksum (SHA-256): `{graph_mutation_benchmark.get('fixture_checksum_sha256', '')}`"
        )
        lines.append("")
        lines.append(
            "| Scenario | Samples | Wall p95 (ms) | First frame p95 (ms) | "
            "Setup dirty nodes p95 | Setup dirty edges p95 | "
            "Model dirty nodes p95 | Model dirty edges p95 | "
            "Scene publish dirty nodes p95 | Scene publish dirty edges p95 | Publication paths |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        scenario_summaries = graph_mutation_benchmark.get("scenario_summaries", {})
        for scenario_name in graph_mutation_benchmark.get("scenarios", []):
            summary = scenario_summaries.get(str(scenario_name), {})
            wall = summary.get("mutation_wall_clock_samples_ms", {}).get("summary", {})
            first_frame = summary.get("first_frame_after_mutation_ms", {}).get(
                "summary", {}
            )
            setup_dirty_nodes = summary.get("setup_dirty_node_count", {}).get(
                "summary", {}
            )
            setup_dirty_edges = summary.get("setup_dirty_edge_count", {}).get(
                "summary", {}
            )
            model_dirty_nodes = summary.get("model_delta_dirty_node_count", {}).get(
                "summary", {}
            )
            model_dirty_edges = summary.get("model_delta_dirty_edge_count", {}).get(
                "summary", {}
            )
            scene_dirty_nodes = summary.get(
                "scene_publication_dirty_node_count", {}
            ).get("summary", {})
            scene_dirty_edges = summary.get(
                "scene_publication_dirty_edge_count", {}
            ).get("summary", {})
            publication_paths = ", ".join(
                str(value) for value in summary.get("scene_publication_paths", [])
            )
            lines.append(
                "| "
                f"`{scenario_name}` | "
                f"{int(summary.get('sample_count', 0))} | "
                f"{float(wall.get('p95', 0.0)):.3f} | "
                f"{float(first_frame.get('p95', 0.0)):.3f} | "
                f"{float(setup_dirty_nodes.get('p95', 0.0)):.0f} | "
                f"{float(setup_dirty_edges.get('p95', 0.0)):.0f} | "
                f"{float(model_dirty_nodes.get('p95', 0.0)):.0f} | "
                f"{float(model_dirty_edges.get('p95', 0.0)):.0f} | "
                f"{float(scene_dirty_nodes.get('p95', 0.0)):.0f} | "
                f"{float(scene_dirty_edges.get('p95', 0.0)):.0f} | "
                f"`{publication_paths}` |"
            )
        lines.append("")
        lines.append(
            "Setup dirty counts are captured in a separate setup scope and excluded from each timed mutation sample. "
            "Model dirty counts describe graph mutation deltas; scene publish dirty counts describe emitted canvas payloads."
        )
        if any(
            scenario_summaries.get(str(scenario_name), {}).get("mutation_counters")
            for scenario_name in graph_mutation_benchmark.get("scenarios", [])
        ):
            lines.append("")
            lines.append("### Mutation Churn Counters")
            lines.append("")
            lines.append("| Scenario | Counters | Reason buckets |")
            lines.append("|---|---|---|")
            for scenario_name in graph_mutation_benchmark.get("scenarios", []):
                summary = scenario_summaries.get(str(scenario_name), {})
                counters = summary.get("mutation_counters", {})
                counter_reasons = summary.get("mutation_counter_reasons", {})
                counter_text = ", ".join(
                    f"{name}={count}" for name, count in counters.items()
                )
                reason_parts: list[str] = []
                for counter_name, reasons in counter_reasons.items():
                    if not isinstance(reasons, dict):
                        continue
                    reason_text = ", ".join(
                        f"{reason}={count}" for reason, count in reasons.items()
                    )
                    if reason_text:
                        reason_parts.append(f"{counter_name}: {reason_text}")
                lines.append(
                    "| "
                    f"`{scenario_name}` | "
                    f"`{counter_text}` | "
                    f"`{'; '.join(reason_parts)}` |"
                )
        attribution_schema = graph_mutation_benchmark.get(
            "first_frame_phase_attribution_schema", {}
        )
        if attribution_schema:
            lines.append(
                "First-frame phase attribution keeps state-side visible-model publication, harness-forced "
                "exact refresh, Qt event drains, render wait, readback, and residual unattributed time in "
                "separate non-overlapping buckets without renaming raw timing fields."
            )
            lines.append(
                f"- First-frame includes readback: "
                f"`{bool(attribution_schema.get('first_frame_includes_readback', False))}`"
            )
            lines.append(
                f"- First-frame completion semantics: "
                f"{attribution_schema.get('completion_semantics', '')}"
            )
        residual_dirty_blockers = list(
            graph_mutation_benchmark.get("residual_mutation_dirty_blockers", [])
        )
        if residual_dirty_blockers:
            blocker_descriptions = []
            for blocker in residual_dirty_blockers:
                blocker_descriptions.append(
                    f"`{blocker.get('scenario', '')}` "
                    f"(mutation dirty nodes p95={float(blocker.get('dirty_node_count_p95', 0.0)):.0f}, "
                    f"edges p95={float(blocker.get('dirty_edge_count_p95', 0.0)):.0f})"
                )
            lines.append(
                "- Residual blocker: isolated mutation dirty publication remains broad for "
                + "; ".join(blocker_descriptions)
                + ". P02-P04 own structural delta reduction."
            )
        lines.append("")
        for scenario_name in graph_mutation_benchmark.get("scenarios", []):
            summary = scenario_summaries.get(str(scenario_name), {})
            phase_timings = summary.get("phase_timings_ms", {})
            if not phase_timings:
                continue
            lines.append(f"### `{scenario_name}` Mutation Phase Timings")
            lines.append("")
            lines.append("| Phase | Samples | p95 (ms) |")
            lines.append("|---|---:|---:|")
            for phase_key, payload in phase_timings.items():
                phase_summary = payload.get("summary", {})
                lines.append(
                    "| "
                    f"`{phase_key}` | "
                    f"{len(payload.get('samples', []))} | "
                    f"{float(phase_summary.get('p95', 0.0)):.3f} |"
                )
            lines.append("")
            phase_attribution = summary.get("first_frame_phase_attribution_ms", {})
            phase_attribution_ratios = summary.get(
                "first_frame_phase_attribution_ratio", {}
            )
            if phase_attribution:
                bucket_descriptions = attribution_schema.get(
                    "phase_bucket_semantics", {}
                )
                lines.append(f"### `{scenario_name}` First-Frame Phase Attribution")
                lines.append("")
                lines.append(
                    "| Phase bucket | Samples | p95 (ms) | p95 ratio | Semantics |"
                )
                lines.append("|---|---:|---:|---:|---|")
                for phase_key, payload in phase_attribution.items():
                    phase_summary = payload.get("summary", {})
                    ratio_summary = phase_attribution_ratios.get(
                        str(phase_key), {}
                    ).get("summary", {})
                    lines.append(
                        "| "
                        f"`{phase_key}` | "
                        f"{len(payload.get('samples', []))} | "
                        f"{float(phase_summary.get('p95', 0.0)):.3f} | "
                        f"{float(ratio_summary.get('p95', 0.0)):.3f} | "
                        f"{bucket_descriptions.get(str(phase_key), '')} |"
                    )
                lines.append("")
            setup_phase_timings = summary.get("setup_phase_timings_ms", {})
            if setup_phase_timings:
                lines.append(f"### `{scenario_name}` Setup Phase Timings")
                lines.append("")
                lines.append("| Phase | Samples | p95 (ms) |")
                lines.append("|---|---:|---:|")
                for phase_key, payload in setup_phase_timings.items():
                    phase_summary = payload.get("summary", {})
                    lines.append(
                        "| "
                        f"`{phase_key}` | "
                        f"{len(payload.get('samples', []))} | "
                        f"{float(phase_summary.get('p95', 0.0)):.3f} |"
                    )
                lines.append("")
    if interaction_benchmark:
        viewport = interaction_benchmark.get("viewport", {})
        lines.append("## Interaction Benchmark")
        lines.append("")
        lines.append(f"- Kind: `{interaction_benchmark.get('kind', '')}`")
        lines.append(f"- Render path: `{interaction_benchmark.get('render_path', '')}`")
        lines.append(
            f"- Driver: `{interaction_benchmark.get('measurement_driver', '')}`"
        )
        lines.append(
            f"- grabWindow readback included: `{bool(interaction_benchmark.get('grab_window_readback_included', False))}`"
        )
        lines.append(
            f"- No-readback frame metric: `{interaction_benchmark.get('frame_interval_metric', '')}`"
        )
        lines.append(
            f"- Edge renderer: `{interaction_benchmark.get('edge_renderer_kind', '')}`"
        )
        lines.append(
            f"- Requested edge renderer: `{interaction_benchmark.get('edge_renderer_requested_kind', '')}`"
        )
        lines.append(
            "- Edge renderer Canvas fallback active: "
            f"`{bool(interaction_benchmark.get('edge_renderer_canvas_fallback_active', False))}`"
        )
        lines.append(
            f"- Viewport: `{viewport.get('width', 0)}` x `{viewport.get('height', 0)}`"
        )
        lines.append(
            f"- Theme pair: `{interaction_benchmark.get('theme_id', '')}` / `{interaction_benchmark.get('graph_theme_id', '')}`"
        )
        lines.append(f"- Scenario: `{interaction_benchmark.get('scenario', '')}`")
        lines.append(
            f"- Media surface count: `{interaction_benchmark.get('media_surface_count', 0)}`"
        )
        animation_activity = interaction_benchmark.get("animation_activity", {})
        if animation_activity:
            lines.append(
                "- Animation activity: "
                f"instances=`{animation_activity.get('animator_instance_count', 0)}`, "
                f"loaded=`{animation_activity.get('animator_loaded_source_count', 0)}`, "
                f"visible=`{animation_activity.get('visible_animated_count', 0)}`, "
                f"playing=`{animation_activity.get('actively_playing_count', 0)}`, "
                f"offscreen paused=`{animation_activity.get('offscreen_paused_count', 0)}`, "
                f"idle paused=`{animation_activity.get('idle_paused_count', 0)}`"
            )
            lines.append(
                f"- Animation playback policy pass: `{bool(animation_activity.get('policy_pass', False))}`"
            )
        lines.append(
            f"- Real canvas path: `{bool(interaction_benchmark.get('uses_actual_canvas_render_path', False))}`"
        )
        lines.append(
            f"- Reused steady-state host: `{bool(interaction_benchmark.get('steady_state_canvas_host_reused', False))}`"
        )
        lines.append("")
    if renderer_diagnostics:
        lines.append("## Renderer Diagnostics")
        lines.append("")
        lines.append(f"- Qt version: `{renderer_diagnostics.get('qt_version', '')}`")
        lines.append(
            f"- QT_QPA_PLATFORM: `{renderer_diagnostics.get('qt_qpa_platform', '')}`"
        )
        lines.append(
            f"- EA_NODE_EDITOR_QML_HOST: `{renderer_diagnostics.get('qml_host_env', '')}`"
        )
        lines.append(
            f"- QT_QUICK_BACKEND: `{renderer_diagnostics.get('qt_quick_backend', '')}`"
        )
        lines.append(
            f"- QSG_RHI_BACKEND: `{renderer_diagnostics.get('qsg_rhi_backend', '')}`"
        )
        lines.append(
            f"- EA_NODE_EDITOR_QSG_RHI_BACKEND: `{renderer_diagnostics.get('qsg_rhi_backend_override', '')}`"
        )
        lines.append(
            "- Backend selection: "
            f"`{renderer_diagnostics.get('qtquick_backend_selection_reason', '')}` / "
            f"`{renderer_diagnostics.get('qtquick_backend_selected', '')}`"
        )
        lines.append(
            f"- QSG_RENDER_LOOP: `{renderer_diagnostics.get('qsg_render_loop', '')}`"
        )
        lines.append(
            f"- Graphics API: `{renderer_diagnostics.get('graphics_api', '')}`"
        )
        lines.append(
            f"- Graphics API label: `{renderer_diagnostics.get('graphics_api_label', '')}`"
        )
        lines.append(
            f"- QML host kind: `{renderer_diagnostics.get('qml_host_kind', '')}`"
        )
        lines.append(
            f"- Screen DPR: `{float(renderer_diagnostics.get('screen_device_pixel_ratio', 0.0)):.3f}`"
        )
        lines.append(
            f"- Effective window DPR: `{float(renderer_diagnostics.get('window_effective_device_pixel_ratio', 0.0)):.3f}`"
        )
        lines.append(
            f"- grabWindow readback included: `{bool(renderer_diagnostics.get('grab_window_readback_included', False))}`"
        )
        lines.append("")
    if display_diagnostics:
        lines.append("## Display Diagnostics")
        lines.append("")
        lines.append(f"- Qt platform: `{display_diagnostics.get('qt_platform', '')}`")
        lines.append(
            f"- Display attached: `{bool(display_diagnostics.get('display_attached', False))}`"
        )
        lines.append(
            f"- Active graphics API: `{display_diagnostics.get('active_graphics_api', '')}`"
        )
        lines.append(
            f"- Active graphics API label: `{display_diagnostics.get('active_graphics_api_label', '')}`"
        )
        lines.append(f"- RHI backend: `{display_diagnostics.get('rhi_backend', '')}`")
        lines.append(f"- Render loop: `{display_diagnostics.get('render_loop', '')}`")
        lines.append(f"- Host kind: `{display_diagnostics.get('host_kind', '')}`")
        lines.append(
            f"- Screen DPR: `{float(display_diagnostics.get('screen_device_pixel_ratio', 0.0)):.3f}`"
        )
        lines.append(
            "- Effective window DPR: "
            f"`{float(display_diagnostics.get('window_effective_device_pixel_ratio', 0.0)):.3f}`"
        )
        lines.append(
            "- Software fallback active: "
            f"`{bool(display_diagnostics.get('software_fallback_active', False))}`"
        )
        lines.append(
            f"- Software fallback reason: `{display_diagnostics.get('software_fallback_reason', '')}`"
        )
        lines.append(
            f"- Readback included: `{bool(display_diagnostics.get('readback_included', False))}`"
        )
        lines.append(
            f"- QSG_INFO capture enabled: `{bool(display_diagnostics.get('qsg_info_capture_enabled', False))}`"
        )
        blockers = display_diagnostics.get("acceptance_blockers", [])
        if blockers:
            lines.append(
                "- Acceptance blockers: `"
                + "`, `".join(str(item) for item in blockers)
                + "`"
            )
        lines.append("")
    if packet_verification_result or performance_acceptance_result:
        lines.append("## Acceptance Results")
        lines.append("")
        if packet_verification_result:
            lines.append(
                "- Packet verification: "
                f"`{packet_verification_result.get('status', '')}` - "
                f"{packet_verification_result.get('details', '')}"
            )
        if performance_acceptance_result:
            lines.append(
                "- Performance acceptance: "
                f"`{performance_acceptance_result.get('status', '')}` - "
                f"{performance_acceptance_result.get('details', '')}"
            )
        lines.append("")
    if feature_parity:
        lines.append("## Feature Parity Snapshot")
        lines.append("")
        lines.append(
            f"- Zero-loss enforced: `{bool(feature_parity.get('zero_loss_enforced', False))}`"
        )
        lines.append(
            f"- Result: `{'PASS' if feature_parity.get('pass', False) else 'FAIL'}`"
        )
        lines.append(
            f"- Grid visible: `{bool(feature_parity.get('show_grid', False))}`"
        )
        lines.append(
            f"- Minimap visible: `{bool(feature_parity.get('minimap_visible', False))}`"
        )
        lines.append(
            f"- Shadows enabled: `{bool(feature_parity.get('node_shadows_enabled', False))}`"
        )
        lines.append(
            f"- Notched ports enabled: `{bool(feature_parity.get('notched_ports_enabled', False))}`"
        )
        lines.append(
            f"- Port labels visible: `{bool(feature_parity.get('port_labels_visible', False))}`"
        )
        lines.append(
            f"- Edge crossing style: `{feature_parity.get('edge_crossing_style', '')}`"
        )
        lines.append(
            "- Embedded media surfaces: "
            f"`{int(feature_parity.get('embedded_media_count', 0))}` / "
            f"`{int(feature_parity.get('expected_embedded_media_count', 0))}`"
        )
        lines.append(
            f"- Embedded media ready states: `{int(feature_parity.get('embedded_media_ready_count', 0))}` ready; "
            f"`{feature_parity.get('embedded_media_preview_states', [])}`"
        )
        lines.append(
            f"- Edge renderer kind: `{feature_parity.get('edge_renderer_kind', '')}`"
        )
        lines.append(
            f"- Edge renderer fallback reason: `{feature_parity.get('edge_renderer_fallback_reason', '')}`"
        )
        lines.append(
            "- Simplification flags: "
            f"grid=`{bool(feature_parity.get('grid_simplification_active', False))}`, "
            f"minimap=`{bool(feature_parity.get('minimap_simplification_active', False))}`, "
            f"shadows=`{bool(feature_parity.get('shadow_simplification_active', False))}`, "
            f"edge_labels=`{bool(feature_parity.get('edge_label_simplification_active', False))}`"
        )
        failures = feature_parity.get("failures", [])
        if failures:
            lines.append(
                "- Failures: `" + "`, `".join(str(item) for item in failures) + "`"
            )
        lines.append("")
    if edge_renderer_ab:
        lines.append("## Edge Renderer A/B")
        lines.append("")
        lines.append(
            f"- Active renderer: `{edge_renderer_ab.get('active_renderer_kind', '')}`"
        )
        lines.append(
            f"- Requested renderer: `{edge_renderer_ab.get('requested_renderer_kind', '')}`"
        )
        lines.append(
            f"- Accepted renderer: `{edge_renderer_ab.get('accepted_renderer_kind', '')}`"
        )
        lines.append(
            f"- Canvas fallback active: `{bool(edge_renderer_ab.get('canvas_fallback_active', False))}`"
        )
        fallback_reason = str(edge_renderer_ab.get("fallback_reason", "")).strip()
        if fallback_reason:
            lines.append(f"- Fallback reason: `{fallback_reason}`")
        lines.append(
            f"- Rationale: {edge_renderer_ab.get('accepted_renderer_rationale', '')}"
        )
        lines.append("")
        lines.append(
            "| Variant | Role | Measured | Pan edge paint p95 (ms) | Zoom edge paint p95 (ms) |"
        )
        lines.append("|---|---|---:|---:|---:|")
        for variant in edge_renderer_ab.get("variants", []):
            lines.append(
                "| "
                f"{variant.get('kind', '')} | "
                f"{variant.get('role', '')} | "
                f"{bool(variant.get('measured', False))} | "
                f"{float(variant.get('pan_edge_paint_p95_ms', 0.0)):.3f} | "
                f"{float(variant.get('zoom_edge_paint_p95_ms', 0.0)):.3f} |"
            )
        lines.append("")
    if phase_timings:
        lines.append("## Phase Timings (ms)")
        lines.append("")
        lines.append("| Phase | p50 | p95 | Mean | Min | Max | Samples |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for phase_key in (
            "project_graph_load_ms",
            *_PROJECT_LOAD_PHASE_KEYS,
            "canvas_setup_ms",
            *_CANVAS_SETUP_PHASE_KEYS,
            "canvas_warmup_ms",
            "pan_interaction_ms",
            "zoom_interaction_ms",
            "node_drag_control_ms",
            "node_drag_first_offset_ms",
            "node_drag_steady_offset_ms",
            "node_drag_full_gesture_ms",
            "node_drag_end_clear_ms",
            "frame_interval_ms_without_readback",
            "pan_visible_model_query_ms",
            "zoom_visible_model_query_ms",
            "pan_edge_snapshot_build_ms",
            "zoom_edge_snapshot_build_ms",
            "pan_edge_snapshot_refresh_ms",
            "zoom_edge_snapshot_refresh_ms",
            "pan_edge_spatial_index_build_ms",
            "zoom_edge_spatial_index_build_ms",
            "pan_edge_paint_ms",
            "zoom_edge_paint_ms",
            "pan_grid_update_ms",
            "zoom_grid_update_ms",
            "pan_grid_paint_ms",
            "zoom_grid_paint_ms",
            "pan_overlay_sync_ms",
            "zoom_overlay_sync_ms",
        ):
            phase_entry = phase_timings.get(phase_key, {})
            summary = phase_entry.get("summary", {})
            phase_samples = phase_entry.get("samples", [])
            lines.append(
                "| "
                f"{phase_key} | "
                f"{float(summary.get('p50', 0.0)):.3f} | "
                f"{float(summary.get('p95', 0.0)):.3f} | "
                f"{float(summary.get('mean', 0.0)):.3f} | "
                f"{float(summary.get('min', 0.0)):.3f} | "
                f"{float(summary.get('max', 0.0)):.3f} | "
                f"{len(phase_samples)} |"
            )
        lines.append("")
    if profiling_counts:
        lines.append("## Targeted Profiling (Counts)")
        lines.append("")
        lines.append("| Metric | p50 | p95 | Mean | Min | Max | Samples |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for metric_key in (
            "pan_grid_update_count",
            "zoom_grid_update_count",
            "pan_visible_model_query_count",
            "zoom_visible_model_query_count",
            "pan_edge_snapshot_refresh_count",
            "zoom_edge_snapshot_refresh_count",
            "pan_total_node_count",
            "zoom_total_node_count",
            "pan_total_edge_count",
            "zoom_total_edge_count",
            "pan_candidate_edge_count",
            "zoom_candidate_edge_count",
            "pan_visible_edge_snapshot_count",
            "zoom_visible_edge_snapshot_count",
            "pan_skipped_edge_count",
            "zoom_skipped_edge_count",
            "pan_geometry_cache_hit_count",
            "zoom_geometry_cache_hit_count",
            "pan_geometry_cache_miss_count",
            "zoom_geometry_cache_miss_count",
            "pan_visible_node_delegate_count",
            "zoom_visible_node_delegate_count",
            "pan_visible_backdrop_delegate_count",
            "zoom_visible_backdrop_delegate_count",
            "pan_visible_node_card_count",
            "zoom_visible_node_card_count",
            "pan_delegate_create_count",
            "zoom_delegate_create_count",
            "pan_delegate_destroy_count",
            "zoom_delegate_destroy_count",
            "pan_active_node_surface_count",
            "zoom_active_node_surface_count",
            "pan_visible_edge_label_count",
            "zoom_visible_edge_label_count",
            "pan_visible_edge_count",
            "zoom_visible_edge_count",
            "pan_frame_scheduler_requested_redraw_count",
            "zoom_frame_scheduler_requested_redraw_count",
            "pan_frame_scheduler_view_state_redraw_request_count",
            "zoom_frame_scheduler_view_state_redraw_request_count",
            "pan_frame_scheduler_edge_redraw_request_count",
            "zoom_frame_scheduler_edge_redraw_request_count",
            "pan_frame_scheduler_overlay_redraw_request_count",
            "zoom_frame_scheduler_overlay_redraw_request_count",
            "pan_frame_scheduler_flushed_frame_count",
            "zoom_frame_scheduler_flushed_frame_count",
            "pan_frame_scheduler_coalesced_redraw_request_count",
            "zoom_frame_scheduler_coalesced_redraw_request_count",
            "pan_live_drag_offset_update_count",
            "zoom_live_drag_offset_update_count",
        ):
            metric_entry = profiling_counts.get(metric_key, {})
            summary = metric_entry.get("summary", {})
            metric_samples = metric_entry.get("samples", [])
            lines.append(
                "| "
                f"{metric_key} | "
                f"{float(summary.get('p50', 0.0)):.3f} | "
                f"{float(summary.get('p95', 0.0)):.3f} | "
                f"{float(summary.get('mean', 0.0)):.3f} | "
                f"{float(summary.get('min', 0.0)):.3f} | "
                f"{float(summary.get('max', 0.0)):.3f} | "
                f"{len(metric_samples)} |"
            )
        lines.append("")
    if stress_breakdown:
        lines.append("## Stress 1200 Bottleneck Breakdown")
        lines.append("")
        next_bottleneck = stress_breakdown.get("next_measured_bottleneck", {})
        if next_bottleneck.get("metric_key"):
            lines.append(
                "- Next measured bottleneck: "
                f"`{next_bottleneck.get('label', '')}` "
                f"({float(next_bottleneck.get('value', 0.0)):.3f} "
                f"{next_bottleneck.get('unit', '')} {next_bottleneck.get('stat', '')})"
            )
        else:
            lines.append(
                "- Next measured bottleneck: unavailable "
                f"({next_bottleneck.get('unavailable_reason', 'no timing samples')})"
            )
        backend_state = stress_breakdown.get("backend_state", {})
        lines.append(
            "- Backend state: "
            f"graphics_api=`{backend_state.get('graphics_api_label', '')}`, "
            f"host=`{backend_state.get('qml_host_kind', '')}`, "
            f"host_env=`{backend_state.get('qml_host_env', '')}`, "
            f"qpa=`{backend_state.get('qt_qpa_platform', '')}`, "
            f"rhi=`{backend_state.get('qsg_rhi_backend', '')}`, "
            f"override=`{backend_state.get('qsg_rhi_backend_override', '')}`, "
            f"render_loop=`{backend_state.get('qsg_render_loop', '')}`"
        )
        lines.append("")
        lines.append("| Group | Metric | p95 / State | Samples | Availability |")
        lines.append("|---|---|---:|---:|---|")
        for group in stress_breakdown.get("groups", []):
            group_name = str(group.get("name", ""))
            for metric in group.get("metrics", []):
                if metric.get("available"):
                    value_text = f"{float(metric.get('value', 0.0)):.3f} {metric.get('unit', '')}"
                    availability_text = "available"
                else:
                    value_text = "unavailable"
                    availability_text = str(
                        metric.get("unavailable_reason", "not captured")
                    )
                lines.append(
                    "| "
                    f"{group_name} | "
                    f"{metric.get('label', metric.get('metric_key', ''))} | "
                    f"{value_text} | "
                    f"{int(metric.get('sample_count', 0))} | "
                    f"{availability_text} |"
                )
        lines.append("")
    lines.append("## Metrics (ms)")
    lines.append("")
    lines.append("| Metric | p50 | p95 | Mean | Min | Max |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    lines.append(
        f"| Project + graph load | {load['p50']:.3f} | {load['p95']:.3f} | {load['mean']:.3f} | {load['min']:.3f} | {load['max']:.3f} |"
    )
    lines.append(
        f"| Pan interaction | {pan['p50']:.3f} | {pan['p95']:.3f} | {pan['mean']:.3f} | {pan['min']:.3f} | {pan['max']:.3f} |"
    )
    lines.append(
        f"| Zoom interaction | {zoom['p50']:.3f} | {zoom['p95']:.3f} | {zoom['mean']:.3f} | {zoom['min']:.3f} | {zoom['max']:.3f} |"
    )
    lines.append(
        f"| Pan + zoom (combined) | {combined['p50']:.3f} | {combined['p95']:.3f} | {combined['mean']:.3f} | {combined['min']:.3f} | {combined['max']:.3f} |"
    )
    lines.append(
        f"| Node-drag legacy single-offset control | {node_drag_control['p50']:.3f} | {node_drag_control['p95']:.3f} | {node_drag_control['mean']:.3f} | {node_drag_control['min']:.3f} | {node_drag_control['max']:.3f} |"
    )
    lines.append(
        f"| Node-drag first offset | {node_drag_first_offset['p50']:.3f} | {node_drag_first_offset['p95']:.3f} | {node_drag_first_offset['mean']:.3f} | {node_drag_first_offset['min']:.3f} | {node_drag_first_offset['max']:.3f} |"
    )
    lines.append(
        f"| Node-drag steady offset | {node_drag_steady_offset['p50']:.3f} | {node_drag_steady_offset['p95']:.3f} | {node_drag_steady_offset['mean']:.3f} | {node_drag_steady_offset['min']:.3f} | {node_drag_steady_offset['max']:.3f} |"
    )
    lines.append(
        f"| Node-drag full gesture | {node_drag_full_gesture['p50']:.3f} | {node_drag_full_gesture['p95']:.3f} | {node_drag_full_gesture['mean']:.3f} | {node_drag_full_gesture['min']:.3f} | {node_drag_full_gesture['max']:.3f} |"
    )
    lines.append(
        f"| Node-drag end/clear | {node_drag_end_clear['p50']:.3f} | {node_drag_end_clear['p95']:.3f} | {node_drag_end_clear['mean']:.3f} | {node_drag_end_clear['min']:.3f} | {node_drag_end_clear['max']:.3f} |"
    )
    lines.append(
        "| Frame interval without readback | "
        f"{frame_interval_without_readback['p50']:.3f} | "
        f"{frame_interval_without_readback['p95']:.3f} | "
        f"{frame_interval_without_readback['mean']:.3f} | "
        f"{frame_interval_without_readback['min']:.3f} | "
        f"{frame_interval_without_readback['max']:.3f} |"
    )
    lines.append("")
    lines.append("## Supplemental Selected Drag")
    lines.append("")
    if not supplemental_selected_drag.get("supported", False):
        lines.append(
            "- Unavailable: "
            f"{supplemental_selected_drag.get('unavailable_reason', 'unsupported by this build')}"
        )
    else:
        selected_metrics = supplemental_selected_drag.get("metrics", {})
        lines.append("- Supplemental only; formal drag and frame gates are unchanged.")
        lines.append(
            f"- Selected nodes: `{supplemental_selected_drag.get('selected_node_ids', [])}`"
        )
        lines.append(
            "- Membership size verified: "
            f"`{supplemental_selected_drag.get('membership_size', {}).get('verified')}`"
        )
        lines.append(
            "- Membership freeze verified: "
            f"`{supplemental_selected_drag.get('membership_freeze', {}).get('verified')}`"
        )
        lines.append("")
        lines.append("| Metric | p50 (ms) | p95 (ms) | Samples |")
        lines.append("|---|---:|---:|---:|")
        for metric_key in (
            "first_offset_ms",
            "steady_offset_ms",
            "full_gesture_ms",
            "end_clear_ms",
            "frame_interval_ms_without_readback",
        ):
            metric = selected_metrics.get(metric_key, {})
            summary = metric.get("summary", {})
            lines.append(
                f"| `{metric_key}` | {float(summary.get('p50', 0.0)):.3f} | "
                f"{float(summary.get('p95', 0.0)):.3f} | {len(metric.get('samples', []))} |"
            )
    lines.append("")
    lines.append("## Requirement Check")
    lines.append("")
    lines.append("| Requirement | Result | Details |")
    lines.append("|---|---|---|")
    for requirement_id, entry in report["requirements_eval"].items():
        result = "PASS" if entry["pass"] else "FAIL"
        lines.append(f"| {requirement_id} | {result} | {entry['details']} |")
    lines.append("")
    if baseline_series:
        lines.append("## Baseline Series")
        lines.append("")
        lines.append(f"- Mode: `{baseline_series.get('mode', 'offscreen')}`")
        lines.append(f"- Tag: `{baseline_series.get('tag', 'local')}`")
        lines.append(
            f"- Scenario: `{baseline_series.get('scenario', _DEFAULT_BENCHMARK_SCENARIO)}`"
        )
        lines.append(f"- Run count: `{baseline_series.get('run_count', 0)}`")
        lines.append("")
        lines.append(
            "| Run | Mode | Load p95 (ms) | Pan p95 (ms) | Zoom p95 (ms) | "
            "Pan+Zoom p95 (ms) | Drag legacy p95 (ms) | Drag steady p95 (ms) | "
            "Drag full p95 (ms) | Frame p95 no-readback (ms) | Host | RHI | Qt Platform | Machine |"
        )
        lines.append(
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|"
        )
        for run in baseline_series.get("runs", []):
            env = run.get("environment", {})
            run_metrics = run.get("metrics", {})
            lines.append(
                "| "
                f"{run.get('run_id', '')} | "
                f"{run.get('mode', '')} | "
                f"{float(run_metrics.get('load_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('pan_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('zoom_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('pan_zoom_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('node_drag_control_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('node_drag_steady_offset_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('node_drag_full_gesture_p95_ms', 0.0)):.3f} | "
                f"{float(run_metrics.get('frame_interval_without_readback_p95_ms', 0.0)):.3f} | "
                f"{env.get('qml_host_kind_selected', env.get('qml_host_env', ''))} | "
                f"{env.get('qsg_rhi_backend_override', env.get('qsg_rhi_backend', ''))} | "
                f"{env.get('qt_qpa_platform', '')} | "
                f"{env.get('machine', '')} |"
            )
        lines.append("")
        lines.append("### Variance Policy")
        lines.append("")
        thresholds = baseline_series.get("variance_thresholds", {})
        variance_eval = baseline_series.get("variance_eval", {})
        lines.append(
            "| Metric | CV Threshold | Range Threshold (ms) | Observed CV | Observed Range (ms) | Result |"
        )
        lines.append("|---|---:|---:|---:|---:|---|")
        for metric_key in (
            "load_p95_ms",
            "pan_p95_ms",
            "zoom_p95_ms",
            "pan_zoom_p95_ms",
            "node_drag_control_p95_ms",
            "node_drag_first_offset_p95_ms",
            "node_drag_steady_offset_p95_ms",
            "node_drag_full_gesture_p95_ms",
            "node_drag_end_clear_p95_ms",
            "frame_interval_without_readback_p95_ms",
        ):
            threshold = thresholds.get(metric_key, {})
            observed = variance_eval.get(metric_key, {})
            result = "PASS" if observed.get("pass", False) else "FAIL"
            lines.append(
                "| "
                f"{metric_key} | "
                f"{float(threshold.get('max_cv', 0.0)):.2f} | "
                f"{float(threshold.get('max_range_ms', 0.0)):.1f} | "
                f"{float(observed.get('cv', 0.0)):.4f} | "
                f"{float(observed.get('range_ms', 0.0)):.3f} | "
                f"{result} |"
            )
        lines.append("")
        lines.append("### Triage")
        lines.append("")
        for item in baseline_series.get("triage_policy", []):
            lines.append(f"- {item}")
        note = str(baseline_series.get("notes", "")).strip()
        if note:
            lines.append("")
            lines.append(f"- Note: {note}")
        lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


_COMPARISON_SCALAR_METRICS = (
    (
        "load_p95_ms",
        ("metrics", "project_graph_load_ms", "summary", "p95"),
        1.0,
    ),
    (
        "pan_zoom_p95_ms",
        ("metrics", "pan_zoom_combined_ms", "summary", "p95"),
        1.0,
    ),
    (
        "node_drag_steady_offset_p95_ms",
        ("metrics", "node_drag_steady_offset_ms", "summary", "p95"),
        1.0,
    ),
    (
        "process_rss_end_mib",
        ("process_resources", "rss_end_bytes"),
        1.0 / (1024.0 * 1024.0),
    ),
)


def _report_scalar(
    report: Mapping[str, Any],
    path: tuple[str, ...],
    *,
    scale: float = 1.0,
) -> float | None:
    value: Any = report
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    try:
        return float(value) * scale
    except (TypeError, ValueError):
        return None


def _comparison_rows(
    current_report: Mapping[str, Any],
    reference_report: Mapping[str, Any],
) -> list[tuple[str, float | None, float | None]]:
    rows = [
        (
            label,
            _report_scalar(reference_report, path, scale=scale),
            _report_scalar(current_report, path, scale=scale),
        )
        for label, path, scale in _COMPARISON_SCALAR_METRICS
    ]
    for scenario in _MUTATION_BENCHMARK_SCENARIOS:
        path = (
            "graph_mutation_benchmark",
            "scenario_summaries",
            scenario,
            "mutation_wall_clock_samples_ms",
            "summary",
            "p95",
        )
        reference_value = _report_scalar(reference_report, path)
        current_value = _report_scalar(current_report, path)
        if reference_value is not None or current_value is not None:
            rows.append(
                (
                    f"mutation.{scenario}.wall_p95_ms",
                    reference_value,
                    current_value,
                )
            )
    return rows


def _format_report_comparison(
    current_report: Mapping[str, Any],
    reference_report: Mapping[str, Any],
) -> str:
    rows = _comparison_rows(current_report, reference_report)
    metric_width = max(len("metric"), *(len(label) for label, _, _ in rows))
    lines = [
        "comparison (lower is better)",
        f"{'metric':<{metric_width}}  {'reference':>12}  {'current':>12}  {'delta':>12}  {'delta_pct':>10}",
    ]
    for label, reference_value, current_value in rows:
        reference_text = "n/a" if reference_value is None else f"{reference_value:.3f}"
        current_text = "n/a" if current_value is None else f"{current_value:.3f}"
        if reference_value is None or current_value is None:
            delta_text = "n/a"
            delta_pct_text = "n/a"
        else:
            delta = current_value - reference_value
            delta_text = f"{delta:+.3f}"
            delta_pct_text = (
                "n/a"
                if reference_value == 0.0
                else f"{(delta / reference_value) * 100.0:+.2f}%"
            )
        lines.append(
            f"{label:<{metric_width}}  {reference_text:>12}  {current_text:>12}  "
            f"{delta_text:>12}  {delta_pct_text:>10}"
        )
    return "\n".join(lines)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track H performance harness for COREX Node Editor."
    )
    parser.add_argument("--nodes", type=int, default=1000, help="Synthetic node count.")
    parser.add_argument("--edges", type=int, default=5000, help="Synthetic edge count.")
    parser.add_argument(
        "--seed", type=int, default=1337, help="Deterministic random seed."
    )
    parser.add_argument(
        "--load-iterations", type=int, default=5, help="Project/graph load iterations."
    )
    parser.add_argument(
        "--interaction-samples", type=int, default=200, help="Pan/zoom sample count."
    )
    parser.add_argument(
        "--interaction-warmup-samples",
        type=int,
        default=3,
        help="Unmeasured warmup interaction cycles to run on the real canvas host before steady-state sampling.",
    )
    parser.add_argument(
        "--interaction-zoom-min",
        type=float,
        default=0.5,
        help="Minimum zoom factor used by interaction sampling.",
    )
    parser.add_argument(
        "--interaction-zoom-max",
        type=float,
        default=2.0,
        help="Maximum zoom factor used by interaction sampling.",
    )
    parser.add_argument(
        "--node-insertion-samples",
        type=int,
        default=40,
        help="Measured node-insertion sample budget balanced across profiles (default: 40).",
    )
    parser.add_argument(
        "--node-insertion-warmup-samples",
        type=int,
        default=3,
        help="Unmeasured warmup insertions per node-insertion profile (default: 3).",
    )
    parser.add_argument(
        "--scenario",
        choices=_BENCHMARK_SCENARIOS,
        default=_DEFAULT_BENCHMARK_SCENARIO,
        help="Benchmark scene composition to load into GraphCanvas.qml when no project fixture is selected.",
    )
    parser.add_argument(
        "--mutation-scenario",
        action="append",
        choices=_MUTATION_BENCHMARK_SCENARIOS,
        default=[],
        help=(
            "Repeat to select graph_mutations cases. Omit to run the full canonical "
            "mutation scenario set."
        ),
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Load this .cxproj project through JsonProjectSerializer instead of generating a synthetic scenario.",
    )
    parser.add_argument(
        "--workspace-id",
        type=str,
        default="",
        help="Workspace id to benchmark when --project-path or --stress-fixture is used.",
    )
    parser.add_argument(
        "--stress-fixture",
        choices=_STRESS_FIXTURE_MODES,
        default="",
        help=(
            "Use the canonical real stress-1200 fixture at "
            "examples/stress_1200_nodes.cxproj."
        ),
    )
    parser.add_argument(
        "--baseline-runs",
        type=int,
        default=1,
        help="Number of repeated baseline runs for variance analysis.",
    )
    parser.add_argument(
        "--baseline-in-process",
        action="store_true",
        help=(
            "Diagnostic opt-out that keeps repeated baselines in this process; "
            "isolated child processes are the default for --baseline-runs > 1."
        ),
    )
    parser.add_argument(
        "--baseline-mode",
        choices=("auto", "offscreen", "interactive"),
        default="auto",
        help="Label for run mode; auto resolves from active Qt platform.",
    )
    parser.add_argument(
        "--baseline-tag",
        type=str,
        default="local",
        help="Free-form tag for grouping baseline runs (e.g., pilot_hw_a).",
    )
    parser.add_argument(
        "--qt-platform",
        type=str,
        default="",
        help="Optional override for QT_QPA_PLATFORM before creating QApplication.",
    )
    parser.add_argument(
        "--qml-host",
        choices=(QML_HOST_QQUICKWIDGET, QML_HOST_QQUICKVIEW_CONTAINER),
        default="",
        help="Optional override for EA_NODE_EDITOR_QML_HOST before creating the Qt Quick host.",
    )
    parser.add_argument(
        "--qsg-rhi-backend",
        choices=("auto", "d3d11", "d3d12", "opengl", "vulkan", "metal", "software"),
        default="",
        help="Optional override for EA_NODE_EDITOR_QSG_RHI_BACKEND before creating QApplication.",
    )
    parser.add_argument(
        "--capture-qsg-info",
        action="store_true",
        help="Set QSG_INFO=1 before Qt Quick initialization and record scene graph diagnostics in process logs.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("docs/specs/perf"),
        help="Output folder for benchmark reports.",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        default=None,
        help="Compare a bounded scalar metric table with an existing report JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.qt_platform:
        os.environ["QT_QPA_PLATFORM"] = args.qt_platform
    if args.qml_host:
        os.environ[QML_HOST_ENV] = args.qml_host
    if args.qsg_rhi_backend:
        os.environ[BACKEND_OVERRIDE_ENV] = args.qsg_rhi_backend
    if args.capture_qsg_info:
        os.environ["QSG_INFO"] = "1"
    configure_qtquick_backend()
    resolved_qml_host = (
        normalize_qml_host_kind(args.qml_host)
        or os.environ.get(QML_HOST_ENV, "").strip()
    )
    resolved_qsg_rhi_backend = (
        normalize_qsg_rhi_backend_override(args.qsg_rhi_backend)
        or os.environ.get(BACKEND_OVERRIDE_ENV, "").strip()
    )
    resolved_mode = _resolve_baseline_mode(
        args.baseline_mode, os.environ.get("QT_QPA_PLATFORM", "")
    )
    config = BenchmarkConfig(
        synthetic_graph=SyntheticGraphConfig(
            node_count=args.nodes,
            edge_count=args.edges,
            seed=args.seed,
        ),
        load_iterations=args.load_iterations,
        interaction_samples=args.interaction_samples,
        interaction_warmup_samples=args.interaction_warmup_samples,
        interaction_zoom_min=args.interaction_zoom_min,
        interaction_zoom_max=args.interaction_zoom_max,
        scenario=args.scenario,
        project_path=str(args.project_path or ""),
        workspace_id=args.workspace_id,
        stress_fixture=args.stress_fixture,
        qml_host=resolved_qml_host,
        qsg_rhi_backend=resolved_qsg_rhi_backend,
        node_insertion_samples=args.node_insertion_samples,
        node_insertion_warmup_samples=args.node_insertion_warmup_samples,
        mutation_scenarios=tuple(args.mutation_scenario),
    )
    report_dir: Path = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    report = run_benchmark(
        config,
        baseline_runs=args.baseline_runs,
        baseline_mode=resolved_mode,
        baseline_tag=args.baseline_tag,
        report_dir=report_dir,
        isolate_baseline_runs=not args.baseline_in_process,
    )

    reference_report: dict[str, Any] | None = None
    if args.compare_to is not None:
        reference_report = json.loads(args.compare_to.read_text(encoding="utf-8"))
    json_path = report_dir / "track_h_benchmark_report.json"
    md_path = report_dir / "TRACK_H_BENCHMARK_REPORT.md"
    _write_json_atomic(report, json_path)
    _write_markdown_report(report, md_path)

    load = report["metrics"]["project_graph_load_ms"]["summary"]
    pan_zoom = report["metrics"]["pan_zoom_combined_ms"]["summary"]
    node_drag_control = report["metrics"]["node_drag_control_ms"]["summary"]
    node_drag_steady_offset = report["metrics"]["node_drag_steady_offset_ms"]["summary"]
    node_drag_full_gesture = report["metrics"]["node_drag_full_gesture_ms"]["summary"]
    frame_interval_without_readback = report["metrics"][
        "frame_interval_ms_without_readback"
    ]["summary"]
    baseline = report.get("baseline_series", {})
    print(f"Benchmark report written: {md_path}")
    print(f"Benchmark data written:   {json_path}")
    if baseline:
        print(
            "baseline_mode="
            f"{baseline.get('mode', 'offscreen')} baseline_runs={baseline.get('run_count', 1)}"
        )
    print(f"scenario={report['config']['scenario']}")
    process_resources = report.get("process_resources", {})
    print(f"process_cpu_percent={float(process_resources.get('cpu_percent', 0.0)):.3f}")
    print(f"process_rss_end_bytes={int(process_resources.get('rss_end_bytes', 0))}")
    animation_activity = report.get("feature_parity", {}).get("animation_activity", {})
    if animation_activity:
        print(
            f"animation_animator_instance_count={animation_activity.get('animator_instance_count', 0)}"
        )
        print(
            f"animation_visible_count={animation_activity.get('visible_animated_count', 0)}"
        )
        print(
            f"animation_playing_count={animation_activity.get('actively_playing_count', 0)}"
        )
        print(f"animation_policy_pass={animation_activity.get('policy_pass', False)}")
    print(f"qml_host={report['renderer_diagnostics'].get('qml_host_kind', '')}")
    print(
        f"qsg_rhi_backend_override={report['renderer_diagnostics'].get('qsg_rhi_backend_override', '')}"
    )
    print(
        f"graphics_api_label={report['renderer_diagnostics'].get('graphics_api_label', '')}"
    )
    print(
        f"edge_renderer_kind={report.get('interaction_benchmark', {}).get('edge_renderer_kind', '')}"
    )
    print(
        "edge_renderer_canvas_fallback_active="
        f"{report.get('interaction_benchmark', {}).get('edge_renderer_canvas_fallback_active', False)}"
    )
    if report.get("graph_mutation_benchmark"):
        mutation_benchmark = report["graph_mutation_benchmark"]
        print(f"graph_mutation_status={mutation_benchmark.get('status', '')}")
        print(
            f"graph_mutation_sample_count={mutation_benchmark.get('sample_count', 0)}"
        )
    if report.get("node_insertion_benchmark"):
        insertion_benchmark = report["node_insertion_benchmark"]
        print(
            "node_insertion_acceptance="
            f"{insertion_benchmark.get('acceptance_result', {}).get('status', '')}"
        )
        for profile_name in insertion_benchmark.get("profiles", []):
            profile_summary = insertion_benchmark.get("profile_summaries", {}).get(
                profile_name,
                {},
            )
            presented_p95 = (
                profile_summary.get(
                    "all_primary_delegates_presented_ms",
                    {},
                )
                .get("summary", {})
                .get("p95", 0.0)
            )
            print(f"node_insertion_{profile_name}_p95_ms={float(presented_p95):.3f}")
    display_diagnostics = report.get("display_diagnostics", {})
    print(f"display_attached={display_diagnostics.get('display_attached', False)}")
    print(
        f"software_fallback_active={display_diagnostics.get('software_fallback_active', False)}"
    )
    print(
        f"qsg_info_capture_enabled={display_diagnostics.get('qsg_info_capture_enabled', False)}"
    )
    print(
        f"packet_verification_result={report.get('packet_verification_result', {}).get('status', '')}"
    )
    print(
        f"performance_acceptance_result={report.get('performance_acceptance_result', {}).get('status', '')}"
    )
    if report.get("fixture_metadata"):
        fixture = report["fixture_metadata"]
        print(f"fixture_source_kind={fixture.get('fixture_source_kind', '')}")
        print(
            f"display_acceptance_eligible={fixture.get('display_acceptance_eligible', False)}"
        )
        print(f"fixture_project_path={fixture.get('project_path', '')}")
        print(f"fixture_checksum_sha256={fixture.get('fixture_checksum_sha256', '')}")
        print(f"fixture_workspace_id={fixture.get('workspace_id', '')}")
        print(f"fixture_nodes={fixture.get('node_count', 0)}")
        print(f"fixture_edges={fixture.get('edge_count', 0)}")
    print(f"load_p50_ms={load['p50']:.3f}")
    print(f"load_p95_ms={load['p95']:.3f}")
    print(f"pan_zoom_p50_ms={pan_zoom['p50']:.3f}")
    print(f"pan_zoom_p95_ms={pan_zoom['p95']:.3f}")
    print(f"node_drag_control_p95_ms={node_drag_control['p95']:.3f}")
    print(f"node_drag_steady_offset_p95_ms={node_drag_steady_offset['p95']:.3f}")
    print(f"node_drag_full_gesture_p95_ms={node_drag_full_gesture['p95']:.3f}")
    print(
        f"frame_interval_without_readback_p95_ms={frame_interval_without_readback['p95']:.3f}"
    )
    if reference_report is not None:
        print(f"compare_to={args.compare_to}")
        print(_format_report_comparison(report, reference_report))
    return 1 if int(baseline.get("failed_run_count", 0) or 0) > 0 else 0


def _run_cli() -> None:
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Qt scenegraph teardown can leave non-Python threads alive after the
    # benchmark has written its artifacts. The CLI is a one-shot verifier, so
    # terminate once main() has completed successfully or failed.
    os._exit(exit_code)


if __name__ == "__main__":
    _run_cli()
