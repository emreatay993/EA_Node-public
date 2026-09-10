from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

PLOT_SURFACE_LIVE = "live"
PLOT_SURFACE_STATIC_EXPORT = "static_export"
PLOT_SURFACE_DATA_EXPORT = "data_export"
PLOT_SURFACES = (
    PLOT_SURFACE_LIVE,
    PLOT_SURFACE_STATIC_EXPORT,
    PLOT_SURFACE_DATA_EXPORT,
)

PLOT_TYPE_LINE = "line"
PLOT_TYPE_SCATTER = "scatter"
PLOT_TYPE_BAR = "bar"
PLOT_TYPE_HISTOGRAM = "histogram"
PLOT_TYPE_HEATMAP = "heatmap"
PLOT_TYPE_CONTOUR = "contour"
PLOT_TYPE_SURFACE = "surface"
PLOT_TYPE_POINT_CLOUD = "point_cloud"
PLOT_TYPE_STREAMLINES = "streamlines"
V1_PLOT_TYPES = (
    PLOT_TYPE_LINE,
    PLOT_TYPE_SCATTER,
    PLOT_TYPE_BAR,
    PLOT_TYPE_HISTOGRAM,
    PLOT_TYPE_HEATMAP,
    PLOT_TYPE_CONTOUR,
    PLOT_TYPE_SURFACE,
    PLOT_TYPE_POINT_CLOUD,
    PLOT_TYPE_STREAMLINES,
)

AUTO_PLOT_BACKEND_ID = "auto"
GENERIC_PLOT_SERIES_RUNTIME_SHAPES = (
    "numpy arrays",
    "lists of numbers",
    "dict-of-arrays",
)
_SUPPORTED_PLOT_SURFACES = set(PLOT_SURFACES)


def normalize_plot_type(value: object) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized:
        raise ValueError("plot_type is required")
    return normalized


def normalize_plot_surface(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _SUPPORTED_PLOT_SURFACES:
        raise ValueError(f"Unknown plot surface: {normalized!r}.")
    return normalized


def _normalize_backend_id(value: object, *, field_name: str = "backend_id") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_format(value: object) -> str:
    return str(value or "").strip().lower().lstrip(".")


def _normalize_series_tuple(value: object) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        raw_series: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_series = value
    else:
        raise TypeError("plot series must be a mapping or sequence of mappings")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_series):
        if not isinstance(item, Mapping):
            raise TypeError(f"plot series item {index} must be a mapping")
        normalized.append(dict(item))
    return tuple(normalized)


def _as_runtime_shape_value(value: object) -> object:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return value


def normalize_generic_plot_series(value: object) -> tuple[dict[str, Any], ...]:
    """Coerce generic plot node runtime input into backend series mappings.

    The generic node family intentionally keeps numpy optional. Array-like
    inputs are detected structurally by ``tolist()`` instead of importing
    numpy in the core execution contract.
    """

    normalized_value = _as_runtime_shape_value(value)
    if normalized_value is None:
        return ()
    if isinstance(normalized_value, Mapping):
        return (dict(normalized_value),)
    if isinstance(normalized_value, Sequence) and not isinstance(
        normalized_value,
        (str, bytes, bytearray),
    ):
        raw_items = [_as_runtime_shape_value(item) for item in normalized_value]
        if not raw_items:
            return ()
        if all(isinstance(item, Mapping) for item in raw_items):
            return tuple(dict(item) for item in raw_items if isinstance(item, Mapping))
        return ({"values": raw_items},)
    return ({"values": [normalized_value]},)


@dataclass(slots=True, frozen=True, order=True)
class PlotCapability:
    plot_type: str
    surface: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "plot_type", normalize_plot_type(self.plot_type))
        object.__setattr__(self, "surface", normalize_plot_surface(self.surface))

    @classmethod
    def from_value(cls, value: object) -> "PlotCapability":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(
                plot_type=value.get("plot_type"),  # type: ignore[arg-type]
                surface=value.get("surface"),  # type: ignore[arg-type]
            )
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if len(value) != 2:
                raise ValueError("plot capability tuple must contain plot_type and surface")
            return cls(plot_type=value[0], surface=value[1])  # type: ignore[arg-type]
        raise TypeError("plot capability must be a PlotCapability, mapping, or 2-item sequence")


@dataclass(slots=True, frozen=True)
class PlotRenderRequest:
    plot_type: str
    series: tuple[Mapping[str, Any], ...] = ()
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "plot_type", normalize_plot_type(self.plot_type))
        object.__setattr__(self, "series", _normalize_series_tuple(self.series))
        object.__setattr__(self, "title", str(self.title or "").strip())
        object.__setattr__(self, "x_label", str(self.x_label or "").strip())
        object.__setattr__(self, "y_label", str(self.y_label or "").strip())
        object.__setattr__(self, "options", dict(self.options or {}))


def _json_safe_plot_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_plot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe_plot_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def plot_render_request_to_payload(request: PlotRenderRequest) -> dict[str, Any]:
    if not isinstance(request, PlotRenderRequest):
        raise TypeError("request must be a PlotRenderRequest")
    return {
        "plot_type": request.plot_type,
        "series": _json_safe_plot_value(request.series),
        "title": request.title,
        "x_label": request.x_label,
        "y_label": request.y_label,
        "options": _json_safe_plot_value(request.options),
    }


def plot_render_request_from_payload(payload: Mapping[str, Any]) -> PlotRenderRequest:
    return PlotRenderRequest(
        plot_type=payload.get("plot_type"),
        series=normalize_generic_plot_series(payload.get("series")),
        title=str(payload.get("title") or "").strip(),
        x_label=str(payload.get("x_label") or "").strip(),
        y_label=str(payload.get("y_label") or "").strip(),
        options=dict(payload.get("options") or {}) if isinstance(payload.get("options"), Mapping) else {},
    )


def plot_options_from_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    raw_options = properties.get("plot_options")
    options = dict(raw_options) if isinstance(raw_options, Mapping) else {}
    axis_limits = properties.get("axis_limits")
    log_scales = properties.get("log_scales")
    options.update(
        {
            "axis_limits": dict(axis_limits) if isinstance(axis_limits, Mapping) else {},
            "log_scales": dict(log_scales) if isinstance(log_scales, Mapping) else {},
            "grid": bool(properties.get("grid", True)),
            "legend": bool(properties.get("legend", True)),
            "render_in_canvas": bool(properties.get("render_in_canvas", True)),
            "z_label": str(properties.get("z_label") or "").strip(),
        }
    )
    colormap = str(properties.get("colormap") or "").strip()
    if colormap:
        options["cmap"] = colormap
    return options


def build_plot_render_request(
    *,
    plot_type: str,
    properties: Mapping[str, Any],
    series: Any,
    options: Mapping[str, Any] | None = None,
) -> PlotRenderRequest:
    resolved_options = dict(options) if isinstance(options, Mapping) else plot_options_from_properties(properties)
    return PlotRenderRequest(
        plot_type=plot_type,
        series=normalize_generic_plot_series(series),
        title=str(properties.get("title") or "").strip(),
        x_label=str(properties.get("x_label") or "").strip(),
        y_label=str(properties.get("y_label") or "").strip(),
        options=resolved_options,
    )


@dataclass(slots=True, frozen=True)
class PlotStaticExportRequest:
    render_request: PlotRenderRequest
    output_path: str | os.PathLike[str]
    format: str = ""
    width_inches: float = 6.4
    height_inches: float = 4.8
    dpi: int = 100
    transparent: bool = False
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.render_request, PlotRenderRequest):
            raise TypeError("render_request must be a PlotRenderRequest")
        object.__setattr__(self, "output_path", Path(self.output_path))
        object.__setattr__(self, "format", _normalize_optional_format(self.format))
        object.__setattr__(self, "width_inches", float(self.width_inches))
        object.__setattr__(self, "height_inches", float(self.height_inches))
        object.__setattr__(self, "dpi", int(self.dpi))
        object.__setattr__(self, "transparent", bool(self.transparent))
        object.__setattr__(self, "options", dict(self.options or {}))


@dataclass(slots=True, frozen=True)
class PlotDataExportRequest:
    render_request: PlotRenderRequest
    output_path: str | os.PathLike[str]
    format: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.render_request, PlotRenderRequest):
            raise TypeError("render_request must be a PlotRenderRequest")
        object.__setattr__(self, "output_path", Path(self.output_path))
        object.__setattr__(self, "format", _normalize_optional_format(self.format))
        object.__setattr__(self, "options", dict(self.options or {}))


@dataclass(slots=True, frozen=True)
class PlotExportResult:
    backend_id: str
    output_path: Path
    format: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_id", _normalize_backend_id(self.backend_id))
        object.__setattr__(self, "output_path", Path(self.output_path))
        object.__setattr__(self, "format", _normalize_optional_format(self.format))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


class PlotBackend(Protocol):
    backend_id: str

    def export_static(self, request: PlotStaticExportRequest) -> PlotExportResult:
        ...

    def export_data(self, request: PlotDataExportRequest) -> PlotExportResult:
        ...


@dataclass(slots=True, frozen=True)
class PlotBackendRecord:
    backend_id: str
    display_name: str
    factory: Callable[[], PlotBackend]
    capabilities: Iterable[PlotCapability | Mapping[str, Any] | Sequence[str]]
    headless_safe_surfaces: Iterable[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_id", _normalize_backend_id(self.backend_id))
        display_name = str(self.display_name or "").strip() or self.backend_id
        object.__setattr__(self, "display_name", display_name)
        if not callable(self.factory):
            raise TypeError("plot backend factory must be callable")

        capabilities = frozenset(PlotCapability.from_value(item) for item in self.capabilities)
        if not capabilities:
            raise ValueError("plot backend capabilities are required")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(
            self,
            "headless_safe_surfaces",
            frozenset(normalize_plot_surface(surface) for surface in self.headless_safe_surfaces),
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def supports(self, *, plot_type: str, surface: str) -> bool:
        return PlotCapability(plot_type=plot_type, surface=surface) in self.capabilities

    def is_headless_safe_for(self, surface: str) -> bool:
        return normalize_plot_surface(surface) in self.headless_safe_surfaces


class PlotBackendRegistry:
    def __init__(self) -> None:
        self._records: dict[str, PlotBackendRecord] = {}

    def register_record(self, record: PlotBackendRecord) -> None:
        if not isinstance(record, PlotBackendRecord):
            raise TypeError("plot backend registration must be a PlotBackendRecord")
        self._records[record.backend_id] = record

    register = register_record

    @property
    def backend_ids(self) -> tuple[str, ...]:
        return tuple(self._records)

    def records(self) -> tuple[PlotBackendRecord, ...]:
        return tuple(self._records.values())

    def get_record(self, backend_id: str) -> PlotBackendRecord:
        normalized_backend_id = _normalize_backend_id(backend_id)
        try:
            return self._records[normalized_backend_id]
        except KeyError as exc:
            raise LookupError(f"Unknown plot backend: {normalized_backend_id!r}.") from exc

    def records_for(
        self,
        *,
        plot_type: str,
        surface: str,
        require_headless_safe: bool = False,
    ) -> tuple[PlotBackendRecord, ...]:
        normalized_plot_type = normalize_plot_type(plot_type)
        normalized_surface = normalize_plot_surface(surface)
        return tuple(
            record
            for record in self._records.values()
            if record.supports(plot_type=normalized_plot_type, surface=normalized_surface)
            and (not require_headless_safe or record.is_headless_safe_for(normalized_surface))
        )

    def resolve_record(
        self,
        backend_id: str,
        *,
        plot_type: str,
        surface: str,
        plot_default_backend_per_type: Mapping[str, str] | None = None,
        require_headless_safe: bool = False,
    ) -> PlotBackendRecord:
        normalized_plot_type = normalize_plot_type(plot_type)
        normalized_surface = normalize_plot_surface(surface)
        resolved_backend_id = self._resolve_backend_id(
            backend_id,
            plot_type=normalized_plot_type,
            surface=normalized_surface,
            plot_default_backend_per_type=plot_default_backend_per_type,
        )
        record = self.get_record(resolved_backend_id)
        if not record.supports(plot_type=normalized_plot_type, surface=normalized_surface):
            raise LookupError(
                f"Plot backend {record.backend_id!r} does not support plot type "
                f"{normalized_plot_type!r} on surface {normalized_surface!r}."
            )
        if require_headless_safe and not record.is_headless_safe_for(normalized_surface):
            raise LookupError(
                f"Plot backend {record.backend_id!r} is not marked headless-safe for "
                f"surface {normalized_surface!r}."
            )
        return record

    def resolve(
        self,
        backend_id: str,
        *,
        plot_type: str,
        surface: str,
        plot_default_backend_per_type: Mapping[str, str] | None = None,
        require_headless_safe: bool = False,
    ) -> PlotBackend:
        record = self.resolve_record(
            backend_id,
            plot_type=plot_type,
            surface=surface,
            plot_default_backend_per_type=plot_default_backend_per_type,
            require_headless_safe=require_headless_safe,
        )
        backend = record.factory()
        materialized_backend_id = _normalize_backend_id(
            getattr(backend, "backend_id", ""),
            field_name="plot backend factory result backend_id",
        )
        if materialized_backend_id != record.backend_id:
            raise ValueError(
                f"Plot backend factory for {record.backend_id!r} returned backend "
                f"{materialized_backend_id!r}."
            )
        return backend

    def _resolve_backend_id(
        self,
        backend_id: str,
        *,
        plot_type: str,
        surface: str,
        plot_default_backend_per_type: Mapping[str, str] | None,
    ) -> str:
        normalized_backend_id = _normalize_backend_id(backend_id)
        if normalized_backend_id.lower() != AUTO_PLOT_BACKEND_ID:
            return normalized_backend_id

        normalized_defaults = {
            normalize_plot_type(key): str(value or "").strip()
            for key, value in dict(plot_default_backend_per_type or {}).items()
        }
        default_backend_id = normalized_defaults.get(plot_type) or normalized_defaults.get("default")
        if not default_backend_id:
            raise LookupError(f"No default plot backend configured for plot type {plot_type!r}.")
        if default_backend_id.lower() == AUTO_PLOT_BACKEND_ID:
            raise LookupError(f"Default plot backend for plot type {plot_type!r} cannot be 'auto'.")
        if default_backend_id not in self._records:
            raise LookupError(
                f"Default plot backend {default_backend_id!r} for plot type {plot_type!r} "
                f"and surface {surface!r} is not registered."
            )
        return default_backend_id


def create_builtin_plot_backend_records() -> tuple[PlotBackendRecord, ...]:
    from ea_node_editor.execution.plot_backend_matplotlib import (
        create_matplotlib_plot_backend_record,
    )
    from ea_node_editor.execution.plot_backend_pyqtgraph import (
        create_pyqtgraph_plot_backend_record,
    )
    from ea_node_editor.execution.plot_backend_pyvista import (
        create_pyvista_plot_backend_record,
    )

    return (
        create_matplotlib_plot_backend_record(),
        create_pyqtgraph_plot_backend_record(),
        create_pyvista_plot_backend_record(),
    )


def create_plot_backend_registry(
    backend_records: Iterable[PlotBackendRecord] = (),
) -> PlotBackendRegistry:
    registry = PlotBackendRegistry()
    for record in create_builtin_plot_backend_records():
        registry.register_record(record)
    for record in backend_records:
        registry.register_record(record)
    return registry


def create_default_plot_backend_registry(
    *,
    backend_records: Iterable[PlotBackendRecord] | None = None,
    preferences_document: Any = None,
    store: Any = None,
) -> PlotBackendRegistry:
    if backend_records is None:
        from ea_node_editor.addons.catalog import create_live_execution_plot_backends

        backend_records = create_live_execution_plot_backends(
            preferences_document=preferences_document,
            store=store,
        )
    return create_plot_backend_registry(backend_records)


__all__ = [
    "AUTO_PLOT_BACKEND_ID",
    "GENERIC_PLOT_SERIES_RUNTIME_SHAPES",
    "PLOT_SURFACE_DATA_EXPORT",
    "PLOT_SURFACE_LIVE",
    "PLOT_SURFACE_STATIC_EXPORT",
    "PLOT_SURFACES",
    "PLOT_TYPE_BAR",
    "PLOT_TYPE_CONTOUR",
    "PLOT_TYPE_HEATMAP",
    "PLOT_TYPE_HISTOGRAM",
    "PLOT_TYPE_LINE",
    "PLOT_TYPE_POINT_CLOUD",
    "PLOT_TYPE_SCATTER",
    "PLOT_TYPE_STREAMLINES",
    "PLOT_TYPE_SURFACE",
    "PlotBackend",
    "PlotBackendRecord",
    "PlotBackendRegistry",
    "PlotCapability",
    "PlotDataExportRequest",
    "PlotExportResult",
    "PlotRenderRequest",
    "PlotStaticExportRequest",
    "V1_PLOT_TYPES",
    "build_plot_render_request",
    "create_builtin_plot_backend_records",
    "create_default_plot_backend_registry",
    "create_plot_backend_registry",
    "normalize_generic_plot_series",
    "normalize_plot_surface",
    "normalize_plot_type",
    "plot_options_from_properties",
    "plot_render_request_from_payload",
    "plot_render_request_to_payload",
]
