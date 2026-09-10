# Purpose: Verify the concrete OCP body carrier and Cylinder built-in.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_geometry_primitives.py

from __future__ import annotations

from dataclasses import asdict, replace
from functools import lru_cache
import json
import math
from pathlib import Path

import pytest

from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtin_functions import engineering_geometry
from ea_node_editor.nodes.builtins.geometry_contracts import BODY_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.geometry_primitives import (
    CONSTRUCT_GEOMETRY_GROUP_NODE_TYPE_ID,
    CYLINDER_NODE_TYPE_ID,
    OCP_BODY_DATA_TYPE_ID,
    OCP_BODY_HANDLE_KIND,
    _resolve_ocp_body,
    _resolve_geometry_group,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import PLANE_DATA_TYPE_ID
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import Interval1D, RuntimeHandleRef, TypedInlineValue
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

_CONVERTED_TYPE_IDS = (
    "geometry.cylinder",
    "geometry.construct_group",
    "mesh.deconstruct_mesh_face",
)
def _plane() -> TypedInlineValue:
    return TypedInlineValue(
        PLANE_DATA_TYPE_ID,
        1,
        {
            "origin": [10.0, 20.0, 30.0],
            "axes": [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0]],
            "normal": [0.0, 1.0, 0.0],
        },
    )


@lru_cache(maxsize=1)
def _function_adapters() -> dict[str, PythonFunctionAdapter]:
    namespace: dict[str, object] = {}
    exec(compile(engineering_geometry.SOURCE, "engineering_geometry.py", "exec"), namespace)
    declarations = discover_plugin_declarations(
        engineering_geometry.SOURCE,
        filename="engineering_geometry.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    return {
        declaration.spec.type_id: PythonFunctionAdapter(
            declaration.spec,
            namespace[declaration.function_name],  # type: ignore[arg-type]
        )
        for declaration in declarations
    }


def test_geometry_function_declarations_match_golden() -> None:
    declarations = discover_plugin_declarations(
        engineering_geometry.SOURCE,
        filename="engineering_geometry.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
    expected = {
        row["spec"]["type_id"]: row["spec"]
        for row in load_current_repo_owned_catalog()
        if row["spec"]["type_id"] in _CONVERTED_TYPE_IDS
    }
    assert tuple(declaration.spec.type_id for declaration in declarations) == (
        _CONVERTED_TYPE_IDS
    )
    assert {
        declaration.spec.type_id: json.loads(json.dumps(asdict(declaration.spec)))
        for declaration in declarations
    } == expected


def _runtime() -> tuple[object, WorkerServices, ExecutionContext]:
    registry = build_builtin_registry()
    services = WorkerServices()
    services.bind_data_types(registry.data_types)
    context = ExecutionContext(
        run_id="cylinder-run",
        node_id="cylinder-node",
        workspace_id="geometry-workspace",
        inputs={
            "plane": _plane(),
            "radius": 3.0,
            "interval": Interval1D(2.0, 6.0),
        },
        properties={},
        emit_log=lambda _level, _message: None,
        worker_services=services,
    )
    return _function_adapters()[CYLINDER_NODE_TYPE_ID], services, context




def test_construct_geometry_group_broadcasts_tolerance_and_releases_leases() -> None:
    cylinder, services, cylinder_context = _runtime()
    first_body = cylinder.execute(cylinder_context).outputs["body"]
    second_body = cylinder.execute(cylinder_context).outputs["body"]
    group_node = _function_adapters()[CONSTRUCT_GEOMETRY_GROUP_NODE_TYPE_ID]

    def group_context(geometry: list[object], tolerances: list[object]):
        return ExecutionContext(
            run_id=cylinder_context.run_id,
            node_id="construct-geometry-group-node",
            workspace_id=cylinder_context.workspace_id,
            inputs={
                "name": "Primary Geometry Group",
                "geometry": geometry,
                "tolerances": tolerances,
            },
            properties={},
            emit_log=lambda _level, _message: None,
            worker_services=services,
        )

    group_ref = group_node.execute(
        group_context([first_body, second_body], [-1.25])
    ).outputs["group"]
    resolved_ref, record = _resolve_geometry_group(
        group_context([], []),
        group_ref,
    )
    assert resolved_ref is group_ref
    assert record.name == "Primary Geometry Group"
    assert record.tolerances == (-1.25, -1.25)
    assert [ref.handle_id for ref in record.child_leases] == [
        first_body.handle_id,
        second_body.handle_id,
    ]
    aggregate_scope = record.child_leases[0].owner_scope
    assert aggregate_scope.startswith("cache:geometry_group:")
    assert aggregate_scope != first_body.owner_scope
    assert {ref.owner_scope for ref in record.child_leases} == {aggregate_scope}
    assert services.handle_registry.lease_count(
        first_body,
        owner_scope=aggregate_scope,
    ) == 1
    assert services.handle_registry.lease_count(
        second_body,
        owner_scope=aggregate_scope,
    ) == 1

    lease_count = services.handle_registry.active_lease_count
    with pytest.raises(ValueError, match="match geometry count"):
        group_node.execute(
            group_context([first_body, second_body], [1.0, 2.0, 3.0])
        )
    assert services.handle_registry.active_lease_count == lease_count

    wrong_kind = replace(second_body, kind="wrong.kind")
    with pytest.raises(TypeError, match="exact COREX OCPBody handle"):
        group_node.execute(group_context([first_body, wrong_kind], []))
    assert services.handle_registry.active_lease_count == lease_count

    class Hostile:
        def __getattribute__(self, _name: str) -> object:
            raise AssertionError("hostile input was accessed")

    with pytest.raises(TypeError, match="exact COREX Geometry Group handle"):
        _resolve_geometry_group(group_context([], []), Hostile())
    with pytest.raises(TypeError, match="exact COREX Geometry Group handle"):
        _resolve_geometry_group(
            group_context([], []),
            replace(group_ref, kind="wrong.kind"),
        )

    assert services.release_handle(group_ref)
    assert record.closed
    assert record.child_leases == ()
    assert services.handle_registry.lease_count(first_body) == 1
    assert services.handle_registry.lease_count(second_body) == 1
    assert services.release_handle(first_body)
    assert services.release_handle(second_body)


def test_cylinder_uses_shifted_plane_interval_and_disposes_idempotently() -> None:
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box

    node, services, context = _runtime()
    result = node.execute(context)
    body_ref = result.outputs["body"]
    assert type(body_ref) is RuntimeHandleRef
    assert body_ref.data_type_id == OCP_BODY_DATA_TYPE_ID
    assert body_ref.kind == OCP_BODY_HANDLE_KIND
    assert body_ref.metadata == {}
    record = context.resolve_handle(
        body_ref,
        expected_data_type=BODY_DATA_TYPE_ID,
        expected_kind=OCP_BODY_HANDLE_KIND,
    )
    shape = record.shape
    assert shape is not None and not shape.IsNull()
    resolved_ref, resolved_shape = _resolve_ocp_body(context, body_ref)
    assert resolved_ref is body_ref
    assert resolved_shape is shape

    class Hostile:
        def __getattribute__(self, _name: str) -> object:
            raise AssertionError("hostile input was accessed")

    with pytest.raises(TypeError, match="exact COREX OCPBody handle"):
        _resolve_ocp_body(context, Hostile())
    with pytest.raises(TypeError, match="exact COREX OCPBody handle"):
        _resolve_ocp_body(
            context,
            RuntimeHandleRef(
                data_type_id=OCP_BODY_DATA_TYPE_ID,
                schema_version=1,
                handle_id=body_ref.handle_id,
                kind="wrong.kind",
                owner_scope=body_ref.owner_scope,
                worker_generation=body_ref.worker_generation,
            ),
        )

    bounds = Bnd_Box()
    BRepBndLib.Add_s(shape, bounds)
    assert bounds.Get() == pytest.approx(
        (7.0, 22.0, 27.0, 13.0, 26.0, 33.0),
        abs=1.0e-6,
    )
    assert context.release_handle(body_ref)
    assert services.handle_registry.active_handle_count == 0
    assert record.shape is None
    record.close()
    record.dispose()
    assert record.shape is None


@pytest.mark.parametrize(
    "radius, interval, error",
    (
        (0.0, Interval1D(0.0, 1.0), "greater than zero"),
        (-1.0, Interval1D(0.0, 1.0), "greater than zero"),
        (math.inf, Interval1D(0.0, 1.0), "finite"),
        (True, Interval1D(0.0, 1.0), "finite numeric"),
        (1.0, Interval1D(2.0, 2.0), "strictly increasing"),
        (1.0, Interval1D(3.0, 2.0), "strictly increasing"),
    ),
)
def test_cylinder_rejects_invalid_radius_or_interval_without_a_handle(
    radius: object,
    interval: Interval1D,
    error: str,
) -> None:
    node, services, context = _runtime()
    context.inputs["radius"] = radius
    context.inputs["interval"] = interval

    with pytest.raises((TypeError, ValueError), match=error):
        node.execute(context)

    assert services.handle_registry.active_handle_count == 0
