"""Detailed pan/zoom canvas profiler for EA Node Editor.

Goal
----
Pinpoint what causes lag in the GraphCanvas during pan/zoom interactions on
high-DPI desktops, especially when "heavy" nodes (passive media, viewers) are
present. The user reports lower FPS during pan/zoom on a 4K@200% display.

What this profiler measures
---------------------------
1. Per pan/zoom step wall-clock cost on the *real* GraphCanvas.qml render path,
   reusing the steady-state benchmark host that ships in
   `ea_node_editor.ui.perf.performance_harness`.
2. Per-component breakdown via Python monkey-patches on the hot path:
     * `ViewportBridge.set_view_state`
     * `ViewportBridge._refresh_visible_scene_rect_cache`
     * `EmbeddedViewerOverlayManager._sync_impl` (run as a separate
       micro-benchmark over a synthetic scene tree)
3. cProfile capture over the steady-state pan/zoom loop to surface the top
   Python functions by cumulative time.
4. A device-pixel-ratio (DPR) ablation: same scenario rendered with the user's
   native DPR vs `QT_SCALE_FACTOR=1.0`. The delta isolates the cost imposed by
   high-DPI compositing.

Output
------
- `artifacts/canvas_lag_profiling/profile_<timestamp>/profile_results.json`
- A markdown summary, plus matplotlib PNG charts for visual inspection.

The profiler runs each scenario in a fresh subprocess so DPR overrides and Qt
state stay isolated. Sub-runs use the `windows` Qt platform plugin so the
display's actual scale factor is honoured.

Usage
-----
    venv\\Scripts\\python scripts/profile_canvas_lag.py
    venv\\Scripts\\python scripts/profile_canvas_lag.py --samples 30
    venv\\Scripts\\python scripts/profile_canvas_lag.py --skip-dpr-ablation

This script is intentionally side-effect free with respect to the repo: it only
writes into `artifacts/canvas_lag_profiling/`.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import queue
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

QML_HOST_ENV = "EA_NODE_EDITOR_QML_HOST"
QSG_RHI_BACKEND_ENV = "EA_NODE_EDITOR_QSG_RHI_BACKEND"

_ENGINEERING_WORKSPACE_ID = "ws_canvas_engineering"
_ENGINEERING_PANEL_NODE_ID = "node_canvas_panel"
_ENGINEERING_CAD_NODE_ID = "node_canvas_cad_import"
_ENGINEERING_VIEWER_NODE_ID = "node_canvas_model_viewer"
_ENGINEERING_UNRELATED_NODE_ID = "node_canvas_unrelated"
_ENGINEERING_WIRE_SOURCE_NODE_ID = "node_canvas_wire_source"
_ENGINEERING_WIRE_TARGET_A_NODE_ID = "node_canvas_wire_target_a"
_ENGINEERING_WIRE_TARGET_B_NODE_ID = "node_canvas_wire_target_b"

_ENGINEERING_OPERATION_ORDER = (
    "startup_proxy",
    "proxy_pan_control",
    "proxy_zoom_control",
    "selection_without_activation",
    "hover_without_activation",
    "single_click_without_activation",
    "proxy_double_click_activation",
    "live_wheel_zoom",
    "live_box_zoom",
    "active_viewer_drag",
    "active_viewer_resize",
    "canvas_click_demotion",
    "retained_proxy_pan",
    "retained_proxy_zoom",
    "double_click_reactivation",
    "active_wire_drag",
    "unrelated_property_edit",
    "unrelated_node_add",
    "unrelated_node_delete",
    "unrelated_wire_create",
    "unrelated_wire_reroute",
    "unrelated_wire_delete",
    "viewer_deletion",
)

_ENGINEERING_CONTINUOUS_OPERATION_NAMES = (
    "proxy_pan_control",
    "proxy_zoom_control",
    "live_wheel_zoom",
    "live_box_zoom",
    "active_viewer_drag",
    "active_viewer_resize",
    "retained_proxy_pan",
    "retained_proxy_zoom",
    "active_wire_drag",
)


def _build_engineering_project(step_path: Path, registry: Any) -> Any:
    """Build the production Panel -> CAD Import -> Model Viewer graph."""
    from ea_node_editor.graph.project_state import ProjectData
    from ea_node_editor.graph.records import EdgeInstance, NodeInstance
    from ea_node_editor.graph.workspace_state import ViewState, WorkspaceData
    from ea_node_editor.nodes.instance_resolution import resolve_instance_ports

    def node(
        node_id: str,
        type_id: str,
        title: str,
        x: float,
        y: float,
        *,
        properties: dict[str, Any] | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> NodeInstance:
        values = registry.default_properties(type_id)
        values.update(properties or {})
        ports = resolve_instance_ports(
            registry.resolve_spec(type_id, values),
            values,
            data_types=registry.data_types,
        )
        return NodeInstance(
            node_id=node_id,
            type_id=type_id,
            title=title,
            x=x,
            y=y,
            properties=values,
            exposed_ports={port.key: bool(port.exposed) for port in ports},
            custom_width=width,
            custom_height=height,
        )

    workspace = WorkspaceData(
        workspace_id=_ENGINEERING_WORKSPACE_ID,
        name="Canvas Engineering Profile",
    )
    workspace.views["view_canvas_engineering"] = ViewState(
        view_id="view_canvas_engineering",
        name="Profile",
        zoom=0.8,
        pan_x=80.0,
        pan_y=0.0,
    )
    workspace.active_view_id = "view_canvas_engineering"
    workspace.nodes = {
        _ENGINEERING_PANEL_NODE_ID: node(
            _ENGINEERING_PANEL_NODE_ID,
            "data.panel",
            "STEP Path",
            -650.0,
            40.0,
            properties={"value": str(step_path.resolve())},
            width=300.0,
            height=180.0,
        ),
        _ENGINEERING_CAD_NODE_ID: node(
            _ENGINEERING_CAD_NODE_ID,
            "engineering.cad_import",
            "CAD Import",
            -260.0,
            40.0,
            properties={"length_unit": "mm"},
            width=320.0,
        ),
        _ENGINEERING_VIEWER_NODE_ID: node(
            _ENGINEERING_VIEWER_NODE_ID,
            "model.viewer",
            "Model Viewer",
            160.0,
            20.0,
            width=720.0,
            height=560.0,
        ),
        _ENGINEERING_UNRELATED_NODE_ID: node(
            _ENGINEERING_UNRELATED_NODE_ID,
            "data.boolean_toggle",
            "Unrelated Toggle",
            -260.0,
            420.0,
        ),
        _ENGINEERING_WIRE_SOURCE_NODE_ID: node(
            _ENGINEERING_WIRE_SOURCE_NODE_ID,
            "core.constant",
            "Wire Source",
            980.0,
            40.0,
        ),
        _ENGINEERING_WIRE_TARGET_A_NODE_ID: node(
            _ENGINEERING_WIRE_TARGET_A_NODE_ID,
            "core.python_script",
            "Wire Target A",
            1220.0,
            40.0,
        ),
        _ENGINEERING_WIRE_TARGET_B_NODE_ID: node(
            _ENGINEERING_WIRE_TARGET_B_NODE_ID,
            "core.python_script",
            "Wire Target B",
            1220.0,
            300.0,
        ),
    }
    workspace.edges = {
        "edge_panel_to_cad": EdgeInstance(
            edge_id="edge_panel_to_cad",
            source_node_id=_ENGINEERING_PANEL_NODE_ID,
            source_port_key="output",
            target_node_id=_ENGINEERING_CAD_NODE_ID,
            target_port_key="path",
        ),
        "edge_cad_to_viewer": EdgeInstance(
            edge_id="edge_cad_to_viewer",
            source_node_id=_ENGINEERING_CAD_NODE_ID,
            source_port_key="scene",
            target_node_id=_ENGINEERING_VIEWER_NODE_ID,
            target_port_key="scene_1",
        ),
    }
    return ProjectData(
        project_id="proj_canvas_engineering",
        name="Canvas Engineering Profile",
        active_workspace_id=workspace.workspace_id,
        workspaces={workspace.workspace_id: workspace},
    )


def _run_engineering_workflow(
    *,
    step_path: Path,
    registry: Any,
    project: Any,
) -> tuple[
    Any,
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    from ea_node_editor.execution.protocol_codec import (
        coerce_start_run_command,
        event_to_dict,
    )
    from ea_node_editor.execution.viewer_messages import UpdateViewerSessionCommand
    from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
    from ea_node_editor.execution.worker import run_workflow
    from ea_node_editor.execution.worker_services import WorkerServices
    from ea_node_editor.runtime_contracts import (
        COREX_VIEWER_SESSION_HANDLE_KIND,
        VIEWER_SESSION_DATA_TYPE_ID,
        default_viewer_session_id,
    )

    worker_services = WorkerServices()
    worker_services.bind_data_types(registry.data_types)
    runtime_snapshot = build_runtime_snapshot(
        project,
        workspace_id=_ENGINEERING_WORKSPACE_ID,
        registry=registry,
    )
    event_queue: queue.Queue[Any] = queue.Queue()
    run_id = "run_canvas_engineering_profile"
    run_workflow(
        coerce_start_run_command(
            {
                "run_id": run_id,
                "project_path": str(step_path.resolve()),
                "workspace_id": _ENGINEERING_WORKSPACE_ID,
                "runtime_snapshot": runtime_snapshot,
                "trigger": {},
                "plugin_bundles": registry.plugin_bundle_refs(),
                "plugin_fingerprint": registry.plugin_fingerprint(),
                "registry_contract_fingerprint": registry.contract_fingerprint(),
                "addon_runtime_config": registry.addon_runtime_config(),
            },
            catalog=registry.data_types,
        ),
        event_queue,
        worker_services=worker_services,
    )
    events: list[dict[str, Any]] = []
    while not event_queue.empty():
        events.append(event_queue.get())
    failures = [
        event
        for event in events
        if str(event.get("type", "")) in {"run_failed", "protocol_error"}
        or (
            str(event.get("type", "")) == "node_settled"
            and str(event.get("status", "")) in {"failed", "blocked"}
        )
    ]
    if failures:
        raise RuntimeError(f"Engineering workflow failed: {failures!r}")
    if not any(str(event.get("type", "")) == "run_completed" for event in events):
        raise RuntimeError("Engineering workflow did not complete")

    session_id = default_viewer_session_id(
        _ENGINEERING_WORKSPACE_ID,
        _ENGINEERING_VIEWER_NODE_ID,
    )
    session_ref = worker_services.viewer_session_service.session_handle(
        _ENGINEERING_WORKSPACE_ID,
        session_id,
    )
    session_model = worker_services.resolve_handle(
        session_ref,
        expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
        expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
    )
    proxy_event = worker_services.viewer_session_service.update_session(
        UpdateViewerSessionCommand(
            request_id="canvas_engineering_proxy",
            workspace_id=_ENGINEERING_WORKSPACE_ID,
            node_id=_ENGINEERING_VIEWER_NODE_ID,
            session_id=session_id,
            backend_id=str(session_model.get("backend_id", "")),
            options={**dict(session_model.get("options", {})), "live_mode": "proxy"},
        )
    )
    proxy_payload = event_to_dict(proxy_event, catalog=registry.data_types)
    if proxy_payload.get("type") == "viewer_session_failed":
        raise RuntimeError(str(proxy_payload.get("error", "Viewer proxy setup failed")))
    return worker_services, dict(session_model), proxy_payload, events


def _apply_host_backend_environment(args: argparse.Namespace) -> None:
    qml_host = str(getattr(args, "qml_host", "") or "").strip()
    qsg_rhi_backend = str(getattr(args, "qsg_rhi_backend", "") or "").strip()
    if qml_host:
        os.environ[QML_HOST_ENV] = qml_host
    if qsg_rhi_backend:
        os.environ[QSG_RHI_BACKEND_ENV] = qsg_rhi_backend


# ---------------------------------------------------------------------------
# Subprocess entry-point: runs a single profiling scenario and writes JSON.
# ---------------------------------------------------------------------------


def _run_subprocess_scenario(args: argparse.Namespace) -> int:
    # Force the Qt platform BEFORE any Qt imports.
    os.environ["QT_QPA_PLATFORM"] = args.qt_platform
    _apply_host_backend_environment(args)
    if args.capture_qsg_info:
        os.environ["QSG_INFO"] = "1"
    if args.scale_factor:
        # On Windows, the OS display scaling cannot be overridden via
        # QT_SCALE_FACTOR alone — the per-screen devicePixelRatio still
        # reflects the OS setting. To force a true DPR=1 we need a
        # combination of env overrides AND a Floor rounding policy applied
        # before QApplication is constructed (handled below).
        os.environ["QT_SCALE_FACTOR"] = args.scale_factor
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
        os.environ["QT_SCREEN_SCALE_FACTORS"] = args.scale_factor
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    else:
        os.environ.pop("QT_SCALE_FACTOR", None)
        os.environ.pop("QT_AUTO_SCREEN_SCALE_FACTOR", None)
        os.environ.pop("QT_SCREEN_SCALE_FACTORS", None)
        os.environ.pop("QT_ENABLE_HIGHDPI_SCALING", None)

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    if args.scale_factor:
        # MUST be set before any QApplication is constructed.
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.Floor
        )

    # Import the existing harness pieces lazily so the env vars above take
    # effect first.
    from ea_node_editor.persistence.serializer import JsonProjectSerializer
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.ui.perf.performance_harness import (
        BenchmarkConfig,
        SyntheticGraphConfig,
        _build_scenario_project,
        _GraphCanvasBenchmarkHost,
        _augment_fixture_metadata,
        _measure_pan_zoom_step,
        _pan_zoom_target,
        _scenario_label_for_config,
    )
    from ea_node_editor.ui_qml.viewport_bridge import ViewportBridge
    from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
        EmbeddedViewerOverlayManager,
    )

    # The harness's per-sample loop calls wait_for_viewport_interaction_idle
    # with a 1000 ms default timeout. With GraphCanvas.qml's
    # interactionIdleDelayMs raised to 5000, that wait would always time out
    # (RuntimeError) AND it would force a layer-cache teardown between every
    # sample, defeating the purpose of measuring the post-fix steady state.
    # Patch the wait to be a no-op so interactionActive stays true across the
    # whole sample loop — modelling the continuous flick-and-drag behaviour
    # that the new debounce is meant to optimise.
    def _noop_wait_for_viewport_interaction_idle(
        self: "_GraphCanvasBenchmarkHost", *_args: object, **_kwargs: object
    ) -> None:
        return None

    if not args.engineering_step:
        _GraphCanvasBenchmarkHost.wait_for_viewport_interaction_idle = (  # type: ignore[method-assign]
            _noop_wait_for_viewport_interaction_idle
        )

    app = QApplication.instance() or QApplication(sys.argv)
    if args.engineering_step:
        return _run_engineering_canvas_scenario(args, app)

    # ---- Instrument the hot Python path -------------------------------
    instrumentation = _Instrumentation()
    instrumentation.install(ViewportBridge, "set_view_state", classmethod_like=False)
    instrumentation.install(
        ViewportBridge,
        "_refresh_visible_scene_rect_cache",
        classmethod_like=False,
    )
    instrumentation.install(ViewportBridge, "adjust_zoom", classmethod_like=False)
    instrumentation.install(
        ViewportBridge, "adjust_zoom_at_viewport_point", classmethod_like=False
    )
    instrumentation.install(ViewportBridge, "centerOn", classmethod_like=False)
    instrumentation.install(ViewportBridge, "pan_by", classmethod_like=False)

    # Build scenario through existing code paths.
    scenario = args.scenario
    cfg = BenchmarkConfig(
        synthetic_graph=SyntheticGraphConfig(
            node_count=args.nodes,
            edge_count=args.edges,
            seed=1337,
        ),
        load_iterations=1,
        interaction_samples=args.samples,
        interaction_warmup_samples=args.warmup,
        scenario=scenario,
        project_path=args.project_path,
        workspace_id=args.workspace_id,
        stress_fixture=args.stress_fixture,
        qml_host=args.qml_host,
        qsg_rhi_backend=args.qsg_rhi_backend,
    )
    scenario = _scenario_label_for_config(cfg)

    serializer = JsonProjectSerializer(build_default_registry())
    with _build_scenario_project(cfg) as scenario_project:
        project = scenario_project.project
        doc = serializer.to_document(project)
        workspace_id = scenario_project.workspace_id or project.active_workspace_id
        workspace = project.workspaces[workspace_id]
        expected_media = int(
            scenario_project.scenario_details["expected_media_surface_count"]
        )

        host: _GraphCanvasBenchmarkHost | None = None
        try:
            t_setup = time.perf_counter()
            host = _GraphCanvasBenchmarkHost(
                app=app,
                doc=doc,
                workspace_id=workspace_id,
            )
            if expected_media > 0:
                host.prepare_media_ready_view()
            host.wait_for_media_surfaces_ready(expected_count=expected_media, require_ready=False)
            setup_ms = (time.perf_counter() - t_setup) * 1000.0
            renderer_diagnostics = host.renderer_diagnostics()
            feature_parity = host.collect_feature_parity_snapshot(
                expected_media_surface_count=expected_media
            )
            fixture_metadata = _augment_fixture_metadata(
                scenario_project.scenario_details.get("fixture_metadata", {}),
                renderer_diagnostics=renderer_diagnostics,
                interaction_benchmark={
                    "grab_window_readback_included": True,
                    "frame_interval_metric": "frame_interval_ms_without_readback",
                },
            )

            # ---- Wire frame-time hook ---------------------------------
            frame_times: list[float] = []

            def _record_frame_time() -> None:
                frame_times.append(time.perf_counter())

            host.window.afterRendering.connect(
                _record_frame_time, Qt.ConnectionType.DirectConnection
            )

            # Resolve scene bounds for sampling targets.
            workspace = host.model.project.workspaces[workspace_id]
            xs = [float(node.x) for node in workspace.nodes.values()] or [0.0]
            ys = [float(node.y) for node in workspace.nodes.values()] or [0.0]
            margin_x = 800.0
            margin_y = 500.0
            left = min(xs) - margin_x
            right = max(xs) + margin_x
            top = min(ys) - margin_y
            bottom = max(ys) + margin_y

            current_center_x = float(host.view.center_x)
            current_center_y = float(host.view.center_y)
            current_zoom = float(host.view.zoom)

            import random
            rng = random.Random(args.seed)

            # Warmup loop (untimed)
            for warmup_index in range(args.warmup):
                pan_x, pan_y, zoom = _pan_zoom_target(
                    current_center_x=current_center_x,
                    current_center_y=current_center_y,
                    current_zoom=current_zoom,
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    random_gen=rng,
                    index=warmup_index,
                    zoom_min=args.zoom_min,
                    zoom_max=args.zoom_max,
                )
                _measure_pan_zoom_step(
                    host, pan_to_x=pan_x, pan_to_y=pan_y, zoom_to=zoom
                )
                current_center_x, current_center_y, current_zoom = pan_x, pan_y, zoom

            # Reset frame and Python instrumentation counters now that warmup
            # is done.
            frame_times.clear()
            instrumentation.reset()

            # cProfile the steady-state loop.
            pan_samples_ms: list[float] = []
            zoom_samples_ms: list[float] = []
            profiler = cProfile.Profile()
            profiler.enable()

            for index in range(args.samples):
                pan_x, pan_y, zoom = _pan_zoom_target(
                    current_center_x=current_center_x,
                    current_center_y=current_center_y,
                    current_zoom=current_zoom,
                    left=left,
                    right=right,
                    top=top,
                    bottom=bottom,
                    random_gen=rng,
                    index=args.warmup + index,
                    zoom_min=args.zoom_min,
                    zoom_max=args.zoom_max,
                )
                pan_step, zoom_step = _measure_pan_zoom_step(
                    host, pan_to_x=pan_x, pan_to_y=pan_y, zoom_to=zoom
                )
                pan_samples_ms.append(pan_step.elapsed_ms)
                zoom_samples_ms.append(zoom_step.elapsed_ms)
                current_center_x, current_center_y, current_zoom = pan_x, pan_y, zoom

            profiler.disable()

            # ---- Capture screen DPR ----------------------------------
            primary_screen = QGuiApplication.primaryScreen()
            screen_dpr = float(primary_screen.devicePixelRatio()) if primary_screen else 1.0
            window_dpr = float(host.window.effectiveDevicePixelRatio()) if host.window else 1.0

            # ---- Build cProfile top-N payload -------------------------
            stats = pstats.Stats(profiler)
            stats.sort_stats("cumulative")
            top_functions = _profile_top_functions(stats, top_n=25)

            # ---- Compute per-frame intervals --------------------------
            frame_intervals_ms: list[float] = []
            for previous, nxt in zip(frame_times, frame_times[1:]):
                frame_intervals_ms.append((nxt - previous) * 1000.0)

            payload = {
                "scenario": scenario,
                "qt_platform": args.qt_platform,
                "scale_factor_override": args.scale_factor or "",
                "screen_dpr": screen_dpr,
                "window_effective_dpr": window_dpr,
                "samples": args.samples,
                "warmup": args.warmup,
                "media_surface_count": expected_media,
                "node_count": len(workspace.nodes),
                "edge_count": len(workspace.edges),
                "workspace_id": workspace_id,
                "fixture_metadata": fixture_metadata,
                "setup_ms": setup_ms,
                "pan_ms": pan_samples_ms,
                "zoom_ms": zoom_samples_ms,
                "frame_intervals_ms": frame_intervals_ms,
                "frame_interval_ms_without_readback": frame_intervals_ms,
                "frame_count": len(frame_times),
                "renderer_diagnostics": renderer_diagnostics,
                "feature_parity": feature_parity,
                "grab_window_readback_included": True,
                "qsg_info_capture_enabled": bool(args.capture_qsg_info),
                "qsg_info_log_hint": (
                    "Qt scene graph diagnostics are captured in the scenario log "
                    "when --capture-qsg-info enables QSG_INFO=1."
                ),
                "instrumentation": instrumentation.snapshot(),
                "top_functions": top_functions,
            }

        finally:
            if host is not None:
                host.close()

    Path(args.output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def _run_engineering_canvas_scenario(args: argparse.Namespace, app: Any) -> int:
    from dataclasses import fields

    from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QTimer, Qt, pyqtSignal
    from PyQt6.QtGui import QGuiApplication, QWheelEvent
    from PyQt6.QtTest import QTest

    from ea_node_editor.execution.protocol_codec import event_to_dict
    from ea_node_editor.execution.viewer_messages import (
        CloseViewerSessionCommand,
        MaterializeViewerDataCommand,
        OpenViewerSessionCommand,
        QueryViewerSessionCommand,
        UpdateViewerSessionCommand,
    )
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.persistence.serializer import JsonProjectSerializer
    from ea_node_editor.ui.plot_preview_cache_provider import (
        VIEWER_PREVIEW_CACHE_PROVIDER_ID,
        ViewerPreviewCacheImageProvider,
    )
    from ea_node_editor.ui.perf.performance_harness import _GraphCanvasBenchmarkHost
    from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
        EmbeddedViewerOverlayManager,
        _OverlayWidgetPresentationService,
    )
    from ea_node_editor.ui_qml.engineering_viewer_widget_binder import (
        EngineeringViewerWidgetBinder,
    )
    from ea_node_editor.ui_qml.viewer_host_service import ViewerHostService
    from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge

    app.setQuitOnLastWindowClosed(False)
    step_path = Path(args.engineering_step).expanduser().resolve()
    if not step_path.is_file():
        raise FileNotFoundError(f"Engineering STEP file does not exist: {step_path}")
    if step_path.suffix.casefold() not in {".step", ".stp"}:
        raise ValueError("--engineering-step must name a .step or .stp file")

    registry = build_default_registry()
    project = _build_engineering_project(step_path, registry)
    setup_started = time.perf_counter()
    (
        worker_services,
        initial_session,
        proxy_event,
        worker_events,
    ) = _run_engineering_workflow(
        step_path=step_path,
        registry=registry,
        project=project,
    )
    doc = JsonProjectSerializer(registry).to_document(project)

    class _Shell(QObject):
        execution_event = pyqtSignal(dict)

    shell = _Shell()
    shell.project_path = str(step_path)
    host: _GraphCanvasBenchmarkHost | None = None
    viewer_bridge: ViewerSessionBridge | None = None
    viewer_host: ViewerHostService | None = None
    overlay_manager: EmbeddedViewerOverlayManager | None = None
    preview_provider: ViewerPreviewCacheImageProvider | None = None
    viewer_host_ref: list[ViewerHostService | None] = [None]
    lifecycle = _Instrumentation()
    render_key = ""
    geometry_counts = {
        "native_move_calls": 0,
        "native_resize_calls": 0,
        "native_set_geometry_calls": 0,
    }
    original_apply_geometry = _OverlayWidgetPresentationService.apply_widget_geometry

    def _counted_apply_geometry(widget, geometry):  # noqa: ANN001, ANN202
        current = widget.geometry()
        moved = current.topLeft() != geometry.topLeft()
        resized = current.size() != geometry.size()
        if moved and resized:
            geometry_counts["native_set_geometry_calls"] += 1
        elif moved:
            geometry_counts["native_move_calls"] += 1
        elif resized:
            geometry_counts["native_resize_calls"] += 1
        return original_apply_geometry(widget, geometry)

    _OverlayWidgetPresentationService.apply_widget_geometry = staticmethod(
        _counted_apply_geometry
    )

    command_types = {
        "open_viewer_session": OpenViewerSessionCommand,
        "update_viewer_session": UpdateViewerSessionCommand,
        "close_viewer_session": CloseViewerSessionCommand,
        "materialize_viewer_data": MaterializeViewerDataCommand,
        "query_viewer_session": QueryViewerSessionCommand,
    }

    class _ExecutionClient:
        def __init__(self) -> None:
            self._serial = 0
            self.command_counts = {name: 0 for name in command_types}

        def _send(self, command_name: str, values: dict[str, Any]) -> str:
            self._serial += 1
            self.command_counts[command_name] += 1
            request_id = f"canvas_engineering_{self._serial}"
            command_type = command_types[command_name]
            accepted = {item.name for item in fields(command_type)}
            command = command_type(
                **{
                    key: value
                    for key, value in {**values, "request_id": request_id}.items()
                    if key in accepted
                }
            )
            payload = event_to_dict(
                worker_services.viewer_session_service.handle_command(command),
                catalog=registry.data_types,
            )
            QTimer.singleShot(0, lambda event=payload: shell.execution_event.emit(event))
            return request_id

        def open_viewer_session(self, **values: Any) -> str:
            return self._send("open_viewer_session", values)

        def update_viewer_session(self, **values: Any) -> str:
            return self._send("update_viewer_session", values)

        def close_viewer_session(self, **values: Any) -> str:
            return self._send("close_viewer_session", values)

        def materialize_viewer_data(self, **values: Any) -> str:
            return self._send("materialize_viewer_data", values)

        def query_viewer_session(self, **values: Any) -> str:
            return self._send("query_viewer_session", values)

        def reset_counts(self) -> None:
            for name in self.command_counts:
                self.command_counts[name] = 0

    execution_client = _ExecutionClient()
    shell.execution_client = execution_client

    def _capture_camera(node_id: str, *, workspace_id: str = "") -> dict[str, Any]:
        service = viewer_host_ref[0]
        return (
            service.capture_overlay_camera_state(node_id, workspace_id=workspace_id)
            if service is not None
            else {}
        )

    def _setup_viewer_context(benchmark_host: Any, root_context: Any) -> None:
        nonlocal overlay_manager, preview_provider, viewer_bridge, viewer_host
        if benchmark_host.widget is None:
            raise RuntimeError(
                "The engineering canvas profiler requires the qquickwidget host."
            )
        shell.model = benchmark_host.model
        shell.scene = benchmark_host.scene
        shell.quick_widget = benchmark_host.widget
        preview_provider = ViewerPreviewCacheImageProvider()
        benchmark_host.engine.addImageProvider(
            VIEWER_PREVIEW_CACHE_PROVIDER_ID,
            preview_provider,
        )

        viewer_bridge = ViewerSessionBridge(
            shell,
            shell_window=shell,
            scene_bridge=benchmark_host.scene,
            data_types=registry.data_types,
            capture_overlay_camera_state=_capture_camera,
        )
        viewer_host = ViewerHostService(
            shell,
            shell_window=shell,
            viewer_session_bridge=viewer_bridge,
            preview_cache_provider=preview_provider,
        )
        viewer_host_ref[0] = viewer_host
        shell.viewer_session_bridge = viewer_bridge
        shell.viewer_host_service = viewer_host
        overlay_manager = EmbeddedViewerOverlayManager(
            benchmark_host.widget,
            quick_widget=benchmark_host.widget,
            overlay_parent_widget=benchmark_host.widget,
            event_filter_widget=benchmark_host.widget,
            shell_window=shell,
            scene_bridge=benchmark_host.scene,
            view_bridge=benchmark_host.view,
        )
        viewer_host.set_overlay_manager(overlay_manager)
        root_context.setContextProperty("viewerSessionBridge", viewer_bridge)
        root_context.setContextProperty("viewerHostService", viewer_host)

    try:
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "bind_widget",
            classmethod_like=False,
        )
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "release_widget",
            classmethod_like=False,
        )
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "_load_layer_datasets",
            classmethod_like=False,
        )
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "_populate_interactor",
            classmethod_like=False,
        )
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "_update_existing_actors",
            classmethod_like=False,
        )
        lifecycle.install(
            EngineeringViewerWidgetBinder,
            "_create_interactor",
            classmethod_like=True,
        )
        lifecycle.install(
            EmbeddedViewerOverlayManager,
            "sync",
            classmethod_like=False,
        )
        lifecycle.install(
            EmbeddedViewerOverlayManager,
            "sync_transform_only",
            classmethod_like=False,
        )
        lifecycle.install(
            ViewerHostService,
            "sync",
            classmethod_like=False,
        )
        lifecycle.install(
            ViewerHostService,
            "capture_overlay_camera_state",
            classmethod_like=False,
        )
        lifecycle.install(
            ViewerHostService,
            "capture_overlay_preview_image",
            classmethod_like=False,
        )
        lifecycle.install(
            ViewerSessionBridge,
            "set_embedded_interaction_active",
            classmethod_like=False,
        )

        host = _GraphCanvasBenchmarkHost(
            app=app,
            doc=doc,
            workspace_id=_ENGINEERING_WORKSPACE_ID,
            root_context_setup=_setup_viewer_context,
        )
        assert host.widget is not None
        assert viewer_bridge is not None
        assert viewer_host is not None
        assert overlay_manager is not None
        host.frame_scene_rect(QRectF(-760.0, -80.0, 1780.0, 760.0))

        def _drain(*, timeout_s: float = 0.0) -> None:
            deadline = time.perf_counter() + max(0.0, timeout_s)
            while True:
                app.processEvents()
                host.window.update()
                if time.perf_counter() >= deadline:
                    return
                time.sleep(0.005)

        def _render_without_readback(*, timeout_s: float = 1.0) -> None:
            frame_before = host.frame_render_timestamp_index()
            deadline = time.perf_counter() + timeout_s
            if host.widget is not None:
                host.widget.update()
            host.window.update()
            while host.frame_render_timestamp_index() <= frame_before:
                app.processEvents()
                if time.perf_counter() >= deadline:
                    raise RuntimeError("Timed out waiting for a no-readback rendered frame")

        host.scene.clear_selection()
        shell.execution_event.emit(proxy_event)
        deadline = time.perf_counter() + 3.0
        while True:
            _drain()
            projected = viewer_bridge.session_state(
                _ENGINEERING_VIEWER_NODE_ID,
                {"workspace_id": _ENGINEERING_WORKSPACE_ID},
            )
            widget = overlay_manager.overlay_widget(
                _ENGINEERING_VIEWER_NODE_ID,
                workspace_id=_ENGINEERING_WORKSPACE_ID,
            )
            if str(projected.get("live_mode", "")) == "proxy" and widget is None:
                break
            if time.perf_counter() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for initial proxy-only Model Viewer state"
                )
            time.sleep(0.01)
        host.render_frame()
        setup_ms = (time.perf_counter() - setup_started) * 1000.0
        host.reset_frame_interval_capture()

        def _node_card(node_id: str) -> Any:
            for card in host.node_cards() or host._force_visible_node_cards_current():
                data = card.property("nodeData") or {}
                if str(data.get("node_id", "")) == node_id:
                    return card
            raise RuntimeError(f"Graph node card is not instantiated: {node_id}")

        def _method_calls(snapshot: dict[str, Any], key: str) -> int:
            return int(snapshot.get(key, {}).get("call_count", 0))

        def _lifecycle_snapshot() -> dict[str, int]:
            stats = lifecycle.snapshot()
            return {
                "binder_bind": _method_calls(
                    stats, "EngineeringViewerWidgetBinder.bind_widget"
                ),
                "binder_release": _method_calls(
                    stats, "EngineeringViewerWidgetBinder.release_widget"
                ),
                "binder_render": (
                    _method_calls(stats, render_key)
                    + _method_calls(
                        stats, "EngineeringViewerWidgetBinder._populate_interactor"
                    )
                    + _method_calls(
                        stats, "EngineeringViewerWidgetBinder._update_existing_actors"
                    )
                ),
                "dataset_load": _method_calls(
                    stats, "EngineeringViewerWidgetBinder._load_layer_datasets"
                ),
                "widget_create": _method_calls(
                    stats, "EngineeringViewerWidgetBinder._create_interactor"
                ),
                "overlay_full_sync": _method_calls(
                    stats, "EmbeddedViewerOverlayManager.sync"
                ),
                "overlay_transform_sync": _method_calls(
                    stats, "EmbeddedViewerOverlayManager.sync_transform_only"
                ),
                "viewer_host_sync": _method_calls(
                    stats, "ViewerHostService.sync"
                ),
                "embedded_interaction_sync": _method_calls(
                    stats, "ViewerSessionBridge.set_embedded_interaction_active"
                ),
                "camera_capture": _method_calls(
                    stats, "ViewerHostService.capture_overlay_camera_state"
                ),
                "preview_capture": _method_calls(
                    stats, "ViewerHostService.capture_overlay_preview_image"
                ),
                "native_move_calls": int(geometry_counts["native_move_calls"]),
                "native_resize_calls": int(
                    geometry_counts["native_resize_calls"]
                ),
                "native_set_geometry_calls": int(
                    geometry_counts["native_set_geometry_calls"]
                ),
                "overlay_skipped_delta": int(
                    overlay_manager.overlay_metrics_snapshot().get(
                        "skipped_delta_sync_count", 0
                    )
                ),
                "execution_open": int(
                    execution_client.command_counts["open_viewer_session"]
                ),
                "execution_update": int(
                    execution_client.command_counts["update_viewer_session"]
                ),
                "execution_close": int(
                    execution_client.command_counts["close_viewer_session"]
                ),
                "execution_materialize": int(
                    execution_client.command_counts["materialize_viewer_data"]
                ),
                "execution_query": int(
                    execution_client.command_counts["query_viewer_session"]
                ),
            }

        def _viewer_state() -> dict[str, Any]:
            workspace = host.model.project.workspaces[_ENGINEERING_WORKSPACE_ID]
            state = (
                viewer_bridge.session_state(
                    _ENGINEERING_VIEWER_NODE_ID,
                    {"workspace_id": _ENGINEERING_WORKSPACE_ID},
                )
                if viewer_bridge is not None
                and _ENGINEERING_VIEWER_NODE_ID in workspace.nodes
                else {}
            )
            if not state and _ENGINEERING_VIEWER_NODE_ID in workspace.nodes:
                state = dict(initial_session)
            widget = (
                overlay_manager.overlay_widget(
                    _ENGINEERING_VIEWER_NODE_ID,
                    workspace_id=_ENGINEERING_WORKSPACE_ID,
                )
                if overlay_manager is not None
                else None
            )
            _bound, resident_widget = (
                viewer_host._bound_overlay_widget_for_node(_ENGINEERING_VIEWER_NODE_ID)
                if viewer_host is not None
                else (None, None)
            )
            identity_widget = widget or resident_widget
            container = (
                overlay_manager.overlay_container(
                    _ENGINEERING_VIEWER_NODE_ID,
                    workspace_id=_ENGINEERING_WORKSPACE_ID,
                )
                if overlay_manager is not None
                else None
            )
            cached_source = (
                viewer_host.cached_preview_source(_ENGINEERING_VIEWER_NODE_ID)
                if viewer_host is not None
                else ""
            )
            data_refs = dict(state.get("data_refs", {}))
            surface = (
                _node_card(_ENGINEERING_VIEWER_NODE_ID).findChild(
                    QObject, "graphNodeViewerSurface"
                )
                if _ENGINEERING_VIEWER_NODE_ID in workspace.nodes
                else None
            )
            return {
                "phase": str(state.get("phase", "")),
                "session_id": str(state.get("session_id", "")),
                "backend_id": str(state.get("backend_id", "")),
                "live_mode": str(
                    state.get("live_mode")
                    or dict(state.get("options", {})).get("live_mode", "")
                ),
                "cache_state": str(state.get("cache_state", "")),
                "transport_revision": int(state.get("transport_revision", 0) or 0),
                "cached_preview_available": bool(
                    cached_source or data_refs.get("png") or data_refs.get("preview")
                ),
                "cached_preview_source": str(cached_source or ""),
                "preview_cache_revision": int(viewer_host.preview_cache_revision),
                "native_overlay_visible": bool(
                    widget is not None
                    and widget.isVisible()
                    and container is not None
                    and container.isVisible()
                ),
                "native_overlay_geometry_ready": bool(
                    overlay_manager is not None
                    and overlay_manager.overlay_geometry_ready(
                        _ENGINEERING_VIEWER_NODE_ID,
                        workspace_id=_ENGINEERING_WORKSPACE_ID,
                    )
                ),
                "native_updates_enabled": bool(
                    identity_widget is not None and identity_widget.updatesEnabled()
                ),
                "retained_inline_node_id": str(
                    viewer_host.retained_inline_viewer_node_id or ""
                ),
                "presentation_hold_count": len(
                    viewer_bridge._viewer_presentation_holds
                ),
                "explicit_inline_active": bool(
                    surface is not None and surface.property("inlineLiveRequested")
                ),
                "active_overlay_count": int(viewer_host.active_overlay_count),
                "widget_identity": (
                    hex(id(identity_widget)) if identity_widget is not None else ""
                ),
            }

        def _install_render_counter() -> None:
            nonlocal render_key
            if render_key:
                return
            _bound, widget = viewer_host._bound_overlay_widget_for_node(
                _ENGINEERING_VIEWER_NODE_ID
            )
            if widget is None or not callable(getattr(widget, "render", None)):
                return
            lifecycle.install(type(widget), "render", classmethod_like=False)
            render_key = f"{type(widget).__name__}.render"

        def _wait_for_state(predicate, message: str, *, timeout_s: float = 4.0) -> None:  # noqa: ANN001
            deadline = time.perf_counter() + timeout_s
            while True:
                _drain()
                viewer_host.sync()
                overlay_manager.sync()
                if predicate(_viewer_state()):
                    return
                if time.perf_counter() >= deadline:
                    raise RuntimeError(f"{message}: {_viewer_state()!r}")
                time.sleep(0.01)

        def _wait_for_live() -> None:
            _wait_for_state(
                lambda current: bool(current["widget_identity"])
                and current["live_mode"] == "full"
                and current["explicit_inline_active"]
                and current["native_overlay_visible"]
                and current["native_overlay_geometry_ready"]
                and current["native_updates_enabled"],
                "Timed out waiting for explicitly activated inline viewer",
            )
            _install_render_counter()

        def _wait_for_retained_proxy() -> None:
            _wait_for_state(
                lambda current: bool(current["widget_identity"])
                and current["live_mode"] == "proxy"
                and not current["explicit_inline_active"]
                and current["retained_inline_node_id"]
                == _ENGINEERING_VIEWER_NODE_ID
                and not current["native_overlay_visible"]
                and not current["native_overlay_geometry_ready"],
                "Timed out waiting for retained proxy viewer",
            )

        def _viewer_viewport_point() -> QPoint:
            card = _node_card(_ENGINEERING_VIEWER_NODE_ID)
            viewport = card.findChild(QObject, "graphNodeViewerViewport")
            if viewport is None:
                raise RuntimeError("Model Viewer proxy viewport is unavailable")
            center = viewport.mapToItem(
                host.canvas,
                QPointF(float(viewport.width()) * 0.5, float(viewport.height()) * 0.5),
            )
            return QPoint(round(center.x()), round(center.y()))

        def _prepare_retained_reactivation_point() -> QPoint:
            workspace = host.model.project.workspaces[_ENGINEERING_WORKSPACE_ID]
            node = workspace.nodes[_ENGINEERING_VIEWER_NODE_ID]
            card = _node_card(_ENGINEERING_VIEWER_NODE_ID)
            node_rect = QRectF(
                float(node.x),
                float(node.y),
                max(1.0, float(node.custom_width or card.width())),
                max(1.0, float(node.custom_height or card.height())),
            ).adjusted(-40.0, -40.0, 40.0, 40.0)
            if not host.frame_scene_rect(node_rect):
                raise RuntimeError("Could not frame retained Model Viewer for reactivation")
            _drain(timeout_s=0.1)
            _render_without_readback()
            point = _viewer_viewport_point()
            if not (
                0 <= point.x() < host.window.width()
                and 0 <= point.y() < host.window.height()
            ):
                raise RuntimeError(
                    f"Retained Model Viewer viewport is outside the visible window: {point!r}"
                )
            card = _node_card(_ENGINEERING_VIEWER_NODE_ID)
            viewport = card.findChild(QObject, "graphNodeViewerViewport")
            if viewport is None:
                raise RuntimeError("Retained Model Viewer viewport disappeared after framing")
            local = viewport.mapFromItem(host.canvas, QPointF(point))
            if not viewport.contains(local):
                raise RuntimeError(
                    "Reactivation point does not resolve inside the retained viewer viewport"
                )
            return point

        def _empty_canvas_point() -> QPoint:
            candidates = (
                QPoint(24, round(host.widget.height()) - 24),
                QPoint(round(host.widget.width()) - 24, round(host.widget.height()) - 24),
                QPoint(24, 24),
                QPoint(round(host.widget.width()) - 24, 24),
            )
            card_rects: list[QRectF] = []
            for card in host.node_cards():
                origin = card.mapToItem(host.canvas, QPointF(0.0, 0.0))
                card_rects.append(
                    QRectF(origin.x(), origin.y(), card.width(), card.height())
                )
            for candidate in candidates:
                if not any(rect.contains(QPointF(candidate)) for rect in card_rects):
                    return candidate
            raise RuntimeError("No empty canvas point is available for input sampling")

        def _send_wheel(point: QPoint, delta: int) -> None:
            global_point = host.widget.mapToGlobal(point)
            event = QWheelEvent(
                QPointF(point),
                QPointF(global_point),
                QPoint(),
                QPoint(0, int(delta)),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            app.sendEvent(host.window, event)
            if not event.isAccepted():
                raise RuntimeError("Graph canvas did not accept wheel input")

        operations: list[dict[str, Any]] = []

        def _record_operation(
            name: str,
            action,
        ) -> None:  # noqa: ANN001
            sys.stdout.write(f"[profile] Engineering operation {name} ...\n")
            sys.stdout.flush()
            before = _viewer_state()
            before_counts = _lifecycle_snapshot()
            frame_start = host.frame_render_timestamp_index()
            status = "measured"
            reason = ""
            details: dict[str, Any] = {}
            try:
                details = dict(action() or {})
                _drain(timeout_s=0.05)
            except SystemExit as exc:
                status = "unsupported"
                reason = f"Qt requested process exit during the operation: {exc.code!r}"
            except Exception as exc:  # noqa: BLE001
                status = "unsupported"
                reason = str(exc)
            after = _viewer_state()
            after_counts = _lifecycle_snapshot()
            frame_end = host.frame_render_timestamp_index()
            measured_frame_range = details.pop("frame_timestamp_range", None)
            if (
                isinstance(measured_frame_range, (list, tuple))
                and len(measured_frame_range) == 2
            ):
                frame_start = int(measured_frame_range[0])
                frame_end = int(measured_frame_range[1])
            timestamps = list(host._frame_render_timestamps[frame_start:frame_end])
            frame_intervals = [
                (next_value - previous) * 1000.0
                for previous, next_value in zip(timestamps, timestamps[1:])
            ]
            timings = [float(value) for value in details.pop("timings_ms", [])]
            boundaries = details.pop("counter_boundaries", {})

            def boundary_delta(start_key: str, end_key: str) -> dict[str, int]:
                start = boundaries.get(start_key)
                end = boundaries.get(end_key)
                if not isinstance(start, dict) or not isinstance(end, dict):
                    return {key: 0 for key in before_counts}
                keys = set(start) | set(end)
                return {
                    key: int(end.get(key, 0)) - int(start.get(key, 0))
                    for key in keys
                }

            operations.append(
                {
                    "operation": name,
                    "status": status,
                    "unavailable_reason": reason,
                    "timings_ms": timings,
                    "timing_p50_ms": _percentile(timings, 50.0),
                    "timing_p95_ms": _percentile(timings, 95.0),
                    "frame_intervals_ms": frame_intervals,
                    "frame_interval_p50_ms": _percentile(frame_intervals, 50.0),
                    "frame_interval_p95_ms": _percentile(frame_intervals, 95.0),
                    "viewer_before": before,
                    "viewer_during": details.pop("viewer_during", {}),
                    "viewer_after": after,
                    "lifecycle_deltas": {
                        key: int(after_counts[key] - before_counts[key])
                        for key in before_counts
                    },
                    "transition_lifecycle_deltas": boundary_delta(
                        "transition_before", "transition_after"
                    ),
                    "continuous_lifecycle_deltas": boundary_delta(
                        "continuous_before", "continuous_after"
                    ),
                    "restoration_lifecycle_deltas": boundary_delta(
                        "continuous_after", "restoration_after"
                    ),
                    **details,
                }
            )
            sys.stdout.write(f"[profile]   {name}: {status}\n")
            sys.stdout.flush()

        def _operation_record(name: str) -> dict[str, Any]:
            return next(
                item for item in reversed(operations) if item["operation"] == name
            )

        def _set_operation_status(
            name: str,
            status: str,
            reason: str,
            *,
            derived_from: str = "",
        ) -> None:
            item = _operation_record(name)
            item["status"] = status
            item["unavailable_reason"] = reason
            if derived_from:
                item["derived_from"] = derived_from

        def _record_blocked(name: str, prerequisite: str) -> None:
            _record_operation(name, lambda: {})
            _set_operation_status(
                name,
                "blocked",
                f"Blocked by prerequisite phase {prerequisite}",
                derived_from=prerequisite,
            )

        def _record_derived(name: str, action, prerequisite: str) -> None:  # noqa: ANN001
            _record_operation(name, action)
            if _operation_record(name)["status"] == "measured":
                _set_operation_status(
                    name,
                    "derived",
                    f"Metrics derived after prerequisite failure {prerequisite}",
                    derived_from=prerequisite,
                )

        startup_viewer_state = _viewer_state()
        startup_lifecycle = _lifecycle_snapshot()
        operations.append(
            {
                "operation": "startup_proxy",
                "status": "measured",
                "unavailable_reason": "",
                "timings_ms": [setup_ms],
                "timing_p50_ms": setup_ms,
                "timing_p95_ms": setup_ms,
                "frame_intervals_ms": [],
                "frame_interval_p50_ms": 0.0,
                "frame_interval_p95_ms": 0.0,
                "viewer_before": startup_viewer_state,
                "viewer_during": {},
                "viewer_after": startup_viewer_state,
                "lifecycle_deltas": startup_lifecycle,
                "transition_lifecycle_deltas": startup_lifecycle,
                "continuous_lifecycle_deltas": {
                    key: 0 for key in startup_lifecycle
                },
                "restoration_lifecycle_deltas": {
                    key: 0 for key in startup_lifecycle
                },
            }
        )
        lifecycle.reset()
        geometry_counts.update(
            native_move_calls=0,
            native_resize_calls=0,
            native_set_geometry_calls=0,
        )
        execution_client.reset_counts()

        def _viewport_steps(*, mode: str) -> dict[str, Any]:
            timings: list[float] = []
            warmup_count = max(0, int(args.warmup))
            measured_count = max(1, int(args.samples))
            total_count = warmup_count + measured_count
            scheduler = host.canvas.findChild(QObject, "graphCanvasFrameScheduler")
            if scheduler is None:
                raise RuntimeError("Graph canvas frame scheduler is unavailable")
            transition_before = _lifecycle_snapshot()
            if mode == "wheel":
                _send_wheel(_empty_canvas_point(), 120)
                app.processEvents()
            else:
                host.begin_viewport_interaction()
                _drain(timeout_s=0.05)
            _render_without_readback()
            viewer_during = _viewer_state()
            transition_after = _lifecycle_snapshot()
            continuous_before = _lifecycle_snapshot()
            measured_frame_start = host.frame_render_timestamp_index()
            for index in range(total_count):
                if index == warmup_count:
                    measured_frame_start = host.frame_render_timestamp_index()
                started = time.perf_counter()
                if mode == "wheel":
                    _send_wheel(
                        _empty_canvas_point(),
                        120 if index % 2 == 0 else -120,
                    )
                else:
                    dx, dy = ((18.0, 10.0), (-14.0, 8.0), (12.0, -9.0))[index % 3]
                    scheduler.queuePanBy(host.view, dx, dy)
                _render_without_readback()
                if index >= warmup_count:
                    timings.append((time.perf_counter() - started) * 1000.0)
            measured_frame_end = host.frame_render_timestamp_index()
            continuous_after = _lifecycle_snapshot()
            if mode != "wheel":
                host.finish_viewport_interaction()
            host.wait_for_viewport_interaction_idle(timeout_ms=3500)
            _drain(timeout_s=0.05)
            restoration_after = _lifecycle_snapshot()
            return {
                "timings_ms": timings,
                "viewer_during": viewer_during,
                "frame_timestamp_range": [
                    measured_frame_start,
                    measured_frame_end,
                ],
                "warmup_samples_applied": warmup_count,
                "counter_boundaries": {
                    "transition_before": transition_before,
                    "transition_after": transition_after,
                    "continuous_before": continuous_before,
                    "continuous_after": continuous_after,
                    "restoration_after": restoration_after,
                },
            }

        def _box_zoom_steps() -> dict[str, Any]:
            warmup_count = max(0, int(args.warmup))
            measured_count = max(1, int(args.samples))
            total_count = warmup_count + measured_count
            start = _empty_canvas_point()
            direction = -1 if start.x() > host.widget.width() * 0.5 else 1
            end = QPoint(
                max(8, min(host.widget.width() - 8, start.x() + direction * 180)),
                max(8, min(host.widget.height() - 8, start.y() - 120)),
            )
            center_x = float(host.view.center_x)
            center_y = float(host.view.center_y)
            zoom = float(host.view.zoom)
            transition_before = _lifecycle_snapshot()
            QTest.mousePress(
                host.window,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                start,
            )
            QTest.mouseMove(host.window, end)
            _drain(timeout_s=0.05)
            _render_without_readback()
            if not bool(host.canvas.property("nativeOverlaySuppressionActive")):
                raise RuntimeError("Box zoom did not activate native overlay suppression")
            viewer_during = _viewer_state()
            transition_after = _lifecycle_snapshot()
            continuous_before = _lifecycle_snapshot()
            timings: list[float] = []
            measured_frame_start = host.frame_render_timestamp_index()
            current = end
            for index in range(total_count):
                if index == warmup_count:
                    measured_frame_start = host.frame_render_timestamp_index()
                current = QPoint(
                    end.x() + direction * (index % 3),
                    end.y() - (index % 2),
                )
                started = time.perf_counter()
                QTest.mouseMove(host.window, current)
                _render_without_readback()
                if index >= warmup_count:
                    timings.append((time.perf_counter() - started) * 1000.0)
            measured_frame_end = host.frame_render_timestamp_index()
            continuous_after = _lifecycle_snapshot()
            QTest.mouseRelease(
                host.window,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                current,
            )
            host.view.set_zoom(zoom)
            host.view.centerOn(center_x, center_y)
            host.wait_for_viewport_interaction_idle(timeout_ms=3500)
            _drain(timeout_s=0.05)
            restoration_after = _lifecycle_snapshot()
            return {
                "timings_ms": timings,
                "viewer_during": viewer_during,
                "frame_timestamp_range": [measured_frame_start, measured_frame_end],
                "warmup_samples_applied": warmup_count,
                "counter_boundaries": {
                    "transition_before": transition_before,
                    "transition_after": transition_after,
                    "continuous_before": continuous_before,
                    "continuous_after": continuous_after,
                    "restoration_after": restoration_after,
                },
            }

        def _drag(node_id: str) -> dict[str, Any]:
            card = _node_card(node_id)
            node_data = card.property("nodeData") or {}
            x = float(node_data.get("x", 0.0))
            y = float(node_data.get("y", 0.0))
            timings: list[float] = []
            warmup_count = max(0, int(args.warmup))
            measured_count = max(1, int(args.samples))
            total_count = warmup_count + measured_count
            final_dx = final_dy = 0.0
            transition_before = _lifecycle_snapshot()
            transition_started = time.perf_counter()
            card.dragOffsetChanged.emit(node_id, 0.1, 0.1)
            _drain(timeout_s=0.05)
            _render_without_readback()
            transition_ms = (time.perf_counter() - transition_started) * 1000.0
            viewer_during = _viewer_state()
            transition_after = _lifecycle_snapshot()
            _drain(timeout_s=0.05)
            _render_without_readback()
            continuous_before = _lifecycle_snapshot()
            measured_frame_start = host.frame_render_timestamp_index()
            for index in range(total_count):
                if index == warmup_count:
                    measured_frame_start = host.frame_render_timestamp_index()
                final_dx = 12.0 * float(index + 1) / float(total_count)
                final_dy = 8.0 * float(index + 1) / float(total_count)
                started = time.perf_counter()
                card.dragOffsetChanged.emit(node_id, final_dx, final_dy)
                _render_without_readback()
                if index >= warmup_count:
                    timings.append((time.perf_counter() - started) * 1000.0)
            measured_frame_end = host.frame_render_timestamp_index()
            continuous_after = _lifecycle_snapshot()
            card.dragFinished.emit(node_id, x + final_dx, y + final_dy, True)
            _drain(timeout_s=0.05)
            _render_without_readback()
            restoration_after = _lifecycle_snapshot()
            return {
                "timings_ms": timings,
                "transition_ms": transition_ms,
                "viewer_during": viewer_during,
                "warmup_samples_applied": warmup_count,
                "frame_timestamp_range": [
                    measured_frame_start,
                    measured_frame_end,
                ],
                "committed": True,
                "counter_boundaries": {
                    "transition_before": transition_before,
                    "transition_after": transition_after,
                    "continuous_before": continuous_before,
                    "continuous_after": continuous_after,
                    "restoration_after": restoration_after,
                },
            }

        def _resize(node_id: str) -> dict[str, Any]:
            card = _node_card(node_id)
            data = card.property("nodeData") or {}
            x = float(data.get("x", 0.0))
            y = float(data.get("y", 0.0))
            width = float(data.get("width", card.width()))
            height = float(data.get("height", card.height()))
            timings: list[float] = []
            warmup_count = max(0, int(args.warmup))
            measured_count = max(1, int(args.samples))
            total_count = warmup_count + measured_count
            final_width = width
            final_height = height
            transition_before = _lifecycle_snapshot()
            transition_started = time.perf_counter()
            card.resizePreviewChanged.emit(
                node_id,
                x,
                y,
                width,
                height,
                True,
            )
            _drain(timeout_s=0.05)
            _render_without_readback()
            transition_ms = (time.perf_counter() - transition_started) * 1000.0
            viewer_during = _viewer_state()
            transition_after = _lifecycle_snapshot()
            _drain(timeout_s=0.05)
            _render_without_readback()
            continuous_before = _lifecycle_snapshot()
            measured_frame_start = host.frame_render_timestamp_index()
            for index in range(total_count):
                if index == warmup_count:
                    measured_frame_start = host.frame_render_timestamp_index()
                progress = float(index + 1) / float(total_count)
                final_width = width + 24.0 * progress
                final_height = height + 18.0 * progress
                started = time.perf_counter()
                card.resizePreviewChanged.emit(
                    node_id,
                    x,
                    y,
                    final_width,
                    final_height,
                    True,
                )
                _render_without_readback()
                if index >= warmup_count:
                    timings.append((time.perf_counter() - started) * 1000.0)
            measured_frame_end = host.frame_render_timestamp_index()
            continuous_after = _lifecycle_snapshot()
            card.resizeFinished.emit(node_id, x, y, final_width, final_height)
            _drain(timeout_s=0.05)
            _render_without_readback()
            restoration_after = _lifecycle_snapshot()
            return {
                "timings_ms": timings,
                "transition_ms": transition_ms,
                "viewer_during": viewer_during,
                "warmup_samples_applied": warmup_count,
                "frame_timestamp_range": [
                    measured_frame_start,
                    measured_frame_end,
                ],
                "committed": True,
                "counter_boundaries": {
                    "transition_before": transition_before,
                    "transition_after": transition_after,
                    "continuous_before": continuous_before,
                    "continuous_after": continuous_after,
                    "restoration_after": restoration_after,
                },
            }

        def _wire_drag() -> dict[str, Any]:
            card = _node_card(_ENGINEERING_CAD_NODE_ID)
            transition_before = _lifecycle_snapshot()
            card.portDragStarted.emit(
                _ENGINEERING_CAD_NODE_ID,
                "scene",
                "output",
                0.0,
                0.0,
                420.0,
                220.0,
                0,
            )
            card.portDragMoved.emit(
                _ENGINEERING_CAD_NODE_ID,
                "scene",
                "output",
                0.0,
                0.0,
                450.0,
                250.0,
                True,
                0,
            )
            _drain(timeout_s=0.05)
            _render_without_readback()
            viewer_during = _viewer_state()
            _drain(timeout_s=0.05)
            _render_without_readback()
            transition_after = _lifecycle_snapshot()
            timings: list[float] = []
            warmup_count = max(0, int(args.warmup))
            measured_count = max(1, int(args.samples))
            total_count = warmup_count + measured_count
            continuous_before = _lifecycle_snapshot()
            measured_frame_start = host.frame_render_timestamp_index()
            for index in range(total_count):
                if index == warmup_count:
                    measured_frame_start = host.frame_render_timestamp_index()
                started = time.perf_counter()
                card.portDragMoved.emit(
                    _ENGINEERING_CAD_NODE_ID,
                    "scene",
                    "output",
                    0.0,
                    0.0,
                    450.0 + index * 3.0,
                    250.0 + index * 2.0,
                    True,
                    0,
                )
                _render_without_readback()
                if index >= warmup_count:
                    timings.append((time.perf_counter() - started) * 1000.0)
            measured_frame_end = host.frame_render_timestamp_index()
            continuous_after = _lifecycle_snapshot()
            card.portDragCanceled.emit(
                _ENGINEERING_CAD_NODE_ID,
                "scene",
                "output",
            )
            _drain(timeout_s=0.05)
            _render_without_readback()
            restoration_after = _lifecycle_snapshot()
            return {
                "timings_ms": timings,
                "viewer_during": viewer_during,
                "warmup_samples_applied": warmup_count,
                "frame_timestamp_range": [
                    measured_frame_start,
                    measured_frame_end,
                ],
                "committed": False,
                "counter_boundaries": {
                    "transition_before": transition_before,
                    "transition_after": transition_after,
                    "continuous_before": continuous_before,
                    "continuous_after": continuous_after,
                    "restoration_after": restoration_after,
                },
            }

        created_node_id = [""]

        def _single(action) -> dict[str, Any]:  # noqa: ANN001
            started = time.perf_counter()
            result = action()
            app.processEvents()
            _render_without_readback()
            return {
                "timings_ms": [(time.perf_counter() - started) * 1000.0],
                **(dict(result) if isinstance(result, dict) else {}),
            }

        def _select_without_activation() -> None:
            host.scene.select_node(_ENGINEERING_VIEWER_NODE_ID, False)
            _drain(timeout_s=0.05)
            if _viewer_state()["live_mode"] != "proxy":
                raise RuntimeError("Selection unexpectedly activated the Model Viewer")

        def _hover_without_activation() -> None:
            QTest.mouseMove(host.window, _viewer_viewport_point())
            _drain(timeout_s=0.05)
            if _viewer_state()["live_mode"] != "proxy":
                raise RuntimeError("Hover unexpectedly activated the Model Viewer")

        def _single_click_without_activation() -> None:
            QTest.mouseClick(
                host.window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                _viewer_viewport_point(),
            )
            _drain(timeout_s=0.05)
            if _viewer_state()["live_mode"] != "proxy":
                raise RuntimeError("Single click unexpectedly activated the Model Viewer")

        def _double_click_activate(*, retained: bool = False) -> None:
            if _ENGINEERING_VIEWER_NODE_ID not in dict(
                host.scene.selected_node_lookup
            ):
                host.scene.select_node(_ENGINEERING_VIEWER_NODE_ID, False)
                _drain(timeout_s=0.05)
            point = (
                _prepare_retained_reactivation_point()
                if retained
                else _viewer_viewport_point()
            )
            QTest.mouseDClick(
                host.window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
            )
            _wait_for_live()

        def _canvas_click_demote() -> None:
            QTest.mouseClick(
                host.window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                _empty_canvas_point(),
            )
            _wait_for_retained_proxy()

        wire_edge_id = [""]

        def _add_unrelated() -> dict[str, Any]:
            created_node_id[0] = host.scene.add_node_from_type(
                "data.boolean_toggle", 940.0, 440.0
            )
            _wait_for_retained_proxy()
            return {"created_node_id": created_node_id[0]}

        def _create_wire() -> dict[str, Any]:
            wire_edge_id[0] = host.scene.add_edge(
                _ENGINEERING_WIRE_SOURCE_NODE_ID,
                "value",
                _ENGINEERING_WIRE_TARGET_A_NODE_ID,
                "payload",
            )
            return {"edge_id": wire_edge_id[0]}

        def _reroute_wire() -> dict[str, Any]:
            if not host.scene.request_rewire_edges(
                [wire_edge_id[0]],
                "target",
                _ENGINEERING_WIRE_TARGET_B_NODE_ID,
                "payload",
            ):
                raise RuntimeError("Committed wire reroute was rejected")
            return {"edge_id": wire_edge_id[0]}

        _record_operation("proxy_pan_control", lambda: _viewport_steps(mode="pan"))
        _record_operation("proxy_zoom_control", lambda: _viewport_steps(mode="wheel"))
        _record_operation(
            "selection_without_activation", lambda: _single(_select_without_activation)
        )
        _record_operation(
            "hover_without_activation", lambda: _single(_hover_without_activation)
        )
        _record_operation(
            "single_click_without_activation",
            lambda: _single(_single_click_without_activation),
        )
        _record_operation(
            "proxy_double_click_activation", lambda: _single(_double_click_activate)
        )
        activation_ok = (
            _operation_record("proxy_double_click_activation")["status"] == "measured"
            and _viewer_state()["live_mode"] == "full"
            and _viewer_state()["explicit_inline_active"]
        )
        if activation_ok:
            _record_operation("live_wheel_zoom", lambda: _viewport_steps(mode="wheel"))
            if _viewer_state()["live_mode"] != "full":
                _set_operation_status(
                    "live_wheel_zoom",
                    "failed",
                    "Viewer did not remain live after wheel zoom",
                )
            if _viewer_state()["live_mode"] == "full":
                _record_operation("live_box_zoom", _box_zoom_steps)
            else:
                _record_blocked("live_box_zoom", "live_wheel_zoom")
            box_ok = (
                _operation_record("live_box_zoom")["status"] == "measured"
                and _viewer_state()["live_mode"] == "full"
                and _viewer_state()["explicit_inline_active"]
            )
            if not box_ok and _operation_record("live_box_zoom")["status"] == "measured":
                _set_operation_status(
                    "live_box_zoom",
                    "failed",
                    "Viewer did not restore explicit live mode after box zoom",
                )
            live_root = "" if box_ok else "live_box_zoom"
        else:
            _record_blocked("live_wheel_zoom", "proxy_double_click_activation")
            _record_blocked("live_box_zoom", "proxy_double_click_activation")
            live_root = "proxy_double_click_activation"

        if not live_root:
            _record_operation(
                "active_viewer_drag", lambda: _drag(_ENGINEERING_VIEWER_NODE_ID)
            )
            _record_operation(
                "active_viewer_resize", lambda: _resize(_ENGINEERING_VIEWER_NODE_ID)
            )
            _record_operation(
                "canvas_click_demotion", lambda: _single(_canvas_click_demote)
            )
        else:
            _record_blocked("active_viewer_drag", live_root)
            _record_blocked("active_viewer_resize", live_root)
            _record_blocked("canvas_click_demotion", live_root)

        retained_ready = (
            _viewer_state()["retained_inline_node_id"]
            == _ENGINEERING_VIEWER_NODE_ID
            and _viewer_state()["live_mode"] == "proxy"
        )
        if retained_ready:
            if live_root:
                _record_derived(
                    "retained_proxy_pan",
                    lambda: _viewport_steps(mode="pan"),
                    live_root,
                )
                _record_derived(
                    "retained_proxy_zoom",
                    lambda: _viewport_steps(mode="wheel"),
                    live_root,
                )
            else:
                _record_operation(
                    "retained_proxy_pan", lambda: _viewport_steps(mode="pan")
                )
                _record_operation(
                    "retained_proxy_zoom", lambda: _viewport_steps(mode="wheel")
                )
            _record_operation(
                "double_click_reactivation",
                lambda: _single(lambda: _double_click_activate(retained=True)),
            )
            reactivation_ok = (
                _operation_record("double_click_reactivation")["status"] == "measured"
                and _viewer_state()["live_mode"] == "full"
                and _viewer_state()["explicit_inline_active"]
            )
        else:
            _record_blocked("retained_proxy_pan", live_root or "canvas_click_demotion")
            _record_blocked("retained_proxy_zoom", live_root or "canvas_click_demotion")
            _record_blocked(
                "double_click_reactivation", live_root or "canvas_click_demotion"
            )
            reactivation_ok = False

        if reactivation_ok:
            _record_operation("active_wire_drag", _wire_drag)
        else:
            _record_blocked("active_wire_drag", "double_click_reactivation")
        _record_operation(
            "unrelated_property_edit",
            lambda: _single(
                lambda: host.scene.set_node_property(
                    _ENGINEERING_UNRELATED_NODE_ID,
                    "value",
                    not bool(
                        host.model.project.workspaces[_ENGINEERING_WORKSPACE_ID]
                        .nodes[_ENGINEERING_UNRELATED_NODE_ID]
                        .properties.get("value", False)
                    ),
                )
            ),
        )
        _record_operation("unrelated_node_add", lambda: _single(_add_unrelated))
        _record_operation(
            "unrelated_node_delete",
            lambda: _single(
                lambda: host.scene.remove_node(created_node_id[0])
                if created_node_id[0]
                else None
            ),
        )
        _record_operation("unrelated_wire_create", lambda: _single(_create_wire))
        _record_operation("unrelated_wire_reroute", lambda: _single(_reroute_wire))
        _record_operation(
            "unrelated_wire_delete",
            lambda: _single(lambda: host.scene.remove_edge(wire_edge_id[0])),
        )
        _record_operation(
            "viewer_deletion",
            lambda: _single(lambda: host.scene.remove_node(_ENGINEERING_VIEWER_NODE_ID)),
        )

        all_frame_intervals = host.frame_interval_samples_without_readback_ms()
        operation_lookup = {item["operation"]: item for item in operations}
        primary_screen = QGuiApplication.primaryScreen()
        renderer_diagnostics = host.renderer_diagnostics()
        renderer_diagnostics["grab_window_readback_included"] = False
        payload = {
            "scenario": "engineering_step",
            "engineering_step": str(step_path),
            "qt_platform": args.qt_platform,
            "scale_factor_override": args.scale_factor or "",
            "screen_dpr": (
                float(primary_screen.devicePixelRatio()) if primary_screen else 1.0
            ),
            "window_effective_dpr": float(host.window.effectiveDevicePixelRatio()),
            "samples": args.samples,
            "warmup": args.warmup,
            "media_surface_count": 0,
            "node_count": 7,
            "edge_count": 2,
            "workspace_id": _ENGINEERING_WORKSPACE_ID,
            "fixture_metadata": {
                "fixture_source_kind": "production_engineering_step",
                "node_flow": ["data.panel", "engineering.cad_import", "model.viewer"],
                "step_path": str(step_path),
            },
            "setup_ms": setup_ms,
            "pan_ms": operation_lookup["proxy_pan_control"]["timings_ms"],
            "zoom_ms": operation_lookup["proxy_zoom_control"]["timings_ms"],
            "frame_intervals_ms": all_frame_intervals,
            "frame_interval_ms_without_readback": all_frame_intervals,
            "frame_count": host.frame_render_timestamp_index(),
            "renderer_diagnostics": renderer_diagnostics,
            "feature_parity": host.collect_feature_parity_snapshot(
                expected_media_surface_count=0
            ),
            "grab_window_readback_included": False,
            "qsg_info_capture_enabled": bool(args.capture_qsg_info),
            "instrumentation": lifecycle.snapshot(),
            "overlay_metrics": overlay_manager.overlay_metrics_snapshot(),
            "top_functions": [],
            "operations": operations,
            "operation_gaps": [
                {
                    "operation": item["operation"],
                    "reason": item["unavailable_reason"],
                }
                for item in operations
                if item["status"] != "measured"
            ],
            "driver_limitations": [
                "Node drag, resize, and active wire drag use the production delegate signals; hover, click, double-click, canvas click, wheel, and box zoom use actual QML input events.",
            ],
            "initial_viewer_state": startup_viewer_state,
            "final_viewer_state": _viewer_state(),
            "worker_event_types": [str(event.get("type", "")) for event in worker_events],
        }
        payload["engineering_acceptance"] = _evaluate_engineering_acceptance(payload)
        Path(args.output_path).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        return 0
    finally:
        _OverlayWidgetPresentationService.apply_widget_geometry = staticmethod(
            original_apply_geometry
        )
        if viewer_host is not None:
            viewer_host.shutdown(reason="canvas_engineering_profile_complete")
        if overlay_manager is not None:
            overlay_manager.deleteLater()
        if host is not None:
            host.close()
        worker_services.reset()


# ---------------------------------------------------------------------------
# Instrumentation helper
# ---------------------------------------------------------------------------


@dataclass
class _MethodStat:
    call_count: int = 0
    total_ns: int = 0
    samples_ns: list[int] = field(default_factory=list)


class _Instrumentation:
    def __init__(self) -> None:
        self._stats: dict[str, _MethodStat] = {}

    def install(self, owner: type, attr: str, *, classmethod_like: bool) -> None:
        original = getattr(owner, attr)
        key = f"{owner.__name__}.{attr}"
        stat = self._stats.setdefault(key, _MethodStat())

        def _recorded_call(*args, **kwargs):  # noqa: ANN001
            t0 = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                elapsed = time.perf_counter_ns() - t0
                stat.call_count += 1
                stat.total_ns += elapsed
                stat.samples_ns.append(elapsed)

        _recorded_call.__name__ = original.__name__
        _recorded_call.__wrapped__ = original  # type: ignore[attr-defined]
        setattr(
            owner,
            attr,
            staticmethod(_recorded_call) if classmethod_like else _recorded_call,
        )

    def reset(self) -> None:
        for stat in self._stats.values():
            stat.call_count = 0
            stat.total_ns = 0
            stat.samples_ns = []

    def snapshot(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key, stat in self._stats.items():
            samples_ms = [s / 1_000_000.0 for s in stat.samples_ns]
            summary = {
                "call_count": stat.call_count,
                "total_ms": stat.total_ns / 1_000_000.0,
                "mean_ms": (statistics.fmean(samples_ms) if samples_ms else 0.0),
                "median_ms": (statistics.median(samples_ms) if samples_ms else 0.0),
                "max_ms": max(samples_ms, default=0.0),
                "p95_ms": _percentile(samples_ms, 95.0),
            }
            result[key] = summary
        return result


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower))


def _evaluate_engineering_acceptance(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one engineering interaction report without launching Qt or CAD."""
    failures: list[str] = []
    operations = list(report.get("operations", []))
    actual_order = tuple(str(item.get("operation", "")) for item in operations)
    if actual_order != _ENGINEERING_OPERATION_ORDER:
        failures.append(
            "operation order mismatch: "
            f"expected {list(_ENGINEERING_OPERATION_ORDER)!r}, got {list(actual_order)!r}"
        )
    by_name = {str(item.get("operation", "")): item for item in operations}

    def operation(name: str) -> dict[str, Any]:
        value = by_name.get(name)
        if value is None:
            failures.append(f"missing operation: {name}")
            return {}
        status = str(value.get("status", ""))
        if status in {"failed", "unsupported"}:
            failures.append(
                f"{name}: {value.get('unavailable_reason') or 'not measured'}"
            )
        return value

    def measured(item: dict[str, Any]) -> bool:
        return str(item.get("status", "")) == "measured"

    def state(item: dict[str, Any], key: str) -> dict[str, Any]:
        value = item.get(key, {})
        return dict(value) if isinstance(value, dict) else {}

    def deltas(item: dict[str, Any], key: str = "lifecycle_deltas") -> dict[str, int]:
        value = item.get(key, {})
        if not isinstance(value, dict):
            return {}
        return {str(name): int(count or 0) for name, count in value.items()}

    native_churn_keys = (
        "binder_bind",
        "binder_release",
        "binder_render",
        "dataset_load",
        "widget_create",
        "native_move_calls",
        "native_resize_calls",
        "native_set_geometry_calls",
    )
    passive_unchanged_keys = (
        *native_churn_keys,
        "viewer_host_sync",
        "embedded_interaction_sync",
        "camera_capture",
        "preview_capture",
        "execution_open",
        "execution_update",
        "execution_close",
        "execution_materialize",
        "execution_query",
        "overlay_full_sync",
        "overlay_transform_sync",
        "overlay_skipped_delta",
    )

    def require_zero(name: str, values: dict[str, int], keys=native_churn_keys) -> None:  # noqa: ANN001
        nonzero = {key: values.get(key, 0) for key in keys if values.get(key, 0)}
        if nonzero:
            failures.append(f"{name}: unexpected native work {nonzero!r}")

    startup = operation("startup_proxy")
    if measured(startup):
        startup_after = state(startup, "viewer_after")
        if startup_after.get("live_mode") != "proxy":
            failures.append("startup_proxy: viewer must remain proxy")
        if startup_after.get("widget_identity"):
            failures.append("startup_proxy: native widget exists before activation")
        if startup_after.get("retained_inline_node_id"):
            failures.append("startup_proxy: retained widget exists before activation")
        if bool(startup_after.get("explicit_inline_active")):
            failures.append("startup_proxy: explicit activation became active")
        require_zero("startup_proxy", deltas(startup))

    passive_names = (
        "selection_without_activation",
        "hover_without_activation",
        "single_click_without_activation",
    )
    for name in passive_names:
        item = operation(name)
        if not measured(item):
            continue
        after = state(item, "viewer_after")
        if after.get("live_mode") != "proxy":
            failures.append(f"{name}: viewer must remain proxy")
        if after.get("widget_identity"):
            failures.append(f"{name}: native widget exists before activation")
        if after.get("retained_inline_node_id"):
            failures.append(f"{name}: retained widget exists before activation")
        if bool(after.get("explicit_inline_active")):
            failures.append(f"{name}: explicit activation became active")
        require_zero(name, deltas(item), passive_unchanged_keys)

    activation = operation("proxy_double_click_activation")
    if measured(activation):
        activation_before = state(activation, "viewer_before")
        activation_after = state(activation, "viewer_after")
        activation_delta = deltas(activation)
        if activation_before.get("widget_identity"):
            failures.append("proxy_double_click_activation: widget existed before activation")
        if not activation_after.get("widget_identity"):
            failures.append("proxy_double_click_activation: widget was not created")
        if activation_after.get("live_mode") != "full":
            failures.append("proxy_double_click_activation: viewer did not become full")
        if not bool(activation_after.get("explicit_inline_active")):
            failures.append("proxy_double_click_activation: explicit activation not recorded")
        if activation_delta.get("widget_create", 0) != 1:
            failures.append("proxy_double_click_activation: expected exactly one widget creation")
        if activation_delta.get("dataset_load", 0) != 1:
            failures.append("proxy_double_click_activation: expected exactly one dataset load")
        if activation_delta.get("binder_release", 0):
            failures.append("proxy_double_click_activation: binder released during activation")
        if activation_before.get("transport_revision") != activation_after.get(
            "transport_revision"
        ):
            failures.append("proxy_double_click_activation: transport revision changed")

    continuous_names = _ENGINEERING_CONTINUOUS_OPERATION_NAMES
    live_names = {
        "live_wheel_zoom",
        "live_box_zoom",
        "active_viewer_drag",
        "active_viewer_resize",
        "active_wire_drag",
    }
    for name in continuous_names:
        item = operation(name)
        if not measured(item):
            continue
        continuous_delta = deltas(item, "continuous_lifecycle_deltas")
        require_zero(name, continuous_delta)
        if deltas(item).get("execution_update", 0):
            failures.append(
                f"{name}: execution live-mode update occurred during transient gesture"
            )
        if name == "active_wire_drag":
            require_zero(
                name,
                continuous_delta,
                ("viewer_host_sync", "overlay_full_sync"),
            )
        if float(item.get("timing_p95_ms", 0.0)) > 33.3:
            failures.append(f"{name}: timing p95 exceeds 33.3 ms")
        if float(item.get("frame_interval_p95_ms", 0.0)) > 33.3:
            failures.append(f"{name}: frame p95 exceeds 33.3 ms")
        before = state(item, "viewer_before")
        after = state(item, "viewer_after")
        if before.get("transport_revision") != after.get("transport_revision"):
            failures.append(f"{name}: transport revision changed")
        if name in live_names:
            during = state(item, "viewer_during")
            if before.get("live_mode") != "full" or not bool(
                before.get("explicit_inline_active")
            ):
                failures.append(f"{name}: viewer was not explicitly live before gesture")
            if bool(during.get("native_overlay_visible")):
                failures.append(f"{name}: native overlay remained visible during gesture")
            if bool(during.get("native_overlay_geometry_ready")):
                failures.append(f"{name}: native geometry remained ready during gesture")
            if bool(during.get("native_updates_enabled")):
                failures.append(f"{name}: native updates remained enabled during gesture")
            if before.get("widget_identity") != after.get("widget_identity"):
                failures.append(f"{name}: widget identity changed")
            if after.get("live_mode") != "full":
                failures.append(f"{name}: viewer did not restore full mode")
            if not bool(after.get("explicit_inline_active")):
                failures.append(f"{name}: explicit inline activation did not restore")
            if not bool(after.get("native_overlay_visible")):
                failures.append(f"{name}: native overlay did not restore")
            if not bool(after.get("native_overlay_geometry_ready")):
                failures.append(f"{name}: native geometry did not restore")
            if not bool(after.get("native_updates_enabled")):
                failures.append(f"{name}: native updates did not restore")

    proxy_pan = operation("proxy_pan_control")
    retained_pan = operation("retained_proxy_pan")
    proxy_zoom = operation("proxy_zoom_control")
    retained_zoom = operation("retained_proxy_zoom")
    if measured(proxy_pan) and measured(retained_pan) and float(
        retained_pan.get("timing_p95_ms", 0.0)
    ) > float(
        proxy_pan.get("timing_p95_ms", 0.0)
    ) + 8.0:
        failures.append("retained_proxy_pan: more than 8 ms slower than proxy control")
    if measured(proxy_zoom) and measured(retained_zoom) and float(
        retained_zoom.get("timing_p95_ms", 0.0)
    ) > float(
        proxy_zoom.get("timing_p95_ms", 0.0)
    ) + 8.0:
        failures.append("retained_proxy_zoom: more than 8 ms slower than proxy control")

    demotion = operation("canvas_click_demotion")
    if measured(demotion):
        demotion_before = state(demotion, "viewer_before")
        demotion_after = state(demotion, "viewer_after")
        if demotion_before.get("live_mode") != "full" or not bool(
            demotion_before.get("explicit_inline_active")
        ):
            failures.append("canvas_click_demotion: viewer was not live before click")
        if demotion_before.get("widget_identity") != demotion_after.get("widget_identity"):
            failures.append("canvas_click_demotion: widget identity changed")
        if demotion_after.get("live_mode") != "proxy":
            failures.append("canvas_click_demotion: viewer did not demote")
        if demotion_after.get("retained_inline_node_id") != _ENGINEERING_VIEWER_NODE_ID:
            failures.append("canvas_click_demotion: viewer was not retained")
        if demotion_after.get("native_overlay_visible"):
            failures.append("canvas_click_demotion: retained widget remained visible")
        demotion_delta = deltas(demotion)
        if demotion_delta.get("binder_release", 0):
            failures.append("canvas_click_demotion: binder released retained widget")
        preview_captures = demotion_delta.get("preview_capture", 0)
        if preview_captures > 1:
            failures.append("canvas_click_demotion: captured more than one preview")
        if (
            preview_captures == 1
            or bool(demotion_before.get("cached_preview_available"))
        ) and not bool(demotion_after.get("cached_preview_available")):
            failures.append("canvas_click_demotion: cached preview was not retained")

    reactivation = operation("double_click_reactivation")
    if measured(reactivation):
        reactivation_before = state(reactivation, "viewer_before")
        reactivation_after = state(reactivation, "viewer_after")
        if reactivation_before.get("widget_identity") != reactivation_after.get(
            "widget_identity"
        ):
            failures.append("double_click_reactivation: widget identity changed")
        if reactivation_after.get("live_mode") != "full" or not bool(
            reactivation_after.get("explicit_inline_active")
        ):
            failures.append("double_click_reactivation: viewer did not restore full mode")
        require_zero(
            "double_click_reactivation",
            deltas(reactivation),
            ("binder_release", "dataset_load", "widget_create"),
        )

    unrelated_names = (
        "unrelated_property_edit",
        "unrelated_node_add",
        "unrelated_node_delete",
        "unrelated_wire_create",
        "unrelated_wire_reroute",
        "unrelated_wire_delete",
    )
    for name in unrelated_names:
        item = operation(name)
        if not measured(item):
            continue
        require_zero(name, deltas(item))
        before = state(item, "viewer_before")
        after = state(item, "viewer_after")
        if before.get("widget_identity") != after.get("widget_identity"):
            failures.append(f"{name}: retained widget identity changed")
        if before.get("transport_revision") != after.get("transport_revision"):
            failures.append(f"{name}: transport revision changed")
        if deltas(item).get("overlay_skipped_delta", 0) < 1:
            failures.append(f"{name}: skipped-delta counter did not increment")

    deletion = operation("viewer_deletion")
    if measured(deletion):
        deletion_after = state(deletion, "viewer_after")
        if deltas(deletion).get("binder_release", 0) != 1:
            failures.append("viewer_deletion: expected exactly one binder release")
        if deletion_after.get("widget_identity"):
            failures.append("viewer_deletion: widget remains resident")
        if deletion_after.get("retained_inline_node_id"):
            failures.append("viewer_deletion: retained key remains")
        if deletion_after.get("phase") or deletion_after.get("session_id"):
            failures.append("viewer_deletion: session projection remains")
        if bool(deletion_after.get("explicit_inline_active")):
            failures.append("viewer_deletion: explicit inline activation remains")
        if int(deletion_after.get("transport_revision", 0) or 0) != 0:
            failures.append("viewer_deletion: transport revision remains")

    return {
        "status": "PASS" if not failures else "FAIL",
        "evaluation_scope": "single_run_diagnostic",
        "release_status": "DIAGNOSTIC_ONLY",
        "release_ready": False,
        "failures": failures,
        "operation_count": len(operations),
        "preferred_frame_target_ms": 16.7,
        "hard_frame_target_ms": 33.3,
        "three_run_cv_gate": 0.20,
        "three_run_cv_evaluated": False,
    }


def _evaluate_engineering_release_acceptance(
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate three independent engineering reports for release readiness."""
    failures: list[str] = []
    if len(reports) != 3:
        failures.append(
            f"release acceptance requires exactly 3 reports; received {len(reports)}"
        )
    per_run_results = [
        _evaluate_engineering_acceptance(report) for report in reports
    ]
    for index, (report, result) in enumerate(
        zip(reports, per_run_results), start=1
    ):
        if str(report.get("qt_platform", "")).strip().casefold() != "windows":
            failures.append(f"run {index}: qt_platform must be windows")
        renderer = report.get("renderer_diagnostics", {})
        renderer = renderer if isinstance(renderer, dict) else {}
        if str(renderer.get("graphics_api", "")) != "Direct3D11Rhi":
            failures.append(
                f"run {index}: graphics_api must be Direct3D11Rhi"
            )
        if str(renderer.get("qml_host_kind", "")) != "qquickwidget":
            failures.append(f"run {index}: qml_host_kind must be qquickwidget")
        if renderer.get("grab_window_readback_included") is not False:
            failures.append(
                f"run {index}: renderer grab_window_readback_included must be false"
            )
        feature_parity = report.get("feature_parity", {})
        feature_parity = feature_parity if isinstance(feature_parity, dict) else {}
        if feature_parity.get("pass") is not True:
            failures.append(f"run {index}: feature parity must pass")
        if report.get("grab_window_readback_included") is not False:
            failures.append(
                f"run {index}: grab_window_readback_included must be false"
            )
        if result["status"] != "PASS":
            failures.extend(
                f"run {index}: {failure}" for failure in result["failures"]
            )
        non_measured = [
            str(item.get("operation", ""))
            for item in report.get("operations", [])
            if str(item.get("status", "")) != "measured"
        ]
        if non_measured:
            failures.append(
                f"run {index}: non-measured operations {non_measured!r}"
            )

    coefficients: dict[str, dict[str, float]] = {}
    if len(reports) == 3:
        operation_maps = [
            {
                str(item.get("operation", "")): item
                for item in report.get("operations", [])
            }
            for report in reports
        ]
        for name in _ENGINEERING_CONTINUOUS_OPERATION_NAMES:
            timing_values = [
                float(operation_map.get(name, {}).get("timing_p95_ms", 0.0))
                for operation_map in operation_maps
            ]
            frame_values = [
                float(
                    operation_map.get(name, {}).get(
                        "frame_interval_p95_ms", 0.0
                    )
                )
                for operation_map in operation_maps
            ]

            def cv(values: list[float]) -> float:
                mean = statistics.fmean(values)
                if mean == 0.0:
                    return 0.0 if not any(values) else float("inf")
                return statistics.pstdev(values) / abs(mean)

            timing_cv = cv(timing_values)
            frame_cv = cv(frame_values)
            coefficients[name] = {
                "timing_p95_cv": timing_cv,
                "frame_p95_cv": frame_cv,
            }
            if timing_cv > 0.20:
                failures.append(f"{name}: timing p95 CV exceeds 0.20")
            if frame_cv > 0.20:
                failures.append(f"{name}: frame p95 CV exceeds 0.20")

    release_ready = len(reports) == 3 and not failures
    return {
        "status": "PASS" if release_ready else "FAIL",
        "evaluation_scope": "three_run_release",
        "release_status": "READY" if release_ready else "NOT_READY",
        "release_ready": release_ready,
        "failures": failures,
        "run_count": len(reports),
        "per_run_results": per_run_results,
        "coefficients_of_variation": coefficients,
        "three_run_cv_gate": 0.20,
        "three_run_cv_evaluated": len(reports) == 3,
    }


def _profile_top_functions(stats: pstats.Stats, *, top_n: int) -> list[dict[str, Any]]:
    """Extract top-N functions sorted by cumulative time."""
    func_records: list[tuple[float, float, int, str]] = []
    for func, (call_count, _, total, cumulative, _callers) in stats.stats.items():
        filename, lineno, name = func
        # Skip pstats internals and built-ins
        if filename in {"~", "<built-in>"}:
            continue
        # Only include functions from the project, PyQt6, or Qt-related code.
        loc = f"{filename}:{lineno}"
        func_records.append((cumulative, total, call_count, f"{name}@{loc}"))
    func_records.sort(key=lambda r: r[0], reverse=True)
    return [
        {
            "function": rec[3],
            "call_count": rec[2],
            "total_ms": rec[1] * 1000.0,
            "cumulative_ms": rec[0] * 1000.0,
        }
        for rec in func_records[:top_n]
    ]


# ---------------------------------------------------------------------------
# Overlay-sync micro-benchmark (separate process)
# ---------------------------------------------------------------------------


def _run_overlay_sync_micro(args: argparse.Namespace) -> int:
    """Pure-Python timing of `EmbeddedViewerOverlayManager._sync_impl`.

    The overlay manager is normally driven by `view_state_changed` from a real
    `ViewportBridge`. The cost of `_sync_impl` scales with the number of
    `graphNodeCard` items in the QML tree because of the recursive walk in
    `_walk_items`. This micro-benchmark builds a synthetic GraphCanvas with N
    nodes and an attached widget, then times one full pan/zoom-driven sync per
    sample.
    """
    os.environ["QT_QPA_PLATFORM"] = args.qt_platform
    _apply_host_backend_environment(args)
    if args.scale_factor:
        os.environ["QT_SCALE_FACTOR"] = args.scale_factor

    from PyQt6.QtCore import QRectF, QUrl, Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtQml import QQmlComponent
    from PyQt6.QtQuickWidgets import QQuickWidget
    from PyQt6.QtWidgets import QApplication, QFrame

    from ea_node_editor.persistence.serializer import JsonProjectSerializer
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.ui.perf.performance_harness import (
        BenchmarkConfig,
        SyntheticGraphConfig,
        _BenchmarkMainWindowBridge,
        _build_scenario_project,
        _CANVAS_BENCHMARK_HEIGHT,
        _CANVAS_BENCHMARK_WIDTH,
        _CANVAS_GRAPH_THEME_ID,
        _CANVAS_THEME_ID,
        _bind_scene_for_workspace,
        _graph_canvas_qml_path,
        _scenario_label_for_config,
    )
    from ea_node_editor.ui.media_preview_provider import (
        LOCAL_MEDIA_PREVIEW_PROVIDER_ID,
        LocalMediaPreviewImageProvider,
    )
    from ea_node_editor.ui.pdf_preview_provider import (
        LOCAL_PDF_PREVIEW_PROVIDER_ID,
        LocalPdfPreviewImageProvider,
    )
    from ea_node_editor.ui_qml.embedded_viewer_overlay_manager import (
        EmbeddedViewerOverlayManager,
        EmbeddedViewerOverlaySpec,
    )
    from ea_node_editor.ui_qml.graph_canvas_command import GraphCanvasCommandBridge
    from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
    from ea_node_editor.ui_qml.graph_theme_bridge import GraphThemeBridge
    from ea_node_editor.ui_qml.theme_bridge import ThemeBridge

    app = QApplication.instance() or QApplication(sys.argv)

    # Build a heavy-media project so we have many node cards.
    cfg = BenchmarkConfig(
        synthetic_graph=SyntheticGraphConfig(
            node_count=args.nodes,
            edge_count=args.edges,
            seed=1337,
        ),
        load_iterations=1,
        interaction_samples=1,
        interaction_warmup_samples=0,
        scenario=args.scenario,
        project_path=args.project_path,
        workspace_id=args.workspace_id,
        stress_fixture=args.stress_fixture,
        qml_host=args.qml_host,
        qsg_rhi_backend=args.qsg_rhi_backend,
    )
    scenario = _scenario_label_for_config(cfg)

    serializer = JsonProjectSerializer(build_default_registry())
    with _build_scenario_project(cfg) as scenario_project:
        project = scenario_project.project
        doc = serializer.to_document(project)
        workspace_id = scenario_project.workspace_id or project.active_workspace_id

        from ea_node_editor.graph.model import GraphModel
        model = GraphModel(serializer.from_document(doc))
        scene_bridge, view_bridge = _bind_scene_for_workspace(
            app=app, model=model, workspace_id=workspace_id
        )
        view_bridge.set_viewport_size(
            float(_CANVAS_BENCHMARK_WIDTH), float(_CANVAS_BENCHMARK_HEIGHT)
        )

        # Create the QQuickWidget instead of QQuickWindow so we can attach
        # an EmbeddedViewerOverlayManager.
        widget = QQuickWidget()
        widget.engine().addImageProvider(
            LOCAL_MEDIA_PREVIEW_PROVIDER_ID, LocalMediaPreviewImageProvider()
        )
        widget.engine().addImageProvider(
            LOCAL_PDF_PREVIEW_PROVIDER_ID, LocalPdfPreviewImageProvider()
        )
        theme_bridge = ThemeBridge(widget.engine(), theme_id=_CANVAS_THEME_ID)
        graph_theme_bridge = GraphThemeBridge(
            widget.engine(), theme_id=_CANVAS_GRAPH_THEME_ID
        )
        main_window_bridge = _BenchmarkMainWindowBridge()
        canvas_state_bridge = GraphCanvasStateBridge(
            shell_window=main_window_bridge,
            scene_bridge=scene_bridge,
            view_bridge=view_bridge,
        )
        canvas_command_bridge = GraphCanvasCommandBridge(
            shell_window=main_window_bridge,
            scene_bridge=scene_bridge,
            view_bridge=view_bridge,
        )
        ctx = widget.engine().rootContext()
        ctx.setContextProperty("themeBridge", theme_bridge)
        ctx.setContextProperty("graphThemeBridge", graph_theme_bridge)
        ctx.setContextProperty("canvasStateBridge", canvas_state_bridge)
        ctx.setContextProperty("canvasCommandBridge", canvas_command_bridge)

        widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        widget.resize(_CANVAS_BENCHMARK_WIDTH, _CANVAS_BENCHMARK_HEIGHT)
        # Provide initial properties via setContent so canvasStateBridge wires up.
        widget.setSource(QUrl.fromLocalFile(str(_graph_canvas_qml_path())))
        widget.show()
        # Pump events until QML is ready.
        app.processEvents()
        for _ in range(10):
            app.processEvents()

        if widget.status() != QQuickWidget.Status.Ready:
            sys.stderr.write(
                f"GraphCanvas.qml not ready in QQuickWidget: {widget.status()}\n"
            )

        overlay_manager = EmbeddedViewerOverlayManager(
            widget,
            quick_widget=widget,
            scene_bridge=scene_bridge,
            view_bridge=view_bridge,
        )

        # Pick the first available node id (any node will do for the
        # micro-bench because we are timing the *traversal* and the geometry
        # mapping, both of which are independent of node type).
        first_node_id = next(iter(model.project.workspaces[workspace_id].nodes.keys()))
        spec = EmbeddedViewerOverlaySpec(
            workspace_id=workspace_id, node_id=first_node_id, session_id="profile"
        )
        overlay_manager.set_active_overlays([spec])

        # Attach a synthetic heavy widget so the overlay container is real.
        fake_widget = QFrame(widget)
        fake_widget.setFrameShape(QFrame.Shape.Box)
        fake_widget.setStyleSheet("background-color: #2bd576;")
        fake_widget.resize(320, 240)
        overlay_manager.attach_overlay_widget(first_node_id, fake_widget)

        # Pump until the manager has settled and node cards exist.
        for _ in range(20):
            app.processEvents()

        # Time `_sync_impl` directly to isolate Python overhead.
        sync_samples_ms: list[float] = []
        overlay_metrics_samples: list[dict[str, Any]] = []
        for _ in range(args.samples):
            t0 = time.perf_counter_ns()
            overlay_manager._sync_impl()
            elapsed_ns = time.perf_counter_ns() - t0
            sync_samples_ms.append(elapsed_ns / 1_000_000.0)
            overlay_metrics_samples.append(overlay_manager.overlay_metrics_snapshot())
            # Move the viewport so the next sync sees a different geometry
            # (forces real `_aligned_rect` work + `mapToItem` re-evaluation).
            view_bridge.pan_by(8.0, 5.0)
            app.processEvents()

        primary_screen = QGuiApplication.primaryScreen()
        screen_dpr = float(primary_screen.devicePixelRatio()) if primary_screen else 1.0

        payload = {
            "scenario": scenario,
            "workspace_id": workspace_id,
            "node_count": len(project.workspaces[workspace_id].nodes),
            "edge_count": len(project.workspaces[workspace_id].edges),
            "fixture_metadata": scenario_project.scenario_details.get("fixture_metadata", {}),
            "samples": args.samples,
            "screen_dpr": screen_dpr,
            "scale_factor_override": args.scale_factor or "",
            "sync_impl_ms": sync_samples_ms,
            "overlay_metrics": overlay_manager.overlay_metrics_snapshot(),
            "overlay_metrics_samples": overlay_metrics_samples,
        }

        widget.deleteLater()
        scene_bridge.deleteLater()
        view_bridge.deleteLater()
        main_window_bridge.deleteLater()

    Path(args.output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Main driver: orchestrates subprocess scenarios + visualization
# ---------------------------------------------------------------------------


_DEFAULT_SCENARIOS = [
    {
        "label": "synthetic_native_dpr",
        "scenario": "synthetic_exec",
        "scale_factor": "",
        "nodes": 200,
        "edges": 320,
    },
    {
        "label": "heavy_media_native_dpr",
        "scenario": "heavy_media",
        "scale_factor": "",
        "nodes": 18,
        "edges": 30,
    },
    {
        "label": "heavy_media_dpr_1x",
        "scenario": "heavy_media",
        "scale_factor": "1",
        "nodes": 18,
        "edges": 30,
    },
]


def _orchestrate(args: argparse.Namespace) -> int:
    out_root = REPO_ROOT / "artifacts" / "canvas_lag_profiling"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = out_root / f"profile_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.engineering_step:
        scenarios = [
            {
                "label": "engineering_explicit_live",
                "scenario": "synthetic_exec",
                "scale_factor": "",
                "nodes": 7,
                "edges": 2,
            }
        ]
    elif args.stress_fixture or args.project_path:
        scenarios = [
            {
                "label": f"stress_fixture_{args.stress_fixture}" if args.stress_fixture else "project_fixture",
                "scenario": "stress_fixture" if args.stress_fixture else "project_fixture",
                "scale_factor": "",
                "nodes": args.nodes,
                "edges": args.edges,
            }
        ]
    else:
        scenarios = _DEFAULT_SCENARIOS
        if args.skip_dpr_ablation:
            scenarios = [s for s in scenarios if s["label"] != "heavy_media_dpr_1x"]

    results: list[dict[str, Any]] = []
    for scenario_cfg in scenarios:
        host_backend_suffix = ""
        if args.qml_host or args.qsg_rhi_backend:
            host_backend_suffix = (
                f"_{args.qml_host or 'host_env'}_"
                f"{args.qsg_rhi_backend or 'qt_default'}"
            )
        label = f"{scenario_cfg['label']}{host_backend_suffix}"
        out_path = out_dir / f"scenario_{label}.json"
        cmd = [
            sys.executable,
            __file__,
            "--mode",
            "scenario",
            "--scenario",
            scenario_cfg["scenario"],
            "--samples",
            str(args.samples),
            "--warmup",
            str(args.warmup),
            "--nodes",
            str(scenario_cfg["nodes"]),
            "--edges",
            str(scenario_cfg["edges"]),
            "--seed",
            str(args.seed),
            "--zoom-min",
            str(args.zoom_min),
            "--zoom-max",
            str(args.zoom_max),
            "--qt-platform",
            args.qt_platform,
            "--output-path",
            str(out_path),
        ]
        if scenario_cfg["scale_factor"]:
            cmd.extend(["--scale-factor", scenario_cfg["scale_factor"]])
        if args.project_path:
            cmd.extend(["--project-path", args.project_path])
        if args.workspace_id:
            cmd.extend(["--workspace-id", args.workspace_id])
        if args.stress_fixture:
            cmd.extend(["--stress-fixture", args.stress_fixture])
        if args.engineering_step:
            cmd.extend(["--engineering-step", args.engineering_step])
        if args.qml_host:
            cmd.extend(["--qml-host", args.qml_host])
        if args.qsg_rhi_backend:
            cmd.extend(["--qsg-rhi-backend", args.qsg_rhi_backend])
        if args.capture_qsg_info:
            cmd.append("--capture-qsg-info")
        sys.stdout.write(f"[profile] Running scenario {label} ...\n")
        sys.stdout.flush()
        log_path = out_dir / f"scenario_{label}.log"
        with log_path.open("wb") as log_file:
            completed = subprocess.run(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        if completed.returncode != 0:
            sys.stderr.write(
                f"[profile] Scenario {label} failed (rc={completed.returncode}).\n"
                f"See log at: {log_path}\n"
            )
            continue
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[profile] Failed to read {out_path}: {exc}\n")
            continue
        payload["label"] = label
        results.append(payload)
        sys.stdout.write(f"[profile]   pan p95 {_p95(payload['pan_ms']):.2f} ms / "
                         f"zoom p95 {_p95(payload['zoom_ms']):.2f} ms / "
                         f"frames {payload['frame_count']}\n")

    # Run overlay-sync micro-bench.
    if not args.skip_overlay_micro and not args.engineering_step:
        out_path = out_dir / "overlay_sync_micro.json"
        overlay_scenario = "heavy_media"
        overlay_nodes = "18"
        overlay_edges = "30"
        if args.stress_fixture or args.project_path:
            overlay_scenario = "stress_fixture" if args.stress_fixture else "project_fixture"
            overlay_nodes = str(args.nodes)
            overlay_edges = str(args.edges)
        cmd = [
            sys.executable,
            __file__,
            "--mode",
            "overlay-sync",
            "--scenario",
            overlay_scenario,
            "--samples",
            str(max(20, args.samples)),
            "--nodes",
            overlay_nodes,
            "--edges",
            overlay_edges,
            "--qt-platform",
            args.qt_platform,
            "--output-path",
            str(out_path),
        ]
        if args.project_path:
            cmd.extend(["--project-path", args.project_path])
        if args.workspace_id:
            cmd.extend(["--workspace-id", args.workspace_id])
        if args.stress_fixture:
            cmd.extend(["--stress-fixture", args.stress_fixture])
        if args.qml_host:
            cmd.extend(["--qml-host", args.qml_host])
        if args.qsg_rhi_backend:
            cmd.extend(["--qsg-rhi-backend", args.qsg_rhi_backend])
        if args.capture_qsg_info:
            cmd.append("--capture-qsg-info")
        sys.stdout.write("[profile] Running overlay sync micro-benchmark ...\n")
        sys.stdout.flush()
        log_path = out_dir / "overlay_sync_micro.log"
        with log_path.open("wb") as log_file:
            completed = subprocess.run(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        if completed.returncode != 0:
            sys.stderr.write(
                "[profile] Overlay sync micro-benchmark failed.\n"
                f"See log at: {log_path}\n"
            )
            overlay_payload = None
        else:
            try:
                overlay_payload = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[profile] Failed to read {out_path}: {exc}\n")
                overlay_payload = None
    else:
        overlay_payload = None

    summary_path = out_dir / "profile_results.json"
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command_args": vars(args),
        "scenarios": results,
        "overlay_sync_micro": overlay_payload,
        "qsg_info_capture_enabled": bool(args.capture_qsg_info),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Generate charts + markdown.
    _make_visualizations(out_dir, results, overlay_payload)
    _write_markdown_report(out_dir, results, overlay_payload)

    sys.stdout.write(f"\n[profile] Done. Results in: {out_dir}\n")
    return 0


def _p95(values: list[float]) -> float:
    return _percentile(values, 95.0)


def _make_visualizations(
    out_dir: Path,
    results: list[dict[str, Any]],
    overlay_payload: dict[str, Any] | None,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.stderr.write("[profile] matplotlib not available; skipping charts.\n")
        return

    if not results:
        return

    # 1. Pan / zoom timing per scenario (box plot).
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [r["label"] for r in results]
    pan_data = [r["pan_ms"] for r in results]
    zoom_data = [r["zoom_ms"] for r in results]
    width = 0.35
    positions = list(range(len(labels)))
    bp1 = ax.boxplot(
        pan_data,
        positions=[p - width / 2 for p in positions],
        widths=width,
        patch_artist=True,
        boxprops=dict(facecolor="#4e79a7"),
        medianprops=dict(color="white"),
    )
    bp2 = ax.boxplot(
        zoom_data,
        positions=[p + width / 2 for p in positions],
        widths=width,
        patch_artist=True,
        boxprops=dict(facecolor="#f28e2b"),
        medianprops=dict(color="white"),
    )
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("Step time (ms)")
    ax.set_title("Pan / zoom step time by scenario (lower is better)")
    ax.axhline(33.3, color="#e15759", linestyle="--", linewidth=1, label="30 FPS budget (33.3 ms)")
    ax.axhline(16.7, color="#76b7b2", linestyle="--", linewidth=1, label="60 FPS budget (16.7 ms)")
    ax.legend(
        [bp1["boxes"][0], bp2["boxes"][0], plt.Line2D([], [], color="#e15759", linestyle="--"),
         plt.Line2D([], [], color="#76b7b2", linestyle="--")],
        ["pan_ms", "zoom_ms", "30 FPS", "60 FPS"],
        loc="upper left",
    )
    fig.tight_layout()
    fig.savefig(out_dir / "01_pan_zoom_step_times.png", dpi=120)
    plt.close(fig)

    # 2. Frame interval distribution (histogram per scenario).
    fig, axes = plt.subplots(
        nrows=len(results), ncols=1, figsize=(10, max(3, 2.5 * len(results))), sharex=True
    )
    if len(results) == 1:
        axes = [axes]
    for ax, r in zip(axes, results):
        intervals = r["frame_intervals_ms"]
        if not intervals:
            ax.text(0.5, 0.5, "no frames captured", ha="center", va="center")
            ax.set_title(r["label"])
            continue
        ax.hist(intervals, bins=40, color="#59a14f", alpha=0.85)
        ax.axvline(16.7, color="#76b7b2", linestyle="--", linewidth=1)
        ax.axvline(33.3, color="#e15759", linestyle="--", linewidth=1)
        median_iv = statistics.median(intervals)
        p95_iv = _percentile(intervals, 95.0)
        ax.set_title(
            f"{r['label']}  median={median_iv:.1f} ms  p95={p95_iv:.1f} ms  "
            f"(equiv FPS p50={_safe_fps(median_iv):.1f}, p5={_safe_fps(p95_iv):.1f})"
        )
        ax.set_ylabel("Frames")
    axes[-1].set_xlabel("Frame interval (ms)")
    fig.tight_layout()
    fig.savefig(out_dir / "02_frame_interval_histograms.png", dpi=120)
    plt.close(fig)

    # 3. Per-component instrumentation breakdown (stacked bar).
    fig, ax = plt.subplots(figsize=(10, 5))
    component_keys: list[str] = []
    for r in results:
        for k in r["instrumentation"].keys():
            if k not in component_keys:
                component_keys.append(k)
    bottoms = [0.0] * len(results)
    palette = [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
        "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    ]
    for index, comp in enumerate(component_keys):
        totals = []
        for r in results:
            stat = r["instrumentation"].get(comp, {})
            totals.append(float(stat.get("total_ms", 0.0)))
        ax.bar(
            range(len(results)),
            totals,
            bottom=bottoms,
            color=palette[index % len(palette)],
            label=comp,
        )
        bottoms = [b + t for b, t in zip(bottoms, totals)]
    ax.set_xticks(range(len(results)))
    ax.set_xticklabels([r["label"] for r in results], rotation=20, ha="right")
    ax.set_ylabel("Total Python time during pan/zoom loop (ms)")
    ax.set_title("Python hot path per scenario (instrumented methods)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(out_dir / "03_python_component_stack.png", dpi=120)
    plt.close(fig)

    # 4. cProfile top-N functions for the heaviest scenario.
    heaviest = max(results, key=lambda r: _p95(r["pan_ms"]))
    top = heaviest["top_functions"][:15]
    fig, ax = plt.subplots(figsize=(11, 6))
    names = [_short_func_name(t["function"]) for t in top]
    cumulative = [t["cumulative_ms"] for t in top]
    y_positions = list(range(len(names)))
    ax.barh(y_positions, cumulative, color="#4e79a7")
    ax.set_yticks(y_positions)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Cumulative time (ms)")
    ax.set_title(
        f"cProfile top functions during pan/zoom loop ({heaviest['label']})"
    )
    fig.tight_layout()
    fig.savefig(out_dir / "04_cprofile_top_functions.png", dpi=120)
    plt.close(fig)

    # 5. DPR ablation summary (only when both heavy_media native and 1x exist).
    by_label = {r["label"]: r for r in results}
    if "heavy_media_native_dpr" in by_label and "heavy_media_dpr_1x" in by_label:
        a = by_label["heavy_media_native_dpr"]
        b = by_label["heavy_media_dpr_1x"]
        metrics = ["pan p50", "pan p95", "zoom p50", "zoom p95"]
        a_vals = [
            _percentile(a["pan_ms"], 50),
            _percentile(a["pan_ms"], 95),
            _percentile(a["zoom_ms"], 50),
            _percentile(a["zoom_ms"], 95),
        ]
        b_vals = [
            _percentile(b["pan_ms"], 50),
            _percentile(b["pan_ms"], 95),
            _percentile(b["zoom_ms"], 50),
            _percentile(b["zoom_ms"], 95),
        ]
        fig, ax = plt.subplots(figsize=(8, 5))
        x = list(range(len(metrics)))
        width = 0.35
        ax.bar(
            [xi - width / 2 for xi in x],
            a_vals,
            width=width,
            color="#e15759",
            label=f"native DPR ({a.get('window_effective_dpr', 'unknown')}x)",
        )
        ax.bar(
            [xi + width / 2 for xi in x],
            b_vals,
            width=width,
            color="#4e79a7",
            label="forced DPR 1x (QT_SCALE_FACTOR=1)",
        )
        ax.set_xticks(x)
        ax.set_xticklabels(metrics)
        ax.set_ylabel("Step time (ms)")
        ax.set_title("DPR ablation: heavy_media scenario")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "05_dpr_ablation.png", dpi=120)
        plt.close(fig)

    # 6. Overlay sync micro-benchmark, if available.
    if overlay_payload and overlay_payload.get("sync_impl_ms"):
        samples = overlay_payload["sync_impl_ms"]
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(samples, bins=30, color="#9c755f")
        ax.axvline(statistics.median(samples), color="#fff", linestyle="--", label="median")
        ax.set_xlabel("EmbeddedViewerOverlayManager._sync_impl (ms)")
        ax.set_ylabel("Samples")
        ax.set_title(
            f"Overlay sync micro-benchmark "
            f"(N={overlay_payload['node_count']} nodes; "
            f"DPR={overlay_payload['screen_dpr']}x)"
        )
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "06_overlay_sync_micro.png", dpi=120)
        plt.close(fig)


def _safe_fps(interval_ms: float) -> float:
    if interval_ms <= 0:
        return 0.0
    return 1000.0 / interval_ms


def _short_func_name(qualified: str) -> str:
    name, _, loc = qualified.partition("@")
    short_loc = loc
    for marker in ("ea_node_editor", "PyQt6", "site-packages"):
        idx = loc.rfind(marker)
        if idx >= 0:
            short_loc = loc[idx:]
            break
    return f"{name}  ({short_loc})"


def _write_markdown_report(
    out_dir: Path,
    results: list[dict[str, Any]],
    overlay_payload: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append("# Canvas Lag Profiling Report")
    lines.append("")
    lines.append(f"Generated: `{datetime.now(timezone.utc).isoformat()}`")
    lines.append("")
    lines.append("## Per-Scenario Summary")
    lines.append("")
    lines.append(
        "| Label | Scenario | Graphics API | DPR | Readback | Pan p50 (ms) | Pan p95 (ms) | "
        "Zoom p50 (ms) | Zoom p95 (ms) | Frame p95 no-readback (ms) | Frames | Setup (ms) |"
    )
    lines.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        renderer = r.get("renderer_diagnostics", {})
        intervals = r.get("frame_interval_ms_without_readback", r.get("frame_intervals_ms", []))
        lines.append(
            "| {label} | {scenario} | {api} | {dpr} | {readback} | {p50p:.2f} | {p95p:.2f} | "
            "{p50z:.2f} | {p95z:.2f} | {frame_p95:.2f} | {frames} | {setup:.0f} |".format(
                label=r["label"],
                scenario=r["scenario"],
                api=renderer.get("graphics_api", ""),
                dpr=r.get("window_effective_dpr", "?"),
                readback=bool(r.get("grab_window_readback_included", False)),
                p50p=_percentile(r["pan_ms"], 50),
                p95p=_percentile(r["pan_ms"], 95),
                p50z=_percentile(r["zoom_ms"], 50),
                p95z=_percentile(r["zoom_ms"], 95),
                frame_p95=_percentile(intervals, 95),
                frames=r["frame_count"],
                setup=r["setup_ms"],
            )
        )
    lines.append("")

    lines.append("## Renderer and Feature Parity Diagnostics")
    lines.append("")
    lines.append(
        "| Label | Qt | QPA | Qt Quick | RHI | Override | Selection | Render loop | Host | Screen DPR | Window DPR | Feature parity |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---:|---:|---|")
    for r in results:
        renderer = r.get("renderer_diagnostics", {})
        feature_parity = r.get("feature_parity", {})
        lines.append(
            "| {label} | {qt} | {qpa} | {quick} | {rhi} | {override} | {selection} | {loop} | {host} | {screen:.3f} | {window:.3f} | {parity} |".format(
                label=r["label"],
                qt=renderer.get("qt_version", ""),
                qpa=renderer.get("qt_qpa_platform", ""),
                quick=renderer.get("qt_quick_backend", ""),
                rhi=renderer.get("qsg_rhi_backend", ""),
                override=renderer.get("qsg_rhi_backend_override", ""),
                selection=(
                    f"{renderer.get('qtquick_backend_selection_reason', '')}/"
                    f"{renderer.get('qtquick_backend_selected', '')}"
                ),
                loop=renderer.get("qsg_render_loop", ""),
                host=renderer.get("qml_host_kind", ""),
                screen=float(renderer.get("screen_device_pixel_ratio", 0.0)),
                window=float(renderer.get("window_effective_device_pixel_ratio", 0.0)),
                parity="PASS" if feature_parity.get("pass", False) else "FAIL",
            )
        )
    lines.append("")

    for result in results:
        operations = list(result.get("operations", []))
        if not operations:
            continue
        lines.append(f"## Engineering operations: {result['label']}")
        lines.append("")
        acceptance = dict(result.get("engineering_acceptance", {}))
        lines.append(
            "- Per-run diagnostic acceptance: "
            f"`{acceptance.get('status', 'NOT_EVALUATED')}`"
        )
        lines.append(
            "- Release readiness: "
            f"`{acceptance.get('release_ready', False)}` "
            f"(`{acceptance.get('release_status', 'NOT_EVALUATED')}`)"
        )
        for failure in acceptance.get("failures", []):
            lines.append(f"  - {failure}")
        lines.append("")
        lines.append(
            "| Operation | Status | p50 (ms) | p95 (ms) | Frame p95 (ms) | "
            "Widget before/after | Bind | Release | Render | Load | Full sync | "
            "Transform sync | Native move | Native resize | Native setGeometry |"
        )
        lines.append(
            "|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for operation in operations:
            delta = operation.get("lifecycle_deltas", {})
            before = operation.get("viewer_before", {})
            after = operation.get("viewer_after", {})
            lines.append(
                "| {name} | {status} | {p50:.2f} | {p95:.2f} | {frame:.2f} | "
                "{before}/{after} | {bind} | {release} | {render} | {load} | "
                "{full} | {transform} | {move} | {resize} | {set_geometry} |".format(
                    name=operation.get("operation", ""),
                    status=operation.get("status", ""),
                    p50=float(operation.get("timing_p50_ms", 0.0)),
                    p95=float(operation.get("timing_p95_ms", 0.0)),
                    frame=float(operation.get("frame_interval_p95_ms", 0.0)),
                    before=before.get("widget_identity", "") or "none",
                    after=after.get("widget_identity", "") or "none",
                    bind=delta.get("binder_bind", 0),
                    release=delta.get("binder_release", 0),
                    render=delta.get("binder_render", 0),
                    load=delta.get("dataset_load", 0),
                    full=delta.get("overlay_full_sync", 0),
                    transform=delta.get("overlay_transform_sync", 0),
                    move=delta.get("native_move_calls", 0),
                    resize=delta.get("native_resize_calls", 0),
                    set_geometry=delta.get("native_set_geometry_calls", 0),
                )
            )
        lines.append("")

    lines.append("## Steady-state vs spike frame analysis")
    lines.append("")
    lines.append(
        "Frames are split at 100 ms: anything below is treated as part of the "
        "in-interaction steady state, anything above is a *hitch*. Hitches in "
        "this codebase are dominated by the `interactionIdleTimer` (150 ms "
        "debounce) firing and tearing down the per-node `layer.enabled` "
        "texture cache, which forces a full rasterization on the next frame."
    )
    lines.append("")
    lines.append(
        "| Scenario | DPR | Frames | Steady median (ms) | Steady FPS | "
        "Steady p95 (ms) | Spike count | Spike median (ms) | Spike rate |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for r in results:
        intervals = r.get("frame_intervals_ms", [])
        steady = [iv for iv in intervals if iv < 100.0]
        spikes = [iv for iv in intervals if iv >= 100.0]
        steady_median = statistics.median(steady) if steady else 0.0
        steady_p95 = _percentile(steady, 95.0)
        spike_median = statistics.median(spikes) if spikes else 0.0
        spike_rate = (len(spikes) / len(intervals) * 100.0) if intervals else 0.0
        steady_fps = (1000.0 / steady_median) if steady_median > 0 else 0.0
        lines.append(
            f"| {r['label']} | {r.get('window_effective_dpr', '?')} | "
            f"{len(intervals)} | {steady_median:.1f} | {steady_fps:.0f} | "
            f"{steady_p95:.1f} | {len(spikes)} | {spike_median:.1f} | "
            f"{spike_rate:.0f}% |"
        )
    lines.append("")

    lines.append("## Python Hot Path (instrumented)")
    lines.append("")
    component_keys: list[str] = []
    for r in results:
        for k in r["instrumentation"].keys():
            if k not in component_keys:
                component_keys.append(k)
    header = ["scenario"] + component_keys
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for r in results:
        row = [r["label"]]
        for k in component_keys:
            stat = r["instrumentation"].get(k, {})
            calls = int(stat.get("call_count", 0))
            total = float(stat.get("total_ms", 0.0))
            row.append(f"{calls} calls / {total:.1f} ms")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## cProfile top functions per scenario (top 10)")
    lines.append("")
    for r in results:
        lines.append(f"### {r['label']}")
        lines.append("")
        lines.append("| Function | Calls | Cumulative (ms) | Self total (ms) |")
        lines.append("|---|---:|---:|---:|")
        for entry in r["top_functions"][:10]:
            lines.append(
                f"| `{entry['function']}` | {entry['call_count']} | "
                f"{entry['cumulative_ms']:.2f} | {entry['total_ms']:.2f} |"
            )
        lines.append("")

    if overlay_payload:
        lines.append("## EmbeddedViewerOverlayManager._sync_impl micro-benchmark")
        lines.append("")
        samples = overlay_payload.get("sync_impl_ms", [])
        if samples:
            metrics = overlay_payload.get("overlay_metrics", {})
            lines.append(
                f"- Samples: {len(samples)}  "
                f"DPR: {overlay_payload.get('screen_dpr', '?')}x  "
                f"Nodes: {overlay_payload.get('node_count', '?')}"
            )
            lines.append(
                f"- Mean: {statistics.fmean(samples):.3f} ms  "
                f"median: {statistics.median(samples):.3f} ms  "
                f"p95: {_percentile(samples, 95):.3f} ms  "
                f"max: {max(samples):.3f} ms"
            )
            lines.append(
                "- Last overlay metrics: "
                f"total={metrics.get('total_count', 0)}  "
                f"visible={metrics.get('visible_count', 0)}  "
                f"offscreen skipped={metrics.get('skipped_offscreen_count', 0)}  "
                f"geometry-only={metrics.get('geometry_only_updates', 0)}  "
                f"content={metrics.get('content_updates', 0)}"
            )
        else:
            lines.append("- (no samples recorded)")
        lines.append("")

    lines.append("## Charts")
    lines.append("")
    lines.append("- `01_pan_zoom_step_times.png` – pan/zoom step distribution per scenario")
    lines.append("- `02_frame_interval_histograms.png` – frame interval histogram per scenario")
    lines.append("- `03_python_component_stack.png` – instrumented Python time stack")
    lines.append("- `04_cprofile_top_functions.png` – cProfile top cumulative functions (heaviest scenario)")
    lines.append("- `05_dpr_ablation.png` – heavy_media native DPR vs forced 1x DPR")
    lines.append("- `06_overlay_sync_micro.png` – EmbeddedViewerOverlayManager._sync_impl distribution")
    lines.append("")

    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Canvas pan/zoom lag profiler")
    parser.add_argument(
        "--selection", action="store_true",
        help="Measure composed-shell canvas clicks and inspector lifecycle with isolated preferences.",
    )
    parser.add_argument(
        "--mode",
        choices=("orchestrate", "scenario", "overlay-sync"),
        default="orchestrate",
    )
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--nodes", type=int, default=200)
    parser.add_argument("--edges", type=int, default=320)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--zoom-min", type=float, default=0.5)
    parser.add_argument("--zoom-max", type=float, default=2.0)
    parser.add_argument("--scenario", choices=("synthetic_exec", "heavy_media", "project_fixture", "stress_fixture"))
    parser.add_argument(
        "--project-path",
        default="",
        help="Load this .cxproj project through the shared performance harness fixture path.",
    )
    parser.add_argument(
        "--workspace-id",
        default="",
        help="Workspace id to profile when --project-path or --stress-fixture is used.",
    )
    parser.add_argument(
        "--stress-fixture",
        choices=("real",),
        default="",
        help="Profile the canonical real stress-1200 fixture at examples/stress_1200_nodes.cxproj.",
    )
    parser.add_argument(
        "--engineering-step",
        default="",
        help="Run the production Panel -> CAD Import -> Model Viewer flow with this STEP file.",
    )
    parser.add_argument("--qt-platform", default="windows")
    parser.add_argument("--qml-host", choices=("qquickwidget", "qquickview_container"), default="")
    parser.add_argument(
        "--qsg-rhi-backend",
        choices=("auto", "d3d11", "d3d12", "opengl", "vulkan", "metal", "software"),
        default="",
    )
    parser.add_argument("--scale-factor", default="")
    parser.add_argument("--output-path", default="")
    parser.add_argument(
        "--skip-dpr-ablation",
        action="store_true",
        help="Skip the forced QT_SCALE_FACTOR=1 sub-run.",
    )
    parser.add_argument(
        "--skip-overlay-micro",
        action="store_true",
        help="Skip the overlay sync micro-benchmark.",
    )
    parser.add_argument(
        "--capture-qsg-info",
        action="store_true",
        help="Set QSG_INFO=1 in profile subprocesses and capture Qt scene graph diagnostics in logs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.capture_qsg_info:
        os.environ["QSG_INFO"] = "1"
    if args.selection:
        from scripts.canvas_selection_profile import run_selection_profile

        return run_selection_profile(args)
    if args.mode == "scenario":
        if not args.scenario:
            sys.stderr.write("--scenario required in scenario mode\n")
            return 2
        return _run_subprocess_scenario(args)
    if args.mode == "overlay-sync":
        return _run_overlay_sync_micro(args)
    return _orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
