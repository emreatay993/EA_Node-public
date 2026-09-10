from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
    StartRunCommand,
)
from ea_node_editor.execution.protocol_codec import (
    command_to_dict,
    coerce_start_run_command,
    dict_to_command,
    dict_to_event,
    event_to_dict,
)
from ea_node_editor.runtime_contracts.settled_results import SettledPortResult
from ea_node_editor.execution.runtime_snapshot import (
    RuntimeSnapshot,
    RuntimeSnapshotContext,
)
from ea_node_editor.execution.runtime_dto import RuntimeWorkspace
from ea_node_editor.runtime_contracts.value_codec import (
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.nodes.builtins.integrations_file_io import (
    execute_file_read,
    execute_file_write,
)
from ea_node_editor.nodes.output_artifacts import (
    register_staged_artifact,
    register_staged_path_artifact,
    write_managed_output,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.value_refs import RuntimeArtifactRef
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.runtime_contracts import DataTree, PATH_DATA_TYPE_ID
from ea_node_editor.execution.worker_runtime import RuntimeArtifactService
from ea_node_editor.execution.worker_runner import NodeExecutor


_FIXTURE_REGISTRY = NodeRegistry()
_FIXTURE_REGISTRY.freeze()
_DATA_TYPES = _FIXTURE_REGISTRY.data_types
_PATH_TYPE = _DATA_TYPES.require(PATH_DATA_TYPE_ID)
_FIXTURE_SIZE_BYTES = 0
_FIXTURE_SHA256 = hashlib.sha256(b"").hexdigest()
_FIXTURE_PROVENANCE = "corex.test.fixture"


def _register_staged_fixture(
    store: ProjectArtifactStore,
    *,
    temporary_root_parent: str | Path,
    artifact_id: str = "verified",
    content: bytes = b"payload",
) -> tuple[Path, RuntimeArtifactRef]:
    store.ensure_staging_root(
        temporary_root_parent=temporary_root_parent,
    )
    paths = store.node_artifact_paths(
        artifact_id=artifact_id,
        workspace_id="ws_main",
        node_id="node_writer",
        io_dir="out",
        filename=f"{artifact_id}.bin",
    )
    payload_path = store.staged_target_path(paths.staged_relative_path)
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(content)
    runtime_ref = register_staged_artifact(
        store=store,
        artifact_id=artifact_id,
        payload_path=payload_path,
        relative_path=paths.staged_relative_path,
        slot=f"ws_main:node_writer:{artifact_id}",
        data_type_id=PATH_DATA_TYPE_ID,
        schema_version=_PATH_TYPE.payload_schema_version,
        format="bin",
        provenance=_FIXTURE_PROVENANCE,
        entry_metadata=paths.metadata,
    )
    return payload_path, runtime_ref


def _stage_managed_fixture(
    *,
    temporary_root_parent: str | Path,
) -> tuple[ProjectArtifactStore, RuntimeArtifactService, RuntimeArtifactRef]:
    source_project_path = Path(temporary_root_parent) / "source.cxproj"
    project_path = Path(temporary_root_parent) / "artifact.cxproj"
    source_store = ProjectArtifactStore(project_path=source_project_path, metadata=None)
    _payload_path, staged_ref = _register_staged_fixture(
        source_store,
        temporary_root_parent=temporary_root_parent,
    )
    stage = source_store.stage_project_save(
        destination_project_path=project_path,
        workspaces={},
        referenced_staged_ids={staged_ref.artifact_id},
    )
    store = stage.destination_store
    entry = store.managed_entry(staged_ref.artifact_id)
    if entry is None:
        raise AssertionError("promoted artifact entry is missing")
    descriptor = entry.extra["runtime_artifact"]
    managed_ref = RuntimeArtifactRef.managed(
        staged_ref.artifact_id,
        data_type_id=descriptor["data_type_id"],
        schema_version=descriptor["schema_version"],
        format=descriptor["format"],
        size_bytes=descriptor["size_bytes"],
        sha256=descriptor["sha256"],
        provenance=descriptor["provenance"],
    )
    service = RuntimeArtifactService(
        runtime_context=RuntimeSnapshotContext.from_snapshot(
            None,
            project_path=str(project_path),
            artifact_store=store,
        ),
        data_types=_DATA_TYPES,
    )
    return store, service, managed_ref


class ExecutionArtifactRefProtocolTests(unittest.TestCase):
    def test_runtime_artifact_payload_shape_stays_wire_compatible_through_codec(
        self,
    ) -> None:
        payload = {
            "__ea_runtime_value__": "artifact_ref",
            "ref": "temp://stored_stdout",
            "artifact_id": "stored_stdout",
            "scope": "staged",
            "data_type_id": PATH_DATA_TYPE_ID,
            "schema_version": _PATH_TYPE.payload_schema_version,
            "format": "txt",
            "size_bytes": _FIXTURE_SIZE_BYTES,
            "sha256": _FIXTURE_SHA256,
            "provenance": _FIXTURE_PROVENANCE,
            "metadata": {"line_count": 4},
        }

        restored = deserialize_runtime_value(payload, catalog=_DATA_TYPES)
        self.assertIsInstance(restored, RuntimeArtifactRef)
        self.assertEqual(
            serialize_runtime_value(restored, catalog=_DATA_TYPES),
            payload,
        )

    def test_node_settled_event_round_trips_runtime_artifact_ref_payloads(self) -> None:
        event = NodeSettledEvent(
            run_id="run_artifact",
            workspace_id="ws_main",
            node_id="node_process",
            outputs={
                "stdout": SettledPortResult(
                    status="value",
                    value=DataTree.from_item(
                        RuntimeArtifactRef.staged(
                            "stored_stdout",
                            data_type_id=PATH_DATA_TYPE_ID,
                            schema_version=_PATH_TYPE.payload_schema_version,
                            format="txt",
                            size_bytes=_FIXTURE_SIZE_BYTES,
                            sha256=_FIXTURE_SHA256,
                            provenance=_FIXTURE_PROVENANCE,
                        )
                    ),
                ),
                "preview": SettledPortResult(
                    status="value",
                    value=DataTree.from_item("inline preview"),
                ),
            },
        )

        payload = event_to_dict(event, catalog=_DATA_TYPES)

        self.assertEqual(
            payload["outputs"]["stdout"]["value"]["branches"][0]["items"][0],
            {
                "__ea_runtime_value__": "artifact_ref",
                "ref": "temp://stored_stdout",
                "artifact_id": "stored_stdout",
                "scope": "staged",
                "data_type_id": PATH_DATA_TYPE_ID,
                "schema_version": _PATH_TYPE.payload_schema_version,
                "format": "txt",
                "size_bytes": _FIXTURE_SIZE_BYTES,
                "sha256": _FIXTURE_SHA256,
                "provenance": _FIXTURE_PROVENANCE,
            },
        )
        self.assertEqual(
            payload["outputs"]["preview"]["value"]["branches"][0]["items"][0],
            "inline preview",
        )

        restored = dict_to_event(payload, catalog=_DATA_TYPES)
        self.assertEqual(
            restored.outputs["stdout"].value,
            DataTree.from_item(
                RuntimeArtifactRef.staged(
                    "stored_stdout",
                    data_type_id=PATH_DATA_TYPE_ID,
                    schema_version=_PATH_TYPE.payload_schema_version,
                    format="txt",
                    size_bytes=_FIXTURE_SIZE_BYTES,
                    sha256=_FIXTURE_SHA256,
                    provenance=_FIXTURE_PROVENANCE,
                )
            ),
        )
        self.assertEqual(
            restored.outputs["preview"].value,
            DataTree.from_item("inline preview"),
        )

    def test_start_run_command_round_trips_runtime_snapshot_artifact_payloads(
        self,
    ) -> None:
        snapshot = RuntimeSnapshot(
            schema_version=1,
            project_id="project_demo",
            metadata={
                "artifact_cache": {
                    "stdout": RuntimeArtifactRef.managed(
                        "stored_report",
                        data_type_id=PATH_DATA_TYPE_ID,
                        schema_version=_PATH_TYPE.payload_schema_version,
                        format="txt",
                        size_bytes=_FIXTURE_SIZE_BYTES,
                        sha256=_FIXTURE_SHA256,
                        provenance=_FIXTURE_PROVENANCE,
                    ),
                }
            },
        )
        command = StartRunCommand(
            run_id="run_demo",
            workspace_id="ws_main",
            trigger={"kind": "manual"},
            runtime_snapshot=snapshot,
            plugin_bundles=_FIXTURE_REGISTRY.plugin_bundle_refs(),
            plugin_fingerprint=_FIXTURE_REGISTRY.plugin_fingerprint(),
            registry_contract_fingerprint=(
                _FIXTURE_REGISTRY.contract_fingerprint()
            ),
            addon_runtime_config=_FIXTURE_REGISTRY.addon_runtime_config(),
        )

        payload = command_to_dict(command, catalog=_DATA_TYPES)

        self.assertEqual(
            payload["runtime_snapshot"]["metadata"]["artifact_cache"]["stdout"],
            {
                "__ea_runtime_value__": "artifact_ref",
                "ref": "saved://stored_report",
                "artifact_id": "stored_report",
                "scope": "managed",
                "data_type_id": PATH_DATA_TYPE_ID,
                "schema_version": _PATH_TYPE.payload_schema_version,
                "format": "txt",
                "size_bytes": _FIXTURE_SIZE_BYTES,
                "sha256": _FIXTURE_SHA256,
                "provenance": _FIXTURE_PROVENANCE,
            },
        )

        restored = dict_to_command(payload, catalog=_DATA_TYPES)
        self.assertIsNotNone(restored.runtime_snapshot)
        if restored.runtime_snapshot is None:
            self.fail("runtime snapshot was not restored")
        restored_ref = restored.runtime_snapshot.metadata["artifact_cache"]["stdout"]
        self.assertIsInstance(restored_ref, RuntimeArtifactRef)
        self.assertEqual(restored_ref.ref, "saved://stored_report")

    def test_runtime_snapshot_preserves_queue_safe_metadata_artifact_refs(self) -> None:
        snapshot = RuntimeSnapshot(
            schema_version=1,
            project_id="project_artifacts",
            metadata={
                "artifact_cache": {
                    "stdout": RuntimeArtifactRef.managed(
                        "stored_report",
                        data_type_id=PATH_DATA_TYPE_ID,
                        schema_version=_PATH_TYPE.payload_schema_version,
                        format="txt",
                        size_bytes=_FIXTURE_SIZE_BYTES,
                        sha256=_FIXTURE_SHA256,
                        provenance=_FIXTURE_PROVENANCE,
                    ),
                    "preview": RuntimeArtifactRef.staged(
                        "preview_png",
                        data_type_id=PATH_DATA_TYPE_ID,
                        schema_version=_PATH_TYPE.payload_schema_version,
                        format="png",
                        size_bytes=_FIXTURE_SIZE_BYTES,
                        sha256=_FIXTURE_SHA256,
                        provenance=_FIXTURE_PROVENANCE,
                    ),
                }
            },
        )

        self.assertEqual(
            snapshot.to_document(catalog=_DATA_TYPES)["metadata"]["artifact_cache"],
            {
                "stdout": {
                    "__ea_runtime_value__": "artifact_ref",
                    "ref": "saved://stored_report",
                    "artifact_id": "stored_report",
                    "scope": "managed",
                    "data_type_id": PATH_DATA_TYPE_ID,
                    "schema_version": _PATH_TYPE.payload_schema_version,
                    "format": "txt",
                    "size_bytes": _FIXTURE_SIZE_BYTES,
                    "sha256": _FIXTURE_SHA256,
                    "provenance": _FIXTURE_PROVENANCE,
                },
                "preview": {
                    "__ea_runtime_value__": "artifact_ref",
                    "ref": "temp://preview_png",
                    "artifact_id": "preview_png",
                    "scope": "staged",
                    "data_type_id": PATH_DATA_TYPE_ID,
                    "schema_version": _PATH_TYPE.payload_schema_version,
                    "format": "png",
                    "size_bytes": _FIXTURE_SIZE_BYTES,
                    "sha256": _FIXTURE_SHA256,
                    "provenance": _FIXTURE_PROVENANCE,
                },
            },
        )

    def test_start_run_command_requires_runtime_snapshot_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires runtime_snapshot"):
            coerce_start_run_command(
                {
                    "run_id": "run_missing_snapshot",
                    "workspace_id": "ws_main",
                    "project_path": "demo.cxproj",
                    "trigger": {"kind": "manual"},
                    "plugin_bundles": _FIXTURE_REGISTRY.plugin_bundle_refs(),
                    "plugin_fingerprint": _FIXTURE_REGISTRY.plugin_fingerprint(),
                    "registry_contract_fingerprint": (
                        _FIXTURE_REGISTRY.contract_fingerprint()
                    ),
                    "addon_runtime_config": (
                        _FIXTURE_REGISTRY.addon_runtime_config()
                    ),
                },
                catalog=_DATA_TYPES,
            )

    def test_runtime_snapshot_mapping_requires_workspace_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_order"):
            RuntimeSnapshot.from_mapping(
                {
                    "schema_version": 1,
                    "project_id": "project_demo",
                    "active_workspace_id": "ws_main",
                    "workspaces": [],
                    "metadata": {},
                }
            )

    def test_runtime_workspace_mapping_requires_document_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "document_fields"):
            RuntimeWorkspace.from_mapping(
                {
                    "workspace_id": "ws_main",
                    "name": "Main",
                    "nodes": [],
                    "edges": [],
                }
            )

    def test_execution_context_resolves_runtime_artifact_inputs_through_project_artifact_resolver(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_store = ProjectArtifactStore(
                project_path=None,
                metadata=None,
            )
            staging_root = artifact_store.ensure_staging_root(
                temporary_root_parent=temp_dir,
            )
            artifact_paths = artifact_store.node_artifact_paths(
                artifact_id="stored_stdout",
                workspace_id="ws_main",
                node_id="node_process",
                io_dir="out",
                filename="stored_stdout.txt",
            )
            artifact_path = staging_root.joinpath(
                *Path(artifact_paths.staged_relative_path).parts
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text("stored output", encoding="utf-8")
            runtime_ref = register_staged_artifact(
                store=artifact_store,
                artifact_id="stored_stdout",
                payload_path=artifact_path,
                relative_path=artifact_paths.staged_relative_path,
                slot="ws_main:node_process:stdout",
                data_type_id=PATH_DATA_TYPE_ID,
                schema_version=_PATH_TYPE.payload_schema_version,
                format="txt",
                provenance=_FIXTURE_PROVENANCE,
            )
            resolver = ProjectArtifactResolver(
                project_path=None,
                artifact_store=artifact_store,
            )
            ctx = ExecutionContext(
                run_id="run_demo",
                node_id="node_consumer",
                workspace_id="ws_main",
                inputs={
                    "artifact": runtime_ref
                },
                properties={},
                emit_log=lambda _level, _message: None,
                path_resolver=resolver.resolve_to_path,
            )

            self.assertEqual(ctx.resolve_input_path("artifact"), artifact_path)
            self.assertEqual(
                ctx.resolve_path_value("temp://stored_stdout"),
                artifact_path,
            )

    def test_file_write_managed_output_updates_runtime_store_and_downstream_reads(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "managed_output_demo.cxproj"
            runtime_snapshot = RuntimeSnapshot(
                schema_version=1,
                project_id="project_demo",
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

            write_ctx = ExecutionContext(
                run_id="run_demo",
                node_id="node_writer",
                workspace_id="ws_main",
                inputs={"text": "managed output"},
                properties={"path": "", "as_json": False},
                emit_log=lambda _level, _message: None,
                trigger={},
                project_path=str(project_path),
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
                node_type_id="io.file_write",
            )

            write_result = execute_file_write(write_ctx)

            written_ref = write_result.outputs["written_path"]
            self.assertIsInstance(written_ref, RuntimeArtifactRef)
            if not isinstance(written_ref, RuntimeArtifactRef):
                self.fail("managed output did not return a runtime artifact ref")
            self.assertEqual(written_ref.scope, "staged")
            self.assertEqual(written_ref.data_type_id, PATH_DATA_TYPE_ID)
            self.assertEqual(
                written_ref.schema_version,
                _PATH_TYPE.payload_schema_version,
            )
            self.assertEqual(written_ref.format, "txt")
            self.assertNotIn("format", written_ref.metadata)
            self.assertNotIn("absolute_path", written_ref.metadata)
            self.assertNotIn("relative_path", written_ref.metadata)

            staged_path = resolver.resolve_to_path(written_ref.ref)
            if staged_path is None:
                self.fail(
                    "managed output artifact ref did not resolve to a staged file"
                )
            self.assertTrue(staged_path.exists())
            self.assertEqual(staged_path.read_text(encoding="utf-8"), "managed output")
            self.assertEqual(runtime_snapshot.metadata, {})
            self.assertIn(
                written_ref.artifact_id,
                runtime_snapshot_context.project_metadata()["artifact_store"]["staged"],
            )

            read_ctx = ExecutionContext(
                run_id="run_demo",
                node_id="node_reader",
                workspace_id="ws_main",
                inputs={"path": written_ref},
                properties={"path": ""},
                emit_log=lambda _level, _message: None,
                trigger={},
                project_path=str(project_path),
                runtime_snapshot=runtime_snapshot,
                runtime_snapshot_context=runtime_snapshot_context,
                path_resolver=resolver.resolve_to_path,
            )

            read_result = execute_file_read(read_ctx)
            self.assertEqual(read_result.outputs["text"], "managed output")

    def test_managed_output_rejects_descriptor_free_intermediate_reparse_before_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            staging_root = store.ensure_staging_root(
                temporary_root_parent=temp_dir,
            )
            ctx = ExecutionContext(
                run_id="run_demo",
                node_id="node_writer",
                workspace_id="ws_main",
                inputs={},
                properties={},
                emit_log=lambda _level, _message: None,
                runtime_snapshot_context=RuntimeSnapshotContext.from_snapshot(
                    None,
                    artifact_store=store,
                ),
                node_type_id="io.file_write",
            )
            artifact_id = "generated.ws_main.node_writer.written_path"
            artifact_paths = store.node_artifact_paths(
                artifact_id=artifact_id,
                workspace_id=ctx.workspace_id,
                workspace_name=ctx.workspace_name,
                node_id=ctx.node_id,
                node_title=ctx.node_title,
                node_type=ctx.node_type_display_name or ctx.node_type_id,
                io_dir="out",
                subdirectory="generated",
                filename=f"{artifact_id}.txt",
            )
            relative_parts = artifact_paths.staged_relative_path.split("/")
            attempted_path = staging_root.joinpath(*relative_parts)
            reparse_intermediate = staging_root / relative_parts[0]
            reparse_intermediate.mkdir()
            sentinel = staging_root / "sentinel.txt"
            sentinel.write_text("sentinel", encoding="utf-8")
            outside_target = Path(temp_dir) / "outside" / attempted_path.name
            outside_target.parent.mkdir()
            outside_target.write_text("outside", encoding="utf-8")
            state_before = store.state
            hint_before = store.staging_root_hint
            real_lstat = os.lstat
            intermediate_stat = real_lstat(reparse_intermediate)
            reparse_flag = 0x400
            writer = Mock()

            def mark_intermediate_as_reparse(path):
                if os.path.normcase(os.path.abspath(path)) == os.path.normcase(
                    os.path.abspath(reparse_intermediate)
                ):
                    return SimpleNamespace(
                        st_mode=intermediate_stat.st_mode,
                        st_file_attributes=reparse_flag,
                    )
                return real_lstat(path)

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=mark_intermediate_as_reparse,
                ),
                patch(
                    "ea_node_editor.persistence.artifact_store.stat."
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    reparse_flag,
                    create=True,
                ),
                patch.object(
                    store,
                    "staged_target_path",
                    wraps=store.staged_target_path,
                ) as resolved_target,
                patch.object(Path, "open") as opened_file,
                self.assertRaises(ValueError) as caught,
            ):
                write_managed_output(
                    ctx,
                    output_key="written_path",
                    default_suffix=".txt",
                    write_payload=writer,
                )

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(staging_root), str(caught.exception))
            self.assertNotIn(str(outside_target), str(caught.exception))
            writer.assert_not_called()
            opened_file.assert_not_called()
            resolved_target.assert_not_called()
            self.assertFalse(attempted_path.exists())
            self.assertFalse(attempted_path.parent.exists())
            self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel")
            self.assertIs(store.state, state_before)
            self.assertIs(store.staging_root_hint, hint_before)
            self.assertEqual(store.active_staging_root(), staging_root)
            self.assertIsNone(store.staged_entry(artifact_id))

    def test_managed_output_registration_failure_rolls_back_only_attempted_output(
        self,
    ) -> None:
        real_register = register_staged_path_artifact
        cases = (
            (False, False),
            (True, False),
            (False, True),
        )
        for mutate_before_failure, reject_path_cleanup in cases:
            with self.subTest(
                mutate_before_failure=mutate_before_failure,
                reject_path_cleanup=reject_path_cleanup,
            ):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store = ProjectArtifactStore(project_path=None, metadata=None)
                    unrelated_path, _ = _register_staged_fixture(
                        store,
                        temporary_root_parent=temp_dir,
                        artifact_id="unrelated",
                        content=b"keep me",
                    )
                    staging_root = store.active_staging_root()
                    self.assertIsNotNone(staging_root)
                    if staging_root is None:
                        self.fail("staging root was not allocated")
                    sentinel = staging_root / "sentinel.txt"
                    sentinel.write_text("sentinel", encoding="utf-8")
                    ctx = ExecutionContext(
                        run_id="run_demo",
                        node_id="node_writer",
                        workspace_id="ws_main",
                        inputs={},
                        properties={},
                        emit_log=lambda _level, _message: None,
                        runtime_snapshot_context=(
                            RuntimeSnapshotContext.from_snapshot(
                                None,
                                artifact_store=store,
                            )
                        ),
                        node_type_id="io.file_write",
                    )
                    seeded = write_managed_output(
                        ctx,
                        output_key="written_path",
                        default_suffix=".txt",
                        write_payload=lambda path: path.write_text(
                            "old output",
                            encoding="utf-8",
                        ),
                    )
                    attempted_id = seeded.artifact_ref.artifact_id
                    attempted_path = seeded.path
                    marker = RuntimeError("registration marker")
                    cleanup_marker = ValueError(
                        "staged artifact discard target is unsafe"
                    )
                    real_discard_paths = store.discard_staged_paths
                    discard_path_calls = 0

                    def fail_registration(*args, **kwargs):
                        if mutate_before_failure:
                            real_register(*args, **kwargs)
                        raise marker

                    def discard_attempted_path(relative_paths):
                        nonlocal discard_path_calls
                        discard_path_calls += 1
                        if reject_path_cleanup and discard_path_calls == 2:
                            raise cleanup_marker
                        return real_discard_paths(relative_paths)

                    raw_unlink_patch = (
                        patch.object(Path, "unlink")
                        if reject_path_cleanup
                        else nullcontext()
                    )
                    with (
                        patch(
                            "ea_node_editor.nodes.output_artifacts."
                            "register_staged_path_artifact",
                            side_effect=fail_registration,
                        ) as mocked_register,
                        patch.object(
                            store,
                            "discard_staged_paths",
                            side_effect=discard_attempted_path,
                        ) as mocked_discard_paths,
                        raw_unlink_patch as raw_unlink,
                        self.assertRaises(RuntimeError) as caught,
                    ):
                        def write_replacement(path):
                            if reject_path_cleanup:
                                raw_unlink.reset_mock()
                            path.write_text(
                                "replacement output",
                                encoding="utf-8",
                            )

                        write_managed_output(
                            ctx,
                            output_key="written_path",
                            default_suffix=".txt",
                            write_payload=write_replacement,
                        )

                    self.assertIs(caught.exception, marker)
                    mocked_register.assert_called_once()
                    self.assertEqual(mocked_discard_paths.call_count, 2)
                    self.assertIsNone(store.staged_entry(attempted_id))
                    for discard_call in mocked_discard_paths.call_args_list:
                        discarded_paths = discard_call.args[0]
                        self.assertEqual(len(discarded_paths), 1)
                        self.assertEqual(
                            store.staged_target_path(discarded_paths[0]),
                            attempted_path,
                        )
                    if reject_path_cleanup:
                        self.assertIsNotNone(raw_unlink)
                        raw_unlink.assert_not_called()
                        self.assertTrue(attempted_path.exists())
                    else:
                        self.assertFalse(attempted_path.exists())
                    self.assertIsNotNone(store.staged_entry("unrelated"))
                    self.assertEqual(unrelated_path.read_bytes(), b"keep me")
                    self.assertEqual(store.active_staging_root(), staging_root)
                    self.assertTrue(staging_root.exists())
                    self.assertEqual(
                        sentinel.read_text(encoding="utf-8"),
                        "sentinel",
                    )

    def test_artifact_content_integrity_hashes_files_and_directory_shape(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload_file = root / "payload.bin"
            payload_file.write_bytes(b"payload")
            self.assertEqual(
                artifact_content_integrity(root, "payload.bin"),
                (7, hashlib.sha256(b"payload").hexdigest()),
            )

            bundle = root / "bundle"
            (bundle / "nested").mkdir(parents=True)
            (bundle / "empty").mkdir()
            (bundle / "a.txt").write_bytes(b"a")
            (bundle / "nested" / "b.txt").write_bytes(b"bc")
            original = artifact_content_integrity(root, "bundle")
            self.assertEqual(original[0], 3)
            self.assertEqual(
                original,
                artifact_content_integrity(root, "bundle"),
            )

            reordered = root / "reordered"
            (reordered / "empty").mkdir(parents=True)
            (reordered / "nested").mkdir()
            (reordered / "nested" / "b.txt").write_bytes(b"bc")
            (reordered / "a.txt").write_bytes(b"a")
            self.assertEqual(
                artifact_content_integrity(root, "reordered"),
                original,
            )

            (bundle / "empty").rename(bundle / "renamed_empty")
            renamed = artifact_content_integrity(root, "bundle")
            self.assertEqual(renamed[0], original[0])
            self.assertNotEqual(renamed[1], original[1])

    def test_artifact_content_integrity_rejects_symlinks_without_path_leak(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload.bin"
            payload.write_bytes(b"payload")
            with (
                patch(
                    "ea_node_editor.common.payload_tools.os.lstat",
                    side_effect=(
                        os.lstat(root),
                        SimpleNamespace(
                            st_mode=stat.S_IFLNK,
                            st_file_attributes=0,
                        ),
                    ),
                ),
                self.assertRaises(ValueError) as caught,
            ):
                artifact_content_integrity(root, "payload.bin")
            self.assertNotIn(str(root), str(caught.exception))

    def test_artifact_content_integrity_rejects_intermediate_reparse_points(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "junction"
            nested.mkdir()
            (nested / "payload.bin").write_bytes(b"payload")
            reparse_flag = 0x400
            root_stat = os.lstat(root)
            nested_stat = os.lstat(nested)

            with (
                patch(
                    "ea_node_editor.common.payload_tools.os.lstat",
                    side_effect=(
                        root_stat,
                        SimpleNamespace(
                            st_mode=nested_stat.st_mode,
                            st_size=nested_stat.st_size,
                            st_dev=nested_stat.st_dev,
                            st_ino=nested_stat.st_ino,
                            st_mtime_ns=nested_stat.st_mtime_ns,
                            st_file_attributes=reparse_flag,
                        ),
                    ),
                ),
                patch(
                    "ea_node_editor.common.payload_tools.stat."
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    reparse_flag,
                    create=True,
                ),
                patch(
                    "ea_node_editor.common.payload_tools.os.open",
                ) as opened_file,
                self.assertRaises(ValueError) as caught,
            ):
                artifact_content_integrity(
                    root,
                    "junction/payload.bin",
                )

            opened_file.assert_not_called()
            self.assertIn("reparse", str(caught.exception))
            self.assertNotIn(str(root), str(caught.exception))

    def test_artifact_content_integrity_rejects_intermediate_symlinks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "link"
            nested.mkdir()
            (nested / "payload.bin").write_bytes(b"payload")

            with (
                patch(
                    "ea_node_editor.common.payload_tools.os.lstat",
                    side_effect=(
                        os.lstat(root),
                        SimpleNamespace(
                            st_mode=stat.S_IFLNK,
                            st_file_attributes=0,
                        ),
                    ),
                ),
                patch(
                    "ea_node_editor.common.payload_tools.os.open",
                ) as opened_file,
                self.assertRaises(ValueError) as caught,
            ):
                artifact_content_integrity(root, "link/payload.bin")

            opened_file.assert_not_called()
            self.assertIn("symbolic link", str(caught.exception))
            self.assertNotIn(str(root), str(caught.exception))

    def test_artifact_content_integrity_rejects_unreadable_directories_safely(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = root / "bundle"
            denied = bundle / "denied"
            denied.mkdir(parents=True)
            original_scandir = os.scandir

            def guarded_scandir(path: object):
                if Path(path) == denied:
                    raise PermissionError(f"denied: {denied}")
                return original_scandir(path)

            with (
                patch(
                    "ea_node_editor.common.payload_tools.os.scandir",
                    side_effect=guarded_scandir,
                ),
                self.assertRaises(OSError) as caught,
            ):
                artifact_content_integrity(root, "bundle")

            self.assertEqual(
                str(caught.exception),
                "artifact payload could not be inspected",
            )
            self.assertNotIn(str(root), str(caught.exception))

    def test_artifact_content_integrity_rejects_swapped_file_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload.bin"
            payload.write_bytes(b"payload")
            original_lstat = os.lstat
            target_checks = 0

            def swapped_lstat(path: object):
                nonlocal target_checks
                result = original_lstat(path)
                if Path(path) != payload:
                    return result
                target_checks += 1
                if target_checks == 1:
                    return result
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_size=result.st_size,
                    st_dev=result.st_dev,
                    st_ino=result.st_ino + 1,
                    st_mtime_ns=result.st_mtime_ns,
                    st_file_attributes=getattr(
                        result,
                        "st_file_attributes",
                        0,
                    ),
                )

            with (
                patch(
                    "ea_node_editor.common.payload_tools.os.lstat",
                    side_effect=swapped_lstat,
                ),
                self.assertRaises(OSError) as caught,
            ):
                artifact_content_integrity(root, "payload.bin")

            self.assertIn("changed while hashing", str(caught.exception))
            self.assertNotIn(str(root), str(caught.exception))

    def test_staged_registration_rejects_external_payload_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            store.ensure_staging_root(temporary_root_parent=temp_dir)
            paths = store.node_artifact_paths(
                artifact_id="external",
                workspace_id="workspace",
                node_id="node",
                io_dir="out",
                filename="external.bin",
            )
            external_path = Path(temp_dir) / "outside-store.bin"
            external_path.write_bytes(b"outside")

            with self.assertRaisesRegex(
                ValueError,
                "active store target",
            ) as caught:
                register_staged_artifact(
                    store=store,
                    artifact_id="external",
                    payload_path=external_path,
                    relative_path=paths.staged_relative_path,
                    slot="workspace:node:external",
                    data_type_id=PATH_DATA_TYPE_ID,
                    schema_version=_PATH_TYPE.payload_schema_version,
                    format="bin",
                    provenance=_FIXTURE_PROVENANCE,
                )

            self.assertIsNone(store.staged_entry("external"))
            self.assertNotIn(str(external_path), str(caught.exception))

    def test_staged_path_registration_requires_truthful_producer_identity(
        self,
    ) -> None:
        ctx = ExecutionContext(
            run_id="run",
            node_id="node",
            workspace_id="workspace",
            inputs={},
            properties={},
            emit_log=lambda _level, _message: None,
        )
        with self.assertRaisesRegex(ValueError, "node_type_id"):
            register_staged_path_artifact(
                ctx,
                store=object(),
                artifact_id="artifact",
                payload_path="missing",
                relative_path="missing",
                slot=None,
                format="bin",
            )

    def test_runtime_artifact_service_validates_staged_and_saved_ownership(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact.cxproj"
            store = ProjectArtifactStore(project_path=project_path, metadata=None)
            payload_path, staged_ref = _register_staged_fixture(
                store,
                temporary_root_parent=temp_dir,
            )
            context = RuntimeSnapshotContext.from_snapshot(
                None,
                project_path=str(project_path),
                artifact_store=store,
            )
            service = RuntimeArtifactService(
                runtime_context=context,
                data_types=_DATA_TYPES,
            )

            for untyped_ref in (
                f"temp://{staged_ref.artifact_id}",
                f"saved://{staged_ref.artifact_id}",
            ):
                with self.subTest(untyped_ref=untyped_ref, entry="settlement"):
                    with self.assertRaisesRegex(
                        TypeError,
                        "RuntimeArtifactRef",
                    ):
                        service.normalize_outputs({"artifact": untyped_ref})
                with self.subTest(untyped_ref=untyped_ref, entry="resolution"):
                    with self.assertRaisesRegex(
                        TypeError,
                        "RuntimeArtifactRef",
                    ):
                        service.resolve_path(untyped_ref)

            self.assertEqual(
                service.normalize_outputs({"artifact": staged_ref}),
                {"artifact": staged_ref},
            )
            self.assertEqual(service.resolve_path(staged_ref), payload_path)

            stage = store.stage_project_save(
                destination_project_path=Path(temp_dir) / "published.cxproj",
                workspaces={},
                referenced_staged_ids={staged_ref.artifact_id},
            )
            self.assertEqual(
                stage.ref_replacements,
                {staged_ref.ref: f"saved://{staged_ref.artifact_id}"},
            )
            destination_store = stage.destination_store
            managed_ref = RuntimeArtifactRef.managed(
                staged_ref.artifact_id,
                data_type_id=staged_ref.data_type_id,
                schema_version=staged_ref.schema_version,
                format=staged_ref.format,
                size_bytes=staged_ref.size_bytes,
                sha256=staged_ref.sha256,
                provenance=staged_ref.provenance,
                metadata=staged_ref.metadata,
            )
            managed_entry = destination_store.managed_entry(managed_ref.artifact_id)
            self.assertIsNotNone(managed_entry)
            if managed_entry is None:
                self.fail("promoted artifact entry is missing")
            self.assertEqual(
                managed_entry.extra["runtime_artifact"],
                managed_ref.to_descriptor(),
            )
            destination_service = RuntimeArtifactService(
                runtime_context=RuntimeSnapshotContext.from_snapshot(
                    None,
                    project_path=str(destination_store.project_path),
                    artifact_store=destination_store,
                ),
                data_types=_DATA_TYPES,
            )
            self.assertEqual(
                destination_service.resolve_path(managed_ref),
                destination_store.resolve_managed_path(managed_ref.artifact_id),
            )
            with self.assertRaisesRegex(
                FileNotFoundError,
                "not registered in the active store",
            ):
                destination_service.resolve_path(staged_ref)
            self.assertEqual(service.resolve_path(staged_ref), payload_path)

    def test_runtime_artifact_service_materializes_registered_saved_ref(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )

            materialized = service.materialize_persisted_value(managed_ref.ref)

            self.assertEqual(materialized, managed_ref)
            self.assertEqual(
                service.resolve_path(materialized),
                store.resolve_managed_path(managed_ref.artifact_id),
            )

    def test_runtime_artifact_service_materializes_nested_saved_refs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )
            raw_ref = managed_ref.ref
            opaque_nested = {
                "__ea_runtime_value__": "secret_data",
                "nested": {
                    "__ea_runtime_value__": "ssh_sftp_host_data",
                    "ref": raw_ref,
                },
            }
            serialized_tree = serialize_runtime_value(
                DataTree(
                    (
                        (
                            (9, 3),
                            (
                                managed_ref,
                                {"raw": raw_ref},
                                {
                                    "__ea_runtime_value__": "secret_data",
                                    "ref": raw_ref,
                                },
                            ),
                        ),
                    )
                ),
                catalog=_DATA_TYPES,
            )
            value = {
                "direct": raw_ref,
                raw_ref: "mapping key stays raw",
                "list": [raw_ref, ("plain", raw_ref)],
                "tree": DataTree(
                    (
                        (
                            (4, 2),
                            (raw_ref, {"nested": [raw_ref]}),
                        ),
                    )
                ),
                "serialized_tree": serialized_tree,
                "live_direct": managed_ref,
                "live_nested": {"items": [managed_ref]},
                "ordinary": {"enabled": True, "count": 2},
                "opaque": opaque_nested,
            }

            with patch(
                "ea_node_editor.runtime_contracts.value_codec.deserialize_runtime_value",
                wraps=deserialize_runtime_value,
            ) as decoder:
                materialized = service.materialize_persisted_value(value)

            self.assertEqual(materialized["direct"], managed_ref)
            self.assertEqual(materialized[raw_ref], "mapping key stays raw")
            self.assertEqual(
                materialized["list"],
                [managed_ref, ("plain", managed_ref)],
            )
            self.assertEqual(
                materialized["tree"],
                DataTree(
                    (
                        (
                            (4, 2),
                            (
                                managed_ref,
                                {"nested": [managed_ref]},
                            ),
                        ),
                    )
                ),
            )
            self.assertEqual(
                materialized["serialized_tree"],
                DataTree(
                    (
                        (
                            (9, 3),
                            (
                                managed_ref,
                                {"raw": managed_ref},
                                {
                                    "__ea_runtime_value__": "secret_data",
                                    "ref": managed_ref,
                                },
                            ),
                        ),
                    )
                ),
            )
            self.assertIs(materialized["live_direct"], managed_ref)
            self.assertIs(materialized["live_nested"]["items"][0], managed_ref)
            self.assertEqual(
                materialized["ordinary"],
                {"enabled": True, "count": 2},
            )
            self.assertEqual(
                materialized["opaque"],
                {
                    "__ea_runtime_value__": "secret_data",
                    "nested": {
                        "__ea_runtime_value__": "ssh_sftp_host_data",
                        "ref": managed_ref,
                    },
                },
            )
            self.assertEqual(decoder.call_count, 2)
            serialized_artifact = materialized["serialized_tree"].branches[0][1][0]
            self.assertIsInstance(serialized_artifact, RuntimeArtifactRef)
            self.assertEqual(
                service.resolve_path(serialized_artifact),
                store.resolve_managed_path(managed_ref.artifact_id),
            )

    def test_node_input_accepts_materialized_saved_property_ref(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )
            raw_property = {
                "raw_top": managed_ref.ref,
                "typed_top": managed_ref,
                "list": [
                    managed_ref.ref,
                    managed_ref,
                    {"enabled": True},
                ],
                "tuple": ("plain", managed_ref.ref, managed_ref),
                "dict": {
                    "raw": managed_ref.ref,
                    "typed": managed_ref,
                },
                "tree": DataTree(
                    (
                        (
                            (3, 1),
                            (
                                managed_ref.ref,
                                managed_ref,
                                {"nested": managed_ref.ref},
                            ),
                        ),
                    )
                ),
                "ordinary": {"count": 3, "ratio": 1.5},
            }
            executor = object.__new__(NodeExecutor)
            executor._plan = SimpleNamespace(
                nodes={"node": SimpleNamespace(port_modifiers={})},
                incoming_edges_for=lambda *_args: (),
            )
            executor._data_types = _DATA_TYPES
            executor._prepare_untyped_tree = (
                lambda _node_id, _port, tree: tree
            )
            port = SimpleNamespace(
                key="path",
                uses_property_default=True,
                data_access="item",
            )

            with (
                patch(
                    "ea_node_editor.runtime_contracts.value_codec."
                    "serialize_runtime_value",
                    side_effect=AssertionError(
                        "persisted properties must not be serialized"
                    ),
                ) as serialized,
                patch(
                    "ea_node_editor.runtime_contracts.value_codec."
                    "deserialize_runtime_value",
                    side_effect=AssertionError(
                        "persisted properties must not be deserialized"
                    ),
                ) as deserialized,
            ):
                materialized = service.materialize_persisted_value(raw_property)
                result = executor._input_result(
                    "node",
                    port,
                    {"path": materialized},
                )

            self.assertEqual(result.status, "value")
            self.assertEqual(result.value, DataTree.from_item(materialized))
            serialized.assert_not_called()
            deserialized.assert_not_called()
            self.assertIsNot(materialized, raw_property)
            self.assertIsNot(materialized["list"], raw_property["list"])
            self.assertIsInstance(materialized["tuple"], tuple)
            self.assertIsNot(materialized["dict"], raw_property["dict"])
            self.assertIsNot(materialized["tree"], raw_property["tree"])
            self.assertEqual(
                materialized["ordinary"],
                {"count": 3, "ratio": 1.5},
            )
            self.assertEqual(materialized["raw_top"], managed_ref)
            self.assertIs(materialized["typed_top"], managed_ref)
            expected_path = store.resolve_managed_path(managed_ref.artifact_id)
            nested_refs = (
                materialized["raw_top"],
                materialized["typed_top"],
                materialized["list"][0],
                materialized["list"][1],
                materialized["tuple"][1],
                materialized["tuple"][2],
                materialized["dict"]["raw"],
                materialized["dict"]["typed"],
                *materialized["tree"].branches[0][1][:2],
            )
            for runtime_ref in nested_refs:
                self.assertEqual(
                    service.resolve_path(runtime_ref),
                    expected_path,
                )

    def test_runtime_artifact_service_rejects_unsupported_property_values(
        self,
    ) -> None:
        service = RuntimeArtifactService(
            runtime_context=RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=ProjectArtifactStore(
                    project_path=None,
                    metadata=None,
                ),
            ),
            data_types=_DATA_TYPES,
        )

        for case, value in (
            ("non_string_mapping_key", {1: "not a string key"}),
            ("unsupported_object_leaf", object()),
        ):
            with self.subTest(case=case), self.assertRaises(TypeError):
                service.materialize_persisted_value(value)

    def test_normal_node_materializes_saved_properties_before_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )
            node_id = "node"
            port = SimpleNamespace(
                key="path",
                uses_property_default=True,
                data_access="item",
                required=True,
                allow_empty_string=False,
            )
            node = SimpleNamespace(
                type_id="tests.saved_property",
                title="Saved Property",
                properties={"path": managed_ref.ref},
                port_modifiers={},
                principal_input_port_id=None,
            )
            spec = SimpleNamespace(
                is_async=False,
                ports=(port,),
            )
            plan = SimpleNamespace(
                nodes={node_id: node},
                node_specs={node_id: spec},
                node_preflight_errors={},
                input_ports=lambda _node_id: (port,),
                output_ports=lambda _node_id: (),
                incoming_edges_for=lambda _node_id, _port_key=None: (),
            )
            observed: dict[str, object] = {}

            def execute(ctx):  # noqa: ANN001, ANN202
                observed["input"] = ctx.inputs["path"]
                observed["property"] = ctx.properties["path"]
                observed["resolved"] = ctx.resolve_path_value(ctx.inputs["path"])
                return SimpleNamespace(outputs={}, warnings=())

            registry = SimpleNamespace(
                normalize_properties=lambda _type_id, properties: dict(properties),
                create=lambda _type_id: SimpleNamespace(execute=execute),
                python_function_ref_or_none=lambda _type_id: None,
            )
            control = Mock()
            control.shutdown_requested = False
            control.stop_requested = False
            control.should_stop.return_value = False
            publisher = Mock()
            publisher.run_id = "run"
            publisher.workspace_id = "workspace"
            executor = object.__new__(NodeExecutor)
            executor._plan = plan
            executor._registry = registry
            executor._data_types = _DATA_TYPES
            executor._control = control
            executor._publisher = publisher
            executor._artifact_service = service
            executor.node_outputs = {}
            executor.executed = set()
            executor._developer_mode = False
            executor._prepare_untyped_tree = (
                lambda _node_id, _port, tree: tree
            )
            executor._execution_context = (
                lambda _node_id, inputs, properties, **_kwargs: SimpleNamespace(
                    inputs=inputs,
                    properties=dict(properties),
                    resolve_path_value=service.resolve_path,
                )
            )
            settlements: list[dict[str, object]] = []

            def settle(*_args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                settlements.append(kwargs)
                return "ok"

            executor._settle = settle

            with (
                patch(
                    "ea_node_editor.execution.worker_runner."
                    "resolve_instance_ports",
                    return_value=(port,),
                ),
                patch(
                    "ea_node_editor.execution.worker_runner."
                    "evaluate_node_readiness",
                    return_value=(),
                ),
                patch(
                    "ea_node_editor.execution.worker_runner.replace",
                    return_value=spec,
                ),
            ):
                status = executor._execute_node(node_id)

            self.assertEqual(status, "ok")
            self.assertEqual(observed["input"], managed_ref)
            self.assertEqual(observed["property"], managed_ref)
            self.assertEqual(
                observed["resolved"],
                store.resolve_managed_path(managed_ref.artifact_id),
            )
            self.assertEqual(settlements[-1]["status"], "completed")

            node.properties = {"path": "saved://unknown"}
            self.assertEqual(executor._execute_node(node_id), "ok")
            self.assertEqual(settlements[-1]["status"], "failed")
            self.assertIn(
                "not registered in the active store",
                settlements[-1]["errors"][0].error,
            )

    def test_clicked_trigger_materializes_saved_properties_before_branching(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )
            node_id = "trigger"
            node = SimpleNamespace(
                type_id="core.trigger",
                properties={"path": managed_ref.ref},
                port_modifiers={},
            )
            plan = SimpleNamespace(
                nodes={node_id: node},
                clicked_trigger_node_id=node_id,
                incoming_edges_for=lambda _node_id, _port_key=None: (),
            )
            executor = object.__new__(NodeExecutor)
            executor._plan = plan
            executor._registry = SimpleNamespace(
                normalize_properties=lambda _type_id, properties: dict(properties)
            )
            executor._artifact_service = service
            executor._publisher = Mock()
            executor._trigger_captures = {}
            executor._trigger_publications = {}
            executor.pending_trigger_publication = None
            executor._developer_mode = False
            settlements: list[dict[str, object]] = []

            def settle(*_args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                settlements.append(kwargs)
                return "ok"

            executor._settle = settle
            observed: list[dict[str, object]] = []
            original_materialize = service.materialize_authored_properties

            def record_materialized(value):  # noqa: ANN001, ANN202
                result = original_materialize(value)
                if isinstance(value, dict) and "path" in value:
                    observed.append(result)
                return result

            with patch.object(
                service,
                "materialize_authored_properties",
                side_effect=record_materialized,
            ):
                status = executor._execute_trigger(node_id)

            self.assertEqual(status, "ok")
            self.assertEqual(observed, [{"path": managed_ref}])
            self.assertIsNotNone(executor.pending_trigger_publication)
            self.assertEqual(settlements[-1]["status"], "completed")

            with patch.object(
                store,
                "managed_entry",
                return_value=SimpleNamespace(
                    extra={"runtime_artifact": "malformed"}
                ),
            ):
                self.assertEqual(executor._execute_trigger(node_id), "ok")
            self.assertEqual(settlements[-1]["status"], "failed")
            self.assertIn(
                "descriptor is invalid",
                settlements[-1]["errors"][0].error,
            )

    def test_trigger_capture_materializes_saved_properties_before_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _store, service, managed_ref = _stage_managed_fixture(
                temporary_root_parent=temp_dir,
            )
            trigger_id = "trigger"
            edge = SimpleNamespace(source_node_id="source", source_port_key="output")
            node = SimpleNamespace(
                type_id="core.trigger",
                properties={"path": managed_ref.ref},
            )
            plan = SimpleNamespace(
                nodes={trigger_id: node},
                clicked_trigger_node_id="",
                is_trigger=lambda node_id: node_id == trigger_id,
                incoming_edges_for=lambda node_id, _port_key=None: (
                    (edge,) if node_id == trigger_id else ()
                ),
                ports_by_key={
                    trigger_id: {
                        "input": SimpleNamespace(key="input"),
                    }
                },
            )
            executor = object.__new__(NodeExecutor)
            executor._plan = plan
            executor._registry = SimpleNamespace(
                normalize_properties=lambda _type_id, properties: dict(properties)
            )
            executor._artifact_service = service
            executor._publisher = Mock()
            executor.executed = {"source"}
            executor.node_outputs = {
                "source": {"output": SettledPortResult(status="empty")}
            }
            captured_properties: list[Mapping[str, object]] = []

            def input_result(_node_id, _port, properties):  # noqa: ANN001, ANN202
                captured_properties.append(properties)
                return SettledPortResult(
                    status="value",
                    value=DataTree.from_item(True),
                )

            executor._input_result = input_result

            executor.refresh_trigger_captures()

            self.assertEqual(
                captured_properties,
                [{"path": managed_ref}],
            )
            executor._publisher.emit_trigger_capture_settled.assert_called_once()

            # Reading another current output must not overwrite this capture.
            executor.node_outputs = {"source": {}}
            executor._publisher.reset_mock()
            captured_properties.clear()
            executor.refresh_trigger_captures()
            self.assertEqual(captured_properties, [])
            executor._publisher.emit_trigger_capture_settled.assert_not_called()

    def test_runtime_artifact_service_rejects_missing_saved_descriptor(
        self,
    ) -> None:
        store = ProjectArtifactStore(project_path=None, metadata=None)
        service = RuntimeArtifactService(
            runtime_context=RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=store,
            ),
            data_types=_DATA_TYPES,
        )

        with (
            patch.object(
                store,
                "managed_entry",
                return_value=SimpleNamespace(extra={}),
            ),
            self.assertRaisesRegex(
                ValueError,
                "^artifact 'missing_descriptor' descriptor is missing$",
            ),
        ):
            service.materialize_persisted_value(
                "saved://missing_descriptor"
            )

    def test_runtime_artifact_service_rejects_malformed_saved_descriptor(
        self,
    ) -> None:
        store = ProjectArtifactStore(project_path=None, metadata=None)
        service = RuntimeArtifactService(
            runtime_context=RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=store,
            ),
            data_types=_DATA_TYPES,
        )
        malformed_descriptors = (
            "secret.token.value",
            {"data_type_id": "secret.token.value"},
            {
                "data_type_id": "secret.token.value",
                "schema_version": 1,
                "format": "bin",
                "size_bytes": 0,
                "sha256": "0" * 64,
                "provenance": _FIXTURE_PROVENANCE,
            },
        )

        for descriptor in malformed_descriptors:
            with (
                self.subTest(descriptor=descriptor),
                patch.object(
                    store,
                    "managed_entry",
                    return_value=SimpleNamespace(
                        extra={"runtime_artifact": descriptor}
                    ),
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "^artifact 'malformed' descriptor is invalid$",
                ) as caught,
            ):
                service.materialize_persisted_value("saved://malformed")
            self.assertNotIn("secret.token.value", str(caught.exception))

    def test_runtime_artifact_service_rejects_unregistered_saved_ref(
        self,
    ) -> None:
        service = RuntimeArtifactService(
            runtime_context=RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=ProjectArtifactStore(
                    project_path=None,
                    metadata=None,
                ),
            ),
            data_types=_DATA_TYPES,
        )

        with self.assertRaisesRegex(
            FileNotFoundError,
            "^artifact 'unknown' is not registered in the active store$",
        ):
            service.materialize_persisted_value("saved://unknown")

    def test_runtime_artifact_service_rejects_malformed_and_staged_raw_refs(
        self,
    ) -> None:
        service = RuntimeArtifactService(
            runtime_context=RuntimeSnapshotContext.from_snapshot(
                None,
                artifact_store=ProjectArtifactStore(
                    project_path=None,
                    metadata=None,
                ),
            ),
            data_types=_DATA_TYPES,
        )

        for raw_ref in ("saved://", "saved://bad/id", "SAVED://artifact"):
            with (
                self.subTest(raw_ref=raw_ref),
                self.assertRaisesRegex(
                    ValueError,
                    "^persisted artifact reference is malformed$",
                ),
            ):
                service.materialize_persisted_value(raw_ref)
        for raw_ref in ("temp://artifact", "TEMP://artifact"):
            with (
                self.subTest(raw_ref=raw_ref),
                self.assertRaisesRegex(
                    TypeError,
                    "RuntimeArtifactRef",
                ),
            ):
                service.materialize_persisted_value(raw_ref)

    def test_runtime_artifact_service_rejects_wrong_store_and_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            payload_path, runtime_ref = _register_staged_fixture(
                store,
                temporary_root_parent=temp_dir,
            )
            service = RuntimeArtifactService(
                runtime_context=RuntimeSnapshotContext.from_snapshot(
                    None,
                    artifact_store=store,
                ),
                data_types=_DATA_TYPES,
            )
            wrong_store_service = RuntimeArtifactService(
                runtime_context=RuntimeSnapshotContext.from_snapshot(
                    None,
                    artifact_store=ProjectArtifactStore(
                        project_path=None,
                        metadata=None,
                    ),
                ),
                data_types=_DATA_TYPES,
            )

            with self.assertRaisesRegex(
                FileNotFoundError,
                "not registered in the active store",
            ):
                wrong_store_service.resolve_path(runtime_ref)

            payload_path.write_bytes(b"PAYLOAD")
            with self.assertRaisesRegex(ValueError, "sha256"):
                service.resolve_path(runtime_ref)

            payload_path.write_bytes(b"longer payload")
            with self.assertRaisesRegex(ValueError, "size_bytes"):
                service.resolve_path(runtime_ref)

            payload_path.unlink()
            with self.assertRaises(FileNotFoundError) as caught:
                service.resolve_path(runtime_ref)
            self.assertNotIn(str(payload_path), str(caught.exception))

    def test_runtime_artifact_service_rejects_descriptor_mismatch_safely(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            payload_path, runtime_ref = _register_staged_fixture(
                store,
                temporary_root_parent=temp_dir,
            )
            service = RuntimeArtifactService(
                runtime_context=RuntimeSnapshotContext.from_snapshot(
                    None,
                    artifact_store=store,
                ),
                data_types=_DATA_TYPES,
            )
            entry = store.staged_entry(runtime_ref.artifact_id)
            self.assertIsNotNone(entry)
            if entry is None:
                self.fail("staged artifact entry is missing")
            mismatches = {
                "data_type_id": "COREX.DataTypes.String",
                "schema_version": True,
                "format": "txt",
                "size_bytes": runtime_ref.size_bytes + 1,
                "sha256": "f" * 64,
                "provenance": "secret.token.value",
            }
            for field_name, mismatch in mismatches.items():
                with self.subTest(field_name=field_name):
                    descriptor = dict(entry.extra["runtime_artifact"])
                    descriptor[field_name] = mismatch
                    extra = dict(entry.extra)
                    extra["runtime_artifact"] = descriptor
                    store.register_staged_entry(
                        runtime_ref.artifact_id,
                        relative_path=entry.relative_path,
                        slot=entry.slot,
                        extra=extra,
                    )

                    with self.assertRaises(ValueError) as caught:
                        service.normalize_outputs({"artifact": runtime_ref})
                    message = str(caught.exception)
                    self.assertIn(field_name, message)
                    self.assertNotIn(str(mismatch), message)
                    self.assertNotIn(str(payload_path), message)


if __name__ == "__main__":
    unittest.main()
