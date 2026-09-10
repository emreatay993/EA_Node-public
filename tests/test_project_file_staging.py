from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.ui.shell.controllers.project_session_controller import (
    ProjectSessionController,
)
from ea_node_editor.ui.shell.controllers.project_session_services_support.project_files_service import (
    ProjectFilesService,
)


class _Signal:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self) -> None:
        self.calls += 1


class _SessionStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def staging_workspace_root(self) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root


class _Host:
    def __init__(self, root: Path, *, project_path: str = "") -> None:
        self.model = GraphModel()
        self.registry = build_default_registry()
        self.workspace_manager = SimpleNamespace(
            active_workspace_id=lambda: self.model.active_workspace.workspace_id
        )
        self.scene = SimpleNamespace(selected_node_id=lambda: "")
        self.session_store = _SessionStore(root / "session")
        self.project_path = project_path
        self.project_meta_changed = _Signal()


def _controller(host: _Host) -> ProjectSessionController:
    controller = ProjectSessionController.__new__(ProjectSessionController)
    controller._host = host  # noqa: SLF001
    controller._project_files_service = ProjectFilesService(  # noqa: SLF001
        host,
        dialog_parent_source=SimpleNamespace(),
        path_browser=SimpleNamespace(),
        workspace_session=SimpleNamespace(),
    )
    return controller


class ProjectFileStagingTests(unittest.TestCase):
    def test_file_staging_reuses_id_and_touches_same_metadata_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "first.csv"
            source.write_text("one\n", encoding="utf-8")
            host = _Host(root, project_path=str(root / "project.cxproj"))
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_revision = host.model.project.project_document_revision

            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as first_publication:
                first_ref = controller.stage_node_artifact_file(
                    source,
                    artifact_prefix="tabular_source",
                    artifact_id="tabular_source.weather",
                    io_dir="in",
                    subdirectory="tabular/source",
                    filename="tabular_source.weather.csv",
                    entry_metadata={"artifact_kind": "tabular_source"},
                )

            self.assertEqual(first_ref, "temp://tabular_source.weather")
            self.assertEqual(first_publication.call_count, 1)
            self.assertEqual(
                host.model.project.project_document_revision,
                before_revision + 1,
            )
            self.assertEqual(host.project_meta_changed.calls, 1)
            first_entry = controller.project_artifact_store().staged_entry(first_ref)
            self.assertIsNotNone(first_entry)
            assert first_entry is not None
            self.assertEqual(first_entry.extra["artifact_kind"], "tabular_source")
            self.assertEqual(first_entry.extra["io_dir"], "in")
            self.assertIn("/tmp/in/tabular/source/", first_entry.relative_path)
            self.assertIn(
                "/in/tabular/source/",
                first_entry.extra["managed_relative_path"],
            )

            first_revision = host.model.project.project_document_revision
            source.write_text("two\n", encoding="utf-8")
            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as second_publication:
                second_ref = controller.stage_node_artifact_file(
                    source,
                    artifact_prefix="tabular_source",
                    artifact_id="tabular_source.weather",
                    io_dir="in",
                    subdirectory="tabular/source",
                    filename="tabular_source.weather.csv",
                    entry_metadata={"artifact_kind": "tabular_source"},
                )

            self.assertEqual(first_ref, second_ref)
            self.assertEqual(second_publication.call_count, 1)
            self.assertEqual(
                host.model.project.project_document_revision, first_revision + 1
            )
            self.assertEqual(host.project_meta_changed.calls, 2)
            staged = controller.project_artifact_store().resolve_staged_path(second_ref)
            self.assertIsNotNone(staged)
            assert staged is not None
            self.assertIn("/tmp/in/tabular/source/", staged.as_posix())
            self.assertEqual(staged.read_text(encoding="utf-8"), "two\n")

    def test_file_staging_preserves_file_source_and_tabular_cache_layouts(self) -> None:
        cases = (
            {
                "label": "file source",
                "filename": "input.dat",
                "artifact_id": "source_file.input",
                "artifact_prefix": "source_file",
                "io_dir": "in",
                "subdirectory": "files",
                "artifact_kind": "source_file",
                "expected_staged": "/tmp/in/files/",
                "expected_managed": "/in/files/",
            },
            {
                "label": "tabular cache",
                "filename": "weather.parquet",
                "artifact_id": "tabular_cache.weather",
                "artifact_prefix": "tabular_cache",
                "io_dir": "out",
                "subdirectory": "tabular/cache",
                "artifact_kind": "tabular_cache",
                "expected_staged": "/tmp/out/tabular/cache/",
                "expected_managed": "/out/tabular/cache/",
            },
        )
        for case in cases:
            with (
                self.subTest(case=case["label"]),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                root = Path(temp_dir)
                source = root / str(case["filename"])
                source.write_bytes(b"source-bytes")
                host = _Host(root, project_path=str(root / "project.cxproj"))
                controller = _controller(host)
                service = controller._project_files_service  # noqa: SLF001
                before_revision = host.model.project.project_document_revision

                with patch.object(
                    service,
                    "replace_project_artifact_store",
                    wraps=service.replace_project_artifact_store,
                ) as publication:
                    ref = controller.stage_node_artifact_file(
                        source,
                        artifact_prefix=str(case["artifact_prefix"]),
                        artifact_id=str(case["artifact_id"]),
                        io_dir=str(case["io_dir"]),
                        subdirectory=str(case["subdirectory"]),
                        filename=str(case["filename"]),
                        entry_metadata={"artifact_kind": case["artifact_kind"]},
                        node_id="node-file",
                        node_title="File Node",
                        node_type="File",
                    )

                store = controller.project_artifact_store()
                entry = store.staged_entry(ref)
                path = store.resolve_staged_path(ref)
                self.assertIsNotNone(entry)
                self.assertIsNotNone(path)
                assert entry is not None and path is not None
                self.assertEqual(path.read_bytes(), b"source-bytes")
                self.assertIn(str(case["expected_staged"]), entry.relative_path)
                self.assertIn(
                    str(case["expected_managed"]),
                    entry.extra["managed_relative_path"],
                )
                self.assertEqual(entry.extra["artifact_kind"], case["artifact_kind"])
                self.assertEqual(entry.extra["io_dir"], case["io_dir"])
                self.assertEqual(entry.extra["node_id"], "node-file")
                self.assertEqual(entry.extra["node_title"], "File Node")
                self.assertEqual(entry.extra["node_type"], "File")
                self.assertEqual(publication.call_count, 1)
                self.assertEqual(
                    host.model.project.project_document_revision,
                    before_revision + 1,
                )
                self.assertEqual(host.project_meta_changed.calls, 1)

    def test_byte_staging_publishes_complete_integrity_metadata_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = _Host(root, project_path=str(root / "project.cxproj"))
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_revision = host.model.project.project_document_revision
            raw_data = b"clipboard-image"

            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as publication:
                byte_ref = controller.stage_node_artifact_bytes(
                    raw_data,
                    filename="paste.png",
                    mime_type="image/png",
                    artifact_prefix="clipboard_image",
                    subdirectory="media",
                    artifact_kind="clipboard_image_source",
                    node_id="node-image",
                    node_title="Image",
                    node_type="Media Panel",
                )

            store = controller.project_artifact_store()
            byte_entry = store.staged_entry(byte_ref)
            byte_path = store.resolve_staged_path(byte_ref)
            self.assertIsNotNone(byte_entry)
            self.assertIsNotNone(byte_path)
            assert byte_entry is not None and byte_path is not None
            self.assertEqual(byte_path.read_bytes(), raw_data)
            self.assertEqual(
                byte_entry.extra["artifact_kind"], "clipboard_image_source"
            )
            self.assertEqual(byte_entry.extra["mime_type"], "image/png")
            self.assertEqual(byte_entry.extra["size"], len(raw_data))
            self.assertEqual(
                byte_entry.extra["sha256"],
                hashlib.sha256(raw_data).hexdigest(),
            )
            self.assertEqual(byte_entry.extra["io_dir"], "in")
            self.assertEqual(byte_entry.extra["node_id"], "node-image")
            self.assertIn("/tmp/in/media/", byte_entry.relative_path)
            self.assertIn("/in/media/", byte_entry.extra["managed_relative_path"])
            self.assertEqual(publication.call_count, 1)
            self.assertEqual(
                host.model.project.project_document_revision,
                before_revision + 1,
            )
            self.assertEqual(host.project_meta_changed.calls, 1)

    def test_notebook_staging_writes_valid_notebook_and_publishes_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            import nbformat

            root = Path(temp_dir)
            host = _Host(root, project_path=str(root / "project.cxproj"))
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_revision = host.model.project.project_document_revision

            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as publication:
                notebook_ref = controller.create_blank_notebook_artifact(
                    kernel_name="python3"
                )

            store = controller.project_artifact_store()
            notebook_entry = store.staged_entry(notebook_ref)
            notebook_path = store.resolve_staged_path(notebook_ref)
            self.assertIsNotNone(notebook_entry)
            self.assertIsNotNone(notebook_path)
            assert notebook_entry is not None and notebook_path is not None
            self.assertIn(
                "/tmp/in/jupyter/notebooks/notebook.ipynb", notebook_path.as_posix()
            )
            notebook = nbformat.read(str(notebook_path), as_version=4)
            self.assertEqual(notebook.nbformat, 4)
            self.assertEqual(len(notebook.cells), 1)
            self.assertEqual(notebook.cells[0].cell_type, "code")
            self.assertEqual(notebook.cells[0].source, "")
            self.assertEqual(notebook.metadata["kernelspec"]["name"], "python3")
            self.assertEqual(notebook.metadata["kernelspec"]["display_name"], "python3")
            self.assertEqual(notebook_entry.extra["artifact_kind"], "jupyter_notebook")
            self.assertEqual(notebook_entry.extra["io_dir"], "in")
            self.assertIn(
                "/in/jupyter/notebooks/notebook.ipynb",
                notebook_entry.extra["managed_relative_path"],
            )
            self.assertEqual(publication.call_count, 1)
            self.assertEqual(
                host.model.project.project_document_revision,
                before_revision + 1,
            )
            self.assertEqual(host.project_meta_changed.calls, 1)

    def test_invalid_requests_leave_metadata_revision_and_staging_root_unchanged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = _Host(root)
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_metadata = dict(host.model.project.metadata)
            before_revision = host.model.project.project_document_revision

            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as publication:
                self.assertEqual(
                    controller.stage_node_artifact_file(
                        root / "missing.txt",
                        artifact_prefix="missing",
                        io_dir="in",
                    ),
                    "",
                )
                self.assertEqual(
                    controller.stage_node_artifact_bytes(
                        b"",
                        filename="empty.bin",
                        mime_type="application/octet-stream",
                        artifact_prefix="empty",
                        subdirectory="clipboard",
                        artifact_kind="clipboard_source",
                    ),
                    "",
                )
            self.assertEqual(host.model.project.metadata, before_metadata)
            self.assertEqual(
                host.model.project.project_document_revision, before_revision
            )
            self.assertEqual(host.project_meta_changed.calls, 0)
            publication.assert_not_called()
            self.assertFalse((root / "session").exists())

    def test_writer_failure_removes_only_the_new_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = _Host(root)
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_metadata = dict(host.model.project.metadata)
            before_revision = host.model.project.project_document_revision

            def fail_after_write(destination: Path) -> None:
                destination.write_bytes(b"partial")
                raise OSError("injected write failure")

            with patch.object(
                service,
                "replace_project_artifact_store",
                wraps=service.replace_project_artifact_store,
            ) as publication:
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    service._stage_node_artifact(  # noqa: SLF001
                        artifact_id="broken_artifact",
                        io_dir="in",
                        subdirectory="broken",
                        filename="candidate.bin",
                        entry_metadata=None,
                        node_id="",
                        node_title="",
                        node_type="",
                        writer=fail_after_write,
                    )

            self.assertFalse(list((root / "session").rglob("candidate.bin")))
            self.assertEqual(host.model.project.metadata, before_metadata)
            self.assertEqual(
                host.model.project.project_document_revision, before_revision
            )
            self.assertEqual(host.project_meta_changed.calls, 0)
            publication.assert_not_called()

    def test_publication_failure_cleans_new_byte_candidate_without_signalling(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            host = _Host(root)
            controller = _controller(host)
            service = controller._project_files_service  # noqa: SLF001
            before_metadata = dict(host.model.project.metadata)
            before_revision = host.model.project.project_document_revision

            with patch.object(
                service,
                "replace_project_artifact_store",
                side_effect=RuntimeError("injected publication failure"),
            ) as publication:
                ref = controller.stage_node_artifact_bytes(
                    b"candidate-bytes",
                    filename="publication-failure.bin",
                    mime_type="application/octet-stream",
                    artifact_prefix="publication_failure",
                    subdirectory="clipboard",
                    artifact_kind="clipboard_source",
                )

            self.assertEqual(ref, "")
            self.assertFalse(list((root / "session").rglob("publication-failure.bin")))
            self.assertEqual(host.model.project.metadata, before_metadata)
            self.assertEqual(
                host.model.project.project_document_revision, before_revision
            )
            self.assertEqual(host.project_meta_changed.calls, 0)
            self.assertEqual(publication.call_count, 1)


if __name__ == "__main__":
    unittest.main()
