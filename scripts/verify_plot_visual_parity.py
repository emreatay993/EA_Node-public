"""Visual parity spot-check: decimated plot series vs full-fidelity rendering.

Renders the same tabular source twice through the matplotlib static-export
backend — once with the production decimated series path and once with every
source row — and compares the resulting images. Min-max envelope decimation
must be visually indistinguishable at canvas resolution for line plots.

Usage
-----
    venv\\Scripts\\python.exe scripts\\verify_plot_visual_parity.py --csv path\\to\\data.csv --x time --y value
    venv\\Scripts\\python.exe scripts\\verify_plot_visual_parity.py  (uses the 400k-row benchmark CSV)

Outputs PNGs + metrics into artifacts/perf/parity/ and fails (exit 1) when the
mean absolute pixel difference exceeds the threshold.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CSV = "C:/Users/user/Documents/plot_data/full_data.csv"
PARITY_DIR = REPO_ROOT / "artifacts" / "perf" / "parity"
MEAN_DIFF_THRESHOLD = 2.0  # mean abs pixel delta out of 255 across the figure


def _render(request, output_path: Path) -> None:  # noqa: ANN001
    from ea_node_editor.execution.plot_backend import PlotStaticExportRequest
    from ea_node_editor.execution.plot_backend_matplotlib import MatplotlibPlotBackend

    backend = MatplotlibPlotBackend()
    backend.export_static(
        PlotStaticExportRequest(
            render_request=request,
            output_path=output_path,
            format="png",
            width_inches=9.6,
            height_inches=5.4,
            dpi=100,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decimated-vs-full plot parity check")
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--x", default="", help="x column (auto when omitted)")
    parser.add_argument("--y", default="", help="y column (auto when omitted)")
    parser.add_argument("--threshold", type=float, default=MEAN_DIFF_THRESHOLD)
    args = parser.parse_args(argv)

    import numpy as np

    from ea_node_editor.addons.tabular_data.loader_cache_service import (
        shared_tabular_loader_cache_service,
    )
    from ea_node_editor.execution.plot_backend import PlotRenderRequest
    from ea_node_editor.nodes.builtins.plot.generic import _series_from_tabular_ref
    from ea_node_editor.runtime_contracts import TabularArrowBatchOptions

    source = Path(args.csv)
    if not source.is_file():
        sys.stderr.write(f"csv not found: {source}\n")
        return 2
    PARITY_DIR.mkdir(parents=True, exist_ok=True)

    service = shared_tabular_loader_cache_service()
    ref = service.open_source(source)
    mapping: dict[str, object] = {}
    if args.x:
        mapping["x"] = args.x
    if args.y:
        mapping["y"] = [args.y]

    decimated_series, _warnings = _series_from_tabular_ref(ref, plot_type="line", mapping=mapping)
    if not decimated_series:
        sys.stderr.write("no plottable series found\n")
        return 2
    first = decimated_series[0]
    x_column = str(first.get("x_column", "") or "")
    y_column = str(first.get("y_column", "") or "")

    columns = tuple(name for name in (x_column, y_column) if name)
    chunks: dict[str, list] = {name: [] for name in columns}
    for batch in service.arrow_batches(
        ref,
        TabularArrowBatchOptions(row_limit=2_147_483_647, batch_size=262_144, columns=columns),
    ):
        for name in columns:
            index = batch.schema.names.index(name)
            chunks[name].append(batch.column(index).to_numpy(zero_copy_only=False))
    full: dict[str, object] = {name: np.concatenate(parts) for name, parts in chunks.items()}
    full_y = full[y_column].astype(np.float64)
    full_rows = int(len(full_y))
    first = dict(first)
    if x_column:
        try:
            full_x = full[x_column].astype(np.float64)
        except (TypeError, ValueError):
            # Label axis: compare on sequential positions (tick labels differ
            # by construction between the full and decimated renders).
            full_x = np.arange(full_rows, dtype=np.float64)
            first.pop("x_labels", None)
    else:
        full_x = np.arange(full_rows, dtype=np.float64)
    finite = np.isfinite(full_x) & np.isfinite(full_y)
    full_series = {
        "label": first.get("label", "series"),
        "x": full_x[finite].tolist(),
        "y": full_y[finite].tolist(),
    }

    decimated_request = PlotRenderRequest(plot_type="line", series=(first,))
    full_request = PlotRenderRequest(plot_type="line", series=(full_series,))

    decimated_png = PARITY_DIR / "decimated.png"
    full_png = PARITY_DIR / "full.png"
    _render(decimated_request, decimated_png)
    _render(full_request, full_png)

    from matplotlib import image as mpimg

    decimated_pixels = (mpimg.imread(decimated_png) * 255.0).astype(np.float64)
    full_pixels = (mpimg.imread(full_png) * 255.0).astype(np.float64)
    if decimated_pixels.shape != full_pixels.shape:
        sys.stderr.write(f"shape mismatch: {decimated_pixels.shape} vs {full_pixels.shape}\n")
        return 1
    delta = np.abs(decimated_pixels - full_pixels)
    metrics = {
        "csv": str(source),
        "rows_full": full_rows,
        "points_decimated": first.get("decimation", {}),
        "mean_abs_diff": float(delta.mean()),
        "max_abs_diff": float(delta.max()),
        "diff_pixel_fraction": float((delta.max(axis=-1) > 8).mean()),
        "threshold": args.threshold,
    }
    (PARITY_DIR / "parity_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    if metrics["mean_abs_diff"] > args.threshold:
        sys.stderr.write("PARITY FAIL: mean pixel difference exceeds threshold\n")
        return 1
    print("parity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
