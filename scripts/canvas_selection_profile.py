"""Composed-shell pointer-to-frame selection profiling for profile_canvas_lag."""
# Purpose: Measure real canvas selection with the production inspector and isolated shell state.
# Map: docs/agent_maps/feature_routes/performance_harness_graph_stress.md
# Tests: tests/main_window_shell/passive_property_editors.py
from __future__ import annotations

import json
import math
import os
import statistics
import time
from pathlib import Path


def run_selection_profile(args) -> int:
    # Reuse the shell test fixture's temporary preference/session paths and inert
    # execution client. Selection, QML, presenters and rendering remain production.
    from tests.main_window_shell.base import MainWindowShellTestBase

    os.environ["QT_QPA_PLATFORM"] = args.qt_platform
    if args.qml_host:
        os.environ["EA_NODE_EDITOR_QML_HOST"] = args.qml_host
    if args.qsg_rhi_backend:
        os.environ["EA_NODE_EDITOR_QSG_RHI_BACKEND"] = args.qsg_rhi_backend
    if args.scale_factor:
        os.environ["QT_SCALE_FACTOR"] = args.scale_factor

    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtTest import QTest

    from ea_node_editor.ui_qml.qtquick_backend import configure_qtquick_backend, graphics_api_name

    configure_qtquick_backend()
    case = MainWindowShellTestBase()
    case.setUp()
    started = time.perf_counter()
    pending: dict = {}
    profiles = []
    try:
        shell, app = case.window, case.app
        shell.resize(1500, 900)
        pane = case._find_qml_item("inspectorPane")
        canvas = case._graph_canvas_item()
        quick_window = case._qml_host().quick_window()
        input_surface = case._qml_input_widget()
        ids = {
            kind: shell.scene.create_node_from_type(
                type_id=kind, x=index * 340, y=0, parent_node_id=None, select_node=False,
            )
            for index, kind in enumerate(("core.constant", "plot.signal", "media.panel"))
        }
        canvas.property("viewBridge").set_view_state(0.7, 450, 150)
        QTest.qWait(300)
        cards = {node_id: case._graph_node_card(node_id) for node_id in ids.values()}

        def before_sync():
            if pending and not pending.get("frame_at"):
                pending["synced"] = all(
                    bool(card.property("isSelected")) == (node_id == pending["expected"])
                    for node_id, card in cards.items()
                )

        def after_render():
            if pending.get("synced") and not pending.get("frame_at"):
                pending["frame_at"] = time.perf_counter()

        quick_window.beforeSynchronizing.connect(before_sync, Qt.ConnectionType.DirectConnection)
        quick_window.afterRendering.connect(after_render, Qt.ConnectionType.DirectConnection)

        def click(expected):
            if expected:
                card = cards[expected]
                point = card.mapToScene(QPointF(card.width() * 0.5, 12)).toPoint()
            else:
                point = canvas.mapToScene(QPointF(40, 40)).toPoint()
            QTest.mouseMove(input_surface, point, 0)
            app.processEvents()
            pending.clear()
            pending.update(expected=expected, synced=False)
            start = time.perf_counter()
            QTest.mouseClick(input_surface, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point, 0)
            dispatch_end = time.perf_counter()
            if (shell.scene.selected_node_id() or "") != expected:
                raise AssertionError(f"Physical click at {point} selected {shell.scene.selected_node_id()!r}, expected {expected!r}; canvas={canvas.width()}x{canvas.height()}")
            quick_window.update()
            case._qml_host().container_widget.update()
            while not pending.get("frame_at"):
                if time.perf_counter() - start > 5:
                    raise TimeoutError("No rendered frame with the requested selection")
                app.processEvents()
                QTest.qWait(1)
            sample = {
                "dispatch_ms": (dispatch_end - start) * 1000,
                "click_to_frame_ms": (pending["frame_at"] - start) * 1000,
            }
            pending.clear()
            return sample

        operations = (
            ("select_signal", ids["plot.signal"]),
            ("switch_to_constant", ids["core.constant"]),
            ("switch_to_signal", ids["plot.signal"]),
            ("clear_signal", ""),
            ("select_media", ids["media.panel"]),
            ("clear_media", ""),
        )
        for variant in ("collapsed", "smart_groups", "accordion_cards", "palette"):
            pane.setProperty("paneCollapsed", variant == "collapsed")
            shell.shell_inspector_presenter.set_property_pane_variant(
                "smart_groups" if variant == "collapsed" else variant
            )
            QTest.qWait(300)
            samples = {name: [] for name, _ in operations}
            clear_object_counts = []
            for iteration in range(max(0, args.warmup) + max(1, args.samples)):
                for name, node_id in operations:
                    sample = click(node_id)
                    if iteration >= args.warmup:
                        samples[name].append(sample)
                app.processEvents()
                clear_object_counts.append(sum(1 for _ in case._walk_items(pane)))
            summaries = {}
            for name, rows in samples.items():
                summaries[name] = {}
                for metric in ("dispatch_ms", "click_to_frame_ms"):
                    values = sorted(row[metric] for row in rows)
                    summaries[name][metric] = {
                        "p50": statistics.median(values),
                        "p95": values[math.ceil(len(values) * 0.95) - 1],
                        "max": max(values),
                    }
            profiles.append({
                "variant": variant, "samples": samples, "summary": summaries,
                "cleared_inspector_visual_counts": clear_object_counts,
            })
            print(json.dumps({
                "variant": variant,
                "click_to_frame_p95_ms": {
                    name: round(summary["click_to_frame_ms"]["p95"], 2)
                    for name, summary in summaries.items()
                },
            }), flush=True)
        quick_window.beforeSynchronizing.disconnect(before_sync)
        quick_window.afterRendering.disconnect(after_render)
        renderer = graphics_api_name(quick_window)
        qualified = args.qt_platform == "windows" and renderer == "Direct3D11Rhi"
        latency_passed = all(
            summary["click_to_frame_ms"]["p95"] < 100
            for profile in profiles for summary in profile["summary"].values()
        )
        report = {
            "scenario": "composed_shell_selection", "renderer": renderer,
            "qt_platform": args.qt_platform, "qml_host": case._qml_host().host_kind,
            "screen_dpr": quick_window.devicePixelRatio(),
            "samples_per_operation": max(1, args.samples), "warmup_cycles": max(0, args.warmup),
            "execution_client": "isolated_inert", "readback_in_timing": False,
            "render_boundary": "QQuickWindow.afterRendering after confirmed QML selection synchronization",
            "excludes": ["widget_composition", "gpu_completion", "display_presentation"],
            "display_gate_applicable": qualified, "latency_gate_ms": 100,
            "latency_gate_passed": latency_passed if qualified else None,
            "elapsed_seconds": time.perf_counter() - started, "profiles": profiles,
        }
        if args.output_path:
            output = Path(args.output_path).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({key: value for key, value in report.items() if key != "profiles"}), flush=True)
        return 0 if not qualified or latency_passed else 1
    finally:
        pending.clear()
        case.tearDown()
