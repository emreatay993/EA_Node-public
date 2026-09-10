from __future__ import annotations

from dataclasses import asdict, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from ea_node_editor.common.optimization_links import (
    PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
    PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE,
    PARAMETER_SETUP_RESPONSE_POOL_LINK_ID,
    PARAMETER_SETUP_RESPONSE_POOL_LINK_TITLE,
)
from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtin_functions import engineering_fem, engineering_geometry
from ea_node_editor.nodes.builtins import fem_contracts as fem_module
from ea_node_editor.nodes.builtins.fem_contracts import (
    CONSTRAINT_DATA_TYPE_ID,
    CONSTRUCT_DESIGN_NODE_TYPE_ID,
    CONSTRUCT_PARAMETERS_NODE_TYPE_ID,
    CONSTRUCT_RESPONSES_NODE_TYPE_ID,
    ELEMENT_DATA_TYPE_ID,
    ELEMENT_QUALITY_CRITERIA_DATA_TYPE_ID,
    FIXED_DISPLACEMENT_DATA_TYPE_ID,
    FORCE_DATA_TYPE_ID,
    FORCE_HANDLE_KIND,
    FORCE_NODE_TYPE_ID,
    LINEAR_STATIC_MECHANICAL_DATA_TYPE_ID,
    LOAD_CONTAINER_NODE_TYPE_ID,
    LOAD_DATA_TYPE_ID,
    LOAD_STEP_DATA_TYPE_ID,
    NODE_DATA_TYPE_ID,
    OBJECTIVE_DATA_TYPE_ID,
    OPTIMIZATION_DESIGN_DATA_TYPE_ID,
    OPTIMIZATION_DESIGN_HANDLE_KIND,
    OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
    OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
    OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
    OPTIMIZATION_VARIABLE_HANDLE_KIND,
    PARAMETER_POOL_NODE_TYPE_ID,
    PARAMETER_SETUP_NODE_TYPE_ID,
    PRESSURE_DATA_TYPE_ID,
    RESPONSE_DATA_TYPE_ID,
    RESPONSE_POOL_NODE_TYPE_ID,
    STEADY_STATE_HEAT_TRANSFER_DATA_TYPE_ID,
    COREX_FEM_CONTRACT_MANIFEST,
    COREX_FEM_CONTRACTS_OWNER_ID,
    COREX_FEM_CONTRACTS_OWNER_VERSION,
    COREX_FEM_DATA_TYPES,
    VARIABLE_DATA_TYPE_ID,
)
from ea_node_editor.nodes.builtins.geometry_primitives import (
    CYLINDER_NODE_TYPE_ID,
    OCP_BODY_DATA_TYPE_ID,
    OCP_BODY_HANDLE_KIND,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import PLANE_DATA_TYPE_ID
from ea_node_editor.nodes.builtins.spatial_values import (
    make_vector3d_value,
)
from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalogError,
    Interval1D,
    RuntimeHandleRef,
    TypedInlineValue,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog

_CONVERTED_TYPE_IDS = (
    "fea.force",
    "fea.load_container",
    "optimization.construct_parameters",
    "optimization.construct_responses",
    "optimization.construct_design",
)
@lru_cache(maxsize=1)
def _function_adapters() -> dict[str, PythonFunctionAdapter]:
    adapters: dict[str, PythonFunctionAdapter] = {}
    for filename, source in (
        ("engineering_geometry.py", engineering_geometry.SOURCE),
        ("engineering_fem.py", engineering_fem.SOURCE),
    ):
        namespace: dict[str, object] = {}
        exec(compile(source, filename, "exec"), namespace)
        for declaration in discover_plugin_declarations(
            source,
            filename=filename,
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        ):
            adapters[declaration.spec.type_id] = PythonFunctionAdapter(
                declaration.spec,
                namespace[declaration.function_name],  # type: ignore[arg-type]
            )
    return adapters


def test_fem_function_declarations_match_golden() -> None:
    declarations = discover_plugin_declarations(
        engineering_fem.SOURCE,
        filename="engineering_fem.py",
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

_EXPECTED_CONTACT_PAIR_TYPE_ROWS = (
    (
        "COREX.Fem.ContactPairs.IContactPair",
        "Contact Pair",
        GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.ContactPairs.IContactPairSettings",
        "Contact Pair Settings",
        GRAPH_DATA_TYPE_ID,
    ),
)

_EXPECTED_CROSS_SECTION_TYPE_ROWS = (
    (
        "COREX.Fem.CrossSections.ICrossSection",
        "Cross Section",
        GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Optimization.Variables.ICrossSectionVariable",
        "Cross Section Variable",
        VARIABLE_DATA_TYPE_ID,
    ),
)

_EXPECTED_FEM_SUPPORT_TYPE_ROWS = (
    (
        "COREX.Fem.Model.ISet",
        "Set",
        GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Settings.IModelSetting",
        "Model Setting",
        GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Settings.ILsDynaModelSetting",
        "LS-DYNA Model Setting",
        "COREX.Fem.Settings.IModelSetting",
    ),
    (
        "COREX.Fem.TabularCurves.ITabularCurve",
        "Tabular Curve",
        GRAPH_DATA_TYPE_ID,
    ),
)

_EXPECTED_ELEMENT_SUBINTERFACE_TYPE_ROWS = (
    (
        "COREX.Fem.Elements.IIndependentElement",
        "Independent Element",
        ELEMENT_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Elements.IPointMass",
        "Point Mass",
        "COREX.Fem.Elements.IIndependentElement",
    ),
    (
        "COREX.Fem.Elements.ISpotWeld",
        "Spot Weld",
        "COREX.Fem.Elements.IIndependentElement",
    ),
    (
        "COREX.Fem.Elements.ISpring",
        "Spring",
        "COREX.Fem.Elements.IIndependentElement",
    ),
)

_EXPECTED_MATERIAL_TYPE_ROWS = (
    (
        "COREX.Fem.Materials.IMaterial",
        "Material",
        GRAPH_DATA_TYPE_ID,
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
        GRAPH_DATA_TYPE_ID,
    ),
    (
        "COREX.Fem.Materials.IMaterialFailureSettings",
        "Material Failure Settings",
        GRAPH_DATA_TYPE_ID,
    ),
)

_EXPECTED_OPTIMIZATION_RESPONSE_TYPE_ROWS = (
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


def _register_candidate(registry: NodeRegistry) -> None:
    registry.register_plugin_bundle(
        COREX_FEM_CONTRACT_MANIFEST,
        (),
        owner_id=COREX_FEM_CONTRACTS_OWNER_ID,
        owner_version=COREX_FEM_CONTRACTS_OWNER_VERSION,
        source_label=fem_module.__name__,
    )






def test_exact_abstract_and_concrete_handle_specs_are_bounded() -> None:
    (
        load_step_spec,
        load_spec,
        fixed_displacement_spec,
        pressure_spec,
        force_spec,
        linear_static_spec,
        steady_state_spec,
    ) = COREX_FEM_DATA_TYPES[:7]
    contact_pair_specs = COREX_FEM_DATA_TYPES[7:9]
    (
        node_spec,
        element_spec,
    ) = COREX_FEM_DATA_TYPES[9:11]
    element_subinterface_specs = COREX_FEM_DATA_TYPES[11:15]
    material_specs = COREX_FEM_DATA_TYPES[15:22]
    response_spec = COREX_FEM_DATA_TYPES[22]
    optimization_response_specs = COREX_FEM_DATA_TYPES[23:42]
    (
        constraint_spec,
        objective_spec,
        variable_spec,
    ) = COREX_FEM_DATA_TYPES[42:45]
    cross_section_specs = COREX_FEM_DATA_TYPES[45:47]
    fem_support_specs = COREX_FEM_DATA_TYPES[47:51]
    (
        optimization_variable_spec,
        optimization_parameter_spec,
        optimization_workflow_response_spec,
        optimization_design_spec,
    ) = COREX_FEM_DATA_TYPES[51:55]
    assert (
        load_step_spec.type_id,
        load_step_spec.display_name,
        load_step_spec.family_id,
        load_step_spec.parents,
        load_step_spec.abstract,
        load_step_spec.carriers,
        load_step_spec.persistence,
        load_step_spec.sensitivity,
        load_step_spec.payload_schema_version,
        load_step_spec.implementation_version,
        load_step_spec.description,
        load_step_spec.capabilities,
        load_step_spec.coerce_untyped_input,
    ) == (
        LOAD_STEP_DATA_TYPE_ID,
        "Load Step",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
        "",
        frozenset(),
        None,
    )
    assert (
        load_spec.type_id,
        load_spec.display_name,
        load_spec.family_id,
        load_spec.parents,
        load_spec.abstract,
        load_spec.carriers,
        load_spec.persistence,
        load_spec.sensitivity,
        load_spec.payload_schema_version,
        load_spec.implementation_version,
    ) == (
        LOAD_DATA_TYPE_ID,
        "Load",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
    )
    assert (
        force_spec.type_id,
        force_spec.display_name,
        force_spec.family_id,
        force_spec.parents,
        force_spec.abstract,
        force_spec.carriers,
        force_spec.persistence,
        force_spec.sensitivity,
        force_spec.payload_schema_version,
        force_spec.implementation_version,
    ) == (
        FORCE_DATA_TYPE_ID,
        "Force",
        "engineering",
        (LOAD_DATA_TYPE_ID,),
        False,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
    )

    for spec, type_id, display_name, parents in (
        (
            fixed_displacement_spec,
            FIXED_DISPLACEMENT_DATA_TYPE_ID,
            "Fixed Displacement",
            (LOAD_DATA_TYPE_ID,),
        ),
        (
            pressure_spec,
            PRESSURE_DATA_TYPE_ID,
            "Pressure",
            (LOAD_DATA_TYPE_ID,),
        ),
        (
            linear_static_spec,
            LINEAR_STATIC_MECHANICAL_DATA_TYPE_ID,
            "Linear Static Mechanical",
            (LOAD_STEP_DATA_TYPE_ID,),
        ),
        (
            steady_state_spec,
            STEADY_STATE_HEAT_TRANSFER_DATA_TYPE_ID,
            "Steady State Heat Transfer",
            (LOAD_STEP_DATA_TYPE_ID,),
        ),
        (node_spec, NODE_DATA_TYPE_ID, "Node", (GRAPH_DATA_TYPE_ID,)),
        (element_spec, ELEMENT_DATA_TYPE_ID, "Element", (GRAPH_DATA_TYPE_ID,)),
        (response_spec, RESPONSE_DATA_TYPE_ID, "Response", (GRAPH_DATA_TYPE_ID,)),
        (
            constraint_spec,
            CONSTRAINT_DATA_TYPE_ID,
            "Constraint",
            (GRAPH_DATA_TYPE_ID,),
        ),
        (
            objective_spec,
            OBJECTIVE_DATA_TYPE_ID,
            "Objective",
            (GRAPH_DATA_TYPE_ID,),
        ),
        (variable_spec, VARIABLE_DATA_TYPE_ID, "Variable", (GRAPH_DATA_TYPE_ID,)),
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            parents,
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(contact_pair_specs) == 2
    for spec, (type_id, display_name, parent_type_id) in zip(
        contact_pair_specs,
        _EXPECTED_CONTACT_PAIR_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (parent_type_id,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(element_subinterface_specs) == 4
    for spec, (type_id, display_name, parent_type_id) in zip(
        element_subinterface_specs,
        _EXPECTED_ELEMENT_SUBINTERFACE_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (parent_type_id,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(material_specs) == 7
    for spec, (type_id, display_name, parent_type_id) in zip(
        material_specs,
        _EXPECTED_MATERIAL_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (parent_type_id,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(optimization_response_specs) == 19
    for spec, (type_id, display_name) in zip(
        optimization_response_specs,
        _EXPECTED_OPTIMIZATION_RESPONSE_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (RESPONSE_DATA_TYPE_ID,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(cross_section_specs) == 2
    for spec, (type_id, display_name, parent_type_id) in zip(
        cross_section_specs,
        _EXPECTED_CROSS_SECTION_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (parent_type_id,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert len(fem_support_specs) == 4
    for spec, (type_id, display_name, parent_type_id) in zip(
        fem_support_specs,
        _EXPECTED_FEM_SUPPORT_TYPE_ROWS,
        strict=True,
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (parent_type_id,),
            True,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert (
        optimization_variable_spec.type_id,
        optimization_variable_spec.display_name,
        optimization_variable_spec.family_id,
        optimization_variable_spec.parents,
        optimization_variable_spec.abstract,
        optimization_variable_spec.carriers,
        optimization_variable_spec.persistence,
        optimization_variable_spec.sensitivity,
        optimization_variable_spec.payload_schema_version,
        optimization_variable_spec.implementation_version,
    ) == (
        OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
        "Optimization Variable",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        True,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
    )
    for spec, type_id, display_name in (
        (
            optimization_parameter_spec,
            OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
            "Optimization Parameter",
        ),
        (
            optimization_workflow_response_spec,
            OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
            "Optimization Response",
        ),
    ):
        assert (
            spec.type_id,
            spec.display_name,
            spec.family_id,
            spec.parents,
            spec.abstract,
            spec.carriers,
            spec.persistence,
            spec.sensitivity,
            spec.payload_schema_version,
            spec.implementation_version,
            spec.description,
            spec.capabilities,
            spec.coerce_untyped_input,
        ) == (
            type_id,
            display_name,
            "engineering",
            (OPTIMIZATION_VARIABLE_DATA_TYPE_ID,),
            False,
            frozenset({"handle"}),
            "never",
            "normal",
            1,
            "1",
            "",
            frozenset(),
            None,
        )

    assert (
        optimization_design_spec.type_id,
        optimization_design_spec.display_name,
        optimization_design_spec.family_id,
        optimization_design_spec.parents,
        optimization_design_spec.abstract,
        optimization_design_spec.carriers,
        optimization_design_spec.persistence,
        optimization_design_spec.sensitivity,
        optimization_design_spec.payload_schema_version,
        optimization_design_spec.implementation_version,
    ) == (
        OPTIMIZATION_DESIGN_DATA_TYPE_ID,
        "Optimization Design",
        "engineering",
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"handle"}),
        "never",
        "normal",
        1,
        "1",
    )

    registry = NodeRegistry()
    _register_candidate(registry)
    assert registry.data_types.is_assignable(
        FIXED_DISPLACEMENT_DATA_TYPE_ID, LOAD_DATA_TYPE_ID
    )
    assert registry.data_types.is_assignable(
        PRESSURE_DATA_TYPE_ID, LOAD_DATA_TYPE_ID
    )
    assert registry.data_types.is_assignable(
        LINEAR_STATIC_MECHANICAL_DATA_TYPE_ID, LOAD_STEP_DATA_TYPE_ID
    )
    assert registry.data_types.is_assignable(
        STEADY_STATE_HEAT_TRANSFER_DATA_TYPE_ID, LOAD_STEP_DATA_TYPE_ID
    )
    contact_pair_type_ids = tuple(
        type_id
        for type_id, _display_name, _parent_type_id in _EXPECTED_CONTACT_PAIR_TYPE_ROWS
    )
    for source_type_id in contact_pair_type_ids:
        assert registry.data_types.is_assignable(source_type_id, GRAPH_DATA_TYPE_ID)
        for target_type_id in contact_pair_type_ids:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    assert registry.data_types.is_assignable(NODE_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID)
    assert registry.data_types.is_assignable(ELEMENT_DATA_TYPE_ID, GRAPH_DATA_TYPE_ID)
    independent_element_type_id = _EXPECTED_ELEMENT_SUBINTERFACE_TYPE_ROWS[0][0]
    assert registry.data_types.is_assignable(
        independent_element_type_id, ELEMENT_DATA_TYPE_ID
    )
    element_sibling_type_ids = tuple(
        type_id for type_id, _display_name, _parent_type_id in (
            _EXPECTED_ELEMENT_SUBINTERFACE_TYPE_ROWS[1:]
        )
    )
    for source_type_id in element_sibling_type_ids:
        assert registry.data_types.is_assignable(
            source_type_id, independent_element_type_id
        )
        assert registry.data_types.is_assignable(source_type_id, ELEMENT_DATA_TYPE_ID)
        for target_type_id in element_sibling_type_ids:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    material_type_id = _EXPECTED_MATERIAL_TYPE_ROWS[0][0]
    assert registry.data_types.is_assignable(material_type_id, GRAPH_DATA_TYPE_ID)
    material_leaf_type_ids = tuple(
        type_id
        for type_id, _display_name, _parent_type_id in _EXPECTED_MATERIAL_TYPE_ROWS[1:5]
    )
    for source_type_id in material_leaf_type_ids:
        assert registry.data_types.is_assignable(source_type_id, material_type_id)
        assert registry.data_types.is_assignable(source_type_id, GRAPH_DATA_TYPE_ID)
        for target_type_id in material_leaf_type_ids:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    material_settings_type_ids = tuple(
        type_id
        for type_id, _display_name, _parent_type_id in _EXPECTED_MATERIAL_TYPE_ROWS[5:]
    )
    for source_type_id in material_settings_type_ids:
        assert registry.data_types.is_assignable(source_type_id, GRAPH_DATA_TYPE_ID)
        assert not registry.data_types.is_assignable(source_type_id, material_type_id)
        for target_type_id in (
            *material_leaf_type_ids,
            *material_settings_type_ids,
        ):
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    optimization_response_type_ids = tuple(
        type_id for type_id, _display_name in _EXPECTED_OPTIMIZATION_RESPONSE_TYPE_ROWS
    )
    for source_type_id in optimization_response_type_ids:
        assert registry.data_types.is_assignable(
            source_type_id, RESPONSE_DATA_TYPE_ID
        )
        for target_type_id in optimization_response_type_ids:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    optimization_roots = (
        RESPONSE_DATA_TYPE_ID,
        CONSTRAINT_DATA_TYPE_ID,
        OBJECTIVE_DATA_TYPE_ID,
        VARIABLE_DATA_TYPE_ID,
    )
    for source_type_id in optimization_roots:
        for target_type_id in optimization_roots:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (source_type_id == target_type_id)
    cross_section_type_id, cross_section_variable_type_id = (
        type_id
        for type_id, _display_name, _parent_type_id in (
            _EXPECTED_CROSS_SECTION_TYPE_ROWS
        )
    )
    assert registry.data_types.is_assignable(
        cross_section_type_id, GRAPH_DATA_TYPE_ID
    )
    assert registry.data_types.is_assignable(
        cross_section_variable_type_id, VARIABLE_DATA_TYPE_ID
    )
    assert registry.data_types.is_assignable(
        cross_section_variable_type_id, GRAPH_DATA_TYPE_ID
    )
    for source_type_id, target_type_id in (
        (cross_section_type_id, cross_section_variable_type_id),
        (cross_section_variable_type_id, cross_section_type_id),
        (cross_section_type_id, VARIABLE_DATA_TYPE_ID),
        (cross_section_type_id, RESPONSE_DATA_TYPE_ID),
        (cross_section_type_id, CONSTRAINT_DATA_TYPE_ID),
        (cross_section_type_id, OBJECTIVE_DATA_TYPE_ID),
        (VARIABLE_DATA_TYPE_ID, cross_section_variable_type_id),
        (cross_section_variable_type_id, RESPONSE_DATA_TYPE_ID),
        (cross_section_variable_type_id, CONSTRAINT_DATA_TYPE_ID),
        (cross_section_variable_type_id, OBJECTIVE_DATA_TYPE_ID),
    ):
        assert not registry.data_types.is_assignable(source_type_id, target_type_id)
    fem_support_type_ids = tuple(
        type_id
        for type_id, _display_name, _parent_type_id in _EXPECTED_FEM_SUPPORT_TYPE_ROWS
    )
    model_setting_type_id = fem_support_type_ids[1]
    expected_support_targets = {
        fem_support_type_ids[0]: {fem_support_type_ids[0]},
        model_setting_type_id: {model_setting_type_id},
        fem_support_type_ids[2]: {
            model_setting_type_id,
            fem_support_type_ids[2],
        },
        fem_support_type_ids[3]: {fem_support_type_ids[3]},
    }
    for source_type_id in fem_support_type_ids:
        assert registry.data_types.is_assignable(source_type_id, GRAPH_DATA_TYPE_ID)
        for target_type_id in fem_support_type_ids:
            assert registry.data_types.is_assignable(
                source_type_id, target_type_id
            ) is (target_type_id in expected_support_targets[source_type_id])
    for concrete_type_id in (
        OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
        OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
    ):
        assert registry.data_types.is_assignable(
            concrete_type_id, OPTIMIZATION_VARIABLE_DATA_TYPE_ID
        )
        assert registry.data_types.is_assignable(concrete_type_id, GRAPH_DATA_TYPE_ID)
    assert not registry.data_types.is_assignable(
        OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
        OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
    )
    assert not registry.data_types.is_assignable(
        OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
        OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
    )
    assert not registry.data_types.is_assignable(
        OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
        VARIABLE_DATA_TYPE_ID,
    )
    assert not registry.data_types.is_assignable(
        VARIABLE_DATA_TYPE_ID,
        OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
    )
    assert registry.data_types.is_assignable(
        OPTIMIZATION_DESIGN_DATA_TYPE_ID,
        GRAPH_DATA_TYPE_ID,
    )
    assert not registry.data_types.is_assignable(
        OPTIMIZATION_DESIGN_DATA_TYPE_ID,
        OPTIMIZATION_VARIABLE_DATA_TYPE_ID,
    )


def test_element_quality_criteria_has_strict_inline_schema() -> None:
    spec = COREX_FEM_DATA_TYPES[-1]
    assert (
        spec.type_id,
        spec.parents,
        spec.abstract,
        spec.carriers,
        spec.persistence,
        spec.sensitivity,
        spec.payload_schema_version,
        spec.implementation_version,
    ) == (
        ELEMENT_QUALITY_CRITERIA_DATA_TYPE_ID,
        (GRAPH_DATA_TYPE_ID,),
        False,
        frozenset({"inline"}),
        "inline",
        "normal",
        1,
        "1",
    )

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
    payload = {
        "MinimumEdgeLength": 0.0,
        **{
            name: {
                "AspectRatioUpperBound": 1.0,
                "MinimumInternalAngle": 0.0,
            }
            for name in pair_names
        },
        **{
            name: {
                "AspectRatioUpperBound": 1.0,
                "QuadMinimumInternalAngle": 0.0,
                "TriaMinimumInternalAngle": 0.0,
            }
            for name in triple_names
        },
    }
    assert spec.validate_item(payload)

    invalid_payloads = (
        MappingProxyType(payload),
        payload | {"Extra": 0.0},
        {key: value for key, value in payload.items() if key != "Hexa20"},
        payload | {"MinimumEdgeLength": True},
        payload | {"MinimumEdgeLength": "0.0"},
        payload | {"MinimumEdgeLength": float("nan")},
        payload | {"Hexa20": None},
        payload | {"Hexa20": []},
        payload
        | {
            "Hexa20": {
                **payload["Hexa20"],
                "Extra": 0.0,
            }
        },
        payload | {"Hexa20": {"AspectRatioUpperBound": 1.0}},
        payload
        | {
            "Hexa20": {
                **payload["Hexa20"],
                "MinimumInternalAngle": True,
            }
        },
        payload
        | {
            "Hexa20": {
                **payload["Hexa20"],
                "MinimumInternalAngle": "0.0",
            }
        },
        payload
        | {
            "Hexa20": {
                **payload["Hexa20"],
                "MinimumInternalAngle": float("inf"),
            }
        },
        payload
        | {
            "Prism15": {
                **payload["Prism15"],
                "TriaMinimumInternalAngle": float("-inf"),
            }
        },
    )
    assert all(not spec.validate_item(candidate) for candidate in invalid_payloads)


def test_abstract_validators_and_exact_handles_reject() -> None:
    registry = NodeRegistry()
    _register_candidate(registry)
    for spec in (spec for spec in COREX_FEM_DATA_TYPES if spec.abstract):
        for value in (None, object(), "abstract", {"id": "abstract"}):
            assert spec.validate_item(value) is False
        handle = RuntimeHandleRef(
            data_type_id=spec.type_id,
            schema_version=1,
            handle_id="abstract-fem-test",
            kind="test.abstract_fem",
            owner_scope="run:test",
            worker_generation=1,
            metadata={},
        )
        assert spec.validate_item(handle) is False
        with pytest.raises(DataTypeCatalogError, match="must be concrete"):
            registry.data_types.validate_carrier(spec.type_id, handle)

    force_handle = RuntimeHandleRef(
        data_type_id=FORCE_DATA_TYPE_ID,
        schema_version=1,
        handle_id="force-test",
        kind=FORCE_HANDLE_KIND,
        owner_scope="run:test",
        worker_generation=1,
        metadata={},
    )
    assert COREX_FEM_DATA_TYPES[4].validate_item(force_handle)
    assert not COREX_FEM_DATA_TYPES[4].validate_item(
        replace(force_handle, metadata={"shape": "forbidden"})
    )


def test_construct_optimization_variables_match_workflow_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = build_builtin_registry()
    services = WorkerServices()
    services.bind_data_types(registry.data_types)

    def context(node_id: str, inputs: dict[str, object]) -> ExecutionContext:
        return ExecutionContext(
            run_id="optimization-run",
            node_id=node_id,
            workspace_id="optimization-workspace",
            inputs=inputs,
            properties={},
            emit_log=lambda _level, _message: None,
            worker_services=services,
        )

    construct_parameters = _function_adapters()[CONSTRUCT_PARAMETERS_NODE_TYPE_ID]
    parameter_result = construct_parameters.execute(
        context(
            "construct-parameters",
            {
                "names": ["Parameter A", "", "unused"],
                "minimum_values": [2.5, 1.234],
                "maximum_values": [3.5, 9.876],
                "decimal_places": [0, 2],
            },
        )
    )
    truncation_warning = (
        "Input list lengths differ; output was truncated to the shortest "
        "participating list."
    )
    assert parameter_result.warnings == (truncation_warning,)
    parameter_refs = parameter_result.outputs["parameters"]
    assert type(parameter_refs) is list
    assert len(parameter_refs) == 2
    parameter_records = [
        services.resolve_handle(
            ref,
            expected_data_type=OPTIMIZATION_PARAMETER_DATA_TYPE_ID,
            expected_kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
        )
        for ref in parameter_refs
    ]
    assert [
        (
            record.name,
            record.minimum_value,
            record.maximum_value,
            record.decimal_places,
        )
        for record in parameter_records
    ] == [
        ("Parameter A", 2.0, 4.0, 0),
        ("", 1.23, 9.88, 2),
    ]
    assert all(type(record.id) is UUID and record.id.int != 0 for record in parameter_records)
    assert len({record.id for record in parameter_records}) == 2
    assert all(type(record.node_id) is UUID and record.node_id.int == 0 for record in parameter_records)
    assert parameter_records[0].__dataclass_params__.frozen
    assert not hasattr(parameter_records[0], "__dict__")
    assert all(
        type(ref) is RuntimeHandleRef
        and ref.data_type_id == OPTIMIZATION_PARAMETER_DATA_TYPE_ID
        and ref.kind == OPTIMIZATION_VARIABLE_HANDLE_KIND
        and ref.metadata == {}
        for ref in parameter_refs
    )

    construct_responses = _function_adapters()[CONSTRUCT_RESPONSES_NODE_TYPE_ID]
    response_result = construct_responses.execute(
        context(
            "construct-responses",
            {
                "names": ["Response A", "Response B", "unused"],
                "objectives": [0, 1, 2],
                "minimum_constraints": [None, 1.234567],
                "maximum_constraints": [10.0, None, 99.0],
            },
        )
    )
    assert response_result.warnings == (truncation_warning,)
    response_refs = response_result.outputs["responses"]
    assert type(response_refs) is list
    assert len(response_refs) == 2
    response_records = [
        services.resolve_handle(
            ref,
            expected_data_type=OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
            expected_kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
        )
        for ref in response_refs
    ]
    assert [
        (
            record.name,
            record.objective,
            record.minimum_constraint,
            record.maximum_constraint,
        )
        for record in response_records
    ] == [
        ("Response A", 0, None, 10.0),
        ("Response B", 1, 1.234567, None),
    ]
    assert all(type(record.id) is UUID and record.id.int != 0 for record in response_records)
    assert len({record.id for record in (*parameter_records, *response_records)}) == 4
    assert all(type(record.node_id) is UUID and record.node_id.int == 0 for record in response_records)
    assert response_records[0].__dataclass_params__.frozen
    assert not hasattr(response_records[0], "__dict__")
    assert all(
        ref.data_type_id == OPTIMIZATION_RESPONSE_DATA_TYPE_ID
        and ref.kind == OPTIMIZATION_VARIABLE_HANDLE_KIND
        and ref.metadata == {}
        for ref in response_refs
    )

    unconstrained_result = construct_responses.execute(
        context(
            "construct-unconstrained-responses",
            {
                "names": ["Free A", "Free B"],
                "objectives": [2, 0],
                "minimum_constraints": [],
            },
        )
    )
    assert unconstrained_result.warnings == ()
    unconstrained_refs = unconstrained_result.outputs["responses"]
    unconstrained_records = [
        services.resolve_handle(
            ref,
            expected_data_type=OPTIMIZATION_RESPONSE_DATA_TYPE_ID,
            expected_kind=OPTIMIZATION_VARIABLE_HANDLE_KIND,
        )
        for ref in unconstrained_refs
    ]
    assert [
        (record.name, record.minimum_constraint, record.maximum_constraint)
        for record in unconstrained_records
    ] == [("Free A", None, None), ("Free B", None, None)]

    active_count = services.handle_registry.active_handle_count
    invalid_parameter_inputs = (
        {
            "names": [],
            "minimum_values": [0.0],
            "maximum_values": [1.0],
            "decimal_places": [2],
        },
        {
            "names": ["P"],
            "minimum_values": [0.0],
            "maximum_values": [1.0],
            "decimal_places": [True],
        },
        {
            "names": ["P"],
            "minimum_values": [0.0],
            "maximum_values": [1.0],
            "decimal_places": [16],
        },
        {
            "names": ["P"],
            "minimum_values": [2.49],
            "maximum_values": [2.5],
            "decimal_places": [0],
        },
    )
    for inputs in invalid_parameter_inputs:
        with pytest.raises((TypeError, ValueError)):
            construct_parameters.execute(context("invalid-parameters", inputs))
        assert services.handle_registry.active_handle_count == active_count

    invalid_response_inputs = (
        {"names": ["R"], "objectives": [True]},
        {"names": ["R"], "objectives": [3]},
        {"names": ["R"], "objectives": ["bad"]},
        {
            "names": ["R"],
            "objectives": [0],
            "minimum_constraints": [5.0],
            "maximum_constraints": [5.0],
        },
    )
    for inputs in invalid_response_inputs:
        with pytest.raises((TypeError, ValueError)):
            construct_responses.execute(context("invalid-responses", inputs))
        assert services.handle_registry.active_handle_count == active_count

    original_register_handle = WorkerServices.register_handle
    register_calls = 0

    def fail_second_register(
        worker_services: WorkerServices,
        value: object,
        **kwargs: object,
    ) -> RuntimeHandleRef:
        nonlocal register_calls
        register_calls += 1
        if register_calls == 2:
            raise RuntimeError("injected optimization registration failure")
        return original_register_handle(worker_services, value, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(WorkerServices, "register_handle", fail_second_register)
        with pytest.raises(RuntimeError, match="injected optimization registration failure"):
            construct_parameters.execute(
                context(
                    "rollback-parameters",
                    {
                        "names": ["Rollback A", "Rollback B"],
                        "minimum_values": [0.0, 1.0],
                        "maximum_values": [1.0, 2.0],
                        "decimal_places": [2, 2],
                    },
                )
            )
    assert register_calls == 2
    assert services.handle_registry.active_handle_count == active_count

    all_refs = [*parameter_refs, *response_refs, *unconstrained_refs]
    assert services.cleanup_run("optimization-run") == len(all_refs)
    assert services.handle_registry.active_handle_count == 0
    for ref in all_refs:
        with pytest.raises(StaleHandleError):
            services.resolve_handle(ref)


def test_parameter_setup_pools_and_construct_design_form_a_worker_local_chain() -> None:
    radius_id = fem_module._deterministic_optimization_id("Radius")
    assert radius_id == fem_module._deterministic_optimization_id("Radius")
    assert radius_id.version == 5
    assert radius_id != fem_module._deterministic_optimization_id("Height")
    assert radius_id != fem_module._deterministic_optimization_id("Stress response")
    literal_node_uuid = UUID("bc409e14-a8d4-48af-945a-b10679ca1ddc")
    assert fem_module._optimization_node_uuid(
        "workspace",
        str(literal_node_uuid),
    ) == literal_node_uuid
    with pytest.raises(ValueError, match="must be nonzero"):
        fem_module._optimization_node_uuid("workspace", str(UUID(int=0)))
    assert (
        fem_module._DESIGN_STATUS_REFERENCE,
        fem_module._DESIGN_STATUS_PENDING,
        fem_module._DESIGN_STATUS_ERROR_PARAMETERS,
        fem_module._DESIGN_STATUS_ERROR_RESPONSES,
        fem_module._DESIGN_STATUS_INFEASIBLE,
        fem_module._DESIGN_STATUS_COMPUTED,
        fem_module._DESIGN_STATUS_FEASIBLE,
    ) == (-1, 0, 1, 2, 3, 4, 5)

    registry = build_builtin_registry()
    services = WorkerServices()
    services.bind_data_types(registry.data_types)
    workspace_id = "optimization-design-workspace"
    setup_id = "c3339e36-159d-4f68-8068-fe26c23cfe1e"
    parameter_pool_id = "node_parameter_pool"
    response_pool_id = "node_response_pool"
    design_node_id = "node_construct_design"
    workspace_node_types = MappingProxyType(
        {
            setup_id: PARAMETER_SETUP_NODE_TYPE_ID,
            parameter_pool_id: PARAMETER_POOL_NODE_TYPE_ID,
            response_pool_id: RESPONSE_POOL_NODE_TYPE_ID,
            design_node_id: CONSTRUCT_DESIGN_NODE_TYPE_ID,
        }
    )
    run_state: dict[str, object] = {}

    def context(
        node_id: str,
        inputs: dict[str, object],
        *,
        properties: dict[str, object] | None = None,
        semantic_links: tuple[dict[str, object], ...] = (),
    ) -> ExecutionContext:
        return ExecutionContext(
            run_id="design-run",
            node_id=node_id,
            workspace_id=workspace_id,
            inputs=inputs,
            properties={} if properties is None else properties,
            emit_log=lambda _level, _message: None,
            worker_services=services,
            semantic_links=tuple(
                MappingProxyType(dict(link)) for link in semantic_links
            ),
            workspace_node_types=workspace_node_types,
            _publish_node_state=run_state.__setitem__,
            _read_node_state=run_state.get,
        )

    construct_parameters = _function_adapters()[CONSTRUCT_PARAMETERS_NODE_TYPE_ID]
    direct_parameter_refs = construct_parameters.execute(
        context(
            "construct-parameters",
            {
                "names": ["Radius", "Height"],
                "minimum_values": [1.0, 2.0],
                "maximum_values": [5.0, 8.0],
                "decimal_places": [2, 2],
            },
        )
    ).outputs["parameters"]
    construct_responses = _function_adapters()[CONSTRUCT_RESPONSES_NODE_TYPE_ID]
    direct_response_refs = construct_responses.execute(
        context(
            "construct-responses",
            {
                "names": ["Stress response", "Free response"],
                "objectives": [0, 0],
                "minimum_constraints": [10.0, None],
                "maximum_constraints": [20.0, None],
            },
        )
    ).outputs["responses"]
    direct_records = [
        services.resolve_handle(ref) for ref in [
            *direct_parameter_refs,
            *direct_response_refs,
        ]
    ]
    assert all(record.node_id.int == 0 for record in direct_records)

    construct_design = _function_adapters()[CONSTRUCT_DESIGN_NODE_TYPE_ID]
    active_count = services.handle_registry.active_handle_count
    with pytest.raises(ValueError, match="Parameter Setup-bound"):
        construct_design.execute(
            context(
                design_node_id,
                {"parameters_and_responses": direct_parameter_refs},
            )
        )
    assert services.handle_registry.active_handle_count == active_count

    links = (
        {
            "id": PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
            "kind": "node",
            "title": PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE,
            "target": parameter_pool_id,
            "subtitle": "",
            "target_workspace_id": workspace_id,
            "target_node_id": parameter_pool_id,
        },
        {
            "id": PARAMETER_SETUP_RESPONSE_POOL_LINK_ID,
            "kind": "node",
            "title": PARAMETER_SETUP_RESPONSE_POOL_LINK_TITLE,
            "target": response_pool_id,
            "subtitle": "",
            "target_workspace_id": workspace_id,
            "target_node_id": response_pool_id,
        },
    )
    parameter_setup = registry.get_descriptor(
        PARAMETER_SETUP_NODE_TYPE_ID
    ).factory()
    interleaved_refs = [
        direct_response_refs[0],
        direct_parameter_refs[0],
        direct_response_refs[1],
        direct_parameter_refs[1],
    ]
    setup_result = parameter_setup.execute(
        context(
            setup_id,
            {"parameters_and_responses": interleaved_refs},
            semantic_links=links,
        )
    )
    setup_refs = setup_result.outputs["output"]
    assert type(setup_refs) is list
    assert len(setup_refs) == 4
    setup_records = [services.resolve_handle(ref) for ref in setup_refs]
    assert [record.name for record in setup_records] == [
        "Radius",
        "Height",
        "Stress response",
        "Free response",
    ]
    assert [record.id for record in setup_records] == [
        fem_module._deterministic_optimization_id("Radius"),
        fem_module._deterministic_optimization_id("Height"),
        fem_module._deterministic_optimization_id("Stress response"),
        fem_module._deterministic_optimization_id("Free response"),
    ]
    assert [record.node_id for record in setup_records] == [
        fem_module._optimization_node_uuid(workspace_id, parameter_pool_id),
        fem_module._optimization_node_uuid(workspace_id, parameter_pool_id),
        fem_module._optimization_node_uuid(workspace_id, response_pool_id),
        fem_module._optimization_node_uuid(workspace_id, response_pool_id),
    ]
    assert all(
        setup_record is not direct_record
        for setup_record, direct_record in zip(
            setup_records,
            [direct_records[0], direct_records[1], direct_records[2], direct_records[3]],
            strict=True,
        )
    )

    parameter_pool = registry.get_descriptor(PARAMETER_POOL_NODE_TYPE_ID).factory()
    parameter_pool_result = parameter_pool.execute(
        context(parameter_pool_id, {})
    )
    assert parameter_pool_result.outputs == {
        "names": ["Radius", "Height"],
        "values": [1.0, 2.0],
        "bounds": [Interval1D(1.0, 5.0), Interval1D(2.0, 8.0)],
    }
    parameter_state = run_state.pop(parameter_pool_id)
    with pytest.raises(ValueError, match="requires Parameter Setup state"):
        parameter_pool.execute(context(parameter_pool_id, {}))
    run_state[parameter_pool_id] = parameter_state

    response_pool = registry.get_descriptor(RESPONSE_POOL_NODE_TYPE_ID).factory()
    response_result = response_pool.execute(
        context(response_pool_id, {"values": [None, 2.0]})
    )
    assert response_result.outputs == {}
    assert response_result.warnings == ()
    assert run_state[response_pool_id].values == (None, 2.0)
    response_result = response_pool.execute(
        context(response_pool_id, {"values": [25.0, None]})
    )
    assert response_result.warnings == (
        "One or more response values violate their constraints.",
    )
    assert run_state[response_pool_id].values == (25.0, None)
    with pytest.raises(ValueError, match="configured response count"):
        response_pool.execute(context(response_pool_id, {"values": [12.0]}))
    assert run_state[response_pool_id].values == (25.0, None)
    response_pool.execute(context(response_pool_id, {}))
    assert run_state[response_pool_id].values == (None, None)

    state_before_invalid_setup = dict(run_state)
    handles_before_invalid_setup = services.handle_registry.active_handle_count
    with pytest.raises(ValueError, match="requires one Parameter Pool link"):
        parameter_setup.execute(
            context(
                setup_id,
                {"parameters_and_responses": direct_parameter_refs},
                semantic_links=(links[1],),
            )
        )
    assert run_state == state_before_invalid_setup
    assert services.handle_registry.active_handle_count == handles_before_invalid_setup
    with pytest.raises(ValueError, match="duplicate IDs"):
        parameter_setup.execute(
            context(
                setup_id,
                {"parameters_and_responses": [direct_parameter_refs[0]] * 2},
                semantic_links=(links[0],),
            )
        )
    assert run_state == state_before_invalid_setup

    duplicate_name_refs = construct_parameters.execute(
        context(
            "construct-duplicate-names",
            {
                "names": ["Duplicate", "Duplicate"],
                "minimum_values": [0.0, 1.0],
                "maximum_values": [1.0, 2.0],
                "decimal_places": [2, 2],
            },
        )
    ).outputs["parameters"]
    with pytest.raises(ValueError, match="duplicate IDs"):
        parameter_setup.execute(
            context(
                setup_id,
                {"parameters_and_responses": duplicate_name_refs},
                semantic_links=(links[0],),
            )
        )
    assert run_state == state_before_invalid_setup

    invalid_design_inputs = (
        {"parameters_and_responses": setup_refs, "parameter_values": [2.0]},
        {
            "parameters_and_responses": setup_refs,
            "parameter_values": [0.0, 3.0],
        },
        {
            "parameters_and_responses": setup_refs,
            "response_values": [15.0],
        },
        {
            "parameters_and_responses": setup_refs,
            "parameter_values": [math.nan, 3.0],
        },
        {"parameters_and_responses": [setup_refs[0], setup_refs[0]]},
    )
    active_count = services.handle_registry.active_handle_count
    for invalid_inputs in invalid_design_inputs:
        with pytest.raises((TypeError, ValueError)):
            construct_design.execute(context(design_node_id, invalid_inputs))
        assert services.handle_registry.active_handle_count == active_count

    design_refs: list[RuntimeHandleRef] = []

    def build_design(inputs: dict[str, object]) -> object:
        result = construct_design.execute(context(design_node_id, inputs))
        ref = result.outputs["design"]
        assert type(ref) is RuntimeHandleRef
        assert ref.data_type_id == OPTIMIZATION_DESIGN_DATA_TYPE_ID
        assert ref.kind == OPTIMIZATION_DESIGN_HANDLE_KIND
        assert ref.metadata == {}
        design_refs.append(ref)
        return services.resolve_handle(
            ref,
            expected_data_type=OPTIMIZATION_DESIGN_DATA_TYPE_ID,
            expected_kind=OPTIMIZATION_DESIGN_HANDLE_KIND,
        )

    pending_design = build_design({"parameters_and_responses": setup_refs})
    assert (
        pending_design.name,
        pending_design.status,
        pending_design.values,
        pending_design.solution,
        pending_design.screenshot,
    ) == ("Design", 0, (1.0, 2.0, None, None), None, None)
    assert pending_design.variables == tuple(setup_records)
    assert all(
        copied is not original
        for copied, original in zip(
            pending_design.variables,
            setup_records,
            strict=True,
        )
    )
    infeasible_design = build_design(
        {
            "parameters_and_responses": setup_refs,
            "name": "Infeasible Design",
            "parameter_values": [2.0, 3.0],
            "response_values": [25.0, 1.0],
        }
    )
    assert (infeasible_design.name, infeasible_design.status) == (
        "Infeasible Design",
        3,
    )
    computed_design = build_design(
        {
            "parameters_and_responses": [setup_refs[0], setup_refs[3]],
            "response_values": [1.0],
        }
    )
    assert (computed_design.status, computed_design.values) == (4, (1.0, 1.0))
    feasible_design = build_design(
        {
            "parameters_and_responses": setup_refs,
            "parameter_values": [5.0, 8.0],
            "response_values": [15.0, 1.0],
        }
    )
    assert (feasible_design.status, feasible_design.values) == (
        5,
        (5.0, 8.0, 15.0, 1.0),
    )
    parameter_only_design = build_design(
        {"parameters_and_responses": setup_refs[:2]}
    )
    assert (parameter_only_design.status, parameter_only_design.values) == (
        0,
        (1.0, 2.0),
    )
    second_parameter_only_design = build_design(
        {"parameters_and_responses": setup_refs[:2]}
    )
    assert second_parameter_only_design.id != parameter_only_design.id
    assert registry.data_types.require(OPTIMIZATION_DESIGN_DATA_TYPE_ID).validate_item(
        design_refs[0]
    )
    assert not registry.data_types.require(
        OPTIMIZATION_DESIGN_DATA_TYPE_ID
    ).validate_item(replace(design_refs[0], metadata={"path": "forbidden"}))

    all_refs = [
        *direct_parameter_refs,
        *direct_response_refs,
        *duplicate_name_refs,
        *setup_refs,
        *design_refs,
    ]
    assert services.cleanup_run("design-run") == len(all_refs)
    assert services.handle_registry.active_handle_count == 0
    for ref in all_refs:
        with pytest.raises(StaleHandleError):
            services.resolve_handle(ref)


def _plane() -> TypedInlineValue:
    return TypedInlineValue(
        PLANE_DATA_TYPE_ID,
        1,
        {
            "origin": [0.0, 0.0, 0.0],
            "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            "normal": [0.0, 0.0, 1.0],
        },
    )


def test_force_load_container_lifecycle_rolls_back_and_releases_in_reverse() -> None:
    registry = build_builtin_registry()
    load_port = next(port for port in registry.get_spec(FORCE_NODE_TYPE_ID).ports if port.key == "load")
    assert load_port.data_type == FORCE_DATA_TYPE_ID
    services = WorkerServices()
    services.bind_data_types(registry.data_types)

    def context(node_id: str, inputs: dict[str, object]) -> ExecutionContext:
        return ExecutionContext(
            run_id="force-run",
            node_id=node_id,
            workspace_id="fem-workspace",
            inputs=inputs,
            properties={},
            emit_log=lambda _level, _message: None,
            worker_services=services,
        )

    cylinder = _function_adapters()[CYLINDER_NODE_TYPE_ID]
    cylinder_inputs = {
        "plane": _plane(),
        "radius": 1.0,
        "interval": Interval1D(0.0, 2.0),
    }
    first_body = cylinder.execute(
        context("first-cylinder", cylinder_inputs)
    ).outputs["body"]
    second_body = cylinder.execute(
        context("second-cylinder", cylinder_inputs)
    ).outputs["body"]
    body_records = [
        services.resolve_handle(
            body,
            expected_data_type=OCP_BODY_DATA_TYPE_ID,
            expected_kind=OCP_BODY_HANDLE_KIND,
        )
        for body in (first_body, second_body)
    ]

    force = _function_adapters()[FORCE_NODE_TYPE_ID]

    def force_context(
        geometry: list[object], tolerances: list[object]
    ) -> ExecutionContext:
        return context(
            "force-node",
            {
                "name": "Primary Force",
                "index": 7,
                "geometry": geometry,
                "tolerances": tolerances,
                "vector": make_vector3d_value(1.0, 2.0, 3.0),
            },
        )

    lease_count = services.handle_registry.active_lease_count
    with pytest.raises(ValueError, match="match geometry count"):
        force.execute(force_context([first_body, second_body], [0.1, 0.2, 0.3]))
    assert services.handle_registry.active_lease_count == lease_count

    wrong_kind = replace(second_body, kind="wrong.kind")
    with pytest.raises(TypeError, match="exact COREX OCPBody handle"):
        force.execute(force_context([first_body, wrong_kind], []))
    assert services.handle_registry.active_lease_count == lease_count

    for invalid in (True, math.inf, 0.0, -1.0):
        with pytest.raises((TypeError, ValueError)):
            force.execute(force_context([first_body], [invalid]))
    assert services.handle_registry.active_lease_count == lease_count

    force_ref = force.execute(
        force_context([first_body, second_body], [0.25])
    ).outputs["load"]
    assert type(force_ref) is RuntimeHandleRef
    assert force_ref.data_type_id == FORCE_DATA_TYPE_ID
    assert force_ref.kind == FORCE_HANDLE_KIND
    assert force_ref.metadata == {}
    force_record = services.resolve_handle(
        force_ref,
        expected_data_type=FORCE_DATA_TYPE_ID,
        expected_kind=FORCE_HANDLE_KIND,
    )
    assert force_record.name == "Primary Force"
    assert force_record.index == 7
    assert force_record.tolerances == (0.25, 0.25)
    assert force_record.vector_components == (1.0, 2.0, 3.0)
    assert [lease.handle_id for lease in force_record.child_leases] == [
        first_body.handle_id,
        second_body.handle_id,
    ]
    assert len({lease.owner_scope for lease in force_record.child_leases}) == 1
    assert force_record.child_leases[0].owner_scope.startswith("cache:force:")

    load_container = _function_adapters()[LOAD_CONTAINER_NODE_TYPE_ID]
    passed = load_container.execute(
        context("load-container-node", {"load": force_ref})
    ).outputs["output"]
    assert passed is force_ref

    consumer_ref = services.lease_handle(
        force_ref,
        owner_scope="consumer:force-test",
    )
    released_children: list[str] = []
    original_release = force_record._release_handle

    def logged_release(value: object) -> bool:
        assert type(value) is RuntimeHandleRef
        released_children.append(value.handle_id)
        return original_release(value)

    force_record._release_handle = logged_release
    assert services.cleanup_run("force-run") == 3
    assert not force_record.closed
    assert all(record.shape is not None for record in body_records)

    assert services.release_handle(consumer_ref)
    assert force_record.closed
    assert force_record.child_leases == ()
    assert released_children == [second_body.handle_id, first_body.handle_id]
    assert all(record.shape is None for record in body_records)
    assert services.handle_registry.active_handle_count == 0

    with pytest.raises(StaleHandleError):
        load_container.execute(
            context("stale-load-container-node", {"load": force_ref})
        )
