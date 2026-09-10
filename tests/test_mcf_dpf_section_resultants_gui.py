from __future__ import annotations

import csv
import json
import math
import sys
import types
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest

from scripts.mcf_dpf_section_resultants import (
    cli,
    core,
    dpf_io,
    extraction,
    gui,
    visualization,
)


class _FakeScoping:
    def __init__(self, ids: list[int] | None = None, location: str | None = None) -> None:
        self.ids = list(ids or [])
        self.location = location


class _FakeField:
    def __init__(
        self,
        ids: list[int],
        data: list[Any],
        unit: str | None = None,
    ) -> None:
        self.scoping = _FakeScoping(ids)
        self.data = data
        self.unit = unit


class _FakeDpf:
    class locations:
        elemental = "elemental"
        nodal = "nodal"
        time_freq = "time_freq"

    @staticmethod
    def Scoping(
        ids: list[int] | None = None,
        location: str | None = None,
    ) -> _FakeScoping:
        return _FakeScoping(ids, location)


class _FakePin:
    def __init__(self, owner: Any, name: str) -> None:
        self.owner = owner
        self.name = name

    def connect(self, value: Any) -> None:
        self.owner.values[self.name] = value


def _install_fake_dpf_core(monkeypatch: pytest.MonkeyPatch, fake_dpf: Any) -> None:
    fake_ansys = types.ModuleType("ansys")
    fake_dpf_package = types.ModuleType("ansys.dpf")
    fake_dpf_package.core = fake_dpf
    fake_ansys.dpf = fake_dpf_package
    monkeypatch.setitem(sys.modules, "ansys", fake_ansys)
    monkeypatch.setitem(sys.modules, "ansys.dpf", fake_dpf_package)
    monkeypatch.setitem(sys.modules, "ansys.dpf.core", fake_dpf)


class _FakeNode:
    def __init__(self, coordinates: list[float]) -> None:
        self.coordinates = coordinates


class _FakeNodes:
    def __init__(self, nodes: dict[int, list[float]]) -> None:
        self._nodes = nodes
        self.scoping = _FakeScoping(sorted(nodes))

    def node_by_id(self, node_id: int) -> _FakeNode:
        return _FakeNode(self._nodes[int(node_id)])


class _FakeElement:
    def __init__(self, node_ids: list[int]) -> None:
        self.node_ids = node_ids


class _FakeElements:
    def __init__(self, elements: dict[int, list[int]]) -> None:
        self._elements = elements
        self.scoping = _FakeScoping(sorted(elements))

    def element_by_id(self, element_id: int) -> _FakeElement:
        return _FakeElement(self._elements[int(element_id)])


class _FakeGrid:
    def __init__(
        self,
        points: list[list[float]],
        cells: list[int],
        celltypes: list[int],
    ) -> None:
        self.points = points
        self.cells = cells
        self.celltypes = celltypes


class _FakeMesh:
    def __init__(
        self,
        *,
        nodes: dict[int, list[float]],
        elements: dict[int, list[int]],
        grid: _FakeGrid | None = None,
        unit: str = "m",
    ) -> None:
        self.nodes = _FakeNodes(nodes)
        self.elements = _FakeElements(elements)
        self.grid = grid
        self.unit = unit


class _TypedFakeElement(_FakeElement):
    def __init__(self, node_ids: list[int], element_type_value: int) -> None:
        super().__init__(node_ids)
        self.type = types.SimpleNamespace(
            value=int(element_type_value),
            name={
                1: "Hex20",
                10: "Tet4",
                14: "Tri3",
            }.get(int(element_type_value), "Unknown"),
        )


class _TypedFakeElements:
    def __init__(
        self,
        elements: dict[int, list[int]],
        element_type_values: dict[int, int],
        source_order: list[int],
    ) -> None:
        self._elements = {
            int(element_id): [int(node_id) for node_id in node_ids]
            for element_id, node_ids in elements.items()
        }
        self._element_type_values = {
            int(element_id): int(value)
            for element_id, value in element_type_values.items()
        }
        self.scoping = _FakeScoping(source_order)

    def element_by_id(self, element_id: int) -> _TypedFakeElement:
        element_id = int(element_id)
        return _TypedFakeElement(
            self._elements[element_id], self._element_type_values[element_id]
        )


class _SourceMeshWithoutGrid:
    """Native mesh fixture that fails if a code path asks DPF for a VTK grid."""

    def __init__(
        self,
        *,
        nodes: dict[int, list[float]],
        elements: dict[int, list[int]],
        element_type_values: dict[int, int],
        node_order: list[int],
        element_order: list[int],
        unit: str = "mm",
    ) -> None:
        self.nodes = _FakeNodes(nodes)
        self.nodes.scoping = _FakeScoping(node_order)
        self.elements = _TypedFakeElements(
            elements,
            element_type_values,
            element_order,
        )
        self.unit = unit

    @property
    def grid(self) -> Any:
        raise AssertionError("The local selected-mesh fallback must not request source_mesh.grid.")


class _DpfWithoutMeshOperators:
    @property
    def operators(self) -> Any:
        raise AssertionError(
            "The local selected-mesh fallback must not request DPF mesh operators."
        )


def _fake_metadata(
    signature: dpf_io.ModalRstSignature,
    *,
    names: list[str] | None = None,
    modal_set_count: int = 7,
) -> dpf_io.ModalRstMetadata:
    global_option = {
        "id": 0,
        "name": "Global Coordinate System",
        "type": "Cartesian",
        "origin": [0.0, 0.0, 0.0],
        "origin_unit": core.GUI_ORIGIN_UNIT,
        "axes": {
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        "source": "global",
    }
    global_option["label"] = dpf_io.coordinate_system_label(global_option)
    return dpf_io.ModalRstMetadata(
        signature=signature,
        named_selection_names=names or ["CUT_SMALL", "BOLT_NODES"],
        modal_set_count=modal_set_count,
        result_names=["displacement"],
        mesh_unit=core.GUI_ORIGIN_UNIT,
        coordinate_system_options=[global_option],
        caerep_coordinate_systems={},
        ds_dat_apdl_names={},
        result_sets=[
            {
                "id": set_id,
                "value": float(set_id),
                "unit": "s",
                "label": f"Set {set_id} — {set_id} s",
            }
            for set_id in range(1, modal_set_count + 1)
        ],
    )


def _install_fake_named_selection_dpf(
    monkeypatch: pytest.MonkeyPatch,
    names: list[str],
    scopes_by_name: dict[str, _FakeScoping],
    operator_scopes_by_name: dict[str, _FakeScoping] | None = None,
) -> list[bool]:
    released: list[bool] = []

    class FakeOutput:
        def __init__(self, owner: Any) -> None:
            self.owner = owner

        def __call__(self) -> _FakeScoping:
            name = str(self.owner.values["named_selection_name"]).upper()
            return (operator_scopes_by_name or scopes_by_name)[name]

    class FakeNamedSelectionOperator:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            self.inputs = types.SimpleNamespace(
                requested_location=_FakePin(self, "requested_location"),
                named_selection_name=_FakePin(self, "named_selection_name"),
                int_inclusive=_FakePin(self, "int_inclusive"),
                streams_container=_FakePin(self, "streams_container"),
                data_sources=_FakePin(self, "data_sources"),
            )
            self.outputs = types.SimpleNamespace(mesh_scoping=FakeOutput(self))

    class FakeMetadata:
        available_named_selections = names

        def named_selection(self, name: str) -> _FakeScoping:
            return scopes_by_name[str(name).upper()]

    class FakeModel:
        def __init__(self, _data_sources: Any) -> None:
            self.metadata = FakeMetadata()

    fake_dpf = types.SimpleNamespace(
        locations=types.SimpleNamespace(elemental="Elemental"),
        DataSources=lambda path: types.SimpleNamespace(path=path),
        Model=FakeModel,
        operators=types.SimpleNamespace(
            scoping=types.SimpleNamespace(on_named_selection=FakeNamedSelectionOperator)
        ),
    )
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(
        dpf_io,
        "create_streams_container",
        lambda _dpf, _data_sources: types.SimpleNamespace(
            release_handles=lambda: released.append(True)
        ),
    )
    return released


def _install_fake_visualization_dpf(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    released: list[bool] = []

    class FakeModel:
        def __init__(self, _data_sources: Any) -> None:
            self.metadata = types.SimpleNamespace(
                available_named_selections=["CUT_SMALL", "BOLT_NODES"],
            )

    fake_dpf = types.SimpleNamespace(
        __version__="0.15.2",
        locations=types.SimpleNamespace(elemental="Elemental", nodal="Nodal"),
        Scoping=lambda ids=None, location=None: _FakeScoping(ids, location),
        DataSources=lambda path: types.SimpleNamespace(path=path),
        Model=FakeModel,
    )
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(dpf_io, "detected_ansys_release_codes", lambda: [])
    monkeypatch.setattr(
        visualization,
        "create_streams_container",
        lambda _dpf, _data_sources: types.SimpleNamespace(
            release_handles=lambda: released.append(True)
        ),
    )
    return released


def _visualization_cache_config(rst: Path, *, element_name: str = "CUT_SMALL") -> core.SectionConfig:
    return core.SectionConfig(
        modal_rst=str(rst),
        element_named_selection=element_name,
        coordinate_system_origin=[0.5, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        reference_frame_motion="fixed",
        section_normal_axis="x",
        extraction_side="positive",
    )


def _visualization_cache_mesh() -> _FakeMesh:
    return _FakeMesh(
        nodes={
            101: [-1.0, 0.0, 0.0],
            102: [1.0, 0.0, 0.0],
            103: [2.0, 0.0, 0.0],
            104: [3.0, 0.0, 0.0],
        },
        elements={7: [101, 102], 8: [103, 104]},
        grid=_FakeGrid(
            points=[
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
            ],
            cells=[2, 0, 1, 2, 2, 3],
            celltypes=[3, 3],
        ),
        unit="mm",
    )


def test_selected_element_mesh_view_preserves_scoped_ids_native_connectivity_and_unit() -> None:
    source_mesh = _SourceMeshWithoutGrid(
        nodes={
            9: [9.0, 0.0, 0.0],
            1: [1.0, 0.0, 0.0],
            3: [3.0, 0.0, 0.0],
            2: [2.0, 0.0, 0.0],
            4: [4.0, 0.0, 0.0],
            5: [5.0, 0.0, 0.0],
            6: [6.0, 0.0, 0.0],
        },
        elements={
            10: [1, 2, 3, 4],
            20: [4, 5, 6],
            30: [9, 3, 1],
        },
        element_type_values={10: 10, 20: 14, 30: 14},
        node_order=[9, 1, 3, 2, 4, 5, 6],
        element_order=[10, 20, 30],
        unit="mm",
    )

    mesh = dpf_io.selected_element_mesh_view(source_mesh, _FakeScoping([30, 10]))

    assert mesh.unit == "mm"
    assert mesh.elements.scoping.ids == [30, 10]
    assert mesh.nodes.scoping.ids == [9, 3, 1, 2, 4]
    assert mesh.nodes.node_by_id(3).coordinates == [3.0, 0.0, 0.0]
    assert mesh.elements.element_by_id(30).node_ids == [9, 3, 1]
    assert mesh.elements.element_by_id(10).node_ids == [1, 2, 3, 4]
    assert visualization.mesh_grid_payload(mesh) == {
        "points": [
            [9.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
        ],
        "cells": [3, 0, 1, 2, 4, 2, 3, 1, 4],
        "celltypes": [5, 10],
        "element_ids": [30, 10],
    }


def test_selected_element_mesh_view_linearizes_hex20_grid_but_keeps_native_topology() -> None:
    node_ids = list(range(101, 121))
    source_mesh = _SourceMeshWithoutGrid(
        nodes={node_id: [float(node_id), 0.0, 0.0] for node_id in node_ids},
        elements={50: node_ids},
        element_type_values={50: 1},
        node_order=node_ids,
        element_order=[50],
    )

    mesh = dpf_io.selected_element_mesh_view(source_mesh, _FakeScoping([50]))
    grid = visualization.mesh_grid_payload(mesh)

    assert mesh.elements.element_by_id(50).node_ids == node_ids
    assert mesh.nodes.scoping.ids == node_ids
    assert grid["cells"] == [8, *range(8)]
    assert grid["celltypes"] == [12]
    assert grid["element_ids"] == [50]


def test_selected_element_mesh_view_is_consumed_by_static_animation_without_grid_or_dpf_operators() -> None:
    node_ids = list(range(201, 221))
    source_mesh = _SourceMeshWithoutGrid(
        nodes={node_id: [float(node_id), 1.0, 2.0] for node_id in node_ids},
        elements={60: node_ids},
        element_type_values={60: 1},
        node_order=node_ids,
        element_order=[60],
    )

    class _ModelWithoutMeshOperators:
        def __init__(self) -> None:
            self.metadata = types.SimpleNamespace(meshed_region=source_mesh)

        @property
        def operators(self) -> Any:
            return _DpfWithoutMeshOperators().operators

    mesh = dpf_io.selected_element_mesh(_ModelWithoutMeshOperators(), _FakeScoping([60]))
    topology = visualization.static_animation_topology_from_mesh(
        core.SectionConfig(),
        mesh=mesh,
        element_scoping=_FakeScoping([60]),
        element_name="HEX20_SCOPE",
        available_named=["HEX20_SCOPE"],
        displacement_node_ids=node_ids,
        tracking_node_ids=[],
        tracking_reference_coordinates={},
        attachment={"source": "test"},
    )

    assert topology.node_ids == tuple(node_ids)
    assert topology.element_ids == (60,)
    assert topology.element_node_ids == {60: tuple(node_ids)}
    assert topology.cells.tolist() == [8, *range(8)]
    assert topology.celltypes.tolist() == [12]
    assert topology.connectivity_point_indices.tolist() == list(range(20))


def test_selected_element_mesh_view_does_not_require_renderer_support_for_extraction() -> None:
    source_mesh = _SourceMeshWithoutGrid(
        nodes={
            node_id: [float(node_id), 0.0, 0.0]
            for node_id in range(301, 308)
        },
        elements={70: list(range(301, 308))},
        element_type_values={70: 999},
        node_order=list(range(301, 308)),
        element_order=[70],
    )

    mesh = dpf_io.selected_element_mesh_view(source_mesh, _FakeScoping([70]))

    assert mesh.elements.scoping.ids == [70]
    assert mesh.nodes.scoping.ids == list(range(301, 308))
    assert dpf_io.selected_mesh_node_ids(mesh) == list(range(301, 308))
    deformed_mesh = visualization.mesh_with_nodal_displacements(
        mesh,
        {node_id: [0.0, 0.0, 1.0] for node_id in range(301, 308)},
        {"geometry_state": "deformed"},
        include_grid=False,
    )
    assert deformed_mesh.nodes.node_by_id(301).coordinates == [301.0, 0.0, 1.0]
    assert visualization.mesh_grid_payload(deformed_mesh)["points"] == []
    with pytest.raises(ValueError, match="not supported by the local selected-mesh renderer"):
        visualization.mesh_grid_payload(mesh)


def test_construction_surface_scoping_keeps_full_visualization_ids() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [-1.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
            3: [2.0, 0.0, 0.0],
            4: [3.0, 0.0, 0.0],
        },
        elements={10: [1, 2], 20: [3, 4]},
    )

    elem_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        core.SectionConfig(
            coordinate_system_origin=[0.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
            section_normal_axis="x",
            extraction_side="positive",
            side_filter_tolerance=1.0e-8,
        ),
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        mesh=mesh,
    )

    assert elem_scope.ids == [10]
    assert elem_scope.location == "elemental"
    assert node_scope.ids == [2]
    assert node_scope.location == "nodal"
    assert info["raw_element_ids"] == [10, 20]
    assert info["cut_element_ids"] == [10]
    assert info["not_cut_element_ids"] == [20]
    assert info["selected_node_ids"] == [2]
    assert info["selected_node_coordinates"] == {"2": [1.0, 0.0, 0.0]}
    compact = visualization.compact_side_filter_info(info)
    assert "cut_element_ids" not in compact
    assert compact["cut_element_ids_preview"] == [10]


def _coincident_interface_config(
    *, extraction_side: str, normal: list[float] | None = None
) -> tuple[core.SectionConfig, list[list[float]]]:
    normal = normal or [1.0, 0.0, 0.0]
    return (
        core.SectionConfig(
            coordinate_system_origin=[0.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": normal,
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
            section_normal_axis="x",
            extraction_side=extraction_side,
            side_filter_tolerance=1.0e-8,
        ),
        [normal, [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    )


def _coincident_interface_mesh(*, conformal: bool = False) -> _FakeMesh:
    positive_plane_nodes = [1, 2, 7] if conformal else [4, 5, 8]
    return _FakeMesh(
        nodes={
            1: [0.0, 0.0, 0.0],
            2: [0.0, 1.0, 0.0],
            7: [0.0, 0.0, 1.0],
            3: [-1.0, 0.25, 0.25],
            4: [0.0, 0.0, 0.0],
            5: [0.0, 1.0, 0.0],
            8: [0.0, 0.0, 1.0],
            6: [1.0, 0.25, 0.25],
        },
        elements={
            10: [1, 2, 7, 3],
            20: [*positive_plane_nodes, 6],
        },
    )


@pytest.mark.parametrize(
    ("extraction_side", "expected_signs"),
    [
        ("positive", {"negative_tangent": 1, "positive_tangent": -1}),
        ("negative", {"negative_tangent": -1, "positive_tangent": 1}),
    ],
)
def test_construction_surface_scoping_splits_duplicate_tangent_sheets(
    extraction_side: str,
    expected_signs: dict[str, int],
) -> None:
    config, axes = _coincident_interface_config(extraction_side=extraction_side)

    element_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=_coincident_interface_mesh(),
    )

    terms = {term["role"]: term for term in info["force_summation_terms"]}
    assert element_scope.ids == [10, 20]
    assert node_scope.ids == [1, 2, 4, 5, 7, 8]
    assert info["selected_node_ids"] == [1, 2, 4, 5, 7, 8]
    assert info["force_summation_policy"] == "coordinate_matched_duplicate_tangent_interface"
    assert info["duplicate_tangent_pair_count"] == 1
    expected_reference_ids = [1, 2, 7] if extraction_side == "positive" else [4, 5, 8]
    assert info["moment_reference_node_ids"] == expected_reference_ids
    assert info["moment_reference_centroid"] == pytest.approx(
        [0.0, 1.0 / 3.0, 1.0 / 3.0]
    )
    assert set(terms) == {"negative_tangent", "positive_tangent"}
    assert terms["negative_tangent"] == {
        "role": "negative_tangent",
        "sign": expected_signs["negative_tangent"],
        "element_ids": [10],
        "node_ids": [1, 2, 7],
    }
    assert terms["positive_tangent"] == {
        "role": "positive_tangent",
        "sign": expected_signs["positive_tangent"],
        "element_ids": [20],
        "node_ids": [4, 5, 8],
    }
    compact = visualization.compact_side_filter_info(info)
    assert "force_summation_terms" not in compact
    assert compact["force_summation_terms_preview"][0]["node_ids_preview"] == [1, 2, 7]


def test_construction_surface_scoping_duplicate_tangent_terms_follow_normal_flip() -> None:
    config, axes = _coincident_interface_config(
        extraction_side="positive",
        normal=[-1.0, 0.0, 0.0],
    )

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=_coincident_interface_mesh(),
    )

    terms = {term["role"]: term for term in info["force_summation_terms"]}
    assert terms["negative_tangent"]["element_ids"] == [20]
    assert terms["negative_tangent"]["node_ids"] == [4, 5, 8]
    assert terms["negative_tangent"]["sign"] == 1
    assert terms["positive_tangent"]["element_ids"] == [10]
    assert terms["positive_tangent"]["node_ids"] == [1, 2, 7]
    assert terms["positive_tangent"]["sign"] == -1


def test_construction_surface_scoping_keeps_residual_cut_in_baseline_term() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.0, 0.0, 0.0],
            2: [0.0, 1.0, 0.0],
            9: [0.0, 0.0, 1.0],
            3: [-1.0, 0.25, 0.25],
            4: [0.0, 0.0, 0.0],
            5: [0.0, 1.0, 0.0],
            10: [0.0, 0.0, 1.0],
            6: [1.0, 0.25, 0.25],
            7: [-1.0, 2.0, 0.0],
            8: [1.0, 2.0, 0.0],
        },
        elements={10: [1, 2, 9, 3], 20: [4, 5, 10, 6], 30: [7, 8]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    element_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20, 30], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    terms = {term["role"]: term for term in info["force_summation_terms"]}
    assert element_scope.ids == [10, 20, 30]
    assert node_scope.ids == [1, 2, 4, 5, 8, 9, 10]
    assert terms["baseline"] == {
        "role": "baseline",
        "sign": 1,
        "element_ids": [30],
        "node_ids": [8],
    }


def test_construction_surface_scoping_keeps_conformal_tangent_interface_as_baseline() -> None:
    config, axes = _coincident_interface_config(extraction_side="positive")

    element_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=_coincident_interface_mesh(conformal=True),
    )

    assert element_scope.ids == [10, 20]
    assert node_scope.ids == [1, 2, 6, 7]
    assert info["force_summation_policy"] == "single_baseline"
    assert info["duplicate_tangent_pair_count"] == 0
    assert info["force_summation_terms"] == [
        {
            "role": "baseline",
            "sign": 1,
            "element_ids": [10, 20],
            "node_ids": [1, 2, 6, 7],
        }
    ]


def test_construction_surface_scoping_keeps_strict_crossing_as_baseline() -> None:
    mesh = _FakeMesh(
        nodes={1: [-1.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        elements={10: [1, 2]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    element_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    assert element_scope.ids == [10]
    assert node_scope.ids == [2]
    assert info["force_summation_policy"] == "single_baseline"
    assert info["force_summation_terms"] == [
        {"role": "baseline", "sign": 1, "element_ids": [10], "node_ids": [2]}
    ]


@pytest.mark.parametrize("plane_node_count", [1, 2])
def test_construction_surface_scoping_does_not_split_vertex_or_edge_touches(
    plane_node_count: int,
) -> None:
    negative_coordinates = [
        [0.0, 0.0, 0.0],
        [0.0 if plane_node_count == 2 else -1.0, 1.0, 0.0],
        [-1.0, 0.0, 1.0],
        [-1.0, 1.0, 1.0],
    ]
    positive_coordinates = [
        [0.0, 0.0, 0.0],
        [0.0 if plane_node_count == 2 else 1.0, 1.0, 0.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
    ]
    mesh = _FakeMesh(
        nodes={
            **{index + 1: point for index, point in enumerate(negative_coordinates)},
            **{index + 11: point for index, point in enumerate(positive_coordinates)},
        },
        elements={10: [1, 2, 3, 4], 20: [11, 12, 13, 14]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    assert info["force_summation_policy"] == "single_baseline"
    assert info["duplicate_tangent_pair_count"] == 0
    assert info["duplicate_tangent_face_rejection_counts"] == {
        "partial_face_edge_or_vertex_touch": 2
    }


def test_construction_surface_scoping_does_not_split_zero_area_full_faces() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.0, 0.0, 0.0],
            2: [0.0, 1.0, 0.0],
            3: [0.0, 2.0, 0.0],
            4: [-1.0, 0.5, 1.0],
            11: [0.0, 0.0, 0.0],
            12: [0.0, 1.0, 0.0],
            13: [0.0, 2.0, 0.0],
            14: [1.0, 0.5, 1.0],
        },
        elements={10: [1, 2, 3, 4], 20: [11, 12, 13, 14]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    assert info["force_summation_policy"] == "single_baseline"
    assert info["duplicate_tangent_pair_count"] == 0
    assert info["duplicate_tangent_face_rejection_counts"] == {"zero_area_face": 2}


def test_construction_surface_scoping_hex20_duplicate_full_face_triggers() -> None:
    face_points = [
        [0.0, 0.0, 0.0],
        [0.0, 2.0, 0.0],
        [0.0, 2.0, 2.0],
        [0.0, 0.0, 2.0],
        [0.0, 1.0, 0.0],
        [0.0, 2.0, 1.0],
        [0.0, 1.0, 2.0],
        [0.0, 0.0, 1.0],
    ]

    def hex20_points(off_plane_x: float) -> list[list[float]]:
        points = [point[:] for point in face_points[:4]]
        points.extend([[off_plane_x, point[1], point[2]] for point in face_points[:4]])
        points.extend(point[:] for point in face_points[4:])
        points.extend([[off_plane_x, point[1], point[2]] for point in face_points[4:]])
        points.extend(
            [
                [off_plane_x / 2.0, 0.0, 0.0],
                [off_plane_x / 2.0, 2.0, 0.0],
                [off_plane_x / 2.0, 2.0, 2.0],
                [off_plane_x / 2.0, 0.0, 2.0],
            ]
        )
        return points

    negative_points = hex20_points(-1.0)
    positive_points = hex20_points(1.0)
    mesh = _FakeMesh(
        nodes={
            **{index + 1: point for index, point in enumerate(negative_points)},
            **{index + 101: point for index, point in enumerate(positive_points)},
        },
        elements={10: list(range(1, 21)), 20: list(range(101, 121))},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    terms = {term["role"]: term for term in info["force_summation_terms"]}
    assert info["force_summation_policy"] == "coordinate_matched_duplicate_tangent_interface"
    assert info["duplicate_tangent_pair_count"] == 1
    assert terms["negative_tangent"]["node_ids"] == [1, 2, 3, 4, 9, 10, 11, 12]
    assert terms["positive_tangent"]["node_ids"] == [101, 102, 103, 104, 109, 110, 111, 112]


def test_construction_surface_scoping_loose_side_tolerance_does_not_bridge_gap() -> None:
    gap = 1.0e-3
    mesh = _FakeMesh(
        nodes={
            1: [-gap, 0.0, 0.0],
            2: [-gap, 1.0, 0.0],
            3: [-gap, 0.0, 1.0],
            4: [-1.0, 0.25, 0.25],
            11: [gap, 0.0, 0.0],
            12: [gap, 1.0, 0.0],
            13: [gap, 0.0, 1.0],
            14: [1.0, 0.25, 0.25],
        },
        elements={10: [1, 2, 3, 4], 20: [11, 12, 13, 14]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")
    config.side_filter_tolerance = 1.0e-2

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=mesh,
    )

    assert info["force_summation_policy"] == "single_baseline"
    assert info["duplicate_tangent_match_status"] == "no_coordinate_match"
    assert info["duplicate_tangent_coordinate_tolerance"] < gap
    assert info["duplicate_tangent_coordinate_tolerance"] < config.side_filter_tolerance


def test_construction_surface_scoping_ambiguous_coincident_stack_fails_closed() -> None:
    face = [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    mesh = _FakeMesh(
        nodes={
            **{index + 1: point for index, point in enumerate(face)},
            4: [-1.0, 0.25, 0.25],
            **{index + 11: point for index, point in enumerate(face)},
            14: [1.0, 0.25, 0.25],
            **{index + 21: point for index, point in enumerate(face)},
            24: [2.0, 0.25, 0.25],
        },
        elements={10: [1, 2, 3, 4], 20: [11, 12, 13, 14], 30: [21, 22, 23, 24]},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    with pytest.raises(ValueError, match="ambiguous stack"):
        visualization.construction_surface_scoping(
            _FakeDpf,
            object(),
            _FakeScoping([10, 20, 30], "elemental"),
            config,
            axes,
            mesh=mesh,
        )


@pytest.mark.parametrize(
    ("node_count", "plane_indices", "plane_points"),
    [
        (5, (0, 1, 2, 3), ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1))),
        (6, (0, 1, 2), ((0, 0, 0), (0, 1, 0), (0, 0, 1))),
        (
            13,
            (0, 1, 2, 3, 5, 6, 7, 8),
            (
                (0, 0, 0),
                (0, 1, 0),
                (0, 1, 1),
                (0, 0, 1),
                (0, 0.5, 0),
                (0, 1, 0.5),
                (0, 0.5, 1),
                (0, 0, 0.5),
            ),
        ),
        (
            15,
            (0, 1, 2, 6, 7, 8),
            (
                (0, 0, 0),
                (0, 1, 0),
                (0, 0, 1),
                (0, 0.5, 0),
                (0, 0.5, 0.5),
                (0, 0, 0.5),
            ),
        ),
    ],
)
def test_construction_surface_scoping_supports_duplicate_pyramid_and_wedge_faces(
    node_count: int,
    plane_indices: tuple[int, ...],
    plane_points: tuple[tuple[float, float, float], ...],
) -> None:
    nodes: dict[int, list[float]] = {}
    elements: dict[int, list[int]] = {}
    for element_id, node_offset, side_x in ((10, 0, -1.0), (20, 100, 1.0)):
        element_node_ids = [node_offset + index + 1 for index in range(node_count)]
        elements[element_id] = element_node_ids
        plane_point_by_index = dict(zip(plane_indices, plane_points))
        for index, node_id in enumerate(element_node_ids):
            if index in plane_point_by_index:
                point = plane_point_by_index[index]
                nodes[node_id] = [float(value) for value in point]
            else:
                nodes[node_id] = [side_x, float(index), float(index % 3)]
    config, axes = _coincident_interface_config(extraction_side="positive")

    _element_scope, _node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=_FakeMesh(nodes=nodes, elements=elements),
    )

    assert info["force_summation_policy"] == (
        "coordinate_matched_duplicate_tangent_interface"
    )
    assert info["duplicate_tangent_pair_count"] == 1
    assert [term["sign"] for term in info["force_summation_terms"]] == [1, -1]


def test_construction_surface_scoping_rejects_matching_unsupported_duplicate_faces() -> None:
    face = [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    nodes = {
        **{index + 1: point for index, point in enumerate(face)},
        **{index + 4: [-1.0, float(index), 0.25] for index in range(4)},
        **{index + 101: point for index, point in enumerate(face)},
        **{index + 104: [1.0, float(index), 0.25] for index in range(4)},
    }
    mesh = _FakeMesh(
        nodes=nodes,
        elements={10: list(range(1, 8)), 20: list(range(101, 108))},
    )
    config, axes = _coincident_interface_config(extraction_side="positive")

    with pytest.raises(ValueError, match="unsupported solid connectivity"):
        visualization.construction_surface_scoping(
            _FakeDpf,
            object(),
            _FakeScoping([10, 20], "elemental"),
            config,
            axes,
            mesh=mesh,
        )


def _duplicate_interface_element_nodal_dpf(
    rows_by_element: dict[int, list[list[float]]],
    captured: dict[str, Any],
) -> Any:
    class FakeElementNodalField:
        component_count = 9
        unit = "N"

        def get_entity_data_by_id(self, element_id: int) -> list[list[float]]:
            return rows_by_element[int(element_id)]

    class FakeFieldsContainer:
        def get_field_by_time_id(self, time_id: int) -> FakeElementNodalField:
            captured["field_time_id"] = int(time_id)
            return FakeElementNodalField()

    class FakeOutput:
        def __call__(self) -> FakeFieldsContainer:
            return FakeFieldsContainer()

    class FakeElementNodalForces:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            captured["operator"] = self
            self.inputs = types.SimpleNamespace(
                data_sources=_FakePin(self, "data_sources"),
                streams_container=_FakePin(self, "streams_container"),
                time_scoping=_FakePin(self, "time_scoping"),
                mesh_scoping=_FakePin(self, "mesh_scoping"),
                bool_rotate_to_global=_FakePin(self, "bool_rotate_to_global"),
                requested_location=_FakePin(self, "requested_location"),
            )
            self.outputs = types.SimpleNamespace(fields_container=FakeOutput())

    return types.SimpleNamespace(
        locations=types.SimpleNamespace(
            elemental="Elemental",
            elemental_nodal="ElementalNodal",
            time_freq="TimeFreq_sets",
        ),
        Scoping=lambda ids=None, location=None: _FakeScoping(ids, location),
        operators=types.SimpleNamespace(
            result=types.SimpleNamespace(element_nodal_forces=FakeElementNodalForces)
        ),
    )


def _duplicate_interface_element_nodal_rows() -> dict[int, list[list[float]]]:
    return {
        10: [
            [999.0, 999.0, 999.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ],
        20: [
            [777.0, 777.0, 777.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ],
    }


def test_static_duplicate_interface_resultants_signs_element_rows_and_deformed_moment() -> None:
    captured: dict[str, Any] = {}
    fake_dpf = _duplicate_interface_element_nodal_dpf(
        _duplicate_interface_element_nodal_rows(), captured
    )
    mesh = _FakeMesh(
        nodes={
            1: [0.0, 0.0, 0.0],
            2: [0.0, 2.0, 0.0],
            3: [-1.0, 0.0, 0.0],
            4: [0.0, 0.0, 0.0],
            5: [0.0, 2.0, 0.0],
            6: [1.0, 0.0, 0.0],
        },
        # Deliberately non-sorted connectivity proves that each elemental-nodal
        # row is mapped to the corresponding connectivity position.
        elements={10: [3, 1, 2], 20: [6, 5, 4]},
        unit="mm",
    )
    data_sources = object()
    streams_container = object()
    terms = [
        {
            "role": "negative_tangent",
            "sign": 1,
            "element_ids": [10],
            "node_ids": [1, 2],
        },
        {
            "role": "positive_tangent",
            "sign": -1,
            "element_ids": [20],
            "node_ids": [4, 5],
        },
    ]

    result = extraction.static_duplicate_interface_resultants(
        fake_dpf,
        data_sources,
        streams_container,
        mesh,
        {
            1: [0.0, 0.0, 1.0],
            2: [0.0, 0.0, 0.0],
            4: [0.0, 1.0, 0.0],
            5: [0.0, 0.0, 2.0],
        },
        7,
        [0.0, 0.0, 0.0],
        terms,
        1,
    )

    assert result["force"] == pytest.approx([7.0, 15.0, 0.0])
    assert result["moment_about_reference"] == pytest.approx([10.0, 10.0, 3.0])
    assert result["nodal_force_rows"] == {
        1: [10.0, 0.0, 0.0],
        2: [0.0, 20.0, 0.0],
        4: [-3.0, 0.0, 0.0],
        5: [0.0, -5.0, 0.0],
    }
    assert result["nodal_moment_rows"] == {}
    assert result["nodal_moment_output_status"] == (
        "solid_element_nodal_no_explicit_couples"
    )
    assert result["force_unit"] == "N"
    assert result["moment_unit"] == "N mm"
    assert result["term_resultants"] == [
        {
            "role": "negative_tangent",
            "sign": 1.0,
            "element_count": 1,
            "node_count": 2,
            "force_global": [10.0, 20.0, 0.0],
            "moment_about_reference_global": [0.0, 10.0, 0.0],
        },
        {
            "role": "positive_tangent",
            "sign": -1.0,
            "element_count": 1,
            "node_count": 2,
            "force_global": [3.0, 5.0, 0.0],
            "moment_about_reference_global": [-10.0, 0.0, -3.0],
        },
    ]
    operator = captured["operator"]
    assert captured["field_time_id"] == 7
    assert operator.values["data_sources"] is data_sources
    assert operator.values["streams_container"] is streams_container
    assert operator.values["time_scoping"].ids == [7]
    assert operator.values["time_scoping"].location == "TimeFreq_sets"
    assert operator.values["mesh_scoping"].ids == [10, 20]
    assert operator.values["mesh_scoping"].location == "Elemental"
    assert operator.values["bool_rotate_to_global"] is True
    assert operator.values["requested_location"] == "ElementalNodal"


def test_static_duplicate_interface_resultants_rejects_element_row_count_mismatch() -> None:
    captured: dict[str, Any] = {}
    rows = _duplicate_interface_element_nodal_rows()
    rows[10] = rows[10][1:]
    fake_dpf = _duplicate_interface_element_nodal_dpf(rows, captured)
    mesh = _FakeMesh(
        nodes={1: [0.0, 0.0, 0.0], 2: [0.0, 2.0, 0.0], 3: [-1.0, 0.0, 0.0]},
        elements={10: [3, 1, 2]},
        unit="mm",
    )

    with pytest.raises(
        RuntimeError,
        match=r"element=10, rows=2, nodes=3",
    ):
        extraction.static_duplicate_interface_resultants(
            fake_dpf,
            object(),
            object(),
            mesh,
            {1: [0.0, 0.0, 0.0], 2: [0.0, 0.0, 0.0]},
            7,
            [0.0, 0.0, 0.0],
            [
                {
                    "role": "negative_tangent",
                    "sign": 1,
                    "element_ids": [10],
                    "node_ids": [1, 2],
                }
            ],
            1,
        )


def test_static_force_series_publishes_signed_duplicate_interface_resultants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_dpf = _duplicate_interface_element_nodal_dpf(
        _duplicate_interface_element_nodal_rows(), captured
    )
    element_nodes = {10: [3, 1, 2], 20: [6, 5, 4]}

    class SolidElements(_FakeElements):
        def element_by_id(self, element_id: int) -> Any:
            element = super().element_by_id(element_id)
            element.shape = "solid"
            return element

    def mesh_from_nodes(nodes: dict[int, list[float]]) -> _FakeMesh:
        mesh = _FakeMesh(nodes=nodes, elements=element_nodes, unit="mm")
        mesh.elements = SolidElements(element_nodes)
        return mesh

    reference_nodes = {
        1: [0.0, 0.0, 0.0],
        2: [0.0, 2.0, 0.0],
        3: [-1.0, 0.0, 0.0],
        4: [0.0, 0.0, 0.0],
        5: [0.0, 2.0, 0.0],
        6: [1.0, 0.0, 0.0],
    }
    displacements = {
        1: [0.0, 0.0, 1.0],
        2: [0.0, 0.0, 0.0],
        3: [0.0, 0.0, 0.0],
        4: [0.0, 1.0, 0.0],
        5: [0.0, 0.0, 2.0],
        6: [0.0, 0.0, 0.0],
    }
    reference_mesh = mesh_from_nodes(reference_nodes)
    deformed_mesh = mesh_from_nodes(
        {
            node_id: [
                reference_nodes[node_id][index] + displacements[node_id][index]
                for index in range(3)
            ]
            for node_id in reference_nodes
        }
    )
    terms = [
        {
            "role": "negative_tangent",
            "sign": 1,
            "element_ids": [10],
            "node_ids": [1, 2],
        },
        {
            "role": "positive_tangent",
            "sign": -1,
            "element_ids": [20],
            "node_ids": [4, 5],
        },
    ]

    class FakeModel:
        metadata = types.SimpleNamespace(
            result_info=types.SimpleNamespace(available_results=["element_nodal_forces"])
        )

    fake_dpf.__version__ = "0.16.1"
    fake_dpf.DataSources = lambda path: types.SimpleNamespace(path=path)
    fake_dpf.Model = lambda _data_sources: FakeModel()
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(extraction, "preflight_dpf_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        extraction,
        "create_streams_container",
        lambda *_args, **_kwargs: types.SimpleNamespace(release_handles=lambda: None),
    )
    monkeypatch.setattr(
        extraction,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([10, 20], "Elemental"),
            "DUPLICATE_INTERFACE",
            ["DUPLICATE_INTERFACE"],
        ),
    )
    monkeypatch.setattr(
        extraction, "selected_element_mesh", lambda *_args, **_kwargs: reference_mesh
    )
    monkeypatch.setattr(
        extraction,
        "nodal_displacements_for_ids",
        lambda *_args, **_kwargs: (
            displacements,
            {
                "geometry_state": "deformed",
                "result_set_id": 7,
                "mesh_unit": "mm",
                "displacement_unit": "mm",
            },
        ),
    )
    monkeypatch.setattr(
        extraction,
        "mesh_with_nodal_displacements",
        lambda *_args, **_kwargs: deformed_mesh,
    )

    def duplicate_scope(
        *_args: Any, **_kwargs: Any
    ) -> tuple[_FakeScoping, _FakeScoping, dict[str, Any]]:
        return (
            _FakeScoping([10, 20], "Elemental"),
            _FakeScoping([1, 2, 4, 5], "Nodal"),
            {
                "raw_element_ids": [10, 20],
                "raw_node_ids": [1, 2, 3, 4, 5, 6],
                "cut_element_ids": [10, 20],
                "selected_node_ids": [1, 2, 4, 5],
                "moment_reference_node_ids": [1, 2],
                "cut_element_count": 2,
                "selected_node_count": 4,
                "not_cut_element_count": 0,
                "element_failure_count": 0,
                "moment_reference_centroid": [0.0, 1.0, 0.0],
                "selected_node_centroid": [0.0, 1.0, 0.0],
                "force_summation_policy": (
                    "coordinate_matched_duplicate_tangent_interface"
                ),
                "force_summation_terms": terms,
            },
        )

    monkeypatch.setattr(extraction, "construction_surface_scoping", duplicate_scope)
    monkeypatch.setattr(
        extraction,
        "projected_section_geometry_from_mesh",
        lambda *_args, **_kwargs: {},
    )
    axes = [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    selected_sets = [{"id": 7, "value": 2.5, "unit": "s"}]

    series = extraction.static_force_moment_series(
        core.SectionConfig(
            analysis_mode="static",
            modal_rst="duplicate-interface.rst",
            element_named_selection="DUPLICATE_INTERFACE",
            coordinate_system_origin=[1.0, 0.0, 0.0],
            coordinate_system_axes={"x": axes[0], "y": axes[1], "z": axes[2]},
            reference_frame_motion="fixed",
            section_normal_axis="x",
            extraction_side="positive",
        ),
        axes,
        selected_sets,
        capture_nodal_vectors=True,
        capture_animation_frames=False,
    )

    global_origin = [7.0, 15.0, 0.0, 10.0, 10.0, 3.0]
    reference_global = [7.0, 15.0, 0.0, 10.0, 10.0, -12.0]
    local = [15.0, -7.0, 0.0, 10.0, -10.0, -12.0]
    assert series["aggregate_result_sources"] == [
        "dpf_element_nodal_signed_duplicate_interface"
    ]
    assert series["resultants_global_origin"][0] == pytest.approx(global_origin)
    assert series["resultants_reference_global"][0] == pytest.approx(reference_global)
    assert series["resultants_local"][0] == pytest.approx(local)
    assert series["resultants_local"][0] == pytest.approx(
        core.rotate_to_local(reference_global, axes)
    )
    static_set = series["static_set_results"][0]
    assert static_set["resultant_global_origin"] == pytest.approx(global_origin)
    assert static_set["resultant_reference_global"] == pytest.approx(reference_global)
    assert static_set["resultant_local"] == pytest.approx(local)

    history_data = {
        "analysis_mode": "static",
        "times": series["times"],
        "result_set_ids": series["result_set_ids"],
        "selected_result_sets": selected_sets,
        "result_units": series["result_units"],
        "resultants_global": series["resultants_global"],
        "resultants_local": series["resultants_local"],
    }
    global_history = visualization.result_component_history(history_data, "global")
    local_history = visualization.result_component_history(history_data, "local")
    assert global_history["force"]["components"]["x"] == [7.0]
    assert global_history["force"]["components"]["y"] == [15.0]
    assert global_history["moment"]["components"]["x"] == [10.0]
    assert global_history["moment"]["components"]["y"] == [10.0]
    assert global_history["moment"]["components"]["z"] == [3.0]
    assert local_history["force"]["components"]["x"] == [15.0]
    assert local_history["force"]["components"]["y"] == [-7.0]
    assert local_history["moment"]["components"]["x"] == [10.0]
    assert local_history["moment"]["components"]["y"] == [-10.0]
    assert local_history["moment"]["components"]["z"] == [-12.0]


def test_fixed_section_scope_keeps_reference_membership_with_deformed_coordinates() -> None:
    reference_mesh = _FakeMesh(
        nodes={1: [-1.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        elements={10: [1, 2]},
    )
    deformed_mesh = _FakeMesh(
        nodes={1: [4.0, 0.0, 0.0], 2: [6.0, 0.0, 0.0]},
        elements={10: [1, 2]},
    )
    _element_scope, _node_scope, reference_info = (
        visualization.construction_surface_scoping(
            _FakeDpf,
            object(),
            _FakeScoping([10], "elemental"),
            core.SectionConfig(
                coordinate_system_origin=[0.0, 0.0, 0.0],
                coordinate_system_axes={
                    "x": [1.0, 0.0, 0.0],
                    "y": [0.0, 1.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                },
                section_normal_axis="x",
                extraction_side="positive",
            ),
            core.validate_axes(
                {
                    "x": [1.0, 0.0, 0.0],
                    "y": [0.0, 1.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                }
            ),
            mesh=reference_mesh,
        )
    )

    evidence = visualization.side_filter_with_mesh_coordinates(
        reference_info,
        deformed_mesh,
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        scoping_geometry_state="reference",
    )

    assert evidence["cut_element_ids"] == [10]
    assert evidence["selected_node_ids"] == [2]
    assert evidence["selected_node_coordinates"] == {"2": [6.0, 0.0, 0.0]}
    assert evidence["selected_node_centroid"] == [6.0, 0.0, 0.0]
    assert evidence["scoping_geometry_state"] == "reference"
    assert evidence["coordinate_geometry_state"] == "deformed"


def test_deformed_mesh_changes_cut_elements_nodes_and_grid_points() -> None:
    reference_mesh = _FakeMesh(
        nodes={
            1: [-1.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
            3: [2.0, 0.0, 0.0],
            4: [3.0, 0.0, 0.0],
        },
        elements={10: [1, 2], 20: [3, 4]},
        grid=_FakeGrid(
            points=[
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
            ],
            cells=[2, 0, 1, 2, 2, 3],
            celltypes=[3, 3],
        ),
        unit="mm",
    )


def _static_animation_test_topology(
    *,
    follow_geometry: bool = False,
) -> tuple[core.StaticAnimationTopology, core.SectionConfig]:
    np = pytest.importorskip("numpy")
    config = core.SectionConfig(
        analysis_mode="static",
        static_set_scope="range",
        modal_rst="animation-test.rst",
        element_named_selection="CUT_SMALL",
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        reference_frame_motion=(
            "follow-geometry" if follow_geometry else "fixed"
        ),
        section_normal_axis="x",
        extraction_side="positive",
        side_filter_tolerance=1.0e-10,
    )
    reference_points = np.asarray(
        [
            [-1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [2.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    tracking_ids = (1, 2, 3, 4) if follow_geometry else tuple()
    tracking_indices = (
        np.asarray([0, 1, 2, 3], dtype=np.int64)
        if follow_geometry
        else np.asarray([], dtype=np.int64)
    )
    topology = core.StaticAnimationTopology(
        node_ids=(1, 2, 3, 4),
        displacement_node_ids=(1, 2, 3, 4),
        reference_points=reference_points,
        displacement_reference_points=reference_points.copy(),
        cells=np.asarray([3, 0, 1, 2, 3, 1, 3, 2], dtype=np.int64),
        celltypes=np.asarray([5, 5], dtype=np.uint8),
        element_ids=(10, 20),
        element_node_ids={10: (1, 2, 3), 20: (2, 4, 3)},
        connectivity_point_indices=np.asarray(
            [0, 1, 2, 1, 3, 2], dtype=np.int64
        ),
        element_offsets=np.asarray([0, 3], dtype=np.int64),
        mesh_displacement_indices=np.asarray([0, 1, 2, 3], dtype=np.int64),
        tracking_node_ids=tracking_ids,
        tracking_displacement_indices=tracking_indices,
        element_name="CUT_SMALL",
        available_named_selections=("CUT_SMALL",),
        mesh_unit="mm",
        mesh_config=dict(config.__dict__),
        origin_unit_conversion=None,
        attachment={
            "source": "local_section_cut_neighborhood",
            "selection": "CUT_SMALL",
        },
    )
    return topology, config


def _static_animation_test_session(
    result_values: tuple[float, ...] = (0.0, 10.0),
    *,
    follow_geometry: bool = False,
    ram_limit_bytes: int = core.STATIC_ANIMATION_RAM_LIMIT_BYTES,
) -> core.StaticAnimationSession:
    topology, config = _static_animation_test_topology(
        follow_geometry=follow_geometry
    )
    selected_sets = [
        {
            "id": index + 1,
            "value": float(value),
            "unit": "s",
            "label": f"Set {index + 1}",
        }
        for index, value in enumerate(result_values)
    ]
    return core.StaticAnimationSession(
        core.static_animation_session_signature(config, selected_sets),
        topology,
        selected_sets,
        ram_limit_bytes=ram_limit_bytes,
    )
    displacements = {
        1: [5.0, 0.0, 0.0],
        2: [5.0, 0.0, 0.0],
        3: [-3.0, 0.0, 0.0],
        4: [-3.0, 0.0, 0.0],
    }
    deformed_mesh = visualization.mesh_with_nodal_displacements(
        reference_mesh,
        displacements,
        {"geometry_state": "deformed", "result_set_id": 2},
    )
    config = core.SectionConfig(
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        section_normal_axis="x",
        extraction_side="positive",
    )
    element_scoping = _FakeScoping([10, 20], "elemental")
    axes = core.validate_axes(config.coordinate_system_axes)
    _, reference_node_scope, reference_info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        element_scoping,
        config,
        axes,
        mesh=reference_mesh,
    )
    _, deformed_node_scope, deformed_info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        element_scoping,
        config,
        axes,
        mesh=deformed_mesh,
    )

    assert reference_info["cut_element_ids"] == [10]
    assert reference_node_scope.ids == [2]
    assert deformed_info["cut_element_ids"] == [20]
    assert deformed_node_scope.ids == [4]
    assert deformed_info["selected_node_coordinates"] == {"4": [0.0, 0.0, 0.0]}
    assert visualization.mesh_grid_payload(deformed_mesh)["points"] == [
        [4.0, 0.0, 0.0],
        [6.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    assert deformed_mesh.elements.element_by_id(10).node_ids == [1, 2]
    change = visualization.deformation_scope_change_evidence(
        reference_info,
        deformed_info,
    )
    assert change["element_membership_changed"] is True
    assert change["added_cut_element_ids_preview"] == [20]
    assert change["removed_cut_element_ids_preview"] == [10]


def test_construction_surface_scoping_can_preview_zero_cut_elements() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [2.0, 0.0, 0.0],
            2: [3.0, 0.0, 0.0],
            3: [4.0, 0.0, 0.0],
        },
        elements={10: [1, 2], 20: [2, 3]},
    )
    config = core.SectionConfig(
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        section_normal_axis="x",
        extraction_side="positive",
        side_filter_tolerance=1.0e-8,
    )
    axes = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]

    with pytest.raises(ValueError, match="selected zero elements"):
        visualization.construction_surface_scoping(
            _FakeDpf,
            object(),
            _FakeScoping([10, 20], "elemental"),
            config,
            axes,
            mesh=mesh,
        )

    elem_scope, node_scope, info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([10, 20], "elemental"),
        config,
        axes,
        mesh=mesh,
        allow_empty_cut=True,
    )

    assert elem_scope.ids == []
    assert node_scope.ids == []
    assert info["cut_status"] == "no_cut"
    assert info["cut_element_count"] == 0
    assert info["selected_node_count"] == 0
    assert info["raw_node_count"] == 3
    assert info["moment_reference_centroid"] == [3.0, 0.0, 0.0]

    payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=config,
        axes=axes,
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info=info,
    )
    assert payload["cut_element_ids"] == []
    assert payload["force_summation_node_ids"] == []
    assert payload["warnings"] == [
        "Construction plane cuts zero selected elements; adjust origin, normal, or tolerance."
    ]


def test_section_plane_corners_bound_points_in_plane_axes() -> None:
    corners = visualization.section_plane_corners(
        [0.0, 0.0, 0.0],
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "z",
        [[-1.0, -2.0, 3.0], [3.0, 2.0, -1.0]],
    )

    assert corners == [
        [-1.2, -2.2, 0.0],
        [3.2, -2.2, 0.0],
        [3.2, 2.2, 0.0],
        [-1.2, 2.2, 0.0],
    ]


def test_projected_section_geometry_uses_unpadded_local_plane_spans() -> None:
    geometry = visualization.projected_section_geometry(
        [0.0, 0.0, 0.0],
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "x",
        [[0.0, -0.002, -0.003], [0.0, 0.004, 0.007]],
        source_unit="m",
        point_source="selected_side_nodes",
    )

    assert geometry["width_axis"] == "y"
    assert geometry["height_axis"] == "z"
    assert geometry["unit"] == "mm"
    assert geometry["point_source"] == "selected_side_nodes"
    assert geometry["point_count"] == 2
    assert geometry["width_mm"] == pytest.approx(6.0)
    assert geometry["height_mm"] == pytest.approx(10.0)
    assert geometry["area_mm2"] == pytest.approx(60.0)


def test_section_plane_corners_preserve_small_meter_cut_bounds() -> None:
    corners = visualization.section_plane_corners(
        [0.051, 0.0, 0.0],
        [
            [0.0, 0.0, -1.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
        ],
        "z",
        [
            [0.055, -0.00494, -0.005],
            [0.055, 0.00494, 0.005],
        ],
    )

    y_values = [corner[1] for corner in corners]
    z_values = [corner[2] for corner in corners]
    assert max(y_values) - min(y_values) == pytest.approx(0.010868)
    assert max(z_values) - min(z_values) == pytest.approx(0.011)


def test_section_visualization_plane_uses_selected_named_selection_nodes() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [-1.0, -2.0, 0.0],
            2: [3.0, 2.0, 0.0],
        },
        elements={10: [1, 2]},
        grid=_FakeGrid(
            points=[
                [-100.0, -100.0, 0.0],
                [100.0, 100.0, 0.0],
            ],
            cells=[2, 0, 1],
            celltypes=[3],
        ),
    )
    config = core.SectionConfig(
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        section_normal_axis="z",
        extraction_side="positive",
    )

    payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=config,
        axes=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info={
            "raw_element_ids": [10],
            "cut_element_ids": [10],
            "selected_node_ids": [2],
        },
    )

    assert payload["plane"]["corners"] == [
        [-1.2, -2.2, 0.0],
        [3.2, -2.2, 0.0],
        [3.2, 2.2, 0.0],
        [-1.2, 2.2, 0.0],
    ]
    assert payload["section_geometry"]["point_source"] == "cut_element_nodes"
    assert payload["section_geometry"]["width_mm"] == pytest.approx(4000.0)
    assert payload["section_geometry"]["height_mm"] == pytest.approx(4000.0)
    assert payload["section_geometry"]["area_mm2"] == pytest.approx(16000000.0)


def test_section_visualization_plane_prefers_selected_side_nodes() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.051, -0.5, -0.5],
            2: [0.051, 0.5, 0.5],
            3: [0.055, -0.00494, -0.005],
            4: [0.055, 0.00494, 0.005],
        },
        elements={10: [1, 2], 20: [3, 4]},
        grid=_FakeGrid(
            points=[
                [0.051, -0.5, -0.5],
                [0.051, 0.5, 0.5],
                [0.055, -0.00494, -0.005],
                [0.055, 0.00494, 0.005],
            ],
            cells=[2, 0, 1, 2, 2, 3],
            celltypes=[3, 3],
        ),
    )
    config = core.SectionConfig(
        coordinate_system_origin=[0.051, 0.0, 0.0],
        coordinate_system_axes={
            "x": [0.0, 0.0, -1.0],
            "y": [0.0, 1.0, 0.0],
            "z": [1.0, 0.0, 0.0],
        },
        section_normal_axis="z",
        extraction_side="positive",
    )
    payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=config,
        axes=core.validate_axes(config.coordinate_system_axes),
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info={
            "raw_element_ids": [10, 20],
            "cut_element_ids": [20],
            "selected_node_ids": [3, 4],
            "selected_node_coordinates": {
                "3": [0.055, -0.00494, -0.005],
                "4": [0.055, 0.00494, 0.005],
            },
            "raw_element_count": 2,
            "cut_element_count": 1,
            "selected_node_count": 2,
        },
    )

    y_values = [corner[1] for corner in payload["plane"]["corners"]]
    z_values = [corner[2] for corner in payload["plane"]["corners"]]
    assert payload["plane"]["point_source"] == "selected_side_nodes"
    assert max(y_values) - min(y_values) == pytest.approx(0.010868)
    assert max(z_values) - min(z_values) == pytest.approx(0.011)
    assert payload["section_geometry"]["width_axis"] == "x"
    assert payload["section_geometry"]["height_axis"] == "y"
    assert payload["section_geometry"]["width_mm"] == pytest.approx(10.0)
    assert payload["section_geometry"]["height_mm"] == pytest.approx(9.88)
    assert payload["section_geometry"]["area_mm2"] == pytest.approx(98.8)


def test_section_visualization_payload_maps_cut_cells_and_force_nodes() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [-1.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
            3: [2.0, 0.0, 0.0],
            4: [3.0, 0.0, 0.0],
        },
        elements={10: [1, 2], 20: [3, 4]},
        grid=_FakeGrid(
            points=[
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [2.0, 0.0, 0.0],
                [3.0, 0.0, 0.0],
            ],
            cells=[2, 0, 1, 2, 2, 3],
            celltypes=[3, 3],
        ),
    )
    side_filter_info = {
        "raw_element_ids": [10, 20],
        "cut_element_ids": [10],
        "selected_node_ids": [2],
        "raw_element_count": 2,
        "cut_element_count": 1,
        "selected_node_count": 1,
        "selected_node_centroid": [1.0, 0.0, 0.0],
        "moment_reference_centroid": [-1.0, 0.0, 0.0],
        "cut_element_ids_preview": [10],
    }
    config = core.SectionConfig(
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        section_normal_axis="x",
        extraction_side="positive",
    )

    payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=config,
        axes=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info=side_filter_info,
        dpf_version="fake",
    )

    assert payload["element_named_selection"] == "CUT"
    assert payload["cut_cell_indices"] == [0]
    assert payload["missing_cut_element_ids"] == []
    assert payload["force_summation_node_ids"] == [2]
    assert payload["force_summation_nodes"] == [{"id": 2, "xyz": [1.0, 0.0, 0.0]}]
    assert payload["moment_reference_label"] == "Moment reference: Coordinate system origin"
    assert payload["moment_reference_xyz"] == [0.0, 0.0, 0.0]
    assert payload["counts"]["raw_element_count"] == 2
    assert payload["counts"]["cut_element_count"] == 1
    assert payload["counts"]["force_summation_node_count"] == 1


def test_config_with_origin_in_mesh_units_converts_far_mm_origin() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.049, -0.005, -0.005],
            2: [0.051, 0.005, 0.005],
            3: [0.052, 0.0, 0.0],
        },
        elements={19: [1, 2, 3]},
        grid=_FakeGrid(
            points=[
                [0.049, -0.005, -0.005],
                [0.051, 0.005, 0.005],
                [0.052, 0.0, 0.0],
            ],
            cells=[3, 0, 1, 2],
            celltypes=[5],
        ),
    )
    config = core.SectionConfig(coordinate_system_origin=[51.0, 0.0, 0.0])

    normalized, conversion = visualization.config_with_origin_in_mesh_units(config, mesh)

    assert config.coordinate_system_origin == [51.0, 0.0, 0.0]
    assert normalized.coordinate_system_origin == pytest.approx([0.051, 0.0, 0.0])
    assert conversion is not None
    assert conversion["source_unit"] == "mm"
    assert conversion["mesh_unit"] == "m"
    assert conversion["factor"] == pytest.approx(0.001)


def test_config_with_origin_in_mesh_units_always_treats_origin_as_gui_mm() -> None:
    mesh = _FakeMesh(
        nodes={1: [1.0, 0.0, 0.0], 2: [1.01, 0.0, 0.0]},
        elements={19: [1, 2]},
        grid=_FakeGrid(
            points=[[1.0, 0.0, 0.0], [1.01, 0.0, 0.0]],
            cells=[2, 0, 1],
            celltypes=[3],
        ),
    )
    config = core.SectionConfig(coordinate_system_origin=[1.0, 0.0, 0.0])

    normalized, conversion = visualization.config_with_origin_in_mesh_units(config, mesh)

    assert normalized.coordinate_system_origin == pytest.approx([0.001, 0.0, 0.0])
    assert conversion is not None
    assert conversion["source_unit"] == core.GUI_ORIGIN_UNIT
    assert conversion["mesh_unit"] == "m"


def test_config_with_origin_in_mesh_units_does_not_guess_centimeters() -> None:
    mesh = _FakeMesh(
        nodes={1: [0.51, 0.0, 0.0], 2: [0.52, 0.0, 0.0]},
        elements={19: [1, 2]},
        grid=_FakeGrid(
            points=[[0.51, 0.0, 0.0], [0.52, 0.0, 0.0]],
            cells=[2, 0, 1],
            celltypes=[3],
        ),
    )
    config = core.SectionConfig(coordinate_system_origin=[51.0, 0.0, 0.0])

    normalized, conversion = visualization.config_with_origin_in_mesh_units(config, mesh)

    assert normalized.coordinate_system_origin == pytest.approx([0.051, 0.0, 0.0])
    assert conversion is not None
    assert conversion["source_unit"] == core.GUI_ORIGIN_UNIT


def test_visualization_payload_uses_mesh_unit_origin_for_camera_bounds() -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.049, -0.005, -0.005],
            2: [0.051, 0.005, 0.005],
            3: [0.052, 0.0, 0.0],
        },
        elements={19: [1, 2, 3]},
        grid=_FakeGrid(
            points=[
                [0.049, -0.005, -0.005],
                [0.051, 0.005, 0.005],
                [0.052, 0.0, 0.0],
            ],
            cells=[3, 0, 1, 2],
            celltypes=[5],
        ),
    )
    config = core.SectionConfig(
        coordinate_system_origin=[51.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [0.0, 0.0, -1.0],
            "y": [0.0, 1.0, 0.0],
            "z": [1.0, 0.0, 0.0],
        },
        section_normal_axis="x",
        extraction_side="positive",
        moment_reference_mode="coordinate_system_origin",
    )
    axes = core.validate_axes(config.coordinate_system_axes)
    normalized, conversion = visualization.config_with_origin_in_mesh_units(config, mesh)
    _elem_scope, _node_scope, side_filter_info = visualization.construction_surface_scoping(
        _FakeDpf,
        object(),
        _FakeScoping([19], "elemental"),
        normalized,
        axes,
        mesh=mesh,
    )

    old_payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=config,
        axes=axes,
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info=side_filter_info,
    )
    payload = visualization.section_visualization_payload_from_mesh(
        mesh=mesh,
        config=normalized,
        axes=axes,
        element_name="CUT",
        available_named=["CUT"],
        side_filter_info=side_filter_info,
        origin_unit_conversion=conversion,
    )

    assert old_payload["moment_reference_xyz"] == [51.0, 0.0, 0.0]
    assert visualization.visualization_scene_extent(old_payload) > 50.0
    assert payload["coordinate_system_origin"] == pytest.approx([0.051, 0.0, 0.0])
    assert payload["moment_reference_xyz"] == pytest.approx([0.051, 0.0, 0.0])
    assert payload["plane"]["origin"] == pytest.approx([0.051, 0.0, 0.0])
    assert payload["coordinate_system_origin_unit_conversion"]["source_unit"] == "mm"
    assert payload["result_signature"]["coordinate_system_origin"] == pytest.approx(
        [0.051, 0.0, 0.0]
    )
    assert payload["result_signature"]["mesh_unit"] == "m"
    assert visualization.visualization_scene_extent(payload) < 2.0


def test_visualization_bottom_ruler_uses_mm_scale() -> None:
    payload = {
        "mesh_unit": "m",
        "mesh": {
            "points": [
                [0.0, 0.0, 0.0],
                [0.2, 0.0, 0.0],
                [0.2, 0.1, 0.0],
                [0.0, 0.1, 0.0],
            ]
        },
        "plane": {
            "corners": [
                [0.0, 0.0, 0.0],
                [0.2, 0.0, 0.0],
                [0.2, 0.1, 0.0],
                [0.0, 0.1, 0.0],
            ]
        },
    }

    pointa, pointb, scale = visualization.visualization_bottom_ruler(payload)

    assert pointa == pytest.approx([0.0, -0.016, 0.0])
    assert pointb == pytest.approx([0.2, -0.016, 0.0])
    assert scale == pytest.approx(1000.0)


def test_add_visualization_bottom_ruler_adds_pyvista_ruler_in_mm() -> None:
    payload = {
        "mesh_unit": "cm",
        "plane": {
            "corners": [
                [0.0, 0.0, 0.0],
                [20.0, 0.0, 0.0],
                [20.0, 10.0, 0.0],
                [0.0, 10.0, 0.0],
            ]
        },
    }
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class FakePlotter:
        def add_ruler(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

    visualization.add_visualization_bottom_ruler(FakePlotter(), payload)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == pytest.approx([0.0, -1.6, 0.0])
    assert args[1] == pytest.approx([20.0, -1.6, 0.0])
    assert kwargs["title"] == "Distance [mm]"
    assert kwargs["scale"] == pytest.approx(10.0)


def test_add_visualization_ruler_can_hide_ruler() -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class FakePlotter:
        def add_ruler(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

        def add_actor(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

    visualization.add_visualization_ruler(
        FakePlotter(),
        {"mesh_unit": "m", "plane": {"corners": [[0.0, 0.0, 0.0]] * 4}},
        visible=False,
    )

    assert calls == []


def test_add_visualization_ruler_uses_default_plane_edge_mode() -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class FakePlotter:
        def add_ruler(self, *args: Any, **kwargs: Any) -> None:
            calls.append((args, kwargs))

    visualization.add_visualization_ruler(
        FakePlotter(),
        {
            "mesh_unit": "m",
            "plane": {
                "corners": [
                    [0.0, 0.0, 0.0],
                    [0.2, 0.0, 0.0],
                    [0.2, 0.1, 0.0],
                    [0.0, 0.1, 0.0],
                ]
            },
        },
    )

    assert len(calls) == 1
    assert calls[0][1]["scale"] == pytest.approx(1000.0)


def test_add_visualization_ruler_can_use_static_viewport_bottom_actor() -> None:
    actors: list[tuple[Any, dict[str, Any]]] = []

    class FakeCamera:
        parallel_projection = True
        parallel_scale = 0.1

    class FakePlotter:
        camera = FakeCamera()
        window_size = (1000, 500)

        def add_actor(self, actor: Any, **kwargs: Any) -> None:
            actors.append((actor, kwargs))

    plotter = FakePlotter()
    returned = visualization.add_visualization_static_bottom_ruler(
        plotter,
        {"mesh_unit": "m", "plane": {"corners": []}},
    )

    assert len(actors) == 1
    actor, kwargs = actors[0]
    assert returned is actor
    assert kwargs == {"reset_camera": False, "pickable": False}
    assert actor.GetTitle() == "Distance [mm]"
    assert actor.GetRange() == pytest.approx((0.0, 256.0))
    assert actor.GetPositionCoordinate().GetCoordinateSystemAsString() == (
        "Normalized Viewport"
    )
    assert actor.GetPosition2Coordinate().GetCoordinateSystemAsString() == (
        "Normalized Viewport"
    )
    assert actor.GetPositionCoordinate().GetValue() == pytest.approx(
        (0.18, visualization.VISUALIZATION_STATIC_RULER_VIEWPORT_Y, 0.0)
    )
    assert actor.GetPosition2Coordinate().GetValue() == pytest.approx(
        (0.82, visualization.VISUALIZATION_STATIC_RULER_VIEWPORT_Y, 0.0)
    )


def test_nodal_force_scalar_bar_args_place_vertical_legend_on_left() -> None:
    args = visualization.nodal_force_scalar_bar_args("N")

    assert args["title"] == "Nodal force [N]"
    assert args["vertical"] is True
    assert args["position_x"] < 0.1
    assert args["position_y"] > visualization.VISUALIZATION_STATIC_RULER_VIEWPORT_Y
    assert args["height"] > args["width"]
    assert args["width"] <= 0.055
    assert args["title_font_size"] == 9
    assert args["label_font_size"] == 8


def test_run_gui_main_panel_collapses_to_left_rail(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(core.SectionConfig()) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        splitter = window.run_log_splitter
        tolerance_label = next(
            label
            for label in window.findChildren(qt_widgets.QLabel)
            if label.text() == "Side tolerance"
        )

        assert window.tolerance_edit.toolTip() == core.SIDE_TOLERANCE_TOOLTIP
        assert tolerance_label.toolTip() == core.SIDE_TOLERANCE_TOOLTIP

        assert window._main_panel_collapsed is False
        assert window.main_panel_stack.currentWidget() is window.main_panel_expanded_widget
        assert (
            window.input_inspector_scroll_area.widget()
            is window.input_inspector_content
        )
        assert (
            window.input_files_group.parentWidget()
            is window.input_inspector_content
        )
        assert not window.input_inspector_scroll_area.isAncestorOf(
            window.input_action_footer
        )
        assert window.input_action_footer.isAncestorOf(window.run_button)
        assert window.input_action_footer.isAncestorOf(window.status_label)
        assert (
            window.main_panel_collapse_button.parentWidget()
            is window.input_files_group.header_widget
        )
        assert "maximize the 3D view" in window.main_panel_collapse_button.toolTip()
        assert window.main_panel_expand_button.toolTip() == "Restore the input panel"

        window.set_main_panel_collapsed(True)
        qapp.processEvents()

        assert window._main_panel_collapsed is True
        assert window.main_panel_stack.currentWidget() is window.main_panel_collapsed_widget
        assert window.main_panel_stack.minimumWidth() == gui.VISUALIZATION_DOCK_COLLAPSED_WIDTH
        assert window.main_panel_stack.maximumWidth() == gui.VISUALIZATION_DOCK_COLLAPSED_WIDTH
        assert window._main_panel_expanded_width >= gui.VISUALIZATION_DOCK_MIN_WIDTH
        assert window.run_log_splitter is splitter

        window.set_main_panel_collapsed(False)
        qapp.processEvents()

        assert window._main_panel_collapsed is False
        assert window.main_panel_stack.currentWidget() is window.main_panel_expanded_widget
        assert window.main_panel_stack.maximumWidth() > gui.VISUALIZATION_DOCK_COLLAPSED_WIDTH
        assert window.run_log_splitter is splitter
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_starts_maximized(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(core.SectionConfig()) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        assert window.windowState() & qt_core.Qt.WindowState.WindowMaximized
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_extraction_failure_shows_actionable_exception_text(
    qapp: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PyQt6 import QtWidgets as qt_widgets

    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    gui.run_gui(core.SectionConfig())
    window = qapp._mcf_dpf_section_resultants_window
    dialogs: list[tuple[Any, ...]] = []
    try:
        monkeypatch.setattr(
            window,
            "_show_themed_error_dialog",
            lambda *args: dialogs.append(args),
        )
        window.run_button.setEnabled(False)

        window.on_failed(
            "Enable Nodal Forces and re-solve.",
            "Traceback (most recent call last):\nMissingElementNodalForceDataError",
        )

        assert window.run_button.isEnabled() is True
        assert window.status_label.text() == "Failed"
        assert dialogs == [
            (
                "Extraction failed",
                "Enable Nodal Forces and re-solve.",
                "Traceback (most recent call last):\nMissingElementNodalForceDataError",
            )
        ]
        assert "MissingElementNodalForceDataError" in window.log.toPlainText()
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_input_groups_collapse_independently_and_preserve_state(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(
        core.SectionConfig(
            analysis_mode="static",
            reference_frame_motion="follow-geometry",
        )
    ) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        expanded_groups = (window.input_files_group,)
        collapsed_groups = (
            window.section_parameters_group,
            window.orientation_group,
            window.section_cut_group,
            window.reference_frame_advanced_group,
        )
        splitter = window.run_log_splitter
        tolerance_edit = window.tolerance_edit
        origin_edits = tuple(window.origin_edits)
        axis_edits = {
            axis: tuple(edits) for axis, edits in window.axis_edits.items()
        }
        log = window.log
        tolerance_edit.setText("0.125")
        log.setPlainText("diagnostics stay here")

        assert window.input_inspector_scroll_area.widgetResizable() is True
        assert (
            window.input_inspector_scroll_area.horizontalScrollBarPolicy()
            == _qt_core.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for group in expanded_groups:
            assert group.is_expanded() is True
            assert group.body_widget.isHidden() is False
            assert group.toggle_button.toolTip().startswith("Collapse ")
        for group in collapsed_groups:
            assert group.is_expanded() is False
            assert group.body_widget.isHidden() is True
            assert group.toggle_button.toolTip().startswith("Expand ")
        assert window.diagnostics_log_group.is_expanded() is False
        assert window.diagnostics_log_group.body_widget.isHidden() is True

        collapsed_content_height = window.input_inspector_content.sizeHint().height()
        window.orientation_group.toggle_button.clicked.emit()
        qapp.processEvents()
        assert window.orientation_group.is_expanded() is True
        assert window.input_inspector_content.sizeHint().height() > (
            collapsed_content_height
        )
        window.orientation_group.toggle_button.clicked.emit()
        qapp.processEvents()
        assert window.orientation_group.is_expanded() is False

        compact_log_height = splitter.sizes()[1]
        window.diagnostics_log_group.toggle_button.clicked.emit()
        qapp.processEvents()
        assert window.diagnostics_log_group.is_expanded() is True
        assert splitter.sizes()[1] > compact_log_height
        window.diagnostics_log_group.toggle_button.clicked.emit()
        qapp.processEvents()
        assert window.diagnostics_log_group.is_expanded() is False

        for selected_group in expanded_groups:
            selected_group.toggle_button.clicked.emit()
            qapp.processEvents()

            margins = selected_group._root_layout.contentsMargins()
            compact_height = (
                selected_group.header_widget.sizeHint().height()
                + margins.top()
                + margins.bottom()
            )
            assert selected_group.is_expanded() is False
            assert selected_group.body_widget.isHidden() is True
            assert selected_group.toggle_button.toolTip().startswith("Expand ")
            assert selected_group.minimumHeight() == compact_height
            assert selected_group.maximumHeight() == compact_height
            assert selected_group.height() == compact_height
            assert (
                selected_group.sizePolicy().verticalPolicy()
                == qt_widgets.QSizePolicy.Policy.Fixed
            )
            assert all(
                group.is_expanded()
                for group in expanded_groups
                if group is not selected_group
            )

            selected_group.toggle_button.clicked.emit()
            qapp.processEvents()
            assert selected_group.is_expanded() is True
            assert selected_group.body_widget.isHidden() is False
            assert selected_group.minimumHeight() == 0
            assert selected_group.maximumHeight() == selected_group._UNBOUNDED_HEIGHT
            assert (
                selected_group.sizePolicy().verticalPolicy()
                == qt_widgets.QSizePolicy.Policy.Preferred
            )

        assert window.tolerance_edit is tolerance_edit
        assert tolerance_edit.text() == "0.125"
        assert tuple(window.origin_edits) == origin_edits
        assert {
            axis: tuple(edits) for axis, edits in window.axis_edits.items()
        } == axis_edits
        assert window.log is log
        assert log.toPlainText() == "diagnostics stay here"
        assert window.run_log_splitter is splitter
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_uses_compact_coordinate_and_orientation_editors(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        assert not [
            label
            for label in window.findChildren(qt_widgets.QLabel)
            if label.objectName() == "rowHelp"
        ]
        origin_layout = window.origin_vector_editor.layout()
        assert all(origin_layout.indexOf(edit) >= 0 for edit in window.origin_edits)
        assert all(edit.toolTip() == core.ORIGIN_TOOLTIP for edit in window.origin_edits)

        orientation_layout = window.orientation_matrix.layout()
        assert all(
            orientation_layout.indexOf(edit) >= 0
            for edits in window.axis_edits.values()
            for edit in edits
        )
        assert all(
            edit.toolTip()
            for edits in window.axis_edits.values()
            for edit in edits
        )
        component_headers = {
            label.text()
            for label in window.findChildren(qt_widgets.QLabel)
            if label.objectName() == "vectorComponentHeader"
        }
        assert {"X", "Y", "Z", "Global X", "Global Y", "Global Z"} <= (
            component_headers
        )
        assert window.orientation_group.is_expanded() is False
        assert window.section_cut_group.is_expanded() is False
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_light_theme_styles_numeric_inputs_in_all_states(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(
        core.SectionConfig(
            analysis_mode="static",
            reference_frame_motion="follow-geometry",
        )
    ) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        stylesheet = " ".join(qapp.styleSheet().split())
        assert (
            "QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {"
            in stylesheet
        )
        assert (
            "QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, "
            "QSpinBox:disabled, QDoubleSpinBox:disabled {"
            in stylesheet
        )
        assert "background: #eef2f3;" in stylesheet
        assert "color: #52616b;" in stylesheet

        numeric_inputs = (
            window.result_set_range_start_spin,
            window.result_set_range_end_spin,
            window.result_set_range_stride_spin,
            window.reference_frame_fit_warning_spin,
            window.modal_batch_spin,
            window.skip_first_modes_spin,
            window.animation_deformation_spin,
        )
        assert all(
            isinstance(widget, (qt_widgets.QSpinBox, qt_widgets.QDoubleSpinBox))
            for widget in numeric_inputs
        )
        assert window.reference_frame_fit_warning_spin.isEnabled()
        window.reference_frame_fit_warning_spin.setEnabled(False)
        assert not window.reference_frame_fit_warning_spin.isEnabled()
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_run_gui_lists_external_cdb_components_without_rst_named_selections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    cdb_export = tmp_path / "named_selections.cdb"
    cdb_export.write_text(
        "CMBLOCK,CUT_NODES,NODE,2\n"
        "(8i10)\n"
        "         1         2\n"
        "CMBLOCK,CUT_BODY,ELEMENT,1\n"
        "(8i10)\n"
        "        10\n",
        encoding="ascii",
    )
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(
        core.SectionConfig(
            external_named_selection_path=str(cdb_export),
            element_named_selection="CUT_BODY",
        )
    ) == 0
    window = qapp._mcf_dpf_section_resultants_window
    qapp.processEvents()
    try:
        assert window._loaded_element_named_selections == ["CUT_NODES", "CUT_BODY"]
        assert window.element_combo.currentText() == "CUT_BODY"
        config = window.collect_config()
        assert config.external_named_selection_path == str(cdb_export)
        assert config.element_named_selection == "CUT_BODY"
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_update_static_ruler_actor_range_tracks_camera_scale() -> None:
    class FakeActor:
        def __init__(self) -> None:
            self.ranges: list[tuple[float, float]] = []

        def SetRange(self, start: float, end: float) -> None:  # noqa: N802
            self.ranges.append((start, end))

    class FakeCamera:
        parallel_projection = True

        def __init__(self) -> None:
            self.parallel_scale = 0.1

    class FakePlotter:
        def __init__(self) -> None:
            self.camera = FakeCamera()
            self.window_size = (1000, 500)

    actor = FakeActor()
    plotter = FakePlotter()
    payload = {"mesh_unit": "m", "plane": {"corners": []}}

    assert visualization.update_static_ruler_actor_range(actor, plotter, payload) is True
    plotter.camera.parallel_scale = 0.2
    assert visualization.update_static_ruler_actor_range(actor, plotter, payload) is True

    assert actor.ranges == pytest.approx([(0.0, 256.0), (0.0, 512.0)])


def test_remove_camera_observer_calls_vtk_remove_observer() -> None:
    class FakeCamera:
        def __init__(self) -> None:
            self.removed: list[int] = []

        def RemoveObserver(self, observer_id: int) -> None:  # noqa: N802
            self.removed.append(observer_id)

    camera = FakeCamera()

    visualization.remove_camera_observer(camera, 42)

    assert camera.removed == [42]


def test_restore_or_reset_plotter_camera_restores_position_and_scale() -> None:
    class FakeCamera:
        def __init__(self) -> None:
            self.parallel_scale = 4.0

    class FakePlotter:
        def __init__(self) -> None:
            self.camera = FakeCamera()
            self.camera_position = ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            self.reset_count = 0

        def reset_camera(self) -> None:
            self.reset_count += 1

    plotter = FakePlotter()
    state = visualization.capture_plotter_camera_state(plotter)
    plotter.camera_position = ((9.0, 9.0, 9.0), (1.0, 1.0, 1.0), (0.0, 1.0, 0.0))
    plotter.camera.parallel_scale = 12.0

    assert visualization.restore_or_reset_plotter_camera(plotter, state) is True

    assert plotter.camera_position == state["camera_position"]
    assert plotter.camera.parallel_scale == pytest.approx(4.0)
    assert plotter.reset_count == 0


def test_restore_or_reset_plotter_camera_resets_without_saved_state() -> None:
    class FakePlotter:
        def __init__(self) -> None:
            self.reset_count = 0

        def reset_camera(self) -> None:
            self.reset_count += 1

    plotter = FakePlotter()

    assert visualization.restore_or_reset_plotter_camera(plotter, None) is False
    assert plotter.reset_count == 1


def test_moment_reference_choice_label_uses_dropdown_text() -> None:
    assert (
        core.moment_reference_choice_label("coordinate_system_origin")
        == "Coordinate system origin"
    )
    assert core.moment_reference_choice_label("custom") == "custom"


def test_coordinate_system_label_displays_origin_in_gui_mm() -> None:
    option = {
        "id": 52,
        "name": "Coordinate System",
        "type": "Cartesian",
        "origin": [0.05, 0.0, 0.0],
        "origin_unit": "m",
    }

    assert dpf_io.coordinate_system_origin_for_gui_units(option) == pytest.approx(
        [50.0, 0.0, 0.0]
    )
    assert "origin[mm]=(50, 0, 0)" in dpf_io.coordinate_system_label(option)


def test_metadata_coordinate_system_options_use_mesh_unit_for_missing_caerep_unit() -> None:
    options = dpf_io.metadata_coordinate_system_options(
        {
            52: {
                "name": "Coordinate System",
                "type": "Cartesian",
                "origin": [0.05, 0.0, 0.0],
                "origin_unit": None,
                "axes": {
                    "x": [1.0, 0.0, 0.0],
                    "y": [0.0, 1.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                },
            }
        },
        {},
        mesh_unit="m",
    )

    option = next(item for item in options if int(item["id"]) == 52)
    assert option["origin_unit"] == "m"
    assert dpf_io.coordinate_system_origin_for_gui_units(option) == pytest.approx(
        [50.0, 0.0, 0.0]
    )


def test_scan_dpf_coordinate_system_options_uses_mesh_unit_for_dpf_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    axes = {
        "x": [1.0, 0.0, 0.0],
        "y": [0.0, 1.0, 0.0],
        "z": [0.0, 0.0, 1.0],
    }
    fake_dpf = types.SimpleNamespace(
        DataSources=lambda path: types.SimpleNamespace(path=path)
    )
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(
        dpf_io,
        "dpf_coordinate_system_transform",
        lambda *_args: ([0.05, 0.0, 0.0], axes),
    )
    monkeypatch.setattr(
        dpf_io,
        "dpf_coordinate_system_type",
        lambda *_args: "Cartesian",
    )

    options = dpf_io.scan_dpf_coordinate_system_options(
        "modal.rst",
        {
            52: {
                "name": "Coordinate System",
                "type": "Cartesian",
                "origin": [50.0, 0.0, 0.0],
                "origin_unit": "mm",
                "axes": axes,
            }
        },
        {},
        [],
        mesh_unit="m",
    )

    option = next(item for item in options if int(item["id"]) == 52)
    assert option["origin_unit"] == "m"
    assert dpf_io.coordinate_system_origin_for_gui_units(option) == pytest.approx(
        [50.0, 0.0, 0.0]
    )


def test_field_vector_rows_by_id_maps_scoping_rows() -> None:
    assert dpf_io.field_vector_rows_by_id(
        _FakeField([10, 20], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    ) == {
        10: [1.0, 2.0, 3.0],
        20: [4.0, 5.0, 6.0],
    }

    assert dpf_io.field_vector_rows_by_id(
        _FakeField([30, 40], [7.0, 8.0, 9.0, 10.0, 11.0, 12.0])
    ) == {
        30: [7.0, 8.0, 9.0],
        40: [10.0, 11.0, 12.0],
    }


def test_combine_modal_nodal_force_vectors_uses_mcf_row() -> None:
    vectors = visualization.combine_modal_nodal_force_vectors(
        {
            1: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            2: [[0.0, 2.0, 0.0], [0.0, 0.0, 3.0]],
        },
        [2.0, 3.0],
        node_coordinates={1: [0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        modes_used=2,
    )

    assert vectors[0]["node_id"] == 1
    assert vectors[0]["origin"] == [0.0, 0.0, 0.0]
    assert vectors[0]["vector"] == [2.0, 3.0, 0.0]
    assert vectors[1]["node_id"] == 2
    assert vectors[1]["origin"] == [1.0, 0.0, 0.0]
    assert vectors[1]["vector"] == [0.0, 4.0, 9.0]


def test_nodal_force_time_export_payload_uses_selected_time() -> None:
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        result_units={"force": "N", "moment": "N mm"},
        mesh_unit="mm",
        section_geometry={
            "width_axis": "x",
            "height_axis": "y",
            "width_mm": 12.0,
            "height_mm": 5.0,
            "area_mm2": 60.0,
            "point_source": "selected_side_nodes",
        },
    )

    export_payload = visualization.build_nodal_force_time_export_payload(result_data, 1)

    assert export_payload is not None
    assert export_payload["time"] == 1.0
    assert export_payload["time_index"] == 1
    assert export_payload["force_unit"] == "N"
    assert export_payload["location_unit"] == "mm"
    assert [row["node_id"] for row in export_payload["rows"]] == [1, 2]
    assert export_payload["rows"][0]["origin"] == [0.0, 0.0, 0.0]
    assert export_payload["rows"][0]["vector"] == [4.0, 5.0, 0.0]
    assert export_payload["rows"][1]["origin"] == [1.0, 0.0, 0.0]
    assert export_payload["rows"][1]["vector"] == [0.0, 8.0, 15.0]


def test_write_nodal_force_time_csv_exports_locations_and_forces(tmp_path: Path) -> None:
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        result_units={"force": "N", "moment": "N mm"},
        mesh_unit="mm",
        section_geometry={
            "width_axis": "x",
            "height_axis": "y",
            "width_mm": 12.0,
            "height_mm": 5.0,
            "area_mm2": 60.0,
            "point_source": "selected_side_nodes",
        },
    )
    export_payload = visualization.build_nodal_force_time_export_payload(result_data, 0)
    assert export_payload is not None
    out_csv = tmp_path / "nodal_forces.csv"

    visualization.write_nodal_force_time_csv(str(out_csv), export_payload)

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == [
        "time_s",
        "node_id",
        "x [mm]",
        "y [mm]",
        "z [mm]",
        "fx_global [N]",
        "fy_global [N]",
        "fz_global [N]",
        "f_magnitude [N]",
    ]
    assert rows[1] == ["0", "1", "0", "0", "0", "2", "3", "0", "3.605551275463989"]
    assert rows[2] == ["0", "2", "1", "0", "0", "0", "4", "9", "9.848857801796104"]


def test_nodal_force_time_excel_payload_adds_local_force_and_reference_moment() -> None:
    _payload, result_data = _result_overlay_fixture()
    signature = dict(result_data["signature"])
    signature["coordinate_system_axes"] = {
        "x": [0.0, 1.0, 0.0],
        "y": [-1.0, 0.0, 0.0],
        "z": [0.0, 0.0, 1.0],
    }
    result_data = dict(
        result_data,
        signature=signature,
        result_units={"force": "N", "moment": "N mm"},
        mesh_unit="mm",
    )

    payload = visualization.build_nodal_force_time_excel_payload(result_data, 0)

    assert payload is not None
    assert payload["rows"][1]["force_global"] == [0.0, 4.0, 9.0]
    assert payload["rows"][1]["force_local"] == [4.0, 0.0, 9.0]
    assert payload["rows"][1]["lever_arm"] == [1.0, 0.0, 0.0]
    assert payload["rows"][1]["moment_global"] == [0.0, -9.0, 4.0]
    assert payload["rows"][1]["moment_local"] == [-9.0, 0.0, 4.0]
    assert payload["force_source_frame"] == "global"
    assert payload["local_axes"] == [
        [0.0, 1.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    assert payload["nodal_totals_global"] == pytest.approx(
        [2.0, 7.0, 9.0, 0.0, -9.0, 4.0]
    )
    assert payload["nodal_totals_local"] == pytest.approx(
        [7.0, -2.0, 9.0, -9.0, 0.0, 4.0]
    )


def test_nodal_force_time_excel_payload_converts_nodal_moments_to_result_unit() -> None:
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        result_units={"force": "N", "moment": "N m"},
        mesh_unit="mm",
    )

    payload = visualization.build_nodal_force_time_excel_payload(result_data, 0)

    assert payload is not None
    assert payload["moment_unit"] == "N m"
    assert payload["nodal_moment_source_unit"] == "N mm"
    assert payload["nodal_moment_unit_factor"] == pytest.approx(0.001)
    assert payload["rows"][1]["moment_global"] == pytest.approx(
        [0.0, -0.009, 0.004]
    )
    assert payload["nodal_totals_global"] == pytest.approx(
        [2.0, 7.0, 9.0, 0.0, -0.009, 0.004]
    )


def test_nodal_force_time_excel_payload_shifts_global_resultants_to_reference() -> None:
    _payload, result_data = _result_overlay_fixture()
    global_origin_row = [0.0, 10.0, 0.0, 10.0, 20.0, 50.0]
    result_data = dict(
        result_data,
        moment_reference_xyz=[2.0, 0.0, 0.0],
        resultants_global=[global_origin_row],
        resultants_global_origin=[],
        resultants_reference_global=[],
    )

    payload = visualization.build_nodal_force_time_excel_payload(result_data, 0)

    assert payload is not None
    assert payload["extracted_resultants_global_origin"] == pytest.approx(
        global_origin_row
    )
    assert payload["extracted_resultants_global"] == pytest.approx(
        [0.0, 10.0, 0.0, 10.0, 20.0, 30.0]
    )


def test_write_nodal_force_time_excel_creates_summary_and_nodal_sheet(
    tmp_path: Path,
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        result_units={"force": "N", "moment": "N mm"},
        mesh_unit="mm",
        section_geometry={
            "width_axis": "x",
            "height_axis": "y",
            "width_mm": 12.0,
            "height_mm": 5.0,
            "area_mm2": 60.0,
            "point_source": "selected_side_nodes",
        },
    )
    payload = visualization.build_nodal_force_time_excel_payload(result_data, 0)
    assert payload is not None
    out_xlsx = tmp_path / "nodal_forces.xlsx"

    visualization.write_nodal_force_time_excel(str(out_xlsx), payload)

    workbook = openpyxl.load_workbook(out_xlsx, data_only=False)
    assert workbook.sheetnames == ["Summary", "Nodal Forces", "Formulas"]
    summary = workbook["Summary"]
    nodal = workbook["Nodal Forces"]
    formulas = workbook["Formulas"]
    assert summary["A1"].value == (
        "MSUP MCF Section Resultants - Nodal Force, Local Force, and Local Moment Export"
    )
    assert summary["A7"].value == "Local moment summary source"
    assert summary["B7"].value == "Nodal Forces sheet sum of local r x F"
    assert summary["A11"].value == "Section width axis"
    assert summary["B11"].value == "x"
    assert summary["A12"].value == "Section width [mm]"
    assert summary["B12"].value == 12.0
    assert summary["A14"].value == "Section height [mm]"
    assert summary["B14"].value == 5.0
    assert summary["A15"].value == "Projected section area [mm^2]"
    assert summary["B15"].value == 60.0
    assert summary["A17"].value == "DPF nodal force source frame"
    assert summary["B17"].value == "global"
    assert summary["A19"].value == "Local X axis in global components"
    assert [summary.cell(19, column).value for column in range(2, 5)] == [1.0, 0.0, 0.0]
    assert summary["A23"].value == "Component"
    assert summary["B23"].value == "Nodal sheet sum, global about reference"
    assert summary["C23"].value == "Nodal sheet sum, local about reference"
    assert summary["D23"].value == "DPF moment_accumulation, global origin"
    assert summary["E23"].value == "DPF moment_accumulation, global about reference"
    assert summary["F23"].value == "DPF moment_accumulation, local about reference"
    assert summary["G23"].value == "DPF local minus nodal local"
    assert nodal["A1"].value == "node_id"
    assert nodal["M1"].value == "fx_local [N]"
    assert nodal["Q1"].value == "mx_about_reference_global [N mm]"
    assert nodal["A2"].value == 1
    assert nodal["I2"].value == 2
    assert nodal["F3"].value == "=C3-Summary!$B$8"
    assert nodal["L2"].value == "=SQRT(SUMSQ(I2:K2))"
    assert nodal["M2"].value == "=I2*1+J2*0+K2*0"
    assert nodal["Q3"].value == "=(G3*K3-H3*J3)*1"
    assert nodal["U3"].value == "=Q3*1+R3*0+S3*0"
    assert summary["C27"].value == "=SUM('Nodal Forces'!U2:U3)"
    assert summary["C28"].value == "=SUM('Nodal Forces'!V2:V3)"
    assert summary["C29"].value == "=SUM('Nodal Forces'!W2:W3)"
    assert summary["F27"].value == 3
    assert summary["G27"].value == "=F27-C27"
    assert formulas["A3"].value == "Quantity"
    assert "q_j(time)" in formulas["B4"].value
    assert "Nodal Forces!Q:S" in formulas["B8"].value
    assert "NodalForces" in nodal.tables


def _result_overlay_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    config = core.SectionConfig(
        modal_rst="modal.rst",
        mcf="file.mcf",
        element_named_selection="CUT",
        coordinate_system_origin=[0.0, 0.0, 0.0],
        coordinate_system_axes={
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        section_normal_axis="z",
        extraction_side="positive",
        force_type=1,
    )
    signature = visualization.result_visualization_signature(config)
    payload = {
        "result_signature": signature,
        "mesh": {"points": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]},
        "plane": {
            "corners": [
                [0.0, 0.0, 0.0],
                [10.0, 0.0, 0.0],
                [10.0, 10.0, 0.0],
                [0.0, 10.0, 0.0],
            ]
        },
        "force_summation_nodes": [
            {"id": 1, "xyz": [0.0, 0.0, 0.0]},
            {"id": 2, "xyz": [1.0, 0.0, 0.0]},
        ],
        "selected_node_centroid": [0.5, 0.0, 0.0],
        "moment_reference_xyz": [0.0, 0.0, 0.0],
    }
    result_data = {
        "signature": signature,
        "times": [0.0, 1.0],
        "modal_coordinates": [[2.0, 3.0], [4.0, 5.0]],
        "modes_used": 2,
        "resultants_global": [
            [10.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 20.0, 0.0, 0.0, 0.0, 30.0],
        ],
        "resultants_local": [
            [1.0, 2.0, 2.0, 3.0, 4.0, 0.0],
            [4.0, 0.0, 3.0, 0.0, 12.0, 5.0],
        ],
        "nodal_force_modal_coefficients": {
            1: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            2: [[0.0, 2.0, 0.0], [0.0, 0.0, 3.0]],
        },
        "selected_node_coordinates": {
            1: [0.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
        },
        "selected_node_centroid": [0.5, 0.0, 0.0],
        "moment_reference_xyz": [0.0, 0.0, 0.0],
    }
    return payload, result_data


def _static_result_history_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    payload, modal_result_data = _result_overlay_fixture()
    signatures = [
        dict(modal_result_data["signature"], analysis_mode="static", result_set_id=set_id)
        for set_id in (2, 5, 8)
    ]
    selected_sets = [
        {
            "id": set_id,
            "value": result_value,
            "unit": "s",
            "label": f"Set {set_id} — {result_value:g} s",
        }
        for set_id, result_value in zip((2, 5, 8), (0.25, 0.5, 1.0))
    ]
    payload = dict(payload, result_signature=signatures[0])
    result_data = {
        "analysis_mode": "static",
        "static_set_scope": "all",
        "signature": signatures[-1],
        "signatures": signatures,
        "times": [0.25, 0.5, 1.0],
        "result_set_ids": [2, 5, 8],
        "selected_result_sets": selected_sets,
        "result_units": {"force": "N", "moment": "N mm"},
        "resultants_global": [
            [10.0, 0.0, 0.0, 0.0, 0.0, 100.0],
            [0.0, 20.0, 0.0, 0.0, 200.0, 0.0],
            [0.0, 0.0, 30.0, 300.0, 0.0, 0.0],
        ],
        "resultants_local": [
            [1.0, 2.0, 2.0, 3.0, 4.0, 0.0],
            [4.0, 0.0, 3.0, 0.0, 12.0, 5.0],
            [0.0, 6.0, 8.0, 8.0, 15.0, 0.0],
        ],
    }
    return payload, result_data


def test_result_overlay_force_mode_has_nodal_and_total_vectors() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data, result_units={"force": "N", "moment": "N mm"})

    overlay = visualization.build_result_overlay_payload(payload, result_data, "force", 0)

    assert overlay is not None
    assert overlay["mode"] == "force"
    assert overlay["unit"] == "N"
    assert "[10, 0, 0] N" in overlay["text"]
    assert "|V|=10 N" in overlay["text"]
    assert overlay["total_vector"]["origin"] == [0.0, 0.0, 0.0]
    assert overlay["total_vector"]["vector"] == [10.0, 0.0, 0.0]
    assert overlay["total_vector"]["color"] == visualization.VISUALIZATION_TOTAL_FORCE_COLOR
    force_display = overlay["total_vector"]["display_vector"]
    assert overlay["total_vector"]["origin"][0] + force_display[0] > 10.0
    assert len(overlay["nodal_vectors"]) == 2
    assert overlay["nodal_vectors"][0]["vector"] == [2.0, 3.0, 0.0]
    assert overlay["nodal_vectors"][1]["vector"] == [0.0, 4.0, 9.0]
    assert all("display_vector" in item for item in overlay["nodal_vectors"])


def test_result_overlay_caps_nearly_plane_normal_force_summation_arrow() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        resultants_global=[
            [1.0e-6, 0.0, 10.0, 0.0, 0.0, 0.0],
            result_data["resultants_global"][1],
        ],
    )

    overlay = visualization.build_result_overlay_payload(payload, result_data, "force", 0)

    assert overlay is not None
    display_length = core.vector_magnitude(overlay["total_vector"]["display_vector"])
    plane_span = visualization.section_plane_corner_span(payload["plane"]["corners"])
    assert display_length == pytest.approx(
        plane_span * visualization.VISUALIZATION_TOTAL_VECTOR_PLANE_EXIT_MARGIN
    )


def test_result_overlay_scales_nodal_vectors_from_actual_small_scene_extent() -> None:
    signature = {"force_type": 0}
    payload = {
        "result_signature": signature,
        "mesh": {
            "points": [
                [0.0, -0.005, -0.005],
                [0.1, 0.005, 0.005],
            ]
        },
        "plane": {
            "corners": [
                [0.05, -0.005, -0.005],
                [0.05, 0.005, -0.005],
                [0.05, 0.005, 0.005],
                [0.05, -0.005, 0.005],
            ]
        },
        "force_summation_nodes": [
            {"id": 1, "xyz": [0.05, 0.0, 0.0]},
            {"id": 2, "xyz": [0.05, 0.002, 0.0]},
        ],
        "selected_node_centroid": [0.05, 0.0, 0.0],
        "moment_reference_xyz": [0.05, 0.0, 0.0],
    }
    result_data = {
        "signature": signature,
        "times": [0.0],
        "modal_coordinates": [[1.0]],
        "modes_used": 1,
        "resultants_global": [[0.0, 0.0, 10.0, 0.0, 0.0, 0.0]],
        "nodal_force_modal_coefficients": {
            1: [[0.0, 0.0, 1.0]],
            2: [[0.0, 0.0, 2.0]],
        },
        "selected_node_coordinates": {
            1: [0.05, 0.0, 0.0],
            2: [0.05, 0.002, 0.0],
        },
    }

    overlay = visualization.build_result_overlay_payload(payload, result_data, "force", 0)

    assert overlay is not None
    assert visualization.visualization_scene_extent(payload) == pytest.approx(0.1)
    max_display_length = max(
        core.vector_magnitude(item["display_vector"])
        for item in overlay["nodal_vectors"]
    )
    assert max_display_length == pytest.approx(
        0.1 * visualization.VISUALIZATION_NODAL_VECTOR_LENGTH_FRACTION
    )
    assert max_display_length < visualization.section_plane_corner_span(payload["plane"]["corners"])


def test_nodal_vector_glyph_items_scale_from_display_length_not_raw_force() -> None:
    glyph_items = visualization.nodal_vector_glyph_items(
        [
            {
                "origin": [0.05, 0.0, 0.0],
                "vector": [0.0, 0.0, 1200.0],
                "display_vector": [0.0, 0.0, 0.008],
                "magnitude": 1200.0,
            }
        ]
    )

    assert glyph_items == [
        {
            "origin": [0.05, 0.0, 0.0],
            "display_vector": [0.0, 0.0, 0.008],
            "display_length": pytest.approx(0.008),
            "magnitude": 1200.0,
        }
    ]


def test_result_overlay_moment_mode_has_total_moment_only() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data, result_units={"force": "N", "moment": "N mm"})

    overlay = visualization.build_result_overlay_payload(payload, result_data, "moment", 1)

    assert overlay is not None
    assert overlay["mode"] == "moment"
    assert overlay["label"] == "Moment Reaction (nodal r x F)"
    assert overlay["unit"] == "N mm"
    assert "[0, -15, 8] N mm" in overlay["text"]
    assert "|V|=17 N mm" in overlay["text"]
    assert overlay["total_vector"]["origin"] == [0.0, 0.0, 0.0]
    assert overlay["total_vector"]["vector"] == [0.0, -15.0, 8.0]
    assert overlay["total_vector"]["color"] == visualization.VISUALIZATION_TOTAL_MOMENT_COLOR
    assert overlay["total_vector"]["display_vector"][1] < 0.0
    assert overlay["total_vector"]["display_vector"][2] > 0.0
    assert overlay["nodal_vectors"] == []


def test_result_overlay_moment_falls_back_to_reference_global_resultant() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(
        result_data,
        nodal_force_modal_coefficients={},
        resultants_reference_global=[
            [10.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 20.0, 0.0, 0.0, 0.0, 10.0],
        ],
    )

    overlay = visualization.build_result_overlay_payload(payload, result_data, "moment", 1)

    assert overlay is not None
    assert overlay["total_vector"]["vector"] == [0.0, 0.0, 10.0]


def test_result_overlay_requires_matching_signature() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data)
    result_data["signature"] = dict(result_data["signature"], force_type=2)

    assert visualization.build_result_overlay_payload(payload, result_data, "force", 0) is None


def test_moment_about_reference_point_removes_reference_cross_force() -> None:
    moment = core.moment_about_reference_point(
        moment_about_global_origin=[10.0, 20.0, 50.0],
        reference_xyz=[2.0, 0.0, 0.0],
        force=[0.0, 10.0, 0.0],
    )

    assert moment == pytest.approx([10.0, 20.0, 30.0])

    converted = core.moment_about_reference_point(
        moment_about_global_origin=[0.0, 0.0, 2.0],
        reference_xyz=[1000.0, 0.0, 0.0],
        force=[0.0, 1.0, 0.0],
        cross_product_moment_factor=0.001,
    )
    assert converted == pytest.approx([0.0, 0.0, 1.0])


def test_mechanical_equivalent_static_resultants_replaces_raw_dpf_moment_and_scales_shift() -> None:
    resultants = extraction.mechanical_equivalent_static_resultants(
        force=[0.0, 1.0, 0.0],
        raw_dpf_moment_about_reference=[0.0, 0.0, 30.0],
        mechanical_equivalent_reference_row=[0.0, 1.0, 0.0, 0.0, 0.0, 2.0],
        moment_reference_xyz=[1000.0, 0.0, 0.0],
        axes=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        cross_product_moment_factor=0.001,
    )

    assert resultants["resultant_reference_global"] == pytest.approx(
        [0.0, 1.0, 0.0, 0.0, 0.0, 2.0]
    )
    assert resultants["resultant_global_origin"] == pytest.approx(
        [0.0, 1.0, 0.0, 0.0, 0.0, 3.0]
    )
    assert resultants["raw_dpf_resultant_reference_global"][3:6] == pytest.approx(
        [0.0, 0.0, 30.0]
    )
    assert resultants["raw_dpf_resultant_global_origin"][3:6] == pytest.approx(
        [0.0, 0.0, 31.0]
    )


def test_global_and_local_plot_csv_rows_use_separate_moment_references(
    tmp_path: Path,
) -> None:
    payload, result_data = _result_overlay_fixture()
    force = [0.0, 10.0, 0.0]
    global_origin_row = force + [10.0, 20.0, 50.0]
    reference_global_row = core.resultant_about_reference(
        global_origin_row,
        [2.0, 0.0, 0.0],
    )
    local_row = core.rotate_to_local(
        reference_global_row,
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    )
    result_data = dict(
        result_data,
        times=[0.0],
        nodal_force_modal_coefficients={},
        resultants_global=[global_origin_row],
        resultants_reference_global=[reference_global_row],
        resultants_local=[local_row],
        result_units={"force": "N", "moment": "N mm"},
    )

    history = visualization.build_result_history_plot_payload(payload, result_data, "local")

    assert history is not None
    assert history["moment"]["components"]["x"] == pytest.approx([20.0])
    assert history["moment"]["components"]["y"] == pytest.approx([10.0])
    assert history["moment"]["components"]["z"] == pytest.approx([30.0])
    assert history["moment"]["components"]["total"] == pytest.approx(
        [(10.0**2 + 20.0**2 + 30.0**2) ** 0.5]
    )

    out_csv = tmp_path / "resultants.csv"
    extraction.write_result_csv(
        str(out_csv),
        [0.0],
        [global_origin_row],
        [local_row],
        {"force": "N", "moment": "N mm"},
    )

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0][4:7] == [
        "mx_global_about_global_origin [N mm]",
        "my_global_about_global_origin [N mm]",
        "mz_global_about_global_origin [N mm]",
    ]
    assert rows[0][10:13] == [
        "mx_local_about_moment_reference [N mm]",
        "my_local_about_moment_reference [N mm]",
        "mz_local_about_moment_reference [N mm]",
    ]
    assert rows[1][4:7] == ["10", "20", "50"]
    assert rows[1][10:13] == ["20", "10", "30"]


def test_local_result_history_prefers_nodal_reconstructed_moment() -> None:
    payload, result_data = _result_overlay_fixture()
    signature = dict(result_data["signature"])
    signature["coordinate_system_axes"] = {
        "x": [0.0, 1.0, 0.0],
        "y": [-1.0, 0.0, 0.0],
        "z": [0.0, 0.0, 1.0],
    }
    payload = dict(payload, result_signature=signature)
    result_data = dict(
        result_data,
        signature=signature,
        resultants_local=[
            [0.0, 0.0, 0.0, 100.0, 200.0, 300.0],
            [0.0, 0.0, 0.0, 400.0, 500.0, 600.0],
        ],
        result_units={"force": "N", "moment": "N mm"},
        mesh_unit="mm",
    )

    history = visualization.build_result_history_plot_payload(payload, result_data, "local")

    assert history is not None
    assert history["moment"]["components"]["x"] == pytest.approx([-9.0, -15.0])
    assert history["moment"]["components"]["y"] == pytest.approx([0.0, 0.0])
    assert history["moment"]["components"]["z"] == pytest.approx([4.0, 8.0])


def test_reference_moment_is_small_for_nearby_reference_with_identity_axes() -> None:
    global_origin_row = [0.0, 10.0, 0.0, 10.0, 20.0, 50.0]
    reference_global_row = core.resultant_about_reference(
        global_origin_row,
        [2.0, 0.0, 0.0],
    )
    local_row = core.rotate_to_local(
        reference_global_row,
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    )

    assert reference_global_row[:3] == pytest.approx(global_origin_row[:3])
    assert reference_global_row[3:] == pytest.approx([10.0, 20.0, 30.0])
    assert local_row[3:] == pytest.approx([10.0, 20.0, 30.0])
    assert local_row[3:] != pytest.approx(global_origin_row[3:])


def test_result_component_history_uses_global_resultants_by_default() -> None:
    _payload, result_data = _result_overlay_fixture()

    history = visualization.result_component_history(result_data)

    assert history["frame"] == "global"
    assert history["times"] == [0.0, 1.0]
    assert history["force"]["components"]["x"] == [10.0, 0.0]
    assert history["force"]["components"]["y"] == [0.0, 20.0]
    assert history["force"]["components"]["total"] == [10.0, 20.0]
    assert history["moment"]["components"]["z"] == [0.0, 30.0]
    assert history["moment"]["components"]["total"] == pytest.approx(
        [1.0, 30.0]
    )


def test_result_component_history_carries_result_units() -> None:
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data, result_units={"force": "N", "moment": "N mm"})

    history = visualization.result_component_history(result_data)

    assert history["result_units"] == {"force": "N", "moment": "N mm"}
    assert history["force"]["unit"] == "N"
    assert history["moment"]["unit"] == "N mm"


def test_moment_unit_conversion_factor_handles_common_units() -> None:
    assert core.moment_unit_conversion_factor("N mm", "N m") == pytest.approx(0.001)
    assert core.moment_unit_conversion_factor("N*mm", "N m") == pytest.approx(0.001)
    assert core.moment_unit_conversion_factor("kN m", "N mm") == pytest.approx(
        1.0e6
    )
    assert core.moment_unit_conversion_factor("lbf in", "lbf ft") == pytest.approx(
        1.0 / 12.0
    )
    assert core.moment_unit_conversion_factor("N.mm", "N m") == pytest.approx(0.001)


def test_result_component_history_can_convert_moment_plot_unit() -> None:
    _payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data, result_units={"force": "N", "moment": "N mm"})

    history = visualization.result_component_history(
        result_data,
        moment_display_unit="N m",
    )

    assert history["source_result_units"] == {"force": "N", "moment": "N mm"}
    assert history["result_units"] == {"force": "N", "moment": "N m"}
    assert history["moment"]["unit"] == "N m"
    assert history["moment"]["components"]["z"] == pytest.approx([0.0, 0.03])
    assert history["moment"]["components"]["total"] == pytest.approx(
        [0.001, 0.03]
    )


def test_rst_mesh_unit_indicator_text_and_tooltip() -> None:
    assert (
        core.rst_mesh_unit_indicator_text(None, state="not_loaded")
        == "RST mesh unit: not loaded"
    )
    assert (
        core.rst_mesh_unit_indicator_text(None)
        == "RST mesh unit: unavailable"
    )
    assert (
        core.rst_mesh_unit_indicator_text(None, state="read_failed")
        == "RST mesh unit: read failed"
    )
    assert core.rst_mesh_unit_indicator_text("mm") == "RST mesh unit: mm"

    tooltip = core.rst_mesh_unit_indicator_tooltip(
        "mm",
        {"force": "N", "moment": "N mm"},
    )
    assert "model.metadata.meshed_region.unit" in tooltip
    assert "Current RST mesh unit: mm." in tooltip
    assert "force=N, moment=N mm" in tooltip
    assert "plot moment-unit dropdown" in tooltip


def test_result_component_history_can_use_local_resultants() -> None:
    _payload, result_data = _result_overlay_fixture()

    history = visualization.result_component_history(result_data, "local")

    assert history["frame"] == "local"
    assert history["force"]["components"]["x"] == [1.0, 4.0]
    assert history["force"]["components"]["total"] == [3.0, 5.0]
    assert history["moment"]["components"]["y"] == [-9.0, -15.0]
    assert history["moment"]["components"]["total"] == pytest.approx(
        [(9.0**2 + 4.0**2) ** 0.5, 17.0]
    )


def test_result_history_default_frame_is_local_for_offset_moment_reference() -> None:
    assert (
        visualization.result_history_default_frame({"moment_reference_xyz": [0.0, 0.0, 0.0]})
        == "global"
    )
    assert (
        visualization.result_history_default_frame({"moment_reference_xyz": [0.05, 0.0, 0.0]})
        == "local"
    )
    assert visualization.result_history_default_frame({}) == "global"


def test_result_history_plot_payload_requires_matching_signature() -> None:
    payload, result_data = _result_overlay_fixture()
    result_data = dict(result_data, result_units={"force": "lbf", "moment": "lbf in"})

    history = visualization.build_result_history_plot_payload(payload, result_data, "local")

    assert history is not None
    assert history["frame"] == "local"
    assert history["force"]["labels"]["total"] == "Ftotal"
    assert history["force"]["unit"] == "lbf"
    assert history["moment"]["unit"] == "lbf in"

    mismatched = dict(result_data)
    mismatched["signature"] = dict(mismatched["signature"], force_type=2)
    assert visualization.build_result_history_plot_payload(payload, mismatched, "global") is None


@pytest.mark.parametrize("selected_time_index", [0, 1, 2])
def test_static_result_history_accepts_signature_for_selected_set(
    selected_time_index: int,
) -> None:
    payload, result_data = _static_result_history_fixture()
    payload["result_signature"] = result_data["signatures"][selected_time_index]

    history = visualization.build_result_history_plot_payload(
        payload,
        result_data,
        "global",
        selected_time_index=selected_time_index,
    )

    assert history is not None
    assert history["x_axis"] == {
        "kind": "result_value",
        "values": [0.25, 0.5, 1.0],
        "label": "Time [s]",
        "unit": "s",
        "point_labels": [
            "Set 2 — 0.25 s",
            "Set 5 — 0.5 s",
            "Set 8 — 1 s",
        ],
        "result_set_ids": [2, 5, 8],
        "result_values": [0.25, 0.5, 1.0],
    }


def test_static_result_history_rejects_signature_for_different_selected_set() -> None:
    payload, result_data = _static_result_history_fixture()
    payload["result_signature"] = result_data["signatures"][0]

    assert (
        visualization.build_result_history_plot_payload(
            payload,
            result_data,
            "global",
            selected_time_index=1,
        )
        is None
    )


@pytest.mark.parametrize(
    ("result_values", "expected_kind", "expected_values"),
    [
        ([0.25, 0.5, 1.0], "result_value", [0.25, 0.5, 1.0]),
        ([0.25, 0.25, 1.0], "result_set_id", [2.0, 5.0, 8.0]),
        ([1.0, 0.5, 2.0], "result_set_id", [2.0, 5.0, 8.0]),
        ([1.0, float("nan"), 2.0], "result_set_id", [2.0, 5.0, 8.0]),
    ],
)
def test_static_result_history_x_axis_uses_safe_result_values_or_set_ids(
    result_values: list[float],
    expected_kind: str,
    expected_values: list[float],
) -> None:
    _payload, result_data = _static_result_history_fixture()
    result_data["times"] = list(result_values)
    for selected_set, value in zip(result_data["selected_result_sets"], result_values):
        selected_set["value"] = value

    x_axis = visualization.result_history_x_axis(result_data, 3)

    assert x_axis["kind"] == expected_kind
    assert x_axis["values"] == pytest.approx(expected_values)
    assert x_axis["label"] == (
        "Time [s]" if expected_kind == "result_value" else "Cumulative set ID"
    )
    assert x_axis["unit"] == "s"
    assert x_axis["point_labels"] == [
        "Set 2 — 0.25 s",
        "Set 5 — 0.5 s",
        "Set 8 — 1 s",
    ]
    assert x_axis["result_set_ids"] == [2, 5, 8]
    for actual, expected in zip(x_axis["result_values"], result_values):
        if expected != expected:
            assert actual != actual
        else:
            assert actual == pytest.approx(expected)


def test_static_result_history_x_axis_supports_one_solved_set() -> None:
    _payload, result_data = _static_result_history_fixture()
    result_data["times"] = [0.25]
    result_data["result_set_ids"] = [2]
    result_data["selected_result_sets"] = result_data["selected_result_sets"][:1]

    x_axis = visualization.result_history_x_axis(result_data, 1)

    assert x_axis == {
        "kind": "result_value",
        "values": [0.25],
        "label": "Time [s]",
        "unit": "s",
        "point_labels": ["Set 2 — 0.25 s"],
        "result_set_ids": [2],
        "result_values": [0.25],
    }


@pytest.mark.parametrize("static_set_scope", ["range", "all"])
def test_static_force_moment_and_overlay_history_preserve_frames_and_units(
    static_set_scope: str,
) -> None:
    payload, result_data = _static_result_history_fixture()
    result_data["static_set_scope"] = static_set_scope
    payload["result_signature"] = result_data["signatures"][1]

    global_history = visualization.build_result_history_plot_payload(
        payload,
        result_data,
        "global",
        selected_time_index=1,
        moment_display_unit="N m",
    )
    local_history = visualization.build_result_history_plot_payload(
        payload,
        result_data,
        "local",
        selected_time_index=1,
        moment_display_unit="N m",
    )

    assert global_history is not None
    assert local_history is not None
    assert global_history["force"]["unit"] == "N"
    assert global_history["moment"]["unit"] == "N m"
    assert global_history["force"]["components"]["x"] == [10.0, 0.0, 0.0]
    assert global_history["moment"]["components"]["z"] == pytest.approx(
        [0.1, 0.0, 0.0]
    )
    assert local_history["force"]["components"]["total"] == pytest.approx(
        [3.0, 5.0, 10.0]
    )
    assert local_history["moment"]["components"]["total"] == pytest.approx(
        [0.005, 0.013, 0.017]
    )
    assert global_history["x_axis"] == local_history["x_axis"]
    assert global_history["series_signature"] == local_history["series_signature"]


def test_static_result_history_series_identity_is_stable_across_displayed_sets() -> None:
    payload, result_data = _static_result_history_fixture()
    series_signatures = []
    for selected_time_index, signature in enumerate(result_data["signatures"]):
        payload["result_signature"] = signature
        history = visualization.build_result_history_plot_payload(
            payload,
            result_data,
            "global",
            selected_time_index=selected_time_index,
        )
        assert history is not None
        series_signatures.append(history["series_signature"])

    assert series_signatures[0] == series_signatures[1] == series_signatures[2]


def test_static_result_history_marker_updates_in_place_without_plot_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window
    widget = window.result_history_widget
    try:
        payload, result_data = _static_result_history_fixture()
        payload["result_signature"] = result_data["signatures"][0]
        history = visualization.build_result_history_plot_payload(
            payload,
            result_data,
            "global",
            selected_time_index=0,
        )
        assert history is not None
        if not widget._matplotlib_ready:
            pytest.skip("Matplotlib Qt canvas is unavailable.")

        widget.set_history_payload(history, 0)
        assert set(widget._selected_time_markers) == {"force", "moment", "overlay"}
        marker_ids = {
            plot_key: id(marker)
            for plot_key, marker in widget._selected_time_markers.items()
        }
        draw_counts = {plot_key: 0 for plot_key in widget._plots}
        for plot_key, plot in widget._plots.items():
            monkeypatch.setattr(
                plot["canvas"],
                "draw_idle",
                lambda *, key=plot_key: draw_counts.__setitem__(
                    key, draw_counts[key] + 1
                ),
            )
        full_rebuilds: list[bool] = []
        monkeypatch.setattr(
            widget,
            "_draw_all_plots",
            lambda: full_rebuilds.append(True),
        )

        widget.set_selected_time_index(2)

        assert full_rebuilds == []
        assert draw_counts == {"force": 1, "moment": 1, "overlay": 1}
        assert {
            plot_key: id(marker)
            for plot_key, marker in widget._selected_time_markers.items()
        } == marker_ids
        for marker in widget._selected_time_markers.values():
            assert list(marker.get_xdata()) == pytest.approx([1.0, 1.0])

        widget.set_selected_time_index(2)
        assert draw_counts == {"force": 1, "moment": 1, "overlay": 1}

        assert widget.frame_for_payload(history["series_signature"], "global") == "global"
        widget._set_frame("local")
        widget._frame_user_selected = True
        payload["result_signature"] = result_data["signatures"][2]
        later_history = visualization.build_result_history_plot_payload(
            payload,
            result_data,
            "local",
            selected_time_index=2,
        )
        assert later_history is not None
        assert later_history["series_signature"] == history["series_signature"]
        assert (
            widget.frame_for_payload(later_history["series_signature"], "global")
            == "local"
        )
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_nearest_history_point_selects_point_within_pixel_tolerance() -> None:
    candidates = [
        {
            "time_index": 0,
            "mode": "force",
            "x_pixel": 10.0,
            "y_pixel": 10.0,
        },
        {
            "time_index": 1,
            "mode": "moment",
            "x_pixel": 20.0,
            "y_pixel": 25.0,
        },
    ]

    nearest = visualization.nearest_history_point(candidates, 19.0, 24.0)

    assert nearest is not None
    assert nearest["time_index"] == 1
    assert nearest["mode"] == "moment"
    assert nearest["distance_pixels"] == pytest.approx(2**0.5)
    assert (
        visualization.nearest_history_point(
            candidates,
            100.0,
            100.0,
            max_distance_pixels=5.0,
        )
        is None
    )


def test_visualization_paths_only_require_modal_rst(tmp_path: Path) -> None:
    rst = tmp_path / "modal.rst"
    rst.write_bytes(b"rst")

    visualization.validate_visualization_paths(
        core.SectionConfig(modal_rst=str(rst), mcf="", out_csv="")
    )

    with pytest.raises(ValueError):
        visualization.validate_visualization_paths(core.SectionConfig(modal_rst=""))


def test_large_visualization_guard_uses_counts() -> None:
    payload = {
        "counts": {
            "raw_element_count": visualization.VISUALIZATION_LARGE_ELEMENT_COUNT + 1,
            "mesh_node_count": 1,
        }
    }

    assert visualization.visualization_payload_exceeds_large_scene_limit(payload)
    assert "selected element" in visualization.visualization_large_scene_message(payload)


def test_visualization_payload_reuses_selected_mesh_snapshot_for_section_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "modal.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []
    resolved_names: list[str] = []

    def fake_resolve(
        _dpf: Any,
        _model: Any,
        _data_sources: Any,
        _streams_container: Any,
        name: str,
    ) -> tuple[_FakeScoping, str, list[str]]:
        resolved_names.append(name)
        return _FakeScoping([7, 8], "Elemental"), "CUT_SMALL", ["CUT_SMALL"]

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return _visualization_cache_mesh()

    monkeypatch.setattr(visualization, "resolve_element_named_selection_scoping", fake_resolve)
    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)

    first = visualization.build_section_visualization_payload(_visualization_cache_config(rst))
    second_config = _visualization_cache_config(rst)
    second_config.coordinate_system_origin = [2.5, 0.0, 0.0]
    second = visualization.build_section_visualization_payload(second_config)

    assert selected_mesh_calls == [True]
    assert resolved_names == ["CUT_SMALL"]
    assert first["cut_element_ids"] == [7]
    assert second["cut_element_ids"] == [8]


def test_static_visualization_cache_is_result_set_specific_and_deformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []
    displacement_set_calls: list[int] = []

    monkeypatch.setattr(
        visualization,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([7, 8], "Elemental"),
            "CUT_SMALL",
            ["CUT_SMALL"],
        ),
    )

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return _visualization_cache_mesh()

    def fake_displacements(
        _dpf: Any,
        _data_sources: Any,
        _streams: Any,
        mesh: _FakeMesh,
        result_set_id: int,
        log: Any = None,
    ) -> tuple[dict[int, list[float]], dict[str, Any]]:
        displacement_set_calls.append(int(result_set_id))
        rows = {node_id: [0.0, 0.0, 0.0] for node_id in mesh.nodes.scoping.ids}
        if int(result_set_id) == 2:
            rows.update(
                {
                    101: [5.0, 0.0, 0.0],
                    102: [5.0, 0.0, 0.0],
                    103: [-3.0, 0.0, 0.0],
                    104: [-3.0, 0.0, 0.0],
                }
            )
        return rows, {
            "geometry_state": "deformed",
            "result_set_id": int(result_set_id),
            "mesh_unit": "mm",
            "max_displacement": max(
                visualization.vector_magnitude(value) for value in rows.values()
            ),
        }

    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)
    monkeypatch.setattr(
        visualization,
        "selected_set_nodal_displacements",
        fake_displacements,
    )

    set_one_config = _visualization_cache_config(rst)
    set_one_config.analysis_mode = "static"
    set_one_config.result_set_id = 1
    set_one_config.coordinate_system_origin = [0.0, 0.0, 0.0]
    set_two_config = _visualization_cache_config(rst)
    set_two_config.analysis_mode = "static"
    set_two_config.result_set_id = 2
    set_two_config.coordinate_system_origin = [0.0, 0.0, 0.0]
    set_three_config = _visualization_cache_config(rst)
    set_three_config.analysis_mode = "static"
    set_three_config.result_set_id = 3
    set_three_config.coordinate_system_origin = [0.0, 0.0, 0.0]
    set_four_config = _visualization_cache_config(rst)
    set_four_config.analysis_mode = "static"
    set_four_config.result_set_id = 4
    set_four_config.coordinate_system_origin = [0.0, 0.0, 0.0]

    set_one = visualization.build_section_visualization_payload(set_one_config)
    set_two = visualization.build_section_visualization_payload(set_two_config)
    set_two_repeat = visualization.build_section_visualization_payload(set_two_config)
    visualization.build_section_visualization_payload(set_three_config)
    visualization.build_section_visualization_payload(set_four_config)
    visualization.build_section_visualization_payload(set_two_config)

    assert selected_mesh_calls == [True, True, True, True]
    assert displacement_set_calls == [1, 2, 3, 4]
    assert set_one["geometry_state"] == "deformed"
    assert set_one["deformation"]["result_set_id"] == 1
    assert set_one["cut_element_ids"] == [7]
    assert set_two["cut_element_ids"] == [7]
    assert set_two["force_summation_node_ids"] == [102]
    assert set_two["force_summation_nodes"][0]["xyz"] == [6.0, 0.0, 0.0]
    assert set_two["mesh"]["points"] == [
        [4.0, 0.0, 0.0],
        [6.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    assert set_two["deformation"]["scope_change"]["element_membership_changed"] is False
    assert set_two["deformation"]["scope_change"]["node_membership_changed"] is False
    assert set_two["deformation"]["scoping_geometry_state"] == "reference"
    assert set_two_repeat["mesh"]["points"] == set_two["mesh"]["points"]
    assert len(visualization._VISUALIZATION_MESH_SNAPSHOT_CACHE) == 3
    assert {
        int(key[8]) for key in visualization._VISUALIZATION_MESH_SNAPSHOT_CACHE
    } == {2, 3, 4}


def test_static_visualization_cache_rebases_current_origin_and_axes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []
    displacement_calls: list[int] = []
    monkeypatch.setattr(
        visualization,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([7, 8], "Elemental"),
            "CUT_SMALL",
            ["CUT_SMALL"],
        ),
    )

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return _visualization_cache_mesh()

    def fake_displacements(
        _dpf: Any,
        _data_sources: Any,
        _streams: Any,
        mesh: _FakeMesh,
        result_set_id: int,
        log: Any = None,
    ) -> tuple[dict[int, list[float]], dict[str, Any]]:
        displacement_calls.append(int(result_set_id))
        return (
            {node_id: [0.0, 0.0, 0.0] for node_id in mesh.nodes.scoping.ids},
            {
                "geometry_state": "deformed",
                "result_set_id": int(result_set_id),
                "mesh_unit": "mm",
                "max_displacement": 0.0,
            },
        )

    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)
    monkeypatch.setattr(
        visualization,
        "selected_set_nodal_displacements",
        fake_displacements,
    )
    first_config = _visualization_cache_config(rst)
    first_config.analysis_mode = "static"
    first_config.result_set_id = 1
    first = visualization.build_section_visualization_payload(first_config)

    second_config = _visualization_cache_config(rst)
    second_config.analysis_mode = "static"
    second_config.result_set_id = 1
    second_config.coordinate_system_origin = [2.5, 0.0, 0.0]
    second_config.coordinate_system_axes = {
        "x": [0.0, 1.0, 0.0],
        "y": [-1.0, 0.0, 0.0],
        "z": [0.0, 0.0, 1.0],
    }
    second = visualization.build_section_visualization_payload(second_config)

    assert selected_mesh_calls == [True]
    assert displacement_calls == [1]
    assert first["plane"]["origin"] == pytest.approx([0.5, 0.0, 0.0])
    assert second["coordinate_system_origin"] == pytest.approx([2.5, 0.0, 0.0])
    assert second["coordinate_system_axes"] == second_config.coordinate_system_axes
    assert second["plane"]["origin"] == pytest.approx([2.5, 0.0, 0.0])
    assert second["plane"]["normal"] == pytest.approx([0.0, 1.0, 0.0])
    assert second["resolved_reference_frame"]["initial_origin"] == pytest.approx(
        [2.5, 0.0, 0.0]
    )
    assert second["resolved_reference_frame"]["resolved_origin"] == pytest.approx(
        [2.5, 0.0, 0.0]
    )
    assert second["result_signature"]["coordinate_system_origin"] == pytest.approx(
        second["plane"]["origin"]
    )
    assert second["result_signature"]["coordinate_system_axes"] == (
        second["coordinate_system_axes"]
    )


def test_follow_geometry_cache_refits_changed_implicit_cut_from_cached_mesh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []
    displacement_calls: list[list[int]] = []
    mesh = _FakeMesh(
        nodes={
            1: [-1.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
            3: [-1.0, 1.0, 0.0],
            4: [-1.0, 0.0, 1.0],
            5: [9.0, 0.0, 0.0],
            6: [11.0, 0.0, 0.0],
            7: [9.0, 1.0, 0.0],
            8: [9.0, 0.0, 1.0],
        },
        elements={7: [1, 2, 3, 4], 8: [5, 6, 7, 8]},
        grid=_FakeGrid(
            points=[
                [-1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [-1.0, 1.0, 0.0],
                [-1.0, 0.0, 1.0],
                [9.0, 0.0, 0.0],
                [11.0, 0.0, 0.0],
                [9.0, 1.0, 0.0],
                [9.0, 0.0, 1.0],
            ],
            cells=[4, 0, 1, 2, 3, 4, 4, 5, 6, 7],
            celltypes=[10, 10],
        ),
        unit="mm",
    )
    monkeypatch.setattr(
        visualization,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([7, 8], "Elemental"),
            "CUT_SMALL",
            ["CUT_SMALL"],
        ),
    )

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return mesh

    def fake_displacements(
        _dpf: Any,
        _data_sources: Any,
        _streams: Any,
        node_ids: list[int],
        result_set_id: int,
        mesh_unit: str,
        log: Any = None,
    ) -> tuple[dict[int, list[float]], dict[str, Any]]:
        displacement_calls.append(list(node_ids))
        return (
            {int(node_id): [0.0, 0.0, 2.0] for node_id in node_ids},
            {
                "geometry_state": "deformed",
                "result_set_id": int(result_set_id),
                "mesh_unit": mesh_unit,
                "max_displacement": 2.0,
            },
        )

    def fake_selected_displacements(
        dpf: Any,
        data_sources: Any,
        streams: Any,
        selected_mesh: _FakeMesh,
        result_set_id: int,
        log: Any = None,
    ) -> tuple[dict[int, list[float]], dict[str, Any]]:
        return fake_displacements(
            dpf,
            data_sources,
            streams,
            list(selected_mesh.nodes.scoping.ids),
            result_set_id,
            selected_mesh.unit,
            log,
        )

    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)
    monkeypatch.setattr(visualization, "nodal_displacements_for_ids", fake_displacements)
    monkeypatch.setattr(
        visualization,
        "selected_set_nodal_displacements",
        fake_selected_displacements,
    )
    first_config = _visualization_cache_config(rst)
    first_config.analysis_mode = "static"
    first_config.result_set_id = 1
    first_config.reference_frame_motion = "follow-geometry"
    first_config.coordinate_system_origin = [100.0, 0.0, 0.0]
    first = visualization.build_section_visualization_payload(first_config)

    second_config = core.config_from_mapping(asdict(first_config))
    second_config.coordinate_system_origin = [0.0, 0.0, 0.0]
    second = visualization.build_section_visualization_payload(second_config)

    third_config = core.config_from_mapping(asdict(first_config))
    third_config.coordinate_system_origin = [10.0, 0.0, 0.0]
    third = visualization.build_section_visualization_payload(third_config)

    assert selected_mesh_calls == [True]
    assert len(displacement_calls) == 1
    assert first["geometry_state"] == "reference"
    assert first["result_set_id"] is None
    assert first["requested_result_set_id"] == 1
    assert first["deformation"] is None
    assert first["resolved_reference_frame"] is None
    assert first["result_signature"] is None
    assert first["preview_only_reason"] == (
        visualization.FOLLOW_GEOMETRY_REFERENCE_PREVIEW_REASON
    )
    assert first["counts"]["cut_element_count"] == 0
    assert first["counts"]["force_summation_node_count"] == 0
    assert first["mesh"]["points"] == mesh.grid.points
    assert any(
        "other result sets cannot be previewed" in warning
        for warning in first["warnings"]
    )
    assert second["geometry_state"] == "deformed"
    assert second["resolved_reference_frame"]["tracking_node_ids"] == [1, 2, 3, 4]
    assert third["resolved_reference_frame"]["tracking_node_ids"] == [5, 6, 7, 8]
    assert second["resolved_reference_frame"]["tracking_node_ids_hash"] != (
        third["resolved_reference_frame"]["tracking_node_ids_hash"]
    )
    assert second["resolved_reference_frame"]["resolved_origin"] == pytest.approx(
        [0.0, 0.0, 2.0]
    )
    assert third["resolved_reference_frame"]["resolved_origin"] == pytest.approx(
        [10.0, 0.0, 2.0]
    )
    assert third["plane"]["origin"] == pytest.approx([10.0, 0.0, 2.0])


def test_visualization_payload_cache_misses_for_named_selection_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "modal.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []

    def fake_resolve(
        _dpf: Any,
        _model: Any,
        _data_sources: Any,
        _streams_container: Any,
        name: str,
    ) -> tuple[_FakeScoping, str, list[str]]:
        if str(name).lower() == "bolt_nodes":
            return _FakeScoping([8], "Elemental"), "BOLT_NODES", ["CUT_SMALL", "BOLT_NODES"]
        return _FakeScoping([7], "Elemental"), "CUT_SMALL", ["CUT_SMALL", "BOLT_NODES"]

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return _visualization_cache_mesh()

    monkeypatch.setattr(visualization, "resolve_element_named_selection_scoping", fake_resolve)
    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)

    visualization.build_section_visualization_payload(_visualization_cache_config(rst))
    visualization.build_section_visualization_payload(
        _visualization_cache_config(rst, element_name="BOLT_NODES")
    )

    assert selected_mesh_calls == [True, True]


def test_visualization_cache_key_tracks_external_selection_file_changes(
    tmp_path: Path,
) -> None:
    rst = tmp_path / "modal.rst"
    rst.write_bytes(b"rst")
    selection = tmp_path / "section.txt"
    selection.write_text("1\n", encoding="ascii")
    signature = dpf_io.modal_rst_signature(str(rst))

    first = visualization.visualization_mesh_snapshot_cache_key(
        signature,
        "section",
        str(selection),
    )
    selection.write_text("1\n2\n", encoding="ascii")
    second = visualization.visualization_mesh_snapshot_cache_key(
        signature,
        "section",
        str(selection),
    )

    assert first != second
    assert first[4] == second[4] == str(selection.resolve())
    assert first[9] == second[9] == "follow-geometry"


def test_clear_visualization_mesh_snapshot_cache_resets_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "modal.rst"
    rst.write_bytes(b"rst")
    visualization.clear_visualization_mesh_snapshot_cache()
    _install_fake_visualization_dpf(monkeypatch)
    selected_mesh_calls: list[bool] = []

    monkeypatch.setattr(
        visualization,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([7, 8], "Elemental"),
            "CUT_SMALL",
            ["CUT_SMALL"],
        ),
    )

    def fake_selected_mesh(*_args: Any, **_kwargs: Any) -> _FakeMesh:
        selected_mesh_calls.append(True)
        return _visualization_cache_mesh()

    monkeypatch.setattr(visualization, "selected_element_mesh", fake_selected_mesh)

    visualization.build_section_visualization_payload(_visualization_cache_config(rst))
    visualization.clear_visualization_mesh_snapshot_cache()
    visualization.build_section_visualization_payload(_visualization_cache_config(rst))

    assert selected_mesh_calls == [True, True]


def test_parse_mcf_supports_wrapped_modal_coordinate_rows(tmp_path: Path) -> None:
    mcf = tmp_path / "file.mcf"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 4",
                "Time Coordinates",
                "0.0 1.0 2.0",
                "3.0 4.0",
                "1.0 5.0 6.0 7.0",
                "8.0",
            ]
        ),
        encoding="utf-8",
    )

    times, coordinates = core.parse_mcf(str(mcf))

    assert times == [0.0, 1.0]
    assert coordinates == [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]


def test_parse_mcf_unwraps_indented_modal_coordinate_records_without_mode_header(
    tmp_path: Path,
) -> None:
    mcf = tmp_path / "file.mcf"
    mcf.write_text(
        "\n".join(
            [
                "Modal Coordinate File",
                "Time Coordinates",
                "0.0 1.0 2.0",
                "    3.0 4.0",
                "1.0 5.0 6.0",
                "    7.0 8.0",
            ]
        ),
        encoding="utf-8",
    )

    times, coordinates = core.parse_mcf(str(mcf))

    assert times == [0.0, 1.0]
    assert coordinates == [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]


def test_coordinate_system_candidates_are_metadata_first_by_default(tmp_path: Path) -> None:
    rst = tmp_path / "file.rst"
    rst.write_bytes(b"rst placeholder")

    assert dpf_io.candidate_coordinate_system_ids(str(rst), {}) == []
    assert len(dpf_io.candidate_coordinate_system_ids(str(rst), {}, exhaustive=True)) == (
        dpf_io.COORDINATE_SYSTEM_ID_SCAN_LIMIT
    )

    (tmp_path / "ds.dat").write_text("LOCAL,42,0,0,0\n", encoding="utf-8")

    assert dpf_io.candidate_coordinate_system_ids(str(rst), {}) == [42]


def test_default_coordinate_discovery_does_not_run_dpf_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "file.rst"
    rst.write_bytes(b"rst placeholder")
    dpf_io.clear_modal_rst_metadata_cache()

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature)

    def fail_scan(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise AssertionError("default coordinate discovery must not scan DPF IDs")

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(dpf_io, "scan_dpf_coordinate_system_options", fail_scan)

    options = dpf_io.discover_coordinate_system_options(str(rst))

    assert [option["id"] for option in options] == [0]
    assert options[0]["source"] == "global"


def test_named_selection_dropdown_filters_to_non_empty_elemental_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "file.rst"
    rst.write_bytes(b"rst placeholder")
    dpf_io.clear_modal_rst_metadata_cache()

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(
            signature,
            names=["CUT_SMALL", "NODE_ONLY", "EMPTY_BODY"],
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    released = _install_fake_named_selection_dpf(
        monkeypatch,
        ["CUT_SMALL", "NODE_ONLY", "EMPTY_BODY"],
        {
            "CUT_SMALL": _FakeScoping([10, 20], "Elemental"),
            "NODE_ONLY": _FakeScoping([99], "Nodal"),
            "EMPTY_BODY": _FakeScoping([], "Elemental"),
        },
    )

    options = dpf_io.discover_element_named_selection_options(str(rst))

    assert [option["name"] for option in options] == ["CUT_SMALL"]
    assert options[0]["location"] == "Elemental"
    assert options[0]["count"] == 2
    assert options[0]["metadata_only"] is False
    assert released == [True]


def test_resolve_element_named_selection_scoping_matches_available_names_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_named_selection_dpf(
        monkeypatch,
        ["Cut_Small"],
        {"CUT_SMALL": _FakeScoping([10], "Elemental")},
    )
    dpf = sys.modules["ansys.dpf.core"]
    data_sources = dpf.DataSources("file.rst")
    model = dpf.Model(data_sources)

    scoping, matched_name, available = dpf_io.resolve_element_named_selection_scoping(
        dpf,
        model,
        data_sources,
        types.SimpleNamespace(),
        "cut_small",
    )

    assert matched_name == "Cut_Small"
    assert available == ["Cut_Small"]
    assert scoping.ids == [10]


def test_resolve_element_named_selection_scoping_rejects_node_only_named_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_named_selection_dpf(
        monkeypatch,
        ["NODE_ONLY"],
        {"NODE_ONLY": _FakeScoping([99], "Nodal")},
    )
    dpf = sys.modules["ansys.dpf.core"]
    data_sources = dpf.DataSources("file.rst")
    model = dpf.Model(data_sources)

    with pytest.raises(ValueError, match="did not resolve to elemental scoping"):
        dpf_io.resolve_element_named_selection_scoping(
            dpf,
            model,
            data_sources,
            types.SimpleNamespace(),
            "node_only",
        )


def test_resolve_element_named_selection_scoping_converts_metadata_nodal_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_named_selection_dpf(
        monkeypatch,
        ["MIXED_SELECTION"],
        {"MIXED_SELECTION": _FakeScoping([99], "Nodal")},
        operator_scopes_by_name={
            "MIXED_SELECTION": _FakeScoping([10, 20], "Elemental")
        },
    )
    dpf = sys.modules["ansys.dpf.core"]
    data_sources = dpf.DataSources("file.rst")
    model = dpf.Model(data_sources)

    scoping, matched_name, available = dpf_io.resolve_element_named_selection_scoping(
        dpf,
        model,
        data_sources,
        types.SimpleNamespace(),
        "mixed_selection",
    )

    assert matched_name == "MIXED_SELECTION"
    assert available == ["MIXED_SELECTION"]
    assert scoping.location == "Elemental"
    assert scoping.ids == [10, 20]


def test_external_named_selection_parsers_support_text_and_compact_cdb(
    tmp_path: Path,
) -> None:
    text_export = tmp_path / "section_nodes.txt"
    text_export.write_text(
        "Node Number\tX Location\tY Location\tZ Location\n"
        "101\t0.0\t1.0\t2.0\n"
        "102\t3.0\t4.0\t5.0\n"
        "102\t3.0\t4.0\t5.0\n",
        encoding="utf-16",
    )
    cdb_export = tmp_path / "named_selections.cdb"
    cdb_export.write_text(
        "CMBLOCK,CUT_NODES,NODE,4\n"
        "(8i10)\n"
        "         1        30        80       -83\n"
        "CMBLOCK,CUT_BODY,ELEMENT,2\n"
        "(8i10)\n"
        "        10       -12\n"
        "CMBLOCK,CUT_FACE,EFACE,2\n"
        "(8i10)\n"
        "        10         2\n",
        encoding="ascii",
    )

    assert dpf_io.parse_mechanical_named_selection_text(str(text_export)) == [101, 102]
    assert dpf_io.parse_cdb_named_selection_components(str(cdb_export)) == [
        {
            "name": "CUT_NODES",
            "entity": "NODE",
            "ids": [1, 30, 80, 81, 82, 83],
            "count": 6,
        },
        {
            "name": "CUT_BODY",
            "entity": "ELEMENT",
            "ids": [10, 11, 12],
            "count": 3,
        },
    ]


def test_external_element_and_node_components_resolve_against_rst_mesh(
    tmp_path: Path,
) -> None:
    cdb_export = tmp_path / "named_selections.cdb"
    cdb_export.write_text(
        "CMBLOCK,CUT_NODES,NODE,2\n"
        "(8i10)\n"
        "         1         2\n"
        "CMBLOCK,CUT_BODY,ELEMENT,2\n"
        "(8i10)\n"
        "        10        11\n",
        encoding="ascii",
    )
    mesh = _FakeMesh(
        nodes={1: [0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        elements={10: [1, 2], 11: [1, 2]},
    )
    model = types.SimpleNamespace(
        metadata=types.SimpleNamespace(meshed_region=mesh)
    )
    transpose_values: dict[str, Any] = {}

    class FakeTranspose:
        def __init__(self) -> None:
            self.values = transpose_values
            self.inputs = types.SimpleNamespace(
                mesh_scoping=_FakePin(self, "mesh_scoping"),
                meshed_region=_FakePin(self, "meshed_region"),
                inclusive=_FakePin(self, "inclusive"),
                extend_midside_nodes=_FakePin(self, "extend_midside_nodes"),
                requested_location=_FakePin(self, "requested_location"),
            )

        def eval(self) -> _FakeScoping:
            return _FakeScoping([10, 11], "Elemental")

    fake_dpf = types.SimpleNamespace(
        locations=types.SimpleNamespace(elemental="Elemental", nodal="Nodal"),
        Scoping=lambda ids=None, location=None: _FakeScoping(ids, location),
        operators=types.SimpleNamespace(
            scoping=types.SimpleNamespace(transpose=FakeTranspose)
        ),
    )

    node_scope, node_name, available = dpf_io.resolve_external_element_scoping(
        fake_dpf,
        model,
        str(cdb_export),
        "cut_nodes",
    )
    element_scope, element_name, _ = dpf_io.resolve_external_element_scoping(
        fake_dpf,
        model,
        str(cdb_export),
        "CUT_BODY",
    )
    tracking_nodes, tracking_node_evidence = (
        dpf_io.resolve_reference_frame_attachment_nodes(
            fake_dpf,
            model,
            name="CUT_NODES",
            external_named_selection_path=str(cdb_export),
        )
    )
    tracking_elements, tracking_element_evidence = (
        dpf_io.resolve_reference_frame_attachment_nodes(
            fake_dpf,
            model,
            name="CUT_BODY",
            external_named_selection_path=str(cdb_export),
        )
    )

    assert node_scope.ids == [10, 11]
    assert node_name == "CUT_NODES"
    assert available == ["CUT_NODES", "CUT_BODY"]
    assert transpose_values["mesh_scoping"].ids == [1, 2]
    assert transpose_values["inclusive"] == 0
    assert transpose_values["extend_midside_nodes"] is False
    assert element_scope.ids == [10, 11]
    assert element_scope.location == "Elemental"
    assert element_name == "CUT_BODY"
    assert tracking_nodes == [1, 2]
    assert tracking_node_evidence["entity"] == "NODE"
    assert tracking_node_evidence["source"] == "external_named_selection"
    assert tracking_elements == [1, 2]
    assert tracking_element_evidence["entity"] == "ELEMENT"
    assert tracking_element_evidence["entity_count"] == 2


def test_rst_frame_attachment_keeps_nodes_and_expands_elements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = _FakeMesh(
        nodes={
            1: [0.0, 0.0, 0.0],
            2: [1.0, 0.0, 0.0],
            3: [0.0, 1.0, 0.0],
        },
        elements={10: [1, 2], 11: [2, 3]},
    )
    model = types.SimpleNamespace(metadata=types.SimpleNamespace(meshed_region=mesh))

    def fake_named_scoping(
        _model: Any,
        name: str,
    ) -> tuple[_FakeScoping, str, list[str]]:
        if name.lower() == "track_nodes":
            return _FakeScoping([3, 1, 3], "Nodal"), "TRACK_NODES", [
                "TRACK_NODES",
                "TRACK_ELEMENTS",
            ]
        return _FakeScoping([10, 11], "Elemental"), "TRACK_ELEMENTS", [
            "TRACK_NODES",
            "TRACK_ELEMENTS",
        ]

    monkeypatch.setattr(dpf_io, "get_named_scoping", fake_named_scoping)

    node_ids, node_evidence = dpf_io.resolve_reference_frame_attachment_nodes(
        _FakeDpf,
        model,
        name="track_nodes",
    )
    element_node_ids, element_evidence = (
        dpf_io.resolve_reference_frame_attachment_nodes(
            _FakeDpf,
            model,
            name="track_elements",
        )
    )

    assert node_ids == [1, 3]
    assert node_evidence["entity"] == "NODE"
    assert node_evidence["entity_count"] == 3
    assert element_node_ids == [1, 2, 3]
    assert element_evidence["entity"] == "ELEMENT"
    assert element_evidence["node_count"] == 3


def test_external_selection_rejects_ids_missing_from_rst_mesh(tmp_path: Path) -> None:
    text_export = tmp_path / "missing_nodes.txt"
    text_export.write_text("1\n99\n", encoding="ascii")
    mesh = _FakeMesh(
        nodes={1: [0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        elements={10: [1, 2]},
    )
    model = types.SimpleNamespace(
        metadata=types.SimpleNamespace(meshed_region=mesh)
    )

    with pytest.raises(ValueError, match="1 ID\\(s\\) absent from the RST mesh: 99"):
        dpf_io.resolve_external_element_scoping(
            _FakeDpf,
            model,
            str(text_export),
            "missing_nodes",
        )


def test_metadata_load_logs_cache_state_and_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "file.rst"
    rst.write_bytes(b"rst placeholder")
    dpf_io.clear_modal_rst_metadata_cache()
    messages: list[str] = []

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, names=["CUT_SMALL"], modal_set_count=3)

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)

    first = dpf_io.load_modal_rst_metadata(str(rst), log=messages.append)
    second = dpf_io.load_modal_rst_metadata(str(rst), log=messages.append)

    assert first is second
    joined = "\n".join(messages)
    assert "Metadata cache miss" in joined
    assert "Metadata cache hit" in joined
    assert "1 named selection(s)" in joined
    assert "3 modal/time set(s)" in joined


def test_dpf_preflight_rejects_too_new_client_for_2023r2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDpf:
        __version__ = "0.16.0"

    monkeypatch.setattr(
        dpf_io,
        "detected_ansys_release_codes",
        lambda: [dpf_io.ANSYS_2023R2_RELEASE_CODE],
    )
    messages: list[str] = []

    with pytest.raises(dpf_io.DpfCompatibilityError) as exc_info:
        dpf_io.preflight_dpf_open(FakeDpf(), r"C:\runs\file.rst", log=messages.append)

    assert "Ansys 2023 R2" in str(exc_info.value)
    assert "ansys-dpf-core<0.16.0" in str(exc_info.value)
    assert "DPF compatibility check failed" in "\n".join(messages)


def test_dpf_preflight_warns_for_unc_path_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDpf:
        __version__ = "0.15.2"

    monkeypatch.setattr(dpf_io, "detected_ansys_release_codes", lambda: [])
    messages: list[str] = []

    dpf_io.preflight_dpf_open(
        FakeDpf(),
        r"\\192.168.186.7\lustre\analysis\file.rst",
        log=messages.append,
    )

    joined = "\n".join(messages)
    assert "PyDPF-Core client version: 0.15.2" in joined
    assert "UNC/network path" in joined


def test_force_summation_failure_message_points_to_rst_force_output() -> None:
    message = extraction.build_force_summation_failure_message(
        config=core.SectionConfig(
            modal_rst="file.rst",
            mcf="file.mcf",
            out_csv="out.csv",
            element_named_selection="NS_CRITICAL_REGION",
            force_type=extraction.MECHANICAL_PROBE_FORCE_TYPE,
        ),
        result_names=["displacement", "stress", "element_nodal_forces"],
        raw_element_count=208,
        cut_element_count=12,
        side_node_count=44,
        modes_to_evaluate=226,
        raw_error=RuntimeError(
            "fields container expected\nforce_summation:39<-elemental_nodal_to_nodal_fc:64"
        ),
    )

    assert "could not produce force/moment fields" in message
    assert "OUTRES,NLOAD" in message
    assert "Static forces" in message
    assert "NS_CRITICAL_REGION" in message
    assert "raw elements=208" in message
    assert "cut elements=12" in message
    assert "side nodes=44" in message
    assert "modal sets requested=226" in message
    assert "displacement, stress, element_nodal_forces" in message
    assert "fields container expected" in message
    assert "ansys-dpf-core<0.16.0" not in message

    static_message = extraction.build_force_summation_failure_message(
        config=core.SectionConfig(analysis_mode="static", force_type=3),
        result_names=["element_nodal_forces"],
        raw_element_count=2,
        cut_element_count=1,
        side_node_count=4,
        modes_to_evaluate=1,
        raw_error=RuntimeError("missing static force data"),
    )
    assert "Static Structural RST" in static_message
    assert "Static forces" in static_message
    assert "result sets requested=1" in static_message
    assert "modal sets requested" not in static_message


def test_missing_element_nodal_force_preflight_is_exact_and_actionable() -> None:
    with pytest.raises(core.MissingElementNodalForceDataError) as exc_info:
        core.require_element_nodal_force_result(
            rst_path=r"C:\runs\file.rst",
            result_names=["displacement", "reaction_force", "stress"],
        )

    message = str(exc_info.value)
    assert "Exact section force/moment extraction is unavailable" in message
    assert "Nodal Forces to Yes" in message
    assert "OUTRES,NLOAD,ALL" in message
    assert "then re-solve" in message
    assert "changing the PyDPF version cannot recreate it" in message
    assert "Reaction-force output is not a valid replacement" in message
    assert r"C:\runs\file.rst" in message

    for available_name in (
        "element_nodal_forces",
        "Element Nodal Forces",
        "elemental_nodal_force",
    ):
        core.require_element_nodal_force_result(
            rst_path="file.rst",
            result_names=["displacement", available_name],
        )

    # Empty metadata is inconclusive, so the operator's own diagnostic remains authoritative.
    core.require_element_nodal_force_result(rst_path="file.rst", result_names=[])


def test_static_force_series_stops_before_mesh_work_when_force_data_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released: list[bool] = []

    class FakeModel:
        metadata = types.SimpleNamespace(
            result_info=types.SimpleNamespace(
                available_results=["displacement", "reaction_force", "stress"]
            )
        )

    fake_dpf = types.SimpleNamespace(
        __version__="0.16.1",
        DataSources=lambda path: types.SimpleNamespace(path=path),
        Model=lambda _data_sources: FakeModel(),
    )
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(extraction, "preflight_dpf_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        extraction,
        "create_streams_container",
        lambda *_args, **_kwargs: types.SimpleNamespace(
            release_handles=lambda: released.append(True)
        ),
    )
    monkeypatch.setattr(
        extraction,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: pytest.fail("named-selection work must not start"),
    )

    with pytest.raises(core.MissingElementNodalForceDataError) as exc_info:
        extraction.static_force_moment_series(
            core.SectionConfig(
                analysis_mode="static",
                modal_rst="missing-nload.rst",
                element_named_selection="SELECTION",
            ),
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            [{"id": 1, "value": 1.0, "unit": "s"}],
        )

    assert "OUTRES,NLOAD,ALL" in str(exc_info.value)
    assert released == [True]


def test_modal_summation_batches_split_mode_ids() -> None:
    assert extraction.modal_summation_batches(0, 25) == []
    assert extraction.modal_summation_batches(5, 2) == [[1, 2], [3, 4], [5]]
    assert extraction.modal_summation_batches(3, 2, start_mode_id=3) == [[3, 4], [5]]


def test_config_and_cli_accept_skip_first_modes() -> None:
    cfg = core.config_from_mapping(
        {"skip_first_modes": -4, "modal_summation_batch_size": 0}
    )
    assert cfg.skip_first_modes == 0
    assert cfg.modal_summation_batch_size == extraction.DEFAULT_MODAL_SUMMATION_BATCH_SIZE

    args = cli.build_arg_parser().parse_args(
        [
            "--cli",
            "--skip-first-modes",
            "3",
            "--modal-summation-batch-size",
            "7",
        ]
    )
    cfg = cli.config_from_args(args)
    assert cfg.skip_first_modes == 3
    assert cfg.modal_summation_batch_size == 7


def test_selected_set_displacement_uses_cumulative_set_and_mesh_units() -> None:
    captured: dict[str, Any] = {}

    class FakeFieldsContainer:
        def get_field_by_time_id(self, time_id: int) -> _FakeField:
            assert time_id == 2
            return _FakeField(
                [1, 2],
                [[0.001, 0.0, 0.0], [0.0, -0.002, 0.0]],
                "m",
            )

    class FakeOutput:
        def __call__(self) -> FakeFieldsContainer:
            return FakeFieldsContainer()

    class FakeDisplacement:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            captured["operator"] = self
            self.inputs = types.SimpleNamespace(
                data_sources=_FakePin(self, "data_sources"),
                streams_container=_FakePin(self, "streams_container"),
                time_scoping=_FakePin(self, "time_scoping"),
                mesh_scoping=_FakePin(self, "mesh_scoping"),
                bool_rotate_to_global=_FakePin(self, "bool_rotate_to_global"),
            )
            self.outputs = types.SimpleNamespace(fields_container=FakeOutput())

    fake_dpf = types.SimpleNamespace(
        locations=types.SimpleNamespace(
            nodal="Nodal",
            time_freq="TimeFreq_sets",
        ),
        Scoping=lambda ids=None, location=None: _FakeScoping(ids, location),
        operators=types.SimpleNamespace(
            result=types.SimpleNamespace(displacement=FakeDisplacement)
        ),
    )
    mesh = _FakeMesh(
        nodes={1: [0.0, 0.0, 0.0], 2: [1.0, 0.0, 0.0]},
        elements={10: [1, 2]},
        unit="mm",
    )

    rows, evidence = dpf_io.selected_set_nodal_displacements(
        fake_dpf,
        object(),
        object(),
        mesh,
        2,
    )

    operator = captured["operator"]
    assert operator.values["time_scoping"].ids == [2]
    assert operator.values["time_scoping"].location == "TimeFreq_sets"
    assert operator.values["mesh_scoping"].ids == [1, 2]
    assert operator.values["mesh_scoping"].location == "Nodal"
    assert operator.values["bool_rotate_to_global"] is True
    assert rows == {1: [1.0, 0.0, 0.0], 2: [0.0, -2.0, 0.0]}
    assert evidence["geometry_state"] == "deformed"
    assert evidence["result_set_id"] == 2
    assert evidence["displacement_to_mesh_unit_factor"] == pytest.approx(1000.0)
    assert evidence["max_displacement"] == pytest.approx(2.0)
    assert evidence["max_displacement_node_id"] == 2


def test_result_set_options_use_cumulative_ids_and_require_aligned_values() -> None:
    support = types.SimpleNamespace(
        n_sets=3,
        time_frequencies=_FakeField([1, 2, 3], [0.1, 0.2, 0.3], "s"),
    )

    assert dpf_io.result_set_options(support) == [
        {"id": 1, "value": 0.1, "unit": "s", "label": "Set 1 — 0.1 s"},
        {"id": 2, "value": 0.2, "unit": "s", "label": "Set 2 — 0.2 s"},
        {"id": 3, "value": 0.3, "unit": "s", "label": "Set 3 — 0.3 s"},
    ]

    with pytest.raises(ValueError, match="misaligned"):
        dpf_io.result_set_options(
            types.SimpleNamespace(
                n_sets=3,
                time_frequencies=_FakeField([1, 2], [0.1, 0.2], "s"),
            )
        )


def test_resolve_static_result_set_ids_supports_single_range_and_all() -> None:
    result_sets = [{"id": set_id} for set_id in range(1, 9)]

    assert core.resolve_static_result_set_ids(
        core.SectionConfig(static_set_scope="single", result_set_id=4),
        result_sets,
    ) == [4]
    assert core.resolve_static_result_set_ids(
        core.SectionConfig(
            static_set_scope="range",
            result_set_range_start=2,
            result_set_range_end=8,
            result_set_range_stride=3,
        ),
        result_sets,
    ) == [2, 5, 8]
    assert core.resolve_static_result_set_ids(
        core.SectionConfig(
            static_set_scope="range",
            result_set_range_start=2,
            result_set_range_end=7,
            result_set_range_stride=3,
        ),
        result_sets,
    ) == [2, 5]
    assert core.resolve_static_result_set_ids(
        core.SectionConfig(static_set_scope="all"),
        result_sets,
    ) == list(range(1, 9))

    with pytest.raises(ValueError, match="must not exceed"):
        core.resolve_static_result_set_ids(
            core.SectionConfig(
                static_set_scope="range",
                result_set_range_start=5,
                result_set_range_end=2,
            ),
            result_sets,
        )
    with pytest.raises(ValueError, match="unavailable"):
        core.resolve_static_result_set_ids(
            core.SectionConfig(static_set_scope="single", result_set_id=9),
            result_sets,
        )


@pytest.mark.parametrize(
    ("rotation", "translation"),
    [
        (
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            [5.0, -3.0, 2.0],
        ),
        (
            [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
            [2.0, 4.0, -1.0],
        ),
        (
            [[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]],
            [-2.0, 1.0, 3.0],
        ),
    ],
)
def test_geometry_following_frame_recovers_finite_rigid_motion(
    rotation: list[list[float]],
    translation: list[float],
) -> None:
    reference = {
        1: [0.0, 0.0, 0.0],
        2: [2.0, 0.0, 0.0],
        3: [0.0, 1.0, 0.0],
        4: [2.0, 1.0, 0.0],
    }

    def moved(point: list[float]) -> list[float]:
        return [
            sum(rotation[row][column] * point[column] for column in range(3))
            + translation[row]
            for row in range(3)
        ]

    initial_origin = [3.0, -2.0, 1.0]
    current = {node_id: moved(point) for node_id, point in reference.items()}
    frame = core.fit_geometry_following_frame(
        reference,
        current,
        initial_origin,
        {
            "x": [1.0, 0.0, 0.0],
            "y": [0.0, 1.0, 0.0],
            "z": [0.0, 0.0, 1.0],
        },
        result_set_id=7,
    )

    for actual_row, expected_row in zip(frame.rotation_matrix, rotation):
        assert actual_row == pytest.approx(expected_row, abs=1.0e-12)
    assert frame.translation == pytest.approx(translation, abs=1.0e-12)
    assert frame.resolved_origin == pytest.approx(moved(initial_origin), abs=1.0e-12)
    assert frame.resolved_axes["x"] == pytest.approx(
        [rotation[row][0] for row in range(3)], abs=1.0e-12
    )
    assert frame.rank == 2
    assert frame.final_determinant == pytest.approx(1.0)
    assert frame.normalized_residual == pytest.approx(0.0, abs=1.0e-12)
    assert frame.warnings == []


def test_rebase_reference_frame_applies_cached_motion_to_current_definition() -> None:
    reference = {
        1: [0.0, 0.0, 0.0],
        2: [2.0, 0.0, 0.0],
        3: [0.0, 1.0, 0.0],
        4: [2.0, 1.0, 0.0],
    }
    rotation = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    translation = [2.0, 4.0, -1.0]
    current = {
        node_id: [
            sum(rotation[row][column] * point[column] for column in range(3))
            + translation[row]
            for row in range(3)
        ]
        for node_id, point in reference.items()
    }
    cached = core.fit_geometry_following_frame(
        reference,
        current,
        [0.0, 0.0, 0.0],
        {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        result_set_id=3,
    )

    rebased = core.rebase_reference_frame(
        cached,
        [10.0, 0.0, 0.0],
        {"x": [0.0, 1.0, 0.0], "y": [-1.0, 0.0, 0.0], "z": [0.0, 0.0, 1.0]},
        warning_ratio=0.01,
    )

    for actual_row, expected_row in zip(rebased.rotation_matrix, rotation):
        assert actual_row == pytest.approx(expected_row, abs=1.0e-12)
    assert rebased.translation == pytest.approx(translation, abs=1.0e-12)
    assert rebased.initial_origin == pytest.approx([10.0, 0.0, 0.0])
    assert rebased.resolved_origin == pytest.approx([2.0, 14.0, -1.0])
    assert rebased.resolved_axes["x"] == pytest.approx([-1.0, 0.0, 0.0])
    assert rebased.resolved_axes["y"] == pytest.approx([0.0, -1.0, 0.0])


def test_geometry_following_frame_rejects_collinear_nodes() -> None:
    coordinates = {
        1: [0.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [2.0, 0.0, 0.0],
    }

    with pytest.raises(ValueError, match="collinear"):
        core.fit_geometry_following_frame(
            coordinates,
            coordinates,
            [0.0, 0.0, 0.0],
            {
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
            result_set_id=1,
        )


def test_coordinate_axes_reject_left_handed_local_frame() -> None:
    with pytest.raises(ValueError, match="right-handed"):
        core.validate_axes(
            {
                "x": [0.0, 1.0, 0.0],
                "y": [1.0, 0.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            }
        )


def test_arbitrarily_oriented_resultant_round_trips_between_global_and_local() -> None:
    sqrt_2 = math.sqrt(2.0)
    sqrt_3 = math.sqrt(3.0)
    sqrt_6 = math.sqrt(6.0)
    axes = core.validate_axes(
        {
            "x": [1.0 / sqrt_2, -1.0 / sqrt_2, 0.0],
            "y": [1.0 / sqrt_6, 1.0 / sqrt_6, -2.0 / sqrt_6],
            "z": [1.0 / sqrt_3, 1.0 / sqrt_3, 1.0 / sqrt_3],
        }
    )
    global_resultant = [3.0, -4.0, 5.0, -7.0, 11.0, 13.0]

    local_resultant = core.rotate_to_local(global_resultant, axes)
    reconstructed_global = []
    for offset in (0, 3):
        reconstructed_global.extend(
            sum(local_resultant[offset + axis_index] * axes[axis_index][component]
                for axis_index in range(3))
            for component in range(3)
        )

    assert reconstructed_global == pytest.approx(global_resultant)
    assert core.vector_magnitude(local_resultant[:3]) == pytest.approx(
        core.vector_magnitude(global_resultant[:3])
    )
    assert core.vector_magnitude(local_resultant[3:]) == pytest.approx(
        core.vector_magnitude(global_resultant[3:])
    )


def test_geometry_following_frame_corrects_reflection_and_warns_on_distortion() -> None:
    reference_3d = {
        1: [0.0, 0.0, 0.0],
        2: [1.0, 0.0, 0.0],
        3: [0.0, 1.0, 0.0],
        4: [0.0, 0.0, 1.0],
    }
    reflected = {
        node_id: [-point[0], point[1], point[2]]
        for node_id, point in reference_3d.items()
    }
    reflected_frame = core.fit_geometry_following_frame(
        reference_3d,
        reflected,
        [0.0, 0.0, 0.0],
        {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        result_set_id=2,
    )
    assert reflected_frame.reflection_corrected is True
    assert reflected_frame.raw_determinant < 0.0
    assert reflected_frame.final_determinant == pytest.approx(1.0)

    distorted = dict(reference_3d)
    distorted[4] = [0.0, 0.0, 1.25]
    distorted_frame = core.fit_geometry_following_frame(
        reference_3d,
        distorted,
        [0.0, 0.0, 0.0],
        {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        result_set_id=3,
        warning_ratio=1.0e-4,
    )
    assert distorted_frame.normalized_residual > 1.0e-4
    assert "residual exceeds" in distorted_frame.warnings[0]


def test_summation_point_field_has_global_overall_scoping_and_mesh_unit() -> None:
    class FakeSummationPointField:
        def __init__(self, *, nentities: int, nature: str, location: str) -> None:
            self.nentities = nentities
            self.nature = nature
            self.location = location
            self.scoping = _FakeScoping()
            self.data: list[list[float]] = []
            self.unit = ""

    fake_dpf = types.SimpleNamespace(
        Field=FakeSummationPointField,
        natures=types.SimpleNamespace(vector="Vector"),
        locations=types.SimpleNamespace(overall="overall"),
    )

    field = dpf_io.summation_point_field(fake_dpf, [1.0, 2.0, 3.0], "mm")

    assert field.nentities == 1
    assert field.nature == "Vector"
    assert field.location == "overall"
    assert field.scoping.ids == [0]
    assert field.data == [[1.0, 2.0, 3.0]]
    assert field.unit == "mm"
    with pytest.raises(ValueError, match="mesh length unit"):
        dpf_io.summation_point_field(fake_dpf, [0.0, 0.0, 0.0], "")


def test_config_and_cli_accept_static_mode_and_rst_alias() -> None:
    args = cli.build_arg_parser().parse_args(
        [
            "--cli",
            "--analysis-mode",
            "static",
            "--result-set-id",
            "4",
            "--static-set-scope",
            "range",
            "--result-set-start",
            "2",
            "--result-set-end",
            "8",
            "--result-set-stride",
            "3",
            "--reference-frame-motion",
            "follow-geometry",
            "--reference-frame-attachment",
            "BOLT_TRACKING",
            "--frame-fit-warning-ratio",
            "0.02",
            "--rst",
            "static.rst",
        ]
    )

    cfg = cli.config_from_args(args)

    assert cfg.analysis_mode == "static"
    assert cfg.result_set_id == 4
    assert cfg.static_set_scope == "range"
    assert cfg.result_set_range_start == 2
    assert cfg.result_set_range_end == 8
    assert cfg.result_set_range_stride == 3
    assert cfg.reference_frame_motion == "follow-geometry"
    assert cfg.reference_frame_attachment_selection == "BOLT_TRACKING"
    assert cfg.reference_frame_fit_warning_ratio == pytest.approx(0.02)
    assert cfg.modal_rst == "static.rst"
    assert core.SectionConfig().analysis_mode == "modal"
    assert core.SectionConfig().reference_frame_motion == "follow-geometry"
    assert core.config_from_mapping({}).reference_frame_motion == "follow-geometry"
    assert core.config_from_mapping(
        {"reference_frame_motion": ""}
    ).reference_frame_motion == "follow-geometry"
    assert cli.build_arg_parser().parse_args(
        ["--modal-rst", "legacy-name.rst"]
    ).modal_rst == "legacy-name.rst"
    assert core.config_from_mapping(
        {"analysis_mode": "static", "force_type": 3}
    ).force_type == core.MECHANICAL_PROBE_FORCE_TYPE


def test_static_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "static.json"
    external_selection = tmp_path / "named_selections.cdb"
    core.save_config(
        str(path),
        core.SectionConfig(
            analysis_mode="static",
            static_set_scope="range",
            result_set_id=2,
            result_set_range_start=2,
            result_set_range_end=6,
            result_set_range_stride=2,
            modal_rst="static.rst",
            out_csv="result.csv",
            external_named_selection_path=str(external_selection),
            element_named_selection="CUT_BODY",
            reference_frame_motion="follow-geometry",
            reference_frame_attachment_selection="BOLT_TRACKING",
            reference_frame_fit_warning_ratio=0.025,
        ),
    )

    loaded = core.load_config(str(path))

    assert loaded.analysis_mode == "static"
    assert loaded.static_set_scope == "range"
    assert loaded.result_set_id == 2
    assert loaded.result_set_range_start == 2
    assert loaded.result_set_range_end == 6
    assert loaded.result_set_range_stride == 2
    assert loaded.modal_rst == "static.rst"
    assert loaded.external_named_selection_path == str(external_selection)
    assert loaded.element_named_selection == "CUT_BODY"
    assert loaded.reference_frame_motion == "follow-geometry"
    assert loaded.reference_frame_attachment_selection == "BOLT_TRACKING"
    assert loaded.reference_frame_fit_warning_ratio == pytest.approx(0.025)


def test_static_validation_requires_one_available_result_set_but_not_mcf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst placeholder")
    out_csv = tmp_path / "result.csv"
    with pytest.raises(ValueError, match="requires a result-set ID"):
        extraction.validate_paths(
            core.SectionConfig(
                analysis_mode="static",
                modal_rst=str(rst),
                out_csv=str(out_csv),
            )
        )

    dpf_io.clear_modal_rst_metadata_cache()
    monkeypatch.setattr(
        dpf_io,
        "_read_modal_rst_metadata_uncached",
        lambda signature, log=None: _fake_metadata(signature, modal_set_count=2),
    )
    with pytest.raises(ValueError, match="Static result-set ID 3 is unavailable"):
        extraction.extract_section_resultants(
            core.SectionConfig(
                analysis_mode="static",
                result_set_id=3,
                modal_rst=str(rst),
                out_csv=str(out_csv),
            )
        )


def test_run_gui_static_mode_defaults_to_last_set_and_hides_modal_controls(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window
    try:
        window._refresh_result_set_options(
            [
                {"id": 1, "value": 1.0, "unit": "s", "label": "Set 1 — 1 s"},
                {"id": 2, "value": 2.0, "unit": "s", "label": "Set 2 — 2 s"},
            ]
        )
        qapp.processEvents()

        assert window.result_set_combo.currentData() == 2
        assert window.static_set_scope_combo.currentData() == "single"
        assert window.reference_frame_motion_combo.currentData() == "follow-geometry"
        assert "moving section" in window.reference_frame_motion_combo.currentText()
        assert window.reference_frame_advanced_group.isHidden() is False
        assert "inclusive set-ID range" in window.static_set_scope_combo.toolTip()
        assert "First Static Structural" in window.result_set_range_start_spin.toolTip()
        assert "Last Static Structural" in window.result_set_range_end_spin.toolTip()
        assert "every Nth result set" in window.result_set_range_stride_spin.toolTip()
        assert "Follow Geometry transports" in window.reference_frame_motion_combo.toolTip()
        fixed_index = window.reference_frame_motion_combo.findData("fixed")
        assert "Mechanical Construction Surface" in (
            window.reference_frame_motion_combo.itemText(fixed_index)
        )
        assert "Mechanical-parity mode" in window.reference_frame_motion_combo.itemData(
            fixed_index,
            _qt_core.Qt.ItemDataRole.ToolTipRole,
        )
        assert "which nodes transport the frame" in (
            window.reference_frame_tracking_status_label.toolTip()
        )
        assert window._files_form.isRowVisible(window.static_set_scope_combo)
        assert window.result_set_combo.isEnabled()
        assert window._files_form.isRowVisible(window.result_set_combo)
        assert not window._files_form.isRowVisible(window.result_set_range_start_spin)
        assert not window._files_form.isRowVisible(window.all_result_sets_label)
        assert not window.mcf_row.isEnabled()
        assert not window._files_form.isRowVisible(window.mcf_row)
        assert not window.force_type_combo.isEnabled()
        assert not window.skip_first_modes_spin.isEnabled()
        assert not window.modal_batch_spin.isEnabled()
        assert window.modal_options_group.isHidden()
        assert not window.section_parameters_group.isHidden()
        assert not window.orientation_group.isHidden()
        assert not window.section_cut_group.isHidden()
        assert window._reference_frame_form.isRowVisible(
            window.reference_frame_motion_combo
        )
        assert window.collect_config().result_set_id == 2

        window._set_combo_value(window.static_set_scope_combo, "range")
        window.on_static_set_scope_changed()
        assert not window._files_form.isRowVisible(window.result_set_combo)
        assert window._files_form.isRowVisible(window.result_set_range_start_spin)
        assert window._files_form.isRowVisible(window.result_set_range_end_spin)
        assert window._files_form.isRowVisible(window.result_set_range_stride_spin)
        window.result_set_range_start_spin.setValue(1)
        window.result_set_range_end_spin.setValue(2)
        window.result_set_range_stride_spin.setValue(2)
        ranged_config = window.collect_config()
        assert ranged_config.static_set_scope == "range"
        assert ranged_config.result_set_range_start == 1
        assert ranged_config.result_set_range_end == 2
        assert ranged_config.result_set_range_stride == 2

        window._set_combo_value(window.static_set_scope_combo, "all")
        window.on_static_set_scope_changed()
        assert window._files_form.isRowVisible(window.all_result_sets_label)
        assert window.all_result_sets_label.text() == "All 2 cumulative set(s)"
        assert not window._files_form.isRowVisible(window.result_set_combo)
        assert not window._files_form.isRowVisible(window.result_set_range_start_spin)

        window._set_combo_value(window.reference_frame_motion_combo, "follow-geometry")
        window.on_reference_frame_motion_changed()
        assert window.reference_frame_advanced_group.isVisible()
        assert "local section-cut neighborhood" in (
            window.reference_frame_tracking_status_label.text()
        )
        window.reference_frame_attachment_combo.setEditText("BOLT_TRACKING")
        window.on_reference_frame_attachment_changed()
        following_config = window.collect_config()
        assert following_config.reference_frame_motion == "follow-geometry"
        assert following_config.reference_frame_attachment_selection == "BOLT_TRACKING"
        assert "BOLT_TRACKING" in window.reference_frame_tracking_status_label.text()

        set_signatures = [
            {"analysis_mode": "static", "result_set_id": set_id}
            for set_id in (2, 5, 8)
        ]
        window._last_visualization_result_data = {
            "analysis_mode": "static",
            "times": [2.0, 5.0, 8.0],
            "result_set_ids": [2, 5, 8],
            "selected_result_sets": [
                {"id": set_id, "label": f"Set {set_id} — {set_id} s"}
                for set_id in (2, 5, 8)
            ],
            "signatures": set_signatures,
        }
        window._last_visualization_payload = {
            "result_signature": set_signatures[-1]
        }
        window._set_visualization_result_times(window._last_visualization_result_data)
        assert window.visualization_time_combo.currentData() == 2
        assert window.visualization_time_combo.currentText() == "Set 8 — 8 s"
        requested_sets: list[int | None] = []
        monkeypatch.setattr(
            window,
            "update_visualization",
            lambda _checked=False, *, result_set_id=None: requested_sets.append(
                result_set_id
            ),
        )
        was_blocked = window.visualization_time_combo.blockSignals(True)
        window.visualization_time_combo.setCurrentIndex(0)
        window.visualization_time_combo.blockSignals(was_blocked)
        window.on_visualization_time_changed(0)
        assert requested_sets == [2]

        window.result_set_combo.setCurrentIndex(0)
        monkeypatch.setattr(
            window,
            "refresh_modal_rst_metadata",
            lambda show_errors=False: window._refresh_result_set_options(
                [
                    {"id": 1, "value": 1.0, "unit": "s", "label": "Set 1"},
                    {"id": 2, "value": 2.0, "unit": "s", "label": "Set 2"},
                    {"id": 3, "value": 3.0, "unit": "s", "label": "Set 3"},
                ]
            ),
        )
        window.on_modal_rst_path_changed("new.rst")
        assert window.result_set_combo.currentData() == 3

        window._set_combo_value(window.analysis_mode_combo, "modal")
        window.on_analysis_mode_changed()
        assert not window.result_set_combo.isEnabled()
        assert not window._files_form.isRowVisible(window.static_set_scope_combo)
        assert not window._files_form.isRowVisible(window.result_set_combo)
        assert window.mcf_row.isEnabled()
        assert window._files_form.isRowVisible(window.mcf_row)
        assert window.force_type_combo.isEnabled()
        assert not window.modal_options_group.isHidden()
        assert window._modal_options_form.isRowVisible(window.force_type_combo)
        assert window._modal_options_form.isRowVisible(window.skip_first_modes_spin)
        assert window._modal_options_form.isRowVisible(window.modal_batch_spin)
        assert not window._reference_frame_form.isRowVisible(
            window.reference_frame_motion_combo
        )
        assert window.reference_frame_advanced_group.isHidden()
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_gui_discards_visualization_completed_for_edited_inputs(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window

    class FakeWorker:
        @staticmethod
        def isRunning() -> bool:  # noqa: N802
            return True

    accepted_payloads: list[dict[str, Any]] = []
    try:
        window._visualization_generation = 4
        started_revision = window._visualization_input_revision
        window.visualization_worker = FakeWorker()
        monkeypatch.setattr(window, "on_visualization_completed", accepted_payloads.append)

        window.origin_edits[0].setText("42")
        qapp.processEvents()
        assert window._visualization_input_revision > started_revision
        assert window._visualization_stale is True
        assert not window.visualization_update_button.isEnabled()

        window._on_visualization_thread_completed(
            4,
            started_revision,
            {"plane": {"origin": [0.0, 0.0, 0.0]}},
        )

        assert accepted_payloads == []
        assert window.visualization_worker is None
        assert window.visualization_update_button.isEnabled()
        assert window._visualization_stale is True
        assert "inputs changed while loading" in window.visualization_status_label.text()
    finally:
        window.visualization_worker = None
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_gui_renders_follow_geometry_reference_preview_as_warning(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    assert gui.run_gui(
        core.SectionConfig(
            analysis_mode="static",
            static_set_scope="all",
            reference_frame_motion="follow-geometry",
        )
    ) == 0
    window = qapp._mcf_dpf_section_resultants_window
    rendered_payloads: list[dict[str, Any]] = []
    error_dialogs: list[tuple[Any, ...]] = []
    warning = visualization.follow_geometry_reference_preview_warning(0)
    payload = {
        "geometry_state": "reference",
        "result_set_id": None,
        "requested_result_set_id": 2,
        "deformation": None,
        "resolved_reference_frame": None,
        "result_signature": None,
        "preview_only_reason": visualization.FOLLOW_GEOMETRY_REFERENCE_PREVIEW_REASON,
        "warnings": [warning],
        "mesh": {"points": [], "cells": [], "celltypes": []},
        "counts": {
            "raw_element_count": 2,
            "cut_element_count": 0,
            "force_summation_node_count": 0,
            "mesh_node_count": 8,
        },
        "result_overlay": {"label": "stale result"},
    }
    try:
        window._loaded_result_sets = [
            {"id": 1, "value": 1.0, "unit": "s", "label": "Set 1"},
            {"id": 2, "value": 2.0, "unit": "s", "label": "Set 2"},
        ]
        window._refresh_animation_availability()
        assert window.animation_group.body_widget.isEnabled() is True
        monkeypatch.setattr(
            window.visualization_widget,
            "render_payload",
            lambda item: rendered_payloads.append(item) or True,
        )
        monkeypatch.setattr(
            window,
            "_show_themed_error_dialog",
            lambda *args: error_dialogs.append(args),
        )

        window.on_visualization_completed(payload)

        assert error_dialogs == []
        assert window._visualization_stale is False
        assert rendered_payloads[-1].get("result_overlay") is None
        status = window.visualization_status_label.text()
        assert "initial/reference state only" in status
        assert "other result sets cannot be previewed" in status
        assert window.visualization_status_label.toolTip() == status
        assert window.animation_group.body_widget.isEnabled() is False
        assert "initial/reference state" in window.animation_group.toolTip()

        valid_payload = dict(payload)
        valid_payload.pop("preview_only_reason")
        valid_payload["geometry_state"] = "deformed"
        valid_payload["result_set_id"] = 2
        valid_payload["deformation"] = {"geometry_state": "deformed"}
        valid_payload["warnings"] = []
        window.on_visualization_completed(valid_payload)
        assert window.animation_group.body_widget.isEnabled() is True
    finally:
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_modal_force_moment_coefficients_batches_dpf_time_scoping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_mode_batches: list[list[int]] = []
    requested_force_types: list[int] = []
    nodal_forces_available = [True]
    nodal_moments_available = [True]

    class FakeFieldsContainer:
        def __init__(self, kind: str, mode_ids: list[int]) -> None:
            self.kind = kind
            self.mode_ids = list(mode_ids)

        def get_field_by_time_id(self, time_id: int) -> _FakeField:
            if time_id not in self.mode_ids:
                raise KeyError(time_id)
            if self.kind == "force":
                return _FakeField([1], [[float(time_id), 0.0, 0.0]], "N")
            if self.kind == "moment":
                return _FakeField([1], [[0.0, 10.0 * float(time_id), 0.0]], "N mm")
            if self.kind == "node_moments":
                return _FakeField(
                    [101, 102],
                    [[0.0, 0.0, float(time_id)], [0.0, 0.0, 0.0]],
                    "N mm",
                )
            return _FakeField(
                [101, 102],
                [
                    [float(time_id), 0.0, 0.0],
                    [0.0, float(time_id), 0.0],
                ],
                "N",
            )

    class FakeOutput:
        def __init__(self, factory: Any) -> None:
            self.factory = factory

        def __call__(self) -> Any:
            return self.factory()

    class FakeForceSummation:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            self._recorded = False
            self.inputs = types.SimpleNamespace(
                data_sources=_FakePin(self, "data_sources"),
                streams_container=_FakePin(self, "streams_container"),
                time_scoping=_FakePin(self, "time_scoping"),
                nodal_scoping=_FakePin(self, "nodal_scoping"),
                elemental_scoping=_FakePin(self, "elemental_scoping"),
                force_type=_FakePin(self, "force_type"),
            )
            self.outputs = types.SimpleNamespace(
                force_accumulation=FakeOutput(lambda: self._fields("force")),
                moment_accumulation=FakeOutput(lambda: self._fields("moment")),
                forces_on_nodes=FakeOutput(lambda: self._fields("nodes")),
                moments_on_nodes=FakeOutput(lambda: self._fields("node_moments")),
            )

        def _mode_ids(self) -> list[int]:
            scoping = self.values["time_scoping"]
            return [int(value) for value in scoping.ids]

        def _fields(self, kind: str) -> FakeFieldsContainer:
            if kind == "nodes" and not nodal_forces_available[0]:
                raise KeyError("missing forces_on_nodes")
            if kind == "node_moments" and not nodal_moments_available[0]:
                raise KeyError("empty moments_on_nodes")
            mode_ids = self._mode_ids()
            if not self._recorded:
                requested_mode_batches.append(mode_ids)
                requested_force_types.append(int(self.values["force_type"]))
                self._recorded = True
            return FakeFieldsContainer(kind, mode_ids)

    class FakeModel:
        def __init__(self) -> None:
            self.metadata = types.SimpleNamespace(
                time_freq_support=types.SimpleNamespace(n_sets=5),
                result_info=types.SimpleNamespace(available_results=["element_nodal_forces"]),
            )

    fake_dpf = types.SimpleNamespace(
        __version__="0.15.2",
        locations=types.SimpleNamespace(elemental="Elemental", nodal="Nodal"),
        Scoping=lambda ids=None, location=None: _FakeScoping(ids, location),
        DataSources=lambda path: types.SimpleNamespace(path=path),
        Model=lambda data_sources: FakeModel(),
        operators=types.SimpleNamespace(
            averaging=types.SimpleNamespace(force_summation=FakeForceSummation)
        ),
    )
    _install_fake_dpf_core(monkeypatch, fake_dpf)
    monkeypatch.setattr(dpf_io, "detected_ansys_release_codes", lambda: [])
    monkeypatch.setattr(
        extraction,
        "create_streams_container",
        lambda _dpf, _data_sources: types.SimpleNamespace(release_handles=lambda: None),
    )
    monkeypatch.setattr(
        extraction,
        "resolve_element_named_selection_scoping",
        lambda *_args, **_kwargs: (
            _FakeScoping([7, 8], "Elemental"),
            "CUT_SMALL",
            ["CUT_SMALL"],
        ),
    )
    monkeypatch.setattr(
        extraction,
        "selected_element_mesh",
        lambda *_args, **_kwargs: _FakeMesh(
            nodes={101: [0.0, 0.0, 0.0], 102: [1.0, 0.0, 0.0]},
            elements={7: [101, 102]},
        ),
    )
    def fake_construction_surface_scoping(
        *_args: Any,
        **kwargs: Any,
    ) -> tuple[_FakeScoping, _FakeScoping, dict[str, Any]]:
        mesh = kwargs["mesh"]
        coordinates = {
            node_id: list(mesh.nodes.node_by_id(node_id).coordinates)
            for node_id in (101, 102)
        }
        return (
            _FakeScoping([7], "Elemental"),
            _FakeScoping([101, 102], "Nodal"),
            {
                "cut_element_count": 1,
                "selected_node_count": 2,
                "not_cut_element_count": 0,
                "element_failure_count": 0,
                "moment_reference_centroid": [0.0, 0.0, 0.0],
                "selected_node_centroid": [0.0, 0.0, 0.0],
                "selected_node_ids": [101, 102],
                "cut_element_ids": [7],
                "selected_node_coordinates": coordinates,
            },
        )

    monkeypatch.setattr(
        extraction,
        "construction_surface_scoping",
        fake_construction_surface_scoping,
    )

    coefficients, info = extraction.modal_force_moment_coefficients(
        core.SectionConfig(
            modal_rst="modal.rst",
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
            modal_summation_batch_size=2,
            skip_first_modes=2,
        ),
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        max_modes=3,
        capture_nodal_vectors=True,
    )

    assert requested_mode_batches == [[3, 4], [5]]
    assert coefficients == [
        [3.0, 0.0, 0.0, 0.0, 30.0, 0.0],
        [4.0, 0.0, 0.0, 0.0, 40.0, 0.0],
        [5.0, 0.0, 0.0, 0.0, 50.0, 0.0],
    ]
    assert info["modal_summation_batch_size"] == 2
    assert info["modal_summation_batch_count"] == 2
    assert info["skip_first_modes"] == 2
    assert info["first_mode_set_id"] == 3
    assert info["last_mode_set_id"] == 5
    assert info["modes_available_after_skip"] == 3
    assert info["_visualization_vector_data"]["nodal_force_modal_coefficients"][101] == [
        [3.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [5.0, 0.0, 0.0],
    ]

    requested_mode_batches.clear()
    requested_force_types.clear()
    monkeypatch.setattr(
        extraction,
        "selected_set_nodal_displacements",
        lambda _dpf, _data_sources, _streams, mesh, result_set_id, log=None: (
            {
                node_id: (
                    [0.0, 0.0, 0.0]
                    if node_id == 101
                    else [float(result_set_id), 0.0, 0.0]
                )
                for node_id in mesh.nodes.scoping.ids
            },
            {
                "geometry_state": "deformed",
                "result_set_id": int(result_set_id),
                "mesh_unit": "m",
            },
        ),
    )
    coefficients, info = extraction.modal_force_moment_coefficients(
        core.SectionConfig(
            analysis_mode="static",
            result_set_id=2,
            modal_rst="static.rst",
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
            force_type=3,
        ),
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        capture_nodal_vectors=True,
    )

    assert requested_mode_batches == [[2]]
    assert requested_force_types == [core.MECHANICAL_PROBE_FORCE_TYPE]
    assert coefficients == [[2.0, 0.0, 0.0, 0.0, 20.0, 0.0]]
    assert info["analysis_mode"] == "static"
    assert info["result_set_id"] == 2
    assert info["geometry_state"] == "deformed"
    assert info["deformation"]["result_set_id"] == 2
    assert info["_visualization_vector_data"]["selected_node_coordinates"][102] == [
        3.0,
        0.0,
        0.0,
    ]
    reconstructed = visualization.nodal_reconstructed_resultant_rows(
        {
            "modal_coordinates": [[1.0]],
            "modes_used": 1,
            "mesh_unit": info["mesh_unit"],
            "result_units": info["result_units"],
            **info["_visualization_vector_data"],
        }
    )
    assert reconstructed is not None
    assert reconstructed["global_rows"][0][3:6] == [0.0, 0.0, 6002.0]
    assert info["modal_summation_batch_count"] == 1
    assert info["_visualization_vector_data"]["nodal_moment_modal_coefficients"][101] == [
        [0.0, 0.0, 2.0]
    ]

    nodal_moments_available[0] = False
    _coefficients, info = extraction.modal_force_moment_coefficients(
        core.SectionConfig(
            analysis_mode="static",
            result_set_id=1,
            modal_rst="static.rst",
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
        ),
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        capture_nodal_vectors=True,
    )
    assert info["_visualization_vector_data"]["nodal_moment_modal_coefficients"][101] == [
        [0.0, 0.0, 0.0]
    ]
    assert info["nodal_moment_output_available"] is False
    assert "empty moments_on_nodes" in info["nodal_moment_capture_warning"]

    nodal_forces_available[0] = False
    with pytest.raises(RuntimeError, match="per-node forces"):
        extraction.modal_force_moment_coefficients(
            core.SectionConfig(
                analysis_mode="static",
                result_set_id=1,
                modal_rst="static.rst",
                element_named_selection="CUT_SMALL",
            ),
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            capture_nodal_vectors=True,
        )


def test_nodal_resultant_parity_scales_tolerance_and_marks_incomplete_moments() -> None:
    parity = extraction.nodal_resultant_parity(
        [1.0e9, 0.0, 0.0, 0.0, 10.0, 0.0],
        [1.0e9 + 100.0, 0.0, 0.0, 0.0, 10.0, 0.0],
        nodal_moments_complete=False,
    )

    assert parity["force_matches"] is True
    assert parity["force_error_norm"] == 100.0
    assert parity["moment_matches"] is None
    assert parity["moment_comparison_complete"] is False


def test_static_nodal_couples_accept_empty_convert_units_and_fail_unreadable_output() -> None:
    rows, status = extraction.static_nodal_moment_rows([], 1, "N m")
    assert rows == {}
    assert status == "empty_zero"

    class CoupleFields:
        def __len__(self) -> int:
            return 1

        def get_field_by_time_id(self, set_id: int) -> _FakeField:
            assert set_id == 1
            return _FakeField([101], [[0.0, 0.0, 1000.0]], "N mm")

    rows, status = extraction.static_nodal_moment_rows(CoupleFields(), 1, "N m")
    assert status == "available"
    assert rows[101] == pytest.approx([0.0, 0.0, 1.0])

    class UnreadableCoupleFields:
        def __len__(self) -> int:
            return 1

        def get_field_by_time_id(self, _set_id: int) -> _FakeField:
            raise RuntimeError("couple field unavailable")

    with pytest.raises(RuntimeError, match="couple field unavailable"):
        extraction.static_nodal_moment_rows(UnreadableCoupleFields(), 1, "N m")


def test_static_force_parity_rejects_hidden_transverse_component_error() -> None:
    parity = extraction.nodal_resultant_parity(
        [1.0e9, 0.0, 0.0, 0.0, 0.0, 0.0],
        [1.0e9, 100.0, 0.0, 0.0, 0.0, 0.0],
    )

    assert parity["force_matches"] is False
    assert parity["force_component_matches"] == [True, False, True]
    with pytest.raises(RuntimeError, match="cannot be published"):
        extraction.require_static_nodal_force_match(parity, 7)


@pytest.mark.parametrize(
    "payload",
    [
        {"mcf": "file.mcf", "out_csv": "resultants.csv"},
        {"modal_rst": None, "mcf": "file.mcf", "out_csv": "resultants.csv"},
    ],
)
def test_load_config_accepts_missing_modal_rst_path(
    tmp_path: Path,
    payload: dict[str, Any],
) -> None:
    config_path = tmp_path / "section_resultants_config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = core.load_config(str(config_path))

    assert config.modal_rst == ""
    assert config.mcf == "file.mcf"
    assert config.out_csv == "resultants.csv"


def test_load_config_can_keep_current_modal_rst_path(tmp_path: Path) -> None:
    config_path = tmp_path / "section_resultants_config.json"
    config_path.write_text(
        json.dumps(
            {
                "modal_rst": r"C:\old\modal.rst",
                "mcf": "file.mcf",
                "out_csv": "resultants.csv",
            }
        ),
        encoding="utf-8",
    )

    config = core.load_config(
        str(config_path),
        include_modal_rst=False,
        current_modal_rst=r"D:\current\modal.rst",
    )

    assert config.modal_rst == r"D:\current\modal.rst"
    assert config.mcf == "file.mcf"
    assert config.out_csv == "resultants.csv"


def test_default_moment_reference_matches_local_coord_summation_origin() -> None:
    assert core.SectionConfig().moment_reference_mode == "coordinate_system_origin"
    assert core.config_from_mapping({}).moment_reference_mode == "coordinate_system_origin"
    assert core.MOMENT_REFERENCE_CHOICES[0] == (
        "Coordinate system origin",
        "coordinate_system_origin",
    )


def test_extract_section_resultants_limits_dpf_modes_to_mcf_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    out_csv = tmp_path / "resultants.csv"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 2",
                "Time Coordinates",
                "0.0 1.0 2.0",
                "1.0 3.0 4.0",
            ]
        ),
        encoding="utf-8",
    )
    dpf_io.clear_modal_rst_metadata_cache()

    captured: dict[str, Any] = {}

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, modal_set_count=7)

    def fake_coefficients(
        _config: core.SectionConfig,
        _axes: core.Matrix3,
        _log: core.LogFn = None,
        *,
        max_modes: int | None = None,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        captured["max_modes"] = max_modes
        return (
            [
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
            ],
            {
                "modal_sets_available": 7,
                "modes_evaluated": 2,
                "raw_element_count": 3,
                "elapsed_seconds": 0.01,
                "result_units": {"force": "N", "moment": "N mm"},
                "section_geometry": {
                    "width_axis": "x",
                    "height_axis": "y",
                    "width_mm": 10.0,
                    "height_mm": 4.0,
                    "area_mm2": 40.0,
                    "point_source": "selected_side_nodes",
                    "point_count": 2,
                },
            },
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(extraction, "modal_force_moment_coefficients", fake_coefficients)
    messages: list[str] = []

    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            modal_rst=str(modal_rst),
            mcf=str(mcf),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        ),
        log=messages.append,
    )

    assert captured["max_modes"] == 2
    assert summary["metadata_only_load"] is True
    assert summary["modal_sets_available"] == 7
    assert summary["modes_evaluated"] == 2
    assert summary["modes_in_modal_rst"] == 7
    assert summary["modes_in_mcf"] == 2
    assert summary["selected_named_selection_count"] == 3
    assert summary["timings"]["metadata_load_seconds"] >= 0.0

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0][1:7] == [
        "fx_global [N]",
        "fy_global [N]",
        "fz_global [N]",
        "mx_global_about_global_origin [N mm]",
        "my_global_about_global_origin [N mm]",
        "mz_global_about_global_origin [N mm]",
    ]
    assert rows[1][:7] == ["0", "1", "20", "0", "0", "0", "0"]
    assert rows[2][:7] == ["1", "3", "40", "0", "0", "0", "0"]

    summary_path = Path(summary["summary_json"])
    persisted = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["result_units"] == {"force": "N", "moment": "N mm"}
    assert persisted["result_units"] == {"force": "N", "moment": "N mm"}
    assert persisted["modes_evaluated"] == 2
    assert persisted["dpf_force_summation"]["section_geometry"]["area_mm2"] == 40.0
    joined = "\n".join(messages)
    assert "Extraction settings:" in joined
    assert "Metadata stage complete" in joined
    assert "MCF parse complete" in joined
    assert "Multiplying 2 MCF row(s) by 2 modal force/moment coefficient row(s)" in joined
    assert "Extraction finished in" in joined


def test_extract_section_resultants_default_reference_matches_local_coord_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    out_csv = tmp_path / "resultants.csv"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 1",
                "Time Coordinates",
                "0.0 1.0",
            ]
        ),
        encoding="utf-8",
    )
    dpf_io.clear_modal_rst_metadata_cache()

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, modal_set_count=1)

    def fake_coefficients(
        config: core.SectionConfig,
        _axes: core.Matrix3,
        _log: core.LogFn = None,
        *,
        max_modes: int | None = None,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        reference = (
            config.coordinate_system_origin
            if config.moment_reference_mode == "coordinate_system_origin"
            else [1.0, 0.0, 0.0]
        )
        return (
            [[0.0, 10.0, 0.0, 0.0, 0.0, 50.0]],
            {
                "modal_sets_available": 1,
                "modes_evaluated": 1,
                "raw_element_count": 3,
                "elapsed_seconds": 0.01,
                "coordinate_system_origin": reference,
                "result_units": {"force": "N", "moment": "N mm"},
            },
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(extraction, "modal_force_moment_coefficients", fake_coefficients)

    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            modal_rst=str(modal_rst),
            mcf=str(mcf),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[2.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [0.0, 0.0, 1.0],
                "y": [0.0, -1.0, 0.0],
                "z": [1.0, 0.0, 0.0],
            },
        )
    )

    assert summary["config"]["moment_reference_mode"] == "coordinate_system_origin"
    assert summary["dpf_force_summation"]["moment_reference_xyz"] == [2.0, 0.0, 0.0]
    assert summary["max_abs_resultant_global_origin"] == pytest.approx(
        {"fx": 0.0, "fy": 10.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 50.0}
    )
    assert summary["max_abs_resultant_global"] == pytest.approx(
        {"fx": 0.0, "fy": 10.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 50.0}
    )
    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][4:7] == ["0", "0", "50"]
    assert rows[1][10:13] == ["30", "0", "0"]


def test_extract_section_resultants_skips_first_modes_before_multiplication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    out_csv = tmp_path / "resultants.csv"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 4",
                "Time Coordinates",
                "0.0 100.0 1.0 2.0 3.0",
                "1.0 200.0 4.0 5.0 6.0",
            ]
        ),
        encoding="utf-8",
    )
    dpf_io.clear_modal_rst_metadata_cache()

    captured: dict[str, Any] = {}

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, modal_set_count=4)

    def fake_coefficients(
        config: core.SectionConfig,
        _axes: core.Matrix3,
        _log: core.LogFn = None,
        *,
        max_modes: int | None = None,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        captured["max_modes"] = max_modes
        captured["skip_first_modes"] = config.skip_first_modes
        return (
            [
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 100.0, 0.0, 0.0, 0.0],
            ],
            {
                "modal_sets_available": 4,
                "modes_available_after_skip": 3,
                "skip_first_modes": 1,
                "first_mode_set_id": 2,
                "last_mode_set_id": 4,
                "modes_evaluated": 3,
                "raw_element_count": 3,
                "elapsed_seconds": 0.01,
                "result_units": {"force": "N", "moment": "N mm"},
            },
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(extraction, "modal_force_moment_coefficients", fake_coefficients)
    messages: list[str] = []

    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            modal_rst=str(modal_rst),
            mcf=str(mcf),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
            skip_first_modes=1,
        ),
        log=messages.append,
    )

    assert captured == {"max_modes": 3, "skip_first_modes": 1}
    assert summary["skip_first_modes"] == 1
    assert summary["skipped_mcf_modes"] == 1
    assert summary["mcf_modes_after_skip"] == 3
    assert summary["modal_sets_after_skip"] == 3
    assert summary["modes_used"] == 3
    assert summary["ignored_mcf_modes"] == 0

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][:7] == ["0", "1", "20", "300", "0", "0", "0"]
    assert rows[2][:7] == ["1", "4", "50", "600", "0", "0", "0"]

    joined = "\n".join(messages)
    assert "Skipping first 1 mode(s)" in joined
    assert "MCF modal coordinate column(s) 1-1" in joined


def test_extract_section_resultants_keeps_vector_data_in_memory_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    out_csv = tmp_path / "resultants.csv"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 1",
                "Time Coordinates",
                "0.0 2.0",
            ]
        ),
        encoding="utf-8",
    )
    dpf_io.clear_modal_rst_metadata_cache()

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, modal_set_count=1)

    def fake_coefficients(
        _config: core.SectionConfig,
        _axes: core.Matrix3,
        _log: core.LogFn = None,
        *,
        max_modes: int | None = None,
        capture_nodal_vectors: bool = False,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        assert max_modes == 1
        assert capture_nodal_vectors is True
        return (
            [[1.0, 0.0, 0.0, 0.0, 0.0, 3.0]],
            {
                "modal_sets_available": 1,
                "modes_evaluated": 1,
                "raw_element_count": 3,
                "elapsed_seconds": 0.01,
                "result_units": {"force": "N", "moment": "N mm"},
                "_visualization_vector_data": {
                    "nodal_force_modal_coefficients": {
                        1: [[1.0, 0.0, 0.0]],
                    },
                    "selected_node_coordinates": {
                        1: [0.0, 0.0, 0.0],
                    },
                    "selected_node_centroid": [0.0, 0.0, 0.0],
                    "moment_reference_xyz": [0.0, 0.0, 0.0],
                },
            },
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(extraction, "modal_force_moment_coefficients", fake_coefficients)

    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            modal_rst=str(modal_rst),
            mcf=str(mcf),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
        ),
        capture_visualization_vectors=True,
    )

    assert "_visualization_result_data" in summary
    assert summary["_visualization_result_data"]["times"] == [0.0]
    assert summary["_visualization_result_data"]["resultants_global"] == [
        [2.0, 0.0, 0.0, 0.0, 0.0, 6.0]
    ]
    assert summary["_visualization_result_data"]["result_units"] == {
        "force": "N",
        "moment": "N mm",
    }
    assert "_visualization_vector_data" not in summary["dpf_force_summation"]

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert "_visualization_result_data" not in persisted
    assert "_visualization_vector_data" not in persisted["dpf_force_summation"]


def test_extract_section_resultants_refuses_locked_output_before_dpf_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    mcf.write_text("Number of Modes : 1\nTime Coordinates\n0.0 1.0\n", encoding="utf-8")
    out_csv = tmp_path / "resultants.csv"
    out_csv.write_text("existing\n", encoding="utf-8")

    def fail_output_check(path: str) -> None:
        raise PermissionError(extraction.output_csv_unavailable_message(path))

    def fail_metadata_load(_path: str, log: core.LogFn = None) -> dpf_io.ModalRstMetadata:
        pytest.fail("DPF metadata should not load when output CSV is unavailable")

    monkeypatch.setattr(extraction, "ensure_output_csv_can_be_replaced", fail_output_check)
    monkeypatch.setattr(extraction, "load_modal_rst_metadata", fail_metadata_load)

    with pytest.raises(PermissionError, match="open or locked"):
        extraction.extract_section_resultants(
            core.SectionConfig(
                modal_rst=str(modal_rst),
                mcf=str(mcf),
                out_csv=str(out_csv),
                element_named_selection="CUT_SMALL",
            )
        )

    assert out_csv.read_text(encoding="utf-8") == "existing\n"


def test_write_result_csv_keeps_existing_file_when_final_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_csv = tmp_path / "resultants.csv"
    out_csv.write_text("existing\n", encoding="utf-8")

    def fail_replace(_source: str | Path, _target: str | Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(extraction.os, "replace", fail_replace)

    with pytest.raises(PermissionError, match="open or locked"):
        extraction.write_result_csv(
            str(out_csv),
            [0.0],
            [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
            [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]],
        )

    assert out_csv.read_text(encoding="utf-8") == "existing\n"
    assert list(tmp_path.glob(".resultants.csv.*.tmp")) == []


def test_write_result_csv_adds_force_and_moment_units_to_headers(tmp_path: Path) -> None:
    out_csv = tmp_path / "resultants.csv"

    extraction.write_result_csv(
        str(out_csv),
        [0.0],
        [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]],
        [[6.0, 5.0, 4.0, 3.0, 2.0, 1.0]],
        {"force": "N", "moment": "N mm"},
    )

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == [
        "time_s",
        "fx_global [N]",
        "fy_global [N]",
        "fz_global [N]",
        "mx_global_about_global_origin [N mm]",
        "my_global_about_global_origin [N mm]",
        "mz_global_about_global_origin [N mm]",
        "fx_local [N]",
        "fy_local [N]",
        "fz_local [N]",
        "mx_local_about_moment_reference [N mm]",
        "my_local_about_moment_reference [N mm]",
        "mz_local_about_moment_reference [N mm]",
    ]


def test_dpf_field_unit_reads_field_units() -> None:
    assert dpf_io.dpf_field_unit(_FakeField([1], [[1.0, 0.0, 0.0]], "N")) == "N"
    assert dpf_io.dpf_field_unit(_FakeField([1], [[1.0, 0.0, 0.0]], "N.mm")) == "N.mm"
    assert (
        dpf_io.result_units_from_fields(
            _FakeField([1], [[1.0, 0.0, 0.0]], "lbf"),
            _FakeField([1], [[1.0, 0.0, 0.0]], "lbf in"),
        )
        == {"force": "lbf", "moment": "lbf in"}
    )
    assert (
        dpf_io.result_units_from_fields(
            _FakeField([1], [[1.0, 0.0, 0.0]], "N"),
            _FakeField([1], [[1.0, 0.0, 0.0]], "N.mm"),
        )
        == {"force": "N", "moment": "N.mm"}
    )
    assert core.complete_result_units(
        {"force": "N", "moment": "N.mm"},
        mesh_unit="m",
    ) == {"force": "N", "moment": "N.mm"}
    assert core.complete_result_units(
        {"force": "N", "moment": None},
        mesh_unit="mm",
    ) == {"force": "N", "moment": "N mm"}
    assert core.complete_result_units(
        {"force": "N", "moment": None},
        mesh_unit="m",
    ) == {"force": "N", "moment": "N m"}


def test_extract_section_resultants_warns_and_ignores_extra_mcf_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modal_rst = tmp_path / "modal.rst"
    modal_rst.write_bytes(b"rst placeholder")
    mcf = tmp_path / "file.mcf"
    out_csv = tmp_path / "resultants.csv"
    mcf.write_text(
        "\n".join(
            [
                "Number of Modes : 4",
                "Time Coordinates",
                "0.0 1.0 2.0 100.0 200.0",
                "1.0 3.0 4.0 300.0 400.0",
            ]
        ),
        encoding="utf-8",
    )
    dpf_io.clear_modal_rst_metadata_cache()

    captured: dict[str, Any] = {}

    def fake_uncached(
        signature: dpf_io.ModalRstSignature,
        log: core.LogFn = None,
    ) -> dpf_io.ModalRstMetadata:
        return _fake_metadata(signature, modal_set_count=2)

    def fake_coefficients(
        _config: core.SectionConfig,
        _axes: core.Matrix3,
        _log: core.LogFn = None,
        *,
        max_modes: int | None = None,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        captured["max_modes"] = max_modes
        return (
            [
                [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
            ],
            {
                "modal_sets_available": 2,
                "modes_evaluated": 2,
                "raw_element_count": 3,
                "elapsed_seconds": 0.01,
            },
        )

    monkeypatch.setattr(dpf_io, "_read_modal_rst_metadata_uncached", fake_uncached)
    monkeypatch.setattr(extraction, "modal_force_moment_coefficients", fake_coefficients)
    messages: list[str] = []

    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            modal_rst=str(modal_rst),
            mcf=str(mcf),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[0.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        ),
        log=messages.append,
    )

    assert captured["max_modes"] == 2
    assert summary["modes_used"] == 2
    assert summary["modes_in_modal_rst"] == 2
    assert summary["modes_in_mcf"] == 4
    assert summary["ignored_mcf_modes"] == 2

    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert rows[1][:7] == ["0", "1", "20", "0", "0", "0", "0"]
    assert rows[2][:7] == ["1", "3", "40", "0", "0", "0", "0"]

    joined = "\n".join(messages)
    assert "Warning: MCF has 4 modal coordinate(s) per point" in joined
    assert "Extra MCF modal coordinate column(s) will be ignored." in joined
    assert "Warning: using 2 common modes; modal RST has 2, MCF has 4 after skipping 0." in joined


def test_static_range_extraction_writes_ordered_compact_set_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst placeholder")
    out_csv = tmp_path / "static_range.csv"
    dpf_io.clear_modal_rst_metadata_cache()
    calls: list[list[int]] = []

    monkeypatch.setattr(
        dpf_io,
        "_read_modal_rst_metadata_uncached",
        lambda signature, log=None: _fake_metadata(signature, modal_set_count=8),
    )
    monkeypatch.setattr(
        extraction,
        "parse_mcf",
        lambda _path: pytest.fail("Static extraction must not read an MCF file."),
    )

    def fake_series(
        config: core.SectionConfig,
        _axes: core.Matrix3,
        selected_result_sets: list[dict[str, Any]],
        _log: core.LogFn = None,
        *,
        capture_nodal_vectors: bool = False,
    ) -> dict[str, Any]:
        selected_ids = [int(item["id"]) for item in selected_result_sets]
        calls.append(selected_ids)
        frames = [
            core.fixed_reference_frame(
                [float(set_id), 0.0, 0.0],
                config.coordinate_system_axes,
                result_set_id=set_id,
                result_value=float(set_id),
                result_unit="s",
            ).__dict__
            for set_id in selected_ids
        ]
        signatures = []
        set_results = []
        global_rows = []
        local_rows = []
        for set_id, frame in zip(selected_ids, frames):
            set_config = core.config_from_mapping(
                {**config.__dict__, "result_set_id": set_id}
            )
            signature = core.result_visualization_signature(set_config, mesh_unit="mm")
            signatures.append(signature)
            global_row = [float(set_id), 0.0, 0.0, 0.0, 0.0, float(set_id * 10)]
            local_row = [float(set_id), 0.0, 0.0, 0.0, 0.0, float(set_id)]
            global_rows.append(global_row)
            local_rows.append(local_row)
            set_results.append(
                {
                    "result_set_id": set_id,
                    "result_value": float(set_id),
                    "result_unit": "s",
                    "reference_frame": frame,
                    "moment_reference_xyz": [float(set_id), 0.0, 0.0],
                    "resultant_global_origin": global_row,
                    "resultant_reference_global": local_row,
                    "resultant_local": local_row,
                    "scope": {"cut_element_count": set_id},
                    "section_geometry": {},
                    "deformation": {"geometry_state": "deformed", "result_set_id": set_id},
                    "nodal_parity": {"available": False},
                    "visualization_signature": signature,
                    "timings": {"total_seconds": 0.01},
                    "warnings": [],
                }
            )
        return {
            "static_set_results": set_results,
            "times": [float(set_id) for set_id in selected_ids],
            "result_set_ids": selected_ids,
            "resultants_global_origin": global_rows,
            "resultants_global": global_rows,
            "resultants_reference_global": local_rows,
            "resultants_local": local_rows,
            "resolved_reference_frames": frames,
            "moment_reference_xyz_by_set": [
                [float(set_id), 0.0, 0.0] for set_id in selected_ids
            ],
            "signatures": signatures,
            "result_units": {"force": "N", "moment": "N mm"},
            "mesh_unit": "mm",
            "raw_element_count": 8,
            "element_count": 8,
            "surface_node_count": 16,
            "section_geometry": {},
            "deformation": set_results[-1]["deformation"],
            "elapsed_seconds": 0.03,
        }

    monkeypatch.setattr(extraction, "static_force_moment_series", fake_series)
    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            analysis_mode="static",
            static_set_scope="range",
            result_set_range_start=2,
            result_set_range_end=8,
            result_set_range_stride=3,
            modal_rst=str(rst),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
        ),
        capture_visualization_vectors=True,
    )

    assert calls == [[2, 5, 8]]
    assert summary["result_set_ids"] == [2, 5, 8]
    assert summary["selected_result_set"] is None
    assert summary["time_point_count"] == 3
    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert [row[0] for row in rows[1:]] == ["2", "5", "8"]
    assert [row[1] for row in rows[1:]] == ["2", "5", "8"]
    persisted_text = Path(summary["summary_json"]).read_text(encoding="utf-8")
    assert "selected_node_coordinates" not in persisted_text
    result_data = summary["_visualization_result_data"]
    assert "modal_coordinates" not in result_data
    assert visualization.result_component_history(result_data, "local")["force"][
        "components"
    ]["x"] == [2.0, 5.0, 8.0]


def test_static_extraction_publishes_mechanical_equivalent_moment_and_raw_dpf_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst placeholder")
    out_csv = tmp_path / "static_resultants.csv"
    dpf_io.clear_modal_rst_metadata_cache()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        dpf_io,
        "_read_modal_rst_metadata_uncached",
        lambda signature, log=None: _fake_metadata(signature, modal_set_count=2),
    )
    monkeypatch.setattr(
        extraction,
        "parse_mcf",
        lambda _path: pytest.fail("Static extraction must not read an MCF file."),
    )

    def fake_series(
        config: core.SectionConfig,
        _axes: core.Matrix3,
        selected_result_sets: list[dict[str, Any]],
        _log: core.LogFn = None,
        *,
        capture_nodal_vectors: bool = False,
    ) -> dict[str, Any]:
        captured.update(
            result_set_id=config.result_set_id,
            selected_ids=[item["id"] for item in selected_result_sets],
            capture_nodal_vectors=capture_nodal_vectors,
        )
        signature = core.result_visualization_signature(config, mesh_unit="mm")
        parity = extraction.nodal_resultant_parity(
            [0.0, 10.0, 0.0, 0.0, 0.0, 30.0],
            [0.0, 10.0, 0.0, 0.0, 0.0, 15.0],
        )
        frame = core.fixed_reference_frame(
            [2.0, 0.0, 0.0],
            config.coordinate_system_axes,
            result_set_id=2,
            result_value=2.0,
            result_unit="s",
        ).__dict__
        set_result = {
            "result_set_id": 2,
            "result_value": 2.0,
            "result_unit": "s",
            "reference_frame": frame,
            "moment_reference_xyz": [2.0, 0.0, 0.0],
            "resultant_global_origin": [0.0, 10.0, 0.0, 0.0, 0.0, 35.0],
            "resultant_reference_global": [0.0, 10.0, 0.0, 0.0, 0.0, 15.0],
            "resultant_local": [0.0, 10.0, 0.0, 0.0, 0.0, 15.0],
            "raw_dpf_resultant_global_origin": [0.0, 10.0, 0.0, 0.0, 0.0, 50.0],
            "raw_dpf_resultant_reference_global": [0.0, 10.0, 0.0, 0.0, 0.0, 30.0],
            "raw_dpf_resultant_local": [0.0, 10.0, 0.0, 0.0, 0.0, 30.0],
            "scope": {"cut_element_count": 1, "selected_node_count": 1},
            "section_geometry": {},
            "deformation": {"geometry_state": "deformed", "result_set_id": 2},
            "nodal_parity": parity,
            "visualization_signature": signature,
            "timings": {"total_seconds": 0.01},
            "warnings": ["audit mismatch"],
        }
        return {
            "static_set_results": [set_result],
            "times": [2.0],
            "result_set_ids": [2],
            "resultants_global_origin": [set_result["resultant_global_origin"]],
            "resultants_global": [set_result["resultant_global_origin"]],
            "resultants_reference_global": [set_result["resultant_reference_global"]],
            "resultants_local": [set_result["resultant_local"]],
            "raw_dpf_resultants_global_origin": [
                set_result["raw_dpf_resultant_global_origin"]
            ],
            "raw_dpf_resultants_reference_global": [
                set_result["raw_dpf_resultant_reference_global"]
            ],
            "raw_dpf_resultants_local": [set_result["raw_dpf_resultant_local"]],
            "resolved_reference_frames": [frame],
            "moment_reference_xyz_by_set": [[2.0, 0.0, 0.0]],
            "signatures": [signature],
            "result_units": {"force": "N", "moment": "N mm"},
            "mesh_unit": "mm",
            "raw_element_count": 3,
            "element_count": 1,
            "surface_node_count": 1,
            "section_geometry": {},
            "deformation": set_result["deformation"],
            "elapsed_seconds": 0.01,
            "_visualization_detail": {
                "selected_node_coordinates": {101: [3.0, 0.0, 0.0]},
                "selected_node_centroid": [3.0, 0.0, 0.0],
                "nodal_force_modal_coefficients": {101: [[0.0, 10.0, 0.0]]},
                "nodal_moment_modal_coefficients": {101: [[0.0, 0.0, 5.0]]},
                "nodal_moment_output_available": True,
                "section_geometry": {},
            },
        }

    monkeypatch.setattr(extraction, "static_force_moment_series", fake_series)
    messages: list[str] = []
    summary = extraction.extract_section_resultants(
        core.SectionConfig(
            analysis_mode="static",
            result_set_id=2,
            modal_rst=str(rst),
            out_csv=str(out_csv),
            element_named_selection="CUT_SMALL",
            coordinate_system_origin=[2.0, 0.0, 0.0],
            coordinate_system_axes={
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        ),
        log=messages.append,
        capture_visualization_vectors=True,
    )

    assert captured == {
        "result_set_id": 2,
        "selected_ids": [2],
        "capture_nodal_vectors": True,
    }
    assert summary["analysis_mode"] == "static"
    assert summary["selected_result_set"]["id"] == 2
    assert summary["selected_result_set"]["value"] == 2.0
    assert summary["time_point_count"] == 1
    assert summary["nodal_parity"]["force_matches"] is True
    assert summary["nodal_parity"]["moment_matches"] is False
    assert summary["nodal_parity"]["primary_result_source"] == (
        "mechanical_equivalent_nodal_reconstruction"
    )
    assert summary["nodal_parity"]["raw_dpf_resultant_reference_global"] == [
        0.0,
        10.0,
        0.0,
        0.0,
        0.0,
        30.0,
    ]
    assert summary["nodal_parity"][
        "mechanical_equivalent_resultant_reference_global"
    ] == [
        0.0,
        10.0,
        0.0,
        0.0,
        0.0,
        15.0,
    ]
    assert summary["nodal_parity"][
        "delta_mechanical_equivalent_minus_raw_dpf"
    ][3:6] == [
        0.0,
        0.0,
        -15.0,
    ]
    with out_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == 2
    assert rows[1][0] == "2"
    assert rows[1][1] == "2"
    assert rows[1][11:14] == ["0", "0", "15"]

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert persisted["analysis_mode"] == "static"
    assert persisted["selected_result_set"]["unit"] == "s"
    assert persisted["nodal_parity"]["moment_matches"] is False

    result_data = summary["_visualization_result_data"]
    assert "modal_coordinates" not in result_data
    nodal_payload = visualization.build_nodal_force_time_export_payload(result_data, 0)
    assert nodal_payload is not None
    assert nodal_payload["rows"][0]["orbital_moment_global"] == [0.0, 0.0, 10.0]
    assert nodal_payload["rows"][0]["explicit_couple_global"] == [0.0, 0.0, 5.0]
    assert nodal_payload["rows"][0]["combined_moment_global"] == [0.0, 0.0, 15.0]
    nodal_csv = tmp_path / "static_nodal.csv"
    visualization.write_nodal_force_time_csv(str(nodal_csv), nodal_payload)
    with nodal_csv.open(newline="", encoding="utf-8") as stream:
        nodal_rows = list(csv.reader(stream))
    assert "mz_combined_global [N mm]" in nodal_rows[0]
    assert "mechanical_equivalent_minus_raw_dpf_m_delta_z [N mm]" in nodal_rows[0]

    excel_payload = visualization.build_nodal_force_time_excel_payload(result_data, 0)
    assert excel_payload is not None
    assert excel_payload["rows"][0]["orbital_moment_global"] == [0.0, 0.0, 10.0]
    assert excel_payload["rows"][0]["explicit_couple_global"] == [0.0, 0.0, 5.0]
    assert excel_payload["rows"][0]["combined_moment_global"] == [0.0, 0.0, 15.0]
    openpyxl = pytest.importorskip("openpyxl")
    static_xlsx = tmp_path / "static_nodal.xlsx"
    visualization.write_nodal_force_time_excel(str(static_xlsx), excel_payload)
    workbook = openpyxl.load_workbook(static_xlsx, data_only=False)
    assert workbook["Nodal Forces"]["Y1"].value == "mx_explicit_couple_global [N mm]"
    assert workbook["Nodal Forces"]["AB1"].value == (
        "mx_combined_about_reference_global [N mm]"
    )
    assert workbook["Nodal Forces"]["AB2"].value == "=Q2+Y2"
    assert workbook["Summary"]["C27"].value == "=SUM('Nodal Forces'!AE2:AE2)"
    assert workbook["Summary"]["D29"].value == 35.0
    assert workbook["Summary"]["E29"].value == 15.0
    assert workbook["Summary"]["F29"].value == 15.0
    assert workbook["Summary"]["H29"].value == 50.0
    assert workbook["Summary"]["I29"].value == 30.0
    assert workbook["Summary"]["J29"].value == 30.0
    assert workbook["Summary"]["K29"].value == "=E29-I29"

    visualization_payload, _old_result_data = _result_overlay_fixture()
    visualization_payload["result_signature"] = result_data["signature"]
    moment_overlay = visualization.build_result_overlay_payload(
        visualization_payload, result_data, "moment", 0
    )
    force_overlay = visualization.build_result_overlay_payload(
        visualization_payload, result_data, "force", 0
    )
    assert moment_overlay is not None
    assert moment_overlay["total_vector"]["vector"] == [0.0, 0.0, 15.0]
    assert moment_overlay["label"] == (
        "Moment Reaction (Mechanical-equivalent section resultant)"
    )
    assert force_overlay is not None
    assert force_overlay["nodal_vectors"][0]["vector"] == [0.0, 10.0, 0.0]
    assert visualization.result_component_history(result_data, "local")["moment"][
        "components"
    ]["z"] == [15.0]


def test_static_animation_interpolation_uses_physical_time_and_exact_sets() -> None:
    selected_sets = [
        {"id": 1, "value": 0.0, "unit": "s"},
        {"id": 2, "value": 2.0, "unit": "s"},
        {"id": 3, "value": 10.0, "unit": "s"},
    ]

    smooth = core.static_animation_interpolation(
        selected_sets, 0.5, mode="smooth"
    )
    exact = core.static_animation_interpolation(selected_sets, 0.5, mode="exact")

    assert (smooth.lower_index, smooth.upper_index) == (1, 2)
    assert smooth.axis_value == pytest.approx(5.0)
    assert smooth.fraction == pytest.approx(3.0 / 8.0)
    assert smooth.exact is False
    assert smooth.warning is None
    assert (exact.lower_index, exact.upper_index) == (1, 1)
    assert exact.axis_value == pytest.approx(2.0)
    assert exact.exact is True


def test_static_animation_interpolation_warns_and_falls_back_to_set_order() -> None:
    selected_sets = [
        {"id": 1, "value": 1.0},
        {"id": 2, "value": 1.0},
        {"id": 3, "value": 0.5},
    ]

    interpolation = core.static_animation_interpolation(
        selected_sets, 0.75, mode="smooth"
    )

    assert (interpolation.lower_index, interpolation.upper_index) == (1, 2)
    assert interpolation.fraction == pytest.approx(0.5)
    assert interpolation.axis_value == pytest.approx(1.5)
    assert "ordered set positions" in str(interpolation.warning)


def test_static_animation_frame_uses_reference_plus_scaled_interpolated_displacement() -> None:
    np = pytest.importorskip("numpy")
    session = _static_animation_test_session()
    first = np.zeros((4, 3), dtype=np.float64)
    second = np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 3.0],
            [-1.0, -2.0, -3.0],
        ],
        dtype=np.float64,
    )
    try:
        session.put_displacements(0, first)
        session.put_displacements(1, second)

        start = visualization.static_animation_frame_state(
            session, 0.0, deformation_scale=2.0
        )
        midpoint = visualization.static_animation_frame_state(
            session, 0.5, deformation_scale=2.0
        )
        end = visualization.static_animation_frame_state(
            session, 1.0, deformation_scale=2.0
        )
        exact = visualization.static_animation_frame_state(
            session, 0.6, mode="exact", deformation_scale=1.0
        )

        assert start["points"] == pytest.approx(session.topology.reference_points)
        assert midpoint["points"] == pytest.approx(
            session.topology.reference_points + second
        )
        assert end["points"] == pytest.approx(
            session.topology.reference_points + 2.0 * second
        )
        assert exact["points"] == pytest.approx(
            session.topology.reference_points + second
        )
        assert exact["interpolation"].lower_index == 1
    finally:
        session.close()


def test_static_animation_follow_frame_remains_right_handed_during_motion() -> None:
    np = pytest.importorskip("numpy")
    session = _static_animation_test_session(follow_geometry=True)
    reference = session.topology.displacement_reference_points
    rotation = np.asarray(
        [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    translation = np.asarray([3.0, -2.0, 1.0], dtype=np.float64)
    final_points = reference @ rotation.T + translation
    try:
        session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
        session.put_displacements(1, final_points - reference)

        midpoint = visualization.static_animation_frame_state(session, 0.5)
        endpoint = visualization.static_animation_frame_state(session, 1.0)

        assert midpoint["frame"].final_determinant == pytest.approx(1.0)
        assert endpoint["frame"].final_determinant == pytest.approx(1.0)
        assert endpoint["frame"].rotation_matrix == pytest.approx(rotation)
        assert endpoint["frame"].translation == pytest.approx(translation)
        resolved_axes = endpoint["frame"].resolved_axes
        assert np.cross(resolved_axes["x"], resolved_axes["y"]) == pytest.approx(
            resolved_axes["z"]
        )
    finally:
        session.close()


def _static_animation_result_history_data(
    session: core.StaticAnimationSession,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    signatures = []
    for record in session.records:
        set_config = core.config_from_mapping(session.topology.mesh_config)
        set_config.result_set_id = record.result_set_id
        signatures.append(
            core.result_visualization_signature(set_config, mesh_unit="mm")
        )
    return signatures, {
        "analysis_mode": "static",
        "static_set_scope": "range",
        "signature": signatures[-1],
        "signatures": signatures,
        "times": [0.0, 10.0],
        "result_set_ids": [1, 2],
        "selected_result_sets": [
            {"id": 1, "value": 0.0, "unit": "s", "label": "Set 1"},
            {"id": 2, "value": 10.0, "unit": "s", "label": "Set 2"},
        ],
        "result_units": {"force": "N", "moment": "N mm"},
        "resultants_global": [
            [10.0, 0.0, 0.0, 0.0, 100.0, 0.0],
            [0.0, 20.0, 0.0, 0.0, 0.0, 200.0],
        ],
        "resultants_local": [
            [1.0, 2.0, 2.0, 3.0, 4.0, 0.0],
            [4.0, 0.0, 3.0, 0.0, 12.0, 5.0],
        ],
    }


@pytest.mark.parametrize("frame", ["global", "local"])
def test_static_animation_history_uses_nearest_exact_solved_set_evidence(
    frame: str,
) -> None:
    np = pytest.importorskip("numpy")
    session = _static_animation_test_session(follow_geometry=True)
    reference = session.topology.displacement_reference_points
    rotation = np.asarray(
        [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    final_points = reference @ rotation.T + np.asarray([3.0, -2.0, 1.0])
    signatures, result_data = _static_animation_result_history_data(session)
    try:
        session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
        session.put_displacements(1, final_points - reference)

        payload = visualization.build_static_animation_render_frame(
            session,
            0.75,
            mode="smooth",
        )

        assert payload["animation"]["lower_result_set_id"] == 1
        assert payload["animation"]["upper_result_set_id"] == 2
        assert payload["animation"]["evidence_time_index"] == 1
        assert payload["animation"]["evidence_result_set_id"] == 2
        assert payload["animation"]["evidence_result_signature"] == signatures[1]
        assert payload["result_signature"] != signatures[1]
        history = visualization.build_result_history_plot_payload(
            payload,
            result_data,
            frame,
            selected_time_index=1,
            moment_display_unit="N m",
        )
        assert history is not None
        assert history["frame"] == frame
        assert history["moment"]["unit"] == "N m"
        assert history["moment"]["components"]["total"][-1] == pytest.approx(
            0.2 if frame == "global" else 0.013
        )
        assert (
            visualization.build_result_history_plot_payload(
                payload,
                result_data,
                frame,
                selected_time_index=0,
            )
            is None
        )
    finally:
        session.close()


def test_static_animation_history_ignores_non_unit_visual_deformation_scale() -> None:
    np = pytest.importorskip("numpy")
    session = _static_animation_test_session(follow_geometry=True)
    reference = session.topology.displacement_reference_points
    translation = np.asarray([3.0, -2.0, 1.0], dtype=np.float64)
    signatures, result_data = _static_animation_result_history_data(session)
    try:
        session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
        session.put_displacements(
            1,
            np.broadcast_to(translation, reference.shape).copy(),
        )

        payload = visualization.build_static_animation_render_frame(
            session,
            1.0,
            mode="exact",
            deformation_scale=10.0,
        )

        assert payload["animation"]["evidence_time_index"] == 1
        assert payload["animation"]["evidence_result_signature"] == signatures[1]
        assert payload["result_signature"] != signatures[1]
        assert (
            visualization.build_result_history_plot_payload(
                payload,
                result_data,
                "global",
                selected_time_index=1,
            )
            is not None
        )
        assert (
            visualization.build_result_history_plot_payload(
                payload,
                result_data,
                "local",
                selected_time_index=1,
                moment_display_unit="N m",
            )
            is not None
        )
    finally:
        session.close()


def test_static_animation_session_bounds_decoded_frames_and_cleans_memmap() -> None:
    np = pytest.importorskip("numpy")
    ram_session = _static_animation_test_session((0.0, 1.0, 2.0, 3.0))
    try:
        assert ram_session.storage_kind == "ram"
        for index in range(4):
            ram_session.put_displacements(
                index, np.full((4, 3), float(index), dtype=np.float64)
            )
        for index in range(4):
            ram_session.displacement_frame(index)
        assert ram_session.decoded_frame_count == 3
    finally:
        ram_session.close()

    mapped_session = _static_animation_test_session(
        (0.0, 1.0), ram_limit_bytes=1
    )
    mapped_path = Path(str(mapped_session.memmap_path))
    assert mapped_session.storage_kind == "memmap"
    assert mapped_path.is_file()
    mapped_session.close()
    assert mapped_session.closed is True
    assert not mapped_path.exists()


def test_static_animation_load_order_and_batch_size_are_bounded() -> None:
    assert core.static_animation_load_order(
        5, priority_index=2, direction=1
    ) == [2, 3, 4, 1, 0]
    assert core.static_animation_load_order(
        5, priority_index=2, direction=-1
    ) == [2, 1, 0, 3, 4]
    assert core.static_animation_batch_size(1) == 16
    node_count_over_64_mib_per_set = (
        core.STATIC_ANIMATION_MAX_BATCH_BYTES // (3 * 8) + 1
    )
    assert core.static_animation_batch_size(node_count_over_64_mib_per_set) == 1


def test_static_animation_vectorized_cut_and_node_membership_changes() -> None:
    np = pytest.importorskip("numpy")
    _topology, config = _static_animation_test_topology()
    reference = np.asarray(
        [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        dtype=np.float64,
    )
    topology = core.StaticAnimationTopology(
        node_ids=(1, 2, 3, 4),
        displacement_node_ids=(1, 2, 3, 4),
        reference_points=reference,
        displacement_reference_points=reference.copy(),
        cells=np.asarray([2, 0, 1, 2, 2, 3], dtype=np.int64),
        celltypes=np.asarray([3, 3], dtype=np.uint8),
        element_ids=(10, 20),
        element_node_ids={10: (1, 2), 20: (3, 4)},
        connectivity_point_indices=np.asarray([0, 1, 2, 3], dtype=np.int64),
        element_offsets=np.asarray([0, 2], dtype=np.int64),
        mesh_displacement_indices=np.asarray([0, 1, 2, 3], dtype=np.int64),
        tracking_node_ids=tuple(),
        tracking_displacement_indices=np.asarray([], dtype=np.int64),
        element_name="CUT_SMALL",
        available_named_selections=("CUT_SMALL",),
        mesh_unit="mm",
        mesh_config=dict(config.__dict__),
        origin_unit_conversion=None,
        attachment={},
    )
    moved = reference.copy()
    moved[0, 0] = 1.0
    moved[1, 0] = 2.0
    moved[2, 0] = -2.0

    initial = visualization.classify_static_animation_section(
        topology, reference, [0.0, 0.0, 0.0], core.validate_axes(config.coordinate_system_axes)
    )
    deformed = visualization.classify_static_animation_section(
        topology, moved, [0.0, 0.0, 0.0], core.validate_axes(config.coordinate_system_axes)
    )
    fixed_membership = visualization.classify_static_animation_section(
        topology,
        moved,
        [0.0, 0.0, 0.0],
        core.validate_axes(config.coordinate_system_axes),
        membership_points=reference,
    )

    assert initial["cut_element_ids"] == [10]
    assert initial["selected_node_ids"] == [2]
    assert deformed["cut_element_ids"] == [20]
    assert deformed["selected_node_ids"] == [4]
    assert fixed_membership["cut_element_ids"] == [10]
    assert fixed_membership["selected_node_ids"] == [2]
    assert fixed_membership["selected_node_coordinates"]["2"] == [2.0, 0.0, 0.0]
    assert fixed_membership["scoping_geometry_state"] == "reference"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("force", [5.0, 10.0, 15.0]), ("moment", [20.0, 25.0, 30.0])],
)
def test_static_animation_interpolates_primary_totals_only(
    mode: str,
    expected: list[float],
) -> None:
    payload = {
        "mesh": {"points": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]},
        "plane": {"corners": [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]},
        "moment_reference_xyz": [0.0, 0.0, 0.0],
    }
    result_data = {
        "analysis_mode": "static",
        "selected_result_sets": [{"id": 1}, {"id": 2}],
        "resultants_global_origin": [
            [0.0, 0.0, 0.0, 10.0, 20.0, 30.0],
            [10.0, 20.0, 30.0, 30.0, 30.0, 30.0],
        ],
        "resultants_reference_global": [
            [0.0, 0.0, 0.0, 10.0, 20.0, 30.0],
            [10.0, 20.0, 30.0, 30.0, 30.0, 30.0],
        ],
        "moment_reference_xyz_by_set": [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        "result_units": {"force": "N", "moment": "N mm"},
    }
    interpolation = core.StaticAnimationInterpolation(
        0, 1, 0.5, 0.5, 0.5, False
    )

    overlay = visualization.build_static_animation_total_overlay(
        payload, result_data, mode, interpolation
    )

    assert overlay is not None
    assert overlay["total_vector"]["vector"] == pytest.approx(expected)
    assert overlay["total_vector"]["origin"] == pytest.approx([1.0, 0.0, 0.0])
    assert overlay["nodal_vectors"] == []
    assert overlay["visual_interpolation"] is True
    assert "Mechanical-equivalent section resultant" in overlay["label"]
    assert "visual interpolation" in overlay["label"]


def test_static_extraction_reuses_private_animation_session_without_serializing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rst = tmp_path / "static.rst"
    rst.write_bytes(b"rst placeholder")
    out_csv = tmp_path / "static_animation_reuse.csv"
    config = core.SectionConfig(
        analysis_mode="static",
        static_set_scope="range",
        result_set_range_start=1,
        result_set_range_end=2,
        modal_rst=str(rst),
        out_csv=str(out_csv),
        element_named_selection="CUT_SMALL",
    )
    selected_sets = [
        {"id": 1, "value": 1.0, "unit": "s", "label": "Set 1"},
        {"id": 2, "value": 2.0, "unit": "s", "label": "Set 2"},
    ]
    private_session = object()
    frames = [
        core.fixed_reference_frame(
            [0.0, 0.0, 0.0],
            config.coordinate_system_axes,
            result_set_id=item["id"],
            result_value=item["value"],
            result_unit="s",
        ).__dict__
        for item in selected_sets
    ]
    signatures = [
        core.result_visualization_signature(
            core.config_from_mapping({**config.__dict__, "result_set_id": item["id"]}),
            mesh_unit="mm",
        )
        for item in selected_sets
    ]
    set_results = [
        {
            "result_set_id": item["id"],
            "result_value": item["value"],
            "result_unit": "s",
            "reference_frame": frame,
            "moment_reference_xyz": [0.0, 0.0, 0.0],
            "resultant_global_origin": [float(item["id"]), 0.0, 0.0, 0.0, 0.0, 0.0],
            "resultant_reference_global": [float(item["id"]), 0.0, 0.0, 0.0, 0.0, 0.0],
            "resultant_local": [float(item["id"]), 0.0, 0.0, 0.0, 0.0, 0.0],
            "scope": {"cut_element_count": 1, "selected_node_count": 1},
            "section_geometry": {},
            "deformation": {"geometry_state": "deformed", "result_set_id": item["id"]},
            "nodal_parity": {"available": False},
            "visualization_signature": signature,
            "timings": {"total_seconds": 0.01},
            "warnings": [],
        }
        for item, frame, signature in zip(selected_sets, frames, signatures)
    ]
    rows = [item["resultant_global_origin"] for item in set_results]
    monkeypatch.setattr(
        extraction,
        "static_force_moment_series",
        lambda *_args, **_kwargs: {
            "static_set_results": set_results,
            "times": [1.0, 2.0],
            "result_set_ids": [1, 2],
            "resultants_global_origin": rows,
            "resultants_global": rows,
            "resultants_reference_global": rows,
            "resultants_local": rows,
            "resolved_reference_frames": frames,
            "moment_reference_xyz_by_set": [[0.0, 0.0, 0.0]] * 2,
            "signatures": signatures,
            "result_units": {"force": "N", "moment": "N mm"},
            "mesh_unit": "mm",
            "raw_element_count": 1,
            "element_count": 1,
            "surface_node_count": 1,
            "section_geometry": {},
            "deformation": set_results[-1]["deformation"],
            "elapsed_seconds": 0.02,
            "_animation_session": private_session,
        },
    )
    metadata = _fake_metadata(
        dpf_io.modal_rst_signature(str(rst)), modal_set_count=2
    )
    metadata.result_sets = selected_sets
    summary_path = tmp_path / "static_animation_reuse.summary.json"

    summary = extraction._extract_static_section_resultants(
        config,
        core.validate_axes(config.coordinate_system_axes),
        metadata,
        metadata_elapsed=0.0,
        total_start=perf_counter(),
        summary_path=str(summary_path),
        log=None,
        capture_visualization_vectors=True,
    )

    assert summary["_animation_session"] is private_session
    persisted = summary_path.read_text(encoding="utf-8")
    assert "_animation_session" not in persisted


def test_animation_control_icon_assets_are_pinned_and_complete() -> None:
    expected = {
        "previous": "player-track-prev.svg",
        "play": "player-play.svg",
        "pause": "player-pause.svg",
        "next": "player-track-next.svg",
        "stop": "player-stop.svg",
        "buffering": "loader-2.svg",
    }
    assert gui.ANIMATION_ICON_FILENAMES == expected
    assert gui.ANIMATION_ICON_NOTICE_FILENAMES == (
        "TABLER_SOURCES.txt",
        "TABLER_LICENSE.txt",
    )

    source_notice = (
        gui.animation_icon_asset_root() / "TABLER_SOURCES.txt"
    ).read_text(encoding="utf-8")
    license_notice = (
        gui.animation_icon_asset_root() / "TABLER_LICENSE.txt"
    ).read_text(encoding="utf-8")
    assert "Tabler Icons v3.46.0" in source_notice
    assert "raw.githubusercontent.com/tabler/tabler-icons/v3.46.0" in source_notice
    assert "Permission is hereby granted" in license_notice
    for semantic_name, filename in expected.items():
        asset_path = gui.animation_icon_asset_path(semantic_name)
        svg = asset_path.read_text(encoding="utf-8")
        assert asset_path.name == filename
        assert "<svg" in svg
        assert "currentColor" in svg
        assert filename in source_notice


def test_run_gui_static_animation_controls_and_manual_selection(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    np = pytest.importorskip("numpy")
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)

    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window
    session = _static_animation_test_session()
    session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
    session.put_displacements(1, np.ones((4, 3), dtype=np.float64))
    try:
        window._refresh_result_set_options(
            [
                {"id": 1, "value": 0.0, "unit": "s", "label": "Set 1"},
                {"id": 2, "value": 10.0, "unit": "s", "label": "Set 2"},
            ]
        )
        qapp.processEvents()
        assert window.animation_group.isHidden() is True

        window._set_combo_value(window.static_set_scope_combo, "range")
        window.result_set_range_start_spin.setValue(1)
        window.result_set_range_end_spin.setValue(1)
        window.on_static_set_scope_changed()
        assert window.animation_group.isHidden() is False
        assert window.animation_group.body_widget.isEnabled() is False

        window.result_set_range_end_spin.setValue(2)
        window._refresh_animation_availability()
        assert window.animation_group.body_widget.isEnabled() is True
        assert window.animation_mode_combo.currentData() == "smooth"
        assert window.animation_cycle_combo.currentData() == "loop"
        assert window.animation_speed_combo.currentData() == pytest.approx(1.0)
        assert window.animation_deformation_spin.value() == pytest.approx(1.0)
        animation_buttons = (
            window.animation_previous_button,
            window.animation_play_button,
            window.animation_next_button,
            window.animation_stop_button,
        )
        assert all(button.text() == "" for button in animation_buttons)
        assert all(not button.icon().isNull() for button in animation_buttons)
        for button in animation_buttons:
            icon_image = button.icon().pixmap(button.iconSize()).toImage()
            assert any(
                icon_image.pixelColor(x, y).alpha() > 0
                for x in range(icon_image.width())
                for y in range(icon_image.height())
            )
        assert all(button.width() == 34 for button in animation_buttons)
        assert all(button.height() == 32 for button in animation_buttons)
        assert window.animation_previous_button.accessibleName() == (
            "Previous solved frame"
        )
        assert window.animation_play_button.accessibleName() == "Play animation"
        assert window.animation_next_button.accessibleName() == "Next solved frame"
        assert window.animation_stop_button.accessibleName() == "Stop animation"
        assert window.animation_play_button.property("animationState") == "play"
        window._set_animation_play_control_state("pause")
        assert window.animation_play_button.text() == ""
        assert window.animation_play_button.accessibleName() == "Pause animation"
        assert window.animation_play_button.property("animationState") == "pause"
        window._set_animation_play_control_state("buffering")
        assert window.animation_play_button.accessibleName() == (
            "Buffering animation frames"
        )
        assert window.animation_play_button.property("animationState") == "buffering"
        window._set_animation_play_control_state("play")
        assert "visually interpolates" in window.animation_mode_combo.toolTip()
        assert "load in the background" in window.animation_play_button.toolTip()
        assert "first exact solved frame" in window.animation_stop_button.toolTip()
        assert "previous exact solved" in window.animation_previous_button.toolTip()
        assert "next exact solved" in window.animation_next_button.toolTip()
        assert "reverses direction" in window.animation_cycle_combo.toolTip()
        assert "Preview playback rate only" in window.animation_speed_combo.toolTip()

        preview_text = window._animation_frame_text(
            {
                "animation": {
                    "lower_result_set_id": 1,
                    "upper_result_set_id": 2,
                    "fraction": 0.5,
                    "exact": False,
                    "deformation_scale": 2.0,
                }
            }
        )
        assert "visual interpolation" in preview_text
        assert "visual-only deformation" in preview_text

        window._adopt_animation_session(session)
        rendered_indices: list[int] = []
        monkeypatch.setattr(
            window,
            "_render_static_animation_progress",
            lambda **_kwargs: rendered_indices.append(window._animation_nearest_index()) or True,
        )
        window._animation_playing = True
        window._animation_play_requested = True
        window.on_visualization_time_changed(1)
        assert window._animation_playing is False
        assert window._animation_play_requested is False
        assert window._animation_progress == pytest.approx(1.0)
        assert rendered_indices[-1] == 1

        window._set_combo_value(window.static_set_scope_combo, "all")
        window.on_static_set_scope_changed()
        assert window.animation_group.isHidden() is False
        window._set_combo_value(window.analysis_mode_combo, "modal")
        window.on_analysis_mode_changed()
        assert window.animation_group.isHidden() is True
    finally:
        window._animation_session = None
        session.close()
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_static_animation_playback_cycles_and_stop_without_sleeps(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    np = pytest.importorskip("numpy")
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    assert gui.run_gui(core.SectionConfig(analysis_mode="static")) == 0
    window = qapp._mcf_dpf_section_resultants_window
    session = _static_animation_test_session()
    session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
    session.put_displacements(1, np.ones((4, 3), dtype=np.float64))

    class FakeElapsedTimer:
        @staticmethod
        def restart() -> int:
            return 1000

    renders: list[float] = []
    try:
        window._refresh_result_set_options(
            [
                {"id": 1, "value": 0.0, "unit": "s", "label": "Set 1"},
                {"id": 2, "value": 10.0, "unit": "s", "label": "Set 2"},
            ]
        )
        window._set_combo_value(window.static_set_scope_combo, "all")
        window.on_static_set_scope_changed()
        window._adopt_animation_session(session)
        window.animation_elapsed_timer = FakeElapsedTimer()
        monkeypatch.setattr(
            window,
            "_render_static_animation_progress",
            lambda **_kwargs: renders.append(window._animation_progress) or True,
        )

        window._animation_playing = True
        window._animation_play_requested = True
        window._animation_progress = 0.9
        window._set_combo_value(window.animation_cycle_combo, "loop")
        window.advance_static_animation()
        assert window._animation_progress == pytest.approx(0.15)

        window._animation_playing = True
        window._animation_play_requested = True
        window._animation_progress = 0.9
        window._animation_direction = 1
        window._set_combo_value(window.animation_cycle_combo, "ping-pong")
        window.advance_static_animation()
        assert window._animation_progress == pytest.approx(0.85)
        assert window._animation_direction == -1

        window._animation_playing = True
        window._animation_play_requested = True
        window._animation_progress = 0.9
        window._animation_direction = 1
        window._set_combo_value(window.animation_cycle_combo, "once")
        window.advance_static_animation()
        assert window._animation_progress == pytest.approx(1.0)
        assert window._animation_playing is False

        window._animation_progress = 0.75
        window._animation_direction = -1

        class FakeWorker:
            cancelled = 0

            @staticmethod
            def isRunning() -> bool:  # noqa: N802
                return True

            def cancel(self) -> None:
                self.cancelled += 1

        worker = FakeWorker()
        window.animation_worker = worker
        window.stop_static_animation()
        assert window._animation_progress == pytest.approx(0.0)
        assert window._animation_direction == 1
        assert window.animation_play_button.text() == ""
        assert window.animation_play_button.property("animationState") == "play"
        assert window.animation_play_button.accessibleName() == "Play animation"
        assert not window.animation_play_button.icon().isNull()
        assert worker.cancelled == 1
        window.animation_worker = None

        stale_session = _static_animation_test_session()
        window._animation_generation = 7
        window._on_animation_loader_completed(6, stale_session)
        assert stale_session.closed is True
        assert renders
    finally:
        window._animation_session = None
        session.close()
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_static_animation_renderer_updates_in_place_with_one_render(
    monkeypatch: pytest.MonkeyPatch,
    qapp: Any,  # noqa: ANN401
) -> None:
    pyvista = pytest.importorskip("pyvista")
    np = pytest.importorskip("numpy")
    _qt_core, _qt_gui, qt_widgets = gui.import_qt()
    monkeypatch.setattr(qt_widgets.QApplication, "exec", lambda self: 0)
    assert gui.run_gui(core.SectionConfig()) == 0
    window = qapp._mcf_dpf_section_resultants_window
    widget = window.visualization_widget
    session = _static_animation_test_session()
    session.put_displacements(0, np.zeros((4, 3), dtype=np.float64))
    session.put_displacements(1, np.ones((4, 3), dtype=np.float64))

    class FakeMapper:
        def __init__(self, dataset: Any) -> None:
            self.dataset = dataset

        def SetInputData(self, dataset: Any) -> None:  # noqa: N802
            self.dataset = dataset

        def Modified(self) -> None:  # noqa: N802
            return None

    class FakeProperty:
        def __init__(self, edges: bool = True) -> None:
            self.edges = edges

        def SetEdgeVisibility(self, visible: bool) -> None:  # noqa: N802
            self.edges = bool(visible)

    class FakeActor:
        def __init__(self, dataset: Any, *, edges: bool = True) -> None:
            self.mapper = FakeMapper(dataset)
            self.property = FakeProperty(edges)
            self.visible = True

        def SetVisibility(self, visible: bool) -> None:  # noqa: N802
            self.visible = bool(visible)

        def GetProperty(self) -> FakeProperty:  # noqa: N802
            return self.property

        def Modified(self) -> None:  # noqa: N802
            return None

    class FakeTextActor:
        def __init__(self, text: str) -> None:
            self.text = text

        def SetInput(self, text: str) -> None:  # noqa: N802
            self.text = text

    class FakePlotter:
        def __init__(self) -> None:
            self.clear_count = 0
            self.render_count = 0
            self.mesh_datasets: list[Any] = []
            self.camera_position = ((4.0, 3.0, 2.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
            self.camera = types.SimpleNamespace(parallel_scale=7.0)

        def clear(self) -> None:
            self.clear_count += 1
            self.mesh_datasets.clear()

        def add_mesh(self, dataset: Any, **kwargs: Any) -> FakeActor:
            self.mesh_datasets.append(dataset)
            return FakeActor(dataset, edges=bool(kwargs.get("show_edges", True)))

        @staticmethod
        def add_points(dataset: Any, **_kwargs: Any) -> FakeActor:
            return FakeActor(dataset)

        @staticmethod
        def add_arrows(
            origins: Any,
            vectors: Any,
            **_kwargs: Any,
        ) -> FakeActor:
            return FakeActor((origins, vectors))

        @staticmethod
        def add_text(text: str, **_kwargs: Any) -> FakeTextActor:
            return FakeTextActor(text)

        @staticmethod
        def add_axes() -> None:
            return None

        @staticmethod
        def reset_camera() -> None:
            return None

        def render(self) -> None:
            self.render_count += 1

    try:
        first = visualization.build_static_animation_render_frame(session, 0.0)
        second = visualization.build_static_animation_render_frame(session, 0.5)
        for payload in (first, second):
            assert payload["mesh"]["points"] is session.topology.reference_points
            assert payload["mesh"]["cells"] is session.topology.cells
            assert payload["mesh"]["celltypes"] is session.topology.celltypes
            assert payload["_animation_topology_identity"] == id(session.topology)
        assert first["mesh"]["points"] is second["mesh"]["points"]
        assert first["mesh"]["cells"] is second["mesh"]["cells"]
        assert first["_animation_points_numpy"] is not second["_animation_points_numpy"]
        first["counts"]["mesh_node_count"] = (
            visualization.VISUALIZATION_LARGE_NODE_COUNT + 1
        )
        second["counts"]["mesh_node_count"] = (
            visualization.VISUALIZATION_LARGE_NODE_COUNT + 1
        )
        plotter = FakePlotter()
        widget._interactor = plotter
        widget._show_ruler = False
        widget._animation_scene = None
        widget._has_rendered_payload = False

        assert widget.render_animation_payload(first, playing=True) is True
        assert plotter.clear_count == 1
        base_actor = widget._animation_scene["base_actor"]
        assert base_actor.GetProperty().edges is False
        camera_before = plotter.camera_position
        renders_before = plotter.render_count

        assert widget.render_animation_payload(second, playing=False) is True
        assert plotter.clear_count == 1
        assert plotter.render_count == renders_before + 1
        assert widget._animation_scene["base_actor"] is base_actor
        assert base_actor.GetProperty().edges is True
        assert plotter.camera_position == camera_before
        assert isinstance(widget._animation_scene["grid"], pyvista.UnstructuredGrid)

        widget._show_ruler = True
        widget._error_label.setText("stale render error")
        widget._set_show_ruler(False)

        assert widget._show_ruler is False
        assert widget._error_label.text() == ""
        assert plotter.clear_count == 2
        assert plotter.mesh_datasets
        assert np.allclose(
            plotter.mesh_datasets[0].points,
            second["_animation_points_numpy"],
        )
        assert widget._animation_scene is None
        assert widget._last_payload is second
        assert plotter.camera_position == camera_before
    finally:
        session.close()
        window.close()
        if getattr(qapp, "_mcf_dpf_section_resultants_window", None) is window:
            delattr(qapp, "_mcf_dpf_section_resultants_window")


def test_static_animation_loader_runs_dpf_work_in_qthread() -> None:
    source = gui.run_gui.__code__
    assert "StaticAnimationLoaderThread" in source.co_consts
    text = Path(gui.__file__).read_text(encoding="utf-8")
    loader_start = text.index("class StaticAnimationLoaderThread")
    loader_end = text.index("\n    class FileRow", loader_start)
    loader_source = text[loader_start:loader_end]
    assert "class StaticAnimationLoaderThread(QtCore.QThread)" in loader_source
    assert "load_static_animation_session(" in loader_source
    assert "cancel_requested=self._cancel_event.is_set" in loader_source
    assert "self.completed.emit(self._generation, session)" in loader_source


def test_static_fixed_construction_surface_real_rst_regression(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dpf.core")
    rst = (
        Path(__file__).parent
        / "ansys_dpf_core"
        / "example_outputs"
        / "static_analysis_1_bolted_joint"
        / "file.rst"
    )
    if not rst.is_file():
        pytest.skip("Committed Static Structural RST fixture is unavailable.")

    try:
        summary = extraction.extract_section_resultants(
            core.SectionConfig(
                analysis_mode="static",
                static_set_scope="single",
                result_set_id=2,
                modal_rst=str(rst),
                out_csv=str(tmp_path / "static_fixed_real.csv"),
                element_named_selection="SELECTION_3",
                coordinate_system_origin=[0.0, 0.0, 50.0],
                coordinate_system_axes={
                    "x": [1.0, 0.0, 0.0],
                    "y": [0.0, 1.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                },
                reference_frame_motion="fixed",
                section_normal_axis="z",
                extraction_side="positive",
            ),
            capture_visualization_vectors=True,
        )
    except core.DpfCompatibilityError as exc:
        pytest.skip(str(exc))

    try:
        force_summary = summary["dpf_force_summation"]
        assert force_summary["element_count"] == 39
        assert force_summary["surface_node_count"] == 80
        assert force_summary["aggregate_result_sources"] == ["dpf_force_summation"]
        assert summary["deformation"]["scoping_geometry_state"] == "reference"
        assert summary["deformation"]["scope_change"]["element_membership_changed"] is False
        assert summary["deformation"]["scope_change"]["node_membership_changed"] is False

        result_data = summary["_visualization_result_data"]
        assert result_data["raw_dpf_resultants_global_origin"][0] == pytest.approx(
            [
                25.262175917625427,
                15.224808037281036,
                -1983.6245503425598,
                -0.7245782569841273,
                -6.60959358939723,
                0.006380507968101093,
            ]
        )
        assert result_data["raw_dpf_resultants_reference_global"][0] == pytest.approx(
            [
                25.262175917625427,
                15.224808037281036,
                -1983.6245503425598,
                0.036662144879924544,
                -7.872702385278501,
                0.006380507968101093,
            ]
        )
        assert result_data["resultants_global_origin"][0] == pytest.approx(
            [
                25.262175917625427,
                15.224808037281036,
                -1983.6245503425598,
                -0.724742903704739,
                -6.609476659959336,
                0.006153787778572686,
            ]
        )
        assert result_data["resultants_reference_global"][0] == pytest.approx(
            [
                25.262175917625427,
                15.224808037281036,
                -1983.6245503425598,
                0.03649749815931286,
                -7.872585455840607,
                0.006153787778572686,
            ]
        )
        reconstructed = visualization.nodal_reconstructed_resultant_rows(result_data)
        assert reconstructed is not None
        reconstructed_reference = reconstructed["global_rows"][0]
        canonical_reference = result_data["resultants_reference_global"][0]
        assert canonical_reference[:3] == pytest.approx(
            result_data["raw_dpf_resultants_reference_global"][0][:3]
        )
        assert canonical_reference[3:6] == pytest.approx(
            reconstructed_reference[3:6]
        )
        assert result_data["resultants_global_origin"][0] == pytest.approx(
            canonical_reference[:3]
            + core.shift_moment_reference(
                canonical_reference[3:6],
                result_data["moment_reference_xyz_by_set"][0],
                [0.0, 0.0, 0.0],
                canonical_reference[:3],
                cross_product_moment_factor=reconstructed["moment_unit_factor"],
            )
        )
        assert result_data["resultants_local"][0] == pytest.approx(
            core.rotate_to_local(
                canonical_reference,
                core.validate_axes(
                    result_data["resolved_reference_frames"][0]["resolved_axes"]
                ),
            )
        )
        assert summary["nodal_parity"]["primary_result_source"] == (
            "mechanical_equivalent_nodal_reconstruction"
        )
    finally:
        animation_session = summary.get("_animation_session")
        if animation_session is not None:
            animation_session.close()


def test_static_extraction_real_rst_smoke(tmp_path: Path) -> None:
    pytest.importorskip("ansys.dpf.core")
    rst = (
        Path(__file__).parent
        / "ansys_dpf_core"
        / "example_outputs"
        / "static_analysis_1_bolted_joint"
        / "file.rst"
    )
    if not rst.is_file():
        pytest.skip("Committed Static Structural RST fixture is unavailable.")

    try:
        summary = extraction.extract_section_resultants(
            core.SectionConfig(
                analysis_mode="static",
                static_set_scope="range",
                result_set_range_start=1,
                result_set_range_end=2,
                result_set_range_stride=1,
                modal_rst=str(rst),
                out_csv=str(tmp_path / "static_real.csv"),
                element_named_selection="SELECTION_3",
                coordinate_system_origin=[0.0, 0.0, 50.0],
                coordinate_system_axes={
                    "x": [1.0, 0.0, 0.0],
                    "y": [0.0, 1.0, 0.0],
                    "z": [0.0, 0.0, 1.0],
                },
                reference_frame_motion="follow-geometry",
                section_normal_axis="z",
                extraction_side="positive",
            ),
            capture_visualization_vectors=True,
        )
    except core.DpfCompatibilityError as exc:
        pytest.skip(str(exc))

    assert summary["analysis_mode"] == "static"
    assert summary["selected_result_set"] is None
    assert summary["result_set_ids"] == [1, 2]
    assert summary["time_point_count"] == 2
    assert summary["geometry_state"] == "deformed"
    assert summary["deformation"]["result_set_id"] == 2
    assert summary["deformation"]["displacement_unit"] == "m"
    assert summary["deformation"]["mesh_unit"] == "m"
    assert summary["deformation"]["max_displacement"] > 0.0
    scope_change = summary["deformation"]["scope_change"]
    assert scope_change["reference_cut_element_count"] == 39
    assert scope_change["deformed_cut_element_count"] == 39
    assert scope_change["element_membership_changed"] is False
    assert scope_change["node_membership_changed"] is True
    assert summary["dpf_force_summation"]["element_count"] == 39
    assert summary["dpf_force_summation"]["surface_node_count"] == 76
    frame = summary["resolved_reference_frame"]
    frames = summary["resolved_reference_frames"]
    assert len(frames) == 2
    assert [item["result_set_id"] for item in frames] == [1, 2]
    assert all(item["final_determinant"] == pytest.approx(1.0) for item in frames)
    assert frames[0]["resolved_origin"] != pytest.approx(frames[1]["resolved_origin"])
    assert frame["motion"] == "follow-geometry"
    assert frame["attachment_source"] == "local_section_cut_neighborhood"
    assert frame["tracking_node_count"] == 160
    assert frame["rank"] == 3
    assert frame["final_determinant"] == pytest.approx(1.0)
    assert frame["normalized_residual"] < 0.01
    assert frame["translation"] != pytest.approx([0.0, 0.0, 0.0])
    assert frame["resolved_origin"] != pytest.approx([0.0, 0.0, 0.05])
    assert summary["dpf_force_summation"]["moment_reference_xyz"] == pytest.approx(
        frame["resolved_origin"]
    )
    assert max(summary["max_abs_resultant_local"].values()) > 0.0
    assert summary["nodal_parity"]["force_matches"] is True
    assert summary["nodal_parity"]["moment_matches"] is False
    result_data = summary["_visualization_result_data"]
    assert result_data["analysis_mode"] == "static"
    for time_index, signature in enumerate(result_data["signatures"]):
        history = visualization.build_result_history_plot_payload(
            {"result_signature": signature},
            result_data,
            "local",
            selected_time_index=time_index,
        )
        assert history is not None
        assert len(history["force"]["components"]["total"]) == 2
        assert len(history["moment"]["components"]["total"]) == 2
        assert history["x_axis"]["result_set_ids"] == [1, 2]
    animation_session = summary.get("_animation_session")
    assert animation_session is not None
    try:
        assert animation_session.complete is True
        assert animation_session.loaded_indices() == [0, 1]
        first_animation_frame = visualization.static_animation_frame_state(
            animation_session, 0.0
        )
        second_animation_frame = visualization.static_animation_frame_state(
            animation_session, 1.0
        )
        assert first_animation_frame["frame"].final_determinant == pytest.approx(1.0)
        assert second_animation_frame["frame"].final_determinant == pytest.approx(1.0)
        assert first_animation_frame["points"] != pytest.approx(
            second_animation_frame["points"]
        )
    finally:
        animation_session.close()
