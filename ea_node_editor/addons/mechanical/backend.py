# Purpose: Open native Mechanical models and execute allowlisted read, graphics, mutation, and save operations.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_owner_protocol.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_result_tables.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_scripts.py, tests/mechanical_catalogue/test_snippets.py, tests/mechanical_catalogue/test_standalone_save.py, tests/mechanical_catalogue/test_workbench_save.py, tests/mechanical_catalogue/test_workbench_model_export.py
# Landmarks: MechanicalOwnerBackend; snippet_preflight; run_snippet; standalone_save; workbench_save; workbench_model_export; convert_workbench_model; open; close

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from ea_node_editor.addons.mechanical.contracts import CATALOGUE_MAX_ENCODED_BYTES
from ea_node_editor.addons.mechanical.inspection import collect_catalogue_rows, search_tree
from ea_node_editor.addons.mechanical.commands import (
    SCRIPT_EXECUTION_BODY,
    SCRIPT_PREFLIGHT_BODY,
    SNIPPET_EXECUTION_BODY,
    SNIPPET_PREFLIGHT_BODY,
    SNIPPET_ROLLBACK_BODY,
    compact_failure_payload,
    receipt_messages,
    snippet_object_values,
    snippet_receipt_messages,
    validate_script_payload,
    validate_snippet_payload,
    validate_snippet_preflight,
)
from ea_node_editor.addons.mechanical.graphics import (
    CAMERA_IDENTITY_FIELDS,
    CAMERA_SCRIPT_BODY,
    IMAGE_PREFLIGHT_SCRIPT_BODY,
    IMAGE_SCRIPT_BODY,
    build_camera_views,
)
from ea_node_editor.addons.mechanical.saving import (
    MODEL_EXPORT_SNAPSHOT_BODY,
    STANDALONE_SAVE_BODY,
    compare_model_export_snapshot,
    model_export_native_owner_map,
    model_export_owner_identity,
    save_receipt_message,
    validate_model_export_save_receipt,
    validate_model_export_snapshot,
    validate_native_save_receipt,
    validate_staged_bundle,
    SaveStaging,
    companion_path,
    validate_archive_inclusions,
    validate_workbench_archive_structure,
    validate_workbench_project_bundle,
)
from ea_node_editor.addons.mechanical.workbench import (
    WORKBENCH_MODEL_COMPONENT_PREDICATE,
    WORKBENCH_MODEL_EXPORT_BODY,
    WORKBENCH_SAVE_BODY,
    validate_workbench_model_export_receipt,
    validate_workbench_model_export_snapshots,
    validate_workbench_semantic_snapshots,
    validate_workbench_save_receipt,
)
from ea_node_editor.runtime_contracts import ImageValue
from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.addons.mechanical.tables import (
    DEFINITION_ENCODED_MAX_BYTES,
    DEFINITION_SCRIPT_BODY,
    build_definition_tables,
)

LIFECYCLE_OPERATIONS = frozenset(
    {
        "health", "open", "search", "definition_tables", "camera_views",
        "image_export", "script_preflight", "run_script",
        "snippet_preflight", "run_snippet", "close",
        "standalone_save", "workbench_save",
        "workbench_model_export", "convert_workbench_model",
    }
)


WORKBENCH_SYSTEMS_BODY = r'''import hashlib,json
try:
    unicode
except NameError:
    unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
''' + WORKBENCH_MODEL_COMPONENT_PREDICATE + r'''rows=[]
for system in GetAllSystems():
    component_ids=[_corex_text(component.UserId) for component in system.Components]
    if not _corex_has_model(component_ids):
        continue
    container=system.GetContainer(ComponentName='Model')
    rows.append({'key':_corex_text(system.Name),'label':_corex_text(system.DisplayText),'model_key':_corex_text(container.Name)})
encoded=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf-8')
stream=open(_corex_data['native_output_path'],'wb')
try:stream.write(encoded)
finally:stream.close()
wb_script_result=json.dumps({'marker':'corex-workbench-systems-v1','byte_length':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()},separators=(',',':'))'''


def _data_script(data: Mapping[str, Any], body: str) -> str:
    encoded = base64.b64encode(json.dumps(dict(data)).encode()).decode("ascii")
    return (
        "import base64,json\n_corex_data=json.loads(base64.b64decode("
        + repr(encoded)
        + ").decode('utf-8'))\n"
        + body
    )


def _read_native_json_file(
    output: Path,
    raw_receipt: object,
    *,
    max_bytes: int,
    label: str,
    expected: Mapping[str, object] | None = None,
) -> Any:
    receipt = (
        json.loads(raw_receipt)
        if type(raw_receipt) is str
        else dict(raw_receipt) if isinstance(raw_receipt, Mapping) else None
    )
    expected = dict(expected or {})
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"byte_length", "sha256", *expected}
        or any(receipt[key] != value for key, value in expected.items())
        or type(receipt["byte_length"]) is not int
        or not 0 < receipt["byte_length"] <= max_bytes
        or type(receipt["sha256"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"]) is None
        or is_reparse_point(output)
        or not output.is_file()
        or output.lstat().st_size != receipt["byte_length"]
    ):
        raise RuntimeError(f"{label} returned an invalid native file receipt")
    encoded = output.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != receipt["sha256"]:
        raise RuntimeError(f"{label} native file digest changed")
    try:
        return json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} native file is not valid UTF-8 JSON") from exc


class MechanicalOwnerBackend:
    def __init__(self) -> None:
        self.app = self.mechanical = self.workbench = None
        self.tree = self.model = self.data_model = self.graphics = None
        self.systems: list[dict[str, Any]] = []
        self.work_root: Path | None = None
        self.system_name = ""
        self.interactive_model = False
        self.native_identities: list[dict[str, int]] = []
        self._snippet_rollback_path: Path | None = None
        self.source_path: Path | None = None
        self.work_path: Path | None = None
        self.release_code = 0
        self.mechanical_server_started = False
        self.connection_generation = 0

    def _launch_workbench(self, *, release: int, mode: str, workdir: Path, timeout_sec: float) -> Any:
        from ea_node_editor.addons.mechanical.workbench import launch_workbench_owner
        client = launch_workbench_owner(
            release_code=release,
            show_gui=mode == "interactive",
            client_workdir=str(workdir),
            server_workdir=str(workdir),
            timeout_sec=timeout_sec,
        )
        self.native_identities.append(dict(client.identity))
        return client

    @staticmethod
    def _require_receipt(value: Any, operation: str) -> None:
        if value is not True:
            raise RuntimeError(f"Workbench {operation} failed; inspect its native diagnostic log")

    def execute(self, operation: str, args: Mapping[str, Any]) -> dict[str, Any]:
        if operation not in LIFECYCLE_OPERATIONS:
            raise ValueError(f"Unsupported Mechanical owner operation: {operation!r}")
        if operation in {"health", "close"}:
            if args:
                raise ValueError(f"Mechanical owner operation {operation!r} does not accept arguments")
            if operation == "close":
                self.close()
            return {"status": "ready" if operation == "health" else "closed"}
        if operation == "open":
            return self.open(args)
        if operation == "search":
            return self.search(args)
        if operation == "camera_views":
            return self.camera_views(args)
        if operation == "image_export":
            return self.image_export(args)
        if operation == "script_preflight":
            return self.script_preflight(args)
        if operation == "run_script":
            return self.run_script(args)
        if operation == "snippet_preflight":
            return self.snippet_preflight(args)
        if operation == "run_snippet":
            return self.run_snippet(args)
        if operation == "standalone_save":
            return self.standalone_save(args)
        if operation == "workbench_save":
            return self.workbench_save(args)
        if operation == "workbench_model_export":
            return self.workbench_model_export(args)
        if operation == "convert_workbench_model":
            return self.convert_workbench_model(args)
        return self.definition_tables(args)

    def _execute_native_script(self, script: str) -> Any:
        return (
            self.app.execute_script(script)
            if self.app is not None
            else self.mechanical.run_python_script(script)
        )

    def _execute_native_json(
        self,
        args: Mapping[str, Any],
        body: str,
        *,
        prefix: str,
        label: str,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> Any:
        if self.work_root is None:
            raise RuntimeError(f"{label} working root is unavailable")
        output = self.work_root / f"{prefix}-{uuid4().hex}.json"
        try:
            raw = self._execute_native_script(
                _data_script({**dict(args), "native_output_path": str(output)}, body)
            )
            return _read_native_json_file(
                output,
                raw,
                max_bytes=max_bytes,
                label=label,
            )
        finally:
            output.unlink(missing_ok=True)

    def _model_export_semantics(
        self,
        identity: Mapping[str, Any],
        *,
        owner_tree: list[dict[str, Any]],
        native_owner_ids: list[int],
        label: str,
    ) -> dict[str, Any]:
        if self.tree is None or self.model is None or self.work_root is None:
            raise RuntimeError(f"{label} model state is unavailable")
        searched = search_tree(
            tree=self.tree,
            model=self.model,
            data_model=self.data_model,
            identity=identity,
            filter_code="name",
            query="",
            match_mode="contains",
            case_sensitive=False,
            include_hidden_properties=False,
            invert=False,
        )
        object_values = list(searched["objects"])
        if not object_values or len(object_values) > 100_000:
            raise RuntimeError(f"{label} tree-owner inventory is empty or exceeds its bound")
        base_indices = model_export_native_owner_map(owner_tree, native_owner_ids)
        object_rows: dict[int, Mapping[str, Any]] = {}
        for item in object_values:
            object_id = item.payload["object_id"]
            if object_id in object_rows:
                raise RuntimeError(f"{label} tree-owner identity is ambiguous")
            object_rows[object_id] = item.payload
        if set(object_rows) != set(base_indices):
            raise RuntimeError(f"{label} tree-owner mapping is incomplete")
        for object_id, payload in object_rows.items():
            index = base_indices[object_id]
            base = owner_tree[index]
            if (
                payload["display_name"] != base["name"]
                or payload["api_type"] != base["api_type"]
            ):
                raise RuntimeError(f"{label} tree-owner mapping is misaligned")
            parent_id = payload["parent_id"]
            if parent_id is not None:
                parent_index = base["parent_index"]
                if (
                    parent_index is None
                    or native_owner_ids[parent_index] != parent_id
                ):
                    raise RuntimeError(f"{label} tree-owner parent mapping is misaligned")
        owner_identities = {
            object_id: model_export_owner_identity(owner_tree, index)
            for object_id, index in base_indices.items()
        }
        native_objects: dict[int, Any] = {}
        for obj in self.tree.AllObjects:
            object_id = int(obj.ObjectId)
            if object_id in native_objects:
                raise RuntimeError(f"{label} native tree-owner identity is ambiguous")
            native_objects[object_id] = obj
        if set(native_objects) != set(object_rows):
            raise RuntimeError(f"{label} native tree-owner mapping is incomplete")
        settings: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for item in searched["properties"]:
            payload = item.payload
            owner_id = payload["object_id"]
            owner = object_rows[owner_id]
            owner_identity = owner_identities[owner_id]
            api_type = owner["api_type"]
            required_definition = (
                owner["analysis_id"] is not None
                and owner["object_id"] != owner["analysis_id"]
                and ".Results." not in api_type
                and not api_type.endswith(".Solution")
                and not api_type.endswith(".CommandSnippet")
            )
            if not required_definition:
                continue
            if payload["property_key"] == "SolverFilesDirectory":
                analysis_id = owner["analysis_id"]
                if (
                    api_type
                    != "Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings"
                    or owner["parent_id"] != analysis_id
                ):
                    raise RuntimeError(
                        f"{label} SolverFilesDirectory requires an exact direct Analysis Settings owner"
                    )
                analysis = object_rows.get(analysis_id)
                native_analysis = native_objects.get(analysis_id)
                if (
                    type(analysis_id) is not int
                    or analysis is None
                    or native_analysis is None
                    or not analysis["api_type"].endswith(".Analysis")
                ):
                    raise RuntimeError(
                        f"{label} SolverFilesDirectory analysis owner is unavailable or ambiguous"
                    )
                try:
                    working_dir = str(native_analysis.WorkingDir or "")
                except Exception as exc:
                    raise RuntimeError(
                        f"{label} native analysis WorkingDir is unavailable"
                    ) from exc
                if (
                    not working_dir
                    or payload["value_status"] != "available"
                    or os.path.normcase(os.path.abspath(payload["display_value"]))
                    != os.path.normcase(os.path.abspath(working_dir))
                ):
                    raise RuntimeError(
                        f"{label} SolverFilesDirectory does not match its native analysis WorkingDir"
                    )
                diagnostics.append({
                    **owner_identity,
                    "property_key": payload["property_key"],
                    "reason": "runtime_location:SolverFilesDirectory",
                })
                continue
            if payload["value_status"] != "available":
                diagnostics.append({
                    **owner_identity,
                    "property_key": payload["property_key"],
                    "reason": payload["value_status"],
                })
                continue
            settings.append({
                **owner_identity,
                "property_key": payload["property_key"],
                "caption": payload["caption"],
                "display_value": payload["display_value"],
                "definition_kind": payload["definition_kind"],
                "scalar_value": payload["scalar_value"],
                "unit": payload["unit"],
                "quantity_name": payload["quantity_name"],
                "formula": payload["formula"],
                "has_tabular_data": payload["has_tabular_data"],
                "tables": [
                    {
                        key: descriptor[key]
                        for key in (
                            "table_family", "definition_kind", "row_count", "column_count"
                        )
                    }
                    for descriptor in payload["tables"]
                ],
            })
        field_sources: list[dict[str, Any]] = []
        field_owners: list[dict[str, Any]] = []
        for obj in native_objects.values():
            object_id = int(obj.ObjectId)
            owner = object_rows.get(object_id)
            if owner is None:
                continue
            try:
                properties = list(obj.VisibleProperties)
            except Exception:
                continue
            for ordinal, prop in enumerate(properties):
                keys = []
                for name in ("APIName", "Name"):
                    try:
                        value = str(getattr(prop, name) or "")
                    except Exception:
                        value = ""
                    if value and value != "None":
                        keys.append(value)
                key = keys[0] if keys else f"property:{ordinal}"
                try:
                    field = getattr(obj, key)
                    is_field = field is not None and (
                        hasattr(field, "Inputs") or hasattr(field, "Output")
                    )
                except Exception:
                    is_field = False
                if is_field:
                    field_sources.append({
                        "kind": "property",
                        "object_id": object_id,
                        "object_path": owner["object_path"],
                        "property_key": key,
                    })
                    field_owners.append(owner_identities[object_id])
        definitions: list[str] = []
        if field_sources:
            result = self.definition_tables({
                "sources": field_sources,
                "family": "model_definition",
                "table": "",
                "table_selector": None,
                "component": "all",
                "units": "source",
                "native_output_path": str(
                    self.work_root / f"native-definitions-export-{uuid4().hex}.json"
                ),
            })["definition_tables"]
            source_owners: dict[tuple[str, str], dict[str, Any]] = {}
            for source, owner_identity in zip(field_sources, field_owners, strict=True):
                source_key = (source["object_path"], source["property_key"])
                if source_key in source_owners:
                    raise RuntimeError(f"{label} definition owner is ambiguous")
                source_owners[source_key] = owner_identity
            definitions_frame = result["definitions"].to_pandas().copy()
            if not {"object_path", "property_key"}.issubset(definitions_frame.columns):
                raise RuntimeError(f"{label} Definitions owner columns are unavailable")
            normalized_paths = []
            for object_path, property_key in zip(
                definitions_frame["object_path"],
                definitions_frame["property_key"],
                strict=True,
            ):
                owner_identity = source_owners.get((str(object_path), str(property_key)))
                if owner_identity is None:
                    raise RuntimeError(f"{label} Definitions owner mapping is missing")
                normalized_paths.append(owner_identity["object_path"])
            definitions_frame["object_path"] = normalized_paths
            definitions = [
                json.dumps(
                    {
                        "sources": [
                            {
                                "kind": source["kind"],
                                **owner_identity,
                                "property_key": source["property_key"],
                            }
                            for source, owner_identity in zip(
                                field_sources, field_owners, strict=True
                            )
                        ],
                        "tables": [
                            json.loads(
                                table.to_pandas().to_json(
                                    orient="split", double_precision=15, force_ascii=False
                                )
                            )
                            for table in result["tables"]
                        ],
                        "definitions": json.loads(
                            definitions_frame.to_json(
                                orient="split", double_precision=15, force_ascii=False
                            )
                        ),
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            ]
        camera_identity = {
            key: identity[key]
            for key in CAMERA_IDENTITY_FIELDS
        }
        camera_result = self.camera_views({
            "include": "saved_and_current",
            "identity": camera_identity,
            "export_path": str(
                self.work_root / f"camera-views-export-{uuid4().hex}.xml"
            ),
            "restore_name": f"COREX restore {uuid4().hex}",
        })["camera_views"]
        camera_fields = (
            "kind", "name", "index", "focal_point", "view_vector", "up_vector",
            "scene_width", "scene_height", "length_unit", "availability_notes",
        )
        cameras = [
            {key: item.payload[key] for key in camera_fields}
            for item in camera_result["views"]
        ]
        return json.loads(json.dumps({
            "settings": settings,
            "definitions": definitions,
            "cameras": cameras,
            "unreadable_display_diagnostics": diagnostics,
        }, ensure_ascii=False, allow_nan=False))

    @staticmethod
    def _write_model_export_snapshot(
        path: Path,
        base: object,
        semantics: Mapping[str, Any],
    ) -> dict[str, Any]:
        validated_base = validate_model_export_snapshot(base, complete=False)
        snapshot = {
            **{
                key: value
                for key, value in validated_base.items()
                if key != "native_owner_ids"
            },
            **semantics,
        }
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > 16 * 1024 * 1024:
            raise RuntimeError(
                "mechanical.save_failed: selected-model recovery snapshot exceeds its bound"
            )
        path.write_bytes(encoded)
        return validate_model_export_snapshot(snapshot)

    def script_preflight(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if set(args) != {"environments", "scope"} or (
            self.app is None and self.mechanical is None
        ):
            raise ValueError("Mechanical script preflight arguments or session state are invalid")
        environments = args["environments"]
        if (
            type(environments) is not list
            or len(environments) > 256
            or args["scope"] not in {"each_environment", "model_once"}
        ):
            raise ValueError("Mechanical script environment selection or Scope is invalid")
        for selector in environments:
            if not isinstance(selector, dict) or (
                selector.get("kind") == "typed"
                and (
                    set(selector) != {"kind", "object_id", "object_path"}
                    or type(selector["object_id"]) is not int
                    or selector["object_id"] < 0
                    or type(selector["object_path"]) is not str
                    or not selector["object_path"]
                )
                or selector.get("kind") == "text"
                and (
                    set(selector) != {"kind", "text"}
                    or type(selector["text"]) is not str
                    or not selector["text"]
                )
                or selector.get("kind") not in {"typed", "text"}
            ):
                raise ValueError("Mechanical script Environment selector is invalid")
        payload = self._execute_native_json(
            args,
            SCRIPT_PREFLIGHT_BODY,
            prefix="script-preflight",
            label="Mechanical script preflight",
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != {"analyses", "selected_ids"}
            or type(payload["analyses"]) is not list
            or type(payload["selected_ids"]) is not list
            or len(payload["analyses"]) > 256
            or any(
                not isinstance(row, dict)
                or set(row) != {"id", "name", "path"}
                or type(row["id"]) is not int
                or row["id"] < 0
                or type(row["name"]) is not str
                or type(row["path"]) is not str
                for row in payload["analyses"]
            )
            or any(type(value) is not int or value < 0 for value in payload["selected_ids"])
            or len(payload["selected_ids"]) != len(set(payload["selected_ids"]))
        ):
            raise RuntimeError("Mechanical script preflight returned an invalid result")
        ordered_ids = [row["id"] for row in payload["analyses"]]
        if payload["selected_ids"] != [
            value for value in ordered_ids if value in payload["selected_ids"]
        ]:
            raise RuntimeError("Mechanical script preflight did not preserve tree order")
        return {"status": "validated", "script_preflight": payload}

    def run_script(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "selected_ids", "scope", "code", "stop_on_error",
            "catalogue_identity", "view_export_path",
        }
        if set(args) != required or (self.app is None and self.mechanical is None):
            raise ValueError("Mechanical script arguments or session state are invalid")
        if (
            type(args["selected_ids"]) is not list
            or len(args["selected_ids"]) > 256
            or any(type(value) is not int or value < 0 for value in args["selected_ids"])
            or len(args["selected_ids"]) != len(set(args["selected_ids"]))
            or args["scope"] not in {"each_environment", "model_once"}
            or type(args["code"]) is not str
            or not args["code"].strip()
            or type(args["stop_on_error"]) is not bool
        ):
            raise ValueError("Mechanical script inputs are invalid")
        payload = validate_script_payload(
            self._execute_native_json(
                args,
                SCRIPT_EXECUTION_BODY,
                prefix="script-execution",
                label="Mechanical script execution",
            )
        )
        if not payload["success"]:
            return {"status": "failed", "script": compact_failure_payload(payload)}
        identity = dict(args["catalogue_identity"])
        identity["view_export_path"] = str(args["view_export_path"])
        return {
            "status": "executed",
            "rows": collect_catalogue_rows(
                tree=self.tree,
                graphics=self.graphics,
                identity=identity,
                systems=self.systems,
                status="script_completed",
                model=self.model,
                data_model=self.data_model,
                operations=receipt_messages(payload["receipts"]),
            ),
        }

    def snippet_preflight(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {"environments", "name", "steps", "selected_steps", "owner_node_token"}
        if set(args) != required or (self.app is None and self.mechanical is None):
            raise ValueError("Mechanical snippet preflight arguments or session state are invalid")
        environments = args["environments"]
        if (
            type(environments) is not list
            or len(environments) > 256
            or type(args["name"]) is not str
            or not args["name"].strip()
            or args["steps"] not in {"all", "selected"}
            or type(args["selected_steps"]) is not list
            or any(type(step) is not int or step < 1 for step in args["selected_steps"])
            or len(args["selected_steps"]) != len(set(args["selected_steps"]))
            or (args["steps"] == "selected" and not args["selected_steps"])
            or (args["steps"] == "all" and args["selected_steps"])
            or type(args["owner_node_token"]) is not str
            or not args["owner_node_token"]
            or len(args["owner_node_token"]) > 512
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in args["owner_node_token"])
        ):
            raise ValueError("Mechanical snippet inputs are invalid")
        for selector in environments:
            if not isinstance(selector, dict) or (
                selector.get("kind") == "typed"
                and (
                    set(selector) != {"kind", "object_id", "object_path"}
                    or type(selector["object_id"]) is not int
                    or selector["object_id"] < 0
                    or type(selector["object_path"]) is not str
                    or not selector["object_path"]
                )
                or selector.get("kind") == "text"
                and (
                    set(selector) != {"kind", "text"}
                    or type(selector["text"]) is not str
                    or not selector["text"]
                )
                or selector.get("kind") not in {"typed", "text"}
            ):
                raise ValueError("Mechanical snippet Environment selector is invalid")
        payload = self._execute_native_json(
            args,
            SNIPPET_PREFLIGHT_BODY,
            prefix="snippet-preflight",
            label="Mechanical snippet preflight",
        )
        return {
            "status": "validated",
            "snippet_preflight": validate_snippet_preflight(
                payload,
                owner_node_token=args["owner_node_token"],
                name=args["name"],
                steps=args["steps"],
                selected_steps=args["selected_steps"],
            ),
        }

    def run_snippet(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "plan", "owner_node_token", "name", "steps", "selected_steps",
            "commands", "issue_solve_command", "catalogue_identity", "view_export_path",
            "rollback_path",
        }
        if set(args) != required or (self.app is None and self.mechanical is None):
            raise ValueError("Mechanical snippet arguments or session state are invalid")
        plan = validate_snippet_preflight(
            args["plan"],
            owner_node_token=args["owner_node_token"],
            name=args["name"],
            steps=args["steps"],
            selected_steps=args["selected_steps"],
        )
        if (
            type(args["commands"]) is not str
            or not args["commands"].strip()
            or type(args["issue_solve_command"]) is not bool
        ):
            raise ValueError("Mechanical snippet mutation inputs are invalid")
        if self.work_root is None or self._snippet_rollback_path is not None:
            raise ValueError("Mechanical snippet rollback state is unavailable")
        rollback_path = Path(args["rollback_path"]).resolve()
        if rollback_path.parent != self.work_root.resolve() or rollback_path.exists():
            raise ValueError("Mechanical snippet rollback path is invalid")
        payload = None
        try:
            try:
                payload = self._execute_native_json(
                    args,
                    SNIPPET_EXECUTION_BODY,
                    prefix="snippet-execution",
                    label="Mechanical snippet execution",
                )
            finally:
                if rollback_path.is_file():
                    self._snippet_rollback_path = rollback_path
        except Exception:
            self.rollback_snippet_transaction()
            raise
        try:
            payload = validate_snippet_payload(payload, plan)
        except Exception:
            self.rollback_snippet_transaction()
            raise
        if not payload["success"]:
            self.rollback_snippet_transaction()
            return {"status": "failed", "snippet": payload}
        if self._snippet_rollback_path is None:
            raise RuntimeError("mechanical.restore_failed: snippet rollback record is missing")
        identity = dict(args["catalogue_identity"])
        identity["view_export_path"] = str(args["view_export_path"])
        try:
            snippet_object_values(payload["snippets"], identity)
            return {
                "status": "executed",
                "snippet": payload,
                "rows": collect_catalogue_rows(
                    tree=self.tree,
                    graphics=self.graphics,
                    identity=identity,
                    systems=self.systems,
                    status="snippet_completed",
                    model=self.model,
                    data_model=self.data_model,
                    operations=snippet_receipt_messages(payload["receipts"]),
                ),
            }
        except Exception as exc:
            self.rollback_snippet_transaction()
            return {
                "status": "failed",
                "snippet": {
                    "success": False,
                    "rollback_verified": True,
                    "error": f"Report production failed: {exc}"[:4096],
                    "receipts": [],
                    "snippets": [],
                },
            }

    def rollback_snippet_transaction(self) -> bool:
        path = self._snippet_rollback_path
        if path is None:
            return False
        try:
            raw = self._execute_native_script(
                _data_script({"rollback_path": str(path)}, SNIPPET_ROLLBACK_BODY)
            )
            payload = json.loads(raw) if type(raw) is str else None
            if payload != {"restored": True} or path.exists():
                raise RuntimeError("snippet rollback verification failed")
        except Exception as exc:
            raise RuntimeError(f"mechanical.restore_failed: {exc}") from exc
        self._snippet_rollback_path = None
        return True

    def commit_snippet_transaction(self) -> None:
        path = self._snippet_rollback_path
        if path is None:
            return
        path.unlink()
        self._snippet_rollback_path = None

    def standalone_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        common = {
            "format", "source_path", "destination_path", "work_path",
            "stage_path", "stage_companion", "verify_path", "files",
            "overwrite", "catalogue_identity", "view_export_path",
        }
        format_code = args.get("format")
        required = common | (
            {"include_results", "include_user_files"}
            if format_code == "mechpz"
            else set()
        )
        if (
            set(args) != required
            or format_code not in {"mechdb", "mechdat", "mechpz"}
            or self.app is None and self.mechanical is None
            or self.source_path is None
            or self.work_path is None
            or self.source_path.suffix.casefold() in {".wbpj", ".wbpz"}
            or Path(str(args["source_path"])).resolve() != self.source_path
            or Path(str(args["work_path"])).resolve() != self.work_path
            or type(args["overwrite"]) is not bool
            or type(args["files"]) is not list
            or any(type(value) is not str for value in args["files"])
        ):
            raise ValueError("Mechanical standalone save arguments or session state are invalid")
        if format_code == "mechpz" and (
            type(args["include_results"]) is not bool
            or type(args["include_user_files"]) is not bool
        ):
            raise ValueError("Mechanical standalone archive inclusion inputs are invalid")
        stage_path = Path(str(args["stage_path"])).resolve()
        stage_companion = (
            Path(str(args["stage_companion"])).resolve()
            if args["stage_companion"]
            else None
        )
        verify_path = Path(str(args["verify_path"])).resolve()
        if (
            stage_path.parent != verify_path.parent.parent
            or not verify_path.parent.is_dir()
            or any(verify_path.parent.iterdir())
            or stage_path.exists()
            or verify_path.exists()
            or stage_companion
            != companion_path(stage_path, str(format_code))
        ):
            raise ValueError("Mechanical standalone native staging paths are invalid")
        staging = SaveStaging(
            stage_path.parent,
            stage_path,
            stage_companion,
            verify_path,
        )
        native_args = {
            key: args[key]
            for key in (
                "format", "work_path", "stage_path", "stage_companion",
                "verify_path", "include_results", "include_user_files",
            )
            if key in args
        }
        payload = validate_native_save_receipt(
            self._execute_native_json(
                native_args,
                STANDALONE_SAVE_BODY,
                prefix="standalone-save",
                label="Mechanical standalone save",
            ),
            format_code=str(format_code),
            staging=staging,
        )
        identity = dict(args["catalogue_identity"])
        identity["view_export_path"] = str(args["view_export_path"])
        policy = (
            validate_archive_inclusions(
                staging.primary,
                work_path=self.work_path,
                result_directories=payload["result_directories"],
                user_directory=payload["user_directory"],
                include_results=args["include_results"],
                include_user_files=args["include_user_files"],
            )
            if format_code == "mechpz"
            else None
        )
        return {
            "status": "staged",
            "native_save": payload,
            "rows": collect_catalogue_rows(
                tree=self.tree,
                graphics=self.graphics,
                identity=identity,
                systems=self.systems,
                status="save_completed",
                model=self.model,
                data_model=self.data_model,
                operations=[save_receipt_message(
                    destination=Path(str(args["destination_path"])),
                    source=self.source_path,
                    format_code=str(format_code),
                    files=[Path(value) for value in args["files"]],
                    overwrite=bool(args["overwrite"]),
                    archive_policy=policy,
                )],
            ),
        }

    def workbench_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        common = {
            "format", "source_path", "destination_path", "work_path",
            "stage_path", "stage_companion", "native_project", "verify_path",
            "snapshot_path", "files", "overwrite", "catalogue_identity", "view_export_path",
        }
        format_code = args.get("format")
        required = common | (
            {"include_results", "include_user_files", "include_external_imported_files"}
            if format_code == "wbpz"
            else set()
        )
        if (
            set(args) != required
            or format_code not in {"wbpj", "wbpz"}
            or self.workbench is None
            or self.mechanical is None
            or not self.system_name
            or self.source_path is None
            or self.work_path is None
            or self.source_path.suffix.casefold() not in {".wbpj", ".wbpz"}
            or Path(str(args["source_path"])).resolve() != self.source_path
            or Path(str(args["work_path"])).resolve() != self.work_path
            or type(args["overwrite"]) is not bool
            or type(args["files"]) is not list
            or any(type(value) is not str for value in args["files"])
        ):
            raise ValueError("Mechanical Workbench save arguments or session state are invalid")
        if format_code == "wbpz" and any(
            type(args[key]) is not bool
            for key in ("include_results", "include_user_files", "include_external_imported_files")
        ):
            raise ValueError("Mechanical Workbench archive inclusion inputs are invalid")
        stage_path = Path(str(args["stage_path"])).resolve()
        stage_companion = Path(str(args["stage_companion"])).resolve() if args["stage_companion"] else None
        native_project = Path(str(args["native_project"])).resolve()
        verify_path = Path(str(args["verify_path"])).resolve()
        snapshot_path = Path(str(args["snapshot_path"])).resolve()
        staging = SaveStaging(stage_path.parent, stage_path, stage_companion, verify_path, native_project)
        if (
            stage_path.exists()
            or verify_path.exists()
            or native_project.exists()
            or verify_path.parent != stage_path.parent / "v"
            or snapshot_path != stage_path.parent / "w.json"
            or snapshot_path.exists()
            or native_project != (stage_path if format_code == "wbpj" else stage_path.parent / "p" / "p.wbpj")
            or stage_companion != companion_path(stage_path, str(format_code))
            or not verify_path.parent.is_dir()
            or any(verify_path.parent.iterdir())
        ):
            raise ValueError("Mechanical Workbench native staging paths are invalid")
        systems_before = self._workbench_systems()
        was_interactive = self.interactive_model
        self.workbench.stop_mechanical_server(system_name=self.system_name)
        self.mechanical_server_started = False
        self.mechanical = self.tree = self.model = self.data_model = self.graphics = None
        native_args = {
            "format": format_code,
            "work_path": str(self.work_path),
            "stage_path": str(stage_path),
            "stage_companion": "" if stage_companion is None else str(stage_companion),
            "native_project": str(native_project),
            "verify_path": str(verify_path),
            "system": self.system_name,
            "snapshot_path": str(snapshot_path),
            **{
                key: args[key]
                for key in ("include_results", "include_user_files", "include_external_imported_files")
                if key in args
            },
        }
        raw = self.workbench.run_script_string(_data_script(native_args, WORKBENCH_SAVE_BODY))
        receipt = validate_workbench_save_receipt(raw, format_code=str(format_code))
        validate_staged_bundle(staging, format_code=str(format_code))
        semantic_proof = validate_workbench_semantic_snapshots(
            snapshot_path,
            receipt=receipt,
            format_code=str(format_code),
            work_path=self.work_path,
            native_project=native_project,
            stage_path=stage_path,
            verify_path=verify_path,
            include_results=bool(args.get("include_results", True)),
            include_user_files=bool(args.get("include_user_files", True)),
            include_external_imported_files=bool(
                args.get("include_external_imported_files", True)
            ),
        )
        if format_code == "wbpj":
            validate_workbench_project_bundle(staging)
            policy = None
        else:
            policy = {
                "results_requested": bool(args["include_results"]),
                "user_files_requested": bool(args["include_user_files"]),
                "external_imported_files_requested": bool(
                    args["include_external_imported_files"]
                ),
                "complete": all(
                    bool(args[key])
                    for key in (
                        "include_results", "include_user_files",
                        "include_external_imported_files",
                    )
                ),
                "exclusions": [
                    label
                    for key, label in (
                        ("include_results", "result/solution files"),
                        ("include_user_files", "user files"),
                        ("include_external_imported_files", "external imported files"),
                    )
                    if not args[key]
                ],
                **validate_workbench_archive_structure(stage_path),
            }
        self.interactive_model = False
        if was_interactive:
            self._edit_workbench_model()
        self._connect_workbench_model()
        systems_after = self._workbench_systems()
        if systems_after != systems_before:
            raise RuntimeError("mechanical.restore_failed: Workbench systems changed after save reconnect")
        self.systems = systems_after
        self.connection_generation += 1
        identity = dict(args["catalogue_identity"])
        identity["view_export_path"] = str(args["view_export_path"])
        return {
            "status": "staged",
            "native_save": receipt,
            "connection_changed": True,
            "connection_generation": self.connection_generation,
            "rows": collect_catalogue_rows(
                tree=self.tree,
                graphics=self.graphics,
                identity=identity,
                systems=self.systems,
                status="save_completed",
                model=self.model,
                data_model=self.data_model,
                operations=[save_receipt_message(
                    destination=Path(str(args["destination_path"])),
                    source=self.source_path,
                    format_code=str(format_code),
                    files=[Path(value) for value in args["files"]],
                    overwrite=bool(args["overwrite"]),
                    archive_policy=policy,
                    semantic_proof=semantic_proof,
                )],
            ),
        }

    def workbench_model_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "format", "source_path", "destination_path", "work_path",
            "bridge_path", "snapshot_path", "model_snapshot_path", "stage_path",
            "stage_companion", "verify_path", "files", "overwrite",
            "catalogue_identity", "view_export_path",
        }
        format_code = args.get("format")
        if (
            set(args) != required
            or format_code not in {"mechdb", "mechdat"}
            or self.workbench is None
            or self.mechanical is None
            or not self.system_name
            or self.source_path is None
            or self.work_path is None
            or self.work_root is None
            or self.source_path.suffix.casefold() not in {".wbpj", ".wbpz"}
            or Path(str(args["source_path"])).resolve() != self.source_path
            or Path(str(args["work_path"])).resolve() != self.work_path
            or type(args["overwrite"]) is not bool
            or type(args["files"]) is not list
            or any(type(value) is not str for value in args["files"])
        ):
            raise ValueError("Mechanical Workbench model-export arguments or session state are invalid")
        bridge = Path(str(args["bridge_path"])).resolve()
        snapshot_path = Path(str(args["snapshot_path"])).resolve()
        model_snapshot_path = Path(str(args["model_snapshot_path"])).resolve()
        root = bridge.parent.parent
        stage_path = Path(str(args["stage_path"])).resolve()
        stage_companion = Path(str(args["stage_companion"])).resolve()
        verify_path = Path(str(args["verify_path"])).resolve()
        if (
            bridge != root / "b" / "b.dsdb"
            or snapshot_path != root / "w.json"
            or model_snapshot_path != root / "m.json"
            or stage_path.parent != root
            or stage_companion != companion_path(stage_path, str(format_code))
            or verify_path != root / "v" / "v.mechdb"
            or bridge.exists()
            or snapshot_path.exists()
            or model_snapshot_path.exists()
            or bridge.parent.exists()
        ):
            raise ValueError("Mechanical Workbench model-export staging paths are invalid")
        bridge.parent.mkdir()
        source_snapshot_receipt = self._execute_native_script(
            _data_script(
                {
                    "native_output_path": str(model_snapshot_path),
                    "view_export_path": str(args["view_export_path"]),
                },
                MODEL_EXPORT_SNAPSHOT_BODY,
            )
        )
        source_base = validate_model_export_snapshot(
            _read_native_json_file(
                model_snapshot_path,
                source_snapshot_receipt,
                max_bytes=16 * 1024 * 1024,
                label="Mechanical selected-model snapshot",
            ),
            complete=False,
        )
        source_snapshot = self._write_model_export_snapshot(
            model_snapshot_path,
            source_base,
            self._model_export_semantics(
                dict(args["catalogue_identity"]),
                owner_tree=source_base["tree"],
                native_owner_ids=source_base["native_owner_ids"],
                label="Mechanical selected-model source",
            ),
        )
        systems_before = self._workbench_systems()
        was_interactive = self.interactive_model
        self.workbench.stop_mechanical_server(system_name=self.system_name)
        self.mechanical_server_started = False
        self.mechanical = self.tree = self.model = self.data_model = self.graphics = None
        raw = self.workbench.run_script_string(
            _data_script(
                {
                    "format": format_code,
                    "work_path": str(self.work_path),
                    "bridge_path": str(bridge),
                    "system": self.system_name,
                    "snapshot_path": str(snapshot_path),
                },
                WORKBENCH_MODEL_EXPORT_BODY,
            )
        )
        receipt = validate_workbench_model_export_receipt(
            raw, format_code=str(format_code)
        )
        if (
            bridge.stat().st_size != receipt["bridge_bytes"]
            or hashlib.sha256(bridge.read_bytes()).hexdigest() != receipt["bridge_sha256"]
        ):
            raise RuntimeError("mechanical.save_failed: private model bridge changed after export")
        workbench_proof = validate_workbench_model_export_snapshots(
            snapshot_path,
            receipt=receipt,
            work_path=self.work_path,
        )
        self.interactive_model = False
        if was_interactive:
            self._edit_workbench_model()
        self._connect_workbench_model()
        systems_after = self._workbench_systems()
        if systems_after != systems_before:
            raise RuntimeError(
                "mechanical.restore_failed: Workbench systems changed after selected-model export"
            )
        self.systems = systems_after
        self.connection_generation += 1
        source_after_base = self._execute_native_json(
            {"view_export_path": str(args["view_export_path"])},
            MODEL_EXPORT_SNAPSHOT_BODY,
            prefix="model-export-source-after",
            label="Mechanical selected-model source restoration",
            max_bytes=16 * 1024 * 1024,
        )
        source_after_base = validate_model_export_snapshot(
            source_after_base, complete=False
        )
        source_after = self._write_model_export_snapshot(
            self.work_root / f"model-export-source-after-{uuid4().hex}.json",
            source_after_base,
            self._model_export_semantics(
                dict(args["catalogue_identity"]),
                owner_tree=source_after_base["tree"],
                native_owner_ids=source_after_base["native_owner_ids"],
                label="Mechanical selected-model restored source",
            ),
        )
        model_proof = compare_model_export_snapshot(source_snapshot, source_after)
        identity = dict(args["catalogue_identity"])
        identity["view_export_path"] = str(args["view_export_path"])
        omissions = [
            "retained result files",
            "user files",
            "imported or external files",
            "Workbench topology and shared links",
            "Workbench design points and project dependencies",
        ]
        return {
            "status": "exported",
            "native_export": {
                "bridge_bytes": receipt["bridge_bytes"],
                "bridge_sha256": receipt["bridge_sha256"],
                "snapshot_bytes": model_snapshot_path.stat().st_size,
                "snapshot_sha256": hashlib.sha256(model_snapshot_path.read_bytes()).hexdigest(),
            },
            "connection_changed": True,
            "connection_generation": self.connection_generation,
            "rows": collect_catalogue_rows(
                tree=self.tree,
                graphics=self.graphics,
                identity=identity,
                systems=self.systems,
                status="save_completed",
                model=self.model,
                data_model=self.data_model,
                operations=[
                    save_receipt_message(
                        destination=Path(str(args["destination_path"])),
                        source=self.source_path,
                        format_code=str(format_code),
                        files=[Path(value) for value in args["files"]],
                        overwrite=bool(args["overwrite"]),
                        archive_policy={
                            "results_consumed": False,
                            "user_files_consumed": False,
                            "external_imported_files_consumed": False,
                            "complete": False,
                            "model_only": True,
                            "omissions": omissions,
                            "exclusions": omissions,
                        },
                        semantic_proof={
                            **workbench_proof,
                            **model_proof,
                            "model_only": True,
                            "conversion_owner": "separate_same_release_standalone",
                        },
                    )
                ],
            ),
        }

    def convert_workbench_model(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "format", "release_code", "bridge_path", "bridge_bytes",
            "bridge_sha256", "stage_path", "stage_companion", "verify_path",
            "model_snapshot_path", "model_snapshot_bytes", "model_snapshot_sha256",
        }
        format_code = args.get("format")
        if (
            set(args) != required
            or format_code not in {"mechdb", "mechdat"}
            or type(args["release_code"]) is not int
            or args["release_code"] < 261
            or any(
                type(args[key]) is not int or args[key] < 1
                for key in ("bridge_bytes", "model_snapshot_bytes")
            )
            or any(
                type(args[key]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", args[key]) is None
                for key in ("bridge_sha256", "model_snapshot_sha256")
            )
            or self.app is not None
            or self.mechanical is not None
            or self.workbench is not None
        ):
            raise ValueError("Mechanical selected-model conversion arguments are invalid")
        bridge = Path(str(args["bridge_path"])).resolve(strict=True)
        stage_path = Path(str(args["stage_path"])).resolve()
        stage_companion = Path(str(args["stage_companion"])).resolve()
        verify_path = Path(str(args["verify_path"])).resolve()
        snapshot_path = Path(str(args["model_snapshot_path"])).resolve(strict=True)
        root = stage_path.parent
        staging = SaveStaging(root, stage_path, stage_companion, verify_path)
        if (
            bridge != root / "b" / "b.dsdb"
            or snapshot_path != root / "m.json"
            or stage_companion != companion_path(stage_path, str(format_code))
            or verify_path != root / "v" / "v.mechdb"
            or not verify_path.parent.is_dir()
            or any(verify_path.parent.iterdir())
            or stage_path.exists()
            or stage_companion.exists()
            or bridge.stat().st_size != args["bridge_bytes"]
            or snapshot_path.stat().st_size != args["model_snapshot_bytes"]
            or hashlib.sha256(bridge.read_bytes()).hexdigest() != args["bridge_sha256"]
            or hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            != args["model_snapshot_sha256"]
        ):
            raise ValueError("Mechanical selected-model conversion staging identity is invalid")
        expected_snapshot = validate_model_export_snapshot(
            _read_native_json_file(
                snapshot_path,
                {
                    "byte_length": args["model_snapshot_bytes"],
                    "sha256": args["model_snapshot_sha256"],
                },
                max_bytes=16 * 1024 * 1024,
                label="Mechanical selected-model conversion source",
            )
        )
        self.work_root = root
        conversion_identity = {
            "schema_version": 1,
            "model_revision": 0,
            "producer_iteration": 0,
            "catalogue_id": "00000000-0000-0000-0000-000000000001",
            "producer_node_id": "conversion",
            "producer_port": "report",
            "producer_path": "[]",
            "run_id": "conversion",
            "session_id": "conversion",
            "document_id": "conversion",
            "source_key": "conversion",
            "system_key": "standalone",
        }
        from ansys.mechanical.core import App, global_variables

        app = App(version=int(args["release_code"]))
        self.app = app
        try:
            values = global_variables(app)
            if int(args["release_code"]) > 261 and (
                not callable(getattr(app, "open", None))
                or not callable(getattr(app, "save_as", None))
                or values.get("Tree") is None
                or values.get("Model") is None
                or values.get("DataModel") is None
                or values.get("Graphics") is None
            ):
                raise RuntimeError(
                    "mechanical.capability_unproved: later standalone release lacks selected-model conversion operations"
                )
            app.open(str(bridge))
            values = global_variables(app)
            self.tree, self.model, self.data_model, self.graphics = (
                values["Tree"], values["Model"], values["DataModel"], values["Graphics"]
            )
            bridge_base = self._execute_native_json(
                {"view_export_path": str(root / "bridge-views.xml")},
                MODEL_EXPORT_SNAPSHOT_BODY,
                prefix="model-export-bridge",
                label="Mechanical selected-model bridge verification",
                max_bytes=16 * 1024 * 1024,
            )
            bridge_base = validate_model_export_snapshot(
                bridge_base, complete=False
            )
            bridge_snapshot = self._write_model_export_snapshot(
                root / "bridge-model.json",
                bridge_base,
                self._model_export_semantics(
                    conversion_identity,
                    owner_tree=bridge_base["tree"],
                    native_owner_ids=bridge_base["native_owner_ids"],
                    label="Mechanical selected-model bridge",
                ),
            )
            proof = compare_model_export_snapshot(expected_snapshot, bridge_snapshot)
            app.save_as(str(stage_path), overwrite=False)
            validate_staged_bundle(staging, format_code=str(format_code))
            app.open(str(stage_path))
            values = global_variables(app)
            self.tree, self.model, self.data_model, self.graphics = (
                values["Tree"], values["Model"], values["DataModel"], values["Graphics"]
            )
            reopened_base = self._execute_native_json(
                {"view_export_path": str(root / "reopen-views.xml")},
                MODEL_EXPORT_SNAPSHOT_BODY,
                prefix="model-export-reopen",
                label="Mechanical selected-model independent reopen",
                max_bytes=16 * 1024 * 1024,
            )
            reopened_base = validate_model_export_snapshot(
                reopened_base, complete=False
            )
            reopened_snapshot = self._write_model_export_snapshot(
                root / "reopen-model.json",
                reopened_base,
                self._model_export_semantics(
                    conversion_identity,
                    owner_tree=reopened_base["tree"],
                    native_owner_ids=reopened_base["native_owner_ids"],
                    label="Mechanical selected-model independent stage reopen",
                ),
            )
            compare_model_export_snapshot(expected_snapshot, reopened_snapshot)
            receipt = {
                "schema_version": 1,
                "marker": "corex-workbench-model-export-v1",
                "format": format_code,
                "reopen_verified": True,
                "source_workbench_preserved": True,
                "bridge_bytes": bridge.stat().st_size,
                "stage_bytes": stage_path.stat().st_size,
                **proof,
            }
            validate_model_export_save_receipt(
                receipt, format_code=str(format_code), staging=staging
            )
            return {"status": "converted", "native_save": receipt}
        finally:
            app.close()
            self.app = None
            self.tree = self.model = self.data_model = self.graphics = None

    def image_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "objects", "views", "width", "height", "background", "fit_view",
            "output_paths", "view_export_path", "restore_name", "preflight_only",
        }
        if set(args) != required or (self.app is None and self.mechanical is None):
            raise ValueError("Mechanical image arguments or session state are invalid")
        if self.work_root is None:
            raise ValueError("Mechanical image working root is unavailable")
        objects, views = args["objects"], args["views"]
        width, height = args["width"], args["height"]
        if (
            type(objects) is not list
            or type(views) is not list
            or type(args["output_paths"]) is not list
            or any(type(value) is not str for value in args["output_paths"])
            or not objects
            or not views
            or len(objects) * len(views) > 256
            or type(width) is not int
            or type(height) is not int
            or not 64 <= width <= 8192
            or not 64 <= height <= 8192
            or width * height > 33_554_432
            or args["background"] not in {"white", "model"}
            or type(args["fit_view"]) is not bool
            or type(args["preflight_only"]) is not bool
        ):
            raise ValueError("Mechanical image dimensions, settings, or capture count are invalid")
        for selector in objects:
            if not isinstance(selector, dict) or (
                selector.get("kind") == "current" and set(selector) != {"kind"}
                or selector.get("kind") == "text" and (
                    set(selector) != {"kind", "text"}
                    or type(selector["text"]) is not str
                    or not selector["text"].strip()
                )
                or selector.get("kind") == "typed" and (
                    set(selector) != {"kind", "object_id", "object_path"}
                    or type(selector["object_id"]) is not int
                    or type(selector["object_path"]) is not str
                    or not selector["object_path"]
                )
                or selector.get("kind") not in {"current", "text", "typed"}
            ):
                raise ValueError("Mechanical image object selector is invalid")
        for selector in views:
            if not isinstance(selector, dict) or (
                selector.get("kind") == "current" and set(selector) != {"kind"}
                or selector.get("kind") == "text" and (
                    set(selector) != {"kind", "text"}
                    or type(selector["text"]) is not str
                    or not selector["text"].strip()
                )
                or selector.get("kind") == "typed" and (
                    set(selector) != {"kind", "index", "name"}
                    or type(selector["index"]) is not int
                    or selector["index"] < 0
                    or selector["name"] is not None and type(selector["name"]) is not str
                )
                or selector.get("kind") not in {"current", "text", "typed"}
            ):
                raise ValueError("Mechanical image view selector is invalid")
        if (
            type(args["restore_name"]) is not str
            or not args["restore_name"].startswith("COREX restore ")
            or len(args["restore_name"]) > 80
        ):
            raise ValueError("Mechanical image restore name is invalid")
        paths = [Path(str(value)) for value in args["output_paths"]]
        view_export = Path(str(args["view_export_path"]))
        if (
            len(paths) != len(objects) * len(views)
            or len(paths) > 256
            or len({path.name for path in paths}) != len(paths)
            or any(
                path.parent.resolve() != self.work_root
                or not path.name.startswith("viewport-")
                or path.suffix.casefold() != ".png"
                or path.exists()
                for path in paths
            )
            or view_export.parent.resolve() != self.work_root
            or not view_export.name.startswith("image-views-")
            or view_export.suffix.casefold() != ".xml"
            or view_export.exists()
        ):
            raise ValueError("Mechanical image temporary paths are not run-owned")
        try:
            body = IMAGE_PREFLIGHT_SCRIPT_BODY if args["preflight_only"] else IMAGE_SCRIPT_BODY
            raw = (
                self.app.execute_script(_data_script(args, body))
                if self.app is not None
                else self.mechanical.run_python_script(_data_script(args, body))
            )
            payload = json.loads(raw) if type(raw) is str else None
            records = payload.get("images") if isinstance(payload, dict) else None
            if type(records) is not list or len(records) != len(paths):
                raise RuntimeError("Mechanical image capture returned an invalid receipt")
            if args["preflight_only"]:
                expected = {
                    "object_index", "object_name", "object_path", "object_id",
                    "view_ordinal", "view_name", "view_kind", "view_index",
                }
                if any(not isinstance(record, dict) or set(record) != expected for record in records):
                    raise RuntimeError("Mechanical image preflight returned invalid selectors")
                if set(payload) != {"images"}:
                    raise RuntimeError("Mechanical image preflight returned an invalid receipt")
                return {"status": "validated", "image_preflight": {"images": records}}
            warnings = payload.get("warnings") if isinstance(payload, dict) else None
            if (
                set(payload) != {"images", "warnings"}
                or type(warnings) is not list
                or len(warnings) > 256
                or any(type(value) is not str or not value or len(value) > 2048 for value in warnings)
            ):
                raise RuntimeError("Mechanical image capture diagnostics are invalid")
            result = []
            for index, (record, expected) in enumerate(zip(records, paths, strict=True)):
                if not isinstance(record, dict) or record.get("output_path") != str(expected):
                    raise RuntimeError("Mechanical image capture path receipt is invalid")
                stat = expected.lstat()
                if expected.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 0x400):
                    raise RuntimeError("Mechanical image capture produced an unsafe file")
                data = expected.read_bytes()
                image = ImageValue.from_png(data)
                result.append(
                    {
                        **{key: value for key, value in record.items() if key != "output_path"},
                        "relative_name": expected.name,
                        "byte_length": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "width": image.width,
                        "height": image.height,
                    }
                )
            return {
                "status": "captured",
                "image_export": {"images": result},
                "warnings": warnings,
            }
        except Exception as exc:
            if "mechanical.restore_failed:" in str(exc):
                try:
                    self.close()
                except Exception as close_exc:
                    raise RuntimeError(f"{exc}; native session retirement failed: {close_exc}") from exc
            for path in paths:
                path.unlink(missing_ok=True)
            raise
        finally:
            view_export.unlink(missing_ok=True)

    def camera_views(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {"include", "identity", "export_path", "restore_name"}
        if set(args) != required or (self.app is None and self.mechanical is None):
            raise ValueError("Mechanical camera arguments or session state are invalid")
        if self.work_root is None:
            raise ValueError("Mechanical camera working root is unavailable")
        output = Path(str(args["export_path"]))
        if (
            output.parent.resolve() != self.work_root
            or not output.name.startswith("camera-views-")
            or output.suffix.casefold() != ".xml"
            or output.exists()
        ):
            raise ValueError("Mechanical camera export path is not run-owned")
        if args["include"] not in {"saved_and_current", "saved", "current"}:
            raise ValueError("Mechanical camera Include is invalid")
        restore_name = args["restore_name"]
        if (
            type(restore_name) is not str
            or not restore_name.startswith("COREX restore ")
            or len(restore_name) > 80
        ):
            raise ValueError("Mechanical camera restore name is invalid")
        try:
            raw = (
                self.app.execute_script(_data_script(args, CAMERA_SCRIPT_BODY))
                if self.app is not None
                else self.mechanical.run_python_script(
                    _data_script(args, CAMERA_SCRIPT_BODY)
                )
            )
            payload = json.loads(raw) if type(raw) is str else None
            return {
                "status": "extracted",
                "camera_views": build_camera_views(
                    payload, identity=dict(args["identity"])
                ),
            }
        except Exception as exc:
            if "mechanical.restore_failed:" in str(exc):
                try:
                    self.close()
                except Exception as close_exc:
                    raise RuntimeError(
                        f"{exc}; native session retirement failed: {close_exc}"
                    ) from exc
            raise
        finally:
            output.unlink(missing_ok=True)

    def definition_tables(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "sources", "family", "table", "table_selector", "component", "units",
            "native_output_path",
        }
        if set(args) not in (required, required | {"sets"}) or (
            self.app is None and self.mechanical is None
        ):
            raise ValueError("Mechanical definition-table arguments or session state are invalid")
        if self.work_root is None:
            raise ValueError("Mechanical definition-table working root is unavailable")
        output = Path(str(args["native_output_path"]))
        if (
            output.parent.resolve() != self.work_root
            or not output.name.startswith("native-definitions-")
            or output.suffix != ".json"
            or output.exists()
        ):
            raise ValueError("Mechanical definition-table output path is not run-owned")
        script = _data_script(args, DEFINITION_SCRIPT_BODY)
        try:
            raw_receipt = (
                self.app.execute_script(script)
                if self.app is not None
                else self.mechanical.run_python_script(script)
            )
            payload = _read_native_json_file(
                output,
                raw_receipt,
                max_bytes=DEFINITION_ENCODED_MAX_BYTES,
                label="Mechanical definition extraction",
            )
            warnings = payload.pop("warnings", [])
            if (
                type(warnings) is not list
                or len(warnings) > 100
                or any(type(item) is not str or not item or len(item) > 2048 for item in warnings)
            ):
                raise RuntimeError("Mechanical table diagnostics are invalid")
            return {
                "status": "extracted",
                "definition_tables": build_definition_tables(payload),
                "warnings": warnings,
            }
        except Exception as exc:
            if "mechanical.restore_failed:" in str(exc):
                try:
                    self.close()
                except Exception as close_exc:
                    raise RuntimeError(f"{exc}; native session retirement failed: {close_exc}") from exc
            raise
        finally:
            output.unlink(missing_ok=True)

    def search(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "filter", "query", "match", "case_sensitive", "include_hidden_properties",
            "invert", "identity", "typed_selector",
        }
        if set(args) != required or self.tree is None or self.model is None:
            raise ValueError("Mechanical search arguments or session state are invalid")
        tree = (
            _RemoteTree(
                self.mechanical,
                self.work_root,
                include_hidden_properties=bool(args["include_hidden_properties"]),
            )
            if isinstance(self.tree, _RemoteTree)
            else self.tree
        )
        return {
            "status": "searched",
            "search": search_tree(
                tree=tree,
                model=self.model,
                data_model=self.data_model,
                identity=dict(args["identity"]),
                filter_code=str(args["filter"]),
                query=str(args["query"]),
                match_mode=str(args["match"]),
                case_sensitive=bool(args["case_sensitive"]),
                include_hidden_properties=bool(args["include_hidden_properties"]),
                invert=bool(args["invert"]),
                typed_selector=args["typed_selector"],
            ),
        }

    def open(self, args: Mapping[str, Any]) -> dict[str, Any]:
        required = {"source_path", "work_path", "mode", "release_code", "system", "catalogue_identity", "view_export_path", "timeout_sec"}
        if set(args) != required:
            raise ValueError("Mechanical open arguments are invalid")
        source = Path(str(args["source_path"])).resolve(strict=True)
        work = Path(str(args["work_path"])).resolve()
        if work.exists():
            raise ValueError("Mechanical working destination already exists")
        self.work_root = work.parent.resolve(strict=True)
        self.source_path = source
        self.work_path = work
        self.release_code = int(args["release_code"])
        suffix = source.suffix.casefold()
        if suffix in {".wbpj", ".wbpz"}:
            systems, tree, graphics, selected = self._open_workbench(
                source, work, int(args["release_code"]), str(args["mode"]), str(args["system"]), float(args["timeout_sec"])
            )
        elif suffix in {".mechdb", ".mechdat", ".mechpz"}:
            systems, tree, graphics, selected = self._open_standalone(
                source, work, int(args["release_code"]), str(args["mode"])
            )
        else:
            raise ValueError("Unsupported Mechanical source extension")
        self.systems = systems
        self.graphics = graphics
        identity = dict(args["catalogue_identity"])
        identity["system_key"] = selected
        identity["view_export_path"] = str(args["view_export_path"])
        if suffix in {".wbpj", ".wbpz"} and not selected:
            rows = collect_catalogue_rows(
                tree=None, graphics=None, identity=identity, systems=systems,
                status="system_required", message="Select a Mechanical Model/system before opening.",
            )
            self.close()
            return {"status": "system_required", "rows": rows, "systems": systems}
        return {
            "status": "opened",
            "rows": collect_catalogue_rows(
                tree=tree, graphics=graphics, identity=identity, systems=systems,
                model=self.model, data_model=self.data_model,
            ),
            "systems": systems,
            "system_key": selected,
        }

    def _open_standalone(self, source: Path, work: Path, release: int, mode: str):
        if mode == "interactive":
            from ansys.mechanical.core import launch_mechanical
            self.mechanical = launch_mechanical(version=release, batch=False, cleanup_on_exit=True)
            if release > 261:
                capability = json.loads(
                    self.mechanical.run_python_script(
                        "import json\np=DataModel.Project\n"
                        "json.dumps(bool(Tree is not None and Graphics is not None and "
                        "all(callable(getattr(p,n,None)) for n in ('Open','SaveAs','Unarchive'))))"
                    )
                )
                if capability is not True:
                    raise RuntimeError(
                        "mechanical.capability_unproved: later interactive standalone release lacks Project/Tree/Graphics operations"
                    )
            self.mechanical.run_python_script(_data_script(
                {"source": str(source), "work": str(work), "archive": source.suffix.casefold() == ".mechpz"},
                "p=_corex_data\nDataModel.Project.Unarchive(p['source'],p['work'],False) if p['archive'] else (DataModel.Project.Open(p['source']),DataModel.Project.SaveAs(p['work'],False))\nstr(True)",
            ))
            self.tree = _RemoteTree(self.mechanical, self.work_root)
            self.model = _RemoteModel(self.mechanical)
            return [], self.tree, _RemoteGraphics(self.mechanical), "standalone"
        from ansys.mechanical.core import App, global_variables
        self.app = App(version=release)
        values = global_variables(self.app)
        if release > 261:
            project = values.get("DataModel").Project if values.get("DataModel") is not None else None
            if (
                project is None
                or not callable(getattr(self.app, "open", None))
                or not callable(getattr(self.app, "save_as", None))
                or not callable(getattr(project, "Unarchive", None))
                or values.get("Tree") is None
                or values.get("Graphics") is None
            ):
                raise RuntimeError(
                    "mechanical.capability_unproved: later embedded standalone release lacks App Open/SaveAs, Project.Unarchive, Tree, or Graphics"
                )
        if source.suffix.casefold() == ".mechpz":
            values["DataModel"].Project.Unarchive(str(source), str(work), False)
        else:
            self.app.open(str(source))
            self.app.save_as(str(work), overwrite=False)
        self.tree, self.model, self.data_model = values["Tree"], values["Model"], values["DataModel"]
        return [], self.tree, values["Graphics"], "standalone"

    def _open_workbench(self, source: Path, work: Path, release: int, mode: str, requested: str, timeout_sec: float):
        self.workbench = self._launch_workbench(
            release=release,
            mode="background",
            workdir=work.parent,
            timeout_sec=timeout_sec,
        )
        if release > 261:
            capability = self.workbench.run_script_string(
                "import json\nwb_script_result=json.dumps(all(name in globals() and callable(globals()[name]) for name in ('Open','Save','Archive','Unarchive','GetAllSystems','GetSystem')))"
            )
            if capability is not True or not all(
                callable(getattr(self.workbench, name, None))
                for name in ("start_mechanical_server", "stop_mechanical_server")
            ):
                raise RuntimeError(
                    "mechanical.capability_unproved: later Workbench release lacks required project/server operations"
                )
        source_choices = None
        if source.suffix.casefold() == ".wbpz":
            body = "Unarchive(ArchivePath=_corex_data['source'],ProjectPath=_corex_data['work'],Overwrite=False)\nSave()\n"
        else:
            archive = work.with_suffix(".wbpz")
            self._require_receipt(self.workbench.run_script_string(_data_script(
                {"source": str(source)},
                "Open(FilePath=_corex_data['source'])\nwb_script_result=json.dumps(True)",
            )), "Open")
            staged = work.with_name(work.stem + "-staged.wbpj")
            self._require_receipt(self.workbench.run_script_string(_data_script(
                {"staged": str(staged)},
                "Save(FilePath=_corex_data['staged'],Overwrite=False)\nwb_script_result=json.dumps(True)",
            )), "working-copy Save")
            self._require_receipt(self.workbench.run_script_string(_data_script(
                {"archive": str(archive)},
                "Archive(FilePath=_corex_data['archive'],IncludeSkippedFiles=True,IncludeUserFiles=True,IncludeExternalImportedFiles=True,FailIfMissingFiles=True)\nwb_script_result=json.dumps(True)",
            )), "Archive")
            source_choices = self._workbench_systems()
            self.workbench.exit()
            self.workbench = None
            if not archive.is_file():
                raise RuntimeError("Workbench did not publish the native working archive")
            self.workbench = self._launch_workbench(
                release=release, mode="background", workdir=work.parent, timeout_sec=timeout_sec
            )
            body = "Unarchive(ArchivePath=_corex_data['archive'],ProjectPath=_corex_data['work'],Overwrite=False)\nSave()\n"
        self._require_receipt(self.workbench.run_script_string(_data_script(
            {"source": str(source), "work": str(work), "archive": str(work.with_suffix('.wbpz')), "archive_name": "corex_working.wbpz"},
            body + "wb_script_result=json.dumps(True)",
        )), "Unarchive")
        target_choices = self._workbench_systems()
        public_choices = source_choices or target_choices
        selected = requested.strip()
        public_match = select_model_system(public_choices, selected)
        if public_match is None:
            return public_choices, None, None, ""
        target_match = select_model_system(target_choices, public_match["key"])
        if target_match is None:
            raise RuntimeError("Unarchived Workbench Model identity does not match its source")
        self.system_name = target_match["system_keys"][0]
        if mode == "interactive":
            self._edit_workbench_model()
        self._connect_workbench_model()
        return public_choices, self.tree, _RemoteGraphics(self.mechanical), public_match["key"]

    def _edit_workbench_model(self) -> None:
        capability = self.workbench.run_script_string(
            _data_script(
                {"system": self.system_name},
                "c=GetSystem(Name=_corex_data['system']).GetContainer(ComponentName='Model')\n"
                "wb_script_result=json.dumps(bool(callable(getattr(c,'Edit',None)) and callable(getattr(c,'Exit',None))))",
            )
        )
        if capability is not True:
            raise RuntimeError(
                "mechanical.capability_unproved: selected Workbench Model lacks Edit/Exit"
            )
        self._require_receipt(
            self.workbench.run_script_string(
                _data_script(
                    {"system": self.system_name},
                    "c=GetSystem(Name=_corex_data['system']).GetContainer(ComponentName='Model')\n"
                    "c.Edit(Hidden=False,Interactive=True)\n"
                    "wb_script_result=json.dumps(True)",
                )
            ),
            "Model.Edit",
        )
        self.interactive_model = True

    def _connect_workbench_model(self) -> None:
        from ansys.mechanical.core import connect_to_mechanical

        port = self.workbench.start_mechanical_server(system_name=self.system_name)
        self.mechanical_server_started = True
        self.mechanical = connect_to_mechanical(ip="127.0.0.1", port=port)
        assert self.work_root is not None
        self.tree = _RemoteTree(self.mechanical, self.work_root)
        self.model = _RemoteModel(self.mechanical)
        self.graphics = _RemoteGraphics(self.mechanical)

    def _workbench_systems(self) -> list[dict[str, Any]]:
        if self.work_root is None:
            raise RuntimeError("Workbench system inventory working root is unavailable")
        output = self.work_root / f"workbench-systems-{uuid4().hex}.json"
        try:
            raw = self.workbench.run_script_string(_data_script(
                {"native_output_path": str(output)},
                WORKBENCH_SYSTEMS_BODY,
            ))
            systems = _read_native_json_file(
                output,
                raw,
                max_bytes=1024 * 1024,
                label="Workbench system inventory",
                expected={"marker": "corex-workbench-systems-v1"},
            )
        finally:
            output.unlink(missing_ok=True)
        if (
            type(systems) is not list
            or not systems
            or len(systems) > 256
            or any(
                not isinstance(item, dict)
                or set(item) != {"key", "label", "model_key"}
                or any(type(item[key]) is not str or not item[key] or len(item[key]) > 512 for key in item)
                for item in systems
            )
        ):
            raise RuntimeError("Workbench system inventory returned an invalid bounded receipt")
        return deduplicate_model_systems(systems)

    def close(self) -> None:
        errors: list[Exception] = []
        if self.app is not None:
            try:
                self.app.close()
                self.app = None
            except Exception as exc:
                errors.append(exc)
        if self.workbench is not None:
            if self.system_name and self.mechanical_server_started:
                try:
                    self.workbench.stop_mechanical_server(system_name=self.system_name)
                    self.mechanical_server_started = False
                except Exception as exc:
                    errors.append(exc)
            if self.interactive_model:
                try:
                    self._require_receipt(
                        self.workbench.run_script_string(
                            _data_script(
                                {"system": self.system_name},
                                "s=GetSystem(Name=_corex_data['system'])\n"
                                "s.GetContainer(ComponentName='Model').Exit(SaveDatabase=False)\n"
                                "wb_script_result=json.dumps(True)",
                            )
                        ),
                        "Model.Exit",
                    )
                    self.interactive_model = False
                except Exception as exc:
                    errors.append(exc)
            try:
                self.workbench.exit()
                self.workbench = self.mechanical = None
            except Exception as exc:
                errors.append(exc)
        if errors:
            # Failed clients remain referenced so the child's final cleanup retries once.
            raise RuntimeError("Mechanical native cleanup failed: " + "; ".join(str(exc) for exc in errors))
        self.work_root = None
        self.source_path = None
        self.work_path = None
        self.release_code = 0


def deduplicate_model_systems(systems: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in systems:
        model_key = str(item["model_key"])
        record = unique.setdefault(
            model_key,
            {"key": str(item["key"]), "label": str(item["label"]), "model_key": model_key, "system_keys": []},
        )
        record["system_keys"].append(str(item["key"]))
    return list(unique.values())


def select_model_system(choices: list[dict[str, Any]], selected: str) -> dict[str, Any] | None:
    if not selected and len(choices) == 1:
        return choices[0]
    if not selected:
        return None
    matches = [item for item in choices if selected in {item["key"], item["model_key"], *item["system_keys"]}]
    if len(matches) != 1:
        raise ValueError(f"Mechanical system selection {selected!r} is unavailable or ambiguous")
    return matches[0]


class _Proxy:
    def __init__(self, **values: Any) -> None:
        self._errors = dict(values.pop("_errors", {}))
        self.__dict__.update(values)
    def __getattr__(self, name: str):
        if name in self._errors:
            raise RuntimeError(self._errors[name])
        raise AttributeError(name)
    def GetType(self):
        if "GetType" in self._errors:
            raise RuntimeError(self._errors["GetType"])
        return _Proxy(FullName=self.api_type)


class _RemoteTree:
    def __init__(
        self,
        client: Any,
        transport_root: Path,
        *,
        include_hidden_properties: bool = False,
    ) -> None:
        self.client = client
        self.transport_root = transport_root.resolve(strict=True)
        self.include_hidden_properties = include_hidden_properties
        self.metadata_errors: list[str] = []
    @property
    def AllObjects(self):
        output = self.transport_root / f"remote-tree-{uuid4().hex}.json"
        script = _data_script({"include_hidden": self.include_hidden_properties, "output_path": str(output)}, """import hashlib,json,os
try:unicode
except NameError:unicode=str
def _corex_text(v):
 return v if isinstance(v,unicode) else unicode(v)
def field(o,n,text=False):
 try:v=getattr(o,n)
 except AttributeError:return {'present':False,'error':'','value':None}
 except Exception as x:return {'present':True,'error':type(x).__name__,'value':None}
 try:return {'present':True,'error':'','value':_corex_text(v) if text else v}
 except Exception as x:return {'present':True,'error':type(x).__name__,'value':None}
rows=[]
tags={};tags_available=True
try:
  for t in list(DataModel.ObjectTags):
   for tagged in list(t.Objects):tags.setdefault(int(tagged.ObjectId),[]).append(_corex_text(t.Name))
except:tags_available=False
for o in list(Tree.AllObjects):
 oid=int(o.ObjectId);name=field(o,'Name',True);category=field(o,'DataModelObjectCategory',True)
 try:api_type={'present':True,'error':'','value':_corex_text(o.GetType().FullName)}
 except Exception as x:api_type={'present':True,'error':type(x).__name__,'value':None}
 parent=field(o,'Parent');parent_value=parent['value']
 try:parent_id=int(parent_value.ObjectId) if parent_value is not None else None
 except:parent_id=None
 props=[];props_error=''
 try:
   for q in list(o.Properties if _corex_data['include_hidden'] else o.VisibleProperties):
    api_name=field(q,'APIName',True);prop_name=field(q,'Name',True);caption=field(q,'Caption',True);string_value=field(q,'StringValue',True)
    key=api_name['value'] if api_name['present'] and not api_name['error'] and api_name['value'] not in ('','None') else prop_name['value'] if prop_name['present'] and not prop_name['error'] and prop_name['value'] not in ('','None') else 'property:'+str(len(props))
    object_field=field(o,key);object_is_field=False
    if object_field['present'] and not object_field['error'] and object_field['value'] is not None:
     object_inputs=field(object_field['value'],'Inputs');object_output=field(object_field['value'],'Output')
     object_is_field=object_inputs['present'] or object_output['present']
    internal=field(q,'InternalValue');internal_error=internal['error'];iv=internal['value'];field_inputs=None;internal_fields=None;is_field=False;output_error=''
    output=None
    if iv is not None:
     inputs_record=field(iv,'Inputs');output_record=field(iv,'Output')
     if inputs_record['present'] or output_record['present']:
      is_field=True;output_error=output_record['error']
      if inputs_record['present'] and not inputs_record['error']:
       try:field_inputs=len(list(inputs_record['value']))
       except:field_inputs=None
      if output_record['present'] and not output_record['error']:
       out=output_record['value'];output={n:field(out,n,n!='DiscreteValueCount') for n in ('DefinitionType','DiscreteValueCount','Formula','Unit','QuantityName')}
     else:
      internal_fields={n:field(iv,n,n in ('Unit','QuantityName')) for n in ('Value','Unit','QuantityName')}
      scalar=internal_fields['Value']
      if scalar['present'] and not scalar['error'] and type(scalar['value']) not in (int,float):scalar['present']=False;scalar['value']=None
    props.append({'APIName':api_name,'Name':prop_name,'Caption':caption,'StringValue':string_value,'object_field_key':key if object_is_field else '','internal_error':internal_error,'is_field':is_field,'output_error':output_error,'field_inputs':field_inputs,'output':output,'internal':internal_fields})
 except Exception as x:props_error=type(x).__name__
 table_field=field(o,'TabularData');table=table_field['value'];table_keys=None
 if table_field['present'] and not table_field['error'] and table is not None:
  try:table_keys=[_corex_text(k) for k in table.Keys]
  except:table_keys=[]
 bindings={}
 for attr in ('CoordinateSystem','Orientation'):
   binding=field(o,attr)
   if binding['present']:
    if binding['error']:bindings[attr]={'error':binding['error']}
    else:
     cs=binding['value'];bindings[attr]=None if cs is None else {'ObjectId':field(cs,'ObjectId')['value'],'Name':field(cs,'Name',True)['value']}
 scopes={}
 for attr in ('Location','SourceLocation','TargetLocation'):
   scope=field(o,attr)
   if scope['present']:
    if scope['error']:scopes[attr]={'error':scope['error']}
    elif scope['value'] is None:scopes[attr]=None
    else:
     s=scope['value'];scopes[attr]={n:field(s,n,n in ('Name','SelectionType','DataModelObjectCategory')) for n in ('ObjectId','Name','SelectionType','DataModelObjectCategory','TotalSelection')}
     ids=field(s,'Ids')
     if ids['present'] and not ids['error']:
      try:ids['value']=list(ids['value'] or ())
      except Exception as x:ids={'present':True,'error':type(x).__name__,'value':None}
     scopes[attr]['Ids']=ids
 rows.append({'ObjectId':oid,'Name':name,'api_type':api_type,'category':category,'parent_id':parent_id,'props':props,'props_error':props_error,'table_keys':table_keys,'hidden':field(o,'Hidden'),'source':field(o,'ImportableObjectSourceId',True),'state':field(o,'ObjectState',True),'suppressed':field(o,'Suppressed'),'working_dir':field(o,'WorkingDir',True),'bindings':bindings,'scopes':scopes,'direct_tags':tags.get(oid,[]),'tags_available':tags_available})
encoded=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf-8')
stream=open(_corex_data['output_path'],'wb')
try:stream.write(encoded)
finally:stream.close()
json.dumps({'marker':'corex-remote-tree-v1','byte_length':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()},separators=(',',':'))""")
        try:
            raw = self.client.run_python_script(script)
            rows = _read_native_json_file(
                output,
                raw,
                max_bytes=CATALOGUE_MAX_ENCODED_BYTES,
                label="Mechanical remote tree",
                expected={"marker": "corex-remote-tree-v1"},
            )
        finally:
            output.unlink(missing_ok=True)
        objects = {}
        for r in rows:
            properties = [_RemoteProperty(**p) for p in r["props"]]
            values = dict(ObjectId=r["ObjectId"], Parent=None, _corex_direct_tags=r["direct_tags"], _corex_tags_available=r["tags_available"])
            values.update({
                prop._object_field_key: _Proxy(Inputs=(), Output=_Proxy())
                for prop in properties
                if prop._object_field_key
            })
            errors = {}
            for key, field_name in (("Name", "Name"), ("api_type", "GetType"), ("category", "DataModelObjectCategory")):
                item = r[key]
                if item["error"]: errors[field_name] = item["error"]
                elif item["present"]: values[field_name if field_name != "GetType" else "api_type"] = item["value"]
            property_field = "Properties" if self.include_hidden_properties else "VisibleProperties"
            if r["props_error"]: errors[property_field] = r["props_error"]
            else: values[property_field] = properties
            if not self.include_hidden_properties and not r["props_error"]: values["VisibleProperties"] = properties
            if r["table_keys"] is not None: values["TabularData"] = _Proxy(Keys=r["table_keys"])
            for key, field_name in (("hidden", "Hidden"), ("source", "ImportableObjectSourceId"), ("state", "ObjectState"), ("suppressed", "Suppressed"), ("working_dir", "WorkingDir")):
                item = r[key]
                if item["error"]: errors[field_name] = item["error"]
                elif item["present"]: values[field_name] = item["value"]
            for name, binding in r["bindings"].items():
                if isinstance(binding, dict) and "error" in binding:
                    errors[name] = binding["error"]
                    self.metadata_errors.append(f"{r['Name']}: {name}: {binding['error']}")
                else: values[name] = None if binding is None else _Proxy(**binding)
            for name, scope in r["scopes"].items():
                if scope is None:
                    values[name] = None
                elif "error" in scope:
                    errors[name] = scope["error"]
                    self.metadata_errors.append(f"{r['Name']}: {name}: {scope['error']}")
                else:
                    scope_values, scope_errors = {}, {}
                    for field_name, item in scope.items():
                        if item["error"]: scope_errors[field_name] = item["error"]
                        elif item["present"]: scope_values[field_name] = item["value"]
                    if "Ids" in scope_values: scope_values["Ids"] = list(scope_values["Ids"] or ())
                    values[name] = _Proxy(_errors=scope_errors, **scope_values)
            objects[r["ObjectId"]] = _Proxy(_errors=errors, **values)
        for row in rows:
            if row["parent_id"] in objects: objects[row["ObjectId"]].Parent = objects[row["parent_id"]]
        return list(objects.values())


class _RemoteProperty(_Proxy):
    def __init__(self, **values: Any) -> None:
        self._object_field_key = values.pop("object_field_key", "")
        internal_error = values.pop("internal_error", "")
        is_field = values.pop("is_field", False)
        output_error = values.pop("output_error", "")
        field_inputs = values.pop("field_inputs", None)
        output_fields = values.pop("output", None)
        internal_fields = values.pop("internal", None)
        property_values, property_errors = {}, {}
        for name, item in values.items():
            if item["error"]: property_errors[name] = item["error"]
            elif item["present"]: property_values[name] = item["value"]
        if internal_error:
            property_errors["InternalValue"] = internal_error
        elif is_field:
            internal_errors = {}
            internal_values = {}
            if field_inputs is None:
                internal_errors["Inputs"] = "unavailable"
            else:
                internal_values["Inputs"] = [None] * field_inputs
            if output_error:
                internal_errors["Output"] = output_error
            else:
                output_values, output_errors = {}, {}
                for name, item in (output_fields or {}).items():
                    if item["error"]: output_errors[name] = item["error"]
                    elif item["present"]: output_values[name] = item["value"]
                internal_values["Output"] = _Proxy(
                    _errors=output_errors, **output_values
                )
            property_values["InternalValue"] = _Proxy(
                _errors=internal_errors, **internal_values
            )
        elif field_inputs is None:
            if internal_fields is None:
                property_values["InternalValue"] = None
            else:
                internal_values, internal_errors = {}, {}
                for name, item in internal_fields.items():
                    if item["error"]: internal_errors[name] = item["error"]
                    elif item["present"]: internal_values[name] = item["value"]
                property_values["InternalValue"] = _Proxy(
                    _errors=internal_errors, **internal_values
                )
        super().__init__(_errors=property_errors, **property_values)


class _RemoteModel:
    def __init__(self, client: Any) -> None:
        self.client = client
    def GetActivationStatusForAnalysis(self, object_id: int, analysis_id: int):
        return self.client.run_python_script(_data_script(
            {"object_id": object_id, "analysis_id": analysis_id},
            "str(Model.GetActivationStatusForAnalysis(_corex_data['object_id'],_corex_data['analysis_id']))",
        ))


class _RemoteViewManager:
    def __init__(self, client: Any) -> None: self.client = client
    @property
    def NumberOfViews(self): return int(self.client.run_python_script("str(Graphics.ModelViewManager.NumberOfViews)"))
    def ExportModelViews(self, path: str) -> None:
        self.client.run_python_script(_data_script({"path": path}, "Graphics.ModelViewManager.ExportModelViews(_corex_data['path'])\nstr(True)"))


class _RemoteGraphics:
    def __init__(self, client: Any) -> None: self.ModelViewManager = _RemoteViewManager(client)


__all__ = ["LIFECYCLE_OPERATIONS", "MechanicalOwnerBackend"]
