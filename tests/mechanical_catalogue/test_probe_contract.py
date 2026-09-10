# Purpose: Keep capability qualification honest without importing or launching Mechanical.
# Map: docs/agent_maps/subsystems/verification_testing_docs_hygiene.md
# Tests: tests/mechanical_catalogue/test_probe_contract.py
import json
import hashlib
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.mechanical_catalogue.probe_capabilities import (
    APPROVED_RESULT_POLICY, DataOnlyTree, FILTERS, NATIVE_ROUTE_CONTRACT, OWNER_EVIDENCE_FILES, REQUIRED_ASSERTIONS, STAGE_A_CHECKS, SearchIncomplete, activation_relation, archive_options,
    coordinate_relation, field_definition, matches, parse_model_views, property_value_query, relation,
    save_route, scope_relation, validate_report,
)


def test_archive_options_use_only_supported_native_flags():
    assert archive_options("wbpz", include_results=False,
                           include_user_files=False,
                           include_external_imported_files=False) == {
        "IncludeSkippedFiles": False,
        "IncludeUserFiles": False,
        "IncludeExternalImportedFiles": False,
    }
    assert archive_options("mechpz", include_results=False,
                           include_user_files=False,
                           include_external_imported_files=True) == {
        "IncludeResultAndSolutionFiles": False,
        "IncludeUserFiles": False,
    }
    for format_code in ("wbpj", "mechdb", "mechdat"):
        assert archive_options(format_code) == {}
    assert save_route("workbench", "wbpz") == "native_workbench"
    assert save_route("workbench", "mechdb") == "model_only_dsdb_bridge"
    assert save_route("standalone", "mechpz") == "native_standalone"
    with pytest.raises(ValueError, match="only as"):
        save_route("workbench", "mechpz")


def test_all_categories_and_unknown_inversion():
    for category in FILTERS:
        row = {category: relation(["COREX value"])}
        assert matches(row, category, "COREX")
        assert not matches(row, category, "missing")
        assert matches(row, category, "missing", invert=True)
        row[category] = relation(status="unavailable")
        with pytest.raises(SearchIncomplete):
            matches(row, category, "missing", invert=True)
        row[category] = relation(status="not_applicable")
        assert not matches(row, category, "missing", invert=True)
    assert matches({"name": relation(["COREX named object"])}, "name", "object COREX")
    assert matches({"state": relation(["LicenseConflict"])}, "state", "Not licensed")
    assert not matches({"model": relation(["source-123"], exact=True)}, "model", "source")
    assert matches({"model": relation(["source-123"], exact=True)}, "model", "source-123", typed_identity=True)


def test_plain_text_and_property_value_grammar():
    assert matches({"name": relation(["Bolt\u2003Pretension A"])}, "name", "a\tbolt")
    assert not matches({"name": relation(["Bolt Pretension"])}, "name", "Bolt", exact=True)
    assert matches({"name": relation(['Bolt "A"'])}, "name", '"A"')
    item = relation(["Load = 100 N"])
    item["captions"] = ["Comment"]
    assert matches({"property_value": item}, "property_value", 'Comment = "Load = 100 N"')
    item = relation(['Bolt "A"'])
    item["captions"] = ["Comment"]
    assert matches({"property_value": item}, "property_value", 'Comment = "Bolt \\"A\\""')
    empty = relation([""])
    empty["captions"] = ["Comment"]
    assert matches({"property_value": empty}, "property_value", 'Comment = ""')
    assert not matches({"property_value": empty}, "property_value", 'Other = ""')
    assert property_value_query(r"Comment = C:\work\it's here") == ("Comment", r"C:\work\it's here", False)
    with pytest.raises(ValueError):
        property_value_query(' = "value"')
    with pytest.raises(ValueError):
        property_value_query('Comment = "unterminated')


def test_native_import_id_stays_opaque_and_exact():
    source_id = "Setup::File1::COREX_IMPORTED_NODES_Nodes"
    row = {"model": relation([source_id], exact=True)}
    assert matches(row, "model", source_id, typed_identity=True)
    assert not matches(row, "model", source_id.lower(), typed_identity=True)
    assert not matches(row, "model", "COREX_IMPORTED_NODES", typed_identity=True)


def test_model_view_parser_preserves_duplicate_names_and_indices(tmp_path):
    path = tmp_path / "views.xml"
    path.write_text('<Views><ModelView Name="same"/><Other/><ModelView Name="same"/></Views>', encoding="utf-8")
    assert parse_model_views(path, 2) == [{"index": 0, "name": "same"}, {"index": 2, "name": "same"}]
    with pytest.raises(ValueError, match="count"):
        parse_model_views(path, 3)
    path.write_text("<Views><ModelView/></Views>", encoding="utf-8")
    with pytest.raises(ValueError, match="Name"):
        parse_model_views(path, 1)


def test_tabular_metadata_never_reads_cells():
    class Variable:
        DefinitionType = "Discrete"
        DiscreteValueCount = 3
        Unit = "N"

        @property
        def DiscreteValues(self):
            raise AssertionError("Search cannot read cells")

    assert field_definition(SimpleNamespace(Output=Variable()))["has_tabular_data"]


def test_activation_uses_only_explicit_active_state():
    for state, expected in (("ObjectActive", [4]), ("ObjectInactive", [])):
        model = SimpleNamespace(GetActivationStatusForAnalysis=lambda *_: state)
        assert activation_relation(model, 3, 4)["values"] == expected
        assert activation_relation(model, 3, 4)["activation_state"] == state
    for state, expected in (("ObjectNotApplicable", "not_applicable"), ("new state", "unavailable")):
        model = SimpleNamespace(GetActivationStatusForAnalysis=lambda *_: state)
        assert activation_relation(model, 3, 4)["status"] == expected


def test_coordinate_binding_never_infers_global():
    def obj(native_type, **properties):
        return SimpleNamespace(GetType=lambda: SimpleNamespace(FullName=native_type), **properties)
    prefix = "Ansys.ACT.Automation.Mechanical."
    force = obj(prefix + "BoundaryConditions.Force", CoordinateSystem=SimpleNamespace(Name="frame", ObjectId=50))
    assert coordinate_relation(force)["related_object_id"] == 50
    force.CoordinateSystem = None
    assert coordinate_relation(force)["binding"] == "Unspecified"
    probe = obj(prefix + "Results.ProbeResults.ForceReaction", Orientation=None)
    assert coordinate_relation(probe)["binding"] == "Solution"
    assert coordinate_relation(obj(prefix + "NamedSelection"))["binding"] == "Unspecified"
    missing = obj(prefix + "BoundaryConditions.Force")
    assert coordinate_relation(missing)["status"] == "unavailable"
    assert coordinate_relation(obj("Extension.Force"))["status"] == "unavailable"


def test_scope_distinguishes_empty_absent_and_failed():
    assert scope_relation(object(), [])["roles"][0]["kind"] == "no_explicit_scope"
    empty = SimpleNamespace(Location=SimpleNamespace(SelectionType="GeometryEntities", Ids=[]))
    assert scope_relation(empty, [("primary", "Location")])["roles"][0]["kind"] == "empty_explicit_scope"
    assert scope_relation(object(), [("primary", "Location")])["status"] == "unavailable"
    named = SimpleNamespace(DataModelObjectCategory="NamedSelection", SelectionType="GeometryEntities", Ids=[1], ObjectId=2, Name="face", TotalSelection=1)
    assert scope_relation(SimpleNamespace(Location=named), [("primary", "Location")])["roles"][0]["kind"] == "named_selection"
    with pytest.raises(ValueError, match="Historical"):
        matches({"scoping": relation([])}, "scoping", "Partial")


def test_tree_guard_prohibits_native_search():
    tree = DataOnlyTree(SimpleNamespace(AllObjects=[1]))
    assert tree.AllObjects == [1]
    for name in ("Filter", "Find", "IsObjInTreeView"):
        with pytest.raises(AssertionError, match="forbidden"):
            getattr(tree, name)


def report(status="not_run"):
    evidence = [] if status == "not_run" else ["proof.json"]
    assertions = {stage: {name: status == "passed" for name in names}
                  for stage, names in REQUIRED_ASSERTIONS.items()}
    return {"schema_version": 2, "release": 261, "accepted": False, "status": "failed",
            "native_route_contract": deepcopy(NATIVE_ROUTE_CONTRACT),
            "stages": {key: {"status": status, "evidence": evidence,
                             "assertions": assertions[key]} for key in "ABCDE"},
            "routes": {
                "native_workbench_archive": {"status": status},
                "native_standalone_archive": {"status": status},
                "model_only_export": {"status": status, "archive": False,
                                      "claims_results": False, "claims_dependencies": False},
            }}


def test_report_cannot_hide_missing_qualification():
    payload = report()
    assert validate_report(payload) is payload
    payload["accepted"] = True
    payload["status"] = "passed"
    with pytest.raises(ValueError, match="Incomplete"):
        validate_report(payload)
    payload["accepted"] = False
    payload["status"] = "failed"
    payload["routes"]["model_only_export"]["claims_results"] = True
    with pytest.raises(ValueError, match="model-only"):
        validate_report(payload)


def test_accepted_report_requires_named_gates_and_real_evidence(tmp_path):
    payload = report("passed")
    payload.update(schema_version=3, accepted=True, status="passed", solver_runs=2,
                   owned_processes_remaining=[], result_policy=deepcopy(APPROVED_RESULT_POLICY),
                   workbench_archive_contract={
                       "archive": {"IncludeSkippedFiles": True, "IncludeUserFiles": True,
                                   "IncludeExternalImportedFiles": True, "FailIfMissingFiles": True},
                       "unarchive": {"ArchivePath": True, "ProjectPath": True}})
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"PNG evidence")
    input_path = tmp_path / "ds.dat"
    input_path.write_text("COREX_OWNER_all\n" * 3 + "COREX_OWNER_step1\nCOREX_OWNER_step3\n", encoding="utf-8")
    camera_catalogue = {"export_count": 2, "initial_count": 0, "final_count": 0, "duplicate_rejected": True, "rename_collision_rejected": True, "restored": True, "direct_children": [{"index": 0, "tag": "ModelView"}, {"index": 1, "tag": "ModelView"}]}
    evidence = {
        "stage_a_qualified.json": {"result": {"checks": [{"name": name, "passed": True} for name in STAGE_A_CHECKS]}},
        "query_getters.json": {"status": "passed", "result": {"fields": [{"name": "COREX constant load", "definition_type": "Discrete", "count": 1, "formula": "None", "unit": "N"}, {"name": "COREX tabular load", "definition_type": "Discrete", "count": 3, "formula": "None", "unit": "N"}, {"name": "COREX formula load", "definition_type": "Formula", "count": 1, "formula": "50*time", "unit": "N"}]}},
        "external_model_qualified.json": {"positive_source_ids": [{"source_id": "Setup::File1::COREX_IMPORTED_NODES_Nodes"}], "exact_id_match_ready": True, "external_included": True, "external_excluded": True, "missing_requested_dependency": {"passed": True}},
        "enriched_bridge_verification.json": {"release": 261, "status": "passed", "bridge_unchanged": True, "bridge_hash_before": "b" * 64, "bridge_hash_after": "b" * 64, "converted": {key: {"analysis_count": 2, "body_count": 2, "has_selection": True, "has_snippet": True, "has_load": True, "views": ["COREX export view"], "path": str(tmp_path / ("out." + key)), "sha256": character * 64} for key, character in (("mechdb", "d"), ("mechdat", "a"))}},
        "camera_qualified.json": {"camera": camera_catalogue},
        "camera_restoration_v2.json": {"release": 261, "status": "passed", "source_unchanged": True, "success_path": {"initial": {"active_ids": [1]}, "final": {"active_ids": [1]}, "mutated": {"active_ids": [2]}, "enumerated_count": 2, "enumerated_views": [{"index": 0}, {"index": 1}], "applied_indices": [1, 0], "restored": True, "manager_count": 0}, "failure_path": {"initial": {"active_ids": [1]}, "final": {"active_ids": [1]}, "mutated": {"active_ids": [2]}, "enumerated_count": 2, "enumerated_views": [{"index": 0}, {"index": 1}], "applied_indices": [1], "restored": True, "manager_count": 0, "error": "injected camera enumeration failure"}},
        "workbench_native_remaining.json": {"status": "passed", "mechanical": {"times": [1.0, 2.0, 3.0], "reader": True, "result_exists": True, "configured_result": {"restored": True}, "force_reaction": {"rows": [{"total": "1 N"}, {"total": "2 N"}, {"total": "3 N"}], "by_assignment_error": ""}}},
        "standalone_modal_archive.json": {"status": "passed", "source_unchanged": True, "archives": {"all": {"members": [{"name": "file.rst", "bytes": 5}, {"name": "corex-user-marker.txt", "bytes": 5}]}, "no_results": {"members": [{"name": "corex-user-marker.txt", "bytes": 5}]}, "no_user": {"members": [{"name": "file.rst", "bytes": 5}]}}, "reopen": {"source_unavailable": True, "result_exists": True, "reader": True, "itable_keys": ["Mode", "Frequency"], "itable_columns": {"Mode": list(range(6)), "Frequency": list(range(6))}, "itable_metadata": {"Mode": {"relation": "dependent"}, "Frequency": {"unit": "Hz", "relation": "dependent"}}, "image": {"path": str(image_path), "bytes": image_path.stat().st_size, "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(), "fit_before_saved_view": True, "fit_after_apply": False}}},
        "layered_worksheet.json": {"status": "passed", "source_unchanged": True, "result": {"active_unit_system": "StandardNMM", "row_count": 1, "rows": [{"material": "Structural Steel", "thickness": 1.5, "angle": 45.0, "thickness_native_type": "<class 'float'>", "angle_native_type": "<class 'float'>"}], "methods": {"GetMaterial": True, "GetThickness": True, "GetAngle": True}}},
        "remaining_embedded.json": {"mesh_worksheet": {"row_count": 1, "active": True, "named_selection": "COREX loaded face"}},
        "script_snippet.json": {"status": "passed", "source_unchanged": True, "result": {"script": {"per_environment_count": 3, "model_once_count": 1, "per_environment": [{"name": name, "result": name} for name in ("COREX structural A", "COREX structural B", "COREX thermal")]}, "snippets": [{"mode": "All", "step": 1, "issue_solve": False, "input": "/COM,COREX_OWNER_all\n/COM,USER_COMMAND_all"}, {"mode": "ByNumber", "step": 1, "issue_solve": False, "input": "/COM,COREX_OWNER_step1\n/COM,USER_COMMAND_step1"}, {"mode": "ByNumber", "step": 3, "issue_solve": False, "input": "/COM,COREX_OWNER_step3\n/COM,USER_COMMAND_step3"}], "input": {"path": str(input_path), "bytes": input_path.stat().st_size, "markers": {"all": 3, "step1": 1, "step3": 1}, "solve_lines": []}}},
        "workbench_archive_controls.json": {"release": 261, "source_unchanged": True, "archive_call": {"IncludeUserFiles": True, "IncludeSkippedFiles": True, "IncludeExternalImportedFiles": True, "FailIfMissingFiles": True}, "archive": {"members": [{"name": "file.rst", "bytes": 5}]}, "independent_reopen": {"result_file_exists": True, "result_reader_available": True, "times": [1.0, 2.0, 3.0]}},
        "enriched_workbench.json": {"source_unchanged": True, "archives": {"no_results": {"members": ["user_files/corex-user-marker.txt", "import_files/fixture.step"]}, "no_user": {"members": ["file.rst", "import_files/fixture.step"]}, "no_external": {"members": ["file.rst", "user_files/corex-user-marker.txt"]}}, "bridge": {"path": "selected.dsdb"}},
        "model_only_omission_receipt.json": {"route": "model_only_dsdb_bridge", "archive": False, "observed_missing": ["results"], "no_preservation_guarantee": ["results", "dependencies", "user_files", "imported_files", "workbench_topology"], "unmeasured_absence": ["dependencies", "user_files", "imported_files", "workbench_topology"], "source_unavailable_during_reopen": True},
        "isolated_export_verification.json": {"result": {"source_locations_unavailable": True, "source_integrity": [{"matches": True}], "formats": [{"format": "mechdb", "result_exists": False}, {"format": "mechdat", "result_exists": False}]}},
        "result_restoration.json": {},
        "result_policy_receipt.json": {"policy": deepcopy(APPROVED_RESULT_POLICY), "force_reaction": {"initial_by": "Time", "assign_by": False, "display_time_restored": True, "by_unchanged": True, "unsupported_modes": "reject"}, "configured_result": {"before": {"by": "Time", "set_number": 0, "display_time": "0 [sec]", "calculate_time_history": True}, "after": {"by": "Time", "set_number": 3, "display_time": "0 [sec]", "calculate_time_history": True}, "set_number_restore_error": "ValueError: input outside of the valid range", "drift_reported": True, "other_restore_failures": "fatal"}},
        "external_model_source.json": {},
        "external_model_archive_followup.json": {},
        "t01_owner_cleanup_reconciliation.json": {"owners": [], "same_processes_remaining": []},
    }
    owner_rows = []
    for index, name in enumerate(OWNER_EVIDENCE_FILES, 1):
        row = {"pid": index, "created": float(index), "role": "owner_" + str(index)}
        evidence[name]["owner"] = row
        owner_rows.append(row)
    evidence["t01_owner_cleanup_reconciliation.json"]["owners"] = owner_rows
    names = list(evidence)
    for row in payload["stages"].values():
        row["evidence"] = names
    for name, value in evidence.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    assert validate_report(payload, tmp_path) is payload
    camera_path = tmp_path / "camera_restoration_v2.json"
    camera = evidence["camera_restoration_v2.json"]
    camera["status"] = "failed"
    camera_path.write_text(json.dumps(camera), encoding="utf-8")
    with pytest.raises(ValueError, match="Camera evidence failed"):
        validate_report(payload, tmp_path)
    camera["status"] = "passed"
    camera_path.write_text(json.dumps(camera), encoding="utf-8")
    cleanup_path = tmp_path / "t01_owner_cleanup_reconciliation.json"
    cleanup = evidence["t01_owner_cleanup_reconciliation.json"]
    cleanup["same_processes_remaining"] = cleanup["owners"]
    cleanup_path.write_text(json.dumps(cleanup), encoding="utf-8")
    with pytest.raises(ValueError, match="cleanup evidence"):
        validate_report(payload, tmp_path)
    cleanup["same_processes_remaining"] = []
    cleanup_path.write_text(json.dumps(cleanup), encoding="utf-8")
    archive_path = tmp_path / "workbench_archive_controls.json"
    archive = evidence["workbench_archive_controls.json"]
    archive["archive_call"]["FailIfMissingFiles"] = False
    archive_path.write_text(json.dumps(archive), encoding="utf-8")
    with pytest.raises(ValueError, match="archive control"):
        validate_report(payload, tmp_path)
    archive["archive_call"]["FailIfMissingFiles"] = True
    archive_path.write_text(json.dumps(archive), encoding="utf-8")

    def reject(name, mutate, message):
        path = tmp_path / name
        original = deepcopy(evidence[name])
        mutate(evidence[name])
        path.write_text(json.dumps(evidence[name]), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            validate_report(payload, tmp_path)
        evidence[name] = original
        path.write_text(json.dumps(original), encoding="utf-8")

    reject("enriched_workbench.json", lambda value: value["archives"].update(no_results={}), "Workbench exclusion")
    reject("enriched_workbench.json", lambda value: value["archives"]["no_results"]["members"].append("file.rst"), "Workbench exclusion")
    reject("enriched_workbench.json", lambda value: value["archives"]["no_user"]["members"].append("user_files/corex-user-marker.txt"), "Workbench exclusion")
    reject("enriched_workbench.json", lambda value: value["archives"]["no_external"]["members"].append("import_files/fixture.step"), "Workbench exclusion")
    reject("external_model_qualified.json", lambda value: value.update(positive_source_ids=[{}]), "External-model")
    reject("external_model_qualified.json", lambda value: value.update(exact_id_match_ready=False), "External-model")
    reject("standalone_modal_archive.json", lambda value: value["archives"]["all"]["members"].pop(0), "Standalone archive member")
    reject("standalone_modal_archive.json", lambda value: value["archives"]["all"]["members"].pop(), "Standalone archive member")
    reject("standalone_modal_archive.json", lambda value: value["reopen"]["image"].update(fit_after_apply=True), "Image fit")
    reject("standalone_modal_archive.json", lambda value: value["reopen"]["image"].update(sha256="0" * 64), "Image fit")
    reject("standalone_modal_archive.json", lambda value: value["reopen"]["image"].update(bytes=999), "Image fit")
    reject("standalone_modal_archive.json", lambda value: value["reopen"]["itable_columns"].update(Mode=[1]), "Modal ITable")
    reject("standalone_modal_archive.json", lambda value: value["reopen"]["itable_metadata"]["Mode"].update(relation="independent"), "Modal ITable")
    reject("script_snippet.json", lambda value: value["result"]["script"].update(per_environment_count=2), "Script/snippet")
    reject("script_snippet.json", lambda value: value["result"]["script"]["per_environment"].reverse(), "Script/snippet")
    reject("script_snippet.json", lambda value: value["result"]["snippets"][1].update(mode="All"), "Script/snippet")
    reject("script_snippet.json", lambda value: value["result"]["snippets"][2].update(step=2), "Script/snippet")
    reject("script_snippet.json", lambda value: value["result"]["snippets"][0].update(input="changed"), "Script/snippet")
    original_input = input_path.read_text(encoding="utf-8")
    input_path.write_text(original_input.replace("COREX_OWNER_step1", "wrong"), encoding="utf-8")
    with pytest.raises(ValueError, match="Script/snippet"):
        validate_report(payload, tmp_path)
    input_path.write_text(original_input, encoding="utf-8")
    reject("remaining_embedded.json", lambda value: value.update(mesh_worksheet={}), "Mesh worksheet")
    reject("query_getters.json", lambda value: value["result"].update(fields=[]), "Field/Variable")
    reject("camera_qualified.json", lambda value: value["camera"]["direct_children"][0].update(tag="Other"), "Camera XML")
    reject("camera_qualified.json", lambda value: value["camera"]["direct_children"][1].update(index=3), "Camera XML")
    reject("enriched_bridge_verification.json", lambda value: value["converted"].pop("mechdat"), "boundary evidence")
    reject("enriched_bridge_verification.json", lambda value: value.update(bridge_hash_after="c" * 64), "conversion evidence")
    reject("isolated_export_verification.json", lambda value: value["result"].update(source_integrity=[]), "observed result/source")
    reject("workbench_archive_controls.json", lambda value: value["archive"].update(members=[]), "all-enabled result")
    reject("workbench_archive_controls.json", lambda value: value["independent_reopen"].update(result_reader_available=False), "all-enabled result")
    reject("t01_owner_cleanup_reconciliation.json", lambda value: value["owners"].pop(), "cleanup evidence")
    reject("result_policy_receipt.json", lambda value: value["force_reaction"].update(initial_by="ResultSet"), "ForceReaction policy")
    reject("result_policy_receipt.json", lambda value: value["configured_result"]["after"].update(display_time="1 [sec]"), "configured-result drift")
    reject("result_policy_receipt.json", lambda value: value["configured_result"]["after"].update(set_number=0), "configured-result drift")
    reject("result_policy_receipt.json", lambda value: value["configured_result"].update(other_restore_failures="ignore"), "configured-result drift")
    policy_path = tmp_path / "result_policy_receipt.json"
    policy_text = policy_path.read_text(encoding="utf-8")
    policy_path.unlink()
    with pytest.raises(ValueError, match="Missing"):
        validate_report(payload, tmp_path)
    policy_path.write_text(policy_text, encoding="utf-8")
    payload["stages"]["D"]["assertions"]["force_reaction"] = False
    with pytest.raises(ValueError, match="unproved"):
        validate_report(payload)
    payload["stages"]["D"]["assertions"]["force_reaction"] = True
    camera_path.unlink()
    with pytest.raises(ValueError, match="Missing"):
        validate_report(payload, tmp_path)


@pytest.mark.parametrize("mutation, message", [
    (lambda payload: payload.update(release=262), "schema/release"),
    (lambda payload: payload.update(status="failed"), "passed status"),
    (lambda payload: payload.update(solver_runs=3), "exactly two"),
    (lambda payload: payload["native_route_contract"]["workbench_archive"].update(format="mechpz"), "route contract"),
    (lambda payload: payload.pop("result_policy"), "current approved result policy"),
])
def test_accepted_report_rejects_inconsistent_top_level(tmp_path, mutation, message):
    payload = report("passed")
    payload.update(schema_version=3, accepted=True, status="passed", solver_runs=2,
                   owned_processes_remaining=[], result_policy=deepcopy(APPROVED_RESULT_POLICY))
    mutation(payload)
    with pytest.raises(ValueError, match=message):
        validate_report(payload)
