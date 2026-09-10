# Purpose: Measure Signal Plot rendering and scientific worker/runtime pipelines.
# Map: feature_routes/plotter_nodes.md
# Tests: tests/test_signal_plot_scientific_integration.py
from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from ea_node_editor.execution.plot_backend import (
    PlotRenderRequest,
    PlotStaticExportRequest,
)
from ea_node_editor.execution.plot_backend_matplotlib import MatplotlibPlotBackend
from ea_node_editor.execution.signal_plot_renderer import render_signal_plot
from ea_node_editor.runtime_contracts import DataTree


def _p95(values: list[float]) -> float:
    return (
        statistics.quantiles(values, n=20, method="inclusive")[18]
        if len(values) > 1
        else values[0]
    )


def _measure(
    render, *, warmups: int, measurements: int, include_children: bool = False
) -> tuple[list[float], int]:
    process = psutil.Process(os.getpid())
    for _ in range(warmups):
        render()
    times: list[float] = []
    peaks: list[int] = []
    for _ in range(measurements):
        gc.collect()
        peak = 0
        stop = threading.Event()

        def sample() -> None:
            nonlocal peak
            while not stop.is_set():
                rss = process.memory_info().rss
                if include_children:
                    for child in process.children(recursive=True):
                        try:
                            rss += child.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                peak = max(peak, rss)
                stop.wait(0.01 if include_children else 0.001)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        started = time.perf_counter()
        try:
            render()
            times.append(time.perf_counter() - started)
        finally:
            stop.set()
            sampler.join()
        peaks.append(max(peak, process.memory_info().rss))
    return times, max(peaks)


def benchmark(
    renderer: str, points: int, *, warmups: int, measurements: int
) -> dict[str, object]:
    x = list(range(points))
    branches = (
        tuple(math.sin(index * 0.001) for index in x),
        tuple(math.cos(index * 0.001) for index in x),
    )
    if renderer == "xy":
        tree = DataTree((((0,), branches[0]), ((1,), branches[1])))

        def render() -> None:
            render_signal_plot({"values": tree, "marker_shapes": [0], "max_points": 0})

    else:
        request = PlotRenderRequest(
            plot_type="line",
            series=(
                {"label": "signal-a", "x": x, "y": branches[0]},
                {"label": "signal-b", "x": x, "y": branches[1]},
            ),
        )
        temporary = tempfile.TemporaryDirectory()
        output = Path(temporary.name) / "baseline.png"

        def render() -> None:
            MatplotlibPlotBackend().export_static(
                PlotStaticExportRequest(
                    render_request=request,
                    output_path=output,
                    width_inches=6.0,
                    height_inches=4.0,
                    dpi=100,
                )
            )

    times, peak = _measure(render, warmups=warmups, measurements=measurements)
    return {
        "renderer": renderer,
        "branches": 2,
        "point_count_per_branch": points,
        "width": 600,
        "height": 400,
        "warmups": warmups,
        "measurements": measurements,
        "times_seconds": times,
        "mean_seconds": statistics.mean(times),
        "p95_seconds": _p95(times),
        "peak_rss_bytes": peak,
    }


def settled_item(event, key, catalog):
    from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
    from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value

    result = event["outputs"][key]
    if isinstance(result, SettledPortResult):
        assert result.status == "value", result.errors
        tree = result.value
    else:
        assert result["status"] == "value", result.get("errors")
        tree = deserialize_runtime_value(result["value"], catalog=catalog)
    return tree[(0,)][0]


def verify_scientific_source(value, rows: int) -> None:
    """Check every original sample, not merely the rendered point count."""
    import numpy as np
    from ea_node_editor.runtime_contracts.scientific_values import (
        ArrayValue,
        TableValue,
    )

    if isinstance(value, ArrayValue):
        assert value.shape == (rows, 4)
        matrix = value.to_numpy()
        assert not matrix.flags.writeable
        columns = [matrix[:, position] for position in range(4)]
    else:
        assert isinstance(value, TableValue) and value.row_count == rows
        assert value.column_names == ("sample", "sine", "cosine", "ramp")
        columns = [value.column_values(position) for position in range(4)]
    x = np.arange(rows, dtype=np.float64)
    for column, expected in zip(
        columns, (x, np.sin(x * 0.001), np.cos(x * 0.001), x * 0.01)
    ):
        np.testing.assert_array_equal(column, expected)


def wait_for_runtime_idle(runtime, timeout: float = 30) -> None:
    # Match the existing runtime integration gate: terminal delivery precedes cleanup.
    deadline = time.monotonic() + timeout
    while runtime._client._active_clients:
        if time.monotonic() >= deadline:
            raise TimeoutError("Execution backend did not retire the completed run")
        time.sleep(0.01)


def scientific_benchmark(
    kind: str, rows: int, *, backend: str, repetitions: int = 2
) -> dict[str, object]:
    from ea_node_editor.execution.process_client import ProcessExecutionClient
    from ea_node_editor.execution.runtime import CorexRuntime
    from ea_node_editor.execution.runtime_requests import ExecutionRequest
    from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.nodes.bootstrap import build_default_registry
    from ea_node_editor.runtime_contracts import ImageValue
    from scripts.generate_signal_plot_scientific_example import add_signal_chain

    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    source, plot, output = add_signal_chain(model, registry, kind=kind, rows=rows)
    workspace_id = model.active_workspace.workspace_id
    snapshot = build_runtime_snapshot(
        model.project, workspace_id=workspace_id, registry=registry
    )
    client = (
        ProcessExecutionClient()
        if backend == "process"
        else CorexRuntime(registry=registry)
    )
    condition = threading.Condition()
    events = []

    def capture(event):
        with condition:
            events.append(event)
            condition.notify_all()

    if backend == "process":
        client.subscribe(capture)
    records = []
    try:
        for repetition in range(repetitions):
            events.clear()

            def execute():
                if backend == "runtime":
                    result = client.run(
                        ExecutionRequest(
                            runtime_snapshot=snapshot, workspace_id=workspace_id
                        ),
                        timeout=180,
                    )
                    assert result.status == "completed", (
                        result.error,
                        result.traceback,
                    )
                    events.extend(result.events)
                    wait_for_runtime_idle(client)
                else:
                    run_id = client.start_run(
                        project_path="",
                        workspace_id=workspace_id,
                        trigger={"kind": "manual", "runtime_snapshot": snapshot},
                        data_types=registry.data_types,
                        plugin_bundles=registry.plugin_bundle_refs(),
                        plugin_fingerprint=registry.plugin_fingerprint(),
                        registry_contract_fingerprint=registry.contract_fingerprint(),
                        addon_runtime_config=registry.addon_runtime_config(),
                    )
                    with condition:
                        assert condition.wait_for(
                            lambda: any(
                                e.get("run_id") == run_id
                                and e.get("type")
                                in {"run_completed", "run_failed", "run_stopped"}
                                for e in events
                            ),
                            timeout=180,
                        ), "Worker timed out"
                    assert any(e.get("type") == "run_completed" for e in events), [
                        (e.get("type"), e.get("error")) for e in events
                    ]

            times, peak = _measure(
                execute, warmups=0, measurements=1, include_children=True
            )
            settled = {
                event["node_id"]: event
                for event in events
                if event.get("type") == "node_settled"
            }
            verify_scientific_source(
                settled_item(settled[source.node_id], output, registry.data_types), rows
            )
            image = settled_item(settled[plot.node_id], "image", registry.data_types)
            assert isinstance(image, ImageValue) and (image.width, image.height) == (
                600,
                400,
            )
            warnings = settled[plot.node_id].get("warnings", ())
            reductions = [
                tuple(map(int, match.groups()))
                for warning in warnings
                if (
                    match := re.fullmatch(
                        r"Trace (\d+) reduced from (\d+) to (\d+) rendered points; source data is unchanged\.",
                        warning,
                    )
                )
            ]
            if rows > 4000:
                assert len(reductions) == 3 and all(
                    original == rows and rendered <= 4000
                    for _, original, rendered in reductions
                ), warnings
            source_reason = settled[source.node_id].get("decision_reason")
            plot_reason = settled[plot.node_id].get("decision_reason")
            if backend == "runtime" and repetition:
                assert (
                    registry.get_spec("core.python_script").solution_reuse_scope
                    == "never"
                )
                assert source_reason == "implementation_identity_unavailable", (
                    source_reason
                )
                assert plot_reason == "upstream_recompute_required", plot_reason
                assert all(
                    settled[node.node_id]["disposition"] == "recomputed"
                    for node in (source, plot)
                )
            records.append(
                {
                    "run": "initial" if repetition == 0 else f"repeat_{repetition}",
                    "elapsed_seconds": times[0],
                    "peak_combined_rss_bytes": peak,
                    "source_decision": source_reason,
                    "plot_decision": plot_reason,
                    "rendered_points": [item[2] for item in reductions]
                    if reductions
                    else [rows] * 3,
                    "full_source_verified": True,
                }
            )
            settled.clear()
    finally:
        client.shutdown()
    return {
        "source": kind,
        "backend": backend,
        "rows": rows,
        "columns": 4,
        "decoded_numeric_bytes": rows * 4 * 8,
        "rss_sample_interval_seconds": 0.01,
        "runs": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scientific",
        action="store_true",
        help="Measure native script-to-Signal Plot process and CorexRuntime execution",
    )
    parser.add_argument("--rows", type=int, default=2_000_000)
    parser.add_argument(
        "--sources", nargs="+", choices=("numpy", "pandas"), default=("numpy", "pandas")
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=("process", "runtime"),
        default=("process", "runtime"),
    )
    parser.add_argument(
        "--renderer", choices=("matplotlib", "xy", "both"), default="both"
    )
    parser.add_argument("--points", type=int, nargs="+", default=(10_000, 1_000_000))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--measurements", type=int, default=10)
    args = parser.parse_args()
    if args.scientific:
        for backend in args.backends:
            for source in args.sources:
                print(
                    json.dumps(
                        scientific_benchmark(source, args.rows, backend=backend),
                        sort_keys=True,
                    ),
                    flush=True,
                )
        return 0
    renderers = ("matplotlib", "xy") if args.renderer == "both" else (args.renderer,)
    for renderer in renderers:
        for points in args.points:
            print(
                json.dumps(
                    benchmark(
                        renderer,
                        points,
                        warmups=args.warmups,
                        measurements=args.measurements,
                    ),
                    sort_keys=True,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
