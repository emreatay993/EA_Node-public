from __future__ import annotations

from types import SimpleNamespace

import pytest

from ea_node_editor.addons import catalog as addon_catalog
from ea_node_editor.addons.catalog import AddOnRegistration, create_live_execution_plot_backends
from ea_node_editor.app_preferences import default_app_preferences_document
from ea_node_editor.execution.plot_backend import (
    AUTO_PLOT_BACKEND_ID,
    PLOT_SURFACE_DATA_EXPORT,
    PLOT_SURFACE_LIVE,
    PLOT_SURFACE_STATIC_EXPORT,
    PLOT_TYPE_LINE,
    PLOT_TYPE_POINT_CLOUD,
    PLOT_TYPE_SCATTER,
    PLOT_TYPE_STREAMLINES,
    PLOT_TYPE_SURFACE,
    PlotBackendRecord,
    PlotCapability,
    create_plot_backend_registry,
)
from ea_node_editor.execution.plot_backend_matplotlib import (
    MATPLOTLIB_PLOT_BACKEND_ID,
    create_matplotlib_plot_backend_record,
)
from ea_node_editor.execution.plot_backend_pyqtgraph import PYQTGRAPH_PLOT_BACKEND_ID
from ea_node_editor.execution.plot_backend_pyvista import (
    PYVISTA_LIVE_3D_PLOT_TYPES,
    PYVISTA_PLOT_BACKEND_ID,
    create_pyvista_plot_backend_record,
    pyvista_static_export_supported,
)
from ea_node_editor.nodes.plugin_contracts import AddOnManifest


class _ThirdPartyPlotBackend:
    backend_id = "third_party"


def _third_party_record(
    *,
    surface: str = PLOT_SURFACE_STATIC_EXPORT,
    plot_type: str = PLOT_TYPE_LINE,
) -> PlotBackendRecord:
    return PlotBackendRecord(
        backend_id=_ThirdPartyPlotBackend.backend_id,
        display_name="Third Party Plot Backend",
        factory=_ThirdPartyPlotBackend,
        capabilities=(PlotCapability(plot_type=plot_type, surface=surface),),
        headless_safe_surfaces=(surface,),
    )


def test_matplotlib_backend_record_declares_headless_static_and_data_capabilities() -> None:
    record = create_matplotlib_plot_backend_record()

    assert record.backend_id == MATPLOTLIB_PLOT_BACKEND_ID
    assert record.supports(plot_type=PLOT_TYPE_LINE, surface=PLOT_SURFACE_LIVE)
    assert record.supports(plot_type=PLOT_TYPE_LINE, surface=PLOT_SURFACE_STATIC_EXPORT)
    assert record.supports(plot_type=PLOT_TYPE_SCATTER, surface=PLOT_SURFACE_DATA_EXPORT)
    assert not record.is_headless_safe_for(PLOT_SURFACE_LIVE)
    assert record.is_headless_safe_for(PLOT_SURFACE_STATIC_EXPORT)
    assert record.is_headless_safe_for(PLOT_SURFACE_DATA_EXPORT)
    assert record.metadata["live_renderer"] is True
    assert record.metadata["qt_required"] is True
    assert record.metadata["renderer"] == "Agg"

    resolved_live_backend = create_plot_backend_registry().resolve(
        MATPLOTLIB_PLOT_BACKEND_ID,
        plot_type=PLOT_TYPE_LINE,
        surface=PLOT_SURFACE_LIVE,
    )
    assert callable(getattr(resolved_live_backend, "render_widget"))


def test_third_party_backend_registers_and_resolves_through_same_registry_path() -> None:
    registry = create_plot_backend_registry((_third_party_record(),))

    assert registry.backend_ids == (
        MATPLOTLIB_PLOT_BACKEND_ID,
        PYQTGRAPH_PLOT_BACKEND_ID,
        PYVISTA_PLOT_BACKEND_ID,
        "third_party",
    )
    resolved_record = registry.resolve_record(
        "third_party",
        plot_type=PLOT_TYPE_LINE,
        surface=PLOT_SURFACE_STATIC_EXPORT,
    )
    resolved_backend = registry.resolve(
        "third_party",
        plot_type=PLOT_TYPE_LINE,
        surface=PLOT_SURFACE_STATIC_EXPORT,
    )

    assert resolved_record.display_name == "Third Party Plot Backend"
    assert isinstance(resolved_backend, _ThirdPartyPlotBackend)


def test_auto_resolution_uses_caller_supplied_default_backend_mapping() -> None:
    registry = create_plot_backend_registry((_third_party_record(surface=PLOT_SURFACE_DATA_EXPORT),))

    resolved = registry.resolve_record(
        AUTO_PLOT_BACKEND_ID,
        plot_type=PLOT_TYPE_LINE,
        surface=PLOT_SURFACE_STATIC_EXPORT,
        plot_default_backend_per_type={PLOT_TYPE_LINE: MATPLOTLIB_PLOT_BACKEND_ID},
        require_headless_safe=True,
    )

    assert resolved.backend_id == MATPLOTLIB_PLOT_BACKEND_ID
    with pytest.raises(LookupError, match="No default plot backend configured"):
        registry.resolve_record(
            AUTO_PLOT_BACKEND_ID,
            plot_type=PLOT_TYPE_LINE,
            surface=PLOT_SURFACE_STATIC_EXPORT,
            plot_default_backend_per_type={},
        )
    with pytest.raises(LookupError, match="does not support"):
        registry.resolve_record(
            AUTO_PLOT_BACKEND_ID,
            plot_type=PLOT_TYPE_LINE,
            surface=PLOT_SURFACE_STATIC_EXPORT,
            plot_default_backend_per_type={PLOT_TYPE_LINE: "third_party"},
        )


def test_registry_filters_by_capability_and_headless_safety() -> None:
    live_only_record = PlotBackendRecord(
        backend_id="live_only",
        display_name="Live Only",
        factory=lambda: SimpleNamespace(backend_id="live_only"),
        capabilities=(PlotCapability(plot_type=PLOT_TYPE_LINE, surface=PLOT_SURFACE_LIVE),),
    )
    registry = create_plot_backend_registry((live_only_record,))

    static_records = registry.records_for(
        plot_type=PLOT_TYPE_LINE,
        surface=PLOT_SURFACE_STATIC_EXPORT,
        require_headless_safe=True,
    )
    live_records = registry.records_for(plot_type=PLOT_TYPE_LINE, surface=PLOT_SURFACE_LIVE)

    assert [record.backend_id for record in static_records] == [MATPLOTLIB_PLOT_BACKEND_ID]
    assert [record.backend_id for record in live_records] == [
        MATPLOTLIB_PLOT_BACKEND_ID,
        PYQTGRAPH_PLOT_BACKEND_ID,
        "live_only",
    ]


def test_pyvista_backend_record_declares_live_3d_and_gated_static_capabilities() -> None:
    record = create_pyvista_plot_backend_record()

    assert record.backend_id == PYVISTA_PLOT_BACKEND_ID
    assert PYVISTA_LIVE_3D_PLOT_TYPES == (
        PLOT_TYPE_SURFACE,
        PLOT_TYPE_POINT_CLOUD,
        PLOT_TYPE_STREAMLINES,
    )
    for plot_type in PYVISTA_LIVE_3D_PLOT_TYPES:
        assert record.supports(plot_type=plot_type, surface=PLOT_SURFACE_LIVE)
        assert not record.supports(plot_type=plot_type, surface=PLOT_SURFACE_DATA_EXPORT)
        if pyvista_static_export_supported():
            assert record.supports(plot_type=plot_type, surface=PLOT_SURFACE_STATIC_EXPORT)
            assert record.is_headless_safe_for(PLOT_SURFACE_STATIC_EXPORT)
        else:
            assert not record.supports(plot_type=plot_type, surface=PLOT_SURFACE_STATIC_EXPORT)
            assert not record.is_headless_safe_for(PLOT_SURFACE_STATIC_EXPORT)


def test_addon_catalog_creates_plot_backends_from_live_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    third_party_record = _third_party_record()
    registration = AddOnRegistration(
        manifest=AddOnManifest(
            addon_id="packet.plot",
            display_name="Packet Plot",
            apply_policy="hot_apply",
        ),
        backend_module="packet.plot.module",
        backend_id="packet.plot",
        plot_backend_factory_attr="create_plot_backends",
    )
    module = SimpleNamespace(create_plot_backends=lambda: (third_party_record,))

    monkeypatch.setattr(addon_catalog, "REGISTERED_ADDON_REGISTRATIONS", (registration,))
    monkeypatch.setattr(addon_catalog.importlib, "import_module", lambda module_name: module)

    records = create_live_execution_plot_backends(
        preferences_document=default_app_preferences_document()
    )

    assert records == (third_party_record,)
