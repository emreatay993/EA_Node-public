"""Tabular/plot workflow performance harness for EA Node Editor.

Boots the real shell window in a subprocess, opens a given ``.cxproj``, and
drives the interactions that the gigabyte-tabular plan budgets:

* full scene payload rebuilds (the cost behind every canvas interaction),
* node-move position deltas (drag steady state),
* content fullscreen open/close for the tabular and plot nodes,
* project save / reload,
* workflow run end-to-end.

It records wall-clock timings, the scene mutation-timing phases
(``payload_rebuild_ms`` / ``scene_publish_ms``), and counts of tabular source
I/O calls (``scan_source`` / ``open_source`` / window reads) per phase so
"zero file I/O on rebuild" claims are checkable. Results land in
``artifacts/perf/<label>.json``.

Usage
-----
    venv\\Scripts\\python.exe scripts\\verify_tabular_perf.py --project plotting_benchmark.cxproj --label baseline_small
    venv\\Scripts\\python.exe scripts\\verify_tabular_perf.py --project plotting_benchmark.cxproj --budgets budgets.json

Budgets file: JSON mapping of metric name -> max value, e.g.
    {"fullscreen_tabular_open_warm_p50_ms": 250, "node_move_wall_p50_ms": 10,
     "save_ms": 200, "load_ms": 1000, "run_ms": 2000,
     "node_move_scan_source_calls": 0}
Breaching any budget makes the harness exit non-zero.

The child process sets ``QT_QUICK_CONTROLS_STYLE=Basic`` (required for
scripted MainShell drivers) and quits itself when done; ``EA_PROFILE_AUTOQUIT``
is intentionally NOT used because the harness owns the app lifetime.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PERF_DIR = REPO_ROOT / "artifacts" / "perf"
CHILD_TIMEOUT_S = 5400

from ea_node_editor.nodes.builtins.plot.generic import PLOT_NODE_DEFINITION_BY_TYPE_ID


def _benchmark_node_ids(nodes: dict[str, Any]) -> tuple[str, str]:
    tabular_node_id = ""
    plot_node_id = ""
    for node_id, node in nodes.items():
        type_id = str(getattr(node, "type_id", "") or "")
        if type_id == "tabular.input" and not tabular_node_id:
            tabular_node_id = node_id
        elif type_id in PLOT_NODE_DEFINITION_BY_TYPE_ID and not plot_node_id:
            plot_node_id = node_id
    return tabular_node_id, plot_node_id


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


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "p50_ms": _percentile(values, 50.0),
        "p95_ms": _percentile(values, 95.0),
        "mean_ms": statistics.fmean(values) if values else 0.0,
        "max_ms": max(values, default=0.0),
    }


# ---------------------------------------------------------------------------
# Child process: boots the shell and drives the scenario.
# ---------------------------------------------------------------------------


class _TabularIoCounters:
    """Phase-scoped counters on the tabular loader service entry points."""

    METHODS = ("scan_source", "open_source", "window", "preview_window", "arrow_batches")

    def __init__(self) -> None:
        self.totals: dict[str, int] = {name: 0 for name in self.METHODS}
        self._phase_counts: dict[str, dict[str, int]] = {}
        self._active_phase: str | None = None

    def install(self) -> None:
        from ea_node_editor.addons.tabular_data import loader_cache_service as module

        service_cls = module.TabularLoaderCacheService
        counters = self

        def _wrap(method_name: str):
            original = getattr(service_cls, method_name)

            def _counted(self, *args, **kwargs):  # noqa: ANN001
                counters._record(method_name)
                return original(self, *args, **kwargs)

            _counted.__name__ = original.__name__
            _counted.__wrapped__ = original  # type: ignore[attr-defined]
            return _counted

        for name in self.METHODS:
            setattr(service_cls, name, _wrap(name))

    def _record(self, method_name: str) -> None:
        self.totals[method_name] += 1
        if self._active_phase is not None:
            phase = self._phase_counts.setdefault(self._active_phase, {})
            phase[method_name] = phase.get(method_name, 0) + 1

    def phase(self, name: str) -> "_PhaseScope":
        return _PhaseScope(self, name)

    def phase_counts(self, name: str) -> dict[str, int]:
        return dict(self._phase_counts.get(name, {}))

    def snapshot(self) -> dict[str, Any]:
        return {"totals": dict(self.totals), "phases": {k: dict(v) for k, v in self._phase_counts.items()}}


class _PhaseScope:
    def __init__(self, counters: _TabularIoCounters, name: str) -> None:
        self._counters = counters
        self._name = name
        self._previous: str | None = None

    def __enter__(self) -> "_PhaseScope":
        self._previous = self._counters._active_phase
        self._counters._active_phase = self._name
        return self

    def __exit__(self, *_exc: object) -> None:
        self._counters._active_phase = self._previous


def _run_child(args: argparse.Namespace) -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    from PyQt6.QtWidgets import QApplication

    from ea_node_editor.app import prepare_qt_application_attributes
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.ui.shell.composition import create_shell_window

    counters = _TabularIoCounters()
    counters.install()

    report: dict[str, Any] = {
        "schema": "tabular_perf_report_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": str(args.project),
        "label": args.label,
        "qt_quick_controls_style": os.environ.get("QT_QUICK_CONTROLS_STYLE", ""),
        "errors": [],
    }

    prepare_qt_application_attributes()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    def checkpoint(phase: str) -> None:
        # Persist partial results after every phase so a watchdog kill still
        # leaves measured data behind, and log progress unbuffered.
        Path(args.output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[verify_tabular_perf] phase done: {phase}", flush=True)

    def pump(duration_ms: int = 0) -> None:
        deadline = time.perf_counter() + duration_ms / 1000.0
        app.processEvents()
        while time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.001)

    window = None
    exit_code = 0
    try:
        t0 = time.perf_counter()
        registry = build_default_registry()
        report["registry_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        window = create_shell_window(registry=registry)
        window.show()
        pump(250)
        report["boot_ms"] = (time.perf_counter() - t0) * 1000.0

        # ---- load -------------------------------------------------------
        with counters.phase("load"):
            t0 = time.perf_counter()
            opened = window.project_session_controller.open_project_path(args.project, show_errors=False)
            pump(100)
            report["load_ms"] = (time.perf_counter() - t0) * 1000.0
        if not opened:
            report["errors"].append("open_project_path returned False")
            raise SystemExit(3)
        report["load_io"] = counters.phase_counts("load")
        checkpoint("load")

        workspace_id = window.model.project.active_workspace_id
        workspace = window.model.project.workspaces[workspace_id]
        tabular_node_id, plot_node_id = _benchmark_node_ids(workspace.nodes)
        report["workspace_id"] = workspace_id
        report["tabular_node_id"] = tabular_node_id
        report["plot_node_id"] = plot_node_id
        report["node_count"] = len(workspace.nodes)

        scene = window.scene
        scene_context = scene._scene_context
        pump(200)  # settle initial publishes before measuring

        def timing_samples_phases() -> dict[str, list[float]]:
            phases: dict[str, list[float]] = {}
            for sample in scene.mutation_timing_samples():
                for phase_name, elapsed in (sample.get("phase_timings_ms") or {}).items():
                    phases.setdefault(phase_name, []).append(float(elapsed))
            return phases

        # ---- full scene rebuilds -----------------------------------------
        scene.set_mutation_timing_enabled(True)
        scene.clear_mutation_timing_samples()
        rebuild_wall: list[float] = []
        with counters.phase("full_rebuild"):
            for _ in range(args.rebuilds):
                t0 = time.perf_counter()
                scene_context.rebuild_models()
                app.processEvents()
                rebuild_wall.append((time.perf_counter() - t0) * 1000.0)
        rebuild_phases = timing_samples_phases()
        report["full_rebuild"] = {
            "wall": _summary(rebuild_wall),
            "payload_rebuild": _summary(rebuild_phases.get("payload_rebuild_ms", [])),
            "scene_publish": _summary(rebuild_phases.get("scene_publish_ms", [])),
            "io": counters.phase_counts("full_rebuild"),
        }
        checkpoint("full_rebuild")

        # ---- node moves (drag steady state) ------------------------------
        scene.clear_mutation_timing_samples()
        move_wall: list[float] = []
        move_node_id = plot_node_id or tabular_node_id
        node = workspace.nodes.get(move_node_id)
        with counters.phase("node_move"):
            for index in range(args.moves):
                if node is not None:
                    node.x = float(node.x) + (1.0 if index % 2 == 0 else -1.0)
                t0 = time.perf_counter()
                scene_context.publish_node_position_delta([move_node_id])
                app.processEvents()
                move_wall.append((time.perf_counter() - t0) * 1000.0)
        move_phases = timing_samples_phases()
        report["node_move"] = {
            "wall": _summary(move_wall),
            "payload_rebuild": _summary(move_phases.get("payload_rebuild_ms", [])),
            "scene_publish": _summary(move_phases.get("scene_publish_ms", [])),
            "io": counters.phase_counts("node_move"),
        }
        scene.set_mutation_timing_enabled(False)
        checkpoint("node_move")

        # ---- content fullscreen open/close -------------------------------
        bridge = window.content_fullscreen_bridge
        for kind, node_id in (("tabular", tabular_node_id), ("plot", plot_node_id)):
            if not node_id:
                continue
            open_ms: list[float] = []
            close_ms: list[float] = []
            with counters.phase(f"fullscreen_{kind}"):
                for _ in range(args.iterations):
                    t0 = time.perf_counter()
                    opened_fullscreen = bridge.request_open_node(node_id)
                    pump(50)
                    open_ms.append((time.perf_counter() - t0) * 1000.0)
                    if not opened_fullscreen:
                        report["errors"].append(f"request_open_node({kind}) returned False")
                        break
                    t0 = time.perf_counter()
                    bridge.request_close()
                    pump(50)
                    close_ms.append((time.perf_counter() - t0) * 1000.0)
            report[f"fullscreen_{kind}"] = {
                "open_cold_ms": open_ms[0] if open_ms else 0.0,
                "open_warm": _summary(open_ms[1:]),
                "close": _summary(close_ms),
                "io": counters.phase_counts(f"fullscreen_{kind}"),
            }
            checkpoint(f"fullscreen_{kind}")

        # ---- fullscreen paging + query (tabular) --------------------------
        if tabular_node_id:
            with counters.phase("fullscreen_paging"):
                bridge.request_open_node(tabular_node_id)
                pump(50)
                paging: dict[str, Any] = {}

                def timed_window(label: str, request: dict[str, Any]) -> None:
                    t0 = time.perf_counter()
                    payload = bridge.request_tabular_window(request)
                    paging[f"{label}_ms"] = (time.perf_counter() - t0) * 1000.0
                    paging[f"{label}_state"] = str(payload.get("state", ""))
                    window_payload = payload.get("window") if isinstance(payload, dict) else {}
                    if isinstance(window_payload, dict):
                        paging[f"{label}_total_rows"] = window_payload.get("total_rows")

                timed_window("page_next", {"row_offset": 60, "row_limit": 50, "column_limit": 50})
                first = bridge.request_tabular_window({"row_offset": 0, "row_limit": 1, "column_limit": 50})
                total_rows = 0
                if isinstance(first, dict):
                    window_payload = first.get("window")
                    if isinstance(window_payload, dict):
                        total_rows = int(window_payload.get("total_rows") or 0)
                if total_rows > 200:
                    timed_window(
                        "page_deep",
                        {"row_offset": max(0, total_rows - 100), "row_limit": 50, "column_limit": 50},
                    )
                # Sort by the first column name if known.
                columns = []
                if isinstance(first, dict):
                    window_payload = first.get("window")
                    if isinstance(window_payload, dict):
                        columns = list(window_payload.get("columns") or [])
                if columns:
                    timed_window(
                        "query_sort_first_column",
                        {"row_offset": 0, "row_limit": 50, "column_limit": 50,
                         "sort": {"column": str(columns[0]), "descending": True}},
                    )
                    # Interactive steady state: the query-table cache is warm.
                    timed_window(
                        "query_sort_repeat",
                        {"row_offset": 0, "row_limit": 50, "column_limit": 50,
                         "sort": {"column": str(columns[0]), "descending": False}},
                    )
                    timed_window(
                        "query_search",
                        {"row_offset": 0, "row_limit": 50, "column_limit": 50, "search": "1"},
                    )
                    timed_window(
                        "query_search_repeat",
                        {"row_offset": 0, "row_limit": 50, "column_limit": 50, "search": "42"},
                    )
                bridge.request_close()
                pump(50)
                report["fullscreen_paging"] = paging
        checkpoint("fullscreen_paging")

        # ---- save ---------------------------------------------------------
        with counters.phase("save"):
            t0 = time.perf_counter()
            window.project_session_controller.save_project()
            pump(50)
            report["save_ms"] = (time.perf_counter() - t0) * 1000.0
        try:
            report["saved_project_bytes"] = Path(window.project_path).stat().st_size
        except OSError:
            report["saved_project_bytes"] = -1
        checkpoint("save")

        # ---- reload --------------------------------------------------------
        with counters.phase("reload"):
            t0 = time.perf_counter()
            window.project_session_controller.open_project_path(args.project, show_errors=False)
            pump(100)
            report["reload_ms"] = (time.perf_counter() - t0) * 1000.0
        checkpoint("reload")

        # ---- run -----------------------------------------------------------
        if not args.skip_run:
            with counters.phase("run"):
                t0 = time.perf_counter()
                window.run_controller.run_workflow()
                deadline = time.perf_counter() + args.run_timeout
                while time.perf_counter() < deadline:
                    app.processEvents()
                    if not window.run_state.active_run_id:
                        break
                    time.sleep(0.005)
                else:
                    report["errors"].append("run timed out")
                report["run_ms"] = (time.perf_counter() - t0) * 1000.0
                report["run_engine_state"] = str(getattr(window.run_state, "engine_state_value", ""))
            checkpoint("run")

        report["io_counters"] = counters.snapshot()
    except SystemExit as exc:
        exit_code = int(exc.code or 1)
    except Exception as exc:  # noqa: BLE001
        import traceback

        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
        exit_code = 4
    finally:
        Path(args.output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        if window is not None:
            try:
                window.close()
            except Exception:  # noqa: BLE001
                pass
        app.processEvents()
    return exit_code


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _fullscreen_paging_metric(report: dict[str, Any], metric: str) -> Any:
    return report.get("fullscreen_paging", {}).get(metric)


def _fullscreen_paging_state_not_ready(report: dict[str, Any], label: str) -> float | None:
    state = report.get("fullscreen_paging", {}).get(f"{label}_state")
    if state is None:
        return None
    return 0.0 if str(state) == "ready" else 1.0


_BUDGET_EXTRACTORS: dict[str, Any] = {
    "load_ms": lambda r: r.get("load_ms"),
    "reload_ms": lambda r: r.get("reload_ms"),
    "save_ms": lambda r: r.get("save_ms"),
    "run_ms": lambda r: r.get("run_ms"),
    "saved_project_bytes": lambda r: r.get("saved_project_bytes"),
    "boot_ms": lambda r: r.get("boot_ms"),
    "full_rebuild_wall_p50_ms": lambda r: r.get("full_rebuild", {}).get("wall", {}).get("p50_ms"),
    "full_rebuild_payload_p50_ms": lambda r: r.get("full_rebuild", {}).get("payload_rebuild", {}).get("p50_ms"),
    "node_move_wall_p50_ms": lambda r: r.get("node_move", {}).get("wall", {}).get("p50_ms"),
    "node_move_payload_p50_ms": lambda r: r.get("node_move", {}).get("payload_rebuild", {}).get("p50_ms"),
    "node_move_scan_source_calls": lambda r: r.get("node_move", {}).get("io", {}).get("scan_source", 0),
    "full_rebuild_scan_source_calls": lambda r: r.get("full_rebuild", {}).get("io", {}).get("scan_source", 0),
    "fullscreen_tabular_open_cold_ms": lambda r: r.get("fullscreen_tabular", {}).get("open_cold_ms"),
    "fullscreen_tabular_open_warm_p50_ms": lambda r: r.get("fullscreen_tabular", {}).get("open_warm", {}).get("p50_ms"),
    "fullscreen_tabular_close_p50_ms": lambda r: r.get("fullscreen_tabular", {}).get("close", {}).get("p50_ms"),
    "fullscreen_plot_open_cold_ms": lambda r: r.get("fullscreen_plot", {}).get("open_cold_ms"),
    "fullscreen_plot_open_warm_p50_ms": lambda r: r.get("fullscreen_plot", {}).get("open_warm", {}).get("p50_ms"),
    "fullscreen_plot_close_p50_ms": lambda r: r.get("fullscreen_plot", {}).get("close", {}).get("p50_ms"),
    "fullscreen_page_next_ms": lambda r: _fullscreen_paging_metric(r, "page_next_ms"),
    "fullscreen_page_deep_ms": lambda r: _fullscreen_paging_metric(r, "page_deep_ms"),
    "fullscreen_query_sort_first_column_ms": lambda r: _fullscreen_paging_metric(r, "query_sort_first_column_ms"),
    "fullscreen_query_sort_repeat_ms": lambda r: _fullscreen_paging_metric(r, "query_sort_repeat_ms"),
    "fullscreen_query_search_ms": lambda r: _fullscreen_paging_metric(r, "query_search_ms"),
    "fullscreen_query_search_repeat_ms": lambda r: _fullscreen_paging_metric(r, "query_search_repeat_ms"),
    "fullscreen_page_next_state_not_ready": lambda r: _fullscreen_paging_state_not_ready(r, "page_next"),
    "fullscreen_page_deep_state_not_ready": lambda r: _fullscreen_paging_state_not_ready(r, "page_deep"),
    "fullscreen_query_sort_first_column_state_not_ready": (
        lambda r: _fullscreen_paging_state_not_ready(r, "query_sort_first_column")
    ),
    "fullscreen_query_search_state_not_ready": lambda r: _fullscreen_paging_state_not_ready(r, "query_search"),
}


def _check_budgets(report: dict[str, Any], budgets: dict[str, float]) -> list[str]:
    breaches: list[str] = []
    for metric, limit in budgets.items():
        extractor = _BUDGET_EXTRACTORS.get(metric)
        if extractor is None:
            breaches.append(f"unknown budget metric: {metric}")
            continue
        value = extractor(report)
        if value is None:
            breaches.append(f"{metric}: missing from report (budget {limit})")
            continue
        if float(value) > float(limit):
            breaches.append(f"{metric}: {float(value):.2f} > budget {float(limit):.2f}")
    return breaches


def _print_summary(report: dict[str, Any]) -> None:
    def fmt(value: Any) -> str:
        return f"{value:.1f}" if isinstance(value, (int, float)) else str(value)

    print(f"label: {report.get('label')}  project: {report.get('project')}")
    print(f"boot_ms={fmt(report.get('boot_ms'))}  load_ms={fmt(report.get('load_ms'))}  "
          f"reload_ms={fmt(report.get('reload_ms'))}  save_ms={fmt(report.get('save_ms'))}  "
          f"saved_bytes={report.get('saved_project_bytes')}  run_ms={fmt(report.get('run_ms'))}")
    for key in ("full_rebuild", "node_move"):
        section = report.get(key, {})
        if not section:
            continue
        wall = section.get("wall", {})
        io = section.get("io", {})
        print(f"{key}: wall p50={fmt(wall.get('p50_ms'))} p95={fmt(wall.get('p95_ms'))} "
              f"payload p50={fmt(section.get('payload_rebuild', {}).get('p50_ms'))} "
              f"io={io}")
    for key in ("fullscreen_tabular", "fullscreen_plot"):
        section = report.get(key, {})
        if not section:
            continue
        print(f"{key}: open cold={fmt(section.get('open_cold_ms'))} "
              f"open warm p50={fmt(section.get('open_warm', {}).get('p50_ms'))} "
              f"close p50={fmt(section.get('close', {}).get('p50_ms'))} io={section.get('io', {})}")
    paging = report.get("fullscreen_paging", {})
    if paging:
        print(
            "fullscreen_paging: "
            f"page_next={fmt(paging.get('page_next_ms'))}/{paging.get('page_next_state')} "
            f"page_deep={fmt(paging.get('page_deep_ms'))}/{paging.get('page_deep_state')} "
            f"sort={fmt(paging.get('query_sort_first_column_ms'))}/{paging.get('query_sort_first_column_state')} "
            f"search={fmt(paging.get('query_search_ms'))}/{paging.get('query_search_state')}"
        )
    if report.get("errors"):
        print(f"errors: {report['errors']}")


def _orchestrate(args: argparse.Namespace) -> int:
    project_path = Path(args.project).resolve()
    if not project_path.is_file():
        sys.stderr.write(f"project not found: {project_path}\n")
        return 2

    PERF_DIR.mkdir(parents=True, exist_ok=True)
    work_dir = PERF_DIR / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    work_project = work_dir / f"{args.label}_{project_path.name}"
    shutil.copy2(project_path, work_project)

    output_path = PERF_DIR / f"{args.label}.json"
    env = dict(os.environ)
    env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    env.pop("EA_PROFILE_AUTOQUIT", None)
    if args.cache_dir:
        # Isolate the managed parquet cache: point cold runs at a fresh dir,
        # warm runs at the same dir again. (A full APPDATA redirect breaks
        # unrelated discovery/cache behavior, so only the tabular cache moves.)
        cache_dir = Path(args.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        env["EA_TABULAR_CACHE_DIR"] = str(cache_dir)

    cmd = [
        sys.executable,
        __file__,
        "--mode", "child",
        "--project", str(work_project),
        "--label", args.label,
        "--iterations", str(args.iterations),
        "--moves", str(args.moves),
        "--rebuilds", str(args.rebuilds),
        "--run-timeout", str(args.run_timeout),
        "--output-path", str(output_path),
    ]
    if args.skip_run:
        cmd.append("--skip-run")

    log_path = PERF_DIR / f"{args.label}.log"
    with log_path.open("wb") as log_file:
        completed = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env, timeout=CHILD_TIMEOUT_S)
    if completed.returncode != 0:
        sys.stderr.write(f"child run failed rc={completed.returncode}; see {log_path}\n")
    if not output_path.is_file():
        sys.stderr.write("child produced no report\n")
        return completed.returncode or 5

    report = json.loads(output_path.read_text(encoding="utf-8"))
    _print_summary(report)

    if args.budgets:
        budgets_arg = args.budgets
        budgets_path = Path(budgets_arg)
        if budgets_path.is_file():
            budgets = json.loads(budgets_path.read_text(encoding="utf-8"))
        else:
            budgets = json.loads(budgets_arg)
        breaches = _check_budgets(report, budgets)
        if breaches:
            for breach in breaches:
                sys.stderr.write(f"BUDGET BREACH: {breach}\n")
            return 1
        print(f"all {len(budgets)} budgets met")
    return completed.returncode


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tabular/plot workflow performance harness")
    parser.add_argument("--mode", choices=("orchestrate", "child"), default="orchestrate")
    parser.add_argument("--project", required=True)
    parser.add_argument("--label", default="tabular_perf_report")
    parser.add_argument("--iterations", type=int, default=5, help="fullscreen open/close cycles")
    parser.add_argument("--moves", type=int, default=20, help="node-move delta publishes")
    parser.add_argument("--rebuilds", type=int, default=10, help="full scene rebuilds")
    parser.add_argument("--run-timeout", type=float, default=600.0)
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--budgets", default="", help="JSON mapping or path to one; breach -> exit 1")
    parser.add_argument(
        "--cache-dir",
        default="",
        help="Redirect the managed tabular cache dir (fresh dir = cold run, reuse = warm run)",
    )
    parser.add_argument("--output-path", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode == "child":
        if not args.output_path:
            sys.stderr.write("--output-path required in child mode\n")
            return 2
        return _run_child(args)
    return _orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
