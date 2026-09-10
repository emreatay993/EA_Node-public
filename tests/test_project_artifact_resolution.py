from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ea_node_editor.common.artifact_refs import format_managed_artifact_ref, format_staged_artifact_ref
from ea_node_editor.persistence.artifact_resolution import ProjectArtifactResolver
from ea_node_editor.persistence.artifact_store import format_node_artifact_folder, format_workspace_artifact_folder


class ProjectArtifactResolutionTests(unittest.TestCase):
    def test_resolve_external_absolute_path_and_file_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            absolute_path = Path(temp_dir) / "image.png"
            resolver = ProjectArtifactResolver(project_path=None, project_metadata=None)

            path_resolution = resolver.resolve(str(absolute_path))
            url_resolution = resolver.resolve(absolute_path.as_uri())

        self.assertEqual(path_resolution.kind, "external_path")
        self.assertEqual(path_resolution.absolute_path, absolute_path)
        self.assertTrue(path_resolution.resolved)
        self.assertEqual(url_resolution.kind, "external_file_url")
        self.assertEqual(url_resolution.absolute_path, absolute_path)
        self.assertTrue(url_resolution.resolved)

    def test_resolve_managed_artifact_ref_uses_project_sidecar_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact_demo.cxproj"
            workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
            folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_title="Image",
                node_type="Image Panel",
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                project_metadata={
                    "artifact_store": {
                        "artifacts": {
                            "image_source": {
                                "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/in/media/diagram.png"
                            },
                        }
                    }
                },
            )

            resolution = resolver.resolve(format_managed_artifact_ref("image_source"))

        self.assertEqual(resolution.kind, "managed")
        self.assertEqual(resolution.artifact_id, "image_source")
        self.assertEqual(
            resolution.absolute_path,
            project_path.with_name("artifact_demo.data")
            / "workspaces"
            / workspace_folder
            / "nodes"
            / folder
            / "in"
            / "media"
            / "diagram.png",
        )

    def test_resolve_staged_artifact_ref_uses_staging_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact_demo.cxproj"
            workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
            folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_title="Writer",
                node_type="File Write",
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                project_metadata={
                    "artifact_store": {
                        "staged": {
                            "pending_output": {
                                "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/tmp/out/outputs/stdout.txt"
                            },
                        }
                    }
                },
            )

            resolution = resolver.resolve(format_staged_artifact_ref("pending_output"))

        self.assertEqual(resolution.kind, "staged")
        self.assertEqual(resolution.artifact_id, "pending_output")
        self.assertEqual(
            resolution.absolute_path,
            project_path.with_name("artifact_demo.data")
            / "workspaces"
            / workspace_folder
            / "nodes"
            / folder
            / "tmp"
            / "out"
            / "outputs"
            / "stdout.txt",
        )

    def test_resolve_to_path_supports_managed_preview_consumers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "artifact_demo.cxproj"
            workspace_folder = format_workspace_artifact_folder(workspace_id="ws", workspace_name="Main")
            folder = format_node_artifact_folder(
                workspace_id="ws",
                node_id="node",
                node_title="Preview",
                node_type="Image Panel",
            )
            resolver = ProjectArtifactResolver(
                project_path=project_path,
                project_metadata={
                    "artifact_store": {
                        "artifacts": {
                            "preview_asset": {
                                "relative_path": f"workspaces/{workspace_folder}/nodes/{folder}/out/media/preview.png"
                            },
                        }
                    }
                },
            )

            resolved_path = resolver.resolve_to_path(format_managed_artifact_ref("preview_asset"))

        self.assertEqual(
            resolved_path,
            project_path.with_name("artifact_demo.data")
            / "workspaces"
            / workspace_folder
            / "nodes"
            / folder
            / "out"
            / "media"
            / "preview.png",
        )

    def test_unknown_managed_and_staged_refs_report_missing(self) -> None:
        resolver = ProjectArtifactResolver(
            project_path=Path("/tmp/demo.cxproj"),
            project_metadata={"artifact_store": {"artifacts": {}, "staged": {}}},
        )

        missing_managed = resolver.resolve("saved://missing_asset")
        missing_staged = resolver.resolve("temp://missing_stage")
        unresolved = resolver.resolve("relative/path.png")

        self.assertEqual(missing_managed.kind, "managed_missing")
        self.assertIsNone(missing_managed.absolute_path)
        self.assertEqual(missing_staged.kind, "staged_missing")
        self.assertIsNone(missing_staged.absolute_path)
        self.assertEqual(unresolved.kind, "unresolved")
        self.assertIsNone(unresolved.absolute_path)


if __name__ == "__main__":
    unittest.main()
