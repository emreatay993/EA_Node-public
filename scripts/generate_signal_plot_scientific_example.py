# Purpose: Generate a runnable CSV, NumPy and pandas Signal Plot workflow.
# Map: feature_routes/plotter_nodes.md
# Tests: tests/test_signal_plot_scientific_integration.py
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.persistence.artifact_store import format_node_artifact_folder
from ea_node_editor.runtime_contracts import PATH_DATA_TYPE_ID, RuntimeArtifactRef


def scientific_script(kind: str, rows: int, *, any_type: bool = False) -> str:
    if kind not in {"numpy", "pandas"} or rows < 2:
        raise ValueError("Use numpy or pandas with at least two rows")
    type_id = (
        "COREX.DataTypes.ArrayValue"
        if kind == "numpy"
        else "COREX.DataTypes.TableValue"
    )
    declaration = "corex.Any" if any_type else repr(type_id)
    return f"""@corex.node
@corex.output("result", value_type={declaration}, structure="item")
def run(ctx):
    import numpy as np
    x = np.arange({rows}, dtype=np.float64)
    data = np.column_stack((x, np.sin(x * 0.001), np.cos(x * 0.001), x * 0.01))
""" + (
        '    return {"result": data}\n'
        if kind == "numpy"
        else '    import pandas as pd\n    return {"result": pd.DataFrame(data, columns=["sample", "sine", "cosine", "ramp"])}\n'
    )


def add_signal_chain(
    model,
    registry,
    *,
    kind: str,
    rows: int,
    path: str = "",
    y: float = 0,
    any_type: bool = False,
):
    mutation = model.validated_mutations(model.active_workspace.workspace_id, registry)
    if kind in {"csv", "npy"}:
        properties = {"path": path, "cache_policy": "source_direct"}
        if kind == "npy":
            properties["array_slice_2d"] = {
                "row_offset": 0,
                "column_offset": 0,
                "row_limit": rows,
                "column_limit": 4,
            }
        source = mutation.add_node(
            type_id="tabular.input",
            title=f"{kind.upper()} source",
            x=0,
            y=y,
            properties=properties,
        )
        output = "table_data" if kind == "csv" else "array_data"
    else:
        source = mutation.add_node(
            type_id="core.python_script",
            title=f"{kind} source",
            x=0,
            y=y,
            properties={"script": scientific_script(kind, rows, any_type=any_type)},
        )
        output = "result"
    plot = mutation.add_node(
        type_id="plot.signal",
        title=f"{kind} signals",
        x=400,
        y=y,
        properties={"title": f"{kind} signals", "marker_shapes": [0]},
    )
    mutation.add_edge(
        source_node_id=source.node_id,
        source_port_key=output,
        target_node_id=plot.node_id,
        target_port_key="values",
    )
    return source, plot, output


def generate_example(destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    registry = build_default_registry(include_public_plugins=False)
    model = GraphModel()
    model.project.name = "Signal Plot scientific inputs"
    source, _, _ = add_signal_chain(
        model, registry, kind="csv", rows=256, path="saved://scientific_csv"
    )
    folder = format_node_artifact_folder(
        workspace_id=model.active_workspace.workspace_id,
        node_id=source.node_id,
        node_title=source.title,
        node_type=source.type_id,
    )
    relative_path = Path("nodes") / folder / "in" / "tabular" / "source" / "signals.csv"
    data_path = destination.with_suffix(".data") / relative_path
    data_path.parent.mkdir(parents=True, exist_ok=True)
    with data_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("sample", "sine", "cosine", "ramp"))
        for index in range(256):
            writer.writerow(
                (index, math.sin(index * 0.001), math.cos(index * 0.001), index * 0.01)
            )
    # A saved reference keeps the example movable together with its data folder.
    size, digest = artifact_content_integrity(
        destination.with_suffix(".data"), relative_path.as_posix()
    )
    descriptor = RuntimeArtifactRef.managed(
        "scientific_csv",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=registry.data_types.require(
            PATH_DATA_TYPE_ID
        ).payload_schema_version,
        format="csv",
        size_bytes=size,
        sha256=digest,
        provenance="corex.example",
    ).to_descriptor()
    model.project.metadata["artifact_store"] = {
        "artifacts": {
            "scientific_csv": {
                "artifact_kind": "tabular_source",
                "relative_path": relative_path.as_posix(),
                "runtime_artifact": descriptor,
            }
        },
        "staged": {},
    }
    for index, kind in enumerate(("numpy", "pandas"), start=1):
        add_signal_chain(model, registry, kind=kind, rows=256, y=index * 320)
    mutation = model.validated_mutations(model.active_workspace.workspace_id, registry)
    for plot in tuple(model.active_workspace.nodes.values()):
        if plot.type_id == "plot.signal":
            panel = mutation.add_node(
                type_id="media.panel",
                title=plot.title,
                x=800,
                y=plot.y,
                custom_width=480,
                custom_height=300,
            )
            mutation.add_edge(
                source_node_id=plot.node_id,
                source_port_key="image",
                target_node_id=panel.node_id,
                target_port_key="source",
            )
    JsonProjectSerializer(registry).save(str(destination), model.project)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/examples/signal_plot_scientific.cxproj"),
    )
    args = parser.parse_args()
    print(generate_example(args.output))


if __name__ == "__main__":
    main()
