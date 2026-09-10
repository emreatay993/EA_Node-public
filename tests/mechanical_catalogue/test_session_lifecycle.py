from __future__ import annotations

from pathlib import Path
import queue
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import psutil
import pytest

from ea_node_editor.addons.mechanical.session import (
    MechanicalSessionService,
    StaleMechanicalModelError,
)
from ea_node_editor.addons.mechanical import session as session_module
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.run_messages import RetireWorkspaceCommand
from ea_node_editor.execution.run_messages import ProtocolErrorEvent
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.worker_runner import RunControl
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    deserialize_runtime_value,
)
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import _build_trusted_registry
from ea_node_editor.nodes.plugin_contracts import (
    PluginAvailability,
    PluginBackendDescriptor,
)
from ea_node_editor.addons.registry_contributions import _register_plugin_backend
from ea_node_editor.ui.shell.controllers.workspace_navigation_controller import (
    WorkspaceNavigationController,
)


class _Owner:
    def __init__(self) -> None:
        self.closed = False
        self.requests = []

    def request(self, **payload):
        self.requests.append(payload)
        return {"status": "ready"}

    def close(self) -> None:
        self.closed = True


def _catalog() -> DataTypeCatalog:
    return build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
    ).data_types


def _services(owners: list[_Owner]) -> WorkerServices:
    services = WorkerServices()
    services.bind_data_types(_catalog())
    services._mechanical_session_service = MechanicalSessionService(
        services, owner_factory=lambda: owners.append(_Owner()) or owners[-1]
    )
    return services


def _model(service, session):
    return service.register_model(
        session,
        document_id="doc",
        source_key="source",
        system_key="system",
        release_code=261,
        catalogue_id=str(uuid4()),
    )


def test_session_key_shares_dependencies_but_isolates_open_items_and_runs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"original")
    owners: list[_Owner] = []
    services = _services(owners)
    service = services.mechanical_session_service
    first = service.open_session(
        run_id="r1",
        workspace_id="A",
        open_node_id="open-1",
        source_path=source,
        target_path=(2,),
        target_iteration=3,
    )
    assert (
        service.open_session(
            run_id="r1",
            workspace_id="A",
            open_node_id="open-1",
            source_path=source,
            target_path=(2,),
            target_iteration=3,
        )
        is first
    )
    second = service.open_session(
        run_id="r1",
        workspace_id="A",
        open_node_id="open-2",
        source_path=source,
        target_path=(2,),
        target_iteration=3,
    )
    third = service.open_session(
        run_id="r2",
        workspace_id="A",
        open_node_id="open-1",
        source_path=source,
        target_path=(2,),
        target_iteration=3,
    )
    assert len({first.session_id, second.session_id, third.session_id}) == 3
    first.work_path.write_bytes(b"changed")
    assert (
        source.read_bytes() == b"original"
        and third.work_path.read_bytes() == b"original"
    )
    service.reset()


@pytest.mark.parametrize(
    ("source_name", "work_name"),
    [("source.mechpz", "source.mechdb"), ("source.wbpz", "source.wbpj")],
)
def test_native_archives_receive_full_family_specific_work_targets(
    tmp_path: Path, source_name: str, work_name: str
) -> None:
    source = tmp_path / source_name
    source.write_bytes(b"archive")
    owners: list[_Owner] = []
    service = _services(owners).mechanical_session_service
    session = service.open_session(
        run_id="run", workspace_id="workspace", open_node_id="open", source_path=source
    )
    assert session.work_path.name == work_name
    service.reset()


def test_work_root_cleanup_failure_remains_retryable(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    service = _services(owners).mechanical_session_service
    session = service.open_session(
        run_id="run", workspace_id="workspace", open_node_id="open", source_path=source
    )
    real_rmtree = session_module.shutil.rmtree
    real_monotonic = session_module.time.monotonic
    ticks = iter((0.0, 3.0))
    monkeypatch.setattr(session_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(session_module.shutil, "rmtree", lambda *_args, **_kwargs: None)
    with pytest.raises(Exception, match="working directory cleanup failed"):
        session.close()
    assert not session.closed and session.work_root.exists()
    monkeypatch.setattr(session_module.shutil, "rmtree", real_rmtree)
    monkeypatch.setattr(session_module.time, "monotonic", real_monotonic)
    session.close()
    assert session.closed and not session.work_root.exists()


def test_cleanup_expires_handles_despite_output_lease_and_rejects_wrong_run(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    services = _services(owners)
    service = services.mechanical_session_service
    session = service.open_session(
        run_id="r1", workspace_id="A", open_node_id="open", source_path=source
    )
    handle = _model(service, session)
    services.lease_handle(handle, owner_scope="solution:retained")
    with pytest.raises(StaleMechanicalModelError):
        service.admit_model(handle, run_id="wrong", workspace_id="A")
    services.cleanup_run("r1")
    assert owners[0].closed
    with pytest.raises((LookupError, StaleMechanicalModelError)):
        service.admit_model(handle, run_id="r1", workspace_id="A")


def test_interactive_retention_is_workspace_scoped_and_next_run_can_omit_open(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    services = _services(owners)
    service = services.mechanical_session_service
    a = service.open_session(
        run_id="a1",
        workspace_id="A",
        open_node_id="open",
        source_path=source,
        backend_mode="interactive",
    )
    b = service.open_session(
        run_id="b1",
        workspace_id="B",
        open_node_id="open",
        source_path=source,
        backend_mode="interactive",
    )
    service.cleanup_run("a1", succeeded=True)
    service.cleanup_run("b1", succeeded=True)
    assert not owners[0].closed and not owners[1].closed
    assert service.begin_run("a2", "A") == 1
    assert owners[0].closed and not owners[1].closed
    assert service.retire_workspace("B") == 1 and owners[1].closed


def test_application_reset_physically_closes_expired_retained_interactive_owner(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    services = _services(owners)
    session = services.mechanical_session_service.open_session(
        run_id="r1",
        workspace_id="A",
        open_node_id="open",
        source_path=source,
        backend_mode="interactive",
    )
    handle = _model(services.mechanical_session_service, session)
    services.cleanup_run("r1", succeeded=True)
    with pytest.raises((LookupError, StaleMechanicalModelError)):
        services.mechanical_session_service.admit_model(
            handle, run_id="r1", workspace_id="A"
        )
    services.reset()
    assert owners[0].closed


def test_failed_physical_close_remains_owned_and_reset_retries(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")

    class RetryOwner(_Owner):
        attempts = 0

        def close(self) -> None:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("first close failed")
            super().close()

    owner = RetryOwner()
    services = _services([])
    service = MechanicalSessionService(services, owner_factory=lambda: owner)
    session = service.open_session(
        run_id="r", workspace_id="A", open_node_id="open", source_path=source
    )
    warnings = []
    service.cleanup_run("r", warn=warnings.append)
    assert session.terminal and not session.closed and not owner.closed
    assert warnings == ["Mechanical session cleanup failed: first close failed"]
    service.reset()
    assert session.closed and owner.closed and owner.attempts == 2


def test_partial_owner_launch_cleans_work_directory(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    services = _services([])
    service = MechanicalSessionService(
        services,
        owner_factory=lambda: (_ for _ in ()).throw(RuntimeError("launch failed")),
    )
    before = set(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match="launch failed"):
        service.open_session(
            run_id="r", workspace_id="A", open_node_id="open", source_path=source
        )
    assert set(tmp_path.iterdir()) == before


def test_failed_mutation_invalidates_old_revision_and_terminal_failure_closes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    services = _services(owners)
    service = services.mechanical_session_service
    session = service.open_session(
        run_id="r", workspace_id="A", open_node_id="open", source_path=source
    )
    owners[0].request = lambda **_payload: (_ for _ in ()).throw(
        TimeoutError("timeout")
    )
    with pytest.raises(TimeoutError):
        service.operate(session, expected_revision=0, operation="health", mutation=True)
    assert session.revision == 1
    services.cleanup_run("r", succeeded=False)
    assert owners[0].closed


def test_registered_run_cancellation_closes_the_owned_session(tmp_path: Path) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    callbacks = []
    owners: list[_Owner] = []
    service = _services(owners).mechanical_session_service
    service.open_session(
        run_id="r",
        workspace_id="A",
        open_node_id="open",
        source_path=source,
        register_cancel=callbacks.append,
    )
    callbacks[0]()
    assert owners[0].closed


def test_backend_workspace_retirement_fans_out_to_every_concrete_client() -> None:
    calls: list[tuple[str, str]] = []

    class Client:
        def __init__(self, name: str) -> None:
            self.name = name

        def retire_workspace(self, workspace_id: str) -> int:
            calls.append((self.name, workspace_id))
            return 1

    backend = object.__new__(ExecutionBackendClient)
    backend._process_client = Client("process")
    backend._trusted_client = Client("trusted")
    backend._external_python_client = Client("external")
    assert backend.retire_workspace("A") == 3
    assert calls == [("process", "A"), ("trusted", "A"), ("external", "A")]


def test_correlated_retirement_protocol_error_wakes_immediately_and_is_still_published() -> (
    None
):
    client = ProcessExecutionClient()
    published = []
    client.subscribe(published.append)

    def reject(command):
        client._dispatch_event(
            ProtocolErrorEvent(
                request_id=command.request_id,
                workspace_id=command.workspace_id,
                command=command.type,
                error="retirement rejected",
            )
        )
        return True

    client._post_command = reject
    started = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="retirement rejected"):
            client._retire_workspace_via_transport("A", timeout_sec=1.0)
    finally:
        client.shutdown()
    assert time.monotonic() - started < 0.5
    assert any(event["type"] == "protocol_error" for event in published)


def test_unrelated_protocol_error_does_not_settle_retirement_but_transport_eof_does() -> (
    None
):
    client = ProcessExecutionClient()
    client._post_command = lambda _command: True
    result = []

    def retire() -> None:
        try:
            client._retire_workspace_via_transport("A", timeout_sec=2.0)
        except Exception as exc:  # noqa: BLE001
            result.append(str(exc))

    thread = threading.Thread(target=retire)
    thread.start()
    deadline = time.monotonic() + 0.5
    while (
        not getattr(client, "_workspace_retirement_waiters", {})
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    client._dispatch_event(
        ProtocolErrorEvent(
            request_id="unrelated-b",
            workspace_id="B",
            command="viewer_query",
            error="unrelated failure",
        )
    )
    thread.join(timeout=0.05)
    assert thread.is_alive()
    client._fail_workspace_retirements("Execution worker transport closed")
    thread.join(timeout=0.5)
    client.shutdown()
    assert result == ["Execution worker transport closed"]


def test_retirement_timeout_is_bounded() -> None:
    client = ProcessExecutionClient()
    client._post_command = lambda _command: True
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="acknowledge"):
            client._retire_workspace_via_transport("A", timeout_sec=0.05)
    finally:
        client.shutdown()
    assert time.monotonic() - started < 0.5


def test_backend_retirement_attempts_all_clients_before_reporting_failure() -> None:
    calls = []

    class Client:
        def __init__(self, name, error=False):
            self.name = name
            self.error = error

        def retire_workspace(self, workspace_id):
            calls.append((self.name, workspace_id))
            if self.error:
                raise RuntimeError("broken transport")
            return 1

    backend = object.__new__(ExecutionBackendClient)
    backend._process_client = Client("process", error=True)
    backend._trusted_client = Client("trusted")
    backend._external_python_client = Client("external")
    with pytest.raises(RuntimeError, match="broken transport"):
        backend.retire_workspace("A")
    assert set(calls) == {("process", "A"), ("trusted", "A"), ("external", "A")}


def test_direct_run_dispatch_is_fail_closed_when_retirement_fails() -> None:
    backend = ExecutionBackendClient()
    catalog = build_default_registry(include_public_plugins=False).data_types
    try:
        with (
            patch.object(
                backend, "retire_workspace", side_effect=RuntimeError("cleanup failed")
            ),
            patch.object(backend._process_client, "start_run") as start_run,
        ):
            with pytest.raises(RuntimeError, match="cleanup failed"):
                backend.start_run("", "A", data_types=catalog)
        start_run.assert_not_called()
    finally:
        backend.shutdown()


def test_workspace_retirement_is_bounded_across_hung_owners_and_leaves_b(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    release = threading.Event()

    class HungOwner(_Owner):
        def close(self) -> None:
            release.wait(2.0)
            super().close()

    owners: list[HungOwner] = []
    services = _services([])
    service = MechanicalSessionService(
        services, owner_factory=lambda: owners.append(HungOwner()) or owners[-1]
    )
    service.open_session(
        run_id="a1",
        workspace_id="A",
        open_node_id="one",
        source_path=source,
        backend_mode="interactive",
    )
    service.open_session(
        run_id="a1",
        workspace_id="A",
        open_node_id="two",
        source_path=source,
        target_iteration=1,
        backend_mode="interactive",
    )
    service.open_session(
        run_id="b1",
        workspace_id="B",
        open_node_id="one",
        source_path=source,
        backend_mode="interactive",
    )
    service.cleanup_run("a1", succeeded=True)
    service.cleanup_run("b1", succeeded=True)
    monkeypatch.setattr(session_module, "SESSION_CLEANUP_TIMEOUT_SEC", 0.1)
    started = time.monotonic()
    assert service.retire_workspace("A") == 2
    assert time.monotonic() - started < 0.5 and not owners[2].closed
    release.set()
    service.retire_workspace("B")


def test_cleanup_does_not_wait_for_inflight_owner_operation_lock(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    entered = threading.Event()
    release = threading.Event()

    class BusyOwner(_Owner):
        def request(self, **payload):
            entered.set()
            release.wait(2.0)
            return {"status": "ready"}

    owner = BusyOwner()
    services = _services([])
    service = MechanicalSessionService(services, owner_factory=lambda: owner)
    session = service.open_session(
        run_id="r", workspace_id="A", open_node_id="open", source_path=source
    )
    thread = threading.Thread(
        target=lambda: service.operate(
            session, expected_revision=0, operation="health"
        ),
        daemon=True,
    )
    thread.start()
    assert entered.wait(0.5)
    started = time.monotonic()
    service.cleanup_run("r")
    assert time.monotonic() - started < 0.5 and owner.closed
    release.set()
    thread.join(timeout=1.0)


def test_real_corex_process_worker_transports_model_scientific_image_and_cleans_terminal_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from ea_node_editor.settings import plugin_generations_dir

    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    type_id = "custom.mechanical_lifecycle.a1b2c3d4"
    function_source = f"""import base64
import corex
import pandas as pd
from uuid import uuid4
from ea_node_editor.runtime_contracts import ImageValue

@corex.node(id={type_id!r}, name="Mechanical lifecycle probe", category=("Tests",))
@corex.output("model", value_type="COREX.Mechanical.Model")
@corex.output("table", value_type="COREX.DataTypes.TableValue")
@corex.output("image", value_type="COREX.DataTypes.Image")
@corex.output("owner_pid", value_type=int)
@corex.path("source_path", default="")
def probe(ctx, settings):
    session = ctx.mechanical_sessions.open_session(
        run_id=ctx.run_id, workspace_id=ctx.workspace_id, open_node_id=ctx.node_id,
        source_path=settings.source_path, register_cancel=ctx.register_cancel,
    )
    model = ctx.mechanical_sessions.register_model(
        session, document_id="doc", source_key="source", system_key="system",
        release_code=261, catalogue_id=str(uuid4()),
    )
    image = ImageValue.from_png(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    return {{"model": model, "table": pd.DataFrame({{"value": [1.0, 2.0]}}), "image": image, "owner_pid": session.owner.identity.pid}}
"""
    generation_root = plugin_generations_dir()
    registry = _build_trusted_registry(
        addon_runtime_config=(("mechanical.corex", True),),
        generation_root=generation_root,
    )
    backend = PluginBackendDescriptor(
        plugin_id="tests.mechanical_lifecycle",
        display_name="Mechanical lifecycle test",
        get_availability=lambda: PluginAvailability.available(),
        load_descriptors=lambda: (),
        load_function_sources=lambda: (("mechanical_probe.py", function_source),),
        function_type_ids=(type_id,),
    )
    assert _register_plugin_backend(
        backend, registry, "test", generation_root=generation_root
    ) == [type_id]
    registry.freeze()
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        type_id,
        "Probe",
        0,
        0,
        properties={"source_path": str(source)},
    )
    snapshot = build_runtime_snapshot(
        model.project, workspace_id=workspace.workspace_id, registry=registry
    )
    events = []
    terminal = threading.Event()
    client = ProcessExecutionClient()
    client.subscribe(
        lambda event: (
            events.append(event),
            terminal.set()
            if event.get("type") in {"run_completed", "run_failed", "run_stopped"}
            else None,
        )
    )
    try:
        run_id = client.start_run(
            "",
            workspace.workspace_id,
            {"runtime_snapshot": snapshot},
            data_types=registry.data_types,
            plugin_bundles=registry.plugin_bundle_refs(),
            plugin_fingerprint=registry.plugin_fingerprint(),
            registry_contract_fingerprint=registry.contract_fingerprint(),
            addon_runtime_config=registry.addon_runtime_config(),
        )
        assert run_id, [(event.get("error"), event.get("command")) for event in events]
        assert terminal.wait(20.0), events
        assert not [
            (event.get("error"), event.get("traceback"))
            for event in events
            if event.get("type") == "run_failed"
        ]
        settled = next(
            event
            for event in events
            if event.get("type") == "node_settled"
            and event.get("node_id") == node.node_id
        )
        assert settled["status"] == "completed", " | ".join(
            str(item.get("message")) for item in events if item.get("type") == "log"
        )
        outputs = {
            key: deserialize_runtime_value(
                value["value"], catalog=registry.data_types
            ).branches[0][1][0]
            for key, value in settled["outputs"].items()
        }
        assert outputs["model"].metadata["run_id"] == run_id
        assert outputs["table"].to_pandas()["value"].tolist() == [1.0, 2.0]
        assert (outputs["image"].width, outputs["image"].height) == (1, 1)
        deadline = time.monotonic() + 5.0
        while psutil.pid_exists(outputs["owner_pid"]) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not psutil.pid_exists(outputs["owner_pid"])
        assert client.retire_workspace(workspace.workspace_id) == 0
    finally:
        client.shutdown()


def test_active_workspace_b_control_acknowledges_a_retirement_without_stopping_b(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mechdb"
    source.write_bytes(b"source")
    owners: list[_Owner] = []
    services = _services(owners)
    service = services.mechanical_session_service
    service.open_session(
        run_id="a1",
        workspace_id="A",
        open_node_id="open-a",
        source_path=source,
        backend_mode="interactive",
    )
    service.cleanup_run("a1", succeeded=True)
    service.open_session(
        run_id="b1",
        workspace_id="B",
        open_node_id="open-b",
        source_path=source,
    )
    events = queue.Queue()
    control = RunControl(
        None,
        events,
        run_id="b1",
        workspace_id="B",
        data_types=services.data_types,
        workspace_retirement_handler=service.retire_workspace,
    )
    started = time.monotonic()
    control._handle_command(
        RetireWorkspaceCommand(request_id="retire-a", workspace_id="A")
    )
    event = events.get(timeout=0.5)
    assert time.monotonic() - started < 0.5
    assert event["type"] == "workspace_retired" and event["workspace_id"] == "A"
    assert not control.stop_requested and not owners[1].closed
    services.cleanup_run("b1")


def test_empty_retirement_does_not_import_ansys_or_start_owner() -> None:
    before = {name for name in sys.modules if name.startswith("ansys.")}
    services = WorkerServices()
    assert services.mechanical_session_service.retire_workspace("A") == 0
    assert {name for name in sys.modules if name.startswith("ansys.")} == before


def test_successful_workspace_close_finishes_ui_refresh_after_retirement_error() -> (
    None
):
    manager = Mock()
    manager.active_workspace_id.return_value = "B"
    runtime_history = Mock()
    execution_client = Mock()
    execution_client.retire_workspace.side_effect = RuntimeError("cleanup failed")
    host = SimpleNamespace(
        workspace_tabs=SimpleNamespace(tabData=lambda _index: "A"),
        model=SimpleNamespace(
            project=SimpleNamespace(
                workspaces={"A": SimpleNamespace(dirty=False, name="A")}
            )
        ),
        workspace_manager=manager,
        execution_client=execution_client,
        runtime_history=runtime_history,
    )
    controller = object.__new__(WorkspaceNavigationController)
    controller._host = host
    controller.refresh_workspace_tabs = Mock()
    controller.switch_workspace = Mock()
    controller._dialog_parent = lambda: None
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as warning:
        controller.on_workspace_tab_close(0)
    manager.close_workspace.assert_called_once_with("A")
    runtime_history.clear_workspace.assert_called_once_with("A")
    controller.refresh_workspace_tabs.assert_called_once_with()
    controller.switch_workspace.assert_called_once_with("B")
    warning.assert_called_once()
