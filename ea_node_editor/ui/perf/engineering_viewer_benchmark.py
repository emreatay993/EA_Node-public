# Purpose: Display-attached performance acceptance for the neutral CAD/FE viewer binder.
# Map: feature_routes/performance_harness_graph_stress
# Tests: tests/test_engineering_viewer_performance.py
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path
from typing import Any


THRESHOLDS = {
    "interaction_frame_p95_ms": 33.0,
    "detail_restore_ms": 500.0,
    "warm_coarse_frame_ms": 5000.0,
    "ui_thread_stall_max_ms": 100.0,
}


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered) + 0.999999) - 1))
    return ordered[index]


def evaluate_metrics(
    metrics: dict[str, Any],
    *,
    display_attached: bool,
    graphics_api: str,
) -> dict[str, Any]:
    checks = {
        key: {
            "value": float(metrics.get(key, float("inf"))),
            "maximum": maximum,
            "pass": float(metrics.get(key, float("inf"))) <= maximum,
        }
        for key, maximum in THRESHOLDS.items()
    }
    checks["released_on_close"] = {
        "value": bool(metrics.get("released_on_close", False)),
        "expected": True,
        "pass": bool(metrics.get("released_on_close", False)),
    }
    native_gate = bool(
        display_attached
        and platform.system() == "Windows"
        and "direct3d11" in str(graphics_api).replace("_", "").casefold()
    )
    return {
        "status": "PASS" if native_gate and all(item["pass"] for item in checks.values()) else "FAIL",
        "acceptance_allowed": native_gate,
        "checks": checks,
        "note": (
            "Native Windows/D3D11 acceptance run."
            if native_gate
            else "Regression evidence only; acceptance requires display-attached Windows with Qt Quick D3D11."
        ),
    }


def _write_reports(report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "engineering_viewer_benchmark.json"
    markdown_path = report_dir / "ENGINEERING_VIEWER_BENCHMARK.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Model Viewer Performance Report",
        "",
        f"- Status: `{report['acceptance']['status']}`",
        f"- Acceptance allowed: `{report['acceptance']['acceptance_allowed']}`",
        f"- Qt platform: `{report['environment']['qt_platform']}`",
        f"- Qt Quick graphics API: `{report['environment']['graphics_api']}`",
        f"- Primary cells: `{report['fixtures']['primary_cells']}`",
        f"- Overlay cells: `{report['fixtures']['overlay_cells']}`",
        "",
        "| Metric | Value | Maximum | Pass |",
        "|---|---:|---:|:---:|",
    ]
    for name, check in report["acceptance"]["checks"].items():
        lines.append(
            f"| `{name}` | {check['value']} | {check.get('maximum', check.get('expected', ''))} | "
            f"{'yes' if check['pass'] else 'no'} |"
        )
    lines.extend(("", report["acceptance"]["note"], ""))
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def _generate_fixtures(fixture_dir: Path, resolution: int) -> dict[str, Any]:
    import numpy as np
    import pyvista as pv

    fixture_dir.mkdir(parents=True, exist_ok=True)
    primary = pv.Plane(i_resolution=resolution, j_resolution=resolution).triangulate()
    primary.point_data["displacement"] = np.linalg.norm(primary.points, axis=1)
    primary_full = primary.cast_to_unstructured_grid()
    primary_coarse = primary.decimate(0.9).cast_to_unstructured_grid()
    overlay = pv.Sphere(
        radius=0.35,
        center=(0.0, 0.0, 0.05),
        theta_resolution=max(48, resolution // 2),
        phi_resolution=max(48, resolution // 2),
    ).triangulate()
    primary_path = fixture_dir / "generated_fe_full.vtu"
    interaction_path = fixture_dir / "generated_fe_interaction.vtu"
    overlay_path = fixture_dir / "generated_cad_overlay.stl"
    primary_full.save(primary_path)
    primary_coarse.save(interaction_path)
    overlay.save(overlay_path)
    return {
        "primary_path": str(primary_path.resolve()),
        "interaction_path": str(interaction_path.resolve()),
        "overlay_path": str(overlay_path.resolve()),
        "primary_cells": int(primary_full.n_cells),
        "interaction_cells": int(primary_coarse.n_cells),
        "overlay_cells": int(overlay.n_cells),
    }


def run_benchmark(
    *,
    report_dir: Path,
    resolution: int = 220,
    interaction_samples: int = 30,
    qt_platform: str = "windows",
    qsg_backend: str = "d3d11",
) -> dict[str, Any]:
    os.environ["QT_QPA_PLATFORM"] = str(qt_platform)
    os.environ["EA_NODE_EDITOR_QSG_RHI_BACKEND"] = str(qsg_backend)

    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtQuick import QQuickWindow
    from PyQt6.QtWidgets import QApplication, QWidget

    from ea_node_editor.common.scene_protocol import ENGINEERING_VIEWER_BACKEND_ID
    from ea_node_editor.execution.viewer_backend_engineering import (
        ENGINEERING_VIEWER_TRANSPORT_KIND,
        ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
    )
    from ea_node_editor.ui_qml.engineering_viewer_widget_binder import (
        EngineeringViewerWidgetBinder,
    )
    from ea_node_editor.ui_qml.qtquick_backend import configure_qtquick_backend
    from ea_node_editor.ui_qml.viewer_widget_binder import (
        ViewerWidgetBindRequest,
        ViewerWidgetNoBind,
        ViewerWidgetReleaseRequest,
    )

    configure_qtquick_backend()
    app = QApplication.instance() or QApplication([])
    quick_window = QQuickWindow()
    quick_window.resize(64, 64)
    quick_window.show()
    app.processEvents()
    graphics_api = QQuickWindow.graphicsApi().name
    display_attached = str(qt_platform).casefold() not in {"offscreen", "minimal"}

    fixtures = _generate_fixtures(report_dir / "fixtures", int(resolution))
    transport = {
        "kind": ENGINEERING_VIEWER_TRANSPORT_KIND,
        "schema": ENGINEERING_VIEWER_TRANSPORT_SCHEMA,
        "status": "ready",
        "primary": {
            "role": "primary",
            "name": "Generated FE",
            "display_path": fixtures["primary_path"],
            "interaction_display_path": fixtures["interaction_path"],
            "visible": True,
            "scale_factor": 1.0,
            "length_unit": "m",
            "style": {"representation": "surface", "show_edges": False, "opacity": 1.0},
        },
        "overlays": [
            {
                "role": "overlay",
                "name": "Generated CAD",
                "display_path": fixtures["overlay_path"],
                "visible": True,
                "scale_factor": 1.0,
                "length_unit": "m",
                "style": {"representation": "surface", "color": "#ff9f43", "opacity": 0.35},
            }
        ],
    }
    container = QWidget()
    container.resize(1280, 800)
    container.show()
    app.processEvents()

    request = ViewerWidgetBindRequest(
        workspace_id="benchmark",
        node_id="engineering_viewer",
        session_id="engineering_viewer_benchmark",
        backend_id=ENGINEERING_VIEWER_BACKEND_ID,
        transport_revision=1,
        live_mode="full",
        cache_state="live_ready",
        live_open_status="ready",
        transport=transport,
        summary={"scene_fingerprint": "0" * 64},
        options={"viewer_background": "gray", "representation": "surface"},
        container=container,
    )
    binder = EngineeringViewerWidgetBinder(background_loading=True)
    start = time.perf_counter()
    previous_tick = start
    stalls: list[float] = []
    widget = None
    deadline = start + 30.0
    while time.perf_counter() < deadline:
        try:
            widget = binder.bind_widget(request)
            break
        except ViewerWidgetNoBind as exc:
            if not bool(getattr(exc, "retry_when_ready", False)):
                raise
        app.processEvents()
        now = time.perf_counter()
        stalls.append((now - previous_tick) * 1000.0)
        previous_tick = now
        time.sleep(0.001)
    if widget is None:
        raise TimeoutError("Model viewer did not produce a warm frame within 30 seconds.")
    warm_frame_ms = (time.perf_counter() - start) * 1000.0

    camera = widget.renderer.GetActiveCamera()
    frame_samples: list[float] = []
    for _index in range(max(1, int(interaction_samples))):
        frame_start = time.perf_counter()
        camera.Azimuth(2.0)
        camera.Elevation(0.5)
        widget.render()
        app.processEvents()
        frame_samples.append((time.perf_counter() - frame_start) * 1000.0)

    interactor = getattr(widget, "iren", None) or getattr(widget, "interactor", None)
    invoke = getattr(interactor, "invoke_event", None) or getattr(interactor, "InvokeEvent", None)
    restore_start = time.perf_counter()
    if callable(invoke):
        invoke("StartInteractionEvent")
        invoke("EndInteractionEvent")
    restore_deadline = restore_start + 0.18
    while time.perf_counter() < restore_deadline:
        app.processEvents()
        time.sleep(0.001)
    detail_restore_ms = (time.perf_counter() - restore_start) * 1000.0

    binder.release_widget(
        ViewerWidgetReleaseRequest(
            workspace_id=request.workspace_id,
            node_id=request.node_id,
            session_id=request.session_id,
            backend_id=request.backend_id,
            transport_revision=request.transport_revision,
            container=container,
            widget=widget,
            reason="benchmark_close",
        )
    )
    released = binder.render_stats(widget).get("dataset_count", 0) == 0
    binder.shutdown()
    metrics = {
        "interaction_frame_p95_ms": _percentile_95(frame_samples),
        "interaction_frame_mean_ms": statistics.fmean(frame_samples),
        "detail_restore_ms": detail_restore_ms,
        "warm_coarse_frame_ms": warm_frame_ms,
        "ui_thread_stall_max_ms": max(stalls, default=0.0),
        "released_on_close": released,
    }
    report = {
        "schema": "corex.engineering_viewer_benchmark.v1",
        "environment": {
            "platform": platform.platform(),
            "qt_platform": str(qt_platform),
            "graphics_api": str(graphics_api),
            "qsg_backend_request": str(qsg_backend),
            "display_attached": display_attached,
        },
        "fixtures": fixtures,
        "metrics": metrics,
        "acceptance": evaluate_metrics(
            metrics,
            display_attached=display_attached,
            graphics_api=graphics_api,
        ),
    }
    quick_window.close()
    container.close()
    QCoreApplication.processEvents()
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="COREX neutral Model Viewer performance gate.")
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts/engineering_viewer_benchmark"))
    parser.add_argument("--resolution", type=int, default=220)
    parser.add_argument("--interaction-samples", type=int, default=30)
    parser.add_argument("--qt-platform", default="windows")
    parser.add_argument("--qsg-rhi-backend", default="d3d11")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_benchmark(
        report_dir=args.report_dir,
        resolution=max(24, int(args.resolution)),
        interaction_samples=max(1, int(args.interaction_samples)),
        qt_platform=args.qt_platform,
        qsg_backend=args.qsg_rhi_backend,
    )
    json_path, markdown_path = _write_reports(report, args.report_dir)
    print(f"Model viewer report written: {markdown_path}")
    print(f"Model viewer data written:   {json_path}")
    print(f"status={report['acceptance']['status']}")
    return 0 if report["acceptance"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
