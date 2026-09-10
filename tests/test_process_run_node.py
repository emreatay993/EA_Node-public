from __future__ import annotations

import hashlib
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.integrations_process import (
    PROCESS_OUTPUT_MODE_STORED,
    _discard_stored_transcripts,
    execute_process_run,
)
from ea_node_editor.nodes.builtins.process_subprocess_policy import (
    ExternalSubprocessPolicy,
    normalize_args,
    normalize_env,
)
from ea_node_editor.nodes.output_artifacts import (
    allocate_managed_output,
    register_staged_path_artifact,
)
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
)
from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import DataTree, PATH_DATA_TYPE_ID


def _context(
    *,
    inputs: dict | None = None,
    properties: dict | None = None,
    emit_log=None,  # noqa: ANN001
    should_stop=None,  # noqa: ANN001
    register_cancel=None,  # noqa: ANN001
    project_path: str = "",
    runtime_snapshot: RuntimeSnapshot | None = None,
    runtime_snapshot_context: RuntimeSnapshotContext | None = None,
    path_resolver=None,  # noqa: ANN001
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="node",
        workspace_id="ws",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=emit_log or (lambda _level, _message: None),
        trigger={},
        should_stop=should_stop or (lambda: False),
        register_cancel=register_cancel or (lambda _callback: None),
        project_path=project_path,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_context=runtime_snapshot_context,
        path_resolver=path_resolver or (lambda _value: None),
        node_type_id="io.process_run",
    )


class ProcessRunNodeTests(unittest.TestCase):
    def test_process_run_declares_typed_property_defaults(self) -> None:
        spec = build_default_registry().get_spec("io.process_run")
        ports = {port.key: port for port in spec.ports}
        properties = {prop.key: prop for prop in spec.properties}

        self.assertTrue(ports["command"].uses_property_default)
        self.assertTrue(ports["args"].uses_property_default)
        self.assertEqual(properties["args"].type, "json")
        self.assertEqual(properties["args"].default, [])
        self.assertEqual(normalize_args(properties["args"].default), [])

    def test_normalize_args_and_env_accept_json_and_shell_text(self) -> None:
        self.assertEqual(normalize_args(["a", 2, True]), ["a", "2", "True"])
        self.assertEqual(normalize_args('["-c", "print(1)"]'), ["-c", "print(1)"])
        self.assertEqual(normalize_args("--flag value"), ["--flag", "value"])

        self.assertEqual(normalize_env({"A": 1, "B": True}), {"A": "1", "B": "True"})
        self.assertEqual(normalize_env('{"A": 1}'), {"A": "1"})
        self.assertEqual(normalize_env("bad json"), {})

    def test_subprocess_policy_captures_workdir_stream_and_resource_hints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = ExternalSubprocessPolicy.from_process_run_inputs(
                inputs={
                    "command": sys.executable,
                    "args": json.dumps(["-c", "print('policy')"]),
                    "stdin_text": "stdin policy",
                },
                properties={
                    "cwd": temp_dir,
                    "env": {"EA_PROCESS_POLICY": "enabled"},
                    "timeout_sec": 2.5,
                    "termination_grace_sec": 0.25,
                    "shell": False,
                    "fail_on_nonzero": False,
                    "encoding": "utf-8",
                    "output_mode": "memory",
                    "core_hint": 2,
                    "thread_hint": 4,
                    "memory_mb_hint": 512,
                },
            )

        self.assertEqual(policy.popen_args, [sys.executable, "-c", "print('policy')"])
        self.assertEqual(policy.popen_cwd, temp_dir)
        self.assertEqual(
            policy.build_environment({"PATH": "base"})["EA_PROCESS_POLICY"], "enabled"
        )
        self.assertEqual(policy.timeout_sec, 2.5)
        self.assertEqual(policy.termination_grace_sec, 0.25)
        self.assertEqual(policy.stream_policy.queue_size, 256)
        self.assertEqual(policy.stream_policy.capture_char_limit, 262_144)
        self.assertEqual(
            policy.resource_hints.to_metadata(),
            {"core_hint": 2, "thread_hint": 4, "memory_mb_hint": 512},
        )

    def test_process_run_node_success_path(self) -> None:
        plugin = execute_process_run
        result = plugin(
            _context(
                inputs={
                    "command": sys.executable,
                    "args": json.dumps(["-c", "print('hello')"]),
                },
                properties={
                    "args": "[]",
                    "output_mode": "memory",
                    "timeout_sec": 5.0,
                    "shell": False,
                    "fail_on_nonzero": True,
                    "env": {},
                    "encoding": "utf-8",
                    "cwd": "",
                },
            )
        )

        self.assertEqual(result.outputs["exit_code"], 0)
        self.assertIn("hello", result.outputs["stdout"])
        self.assertIsInstance(result.outputs["stdout"], str)
        self.assertIsInstance(result.outputs["stderr"], str)

    def test_process_run_node_applies_policy_env_and_stdin(self) -> None:
        plugin = execute_process_run
        script = (
            "import os, sys\n"
            "print(os.environ.get('EA_PROCESS_POLICY_TEST', ''))\n"
            "print(sys.stdin.read())\n"
        )
        result = plugin(
            _context(
                inputs={
                    "command": sys.executable,
                    "args": json.dumps(["-c", script]),
                    "stdin_text": "stdin-from-policy",
                },
                properties={
                    "args": "[]",
                    "output_mode": "memory",
                    "timeout_sec": 5.0,
                    "termination_grace_sec": 0.2,
                    "shell": False,
                    "fail_on_nonzero": True,
                    "env": {"EA_PROCESS_POLICY_TEST": "env-from-policy"},
                    "encoding": "utf-8",
                    "cwd": "",
                    "core_hint": 1,
                    "thread_hint": 2,
                    "memory_mb_hint": 128,
                },
            )
        )

        self.assertEqual(result.outputs["exit_code"], 0)
        self.assertIn("env-from-policy", result.outputs["stdout"])
        self.assertIn("stdin-from-policy", result.outputs["stdout"])

    def test_process_run_node_stored_mode_emits_runtime_artifact_refs_and_stages_transcripts(
        self,
    ) -> None:
        plugin = execute_process_run
        stdout_chars = 275_000
        stderr_text = "warn-line-0\nwarn-line-1\n"

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_run_outputs.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_run",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )
            registrations: list[tuple[str, int]] = []

            def register_final_transcript(ctx, **kwargs):  # noqa: ANN001
                artifact_id = kwargs["artifact_id"]
                store = kwargs["store"]
                payload_path = Path(kwargs["payload_path"])
                if not registrations:
                    self.assertEqual(
                        store.metadata.get("staged", {}),
                        {},
                    )
                self.assertIsNone(store.staged_entry(artifact_id))
                self.assertTrue(payload_path.is_file())
                registrations.append(
                    (artifact_id, payload_path.stat().st_size)
                )
                return register_staged_path_artifact(ctx, **kwargs)

            with patch(
                "ea_node_editor.nodes.builtins.integrations_process."
                "register_staged_path_artifact",
                side_effect=register_final_transcript,
            ):
                result = plugin(
                    _context(
                        inputs={
                            "command": sys.executable,
                            "args": json.dumps(
                                [
                                    "-c",
                                    (
                                        "import sys; "
                                        f"sys.stdout.write('A' * {stdout_chars}); "
                                        f"sys.stderr.write({stderr_text!r})"
                                    ),
                                ]
                            ),
                        },
                        properties={
                            "args": "[]",
                            "output_mode": PROCESS_OUTPUT_MODE_STORED,
                            "timeout_sec": 5.0,
                            "shell": False,
                            "fail_on_nonzero": True,
                            "env": {},
                            "encoding": "utf-8",
                            "cwd": "",
                        },
                        project_path=str(project_path),
                        runtime_snapshot=runtime_snapshot,
                        runtime_snapshot_context=runtime_snapshot_context,
                        path_resolver=resolver.resolve_to_path,
                    )
                )

            stdout_output = result.outputs["stdout"]
            stderr_output = result.outputs["stderr"]
            self.assertIsInstance(stdout_output, RuntimeArtifactRef)
            self.assertIsInstance(stderr_output, RuntimeArtifactRef)
            if not isinstance(stdout_output, RuntimeArtifactRef) or not isinstance(
                stderr_output, RuntimeArtifactRef
            ):
                self.fail("Stored mode did not return runtime artifact refs")

            stdout_path = resolver.resolve_to_path(stdout_output.ref)
            stderr_path = resolver.resolve_to_path(stderr_output.ref)
            self.assertIsNotNone(stdout_path)
            self.assertIsNotNone(stderr_path)
            if stdout_path is None or stderr_path is None:
                self.fail("Stored transcript refs did not resolve to paths")

            self.assertEqual(
                stdout_path.read_text(encoding="utf-8"), "A" * stdout_chars
            )
            self.assertEqual(stderr_path.read_text(encoding="utf-8"), stderr_text)
            self.assertEqual(stdout_output.scope, "staged")
            self.assertEqual(stderr_output.scope, "staged")
            self.assertEqual(stdout_output.data_type_id, PATH_DATA_TYPE_ID)
            self.assertEqual(stderr_output.data_type_id, PATH_DATA_TYPE_ID)
            self.assertEqual(stdout_output.schema_version, 1)
            self.assertEqual(stderr_output.schema_version, 1)
            self.assertEqual(stdout_output.format, "log")
            self.assertEqual(stderr_output.format, "log")
            self.assertEqual(stdout_output.metadata, {})
            self.assertEqual(stderr_output.metadata, {})
            self.assertEqual(len(registrations), 2)
            self.assertEqual(
                {artifact_id for artifact_id, _size in registrations},
                {
                    stdout_output.artifact_id,
                    stderr_output.artifact_id,
                },
            )
            registered_sizes = dict(registrations)
            self.assertEqual(
                registered_sizes[stdout_output.artifact_id],
                stdout_output.size_bytes,
            )
            self.assertEqual(
                registered_sizes[stderr_output.artifact_id],
                stderr_output.size_bytes,
            )
            self.assertEqual(
                stdout_output.sha256,
                hashlib.sha256(stdout_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                stderr_output.sha256,
                hashlib.sha256(stderr_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(runtime_snapshot.metadata, {})
            artifact_store_metadata = runtime_snapshot_context.project_metadata()[
                "artifact_store"
            ]
            self.assertIn(stdout_output.artifact_id, artifact_store_metadata["staged"])
            self.assertIn(stderr_output.artifact_id, artifact_store_metadata["staged"])
            self.assertIn("/nodes/", stdout_path.as_posix())
            # Node-first artifact store humanizes subdir separators ("_" -> " ") for readable folders.
            self.assertIn("/tmp/out/generated/process run/", stdout_path.as_posix())
            self.assertIn("/nodes/", stderr_path.as_posix())
            self.assertIn("/tmp/out/generated/process run/", stderr_path.as_posix())

    def test_process_transcript_allocation_clears_existing_descriptor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_rerun.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_rerun",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )
            ctx = _context(
                project_path=str(project_path),
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )

            original = allocate_managed_output(
                ctx,
                output_key="stdout",
                default_suffix=".log",
                managed_subdirectory="generated/process_run",
            )
            original.path.write_text("old transcript", encoding="utf-8")
            register_staged_path_artifact(
                ctx,
                store=artifact_store,
                artifact_id=original.artifact_id,
                payload_path=original.path,
                relative_path=original.relative_path,
                slot=original.slot,
                format=original.format,
                entry_metadata=original.entry_metadata,
            )
            self.assertIsNotNone(
                artifact_store.staged_entry(original.artifact_id)
            )

            replacement = allocate_managed_output(
                ctx,
                output_key="stdout",
                default_suffix=".log",
                managed_subdirectory="generated/process_run",
            )

            self.assertEqual(replacement.artifact_id, original.artifact_id)
            self.assertEqual(replacement.path, original.path)
            self.assertIsNone(
                artifact_store.staged_entry(original.artifact_id)
            )
            self.assertFalse(replacement.path.exists())

    def test_unsaved_process_transcript_replacement_preserves_staging_root_and_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_store = ProjectArtifactStore(
                project_path=None,
                metadata=None,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=None,
                artifact_store=artifact_store,
            )
            ctx = _context(
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )

            with patch(
                "ea_node_editor.nodes.output_artifacts"
                "._default_staging_workspace_root",
                return_value=Path(temp_dir),
            ):
                original = allocate_managed_output(
                    ctx,
                    output_key="stdout",
                    default_suffix=".log",
                    managed_subdirectory="generated/process_run",
                )
                original.path.write_text("old transcript", encoding="utf-8")
                register_staged_path_artifact(
                    ctx,
                    store=artifact_store,
                    artifact_id=original.artifact_id,
                    payload_path=original.path,
                    relative_path=original.relative_path,
                    slot=original.slot,
                    format=original.format,
                    entry_metadata=original.entry_metadata,
                )
                original_root = artifact_store.active_staging_root()
                self.assertIsNotNone(original_root)
                if original_root is None:
                    self.fail("Unsaved artifact store did not allocate a staging root")
                self.assertTrue(original_root.is_dir())

                replacement = allocate_managed_output(
                    ctx,
                    output_key="stdout",
                    default_suffix=".log",
                    managed_subdirectory="generated/process_run",
                )

            replacement_root = artifact_store.active_staging_root()
            self.assertEqual(replacement_root, original_root)
            self.assertTrue(original_root.is_dir())
            self.assertEqual(replacement.path, original.path)
            self.assertEqual(
                replacement.path,
                artifact_store.staged_target_path(replacement.relative_path),
            )
            self.assertIsNone(
                artifact_store.staged_entry(original.artifact_id)
            )
            self.assertFalse(original.path.exists())
            self.assertFalse(replacement.path.exists())

    def test_unsaved_process_run_replaces_transcripts_in_place_on_rerun(
        self,
    ) -> None:
        plugin = execute_process_run
        run_payloads = (
            ("first stdout payload", "first stderr payload"),
            ("replacement stdout payload", "replacement stderr payload"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_store = ProjectArtifactStore(
                project_path=None,
                metadata=None,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=None,
                artifact_store=artifact_store,
            )
            registrations: list[tuple[int, str]] = []
            stream_observations: list[int] = []
            active_run = -1

            def observe_stream(_level, message):  # noqa: ANN001
                if not str(message).startswith(("[stdout]", "[stderr]")):
                    return
                self.assertEqual(
                    artifact_store.metadata.get("staged", {}),
                    {},
                )
                root = artifact_store.active_staging_root()
                self.assertIsNotNone(root)
                if root is None:
                    self.fail("Streaming lost the unsaved staging root")
                self.assertEqual(
                    len(
                        [
                            path
                            for path in root.rglob("generated.ws.node.*.log")
                            if path.is_file()
                        ]
                    ),
                    2,
                )
                stream_observations.append(active_run)

            ctx = _context(
                properties={
                    "args": "[]",
                    "output_mode": PROCESS_OUTPUT_MODE_STORED,
                    "timeout_sec": 5.0,
                    "shell": False,
                    "fail_on_nonzero": True,
                    "env": {},
                    "encoding": "utf-8",
                    "cwd": "",
                },
                emit_log=observe_stream,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )
            paths_by_run: list[dict[str, Path]] = []
            refs_by_run: list[dict[str, RuntimeArtifactRef]] = []
            roots_by_run: list[Path] = []

            def register_final_transcript(ctx, **kwargs):  # noqa: ANN001
                artifact_id = kwargs["artifact_id"]
                store = kwargs["store"]
                current_registrations = [
                    registered_id
                    for run_index, registered_id in registrations
                    if run_index == active_run
                ]
                if not current_registrations:
                    self.assertEqual(store.metadata.get("staged", {}), {})
                self.assertIsNone(store.staged_entry(artifact_id))
                registrations.append((active_run, artifact_id))
                return register_staged_path_artifact(ctx, **kwargs)

            with (
                patch(
                    "ea_node_editor.nodes.output_artifacts"
                    "._default_staging_workspace_root",
                    return_value=Path(temp_dir),
                ),
                patch(
                    "ea_node_editor.nodes.builtins.integrations_process."
                    "register_staged_path_artifact",
                    side_effect=register_final_transcript,
                ),
            ):
                for active_run, (stdout_text, stderr_text) in enumerate(
                    run_payloads
                ):
                    ctx.inputs = {
                        "command": sys.executable,
                        "args": json.dumps(
                            [
                                "-c",
                                (
                                    "import sys; "
                                    f"sys.stdout.write({stdout_text!r}); "
                                    f"sys.stderr.write({stderr_text!r})"
                                ),
                            ]
                        ),
                    }
                    result = plugin(ctx)
                    refs = {
                        "stdout": result.outputs["stdout"],
                        "stderr": result.outputs["stderr"],
                    }
                    self.assertTrue(
                        all(
                            isinstance(value, RuntimeArtifactRef)
                            for value in refs.values()
                        )
                    )
                    typed_refs = {
                        key: value
                        for key, value in refs.items()
                        if isinstance(value, RuntimeArtifactRef)
                    }
                    paths = {
                        key: resolver.resolve_to_path(value.ref)
                        for key, value in typed_refs.items()
                    }
                    self.assertTrue(all(path is not None for path in paths.values()))
                    paths_by_run.append(
                        {
                            key: path
                            for key, path in paths.items()
                            if path is not None
                        }
                    )
                    refs_by_run.append(typed_refs)
                    expected_text = {
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                    }
                    for key, path in paths_by_run[-1].items():
                        payload = path.read_bytes()
                        runtime_ref = typed_refs[key]
                        entry = artifact_store.staged_entry(
                            runtime_ref.artifact_id
                        )
                        self.assertIsNotNone(entry)
                        if entry is None:
                            self.fail(
                                f"Missing run {active_run} {key} descriptor"
                            )
                        descriptor = entry.extra["runtime_artifact"]
                        self.assertEqual(payload, expected_text[key].encode())
                        self.assertEqual(runtime_ref.size_bytes, len(payload))
                        self.assertEqual(
                            runtime_ref.sha256,
                            hashlib.sha256(payload).hexdigest(),
                        )
                        self.assertEqual(
                            descriptor["size_bytes"],
                            len(payload),
                        )
                        self.assertEqual(
                            descriptor["sha256"],
                            runtime_ref.sha256,
                        )
                    root = artifact_store.active_staging_root()
                    self.assertIsNotNone(root)
                    if root is None:
                        self.fail("Unsaved artifact store lost its staging root")
                    roots_by_run.append(root)

            self.assertEqual(roots_by_run[1], roots_by_run[0])
            self.assertTrue(roots_by_run[0].is_dir())
            self.assertEqual(paths_by_run[1], paths_by_run[0])
            self.assertEqual(set(stream_observations), {0, 1})
            self.assertEqual(len(registrations), 4)
            for run_index, refs in enumerate(refs_by_run):
                self.assertEqual(
                    [
                        artifact_id
                        for registered_run, artifact_id in registrations
                        if registered_run == run_index
                    ],
                    [refs["stdout"].artifact_id, refs["stderr"].artifact_id],
                )

            final_refs = refs_by_run[1]
            final_paths = paths_by_run[1]
            expected_final_text = {
                "stdout": run_payloads[1][0],
                "stderr": run_payloads[1][1],
            }
            for key, path in final_paths.items():
                payload = path.read_bytes()
                runtime_ref = final_refs[key]
                entry = artifact_store.staged_entry(runtime_ref.artifact_id)
                self.assertIsNotNone(entry)
                if entry is None:
                    self.fail(f"Missing final {key} transcript descriptor")
                descriptor = entry.extra["runtime_artifact"]
                self.assertEqual(payload, expected_final_text[key].encode())
                self.assertEqual(runtime_ref.size_bytes, len(payload))
                self.assertEqual(
                    runtime_ref.sha256,
                    hashlib.sha256(payload).hexdigest(),
                )
                self.assertEqual(descriptor["size_bytes"], len(payload))
                self.assertEqual(descriptor["sha256"], runtime_ref.sha256)
                self.assertNotIn(run_payloads[0][0].encode(), payload)
                self.assertNotIn(run_payloads[0][1].encode(), payload)

            expected_artifact_ids = {
                final_refs["stdout"].artifact_id,
                final_refs["stderr"].artifact_id,
            }
            self.assertEqual(
                set(artifact_store.metadata.get("staged", {})),
                expected_artifact_ids,
            )
            self.assertEqual(
                {
                    path
                    for path in roots_by_run[1].rglob("*")
                    if path.is_file()
                },
                set(final_paths.values()),
            )

    def test_process_run_second_transcript_open_failure_cleans_setup(
        self,
    ) -> None:
        plugin = execute_process_run

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_open_failure.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_open_failure",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )
            original_open = Path.open
            real_popen = subprocess.Popen
            transcript_open_count = 0
            started_processes: list[subprocess.Popen] = []

            def tracked_popen(*args, **kwargs):  # noqa: ANN002, ANN003
                process = real_popen(*args, **kwargs)
                started_processes.append(process)
                return process

            def fail_second_transcript_open(
                path: Path,
                *args,
                **kwargs,
            ):  # noqa: ANN002, ANN003
                nonlocal transcript_open_count
                mode = str(args[0] if args else kwargs.get("mode", "r"))
                if mode == "w" and path.name.startswith("generated.ws.node."):
                    transcript_open_count += 1
                    if transcript_open_count == 2:
                        raise OSError("forced transcript open failure")
                return original_open(path, *args, **kwargs)

            with (
                patch(
                    "ea_node_editor.nodes.builtins.integrations_process."
                    "subprocess.Popen",
                    side_effect=tracked_popen,
                ),
                patch.object(Path, "open", new=fail_second_transcript_open),
                self.assertRaisesRegex(
                    OSError,
                    "forced transcript open failure",
                ) as caught,
            ):
                plugin(
                    _context(
                        inputs={
                            "command": sys.executable,
                            "args": json.dumps(
                                [
                                    "-c",
                                    "import time; time.sleep(10)",
                                ]
                            ),
                        },
                        properties={
                            "args": "[]",
                            "output_mode": PROCESS_OUTPUT_MODE_STORED,
                            "timeout_sec": 20.0,
                            "shell": False,
                            "fail_on_nonzero": True,
                            "env": {},
                            "encoding": "utf-8",
                            "cwd": "",
                        },
                        project_path=str(project_path),
                        runtime_snapshot=runtime_snapshot,
                        runtime_snapshot_context=runtime_snapshot_context,
                        path_resolver=resolver.resolve_to_path,
                    )
                )

            self.assertEqual(transcript_open_count, 2)
            self.assertEqual(len(started_processes), 1)
            self.assertIsNotNone(started_processes[0].poll())
            self.assertEqual(
                artifact_store.metadata.get("staged", {}),
                {},
            )
            self.assertFalse(
                list(
                    project_path.with_name(
                        "process_open_failure.data"
                    ).rglob("generated.ws.node.*.log")
                )
            )
            self.assertNotIn(str(project_path), str(caught.exception))

    def test_process_cleanup_preserves_primary_failure_when_discard_is_rejected(
        self,
    ) -> None:
        plugin = execute_process_run

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_cleanup_failure.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_cleanup_failure",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )
            base_context = _context(
                project_path=str(project_path),
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )
            unrelated = allocate_managed_output(
                base_context,
                output_key="unrelated",
                default_suffix=".log",
                managed_subdirectory="generated/process_run",
            )
            unrelated.path.write_text("keep me", encoding="utf-8")
            register_staged_path_artifact(
                base_context,
                store=artifact_store,
                artifact_id=unrelated.artifact_id,
                payload_path=unrelated.path,
                relative_path=unrelated.relative_path,
                slot=unrelated.slot,
                format=unrelated.format,
                entry_metadata=unrelated.entry_metadata,
            )
            staging_root = artifact_store.active_staging_root()
            self.assertIsNotNone(staging_root)
            if staging_root is None:
                self.fail("Process cleanup test did not allocate a staging root")
            sentinel = staging_root / "sentinel.txt"
            sentinel.write_text("sentinel", encoding="utf-8")

            cleanup_only = allocate_managed_output(
                base_context,
                output_key="cleanup_only",
                default_suffix=".log",
                managed_subdirectory="generated/process_run",
            )
            cleanup_only.path.write_text("cleanup only", encoding="utf-8")
            real_discard = artifact_store.discard_staged_entries
            cleanup_only_marker = ValueError(
                "staged artifact discard target is unsafe"
            )

            def reject_cleanup_only(artifact_ids):
                ids = tuple(artifact_ids)
                if ids == (cleanup_only.artifact_id,):
                    raise cleanup_only_marker
                return real_discard(ids)

            with (
                patch.object(
                    artifact_store,
                    "discard_staged_entries",
                    side_effect=reject_cleanup_only,
                ),
                self.assertRaises(ValueError) as cleanup_only_caught,
            ):
                _discard_stored_transcripts(
                    base_context,
                    (cleanup_only,),
                )

            self.assertIs(cleanup_only_caught.exception, cleanup_only_marker)
            self.assertFalse(cleanup_only.path.exists())

            path_rejected = allocate_managed_output(
                base_context,
                output_key="path_rejected",
                default_suffix=".log",
                managed_subdirectory="generated/process_run",
            )
            path_rejected.path.write_text(
                "validator rejection",
                encoding="utf-8",
            )
            path_cleanup_marker = ValueError(
                "staged artifact discard target is unsafe"
            )
            real_discard_paths = artifact_store.discard_staged_paths
            with (
                patch.object(
                    artifact_store,
                    "discard_staged_paths",
                    side_effect=path_cleanup_marker,
                ) as mocked_discard_paths,
                patch.object(Path, "unlink") as raw_unlink,
                self.assertRaises(ValueError) as path_cleanup_caught,
            ):
                _discard_stored_transcripts(
                    base_context,
                    (path_rejected,),
                )

            self.assertIs(
                path_cleanup_caught.exception,
                path_cleanup_marker,
            )
            mocked_discard_paths.assert_called_once_with(
                (path_rejected.relative_path,)
            )
            raw_unlink.assert_not_called()
            self.assertTrue(path_rejected.path.exists())
            real_discard_paths((path_rejected.relative_path,))
            self.assertFalse(path_rejected.path.exists())

            primary_marker = RuntimeError("primary process failure")
            cleanup_marker = ValueError(
                "staged artifact discard target is unsafe"
            )
            process_targets = []
            cleanup_rejections = 0
            started_processes: list[subprocess.Popen] = []
            real_popen = subprocess.Popen

            def capture_target(ctx, **kwargs):  # noqa: ANN001, ANN003
                target = allocate_managed_output(ctx, **kwargs)
                process_targets.append(target)
                return target

            def reject_process_cleanup(artifact_ids):
                nonlocal cleanup_rejections
                ids = tuple(artifact_ids)
                if len(ids) == 2:
                    cleanup_rejections += 1
                    raise cleanup_marker
                return real_discard(ids)

            def fail_process_run() -> bool:
                raise primary_marker

            def tracked_popen(*args, **kwargs):  # noqa: ANN002, ANN003
                process = real_popen(*args, **kwargs)
                started_processes.append(process)
                return process

            with (
                patch(
                    "ea_node_editor.nodes.builtins.integrations_process."
                    "allocate_managed_output",
                    side_effect=capture_target,
                ),
                patch.object(
                    artifact_store,
                    "discard_staged_entries",
                    side_effect=reject_process_cleanup,
                ),
                patch(
                    "ea_node_editor.nodes.builtins.integrations_process."
                    "subprocess.Popen",
                    side_effect=tracked_popen,
                ),
                self.assertRaises(RuntimeError) as primary_caught,
            ):
                plugin(
                    _context(
                        inputs={
                            "command": sys.executable,
                            "args": json.dumps(
                                ["-c", "import time; time.sleep(10)"]
                            ),
                        },
                        properties={
                            "args": "[]",
                            "output_mode": PROCESS_OUTPUT_MODE_STORED,
                            "timeout_sec": 20.0,
                            "shell": False,
                            "fail_on_nonzero": True,
                            "env": {},
                            "encoding": "utf-8",
                            "cwd": "",
                        },
                        should_stop=fail_process_run,
                        project_path=str(project_path),
                        runtime_snapshot=runtime_snapshot,
                        runtime_snapshot_context=runtime_snapshot_context,
                        path_resolver=resolver.resolve_to_path,
                    )
                )

            self.assertIs(primary_caught.exception, primary_marker)
            self.assertEqual(cleanup_rejections, 1)
            self.assertEqual(len(process_targets), 2)
            self.assertTrue(all(not target.path.exists() for target in process_targets))
            self.assertTrue(
                all(
                    artifact_store.staged_entry(target.artifact_id) is None
                    for target in process_targets
                )
            )
            self.assertEqual(len(started_processes), 1)
            self.assertIsNotNone(started_processes[0].poll())
            self.assertIsNotNone(
                artifact_store.staged_entry(unrelated.artifact_id)
            )
            self.assertEqual(unrelated.path.read_text(encoding="utf-8"), "keep me")
            self.assertEqual(artifact_store.active_staging_root(), staging_root)
            self.assertTrue(staging_root.is_dir())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel")

    def test_process_run_node_stored_mode_nonzero_discards_staged_artifact_state(
        self,
    ) -> None:
        plugin = execute_process_run

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_run_failure.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_run_failure",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )

            with self.assertRaises(RuntimeError) as error:
                plugin(
                    _context(
                        inputs={
                            "command": sys.executable,
                            "args": json.dumps(
                                [
                                    "-c",
                                    (
                                        "import sys; "
                                        "sys.stdout.write('stored-failure-stdout\\n'); "
                                        "sys.stderr.write('stored failure line\\n'); "
                                        "sys.exit(7)"
                                    ),
                                ]
                            ),
                        },
                        properties={
                            "args": "[]",
                            "output_mode": PROCESS_OUTPUT_MODE_STORED,
                            "timeout_sec": 5.0,
                            "shell": False,
                            "fail_on_nonzero": True,
                            "env": {},
                            "encoding": "utf-8",
                            "cwd": "",
                        },
                        project_path=str(project_path),
                        runtime_snapshot=runtime_snapshot,
                        runtime_snapshot_context=runtime_snapshot_context,
                        path_resolver=resolver.resolve_to_path,
                    )
                )

            self.assertIn("stored_transcripts_discarded=True", str(error.exception))
            self.assertIn("stored failure line", str(error.exception))

            self.assertEqual(runtime_snapshot.metadata, {})
            artifact_store_metadata = runtime_snapshot_context.project_metadata().get(
                "artifact_store", {}
            )
            staged_entries = artifact_store_metadata.get("staged", {})
            self.assertNotIn("generated.ws.node.stdout", staged_entries)
            self.assertNotIn("generated.ws.node.stderr", staged_entries)
            self.assertIsNone(
                resolver.resolve_to_path("temp://generated.ws.node.stdout")
            )
            self.assertIsNone(
                resolver.resolve_to_path("temp://generated.ws.node.stderr")
            )

            sidecar_root = project_path.with_name("process_run_failure.data")
            self.assertFalse(
                list(
                    (sidecar_root / "nodes").glob(
                        "*/tmp/out/generated/process_run/generated.ws.node.stdout.log"
                    )
                )
            )
            self.assertFalse(
                list(
                    (sidecar_root / "nodes").glob(
                        "*/tmp/out/generated/process_run/generated.ws.node.stderr.log"
                    )
                )
            )

    def test_process_run_node_stored_mode_cancellation_discards_targets(
        self,
    ) -> None:
        plugin = execute_process_run

        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "process_run_cancel.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_process_run_cancel",
                metadata={},
            )
            artifact_store = ProjectArtifactStore.from_project_metadata(
                project_path=project_path,
                project_metadata=runtime_snapshot.metadata,
            )
            runtime_snapshot_context = RuntimeSnapshotContext.from_snapshot(
                runtime_snapshot,
                project_path=str(project_path),
                artifact_store=artifact_store,
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                artifact_store=artifact_store,
            )

            with self.assertRaisesRegex(
                InterruptedError,
                "run_stop_requested",
            ) as caught:
                plugin(
                    _context(
                        inputs={
                            "command": sys.executable,
                            "args": json.dumps(
                                [
                                    "-c",
                                    "import time; time.sleep(10)",
                                ]
                            ),
                        },
                        properties={
                            "args": "[]",
                            "output_mode": PROCESS_OUTPUT_MODE_STORED,
                            "timeout_sec": 20.0,
                            "shell": False,
                            "fail_on_nonzero": True,
                            "env": {},
                            "encoding": "utf-8",
                            "cwd": "",
                        },
                        should_stop=lambda: True,
                        project_path=str(project_path),
                        runtime_snapshot=runtime_snapshot,
                        runtime_snapshot_context=runtime_snapshot_context,
                        path_resolver=resolver.resolve_to_path,
                    )
                )

            self.assertNotIn(str(project_path), str(caught.exception))
            self.assertEqual(
                artifact_store.metadata.get("staged", {}),
                {},
            )
            sidecar_root = project_path.with_name("process_run_cancel.data")
            self.assertFalse(
                list(sidecar_root.rglob("generated.ws.node.*.log"))
            )

    def test_process_run_node_nonzero_timeout_and_invalid_cwd(self) -> None:
        plugin = execute_process_run

        with self.assertRaises(RuntimeError):
            plugin(
                _context(
                    inputs={
                        "command": sys.executable,
                        "args": json.dumps(["-c", "import sys; sys.exit(3)"]),
                    },
                    properties={
                        "args": "[]",
                        "timeout_sec": 5.0,
                        "shell": False,
                        "fail_on_nonzero": True,
                        "env": {},
                        "encoding": "utf-8",
                        "cwd": "",
                    },
                )
            )

        with self.assertRaises(TimeoutError):
            plugin(
                _context(
                    inputs={
                        "command": sys.executable,
                        "args": json.dumps(["-c", "import time; time.sleep(2)"]),
                    },
                    properties={
                        "args": "[]",
                        "timeout_sec": 0.3,
                        "shell": False,
                        "fail_on_nonzero": True,
                        "env": {},
                        "encoding": "utf-8",
                        "cwd": "",
                    },
                )
            )

        with self.assertRaises(ValueError) as cwd_error:
            plugin(
                _context(
                    inputs={
                        "command": sys.executable,
                    },
                    properties={
                        "cwd": "/path/that/does/not/exist",
                        "timeout_sec": 1.0,
                    },
                )
            )
        self.assertIn("working directory", str(cwd_error.exception).lower())

    def test_process_run_node_streams_stdout_and_stderr_logs(self) -> None:
        plugin = execute_process_run
        stream_logs: list[tuple[str, str]] = []
        script = (
            "import sys, time\n"
            "print('tick_0', flush=True)\n"
            "time.sleep(0.15)\n"
            "print('warn_0', file=sys.stderr, flush=True)\n"
            "time.sleep(0.15)\n"
            "print('tick_1', flush=True)\n"
        )
        result = plugin(
            _context(
                inputs={
                    "command": sys.executable,
                    "args": json.dumps(["-c", script]),
                },
                properties={
                    "args": "[]",
                    "timeout_sec": 5.0,
                    "shell": False,
                    "fail_on_nonzero": True,
                    "env": {},
                    "encoding": "utf-8",
                    "cwd": "",
                },
                emit_log=lambda level, message: stream_logs.append(
                    (str(level), str(message))
                ),
            )
        )

        self.assertEqual(result.outputs["exit_code"], 0)
        self.assertIn("tick_0", result.outputs["stdout"])
        self.assertIn("tick_1", result.outputs["stdout"])
        self.assertIn("warn_0", result.outputs["stderr"])
        messages = [message for _level, message in stream_logs]
        self.assertTrue(any("[stdout] tick_0" in message for message in messages))
        self.assertTrue(any("[stdout] tick_1" in message for message in messages))
        self.assertTrue(any("[stderr] warn_0" in message for message in messages))

    def test_run_workflow_process_run_stored_stdout_resolves_into_file_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "workflow_process_run_outputs.cxproj"
            model = GraphModel()
            workspace = model.active_workspace
            process_node = model.add_node(
                workspace.workspace_id,
                "io.process_run",
                "Process",
                120.0,
                0.0,
                properties={
                    "command": sys.executable,
                    "args": ["-c", "print('stored_output_from_artifact')"],
                    "output_mode": PROCESS_OUTPUT_MODE_STORED,
                    "timeout_sec": 5.0,
                    "shell": False,
                    "fail_on_nonzero": True,
                    "env": {},
                    "encoding": "utf-8",
                    "cwd": "",
                },
            )
            file_read_node = model.add_node(
                workspace.workspace_id,
                "io.file_read",
                "Read Output",
                260.0,
                0.0,
                properties={"path": ""},
            )
            model.add_edge(
                workspace.workspace_id,
                process_node.node_id,
                "stdout",
                file_read_node.node_id,
                "path",
            )

            registry = build_default_registry()
            runtime_snapshot = build_runtime_snapshot(
                model.project,
                workspace_id=workspace.workspace_id,
                registry=registry,
            )
            initial_runtime_metadata = json.loads(
                json.dumps(runtime_snapshot.to_document()["metadata"])
            )
            event_queue: queue.Queue = queue.Queue()
            run_workflow(
                coerce_start_run_command(
                    {
                        "run_id": "run_process_stored_output",
                        "project_path": str(project_path),
                        "workspace_id": workspace.workspace_id,
                        "runtime_snapshot": runtime_snapshot,
                        "trigger": {},
                        "plugin_bundles": registry.plugin_bundle_refs(),
                        "plugin_fingerprint": registry.plugin_fingerprint(),
                        "registry_contract_fingerprint": registry.contract_fingerprint(),
                        "addon_runtime_config": registry.addon_runtime_config(),
                    },
                    catalog=registry.data_types,
                ),
                event_queue,
            )

            events = []
            while not event_queue.empty():
                events.append(event_queue.get())

            process_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == process_node.node_id
            )
            stdout_tree = deserialize_runtime_value(
                process_completed["outputs"]["stdout"]["value"],
                catalog=registry.data_types,
            )
            self.assertIsInstance(stdout_tree, DataTree)
            stdout_payload = stdout_tree[(0,)][0]
            self.assertEqual(stdout_payload.scope, "staged")
            self.assertTrue(str(stdout_payload.ref).startswith("temp://"))
            self.assertGreater(stdout_payload.size_bytes, 0)
            self.assertEqual(len(stdout_payload.sha256), 64)
            self.assertEqual(
                stdout_payload.provenance,
                "corex.node:io.process_run",
            )
            self.assertNotIn(
                "stored_output_from_artifact", json.dumps(process_completed)
            )
            self.assertEqual(
                runtime_snapshot.to_document()["metadata"], initial_runtime_metadata
            )

            file_read_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == file_read_node.node_id
            )
            text_tree = deserialize_runtime_value(
                file_read_completed["outputs"]["text"]["value"],
                catalog=registry.data_types,
            )
            self.assertEqual(text_tree[(0,)][0], "stored_output_from_artifact\n")

    def test_stop_run_cancels_active_process_node(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        process_node = model.add_node(
            workspace.workspace_id,
            "io.process_run",
            "Process",
            120.0,
            0.0,
            properties={
                "command": sys.executable,
                "args": ["-c", "import time; time.sleep(10)"],
                "timeout_sec": 20.0,
                "shell": False,
                "fail_on_nonzero": True,
                "env": {},
                "encoding": "utf-8",
                "cwd": "",
            },
        )
        registry = build_default_registry()
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace.workspace_id,
            registry=registry,
        )
        event_queue: queue.Queue = queue.Queue()
        command_queue: queue.Queue = queue.Queue()
        run_id = "run_stop_process"

        def _runner() -> None:
            run_workflow(
                coerce_start_run_command(
                    {
                        "run_id": run_id,
                        "workspace_id": workspace.workspace_id,
                        "runtime_snapshot": runtime_snapshot,
                        "trigger": {},
                        "plugin_bundles": registry.plugin_bundle_refs(),
                        "plugin_fingerprint": registry.plugin_fingerprint(),
                        "registry_contract_fingerprint": registry.contract_fingerprint(),
                        "addon_runtime_config": registry.addon_runtime_config(),
                    },
                    catalog=registry.data_types,
                ),
                event_queue,
                command_queue=command_queue,
            )

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()

        seen_node_started = False
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not seen_node_started:
            try:
                event = event_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if (
                event.get("type") == "node_started"
                and event.get("node_id") == process_node.node_id
            ):
                seen_node_started = True
                break
        self.assertTrue(seen_node_started)

        command_queue.put({"type": "stop_run", "run_id": run_id})
        thread.join(timeout=6.0)
        self.assertFalse(
            thread.is_alive(), "run_workflow did not stop after stop_run command"
        )

        events = []
        while not event_queue.empty():
            events.append(event_queue.get())
        event_types = [event.get("type") for event in events]
        self.assertIn("run_stopped", event_types)
        self.assertNotIn("run_failed", event_types)


if __name__ == "__main__":
    unittest.main()
