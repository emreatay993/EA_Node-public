# Purpose: Prove full-fidelity Mechanical definition extraction and FEA Table wiring.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_definition_tables.py

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.contracts import (
    DEFINITIONS_COLUMNS,
    encode_selector,
    model_handle,
    object_value,
    property_value,
)
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.owner_process import (
    _read_definition_bulk,
    _write_definition_bulk,
)
from ea_node_editor.addons.mechanical.runtime import execute_fea_table
from ea_node_editor.addons.mechanical.tables import (
    DEFINITION_ENCODED_MAX_BYTES,
    build_definition_tables,
)
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.registry_agreement import (
    catalog_agreement,
    runtime_registry_fingerprint,
)
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.execution.signal_plot_renderer import render_signal_plot
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import NodeInputNotReadyError
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import ImageValue, TableValue


IDENTITY = {
    "run_id": "run",
    "session_id": "session",
    "document_id": "document",
    "source_key": "sha256:source",
    "system_key": "standalone",
    "model_revision": 0,
}


class Quantity:
    def __init__(self, value, unit):
        self.Value = value
        self.Unit = unit

    def ConvertToUnitSystem(self, system, quantity_name):
        assert system == "SI"
        if quantity_name == "Temperature" and self.Unit == "C":
            return Quantity(self.Value + 273.15, "K")
        if quantity_name == "Length" and self.Unit == "mm":
            return Quantity(self.Value / 1000.0, "m")
        return Quantity(self.Value, self.Unit)


class Variable(SimpleNamespace):
    pass


class Native(SimpleNamespace):
    def __init__(self, **values):
        super().__init__(**values)
        for prop in values.get("VisibleProperties", ()):
            internal = getattr(prop, "InternalValue", None)
            if hasattr(internal, "Inputs") and hasattr(internal, "Output"):
                setattr(self, prop.APIName, internal)

    def GetType(self):
        return SimpleNamespace(FullName=self.api_type)


def variable(
    name,
    values,
    *,
    unit="",
    quantity_name="",
    definition="Discrete",
    formula=None,
):
    return Variable(
        Name=name,
        DefinitionType=definition,
        Formula=formula,
        Unit=unit,
        QuantityName=quantity_name,
        DiscreteValues=values,
        DiscreteValueCount=len(values),
    )


def field_property(key, caption, inputs, output):
    return SimpleNamespace(
        APIName=key,
        Name=key,
        Caption=caption,
        InternalValue=SimpleNamespace(Name=caption, Inputs=inputs, Output=output),
    )


class FakeApp:
    def __init__(self, objects, model=None, max_return_bytes=None):
        self.objects = objects
        self.model = model or SimpleNamespace()
        self.max_return_bytes = max_return_bytes

    def execute_script(self, script):
        namespace = {
            "Tree": SimpleNamespace(AllObjects=self.objects),
            "Model": self.model,
            "Ansys": SimpleNamespace(
                Core=SimpleNamespace(
                    Units=SimpleNamespace(
                        Quantity=Quantity,
                        UnitsManager=SimpleNamespace(
                            GetQuantityUnitForUnitSystem=lambda *_: "K"
                        )
                    )
                )
            ),
        }
        exec(compile(script, "<mechanical-definition-script>", "exec"), namespace)
        result = namespace["_corex_receipt"]
        if self.max_return_bytes is not None and len(result.encode()) > self.max_return_bytes:
            raise RuntimeError("simulated gRPC receive cap")
        return result

    run_python_script = execute_script


def extract(
    objects,
    sources,
    *,
    table="",
    component="all",
    units="source",
    model=None,
    remote=False,
    family="auto",
):
    backend = MechanicalOwnerBackend()
    with tempfile.TemporaryDirectory() as directory:
        backend.work_root = Path(directory).resolve()
        client = FakeApp(objects, model, max_return_bytes=256 if remote else None)
        if remote:
            backend.mechanical = client
        else:
            backend.app = client
        return backend.definition_tables(
            {
                "sources": sources,
                "family": family,
                "table": table,
                "table_selector": None,
                "component": component,
                "units": units,
                "native_output_path": str(
                    backend.work_root / "native-definitions-test.json"
                ),
            }
        )["definition_tables"]


def property_source(obj, key):
    return {
        "kind": "property",
        "object_id": obj.ObjectId,
        "object_path": f"Analysis/{obj.Name}",
        "property_key": key,
    }


def rows(table):
    return table.to_pandas().to_dict(orient="records")


@pytest.mark.parametrize("remote", [False, True])
def test_scalar_constant_has_one_row_without_invented_time(remote):
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        VisibleProperties=[
            field_property(
                "XComponent",
                "X Component",
                [variable("Time", [], unit="s", quantity_name="Time")],
                variable("X Component", [Quantity(500, "N")], unit="N", quantity_name="Force"),
            )
        ],
    )
    result = extract(
        [analysis, load], [property_source(load, "XComponent")], remote=remote
    )
    table = result["tables"][0]
    assert table.column_names == ("X Component [N]",)
    assert rows(table) == [{"X Component [N]": 500.0}]
    assert rows(result["definitions"])[0]["definition_kind"] == "constant"


def test_multiple_independents_duplicate_nonuniform_rows_and_formula_samples():
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Force",
        VisibleProperties=[
            field_property(
                "Curve",
                "Curve",
                [
                    variable("Time", [Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s"), Quantity(3, "s")], unit="s", quantity_name="Time"),
                    variable("Temperature", [Quantity(20, "C"), Quantity(30, "C"), Quantity(40, "C"), Quantity(50, "C")], unit="C", quantity_name="Temperature"),
                ],
                variable(
                    "Force",
                    [Quantity(0, "N"), Quantity(50, "N"), Quantity(50, "N"), Quantity(150, "N")],
                    unit="N",
                    quantity_name="Force",
                    definition="Formula",
                    formula="50*time",
                ),
            )
        ],
    )
    result = extract([analysis, load], [property_source(load, "Curve")])
    table = result["tables"][0]
    frame = table.to_pandas()
    assert frame["Time [s]"].tolist() == [0.0, 1.0, 1.0, 3.0]
    assert frame["Temperature [C]"].tolist() == [20.0, 30.0, 40.0, 50.0]
    assert frame["Force API samples [N]"].tolist() == [0.0, 50.0, 50.0, 150.0]
    definition = rows(result["definitions"])[-1]
    assert definition["formula"] == "50*time"
    assert definition["definition_kind"] == "formula"
    assert definition["notes"] == "API samples; formula retained separately"


def test_vector_component_selection_and_free_null_values():
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    properties = []
    for key, value in (("XComponent", 1), ("YComponent", 2), ("ZComponent", 3)):
        properties.append(
            field_property(
                key,
                key[0] + " Component",
                [variable("Time", [Quantity(0, "s"), Quantity(2, "s")], unit="s", quantity_name="Time")],
                variable(key[0] + " Component", [Quantity(value, "N"), Quantity(value + 1, "N")], unit="N", quantity_name="Force"),
            )
        )
    properties.append(
        field_property(
            "FreeComponent",
            "Free Component",
            [variable("Time", [Quantity(0, "s"), Quantity(2, "s")], unit="s", quantity_name="Time")],
            variable("Free Component", [], unit="N", quantity_name="Force", definition="Free"),
        )
    )
    load = Native(ObjectId=2, Name="Load", Parent=analysis, api_type="Force", VisibleProperties=properties)
    ordered = extract(
        [analysis, load],
        [
            property_source(load, "ZComponent"),
            property_source(load, "XComponent"),
            property_source(load, "YComponent"),
        ],
    )
    assert [table.column_names[-1] for table in ordered["tables"]] == [
        "Z Component [N]",
        "X Component [N]",
        "Y Component [N]",
    ]
    selected = extract(
        [analysis, load],
        [{"kind": "object", "object_id": 2, "object_path": "Analysis/Load", "property_key": ""}],
        component="Y Component",
    )
    assert selected["tables"][0].column_names[-1] == "Y Component [N]"
    free = extract([analysis, load], [property_source(load, "FreeComponent")])
    assert free["tables"][0].to_pandas()["Free Component [N]"].isna().tolist() == [True, True]
    assert rows(free["definitions"])[-1]["definition_kind"] == "free"
    with pytest.raises(ValueError, match="selector_missing: component"):
        extract(
            [analysis, load],
            [{"kind": "object", "object_id": 2, "object_path": "Analysis/Load", "property_key": ""}],
            component="Missing",
        )
    with pytest.raises(ValueError, match="selector_ambiguous"):
        extract(
            [analysis, load],
            [{"kind": "object", "object_id": 2, "object_path": "Analysis/Load", "property_key": ""}],
        )
    with pytest.raises(ValueError, match="selector_missing: requested definition table"):
        extract(
            [analysis, load],
            [{"kind": "object", "object_id": 2, "object_path": "Analysis/Load", "property_key": ""}],
            table="Missing",
        )


def test_si_uses_native_quantity_conversion_and_keeps_affine_source_unchanged():
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    source_quantity = Quantity(0, "C")
    load = Native(
        ObjectId=2,
        Name="Thermal",
        Parent=analysis,
        api_type="Temperature",
        VisibleProperties=[
            field_property(
                "Magnitude",
                "Temperature",
                [],
                variable("Temperature", [source_quantity], unit="C", quantity_name="Temperature"),
            )
        ],
    )
    result = extract([analysis, load], [property_source(load, "Magnitude")], units="si")
    table = result["tables"][0]
    assert table.column_names == ("Temperature [K]",)
    assert rows(table)[0]["Temperature [K]"] == pytest.approx(273.15)
    assert (source_quantity.Value, source_quantity.Unit) == (0, "C")


def test_bolt_pretension_step_states_preserve_exact_text():
    analysis = Native(
        ObjectId=1,
        Name="Analysis",
        Parent=None,
        api_type="Analysis",
        AnalysisSettings=SimpleNamespace(NumberOfSteps=5),
    )
    states = ["Load", "Lock", "Open", "Adjustment", "Increment"]
    bolt = Native(
        ObjectId=2,
        Name="Bolt",
        Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.BoltPretension",
        VisibleProperties=[],
        GetDefineBy=lambda step: states[step - 1],
    )
    result = extract(
        [analysis, bolt],
        [{"kind": "object", "object_id": 2, "object_path": "Analysis/Bolt", "property_key": ""}],
        table="Bolt pretension step states",
    )
    assert result["tables"][0].to_pandas()["State"].tolist() == states


@pytest.mark.parametrize(
    "api_type, properties",
    [
        (
            "Ansys.ACT.Automation.Mechanical.Results.StressResults.EquivalentStress",
            [
                field_property(
                    "DisplayTime",
                    "Display Time",
                    [],
                    variable("Time", [Quantity(1, "s")], unit="s", quantity_name="Time"),
                )
            ],
        ),
        ("Ansys.ACT.Automation.Mechanical.MeshControlWorksheet", []),
    ],
)
def test_auto_rejects_t08_source_families_before_field_scanning(api_type, properties):
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    source = Native(
        ObjectId=2,
        Name="Future source",
        Parent=analysis,
        api_type=api_type,
        VisibleProperties=properties,
    )
    with pytest.raises(ValueError, match="table_unsupported: .*T08"):
        extract(
            [analysis, source],
            [{"kind": "object", "object_id": 2, "object_path": "Analysis/Future source", "property_key": ""}],
            family="auto",
        )


def test_native_wrapper_path_prefix_is_normalized_to_admitted_source_path():
    project = Native(ObjectId=10, Name="Project", Parent=None, api_type="Project")
    model = Native(ObjectId=11, Name="Model", Parent=project, api_type="Model")
    analysis = Native(ObjectId=1, Name="Analysis", Parent=model, api_type="Analysis")
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Force",
        VisibleProperties=[
            field_property(
                "XComponent",
                "X Component",
                [],
                variable("X Component", [Quantity(1, "N")], unit="N", quantity_name="Force"),
            )
        ],
    )
    result = extract(
        [project, model, analysis, load],
        [{"kind": "property", "object_id": 2, "object_path": "Analysis/Load", "property_key": "XComponent"}],
    )
    assert rows(result["definitions"])[0]["object_path"] == "Analysis/Load"


def test_native_object_field_property_precedes_non_field_internal_value():
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    prop = field_property(
        "XComponent",
        "X Component",
        [],
        variable("unused", [Quantity(99, "N")], unit="N", quantity_name="Force"),
    )
    prop.InternalValue = Quantity(99, "N")
    field = SimpleNamespace(
        Name="X Component",
        Inputs=[],
        Output=variable("X Component", [Quantity(5, "N")], unit="N", quantity_name="Force"),
    )
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Force",
        VisibleProperties=[prop],
        XComponent=field,
    )
    result = extract([analysis, load], [property_source(load, "XComponent")])
    assert rows(result["tables"][0]) == [{"X Component [N]": 5.0}]


def test_missing_exact_object_field_never_falls_back_to_internal_value():
    analysis = Native(ObjectId=1, Name="Analysis", Parent=None, api_type="Analysis")
    prop = field_property(
        "XComponent",
        "X Component",
        [],
        variable("X Component", [Quantity(99, "N")], unit="N", quantity_name="Force"),
    )
    load = Native(
        ObjectId=2,
        Name="Load",
        Parent=analysis,
        api_type="Force",
        VisibleProperties=[],
    )
    load.VisibleProperties = [prop]
    with pytest.raises(ValueError, match="table_unsupported: property has no supported Field"):
        extract([analysis, load], [property_source(load, "XComponent")])


def _detached_field_payload(rows_count=3):
    return {
        "schema_version": 1,
        "records": [
            {
                "kind": "field",
                "table_key": "2:Curve:field",
                "object_path": "Analysis/Load",
                "property_key": "Curve",
                "property_caption": "Curve",
                "component": "Curve",
                "variables": [
                    {
                        "name": "Time",
                        "role": "independent",
                        "definition_type": "Discrete",
                        "formula": "",
                        "unit": "s",
                        "quantity_name": "Time",
                        "values": list(range(rows_count)),
                    },
                    {
                        "name": "Force",
                        "role": "dependent",
                        "definition_type": "Discrete",
                        "formula": "",
                        "unit": "N",
                        "quantity_name": "Force",
                        "values": list(range(rows_count)),
                    },
                ],
            }
        ],
    }


def test_capacity_errors_name_exact_table_and_cumulative_size(monkeypatch):
    import ea_node_editor.addons.mechanical.tables as tables_module

    monkeypatch.setattr(tables_module, "SCIENTIFIC_VALUE_MAX_BYTES", 1)
    with pytest.raises(ValueError, match="2:Curve:field.*decoded bytes.*narrow Source"):
        build_definition_tables(_detached_field_payload())
    monkeypatch.setattr(tables_module, "SCIENTIFIC_VALUE_MAX_BYTES", 256 * 1024 * 1024)
    baseline = build_definition_tables(_detached_field_payload())
    total = sum(value.nbytes for value in (*baseline["tables"], baseline["definitions"]))
    monkeypatch.setattr(tables_module, "SCIENTIFIC_OPERATION_MAX_BYTES", total - 1)
    with pytest.raises(ValueError, match=f"definition output is {total} decoded bytes"):
        build_definition_tables(_detached_field_payload())


def test_definitions_capacity_error_names_exact_size_and_guidance(monkeypatch):
    import ea_node_editor.addons.mechanical.tables as tables_module

    baseline = build_definition_tables(_detached_field_payload())
    table_size = baseline["tables"][0].nbytes
    definitions_size = baseline["definitions"].nbytes
    assert definitions_size > table_size
    monkeypatch.setattr(tables_module, "SCIENTIFIC_VALUE_MAX_BYTES", definitions_size - 1)
    with pytest.raises(
        ValueError,
        match=rf"table 'Definitions' is {definitions_size} decoded bytes.*narrow Source",
    ):
        build_definition_tables(_detached_field_payload())


def test_inconsistent_populated_columns_fail_without_padding():
    payload = _detached_field_payload(3)
    payload["records"][0]["variables"][1]["values"] = [1, 2]
    with pytest.raises(ValueError, match="inconsistent populated column lengths.*no rows were padded"):
        build_definition_tables(payload)


def test_duplicate_display_labels_preserve_both_positional_columns_and_definitions():
    payload = _detached_field_payload(2)
    payload["records"][0]["variables"][0].update(
        name="X", unit="m", quantity_name="Length", values=[1.0, 2.0]
    )
    payload["records"][0]["variables"][1].update(
        name="X", unit="m", quantity_name="Length", values=[10.0, 20.0]
    )
    result = build_definition_tables(payload)
    table = result["tables"][0]
    assert table.column_names == ("X [m]", "X [m]")
    np.testing.assert_array_equal(table.columns[0].to_numpy(), [1.0, 2.0])
    np.testing.assert_array_equal(table.columns[1].to_numpy(), [10.0, 20.0])
    definitions = result["definitions"].to_pandas()
    assert definitions["column_label"].tolist() == ["X [m]", "X [m]"]
    assert definitions["column_index"].tolist() == [0, 1]


def test_hashed_one_shot_spool_roundtrips_multiple_table_values(tmp_path):
    first = build_definition_tables(_detached_field_payload())
    second = build_definition_tables(_detached_field_payload(5))["tables"][0]
    value = {"tables": [first["tables"][0], second], "definitions": first["definitions"]}
    descriptor = _write_definition_bulk(tmp_path, value)
    restored = _read_definition_bulk(tmp_path, descriptor)
    assert [table.row_count for table in restored["tables"]] == [3, 5]
    assert restored["definitions"].column_names == DEFINITIONS_COLUMNS
    assert not list(tmp_path.glob("definitions-*.json"))


def test_encoded_bound_covers_sixfold_json_escaping_at_full_operation_limit():
    from ea_node_editor.runtime_contracts.scientific_values import (
        SCIENTIFIC_OPERATION_MAX_BYTES,
    )

    assert DEFINITION_ENCODED_MAX_BYTES == 8 * SCIENTIFIC_OPERATION_MAX_BYTES
    assert DEFINITION_ENCODED_MAX_BYTES > 6 * SCIENTIFIC_OPERATION_MAX_BYTES
    scaled_limit = 1024
    worst_label_json = json.dumps("\0" * scaled_limit, separators=(",", ":")).encode()
    assert len(worst_label_json) <= 8 * scaled_limit


def test_table_value_runs_directly_through_signal_plot_without_mutation():
    result = build_definition_tables(_detached_field_payload(8))
    table = result["tables"][0]
    before = [np.array(column.to_numpy(), copy=True) for column in table.columns]
    image, _warnings = render_signal_plot({"values": table, "marker_shapes": [0]})
    assert isinstance(image, ImageValue)
    for original, column in zip(before, table.columns, strict=True):
        np.testing.assert_array_equal(original, column.to_numpy())
        assert column.to_numpy().flags.writeable is False


def _model():
    return model_handle(
        handle_id="model",
        owner_scope="run",
        worker_generation=1,
        metadata={
            "workspace_id": "workspace",
            **IDENTITY,
            "connection_generation": 0,
            "release_code": 261,
            "backend_mode": "background",
            "catalogue_id": str(uuid4()),
            "producer_node_id": "open",
            "producer_port": "info",
            "producer_path": [0],
            "producer_iteration": 0,
        },
    )


def _property():
    return property_value(
        {
            **IDENTITY,
            "object_id": 2,
            "object_path": "Analysis/Load",
            "property_key": "Curve",
            "caption": "Curve",
            "definition_kind": "tabular",
            "display_value": "Tabular data",
            "value_status": "available",
            "scalar_value": None,
            "unit": "N",
            "quantity_name": "Force",
            "formula": "",
            "has_tabular_data": True,
            "tables": [
                {
                    "table_key": "2:Curve:field",
                    "table_family": "field_definition",
                    "definition_kind": "Field",
                    "row_count": 3,
                    "column_count": 2,
                }
            ],
            "selector_code": encode_selector(
                "property",
                document_id="document",
                system_key="standalone",
                object_path="Analysis/Load",
                native_id="Curve",
            ),
        }
    )


class Sessions:
    def __init__(self):
        self.operated = None

    def admit_model(self, value, **kwargs):
        self.admitted = value, kwargs
        return SimpleNamespace(work_root=Path(tempfile.gettempdir()))

    def operate(self, session, **kwargs):
        self.operated = session, kwargs
        return {"definition_tables": build_definition_tables(_detached_field_payload())}


def test_runtime_validates_identity_and_connected_values_override_authored_defaults():
    sessions = Sessions()
    context = SimpleNamespace(
        run_id="run",
        workspace_id="workspace",
        inputs={"family": "model_definition", "units": "si", "sets": []},
        properties={"family": "supported_worksheet", "table": "", "component": "all", "units": "source", "sets": [9]},
        mechanical_sessions=sessions,
    )
    result = execute_fea_table(context, _model(), [_property()])
    assert isinstance(result["tables"][0], TableValue)
    args = sessions.operated[1]["args"]
    assert args["units"] == "si" and "sets" not in args
    assert args["sources"] == [
        {
            "kind": "property",
            "object_id": 2,
            "object_path": "Analysis/Load",
            "property_key": "Curve",
        }
    ]
    with pytest.raises(ValueError, match="must contain"):
        execute_fea_table(context, _model(), [])
    with pytest.raises(NodeInputNotReadyError):
        execute_fea_table(context, _model(), None)


@pytest.mark.parametrize(
    "family", ["result_history_summary", "spatial_samples", "supported_worksheet"]
)
def test_each_explicit_t08_family_is_unsupported_without_native_access(family):
    sessions = Sessions()
    context = SimpleNamespace(
        run_id="run",
        workspace_id="workspace",
        inputs={"family": family},
        properties={"table": "", "component": "all", "units": "source", "sets": []},
        mechanical_sessions=sessions,
    )
    with pytest.raises(ValueError, match=f"table_unsupported: family '{family}'"):
        execute_fea_table(context, _model(), [_property()])
    assert sessions.operated is None


def test_actual_decorated_function_and_worker_runtime_register():
    declarations = discover_plugin_declarations(
        SOURCE,
        filename="mechanical_nodes.py",
        allow_reserved_ids=True,
        owner_id="mechanical.corex",
        allow_internal_metadata=True,
    )
    declaration = next(item for item in declarations if item.spec.type_id == "mechanical.fea_table")
    ports = {port.key: port for port in declaration.spec.ports}
    assert ports["source"].data_access == "list"
    assert ports["source"].accepted_data_types == ("COREX.Mechanical.Property",)
    assert ports["tables"].data_access == "list"
    namespace = {}
    exec(SOURCE, namespace)
    sessions = Sessions()
    context = ExecutionContext(
        run_id="run",
        node_id="fea-table",
        workspace_id="workspace",
        inputs={"model": _model(), "source": [_property()], "family": "model_definition"},
        properties={"table": "", "component": "all", "units": "source", "sets": []},
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
    )
    outputs = PythonFunctionAdapter(declaration.spec, namespace["fea_table"]).execute(context).outputs
    assert isinstance(outputs["tables"][0], TableValue)

    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
    )
    fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="run",
        workspace_id="workspace",
        runtime_snapshot=None,
        catalog_fingerprint=fingerprint,
        catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(),
        plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(fingerprint, plugin_digest),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.fea_table")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.fea_table"))
    runtime.clear()
