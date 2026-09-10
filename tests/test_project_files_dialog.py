from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import format_node_artifact_folder, format_workspace_artifact_folder
from ea_node_editor.ui.dialogs.project_files_dialog import (
    ProjectFilesBrokenEntry,
    ProjectFilesDialog,
    ProjectFilesManagedEntry,
    ProjectFilesSnapshot,
    ProjectFilesStagedEntry,
)
from ea_node_editor.ui.shell.controllers.project_session_controller import ProjectSessionController
from ea_node_editor.ui.shell.state import ShellProjectSessionState


class _ProjectFilesHostStub:
    def __init__(self, *, project_path: str, model: GraphModel) -> None:
        self.project_session_state = ShellProjectSessionState()
        self.session_store = object()
        self.registry = build_default_registry()
        self.model = model
        self.workspace_manager = object()
        self.runtime_history = object()
        self.serializer = object()
        self.workspace_navigation_controller = object()
        self.script_editor = object()
        self.action_toggle_script_editor = object()
        self.scene = object()
        self.project_meta_changed = object()
        self.project_path = project_path

    def _refresh_recent_projects_menu(self) -> None:
        return

    def _prompt_recover_autosave(self, recovered_project=None):  # noqa: ANN001, ANN201
        return None

    def browse_node_property_path(self, node_id: str, key: str, current_path: str) -> str:
        return ""

    @staticmethod
    def isVisible() -> bool:
        return True


class ProjectFilesSnapshotTests(unittest.TestCase):
    def test_controller_builds_snapshot_from_managed_staged_and_broken_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_path = root / "project_files_demo.cxproj"

            model = GraphModel()
            workspace = model.active_workspace
            managed_node = model.add_node(
                workspace.workspace_id,
                "media.panel",
                "Managed Panel",
                80.0,
                40.0,
                properties={"source": format_managed_artifact_ref("managed_image")},
                exposed_ports={"source": False},
            )
            staged_node = model.add_node(
                workspace.workspace_id,
                "media.panel",
                "Staged Panel",
                220.0,
                40.0,
                properties={"source": format_staged_artifact_ref("pending_output")},
                exposed_ports={"source": False},
            )
            broken_node = model.add_node(
                workspace.workspace_id,
                "media.panel",
                "Broken Panel",
                360.0,
                40.0,
                properties={"source": str(root / "missing-image.png")},
                exposed_ports={"source": False},
            )
            managed_folder = format_node_artifact_folder(
                workspace_id=workspace.workspace_id,
                node_id=managed_node.node_id,
                node_title=managed_node.title,
                node_type="Image Panel",
            )
            staged_folder = format_node_artifact_folder(
                workspace_id=workspace.workspace_id,
                node_id=staged_node.node_id,
                node_title=staged_node.title,
                node_type="Image Panel",
            )
            workspace_folder = format_workspace_artifact_folder(
                workspace_id=workspace.workspace_id,
                workspace_name=workspace.name,
            )
            managed_path = (
                project_path.with_name("project_files_demo.data")
                / "workspaces"
                / workspace_folder
                / "nodes"
                / managed_folder
                / "in"
                / "media"
                / "diagram.png"
            )
            managed_path.parent.mkdir(parents=True, exist_ok=True)
            managed_path.write_text("managed", encoding="utf-8")
            staged_path = (
                project_path.with_name("project_files_demo.data")
                / "workspaces"
                / workspace_folder
                / "nodes"
                / staged_folder
                / "tmp"
                / "out"
                / "outputs"
                / "run.txt"
            )
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text("staged", encoding="utf-8")
            model.project.metadata = {
                "artifact_store": {
                    "artifacts": {
                        "managed_image": {
                            "relative_path": f"workspaces/{workspace_folder}/nodes/{managed_folder}/in/media/diagram.png",
                        }
                    },
                    "staged": {
                        "pending_output": {
                            "relative_path": f"workspaces/{workspace_folder}/nodes/{staged_folder}/tmp/out/outputs/run.txt",
                            "slot": "process_run.stdout",
                        }
                    },
                }
            }

            controller = ProjectSessionController(
                _ProjectFilesHostStub(project_path=str(project_path), model=model)  # type: ignore[arg-type]
            )

            snapshot = controller.build_project_files_snapshot()

        self.assertEqual(snapshot.managed_count, 1)
        self.assertEqual(snapshot.staged_count, 1)
        self.assertEqual(snapshot.broken_count, 1)
        self.assertEqual(snapshot.data_root_path, str(project_path.with_name("project_files_demo.data")))
        self.assertEqual(
            snapshot.staging_root_path,
            str(project_path.with_name("project_files_demo.data") / "workspaces"),
        )
        self.assertEqual(snapshot.managed_entries[0].artifact_id, "managed_image")
        self.assertTrue(snapshot.managed_entries[0].exists)
        self.assertEqual(snapshot.staged_entries[0].slot, "process_run.stdout")
        self.assertTrue(snapshot.staged_entries[0].exists)
        self.assertEqual(snapshot.broken_entries[0].node_id, broken_node.node_id)
        self.assertEqual(snapshot.broken_entries[0].property_label, "Source")
        self.assertIn("no longer exists", snapshot.broken_entries[0].message)


class ProjectFilesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _snapshot(*, broken_count: int = 1) -> ProjectFilesSnapshot:
        broken_entries = ()
        if broken_count:
            broken_entries = (
                ProjectFilesBrokenEntry(
                    workspace_id="ws_1",
                    workspace_name="Main",
                    node_id="node_broken",
                    node_title="Broken Image",
                    property_key="source",
                    property_label="Image Source",
                    current_value="/tmp/missing.png",
                    issue_kind="external_missing",
                    source_kind="external_missing",
                    source_mode="external_link",
                    message="Image Source points to a file that no longer exists.",
                ),
            )
        return ProjectFilesSnapshot(
            project_path="/tmp/demo_project.cxproj",
            data_root_path="/tmp/demo_project.data",
            staging_root_path="/tmp/demo_project.data/workspaces",
            managed_entries=(
                ProjectFilesManagedEntry(
                    artifact_id="managed_image",
                    relative_path="workspaces/Main [abcd1234]/nodes/Image Panel - Managed Panel [1234abcd]/in/media/diagram.png",
                    absolute_path="/tmp/demo_project.data/workspaces/Main [abcd1234]/nodes/Image Panel - Managed Panel [1234abcd]/in/media/diagram.png",
                    exists=True,
                ),
            ),
            staged_entries=(
                ProjectFilesStagedEntry(
                    artifact_id="pending_output",
                    relative_path="workspaces/Main [abcd1234]/nodes/Process Run - Process [5678abcd]/tmp/out/outputs/run.txt",
                    absolute_path="/tmp/demo_project.data/workspaces/Main [abcd1234]/nodes/Process Run - Process [5678abcd]/tmp/out/outputs/run.txt",
                    slot="process_run.stdout",
                    exists=True,
                ),
            ),
            broken_entries=broken_entries,
        )

    def test_dialog_renders_project_file_counts_and_entries(self) -> None:
        dialog = ProjectFilesDialog(snapshot=self._snapshot(), repair_callback=lambda _entry: True)
        self.addCleanup(dialog.deleteLater)

        self.assertIn("demo_project.cxproj", dialog.project_label.text())
        self.assertEqual(dialog.summary_label.text(), "1 saved file, 1 temporary file, 1 broken file entry")
        self.assertEqual(dialog.managed_tree.topLevelItemCount(), 1)
        self.assertEqual(dialog.staged_tree.topLevelItemCount(), 1)
        self.assertEqual(dialog.broken_tree.topLevelItemCount(), 1)
        self.assertTrue(dialog.repair_button.isEnabled())

    def test_dialog_repair_refreshes_snapshot_and_disables_button_when_issues_are_cleared(self) -> None:
        repaired_entries: list[ProjectFilesBrokenEntry] = []

        def repair(entry: ProjectFilesBrokenEntry) -> bool:
            repaired_entries.append(entry)
            return True

        dialog = ProjectFilesDialog(
            snapshot=self._snapshot(),
            repair_callback=repair,
            refresh_snapshot_callback=lambda: self._snapshot(broken_count=0),
        )
        self.addCleanup(dialog.deleteLater)

        dialog.repair_button.click()
        self.app.processEvents()

        self.assertEqual(len(repaired_entries), 1)
        self.assertEqual(repaired_entries[0].node_id, "node_broken")
        self.assertEqual(dialog.broken_summary_label.text(), "Broken file entries (0)")
        self.assertEqual(dialog.broken_tree.topLevelItemCount(), 1)
        self.assertFalse(dialog.repair_button.isEnabled())


def load_tests(loader, _tests, _pattern):  # noqa: ANN001
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(ProjectFilesSnapshotTests))
    suite.addTests(loader.loadTestsFromTestCase(ProjectFilesDialogTests))
    return suite
