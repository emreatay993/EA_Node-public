from __future__ import annotations

import csv
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ea_node_editor.execution.plot_backend import (
    PLOT_TYPE_LINE,
    PLOT_TYPE_SURFACE,
    PlotDataExportRequest,
    PlotRenderRequest,
    PlotStaticExportRequest,
)
from ea_node_editor.execution.plot_backend_matplotlib import (
    MATPLOTLIB_PLOT_BACKEND_ID,
    MatplotlibPlotBackend,
)
from ea_node_editor.execution.plot_backend_pyvista import (
    PYVISTA_PLOT_BACKEND_ID,
    PyVistaLive3DPlotBackend,
    pyvista_static_export_supported,
)


def _line_request() -> PlotRenderRequest:
    return PlotRenderRequest(
        plot_type=PLOT_TYPE_LINE,
        title="Headless Line",
        x_label="time",
        y_label="value",
        series=(
            {
                "label": "sample",
                "x": [0, 1, 2],
                "y": [1.0, 2.5, 4.0],
            },
        ),
    )


def test_matplotlib_static_export_writes_png_svg_and_pdf_without_qapplication(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    png_path = tmp_path / "line.png"
    svg_path = tmp_path / "line.svg"
    pdf_path = tmp_path / "line.pdf"
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path

        assert "PyQt6.QtWidgets" not in sys.modules
        from ea_node_editor.execution.plot_backend import PLOT_TYPE_LINE, PlotRenderRequest, PlotStaticExportRequest
        from ea_node_editor.execution.plot_backend_matplotlib import MATPLOTLIB_PLOT_BACKEND_ID, MatplotlibPlotBackend

        render_request = PlotRenderRequest(
            plot_type=PLOT_TYPE_LINE,
            title="Headless Line",
            x_label="time",
            y_label="value",
            series=({"label": "sample", "x": [0, 1, 2], "y": [1.0, 2.5, 4.0]},),
        )
        backend = MatplotlibPlotBackend()
        png_result = backend.export_static(
            PlotStaticExportRequest(render_request=render_request, output_path=Path(sys.argv[1]))
        )
        svg_result = backend.export_static(
            PlotStaticExportRequest(render_request=render_request, output_path=Path(sys.argv[2]))
        )
        pdf_result = backend.export_static(
            PlotStaticExportRequest(render_request=render_request, output_path=Path(sys.argv[3]))
        )
        assert png_result.backend_id == MATPLOTLIB_PLOT_BACKEND_ID
        assert png_result.format == "png"
        assert svg_result.format == "svg"
        assert pdf_result.format == "pdf"
        assert "PyQt6.QtWidgets" not in sys.modules
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(png_path), str(svg_path), str(pdf_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert png_path.read_bytes().startswith(b"\x89PNG")
    assert "<svg" in svg_path.read_text(encoding="utf-8", errors="ignore")
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_matplotlib_csv_data_export_writes_simple_line_request(tmp_path: Path) -> None:
    backend = MatplotlibPlotBackend()
    output_path = tmp_path / "line.csv"

    result = backend.export_data(
        PlotDataExportRequest(render_request=_line_request(), output_path=output_path)
    )

    assert result.backend_id == MATPLOTLIB_PLOT_BACKEND_ID
    assert result.format == "csv"
    assert result.metadata["row_count"] == 3
    with output_path.open(newline="", encoding="utf-8") as output_file:
        rows = list(csv.DictReader(output_file))

    assert rows == [
        {"series": "sample", "index": "0", "x": "0", "y": "1.0", "value": "1.0", "row": "", "column": ""},
        {"series": "sample", "index": "1", "x": "1", "y": "2.5", "value": "2.5", "row": "", "column": ""},
        {"series": "sample", "index": "2", "x": "2", "y": "4.0", "value": "4.0", "row": "", "column": ""},
    ]


def test_pyvista_static_export_writes_surface_png_when_offscreen_supported(tmp_path: Path) -> None:
    if not pyvista_static_export_supported():
        pytest.skip("PyVista off-screen static export is not supported by this environment")
    output_path = tmp_path / "surface.png"
    backend = PyVistaLive3DPlotBackend()

    result = backend.export_static(
        PlotStaticExportRequest(
            render_request=PlotRenderRequest(
                plot_type=PLOT_TYPE_SURFACE,
                title="Surface",
                series=({"z": [[0.0, 1.0], [1.0, 2.0]]},),
            ),
            output_path=output_path,
        )
    )

    assert result.backend_id == PYVISTA_PLOT_BACKEND_ID
    assert result.format == "png"
    assert output_path.read_bytes().startswith(b"\x89PNG")


def test_generic_plot_node_archives_headless_line_export_without_qapplication(tmp_path: Path) -> None:
    monkey_env = os.environ.copy()
    monkey_env.pop("QT_QPA_PLATFORM", None)
    project_path = tmp_path / "generic_plot_node.cxproj"
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path

        assert "PyQt6.QtWidgets" not in sys.modules

        from ea_node_editor.addons.tabular_data.input_node import (
            TABULAR_DATA_TABLE_OUTPUT_KEY,
            TABULAR_SELECTED_COLUMNS_PROPERTY,
            execute_tabular_input,
        )
        from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot, RuntimeSnapshotContext
        from ea_node_editor.nodes.bootstrap import build_default_registry
        from ea_node_editor.nodes.execution_context import ExecutionContext
        from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
        from ea_node_editor.persistence.artifact_store import ProjectArtifactStore

        project_path = Path(sys.argv[1])
        runtime_snapshot = RuntimeSnapshot(schema_version=1, project_id="project_plot_headless", metadata={})
        artifact_store = ProjectArtifactStore.from_project_metadata(
            project_path=project_path,
            project_metadata=runtime_snapshot.metadata,
        )
        runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
            runtime_snapshot,
            project_path=str(project_path),
            artifact_store=artifact_store,
        )
        resolver = ProjectArtifactResolver(project_path=project_path, artifact_store=artifact_store)
        registry = build_default_registry()
        plugin = registry.create("plot.scatter")
        source = project_path.with_suffix(".csv")
        source.write_text("time,value\\n0,1.0\\n1,2.5\\n2,4.0\\n", encoding="utf-8")
        table_ref = execute_tabular_input(
            ExecutionContext(
                run_id="run_tabular_headless",
                node_id="node_tabular",
                workspace_id="ws_plot_headless",
                inputs={},
                properties={
                    "path": str(source),
                    TABULAR_SELECTED_COLUMNS_PROPERTY: ["time", "value"],
                },
                emit_log=lambda _level, _message: None,
            )
        ).outputs[TABULAR_DATA_TABLE_OUTPUT_KEY]
        properties = registry.normalize_properties(
            "plot.scatter",
            {
                "title": "Headless Generic Scatter",
                "x_label": "time",
                "y_label": "value",
                "archive_export_on_run": True,
            },
        )
        result = plugin.execute(
            ExecutionContext(
                run_id="run_plot_headless",
                node_id="node_plot_line",
                node_type_id="plot.scatter",
                workspace_id="ws_plot_headless",
                inputs={"series": table_ref},
                properties=properties,
                emit_log=lambda _level, _message: None,
                project_path=str(project_path),
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )
        )
        png_path = resolver.resolve_to_path(result.outputs["static_export"].ref)
        csv_path = resolver.resolve_to_path(result.outputs["data_export"].ref)
        assert png_path is not None and png_path.read_bytes().startswith(b"\\x89PNG")
        assert csv_path is not None and "value" in csv_path.read_text(encoding="utf-8")
        assert "PyQt6.QtWidgets" not in sys.modules
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(project_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=monkey_env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
