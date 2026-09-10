from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QUrl

from ea_node_editor.addons.tabular_data.input_node import tabular_load_options_from_node_properties
from ea_node_editor.addons.tabular_data.loader_cache_service import (
    LargeDataMaterializationError,
    MissingTabularDependencyError,
    SelectionRequiredError,
    SourceScanResult,
    TabularCacheNotReadyError,
    TabularLoaderCacheService,
    UnsupportedTabularFormatError,
    shared_tabular_loader_cache_service,
)
from ea_node_editor.persistence.artifact_resolution import ArtifactResolution, ProjectArtifactResolver
from ea_node_editor.runtime_contracts import (
    ArrayDataRef,
    ArraySlice2D,
    ArraySlice2DRequest,
    TabularDataRef,
    TabularDataWindow,
    TabularSchema,
    TabularWindowRequest,
)

TABULAR_PREVIEW_CONTENT_KIND = "tabular"
TABULAR_PREVIEW_INLINE_ROW_LIMIT = 50
TABULAR_PREVIEW_INLINE_COLUMN_LIMIT = 50
TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT = 50
TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT = 50
TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT = 500
TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT = 200
TABULAR_PREVIEW_INLINE_PAYLOAD_CACHE_LIMIT = 32

_ProjectContext = tuple[str | Path | None, dict[str, Any] | None]
_ProjectContextProvider = Callable[[], _ProjectContext | None]
_ServiceFactory = Callable[[], TabularLoaderCacheService]


@dataclass(frozen=True, slots=True)
class _PreviewSession:
    session_id: str
    service: Any
    ref: TabularDataRef | ArrayDataRef
    source: dict[str, Any]
    selector: dict[str, Any]
    scan: SourceScanResult
    inline_payload_cache: dict[str, dict[str, Any]] = field(default_factory=dict)


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe_value(value.item())
    return str(value)


def _json_safe_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    safe = _json_safe_value(value)
    return dict(safe) if isinstance(safe, Mapping) else {}


def _properties_from_value(value: Mapping[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if isinstance(value, str):
        return {"path": value}
    return {}


def _request_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    return {}


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return min(default, maximum)
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    if normalized <= 0:
        normalized = default
    return max(1, min(normalized, maximum))


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, normalized)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values: Sequence[Any] = [segment.strip() for segment in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        return ()
    return tuple(str(item).strip() for item in values if str(item).strip())


def _has_backend_query_operations(request: Mapping[str, Any]) -> bool:
    for key in ("sort", "filters", "filter", "search"):
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, Mapping) and value:
            return True
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and value:
            return True
    return False


def _payload_from_ref(ref: TabularDataRef | ArrayDataRef) -> dict[str, Any]:
    return ref.to_payload()


def _resolved_source_url(path: Path | None) -> str:
    if path is None:
        return ""
    return QUrl.fromLocalFile(str(path)).toString()


def _source_payload(
    source_value: str,
    resolution: ArtifactResolution,
    path: Path | None,
    *,
    scan: SourceScanResult | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": source_value,
        "resolution_kind": resolution.kind,
        "artifact_id": resolution.artifact_id or "",
        "resolved_path": str(path) if path is not None else "",
        "resolved_source_url": _resolved_source_url(path),
    }
    if scan is not None:
        payload.update(
            {
                "format_id": scan.format_id,
                "size_bytes": int(scan.size_bytes),
                "size_class": str(scan.size_class or ""),
            }
        )
    return payload


def _request_contracts() -> dict[str, Any]:
    return {
        "content_kind": TABULAR_PREVIEW_CONTENT_KIND,
        "table_window": {
            "slot": "request_tabular_window",
            "bounded": True,
            "client_side_full_scan": False,
            "request_keys": [
                "row_offset",
                "row_limit",
                "column_offset",
                "column_limit",
                "columns",
                "sort",
                "filters",
                "search",
            ],
            "backend_operations": {
                "row_window": True,
                "column_window": True,
                "sort": "resolver",
                "filters": "resolver",
                "search": "resolver",
            },
            "max_row_limit": TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT,
            "max_column_limit": TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT,
        },
        "array_slice_2d": {
            "slot": "request_tabular_slice_2d",
            "bounded": True,
            "client_side_full_scan": False,
            "request_keys": ["row_offset", "row_limit", "column_offset", "column_limit"],
            "max_row_limit": TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT,
            "max_column_limit": TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT,
        },
    }


def _base_payload(state: str, message: str = "") -> dict[str, Any]:
    return {
        "state": state,
        "message": message,
        "content_kind": TABULAR_PREVIEW_CONTENT_KIND,
        "preview_kind": "",
        "request_contracts": _request_contracts(),
        "limits": {
            "inline_row_limit": TABULAR_PREVIEW_INLINE_ROW_LIMIT,
            "inline_column_limit": TABULAR_PREVIEW_INLINE_COLUMN_LIMIT,
            "fullscreen_first_paint_row_limit": TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT,
            "fullscreen_first_paint_column_limit": TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT,
            "max_window_row_limit": TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT,
            "max_window_column_limit": TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT,
        },
    }


def _error_payload(
    message: str,
    *,
    code: str,
    source: dict[str, Any] | None = None,
    selector: dict[str, Any] | None = None,
    recoverable: bool = True,
) -> dict[str, Any]:
    payload = _base_payload("error", message)
    payload["source"] = copy.deepcopy(source or {})
    payload["selector"] = copy.deepcopy(selector or {})
    payload["error"] = {
        "code": code,
        "message": message,
        "recoverable": bool(recoverable),
    }
    return payload


def _selector_payload(scan: SourceScanResult, selected_object: str) -> dict[str, Any]:
    return {
        "selected_object": str(selected_object or scan.selected_object_id or ""),
        "requires_selection": bool(scan.requires_selection),
        "objects": [item.to_payload() for item in scan.objects],
    }


def _window_request_payload(request: TabularWindowRequest, source_request: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "row_offset": request.row_offset,
        "row_limit": request.row_limit,
        "column_offset": request.column_offset,
        "column_limit": request.column_limit,
        "columns": list(request.columns),
    }
    for key in ("sort", "filters", "filter", "search"):
        if key in source_request:
            payload[key] = _json_safe_value(source_request[key])
    return payload


def _slice_request_payload(request: ArraySlice2DRequest) -> dict[str, int]:
    return {
        "row_offset": request.row_offset,
        "row_limit": request.row_limit,
        "column_offset": request.column_offset,
        "column_limit": request.column_limit,
    }


def _inline_payload_cache_key(
    *,
    preview_kind: str,
    mode: str,
    request_payload: Mapping[str, Any],
    include_schema: bool = False,
) -> str:
    if mode != "inline":
        return ""
    payload = {
        "preview_kind": preview_kind,
        "request": _json_safe_mapping(request_payload),
    }
    if preview_kind == "table":
        payload["include_schema"] = bool(include_schema)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _cached_inline_payload(session: _PreviewSession, cache_key: str) -> dict[str, Any] | None:
    if not cache_key:
        return None
    cached = session.inline_payload_cache.get(cache_key)
    return copy.deepcopy(cached) if cached is not None else None


def _store_inline_payload(session: _PreviewSession, cache_key: str, payload: Mapping[str, Any]) -> None:
    if not cache_key:
        return
    cache = session.inline_payload_cache
    if cache_key not in cache and len(cache) >= TABULAR_PREVIEW_INLINE_PAYLOAD_CACHE_LIMIT:
        cache.pop(next(iter(cache)), None)
    cache[cache_key] = copy.deepcopy(dict(payload))


class TabularPreviewProvider:
    def __init__(
        self,
        *,
        service_factory: _ServiceFactory | None = None,
        project_context_provider: _ProjectContextProvider | None = None,
    ) -> None:
        self._service_factory = service_factory or shared_tabular_loader_cache_service
        self._project_context_provider = project_context_provider
        self._sessions: dict[str, _PreviewSession] = {}

    def describe_preview(
        self,
        properties_or_source: Mapping[str, Any] | str | None,
        request: Mapping[str, Any] | None = None,
        *,
        mode: str = "inline",
    ) -> dict[str, Any]:
        properties = _properties_from_value(properties_or_source)
        raw_source = str(properties.get("path", "") or "").strip()
        if not raw_source:
            payload = _base_payload("placeholder", "Choose a tabular data file to preview it here.")
            payload["source"] = _source_payload("", self._resolver().resolve(""), None)
            payload["selector"] = {}
            return payload

        session_result = self._session_for_properties(properties)
        if isinstance(session_result, dict):
            return session_result
        session = session_result
        if isinstance(session.ref, TabularDataRef):
            return self.table_window_payload(
                properties,
                request,
                mode=mode,
                session=session,
                include_schema=True,
            )
        return self.array_slice_payload(
            properties,
            request,
            mode=mode,
            session=session,
        )

    def describe_selector(self, properties_or_source: Mapping[str, Any] | str | None) -> dict[str, Any]:
        properties = _properties_from_value(properties_or_source)
        raw_source = str(properties.get("path", "") or "").strip()
        if not raw_source:
            payload = _base_payload("placeholder", "Choose a tabular data file to list sheets, keys, or datasets.")
            payload["source"] = _source_payload("", self._resolver().resolve(""), None)
            payload["selector"] = {}
            return payload
        return self._selector_for_properties(properties)

    def table_window_payload(
        self,
        properties_or_source: Mapping[str, Any] | str | None,
        request: Mapping[str, Any] | None = None,
        *,
        mode: str = "fullscreen",
        session: _PreviewSession | None = None,
        include_schema: bool = True,
    ) -> dict[str, Any]:
        properties = _properties_from_value(properties_or_source)
        session = session or self._session_for_properties(properties)
        if isinstance(session, dict):
            return session
        if not isinstance(session.ref, TabularDataRef):
            return _error_payload(
                "The selected tabular source is a dense array; request a 2D slice instead.",
                code="not_table_ref",
                source=session.source,
                selector=session.selector,
            )

        source_request = _request_mapping(request)
        window_request = self._table_request(source_request, mode=mode)
        request_payload = _window_request_payload(window_request, source_request)
        cache_key = _inline_payload_cache_key(
            preview_kind="table",
            mode=mode,
            request_payload=request_payload,
            include_schema=include_schema,
        )
        cached_payload = _cached_inline_payload(session, cache_key)
        if cached_payload is not None:
            return cached_payload
        query_ops = _has_backend_query_operations(source_request)
        try:
            if query_ops:
                backend_window = self._backend_table_window(session, window_request, source_request)
                if isinstance(backend_window, dict):
                    return backend_window
                window = backend_window
            else:
                window = session.service.window(session.ref, window_request)
        except TabularCacheNotReadyError as exc:
            return self._loading_payload(session, str(exc))

        payload = _base_payload("ready", "Tabular data preview is ready.")
        payload.update(
            {
                "preview_kind": "table",
                "session_id": session.session_id,
                "source": copy.deepcopy(session.source),
                "selector": copy.deepcopy(session.selector),
                "ref": _payload_from_ref(session.ref),
                "metadata": _json_safe_mapping(session.service.metadata(session.ref)),
                "warnings": self._warnings_for_ref(session.ref),
                "window": self._table_window_to_payload(window, window_request, source_request),
            }
        )
        if include_schema:
            payload["schema"] = self._schema_payload(session)
        _store_inline_payload(session, cache_key, payload)
        return payload

    def array_slice_payload(
        self,
        properties_or_source: Mapping[str, Any] | str | None,
        request: Mapping[str, Any] | None = None,
        *,
        mode: str = "fullscreen",
        session: _PreviewSession | None = None,
    ) -> dict[str, Any]:
        properties = _properties_from_value(properties_or_source)
        session = session or self._session_for_properties(properties)
        if isinstance(session, dict):
            return session
        if not isinstance(session.ref, ArrayDataRef):
            return _error_payload(
                "The selected tabular source is a table; request a row/column window instead.",
                code="not_array_ref",
                source=session.source,
                selector=session.selector,
            )

        slice_request = self._slice_request(_request_mapping(request), mode=mode)
        request_payload = _slice_request_payload(slice_request)
        cache_key = _inline_payload_cache_key(
            preview_kind="array",
            mode=mode,
            request_payload=request_payload,
        )
        cached_payload = _cached_inline_payload(session, cache_key)
        if cached_payload is not None:
            return cached_payload
        array_slice = session.service.slice_2d(session.ref, slice_request)
        payload = _base_payload("ready", "Dense array preview is ready.")
        payload.update(
            {
                "preview_kind": "array",
                "session_id": session.session_id,
                "source": copy.deepcopy(session.source),
                "selector": copy.deepcopy(session.selector),
                "ref": _payload_from_ref(session.ref),
                "metadata": _json_safe_mapping(session.service.metadata(session.ref)),
                "warnings": self._warnings_for_ref(session.ref),
                "array": {
                    "shape": list(session.ref.shape),
                    "dtype": session.ref.dtype,
                    "object_id": session.ref.object_id,
                },
                "slice_2d": self._array_slice_to_payload(array_slice, slice_request),
            }
        )
        _store_inline_payload(session, cache_key, payload)
        return payload

    def _selector_for_properties(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        raw_source = str(properties.get("path", "") or "").strip()
        resolution = self._resolver().resolve(raw_source)
        path = resolution.absolute_path
        source = _source_payload(raw_source, resolution, path)
        if path is None:
            return _error_payload(
                "Tabular selectors support absolute local paths and project-managed artifact refs.",
                code=resolution.kind or "unresolved_source",
                source=source,
            )
        if not path.is_file():
            return _error_payload(
                "Unable to find the selected tabular data file.",
                code="missing_source",
                source=source,
            )

        options = tabular_load_options_from_node_properties(properties)
        service = self._service_factory()
        try:
            scan = service.scan_source(path, options)
        except MissingTabularDependencyError as exc:
            return _error_payload(str(exc), code="missing_backend", source=source, recoverable=True)
        except UnsupportedTabularFormatError as exc:
            return _error_payload(str(exc), code="unsupported_format", source=source, recoverable=True)

        selector = _selector_payload(scan, options.selected_object)
        payload_state = "selection_required" if scan.requires_selection and not options.selected_object else "ready"
        payload_message = (
            "Select a sheet, key, or dataset before previewing this source."
            if payload_state == "selection_required"
            else "Tabular source objects are ready."
        )
        payload = _base_payload(payload_state, payload_message)
        payload["source"] = _source_payload(raw_source, resolution, path, scan=scan)
        payload["selector"] = selector
        if payload_state == "selection_required":
            payload["error"] = {
                "code": "selector_required",
                "message": payload_message,
                "recoverable": True,
            }
        return payload

    def _session_for_properties(self, properties: Mapping[str, Any]) -> _PreviewSession | dict[str, Any]:
        raw_source = str(properties.get("path", "") or "").strip()
        resolution = self._resolver().resolve(raw_source)
        path = resolution.absolute_path
        source = _source_payload(raw_source, resolution, path)
        if path is None:
            return _error_payload(
                "Tabular previews support absolute local paths and project-managed artifact refs.",
                code=resolution.kind or "unresolved_source",
                source=source,
            )
        if not path.is_file():
            return _error_payload(
                "Unable to find the selected tabular data file.",
                code="missing_source",
                source=source,
            )

        options = tabular_load_options_from_node_properties(properties)
        session_id = self._session_id(path, options.to_cache_payload())
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached

        service = self._service_factory()
        try:
            scan = service.scan_source(path, options)
        except MissingTabularDependencyError as exc:
            return _error_payload(
                str(exc),
                code="missing_backend",
                source=source,
                recoverable=True,
            )
        except UnsupportedTabularFormatError as exc:
            return _error_payload(
                str(exc),
                code="unsupported_format",
                source=source,
                recoverable=True,
            )

        selector = _selector_payload(scan, options.selected_object)
        source = _source_payload(raw_source, resolution, path, scan=scan)
        if scan.requires_selection and not options.selected_object:
            payload = _base_payload(
                "selection_required",
                "Select a sheet, key, or dataset before previewing this source.",
            )
            payload["source"] = source
            payload["selector"] = selector
            payload["error"] = {
                "code": "selector_required",
                "message": payload["message"],
                "recoverable": True,
            }
            return payload

        try:
            ref = service.open_source(path, options)
        except SelectionRequiredError as exc:
            payload = _base_payload("selection_required", str(exc))
            payload["source"] = source
            payload["selector"] = {
                "selected_object": options.selected_object,
                "requires_selection": True,
                "objects": [choice.to_payload() for choice in exc.choices],
            }
            payload["error"] = {
                "code": "selector_required",
                "message": str(exc),
                "recoverable": True,
            }
            return payload
        except MissingTabularDependencyError as exc:
            return _error_payload(str(exc), code="missing_backend", source=source, selector=selector)
        except LargeDataMaterializationError as exc:
            return _error_payload(str(exc), code="large_data_materialization_gated", source=source, selector=selector)
        except UnsupportedTabularFormatError as exc:
            return _error_payload(str(exc), code="unsupported_format", source=source, selector=selector)

        session = _PreviewSession(
            session_id=session_id,
            service=service,
            ref=ref,
            source=source,
            selector=selector,
            scan=scan,
        )
        self._sessions[session_id] = session
        return session

    @staticmethod
    def _loading_payload(session: _PreviewSession, message: str) -> dict[str, Any]:
        payload = _base_payload("loading", message or "Preparing the tabular data cache…")
        payload.update(
            {
                "preview_kind": "table",
                "session_id": session.session_id,
                "source": copy.deepcopy(session.source),
                "selector": copy.deepcopy(session.selector),
                "ref": _payload_from_ref(session.ref),
            }
        )
        return payload

    def _resolver(self) -> ProjectArtifactResolver:
        context = self._project_context_provider() if callable(self._project_context_provider) else None
        project_path: str | Path | None = None
        project_metadata: dict[str, Any] | None = None
        if isinstance(context, tuple) and len(context) >= 2:
            project_path = context[0]
            metadata = context[1]
            if isinstance(metadata, dict):
                project_metadata = metadata
        return ProjectArtifactResolver(project_path=project_path, project_metadata=project_metadata)

    @staticmethod
    def _session_id(path: Path, options_payload: Mapping[str, Any]) -> str:
        try:
            stats = path.stat()
            stamp = {"mtime_ns": int(stats.st_mtime_ns), "size": int(stats.st_size)}
        except OSError:
            stamp = {"mtime_ns": 0, "size": 0}
        payload = {
            "path": str(path.resolve()),
            "stamp": stamp,
            "options": _json_safe_mapping(options_payload),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _warnings_for_ref(ref: TabularDataRef | ArrayDataRef) -> list[Any]:
        metadata = ref.metadata if isinstance(ref.metadata, Mapping) else {}
        warnings = metadata.get("warning_facts") or metadata.get("warnings") or []
        return _json_safe_value(warnings) if isinstance(warnings, list) else []

    @staticmethod
    def _table_request(request: Mapping[str, Any], *, mode: str) -> TabularWindowRequest:
        inline = str(mode or "").strip().lower() == "inline"
        default_rows = TABULAR_PREVIEW_INLINE_ROW_LIMIT if inline else TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT
        default_columns = TABULAR_PREVIEW_INLINE_COLUMN_LIMIT if inline else TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT
        max_rows = TABULAR_PREVIEW_INLINE_ROW_LIMIT if inline else TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT
        max_columns = TABULAR_PREVIEW_INLINE_COLUMN_LIMIT if inline else TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT
        return TabularWindowRequest(
            row_offset=_non_negative_int(request.get("row_offset", 0)),
            row_limit=_positive_int(request.get("row_limit"), default=default_rows, maximum=max_rows),
            column_offset=_non_negative_int(request.get("column_offset", 0)),
            column_limit=_positive_int(request.get("column_limit"), default=default_columns, maximum=max_columns),
            columns=_string_tuple(request.get("columns", ())),
        )

    @staticmethod
    def _slice_request(request: Mapping[str, Any], *, mode: str) -> ArraySlice2DRequest:
        inline = str(mode or "").strip().lower() == "inline"
        default_rows = TABULAR_PREVIEW_INLINE_ROW_LIMIT if inline else TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT
        default_columns = TABULAR_PREVIEW_INLINE_COLUMN_LIMIT if inline else TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT
        max_rows = TABULAR_PREVIEW_INLINE_ROW_LIMIT if inline else TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT
        max_columns = TABULAR_PREVIEW_INLINE_COLUMN_LIMIT if inline else TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT
        return ArraySlice2DRequest(
            row_offset=_non_negative_int(request.get("row_offset", 0)),
            row_limit=_positive_int(request.get("row_limit"), default=default_rows, maximum=max_rows),
            column_offset=_non_negative_int(request.get("column_offset", 0)),
            column_limit=_positive_int(request.get("column_limit"), default=default_columns, maximum=max_columns),
        )

    def _backend_table_window(
        self,
        session: _PreviewSession,
        window_request: TabularWindowRequest,
        source_request: Mapping[str, Any],
    ) -> TabularDataWindow | dict[str, Any]:
        backend = getattr(session.service, "preview_window", None)
        if not callable(backend):
            return _error_payload(
                "The active tabular backend does not support sort, filter, or search preview requests.",
                code="backend_query_unsupported",
                source=session.source,
                selector=session.selector,
            )
        backend_request = _window_request_payload(window_request, source_request)
        result = backend(session.ref, backend_request)
        if isinstance(result, TabularDataWindow):
            return result
        if isinstance(result, Mapping):
            window_payload = result.get("window")
            if isinstance(window_payload, TabularDataWindow):
                return window_payload
        return _error_payload(
            "The active tabular backend returned an invalid preview window.",
            code="invalid_backend_window",
            source=session.source,
            selector=session.selector,
            recoverable=True,
        )

    @staticmethod
    def _schema_payload(session: _PreviewSession) -> dict[str, Any]:
        schema = session.service.schema(session.ref)
        if isinstance(schema, TabularSchema):
            return schema.to_payload()
        if isinstance(schema, Mapping):
            return _json_safe_mapping(schema)
        return {}

    @staticmethod
    def _table_window_to_payload(
        window: TabularDataWindow,
        request: TabularWindowRequest,
        source_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = window.to_payload()
        payload["request"] = _window_request_payload(request, source_request)
        payload["bounded"] = True
        payload["client_side_full_scan"] = False
        return payload

    @staticmethod
    def _array_slice_to_payload(array_slice: ArraySlice2D, request: ArraySlice2DRequest) -> dict[str, Any]:
        payload = array_slice.to_payload()
        payload["request"] = _slice_request_payload(request)
        payload["bounded"] = True
        payload["client_side_full_scan"] = False
        return payload


def describe_tabular_preview(
    properties_or_source: Mapping[str, Any] | str | None,
    request: Mapping[str, Any] | None = None,
    *,
    mode: str = "inline",
    project_context_provider: _ProjectContextProvider | None = None,
) -> dict[str, Any]:
    return TabularPreviewProvider(project_context_provider=project_context_provider).describe_preview(
        properties_or_source,
        request,
        mode=mode,
    )


def describe_tabular_selector(
    properties_or_source: Mapping[str, Any] | str | None,
    *,
    project_context_provider: _ProjectContextProvider | None = None,
) -> dict[str, Any]:
    return TabularPreviewProvider(project_context_provider=project_context_provider).describe_selector(
        properties_or_source,
    )


__all__ = [
    "TABULAR_PREVIEW_CONTENT_KIND",
    "TABULAR_PREVIEW_FULLSCREEN_COLUMN_LIMIT",
    "TABULAR_PREVIEW_FULLSCREEN_ROW_LIMIT",
    "TABULAR_PREVIEW_INLINE_COLUMN_LIMIT",
    "TABULAR_PREVIEW_INLINE_ROW_LIMIT",
    "TABULAR_PREVIEW_MAX_WINDOW_COLUMN_LIMIT",
    "TABULAR_PREVIEW_MAX_WINDOW_ROW_LIMIT",
    "TabularPreviewProvider",
    "describe_tabular_preview",
    "describe_tabular_selector",
]
