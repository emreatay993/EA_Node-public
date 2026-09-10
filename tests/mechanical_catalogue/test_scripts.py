# Purpose: Verify scoped Mechanical script execution, mutation revisions, and receipts.
# Map: subsystems/addons.md
# Tests: this file

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.commands import (
    SCRIPT_RECEIPT_TEXT_LIMIT,
    compact_failure_payload,
)
from ea_node_editor.addons.mechanical.catalog import MECHANICAL_ADDON_ID
from ea_node_editor.addons.mechanical.contracts import (
    catalogue_table,
    encode_selector,
    model_handle,
    object_value,
)
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.runtime import execute_run_script
from ea_node_editor.addons.mechanical.session import (
    MechanicalSessionService,
    StaleMechanicalModelError,
)
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import TableValue
from tests.mechanical_catalogue.test_contracts import (
    _model_metadata,
    _object_payload,
    _row,
)


class _Native:
    def __init__(
        self, object_id: int, name: str, parent=None, *, analysis=False, api_type=""
    ):
        self.ObjectId = object_id
        self.Name = name
        self.Parent = parent
        self.VisibleProperties = []
        self.marker = 0
        self._analysis = analysis
        self._api_type = api_type

    def GetType(self):
        suffix = "Analysis" if self._analysis else "Model"
        return SimpleNamespace(
            FullName=self._api_type or f"Ansys.ACT.Automation.Mechanical.{suffix}"
        )


class _Views:
    NumberOfViews = 0

    @staticmethod
    def ExportModelViews(path):
        Path(path).write_text("<ModelViewsManager />", encoding="utf-8")


class _App:
    def __init__(self, model, data_model):
        self.namespace = {
            "ExtAPI": SimpleNamespace(name="ExtAPI"),
            "DataModel": data_model,
            "Model": model,
        }

    def execute_script(self, script):
        exec(compile(script, "<mechanical-script-test>", "exec"), self.namespace)
        return self.namespace["_corex_receipt"]


def _backend(tmp_path: Path):
    root = _Native(1, "Model")
    first = _Native(10, "A", root, analysis=True)
    second = _Native(20, "B", root, analysis=True)
    settings = _Native(
        11,
        "Analysis Settings",
        first,
        api_type="Ansys.ACT.Automation.Mechanical.AnalysisSettings.ANSYSAnalysisSettings",
    )
    model = SimpleNamespace(Analyses=[first, second])
    data_model = SimpleNamespace(ObjectTags=[])
    app = _App(model, data_model)
    backend = MechanicalOwnerBackend()
    backend.app = app
    backend.model = model
    backend.data_model = data_model
    backend.tree = SimpleNamespace(
        AllObjects=[root, first, settings, second], metadata_errors=[]
    )
    backend.graphics = SimpleNamespace(ModelViewManager=_Views())
    backend.systems = []
    backend.work_root = tmp_path.resolve()
    return backend, app, first, second


def _preflight(backend, environments=None, scope="each_environment"):
    return backend.script_preflight(
        {"environments": list(environments or ()), "scope": scope}
    )["script_preflight"]


def _identity(tmp_path: Path):
    return {
        "schema_version": 1,
        "model_revision": 3,
        "producer_iteration": 4,
        "catalogue_id": str(uuid4()),
        "producer_node_id": "script-1",
        "producer_port": "report",
        "producer_path": "[3,1]",
        "run_id": "run-1",
        "session_id": "session-1",
        "document_id": "document-1",
        "source_key": "source-1",
        "system_key": "system-1",
    }


def _run(backend, tmp_path, *, selected_ids, scope, code, stop_on_error=True):
    return backend.run_script(
        {
            "selected_ids": list(selected_ids),
            "scope": scope,
            "code": code,
            "stop_on_error": stop_on_error,
            "catalogue_identity": _identity(tmp_path),
            "view_export_path": str(tmp_path / f"script-views-{uuid4().hex}.xml"),
        }
    )


def test_native_script_receipts_round_trip_latin1_and_nested_unicode(tmp_path: Path) -> None:
    backend, _app, first, _second = _backend(tmp_path)
    first.Name = "Static ³ ° Ω 漢字 \\ path"
    preflight = _preflight(backend)
    assert preflight["analyses"][0]["name"] == first.Name
    result = _run(
        backend,
        tmp_path,
        selected_ids=[first.ObjectId],
        scope="each_environment",
        code='print("22 °C · mm³ · 漢字 \\\\ path")\nresult={"nested":"Ω"}',
    )
    operation = next(row for row in result["rows"] if row["record_kind"] == "operation")
    payload = json.loads(operation["message"])
    assert payload["environment_name"] == first.Name
    assert payload["stdout"] == "22 °C · mm³ · 漢字 \\ path\n"
    assert payload["result"] == "{'nested': 'Ω'}"
    assert not list(tmp_path.glob("script-*.json"))


def test_registered_script_node_has_typed_exposed_ports() -> None:
    declaration = next(
        item
        for item in discover_plugin_declarations(
            SOURCE,
            filename="mechanical_nodes.py",
            allow_reserved_ids=True,
            owner_id=MECHANICAL_ADDON_ID,
            allow_internal_metadata=True,
        )
        if item.spec.type_id == "mechanical.run_script"
    )
    ports = {port.key: port for port in declaration.spec.ports}
    assert declaration.spec.solution_reuse_scope == "never"
    assert [(port.key, port.data_type, port.data_access) for port in declaration.spec.ports] == [
        ("source_model", "COREX.Mechanical.Model", "item"),
        ("environments", "COREX.Mechanical.Object", "list"),
        ("scope", "COREX.DataTypes.String", "item"),
        ("code", "COREX.DataTypes.String", "item"),
        ("timeout_s", "COREX.DataTypes.Double", "item"),
        ("stop_on_error", "COREX.DataTypes.Bool", "item"),
        ("model", "COREX.Mechanical.Model", "item"),
        ("report", "COREX.DataTypes.TableValue", "item"),
    ]
    assert ports["environments"].accepted_data_types == ("COREX.DataTypes.String",)
    assert ports["source_model"].required is True
    assert ports["code"].required is True
    assert all(port.exposed for port in ports.values())


def test_preflight_resolves_text_and_typed_environments_in_tree_order(tmp_path) -> None:
    backend, _app, _first, _second = _backend(tmp_path)
    result = _preflight(
        backend,
        [
            {"kind": "text", "text": "B"},
            {"kind": "typed", "object_id": 10, "object_path": "Model/A"},
        ],
    )
    assert result["selected_ids"] == [10, 20]
    with pytest.raises(Exception, match="ambiguous"):
        _preflight(backend, [{"kind": "text", "text": "missing"}])


def test_each_environment_and_model_once_inject_and_cleanup_context(tmp_path) -> None:
    backend, app, first, second = _backend(tmp_path)
    selected = _preflight(backend)["selected_ids"]
    result = _run(
        backend,
        tmp_path,
        selected_ids=selected,
        scope="each_environment",
        code="analysis.marker += 1\nprint(analysis.Name)\nresult = len(analyses)",
    )
    assert result["status"] == "executed"
    receipts = [
        json.loads(row["message"])
        for row in result["rows"]
        if row["record_kind"] == "operation"
    ]
    assert [row["environment_name"] for row in receipts] == ["A", "B"]
    assert [row["stdout"].strip() for row in receipts] == ["A", "B"]
    assert [row["result"] for row in receipts] == ["2", "2"]
    assert (first.marker, second.marker) == (1, 1)
    assert not {"analysis", "analyses", "result"} & app.namespace.keys()
    frame = result["rows"]
    settings_row = next(
        row
        for row in frame
        if row["record_kind"] == "object" and row["display_name"] == "Analysis Settings"
    )
    assert settings_row["analysis_id"] == 10
    assert [row["status"] for row in frame if row["record_kind"] == "operation"] == [
        "completed",
        "completed",
    ]

    once = _run(
        backend,
        tmp_path,
        selected_ids=[20],
        scope="model_once",
        code="result = str(analysis is None) + ':' + str(len(analyses))",
    )
    once_receipts = [
        json.loads(row["message"])
        for row in once["rows"]
        if row["record_kind"] == "operation"
    ]
    assert [(row["environment_id"], row["result"]) for row in once_receipts] == [
        (None, "True:1")
    ]


@pytest.mark.parametrize(("stop_on_error", "expected_names"), [(True, ["A"]), (False, ["A", "B"])])
def test_script_failure_respects_stop_on_error_but_never_reports_success(
    tmp_path, stop_on_error, expected_names
) -> None:
    backend, _app, _first, second = _backend(tmp_path)
    result = _run(
        backend,
        tmp_path,
        selected_ids=[10, 20],
        scope="each_environment",
        code="\nif analysis.Name == 'A':\n    raise Exception('boom')\nanalysis.marker += 1",
        stop_on_error=stop_on_error,
    )
    assert result["status"] == "failed"
    assert result["script"]["success"] is False
    assert [row["environment_name"] for row in result["script"]["receipts"]] == expected_names
    assert second.marker == (0 if stop_on_error else 1)
    assert "rows" not in result


def test_stdout_capture_and_failure_envelope_are_bounded(tmp_path) -> None:
    backend, _app, _first, _second = _backend(tmp_path)
    result = _run(
        backend,
        tmp_path,
        selected_ids=[10],
        scope="each_environment",
        code="print('x' * 1000000)",
    )
    message = next(
        json.loads(row["message"])
        for row in result["rows"]
        if row["record_kind"] == "operation"
    )
    assert len(message["stdout"]) == SCRIPT_RECEIPT_TEXT_LIMIT

    text = "\\" * SCRIPT_RECEIPT_TEXT_LIMIT
    compact = compact_failure_payload(
        {
            "success": False,
            "receipts": [
                {
                    "environment_id": index,
                    "environment_name": text,
                    "stdout": text,
                    "result": text,
                    "error": text,
                    "status": "failed",
                }
                for index in range(256)
            ],
        }
    )
    assert len(json.dumps(compact, ensure_ascii=True, separators=(",", ":")).encode()) < 1024 * 1024


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
        if kwargs["operation"] == "script_preflight":
            return {"script_preflight": {"analyses": [], "selected_ids": [7]}}
        if self.response == "stale":
            raise StaleMechanicalModelError("stale sibling")
        self.session.revision += 1
        if self.response == "failure":
            return {
                "status": "failed",
                "script": {
                    "success": False,
                    "receipts": [{"environment_name": "A", "status": "failed"}],
                },
            }
        if self.response == "timeout":
            raise TimeoutError("uncertain")
        row = _row(
            model_revision=3,
            catalogue_id=kwargs["args"]["catalogue_identity"]["catalogue_id"],
            producer_node_id="script-1",
            producer_port="report",
            producer_path="[3,1]",
            producer_iteration=4,
        )
        return {"status": "executed", "script": {"success": True, "receipts": []}, "catalogue": catalogue_table([row])}

    def register_model(self, _session, **kwargs):
        self.registered.append(kwargs)
        return kwargs

    def retire_session(self, _session):
        self.retired = True


def _runtime_context(tmp_path: Path, sessions: _Sessions, *, invalidation_callback=None):
    invalidations = []
    ctx = ExecutionContext(
        run_id="run-1",
        node_id="script-1",
        workspace_id="workspace-1",
        inputs={},
        properties={
            "environments": [],
            "scope": "each_environment",
            "code": "result = 1",
            "timeout_s": 600.0,
            "stop_on_error": True,
        },
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
        target_path=(3, 1),
        target_iteration=4,
        workspace_node_types=MappingProxyType({"open-1": "mechanical.open_model", "script-1": "mechanical.run_script"}),
        _request_observation_invalidation=(
            invalidation_callback
            or (lambda root, reason: invalidations.append((root, reason)))
        ),
    )
    return ctx, invalidations


def _model():
    return model_handle(
        handle_id="model",
        owner_scope="run-1",
        worker_generation=1,
        metadata=_model_metadata(model_revision=2),
    )


def _environment():
    return object_value(
        _object_payload(
            object_id=7,
            analysis_id=7,
            object_path="Model/A",
            display_name="A",
            selector_code=encode_selector(
                "object",
                document_id="document-1",
                system_key="system-1",
                object_path="Model/A",
                native_id=7,
            ),
        )
    )


def test_runtime_advances_revision_invalidates_observations_and_registers_exact_locator(tmp_path) -> None:
    sessions = _Sessions(tmp_path)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    result = execute_run_script(
        ctx, _model(), [_environment(), "B"], SimpleNamespace(**ctx.properties)
    )
    assert isinstance(result["report"], TableValue)
    assert [call["operation"] for call in sessions.calls] == ["script_preflight", "run_script"]
    assert sessions.calls[1]["mutation"] is True
    assert sessions.calls[0]["args"]["environments"] == [
        {"kind": "typed", "object_id": 7, "object_path": "Model/A"},
        {"kind": "text", "text": "B"},
    ]
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    assert sessions.registered == [
        {
            "document_id": "document-1",
            "source_key": "source-1",
            "system_key": "system-1",
            "release_code": 261,
            "catalogue_id": result["model"]["catalogue_id"],
            "producer_node_id": "script-1",
            "producer_port": "report",
            "producer_path": (3, 1),
            "producer_iteration": 4,
        }
    ]


@pytest.mark.parametrize("response", ["failure", "timeout"])
def test_attempted_failure_invalidates_and_returns_no_model(tmp_path, response) -> None:
    sessions = _Sessions(tmp_path, response=response)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    with pytest.raises((ValueError, RuntimeError)):
        execute_run_script(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert invalidations == [("open-1", "mechanical_model_mutated")]
    assert not sessions.registered
    assert sessions.retired is (response == "timeout")


def test_invalid_code_is_preflight_only_and_does_not_invalidate(tmp_path) -> None:
    sessions = _Sessions(tmp_path)
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    ctx.properties["code"] = ""
    with pytest.raises(NodeInputNotReadyError):
        execute_run_script(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.calls == []
    assert sessions.session.revision == 2
    assert invalidations == []


def test_late_stale_sibling_performs_no_mutation_or_invalidation(tmp_path) -> None:
    sessions = _Sessions(tmp_path, response="stale")
    ctx, invalidations = _runtime_context(tmp_path, sessions)
    with pytest.raises(ValueError, match="mechanical.stale_reference"):
        execute_run_script(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.session.revision == 2
    assert invalidations == []
    assert not sessions.registered


def test_timeout_retires_even_when_invalidation_publication_fails(tmp_path) -> None:
    sessions = _Sessions(tmp_path, response="timeout")

    def fail_invalidation(_root, _reason):
        raise RuntimeError("publisher closed")

    ctx, _invalidations = _runtime_context(
        tmp_path, sessions, invalidation_callback=fail_invalidation
    )
    with pytest.raises(RuntimeError, match="observation invalidation failed"):
        execute_run_script(ctx, _model(), [], SimpleNamespace(**ctx.properties))
    assert sessions.retired is True
    assert len([call for call in sessions.calls if call["operation"] == "run_script"]) == 1


def test_two_sibling_mutations_cannot_consume_one_revision(tmp_path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    entered = threading.Event()
    release = threading.Event()

    class Owner:
        def request(self, **_kwargs):
            entered.set()
            release.wait(5)
            return {"status": "ok"}

        def close(self):
            return None

    services = WorkerServices()
    services.bind_data_types(
        build_default_registry(
            include_public_plugins=False,
            addon_runtime_config=(("mechanical.corex", True),),
        ).data_types
    )
    service = MechanicalSessionService(services, owner_factory=Owner)
    session = service.open_session(
        run_id="run",
        workspace_id="workspace",
        open_node_id="open",
        source_path=source,
    )
    original = service.register_model(
        session,
        document_id="document",
        source_key="source",
        system_key="system",
        release_code=261,
        catalogue_id=str(uuid4()),
    )
    outcomes = []

    def mutate(label):
        try:
            outcomes.append((label, service.operate(session, expected_revision=0, operation="health", mutation=True)))
        except Exception as exc:  # noqa: BLE001
            outcomes.append((label, exc))

    first = threading.Thread(target=mutate, args=("first",))
    second = threading.Thread(target=mutate, args=("second",))
    first.start()
    assert entered.wait(2)
    second.start()
    release.set()
    first.join(2)
    second.join(2)
    assert sum(isinstance(value, dict) for _, value in outcomes) == 1
    assert sum(isinstance(value, StaleMechanicalModelError) for _, value in outcomes) == 1
    assert session.revision == 1
    revised = service.register_model(
        session,
        document_id="document",
        source_key="source",
        system_key="system",
        release_code=261,
        catalogue_id=str(uuid4()),
        producer_node_id="script",
        producer_port="report",
        producer_path=(1,),
        producer_iteration=0,
    )
    with pytest.raises(StaleMechanicalModelError):
        service.admit_model(original, run_id="run", workspace_id="workspace")
    assert service.admit_model(revised, run_id="run", workspace_id="workspace") is session
    service.cleanup_run("run")
