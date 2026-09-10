# Purpose: Provide worker-local OCP geometry primitives with opaque typed handles.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_geometry_primitives.py

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import math
from numbers import Real
from typing import Any, Callable
from uuid import uuid4

from ea_node_editor.nodes.builtins.geometry_contracts import BODY_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.rich_value_nodes import (
    PLANE_DATA_TYPE_ID,
    is_plane_payload,
)
from ea_node_editor.nodes.core_data_types import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.plugin_contracts import PluginContractManifest
from ea_node_editor.runtime_contracts import (
    DataTypeSpec,
    Interval1D,
    RuntimeHandleRef,
    TypedInlineValue,
)

COREX_GEOMETRY_PRIMITIVES_OWNER_ID = "corex.geometry_primitives"
COREX_GEOMETRY_PRIMITIVES_OWNER_VERSION = "1"

OCP_BODY_DATA_TYPE_ID = "COREX.Geometry.OCPBody"
OCP_BODY_HANDLE_KIND = "corex.geometry.ocp_body"
CYLINDER_NODE_TYPE_ID = "geometry.cylinder"
GEOMETRY_GROUP_DATA_TYPE_ID = "COREX.Geometry.Group"
GEOMETRY_GROUP_HANDLE_KIND = "corex.geometry.group"
CONSTRUCT_GEOMETRY_GROUP_NODE_TYPE_ID = "geometry.construct_group"


def is_ocp_body_handle(value: object) -> bool:
    return (
        type(value) is RuntimeHandleRef
        and value.data_type_id == OCP_BODY_DATA_TYPE_ID
        and value.schema_version == 1
        and value.kind == OCP_BODY_HANDLE_KIND
        and value.metadata == {}
    )


def _resolve_ocp_body(
    ctx: ExecutionContext,
    value: object,
) -> tuple[RuntimeHandleRef, Any]:
    if not is_ocp_body_handle(value):
        raise TypeError("OCP Body input must be an exact COREX OCPBody handle")
    record = ctx.resolve_handle(
        value,
        expected_data_type=OCP_BODY_DATA_TYPE_ID,
        expected_kind=OCP_BODY_HANDLE_KIND,
    )
    if type(record) is not _OcpBodyRecord:
        raise TypeError("OCP Body handle does not resolve to an OCP body record")

    from OCP.TopoDS import TopoDS_Shape

    shape = record.shape
    if type(shape) is not TopoDS_Shape or shape.IsNull():
        raise RuntimeError("OCP Body handle no longer owns a live shape")
    return value, shape


def is_geometry_group_handle(value: object) -> bool:
    return (
        type(value) is RuntimeHandleRef
        and value.data_type_id == GEOMETRY_GROUP_DATA_TYPE_ID
        and value.schema_version == 1
        and value.kind == GEOMETRY_GROUP_HANDLE_KIND
        and value.metadata == {}
    )


def _resolve_geometry_group(
    ctx: ExecutionContext,
    value: object,
) -> tuple[RuntimeHandleRef, "_GeometryGroupRecord"]:
    if not is_geometry_group_handle(value):
        raise TypeError(
            "Geometry Group input must be an exact COREX Geometry Group handle"
        )
    record = ctx.resolve_handle(
        value,
        expected_data_type=GEOMETRY_GROUP_DATA_TYPE_ID,
        expected_kind=GEOMETRY_GROUP_HANDLE_KIND,
    )
    if type(record) is not _GeometryGroupRecord or record.closed:
        raise RuntimeError("Geometry Group handle no longer owns a live record")
    return value, record


def _geometry_group_compound(
    ctx: ExecutionContext,
    record: "_GeometryGroupRecord",
) -> Any:
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for child_ref in record.child_leases:
        _child_ref, shape = _resolve_ocp_body(ctx, child_ref)
        builder.Add(compound, shape)
    return compound


OCP_BODY_DATA_TYPE = DataTypeSpec(
    OCP_BODY_DATA_TYPE_ID,
    "OCP Body",
    "engineering",
    is_ocp_body_handle,
    parents=(BODY_DATA_TYPE_ID,),
    carriers=frozenset({"handle"}),
    persistence="never",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)

GEOMETRY_GROUP_DATA_TYPE = DataTypeSpec(
    GEOMETRY_GROUP_DATA_TYPE_ID,
    "Geometry Group",
    "engineering",
    is_geometry_group_handle,
    parents=(GRAPH_DATA_TYPE_ID,),
    carriers=frozenset({"handle"}),
    persistence="never",
    sensitivity="normal",
    payload_schema_version=1,
    implementation_version="1",
)

COREX_GEOMETRY_PRIMITIVES_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=(OCP_BODY_DATA_TYPE, GEOMETRY_GROUP_DATA_TYPE),
)


@dataclass(slots=True)
class _OcpBodyRecord:
    shape: Any | None

    def close(self) -> None:
        self.shape = None

    dispose = close


@dataclass(slots=True)
class _GeometryGroupRecord:
    name: str
    child_leases: tuple[RuntimeHandleRef, ...]
    tolerances: tuple[float, ...]
    _release_handle: Callable[[object], bool]
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        child_leases = self.child_leases
        self.child_leases = ()
        first_error: Exception | None = None
        for child_ref in reversed(child_leases):
            try:
                self._release_handle(child_ref)
            except (LookupError, TypeError):
                continue
            except Exception as exc:  # noqa: BLE001
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    dispose = close


def _geometry_group_tolerances(
    ctx: ExecutionContext,
    *,
    geometry_count: int,
) -> tuple[float, ...]:
    raw_values = ctx.inputs.get("tolerances", [])
    if raw_values is None:
        raw_values = []
    if type(raw_values) is not list:
        raise TypeError("Construct Geometry Group tolerances must be a list")
    double_spec = ctx.worker_services.data_types.require(DOUBLE_DATA_TYPE_ID)
    if any(not double_spec.validate_item(value) for value in raw_values):
        raise TypeError(
            "Construct Geometry Group tolerances must contain COREXDouble values"
        )
    values = tuple(float(value) for value in raw_values)
    if not values:
        return (0.0,) * geometry_count
    if len(values) == 1:
        return values * geometry_count
    if len(values) != geometry_count:
        raise ValueError(
            "Construct Geometry Group tolerances must be empty, one value, or match "
            "geometry count"
        )
    return values


def _plane_payload(value: object) -> dict[str, Any]:
    if (
        not isinstance(value, TypedInlineValue)
        or value.data_type_id != PLANE_DATA_TYPE_ID
        or value.schema_version != 1
        or not is_plane_payload(value.payload)
    ):
        raise ValueError("Plane input is invalid")
    return value.payload


def _positive_radius(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("Cylinder radius must be a finite numeric value")
    try:
        radius = float(value)
    except OverflowError as exc:
        raise ValueError("Cylinder radius must be finite") from exc
    if not math.isfinite(radius):
        raise ValueError("Cylinder radius must be finite")
    if radius <= 0.0:
        raise ValueError("Cylinder radius must be greater than zero")
    return radius


def _increasing_interval(value: object) -> Interval1D:
    if not isinstance(value, Interval1D):
        raise TypeError("Cylinder interval must be an Interval1D value")
    if value.end <= value.start:
        raise ValueError("Cylinder interval must be strictly increasing")
    return value


def _make_cylinder_shape(
    plane: dict[str, Any],
    *,
    radius: float,
    interval: Interval1D,
) -> Any:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    origin = plane["origin"]
    x_axis = plane["axes"][0]
    normal = plane["normal"]
    shifted_origin = tuple(
        float(origin[index]) + interval.start * float(normal[index])
        for index in range(3)
    )
    axis = gp_Ax2(
        gp_Pnt(*shifted_origin),
        gp_Dir(*(float(component) for component in normal)),
        gp_Dir(*(float(component) for component in x_axis)),
    )
    builder = BRepPrimAPI_MakeCylinder(axis, radius, interval.end - interval.start)
    shape = builder.Shape()
    if not builder.IsDone():
        raise RuntimeError("OCP could not build the cylinder")
    if shape.IsNull():
        raise RuntimeError("OCP returned an empty cylinder")
    return shape


def execute_cylinder(ctx: ExecutionContext) -> NodeResult:
    plane = _plane_payload(ctx.inputs["plane"])
    radius = _positive_radius(ctx.inputs["radius"])
    interval = _increasing_interval(ctx.inputs["interval"])
    record = _OcpBodyRecord(
        _make_cylinder_shape(plane, radius=radius, interval=interval)
    )
    body_ref: RuntimeHandleRef | None = None
    try:
        body_ref = ctx.register_handle(
            record,
            data_type_id=OCP_BODY_DATA_TYPE_ID,
            kind=OCP_BODY_HANDLE_KIND,
            metadata={},
            dispose=record.close,
        )
        return NodeResult(outputs={"body": body_ref})
    except Exception:
        if body_ref is not None:
            with suppress(Exception):
                ctx.release_handle(body_ref)
        record.close()
        raise


def execute_construct_geometry_group(ctx: ExecutionContext) -> NodeResult:
    name = ctx.inputs.get("name")
    if not isinstance(name, str):
        raise TypeError("Construct Geometry Group name must be a COREXString value")
    geometry = ctx.inputs.get("geometry")
    if type(geometry) is not list or not geometry:
        raise ValueError("Construct Geometry Group requires a nonempty OCPBody list")
    tolerances = _geometry_group_tolerances(ctx, geometry_count=len(geometry))
    aggregate_scope = f"cache:geometry_group:{uuid4().hex}"
    record = _GeometryGroupRecord(
        name=name,
        child_leases=(),
        tolerances=tolerances,
        _release_handle=ctx.worker_services.release_handle,
    )
    acquired: list[RuntimeHandleRef] = []
    try:
        for value in geometry:
            child_ref, _shape = _resolve_ocp_body(ctx, value)
            acquired.append(ctx.lease_handle(child_ref, owner_scope=aggregate_scope))
        record.child_leases = tuple(acquired)
        group_ref = ctx.register_handle(
            record,
            data_type_id=GEOMETRY_GROUP_DATA_TYPE_ID,
            kind=GEOMETRY_GROUP_HANDLE_KIND,
            metadata={},
            dispose=record.close,
        )
        return NodeResult(outputs={"group": group_ref})
    except Exception:
        record.child_leases = tuple(acquired)
        record.close()
        raise

__all__ = [
    "CONSTRUCT_GEOMETRY_GROUP_NODE_TYPE_ID",
    "CYLINDER_NODE_TYPE_ID",
    "OCP_BODY_DATA_TYPE",
    "OCP_BODY_DATA_TYPE_ID",
    "OCP_BODY_HANDLE_KIND",
    "COREX_GEOMETRY_PRIMITIVES_CONTRACT_MANIFEST",
    "COREX_GEOMETRY_PRIMITIVES_OWNER_ID",
    "COREX_GEOMETRY_PRIMITIVES_OWNER_VERSION",
    "GEOMETRY_GROUP_DATA_TYPE",
    "GEOMETRY_GROUP_DATA_TYPE_ID",
    "GEOMETRY_GROUP_HANDLE_KIND",
    "execute_construct_geometry_group",
    "execute_cylinder",
    "is_geometry_group_handle",
    "is_ocp_body_handle",
]
