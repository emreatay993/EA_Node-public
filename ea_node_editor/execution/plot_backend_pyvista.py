from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from ea_node_editor.execution.plot_backend import (
    PLOT_SURFACE_LIVE,
    PLOT_SURFACE_STATIC_EXPORT,
    PLOT_TYPE_POINT_CLOUD,
    PLOT_TYPE_STREAMLINES,
    PLOT_TYPE_SURFACE,
    PlotBackendRecord,
    PlotCapability,
    PlotExportResult,
    PlotRenderRequest,
    PlotStaticExportRequest,
)

PYVISTA_PLOT_BACKEND_ID = "pyvista"
PYVISTA_PLOT_BACKEND_DISPLAY_NAME = "PyVista Live 3D"
PYVISTA_STATIC_EXPORT_FORMATS = ("png",)
PYVISTA_LIVE_3D_PLOT_TYPES = (
    PLOT_TYPE_SURFACE,
    PLOT_TYPE_POINT_CLOUD,
    PLOT_TYPE_STREAMLINES,
)


def _pyvista():
    try:
        import pyvista
    except ImportError as exc:
        raise RuntimeError(
            "PyVista is required for live 3D plot rendering. "
            "Install the viewer optional dependencies to enable 3D plot widgets."
        ) from exc
    return pyvista


def _numpy():
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError("numpy is required for PyVista plot rendering.") from exc
    return numpy


def _first_present(series: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in series and series[key] is not None:
            return series[key]
    return None


def _as_array(value: Any, *, name: str) -> Any:
    if value is None:
        raise ValueError(f"{name} is required for PyVista plot rendering")
    numpy = _numpy()
    return numpy.asarray(value)


def _plotter_size(request: PlotStaticExportRequest) -> tuple[int, int]:
    return (
        max(1, int(request.width_inches * request.dpi)),
        max(1, int(request.height_inches * request.dpi)),
    )


def _resolve_format(output_path: Path, requested_format: str) -> str:
    resolved = requested_format or output_path.suffix.lower().lstrip(".")
    if not resolved:
        raise ValueError("plot export format is required when output path has no suffix")
    if resolved not in PYVISTA_STATIC_EXPORT_FORMATS:
        supported = ", ".join(PYVISTA_STATIC_EXPORT_FORMATS)
        raise ValueError(f"Unsupported PyVista plot export format {resolved!r}; supported formats: {supported}")
    return resolved


def _prepare_output_path(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _surface_grid(series: Mapping[str, Any]) -> Any:
    pyvista = _pyvista()
    numpy = _numpy()
    z_values = _as_array(_first_present(series, "z", "values", "data"), name="surface z values").astype(float, copy=False)
    if z_values.ndim != 2:
        raise ValueError("surface plots require a 2D 'z', 'values', or 'data' array")
    raw_x = _first_present(series, "x")
    raw_y = _first_present(series, "y")
    if raw_x is None:
        raw_x = numpy.arange(z_values.shape[1], dtype=float)
    if raw_y is None:
        raw_y = numpy.arange(z_values.shape[0], dtype=float)
    x_values = _as_array(raw_x, name="surface x values").astype(float, copy=False)
    y_values = _as_array(raw_y, name="surface y values").astype(float, copy=False)
    if x_values.ndim == 1 and y_values.ndim == 1:
        x_grid, y_grid = numpy.meshgrid(x_values, y_values)
    else:
        x_grid = x_values
        y_grid = y_values
    return pyvista.StructuredGrid(x_grid, y_grid, z_values)


def _point_cloud_points(series: Mapping[str, Any]) -> Any:
    numpy = _numpy()
    raw_points = _first_present(series, "points", "xyz")
    if raw_points is not None:
        points = _as_array(raw_points, name="point cloud points")
    else:
        x_values = _as_array(_first_present(series, "x"), name="point cloud x values").reshape(-1)
        y_values = _as_array(_first_present(series, "y"), name="point cloud y values").reshape(-1)
        z_values = _as_array(_first_present(series, "z"), name="point cloud z values").reshape(-1)
        if len({len(x_values), len(y_values), len(z_values)}) != 1:
            raise ValueError("point cloud 'x', 'y', and 'z' values must have the same length")
        points = numpy.column_stack((x_values, y_values, z_values))
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("point cloud points must be an Nx3 array")
    return points


def _streamline_points(series: Mapping[str, Any]) -> Any:
    points = _as_array(_first_present(series, "points", "path", "xyz"), name="streamline points")
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("streamline points must be an Nx3 array")
    if points.shape[0] < 2:
        raise ValueError("streamlines require at least two points")
    return points


def _colormap(request: PlotRenderRequest) -> str:
    return str(request.options.get("cmap") or request.options.get("colormap") or "viridis")


def _draw_empty(plotter: Any, request: PlotRenderRequest) -> None:
    title = request.title or request.plot_type.replace("_", " ").title()
    add_text = getattr(plotter, "add_text", None)
    if callable(add_text):
        add_text(title, position="upper_left", font_size=10)


def _draw_surface(plotter: Any, request: PlotRenderRequest) -> None:
    series = request.series[0]
    plotter.add_mesh(
        _surface_grid(series),
        cmap=_colormap(request),
        show_edges=bool(request.options.get("show_edges", False)),
    )


def _draw_point_cloud(plotter: Any, request: PlotRenderRequest) -> None:
    pyvista = _pyvista()
    point_size = float(request.options.get("point_size", request.series[0].get("point_size", 5.0)))
    for series in request.series:
        cloud = pyvista.PolyData(_point_cloud_points(series))
        scalars = _first_present(series, "scalars", "values")
        kwargs: dict[str, Any] = {"point_size": point_size, "render_points_as_spheres": True}
        if scalars is not None:
            kwargs["scalars"] = _as_array(scalars, name="point cloud scalars")
            kwargs["cmap"] = _colormap(request)
        plotter.add_points(cloud, **kwargs)


def _draw_streamlines(plotter: Any, request: PlotRenderRequest) -> None:
    pyvista = _pyvista()
    numpy = _numpy()
    line_width = float(request.options.get("line_width", 2.0))
    for series in request.series:
        points = _streamline_points(series)
        polyline = pyvista.PolyData(points)
        polyline.lines = numpy.hstack(([points.shape[0]], numpy.arange(points.shape[0]))).astype(numpy.int_)
        plotter.add_mesh(
            polyline,
            color=str(series.get("color") or request.options.get("color") or "white"),
            line_width=float(series.get("line_width", line_width)),
            render_lines_as_tubes=bool(request.options.get("render_lines_as_tubes", True)),
        )


def _apply_metadata(plotter: Any, request: PlotRenderRequest) -> None:
    if request.title:
        add_title = getattr(plotter, "add_title", None)
        add_text = getattr(plotter, "add_text", None)
        if callable(add_title):
            add_title(request.title, font_size=10)
        elif callable(add_text):
            add_text(request.title, position="upper_left", font_size=10)
    if bool(request.options.get("axes", True)):
        add_axes = getattr(plotter, "add_axes", None)
        if callable(add_axes):
            add_axes()
    reset_camera = getattr(plotter, "reset_camera", None)
    if callable(reset_camera):
        reset_camera()


class PyVistaLive3DPlotBackend:
    backend_id = PYVISTA_PLOT_BACKEND_ID

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        try:
            from pyvistaqt import QtInteractor
        except ImportError as exc:
            raise RuntimeError(
                "pyvistaqt is required for live 3D plot rendering. "
                "Install the viewer optional dependencies to enable 3D plot widgets."
            ) from exc
        platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        off_screen = platform in {"minimal", "offscreen"}
        return QtInteractor(parent=parent, auto_update=False, off_screen=off_screen)

    def render_widget(self, widget: QWidget, request: PlotRenderRequest) -> None:
        self._clear(widget)
        self._draw(widget, request)
        self._render(widget)

    def export_static(self, request: PlotStaticExportRequest) -> PlotExportResult:
        if not pyvista_static_export_supported():
            raise RuntimeError("PyVista off-screen static export is not supported by this environment.")
        render_request = request.render_request
        if render_request.plot_type not in PYVISTA_LIVE_3D_PLOT_TYPES:
            raise ValueError(f"PyVista static export does not support {render_request.plot_type!r}.")
        output_path = _prepare_output_path(Path(request.output_path))
        export_format = _resolve_format(output_path, request.format)
        pyvista = _pyvista()
        plotter = pyvista.Plotter(off_screen=True, window_size=_plotter_size(request))
        try:
            self._draw(plotter, render_request)
            plotter.screenshot(str(output_path), transparent_background=request.transparent)
        finally:
            close = getattr(plotter, "close", None)
            if callable(close):
                close()
        return PlotExportResult(
            backend_id=self.backend_id,
            output_path=output_path,
            format=export_format,
            metadata={
                "plot_type": render_request.plot_type,
                "series_count": len(render_request.series),
                "headless_safe": True,
            },
        )

    def _draw(self, plotter: Any, request: PlotRenderRequest) -> None:
        if request.plot_type not in PYVISTA_LIVE_3D_PLOT_TYPES:
            raise ValueError(f"PyVista live rendering does not support {request.plot_type!r}.")
        if not request.series:
            _draw_empty(plotter, request)
            _apply_metadata(plotter, request)
            return
        if request.plot_type == PLOT_TYPE_SURFACE:
            _draw_surface(plotter, request)
        elif request.plot_type == PLOT_TYPE_POINT_CLOUD:
            _draw_point_cloud(plotter, request)
        elif request.plot_type == PLOT_TYPE_STREAMLINES:
            _draw_streamlines(plotter, request)
        else:
            raise ValueError(f"PyVista live rendering does not support {request.plot_type!r}.")
        _apply_metadata(plotter, request)

    @staticmethod
    def _clear(widget: QWidget) -> None:
        clear = getattr(widget, "clear", None)
        if callable(clear):
            clear()

    @staticmethod
    def _render(widget: QWidget) -> None:
        render = getattr(widget, "render", None)
        if callable(render):
            render()


@lru_cache(maxsize=1)
def pyvista_static_export_supported() -> bool:
    try:
        pyvista = _pyvista()
    except RuntimeError:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="ea_plot_pyvista_probe_") as temp_dir:
            output_path = Path(temp_dir) / "probe.png"
            plotter = pyvista.Plotter(off_screen=True, window_size=(16, 16))
            try:
                plotter.add_mesh(pyvista.Sphere(theta_resolution=4, phi_resolution=4))
                plotter.screenshot(str(output_path))
                return output_path.exists() and output_path.stat().st_size > 0
            finally:
                close = getattr(plotter, "close", None)
                if callable(close):
                    close()
    except Exception:  # noqa: BLE001
        return False


def create_pyvista_plot_backend_record() -> PlotBackendRecord:
    capabilities = [
        PlotCapability(plot_type=plot_type, surface=PLOT_SURFACE_LIVE)
        for plot_type in PYVISTA_LIVE_3D_PLOT_TYPES
    ]
    headless_safe_surfaces: tuple[str, ...] = ()
    metadata: dict[str, Any] = {
        "live_renderer": True,
        "qt_required": True,
        "headless_safe": False,
    }
    if pyvista_static_export_supported():
        capabilities.extend(
            PlotCapability(plot_type=plot_type, surface=PLOT_SURFACE_STATIC_EXPORT)
            for plot_type in PYVISTA_LIVE_3D_PLOT_TYPES
        )
        headless_safe_surfaces = (PLOT_SURFACE_STATIC_EXPORT,)
        metadata.update(
            {
                "headless_safe": True,
                "static_export_formats": PYVISTA_STATIC_EXPORT_FORMATS,
                "off_screen_static_export": True,
            }
        )
    return PlotBackendRecord(
        backend_id=PYVISTA_PLOT_BACKEND_ID,
        display_name=PYVISTA_PLOT_BACKEND_DISPLAY_NAME,
        factory=PyVistaLive3DPlotBackend,
        capabilities=tuple(capabilities),
        headless_safe_surfaces=headless_safe_surfaces,
        metadata=metadata,
    )


__all__ = [
    "PYVISTA_LIVE_3D_PLOT_TYPES",
    "PYVISTA_PLOT_BACKEND_DISPLAY_NAME",
    "PYVISTA_PLOT_BACKEND_ID",
    "PYVISTA_STATIC_EXPORT_FORMATS",
    "PyVistaLive3DPlotBackend",
    "create_pyvista_plot_backend_record",
    "pyvista_static_export_supported",
]
