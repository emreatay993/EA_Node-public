from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import threading
import time

import pytest

from ea_node_editor.addons.tabular_data.metadata import TABULAR_DATA_ADDON_ID
from ea_node_editor.addons.catalog import AddOnRegistration
from ea_node_editor.addons.mars import catalog as mars_catalog
from ea_node_editor.addons.mars.metadata import MARS_ADDON_ID
from ea_node_editor.app_preferences import (
    addon_state,
    default_app_preferences_document,
    set_addon_state,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.function_plugin import EMPTY_PLUGIN_FINGERPRINT
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes.package_manager import (
    PackageInstallState,
    PackageManifest,
)
from ea_node_editor.nodes.plugin_contracts import PluginAvailability
from ea_node_editor.nodes.plugin_contracts import AddOnManifest
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.runtime_requests import ExecutionRequest
from ea_node_editor.ui.shell.registry_replacement import (
    RegistryReplacementCoordinator,
    RegistryReplacementRollbackError,
)
from ea_node_editor.ui.shell.controllers.app_preferences_controller import (
    AppPreferencesController,
    AppPreferencesStore,
)
from ea_node_editor.ui_qml.viewer_session_bridge import ViewerSessionBridge
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge


def _registry(
    type_id: str = "",
    *,
    plugin_fingerprint: str = EMPTY_PLUGIN_FINGERPRINT,
    display_name: str = "",
    addon_runtime_config: tuple[tuple[str, bool], ...] = (),
) -> NodeRegistry:
    registry = NodeRegistry(addon_runtime_config=addon_runtime_config)
    if type_id:
        registry.register_descriptor(
            NodeTypeSpec(
                type_id=type_id,
                display_name=display_name or type_id,
                category_path=("Tests",),
                icon="",
                ports=(),
                properties=(),
            ),
            lambda: None,  # type: ignore[arg-type]
        )
    registry.set_python_plugin_catalog(
        (),
        plugin_fingerprint=plugin_fingerprint,
    )
    registry.freeze()
    return registry


def _project(type_id: str = "") -> ProjectData:
    workspace = WorkspaceData(workspace_id="ws", name="Workspace", dirty=True)
    workspace.mutation_revision = 7
    if type_id:
        workspace.nodes["node"] = NodeInstance(
            node_id="node",
            type_id=type_id,
            title="Node",
            x=0.0,
            y=0.0,
        )
    return ProjectData(
        project_id="project",
        name="Project",
        active_workspace_id="ws",
        workspaces={"ws": workspace},
        project_document_revision=5,
    )


class _ForcedContractRegistry(NodeRegistry):
    def __init__(self, contract_fingerprint: str) -> None:
        super().__init__()
        self._forced_contract_fingerprint = contract_fingerprint

    def contract_fingerprint(self) -> str:
        return self._forced_contract_fingerprint


class _FailureController:
    def __init__(
        self,
        fail_step: str = "",
        *,
        rollback_fail_steps: tuple[str, ...] = (),
    ) -> None:
        self.fail_step = fail_step
        self.rollback_fail_steps = frozenset(rollback_fail_steps)
        self.calls: list[str] = []

    def apply(self, step: str) -> None:
        self.calls.append(f"apply:{step}")
        if self.fail_step == step:
            raise RuntimeError(f"failed after {step}")

    def rollback(self, step: str) -> None:
        self.calls.append(f"rollback:{step}")
        if step in self.rollback_fail_steps:
            raise RuntimeError(f"rollback failed at {step}")


class _RegistryConsumer:
    def __init__(
        self,
        current: NodeRegistry,
        replacement: NodeRegistry,
        failure: _FailureController,
        step: str,
    ) -> None:
        self.current = current
        self._old = current
        self._replacement = replacement
        self._failure = failure
        self._step = step

    def replace_registry(self, registry: NodeRegistry) -> None:
        self.current = registry
        if registry is self._replacement:
            self._failure.apply(self._step)
        elif registry is self._old:
            self._failure.rollback(self._step)


class _Runtime(_RegistryConsumer):
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.preflights = 0

    def assert_registry_replaceable(self) -> None:
        self.preflights += 1

    @contextmanager
    def registry_publication_guard(self):  # noqa: ANN201
        yield


class _SessionStore:
    def __init__(
        self,
        old_serializer: object,
        failure: _FailureController,
    ) -> None:
        self.serializer = old_serializer
        self._old = old_serializer
        self._failure = failure

    def replace_serializer(self, serializer: object) -> None:
        self.serializer = serializer
        if serializer is self._old:
            self._failure.rollback("session_store")
        else:
            self._failure.apply("session_store")


class _ViewerSessions:
    def __init__(
        self,
        current: NodeRegistry,
        replacement: NodeRegistry,
        failure: _FailureController,
    ) -> None:
        self.data_types = current.data_types
        self._old = current.data_types
        self._replacement = replacement.data_types
        self._failure = failure
        self.preflights = 0

    def assert_registry_replaceable(self) -> None:
        self.preflights += 1

    def replace_data_types(self, data_types) -> None:  # noqa: ANN001
        self.data_types = data_types
        if data_types is self._replacement:
            self._failure.apply("viewer_catalog")
        elif data_types is self._old:
            self._failure.rollback("viewer_catalog")


class _Signal:
    def __init__(
        self,
        failure: _FailureController,
        *,
        notification_owner: bool = False,
    ) -> None:
        self._failure = failure
        self._notification_owner = notification_owner

    def emit(self) -> None:
        if self._notification_owner:
            self._failure.apply("notifications")


class _ObserverSignal:
    def __init__(self, host: "_Host", observed: list[NodeRegistry], *, fail=False) -> None:
        self._host = host
        self._observed = observed
        self._fail = fail

    def emit(self) -> None:
        self._observed.append(self._host.registry)
        if self._fail:
            raise RuntimeError("listener failed")


class _ViewerHost:
    def __init__(self, failure: _FailureController) -> None:
        self._failure = failure

    def rebuild_addon_binders(
        self,
        *,
        preferences_document=None,  # noqa: ANN001
        reason: str = "",
    ) -> None:
        del preferences_document
        if reason.startswith("rollback:"):
            self._failure.rollback("addon_viewer_services")
        else:
            self._failure.apply("addon_viewer_services")


class _Host:
    def __init__(
        self,
        current: NodeRegistry,
        replacement: NodeRegistry,
        project: ProjectData,
        failure: _FailureController,
    ) -> None:
        self._current = current
        self._replacement = replacement
        self._failure = failure
        self._registry = current
        self._serializer = JsonProjectSerializer(current)
        self._initializing = True
        self.execution_client = _Runtime(
            current,
            replacement,
            failure,
            "runtime",
        )
        self.scene = _RegistryConsumer(
            current,
            replacement,
            failure,
            "graph_scene",
        )
        self.graph_interactions = _RegistryConsumer(
            current,
            replacement,
            failure,
            "graph_interactions",
        )
        self.session_store = _SessionStore(self._serializer, failure)
        self.viewer_session_bridge = _ViewerSessions(
            current,
            replacement,
            failure,
        )
        self.model = SimpleNamespace(project=project)
        self.node_library_changed = _Signal(failure, notification_owner=True)
        self.selected_node_changed = _Signal(failure)
        self.workspace_state_changed = _Signal(failure)
        self._initializing = False

    @property
    def registry(self) -> NodeRegistry:
        return self._registry

    @registry.setter
    def registry(self, registry: NodeRegistry) -> None:
        self._registry = registry
        if getattr(self, "_initializing", True):
            return
        if registry is self._replacement:
            self._failure.apply("host_registry")
        elif registry is self._current:
            self._failure.rollback("host_registry")

    @property
    def serializer(self):  # noqa: ANN201
        return self._serializer

    @serializer.setter
    def serializer(self, serializer) -> None:  # noqa: ANN001
        self._serializer = serializer
        if getattr(self, "_initializing", True):
            return
        if serializer is self.session_store._old:
            self._failure.rollback("serializer")
        else:
            self._failure.apply("serializer")


class _PackageTransaction:
    def __init__(self, calls: list[str]) -> None:
        self.manifest = PackageManifest(name="packet", nodes=[])
        self.staged_package_root = Path("staged")
        self.installed_package_root = Path("installed")
        self.state = PackageInstallState.STAGED
        self.issues: tuple[str, ...] = ()
        self.calls = calls
        self.rollback_failures_remaining = 0
        self.commit_issues: tuple[str, ...] = ()

    def activate(self) -> None:
        self.calls.append("package:activate")
        self.state = PackageInstallState.ACTIVATED

    def commit(self) -> None:
        self.calls.append("package:commit")
        self.state = PackageInstallState.COMMITTED
        self.issues = self.commit_issues

    def rollback(self) -> None:
        self.calls.append("package:rollback")
        if self.rollback_failures_remaining:
            self.rollback_failures_remaining -= 1
            self.state = PackageInstallState.FAILED
            self.issues = ("rollback_test",)
            raise RuntimeError("package rollback failed")
        self.state = PackageInstallState.ROLLED_BACK
        self.issues = ()


def _coordinator(
    tmp_path: Path,
    host: _Host,
    registries: list[NodeRegistry],
    *,
    build_calls: list[dict[str, object]] | None = None,
    package_stager=None,  # noqa: ANN001
) -> RegistryReplacementCoordinator:
    def build_candidate(**kwargs):  # noqa: ANN003
        if build_calls is not None:
            build_calls.append(dict(kwargs))
        return registries.pop(0)

    return RegistryReplacementCoordinator(
        host,
        candidate_builder=build_candidate,
        package_stager=package_stager or (lambda *_args, **_kwargs: None),
        generation_root_provider=lambda: tmp_path / "canonical",
    )


def test_plugin_reload_publishes_every_consumer_without_changing_graph_state(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    project = _project()
    workspace = project.workspaces["ws"]
    project_revision = project.project_document_revision
    workspace_revision = workspace.mutation_revision
    dirty = workspace.dirty
    failure = _FailureController()
    host = _Host(current, replacement, project, failure)
    coordinator = _coordinator(tmp_path, host, [candidate, replacement])

    result = coordinator.reload_plugins()

    assert result.applied
    assert result.registry is replacement
    assert failure.calls == [
        "apply:runtime",
        "apply:graph_scene",
        "apply:host_registry",
        "apply:graph_interactions",
        "apply:serializer",
        "apply:session_store",
        "apply:viewer_catalog",
        "apply:notifications",
    ]
    assert host.execution_client.preflights == 2
    assert host.viewer_session_bridge.preflights == 2
    assert project.project_document_revision == project_revision
    assert workspace.mutation_revision == workspace_revision
    assert workspace.dirty is dirty


@pytest.mark.parametrize(
    "fail_step",
    (
        "runtime",
        "graph_scene",
        "host_registry",
        "graph_interactions",
        "serializer",
        "session_store",
        "viewer_catalog",
    ),
)
def test_publication_failure_rolls_back_in_exact_reverse_order(
    tmp_path: Path,
    fail_step: str,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController(fail_step)
    host = _Host(current, replacement, _project(), failure)
    coordinator = _coordinator(tmp_path, host, [candidate, replacement])
    step_order = [
        "runtime",
        "graph_scene",
        "host_registry",
        "graph_interactions",
        "serializer",
        "session_store",
        "viewer_catalog",
    ]
    failed_index = step_order.index(fail_step)

    with pytest.raises(RuntimeError, match=f"failed after {fail_step}"):
        coordinator.reload_plugins()

    applied = step_order[: failed_index + 1]
    rollback = [
        step
        for step in reversed(applied)
        if step != "notifications"
    ]
    assert failure.calls == [
        *(f"apply:{step}" for step in applied),
        *(f"rollback:{step}" for step in rollback),
    ]
    assert host.registry is current
    assert host.execution_client.current is current
    assert host.scene.current is current
    assert host.graph_interactions.current is current
    assert host.session_store.serializer is host.serializer
    assert host.viewer_session_bridge.data_types is current.data_types


def test_rollback_continues_and_surfaces_stable_aggregate_failures(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController(
        "viewer_catalog",
        rollback_fail_steps=("session_store", "runtime"),
    )
    host = _Host(current, replacement, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    transaction.rollback_failures_remaining = 2
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, replacement],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    with pytest.raises(RegistryReplacementRollbackError) as captured:
        coordinator.import_package(Path("packet.cxpkg"))

    assert captured.value.failures == (
        ("session_store", "restore_failed"),
        ("runtime", "restore_failed"),
        ("package", "failed:rollback_test"),
    )
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert "failed after viewer_catalog" in str(captured.value.__cause__)
    assert package_calls == [
        "package:activate",
        "package:rollback",
        "package:rollback",
    ]
    assert "rollback:serializer" in failure.calls
    assert "rollback:graph_scene" in failure.calls


def test_package_import_stages_then_activates_and_commits_last(tmp_path: Path) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    build_calls: list[dict[str, object]] = []

    def stage(path: Path):
        package_calls.append(f"package:stage:{path.name}")
        return transaction

    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, replacement],
        build_calls=build_calls,
        package_stager=stage,
    )

    result = coordinator.import_package(Path("packet.cxpkg"))

    assert result.applied
    assert result.package_manifest is transaction.manifest
    assert package_calls == [
        "package:stage:packet.cxpkg",
        "package:activate",
        "package:commit",
    ]
    assert build_calls[0]["staged_package_root"] == transaction.staged_package_root
    assert build_calls[1]["staged_package_root"] is None
    assert failure.calls[-1] == "apply:notifications"


def test_committed_package_cleanup_issues_are_nonfatal_result_warnings(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    transaction = _PackageTransaction([])
    transaction.commit_issues = ("commit_backup_cleanup",)
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, replacement],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    result = coordinator.import_package(Path("packet.cxpkg"))

    assert result.applied
    assert result.warnings == ("commit_backup_cleanup",)
    assert transaction.state is PackageInstallState.COMMITTED
    assert host.registry is replacement
    assert "rollback:runtime" not in failure.calls


def test_incompatible_package_rolls_back_before_activation(tmp_path: Path) -> None:
    type_id = "tests.open_node"
    current = _registry(type_id)
    incompatible = _registry()
    failure = _FailureController()
    project = _project(type_id)
    host = _Host(current, incompatible, project, failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    coordinator = _coordinator(
        tmp_path,
        host,
        [incompatible],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    result = coordinator.import_package(Path("packet.cxpkg"))

    assert not result.applied
    assert result.report.issues[0].code == "node_type_missing"
    assert package_calls == ["package:rollback"]
    assert host.registry is current
    assert project.workspaces["ws"].mutation_revision == 7
    assert project.workspaces["ws"].dirty


def test_final_contract_mismatch_rolls_back_activated_package(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    mismatched = _registry(plugin_fingerprint="1" * 64)
    failure = _FailureController()
    host = _Host(current, mismatched, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, mismatched],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    with pytest.raises(RuntimeError, match="contract does not match"):
        coordinator.import_package(Path("packet.cxpkg"))

    assert package_calls == ["package:activate", "package:rollback"]
    assert failure.calls == []
    assert host.registry is current


def test_full_contract_mismatch_rejects_trusted_node_change_before_commit(
    tmp_path: Path,
) -> None:
    type_id = "tests.trusted_contract"
    current = _registry()
    candidate = _registry(type_id, display_name="Accepted")
    mismatched = _registry(type_id, display_name="Changed")
    assert candidate.data_types.fingerprint() == mismatched.data_types.fingerprint()
    assert candidate.plugin_fingerprint() == mismatched.plugin_fingerprint()
    assert candidate.contract_fingerprint() != mismatched.contract_fingerprint()
    failure = _FailureController()
    host = _Host(current, mismatched, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, mismatched],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    with pytest.raises(RuntimeError, match="contract does not match"):
        coordinator.import_package(Path("packet.cxpkg"))

    assert package_calls == ["package:activate", "package:rollback"]
    assert failure.calls == []
    assert host.registry is current


def test_actual_final_registry_runs_second_compatibility_check(tmp_path: Path) -> None:
    type_id = "tests.final_check"
    current = _registry(type_id)
    candidate = _registry(type_id)
    final = _ForcedContractRegistry(candidate.contract_fingerprint())
    final.set_python_plugin_catalog(
        (),
        plugin_fingerprint=EMPTY_PLUGIN_FINGERPRINT,
    )
    final.freeze()
    failure = _FailureController()
    host = _Host(current, final, _project(type_id), failure)
    coordinator = _coordinator(tmp_path, host, [candidate, final])

    with pytest.raises(RuntimeError, match="Final registry is incompatible"):
        coordinator.reload_plugins()

    assert failure.calls == []
    assert host.registry is current


def test_package_activation_failure_rolls_back_staging_before_publication(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)

    def fail_activation() -> None:
        package_calls.append("package:activate")
        raise OSError("activation failed")

    transaction.activate = fail_activation  # type: ignore[method-assign]
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    with pytest.raises(OSError, match="activation failed"):
        coordinator.import_package(Path("packet.cxpkg"))

    assert package_calls == ["package:activate", "package:rollback"]
    assert failure.calls == []
    assert host.registry is current


def test_active_runtime_refusal_happens_before_package_staging(
    tmp_path: Path,
) -> None:
    current = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    staged: list[Path] = []

    def refuse() -> None:
        raise RuntimeError("active run")

    host.execution_client.assert_registry_replaceable = refuse
    coordinator = RegistryReplacementCoordinator(
        host,
        candidate_builder=lambda **_kwargs: replacement,
        package_stager=lambda path, **_kwargs: staged.append(path),
        generation_root_provider=lambda: tmp_path / "canonical",
    )

    with pytest.raises(RuntimeError, match="active run"):
        coordinator.import_package(Path("packet.cxpkg"))

    assert staged == []
    assert failure.calls == []


def test_final_guarded_preflight_refusal_rolls_back_staged_package(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    package_calls: list[str] = []
    transaction = _PackageTransaction(package_calls)
    preflight_calls = 0

    def preflight() -> None:
        nonlocal preflight_calls
        preflight_calls += 1
        if preflight_calls == 2:
            raise RuntimeError("run admitted before guarded phase")

    host.execution_client.assert_registry_replaceable = preflight
    coordinator = _coordinator(
        tmp_path,
        host,
        [candidate, replacement],
        package_stager=lambda *_args, **_kwargs: transaction,
    )

    with pytest.raises(RuntimeError, match="run admitted"):
        coordinator.import_package(Path("packet.cxpkg"))

    assert preflight_calls == 2
    assert package_calls == ["package:rollback"]
    assert transaction.state is PackageInstallState.ROLLED_BACK
    assert host.registry is current


def test_publication_guard_blocks_run_and_viewer_until_failed_publication_rolls_back(
    tmp_path: Path,
) -> None:
    current = _registry(plugin_fingerprint="3" * 64)
    candidate = _registry()
    replacement = _registry()
    runtime_applied = threading.Event()
    scene_entered = threading.Event()
    release_failure = threading.Event()
    run_attempted = threading.Event()
    viewer_attempted = threading.Event()

    class GuardedBackend:
        def __init__(self) -> None:
            self.lock = threading.RLock()
            self.registry = current
            self.admissions: list[tuple[str, object]] = []

        @contextmanager
        def registry_publication_guard(self):  # noqa: ANN201
            with self.lock:
                yield

        def subscribe(self, _callback):  # noqa: ANN001
            return lambda: None

        def assert_registry_replaceable(self) -> None:
            return None

        def replace_registry(self, registry: NodeRegistry) -> bool:
            self.registry = registry
            if registry is replacement:
                runtime_applied.set()
            return True

        def start_run(self, **kwargs):  # noqa: ANN003, ANN201
            self.admissions.append(
                ("run", kwargs["registry_contract_fingerprint"])
            )
            return "run-after-rollback"

        def open_viewer_session(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
            self.admissions.append(("viewer", (args, kwargs)))
            return "viewer-after-rollback"

    class PausingFailScene:
        def __init__(self) -> None:
            self.current = current

        def replace_registry(self, registry: NodeRegistry) -> None:
            self.current = registry
            if registry is replacement:
                scene_entered.set()
                assert release_failure.wait(timeout=5.0)
                raise RuntimeError("scene publication failed")

    backend = GuardedBackend()
    runtime = CorexRuntime(client=backend, registry=current)  # type: ignore[arg-type]
    runtime.prepare_request = lambda request: request  # type: ignore[method-assign]
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    host.execution_client = runtime
    host.scene = PausingFailScene()
    coordinator = _coordinator(tmp_path, host, [candidate, replacement])
    coordinator_errors: list[BaseException] = []

    def replace_registry() -> None:
        try:
            coordinator.reload_plugins()
        except BaseException as exc:  # noqa: BLE001
            coordinator_errors.append(exc)

    def start_run() -> None:
        run_attempted.set()
        runtime.assert_registry_replaceable()
        backend.admissions.append(("run", runtime._registry.contract_fingerprint()))  # noqa: SLF001

    def open_viewer() -> None:
        viewer_attempted.set()
        runtime.open_viewer_session(workspace_id="ws", node_id="viewer")

    coordinator_thread = threading.Thread(target=replace_registry)
    coordinator_thread.start()
    assert runtime_applied.wait(timeout=5.0)
    assert scene_entered.wait(timeout=5.0)
    run_thread = threading.Thread(target=start_run)
    viewer_thread = threading.Thread(target=open_viewer)
    run_thread.start()
    viewer_thread.start()
    assert run_attempted.wait(timeout=2.0)
    assert viewer_attempted.wait(timeout=2.0)
    time.sleep(0.1)
    assert backend.admissions == []

    release_failure.set()
    coordinator_thread.join(timeout=5.0)
    run_thread.join(timeout=5.0)
    viewer_thread.join(timeout=5.0)

    assert not coordinator_thread.is_alive()
    assert not run_thread.is_alive()
    assert not viewer_thread.is_alive()
    assert len(coordinator_errors) == 1
    assert "scene publication failed" in str(coordinator_errors[0])
    assert backend.registry is current
    assert runtime._registry is current  # noqa: SLF001
    assert host.registry is current
    assert {kind for kind, _payload in backend.admissions} == {"run", "viewer"}
    run_payload = next(
        payload for kind, payload in backend.admissions if kind == "run"
    )
    assert run_payload == current.contract_fingerprint()


def test_viewer_session_bridge_refuses_active_projection_and_replaces_catalog() -> None:
    current = _registry()
    replacement = _registry(plugin_fingerprint="2" * 64)
    bridge = ViewerSessionBridge(
        execution_client_provider=lambda: None,
        active_workspace_id_provider=lambda: "",
        workspace_provider=lambda _workspace_id: None,
        data_types=current.data_types,
    )
    bridge._sessions = {  # noqa: SLF001
        ("ws", "node"): SimpleNamespace(
            phase="open",
            pending_display=SimpleNamespace(phase=None),
        )
    }

    with pytest.raises(RuntimeError, match="viewer session is active"):
        bridge.assert_registry_replaceable()

    bridge._sessions.clear()  # noqa: SLF001
    bridge.assert_registry_replaceable()
    bridge.replace_data_types(replacement.data_types)
    assert bridge._data_types is replacement.data_types  # noqa: SLF001


def test_invalid_candidate_preserves_current_registry(tmp_path: Path) -> None:
    current = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)

    def invalid_candidate(**_kwargs):
        raise ValueError("invalid draft")

    coordinator = RegistryReplacementCoordinator(
        host,
        candidate_builder=invalid_candidate,
        generation_root_provider=lambda: tmp_path / "canonical",
    )

    with pytest.raises(ValueError, match="invalid draft"):
        coordinator.reload_plugins()

    assert failure.calls == []
    assert host.registry is current


def test_plugin_reload_and_package_import_share_one_coordinator_api() -> None:
    assert callable(RegistryReplacementCoordinator.reload_plugins)
    assert callable(RegistryReplacementCoordinator.import_package)


def test_addon_apply_uses_transaction_and_persists_preferences_last(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),))
    candidate = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),))
    replacement = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),))
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    host.viewer_host_service = _ViewerHost(failure)
    state_checks: list[tuple[NodeRegistry, str, bool]] = []
    original_state_check = RegistryReplacementCoordinator._assert_requested_addon_state

    def record_state_check(
        registry: NodeRegistry,
        *,
        addon_id: str,
        expected_enabled: bool,
    ) -> None:
        state_checks.append((registry, addon_id, expected_enabled))
        original_state_check(
            registry,
            addon_id=addon_id,
            expected_enabled=expected_enabled,
        )

    monkeypatch.setattr(
        RegistryReplacementCoordinator,
        "_assert_requested_addon_state",
        staticmethod(record_state_check),
    )

    class RecordingController(AppPreferencesController):
        def persist_document(self, document):  # noqa: ANN001
            failure.calls.append("persist")
            return super().persist_document(document)

    coordinator = _coordinator(tmp_path, host, [candidate, replacement])
    preferences_controller = RecordingController(
        store=AppPreferencesStore(
            path_provider=lambda: tmp_path / "app_preferences.json"
        ),
        preloaded_document=default_app_preferences_document(),
    )

    result = coordinator.apply_addon_enabled_state(
        TABULAR_DATA_ADDON_ID,
        enabled=False,
        app_preferences_controller=preferences_controller,
    )

    assert result.registry is replacement
    assert state_checks == [
        (candidate, TABULAR_DATA_ADDON_ID, False),
        (replacement, TABULAR_DATA_ADDON_ID, False),
    ]
    assert failure.calls == [
        "apply:runtime",
        "apply:graph_scene",
        "apply:host_registry",
        "apply:graph_interactions",
        "apply:serializer",
        "apply:session_store",
        "apply:viewer_catalog",
        "persist",
        "apply:notifications",
    ]


def test_addon_request_rejects_matching_wrong_candidate_and_final_state(
    tmp_path: Path,
) -> None:
    current = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),))
    candidate = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),))
    final_registry = _registry(
        addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),)
    )
    assert candidate.contract_fingerprint() == final_registry.contract_fingerprint()
    failure = _FailureController()
    host = _Host(current, final_registry, _project(), failure)
    build_calls: list[dict[str, object]] = []
    registries = [candidate, final_registry]

    class RecordingController:
        persist_calls = 0

        @staticmethod
        def document():  # noqa: ANN205
            return default_app_preferences_document()

        def persist_document(self, document):  # noqa: ANN001, ANN201
            self.persist_calls += 1
            return document

    controller = RecordingController()
    with pytest.raises(RuntimeError, match="requested enabled state"):
        _coordinator(
            tmp_path,
            host,
            registries,
            build_calls=build_calls,
        ).apply_addon_enabled_state(
            TABULAR_DATA_ADDON_ID,
            enabled=False,
            app_preferences_controller=controller,
        )

    assert len(build_calls) == 1
    assert registries == [final_registry]
    assert controller.persist_calls == 0
    assert failure.calls == []
    assert host.registry is current
    assert host.execution_client.current is current
    assert host.scene.current is current
    assert host.graph_interactions.current is current
    assert host.viewer_session_bridge.data_types is current.data_types


def test_addon_request_rejects_final_only_state_mismatch_before_publication(
    tmp_path: Path,
) -> None:
    current = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),))
    candidate = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),))
    final_registry = _registry(
        addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),)
    )
    failure = _FailureController()
    host = _Host(current, final_registry, _project(), failure)
    build_calls: list[dict[str, object]] = []

    class RecordingController:
        persist_calls = 0

        @staticmethod
        def document():  # noqa: ANN205
            return default_app_preferences_document()

        def persist_document(self, document):  # noqa: ANN001, ANN201
            self.persist_calls += 1
            return document

    controller = RecordingController()
    with pytest.raises(RuntimeError, match="requested enabled state"):
        _coordinator(
            tmp_path,
            host,
            [candidate, final_registry],
            build_calls=build_calls,
        ).apply_addon_enabled_state(
            TABULAR_DATA_ADDON_ID,
            enabled=False,
            app_preferences_controller=controller,
        )

    assert len(build_calls) == 2
    assert controller.persist_calls == 0
    assert failure.calls == []
    assert host.registry is current
    assert host.execution_client.current is current
    assert host.scene.current is current
    assert host.graph_interactions.current is current
    assert host.viewer_session_bridge.data_types is current.data_types


def test_restart_required_addon_persists_pending_without_registry_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = AddOnRegistration(
        manifest=AddOnManifest(
            addon_id="tests.addons.restart_only",
            display_name="Restart Only",
            apply_policy="restart_required",
        ),
        backend_module="tests.addons.restart_only",
        backend_id="tests.addons.restart_only",
    )
    monkeypatch.setattr(
        "ea_node_editor.addons.state_changes.registered_addon_registration_by_id",
        lambda _addon_id: registration,
    )
    current = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    build_calls: list[dict[str, object]] = []
    coordinator = _coordinator(
        tmp_path,
        host,
        [],
        build_calls=build_calls,
    )

    class RecordingController:
        def __init__(self) -> None:
            self._document = default_app_preferences_document()

        def document(self):  # noqa: ANN201
            return self._document

        def persist_document(self, document):  # noqa: ANN001, ANN201
            failure.calls.append("persist")
            self._document = document
            return document

    result = coordinator.apply_addon_enabled_state(
        registration.manifest.addon_id,
        enabled=False,
        app_preferences_controller=RecordingController(),
    )

    assert result.restart_required is True
    assert result.registry is None
    assert build_calls == []
    assert failure.calls == ["persist"]
    assert host.execution_client.preflights == 0
    assert host.viewer_session_bridge.preflights == 0
    assert addon_state(result.preferences_document, registration.manifest.addon_id) == {
        "enabled": False,
        "pending_restart": True,
    }


def test_mars_hot_apply_restores_exact_registry_and_open_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mars_catalog,
        "PLUGIN_BACKENDS",
        (
            replace(
                mars_catalog.MARS_PLUGIN_BACKEND,
                get_availability=lambda: PluginAvailability.available(),
            ),
        ),
    )
    disabled_preferences = set_addon_state(
        default_app_preferences_document(),
        MARS_ADDON_ID,
        enabled=False,
        pending_restart=False,
    )
    enabled_preferences = set_addon_state(
        disabled_preferences,
        MARS_ADDON_ID,
        enabled=True,
        pending_restart=False,
    )
    canonical_root = tmp_path / "canonical"

    def registry(enabled: bool, root: Path) -> NodeRegistry:
        return build_default_registry(
            include_public_plugins=False,
            preferences_document=(
                enabled_preferences if enabled else disabled_preferences
            ),
            generation_root=root,
        )

    initial = registry(False, canonical_root)
    first_enabled = registry(True, canonical_root)
    first_bundle = next(
        bundle
        for bundle in first_enabled.plugin_bundle_refs()
        if bundle.owner_id == MARS_ADDON_ID
    )
    project = _project("plot.signal")
    original_node = replace(project.workspaces["ws"].nodes["node"])
    original_revisions = (
        project.project_document_revision,
        project.workspaces["ws"].mutation_revision,
        project.workspaces["ws"].dirty,
    )

    def apply(
        current: NodeRegistry,
        replacement: NodeRegistry,
        *,
        enabled: bool,
        preferences_document: dict[str, object],
        candidate_root: Path,
    ) -> NodeRegistry:
        candidate = registry(enabled, candidate_root)
        failure = _FailureController()
        host = _Host(current, replacement, project, failure)
        result = _coordinator(
            tmp_path,
            host,
            [candidate, replacement],
        ).apply_addon_enabled_state(
            MARS_ADDON_ID,
            enabled=enabled,
            preferences_document=preferences_document,
        )
        assert result.registry is replacement
        return replacement

    current = apply(
        initial,
        first_enabled,
        enabled=True,
        preferences_document=disabled_preferences,
        candidate_root=tmp_path / "enable-candidate",
    )
    assert all(
        isinstance(current.get_entry(type_id), PythonFunctionEntry)
        for type_id in mars_catalog.MARS_FUNCTION_TYPE_IDS
    )

    disabled_again = registry(False, canonical_root)
    current = apply(
        current,
        disabled_again,
        enabled=False,
        preferences_document=enabled_preferences,
        candidate_root=tmp_path / "disable-candidate",
    )
    assert all(
        current.spec_or_none(type_id) is None
        for type_id in mars_catalog.MARS_FUNCTION_TYPE_IDS
    )
    assert current.contract_fingerprint() == initial.contract_fingerprint()

    reenabled = registry(True, canonical_root)
    current = apply(
        current,
        reenabled,
        enabled=True,
        preferences_document=disabled_preferences,
        candidate_root=tmp_path / "reenable-candidate",
    )
    reenabled_bundle = next(
        bundle
        for bundle in current.plugin_bundle_refs()
        if bundle.owner_id == MARS_ADDON_ID
    )
    assert reenabled_bundle == first_bundle
    assert current.plugin_fingerprint() == first_enabled.plugin_fingerprint()
    assert current.contract_fingerprint() == first_enabled.contract_fingerprint()
    assert project.workspaces["ws"].nodes["node"] == original_node
    assert (
        project.project_document_revision,
        project.workspaces["ws"].mutation_revision,
        project.workspaces["ws"].dirty,
    ) == original_revisions


def test_addon_preference_failure_restores_every_published_consumer(
    tmp_path: Path,
) -> None:
    current = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, True),))
    candidate = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),))
    replacement = _registry(addon_runtime_config=((TABULAR_DATA_ADDON_ID, False),))
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    host.viewer_host_service = _ViewerHost(failure)
    observed: list[NodeRegistry] = []
    host.node_library_changed = _ObserverSignal(host, observed)
    host.selected_node_changed = _ObserverSignal(host, observed)
    host.workspace_state_changed = _ObserverSignal(host, observed)

    class FailingController:
        @staticmethod
        def document():  # noqa: ANN205
            return default_app_preferences_document()

        @staticmethod
        def persist_document(_document):  # noqa: ANN205, ANN001
            raise OSError("preference write failed")

    coordinator = _coordinator(tmp_path, host, [candidate, replacement])

    with pytest.raises(OSError, match="preference write failed"):
        coordinator.apply_addon_enabled_state(
            TABULAR_DATA_ADDON_ID,
            enabled=False,
            app_preferences_controller=FailingController(),
        )

    assert failure.calls == [
        "apply:runtime",
        "apply:graph_scene",
        "apply:host_registry",
        "apply:graph_interactions",
        "apply:serializer",
        "apply:session_store",
        "apply:viewer_catalog",
        "rollback:viewer_catalog",
        "rollback:session_store",
        "rollback:serializer",
        "rollback:graph_interactions",
        "rollback:host_registry",
        "rollback:graph_scene",
        "rollback:runtime",
    ]
    assert host.registry is current
    assert observed == []


def test_post_durable_notifications_observe_final_registry_and_warn_on_listener_failure(
    tmp_path: Path,
) -> None:
    current = _registry()
    candidate = _registry()
    replacement = _registry()
    failure = _FailureController()
    host = _Host(current, replacement, _project(), failure)
    observed: list[NodeRegistry] = []
    host.node_library_changed = _ObserverSignal(host, observed, fail=True)
    host.selected_node_changed = _ObserverSignal(host, observed)
    host.workspace_state_changed = _ObserverSignal(host, observed)
    coordinator = _coordinator(tmp_path, host, [candidate, replacement])

    result = coordinator.reload_plugins()

    assert result.applied
    assert result.warnings == ("notification_node_library_failed",)
    assert observed == [replacement, replacement, replacement]
    assert host.registry is replacement
    assert "rollback:runtime" not in failure.calls
