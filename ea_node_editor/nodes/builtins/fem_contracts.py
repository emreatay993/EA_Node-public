# Purpose: Declare COREX FEM contracts plus bounded Force and optimization constructors.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_fem_contracts.py

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ea_node_editor.common.optimization_links import (
    OPTIMIZATION_PARAMETER_POOL_TYPE_ID,
    OPTIMIZATION_PARAMETER_SETUP_TYPE_ID,
    OPTIMIZATION_RESPONSE_POOL_TYPE_ID,
    PARAMETER_POOL_ROLE,
    RESPONSE_POOL_ROLE,
    parameter_setup_pool_link_facts,
)
from ea_node_editor.nodes.builtins.geometry_primitives import (
    OCP_BODY_DATA_TYPE_ID,
    _resolve_ocp_body,
)
from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from ea_node_editor.nodes.builtins.spatial_values import (
    VECTOR_3D_DATA_TYPE_ID,
    vector3d_coordinates,
)
from ea_node_editor.nodes.core_data_types import (
    DOUBLE_DATA_TYPE_ID,
    GRAPH_DATA_TYPE_ID as _GRAPH_DATA_TYPE_ID,
    INTEGER_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import PortSpec, PropertySpec
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest as _PluginContractManifest,
)
from ea_node_editor.runtime_contracts import (
    DataTypeSpec as _DataTypeSpec,
    Interval1D,
    RuntimeHandleRef,
)

COREX_FEM_CONTRACTS_OWNER_ID = "corex.fem_contracts"
COREX_FEM_CONTRACTS_OWNER_VERSION = "1"

OPTIMIZATION_VARIABLE_DATA_TYPE_ID = (
    "COREX.DataTypes.Optimization.OptimizationVariable"
)
OPTIMIZATION_PARAMETER_DATA_TYPE_ID = (
    "COREX.DataTypes.Optimization.OptimizationParameter"
)
OPTIMIZATION_RESPONSE_DATA_TYPE_ID = (
    "COREX.DataTypes.Optimization.OptimizationResponse"
)
OPTIMIZATION_DESIGN_DATA_TYPE_ID = (
    "COREX.DataTypes.Optimization.OptimizationDesign"
)
OPTIMIZATION_VARIABLE_HANDLE_KIND = "corex.optimization.variable"
OPTIMIZATION_DESIGN_HANDLE_KIND = "corex.optimization.design"
CONSTRUCT_PARAMETERS_NODE_TYPE_ID = "optimization.construct_parameters"
CONSTRUCT_RESPONSES_NODE_TYPE_ID = "optimization.construct_responses"
PARAMETER_SETUP_NODE_TYPE_ID = OPTIMIZATION_PARAMETER_SETUP_TYPE_ID
PARAMETER_POOL_NODE_TYPE_ID = OPTIMIZATION_PARAMETER_POOL_TYPE_ID
RESPONSE_POOL_NODE_TYPE_ID = OPTIMIZATION_RESPONSE_POOL_TYPE_ID
CONSTRUCT_DESIGN_NODE_TYPE_ID = "optimization.construct_design"
_SHORTEST_LIST_WARNING = (
    "Input list lengths differ; output was truncated to the shortest participating list."
)

LOAD_STEP_DATA_TYPE_ID = "COREX.Fem.LoadSteps.ILoadStep"
LOAD_DATA_TYPE_ID = "COREX.Fem.Loads.ILoad"
FIXED_DISPLACEMENT_DATA_TYPE_ID = "COREX.Fem.Loads.IFixedDisplacement"
PRESSURE_DATA_TYPE_ID = "COREX.Fem.Loads.IPressure"
LINEAR_STATIC_MECHANICAL_DATA_TYPE_ID = (
    "COREX.Fem.LoadSteps.ILinearStaticMechanical"
)
STEADY_STATE_HEAT_TRANSFER_DATA_TYPE_ID = (
    "COREX.Fem.LoadSteps.ISteadyStateHeatTransfer"
)

_CONTACT_PAIR_TYPE_ROWS = (
    (
        "COREX.Fem.ContactPairs.IContactPair",
        "Contact Pair",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.ContactPairs.IContactPairSettings",
        "Contact Pair Settings",
        _GRAPH_DATA_TYPE_ID,
    ),
)

NODE_DATA_TYPE_ID = "COREX.Fem.Model.INode"
ELEMENT_DATA_TYPE_ID = "COREX.Fem.Elements.IElement"
ELEMENT_QUALITY_CRITERIA_DATA_TYPE_ID = (
    "COREX.Fem.Elements.Quality.ElementQualityCriteria"
)

_INDEPENDENT_ELEMENT_DATA_TYPE_ID = (
    "COREX.Fem.Elements.IIndependentElement"
)
_ELEMENT_SUBINTERFACE_TYPE_ROWS = (
    (
        _INDEPENDENT_ELEMENT_DATA_TYPE_ID,
        "Independent Element",
        ELEMENT_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Elements.IPointMass",
        "Point Mass",
        _INDEPENDENT_ELEMENT_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Elements.ISpotWeld",
        "Spot Weld",
        _INDEPENDENT_ELEMENT_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Elements.ISpring",
        "Spring",
        _INDEPENDENT_ELEMENT_DATA_TYPE_ID,
    ),
)

_MATERIAL_TYPE_ROWS = (
    (
        "COREX.Fem.Materials.IMaterial",
        "Material",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Materials.IAnisotropicMaterial",
        "Anisotropic Material",
        "COREX.Fem.Materials.IMaterial",
    ),
    (
        "COREX.Fem.Materials.IIsotropicMaterial",
        "Isotropic Material",
        "COREX.Fem.Materials.IMaterial",
    ),
    (
        "COREX.Fem.Materials.IOrthotropicMaterial",
        "Orthotropic Material",
        "COREX.Fem.Materials.IMaterial",
    ),
    (
        "COREX.Fem.Materials.IRigidMaterial",
        "Rigid Material",
        "COREX.Fem.Materials.IMaterial",
    ),
    (
        "COREX.Fem.Materials.IMaterialDamageSettings",
        "Material Damage Settings",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Materials.IMaterialFailureSettings",
        "Material Failure Settings",
        _GRAPH_DATA_TYPE_ID,
    ),
)

RESPONSE_DATA_TYPE_ID = "COREX.Fem.Optimization.Responses.IResponse"
CONSTRAINT_DATA_TYPE_ID = "COREX.Fem.Optimization.Constraints.IConstraint"
OBJECTIVE_DATA_TYPE_ID = "COREX.Fem.Optimization.Objectives.IObjective"
VARIABLE_DATA_TYPE_ID = "COREX.Fem.Optimization.Variables.IVariable"

_OPTIMIZATION_RESPONSE_TYPE_ROWS = (
    (
        "COREX.Fem.Optimization.Responses.IAccelerationResponse",
        "Acceleration Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IBucklingFactorResponse",
        "Buckling Factor Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IDensityResponse",
        "Density Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IDisplacementResponse",
        "Displacement Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IElementMaximumVonMisesStressResponse",
        "Element Maximum Von Mises Stress Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IEquivalentPlasticStrainResponse",
        "Equivalent Plastic Strain Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IFrequencyResponse",
        "Frequency Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IHeatFluxResponse",
        "Heat Flux Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IMassResponse",
        "Mass Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IReactionForceResponse",
        "Reaction Force Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IReactionMomentResponse",
        "Reaction Moment Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IRotationResponse",
        "Rotation Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IShellThicknessResponse",
        "Shell Thickness Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IStrainResponse",
        "Strain Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IStressResponse",
        "Stress Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.ITemperatureResponse",
        "Temperature Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IVelocityResponse",
        "Velocity Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IVolumeFractionResponse",
        "Volume Fraction Response",
    ),
    (
        "COREX.Fem.Optimization.Responses.IWeightedComplianceResponse",
        "Weighted Compliance Response",
    ),
)

_CROSS_SECTION_TYPE_ROWS = (
    (
        "COREX.Fem.CrossSections.ICrossSection",
        "Cross Section",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Optimization.Variables.ICrossSectionVariable",
        "Cross Section Variable",
        VARIABLE_DATA_TYPE_ID,
    ),
)

_FEM_SUPPORT_TYPE_ROWS = (
    (
        "COREX.Fem.Model.ISet",
        "Set",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Settings.IModelSetting",
        "Model Setting",
        _GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Settings.ILsDynaModelSetting",
        "LS-DYNA Model Setting",
        "COREX.Fem.Settings.IModelSetting",
    ),
    (
        "COREX.Fem.TabularCurves.ITabularCurve",
        "Tabular Curve",
        _GRAPH_DATA_TYPE_ID,
    ),
)

FORCE_DATA_TYPE_ID = "COREX.Fem.Force"
FORCE_HANDLE_KIND = "corex.fem.force"
FORCE_NODE_TYPE_ID = "fea.force"
LOAD_CONTAINER_NODE_TYPE_ID = "fea.load_container"


def _is_element_quality_criteria(value: object) -> bool:
    pair_names = (
        "Hexa20",
        "Hexa8",
        "Quad4",
        "Quad8",
        "Tet10",
        "Tet4",
        "Tria3",
        "Tria6",
    )
    triple_names = ("Prism15", "Prism6", "Pyra13", "Pyra5")
    pair_keys = {"AspectRatioUpperBound", "MinimumInternalAngle"}
    triple_keys = {
        "AspectRatioUpperBound",
        "QuadMinimumInternalAngle",
        "TriaMinimumInternalAngle",
    }

    def is_number(item: object) -> bool:
        return type(item) is int or (type(item) is float and math.isfinite(item))

    if type(value) is not dict or set(value) != {
        "MinimumEdgeLength",
        *pair_names,
        *triple_names,
    }:
        return False
    if not is_number(value["MinimumEdgeLength"]):
        return False
    for name, keys in (
        *((name, pair_keys) for name in pair_names),
        *((name, triple_keys) for name in triple_names),
    ):
        criteria = value[name]
        if (
            type(criteria) is not dict
            or set(criteria) != keys
            or not all(is_number(item) for item in criteria.values())
        ):
            return False
    return True


def _is_exact_handle(
    value: object,
    *,
    data_type_id: str,
    kind: str,
) -> bool:
    return (
        type(value) is RuntimeHandleRef
        and value.data_type_id == data_type_id
        and value.schema_version == 1
        and value.kind == kind
        and value.metadata == {}
    )


def _is_force_handle(value: object) -> bool:
    return _is_exact_handle(
        value,
        data_type_id=FORCE_DATA_TYPE_ID,
        kind=FORCE_HANDLE_KIND,
    )

COREX_FEM_DATA_TYPES = (
    _DataTypeSpec(
        LOAD_STEP_DATA_TYPE_ID,
        "Load Step",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        LOAD_DATA_TYPE_ID,
        "Load",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        FIXED_DISPLACEMENT_DATA_TYPE_ID,
        "Fixed Displacement",
        "engineering",
        lambda _value: False,
        parents=(LOAD_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        PRESSURE_DATA_TYPE_ID,
        "Pressure",
        "engineering",
        lambda _value: False,
        parents=(LOAD_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        FORCE_DATA_TYPE_ID,
        "Force",
        "engineering",
        _is_force_handle,
        parents=(LOAD_DATA_TYPE_ID,),
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        LINEAR_STATIC_MECHANICAL_DATA_TYPE_ID,
        "Linear Static Mechanical",
        "engineering",
        lambda _value: False,
        parents=(LOAD_STEP_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        STEADY_STATE_HEAT_TRANSFER_DATA_TYPE_ID,
        "Steady State Heat Transfer",
        "engineering",
        lambda _value: False,
        parents=(LOAD_STEP_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(parent_type_id,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parent_type_id in _CONTACT_PAIR_TYPE_ROWS
    ),
    _DataTypeSpec(
        NODE_DATA_TYPE_ID,
        "Node",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        ELEMENT_DATA_TYPE_ID,
        "Element",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(parent_type_id,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parent_type_id in _ELEMENT_SUBINTERFACE_TYPE_ROWS
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(parent_type_id,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parent_type_id in _MATERIAL_TYPE_ROWS
    ),
    _DataTypeSpec(
        RESPONSE_DATA_TYPE_ID,
        "Response",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(RESPONSE_DATA_TYPE_ID,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name in _OPTIMIZATION_RESPONSE_TYPE_ROWS
    ),
    _DataTypeSpec(
        CONSTRAINT_DATA_TYPE_ID,
        "Constraint",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        OBJECTIVE_DATA_TYPE_ID,
        "Objective",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        VARIABLE_DATA_TYPE_ID,
        "Variable",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(parent_type_id,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parent_type_id in _CROSS_SECTION_TYPE_ROWS
    ),
    *(
        _DataTypeSpec(
            type_id,
            display_name,
            "engineering",
            lambda _value: False,
            parents=(parent_type_id,),
            abstract=True,
            carriers=frozenset({"handle"}),
            persistence="never",
            sensitivity="normal",
            payload_schema_version=1,
            implementation_version="1",
        )
        for type_id, display_name, parent_type_id in _FEM_SUPPORT_TYPE_ROWS
    ),
    _DataTypeSpec(
        OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
        "Optimization Variable",
        "engineering",
        lambda _value: False,
        parents=(_GRAPH_DATA_TYPE_ID,),
        abstract=True,
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
        "Optimization Parameter",
        "engineering",
        lambda value: _is_exact_handle(
            value,
            data_type_id=OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
            kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
        ),
        parents=(OPTIMIZATION_VARIABLE_DATA_TYPE_ID,),
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
        "Optimization Response",
        "engineering",
        lambda value: _is_exact_handle(
            value,
            data_type_id=OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
            kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
        ),
        parents=(OPTIMIZATION_VARIABLE_DATA_TYPE_ID,),
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        OPTIMIZATION_DESIGN_DATA_TYPE_ID,
        "Optimization Design",
        "engineering",
        lambda value: _is_exact_handle(
            value,
            data_type_id=OPTIMIZATION_DESIGN_DATA_TYPE_ID,
            kind=OPTIMIZATION_DESIGN_HANDLE_KIND,
        ),
        parents=(_GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"handle"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
    _DataTypeSpec(
        ELEMENT_QUALITY_CRITERIA_DATA_TYPE_ID,
        "Element Quality Criteria",
        "engineering",
        _is_element_quality_criteria,
        parents=(_GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)

COREX_FEM_CONTRACT_MANIFEST = _PluginContractManifest(
    data_types=COREX_FEM_DATA_TYPES,
)


@dataclass(slots=True, frozen=True)
class _OptimizationParameterRecord:
    id: UUID
    node_id: UUID
    name: str
    minimum_value: float
    maximum_value: float
    decimal_places: int


@dataclass(slots=True, frozen=True)
class _OptimizationResponseRecord:
    id: UUID
    node_id: UUID
    name: str
    objective: int
    minimum_constraint: float | None
    maximum_constraint: float | None


@dataclass(slots=True, frozen=True)
class _OptimizationParameterPoolState:
    definitions: tuple[_OptimizationParameterRecord, ...]
    values: tuple[float, ...]


@dataclass(slots=True, frozen=True)
class _OptimizationResponsePoolState:
    definitions: tuple[_OptimizationResponseRecord, ...]
    values: tuple[float | None, ...]


@dataclass(slots=True, frozen=True)
class _OptimizationDesignRecord:
    id: UUID
    name: str
    status: int
    variables: tuple[_OptimizationParameterRecord | _OptimizationResponseRecord, ...]
    values: tuple[float | None, ...]
    solution: object | None
    screenshot: object | None


_DESIGN_STATUS_REFERENCE = -1
_DESIGN_STATUS_PENDING = 0
_DESIGN_STATUS_ERROR_PARAMETERS = 1
_DESIGN_STATUS_ERROR_RESPONSES = 2
_DESIGN_STATUS_INFEASIBLE = 3
_DESIGN_STATUS_COMPUTED = 4
_DESIGN_STATUS_FEASIBLE = 5


def _deterministic_optimization_id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"corex://optimization/{name}")


def _optimization_node_uuid(workspace_id: str, node_id: str) -> UUID:
    try:
        result = UUID(node_id)
    except (TypeError, ValueError, AttributeError):
        result = uuid5(
            NAMESPACE_URL,
            f"corex://workspace/{workspace_id}/node/{node_id}",
        )
    if result.int == 0:
        raise ValueError("Optimization Pool node ID must be nonzero")
    return result


@dataclass(slots=True)
class _ForceRecord:
    name: str
    index: int | None
    child_leases: tuple[RuntimeHandleRef, ...]
    tolerances: tuple[float, ...]
    vector_components: tuple[int | float, int | float, int | float]
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


def _force_tolerances(
    ctx: ExecutionContext,
    *,
    geometry_count: int,
) -> tuple[float, ...]:
    raw_values = ctx.inputs.get("tolerances", [])
    if raw_values is None:
        raw_values = []
    if type(raw_values) is not list:
        raise TypeError("Force tolerances must be a list")
    double_spec = ctx.worker_services.data_types.require(DOUBLE_DATA_TYPE_ID)
    values: list[float] = []
    for value in raw_values:
        if not double_spec.validate_item(value):
            raise TypeError("Force tolerances must contain finite numeric values")
        try:
            tolerance = float(value)
        except OverflowError as exc:
            raise ValueError("Force tolerances must be finite") from exc
        if not math.isfinite(tolerance):
            raise ValueError("Force tolerances must be finite")
        if tolerance <= 0.0:
            raise ValueError("Explicit Force tolerances must be greater than zero")
        values.append(tolerance)
    if not values:
        # Zero selects automatic tolerance.
        return (0.0,) * geometry_count
    if len(values) == 1:
        return tuple(values) * geometry_count
    if len(values) != geometry_count:
        raise ValueError(
            "Force tolerances must be empty, one value, or match geometry count"
        )
    return tuple(values)


def _force_index(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError("Force index must be an exact integer")
    if value <= 0:
        raise ValueError("Force index must be greater than zero")
    return value


def _required_list_input(
    ctx: ExecutionContext,
    key: str,
    *,
    node_label: str,
) -> list[object]:
    value = ctx.inputs.get(key)
    if type(value) is not list or not value:
        raise ValueError(f"{node_label} requires a nonempty {key} list")
    return value


def _validate_list_items(
    ctx: ExecutionContext,
    values: list[object],
    *,
    data_type_id: str,
    label: str,
    allow_none: bool = False,
) -> None:
    spec = ctx.worker_services.data_types.require(data_type_id)
    for value in values:
        if value is None and allow_none:
            continue
        if not spec.validate_item(value):
            raise TypeError(f"{label} contains an invalid {spec.display_name} item")


def _register_optimization_records(
    ctx: ExecutionContext,
    records: tuple[object, ...],
    *,
    data_type_id: str,
) -> list[RuntimeHandleRef]:
    refs: list[RuntimeHandleRef] = []
    try:
        for record in records:
            refs.append(
                ctx.register_handle(
                    record,
                    data_type_id=data_type_id,
                    kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
                    metadata={},
                )
            )
    except Exception:
        for ref in reversed(refs):
            try:
                ctx.release_handle(ref)
            except (LookupError, TypeError):
                continue
        raise
    return refs


def _copy_optimization_record(
    record: object,
) -> _OptimizationParameterRecord | _OptimizationResponseRecord:
    if type(record) is _OptimizationParameterRecord:
        return _OptimizationParameterRecord(
            id=record.id,
            node_id=record.node_id,
            name=record.name,
            minimum_value=record.minimum_value,
            maximum_value=record.maximum_value,
            decimal_places=record.decimal_places,
        )
    if type(record) is _OptimizationResponseRecord:
        return _OptimizationResponseRecord(
            id=record.id,
            node_id=record.node_id,
            name=record.name,
            objective=record.objective,
            minimum_constraint=record.minimum_constraint,
            maximum_constraint=record.maximum_constraint,
        )
    raise TypeError("Optimization Variable handle resolved to an invalid record")


def _resolve_optimization_record(
    ctx: ExecutionContext,
    value: object,
) -> _OptimizationParameterRecord | _OptimizationResponseRecord:
    if (
        type(value) is not RuntimeHandleRef
        or value.kind != OPTIMIZATION_VARIABLE_HANDLE_KIND
        or value.data_type_id
        not in {
            OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
            OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
        }
    ):
        raise TypeError(
            "Optimization Variables must be existing Parameter or Response handles"
        )
    ctx.worker_services.data_types.validate_carrier(value.data_type_id, value)
    resolved = ctx.resolve_handle(
        value,
        expected_data_type=value.data_type_id,
        expected_kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
    )
    return _copy_optimization_record(resolved)


def _require_unique_optimization_records(
    records: tuple[_OptimizationParameterRecord | _OptimizationResponseRecord, ...],
    *,
    require_unique_names: bool = False,
) -> None:
    identifiers = tuple(record.id for record in records)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Optimization Variables contain duplicate IDs")
    if require_unique_names:
        names = tuple(record.name for record in records)
        if len(set(names)) != len(names):
            raise ValueError("Optimization Variables contain duplicate names")


def _register_mixed_optimization_records(
    ctx: ExecutionContext,
    records: tuple[_OptimizationParameterRecord | _OptimizationResponseRecord, ...],
) -> list[RuntimeHandleRef]:
    refs: list[RuntimeHandleRef] = []
    try:
        for record in records:
            data_type_id = (
                OPTIMIZATION_PARAMETER_DATA_TYPE_ID
                if type(record) is _OptimizationParameterRecord
                else OPTIMIZATION_RESPONSE_DATA_TYPE_ID
            )
            refs.append(
                ctx.register_handle(
                    record,
                    data_type_id=data_type_id,
                    kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
                    metadata={},
                )
            )
    except Exception:
        for ref in reversed(refs):
            try:
                ctx.release_handle(ref)
            except (LookupError, TypeError):
                continue
        raise
    return refs


def _parameter_setup_pool_targets(
    ctx: ExecutionContext,
) -> dict[str, tuple[str, UUID]]:
    targets: dict[str, tuple[str, UUID]] = {}
    for role, expected_type_id in (
        (PARAMETER_POOL_ROLE, PARAMETER_POOL_NODE_TYPE_ID),
        (RESPONSE_POOL_ROLE, RESPONSE_POOL_NODE_TYPE_ID),
    ):
        link_facts = parameter_setup_pool_link_facts(role)
        if link_facts is None:
            continue
        link_id, link_title = link_facts
        matching = tuple(
            link for link in ctx.semantic_links if link.get("id") == link_id
        )
        if not matching:
            continue
        if len(matching) != 1:
            raise ValueError(f"Parameter Setup has duplicate {link_title} links")
        link = matching[0]
        target_node_id = link.get("target_node_id")
        if (
            not isinstance(target_node_id, str)
            or link.get("kind") != "node"
            or link.get("title") != link_title
            or link.get("target") != target_node_id
            or link.get("subtitle") != ""
            or link.get("target_workspace_id") != ctx.workspace_id
            or ctx.workspace_node_types.get(target_node_id) != expected_type_id
        ):
            raise ValueError(f"Parameter Setup has a malformed {link_title} link")
        target_uuid = _optimization_node_uuid(ctx.workspace_id, target_node_id)
        targets[role] = (target_node_id, target_uuid)
    return targets


def _optional_list_input(
    ctx: ExecutionContext,
    key: str,
    *,
    node_label: str,
) -> list[object] | None:
    value = ctx.inputs.get(key)
    if value is None or value == []:
        return None
    if type(value) is not list:
        raise TypeError(f"{node_label} {key} must be a list")
    return value


def _exact_finite_values(
    ctx: ExecutionContext,
    values: list[object],
    *,
    label: str,
    allow_none: bool = False,
) -> tuple[float | None, ...]:
    # Deliberate COREX boundary: COREX double carriers may admit NaN, while the
    # current shared Double contract accepts finite values only.
    _validate_list_items(
        ctx,
        values,
        data_type_id=DOUBLE_DATA_TYPE_ID,
        label=label,
        allow_none=allow_none,
    )
    return tuple(None if value is None else float(value) for value in values)


def _response_design_status(
    definitions: tuple[_OptimizationResponseRecord, ...],
    values: tuple[float | None, ...],
) -> int:
    if not definitions:
        return _DESIGN_STATUS_PENDING
    if any(value is None for value in values):
        return _DESIGN_STATUS_PENDING
    constrained = any(
        definition.minimum_constraint is not None
        or definition.maximum_constraint is not None
        for definition in definitions
    )
    infeasible = any(
        value is not None
        and (
            (
                definition.minimum_constraint is not None
                and value < definition.minimum_constraint
            )
            or (
                definition.maximum_constraint is not None
                and value > definition.maximum_constraint
            )
        )
        for definition, value in zip(definitions, values, strict=True)
    )
    if infeasible:
        return _DESIGN_STATUS_INFEASIBLE
    return _DESIGN_STATUS_FEASIBLE if constrained else _DESIGN_STATUS_COMPUTED


def execute_force(ctx: ExecutionContext) -> NodeResult:
    name = ctx.inputs.get("name")
    if type(name) is not str:
        raise TypeError("Force name must be an exact string")
    if not name:
        raise ValueError("Force name must not be empty")
    index = _force_index(ctx.inputs.get("index"))
    geometry = ctx.inputs.get("geometry")
    if type(geometry) is not list or not geometry:
        raise ValueError("Force requires a nonempty OCPBody list")
    tolerances = _force_tolerances(ctx, geometry_count=len(geometry))
    vector = tuple(vector3d_coordinates(ctx.inputs.get("vector")))
    aggregate_scope = f"cache:force:{uuid4().hex}"
    record = _ForceRecord(
        name=name,
        index=index,
        child_leases=(),
        tolerances=tolerances,
        vector_components=vector,
        _release_handle=ctx.worker_services.release_handle,
    )
    acquired: list[RuntimeHandleRef] = []
    try:
        for value in geometry:
            child_ref, _shape = _resolve_ocp_body(ctx, value)
            acquired.append(ctx.lease_handle(child_ref, owner_scope=aggregate_scope))
        record.child_leases = tuple(acquired)
        force_ref = ctx.register_handle(
            record,
            data_type_id=FORCE_DATA_TYPE_ID,
            kind=FORCE_HANDLE_KIND,
            metadata={},
            dispose=record.close,
        )
        return NodeResult(outputs={"load": force_ref})
    except Exception:
        record.child_leases = tuple(acquired)
        record.close()
        raise


def execute_load_container(ctx: ExecutionContext) -> NodeResult:
    value = ctx.inputs.get("load")
    if type(value) is not RuntimeHandleRef:
        raise TypeError("Load Container requires an authenticated ILoad handle")
    ctx.worker_services.data_types.validate_carrier(LOAD_DATA_TYPE_ID, value)
    ctx.resolve_handle(
        value,
        expected_data_type=value.data_type_id,
        expected_kind=value.kind,
    )
    return NodeResult(outputs={"output": value})


def execute_construct_parameters(ctx: ExecutionContext) -> NodeResult:
    node_label = "Construct Parameters"
    names = _required_list_input(ctx, "names", node_label=node_label)
    minimum_values = _required_list_input(
        ctx,
        "minimum_values",
        node_label=node_label,
    )
    maximum_values = _required_list_input(
        ctx,
        "maximum_values",
        node_label=node_label,
    )
    decimal_places = _required_list_input(
        ctx,
        "decimal_places",
        node_label=node_label,
    )
    _validate_list_items(ctx, names, data_type_id=STRING_DATA_TYPE_ID, label="Names")
    _validate_list_items(
        ctx,
        minimum_values,
        data_type_id=DOUBLE_DATA_TYPE_ID,
        label="Minimum Values",
    )
    _validate_list_items(
        ctx,
        maximum_values,
        data_type_id=DOUBLE_DATA_TYPE_ID,
        label="Maximum Values",
    )
    _validate_list_items(
        ctx,
        decimal_places,
        data_type_id=INTEGER_DATA_TYPE_ID,
        label="Decimal Places",
    )
    if any(not 0 <= value <= 15 for value in decimal_places):
        raise ValueError("Decimal Places items must be between 0 and 15")

    lengths = tuple(
        len(values)
        for values in (names, minimum_values, maximum_values, decimal_places)
    )
    records: list[_OptimizationParameterRecord] = []
    for index in range(min(lengths)):
        places = decimal_places[index]
        rounded_minimum = round(float(minimum_values[index]), places)
        rounded_maximum = round(float(maximum_values[index]), places)
        if rounded_minimum >= rounded_maximum:
            raise ValueError(
                "Optimization Parameter rounded minimum must be less than maximum"
            )
        records.append(
            _OptimizationParameterRecord(
                id=uuid4(),
                node_id=UUID(int=0),
                name=str(names[index]),
                minimum_value=rounded_minimum,
                maximum_value=rounded_maximum,
                decimal_places=places,
            )
        )
    refs = _register_optimization_records(
        ctx,
        tuple(records),
        data_type_id=OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
    )
    warnings = () if len(set(lengths)) == 1 else (_SHORTEST_LIST_WARNING,)
    return NodeResult(outputs={"parameters": refs}, warnings=warnings)


def execute_construct_responses(ctx: ExecutionContext) -> NodeResult:
    node_label = "Construct Responses"
    names = _required_list_input(ctx, "names", node_label=node_label)
    objectives = _required_list_input(ctx, "objectives", node_label=node_label)

    optional_constraints: dict[str, list[object] | None] = {}
    for key in ("minimum_constraints", "maximum_constraints"):
        value = ctx.inputs.get(key)
        if value is None:
            optional_constraints[key] = None
        elif type(value) is not list:
            raise TypeError(f"{node_label} {key} must be a list")
        else:
            optional_constraints[key] = value or None
    minimum_constraints = optional_constraints["minimum_constraints"]
    maximum_constraints = optional_constraints["maximum_constraints"]

    _validate_list_items(ctx, names, data_type_id=STRING_DATA_TYPE_ID, label="Names")
    _validate_list_items(
        ctx,
        objectives,
        data_type_id=INTEGER_DATA_TYPE_ID,
        label="Objectives",
    )
    if any(value not in {0, 1, 2} for value in objectives):
        raise ValueError("Objectives items must be 0, 1, or 2")
    for label, values in (
        ("Minimum Constraints", minimum_constraints),
        ("Maximum Constraints", maximum_constraints),
    ):
        if values is not None:
            _validate_list_items(
                ctx,
                values,
                data_type_id=DOUBLE_DATA_TYPE_ID,
                label=label,
                allow_none=True,
            )

    participating_lists = [names, objectives]
    if minimum_constraints is not None:
        participating_lists.append(minimum_constraints)
    if maximum_constraints is not None:
        participating_lists.append(maximum_constraints)
    lengths = tuple(len(values) for values in participating_lists)
    records: list[_OptimizationResponseRecord] = []
    for index in range(min(lengths)):
        minimum_item = (
            None if minimum_constraints is None else minimum_constraints[index]
        )
        maximum_item = (
            None if maximum_constraints is None else maximum_constraints[index]
        )
        minimum_constraint = None if minimum_item is None else float(minimum_item)
        maximum_constraint = None if maximum_item is None else float(maximum_item)
        if (
            minimum_constraint is not None
            and maximum_constraint is not None
            and minimum_constraint >= maximum_constraint
        ):
            raise ValueError(
                "Optimization Response minimum constraint must be less than maximum"
            )
        records.append(
            _OptimizationResponseRecord(
                id=uuid4(),
                node_id=UUID(int=0),
                name=str(names[index]),
                objective=objectives[index],
                minimum_constraint=minimum_constraint,
                maximum_constraint=maximum_constraint,
            )
        )
    refs = _register_optimization_records(
        ctx,
        tuple(records),
        data_type_id=OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
    )
    warnings = () if len(set(lengths)) == 1 else (_SHORTEST_LIST_WARNING,)
    return NodeResult(outputs={"responses": refs}, warnings=warnings)


@builtin_node_type(
    type_id=PARAMETER_SETUP_NODE_TYPE_ID,
    display_name="Parameter Setup",
    category_path=("Control", "Parameter Optimization"),
    description=(
        "Setup a parameter study that allows to explore and optimize designs "
        "within the given design space."
    ),
    keywords=("optimization", "parameter", "study", "design space"),
    ports=(
        PortSpec(
            "parameters_and_responses",
            "in",
            "data",
            OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
            label="Parameters & Responses",
            required=False,
            description=(
                "Parametric parameters and responses that define the design space. "
                "During optimization or design exploration the parameter values can "
                "be accessed using Parameters Pool node, and the response values "
                "should be set using Response Pool node."
            ),
            data_access="list",
        ),
        PortSpec(
            "output",
            "out",
            "data",
            OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
            label="Parameters & Responses",
            description="Parameters and responses of the created parameter study.",
            data_access="list",
        ),
    ),
    properties=(),
)
class ParameterSetupNodePlugin:

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        raw_variables = ctx.inputs.get("parameters_and_responses")
        if raw_variables is None:
            raw_variables = []
        if type(raw_variables) is not list:
            raise TypeError("Parameter Setup Parameters & Responses must be a list")
        resolved = tuple(
            _resolve_optimization_record(ctx, value) for value in raw_variables
        )
        _require_unique_optimization_records(resolved)
        pool_targets = _parameter_setup_pool_targets(ctx)
        source_parameters = tuple(
            record
            for record in resolved
            if type(record) is _OptimizationParameterRecord
        )
        source_responses = tuple(
            record
            for record in resolved
            if type(record) is _OptimizationResponseRecord
        )
        if source_parameters and PARAMETER_POOL_ROLE not in pool_targets:
            raise ValueError("Parameter Setup requires one Parameter Pool link")
        if source_responses and RESPONSE_POOL_ROLE not in pool_targets:
            raise ValueError("Parameter Setup requires one Response Pool link")

        parameter_node_uuid = (
            pool_targets[PARAMETER_POOL_ROLE][1]
            if PARAMETER_POOL_ROLE in pool_targets
            else UUID(int=0)
        )
        response_node_uuid = (
            pool_targets[RESPONSE_POOL_ROLE][1]
            if RESPONSE_POOL_ROLE in pool_targets
            else UUID(int=0)
        )
        parameters = tuple(
            _OptimizationParameterRecord(
                id=_deterministic_optimization_id(record.name),
                node_id=parameter_node_uuid,
                name=record.name,
                minimum_value=record.minimum_value,
                maximum_value=record.maximum_value,
                decimal_places=record.decimal_places,
            )
            for record in source_parameters
        )
        responses = tuple(
            _OptimizationResponseRecord(
                id=_deterministic_optimization_id(record.name),
                node_id=response_node_uuid,
                name=record.name,
                objective=record.objective,
                minimum_constraint=record.minimum_constraint,
                maximum_constraint=record.maximum_constraint,
            )
            for record in source_responses
        )
        grouped: tuple[
            _OptimizationParameterRecord | _OptimizationResponseRecord, ...
        ] = (*parameters, *responses)
        _require_unique_optimization_records(
            grouped,
            require_unique_names=True,
        )
        refs = _register_mixed_optimization_records(ctx, grouped)

        if PARAMETER_POOL_ROLE in pool_targets:
            ctx.publish_node_state(
                pool_targets[PARAMETER_POOL_ROLE][0],
                _OptimizationParameterPoolState(
                    definitions=parameters,
                    values=tuple(record.minimum_value for record in parameters),
                ),
            )
        if RESPONSE_POOL_ROLE in pool_targets:
            ctx.publish_node_state(
                pool_targets[RESPONSE_POOL_ROLE][0],
                _OptimizationResponsePoolState(
                    definitions=responses,
                    values=(None,) * len(responses),
                ),
            )
        return NodeResult(outputs={"output": refs})


@builtin_node_type(
    type_id=PARAMETER_POOL_NODE_TYPE_ID,
    display_name="Parameter Pool",
    category_path=("Control", "Parameter Optimization"),
    description=(
        "Access the parameter values that are generated by the Optimization or "
        "Design Exploration nodes. This node shows all parameters that are "
        "supplied as an input to Parameter Setup node."
    ),
    keywords=("optimization", "parameter", "pool", "values"),
    ports=(
        PortSpec(
            "names",
            "out",
            "data",
            STRING_DATA_TYPE_ID,
            label="Names",
            description="Names of the parameters.",
            data_access="list",
        ),
        PortSpec(
            "values",
            "out",
            "data",
            DOUBLE_DATA_TYPE_ID,
            label="Values",
            description="Current parameter values.",
            data_access="list",
        ),
        PortSpec(
            "bounds",
            "out",
            "data",
            INTERVAL_1D_GRAPH_DATA_TYPE_ID,
            label="Bounds",
            description="Parameter value boundaries.",
            data_access="list",
        ),
    ),
    properties=(),
)
class ParameterPoolNodePlugin:

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        state = ctx.read_node_state(ctx.node_id)
        if type(state) is not _OptimizationParameterPoolState:
            raise ValueError("Parameter Pool requires Parameter Setup state")
        return NodeResult(
            outputs={
                "names": [record.name for record in state.definitions],
                "values": list(state.values),
                "bounds": [
                    Interval1D(record.minimum_value, record.maximum_value)
                    for record in state.definitions
                ],
            }
        )


@builtin_node_type(
    type_id=RESPONSE_POOL_NODE_TYPE_ID,
    display_name="Response Pool",
    category_path=("Control", "Parameter Optimization"),
    description=(
        "Set the response values calculated during an iteration of Optimization or "
        "Design Exploration nodes. This node expects the same number of values as "
        "the number of responses supplied as an input to Parameter Setup node."
    ),
    keywords=("optimization", "response", "pool", "values"),
    ports=(
        PortSpec(
            "values",
            "in",
            "data",
            DOUBLE_DATA_TYPE_ID,
            label="Values",
            required=False,
            description=(
                "The calculated values of the responses. Null items are preserved "
                "as pending response values."
            ),
            data_access="list",
        ),
    ),
    properties=(),
)
class ResponsePoolNodePlugin:

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        state = ctx.read_node_state(ctx.node_id)
        if type(state) is not _OptimizationResponsePoolState:
            raise ValueError("Response Pool requires Parameter Setup state")
        raw_values = _optional_list_input(
            ctx,
            "values",
            node_label="Response Pool",
        )
        values = (
            (None,) * len(state.definitions)
            if raw_values is None
            else _exact_finite_values(
                ctx,
                raw_values,
                label="Response Pool Values",
                allow_none=True,
            )
        )
        if len(values) != len(state.definitions):
            raise ValueError(
                "Response Pool Values must match the configured response count"
            )
        violation = any(
            value is not None
            and (
                (
                    definition.minimum_constraint is not None
                    and value < definition.minimum_constraint
                )
                or (
                    definition.maximum_constraint is not None
                    and value > definition.maximum_constraint
                )
            )
            for definition, value in zip(state.definitions, values, strict=True)
        )
        ctx.publish_node_state(
            ctx.node_id,
            _OptimizationResponsePoolState(
                definitions=state.definitions,
                values=values,
            ),
        )
        warnings = (
            ("One or more response values violate their constraints.",)
            if violation
            else ()
        )
        return NodeResult(warnings=warnings)


def execute_construct_design(ctx: ExecutionContext) -> NodeResult:
    raw_variables = _required_list_input(
        ctx,
        "parameters_and_responses",
        node_label="Construct Design",
    )
    variables = tuple(
        _resolve_optimization_record(ctx, value) for value in raw_variables
    )
    _require_unique_optimization_records(variables)
    if any(record.node_id.int == 0 for record in variables):
        raise ValueError("Construct Design requires Parameter Setup-bound variables")
    parameters = tuple(
        record
        for record in variables
        if type(record) is _OptimizationParameterRecord
    )
    responses = tuple(
        record
        for record in variables
        if type(record) is _OptimizationResponseRecord
    )

    raw_parameter_values = _optional_list_input(
        ctx,
        "parameter_values",
        node_label="Construct Design",
    )
    parameter_values = (
        tuple(record.minimum_value for record in parameters)
        if raw_parameter_values is None
        else tuple(
            value
            for value in _exact_finite_values(
                ctx,
                raw_parameter_values,
                label="Construct Design Parameter values",
            )
            if value is not None
        )
    )
    if len(parameter_values) != len(parameters):
        raise ValueError(
            "Construct Design Parameter values must match the parameter count"
        )
    if any(
        value < record.minimum_value or value > record.maximum_value
        for record, value in zip(parameters, parameter_values, strict=True)
    ):
        raise ValueError("Construct Design Parameter values must be within bounds")

    raw_response_values = _optional_list_input(
        ctx,
        "response_values",
        node_label="Construct Design",
    )
    response_values = (
        (None,) * len(responses)
        if raw_response_values is None
        else _exact_finite_values(
            ctx,
            raw_response_values,
            label="Construct Design Response values",
        )
    )
    if len(response_values) != len(responses):
        raise ValueError("Construct Design Response values must match the response count")

    parameter_iterator = iter(parameter_values)
    response_iterator = iter(response_values)
    ordered_values = tuple(
        next(parameter_iterator)
        if type(record) is _OptimizationParameterRecord
        else next(response_iterator)
        for record in variables
    )
    raw_name = ctx.inputs.get("name")
    if raw_name is None:
        raw_name = ctx.properties.get("name", "Design")
    string_spec = ctx.worker_services.data_types.require(STRING_DATA_TYPE_ID)
    if not string_spec.validate_item(raw_name):
        raise TypeError("Construct Design Name must be a string")

    design = _OptimizationDesignRecord(
        id=uuid4(),
        name=str(raw_name),
        status=_response_design_status(responses, response_values),
        variables=variables,
        values=ordered_values,
        solution=None,
        screenshot=None,
    )
    design_ref = ctx.register_handle(
        design,
        data_type_id=OPTIMIZATION_DESIGN_DATA_TYPE_ID,
        kind=OPTIMIZATION_DESIGN_HANDLE_KIND,
        metadata={},
    )
    return NodeResult(outputs={"design": design_ref})


COREX_FEM_NODE_DESCRIPTORS = (
    plugin_descriptor(ParameterSetupNodePlugin),
    plugin_descriptor(ParameterPoolNodePlugin),
    plugin_descriptor(ResponsePoolNodePlugin),
)
