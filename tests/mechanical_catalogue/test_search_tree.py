from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ea_node_editor.addons.mechanical.inspection import (
    SearchIncomplete,
    _predicate,
    collect_catalogue_rows,
    property_value_query,
    search_tree,
)
from ea_node_editor.addons.mechanical.contracts import catalogue_table, encode_selector, model_handle
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.runtime import execute_search_tree
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.addons.mechanical.backend import _RemoteTree
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.registry_agreement import catalog_agreement, runtime_registry_fingerprint
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations


class Native(SimpleNamespace):
    def GetType(self):
        return SimpleNamespace(FullName=self.api_type)


class GuardedTree:
    def __init__(self, objects):
        self._objects = objects

    @property
    def AllObjects(self):
        return self._objects

    def __getattr__(self, name):
        raise AssertionError(f"native tree UI method was accessed: {name}")


class GuardedOutput(SimpleNamespace):
    @property
    def DiscreteValues(self):
        raise AssertionError("table cells must not be read by Search")


IDENTITY = {
    "run_id": "run",
    "session_id": "session",
    "document_id": "document",
    "source_key": "sha256:source",
    "system_key": "standalone",
    "model_revision": 0,
}


def prop(key, caption, value, *, output=None):
    internal = None if output is None else SimpleNamespace(Inputs=[object()], Output=output)
    return SimpleNamespace(
        APIName=key, Name=key, Caption=caption, StringValue=value, InternalValue=internal
    )


def fixture():
    analysis = Native(
        ObjectId=1,
        Name="COREX structural A",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.Analysis",
        DataModelObjectCategory="Analysis",
        VisibleProperties=[],
    )
    named = Native(
        ObjectId=9,
        Name="Top face",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.NamedSelection",
        DataModelObjectCategory="NamedSelection",
        TotalSelection=1,
        Location=SimpleNamespace(Ids=[14], SelectionType="GeometryEntities"),
        VisibleProperties=[],
    )
    output = GuardedOutput(
        DefinitionType="Discrete", DiscreteValueCount=3, Formula=None, Unit="N",
        QuantityName="Force",
    )
    force = Native(
        ObjectId=2,
        Name="Straße   Load",
        Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        DataModelObjectCategory="Force",
        ObjectState="UnderDefined",
        Suppressed=False,
        CoordinateSystem=SimpleNamespace(ObjectId=4, Name="Frame α"),
        Location=named,
        ImportableObjectSourceId="Setup::File1::Imported=Load",
        VisibleProperties=[
            prop("Comment", "Comment", "Load = 100 N"),
            prop("Quoted", "Comment", 'Bolt "A"'),
            prop("Empty", "Empty value", ""),
            prop("XComponent", "X Component", "500 N", output=output),
        ],
    )
    body = Native(
        ObjectId=3,
        Name="Hidden Body",
        Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Body",
        DataModelObjectCategory="Body",
        Hidden=True,
        VisibleProperties=[],
    )
    coordinate = Native(
        ObjectId=4,
        Name="Frame α",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.CoordinateSystem",
        DataModelObjectCategory="CoordinateSystem",
        VisibleProperties=[],
    )
    group = Native(
        ObjectId=10,
        Name="Shared group",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditionsGroup",
        DataModelObjectCategory="BoundaryConditionsGroup",
        VisibleProperties=[],
    )
    bolt = Native(
        ObjectId=5,
        Name="Shared bolt",
        Parent=group,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.BoltPretension",
        DataModelObjectCategory="BoltPretension",
        VisibleProperties=[],
    )
    model = SimpleNamespace(
        GetActivationStatusForAnalysis=lambda object_id, analysis_id: (
            "ObjectActive" if (object_id, analysis_id) == (5, 1) else "ObjectNotApplicable"
        )
    )
    for item in (analysis, named, body, coordinate, group, bolt):
        item.ObjectState = "FullyDefined"
        item.Suppressed = False
    tag = SimpleNamespace(Name="Direct β", Objects=[force])
    return [analysis, named, force, body, coordinate, group, bolt], model, SimpleNamespace(ObjectTags=[tag])


def run(filter_code, query, **options):
    objects, model, data_model = fixture()
    mutate = options.pop("mutate", None)
    if mutate is not None:
        mutate(objects)
    return search_tree(
        tree=GuardedTree(objects),
        model=model,
        data_model=data_model,
        identity=IDENTITY,
        filter_code=filter_code,
        query=query,
        match_mode=options.pop("match_mode", "contains"),
        case_sensitive=options.pop("case_sensitive", False),
        include_hidden_properties=options.pop("include_hidden_properties", False),
        invert=options.pop("invert", False),
        typed_selector=options.pop("typed_selector", None),
        **options,
    )


def remote_objects(objects, *, include_hidden=False):
    class Client:
        def run_python_script(self, script):
            receipt = "json.dumps({'marker':'corex-remote-tree-v1','byte_length':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()},separators=(',',':'))"
            compiled = script.replace(receipt, "_result=" + receipt)
            namespace = {
                "Tree": SimpleNamespace(AllObjects=objects),
                "DataModel": SimpleNamespace(ObjectTags=[]),
            }
            exec(compile(compiled, "<remote>", "exec"), namespace)
            return namespace["_result"]

    with tempfile.TemporaryDirectory() as root:
        return list(
            _RemoteTree(
                Client(), Path(root), include_hidden_properties=include_hidden
            ).AllObjects
        )


def test_remote_tree_utf8_file_transport_preserves_native_unicode_payload() -> None:
    objects, _model, _data_model = fixture()
    force = next(item for item in objects if item.ObjectId == 2)
    expected = "3136.5485 mm³ · 22 °C · Ω · 漢字 · C:\\native\\path"
    force.VisibleProperties.append(prop("Unicode", "Unicode", expected))
    projected = remote_objects(objects)
    value = next(item for item in projected if item.ObjectId == 2).VisibleProperties[-1]
    assert value.StringValue == expected


@pytest.mark.parametrize(
    ("filter_code", "query", "expected"),
    [
        ("name", "load strasse", [2]),
        ("tag", "direct β", [2]),
        ("type", "BoundaryConditions.Force", [2]),
        ("state", "Underdefined", [2]),
        ("coordinate_system", "Frame α", [2]),
        ("model", "Setup::File1::Imported=Load", [2]),
        ("graphics", "Hidden bodies", [3]),
        ("environment", "COREX structural A", [1, 2, 3, 5]),
        ("scoping", "Named selection", [2]),
        ("property_name", "X Component", [2]),
        ("property_value", "Tabular data", [2]),
    ],
)
def test_all_eleven_filters_have_exact_corex_background_meanings(filter_code, query, expected):
    result = run(filter_code, query)
    assert [value.payload["object_id"] for value in result["objects"]] == expected
    assert result["details"].row_count >= 1


def test_exact_contains_unicode_name_terms_and_literal_quotes():
    assert [v.payload["object_id"] for v in run("name", "load strasse")["objects"]] == [2]
    assert not run("name", "Straße Load", match_mode="exact")["objects"]
    assert [v.payload["object_id"] for v in run("name", "Straße   Load", match_mode="exact")["objects"]] == [2]
    assert not run("name", '"Straße"')["objects"]
    assert not run("name", "STRASSE", case_sensitive=True)["objects"]


def test_state_visible_aliases_obey_match_and_case_sensitivity():
    assert [v.payload["object_id"] for v in run(
        "state", "licensed", mutate=lambda objects: setattr(objects[2], "ObjectState", "LicenseConflict")
    )["objects"]] == [2]
    assert [v.payload["object_id"] for v in run("state", "underdefined")["objects"]] == [2]
    assert not run("state", "underdefined", case_sensitive=True)["objects"]


@pytest.mark.parametrize(
    ("query", "caption", "value", "empty"),
    [
        ('Comment = "Load = 100 N"', "Comment", "Load = 100 N", False),
        ('Comment = "Bolt \\"A\\""', "Comment", 'Bolt "A"', False),
        (r"Comment = C:\loads\bolt's = 100", "Comment", r"C:\loads\bolt's = 100", False),
        ('Comment = ""', "Comment", "", True),
        ('""', None, "", True),
    ],
)
def test_property_value_query_preserves_the_pinned_single_pair_grammar(query, caption, value, empty):
    assert property_value_query(query) == (caption, value, empty)


@pytest.mark.parametrize("query", ['= value', '"bad', '"bad" tail', 'a "bad"', '"bad\\x"'])
def test_property_value_query_rejects_empty_caption_and_malformed_quotes(query):
    with pytest.raises(ValueError):
        property_value_query(query)


def test_property_value_pairs_quotes_first_delimiter_and_explicit_empty_in_both_modes():
    assert [v.payload["property_key"] for v in run("property_value", 'Comment = "Load = 100 N"')["properties"]] == ["Comment"]
    assert [v.payload["property_key"] for v in run("property_value", 'Comment = "Bolt \\"A\\""')["properties"]] == ["Quoted"]
    for mode in ("contains", "exact"):
        assert [v.payload["property_key"] for v in run("property_value", 'Empty value = ""', match_mode=mode)["properties"]] == ["Empty"]
    assert len(run("property_value", "   ")["properties"]) == 4


def test_typed_picker_identity_bypasses_text_grammar_and_stays_exact():
    selected = run("name", "ignored", typed_selector={
        "kind": "object", "native_id": 2, "object_path": "COREX structural A/Straße   Load"
    })
    assert [value.payload["object_id"] for value in selected["objects"]] == [2]
    selected = run("scoping", "lost scoping", typed_selector={
        "kind": "property", "native_id": "Quoted", "object_path": "COREX structural A/Straße   Load"
    })
    assert [value.payload["property_key"] for value in selected["properties"]] == ["Quoted"]
    for selector in (
        {"kind": "object", "native_id": 999, "object_path": "missing"},
        {"kind": "property", "native_id": "Quoted", "object_path": "wrong/path"},
    ):
        with pytest.raises(ValueError, match="mechanical.selector_missing"):
            run("name", "ignored", typed_selector=selector)


def test_availability_not_applicable_and_inversion_never_turn_unknown_into_match():
    relation = {"status": "unavailable", "values": []}
    with pytest.raises(SearchIncomplete, match="mechanical.search_incomplete"):
        _predicate(relation, "x", filter_code="state", exact=False, case_sensitive=False, invert=True)
    assert not _predicate({"status": "not_applicable", "values": []}, "x", filter_code="graphics", exact=False, case_sensitive=False, invert=True)
    assert [v.payload["object_id"] for v in run("graphics", "Shown bodies", invert=True)["objects"]] == [3]


def test_scoping_distinguishes_confirmed_absence_empty_and_rejects_history_queries():
    assert [v.payload["object_id"] for v in run("scoping", "No explicit scope")["objects"]] == [4]
    assert [v.payload["object_id"] for v in run("scoping", "No explicit scope", invert=True)["objects"]] == [9, 2]
    for query in ("Partial", "partial scope", "lost scope", "lost scoping"):
        with pytest.raises(ValueError, match="unsupported"):
            run("scoping", query)


def test_coordinate_explicit_assignment_is_visible_and_missing_never_means_global():
    result = run(
        "coordinate_system", "Explicit assignment"
    )
    assert [value.payload["object_id"] for value in result["objects"]] == [2]
    detail = result["details"].to_pandas().iloc[0]
    assert detail["relation_role"] == "assignment"
    assert detail["property_key"] == "CoordinateSystem"
    assert not run(
        "coordinate_system", "Global",
        mutate=lambda objects: setattr(objects[2], "CoordinateSystem", None),
    )["objects"]


def test_opaque_source_ids_are_raw_case_sensitive_exact_identities():
    assert [value.payload["object_id"] for value in run(
        "model", "Setup::File1::Imported=Load"
    )["objects"]] == [2]
    assert not run("model", "setup::file1::imported=load")["objects"]
    assert not run("model", "Setup::File1::Imported")["objects"]


def test_no_match_is_empty_and_tabular_presence_never_reads_cells():
    result = run("property_value", "absent")
    assert result["objects"] == [] and result["properties"] == []
    assert result["details"].row_count == 0
    assert run("name", "", invert=True)["objects"] == []
    assert run("property_value", "   ", invert=True)["properties"] == []


def test_object_filter_does_not_read_properties_of_unmatched_objects():
    class Unmatched(Native):
        @property
        def VisibleProperties(self):
            raise AssertionError("unmatched properties must stay unread")

    def add_unmatched(objects):
        objects.append(Unmatched(
            ObjectId=99, Name="Unmatched", Parent=None,
            api_type="Native.Type", DataModelObjectCategory="Type",
            ObjectState="FullyDefined", Suppressed=False,
        ))

    assert [value.payload["object_id"] for value in run(
        "name", "Straße", mutate=add_unmatched
    )["objects"]] == [2]


def test_tabular_metadata_can_decide_match_when_string_value_is_unreadable():
    class MetadataOnlyProperty:
        APIName = Name = "Curve"
        Caption = "Curve"
        InternalValue = SimpleNamespace(
            Inputs=[object()],
            Output=GuardedOutput(
                DefinitionType="Discrete", DiscreteValueCount=3, Formula=None,
                Unit="N", QuantityName="Force",
            ),
        )

        @property
        def StringValue(self):
            raise RuntimeError("unreadable")

    result = run(
        "property_value", "Tabular data",
        mutate=lambda objects: objects[2].VisibleProperties.append(MetadataOnlyProperty()),
    )
    assert "Curve" in [value.payload["property_key"] for value in result["properties"]]
    detail = result["details"].to_pandas()
    curve = detail[detail["property_key"] == "Curve"].iloc[0]
    assert curve["availability"] == "unreadable"
    assert "unreadable" in curve["diagnostic"]
    with pytest.raises(SearchIncomplete):
        run(
            "property_value", "definitely absent",
            mutate=lambda objects: objects[2].VisibleProperties.append(MetadataOnlyProperty()),
        )
    assert not run(
        "property_value", "Other = absent",
        mutate=lambda objects: objects[2].VisibleProperties.append(MetadataOnlyProperty()),
    )["objects"]
    assert [value.payload["property_key"] for value in run(
        "property_value", "Other = absent", invert=True,
        mutate=lambda objects: objects[2].VisibleProperties.append(MetadataOnlyProperty()),
    )["properties"]] == ["Comment", "Quoted", "Empty", "XComponent", "Curve"]


def test_unreadable_applicable_formula_metadata_is_unknown_until_a_known_value_matches():
    class BrokenFormulaOutput:
        DefinitionType = "Formula"
        DiscreteValueCount = 1
        Unit = "N"
        QuantityName = "Force"

        @property
        def Formula(self):
            raise RuntimeError("unreadable")

    broken = prop("Formula", "Formula", "display known", output=BrokenFormulaOutput())
    assert [value.payload["property_key"] for value in run(
        "property_value", "display known",
        mutate=lambda objects: objects[2].VisibleProperties.append(broken),
    )["properties"]] == ["Formula"]
    with pytest.raises(SearchIncomplete, match="property_value"):
        run(
            "property_value", "secret formula",
            mutate=lambda objects: objects[2].VisibleProperties.append(broken),
        )


def test_throwing_output_and_invalid_discrete_count_remain_unknown():
    class ThrowingOutput:
        Inputs = []
        @property
        def Output(self): raise RuntimeError("output")

    class InvalidCount:
        DefinitionType = "Discrete"
        DiscreteValueCount = "three"
        Formula = None
        Unit = "N"
        QuantityName = "Force"

    values = [
        SimpleNamespace(APIName="Output", Name="Output", Caption="Output", StringValue="known", InternalValue=ThrowingOutput()),
        prop("Count", "Count", "known", output=InvalidCount()),
    ]
    for value in values:
        with pytest.raises(SearchIncomplete, match="property_value"):
            run(
                "property_value", "Tabular data",
                mutate=lambda objects, value=value: objects[2].VisibleProperties.append(value),
            )
    class ThrowingInternal:
        APIName = Name = Caption = "Internal"
        StringValue = "known"
        @property
        def InternalValue(self): raise RuntimeError("internal")

    with pytest.raises(SearchIncomplete, match="property_value"):
        run(
            "property_value", "absent",
            mutate=lambda objects: objects[2].VisibleProperties.append(ThrowingInternal()),
        )


def test_known_current_document_can_match_when_import_source_getter_is_unknown():
    class BrokenSource(Native):
        @property
        def ImportableObjectSourceId(self): raise RuntimeError("source")

    broken = BrokenSource(
        ObjectId=90, Name="Object", Parent=None, api_type="Native.Type",
        DataModelObjectCategory="Type", VisibleProperties=[],
    )
    assert search_tree(
        tree=GuardedTree([broken]), model=SimpleNamespace(), data_model=SimpleNamespace(ObjectTags=[]),
        identity=IDENTITY, filter_code="model", query="Current document",
        match_mode="contains", case_sensitive=False, include_hidden_properties=False, invert=False,
    )["objects"]
    with pytest.raises(SearchIncomplete, match="model"):
        search_tree(
            tree=GuardedTree([broken]), model=SimpleNamespace(), data_model=SimpleNamespace(ObjectTags=[]),
            identity=IDENTITY, filter_code="model", query="other source",
            match_mode="contains", case_sensitive=False, include_hidden_properties=False, invert=True,
        )


def test_unclassified_scope_and_unreadable_name_or_type_are_incomplete():
    with pytest.raises(SearchIncomplete, match="scoping"):
        run(
            "scoping", "Geometry",
            mutate=lambda objects: setattr(
                objects[2], "Location", SimpleNamespace(Ids=[1], SelectionType="Mystery")
            ),
        )

    class BrokenName(Native):
        @property
        def Name(self):
            raise RuntimeError("unreadable")

    bad_name = BrokenName(
        ObjectId=50, Parent=None, api_type="Native.Type",
        DataModelObjectCategory="Type", VisibleProperties=[],
    )
    with pytest.raises(SearchIncomplete, match="name"):
        search_tree(
            tree=GuardedTree([bad_name]), model=SimpleNamespace(), data_model=SimpleNamespace(ObjectTags=[]),
            identity=IDENTITY, filter_code="name", query="x", match_mode="contains",
            case_sensitive=False, include_hidden_properties=False, invert=True,
        )


def test_known_environment_and_scope_ids_can_short_circuit_unknown_labels():
    class BrokenAnalysisName(Native):
        @property
        def Name(self): raise RuntimeError("analysis name")

    analysis = BrokenAnalysisName(
        ObjectId=1, Parent=None, api_type="Ansys.ACT.Automation.Mechanical.Analysis",
        DataModelObjectCategory="Analysis", ObjectState="FullyDefined", Suppressed=False,
        VisibleProperties=[],
    )
    child = Native(
        ObjectId=2, Name="Load", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        DataModelObjectCategory="Force", ObjectState="FullyDefined", Suppressed=False,
        CoordinateSystem=None, Location=None, VisibleProperties=[],
    )
    assert search_tree(
        tree=GuardedTree([analysis, child]), model=SimpleNamespace(),
        data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
        filter_code="environment", query="1", match_mode="exact",
        case_sensitive=False, include_hidden_properties=False, invert=False,
    )["objects"]
    with pytest.raises(SearchIncomplete, match="environment"):
        search_tree(
            tree=GuardedTree([analysis, child]), model=SimpleNamespace(),
            data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
            filter_code="environment", query="other", match_mode="contains",
            case_sensitive=False, include_hidden_properties=False, invert=True,
        )

    class BrokenScope:
        ObjectId = 99
        @property
        def Name(self): raise RuntimeError("scope name")
        @property
        def DataModelObjectCategory(self): raise RuntimeError("scope category")

    child.Location = BrokenScope()
    assert search_tree(
        tree=GuardedTree([analysis, child]), model=SimpleNamespace(),
        data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
        filter_code="scoping", query="99", match_mode="exact",
        case_sensitive=False, include_hidden_properties=False, invert=False,
    )["objects"]
    with pytest.raises(SearchIncomplete, match="scoping"):
        search_tree(
            tree=GuardedTree([analysis, child]), model=SimpleNamespace(),
            data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
            filter_code="scoping", query="other", match_mode="contains",
            case_sensitive=False, include_hidden_properties=False, invert=True,
        )

    class BrokenType(Native):
        def GetType(self):
            raise RuntimeError("unreadable")

    bad_type = BrokenType(
        ObjectId=51, Name="Object", Parent=None, api_type="",
        DataModelObjectCategory="", VisibleProperties=[],
    )
    with pytest.raises(SearchIncomplete, match="type"):
        search_tree(
            tree=GuardedTree([bad_type]), model=SimpleNamespace(), data_model=SimpleNamespace(ObjectTags=[]),
            identity=IDENTITY, filter_code="type", query="x", match_mode="contains",
            case_sensitive=False, include_hidden_properties=False, invert=True,
        )
    readable_type_missing_category = Native(
        ObjectId=52, Name="Object", Parent=None, api_type="Native.Type",
        VisibleProperties=[],
    )
    with pytest.raises(SearchIncomplete, match="type"):
        search_tree(
            tree=GuardedTree([readable_type_missing_category]), model=SimpleNamespace(),
            data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
            filter_code="type", query="absent", match_mode="contains",
            case_sensitive=False, include_hidden_properties=False, invert=True,
        )
    for filter_code in ("coordinate_system", "graphics", "environment", "scoping"):
        with pytest.raises(SearchIncomplete, match=filter_code):
            search_tree(
                tree=GuardedTree([bad_type]), model=SimpleNamespace(),
                data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
                filter_code=filter_code, query="absent", match_mode="contains",
                case_sensitive=False, include_hidden_properties=False, invert=True,
            )


def _model_handle():
    return model_handle(
        handle_id="model-handle",
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


class Sessions:
    def admit_model(self, value, **kwargs):
        self.admitted = value, kwargs
        return "session"

    def operate(self, session, **kwargs):
        self.operated = session, kwargs
        return {"search": run(kwargs["args"]["filter"], kwargs["args"]["query"], match_mode=kwargs["args"]["match"], case_sensitive=kwargs["args"]["case_sensitive"], include_hidden_properties=kwargs["args"]["include_hidden_properties"], invert=kwargs["args"]["invert"], typed_selector=kwargs["args"]["typed_selector"])}


def test_registered_function_and_runtime_use_connected_settings_and_emit_found():
    declarations = discover_plugin_declarations(
        SOURCE, filename="mechanical_nodes.py", allow_reserved_ids=True,
        owner_id="mechanical.corex", allow_internal_metadata=True,
    )
    declaration = next(item for item in declarations if item.spec.type_id == "mechanical.search_tree")
    namespace = {}
    exec(SOURCE, namespace)
    sessions = Sessions()
    context = ExecutionContext(
        run_id="run", node_id="search", workspace_id="workspace",
        inputs={"model": _model_handle(), "filter": "property_value", "query": "Tabular data"},
        properties={
            "filter": "name", "query": "absent", "match": "contains",
            "case_sensitive": False, "include_hidden_properties": False, "invert": False,
        },
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
    )
    result = PythonFunctionAdapter(
        declaration.spec, namespace["search_mechanical_tree"]
    ).execute(context).outputs
    assert result["found"] is True
    assert [item.payload["property_key"] for item in result["properties"]] == ["XComponent"]
    assert sessions.operated[1]["operation"] == "search"
    assert sessions.operated[1]["args"]["filter"] == "property_value"


def test_runtime_resolves_validated_picker_before_grammar_and_rejects_stale_models():
    model = _model_handle()
    selector = encode_selector(
        "object", document_id="document", system_key="standalone",
        object_path="COREX structural A/Straße   Load", native_id=2,
    )
    sessions = Sessions()
    context = SimpleNamespace(
        run_id="run", workspace_id="workspace", inputs={"query": selector},
        properties={"filter": "scoping", "match": "contains", "case_sensitive": False, "include_hidden_properties": False, "invert": False},
        mechanical_sessions=sessions,
    )
    result = execute_search_tree(context, model)
    assert [item.payload["object_id"] for item in result["objects"]] == [2]
    assert sessions.operated[1]["args"]["typed_selector"]["native_id"] == 2
    missing = encode_selector(
        "object", document_id="document", system_key="standalone",
        object_path="missing", native_id=999,
    )
    context.inputs["query"] = missing
    with pytest.raises(ValueError, match="mechanical.selector_missing"):
        execute_search_tree(context, model)
    sessions.admit_model = lambda *_args, **_kwargs: (_ for _ in ()).throw(StaleMechanicalModelError("old"))
    with pytest.raises(ValueError, match="mechanical.stale_reference"):
        execute_search_tree(context, model)


def test_worker_runtime_loads_registered_search_function(tmp_path):
    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
        generation_root=tmp_path / "generations",
    )
    fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="run", workspace_id="workspace", runtime_snapshot=None,
        catalog_fingerprint=fingerprint, catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(), plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(fingerprint, plugin_digest),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.search_tree")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.search_tree"))
    runtime.clear()


def test_remote_snapshot_script_executes_non_tabular_tabular_and_scoped_objects_once():
    class Output:
        DefinitionType = "Discrete"
        DiscreteValueCount = 3
        Formula = None
        Unit = "N"
        QuantityName = "Force"

        @property
        def DiscreteValues(self):
            raise AssertionError("table cells must remain unread")

    scalar = SimpleNamespace(Value=12.5, Unit="N", QuantityName="Force")
    field = SimpleNamespace(Inputs=[object()], Output=Output())
    properties = [
        SimpleNamespace(APIName="Magnitude", Name="Magnitude", Caption="Magnitude", StringValue="12.5 N", InternalValue=scalar),
        SimpleNamespace(APIName="Curve", Name="Curve", Caption="Curve", StringValue="Tabular", InternalValue=field),
    ]
    plain = Native(
        ObjectId=70, Name="Plain body", Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.Body",
        DataModelObjectCategory="Body", Hidden=False, ObjectState="FullyDefined",
        Suppressed=False, VisibleProperties=[], Properties=[],
    )
    scoped = Native(
        ObjectId=71, Name="Scoped load", Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        DataModelObjectCategory="Force", ObjectState="FullyDefined", Suppressed=False,
        CoordinateSystem=None,
        Location=SimpleNamespace(
            ObjectId=None, Name="", Ids=(i for i in [1, 2]), SelectionType="GeometryEntities",
            DataModelObjectCategory="", TotalSelection=2,
        ),
        TabularData=SimpleNamespace(Keys=["Time", "Value"]),
        VisibleProperties=properties, Properties=properties,
    )

    detached = remote_objects([plain, scoped])
    assert [item.ObjectId for item in detached] == [70, 71]
    assert list(detached[1].Location.Ids) == [1, 2]
    remote_result = search_tree(
        tree=SimpleNamespace(AllObjects=detached), model=SimpleNamespace(), data_model=None,
        identity=IDENTITY, filter_code="property_value", query="12.5 N",
        match_mode="exact", case_sensitive=False, include_hidden_properties=False, invert=False,
    )
    direct_result = search_tree(
        tree=SimpleNamespace(AllObjects=[plain, scoped]), model=SimpleNamespace(),
        data_model=SimpleNamespace(ObjectTags=[]), identity=IDENTITY,
        filter_code="property_value", query="12.5 N", match_mode="exact",
        case_sensitive=False, include_hidden_properties=False, invert=False,
    )
    assert remote_result["properties"][0].payload["scalar_value"] == direct_result["properties"][0].payload["scalar_value"] == 12.5
    assert remote_result["properties"][0].payload["unit"] == "N"


def test_remote_snapshot_preserves_ironpython_unicode_em_dash_text():
    class IronUnicode(str):
        def __str__(self):
            raise UnicodeEncodeError("unknown", "\0", 0, 1, "")

    text = IronUnicode("COREX commands — Step 1")
    property_value = SimpleNamespace(
        APIName=text,
        Name=text,
        Caption=text,
        StringValue=text,
        InternalValue=None,
    )
    item = Native(
        ObjectId=79,
        Name=text,
        Parent=None,
        api_type=IronUnicode("Ansys.ACT.Automation.Mechanical.CommandSnippet"),
        DataModelObjectCategory=IronUnicode("CommandSnippet — Owned"),
        TabularData=SimpleNamespace(Keys=[IronUnicode("Load — Step")]),
        VisibleProperties=[property_value],
        Properties=[property_value],
    )
    detached = remote_objects([item])[0]
    assert detached.Name == "COREX commands — Step 1"
    assert detached.GetType().FullName == "Ansys.ACT.Automation.Mechanical.CommandSnippet"
    assert detached.DataModelObjectCategory == "CommandSnippet — Owned"
    assert detached.TabularData.Keys == ["Load — Step"]
    assert detached.VisibleProperties[0].Caption == "COREX commands — Step 1"
    assert detached.VisibleProperties[0].StringValue == "COREX commands — Step 1"


def test_remote_snapshot_preserves_query_necessary_getter_failures():
    class BrokenFields:
        ObjectId = 80
        Parent = None
        VisibleProperties = []

        @property
        def Name(self): raise RuntimeError("name")
        @property
        def DataModelObjectCategory(self): raise RuntimeError("category")
        @property
        def ObjectState(self): raise RuntimeError("state")
        @property
        def Suppressed(self): raise RuntimeError("suppressed")
        @property
        def ImportableObjectSourceId(self): raise RuntimeError("source")
        def GetType(self): raise RuntimeError("type")

    detached = remote_objects([BrokenFields()])
    for filter_code in ("name", "type", "state", "model", "graphics", "scoping"):
        with pytest.raises(SearchIncomplete, match=filter_code):
            search_tree(
                tree=SimpleNamespace(AllObjects=detached), model=SimpleNamespace(), data_model=None,
                identity=IDENTITY, filter_code=filter_code, query="absent",
                match_mode="contains", case_sensitive=False,
                include_hidden_properties=False, invert=True,
            )


def test_remote_snapshot_preserves_unreadable_formula_metadata():
    class BrokenFormula:
        DefinitionType = "Formula"
        DiscreteValueCount = 1
        Unit = "N"
        QuantityName = "Force"
        @property
        def Formula(self): raise RuntimeError("formula")

    item = Native(
        ObjectId=81, Name="Load", Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        DataModelObjectCategory="Force", ObjectState="FullyDefined", Suppressed=False,
        CoordinateSystem=None, Location=None,
        VisibleProperties=[prop("Formula", "Formula", "display known", output=BrokenFormula())],
    )
    detached = remote_objects([item])
    with pytest.raises(SearchIncomplete, match="property_value"):
        search_tree(
            tree=SimpleNamespace(AllObjects=detached), model=SimpleNamespace(), data_model=None,
            identity=IDENTITY, filter_code="property_value", query="secret formula",
            match_mode="contains", case_sensitive=False,
            include_hidden_properties=False, invert=False,
        )
    class BrokenInternal:
        APIName = Name = Caption = "Internal"
        StringValue = "known"
        @property
        def InternalValue(self): raise RuntimeError("internal")

    item.VisibleProperties = [BrokenInternal()]
    detached = remote_objects([item])
    with pytest.raises(SearchIncomplete, match="property_value"):
        search_tree(
            tree=SimpleNamespace(AllObjects=detached), model=SimpleNamespace(), data_model=None,
            identity=IDENTITY, filter_code="property_value", query="absent",
            match_mode="contains", case_sensitive=False,
            include_hidden_properties=False, invert=False,
        )


def test_accepted_catalogue_uses_the_same_difficult_relations_and_property_metadata(tmp_path):
    objects, model, data_model = fixture()
    manager = SimpleNamespace(NumberOfViews=0)
    manager.ExportModelViews = lambda path: Path(path).write_text("<Views/>", encoding="utf-8")
    identity = {
        **IDENTITY,
        "schema_version": 1,
        "producer_iteration": 0,
        "catalogue_id": str(uuid4()),
        "producer_node_id": "open",
        "producer_port": "info",
        "producer_path": "[0]",
        "view_export_path": str(tmp_path / "views.xml"),
    }
    rows = collect_catalogue_rows(
        tree=SimpleNamespace(AllObjects=objects),
        graphics=SimpleNamespace(ModelViewManager=manager),
        identity=identity,
        systems=[{"key": "standalone", "label": "Standalone"}],
        model=model,
        data_model=data_model,
    )
    catalogue_table(rows)
    relations = [row for row in rows if row["record_kind"] == "relation"]
    force_coordinate = next(row for row in relations if row["object_id"] == 2 and row["relation_kind"] == "coordinate_system")
    assert force_coordinate["related_label"] == "Frame α"
    assert force_coordinate["relation_role"] == "assignment"
    assert force_coordinate["property_key"] == "CoordinateSystem"
    assert not any(row["object_id"] == 2 and row["relation_kind"] == "body_visibility" and row["relation_status"] == "available" for row in relations)
    assert next(row for row in relations if row["object_id"] == 4 and row["relation_kind"] == "scope")["scope_kind"] == "no_explicit_scope"
    assert next(row for row in relations if row["object_id"] == 5 and row["relation_kind"] == "environment" and row["relation_status"] == "available")["activation_state"] == "ObjectActive"
    curve = next(row for row in rows if row["record_kind"] == "property" and row["property_key"] == "XComponent")
    assert curve["has_tabular_data"] is True and curve["definition_kind"] == "tabular"
