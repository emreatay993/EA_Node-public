from __future__ import annotations

from ea_node_editor.execution.plot_backend import (
    AUTO_PLOT_BACKEND_ID,
    PLOT_SURFACE_LIVE,
    PlotBackendRegistry,
    normalize_plot_type,
)
from ea_node_editor.execution.plot_backend_matplotlib import (
    MATPLOTLIB_2D_PLOT_TYPES,
    MATPLOTLIB_PLOT_BACKEND_ID,
)
from ea_node_editor.execution.plot_backend_pyqtgraph import (
    PYQTGRAPH_LIVE_2D_PLOT_TYPES,
    PYQTGRAPH_PLOT_BACKEND_ID,
)
from ea_node_editor.execution.plot_backend_pyvista import (
    PYVISTA_LIVE_3D_PLOT_TYPES,
    PYVISTA_PLOT_BACKEND_ID,
)

_BUILTIN_LIVE_BACKEND_BY_PLOT_TYPE = {
    **{plot_type: PYQTGRAPH_PLOT_BACKEND_ID for plot_type in PYQTGRAPH_LIVE_2D_PLOT_TYPES},
    **{plot_type: PYVISTA_PLOT_BACKEND_ID for plot_type in PYVISTA_LIVE_3D_PLOT_TYPES},
}


def _auto_live_backend_id(registry: PlotBackendRegistry, *, plot_type: str) -> str:
    live_records = registry.records_for(plot_type=plot_type, surface=PLOT_SURFACE_LIVE)
    for record in live_records:
        if record.backend_id == PYQTGRAPH_PLOT_BACKEND_ID:
            return record.backend_id
    return live_records[0].backend_id if live_records else ""


def resolve_plot_live_backend_id(
    registry: PlotBackendRegistry,
    *,
    plot_type: str,
    requested_backend_id: str,
) -> str:
    normalized_plot_type = normalize_plot_type(plot_type)
    normalized_backend_id = str(requested_backend_id or AUTO_PLOT_BACKEND_ID).strip()
    if normalized_backend_id.lower() != AUTO_PLOT_BACKEND_ID:
        try:
            record = registry.resolve_record(
                normalized_backend_id,
                plot_type=normalized_plot_type,
                surface=PLOT_SURFACE_LIVE,
            )
        except LookupError:
            return ""
        return record.backend_id

    return _auto_live_backend_id(registry, plot_type=normalized_plot_type)


def builtin_plot_live_backend_id(*, plot_type: str, requested_backend_id: str) -> str:
    normalized_plot_type = normalize_plot_type(plot_type)
    normalized_backend_id = str(requested_backend_id or AUTO_PLOT_BACKEND_ID).strip().lower()
    if normalized_backend_id == AUTO_PLOT_BACKEND_ID:
        return _BUILTIN_LIVE_BACKEND_BY_PLOT_TYPE.get(normalized_plot_type, "")
    if normalized_backend_id == MATPLOTLIB_PLOT_BACKEND_ID:
        return normalized_backend_id if normalized_plot_type in MATPLOTLIB_2D_PLOT_TYPES else ""
    if normalized_backend_id == PYQTGRAPH_PLOT_BACKEND_ID and normalized_plot_type in PYQTGRAPH_LIVE_2D_PLOT_TYPES:
        return normalized_backend_id
    if normalized_backend_id == PYVISTA_PLOT_BACKEND_ID and normalized_plot_type in PYVISTA_LIVE_3D_PLOT_TYPES:
        return normalized_backend_id
    return ""


__all__ = [
    "builtin_plot_live_backend_id",
    "resolve_plot_live_backend_id",
]
