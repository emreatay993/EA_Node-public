from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.addons.catalog import (
    addon_registration_is_live_enabled,
    registered_addon_registration_by_id,
)
from ea_node_editor.addons.mars.catalog import (
    MARS_PLUGIN_BACKEND,
    get_mars_addon_availability,
)
from ea_node_editor.addons.mars.function_nodes import SOURCE as MARS_FUNCTION_SOURCE
from ea_node_editor.addons.mars.metadata import (
    MARS_ADDON_MANIFEST,
    MARS_DISTRIBUTION,
    MARS_RUNTIME_BACKEND_ID,
)
from ea_node_editor.addons.mars.nodes import (
    MARS_BATCH_SOLVE_NODE_TYPE_ID,
    MARS_RUN_JOB_NODE_TYPE_ID,
    MARS_TIME_HISTORY_NODE_TYPE_ID,
    execute_mars_batch_solve,
    execute_mars_run_job,
    execute_mars_time_history,
)
from ea_node_editor.addons.mars.runtime import (
    MarsBatchOutcome,
    _artifact_id,
    _build_mars_command,
    _mars_subprocess_environment,
    managed_mars_batch_executable,
    publish_mars_artifacts,
    run_mars_batch,
)
from ea_node_editor.app_preferences import default_app_preferences_document
from ea_node_editor.execution.protocol_codec import (
    coerce_start_run_command,
)
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotContext,
    build_runtime_snapshot,
)
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.output_artifacts import register_staged_path_artifact
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.plugin_contracts import PluginAvailability
from ea_node_editor.addons.registry_contributions import register_plugin_backends
from ea_node_editor.nodes.readiness import evaluate_node_readiness
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    PATH_DATA_TYPE_ID,
    RuntimeArtifactRef,
)
from ea_node_editor.ui_qml.node_title_icon_sources import (
    title_icon_presentation_for_node_payload,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


_MARS_SPECS = {
    declaration.spec.type_id: declaration.spec
    for declaration in discover_plugin_declarations(
        MARS_FUNCTION_SOURCE,
        filename="ea_node_editor/addons/mars/function_nodes.py",
        allow_reserved_ids=True,
        owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    )
}


def _mars_properties(type_id: str) -> dict[str, object]:
    return {
        property_spec.key: property_spec.default
        for property_spec in _MARS_SPECS[type_id].properties
    }


def _generated_mars_registry(generation_root: Path) -> NodeRegistry:
    registry = NodeRegistry(
        addon_runtime_config=((MARS_ADDON_MANIFEST.addon_id, True),)
    )
    backend = replace(
        MARS_PLUGIN_BACKEND,
        get_availability=lambda: PluginAvailability.available(),
    )
    loaded = register_plugin_backends(
        (backend,),
        registry,
        "tests/test_mars_nodes.py",
        generation_root=generation_root,
    )
    if tuple(loaded) != backend.function_type_ids:
        raise AssertionError("MARS function registry generation failed")
    registry.freeze()
    return registry


def _context(
    *,
    properties: dict | None = None,
    inputs: dict | None = None,
    project_path: Path | None = None,
    should_stop=None,  # noqa: ANN001
) -> tuple[ExecutionContext, ProjectArtifactStore | None]:
    store = None
    snapshot = None
    snapshot_context = None
    resolver = None
    if project_path is not None:
        snapshot = RuntimeSnapshot(
            schema_version=1, project_id="mars-tests", metadata={}
        )
        store = ProjectArtifactStore.from_project_metadata(
            project_path=project_path,
            project_metadata=snapshot.metadata,
        )
        snapshot_context = RuntimeSnapshotContext.from_snapshot(
            snapshot,
            project_path=str(project_path),
            artifact_store=store,
        )
        resolver = ProjectArtifactResolver(
            project_path=project_path, artifact_store=store
        )
    ctx = ExecutionContext(
        run_id="run",
        node_id="mars-node",
        workspace_id="workspace",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
        should_stop=should_stop or (lambda: False),
        register_cancel=lambda _callback: None,
        project_path=str(project_path or ""),
        workspace_name="MARS Tests",
        runtime_snapshot=snapshot,
        runtime_snapshot_context=snapshot_context,
        path_resolver=resolver.resolve_to_path
        if resolver is not None
        else (lambda _value: None),
        node_title="MARS Batch Solve",
        node_type_id=MARS_BATCH_SOLVE_NODE_TYPE_ID,
        node_type_display_name="MARS Batch Solve",
    )
    return ctx, store


def _fake_success_command(
    _executable: Path, job_path: Path, output_directory: Path
) -> list[str]:
    script = r"""
import json
import sys
from pathlib import Path

job_path = Path(sys.argv[1])
output_directory = Path(sys.argv[2])
job = json.loads(job_path.read_text(encoding="utf-8"))
output_directory.mkdir(parents=True, exist_ok=True)
if job["mode"] == "time_history":
    name = f"time_history_node_{job['node_id']}_{job['outputs'][0]}.csv"
    primary = {"history_csv": str((output_directory / name).resolve())}
else:
    name = "max_von_mises_stress.csv"
    primary = {"von_mises": str((output_directory / name).resolve())}
(output_directory / name).write_text("Node Number,Value\n1,10\n", encoding="utf-8")
result = {
    "status": "completed",
    "output_directory": str(output_directory.resolve()),
    "files": [str((output_directory / name).resolve())],
    "primary_files": primary,
    "warnings": ["synthetic warning"],
    "elapsed_seconds": 0.01,
}
(output_directory / "mars_result.json").write_text(json.dumps(result), encoding="utf-8")
print(json.dumps({"record": "event", "event": {"kind": "progress", "percent": 50}}), flush=True)
print(json.dumps({"record": "result", "result": result}), flush=True)
"""
    return [sys.executable, "-c", script, str(job_path), str(output_directory)]


class MarsAddOnContractTests(unittest.TestCase):
    def test_static_function_specs_match_pre_cutover_golden(self) -> None:
        rows = load_current_repo_owned_catalog()
        expected = {
            row["spec"]["type_id"]: row["spec"]
            for row in rows
            if row["spec"]["type_id"] in _MARS_SPECS
        }
        actual = {
            type_id: json.loads(json.dumps(asdict(spec)))
            for type_id, spec in _MARS_SPECS.items()
        }

        self.assertEqual(actual, expected)

    def test_fresh_batch_solve_settles_empty_without_constructing_plugin(self) -> None:
        generation = tempfile.TemporaryDirectory(prefix="corex-mars-test-")
        self.addCleanup(generation.cleanup)
        registry = _generated_mars_registry(Path(generation.name))
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            MARS_BATCH_SOLVE_NODE_TYPE_ID,
            "MARS Batch Solve",
            0,
            0,
        )
        snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        event_queue: queue.Queue = queue.Queue()

        with patch.object(registry, "create", wraps=registry.create) as create:
            with (
                patch(
                    "ea_node_editor.nodes.bootstrap.build_default_registry",
                    return_value=registry,
                ),
                patch(
                    "ea_node_editor.execution.registry_agreement.plugin_generations_dir",
                    return_value=Path(generation.name),
                ),
            ):
                run_workflow(
                    coerce_start_run_command(
                        {
                            "run_id": "mars-readiness",
                            "workspace_id": workspace.workspace_id,
                            "runtime_snapshot": snapshot,
                            "trigger": {},
                            "plugin_bundles": registry.plugin_bundle_refs(),
                            "plugin_fingerprint": registry.plugin_fingerprint(),
                            "registry_contract_fingerprint": (
                                registry.contract_fingerprint()
                            ),
                            "addon_runtime_config": registry.addon_runtime_config(),
                        },
                        catalog=registry.data_types,
                    ),
                    event_queue,
                )

        create.assert_not_called()
        events = []
        while not event_queue.empty():
            events.append(event_queue.get())
        settled = next(
            event
            for event in events
            if event.get("type") == "node_settled"
            and event.get("node_id") == node.node_id
        )
        self.assertEqual(settled["status"], "empty")
        self.assertIn("Modal Coordinates", " ".join(settled["warnings"]))
        self.assertTrue(
            any(
                event.get("type") == "log" and event.get("level") == "warning"
                for event in events
            )
        )
        self.assertFalse(
            any(
                event.get("type") == "log" and event.get("level") == "error"
                for event in events
            )
        )
        self.assertFalse(any(event.get("type") == "run_failed" for event in events))

    def test_guided_nodes_declare_blank_modal_coordinates_as_not_ready(self) -> None:
        for type_id in (
            MARS_BATCH_SOLVE_NODE_TYPE_ID,
            MARS_TIME_HISTORY_NODE_TYPE_ID,
        ):
            spec = _MARS_SPECS[type_id]
            properties = {
                property_spec.key: property_spec.default
                for property_spec in spec.properties
            }
            issues = evaluate_node_readiness(
                spec,
                port_has_value={},
                overridden_port_keys=(),
                properties=properties,
            )

            with self.subTest(node_type_id=spec.type_id):
                self.assertEqual(
                    [issue.target_keys for issue in issues],
                    [("modal_coordinates",)],
                )
                self.assertEqual(
                    [issue.target_labels for issue in issues],
                    [("Modal Coordinates",)],
                )
                input_ports = [
                    port
                    for port in spec.ports
                    if port.direction == "in" and port.kind == "data"
                ]
                self.assertTrue(all(port.uses_property_default for port in input_ports))

    def test_batch_damage_requires_each_fatigue_property(self) -> None:
        spec = _MARS_SPECS[MARS_BATCH_SOLVE_NODE_TYPE_ID]
        properties = {
            property_spec.key: property_spec.default
            for property_spec in spec.properties
        }
        properties.update(
            modal_coordinates="response.mcf",
            output_damage=True,
        )

        issues = evaluate_node_readiness(
            spec,
            port_has_value={},
            overridden_port_keys=(),
            properties=properties,
        )

        self.assertEqual(
            [issue.target_keys for issue in issues],
            [("fatigue_A",), ("fatigue_m",)],
        )

    def test_run_job_uses_property_fallback_until_a_wire_overrides_it(self) -> None:
        spec = _MARS_SPECS[MARS_RUN_JOB_NODE_TYPE_ID]
        properties = {
            property_spec.key: property_spec.default
            for property_spec in spec.properties
        }
        properties["job"] = "job.json"

        self.assertEqual(
            evaluate_node_readiness(
                spec,
                port_has_value={},
                overridden_port_keys=(),
                properties=properties,
            ),
            (),
        )
        issues = evaluate_node_readiness(
            spec,
            port_has_value={},
            overridden_port_keys=("job",),
            properties=properties,
        )
        self.assertEqual([issue.target_keys for issue in issues], [("job",)])

    def test_central_registration_is_opt_in_and_managed(self) -> None:
        registration = registered_addon_registration_by_id("mars.corex")
        self.assertIsNotNone(registration)
        if registration is None:
            self.fail("missing MARS add-on registration")
        self.assertEqual(registration.managed_runtime_package_ids, ("mars",))
        self.assertFalse(registration.default_enabled)
        self.assertFalse(
            addon_registration_is_live_enabled(
                registration,
                preferences_document=default_app_preferences_document(),
            )
        )

    def test_manifest_backend_and_three_function_entries_are_self_contained(self) -> None:
        self.assertEqual(MARS_ADDON_MANIFEST.addon_id, "mars.corex")
        self.assertEqual(MARS_PLUGIN_BACKEND.plugin_id, MARS_ADDON_MANIFEST.addon_id)
        self.assertEqual(MARS_ADDON_MANIFEST.dependencies, (MARS_DISTRIBUTION,))
        self.assertEqual(
            MARS_ADDON_MANIFEST.runtime_backends[0].backend_id,
            MARS_RUNTIME_BACKEND_ID,
        )
        self.assertEqual(MARS_PLUGIN_BACKEND.load_descriptors(), ())
        self.assertEqual(
            MARS_PLUGIN_BACKEND.function_type_ids,
            (
                MARS_BATCH_SOLVE_NODE_TYPE_ID,
                MARS_TIME_HISTORY_NODE_TYPE_ID,
                MARS_RUN_JOB_NODE_TYPE_ID,
            ),
        )
        load_sources = MARS_PLUGIN_BACKEND.load_function_sources
        self.assertIsNotNone(load_sources)
        if load_sources is None:
            self.fail("missing MARS function-source loader")
        self.assertEqual(
            tuple(path for path, _source in load_sources()),
            ("mars_nodes.py",),
        )

        generation = tempfile.TemporaryDirectory(prefix="corex-mars-test-")
        self.addCleanup(generation.cleanup)
        registry = _generated_mars_registry(Path(generation.name))
        entries = tuple(
            registry.get_entry(type_id)
            for type_id in MARS_PLUGIN_BACKEND.function_type_ids
        )
        self.assertEqual(
            {entry.spec.type_id for entry in entries},
            {
                MARS_BATCH_SOLVE_NODE_TYPE_ID,
                MARS_TIME_HISTORY_NODE_TYPE_ID,
                MARS_RUN_JOB_NODE_TYPE_ID,
            },
        )
        self.assertTrue(all(isinstance(entry, PythonFunctionEntry) for entry in entries))
        self.assertTrue(
            all(
                registry.descriptor_or_none(entry.spec.type_id) is None
                for entry in entries
            )
        )
        provenance = MARS_PLUGIN_BACKEND.provenance
        self.assertIsNotNone(provenance)
        if provenance is None:
            self.fail("missing MARS package provenance")
        self.assertEqual(provenance.kind, "package")
        expected_icon = (
            Path(__file__).resolve().parents[1]
            / "ea_node_editor"
            / "addons"
            / "mars"
            / "icons"
            / "mars_icon_64.png"
        ).resolve()
        for entry in entries:
            self.assertEqual(entry.spec.icon, "icons/mars_icon_64.png")
            presentation = title_icon_presentation_for_node_payload(
                entry.spec,
                provenance=provenance,
            )
            self.assertEqual(presentation.source, expected_icon.as_uri())
            self.assertFalse(presentation.theme_aware)
            ports = {port.key: port for port in entry.spec.ports}
            self.assertEqual(ports["manifest"].data_type, PATH_DATA_TYPE_ID)
            self.assertEqual(ports["files"].data_type, GRAPH_DATA_TYPE_ID)
            self.assertNotIn("exec_out", ports)
            self.assertNotIn("on_failed", ports)
            self.assertTrue(all(port.kind == "data" for port in ports.values()))
            self.assertTrue(
                all(
                    port.data_access == "tree"
                    for port in ports.values()
                    if port.direction == "in"
                )
            )
        batch_spec = _MARS_SPECS[MARS_BATCH_SOLVE_NODE_TYPE_ID]
        run_job_spec = _MARS_SPECS[MARS_RUN_JOB_NODE_TYPE_ID]
        primary_ports = {
            "von_mises",
            "max_principal",
            "min_principal",
            "deformation",
            "velocity",
            "acceleration",
            "force",
            "moment",
            "damage",
        }
        self.assertTrue(primary_ports.issubset({port.key for port in batch_spec.ports}))
        self.assertTrue(
            primary_ports.issubset({port.key for port in run_job_spec.ports})
        )
        self.assertTrue(
            next(port for port in run_job_spec.ports if port.key == "job").required
        )
        self.assertTrue(
            {
                "Inputs",
                "Results",
                "Modes",
                "RST",
                "Fatigue",
                "Plasticity",
                "Runtime",
            }.issubset({property_spec.group for property_spec in batch_spec.properties})
        )

    def test_availability_requires_managed_distribution_and_fixed_executable(
        self,
    ) -> None:
        expected = Path("C:/COREX/runtime/.venv/Scripts/MARSBatch.exe")
        runtime_paths = object()
        with (
            patch(
                "ea_node_editor.execution.managed_runtime.resolve_addon_runtime_paths",
                return_value=runtime_paths,
            ),
            patch(
                "ea_node_editor.execution.managed_runtime.resolve_managed_console_script",
                return_value=expected,
            ) as resolve_script,
        ):
            self.assertEqual(managed_mars_batch_executable(), expected.resolve())
        resolve_script.assert_called_once_with("MARSBatch", paths=runtime_paths)
        with (
            patch(
                "ea_node_editor.addons.mars.catalog._managed_mars_version",
                return_value="1.0.0",
            ),
            patch(
                "ea_node_editor.addons.mars.catalog.managed_mars_batch_executable",
                return_value=Path(sys.executable),
            ),
        ):
            self.assertTrue(get_mars_addon_availability().is_available)
        source_python = Path("C:/COREX/venv/Scripts/python.exe")
        with (
            patch(
                "ea_node_editor.execution.managed_runtime.resolve_addon_runtime_paths",
                return_value=SimpleNamespace(python_executable=source_python),
            ),
            patch(
                "ea_node_editor.addons.mars.catalog._managed_mars_version",
                return_value="",
            ),
            patch(
                "ea_node_editor.addons.mars.catalog.managed_mars_batch_executable",
                return_value=expected,
            ),
        ):
            availability = get_mars_addon_availability()
        self.assertFalse(availability.is_available)
        self.assertEqual(
            availability.summary,
            f"MARS is not installed in COREX's active Python environment: {source_python}.",
        )

    def test_command_uses_json_protocol_and_scratch_override(self) -> None:
        command = _build_mars_command(
            Path("C:/managed/MARSBatch.exe"),
            Path("C:/jobs/job.json"),
            Path("C:/scratch/results"),
        )
        self.assertEqual(command[1:3], ["run", str(Path("C:/jobs/job.json").resolve())])
        self.assertIn("json", command)
        self.assertEqual(command[-2], "--output-directory")
        self.assertEqual(command[-1], str(Path("C:/scratch/results").resolve()))


class MarsRuntimeTests(unittest.TestCase):
    def test_subprocess_environment_ignores_foreign_python_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {"PYTHONPATH": "foreign", "PythonHome": "foreign", "MARS_KEEP": "yes"},
        ):
            environment = _mars_subprocess_environment()

        self.assertFalse(any(key.upper().startswith("PYTHON") for key in environment))
        self.assertEqual(environment["MARS_KEEP"], "yes")

    def test_every_stdout_line_is_validated(self) -> None:
        script = "print('{not-json', flush=True)"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_path = root / "job.json"
            job_path.write_text("{}", encoding="utf-8")
            ctx, _store = _context()
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    return_value=[sys.executable, "-c", script],
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "invalid JSONL"):
                    run_mars_batch(
                        ctx,
                        job_path=job_path,
                        output_directory=root / "results",
                        timeout_seconds=5.0,
                        termination_grace_seconds=0.2,
                    )

    def test_record_after_terminal_result_is_rejected(self) -> None:
        result_line = json.dumps(
            {"record": "result", "result": {"status": "completed", "files": []}}
        )
        event_line = json.dumps(
            {"record": "event", "event": {"kind": "progress", "percent": 99}}
        )
        script = (
            f"print({result_line!r}, flush=True); print({event_line!r}, flush=True)"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_path = root / "job.json"
            job_path.write_text("{}", encoding="utf-8")
            ctx, _store = _context()
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    return_value=[sys.executable, "-c", script],
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "after its terminal result"):
                    run_mars_batch(
                        ctx,
                        job_path=job_path,
                        output_directory=root / "results",
                        timeout_seconds=5.0,
                        termination_grace_seconds=0.2,
                    )

    def test_timeout_terminates_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            job_path = root / "job.json"
            job_path.write_text("{}", encoding="utf-8")
            ctx, _store = _context()
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    return_value=[sys.executable, "-c", "import time; time.sleep(5)"],
                ),
            ):
                with self.assertRaisesRegex(TimeoutError, "timed out"):
                    run_mars_batch(
                        ctx,
                        job_path=job_path,
                        output_directory=root / "results",
                        timeout_seconds=0.05,
                        termination_grace_seconds=0.1,
                    )


class MarsNodeExecutionTests(unittest.TestCase):
    def test_publication_failure_removes_attempted_seeded_artifacts_only(
        self,
    ) -> None:
        marker = RuntimeError("second MARS registration failed")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "scratch-results"
            output_root.mkdir()
            source = output_root / "result.csv"
            source.write_text("value\n1\n", encoding="utf-8")
            store = ProjectArtifactStore(project_path=None, metadata=None)
            staging_root = store.ensure_staging_root(
                temporary_root_parent=root / "session-staging"
            )
            hint = store.staging_root_hint
            snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="mars-unsaved",
                metadata={},
            )
            ctx, _ = _context()
            ctx.runtime_snapshot = snapshot
            ctx.runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                snapshot,
                artifact_store=store,
            )
            outcome = MarsBatchOutcome(
                terminal_result={"status": "completed"},
                files=(source,),
                primary_files={"von_mises": source},
                warnings=(),
            )
            seeded = publish_mars_artifacts(
                ctx,
                output_directory=output_root,
                outcome=outcome,
                include_results_directory=False,
            )
            seeded_refs = (seeded.manifest, *seeded.files.values())
            seeded_relative_paths = [
                store.metadata["staged"][ref.artifact_id]["relative_path"]
                for ref in seeded_refs
            ]
            seeded_paths = {
                ref.artifact_id: store.resolve_staged_path(ref) for ref in seeded_refs
            }
            seeded_file_ref = seeded.files["result.csv"]

            unrelated_paths = store.node_artifact_paths(
                artifact_id="unrelated",
                workspace_id="other-workspace",
                workspace_name="Other",
                node_id="other-node",
                node_title="Other",
                node_type="Other",
                io_dir="out",
                filename="unrelated.txt",
            )
            unrelated_path = store.staged_target_path(
                unrelated_paths.staged_relative_path
            )
            unrelated_path.parent.mkdir(parents=True, exist_ok=True)
            unrelated_path.write_text("registered keep", encoding="utf-8")
            store.register_staged_entry(
                "unrelated",
                relative_path=unrelated_paths.staged_relative_path,
                extra=unrelated_paths.metadata,
            )
            sentinel = staging_root / "unregistered.txt"
            sentinel.write_text("unregistered keep", encoding="utf-8")
            source.write_text("value\nupdated\n", encoding="utf-8")
            registration_count = 0

            def fail_second_registration(ctx, **kwargs):  # noqa: ANN001
                nonlocal registration_count
                registration_count += 1
                self.assertIsNone(store.staged_entry(kwargs["artifact_id"]))
                if registration_count == 2:
                    self.assertEqual(
                        kwargs["artifact_id"],
                        seeded_file_ref.artifact_id,
                    )
                    self.assertEqual(
                        Path(kwargs["payload_path"]).read_text(encoding="utf-8"),
                        "value\nupdated\n",
                    )
                    raise marker
                return register_staged_path_artifact(ctx, **kwargs)

            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.register_staged_path_artifact",
                    side_effect=fail_second_registration,
                ),
                patch.object(
                    store,
                    "discard_staged_entries",
                    wraps=store.discard_staged_entries,
                ) as discard_entries,
                patch.object(
                    store,
                    "discard_staged_paths",
                    wraps=store.discard_staged_paths,
                ) as discard_paths,
            ):
                with self.assertRaises(RuntimeError) as raised:
                    publish_mars_artifacts(
                        ctx,
                        output_directory=output_root,
                        outcome=outcome,
                        include_results_directory=False,
                    )

            self.assertIs(raised.exception, marker)
            self.assertEqual(registration_count, 2)
            self.assertEqual(
                discard_entries.call_args_list,
                [
                    call((seeded_refs[0].artifact_id,)),
                    call((seeded_refs[1].artifact_id,)),
                    call(tuple(ref.artifact_id for ref in seeded_refs)),
                ],
            )
            self.assertEqual(
                discard_paths.call_args_list,
                [
                    call((seeded_relative_paths[0],)),
                    call((seeded_relative_paths[1],)),
                    call(tuple(seeded_relative_paths)),
                ],
            )
            self.assertEqual(set(store.metadata["staged"]), {"unrelated"})
            for artifact_id, path in seeded_paths.items():
                self.assertIsNone(store.staged_entry(artifact_id))
                self.assertIsNotNone(path)
                if path is None:
                    self.fail("expected seeded staged path")
                self.assertFalse(path.exists())
            self.assertEqual(
                unrelated_path.read_text(encoding="utf-8"),
                "registered keep",
            )
            self.assertEqual(store.active_staging_root(), staging_root)
            self.assertIs(store.staging_root_hint, hint)
            self.assertTrue(staging_root.exists())
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "unregistered keep",
            )
            self.assertEqual(
                {
                    path
                    for path in staging_root.rglob("*")
                    if path.is_file() or path.is_symlink()
                },
                {unrelated_path, sentinel},
            )

    def test_publication_rejects_no_id_intermediate_reparse_before_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "scratch-results"
            output_root.mkdir()
            source = output_root / "result.csv"
            source.write_text("value\n1\n", encoding="utf-8")
            store = ProjectArtifactStore(project_path=None, metadata=None)
            staging_root = store.ensure_staging_root(
                temporary_root_parent=root / "session-staging"
            )
            snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="mars-unsafe-cleanup",
                metadata={},
            )
            ctx, _ = _context()
            ctx.runtime_snapshot = snapshot
            ctx.runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                snapshot,
                artifact_store=store,
            )
            outcome = MarsBatchOutcome(
                terminal_result={"status": "completed"},
                files=(source,),
                primary_files={"von_mises": source},
                warnings=(),
            )
            bundle_id = _artifact_id(ctx, "results")
            bundle_paths = store.node_artifact_paths(
                artifact_id=bundle_id,
                workspace_id=ctx.workspace_id,
                workspace_name=ctx.workspace_name,
                node_id=ctx.node_id,
                node_title=ctx.node_title,
                node_type=ctx.node_type_display_name or ctx.node_type_id or "MARS",
                io_dir="out",
                subdirectory="mars",
                filename="mars_results",
            )
            bundle_path = store.staged_target_path(bundle_paths.staged_relative_path)
            reparse_parent = bundle_path.parent
            bundle_path.mkdir(parents=True)
            target_sentinel = bundle_path / "keep.txt"
            target_sentinel.write_text("target keep", encoding="utf-8")
            outside_sentinel = root / "outside.txt"
            outside_sentinel.write_text("outside keep", encoding="utf-8")
            original_state = store.state
            hint = store.staging_root_hint
            reparse_key = os.path.normcase(os.path.abspath(reparse_parent))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == reparse_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=getattr(
                            result,
                            "st_file_attributes",
                            0,
                        )
                        | 0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                patch.object(
                    store,
                    "ensure_staging_root",
                    return_value=staging_root,
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime.default_staging_workspace_root",
                    return_value=root / "unused-staging-parent",
                ),
                patch.object(
                    store,
                    "discard_staged_entries",
                    wraps=store.discard_staged_entries,
                ) as discard_entries,
                patch.object(
                    store,
                    "discard_staged_paths",
                    wraps=store.discard_staged_paths,
                ) as discard_paths,
                patch.object(
                    store,
                    "staged_target_path",
                    side_effect=AssertionError("resolved before validation"),
                ) as resolve_target,
                patch(
                    "ea_node_editor.persistence.artifact_store._delete_path",
                    side_effect=AssertionError("deleted before validation"),
                ) as delete_path,
                patch.object(
                    Path,
                    "mkdir",
                    side_effect=AssertionError("created before validation"),
                ) as mkdir,
                patch.object(
                    Path,
                    "write_text",
                    side_effect=AssertionError("wrote before validation"),
                ) as write_text,
                patch(
                    "ea_node_editor.addons.mars.runtime.shutil.copy2",
                    side_effect=AssertionError("copied before validation"),
                ) as copy_file,
                patch(
                    "ea_node_editor.addons.mars.runtime.register_staged_path_artifact",
                    side_effect=AssertionError("registered before validation"),
                ) as register,
            ):
                with self.assertRaises(ValueError) as raised:
                    publish_mars_artifacts(
                        ctx,
                        output_directory=output_root,
                        outcome=outcome,
                        include_results_directory=True,
                    )

            self.assertEqual(
                str(raised.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(staging_root), str(raised.exception))
            self.assertEqual(
                discard_entries.call_args_list,
                [call((bundle_id,)), call((bundle_id,))],
            )
            self.assertEqual(
                discard_paths.call_args_list,
                [
                    call((bundle_paths.staged_relative_path,)),
                    call((bundle_paths.staged_relative_path,)),
                ],
            )
            resolve_target.assert_not_called()
            delete_path.assert_not_called()
            mkdir.assert_not_called()
            write_text.assert_not_called()
            copy_file.assert_not_called()
            register.assert_not_called()
            self.assertIs(store.state, original_state)
            self.assertEqual(store.active_staging_root(), staging_root)
            self.assertIs(store.staging_root_hint, hint)
            self.assertIsNone(store.staged_entry(bundle_id))
            self.assertEqual(
                target_sentinel.read_text(encoding="utf-8"),
                "target keep",
            )
            self.assertEqual(
                outside_sentinel.read_text(encoding="utf-8"),
                "outside keep",
            )

    def test_guided_batch_publishes_primary_bundle_manifest_and_files(self) -> None:
        properties = _mars_properties(MARS_BATCH_SOLVE_NODE_TYPE_ID)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            modal_coordinates = root / "response.mcf"
            modal_stress = root / "modal_stress.csv"
            modal_coordinates.write_text("synthetic", encoding="utf-8")
            modal_stress.write_text("synthetic", encoding="utf-8")
            properties.update(
                {
                    "modal_coordinates": str(modal_coordinates),
                    "modal_stress": str(modal_stress),
                    "timeout_seconds": 5.0,
                    "termination_grace_seconds": 0.2,
                }
            )
            ctx, store = _context(
                properties=properties,
                project_path=root / "mars-node.cxproj",
            )
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    side_effect=_fake_success_command,
                ),
            ):
                result = execute_mars_batch_solve(ctx)

            self.assertEqual(result.warnings, ("synthetic warning",))
            for key in ("manifest", "von_mises"):
                self.assertIsInstance(result.outputs[key], RuntimeArtifactRef)
            self.assertIsInstance(result.outputs["files"], dict)
            self.assertEqual(
                result.outputs["von_mises"],
                result.outputs["files"]["max_von_mises_stress.csv"],
            )
            artifact_refs = [
                result.outputs["manifest"],
                *result.outputs["files"].values(),
            ]
            results_directory = result.outputs.get("results_directory")
            if isinstance(results_directory, RuntimeArtifactRef):
                artifact_refs.append(results_directory)
                results_entry = store.metadata["staged"][results_directory.artifact_id]
                self.assertNotIn("format", results_entry)
                self.assertNotIn("files", results_entry)
                self.assertEqual(results_entry["file_count"], 2)
            for artifact_ref in artifact_refs:
                self.assertEqual(artifact_ref.data_type_id, PATH_DATA_TYPE_ID)
                self.assertEqual(artifact_ref.schema_version, 1)
                self.assertTrue(artifact_ref.format)
                self.assertGreaterEqual(artifact_ref.size_bytes, 0)
                self.assertEqual(len(artifact_ref.sha256), 64)
                self.assertTrue(artifact_ref.provenance)
                self.assertNotIn("format", artifact_ref.metadata)
                self.assertNotIn("absolute_path", artifact_ref.metadata)
                self.assertNotIn("relative_path", artifact_ref.metadata)
                artifact_path = store.resolve_staged_path(artifact_ref)
                self.assertIsNotNone(artifact_path)
                if artifact_path is None:
                    self.fail("expected staged artifact path")
                entry = store.staged_entry(artifact_ref.artifact_id)
                trusted_root = store.active_staging_root()
                self.assertIsNotNone(entry)
                self.assertIsNotNone(trusted_root)
                if entry is None or entry.relative_path is None or trusted_root is None:
                    self.fail("expected store-owned staged content target")
                self.assertEqual(
                    artifact_content_integrity(
                        trusted_root,
                        entry.relative_path,
                    ),
                    (artifact_ref.size_bytes, artifact_ref.sha256),
                )
                self.assertEqual(
                    store.metadata["staged"][artifact_ref.artifact_id][
                        "runtime_artifact"
                    ],
                    artifact_ref.to_descriptor(),
                )
            self.assertEqual(result.outputs["manifest"].format, "json")
            self.assertEqual(result.outputs["von_mises"].format, "csv")
            self.assertIsNotNone(store)
            if store is None:
                self.fail("expected artifact store")
            manifest_path = store.resolve_staged_path(result.outputs["manifest"])
            primary_path = store.resolve_staged_path(result.outputs["von_mises"])
            self.assertTrue(manifest_path is not None and manifest_path.is_file())
            self.assertTrue(primary_path is not None and primary_path.is_file())
            portable_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(portable_manifest["output_directory"], ".")
            self.assertEqual(portable_manifest["files"], ["max_von_mises_stress.csv"])

    def test_guided_time_history_publishes_history_csv(self) -> None:
        properties = _mars_properties(MARS_TIME_HISTORY_NODE_TYPE_ID)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            modal_coordinates = root / "response.pch"
            modal_stress = root / "modal_stress.csv"
            modal_coordinates.write_text("synthetic", encoding="utf-8")
            modal_stress.write_text("synthetic", encoding="utf-8")
            properties.update(
                {
                    "modal_coordinates": str(modal_coordinates),
                    "modal_stress": str(modal_stress),
                    "node_id": 42,
                    "output": "max_principal",
                    "timeout_seconds": 5.0,
                    "termination_grace_seconds": 0.2,
                }
            )
            ctx, store = _context(
                properties=properties,
                project_path=root / "mars-history.cxproj",
            )
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    side_effect=_fake_success_command,
                ),
            ):
                result = execute_mars_time_history(ctx)

            self.assertIsInstance(result.outputs["history_csv"], RuntimeArtifactRef)
            self.assertNotIn("results_directory", result.outputs)
            self.assertEqual(
                result.outputs["history_csv"],
                result.outputs["files"]["time_history_node_42_max_principal.csv"],
            )
            self.assertIsNotNone(store)
            if store is None:
                self.fail("expected artifact store")
            history_path = store.resolve_staged_path(result.outputs["history_csv"])
            self.assertTrue(history_path is not None and history_path.is_file())

    def test_run_job_forces_scratch_output_and_leaves_declared_directory_untouched(
        self,
    ) -> None:
        properties = _mars_properties(MARS_RUN_JOB_NODE_TYPE_ID)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            declared_output = root / "must-not-be-used"
            job_path = root / "external_job.json"
            job_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mode": "batch",
                        "inputs": {},
                        "outputs": ["von_mises"],
                        "settings": {},
                        "output_directory": str(declared_output),
                    }
                ),
                encoding="utf-8",
            )
            properties.update(
                {
                    "job": str(job_path),
                    "timeout_seconds": 5.0,
                    "termination_grace_seconds": 0.2,
                }
            )
            ctx, store = _context(
                properties=properties,
                project_path=root / "mars-run-job.cxproj",
            )
            with (
                patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=Path(sys.executable),
                ),
                patch(
                    "ea_node_editor.addons.mars.runtime._build_mars_command",
                    side_effect=_fake_success_command,
                ),
            ):
                result = execute_mars_run_job(ctx)

            self.assertFalse(declared_output.exists())
            self.assertIsInstance(result.outputs["von_mises"], RuntimeArtifactRef)
            self.assertIsNotNone(store)


@unittest.skipUnless(
    os.environ.get("MARS_TEST_BATCH_EXE"),
    "Set MARS_TEST_BATCH_EXE to a built or installed MARSBatch executable.",
)
class MarsRealProcessIntegrationTests(unittest.TestCase):
    def test_guided_batch_and_time_history_run_real_marsbatch(self) -> None:
        executable = Path(os.environ["MARS_TEST_BATCH_EXE"]).resolve()
        self.assertTrue(executable.is_file())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            modal_coordinates = root / "response.mcf"
            modal_deformation = root / "deformation.csv"
            modal_coordinates.write_text(
                "Modal Coordinates File - Synthetic\n"
                "Number of Modes:   2\n"
                "  Mode: 1 2\n"
                "      Time          Coordinates...\n"
                "  0.0 0.0 1.0\n"
                "  0.1 1.0 0.0\n"
                "  0.2 2.0 -1.0\n"
                "  0.3 3.0 0.0\n",
                encoding="utf-8",
            )
            modal_deformation.write_text(
                "NodeID,X,Y,Z,ux_Mode1,uy_Mode1,uz_Mode1,ux_Mode2,uy_Mode2,uz_Mode2\n"
                "7,1,2,3,1,0,0,0.5,0,0\n",
                encoding="utf-8",
            )

            for execute, type_id, updates, expected_port in (
                (
                    execute_mars_batch_solve,
                    MARS_BATCH_SOLVE_NODE_TYPE_ID,
                    {"output_von_mises": False, "output_deformation": True},
                    "deformation",
                ),
                (
                    execute_mars_time_history,
                    MARS_TIME_HISTORY_NODE_TYPE_ID,
                    {"node_id": 7, "output": "deformation"},
                    "history_csv",
                ),
            ):
                properties = _mars_properties(type_id)
                properties.update(
                    modal_coordinates=str(modal_coordinates),
                    modal_deformation=str(modal_deformation),
                    timeout_seconds=60.0,
                    termination_grace_seconds=1.0,
                )
                properties.update(updates)
                ctx, store = _context(
                    properties=properties,
                    project_path=root / f"{type_id}.cxproj",
                )
                with patch(
                    "ea_node_editor.addons.mars.runtime.managed_mars_batch_executable",
                    return_value=executable,
                ):
                    result = execute(ctx)
                self.assertIsInstance(result.outputs[expected_port], RuntimeArtifactRef)
                self.assertIsNotNone(store)


if __name__ == "__main__":
    unittest.main()
