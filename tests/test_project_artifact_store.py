from __future__ import annotations

import os
import hashlib
import stat
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.nodes.output_artifacts import register_staged_artifact
from ea_node_editor.common.artifact_refs import (
    ManagedArtifactRef,
    StagedArtifactRef,
    format_managed_artifact_ref,
    format_staged_artifact_ref,
    parse_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import (
    ArtifactStoreState,
    ProjectArtifactLayout,
    ProjectArtifactStore,
    StagedArtifactEntry,
    StagingRootHint,
    format_node_artifact_folder,
    format_workspace_artifact_folder,
    normalize_artifact_store_metadata,
)


class ProjectArtifactStoreTests(unittest.TestCase):
    def test_layout_derives_workspace_sidecar_root_and_legacy_node_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo_project.cxproj"
            layout = ProjectArtifactLayout.from_project_path(project_path)

        self.assertEqual(layout.project_file, project_path)
        self.assertEqual(layout.sidecar_root, project_path.with_name("demo_project.data"))
        self.assertEqual(layout.workspaces_root, project_path.with_name("demo_project.data") / "workspaces")
        self.assertEqual(layout.nodes_root, project_path.with_name("demo_project.data") / "nodes")

    def test_solution_repository_uses_the_same_project_owned_sidecar_root(self) -> None:
        project_path = Path("demo_project.cxproj")
        layout = ProjectArtifactLayout.from_project_path(project_path)

        self.assertEqual(
            layout.sidecar_root / "solutions" / "v1",
            project_path.with_name("demo_project.data") / "solutions" / "v1",
        )

    def test_node_artifact_paths_create_tmp_and_final_paths_with_metadata(self) -> None:
        store = ProjectArtifactStore(project_path=None, metadata=None)

        paths = store.node_artifact_paths(
            artifact_id="input_file",
            workspace_id="main",
            workspace_name="Main",
            node_id="node:bad/id",
            node_title="Report: Export*",
            node_type="File Write",
            io_dir="in",
            subdirectory="source/media",
            filename="report.csv",
        )

        self.assertTrue(paths.node_folder.startswith("File Write - Report Export ["))
        self.assertTrue(paths.node_folder.endswith("]"))
        self.assertTrue(paths.workspace_folder.startswith("Main ["))
        self.assertTrue(paths.workspace_folder.endswith("]"))
        self.assertEqual(
            paths.managed_relative_path,
            f"workspaces/{paths.workspace_folder}/nodes/{paths.node_folder}/in/source/media/report.csv",
        )
        self.assertEqual(
            paths.staged_relative_path,
            f"workspaces/{paths.workspace_folder}/nodes/{paths.node_folder}/tmp/in/source/media/report.csv",
        )
        self.assertEqual(paths.metadata["managed_relative_path"], paths.managed_relative_path)
        self.assertEqual(paths.metadata["node_workspace_id"], "main")
        self.assertEqual(paths.metadata["node_workspace_name"], "Main")
        self.assertEqual(paths.metadata["workspace_folder"], paths.workspace_folder)
        self.assertEqual(paths.metadata["node_id"], "node:bad/id")
        self.assertEqual(paths.metadata["node_title"], "Report: Export*")
        self.assertEqual(paths.metadata["node_folder"], paths.node_folder)
        self.assertEqual(paths.metadata["io_dir"], "in")

    def test_artifact_store_metadata_accepts_legacy_and_workspace_scoped_relative_paths(self) -> None:
        workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
        folder = format_node_artifact_folder(
            workspace_id="ws",
            node_id="node",
            node_title="Image",
            node_type="Image Panel",
        )
        normalized = normalize_artifact_store_metadata(
            {
                "artifacts": {
                    "image_source": {
                        "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/in/media/diagram.png"
                    },
                },
                "staged": {
                    "pending_output": {"relative_path": f"nodes/{folder}/tmp/out/run.txt"},
                },
            }
        )

        self.assertEqual(
            normalized["artifacts"]["image_source"]["relative_path"],
            f"workspaces/{workspace_folder}/nodes/{folder}/in/media/diagram.png",
        )
        self.assertEqual(
            normalized["staged"]["pending_output"]["relative_path"],
            f"nodes/{folder}/tmp/out/run.txt",
        )
        with self.assertRaisesRegex(ValueError, "valid relative_path"):
            normalize_artifact_store_metadata(
                {"artifacts": {"old": {"relative_path": "assets/media/diagram.png"}}}
            )
        with self.assertRaisesRegex(ValueError, "relative_path or absolute_path"):
            normalize_artifact_store_metadata(
                {"staged": {"old": {"relative_path": ".staging/outputs/run.txt"}}}
            )

    def test_store_resolves_saved_and_temporary_node_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
            folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_title="Writer",
                node_type="File Write",
            )
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "saved_output": {
                            "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/out/reports/run.txt"
                        },
                    },
                    "staged": {
                        "pending_output": {
                            "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/tmp/out/reports/run.txt"
                        },
                    },
                },
            )

            self.assertEqual(
                store.resolve_managed_path("saved_output"),
                project_path.with_name("demo.data")
                / "workspaces"
                / workspace_folder
                / "nodes"
                / folder
                / "out"
                / "reports"
                / "run.txt",
            )
            self.assertEqual(
                store.resolve_staged_path(format_staged_artifact_ref("pending_output")),
                project_path.with_name("demo.data")
                / "workspaces"
                / workspace_folder
                / "nodes"
                / folder
                / "tmp"
                / "out"
                / "reports"
                / "run.txt",
            )

    def test_stage_project_save_copies_tmp_out_to_destination_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_project_path = Path(temp_dir) / "source.cxproj"
            destination_project_path = Path(temp_dir) / "destination.cxproj"
            source_store = ProjectArtifactStore(
                project_path=source_project_path,
                metadata=None,
            )
            root = source_store.ensure_staging_root()
            paths = source_store.node_artifact_paths(
                artifact_id="generated.ws.node.stdout",
                workspace_id="ws",
                node_id="node",
                node_title="Process",
                node_type="Process Run",
                io_dir="out",
                subdirectory="generated/process_run",
                filename="stdout.log",
            )
            staged_path = root.joinpath(*PurePosixPath(paths.staged_relative_path).parts)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text("payload", encoding="utf-8")
            runtime_ref = register_staged_artifact(
                store=source_store,
                artifact_id="generated.ws.node.stdout",
                payload_path=staged_path,
                relative_path=paths.staged_relative_path,
                slot="ws:node:stdout",
                data_type_id="COREX.DataTypes.Path",
                schema_version=1,
                format="txt",
                provenance="corex.test.project_store",
                entry_metadata=paths.metadata,
            )

            stage = source_store.stage_project_save(
                destination_project_path=destination_project_path,
                workspaces={
                    "ws": SimpleNamespace(
                        workspace_id="ws",
                        name="Workspace",
                        nodes={},
                    )
                },
                referenced_staged_ids={"generated.ws.node.stdout"},
            )
            destination_store = stage.destination_store

            managed_path = destination_store.resolve_managed_path(
                "generated.ws.node.stdout"
            )
            self.assertIsNotNone(managed_path)
            if managed_path is None:
                self.fail("copy-on-write stage did not register the managed artifact")
            self.assertEqual(
                stage.ref_replacements,
                {"temp://generated.ws.node.stdout": "saved://generated.ws.node.stdout"},
            )
            self.assertEqual(stage.promoted_artifact_ids, ("generated.ws.node.stdout",))
            self.assertEqual(managed_path.read_text(encoding="utf-8"), "payload")
            self.assertTrue(staged_path.exists())
            self.assertEqual(staged_path.read_text(encoding="utf-8"), "payload")
            self.assertEqual(
                destination_store.metadata["artifacts"]["generated.ws.node.stdout"]["relative_path"],
                paths.managed_relative_path,
            )
            self.assertEqual(
                destination_store.metadata["artifacts"]["generated.ws.node.stdout"]["slot"],
                "ws:node:stdout",
            )
            self.assertEqual(
                destination_store.metadata["artifacts"]["generated.ws.node.stdout"][
                    "runtime_artifact"
                ],
                runtime_ref.to_descriptor(),
            )
            self.assertEqual(destination_store.metadata["staged"], {})
            self.assertIn("generated.ws.node.stdout", source_store.metadata["staged"])

    def test_discard_staged_payloads_deletes_only_tmp_payloads_for_saved_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            store = ProjectArtifactStore(project_path=project_path, metadata=None)
            root = store.ensure_staging_root()
            paths = store.node_artifact_paths(
                artifact_id="pending",
                workspace_id="ws",
                node_id="node",
                node_title="Image",
                node_type="Image Panel",
                io_dir="in",
                subdirectory="media",
                filename="image.png",
            )
            saved_path = root.joinpath(*PurePosixPath(paths.managed_relative_path).parts)
            temp_path = root.joinpath(*PurePosixPath(paths.staged_relative_path).parts)
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            saved_path.write_text("saved", encoding="utf-8")
            temp_path.write_text("temp", encoding="utf-8")
            store.register_staged_entry("pending", relative_path=paths.staged_relative_path, extra=paths.metadata)

            self.assertTrue(store.discard_staged_payloads())

            self.assertTrue(saved_path.exists())
            self.assertFalse(temp_path.exists())

    def test_register_staged_entry_replaces_distinct_payload_safely(self) -> None:
        cases = (
            ("same-id", "pending", "pending", "old-slot", "new-slot"),
            ("same-slot", "old", "new", "shared-slot", "shared-slot"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for label, old_id, new_id, old_slot, new_slot in cases:
                with self.subTest(label=label):
                    store = ProjectArtifactStore(project_path=None, metadata=None)
                    root = store.ensure_staging_root(
                        temporary_root_parent=parent / label
                    )
                    old_relative = f"nodes/{label}-old.txt"
                    new_relative = f"nodes/{label}-new.txt"
                    old_path = root.joinpath(
                        *PurePosixPath(old_relative).parts
                    )
                    new_path = root.joinpath(
                        *PurePosixPath(new_relative).parts
                    )
                    old_path.parent.mkdir(parents=True)
                    old_path.write_text("old", encoding="utf-8")
                    new_path.write_text("fresh", encoding="utf-8")
                    store.register_staged_entry(
                        old_id,
                        relative_path=old_relative,
                        slot=old_slot,
                    )
                    hint = store.staging_root_hint

                    result = store.register_staged_entry(
                        new_id,
                        relative_path=new_relative,
                        slot=new_slot,
                    )

                    self.assertEqual(result.artifact_id, new_id)
                    self.assertEqual(result.relative_path, new_relative)
                    self.assertEqual(set(store.state.staged), {new_id})
                    self.assertFalse(old_path.exists())
                    self.assertEqual(
                        new_path.read_text(encoding="utf-8"),
                        "fresh",
                    )
                    self.assertIs(store.staging_root_hint, hint)
                    self.assertTrue(root.is_dir())
                    self.assertTrue((root / "nodes").is_dir())

    def test_register_staged_entry_preserves_fresh_same_path_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            relative_path = "nodes/shared/payload.txt"
            payload_path = root.joinpath(*PurePosixPath(relative_path).parts)
            payload_path.parent.mkdir(parents=True)
            payload_path.write_text("old", encoding="utf-8")
            unrelated_path = root / "workspaces" / "unrelated.txt"
            unrelated_path.parent.mkdir(parents=True)
            unrelated_path.write_text("unrelated", encoding="utf-8")
            store.register_staged_entry(
                "old",
                relative_path=relative_path,
                slot="shared-slot",
            )
            payload_path.write_text("fresh", encoding="utf-8")
            hint = store.staging_root_hint

            result = store.register_staged_entry(
                "new",
                relative_path="nodes\\shared\\payload.txt",
                slot="shared-slot",
            )

            self.assertEqual(result.relative_path, relative_path)
            self.assertEqual(set(store.state.staged), {"new"})
            self.assertEqual(
                payload_path.read_text(encoding="utf-8"),
                "fresh",
            )
            self.assertEqual(
                unrelated_path.read_text(encoding="utf-8"),
                "unrelated",
            )
            self.assertIs(store.staging_root_hint, hint)
            self.assertTrue(root.is_dir())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_register_staged_entry_rejects_displaced_absolute_hint_atomically(self) -> None:
        cases = (
            ("same-id", "pending", "pending", "old-slot", "new-slot"),
            ("same-slot", "old", "new", "shared-slot", "shared-slot"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for label, old_id, new_id, old_slot, new_slot in cases:
                with self.subTest(label=label):
                    case_root = parent / label
                    root = case_root / "staging"
                    incoming_path = root / "nodes" / "incoming.txt"
                    unrelated_path = root / "workspaces" / "unrelated.txt"
                    outside_path = case_root / "outside.txt"
                    incoming_path.parent.mkdir(parents=True)
                    unrelated_path.parent.mkdir(parents=True)
                    incoming_path.write_text("incoming", encoding="utf-8")
                    unrelated_path.write_text("unrelated", encoding="utf-8")
                    outside_path.write_text("outside", encoding="utf-8")
                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata=ArtifactStoreState(
                            staged={
                                old_id: StagedArtifactEntry(
                                    artifact_id=old_id,
                                    absolute_path_hint=str(outside_path),
                                    slot=old_slot,
                                )
                            },
                            staging_root=StagingRootHint(
                                kind="session_temp",
                                absolute_path=str(root),
                            ),
                        ),
                    )
                    original_state = store.state
                    hint = store.staging_root_hint

                    with self.assertRaises(ValueError) as caught:
                        store.register_staged_entry(
                            new_id,
                            relative_path="nodes/incoming.txt",
                            slot=new_slot,
                        )

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertNotIn(str(root), str(caught.exception))
                    self.assertNotIn(str(outside_path), str(caught.exception))
                    self.assertIs(store.state, original_state)
                    self.assertIs(store.staging_root_hint, hint)
                    self.assertEqual(set(store.state.staged), {old_id})
                    self.assertEqual(
                        incoming_path.read_text(encoding="utf-8"),
                        "incoming",
                    )
                    self.assertEqual(
                        unrelated_path.read_text(encoding="utf-8"),
                        "unrelated",
                    )
                    self.assertEqual(
                        outside_path.read_text(encoding="utf-8"),
                        "outside",
                    )
                    self.assertTrue(root.is_dir())
                    self.assertTrue((root / "nodes").is_dir())
                    self.assertTrue((root / "workspaces").is_dir())

    def test_register_staged_entry_prevalidates_all_displacements_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            safe_old_path = root / "nodes" / "safe-old.txt"
            incoming_path = root / "nodes" / "incoming.txt"
            junction = root / "workspaces" / "junction"
            unsafe_old_path = junction / "unsafe-old.txt"
            retained_path = root / "workspaces" / "retained.txt"
            safe_old_path.parent.mkdir(parents=True)
            unsafe_old_path.parent.mkdir(parents=True)
            safe_old_path.write_text("safe-old", encoding="utf-8")
            incoming_path.write_text("incoming", encoding="utf-8")
            unsafe_old_path.write_text("unsafe-old", encoding="utf-8")
            retained_path.write_text("retained", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "same-id": StagedArtifactEntry(
                            artifact_id="same-id",
                            relative_path="nodes/safe-old.txt",
                            slot="old-slot",
                        ),
                        "slot-old": StagedArtifactEntry(
                            artifact_id="slot-old",
                            relative_path="workspaces/junction/unsafe-old.txt",
                            slot="shared-slot",
                        ),
                        "retained": StagedArtifactEntry(
                            artifact_id="retained",
                            relative_path="workspaces/retained.txt",
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state
            hint = store.staging_root_hint
            junction_key = os.path.normcase(os.path.abspath(junction))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == junction_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.register_staged_entry(
                    "same-id",
                    relative_path="nodes/incoming.txt",
                    slot="shared-slot",
                )

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(junction), str(caught.exception))
            self.assertIs(store.state, original_state)
            self.assertIs(store.staging_root_hint, hint)
            self.assertEqual(
                set(store.state.staged),
                {"same-id", "slot-old", "retained"},
            )
            self.assertEqual(
                safe_old_path.read_text(encoding="utf-8"),
                "safe-old",
            )
            self.assertEqual(
                incoming_path.read_text(encoding="utf-8"),
                "incoming",
            )
            self.assertEqual(
                unsafe_old_path.read_text(encoding="utf-8"),
                "unsafe-old",
            )
            self.assertEqual(
                retained_path.read_text(encoding="utf-8"),
                "retained",
            )
            self.assertTrue(root.is_dir())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_register_staged_entry_rejects_displaced_overlap_atomically(self) -> None:
        cases = (
            (
                "incoming",
                "nodes/tree",
                "nodes/tree/incoming.txt",
                None,
                None,
            ),
            (
                "retained-staged",
                "nodes/tree",
                "nodes/incoming.txt",
                "nodes/tree/retained.txt",
                None,
            ),
            (
                "managed",
                "workspaces/tree",
                "nodes/incoming.txt",
                None,
                "workspaces/tree/managed.txt",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for (
                label,
                old_relative,
                incoming_relative,
                retained_relative,
                managed_relative,
            ) in cases:
                with self.subTest(label=label):
                    root = parent / label
                    root.mkdir()
                    old_path = root.joinpath(
                        *PurePosixPath(old_relative).parts
                    )
                    incoming_path = root.joinpath(
                        *PurePosixPath(incoming_relative).parts
                    )
                    old_marker = old_path / "old.txt"
                    unrelated_path = root / "workspaces" / "unrelated.txt"
                    old_marker.parent.mkdir(parents=True)
                    incoming_path.parent.mkdir(parents=True, exist_ok=True)
                    unrelated_path.parent.mkdir(parents=True, exist_ok=True)
                    old_marker.write_text("old", encoding="utf-8")
                    incoming_path.write_text("incoming", encoding="utf-8")
                    unrelated_path.write_text("unrelated", encoding="utf-8")

                    staged_metadata: dict[str, dict[str, str]] = {
                        "replace": {"relative_path": old_relative}
                    }
                    protected_paths: list[Path] = []
                    if retained_relative is not None:
                        retained_path = root.joinpath(
                            *PurePosixPath(retained_relative).parts
                        )
                        retained_path.parent.mkdir(parents=True, exist_ok=True)
                        retained_path.write_text("retained", encoding="utf-8")
                        staged_metadata["retained"] = {
                            "relative_path": retained_relative
                        }
                        protected_paths.append(retained_path)

                    artifact_metadata: dict[str, dict[str, str]] = {}
                    if managed_relative is not None:
                        managed_path = root.joinpath(
                            *PurePosixPath(managed_relative).parts
                        )
                        managed_path.parent.mkdir(parents=True, exist_ok=True)
                        managed_path.write_text("managed", encoding="utf-8")
                        artifact_metadata["managed"] = {
                            "relative_path": managed_relative
                        }
                        protected_paths.append(managed_path)

                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata={
                            "artifacts": artifact_metadata,
                            "staged": staged_metadata,
                            "staging_root": {
                                "kind": "session_temp",
                                "absolute_path": str(root),
                            },
                        },
                    )
                    original_state = store.state
                    hint = store.staging_root_hint

                    with self.assertRaises(ValueError) as caught:
                        store.register_staged_entry(
                            "replace",
                            relative_path=incoming_relative,
                        )

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertNotIn(str(root), str(caught.exception))
                    self.assertNotIn(str(old_path), str(caught.exception))
                    self.assertIs(store.state, original_state)
                    self.assertIs(store.staging_root_hint, hint)
                    self.assertEqual(
                        old_marker.read_text(encoding="utf-8"),
                        "old",
                    )
                    self.assertEqual(
                        incoming_path.read_text(encoding="utf-8"),
                        "incoming",
                    )
                    self.assertEqual(
                        unrelated_path.read_text(encoding="utf-8"),
                        "unrelated",
                    )
                    for protected_path in protected_paths:
                        self.assertTrue(protected_path.exists())
                    self.assertTrue(root.is_dir())
                    self.assertTrue((root / "nodes").is_dir())
                    self.assertTrue((root / "workspaces").is_dir())

    def test_discard_staged_entries_preserves_unsaved_staging_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            paths = store.node_artifact_paths(
                artifact_id="pending",
                workspace_id="ws",
                node_id="node",
                node_title="Process",
                node_type="Process Run",
                io_dir="out",
                filename="stdout.log",
            )
            payload_path = root.joinpath(*PurePosixPath(paths.staged_relative_path).parts)
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text("payload", encoding="utf-8")
            sentinel_path = root / "unregistered.txt"
            sentinel_path.write_text("keep", encoding="utf-8")
            store.register_staged_entry(
                "pending",
                relative_path=paths.staged_relative_path,
                extra=paths.metadata,
            )
            hint = store.staging_root_hint

            self.assertEqual(store.discard_staged_entries(("pending",)), ("pending",))

            self.assertIsNone(store.resolve_staged_path("pending"))
            self.assertEqual(store.metadata["staged"], {})
            self.assertFalse(payload_path.exists())
            self.assertEqual(store.active_staging_root(), root)
            self.assertIs(store.staging_root_hint, hint)
            self.assertTrue(root.exists())
            self.assertEqual(sentinel_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_absolute_path_hint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "staging"
            root.mkdir()
            outside_path = parent / "outside.txt"
            outside_path.write_text("keep", encoding="utf-8")
            entry = StagedArtifactEntry(
                artifact_id="unsafe",
                relative_path="nodes/payload.txt",
                absolute_path_hint=str(outside_path),
            )
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={"unsafe": entry},
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(outside_path), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(outside_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_malformed_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            root.mkdir()
            malformed_paths = (
                None,
                Path("nodes/payload.txt"),
                "",
                "/nodes/payload.txt",
                "nodes/../outside.txt",
                "nodes/./payload.txt",
                "nodes\\payload.txt",
                "nodes/payload.txt:stream",
                "nodes/CON.txt",
                "nodes/CONIN$",
                "nodes/COM¹.txt",
            )

            for relative_path in malformed_paths:
                with self.subTest(relative_path=repr(relative_path)):
                    entry = StagedArtifactEntry(
                        artifact_id="unsafe",
                        relative_path=relative_path,
                    )
                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata=ArtifactStoreState(
                            staged={"unsafe": entry},
                            staging_root=StagingRootHint(
                                kind="session_temp",
                                absolute_path=str(root),
                            ),
                        ),
                    )

                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_entries(("unsafe",))

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertNotIn(str(root), str(caught.exception))
                    self.assertIn("unsafe", store.state.staged)

    def test_discard_staged_entries_rejects_windows_disguised_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "staging"
            root.mkdir()
            outside_path = parent / "outside.txt"
            outside_path.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "unsafe": StagedArtifactEntry(
                            artifact_id="unsafe",
                            relative_path="nodes/.. /.. /outside.txt",
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(outside_path), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(outside_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_intermediate_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            root.mkdir()
            intermediate = root / "nodes"
            intermediate.write_text("keep", encoding="utf-8")
            entry = StagedArtifactEntry(
                artifact_id="unsafe",
                relative_path="nodes/child/payload.txt",
            )
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={"unsafe": entry},
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(intermediate.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_portable_symlink_stat(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            target = root / "nodes" / "payload.txt"
            target.parent.mkdir(parents=True)
            target.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "unsafe": StagedArtifactEntry(
                            artifact_id="unsafe",
                            relative_path="nodes/payload.txt",
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            target_key = os.path.normcase(os.path.abspath(target))
            real_lstat = os.lstat

            def symlink_lstat(path: str | os.PathLike[str]) -> object:
                if os.path.normcase(os.path.abspath(path)) == target_key:
                    return SimpleNamespace(
                        st_mode=stat.S_IFLNK | 0o777,
                        st_file_attributes=0,
                    )
                return real_lstat(path)

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=symlink_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_intermediate_reparse_point(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            junction = root / "workspaces" / "junction"
            target = junction / "payload.txt"
            target.parent.mkdir(parents=True)
            target.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "unsafe": StagedArtifactEntry(
                            artifact_id="unsafe",
                            relative_path="workspaces/junction/payload.txt",
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            junction_key = os.path.normcase(os.path.abspath(junction))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == junction_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_protected_reparse_path_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            selected_path = root / "nodes" / "output.txt"
            junction = root / "workspaces" / "junction"
            protected_path = junction / "tracked.txt"
            selected_path.parent.mkdir(parents=True)
            protected_path.parent.mkdir(parents=True)
            selected_path.write_text("selected", encoding="utf-8")
            protected_path.write_text("protected", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "selected": StagedArtifactEntry(
                            artifact_id="selected",
                            relative_path="nodes/output.txt",
                        ),
                        "protected": StagedArtifactEntry(
                            artifact_id="protected",
                            relative_path="workspaces/junction/tracked.txt",
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state
            hint = store.staging_root_hint
            junction_key = os.path.normcase(os.path.abspath(junction))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == junction_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_entries(("selected",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(protected_path), str(caught.exception))
            self.assertIs(store.state, original_state)
            self.assertIs(store.staging_root_hint, hint)
            self.assertEqual(
                set(store.state.staged),
                {"selected", "protected"},
            )
            self.assertEqual(
                selected_path.read_text(encoding="utf-8"),
                "selected",
            )
            self.assertEqual(
                protected_path.read_text(encoding="utf-8"),
                "protected",
            )
            self.assertTrue(root.is_dir())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_discard_staged_entries_rejects_special_final_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            target = root / "nodes" / "special"
            target.parent.mkdir(parents=True)
            target.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "unsafe": StagedArtifactEntry(
                            artifact_id="unsafe",
                            relative_path="nodes/special",
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            target_key = os.path.normcase(os.path.abspath(target))
            real_lstat = os.lstat

            def special_lstat(path: str | os.PathLike[str]) -> object:
                if os.path.normcase(os.path.abspath(path)) == target_key:
                    return SimpleNamespace(
                        st_mode=stat.S_IFIFO | 0o600,
                        st_file_attributes=0,
                    )
                return real_lstat(path)

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=special_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_entries(("unsafe",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertIn("unsafe", store.state.staged)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_prevalidation_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            root = parent / "staging"
            safe_path = root / "nodes" / "safe.txt"
            safe_path.parent.mkdir(parents=True)
            safe_path.write_text("safe", encoding="utf-8")
            outside_path = parent / "outside.txt"
            outside_path.write_text("outside", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "safe": StagedArtifactEntry(
                            artifact_id="safe",
                            relative_path="nodes/safe.txt",
                        ),
                        "unsafe": StagedArtifactEntry(
                            artifact_id="unsafe",
                            relative_path="nodes/unsafe.txt",
                            absolute_path_hint=str(outside_path),
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("safe", "unsafe"))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(outside_path), str(caught.exception))
            self.assertIs(store.state, original_state)
            self.assertEqual(set(store.state.staged), {"safe", "unsafe"})
            self.assertEqual(safe_path.read_text(encoding="utf-8"), "safe")
            self.assertEqual(outside_path.read_text(encoding="utf-8"), "outside")

    def test_discard_staged_entries_deletes_safe_file_and_directory_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            file_path = root / "nodes" / "file.txt"
            directory_path = root / "workspaces" / "tree"
            file_path.parent.mkdir(parents=True)
            directory_path.mkdir(parents=True)
            file_path.write_text("file", encoding="utf-8")
            (directory_path / "child.txt").write_text("child", encoding="utf-8")
            sentinel_path = root / "unregistered.txt"
            sentinel_path.write_text("keep", encoding="utf-8")
            store.register_staged_entry("file", relative_path="nodes/file.txt")
            store.register_staged_entry(
                "directory",
                relative_path="workspaces/tree",
            )
            hint = store.staging_root_hint

            removed = store.discard_staged_entries(("file", "directory"))

            self.assertEqual(removed, ("file", "directory"))
            self.assertEqual(store.metadata["staged"], {})
            self.assertFalse(file_path.exists())
            self.assertFalse(directory_path.exists())
            self.assertEqual(store.active_staging_root(), root)
            self.assertIs(store.staging_root_hint, hint)
            self.assertTrue(root.exists())
            self.assertEqual(sentinel_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_allows_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            sentinel_path = root / "unregistered.txt"
            sentinel_path.write_text("keep", encoding="utf-8")
            store.register_staged_entry(
                "missing",
                relative_path="nodes/missing/payload.txt",
            )

            self.assertEqual(
                store.discard_staged_entries(("missing",)),
                ("missing",),
            )

            self.assertEqual(store.metadata["staged"], {})
            self.assertTrue(root.exists())
            self.assertEqual(sentinel_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_invalid_active_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            missing_root = parent / "missing"
            file_root = parent / "file-root"
            file_root.write_text("keep", encoding="utf-8")

            for root in (missing_root, file_root):
                with self.subTest(root_kind=root.name):
                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata=ArtifactStoreState(
                            staged={
                                "unsafe": StagedArtifactEntry(
                                    artifact_id="unsafe",
                                    relative_path="nodes/payload.txt",
                                )
                            },
                            staging_root=StagingRootHint(
                                kind="session_temp",
                                absolute_path=str(root),
                            ),
                        ),
                    )

                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_entries(("unsafe",))

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertNotIn(str(root), str(caught.exception))
                    self.assertIn("unsafe", store.state.staged)

    def test_discard_staged_entries_rejects_managed_root_targets_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for root_name in ("nodes", "workspaces"):
                with self.subTest(root_name=root_name):
                    root = parent / f"staging-{root_name}"
                    unrelated_path = root / root_name / "unrelated" / "keep.txt"
                    unrelated_path.parent.mkdir(parents=True)
                    unrelated_path.write_text("keep", encoding="utf-8")
                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata=ArtifactStoreState(
                            staged={
                                "unsafe": StagedArtifactEntry(
                                    artifact_id="unsafe",
                                    relative_path=root_name,
                                )
                            },
                            staging_root=StagingRootHint(
                                kind="session_temp",
                                absolute_path=str(root),
                            ),
                        ),
                    )
                    original_state = store.state

                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_entries(("unsafe",))

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertIs(store.state, original_state)
                    self.assertIn("unsafe", store.state.staged)
                    self.assertEqual(
                        unrelated_path.read_text(encoding="utf-8"),
                        "keep",
                    )

    def test_discard_staged_entries_rejects_nested_unselected_entry_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            safe_path = root / "nodes" / "safe.txt"
            selected_path = root / "nodes" / "tree"
            unrelated_path = selected_path / "unrelated" / "keep.txt"
            safe_path.parent.mkdir(parents=True)
            unrelated_path.parent.mkdir(parents=True)
            safe_path.write_text("safe", encoding="utf-8")
            unrelated_path.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "safe": StagedArtifactEntry(
                            artifact_id="safe",
                            relative_path="nodes/safe.txt",
                        ),
                        "directory": StagedArtifactEntry(
                            artifact_id="directory",
                            relative_path="nodes/tree",
                        ),
                        "unrelated": StagedArtifactEntry(
                            artifact_id="unrelated",
                            relative_path="nodes/tree/unrelated/keep.txt",
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("safe", "directory"))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertIs(store.state, original_state)
            self.assertEqual(
                set(store.state.staged),
                {"safe", "directory", "unrelated"},
            )
            self.assertEqual(safe_path.read_text(encoding="utf-8"), "safe")
            self.assertEqual(
                unrelated_path.read_text(encoding="utf-8"),
                "keep",
            )

    def test_discard_staged_entries_rejects_unselected_absolute_hint_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            selected_path = root / "nodes" / "tree"
            tracked_path = selected_path / "tracked.txt"
            tracked_path.parent.mkdir(parents=True)
            tracked_path.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "selected": StagedArtifactEntry(
                            artifact_id="selected",
                            relative_path="nodes/tree",
                        ),
                        "tracked": StagedArtifactEntry(
                            artifact_id="tracked",
                            absolute_path_hint=str(tracked_path),
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_entries(("selected",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertIs(store.state, original_state)
            self.assertEqual(
                set(store.state.staged),
                {"selected", "tracked"},
            )
            self.assertEqual(tracked_path.read_text(encoding="utf-8"), "keep")

    def test_discard_staged_entries_rejects_managed_path_overlap_directions(self) -> None:
        cases = (
            ("exact", "nodes/shared.txt", "nodes/shared.txt"),
            ("selected-descendant", "workspaces/tree/child.txt", "workspaces/tree"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for label, selected_relative, managed_relative in cases:
                with self.subTest(label=label):
                    root = parent / label
                    root.mkdir()
                    selected_path = root.joinpath(
                        *PurePosixPath(selected_relative).parts
                    )
                    selected_path.parent.mkdir(parents=True)
                    selected_path.write_text("keep", encoding="utf-8")
                    store = ProjectArtifactStore(
                        project_path=None,
                        metadata={
                            "artifacts": {
                                "managed": {"relative_path": managed_relative}
                            },
                            "staged": {
                                "selected": {"relative_path": selected_relative}
                            },
                            "staging_root": {
                                "kind": "session_temp",
                                "absolute_path": str(root),
                            },
                        },
                    )
                    original_state = store.state

                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_entries(("selected",))

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertIs(store.state, original_state)
                    self.assertEqual(
                        selected_path.read_text(encoding="utf-8"),
                        "keep",
                    )

    def test_discard_staged_entries_uses_component_aware_overlap_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            selected_path = root / "nodes" / "foo"
            protected_path = root / "nodes" / "foobar" / "keep.txt"
            selected_path.mkdir(parents=True)
            protected_path.parent.mkdir(parents=True)
            (selected_path / "delete.txt").write_text("delete", encoding="utf-8")
            protected_path.write_text("keep", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "selected": StagedArtifactEntry(
                            artifact_id="selected",
                            relative_path="nodes/foo",
                        ),
                        "protected": StagedArtifactEntry(
                            artifact_id="protected",
                            relative_path="nodes/foobar/keep.txt",
                        ),
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )

            self.assertEqual(
                store.discard_staged_entries(("selected",)),
                ("selected",),
            )

            self.assertFalse(selected_path.exists())
            self.assertEqual(
                protected_path.read_text(encoding="utf-8"),
                "keep",
            )
            self.assertEqual(set(store.state.staged), {"protected"})

    def test_discard_staged_paths_deletes_untracked_file_directory_and_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            file_path = root / "nodes" / "untracked.txt"
            directory_path = root / "workspaces" / "untracked"
            missing_path = root / "nodes" / "missing.txt"
            file_path.parent.mkdir(parents=True)
            directory_path.mkdir(parents=True)
            file_path.write_text("delete", encoding="utf-8")
            (directory_path / "child.txt").write_text("delete", encoding="utf-8")
            original_state = store.state
            hint = store.staging_root_hint

            removed = store.discard_staged_paths(
                (
                    "nodes/untracked.txt",
                    "workspaces/untracked",
                    "nodes/missing.txt",
                    "nodes/untracked.txt",
                )
            )

            self.assertEqual(
                removed,
                (
                    "nodes/untracked.txt",
                    "workspaces/untracked",
                    "nodes/missing.txt",
                ),
            )
            self.assertIs(store.state, original_state)
            self.assertIs(store.staging_root_hint, hint)
            self.assertFalse(file_path.exists())
            self.assertFalse(directory_path.exists())
            self.assertFalse(missing_path.exists())
            self.assertTrue(root.exists())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_discard_staged_paths_rejects_managed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            for root_name in ("nodes", "workspaces"):
                with self.subTest(root_name=root_name):
                    store = ProjectArtifactStore(project_path=None, metadata=None)
                    root = store.ensure_staging_root(
                        temporary_root_parent=parent / root_name
                    )
                    sentinel_path = root / root_name / "nested" / "keep.txt"
                    sentinel_path.parent.mkdir(parents=True)
                    sentinel_path.write_text("keep", encoding="utf-8")
                    original_state = store.state

                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_paths((root_name,))

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertIs(store.state, original_state)
                    self.assertEqual(
                        sentinel_path.read_text(encoding="utf-8"),
                        "keep",
                    )

    def test_discard_staged_paths_rejects_tracked_overlaps_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "managed": {"relative_path": "nodes/tracked"}
                    },
                    "staged": {
                        "staged": {
                            "relative_path": "workspaces/tracked/keep.txt"
                        }
                    },
                },
            )
            root = store.ensure_staging_root()
            safe_path = root / "nodes" / "safe.txt"
            managed_child = root / "nodes" / "tracked" / "child.txt"
            staged_path = root / "workspaces" / "tracked" / "keep.txt"
            safe_path.parent.mkdir(parents=True)
            managed_child.parent.mkdir(parents=True)
            staged_path.parent.mkdir(parents=True)
            safe_path.write_text("safe", encoding="utf-8")
            managed_child.write_text("managed", encoding="utf-8")
            staged_path.write_text("staged", encoding="utf-8")
            original_state = store.state

            for unsafe_path in (
                "nodes/tracked/untracked.txt",
                "workspaces/tracked/keep.txt",
            ):
                with self.subTest(unsafe_path=unsafe_path):
                    with self.assertRaises(ValueError) as caught:
                        store.discard_staged_paths(
                            ("nodes/safe.txt", unsafe_path)
                        )

                    self.assertEqual(
                        str(caught.exception),
                        "staged artifact discard target is unsafe",
                    )
                    self.assertIs(store.state, original_state)
                    self.assertEqual(
                        safe_path.read_text(encoding="utf-8"),
                        "safe",
                    )
                    self.assertEqual(
                        managed_child.read_text(encoding="utf-8"),
                        "managed",
                    )
                    self.assertEqual(
                        staged_path.read_text(encoding="utf-8"),
                        "staged",
                    )

    def test_discard_staged_paths_rejects_absolute_hint_entry_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            safe_path = root / "nodes" / "safe.txt"
            tracked_path = root / "nodes" / "tracked.txt"
            safe_path.parent.mkdir(parents=True)
            safe_path.write_text("safe", encoding="utf-8")
            tracked_path.write_text("tracked", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "tracked": StagedArtifactEntry(
                            artifact_id="tracked",
                            absolute_path_hint=str(tracked_path),
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state

            with self.assertRaises(ValueError) as caught:
                store.discard_staged_paths(
                    ("nodes/safe.txt", "nodes/tracked.txt")
                )

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertIs(store.state, original_state)
            self.assertEqual(safe_path.read_text(encoding="utf-8"), "safe")
            self.assertEqual(
                tracked_path.read_text(encoding="utf-8"),
                "tracked",
            )

    def test_discard_staged_paths_rejects_managed_protected_reparse_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            selected_path = root / "nodes" / "output.txt"
            junction = root / "workspaces" / "junction"
            protected_path = junction / "tracked.txt"
            selected_path.parent.mkdir(parents=True)
            protected_path.parent.mkdir(parents=True)
            selected_path.write_text("selected", encoding="utf-8")
            protected_path.write_text("protected", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata={
                    "artifacts": {
                        "protected": {
                            "relative_path": "workspaces/junction/tracked.txt"
                        }
                    },
                    "staging_root": {
                        "kind": "session_temp",
                        "absolute_path": str(root),
                    },
                },
            )
            original_state = store.state
            hint = store.staging_root_hint
            junction_key = os.path.normcase(os.path.abspath(junction))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == junction_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_paths(("nodes/output.txt",))

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertNotIn(str(root), str(caught.exception))
            self.assertNotIn(str(protected_path), str(caught.exception))
            self.assertIs(store.state, original_state)
            self.assertIs(store.staging_root_hint, hint)
            self.assertEqual(set(store.state.artifacts), {"protected"})
            self.assertEqual(
                selected_path.read_text(encoding="utf-8"),
                "selected",
            )
            self.assertEqual(
                protected_path.read_text(encoding="utf-8"),
                "protected",
            )
            self.assertTrue(root.is_dir())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_discard_staged_paths_allows_missing_protected_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "staging"
            selected_path = root / "nodes" / "output.txt"
            selected_path.parent.mkdir(parents=True)
            (root / "workspaces").mkdir()
            selected_path.write_text("selected", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=None,
                metadata=ArtifactStoreState(
                    staged={
                        "missing": StagedArtifactEntry(
                            artifact_id="missing",
                            relative_path="workspaces/missing/tracked.txt",
                        )
                    },
                    staging_root=StagingRootHint(
                        kind="session_temp",
                        absolute_path=str(root),
                    ),
                ),
            )
            original_state = store.state
            hint = store.staging_root_hint

            self.assertEqual(
                store.discard_staged_paths(("nodes/output.txt",)),
                ("nodes/output.txt",),
            )

            self.assertIs(store.state, original_state)
            self.assertIs(store.staging_root_hint, hint)
            self.assertFalse(selected_path.exists())
            self.assertEqual(set(store.state.staged), {"missing"})
            self.assertTrue(root.is_dir())
            self.assertTrue((root / "nodes").is_dir())
            self.assertTrue((root / "workspaces").is_dir())

    def test_discard_staged_paths_rejects_reparse_target_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProjectArtifactStore(project_path=None, metadata=None)
            root = store.ensure_staging_root(temporary_root_parent=temp_dir)
            safe_path = root / "nodes" / "safe.txt"
            junction = root / "workspaces" / "junction"
            target = junction / "payload.txt"
            safe_path.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            safe_path.write_text("safe", encoding="utf-8")
            target.write_text("keep", encoding="utf-8")
            original_state = store.state
            junction_key = os.path.normcase(os.path.abspath(junction))
            real_lstat = os.lstat

            def reparse_lstat(path: str | os.PathLike[str]) -> object:
                result = real_lstat(path)
                if os.path.normcase(os.path.abspath(path)) == junction_key:
                    return SimpleNamespace(
                        st_mode=result.st_mode,
                        st_file_attributes=0x400,
                    )
                return result

            with (
                patch(
                    "ea_node_editor.persistence.artifact_store.os.lstat",
                    side_effect=reparse_lstat,
                ),
                self.assertRaises(ValueError) as caught,
            ):
                store.discard_staged_paths(
                    ("nodes/safe.txt", "workspaces/junction/payload.txt")
                )

            self.assertEqual(
                str(caught.exception),
                "staged artifact discard target is unsafe",
            )
            self.assertIs(store.state, original_state)
            self.assertEqual(safe_path.read_text(encoding="utf-8"), "safe")
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_rename_node_artifact_folder_updates_readable_folder_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            store = ProjectArtifactStore(project_path=project_path, metadata=None)
            root = store.ensure_staging_root()
            before = store.node_artifact_paths(
                artifact_id="image",
                workspace_id="ws",
                node_id="node",
                node_title="Old Title",
                node_type="Image Panel",
                io_dir="in",
                subdirectory="media",
                filename="image.png",
            )
            old_file = root.joinpath(*PurePosixPath(before.managed_relative_path).parts)
            old_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.write_text("payload", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "image": {
                            "relative_path": before.managed_relative_path,
                            **before.metadata,
                        }
                    }
                },
            )

            changed = store.rename_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                old_title="Old Title",
                new_title="New Title",
                node_type="Image Panel",
            )

            after = store.node_artifact_paths(
                artifact_id="image",
                workspace_id="ws",
                node_id="node",
                node_title="New Title",
                node_type="Image Panel",
                io_dir="in",
                subdirectory="media",
                filename="image.png",
            )
            new_file = root.joinpath(*PurePosixPath(after.managed_relative_path).parts)
            self.assertTrue(changed)
            self.assertEqual(before.node_folder.rsplit("[", 1)[-1], after.node_folder.rsplit("[", 1)[-1])
            self.assertFalse(old_file.exists())
            self.assertEqual(new_file.read_text(encoding="utf-8"), "payload")
            self.assertEqual(store.metadata["artifacts"]["image"]["relative_path"], after.managed_relative_path)
            self.assertEqual(store.metadata["artifacts"]["image"]["node_folder"], after.node_folder)

    def test_rename_node_artifact_folder_permission_denied_leaves_old_folder_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            store = ProjectArtifactStore(project_path=project_path, metadata=None)
            root = store.ensure_staging_root()
            before = store.node_artifact_paths(
                artifact_id="video",
                workspace_id="ws",
                node_id="node",
                node_title="Old Title",
                node_type="Video Panel",
                io_dir="in",
                subdirectory="media",
                filename="clip.mp4",
            )
            old_file = root.joinpath(*PurePosixPath(before.managed_relative_path).parts)
            old_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.write_bytes(b"video")
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "video": {
                            "relative_path": before.managed_relative_path,
                            **before.metadata,
                        }
                    }
                },
            )

            with patch("ea_node_editor.persistence.artifact_store.shutil.move", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    store.rename_node_artifact_folder(
                        workspace_id="ws",
                        node_id="node",
                        old_title="Old Title",
                        new_title="New Title",
                        node_type="Video Panel",
                    )

            after = store.node_artifact_paths(
                artifact_id="video",
                workspace_id="ws",
                node_id="node",
                node_title="New Title",
                node_type="Video Panel",
                io_dir="in",
                subdirectory="media",
                filename="clip.mp4",
            )
            self.assertTrue(old_file.exists())
            self.assertFalse(root.joinpath(*PurePosixPath(after.managed_relative_path).parts).exists())
            self.assertEqual(store.metadata["artifacts"]["video"]["relative_path"], before.managed_relative_path)
            self.assertEqual(store.metadata["artifacts"]["video"]["node_folder"], before.node_folder)

    def test_migrate_workspace_artifact_folders_moves_registered_legacy_payloads_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            layout = ProjectArtifactLayout.from_project_path(project_path)
            node_folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_title="Image",
                node_type="Image Panel",
            )
            workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
            legacy_saved_relative = f"nodes/{node_folder}/in/media/image.png"
            legacy_staged_relative = f"nodes/{node_folder}/tmp/out/generated/run.txt"
            saved_path = layout.absolute_path_for_relative(legacy_saved_relative)
            staged_path = layout.absolute_path_for_relative(legacy_staged_relative)
            saved_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            saved_path.write_text("saved", encoding="utf-8")
            staged_path.write_text("staged", encoding="utf-8")
            sibling = saved_path.with_name("keep.txt")
            sibling.write_text("unknown", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "image": {
                            "relative_path": legacy_saved_relative,
                            "node_workspace_id": "ws",
                            "node_workspace_name": "Old",
                            "node_id": "node",
                            "node_title": "Image",
                            "node_type": "Image Panel",
                            "node_folder": node_folder,
                        }
                    },
                    "staged": {
                        "pending": {
                            "relative_path": legacy_staged_relative,
                            "node_workspace_id": "ws",
                            "node_id": "node",
                            "managed_relative_path": f"nodes/{node_folder}/out/generated/run.txt",
                        }
                    },
                },
            )

            changed = store.migrate_workspace_artifact_folders(
                workspaces={"ws": SimpleNamespace(workspace_id="ws", name="Main", nodes={})}
            )

            new_saved_relative = f"workspaces/{workspace_folder}/{legacy_saved_relative}"
            new_staged_relative = f"workspaces/{workspace_folder}/{legacy_staged_relative}"
            self.assertTrue(changed)
            self.assertFalse(saved_path.exists())
            self.assertFalse(staged_path.exists())
            self.assertTrue(sibling.exists())
            self.assertEqual(layout.absolute_path_for_relative(new_saved_relative).read_text(encoding="utf-8"), "saved")
            self.assertEqual(layout.absolute_path_for_relative(new_staged_relative).read_text(encoding="utf-8"), "staged")
            self.assertEqual(store.metadata["artifacts"]["image"]["relative_path"], new_saved_relative)
            self.assertEqual(store.metadata["artifacts"]["image"]["workspace_folder"], workspace_folder)
            self.assertEqual(store.metadata["artifacts"]["image"]["node_workspace_name"], "Main")
            self.assertEqual(store.metadata["staged"]["pending"]["relative_path"], new_staged_relative)
            self.assertEqual(
                store.metadata["staged"]["pending"]["managed_relative_path"],
                f"workspaces/{workspace_folder}/nodes/{node_folder}/out/generated/run.txt",
            )

    def test_migrate_workspace_artifact_folders_skips_empty_store_without_owner_scan(self) -> None:
        store = ProjectArtifactStore(project_path=None, metadata=None)

        with patch(
            "ea_node_editor.persistence.artifact_store._artifact_owner_lookup",
            side_effect=AssertionError("owner lookup should not run"),
        ):
            changed = store.migrate_workspace_artifact_folders(workspaces={})

        self.assertFalse(changed)

    def test_migrate_workspace_artifact_folders_skips_workspace_scoped_store(self) -> None:
        seed = ProjectArtifactStore(project_path=None, metadata=None)
        paths = seed.node_artifact_paths(
            artifact_id="image",
            workspace_id="ws",
            workspace_name="Main",
            node_id="node",
            node_title="Image",
            node_type="Image Panel",
            io_dir="in",
            filename="image.png",
        )
        metadata = {
            "artifacts": {
                "image": {
                    "relative_path": paths.managed_relative_path,
                    **paths.metadata,
                }
            },
            "staged": {
                "pending": {
                    "relative_path": paths.staged_relative_path,
                    **paths.metadata,
                }
            },
        }
        store = ProjectArtifactStore(project_path=None, metadata=metadata)

        with (
            patch(
                "ea_node_editor.persistence.artifact_store._artifact_owner_lookup",
                side_effect=AssertionError("owner lookup should not run"),
            ),
            patch.object(
                ProjectArtifactStore,
                "_workspace_scoped_managed_entry",
                side_effect=AssertionError("managed migration scan should not run"),
            ),
            patch.object(
                ProjectArtifactStore,
                "_workspace_scoped_staged_entry",
                side_effect=AssertionError("staged migration scan should not run"),
            ),
        ):
            changed = store.migrate_workspace_artifact_folders(
                workspaces={"ws": SimpleNamespace(workspace_id="ws", name="Main", nodes={})}
            )

        self.assertFalse(changed)
        self.assertEqual(store.metadata, normalize_artifact_store_metadata(metadata))

    def test_migrate_workspace_artifact_folders_preserves_mixed_store_results(self) -> None:
        workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
        node_folder = format_node_artifact_folder(
            workspace_id="ws",
            node_id="node",
            node_title="Image",
            node_type="Image Panel",
        )
        legacy_relative = f"nodes/{node_folder}/in/legacy.png"
        scoped_relative = f"workspaces/{workspace_folder}/nodes/{node_folder}/in/scoped.png"
        scoped_entry = {
            "relative_path": scoped_relative,
            "node_workspace_id": "ws",
            "node_workspace_name": "Main",
            "workspace_folder": workspace_folder,
            "node_id": "node",
            "node_title": "Image",
            "node_type": "Image Panel",
            "node_folder": node_folder,
        }
        store = ProjectArtifactStore(
            project_path=None,
            metadata={
                "artifacts": {
                    "legacy": {"relative_path": legacy_relative},
                    "scoped": scoped_entry,
                }
            },
        )
        node = SimpleNamespace(
            node_id="node",
            title="Image",
            type_id="Image Panel",
            properties={"legacy": "saved://legacy", "scoped": "saved://scoped"},
        )

        changed = store.migrate_workspace_artifact_folders(
            workspaces={
                "ws": SimpleNamespace(
                    workspace_id="ws",
                    name="Main",
                    nodes={"node": node},
                )
            }
        )

        self.assertTrue(changed)
        self.assertEqual(
            store.metadata["artifacts"]["legacy"]["relative_path"],
            f"workspaces/{workspace_folder}/{legacy_relative}",
        )
        self.assertEqual(store.metadata["artifacts"]["legacy"]["node_workspace_id"], "ws")
        self.assertEqual(store.metadata["artifacts"]["scoped"], scoped_entry)

    def test_rename_workspace_artifact_folder_updates_readable_workspace_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "demo.cxproj"
            store = ProjectArtifactStore(project_path=project_path, metadata=None)
            root = store.ensure_staging_root()
            before = store.node_artifact_paths(
                artifact_id="image",
                workspace_id="ws",
                workspace_name="Old Workspace",
                node_id="node",
                node_title="Image",
                node_type="Image Panel",
                io_dir="in",
                subdirectory="media",
                filename="image.png",
            )
            old_file = root.joinpath(*PurePosixPath(before.managed_relative_path).parts)
            old_file.parent.mkdir(parents=True, exist_ok=True)
            old_file.write_text("payload", encoding="utf-8")
            store = ProjectArtifactStore(
                project_path=project_path,
                metadata={
                    "artifacts": {
                        "image": {
                            "relative_path": before.managed_relative_path,
                            **before.metadata,
                        }
                    }
                },
            )

            changed = store.rename_workspace_artifact_folder(
                workspace_id="ws",
                old_name="Old Workspace",
                new_name="New Workspace",
            )

            after = store.node_artifact_paths(
                artifact_id="image",
                workspace_id="ws",
                workspace_name="New Workspace",
                node_id="node",
                node_title="Image",
                node_type="Image Panel",
                io_dir="in",
                subdirectory="media",
                filename="image.png",
            )
            new_file = root.joinpath(*PurePosixPath(after.managed_relative_path).parts)
            self.assertTrue(changed)
            self.assertEqual(before.workspace_folder.rsplit("[", 1)[-1], after.workspace_folder.rsplit("[", 1)[-1])
            self.assertFalse(old_file.exists())
            self.assertEqual(new_file.read_text(encoding="utf-8"), "payload")
            self.assertEqual(store.metadata["artifacts"]["image"]["relative_path"], after.managed_relative_path)
            self.assertEqual(store.metadata["artifacts"]["image"]["workspace_folder"], after.workspace_folder)
            self.assertEqual(store.metadata["artifacts"]["image"]["node_workspace_name"], "New Workspace")

    def test_artifact_ref_helpers_keep_saved_and_temporary_refs_distinct(self) -> None:
        managed = parse_artifact_ref("saved://diagram_asset")
        staged = parse_artifact_ref("temp://diagram_asset")

        self.assertEqual(managed, ManagedArtifactRef("diagram_asset"))
        self.assertEqual(staged, StagedArtifactRef("diagram_asset"))
        self.assertEqual(format_managed_artifact_ref("diagram_asset"), "saved://diagram_asset")
        self.assertEqual(format_staged_artifact_ref("diagram_asset"), "temp://diagram_asset")

    def test_stage_project_save_is_copy_on_write_and_suffixes_full_digest_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source.cxproj"
            destination_project = root / "destination.cxproj"
            workspace_folder = format_workspace_artifact_folder(
                workspace_id="ws", workspace_name="Main"
            )
            node_folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_type="Node",
            )
            relative = f"workspaces/{workspace_folder}/nodes/{node_folder}/out/value.bin"
            staged_relative = f"workspaces/{workspace_folder}/nodes/{node_folder}/tmp/out/new.bin"
            source_layout = ProjectArtifactLayout.from_project_path(source_project)
            source_managed = source_layout.absolute_path_for_relative(relative)
            source_staged = source_layout.absolute_path_for_relative(staged_relative)
            source_managed.parent.mkdir(parents=True, exist_ok=True)
            source_staged.parent.mkdir(parents=True, exist_ok=True)
            source_managed.write_bytes(b"source-managed")
            source_staged.write_bytes(b"source-staged")
            store = ProjectArtifactStore(
                project_path=source_project,
                metadata={
                    "artifacts": {
                        "managed": {
                            "relative_path": relative,
                            "node_workspace_id": "ws",
                            "node_workspace_name": "Main",
                            "node_id": "node",
                            "node_type": "Node",
                        }
                    },
                    "staged": {
                        "staged": {
                            "relative_path": staged_relative,
                            "managed_relative_path": relative,
                            "node_workspace_id": "ws",
                            "node_workspace_name": "Main",
                            "node_id": "node",
                            "node_type": "Node",
                        }
                    },
                },
            )
            destination_layout = ProjectArtifactLayout.from_project_path(
                destination_project
            )
            conflicting = destination_layout.absolute_path_for_relative(relative)
            conflicting.parent.mkdir(parents=True, exist_ok=True)
            conflicting.write_bytes(b"committed-winner")

            stage = store.stage_project_save(
                destination_project_path=destination_project,
                workspaces={"ws": SimpleNamespace(name="Main", nodes={})},
                referenced_managed_ids=("managed",),
                referenced_staged_ids=("staged",),
            )

            digest = hashlib.sha256(b"source-staged").hexdigest()
            staged_entry = stage.destination_store.managed_entry("staged")
            self.assertIsNotNone(staged_entry)
            self.assertIn(digest, staged_entry.relative_path)
            self.assertEqual(conflicting.read_bytes(), b"committed-winner")
            self.assertEqual(source_managed.read_bytes(), b"source-managed")
            self.assertEqual(source_staged.read_bytes(), b"source-staged")
            copied = stage.destination_store.resolve_managed_path("staged")
            self.assertIsNotNone(copied)
            self.assertEqual(copied.read_bytes(), b"source-staged")
            self.assertEqual(stage.destination_store.metadata["staged"], {})

    def test_project_save_cleanup_protects_previous_then_allows_active_only_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project.cxproj"
            metadata = {
                "artifacts": {
                    "old": {"relative_path": "nodes/Old [11111111]/out/old.bin"},
                    "current": {"relative_path": "nodes/Current [22222222]/out/current.bin"},
                },
                "staged": {},
            }
            store = ProjectArtifactStore(project_path=project, metadata=metadata)
            old_path = store.resolve_managed_path("old")
            current_path = store.resolve_managed_path("current")
            old_path.parent.mkdir(parents=True, exist_ok=True)
            current_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.write_bytes(b"old")
            current_path.write_bytes(b"current")

            stage = store.stage_project_save(
                destination_project_path=project,
                workspaces={},
                referenced_managed_ids=("current",),
            )
            first = ProjectArtifactStore.collect_project_save_garbage(
                project_path=project,
                candidate_relative_paths=stage.cleanup_candidates,
                protected_relative_paths=(
                    *stage.previous_relative_paths,
                    *stage.retained_relative_paths,
                ),
            )
            self.assertEqual(first.removed_relative_paths, ())
            self.assertEqual(first.remaining_relative_paths, stage.cleanup_candidates)
            self.assertTrue(first.has_more)
            self.assertTrue(old_path.exists())

            second = ProjectArtifactStore.collect_project_save_garbage(
                project_path=project,
                candidate_relative_paths=stage.cleanup_candidates,
                protected_relative_paths=stage.retained_relative_paths,
            )
            self.assertEqual(
                second.removed_relative_paths,
                (metadata["artifacts"]["old"]["relative_path"],),
            )
            self.assertFalse(second.has_more)
            self.assertFalse(old_path.exists())
            self.assertTrue(current_path.exists())

    def test_project_artifact_gc_partial_batch_returns_retryable_remaining_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project.cxproj"
            root = ProjectArtifactLayout.from_project_path(project).sidecar_root
            candidates = (
                "nodes/Old [11111111]/out/a.bin",
                "nodes/Old [11111111]/out/b.bin",
            )
            for relative in candidates:
                path = root.joinpath(*PurePosixPath(relative).parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode("utf-8"))
            first = ProjectArtifactStore.collect_project_save_garbage(
                project_path=project,
                candidate_relative_paths=candidates,
                protected_relative_paths=(),
                limit=1,
            )
            self.assertTrue(first.has_more)
            self.assertEqual(len(first.removed_relative_paths), 1)
            self.assertEqual(len(first.remaining_relative_paths), 1)
            second = ProjectArtifactStore.collect_project_save_garbage(
                project_path=project,
                candidate_relative_paths=first.remaining_relative_paths,
                protected_relative_paths=(),
            )
            self.assertFalse(second.has_more)
            self.assertEqual(second.remaining_relative_paths, ())


if __name__ == "__main__":
    unittest.main()
