from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ea_node_editor.graph.file_issue_state import encode_file_repair_request
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.common.artifact_refs import format_managed_artifact_ref
from ea_node_editor.persistence.file_issues import collect_workspace_file_issue_map
from tests.conftest import ShellTestEnvironment

_REPO_ROOT = Path(__file__).resolve().parents[1]


class ProjectFileIssueTests(unittest.TestCase):
    def test_collect_workspace_file_issues_tracks_missing_owner_and_consumer_sources_only(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace

        image_node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            80.0,
            80.0,
        )
        video_node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            200.0,
            80.0,
        )
        image_node.exposed_ports["source"] = False
        video_node.exposed_ports["source"] = False
        file_read_node = model.add_node(
            workspace.workspace_id,
            "io.file_read",
            "File Read",
            320.0,
            80.0,
        )
        file_write_node = model.add_node(
            workspace.workspace_id,
            "io.file_write",
            "File Write",
            560.0,
            80.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_path = temp_root / "issues_demo.cxproj"
            model.set_node_property(
                workspace.workspace_id,
                image_node.node_id,
                "source",
                str(temp_root / "missing-image.png"),
            )
            model.set_node_property(
                workspace.workspace_id,
                video_node.node_id,
                "source",
                str(temp_root / "missing-video.mp4"),
            )
            model.set_node_property(
                workspace.workspace_id,
                file_read_node.node_id,
                "path",
                format_managed_artifact_ref("missing_input"),
            )
            model.set_node_property(
                workspace.workspace_id,
                file_write_node.node_id,
                "path",
                "output.txt",
            )

            issue_map = collect_workspace_file_issue_map(
                workspace=workspace,
                registry=registry,
                project_path=str(project_path),
                project_metadata={
                    "artifact_store": {
                        "artifacts": {
                            "missing_input": {
                                "relative_path": "nodes/File Read [11111111]/in/files/missing-input.txt",
                            }
                        }
                    }
                },
            )

        self.assertEqual(issue_map[(image_node.node_id, "source")].issue_kind, "external_missing")
        video_issue = issue_map[(video_node.node_id, "source")]
        self.assertEqual(video_issue.issue_kind, "external_missing")
        self.assertTrue(video_issue.supports_managed_repair)
        self.assertTrue(video_issue.supports_external_repair)
        self.assertEqual(issue_map[(file_read_node.node_id, "path")].issue_kind, "managed_missing")
        self.assertEqual(issue_map[(file_read_node.node_id, "path")].source_mode, "managed_copy")
        self.assertNotIn((file_write_node.node_id, "path"), issue_map)

    def test_shell_window_repairs_missing_external_consumer_path_without_managed_metadata(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ea_node_editor.ui.shell.window import ShellWindow

        app = QApplication.instance() or QApplication([])
        test_env = ShellTestEnvironment()
        temp_root = test_env.start()
        window = ShellWindow()
        try:
            repaired_path = temp_root / "repaired-input.txt"
            repaired_path.write_text("restored", encoding="utf-8")
            missing_path = str(temp_root / "missing-input.txt")

            node_id = window.scene.add_node_from_type("io.file_read", x=120.0, y=80.0)
            self.assertTrue(node_id)
            window.scene.set_node_property(node_id, "path", missing_path)
            window.scene.select_node(node_id, False)
            app.processEvents()

            path_item = _selected_property_item(window, "path")
            self.assertTrue(path_item["file_issue_active"])
            self.assertTrue(str(path_item["file_issue_request"]).startswith("ea-file-repair:"))

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(repaired_path), ""),
            ) as dialog_mock:
                relinked_path = window.browse_node_property_path(
                    node_id,
                    "path",
                    encode_file_repair_request(missing_path),
                )

            self.assertEqual(relinked_path, str(repaired_path))
            self.assertEqual(dialog_mock.call_count, 1)

            window.scene.set_node_property(node_id, "path", relinked_path)
            app.processEvents()

            path_item = _selected_property_item(window, "path")
            self.assertFalse(path_item["file_issue_active"])
            self.assertNotIn("artifact_store", window.model.project.metadata)
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
            test_env.stop()

    def test_exposed_media_source_suppresses_edit_browse_and_repair(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ea_node_editor.ui.shell.window import ShellWindow

        app = QApplication.instance() or QApplication([])
        test_env = ShellTestEnvironment()
        temp_root = test_env.start()
        window = ShellWindow()
        try:
            missing_path = str(temp_root / "dormant-missing.png")
            node_id = window.scene.create_node_from_type(
                type_id="media.panel",
                x=120.0,
                y=80.0,
                parent_node_id=None,
                select_node=False,
                property_overrides={"source": missing_path},
                exposed_port_overrides={"source": True},
            )
            window.scene.select_node(node_id, False)
            app.processEvents()

            source_item = _selected_property_item(window, "source")
            self.assertFalse(source_item["editor_enabled"])
            self.assertFalse(source_item["file_issue_active"])

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName"
            ) as dialog_mock:
                self.assertEqual(
                    window.browse_node_property_path(node_id, "source", missing_path),
                    "",
                )
            dialog_mock.assert_not_called()

            window.set_selected_node_property("source", "C:/blocked.png")
            self.assertEqual(
                window.model.active_workspace.nodes[node_id].properties["source"],
                missing_path,
            )
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
            test_env.stop()

    def test_shell_window_repairs_missing_managed_media_source_with_staged_copy(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ea_node_editor.ui.shell.window import ShellWindow

        app = QApplication.instance() or QApplication([])
        test_env = ShellTestEnvironment()
        temp_root = test_env.start()
        window = ShellWindow()
        try:
            source_fixture = _REPO_ROOT / "tests" / "fixtures" / "passive_nodes" / "reference_preview.png"
            managed_ref = format_managed_artifact_ref("managed_image")

            window.project_path = str(temp_root / "repair_demo.cxproj")
            window.model.project.metadata = {
                "artifact_store": {
                    "artifacts": {
                        "managed_image": {
                            "relative_path": "nodes/Image Panel [11111111]/in/media/missing.png",
                        }
                    }
                }
            }

            node_id = window.scene.add_node_from_type("media.panel", x=120.0, y=80.0)
            self.assertTrue(node_id)
            window.scene.set_exposed_port(node_id, "source", False)
            window.scene.set_node_property(node_id, "source", managed_ref)
            window.scene.select_node(node_id, False)
            app.processEvents()

            path_item = _selected_property_item(window, "source")
            self.assertTrue(path_item["file_issue_active"])

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QInputDialog.getItem",
                return_value=("Managed Copy", True),
            ) as mode_mock, patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(source_fixture), ""),
            ) as dialog_mock:
                repaired_ref = window.browse_node_property_path(
                    node_id,
                    "source",
                    encode_file_repair_request(managed_ref),
                )

            self.assertEqual(repaired_ref, "temp://managed_image")
            self.assertEqual(mode_mock.call_count, 1)
            self.assertEqual(dialog_mock.call_count, 1)

            window.scene.set_node_property(node_id, "source", repaired_ref)
            app.processEvents()

            path_item = _selected_property_item(window, "source")
            self.assertFalse(path_item["file_issue_active"])
            repaired_entry = window.model.project.metadata["artifact_store"]["staged"]["managed_image"]
            self.assertIn("/tmp/in/", repaired_entry["relative_path"])
            self.assertTrue(repaired_entry["relative_path"].endswith("/reference_preview.png"))
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
            test_env.stop()

    def test_shell_window_repairs_missing_staged_media_source_reusing_existing_artifact_id(self) -> None:
        from PyQt6.QtWidgets import QApplication

        from ea_node_editor.ui.shell.window import ShellWindow

        app = QApplication.instance() or QApplication([])
        test_env = ShellTestEnvironment()
        temp_root = test_env.start()
        window = ShellWindow()
        try:
            source_fixture = _REPO_ROOT / "tests" / "fixtures" / "passive_nodes" / "reference_preview.png"
            staged_ref = "temp://managed_image"

            window.project_path = str(temp_root / "repair_demo.cxproj")
            window.model.project.metadata = {
                "artifact_store": {
                    "staged": {
                        "managed_image": {
                            "relative_path": "nodes/Image Panel [11111111]/tmp/in/media/managed_image.png",
                        }
                    }
                }
            }

            node_id = window.scene.add_node_from_type("media.panel", x=120.0, y=80.0)
            self.assertTrue(node_id)
            window.scene.set_exposed_port(node_id, "source", False)
            window.scene.set_node_property(node_id, "source", staged_ref)
            window.scene.select_node(node_id, False)
            app.processEvents()

            path_item = _selected_property_item(window, "source")
            self.assertTrue(path_item["file_issue_active"])

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QInputDialog.getItem",
                return_value=("Managed Copy", True),
            ) as mode_mock, patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(source_fixture), ""),
            ) as dialog_mock:
                repaired_ref = window.browse_node_property_path(
                    node_id,
                    "source",
                    encode_file_repair_request(staged_ref),
                )

            self.assertEqual(repaired_ref, staged_ref)
            self.assertEqual(mode_mock.call_count, 1)
            self.assertEqual(dialog_mock.call_count, 1)

            store = ProjectArtifactStore.from_project_metadata(
                project_path=window.project_path,
                project_metadata=window.model.project.metadata,
            )
            staged_path = store.resolve_staged_path(staged_ref)
            self.assertIsNotNone(staged_path)
            assert staged_path is not None
            self.assertTrue(staged_path.exists())
            self.assertEqual(staged_path.read_bytes(), source_fixture.read_bytes())
            repaired_entry = window.model.project.metadata["artifact_store"]["staged"]["managed_image"]
            self.assertIn("/tmp/in/", repaired_entry["relative_path"])
            self.assertTrue(repaired_entry["relative_path"].endswith("/reference_preview.png"))
        finally:
            window.close()
            window.deleteLater()
            app.processEvents()
            test_env.stop()


def _selected_property_item(window, property_key: str) -> dict[str, object]:  # noqa: ANN001
    return next(
        item
        for item in window.selected_node_property_items
        if str(item.get("key", "")).strip() == property_key
    )


if __name__ == "__main__":
    unittest.main()
