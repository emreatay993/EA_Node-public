# Purpose: Qualify bounded Mechanical query predicates and retain exact live evidence.
# Map: docs/agent_maps/subsystems/verification_testing_docs_hygiene.md
# Tests: tests/mechanical_catalogue/test_probe_contract.py
"""Pure qualification helpers; importing this module never launches a backend."""
from __future__ import annotations

import json
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

FILTERS = ("name", "tag", "type", "state", "coordinate_system", "model",
           "graphics", "environment", "scoping", "property_name", "property_value")
REQUIRED_ASSERTIONS = {
    "A": {"background_filters", "positive_imported_source_id", "native_tree_ui_forbidden"},
    "B": {"mechdb_reopen", "mechdat_reopen", "tree_boundary", "geometry", "loads",
          "selections", "snippets", "views", "source_integrity", "omissions_reported"},
    "C": {"direct_modelview_xml", "count_matches", "stable_indices", "duplicate_names",
          "rename_delete", "camera_restored"},
    "D": {"field_variables", "itable_mapping", "configured_result", "plot_data",
          "force_reaction", "mesh_worksheet", "layered_worksheet", "state_restored",
          "no_solve"},
    "E": {"standalone_archive_all", "standalone_archive_exclusions",
          "workbench_archive_all", "workbench_archive_exclusions",
          "missing_dependencies", "formats", "images", "script_scopes",
          "snippet_steps", "source_integrity", "owned_cleanup"},
}
NATIVE_ROUTE_CONTRACT = {
    "workbench_archive": {
        "format": "wbpz",
        "archive_arguments": ["IncludeSkippedFiles", "IncludeUserFiles",
                              "IncludeExternalImportedFiles", "FailIfMissingFiles"],
        "unarchive_arguments": ["ArchivePath", "ProjectPath"],
    },
    "standalone_archive": {
        "format": "mechpz",
        "archive_arguments": ["IncludeResultAndSolutionFiles", "IncludeUserFiles"],
        "external_imported_files_active": False,
    },
    "model_only_export": {
        "bridge": "dsdb", "formats": ["mechdb", "mechdat"], "archive": False,
        "claims_results": False, "claims_dependencies": False,
    },
}
APPROVED_RESULT_POLICY = {
    "id": "mechanical_catalogue_result_state_v1",
    "force_reaction": {"time_only": True, "require_initial_by": "Time",
                      "assign_by": False, "restore": ["By", "DisplayTime"],
                      "reject_other_modes": True},
    "configured_result": {"zero_sentinel_exception": {"initial_by": "Time",
                                                       "initial_set_number": 0,
                                                       "setter_must_reject_zero": True,
                                                       "resulting_set_must_be_valid": True,
                                                       "report_drift": True},
                          "restore_exact": ["By", "DisplayTime", "CalculateTimeHistory"],
                          "all_other_restore_failures_fatal": True},
}
STAGE_A_CHECKS = {
    *(category + ":" + suffix for category in FILTERS
      for suffix in ("positive", "negative", "invert")),
    "native:inventory", "shared:owning_analysis_absent", "shared:active",
    "shared:inactive", "shared:not_applicable", "coordinate:documented_solution",
    "scope:empty", "scope:confirmed_absence", "scope:roles", "scope:counts",
    "definition:tabular", "definition:constant", "definition:formula",
    "source:opaque_exact", "graphics:nonbody_not_applicable",
    *(category + ":unavailable" for category in FILTERS),
    "state:unchanged", "source:unchanged",
}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_options(format_code, *, include_results=True, include_user_files=True,
                    include_external_imported_files=True):
    """Map COREX archive choices to only the native options the format supports."""
    if format_code == "wbpz":
        return {"IncludeSkippedFiles": bool(include_results),
                "IncludeUserFiles": bool(include_user_files),
                "IncludeExternalImportedFiles": bool(include_external_imported_files)}
    if format_code == "mechpz":
        return {"IncludeResultAndSolutionFiles": bool(include_results),
                "IncludeUserFiles": bool(include_user_files)}
    if format_code in {"wbpj", "mechdb", "mechdat"}:
        return {}
    raise ValueError("Unsupported save format: " + format_code)


def save_route(source_family, format_code):
    if source_family == "workbench":
        if format_code == "mechpz":
            raise ValueError("Workbench sources archive only as .wbpz")
        if format_code in {"mechdb", "mechdat"}:
            return "model_only_dsdb_bridge"
        if format_code in {"wbpj", "wbpz"}:
            return "native_workbench"
    elif source_family == "standalone" and format_code in {"mechdb", "mechdat", "mechpz"}:
        return "native_standalone"
    raise ValueError("Unsupported source/format route")


def parse_model_views(path, expected_count):
    views = []
    for index, child in enumerate(ET.parse(path).getroot()):
        if child.tag.split("}")[-1] != "ModelView":
            continue
        if "Name" not in child.attrib:
            raise ValueError("ModelView is missing Name")
        views.append({"index": index, "name": child.attrib["Name"]})
    if len(views) != expected_count:
        raise ValueError("ModelView count mismatch")
    return views


class SearchIncomplete(ValueError):
    """A required getter failed, so a complete match decision is impossible."""


class DataOnlyTree:
    """Expose the inventory while making native UI search calls fail immediately."""

    def __init__(self, tree):
        self._tree = tree

    @property
    def AllObjects(self):
        return self._tree.AllObjects

    def __getattr__(self, name):
        raise AssertionError("Native tree UI access forbidden: " + name)


def relation(values=(), *, status="available", exact=False):
    return {"status": status, "values": list(values), "exact": exact}


def _operand(text):
    text = text.strip()
    if not text.startswith('"'):
        if '"' in text:
            raise ValueError("Malformed quoted operand")
        return text
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed JSON-style quoted operand") from exc
    if not isinstance(value, str) or text[end:].strip():
        raise ValueError("Quoted operand must be one complete JSON string")
    return value


def property_value_query(query):
    """Return (optional caption, value, explicit-empty) using the fixed grammar."""
    quoted = escaped = False
    delimiter = None
    for index, char in enumerate(query):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "=" and not quoted:
            delimiter = index
            break
    if quoted or escaped:
        raise ValueError("Malformed JSON-style quoted operand")
    if delimiter is None:
        value = _operand(query)
        return None, value, bool(query.strip()) and value == ""
    caption = _operand(query[:delimiter])
    if not caption:
        raise ValueError("Property caption cannot be empty")
    raw_value = query[delimiter + 1:]
    value = _operand(raw_value)
    return caption, value, value == ""


def matches(record, category, query, *, invert=False, exact=False, case_sensitive=False,
            typed_identity=False):
    """Apply the fixed background predicate to an already detached relation."""
    if category not in FILTERS:
        raise ValueError("Unknown filter: " + category)
    if category == "scoping" and query.casefold() in {"partial", "lost", "lost scoping"}:
        raise ValueError("Historical partial/lost scoping is unsupported")
    item = record[category]
    if item["status"] == "unavailable":
        raise SearchIncomplete("mechanical.search_incomplete: " + category)
    if item["status"] == "not_applicable":
        return False
    if item["status"] != "available":
        raise ValueError("Unknown availability")
    if typed_identity:
        matched = query in item["values"]
        return not matched if invert else matched
    caption = None
    explicit_empty = False
    if category == "property_value":
        caption, query, explicit_empty = property_value_query(query)
    if not query and not explicit_empty:
        return not invert
    if category == "state":
        query = {"not licensed": "LicenseConflict", "underdefined": "UnderDefined"}.get(query.casefold(), query)
    exact = exact or item["exact"]
    normalize = (lambda s: str(s)) if case_sensitive else (lambda s: str(s).casefold())
    values = [normalize(v) for v in item["values"]]
    terms = re.findall(r"\S+", query) if category == "name" and not exact else [query]
    matched = all(any(normalize(term) == value if exact else normalize(term) in value
                      for value in values) for term in terms)
    if caption is not None:
        captions = [normalize(value) for value in item.get("captions", [])]
        caption_match = any(normalize(caption) == value if exact else normalize(caption) in value
                            for value in captions)
        matched = matched and caption_match
    return not matched if invert else matched


def field_definition(field):
    """Metadata-only classification: never access discrete sample values."""
    output = field.Output
    kind = str(output.DefinitionType)
    count = int(output.DiscreteValueCount)
    return {"kind": "formula" if kind == "Formula" else "tabular" if count > 1 else "constant",
            "has_tabular_data": kind == "Discrete" and count > 1,
            "row_count": count, "formula": str(output.Formula) if kind == "Formula" else "",
            "unit": str(output.Unit)}


def activation_relation(model, object_id, analysis_id):
    try:
        value = model.GetActivationStatusForAnalysis(object_id, analysis_id)
        name = str(value)
    except Exception:
        return relation(status="unavailable")
    if name == "ObjectActive":
        result = relation([analysis_id], exact=True)
    elif name == "ObjectInactive":
        result = relation([], exact=True)
    elif name == "ObjectNotApplicable":
        result = relation(status="not_applicable")
    else:
        result = relation(status="unavailable")
    return {**result, "activation_state": name}


def coordinate_relation(obj):
    """Use only explicit documented bindings for these qualified native types."""
    native_type = str(obj.GetType().FullName)
    fields = {
        "Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force": ("CoordinateSystem", False),
        "Ansys.ACT.Automation.Mechanical.Results.ProbeResults.ForceReaction": ("Orientation", True),
    }
    if native_type == "Ansys.ACT.Automation.Mechanical.NamedSelection":
        return {**relation(["Unspecified"]), "binding": "Unspecified", "property_key": ""}
    if native_type not in fields:
        return {**relation(status="unavailable"), "binding": "Unavailable", "property_key": ""}
    attribute, none_is_solution = fields[native_type]
    try:
        value = getattr(obj, attribute)
        if value is None:
            binding = "Solution" if none_is_solution else "Unspecified"
            return {**relation([binding]), "binding": binding, "property_key": attribute}
        return {**relation([str(value.Name)]), "binding": "Explicit assignment",
                "property_key": attribute, "related_object_id": int(value.ObjectId)}
    except Exception:
        return {**relation(status="unavailable"), "binding": "Unavailable", "property_key": attribute}


def scope_relation(obj, attributes):
    """The caller supplies the documented fields for this supported object type."""
    if not attributes:
        return {"status": "available", "roles": [{"role": "primary", "kind": "no_explicit_scope", "count": None}]}
    roles = []
    for role, attribute in attributes:
        try:
            value = getattr(obj, attribute)
            if value is None:
                roles.append({"role": role, "kind": "empty_explicit_scope", "count": 0})
            elif hasattr(value, "DataModelObjectCategory"):
                named = str(value.DataModelObjectCategory) == "NamedSelection"
                roles.append({"role": role, "kind": "named_selection" if named else "referenced_object",
                              "object_id": int(value.ObjectId), "name": str(value.Name),
                              "count": int(value.TotalSelection) if named else None})
            elif hasattr(value, "SelectionType"):
                ids = list(value.Ids)
                roles.append({"role": role, "kind": str(value.SelectionType) if ids else "empty_explicit_scope", "count": len(ids)})
            else:
                raise ValueError("Unclassified scope value")
        except Exception as exc:
            return {"status": "unavailable", "roles": roles, "error": str(exc)}
    return {"status": "available", "roles": roles}


def _load_evidence(root, name):
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("Missing or unsafe evidence file: " + name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError("Unreadable evidence file: " + name) from exc


def _owner_rows_are_exact(rows):
    return bool(rows) and all(isinstance(row.get("pid"), int) and
                              isinstance(row.get("created"), (int, float)) and
                              isinstance(row.get("role"), str) and row["role"]
                              for row in rows)


OWNER_EVIDENCE_FILES = (
    "standalone_modal_archive.json", "script_snippet.json", "layered_worksheet.json",
    "camera_restoration_v2.json", "enriched_workbench.json",
    "enriched_bridge_verification.json", "result_restoration.json",
    "external_model_source.json", "external_model_archive_followup.json",
    "workbench_archive_controls.json", "workbench_native_remaining.json",
)


def _recorded_owner_rows(root):
    rows = []
    for name in OWNER_EVIDENCE_FILES:
        report = _load_evidence(root, name)
        value = report.get("owners", report.get("owner", []))
        rows.extend(value if isinstance(value, list) else [value])
    return [row for row in rows if row]


def _validate_acceptance_evidence(root, report):
    required_files = {"external_model_qualified.json", "enriched_bridge_verification.json",
                      "camera_restoration_v2.json", "workbench_native_remaining.json",
                      "standalone_modal_archive.json", "layered_worksheet.json",
                      "script_snippet.json", "workbench_archive_controls.json",
                      "enriched_workbench.json", "t01_owner_cleanup_reconciliation.json",
                      "stage_a_qualified.json", "query_getters.json", "camera_qualified.json",
                      "remaining_embedded.json", "model_only_omission_receipt.json",
                      "isolated_export_verification.json", "result_policy_receipt.json"}
    listed = {name for row in report["stages"].values() for name in row.get("evidence", [])}
    if not required_files <= listed:
        raise ValueError("Accepted qualification omits required evidence linkage")
    stage_a = _load_evidence(root, "stage_a_qualified.json")
    checks = stage_a.get("result", {}).get("checks", [])
    if {row.get("name") for row in checks} != STAGE_A_CHECKS or len(checks) != 61 or not all(row.get("passed") is True for row in checks):
        raise ValueError("Stage A named checks failed")
    getters = _load_evidence(root, "query_getters.json")
    fields = {row.get("name"): row for row in getters.get("result", {}).get("fields", [])}
    expected_fields = {
        "COREX constant load": ("Discrete", 1, "None", "N"),
        "COREX tabular load": ("Discrete", 3, "None", "N"),
        "COREX formula load": ("Formula", 1, "50*time", "N"),
    }
    if getters.get("status") != "passed" or any((fields.get(name, {}).get("definition_type"), fields.get(name, {}).get("count"), fields.get(name, {}).get("formula"), fields.get(name, {}).get("unit")) != values for name, values in expected_fields.items()):
        raise ValueError("Field/Variable evidence failed")
    external = _load_evidence(root, "external_model_qualified.json")
    source_ids = external.get("positive_source_ids", [])
    if not source_ids or not all(isinstance(row.get("source_id"), str) and row["source_id"] for row in source_ids) or not any(row["source_id"] == "Setup::File1::COREX_IMPORTED_NODES_Nodes" for row in source_ids) or external.get("exact_id_match_ready") is not True or not external.get("external_included") or not external.get("external_excluded") or not external.get("missing_requested_dependency", {}).get("passed"):
        raise ValueError("External-model evidence does not prove source identity and archive controls")
    bridge = _load_evidence(root, "enriched_bridge_verification.json")
    if bridge.get("release") != 261 or bridge.get("status") != "passed" or not bridge.get("bridge_unchanged") or bridge.get("bridge_hash_before") != bridge.get("bridge_hash_after"):
        raise ValueError("Selected-model conversion evidence failed")
    output_paths = []
    output_hashes = []
    for format_code in ("mechdb", "mechdat"):
        row = bridge.get("converted", {}).get(format_code, {})
        if not all(row.get(key) for key in ("has_selection", "has_snippet", "has_load")) or row.get("analysis_count") != 2 or row.get("body_count") != 2 or row.get("views") != ["COREX export view"]:
            raise ValueError("Selected-model boundary evidence failed: " + format_code)
        output_paths.append(row.get("path"))
        output_hashes.append(row.get("sha256"))
    if len(set(output_paths)) != 2 or any(not isinstance(value, str) or len(value) != 64 for value in output_hashes):
        raise ValueError("Selected-model outputs are not distinct fingerprinted formats")
    camera = _load_evidence(root, "camera_restoration_v2.json")
    if camera.get("release") != 261 or camera.get("status") != "passed" or not camera.get("source_unchanged"):
        raise ValueError("Camera evidence failed")
    for name in ("success_path", "failure_path"):
        row = camera.get(name, {})
        expected_applied = [1, 0] if name == "success_path" else [1]
        if not row.get("restored") or row.get("initial") != row.get("final") or row.get("manager_count") != 0 or row.get("enumerated_count") != 2 or [view.get("index") for view in row.get("enumerated_views", [])] != [0, 1] or row.get("applied_indices") != expected_applied or row.get("mutated", {}).get("active_ids") == row.get("initial", {}).get("active_ids"):
            raise ValueError("Camera state restoration failed: " + name)
    if "injected camera enumeration failure" not in camera["failure_path"].get("error", ""):
        raise ValueError("Camera failure-path evidence is missing")
    catalogue = _load_evidence(root, "camera_qualified.json").get("camera", {})
    children = catalogue.get("direct_children", [])
    if catalogue.get("export_count") != 2 or catalogue.get("initial_count") != 0 or catalogue.get("final_count") != 0 or not catalogue.get("duplicate_rejected") or not catalogue.get("rename_collision_rejected") or not catalogue.get("restored") or [row.get("index") for row in children] != [0, 1] or any(row.get("tag") != "ModelView" for row in children):
        raise ValueError("Camera XML/edge-case evidence failed")
    native = _load_evidence(root, "workbench_native_remaining.json")
    mechanical = native.get("mechanical", {})
    if native.get("status") != "passed" or mechanical.get("times") != [1.0, 2.0, 3.0] or not mechanical.get("reader") or not mechanical.get("result_exists"):
        raise ValueError("Native Workbench result evidence failed")
    totals = [row.get("total") for row in mechanical.get("force_reaction", {}).get("rows", [])]
    if len(totals) != 3 or len(set(totals)) != 3:
        raise ValueError("ForceReaction addressing evidence failed")
    policy_receipt = _load_evidence(root, "result_policy_receipt.json")
    if policy_receipt.get("policy") != APPROVED_RESULT_POLICY:
        raise ValueError("Current approved result policy is missing")
    force = policy_receipt.get("force_reaction", {})
    if force.get("initial_by") != "Time" or force.get("assign_by") is not False or force.get("display_time_restored") is not True or force.get("by_unchanged") is not True or force.get("unsupported_modes") != "reject":
        raise ValueError("Approved ForceReaction policy evidence failed")
    drift = policy_receipt.get("configured_result", {})
    before = drift.get("before", {}); after = drift.get("after", {})
    if before.get("by") != "Time" or before.get("set_number") != 0 or after.get("by") != "Time" or after.get("display_time") != before.get("display_time") or after.get("calculate_time_history") != before.get("calculate_time_history") or not isinstance(after.get("set_number"), int) or after.get("set_number") <= 0 or after.get("set_number") == before.get("set_number") or "outside of the valid range" not in drift.get("set_number_restore_error", "") or drift.get("drift_reported") is not True or drift.get("other_restore_failures") != "fatal":
        raise ValueError("Approved configured-result drift evidence failed")
    modal = _load_evidence(root, "standalone_modal_archive.json")
    reopen = modal.get("reopen", {})
    if modal.get("status") != "passed" or not modal.get("source_unchanged") or not reopen.get("source_unavailable") or not reopen.get("reader") or reopen.get("itable_keys") != ["Mode", "Frequency"] or reopen.get("itable_metadata", {}).get("Frequency", {}).get("unit") != "Hz":
        raise ValueError("Standalone archive/modal evidence failed")
    modal_columns = reopen.get("itable_columns", {})
    modal_metadata = reopen.get("itable_metadata", {})
    if len(modal_columns.get("Mode", [])) != 6 or len(modal_columns.get("Frequency", [])) != 6 or modal_metadata.get("Mode", {}).get("relation") != "dependent" or modal_metadata.get("Frequency", {}).get("relation") != "dependent":
        raise ValueError("Modal ITable rows/relations failed")
    standalone_members = {name: row.get("members", []) for name, row in modal.get("archives", {}).items()}
    def member_facts(members, external_name):
        return (any(row.get("bytes", 0) > 0 and row.get("name", "").lower().endswith(".rst") for row in members),
                any(row.get("name", "").endswith(external_name) for row in members))
    if member_facts(standalone_members.get("all", []), "corex-user-marker.txt") != (True, True) or member_facts(standalone_members.get("no_results", []), "corex-user-marker.txt") != (False, True) or member_facts(standalone_members.get("no_user", []), "corex-user-marker.txt") != (True, False) or not reopen.get("result_exists"):
        raise ValueError("Standalone archive member evidence failed")
    image = reopen.get("image", {})
    image_path = Path(image.get("path", "")).resolve()
    if root not in image_path.parents or not image_path.is_file() or image.get("bytes", 0) <= 0 or image_path.stat().st_size != image.get("bytes") or _sha256(image_path) != image.get("sha256") or not image.get("fit_before_saved_view") or image.get("fit_after_apply"):
        raise ValueError("Image fit/hash/size evidence failed")
    layered = _load_evidence(root, "layered_worksheet.json")
    layer = layered.get("result", {}); layer_row = (layer.get("rows") or [{}])[0]
    if layered.get("status") != "passed" or layer.get("active_unit_system") != "StandardNMM" or layer.get("row_count") != 1 or layer_row.get("material") != "Structural Steel" or layer_row.get("thickness") != 1.5 or layer_row.get("angle") != 45.0 or layer_row.get("thickness_native_type") != "<class 'float'>" or layer_row.get("angle_native_type") != "<class 'float'>" or not all(layer.get("methods", {}).get(name) for name in ("GetMaterial", "GetThickness", "GetAngle")) or not layered.get("source_unchanged"):
        raise ValueError("Layered worksheet evidence failed")
    mesh = _load_evidence(root, "remaining_embedded.json").get("mesh_worksheet", {})
    if mesh != {"row_count": 1, "active": True, "named_selection": "COREX loaded face"}:
        raise ValueError("Mesh worksheet evidence failed")
    snippets = _load_evidence(root, "script_snippet.json")
    snippet_result = snippets.get("result", {}); script = snippet_result.get("script", {}); snippet_rows = snippet_result.get("snippets", []); input_row = snippet_result.get("input", {})
    expected_names = ["COREX structural A", "COREX structural B", "COREX thermal"]
    expected_snippets = [("All", 1, "/COM,COREX_OWNER_all\n/COM,USER_COMMAND_all"), ("ByNumber", 1, "/COM,COREX_OWNER_step1\n/COM,USER_COMMAND_step1"), ("ByNumber", 3, "/COM,COREX_OWNER_step3\n/COM,USER_COMMAND_step3")]
    input_path = Path(input_row.get("path", "")).resolve()
    input_text = input_path.read_text(encoding="utf-8", errors="replace") if root in input_path.parents and input_path.is_file() else ""
    if snippets.get("status") != "passed" or script.get("per_environment_count") != 3 or script.get("model_once_count") != 1 or [row.get("name") for row in script.get("per_environment", [])] != expected_names or [row.get("result") for row in script.get("per_environment", [])] != expected_names or [(row.get("mode"), row.get("step"), row.get("input")) for row in snippet_rows] != expected_snippets or any(row.get("issue_solve") for row in snippet_rows) or input_row.get("markers") != {"all": 3, "step1": 1, "step3": 1} or input_row.get("solve_lines") or input_row.get("bytes", 0) <= 0 or not input_text or input_path.stat().st_size != input_row.get("bytes") or input_text.count("COREX_OWNER_all") != 3 or input_text.count("COREX_OWNER_step1") != 1 or input_text.count("COREX_OWNER_step3") != 1 or any(line.strip().casefold() == "solve" for line in input_text.splitlines()) or not snippets.get("source_unchanged"):
        raise ValueError("Script/snippet evidence failed")
    archives = _load_evidence(root, "workbench_archive_controls.json")
    if archives.get("release") != 261 or not archives.get("source_unchanged") or archives.get("archive_call") != {
        "IncludeUserFiles": True, "IncludeSkippedFiles": True,
        "IncludeExternalImportedFiles": True, "FailIfMissingFiles": True,
    }:
        raise ValueError("Workbench archive control evidence failed")
    wb_members = archives.get("archive", {}).get("members", [])
    wb_reopen = archives.get("independent_reopen", {})
    if not any(row.get("bytes", 0) > 0 and row.get("name", "").lower().endswith(".rst") for row in wb_members) or not wb_reopen.get("result_file_exists") or not wb_reopen.get("result_reader_available") or wb_reopen.get("times") != [1.0, 2.0, 3.0]:
        raise ValueError("Workbench all-enabled result evidence failed")
    enriched = _load_evidence(root, "enriched_workbench.json")
    exclusions = {name: row.get("members", []) for name, row in enriched.get("archives", {}).items()}
    def wb_facts(members):
        return (any(name.lower().endswith(".rst") for name in members), any(name.endswith("corex-user-marker.txt") for name in members), any(name.endswith("import_files/fixture.step") for name in members))
    if not enriched.get("source_unchanged") or not enriched.get("bridge") or wb_facts(exclusions.get("no_results", [])) != (False, True, True) or wb_facts(exclusions.get("no_user", [])) != (True, False, True) or wb_facts(exclusions.get("no_external", [])) != (True, True, False):
        raise ValueError("Workbench exclusion/export evidence failed")
    omission = _load_evidence(root, "model_only_omission_receipt.json")
    if omission != {"route": "model_only_dsdb_bridge", "archive": False, "observed_missing": ["results"], "no_preservation_guarantee": ["results", "dependencies", "user_files", "imported_files", "workbench_topology"], "unmeasured_absence": ["dependencies", "user_files", "imported_files", "workbench_topology"], "source_unavailable_during_reopen": True}:
        raise ValueError("Model-only omission receipt failed")
    isolated = _load_evidence(root, "isolated_export_verification.json").get("result", {})
    formats = {row.get("format"): row for row in isolated.get("formats", [])}
    integrity = isolated.get("source_integrity", [])
    if not isolated.get("source_locations_unavailable") or not integrity or not all(row.get("matches") is True for row in integrity) or any(formats.get(name, {}).get("result_exists") is not False for name in ("mechdb", "mechdat")):
        raise ValueError("Model-only observed result/source evidence failed")
    cleanup = _load_evidence(root, "t01_owner_cleanup_reconciliation.json")
    cleanup_rows = cleanup.get("owners", [])
    recorded_rows = _recorded_owner_rows(root)
    identity = lambda row: (row.get("role"), row.get("pid"), row.get("created"))
    if cleanup.get("same_processes_remaining") or not _owner_rows_are_exact(cleanup_rows) or not _owner_rows_are_exact(recorded_rows) or sorted(map(identity, cleanup_rows)) != sorted(map(identity, recorded_rows)):
        raise ValueError("Owned-process cleanup evidence failed")


def validate_report(report, evidence_root=None):
    if report.get("schema_version") not in {2, 3} or report.get("release") != 261:
        raise ValueError("Unsupported qualification schema/release")
    if report.get("native_route_contract") != NATIVE_ROUTE_CONTRACT:
        raise ValueError("Native source-family route contract is incomplete")
    accepted = report.get("accepted")
    if not isinstance(accepted, bool):
        raise ValueError("accepted must be Boolean")
    if accepted and report.get("status") != "passed":
        raise ValueError("Accepted qualification must have passed status")
    if not accepted and report.get("status") == "passed":
        raise ValueError("Unaccepted qualification cannot have passed status")
    stages = report.get("stages", {})
    if set(stages) != set("ABCDE"):
        raise ValueError("Every qualification stage needs an explicit status")
    if any(row.get("status") not in {"passed", "failed", "not_run"} for row in stages.values()):
        raise ValueError("Invalid stage status")
    if report.get("accepted") and any(row["status"] != "passed" for row in stages.values()):
        raise ValueError("Incomplete qualification cannot be accepted")
    for row in stages.values():
        if row["status"] != "not_run" and not row.get("evidence"):
            raise ValueError("Executed stages require retained evidence")
    for stage, names in REQUIRED_ASSERTIONS.items():
        assertions = stages[stage].get("assertions", {})
        if set(assertions) != names:
            raise ValueError("Stage " + stage + " must name every required assertion")
        if stages[stage]["status"] == "passed" and not all(value is True for value in assertions.values()):
            raise ValueError("Passed stage has an unproved assertion: " + stage)
    if evidence_root is not None:
        root = Path(evidence_root).resolve()
        for row in stages.values():
            for name in row.get("evidence", []):
                path = (root / name).resolve()
                if root not in path.parents or not path.is_file():
                    raise ValueError("Missing or unsafe evidence file: " + name)
    required = {"native_workbench_archive", "native_standalone_archive", "model_only_export"}
    if set(report.get("routes", {})) != required:
        raise ValueError("Qualification must report each source-family route separately")
    export = report["routes"]["model_only_export"]
    if export.get("claims_results") or export.get("claims_dependencies") or export.get("archive"):
        raise ValueError("Selected-model export is model-only")
    if accepted:
        if report.get("schema_version") != 3 or report.get("result_policy") != APPROVED_RESULT_POLICY:
            raise ValueError("Acceptance requires the current approved result policy")
        for name, route in report["routes"].items():
            if route.get("status") != "passed":
                raise ValueError("Accepted qualification requires every route: " + name)
        if report.get("solver_runs") != 2 or report.get("owned_processes_remaining"):
            raise ValueError("Acceptance requires exactly two authorized solves and complete cleanup")
        if report.get("workbench_archive_contract") != {
            "archive": {"IncludeSkippedFiles": True, "IncludeUserFiles": True,
                        "IncludeExternalImportedFiles": True, "FailIfMissingFiles": True},
            "unarchive": {"ArchivePath": True, "ProjectPath": True},
        }:
            raise ValueError("Workbench native Archive/Unarchive contract is incomplete")
        if evidence_root is None:
            raise ValueError("Acceptance requires concrete evidence validation")
        _validate_acceptance_evidence(Path(evidence_root).resolve(), report)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    validate_report(json.loads(args.report.read_text(encoding="utf-8")), args.evidence_root)
    print("Probe result schema valid")
