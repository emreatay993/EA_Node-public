# Purpose: Verify owned Mechanical APDL snippet placement, rollback, and runtime outputs.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.commands import (
    SNIPPET_EXECUTION_BODY,
    SNIPPET_PREFLIGHT_BODY,
)
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.contracts import catalogue_table, model_handle
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.owner_process import OwnerProtocolError
from ea_node_editor.addons.mechanical.owner_process import _prepare_snippet_response
from ea_node_editor.addons.mechanical.runtime import execute_apdl_snippet
from ea_node_editor.addons.mechanical.session import StaleMechanicalModelError
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import TableValue, TypedInlineValue
from tests.mechanical_catalogue.test_contracts import _model_metadata, _row


class _EnumValue(str):
    def GetType(self):
        return _EnumType


class _EnumType:
    names = ("First", "Last", "All", "ByNumber")


class _Enum:
    @staticmethod
    def GetNames(enum_type):
        return enum_type.names

    @staticmethod
    def Parse(enum_type, name):
        if name not in enum_type.names:
            raise ValueError(name)
        return _EnumValue(name)


class _PropertyInfo:
    CanWrite = True
    PropertyType = _EnumType


class _CommandType:
    @staticmethod
    def GetProperty(_name):
        return _PropertyInfo()

    @staticmethod
    def GetMethod(name):
        return object() if name == "Delete" else None


class _Method:
    ReturnType = _CommandType()


class _NativeType:
    def __init__(self, full_name: str, *, command_factory=False):
        self.FullName = full_name
        self.command_factory = command_factory

    def GetMethod(self, name):
        return _Method() if self.command_factory and name == "AddCommandSnippet" else None


class _Tree:
    def __init__(self):
        self.objects = []
        self.metadata_errors = []
        self.next_id = 100

    @property
    def AllObjects(self):
        return list(self.objects)


class _Native:
    def __init__(self, object_id: int, name: str, parent=None, *, api_type=""):
        self.ObjectId = object_id
        self.Name = name
        self.Parent = parent
        self.VisibleProperties = []
        self.DataModelObjectCategory = "CommandSnippet" if api_type.endswith("CommandSnippet") else ""
        self._type = _NativeType(api_type or "Ansys.ACT.Automation.Mechanical.Model")

    def GetType(self):
        return self._type


class _Snippet(_Native):
    def __init__(self, object_id: int, parent, tree: _Tree):
        super().__init__(
            object_id,
            "Command Snippet",
            parent,
            api_type="Ansys.ACT.Automation.Mechanical.CommandSnippet",
        )
        self._tree = tree
        self._input = ""
        self.StepSelectionMode = _EnumValue("All")
        self.StepNumber = 1
        self.IssueSolveCommand = False
        self.fail_input_once = False
        self.fail_delete = False

    @property
    def Input(self):
        return self._input

    @Input.setter
    def Input(self, value):
        if self.fail_input_once:
            self.fail_input_once = False
            raise RuntimeError("injected input failure")
        self._input = value

    def Delete(self):
        if self.fail_delete:
            raise RuntimeError("injected delete failure")
        self._tree.objects.remove(self)


class _Analysis(_Native):
    def __init__(self, object_id: int, name: str, parent, tree: _Tree, *, physics="Mechanical", analysis_type="Static"):
        super().__init__(object_id, name, parent, api_type="Ansys.ACT.Automation.Mechanical.Analysis")
        self._type = _NativeType(self._type.FullName, command_factory=True)
        self._tree = tree
        self.PhysicsType = _EnumValue(physics)
        self.AnalysisType = _EnumValue(analysis_type)
        self.AnalysisSettings = SimpleNamespace(NumberOfSteps=3)
        self.fail_next_input = False
        self.fail_next_delete = False

    def AddCommandSnippet(self):
        snippet = _Snippet(self._tree.next_id, self, self._tree)
        self._tree.next_id += 1
        snippet.fail_input_once = self.fail_next_input
        snippet.fail_delete = self.fail_next_delete
        self.fail_next_input = False
        self.fail_next_delete = False
        self._tree.objects.append(snippet)
        return snippet


class _Views:
    NumberOfViews = 0

    @staticmethod
    def ExportModelViews(path):
        Path(path).write_text("<ModelViewsManager />", encoding="utf-8")


class _App:
    def __init__(self, namespace):
        self.namespace = namespace

    def execute_script(self, script):
        exec(compile(script, "<mechanical-snippet-test>", "exec"), self.namespace)
        return self.namespace["_corex_receipt"]


def _backend(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(sys.modules, "System", SimpleNamespace(Enum=_Enum))
    tree = _Tree()
    root = _Native(1, "Model")
    first = _Analysis(10, "Static A", root, tree)
    thermal = _Analysis(20, "Thermal", root, tree, physics="Thermal")
    second = _Analysis(30, "Static B", root, tree)
    modal = _Analysis(40, "Modal", root, tree, analysis_type="Modal")
    tree.objects.extend([root, first, thermal, second, modal])
    model = SimpleNamespace(Analyses=[first, thermal, second, modal])
    data_model = SimpleNamespace(ObjectTags=[])
    backend = MechanicalOwnerBackend()
    backend.app = _App({"Tree": tree, "Model": model, "DataModel": data_model})
    backend.tree = tree
    backend.model = model
    backend.data_model = data_model
    backend.graphics = SimpleNamespace(ModelViewManager=_Views())
    backend.systems = []
    backend.work_root = tmp_path.resolve()
    return backend, tree, first, thermal, second, modal


def _identity():
    return {
        "schema_version": 1,
        "model_revision": 3,
        "producer_iteration": 4,
        "catalogue_id": str(uuid4()),
        "producer_node_id": "snippet-1",
        "producer_port": "report",
        "producer_path": "[3,1]",
        "run_id": "run-1",
        "session_id": "session-1",
        "document_id": "document-1",
        "source_key": "source-1",
        "system_key": "system-1",
    }


def _preflight(backend, *, environments=(), name="COREX commands", steps="all", selected_steps=()):
    return backend.snippet_preflight(
        {
            "environments": list(environments),
            "name": name,
            "steps": steps,
            "selected_steps": list(selected_steps),
            "owner_node_token": "c25pcHBldC0x",
        }
    )["snippet_preflight"]


def _mutation_args(backend, plan, *, commands="/prep7\n  ! exact  \n", issue_solve=False):
    first = plan["targets"][0]["entries"]
    steps = "all" if first[0]["step"] is None else "selected"
    selected = [] if steps == "all" else [row["step"] for row in first]
    return {
        "plan": plan,
        "owner_node_token": "c25pcHBldC0x",
        "name": "COREX commands",
        "steps": steps,
        "selected_steps": selected,
        "commands": commands,
        "issue_solve_command": issue_solve,
        "catalogue_identity": _identity(),
        "view_export_path": str(backend.work_root / f"snippet-views-{uuid4().hex}.xml"),
        "rollback_path": str(backend.work_root / f"snippet-rollback-{uuid4().hex}.json"),
    }


def _run(backend, plan, *, commands="/prep7\n  ! exact  \n", issue_solve=False):
    result = backend.run_snippet(
        _mutation_args(backend, plan, commands=commands, issue_solve=issue_solve)
    )
    if result["status"] == "executed":
        backend.commit_snippet_transaction()
    return result


def test_unicode_snippet_receipt_and_rollback_file_round_trip(
    tmp_path: Path, monkeypatch
) -> None:
    backend, _tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    first.Name = "Static ³ ° Ω 漢字 \\ path"
    name = "COREX ³ °"
    plan = _preflight(backend, environments=[{"kind": "text", "text": first.Name}], name=name)
    create_args = _mutation_args(backend, plan, commands="/prep7\n! 漢字 \\ original")
    create_args["name"] = name
    created = backend.run_snippet(create_args)
    backend.commit_snippet_transaction()
    assert created["snippet"]["receipts"][0]["analysis_name"] == first.Name
    snippet = next(item for item in backend.tree.AllObjects if isinstance(item, _Snippet))
    original = snippet.Input
    update = _preflight(backend, environments=[{"kind": "text", "text": first.Name}], name=name)
    update_args = _mutation_args(backend, update, commands="/prep7\n! 22 °C · changed")
    update_args["name"] = name
    changed = backend.run_snippet(update_args)
    assert changed["status"] == "executed"
    rollback = backend._snippet_rollback_path
    assert rollback is not None
    payload = json.loads(rollback.read_bytes().decode("utf-8"))
    assert payload["updates"][0]["name"] == name
    assert payload["updates"][0]["input"] == original
    assert backend.rollback_snippet_transaction() is True
    assert snippet.Input == original
    assert not list(tmp_path.glob("snippet-*.json"))


def test_registered_snippet_node_has_typed_exposed_ports() -> None:
    declaration = next(
        item
        for item in discover_plugin_declarations(
            SOURCE,
            filename="mechanical_nodes.py",
            allow_reserved_ids=True,
            owner_id=MECHANICAL_ADDON_ID,
            allow_internal_metadata=True,
        )
        if item.spec.type_id == "mechanical.apdl_snippet"
    )
    ports = {port.key: port for port in declaration.spec.ports}
    assert declaration.spec.solution_reuse_scope == "never"
    assert [(port.key, port.data_type, port.data_access) for port in declaration.spec.ports] == [
        ("source_model", "COREX.Mechanical.Model", "item"),
        ("environments", "COREX.Mechanical.Object", "list"),
        ("name", "COREX.DataTypes.String", "item"),
        ("commands", "COREX.DataTypes.String", "item"),
        ("steps", "COREX.DataTypes.String", "item"),
        ("selected_steps", "COREX.DataTypes.Int", "list"),
        ("issue_solve_command", "COREX.DataTypes.Bool", "item"),
        ("model", "COREX.Mechanical.Model", "item"),
        ("snippets", "COREX.Mechanical.Object", "list"),
        ("report", "COREX.DataTypes.TableValue", "item"),
    ]
    assert ports["environments"].accepted_data_types == ("COREX.DataTypes.String",)
    assert ports["source_model"].required is True
    assert ports["commands"].required is True
    assert all(port.exposed for port in ports.values())


def test_generated_operation_never_solves_saves_retries_or_writes_input() -> None:
    source = SNIPPET_PREFLIGHT_BODY + SNIPPET_EXECUTION_BODY
    assert ".Solve(" not in source
    assert ".Save" not in source
    assert "WriteInputFile" not in source
    assert "sleep(" not in source
    assert source.count("AddCommandSnippet()") == 1


def test_empty_environment_selects_supported_static_analyses_but_explicit_unsupported_fails(
    tmp_path, monkeypatch
) -> None:
    backend, tree, first, thermal, second, modal = _backend(tmp_path, monkeypatch)
    plan = _preflight(backend)
    assert [target["analysis_id"] for target in plan["targets"]] == [first.ObjectId, second.ObjectId]
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]

    for unsupported in (thermal, modal):
        with pytest.raises(Exception, match="mechanical.capability_unproved"):
            _preflight(
                backend,
                environments=[
                    {
                        "kind": "typed",
                        "object_id": unsupported.ObjectId,
                        "object_path": f"Model/{unsupported.Name}",
                    }
                ],
            )
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]


def test_all_and_selected_steps_create_in_analysis_then_step_order_and_update_owned(
    tmp_path, monkeypatch
) -> None:
    backend, tree, first, _thermal, second, _modal = _backend(tmp_path, monkeypatch)
    all_plan = _preflight(backend)
    first_result = _run(backend, all_plan, issue_solve=False)
    assert first_result["status"] == "executed"
    assert [row["analysis_id"] for row in first_result["snippet"]["receipts"]] == [10, 30]
    body = "/prep7\n  ! exact  \n"
    created = [item for item in tree.AllObjects if isinstance(item, _Snippet)]
    assert len(created) == 2
    assert all(item.Input.split("\n", 1)[1] == body for item in created)
    assert all(str(item.StepSelectionMode) == "All" for item in created)
    assert all(item.IssueSolveCommand is False for item in created)

    update_plan = _preflight(backend)
    assert [entry["action"] for target in update_plan["targets"] for entry in target["entries"]] == [
        "update",
        "update",
    ]
    original_ids = [item.ObjectId for item in created]
    updated = _run(backend, update_plan, commands="\n/COM,changed\n", issue_solve=True)
    assert [row["action"] for row in updated["snippet"]["receipts"]] == ["update", "update"]
    assert [item.ObjectId for item in tree.AllObjects if isinstance(item, _Snippet)] == original_ids
    assert all(item.Input.split("\n", 1)[1] == "\n/COM,changed\n" for item in created)
    assert all(item.IssueSolveCommand is True for item in created)

    selected_plan = _preflight(backend, steps="selected", selected_steps=[1, 3])
    selected = _run(backend, selected_plan)
    assert [
        (row["analysis_id"], row["step_number"], row["snippet_name"])
        for row in selected["snippet"]["receipts"]
    ] == [
        (first.ObjectId, 1, "COREX commands — Step 1"),
        (first.ObjectId, 3, "COREX commands — Step 3"),
        (second.ObjectId, 1, "COREX commands — Step 1"),
        (second.ObjectId, 3, "COREX commands — Step 3"),
    ]
    assert all(
        str(item.StepSelectionMode) == "ByNumber" and item.StepNumber in {1, 3}
        for item in tree.AllObjects
        if isinstance(item, _Snippet) and "Step" in item.Name
    )


def test_range_capability_and_unowned_collisions_are_preflight_only(tmp_path, monkeypatch) -> None:
    backend, tree, first, _thermal, second, _modal = _backend(tmp_path, monkeypatch)
    with pytest.raises(Exception, match="outside 1..3"):
        _preflight(backend, steps="selected", selected_steps=[1, 4])
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]

    second._type.command_factory = False
    with pytest.raises(Exception, match="AddCommandSnippet"):
        _preflight(backend)
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]
    second._type.command_factory = True

    collision = first.AddCommandSnippet()
    collision.Name = "COREX commands"
    collision.Input = "/COM,user owned"
    before = (collision.Name, collision.Input, collision.StepSelectionMode, collision.StepNumber)
    with pytest.raises(Exception, match="same-name unowned snippet collision"):
        _preflight(backend)
    assert (collision.Name, collision.Input, collision.StepSelectionMode, collision.StepNumber) == before
    assert collision in tree.AllObjects


def test_marker_near_miss_is_unowned_and_duplicate_exact_markers_fail_preflight(
    tmp_path, monkeypatch
) -> None:
    backend, tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    marker = "! COREX_OWNER_V1:c25pcHBldC0x:10:all"
    near = first.AddCommandSnippet()
    near.Name = "COREX commands"
    near.Input = marker + "-near\nuser body"
    with pytest.raises(Exception, match="same-name unowned snippet collision"):
        _preflight(backend, environments=[{"kind": "text", "text": "Static A"}])
    near.Delete()

    duplicates = [first.AddCommandSnippet(), first.AddCommandSnippet()]
    for index, item in enumerate(duplicates):
        item.Name = f"Renamed {index}"
        item.Input = marker + "\nowned body"
    with pytest.raises(Exception, match="duplicate owned snippets"):
        _preflight(backend, environments=[{"kind": "text", "text": "Static A"}])
    assert all(item in tree.AllObjects for item in duplicates)


def test_partial_failure_restores_updates_and_deletes_only_new_owned_snippets(
    tmp_path, monkeypatch
) -> None:
    backend, tree, first, _thermal, second, _modal = _backend(tmp_path, monkeypatch)
    initial = _run(backend, _preflight(backend), commands="old body")
    owned = [item for item in tree.AllObjects if isinstance(item, _Snippet)]
    for index, item in enumerate(owned, start=1):
        marker = item.Input.split("\n", 1)[0]
        item.Name = f"User renamed {index}"
        item.Input = marker + f"\nold exact body {index}\n  "
        item.StepSelectionMode = _EnumValue("ByNumber")
        item.StepNumber = index + 1
        item.IssueSolveCommand = True
    unrelated = first.AddCommandSnippet()
    unrelated.Name = "User snippet"
    unrelated.Input = "user body"
    before = [(item.Name, item.Input, str(item.StepSelectionMode), item.StepNumber, item.IssueSolveCommand) for item in owned]
    owned[1].fail_input_once = True
    failed = _run(backend, _preflight(backend), commands="new body", issue_solve=True)
    assert failed["status"] == "failed"
    assert failed["snippet"]["rollback_verified"] is True
    assert [(item.Name, item.Input, str(item.StepSelectionMode), item.StepNumber, item.IssueSolveCommand) for item in owned] == before
    assert unrelated in tree.AllObjects and unrelated.Input == "user body"
    assert initial["snippet"]["success"] is True

    selected_plan = _preflight(backend, steps="selected", selected_steps=[1, 3])
    second.fail_next_input = True
    failed_create = _run(backend, selected_plan)
    assert failed_create["status"] == "failed"
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet) and "Step" in item.Name]
    assert unrelated in tree.AllObjects


def test_report_failure_rolls_back_completed_native_mutation(tmp_path, monkeypatch) -> None:
    backend, tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    existing = first.AddCommandSnippet()
    marker = "! COREX_OWNER_V1:c25pcHBldC0x:10:all"
    existing.Name = "User renamed"
    existing.Input = marker + "\nold body\n  "
    existing.StepSelectionMode = _EnumValue("ByNumber")
    existing.StepNumber = 2
    existing.IssueSolveCommand = True
    before = (
        existing.Name,
        existing.Input,
        str(existing.StepSelectionMode),
        existing.StepNumber,
        existing.IssueSolveCommand,
    )
    plan = _preflight(backend)
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.backend.collect_catalogue_rows",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("injected Report failure")),
    )
    result = backend.run_snippet(_mutation_args(backend, plan))
    assert result["status"] == "failed"
    assert "injected Report failure" in result["snippet"]["error"]
    assert [item for item in tree.AllObjects if isinstance(item, _Snippet)] == [existing]
    assert (
        existing.Name,
        existing.Input,
        str(existing.StepSelectionMode),
        existing.StepNumber,
        existing.IssueSolveCommand,
    ) == before
    assert backend._snippet_rollback_path is None


def test_corrupt_native_success_receipt_adopts_record_then_restores_and_deletes(
    tmp_path, monkeypatch
) -> None:
    backend, tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    existing = first.AddCommandSnippet()
    marker = "! COREX_OWNER_V1:c25pcHBldC0x:10:all"
    existing.Name = "Different name"
    existing.Input = marker + "\ndifferent body\n  "
    existing.StepSelectionMode = _EnumValue("ByNumber")
    existing.StepNumber = 2
    existing.IssueSolveCommand = True
    before = (
        existing.Name,
        existing.Input,
        str(existing.StepSelectionMode),
        existing.StepNumber,
        existing.IssueSolveCommand,
    )
    native_execute = backend._execute_native_script

    def corrupt(script):
        result = native_execute(script)
        return '{"success":' if "_corex_persist_rollback" in script else result

    backend._execute_native_script = corrupt
    with pytest.raises(json.JSONDecodeError):
        backend.run_snippet(_mutation_args(backend, _preflight(backend)))
    assert [item for item in tree.AllObjects if isinstance(item, _Snippet)] == [existing]
    assert (
        existing.Name,
        existing.Input,
        str(existing.StepSelectionMode),
        existing.StepNumber,
        existing.IssueSolveCommand,
    ) == before
    assert backend._snippet_rollback_path is None


def test_native_error_after_mutation_adopts_record_then_rolls_back(tmp_path, monkeypatch) -> None:
    backend, tree, _first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    native_execute = backend._execute_native_script

    def fail_after_mutation(script):
        result = native_execute(script)
        if "_corex_persist_rollback" in script:
            raise RuntimeError("injected transport return failure")
        return result

    backend._execute_native_script = fail_after_mutation
    with pytest.raises(RuntimeError, match="injected transport return failure"):
        backend.run_snippet(_mutation_args(backend, _preflight(backend)))
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]
    assert backend._snippet_rollback_path is None


def test_owner_report_serialization_failure_rolls_back_or_reports_fatal_restore(
    tmp_path, monkeypatch
) -> None:
    backend, tree, _first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    result = backend.run_snippet(_mutation_args(backend, _preflight(backend)))
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.owner_process._write_bulk",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("injected serialization failure")),
    )
    with pytest.raises(RuntimeError, match="injected serialization failure"):
        _prepare_snippet_response(backend, tmp_path, "request-1", result)
    assert not [item for item in tree.AllObjects if isinstance(item, _Snippet)]
    assert backend._snippet_rollback_path is None

    fatal, fatal_tree, first, _thermal, second, _modal = _backend(
        tmp_path / "fatal", monkeypatch
    )
    fatal.work_root.mkdir()
    first.fail_next_delete = True
    second.fail_next_input = False
    fatal_result = fatal.run_snippet(_mutation_args(fatal, _preflight(fatal)))
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        _prepare_snippet_response(fatal, fatal.work_root, "request-2", fatal_result)
    assert [item for item in fatal_tree.AllObjects if isinstance(item, _Snippet)]


def test_post_report_fatal_restore_retires_the_runtime_session(tmp_path, monkeypatch) -> None:
    backend, _tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    first.fail_next_delete = True
    monkeypatch.setattr(
        "ea_node_editor.addons.mechanical.owner_process._write_bulk",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("injected serialization failure")),
    )

    class Sessions:
        def __init__(self):
            self.session = SimpleNamespace(revision=2, work_root=tmp_path, terminal=False)
            self.retired = False

        def admit_model(self, _model, **_kwargs):
            return self.session

        def operate(self, _session, **kwargs):
            if kwargs["operation"] == "snippet_preflight":
                return backend.snippet_preflight(kwargs["args"])
            self.session.revision += 1
            try:
                result = backend.run_snippet(kwargs["args"])
                _prepare_snippet_response(backend, tmp_path, "request", result)
            except Exception as exc:
                raise OwnerProtocolError(str(exc)) from exc
            raise AssertionError("serialization failure was not injected")

        def retire_session(self, _session):
            self.retired = True

        def register_model(self, *_args, **_kwargs):
            raise AssertionError("failed mutation cannot register a Model")

    sessions = Sessions()
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.retired is True
    assert invalidations == [("open-1", "mechanical_model_mutated")]


def test_corrupt_success_with_failed_restore_is_fatal_and_retires(tmp_path, monkeypatch) -> None:
    backend, _tree, first, _thermal, _second, _modal = _backend(tmp_path, monkeypatch)
    first.fail_next_delete = True
    native_execute = backend._execute_native_script

    def corrupt(script):
        result = native_execute(script)
        return '{"success":' if "_corex_persist_rollback" in script else result

    backend._execute_native_script = corrupt

    class Sessions:
        def __init__(self):
            self.session = SimpleNamespace(revision=2, work_root=tmp_path, terminal=False)
            self.retired = False

        def admit_model(self, _model, **_kwargs):
            return self.session

        def operate(self, _session, **kwargs):
            if kwargs["operation"] == "snippet_preflight":
                return backend.snippet_preflight(kwargs["args"])
            self.session.revision += 1
            try:
                return backend.run_snippet(kwargs["args"])
            except Exception as exc:
                raise OwnerProtocolError(str(exc)) from exc

        def retire_session(self, _session):
            self.retired = True

        def register_model(self, *_args, **_kwargs):
            raise AssertionError("failed mutation cannot register a Model")

    sessions = Sessions()
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.retired is True
    assert invalidations == [("open-1", "mechanical_model_mutated")]


def test_failed_cleanup_is_fatal_and_never_deletes_unrelated_snippets(tmp_path, monkeypatch) -> None:
    backend, tree, first, _thermal, second, _modal = _backend(tmp_path, monkeypatch)
    unrelated = first.AddCommandSnippet()
    unrelated.Name = "User snippet"
    unrelated.Input = "user body"
    first.fail_next_delete = True
    second.fail_next_input = True
    with pytest.raises(RuntimeError, match="mechanical.restore_failed"):
        _run(backend, _preflight(backend))
    assert unrelated in tree.AllObjects and unrelated.Input == "user body"


class _Sessions:
    def __init__(self, tmp_path: Path, *, response="success"):
        self.session = SimpleNamespace(revision=2, work_root=tmp_path, terminal=False)
        self.response = response
        self.calls = []
        self.registered = []
        self.retired = False

    def admit_model(self, _model, **_kwargs):
        return self.session

    def operate(self, _session, **kwargs):
        self.calls.append(kwargs)
        if kwargs["operation"] == "snippet_preflight":
            token = kwargs["args"]["owner_node_token"]
            return {
                "snippet_preflight": {
                    "targets": [
                        {
                            "analysis_id": 7,
                            "analysis_name": "A",
                            "analysis_path": "Model/A",
                            "physics_type": "Mechanical",
                            "analysis_type": "Static",
                            "number_of_steps": 3,
                            "entries": [
                                {
                                    "selection": "all",
                                    "step": None,
                                    "name": kwargs["args"]["name"],
                                    "marker": f"! COREX_OWNER_V1:{token}:7:all",
                                    "existing_id": None,
                                    "action": "create",
                                }
                            ],
                        }
                    ]
                }
            }
        if self.response == "stale":
            raise StaleMechanicalModelError("stale sibling")
        self.session.revision += 1
        if self.response == "owner_error":
            raise OwnerProtocolError("mechanical.restore_failed: rollback mismatch")
        if self.response == "failure":
            return {
                "status": "failed",
                "snippet": {
                    "success": False,
                    "rollback_verified": True,
                    "error": "injected",
                    "receipts": [],
                    "snippets": [],
                },
            }
        identity = kwargs["args"]["catalogue_identity"]
        row = _row(
            model_revision=3,
            catalogue_id=identity["catalogue_id"],
            producer_node_id="snippet-1",
            producer_port="report",
            producer_path="[3,1]",
            producer_iteration=4,
        )
        return {
            "status": "executed",
            "snippet": {
                "success": True,
                "rollback_verified": True,
                "error": "",
                "receipts": [],
                "snippets": [
                    {
                        "object_id": 70,
                        "parent_id": 7,
                        "analysis_id": 7,
                        "object_path": "Model/A/COREX commands",
                        "display_name": "COREX commands",
                        "api_type": "Ansys.ACT.Automation.Mechanical.CommandSnippet",
                        "category": "CommandSnippet",
                    }
                ],
            },
            "catalogue": catalogue_table([row]),
        }

    def register_model(self, _session, **kwargs):
        self.registered.append(kwargs)
        return kwargs

    def retire_session(self, _session):
        self.retired = True


def _runtime_context(tmp_path: Path, sessions: _Sessions):
    invalidations = []
    ctx = ExecutionContext(
        run_id="run-1",
        node_id="snippet-1",
        workspace_id="workspace-1",
        inputs={},
        properties={
            "environments": [],
            "name": "COREX commands",
            "commands": "/prep7",
            "steps": "all",
            "selected_steps": ["inactive-invalid"],
            "issue_solve_command": False,
        },
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
        target_path=(3, 1),
        target_iteration=4,
        workspace_node_types=MappingProxyType(
            {"open-1": "mechanical.open_model", "snippet-1": "mechanical.apdl_snippet"}
        ),
        _request_observation_invalidation=lambda root, reason: invalidations.append((root, reason)),
    )
    return ctx, invalidations


def _model():
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(model_revision=2),
    )


def test_runtime_ignores_inactive_steps_and_returns_fresh_model_snippets_and_report(tmp_path) -> None:
    sessions = _Sessions(tmp_path)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    result = execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert [call["operation"] for call in sessions.calls] == ["snippet_preflight", "run_snippet"]
    assert sessions.calls[0]["args"]["selected_steps"] == []
    assert sessions.calls[1]["mutation"] is True
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    assert isinstance(result["report"], TableValue)
    assert len(result["snippets"]) == 1 and type(result["snippets"][0]) is TypedInlineValue
    assert result["snippets"][0].payload["model_revision"] == 3
    assert result["model"]["producer_node_id"] == "snippet-1"
    assert result["model"]["producer_port"] == "report"


@pytest.mark.parametrize(("response", "retired"), [("failure", False), ("owner_error", True)])
def test_runtime_failure_invalidates_and_only_uncertain_restore_failure_retires(
    tmp_path, response, retired
) -> None:
    sessions = _Sessions(tmp_path, response=response)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    with pytest.raises((ValueError, RuntimeError)):
        execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    assert sessions.retired is retired
    assert not sessions.registered
    assert len([call for call in sessions.calls if call["operation"] == "run_snippet"]) == 1


def test_invalid_or_stale_inputs_never_mutate_or_invalidate(tmp_path) -> None:
    sessions = _Sessions(tmp_path)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    ctx.properties["commands"] = ""
    with pytest.raises(NodeInputNotReadyError):
        execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.calls == [] and invalidations == []

    sessions.response = "stale"
    ctx.properties["commands"] = "/prep7"
    with pytest.raises(ValueError, match="mechanical.stale_reference"):
        execute_apdl_snippet(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert [call["operation"] for call in sessions.calls] == ["snippet_preflight", "run_snippet"]
    assert invalidations == []
