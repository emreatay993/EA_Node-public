# Purpose: Shared deterministic fixtures for split execution-client owner suites.
# Map: subsystems/execution.md
# Tests: tests/test_client_common.py, tests/test_process_client.py, tests/test_external_python_client.py, tests/test_trusted_client.py, tests/test_backend_client.py
from __future__ import annotations

import hashlib
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from ea_node_editor.execution.backend_client import ExecutionBackendClient
from ea_node_editor.execution.backends import (
    EXTERNAL_SUBPROCESS_BACKEND,
    ExecutionBackendSelection,
)
from ea_node_editor.execution.external_python_client import (
    ExternalPythonExecutionClient,
)
from ea_node_editor.execution.managed_runtime import (
    ADDON_RUNTIME_PYTHON_ENV,
    resolve_addon_runtime_paths,
)
from ea_node_editor.execution.process_client import ProcessExecutionClient
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import (
    build_builtin_registry,
    build_default_registry,
)
from ea_node_editor.runtime_contracts import (
    DataTree,
    DataTypeCatalog,
    DataTypeFamilySpec,
    DataTypeSpec,
)
from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value


def _decorated_python_script(body: str) -> str:
    indented = "\n".join(f"    {line}" for line in body.splitlines())
    return (
        "@corex.node\n"
        '@corex.output("result", value_type=corex.Any)\n'
        "def run(ctx):\n"
        f"{indented}\n"
        '    return {"result": locals().get("result")}\n'
    )


def _revision_catalog(implementation_version: str) -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(
            DataTypeFamilySpec("tests.catalog", "Catalog", "data.tests", "tests"),
        ),
        types=(
            DataTypeSpec(
                "tests.CatalogValue",
                "Catalog Value",
                "tests.catalog",
                lambda value: isinstance(value, str),
                implementation_version=implementation_version,
            ),
        ),
        owner_id="tests.catalog",
        owner_version=implementation_version,
    )
    catalog.freeze()
    return catalog


def _catalog_contract_fingerprint(catalog: DataTypeCatalog) -> str:
    return hashlib.sha256(f"test:{catalog.fingerprint()}".encode()).hexdigest()


def _default_registry_agreement() -> dict[str, object]:
    registry = build_default_registry()
    return {
        "data_types": registry.data_types,
        "plugin_bundles": registry.plugin_bundle_refs(),
        "plugin_fingerprint": registry.plugin_fingerprint(),
        "registry_contract_fingerprint": registry.contract_fingerprint(),
        "addon_runtime_config": registry.addon_runtime_config(),
    }


def _trusted_registry_agreement() -> dict[str, object]:
    registry = build_builtin_registry()
    return {
        "data_types": registry.data_types,
        "plugin_bundles": registry.plugin_bundle_refs(),
        "plugin_fingerprint": registry.plugin_fingerprint(),
        "registry_contract_fingerprint": registry.contract_fingerprint(),
        "addon_runtime_config": registry.addon_runtime_config(),
    }


def _external_process_mock() -> Mock:
    process = Mock()
    process.returncode = None
    process.poll.side_effect = lambda: process.returncode
    process.stdout.readline.return_value = ""
    process.stderr.readline.return_value = ""

    def wait(*, timeout=None):  # noqa: ANN001, ARG001
        process.returncode = 0
        return 0

    process.wait.side_effect = wait
    process.terminate.side_effect = lambda: setattr(process, "returncode", -15)
    process.kill.side_effect = lambda: setattr(process, "returncode", -9)
    return process


def _simple_runtime_snapshot():  # noqa: ANN201
    registry = build_default_registry()
    model = GraphModel()
    workspace = model.active_workspace
    model.add_node(workspace.workspace_id, "core.logger", "Logger", 0, 0)
    return (
        registry,
        workspace.workspace_id,
        build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        ),
    )


def _external_selection(python_executable: str) -> ExecutionBackendSelection:
    return ExecutionBackendSelection(
        backend_id=EXTERNAL_SUBPROCESS_BACKEND,
        isolation="external_subprocess",
        external_subprocess=True,
        python_executable=python_executable,
    )


def _seed_external_generation(
    client: ExternalPythonExecutionClient,
    process: Mock,
    *,
    python_executable: str,
) -> None:
    client._process = process  # noqa: SLF001
    client._python_executable = python_executable  # noqa: SLF001
    client._catalog_generation_token = 1  # noqa: SLF001
    client._physical_generation_token = 1  # noqa: SLF001
    client._accepted_physical_generation_token = 1  # noqa: SLF001


class _RoutingClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, tuple, dict]] = []
        self._state_lock = threading.Lock()
        self._viewer_request_lock = threading.Lock()
        self._catalog_generation_token = 0
        self._workspace_viewer_epochs: dict[str, int] = {}
        self._node_viewer_epochs: dict[tuple[str, str], int] = {}

    def _record(self, method: str, args: tuple, kwargs: dict) -> str:
        self.calls.append((method, args, dict(kwargs)))
        return f"{self.name}_{method}"

    def open_viewer_session(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return self._record("open", args, kwargs)

    def update_viewer_session(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return self._record("update", args, kwargs)

    def close_viewer_session(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return self._record("close", args, kwargs)

    def materialize_viewer_data(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return self._record("materialize", args, kwargs)

    def query_viewer_session(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return self._record("query", args, kwargs)

    def shutdown(self) -> None:
        return None


class ProcessClientTestHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ProcessExecutionClient()
        self.registry = build_default_registry()
        self.data_types = self.registry.data_types
        # Viewer-only tests emulate a catalog retained from their owning run.
        self.client._data_types = self.data_types  # noqa: SLF001
        self._events: list[dict] = []
        self._events_lock = threading.Lock()
        self.client.subscribe(self._on_event)

    def tearDown(self) -> None:
        self.client.shutdown()

    def _wait_for_event(self, predicate, timeout: float = 6.0) -> dict | None:  # noqa: ANN001
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._events_lock:
                for event in self._events:
                    if predicate(event):
                        return event
            time.sleep(0.05)
        return None

    def _on_event(self, event: dict) -> None:
        with self._events_lock:
            self._events.append(dict(event))

    @staticmethod
    def _build_runtime_snapshot(
        *,
        with_sleep_script: bool = False,
        workflow_python_path: str = "",
    ):
        model = GraphModel()
        workspace = model.active_workspace
        if with_sleep_script:
            script = model.add_node(
                workspace.workspace_id,
                "core.python_script",
                "Script",
                100,
                0,
                properties={
                    "script": _decorated_python_script(
                        "import time\ntime.sleep(2)\nresult = 1"
                    )
                },
            )
        else:
            logger = model.add_node(
                workspace.workspace_id,
                "core.logger",
                "Logger",
                100,
                0,
                properties={"message": "ok"},
            )

        if workflow_python_path:
            model.project.metadata["workflow_settings"] = {
                "environment": {"python_path": workflow_python_path}
            }
        registry = build_default_registry()
        return workspace.workspace_id, build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )

    @staticmethod
    def _build_script_runtime_snapshot(
        script_source: str,
        *,
        timeout_sec: float = 0.0,
        workflow_python_path: str = "",
    ):
        model = GraphModel()
        workspace = model.active_workspace
        script = model.add_node(
            workspace.workspace_id,
            "core.python_script",
            "Script",
            100,
            0,
            properties={
                "script": _decorated_python_script(script_source),
                "timeout_sec": timeout_sec,
            },
        )
        if workflow_python_path:
            model.project.metadata["workflow_settings"] = {
                "environment": {"python_path": workflow_python_path}
            }
        registry = build_default_registry()
        return (
            workspace.workspace_id,
            script.node_id,
            build_runtime_snapshot(
                model.project,
                workspace_id=workspace.workspace_id,
                registry=registry,
            ),
        )

    def _assert_external_python_executable(
        self,
        *,
        workflow_python_path: str = "",
        execution_backend: dict | None = None,
    ) -> None:
        backend_client = ExecutionBackendClient()
        events: list[dict] = []
        events_lock = threading.Lock()

        def _on_event(event: dict) -> None:
            with events_lock:
                events.append(dict(event))

        def _wait_for_event(predicate, timeout: float = 12.0) -> dict | None:  # noqa: ANN001
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                with events_lock:
                    for event in events:
                        if predicate(event):
                            return event
                time.sleep(0.05)
            return None

        backend_client.subscribe(_on_event)
        workspace_id, script_id, runtime_snapshot = self._build_script_runtime_snapshot(
            (
                "import os, sys\n"
                "result = {"
                "'python': sys.executable, "
                f"'addon_python': os.environ.get('{ADDON_RUNTIME_PYTHON_ENV}', '')"
                "}"
            ),
            workflow_python_path=workflow_python_path,
        )
        try:
            run_id = backend_client.start_run(
                project_path="",
                workspace_id=workspace_id,
                trigger={"kind": "manual", "runtime_snapshot": runtime_snapshot},
                execution_backend=execution_backend,
                **_default_registry_agreement(),
            )
            self.assertTrue(run_id, events)
            completed = _wait_for_event(
                lambda event: (
                    event.get("type") == "run_completed"
                    and event.get("run_id") == run_id
                ),
                timeout=12.0,
            )
            self.assertIsNotNone(completed)
            backend_log = _wait_for_event(
                lambda event: (
                    event.get("type") == "log"
                    and event.get("run_id") == run_id
                    and EXTERNAL_SUBPROCESS_BACKEND in str(event.get("message", ""))
                ),
                timeout=3.0,
            )
            self.assertIsNotNone(backend_log)
            script_completed = _wait_for_event(
                lambda event: (
                    event.get("type") == "node_settled"
                    and event.get("run_id") == run_id
                    and event.get("node_id") == script_id
                ),
                timeout=3.0,
            )
            self.assertIsNotNone(script_completed)
            if script_completed is None:
                self.fail("script node did not complete")
            result_tree = deserialize_runtime_value(
                script_completed["outputs"]["result"]["value"]
            )
            self.assertIsInstance(result_tree, DataTree)
            result_payload = result_tree[(0,)][0]
            self.assertEqual(
                Path(result_payload["python"]).resolve(),
                Path(sys.executable).resolve(),
            )
            self.assertEqual(
                Path(result_payload["addon_python"]).resolve(),
                resolve_addon_runtime_paths().python_executable,
            )
            self.assertIsNotNone(backend_client._external_python_client._process)  # noqa: SLF001
        finally:
            backend_client.shutdown()
