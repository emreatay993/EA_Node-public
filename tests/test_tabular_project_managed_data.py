from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from ea_node_editor.addons.tabular_data.input_node import TABULAR_DATA_INPUT_NODE_TYPE_ID
from ea_node_editor.graph.file_issue_state import (
    EXTERNAL_LINK_MODE,
    MANAGED_COPY_MODE,
    repair_modes_for_node_property,
)
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore, format_workspace_artifact_folder
from ea_node_editor.ui.shell.controllers.project_session_controller import ProjectSessionController
from ea_node_editor.ui.shell.host_presenter import ShellHostPresenter
from tests.test_project_save_as_flow import _ProjectHostStub


class _SignalStub:
    def __init__(self) -> None:
        self.emit_count = 0

    def emit(self) -> None:
        self.emit_count += 1


class _AppPreferencesControllerStub:
    @staticmethod
    def source_import_mode() -> str:
        return MANAGED_COPY_MODE


class _ProjectSessionControllerStub:
    def __init__(self, host: "_HostStub") -> None:
        self._host = host

    def project_artifact_store(self) -> ProjectArtifactStore:
        return ProjectArtifactStore.from_project_metadata(
            project_path=self._host.project_path,
            project_metadata=self._host.model.project.metadata,
        )

    def ensure_project_staging_root(self) -> Path:
        store = self.project_artifact_store()
        staging_root = store.ensure_staging_root()
        metadata = dict(self._host.model.project.metadata)
        metadata["artifact_store"] = store.metadata
        self._host.model.project.metadata = metadata
        return staging_root


class _WorkspaceManagerStub:
    @staticmethod
    def active_workspace_id() -> str:
        return ""


class _HostStub(QObject):
    def __init__(self, *, project_path: Path) -> None:
        super().__init__()
        self.project_path = str(project_path)
        self.model = SimpleNamespace(project=SimpleNamespace(metadata={}, workspaces={}))
        self.project_meta_changed = _SignalStub()
        self.app_preferences_controller = _AppPreferencesControllerStub()
        self.project_session_controller = _ProjectSessionControllerStub(self)
        self.workspace_manager = _WorkspaceManagerStub()
        self.scene = SimpleNamespace(selected_node_id=lambda: "")


class TabularProjectManagedPresenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_tabular_path_browse_keeps_external_source_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "weather.csv"
            source_path.write_text("station,temp\nA,21.5\n", encoding="utf-8")
            host = _HostStub(project_path=root / "tabular.cxproj")
            presenter = ShellHostPresenter(host)  # type: ignore[arg-type]

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(source_path), ""),
            ):
                selected = presenter.browse_property_path_dialog("Path", "")

            self.assertEqual(selected, str(source_path))
            self.assertNotIn("artifact_store", host.model.project.metadata)
            self.assertEqual(host.project_meta_changed.emit_count, 0)

    def test_tabular_file_repair_can_choose_managed_copy(self) -> None:
        self.assertEqual(
            repair_modes_for_node_property(TABULAR_DATA_INPUT_NODE_TYPE_ID, "path"),
            (MANAGED_COPY_MODE, EXTERNAL_LINK_MODE),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            replacement_path = root / "replacement.csv"
            replacement_path.write_text("station,temp\nB,22.0\n", encoding="utf-8")
            host = _HostStub(project_path=root / "tabular.cxproj")
            presenter = ShellHostPresenter(host)  # type: ignore[arg-type]
            host.project_session_controller.stage_node_artifact_file = lambda *_args, **_kwargs: "temp://tabular_source_repaired"  # type: ignore[attr-defined]

            with patch(
                "ea_node_editor.ui.shell.host_presenter.QInputDialog.getItem",
                return_value=("Managed Copy", True),
            ), patch(
                "ea_node_editor.ui.shell.host_presenter.QFileDialog.getOpenFileName",
                return_value=(str(replacement_path), ""),
            ):
                repaired_ref = presenter.repair_property_path_dialog(
                    node_type_id=TABULAR_DATA_INPUT_NODE_TYPE_ID,
                    property_key="path",
                    property_label="Path",
                    current_path=str(root / "missing.csv"),
                )

            self.assertTrue(repaired_ref.startswith("temp://tabular_source_"))
            self.assertEqual(repaired_ref, "temp://tabular_source_repaired")


class TabularProjectManagedSaveFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _workspace_relative(relative_path: str, *, workspace_id: str, workspace_name: str = "Main") -> str:
        workspace_folder = format_workspace_artifact_folder(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
        )
        return f"workspaces/{workspace_folder}/{relative_path}"

    @classmethod
    def _workspace_path(
        cls,
        sidecar_root: Path,
        relative_path: str,
        *,
        workspace_id: str,
        workspace_name: str = "Main",
    ) -> Path:
        return sidecar_root.joinpath(
            *Path(cls._workspace_relative(relative_path, workspace_id=workspace_id, workspace_name=workspace_name)).parts
        )

    @staticmethod
    def _tabular_document(*, node_properties: dict, artifact_store: dict) -> dict:
        return {
            "schema_version": 5,
            "project_id": "proj_tabular_managed",
            "name": "Tabular Managed Data",
            "active_workspace_id": "ws_1",
            "workspace_order": ["ws_1"],
            "workspaces": [
                {
                    "workspace_id": "ws_1",
                    "name": "Main",
                    "dirty": True,
                    "active_view_id": "view_1",
                    "views": [
                        {
                            "view_id": "view_1",
                            "name": "Main",
                            "zoom": 1.0,
                            "pan_x": 0.0,
                            "pan_y": 0.0,
                            "scope_path": [],
                        }
                    ],
                    "nodes": [
                        {
                            "node_id": "node_tabular",
                            "type_id": TABULAR_DATA_INPUT_NODE_TYPE_ID,
                            "title": "Tabular Data Input",
                            "x": 0.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": dict(node_properties),
                            "exposed_ports": {},
                        }
                    ],
                    "edges": [],
                }
            ],
            "metadata": {"artifact_store": artifact_store},
        }

    def test_save_project_copies_referenced_tabular_source_and_defers_staged_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "tabular.cxproj"
            sidecar_root = source_project.with_name("tabular.data")
            staged_source_path = (
                sidecar_root
                / "nodes"
                / "Tabular Data [55555555]"
                / "tmp"
                / "in"
                / "tabular"
                / "source"
                / "tabular_source.weather.csv"
            )
            staged_cache_path = (
                sidecar_root
                / "nodes"
                / "Tabular Data [55555555]"
                / "tmp"
                / "out"
                / "tabular"
                / "cache"
                / "tabular_cache.scratch.parquet"
            )
            staged_source_path.parent.mkdir(parents=True, exist_ok=True)
            staged_cache_path.parent.mkdir(parents=True, exist_ok=True)
            staged_source_path.write_text("station,temp\nA,21.5\n", encoding="utf-8")
            staged_cache_path.write_bytes(b"scratch-cache")
            persistent_document = self._tabular_document(
                node_properties={
                    "path": format_staged_artifact_ref("tabular_source.weather"),
                    "project_managed_source": True,
                    "project_managed_cache": False,
                    "app_cache_key": "app-managed-only",
                },
                artifact_store={
                    "artifacts": {},
                    "staged": {
                        "tabular_source.weather": {
                            "artifact_kind": "tabular_source",
                            "relative_path": "nodes/Tabular Data [55555555]/tmp/in/tabular/source/tabular_source.weather.csv",
                        },
                        "tabular_cache.scratch": {
                            "artifact_kind": "tabular_cache",
                            "relative_path": "nodes/Tabular Data [55555555]/tmp/out/tabular/cache/tabular_cache.scratch.parquet",
                        },
                    },
                },
            )
            with patch(
                "ea_node_editor.addons.tabular_data.catalog._find_spec",
                return_value=object(),
            ):
                host = _ProjectHostStub(
                    project_path=str(source_project),
                    persistent_document=persistent_document,
                )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ):
                controller.save_project()

            saved_doc = json.loads(source_project.read_text(encoding="utf-8"))
            saved_properties = saved_doc["workspaces"][0]["nodes"][0]["properties"]
            managed_source_path = self._workspace_path(
                sidecar_root,
                "nodes/Tabular Data [55555555]/in/tabular/source/tabular_source.weather.csv",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            self.assertEqual(saved_properties["path"], format_managed_artifact_ref("tabular_source.weather"))
            self.assertEqual(saved_properties["app_cache_key"], "app-managed-only")
            artifact_store = saved_doc["metadata"]["artifact_store"]
            self.assertEqual(artifact_store["staged"], {})
            self.assertEqual(
                artifact_store["artifacts"]["tabular_source.weather"]["relative_path"],
                self._workspace_relative(
                    "nodes/Tabular Data [55555555]/in/tabular/source/tabular_source.weather.csv",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(artifact_store["artifacts"]["tabular_source.weather"]["artifact_kind"], "tabular_source")
            self.assertEqual(artifact_store["artifacts"]["tabular_source.weather"]["node_workspace_name"], "Main")
            self.assertEqual(managed_source_path.read_text(encoding="utf-8"), "station,temp\nA,21.5\n")
            self.assertTrue(staged_source_path.exists())
            self.assertTrue(staged_cache_path.exists())

    def test_save_as_self_contained_copy_preserves_managed_tabular_source_and_selected_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "tabular.cxproj"
            source_sidecar = source_project.with_name("tabular.data")
            source_path = source_sidecar / "nodes" / "Tabular Data [55555555]" / "in" / "tabular" / "source" / "tabular_source.weather.csv"
            cache_path = source_sidecar / "nodes" / "Tabular Data [55555555]" / "out" / "tabular" / "cache" / "tabular_cache.weather.parquet"
            scratch_path = source_sidecar / "nodes" / "Tabular Data [55555555]" / "tmp" / "out" / "tabular" / "cache" / "scratch.parquet"
            source_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            scratch_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("station,temp\nA,21.5\n", encoding="utf-8")
            cache_path.write_bytes(b"selected-cache")
            scratch_path.write_bytes(b"scratch-cache")
            persistent_document = self._tabular_document(
                node_properties={
                    "path": format_managed_artifact_ref("tabular_source.weather"),
                    "project_managed_source": True,
                    "project_managed_cache": True,
                    "cache_artifact_ref": format_managed_artifact_ref("tabular_cache.weather"),
                    "app_cache_key": "app-cache-key-only",
                },
                artifact_store={
                    "artifacts": {
                        "tabular_source.weather": {
                            "artifact_kind": "tabular_source",
                            "relative_path": "nodes/Tabular Data [55555555]/in/tabular/source/tabular_source.weather.csv",
                        },
                        "tabular_cache.weather": {
                            "artifact_kind": "tabular_cache",
                            "relative_path": "nodes/Tabular Data [55555555]/out/tabular/cache/tabular_cache.weather.parquet",
                        },
                    },
                    "staged": {
                        "tabular_cache.scratch": {
                            "artifact_kind": "tabular_cache",
                            "relative_path": "nodes/Tabular Data [55555555]/tmp/out/tabular/cache/scratch.parquet",
                        }
                    },
                },
            )
            target_project = root / "copies" / "clone_tabular.cxproj"
            stale_target_staging = target_project.with_name("clone_tabular.data") / "nodes" / "Old Node [99999999]" / "tmp" / "out" / "old.parquet"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            with patch(
                "ea_node_editor.addons.tabular_data.catalog._find_spec",
                return_value=object(),
            ):
                host = _ProjectHostStub(
                    project_path=str(source_project),
                    persistent_document=persistent_document,
                )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ), patch(
                "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                return_value=(str(target_project), "COREX Project (*.cxproj)"),
            ), patch(
                "PyQt6.QtWidgets.QMessageBox.warning",
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)

            saved_doc = json.loads(target_project.read_text(encoding="utf-8"))
            saved_properties = saved_doc["workspaces"][0]["nodes"][0]["properties"]
            target_sidecar = target_project.with_name("clone_tabular.data")
            copied_source = self._workspace_path(
                target_sidecar,
                "nodes/Tabular Data [55555555]/in/tabular/source/tabular_source.weather.csv",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_cache = self._workspace_path(
                target_sidecar,
                "nodes/Tabular Data [55555555]/out/tabular/cache/tabular_cache.weather.parquet",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_scratch = self._workspace_path(
                target_sidecar,
                "nodes/Tabular Data [55555555]/tmp/out/tabular/cache/scratch.parquet",
                workspace_id=host.model.active_workspace.workspace_id,
            )

            self.assertEqual(saved_properties["path"], format_managed_artifact_ref("tabular_source.weather"))
            self.assertEqual(saved_properties["cache_artifact_ref"], format_managed_artifact_ref("tabular_cache.weather"))
            self.assertEqual(saved_properties["app_cache_key"], "app-cache-key-only")
            artifact_store = saved_doc["metadata"]["artifact_store"]
            self.assertEqual(artifact_store["staged"], {})
            self.assertEqual(
                artifact_store["artifacts"]["tabular_cache.weather"]["relative_path"],
                self._workspace_relative(
                    "nodes/Tabular Data [55555555]/out/tabular/cache/tabular_cache.weather.parquet",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["tabular_source.weather"]["relative_path"],
                self._workspace_relative(
                    "nodes/Tabular Data [55555555]/in/tabular/source/tabular_source.weather.csv",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(artifact_store["artifacts"]["tabular_cache.weather"]["artifact_kind"], "tabular_cache")
            self.assertEqual(artifact_store["artifacts"]["tabular_source.weather"]["artifact_kind"], "tabular_source")
            self.assertEqual(artifact_store["artifacts"]["tabular_cache.weather"]["node_workspace_name"], "Main")
            self.assertEqual(copied_source.read_text(encoding="utf-8"), "station,temp\nA,21.5\n")
            self.assertEqual(copied_cache.read_bytes(), b"selected-cache")
            self.assertFalse(copied_scratch.exists())
            self.assertFalse(stale_target_staging.exists())


if __name__ == "__main__":
    unittest.main()
