"""Synthesize large CSV fixtures (plus benchmark .cxproj projects) for tabular perf proofs.

Reuses the benchmark dataset generators (`ea_node_editor.benchmarks.tabular.datasets`)
and streams chunks through ``pyarrow.csv`` so multi-gigabyte files are produced
without holding them in memory.

Usage
-----
    venv\\Scripts\\python.exe scripts\\generate_large_tabular_csv.py --target-bytes 400000000 --label large_400mb --emit-project
    venv\\Scripts\\python.exe scripts\\generate_large_tabular_csv.py --rows 5000000 --columns 8 --label tall_5m

Outputs land in ``artifacts/perf/`` by default:
    <label>.csv                      the data file
    <label>.cxproj                   tabular.input -> plot.scatter          (--emit-project)
    <label>_filtered.cxproj          tabular.input -> table_filter -> plot.scatter (--emit-project)
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ea_node_editor.benchmarks.tabular.contracts import DatasetSpec  # noqa: E402
from ea_node_editor.benchmarks.tabular.datasets import iter_table_chunks  # noqa: E402
from ea_node_editor.settings import SCHEMA_VERSION  # noqa: E402

PERF_DIR = REPO_ROOT / "artifacts" / "perf"
_CHUNK_ROWS = 200_000


def generate_csv(
    output_path: Path,
    *,
    rows: int,
    columns: int,
    profile: str,
    seed: int,
    target_bytes: int,
) -> dict[str, object]:
    import pyarrow as pa
    import pyarrow.csv as pa_csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    spec_rows = rows if target_bytes <= 0 else max(rows, 10_000_000_000)
    spec = DatasetSpec(
        size="custom",
        profile=profile,
        rows=spec_rows,
        columns=columns,
        seed=seed,
        target_bytes=target_bytes,
    )

    written_rows = 0
    writer: pa_csv.CSVWriter | None = None
    try:
        for chunk in iter_table_chunks(spec, chunk_rows=_CHUNK_ROWS):
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pa_csv.CSVWriter(str(output_path), table.schema)
            writer.write_table(table)
            written_rows += table.num_rows
            if target_bytes > 0 and output_path.stat().st_size >= target_bytes:
                break
            if target_bytes <= 0 and written_rows >= rows:
                break
    finally:
        if writer is not None:
            writer.close()

    size_bytes = output_path.stat().st_size
    return {
        "path": str(output_path),
        "rows": written_rows,
        "columns": columns,
        "profile": profile,
        "size_bytes": size_bytes,
    }


def _node_id() -> str:
    return f"node_{uuid.uuid4().hex[:10]}"


def _plot_line_node(node_id: str, *, x: float, y: float) -> dict[str, object]:
    return {
        "collapsed": False,
        "custom_height": None,
        "custom_width": None,
        "exposed_ports": {
            "data_export": True,
            "exports": True,
            "series": True,
            "static_export": True,
        },
        "links": [],
        "node_id": node_id,
        "parent_node_id": None,
        "port_labels": {},
        "properties": {
            "archive_export_on_run": False,
            "axis_limits": {"x": [None, None], "y": [None, None], "z": [None, None]},
            "backend": "auto",
            "data_export_format": "csv",
            "grid": True,
            "legend": True,
            "log_scales": {"x": False, "y": False, "z": False},
            "plot_options": {},
            "render_in_canvas": True,
            "static_export_format": "png",
            "tabular_mapping": {},
            "title": "",
            "x_label": "",
            "y_label": "",
            "z_label": "",
        },
        "title": "Line Plot",
        "type_id": "plot.scatter",
        "visual_style": {},
        "x": x,
        "y": y,
    }


def _tabular_input_node(node_id: str, *, path: Path, x: float, y: float) -> dict[str, object]:
    return {
        "collapsed": False,
        "custom_height": None,
        "custom_width": None,
        "exposed_ports": {
            "array_data": True,
            "path": True,
            "table_data": True,
        },
        "links": [],
        "node_id": node_id,
        "parent_node_id": None,
        "port_labels": {},
        "properties": {
            "allow_npz_archive_preview": False,
            "array_slice_2d": {"column_limit": 50, "column_offset": 0, "row_limit": 50, "row_offset": 0},
            "cache_policy": "app_managed_parquet",
            "delimiter": "",
            "encoding": "utf-8",
            "header_row": 0,
            "path": str(path).replace("\\", "/"),
            "project_managed_cache": False,
            "project_managed_source": False,
            "schema_hints": {},
            "selected_object": "",
            "skip_rows": 0,
            "tabular_selected_columns": [],
            "tabular_table_view_state": {},
        },
        "title": "Tabular Data Input",
        "type_id": "tabular.input",
        "visual_style": {},
        "x": x,
        "y": y,
    }


def _table_filter_node(node_id: str, *, x: float, y: float) -> dict[str, object]:
    return {
        "collapsed": False,
        "custom_height": None,
        "custom_width": None,
        "exposed_ports": {"table_data": True, "window": True},
        "links": [],
        "node_id": node_id,
        "parent_node_id": None,
        "port_labels": {},
        "properties": {
            "column_limit": 0,
            "column_offset": 0,
            "columns": "",
            "row_limit": 0,
            "row_offset": 0,
        },
        "title": "Table Filter",
        "type_id": "tabular.table_filter",
        "visual_style": {},
        "x": x,
        "y": y,
    }


def _edge(source_id: str, source_port: str, target_id: str, target_port: str) -> dict[str, object]:
    return {
        "edge_id": f"edge_{uuid.uuid4().hex[:10]}",
        "label": "",
        "source_node_id": source_id,
        "source_port_key": source_port,
        "target_node_id": target_id,
        "target_port_key": target_port,
        "enabled": True,
        "input_order": 0,
        "visual_style": {},
    }


def emit_project(output_path: Path, csv_path: Path, *, with_filter: bool) -> None:
    workspace_id = f"ws_{uuid.uuid4().hex[:10]}"
    view_id = f"view_{uuid.uuid4().hex[:10]}"
    tabular_id = _node_id()
    plot_id = _node_id()
    nodes = [
        _plot_line_node(plot_id, x=140.0, y=-195.0),
        _tabular_input_node(tabular_id, path=csv_path, x=-537.0, y=-225.0),
    ]
    if with_filter:
        filter_id = _node_id()
        nodes.insert(1, _table_filter_node(filter_id, x=-200.0, y=-210.0))
        edges = [
            _edge(tabular_id, "table_data", filter_id, "table_data"),
            _edge(filter_id, "window", plot_id, "series"),
        ]
    else:
        edges = [_edge(tabular_id, "table_data", plot_id, "series")]

    document = {
        "active_workspace_id": workspace_id,
        "metadata": {
            "artifact_store": {"artifacts": {}, "staged": {}},
            "custom_workflows": [],
            "ui": {
                "passive_style_presets": {"edge_presets": [], "node_presets": []},
                "script_editor": {"floating": False, "visible": False, "width": 0.0},
            },
            "workflow_settings": {
                "environment": {"python_path": "", "working_directory": ""},
                "general": {"author": "", "description": "", "project_name": ""},
                "logging": {"capture_console": True, "level": "info"},
                "plugins": {"enabled": []},
                "solver_config": {"enable_parallel": True, "memory_limit_gb": 12, "thread_count": 8},
            },
            "workspace_order": [workspace_id],
        },
        "name": output_path.stem,
        "project_id": "proj_local",
        "schema_version": SCHEMA_VERSION,
        "workspace_order": [workspace_id],
        "workspaces": [
            {
                "active_view_id": view_id,
                "dirty": False,
                "edges": edges,
                "name": "Workspace 1",
                "nodes": nodes,
                "views": [
                    {
                        "hide_optional_ports": False,
                        "name": "V1",
                        "pan_x": 0.0,
                        "pan_y": 0.0,
                        "scope_path": [],
                        "view_id": view_id,
                        "zoom": 0.75,
                    }
                ],
                "workspace_id": workspace_id,
            }
        ],
    }
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate large CSV fixtures + benchmark projects")
    parser.add_argument("--rows", type=int, default=2_000_000)
    parser.add_argument("--columns", type=int, default=8)
    parser.add_argument("--target-bytes", type=int, default=0, help="stop once the CSV reaches this size")
    parser.add_argument("--profile", default="mixed_table")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--label", default="large_tabular")
    parser.add_argument("--output-dir", default=str(PERF_DIR))
    parser.add_argument("--emit-project", action="store_true", help="also write <label>.cxproj and <label>_filtered.cxproj")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    csv_path = output_dir / f"{args.label}.csv"
    summary = generate_csv(
        csv_path,
        rows=args.rows,
        columns=args.columns,
        profile=args.profile,
        seed=args.seed,
        target_bytes=args.target_bytes,
    )
    print(json.dumps(summary, indent=2))

    if args.emit_project:
        project_path = output_dir / f"{args.label}.cxproj"
        emit_project(project_path, csv_path, with_filter=False)
        filtered_path = output_dir / f"{args.label}_filtered.cxproj"
        emit_project(filtered_path, csv_path, with_filter=True)
        print(f"projects: {project_path} ; {filtered_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
