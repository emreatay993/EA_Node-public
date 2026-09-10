from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.execution.runtime import CorexRuntime
from ea_node_editor.execution.signal_plot_renderer import render_signal_plot
from ea_node_editor.execution.project_solution import ProjectSolutionAdoptionResult
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.builtins.core_values import IMAGE_DATA_TYPE_ID
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.artifact_store import (
    ProjectArtifactStore,
    format_workspace_artifact_folder,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
import ea_node_editor.persistence.serializer as serializer_module
from ea_node_editor.persistence.solution_repository import SolutionRepositoryFactory
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    DataTree,
    DataTypeFamilySpec,
    DataTypeSpec,
    ImageValue,
    RuntimeArtifactRef,
)
from ea_node_editor.ui.shell.controllers.project_session_controller import (
    ProjectSessionController,
)
from ea_node_editor.ui.shell.state import ShellProjectSessionState

_TYPED_ARTIFACT_NODE_TYPE_ID = "tests.typed_artifact_save"
_TYPED_ARTIFACT_DATA_TYPE_ID = "Tests.SaveFlow.Artifact"
_OTHER_TYPED_ARTIFACT_DATA_TYPE_ID = "Tests.SaveFlow.OtherArtifact"


def _typed_artifact_registry() -> NodeRegistry:
    registry = NodeRegistry()
    family = DataTypeFamilySpec(
        "tests.save_flow",
        "Save Flow",
        "data.test",
        "test",
    )
    registry.data_types.register_many(
        families=(family,),
        types=(
            DataTypeSpec(
                _TYPED_ARTIFACT_DATA_TYPE_ID,
                "Typed Artifact",
                family.family_id,
                lambda value: isinstance(value, RuntimeArtifactRef),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"artifact"}),
                persistence="saved_artifact",
            ),
            DataTypeSpec(
                _OTHER_TYPED_ARTIFACT_DATA_TYPE_ID,
                "Other Typed Artifact",
                family.family_id,
                lambda value: isinstance(value, RuntimeArtifactRef),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"artifact"}),
                persistence="saved_artifact",
            ),
            DataTypeSpec(
                IMAGE_DATA_TYPE_ID,
                "Image",
                family.family_id,
                lambda value: isinstance(value, ImageValue),
                parents=(GRAPH_DATA_TYPE_ID,),
                carriers=frozenset({"inline"}),
                persistence="inline",
            ),
        ),
        owner_id="tests.save_flow",
    )
    spec = NodeTypeSpec(
        _TYPED_ARTIFACT_NODE_TYPE_ID,
        "Typed Artifact Save",
        ("Tests",),
        "",
        (PortSpec("result", "out", "data", GRAPH_DATA_TYPE_ID),),
        (
            PropertySpec(
                "artifact",
                "path",
                "",
                "Artifact",
                persistence_data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
            ),
            PropertySpec(
                "image",
                "json",
                {},
                "Image",
                persistence_data_type_id=IMAGE_DATA_TYPE_ID,
            ),
        ),
    )
    registry.register_descriptor(spec, lambda: None)  # type: ignore[arg-type]
    return registry


def _typed_artifact_document(runtime_ref: RuntimeArtifactRef) -> dict[str, object]:
    return {
        "schema_version": 5,
        "project_id": "proj_typed_artifact_save",
        "name": "Typed Artifact Save",
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
                    },
                ],
                "nodes": [
                    {
                        "node_id": "node_typed_artifact",
                        "type_id": _TYPED_ARTIFACT_NODE_TYPE_ID,
                        "title": "Typed Artifact",
                        "x": 0.0,
                        "y": 0.0,
                        "collapsed": False,
                        "properties": {"artifact": runtime_ref},
                        "exposed_ports": {},
                    },
                ],
                "edges": [],
            },
        ],
        "metadata": {
            "artifact_store": {
                "artifacts": {},
                "staged": {
                    runtime_ref.artifact_id: {
                        "relative_path": (
                            "nodes/Typed Artifact [33333333]/tmp/in/"
                            f"{runtime_ref.artifact_id}.bin"
                        ),
                        "runtime_artifact": runtime_ref.to_descriptor(),
                    },
                },
            },
        },
    }


def _invalid_typed_literal_artifact_document(
    runtime_ref: RuntimeArtifactRef,
    *,
    case: str,
) -> dict[str, object]:
    document = _typed_artifact_document(runtime_ref)
    document["workspaces"][0]["nodes"][0]["properties"]["artifact"] = runtime_ref.ref
    staged = document["metadata"]["artifact_store"]["staged"]
    if case == "unowned":
        document["metadata"]["artifact_store"]["staged"] = {}
    elif case == "mismatched":
        staged[runtime_ref.artifact_id]["runtime_artifact"]["data_type_id"] = (
            _OTHER_TYPED_ARTIFACT_DATA_TYPE_ID
        )
    elif case == "malformed":
        staged[runtime_ref.artifact_id]["runtime_artifact"]["schema_version"] = True
    else:
        raise ValueError(f"unsupported invalid literal case {case!r}")
    return document


class _SignalStub:
    def __init__(self) -> None:
        self.emit_count = 0

    def emit(self) -> None:
        self.emit_count += 1


class _ScriptEditorStub:
    def __init__(self) -> None:
        self.visible = False
        self.floating = False
        self.panel_width = 0.0


class _WorkspaceNavigationControllerStub:
    def __init__(self) -> None:
        self.save_active_view_state_calls = 0
        self.refresh_workspace_tabs_calls = 0

    def save_active_view_state(self) -> None:
        self.save_active_view_state_calls += 1

    def refresh_workspace_tabs(self) -> None:
        self.refresh_workspace_tabs_calls += 1


class _SerializerStub:
    def __init__(self, persistent_document: dict, registry: NodeRegistry) -> None:
        self._persistent_document = copy.deepcopy(persistent_document)
        self.saved_documents: list[tuple[str, dict]] = []
        self._serializer = JsonProjectSerializer(registry)

    def to_persistent_document(self, project) -> dict:  # noqa: ANN001
        document = copy.deepcopy(self._persistent_document)
        document["metadata"] = copy.deepcopy(project.metadata)
        return document

    def save_document(self, path: str, document: dict) -> None:
        target = Path(path).with_suffix(".cxproj")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = copy.deepcopy(document)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        self.saved_documents.append((str(target), payload))

    def stage_document(self, path, document, commit_mode):  # noqa: ANN001, ANN201
        return self._serializer.stage_document(path, document, commit_mode)

    def commit_staged_document(self, stage):  # noqa: ANN001, ANN201
        result = self._serializer.commit_staged_document(stage)
        if result.committed:
            self.saved_documents.append(
                (str(stage.target_path), copy.deepcopy(stage.prepared_document))
            )
        return result

    def verify_committed_document(self, stage) -> None:  # noqa: ANN001
        self._serializer.verify_committed_document(stage)

    def discard_staged_document(self, stage) -> None:  # noqa: ANN001
        self._serializer.discard_staged_document(stage)

    def load(self, path: str):  # noqa: ANN201
        return self._serializer.load(path)

    def to_document(self, project) -> dict:  # noqa: ANN001
        document = copy.deepcopy(self._persistent_document)
        document["metadata"] = copy.deepcopy(project.metadata)
        return document


class _SessionStoreStub:
    def __init__(self) -> None:
        self.discard_calls = 0
        self.persist_calls: list[dict] = []

    def discard_autosave_snapshot(self) -> None:
        self.discard_calls += 1

    def autosave_if_changed(self, **kwargs) -> str:  # noqa: ANN003
        return str(kwargs.get("last_fingerprint") or "stub-autosave-fingerprint")

    def persist_session(self, **kwargs) -> None:  # noqa: ANN003
        self.persist_calls.append(copy.deepcopy(kwargs))


class _SceneStub:
    @staticmethod
    def selected_node_id() -> str:
        return ""


class _ProjectHostStub:
    def __init__(self, *, project_path: str, persistent_document: dict) -> None:
        self.project_session_state = ShellProjectSessionState()
        self.registry = build_default_registry()
        self.model = GraphModel()
        self.model.project.project_id = str(
            persistent_document.get("project_id", "proj_save_as")
        )
        self.model.project.name = str(persistent_document.get("name", "Save As Demo"))
        workspace = self.model.active_workspace
        workspace_docs = persistent_document.get("workspaces", [])
        if workspace_docs:
            workspace_doc = workspace_docs[0]
            document_workspace_id = str(
                workspace_doc.get("workspace_id", workspace.workspace_id)
            )
            if document_workspace_id != workspace.workspace_id:
                self.model.project.workspaces.pop(workspace.workspace_id)
                workspace.workspace_id = document_workspace_id
                self.model.project.workspaces[document_workspace_id] = workspace
                self.model.project.active_workspace_id = document_workspace_id
            workspace.name = str(workspace_doc.get("name", workspace.name))
            for node_doc in workspace_doc.get("nodes", []):
                node = self.model.add_node(
                    workspace.workspace_id,
                    str(node_doc.get("type_id", "")),
                    str(node_doc.get("title", "")),
                    float(node_doc.get("x", 0.0)),
                    float(node_doc.get("y", 0.0)),
                    properties=copy.deepcopy(node_doc.get("properties", {})),
                    exposed_ports=copy.deepcopy(node_doc.get("exposed_ports", {})),
                )
                document_node_id = str(node_doc.get("node_id", node.node_id))
                if document_node_id != node.node_id:
                    workspace.nodes.pop(node.node_id)
                    node.node_id = document_node_id
                    workspace.nodes[document_node_id] = node
        self.model.project.metadata = copy.deepcopy(
            persistent_document.get("metadata", {})
        )
        for workspace in self.model.project.workspaces.values():
            workspace.dirty = True
        self.project_path = project_path
        if self.project_path and not Path(self.project_path).exists():
            Path(self.project_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.project_path).write_text("{}", encoding="utf-8")
        self.session_store = _SessionStoreStub()
        self.serializer = _SerializerStub(persistent_document, self.registry)
        self.execution_client = CorexRuntime(
            registry=self.registry,
            solution_repository_factory=SolutionRepositoryFactory(),
        )
        self.execution_client.reset_project_session(
            self.model.project.project_id,
            self.project_path,
        )
        self.execution_client.bind_project_solution_store(
            self.model.project.project_id,
            self.project_path,
            self.model.project.metadata.get("solution_store"),
        )
        self.workspace_navigation_controller = _WorkspaceNavigationControllerStub()
        self.script_editor = _ScriptEditorStub()
        self.action_toggle_script_editor = object()
        self.scene = _SceneStub()
        self.project_meta_changed = _SignalStub()
        self.refresh_calls = 0

    def _refresh_recent_projects_menu(self) -> None:
        self.refresh_calls += 1


class ProjectSaveAsFlowTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._warning_patch = patch("PyQt6.QtWidgets.QMessageBox.warning")
        self._warning_patch.start()
        self.addCleanup(self._warning_patch.stop)

    @staticmethod
    def _plain_document(project_id: str = "proj_transaction") -> dict[str, object]:
        return {
            "schema_version": 5,
            "project_id": project_id,
            "name": "Transaction",
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
                    "nodes": [],
                    "edges": [],
                }
            ],
            "metadata": {},
        }

    @staticmethod
    def _workspace_relative(
        relative_path: str, *, workspace_id: str = "ws_1", workspace_name: str = "Main"
    ) -> str:
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
        workspace_id: str = "ws_1",
        workspace_name: str = "Main",
    ) -> Path:
        return sidecar_root.joinpath(
            *Path(
                cls._workspace_relative(
                    relative_path,
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                )
            ).parts
        )

    @staticmethod
    def _typed_host(
        *,
        project_path: Path,
        document: dict[str, object],
    ) -> tuple[_ProjectHostStub, ProjectSessionController]:
        host = _ProjectHostStub(
            project_path=str(project_path),
            persistent_document=document,
        )
        registry = _typed_artifact_registry()
        host.registry = registry
        host.serializer = JsonProjectSerializer(registry)
        return host, ProjectSessionController(host)  # type: ignore[arg-type]

    @staticmethod
    def _typed_staged_path(
        project_path: Path,
        runtime_ref: RuntimeArtifactRef,
    ) -> Path:
        return (
            project_path.with_name(f"{project_path.stem}.data")
            / "nodes"
            / "Typed Artifact [33333333]"
            / "tmp"
            / "in"
            / f"{runtime_ref.artifact_id}.bin"
        )


    def _build_persistent_document(self, *, external_path: str) -> dict:
        return {
            "schema_version": 5,
            "project_id": "proj_save_as",
            "name": "Save As Demo",
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
                            "node_id": "node_managed",
                            "type_id": "media.panel",
                            "title": "Managed",
                            "x": 0.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {
                                "source": format_managed_artifact_ref(
                                    "managed_image"
                                ),
                            },
                            "exposed_ports": {"source": False},
                        },
                        {
                            "node_id": "node_staged",
                            "type_id": "media.panel",
                            "title": "Staged",
                            "x": 120.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {
                                "source": format_staged_artifact_ref(
                                    "pending_output"
                                ),
                            },
                            "exposed_ports": {"source": False},
                        },
                        {
                            "node_id": "node_external",
                            "type_id": "media.panel",
                            "title": "External",
                            "x": 240.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {
                                "source": external_path,
                            },
                            "exposed_ports": {"source": False},
                        },
                    ],
                    "edges": [],
                }
            ],
            "metadata": {
                "artifact_store": {
                    "artifacts": {
                        "managed_image": {
                            "relative_path": "nodes/Image Panel - Managed [11111111]/in/media/diagram.png",
                        }
                    },
                    "staged": {
                        "pending_output": {
                            "relative_path": "nodes/Image Panel - Staged [22222222]/tmp/out/outputs/run.txt",
                            "slot": "process_run.stdout",
                        }
                    },
                }
            },
        }

    def test_save_promotes_typed_staged_carrier_and_rewrites_live_property(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_project = Path(temp_dir) / "source" / "typed_save.cxproj"
            runtime_ref = RuntimeArtifactRef.staged(
                "typed_output",
                data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=13,
                sha256="a" * 64,
                provenance="save-flow",
            )
            staged_path = self._typed_staged_path(source_project, runtime_ref)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(b"typed payload")
            host, controller = self._typed_host(
                project_path=source_project,
                document=_typed_artifact_document(runtime_ref),
            )

            with patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ):
                result = controller.save_project()

            self.assertEqual(result.status, "saved", result.reason_code)
            saved_doc = json.loads(source_project.read_text(encoding="utf-8"))
            saved_property = saved_doc["workspaces"][0]["nodes"][0]["properties"][
                "artifact"
            ]
            managed_ref = format_managed_artifact_ref(runtime_ref.artifact_id)
            self.assertEqual(saved_property, managed_ref)
            managed_entry = saved_doc["metadata"]["artifact_store"]["artifacts"][
                runtime_ref.artifact_id
            ]
            self.assertEqual(
                managed_entry["runtime_artifact"],
                runtime_ref.to_descriptor(),
            )
            managed_path = source_project.with_name(
                f"{source_project.stem}.data"
            ).joinpath(*managed_entry["relative_path"].split("/"))
            self.assertEqual(managed_path.read_bytes(), b"typed payload")
            live_node = next(iter(host.model.active_workspace.nodes.values()))
            self.assertEqual(live_node.properties["artifact"], managed_ref)
            self.assertEqual(
                host.model.project.metadata["artifact_store"]["artifacts"][
                    runtime_ref.artifact_id
                ]["runtime_artifact"],
                runtime_ref.to_descriptor(),
            )
            self.assertNotIn("temp://", json.dumps(saved_doc, sort_keys=True))

    def test_save_as_promotes_typed_staged_carrier_and_rewrites_live_property(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "typed_source.cxproj"
            target_project = root / "target" / "typed_copy.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            runtime_ref = RuntimeArtifactRef.staged(
                "typed_output",
                data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=13,
                sha256="b" * 64,
                provenance="save-as-flow",
            )
            staged_path = self._typed_staged_path(source_project, runtime_ref)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(b"typed payload")
            host, controller = self._typed_host(
                project_path=source_project,
                document=_typed_artifact_document(runtime_ref),
            )

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)
            saved_doc = json.loads(target_project.read_text(encoding="utf-8"))
            managed_ref = format_managed_artifact_ref(runtime_ref.artifact_id)
            self.assertEqual(
                saved_doc["workspaces"][0]["nodes"][0]["properties"]["artifact"],
                managed_ref,
            )
            managed_entry = saved_doc["metadata"]["artifact_store"]["artifacts"][
                runtime_ref.artifact_id
            ]
            self.assertEqual(
                managed_entry["runtime_artifact"],
                runtime_ref.to_descriptor(),
            )
            managed_path = target_project.with_name(
                f"{target_project.stem}.data"
            ).joinpath(*managed_entry["relative_path"].split("/"))
            self.assertEqual(managed_path.read_bytes(), b"typed payload")
            live_node = next(iter(host.model.active_workspace.nodes.values()))
            self.assertEqual(live_node.properties["artifact"], managed_ref)
            self.assertEqual(host.project_path, str(target_project))
            self.assertNotIn("temp://", json.dumps(saved_doc, sort_keys=True))

    def test_save_as_image_and_staged_artifact_survive_source_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "typed_source.cxproj"
            target_project = root / "target" / "typed_copy.cxproj"
            target_project.parent.mkdir(parents=True)
            runtime_ref = RuntimeArtifactRef.staged(
                "typed_output",
                data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=13,
                sha256="b" * 64,
                provenance="portable-save-as",
            )
            image, _warnings = render_signal_plot(
                {"values": DataTree((((0,), (1.0, 2.0, 1.5)),)), "marker_shapes": [0]}
            )
            document = _typed_artifact_document(runtime_ref)
            document["workspaces"][0]["nodes"][0]["properties"]["image"] = image
            staged_path = self._typed_staged_path(source_project, runtime_ref)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(b"typed payload")
            host, controller = self._typed_host(
                project_path=source_project,
                document=document,
            )
            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()
            self.assertEqual(result.status, "saved", result.reason_code)
            target_layout = target_project.with_name("typed_copy.data")
            self.assertEqual(
                (target_layout / "images" / f"{image.sha256}.png").read_bytes(),
                image.encoded_bytes,
            )

            host.execution_client.shutdown()
            source_project.unlink()
            shutil.rmtree(source_project.with_name("typed_source.data"))
            registry = _typed_artifact_registry()
            reopened = JsonProjectSerializer(registry).load(str(target_project))
            node = reopened.workspaces["ws_1"].nodes["node_typed_artifact"]
            self.assertIsInstance(node.properties["image"], ImageValue)
            self.assertEqual(node.properties["image"], image)
            store = ProjectArtifactStore.from_project_metadata(
                project_path=target_project,
                project_metadata=reopened.metadata,
            )
            copied = store.resolve_managed_path(runtime_ref.artifact_id)
            self.assertIsNotNone(copied)
            self.assertEqual(copied.read_bytes(), b"typed payload")

    def test_save_rejects_invalid_typed_staging_metadata_before_promotion(
        self,
    ) -> None:
        cases = ("unowned", "mismatched", "invalid")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                source_project = Path(temp_dir) / "source" / f"typed_{case}.cxproj"
                runtime_ref = RuntimeArtifactRef.staged(
                    "typed_output",
                    data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                    schema_version=1,
                    format="bin",
                    size_bytes=13,
                    sha256="c" * 64,
                    provenance="invalid-flow",
                )
                document = _typed_artifact_document(runtime_ref)
                staged_entry = document["metadata"]["artifact_store"]["staged"][
                    runtime_ref.artifact_id
                ]
                if case == "unowned":
                    document["metadata"]["artifact_store"]["staged"] = {}
                elif case == "mismatched":
                    staged_entry["runtime_artifact"]["sha256"] = "d" * 64
                else:
                    staged_entry["runtime_artifact"]["schema_version"] = True
                staged_path = self._typed_staged_path(source_project, runtime_ref)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(b"typed payload")
                host, controller = self._typed_host(
                    project_path=source_project,
                    document=document,
                )
                artifact_metadata_before = copy.deepcopy(
                    host.model.project.metadata["artifact_store"]
                )
                live_node = next(iter(host.model.active_workspace.nodes.values()))

                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                ):
                    result = controller.save_project()

                self.assertEqual(result.status, "failed")
                self.assertTrue(source_project.exists())
                self.assertTrue(staged_path.exists())
                self.assertEqual(
                    host.model.project.metadata["artifact_store"],
                    artifact_metadata_before,
                )
                self.assertEqual(live_node.properties["artifact"], runtime_ref)

    def test_save_as_rejects_unowned_typed_staging_before_destination_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "typed_source.cxproj"
            target_project = root / "target" / "typed_copy.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            runtime_ref = RuntimeArtifactRef.staged(
                "typed_output",
                data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                schema_version=1,
                format="bin",
                size_bytes=13,
                sha256="e" * 64,
                provenance="invalid-save-as",
            )
            document = _typed_artifact_document(runtime_ref)
            document["metadata"]["artifact_store"]["staged"] = {}
            staged_path = self._typed_staged_path(source_project, runtime_ref)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(b"typed payload")
            host, controller = self._typed_host(
                project_path=source_project,
                document=document,
            )
            artifact_metadata_before = copy.deepcopy(
                host.model.project.metadata["artifact_store"]
            )
            live_node = next(iter(host.model.active_workspace.nodes.values()))

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "failed")
            self.assertFalse(target_project.exists())
            self.assertTrue(staged_path.exists())
            self.assertEqual(
                host.model.project.metadata["artifact_store"],
                artifact_metadata_before,
            )
            self.assertEqual(live_node.properties["artifact"], runtime_ref)

    def test_save_rejects_invalid_typed_literal_staging_before_promotion(
        self,
    ) -> None:
        for case in ("unowned", "mismatched", "malformed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                source_project = Path(temp_dir) / "source" / f"literal_{case}.cxproj"
                source_project.parent.mkdir(parents=True, exist_ok=True)
                source_project.write_bytes(b"original project")
                runtime_ref = RuntimeArtifactRef.staged(
                    "typed_literal",
                    data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                    schema_version=1,
                    format="bin",
                    size_bytes=13,
                    sha256="6" * 64,
                    provenance="literal-save",
                )
                document = _invalid_typed_literal_artifact_document(
                    runtime_ref,
                    case=case,
                )
                staged_path = self._typed_staged_path(source_project, runtime_ref)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(b"literal payload")
                host, controller = self._typed_host(
                    project_path=source_project,
                    document=document,
                )
                artifact_metadata_before = copy.deepcopy(
                    host.model.project.metadata["artifact_store"]
                )
                live_node = next(iter(host.model.active_workspace.nodes.values()))
                workspaces_root = (
                    source_project.with_name(f"{source_project.stem}.data")
                    / "workspaces"
                )

                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                ):
                    result = controller.save_project()

                self.assertEqual(result.status, "failed")
                self.assertEqual(source_project.read_bytes(), b"original project")
                self.assertEqual(staged_path.read_bytes(), b"literal payload")
                self.assertFalse(workspaces_root.exists())
                self.assertEqual(
                    host.model.project.metadata["artifact_store"],
                    artifact_metadata_before,
                )
                self.assertEqual(live_node.properties["artifact"], runtime_ref.ref)
                self.assertEqual(host.project_path, str(source_project))

    def test_save_as_rejects_invalid_typed_literal_before_destination_mutation(
        self,
    ) -> None:
        for case in ("unowned", "mismatched", "malformed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source_project = root / "source" / f"literal_{case}.cxproj"
                target_project = root / "target" / f"literal_{case}.cxproj"
                source_project.parent.mkdir(parents=True, exist_ok=True)
                source_project.write_bytes(b"source project")
                target_project.parent.mkdir(parents=True, exist_ok=True)
                target_project.write_bytes(b"target project")
                target_sentinel = (
                    target_project.with_name(f"{target_project.stem}.data")
                    / "workspaces"
                    / "existing"
                    / "sentinel.bin"
                )
                target_sentinel.parent.mkdir(parents=True, exist_ok=True)
                target_sentinel.write_bytes(b"target sentinel")
                runtime_ref = RuntimeArtifactRef.staged(
                    "typed_literal",
                    data_type_id=_TYPED_ARTIFACT_DATA_TYPE_ID,
                    schema_version=1,
                    format="bin",
                    size_bytes=13,
                    sha256="7" * 64,
                    provenance="literal-save-as",
                )
                document = _invalid_typed_literal_artifact_document(
                    runtime_ref,
                    case=case,
                )
                staged_path = self._typed_staged_path(source_project, runtime_ref)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(b"literal payload")
                host, controller = self._typed_host(
                    project_path=source_project,
                    document=document,
                )
                artifact_metadata_before = copy.deepcopy(
                    host.model.project.metadata["artifact_store"]
                )
                live_node = next(iter(host.model.active_workspace.nodes.values()))

                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                    patch(
                        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(
                            str(target_project),
                            "COREX Project (*.cxproj)",
                        ),
                    ),
                ):
                    result = controller.save_project_as()

                self.assertEqual(result.status, "failed")
                self.assertEqual(source_project.read_bytes(), b"source project")
                self.assertEqual(staged_path.read_bytes(), b"literal payload")
                self.assertEqual(target_project.read_bytes(), b"target project")
                self.assertEqual(target_sentinel.read_bytes(), b"target sentinel")
                self.assertEqual(
                    host.model.project.metadata["artifact_store"],
                    artifact_metadata_before,
                )
                self.assertEqual(live_node.properties["artifact"], runtime_ref.ref)
                self.assertEqual(host.project_path, str(source_project))

    def test_save_promotes_and_rewrites_excalidraw_staged_refs_in_nested_payloads(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "source_project.cxproj"
            source_layout = source_project.with_name("source_project.data")
            staged_image_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "tmp"
                / "in"
                / "excalidraw"
                / "image.png"
            )
            staged_preview_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "tmp"
                / "out"
                / "excalidraw"
                / "preview.png"
            )
            scratch_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "tmp"
                / "out"
                / "excalidraw"
                / "scratch.png"
            )
            staged_image_path.parent.mkdir(parents=True, exist_ok=True)
            staged_image_path.write_text("image payload", encoding="utf-8")
            staged_preview_path.parent.mkdir(parents=True, exist_ok=True)
            staged_preview_path.write_text("preview payload", encoding="utf-8")
            scratch_path.write_text("scratch payload", encoding="utf-8")
            image_ref = format_staged_artifact_ref("pending_excalidraw_image")
            preview_ref = format_staged_artifact_ref("pending_excalidraw_preview")
            persistent_document = {
                "schema_version": 5,
                "project_id": "proj_excalidraw_save",
                "name": "Excalidraw Save",
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
                                "node_id": "node_excalidraw",
                                "type_id": EXCALIDRAW_BOARD_TYPE_ID,
                                "title": "Board",
                                "x": 0.0,
                                "y": 0.0,
                                "collapsed": False,
                                "properties": {
                                    EXCALIDRAW_STATE_PROPERTY: {
                                        "type": "excalidraw",
                                        "version": 2,
                                        "elements": [
                                            {
                                                "id": "image-element",
                                                "type": "image",
                                                "fileId": "file-pending",
                                            }
                                        ],
                                        "files": [
                                            {
                                                "id": "file-pending",
                                                "mimeType": "image/png",
                                                "artifact_ref": image_ref,
                                            }
                                        ],
                                        "appState": {"viewBackgroundColor": "#ffffff"},
                                    },
                                    EXCALIDRAW_PREVIEW_REF_PROPERTY: {
                                        "artifact_ref": preview_ref,
                                        "mime_type": "image/png",
                                    },
                                },
                                "exposed_ports": {},
                            }
                        ],
                        "edges": [],
                    }
                ],
                "metadata": {
                    "artifact_store": {
                        "artifacts": {},
                        "staged": {
                            "pending_excalidraw_image": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/tmp/in/excalidraw/image.png",
                                "slot": "excalidraw.node_excalidraw.image",
                            },
                            "pending_excalidraw_preview": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/tmp/out/excalidraw/preview.png",
                                "slot": "excalidraw.node_excalidraw.preview",
                            },
                            "unused_excalidraw_scratch": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/tmp/out/excalidraw/scratch.png",
                                "slot": "excalidraw.node_excalidraw.scratch",
                            },
                        },
                    }
                },
            }

            host = _ProjectHostStub(
                project_path=str(source_project),
                persistent_document=persistent_document,
            )
            host.script_editor.panel_width = 640.0
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ):
                controller.save_project()

            saved_doc = json.loads(source_project.read_text(encoding="utf-8"))
            self.assertEqual(
                saved_doc["metadata"]["ui"]["script_editor"]["width"], 640.0
            )
            saved_properties = saved_doc["workspaces"][0]["nodes"][0]["properties"]
            managed_image_path = self._workspace_path(
                source_layout,
                "nodes/Excalidraw - Board [33333333]/in/excalidraw/image.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            managed_preview_path = self._workspace_path(
                source_layout,
                "nodes/Excalidraw - Board [33333333]/out/excalidraw/preview.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )

            self.assertEqual(
                saved_properties[EXCALIDRAW_STATE_PROPERTY]["files"][0]["artifact_ref"],
                format_managed_artifact_ref("pending_excalidraw_image"),
            )
            self.assertEqual(
                saved_properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["artifact_ref"],
                format_managed_artifact_ref("pending_excalidraw_preview"),
            )
            artifact_store = saved_doc["metadata"]["artifact_store"]
            self.assertEqual(artifact_store["staged"], {})
            self.assertEqual(
                artifact_store["artifacts"]["pending_excalidraw_image"][
                    "relative_path"
                ],
                self._workspace_relative(
                    "nodes/Excalidraw - Board [33333333]/in/excalidraw/image.png",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_excalidraw_preview"][
                    "relative_path"
                ],
                self._workspace_relative(
                    "nodes/Excalidraw - Board [33333333]/out/excalidraw/preview.png",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_excalidraw_image"]["slot"],
                "excalidraw.node_excalidraw.image",
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_excalidraw_image"][
                    "node_workspace_name"
                ],
                "Main",
            )
            self.assertEqual(
                managed_image_path.read_text(encoding="utf-8"), "image payload"
            )
            self.assertEqual(
                managed_preview_path.read_text(encoding="utf-8"), "preview payload"
            )
            self.assertTrue(staged_image_path.exists())
            self.assertTrue(staged_preview_path.exists())
            self.assertTrue(scratch_path.exists())
            serialized_doc = json.dumps(saved_doc, sort_keys=True)
            self.assertNotIn("temp://", serialized_doc)
            self.assertNotIn("data:image", serialized_doc)
            self.assertNotIn("base64", serialized_doc)

    def test_save_as_copies_referenced_saved_files_and_promotes_temp_by_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "source_project.cxproj"
            source_managed_path = (
                source_project.with_name("source_project.data")
                / "nodes"
                / "Image Panel - Managed [11111111]"
                / "in"
                / "media"
                / "diagram.png"
            )
            source_managed_path.parent.mkdir(parents=True, exist_ok=True)
            source_managed_path.write_text("managed payload", encoding="utf-8")
            source_staging_path = (
                source_project.with_name("source_project.data")
                / "nodes"
                / "Image Panel - Staged [22222222]"
                / "tmp"
                / "out"
                / "outputs"
                / "run.txt"
            )
            source_staging_path.parent.mkdir(parents=True, exist_ok=True)
            source_staging_path.write_text("staged payload", encoding="utf-8")
            external_path = str((root / "external" / "linked.png").resolve())
            Path(external_path).parent.mkdir(parents=True, exist_ok=True)
            Path(external_path).write_text("external payload", encoding="utf-8")
            persistent_document = self._build_persistent_document(
                external_path=external_path
            )

            target_project = root / "copies" / "clone_project.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            stale_managed_path = (
                target_project.with_name("clone_project.data")
                / "nodes"
                / "Old Node [99999999]"
                / "out"
                / "stale.txt"
            )
            stale_staging_path = (
                target_project.with_name("clone_project.data")
                / "nodes"
                / "Old Node [99999999]"
                / "tmp"
                / "out"
                / "outputs"
                / "old.txt"
            )

            host = _ProjectHostStub(
                project_path=str(source_project),
                persistent_document=persistent_document,
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)
            saved_path = target_project.with_suffix(".cxproj")
            saved_doc = json.loads(saved_path.read_text(encoding="utf-8"))
            target_layout = saved_path.with_name("clone_project.data")
            copied_managed_path = self._workspace_path(
                target_layout,
                "nodes/Image Panel - Managed [11111111]/in/media/diagram.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_output_path = self._workspace_path(
                target_layout,
                "nodes/Image Panel - Staged [22222222]/out/outputs/run.txt",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_temp_path = self._workspace_path(
                target_layout,
                "nodes/Image Panel - Staged [22222222]/tmp/out/outputs/run.txt",
                workspace_id=host.model.active_workspace.workspace_id,
            )

            self.assertEqual(host.project_path, str(saved_path))
            self.assertEqual(
                host.project_session_state.recent_project_paths, [str(saved_path)]
            )
            self.assertFalse(next(iter(host.model.project.workspaces.values())).dirty)
            self.assertEqual(host.project_meta_changed.emit_count, 1)
            self.assertEqual(
                host.workspace_navigation_controller.refresh_workspace_tabs_calls, 1
            )
            self.assertEqual(host.session_store.discard_calls, 1)
            self.assertEqual(len(host.session_store.persist_calls), 1)
            self.assertNotIn("project_doc", host.session_store.persist_calls[0])
            artifact_store = saved_doc["metadata"]["artifact_store"]
            self.assertEqual(artifact_store["staged"], {})
            self.assertEqual(
                artifact_store["artifacts"]["managed_image"]["relative_path"],
                self._workspace_relative(
                    "nodes/Image Panel - Managed [11111111]/in/media/diagram.png",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_output"]["relative_path"],
                self._workspace_relative(
                    "nodes/Image Panel - Staged [22222222]/out/outputs/run.txt",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_output"]["slot"],
                "process_run.stdout",
            )
            self.assertEqual(
                artifact_store["artifacts"]["pending_output"]["node_workspace_name"],
                "Main",
            )
            self.assertEqual(
                copied_managed_path.read_text(encoding="utf-8"), "managed payload"
            )
            self.assertEqual(
                copied_output_path.read_text(encoding="utf-8"), "staged payload"
            )
            self.assertFalse(copied_temp_path.exists())
            self.assertFalse(stale_managed_path.exists())
            self.assertFalse(stale_staging_path.exists())

            workspace_doc = saved_doc["workspaces"][0]
            saved_nodes = {node["node_id"]: node for node in workspace_doc["nodes"]}
            self.assertEqual(
                saved_nodes["node_managed"]["properties"]["source"],
                format_managed_artifact_ref("managed_image"),
            )
            self.assertEqual(
                saved_nodes["node_staged"]["properties"]["source"],
                format_managed_artifact_ref("pending_output"),
            )
            self.assertEqual(
                saved_nodes["node_external"]["properties"]["source"], external_path
            )
            host.execution_client.shutdown()
            source_project.unlink(missing_ok=True)
            shutil.rmtree(source_project.with_name("source_project.data"))
            reopened = JsonProjectSerializer(host.registry).load(str(saved_path))
            destination_store = ProjectArtifactStore.from_project_metadata(
                project_path=saved_path,
                project_metadata=reopened.metadata,
            )
            self.assertEqual(
                destination_store.resolve_managed_path("managed_image").read_text(
                    encoding="utf-8"
                ),
                "managed payload",
            )
            self.assertEqual(
                destination_store.resolve_managed_path("pending_output").read_text(
                    encoding="utf-8"
                ),
                "staged payload",
            )
            fresh_runtime = CorexRuntime(
                registry=host.registry,
                solution_repository_factory=SolutionRepositoryFactory(),
            )
            try:
                fresh_runtime.reset_project_session(
                    reopened.project_id,
                    str(saved_path),
                )
                opened = fresh_runtime.bind_project_solution_store(
                    reopened.project_id,
                    str(saved_path),
                    reopened.metadata["solution_store"],
                )
                self.assertEqual(opened.status_code, "durable_bound_active")
            finally:
                fresh_runtime.shutdown()

    def test_save_as_self_contained_copy_preserves_excalidraw_managed_assets_and_excludes_scratch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "source_project.cxproj"
            source_layout = source_project.with_name("source_project.data")
            source_image_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "in"
                / "excalidraw"
                / "image.png"
            )
            source_preview_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "out"
                / "excalidraw"
                / "preview.png"
            )
            source_scratch_path = (
                source_layout
                / "nodes"
                / "Excalidraw - Board [33333333]"
                / "tmp"
                / "out"
                / "excalidraw"
                / "scratch.png"
            )
            source_image_path.parent.mkdir(parents=True, exist_ok=True)
            source_image_path.write_text("managed image", encoding="utf-8")
            source_preview_path.parent.mkdir(parents=True, exist_ok=True)
            source_preview_path.write_text("managed preview", encoding="utf-8")
            source_scratch_path.parent.mkdir(parents=True, exist_ok=True)
            source_scratch_path.write_text("scratch payload", encoding="utf-8")
            image_ref = format_managed_artifact_ref("managed_excalidraw_image")
            preview_ref = format_managed_artifact_ref("managed_excalidraw_preview")
            persistent_document = {
                "schema_version": 5,
                "project_id": "proj_excalidraw_save_as",
                "name": "Excalidraw Save As",
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
                                "node_id": "node_excalidraw",
                                "type_id": EXCALIDRAW_BOARD_TYPE_ID,
                                "title": "Board",
                                "x": 0.0,
                                "y": 0.0,
                                "collapsed": False,
                                "properties": {
                                    EXCALIDRAW_STATE_PROPERTY: {
                                        "type": "excalidraw",
                                        "version": 2,
                                        "elements": [
                                            {
                                                "id": "image-element",
                                                "type": "image",
                                                "fileId": "file-managed",
                                            }
                                        ],
                                        "files": [
                                            {
                                                "id": "file-managed",
                                                "mimeType": "image/png",
                                                "artifact_ref": image_ref,
                                            }
                                        ],
                                        "appState": {"viewBackgroundColor": "#ffffff"},
                                    },
                                    EXCALIDRAW_PREVIEW_REF_PROPERTY: {
                                        "artifact_ref": preview_ref,
                                        "mime_type": "image/png",
                                    },
                                },
                                "exposed_ports": {},
                            }
                        ],
                        "edges": [],
                    }
                ],
                "metadata": {
                    "artifact_store": {
                        "artifacts": {
                            "managed_excalidraw_image": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/in/excalidraw/image.png",
                            },
                            "managed_excalidraw_preview": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/out/excalidraw/preview.png",
                            },
                        },
                        "staged": {
                            "unused_excalidraw_scratch": {
                                "relative_path": "nodes/Excalidraw - Board [33333333]/tmp/out/excalidraw/scratch.png",
                                "slot": "excalidraw.node_excalidraw.scratch",
                            },
                        },
                    }
                },
            }
            target_project = root / "copies" / "clone_project.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            stale_target_scratch = (
                target_project.with_name("clone_project.data")
                / "nodes"
                / "Old Node [99999999]"
                / "tmp"
                / "out"
                / "old.txt"
            )

            host = _ProjectHostStub(
                project_path=str(source_project),
                persistent_document=persistent_document,
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)
            saved_doc = json.loads(target_project.read_text(encoding="utf-8"))
            saved_properties = saved_doc["workspaces"][0]["nodes"][0]["properties"]
            target_layout = target_project.with_name("clone_project.data")
            copied_image_path = self._workspace_path(
                target_layout,
                "nodes/Excalidraw - Board [33333333]/in/excalidraw/image.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_preview_path = self._workspace_path(
                target_layout,
                "nodes/Excalidraw - Board [33333333]/out/excalidraw/preview.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )
            copied_scratch_path = self._workspace_path(
                target_layout,
                "nodes/Excalidraw - Board [33333333]/tmp/out/excalidraw/scratch.png",
                workspace_id=host.model.active_workspace.workspace_id,
            )

            self.assertEqual(
                saved_properties[EXCALIDRAW_STATE_PROPERTY]["files"][0]["artifact_ref"],
                image_ref,
            )
            self.assertEqual(
                saved_properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["artifact_ref"],
                preview_ref,
            )
            artifact_store = saved_doc["metadata"]["artifact_store"]
            self.assertEqual(artifact_store["staged"], {})
            self.assertEqual(
                artifact_store["artifacts"]["managed_excalidraw_image"][
                    "relative_path"
                ],
                self._workspace_relative(
                    "nodes/Excalidraw - Board [33333333]/in/excalidraw/image.png",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["managed_excalidraw_preview"][
                    "relative_path"
                ],
                self._workspace_relative(
                    "nodes/Excalidraw - Board [33333333]/out/excalidraw/preview.png",
                    workspace_id=host.model.active_workspace.workspace_id,
                ),
            )
            self.assertEqual(
                artifact_store["artifacts"]["managed_excalidraw_image"][
                    "node_workspace_name"
                ],
                "Main",
            )
            self.assertEqual(
                copied_image_path.read_text(encoding="utf-8"), "managed image"
            )
            self.assertEqual(
                copied_preview_path.read_text(encoding="utf-8"), "managed preview"
            )
            self.assertFalse(copied_scratch_path.exists())
            self.assertFalse(stale_target_scratch.exists())
            serialized_doc = json.dumps(saved_doc, sort_keys=True)
            self.assertNotIn("data:image", serialized_doc)
            self.assertNotIn("base64", serialized_doc)

    def test_save_as_prompts_with_staged_and_broken_summary_before_file_selection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "source_project.cxproj"
            managed_path = (
                source_project.with_name("source_project.data")
                / "nodes"
                / "Image Panel - Managed [11111111]"
                / "in"
                / "media"
                / "diagram.png"
            )
            managed_path.parent.mkdir(parents=True, exist_ok=True)
            managed_path.write_text("managed payload", encoding="utf-8")
            staged_path = (
                source_project.with_name("source_project.data")
                / "nodes"
                / "Image Panel - Staged [22222222]"
                / "tmp"
                / "out"
                / "outputs"
                / "run.txt"
            )
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text("staged payload", encoding="utf-8")
            missing_external_path = str((root / "external" / "missing.png").resolve())
            persistent_document = self._build_persistent_document(
                external_path=missing_external_path
            )

            host = _ProjectHostStub(
                project_path=str(source_project),
                persistent_document=persistent_document,
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            target_project = root / "copies" / "clone_project.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ) as prompt,
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                controller.save_project_as()

        self.assertEqual(prompt.call_count, 1)
        snapshot = prompt.call_args.kwargs["snapshot"]
        self.assertEqual(snapshot.managed_count, 1)
        self.assertEqual(snapshot.staged_count, 1)
        self.assertEqual(snapshot.broken_count, 1)

    def test_save_as_cancelled_from_project_file_prompt_skips_file_selection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_project = root / "source" / "source_project.cxproj"
            managed_path = (
                source_project.with_name("source_project.data")
                / "nodes"
                / "Image Panel - Managed [11111111]"
                / "in"
                / "media"
                / "diagram.png"
            )
            managed_path.parent.mkdir(parents=True, exist_ok=True)
            managed_path.write_text("managed payload", encoding="utf-8")
            missing_external_path = str((root / "external" / "missing.png").resolve())
            persistent_document = self._build_persistent_document(
                external_path=missing_external_path
            )

            host = _ProjectHostStub(
                project_path=str(source_project),
                persistent_document=persistent_document,
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=False,
                ) as prompt,
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                ) as file_dialog,
            ):
                controller.save_project_as()

        self.assertEqual(prompt.call_count, 1)
        self.assertEqual(file_dialog.call_count, 0)
        self.assertEqual(host.serializer.saved_documents, [])







    def test_save_as_plain_project_without_managed_data_still_switches_to_new_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target_project = root / "copies" / "plain_project.cxproj"
            target_project.parent.mkdir(parents=True, exist_ok=True)
            persistent_document = {
                "schema_version": 5,
                "project_id": "proj_plain",
                "name": "Plain Project",
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
                        "nodes": [],
                        "edges": [],
                    }
                ],
                "metadata": {},
            }
            host = _ProjectHostStub(
                project_path="", persistent_document=persistent_document
            )
            host.script_editor.panel_width = 720.0
            controller = ProjectSessionController(host)  # type: ignore[arg-type]

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_project), "COREX Project (*.cxproj)"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)
            saved_doc = json.loads(target_project.read_text(encoding="utf-8"))
            self.assertEqual(host.project_path, str(target_project))
            self.assertEqual(
                saved_doc["metadata"]["ui"]["script_editor"]["width"], 720.0
            )
            self.assertEqual(
                saved_doc["metadata"]["artifact_store"],
                {
                    "artifacts": {},
                    "staged": {},
                },
            )

    def test_precommit_failure_matrix_preserves_source_disk_and_live_state(self) -> None:
        cases = (
            ("document", "save_document_invalid"),
            ("artifact", "save_artifact_stage_failed"),
            ("solution", "save_solution_stage_failed"),
            ("project_stage", "save_project_stage_failed"),
            ("project_commit", "save_project_commit_failed"),
        )
        for injection, expected_reason in cases:
            with self.subTest(injection=injection), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = root / "source.cxproj"
                source.write_bytes(b"source-before")
                target = root / "target" / "candidate.cxproj"
                target.parent.mkdir(parents=True)
                host = _ProjectHostStub(
                    project_path=str(source),
                    persistent_document=self._plain_document(),
                )
                controller = ProjectSessionController(host)  # type: ignore[arg-type]
                controller.persist_script_editor_state()
                metadata_before = copy.deepcopy(host.model.project.metadata)
                if injection == "document":
                    failure_patch = patch.object(
                        host.serializer,
                        "to_persistent_document",
                        side_effect=ValueError("invalid document"),
                    )
                elif injection == "artifact":
                    failure_patch = patch.object(
                        ProjectArtifactStore,
                        "stage_project_save",
                        side_effect=OSError("artifact stage"),
                    )
                elif injection == "solution":
                    failure_patch = patch.object(
                        host.execution_client,
                        "stage_project_solution_save",
                        side_effect=OSError("solution stage"),
                    )
                elif injection == "project_stage":
                    failure_patch = patch.object(
                        host.serializer,
                        "stage_document",
                        side_effect=OSError("project stage"),
                    )
                else:
                    failure_patch = patch.object(
                        host.serializer,
                        "commit_staged_document",
                        side_effect=OSError("project commit"),
                    )
                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                    patch(
                        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(str(target), "COREX Project (*.cxproj)"),
                    ),
                    failure_patch,
                ):
                    result = controller.save_project_as()

                self.assertEqual(result.status, "failed")
                self.assertEqual(result.reason_code, expected_reason)
                self.assertEqual(source.read_bytes(), b"source-before")
                self.assertFalse(target.exists())
                self.assertEqual(host.project_path, str(source))
                self.assertEqual(host.model.project.metadata, metadata_before)
                self.assertTrue(host.model.active_workspace.dirty)

    def test_precommit_source_drift_and_create_new_race_do_not_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.cxproj"
            source.write_bytes(b"source-before")
            target = root / "target" / "candidate.cxproj"
            target.parent.mkdir(parents=True)
            host = _ProjectHostStub(
                project_path=str(source),
                persistent_document=self._plain_document("proj-drift"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            real_stage = host.serializer.stage_document

            def drift_after_stage(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                staged = real_stage(*args, **kwargs)
                host.model.project.touch_metadata()
                return staged

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch.object(host.serializer, "stage_document", drift_after_stage),
            ):
                drift_result = controller.save_project_as()
            self.assertEqual(drift_result.reason_code, "save_source_changed")
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b"source-before")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.cxproj"
            source.write_bytes(b"source-before")
            target = root / "target" / "candidate.cxproj"
            target.parent.mkdir(parents=True)
            host = _ProjectHostStub(
                project_path=str(source),
                persistent_document=self._plain_document("proj-race"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            real_commit = host.serializer.commit_staged_document

            def race_before_commit(stage):  # noqa: ANN001, ANN202
                target.write_bytes(b"racing-winner")
                return real_commit(stage)

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch.object(host.serializer, "commit_staged_document", race_before_commit),
            ):
                race_result = controller.save_project_as()
            self.assertEqual(race_result.reason_code, "save_destination_exists")
            self.assertEqual(target.read_bytes(), b"racing-winner")
            self.assertEqual(host.project_path, str(source))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.cxproj"
            source.write_bytes(b"source-before")
            target = root / "target" / "candidate.cxproj"
            target.parent.mkdir(parents=True)
            sidecar = target.with_name("candidate.data")
            host = _ProjectHostStub(
                project_path=str(source),
                persistent_document=self._plain_document("proj-sidecar-race"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            real_mkdir = os.mkdir

            def race_sidecar(path, mode=0o777):  # noqa: ANN001, ANN202
                if Path(path) == sidecar:
                    real_mkdir(path, mode)
                    (sidecar / "winner.txt").write_text("winner", encoding="utf-8")
                    raise FileExistsError
                return real_mkdir(path, mode)

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch(
                    "ea_node_editor.ui.shell.controllers.project_session_services_support.document_io_service.os.mkdir",
                    race_sidecar,
                ),
            ):
                sidecar_race_result = controller.save_project_as()
            self.assertEqual(
                sidecar_race_result.reason_code,
                "save_destination_sidecar_exists",
            )
            self.assertFalse(target.exists())
            self.assertEqual(
                (sidecar / "winner.txt").read_text(encoding="utf-8"),
                "winner",
            )

    def test_postcommit_failure_matrix_retains_source_live_binding(self) -> None:
        cases = (
            ("reopen", "save_committed_not_adopted_reopen_failed"),
            ("source_drift", "save_committed_not_adopted_source_changed"),
            ("binding", "save_committed_not_adopted_binding_failed"),
            ("verification", "save_committed_not_adopted_verification_failed"),
        )
        for injection, expected_reason in cases:
            with self.subTest(injection=injection), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = root / "source.cxproj"
                source.write_bytes(b"source-before")
                target = root / "target" / "candidate.cxproj"
                target.parent.mkdir(parents=True)
                host = _ProjectHostStub(
                    project_path=str(source),
                    persistent_document=self._plain_document(f"proj-{injection}"),
                )
                controller = ProjectSessionController(host)  # type: ignore[arg-type]
                controller.persist_script_editor_state()
                metadata_before = copy.deepcopy(host.model.project.metadata)
                real_load = host.serializer.load
                real_commit = host.serializer.commit_staged_document
                if injection == "reopen":
                    failure_patch = patch.object(
                        host.serializer,
                        "load",
                        side_effect=ValueError("reopen failed"),
                    )
                elif injection == "source_drift":
                    def load_and_drift(path):  # noqa: ANN001, ANN202
                        candidate = real_load(path)
                        host.model.project.touch_metadata()
                        return candidate

                    failure_patch = patch.object(
                        host.serializer,
                        "load",
                        load_and_drift,
                    )
                elif injection == "binding":
                    failure_patch = patch.object(
                        host.execution_client,
                        "adopt_project_solution_save",
                        return_value=ProjectSolutionAdoptionResult(
                            False,
                            "project_solution_adoption_candidate_invalid",
                            "Candidate adoption failed.",
                        ),
                    )
                else:
                    def commit_and_corrupt(stage):  # noqa: ANN001, ANN202
                        publication = real_commit(stage)
                        target.write_bytes(b"postcommit-corruption")
                        return publication

                    failure_patch = patch.object(
                        host.serializer,
                        "commit_staged_document",
                        commit_and_corrupt,
                    )
                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                    patch(
                        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(str(target), "COREX Project (*.cxproj)"),
                    ),
                    failure_patch,
                ):
                    result = controller.save_project_as()

                self.assertEqual(result.status, "committed_not_adopted")
                self.assertEqual(result.reason_code, expected_reason)
                self.assertTrue(target.is_file())
                self.assertEqual(host.project_path, str(source))
                self.assertEqual(host.model.project.metadata, metadata_before)
                self.assertTrue(host.model.active_workspace.dirty)

    def test_postpublication_artifact_and_solution_corruption_fail_verification(self) -> None:
        for corruption in ("artifact", "solution"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source = root / "source.cxproj"
                target = root / "target" / "candidate.cxproj"
                target.parent.mkdir(parents=True)
                if corruption == "artifact":
                    managed = source.with_name("source.data") / "nodes" / "Node [11111111]" / "out" / "value.bin"
                    managed.parent.mkdir(parents=True, exist_ok=True)
                    managed.write_bytes(b"managed-source")
                    document = self._plain_document("proj-artifact-corrupt")
                    document["metadata"] = {
                        "artifact_store": {
                            "artifacts": {
                                "managed": {
                                    "relative_path": "nodes/Node [11111111]/out/value.bin"
                                }
                            },
                            "staged": {},
                        }
                    }
                    document["workspaces"][0]["nodes"] = [
                        {
                            "node_id": "node-managed",
                            "type_id": "media.panel",
                            "title": "Managed",
                            "x": 0.0,
                            "y": 0.0,
                            "collapsed": False,
                            "properties": {"source": "saved://managed"},
                            "exposed_ports": {},
                        }
                    ]
                else:
                    document = self._plain_document("proj-solution-corrupt")
                host = _ProjectHostStub(
                    project_path=str(source),
                    persistent_document=document,
                )
                controller = ProjectSessionController(host)  # type: ignore[arg-type]
                real_commit = host.serializer.commit_staged_document

                def commit_then_corrupt(stage):  # noqa: ANN001, ANN202
                    publication = real_commit(stage)
                    committed = json.loads(target.read_text(encoding="utf-8"))
                    if corruption == "artifact":
                        relative = committed["metadata"]["artifact_store"]["artifacts"]["managed"]["relative_path"]
                        (target.with_name("candidate.data") / Path(relative)).write_bytes(b"corrupt")
                    else:
                        generation_id = committed["metadata"]["solution_store"]["active_generation_id"]
                        manifest = target.with_name("candidate.data") / "solutions" / "v1" / "generations" / generation_id / "manifest-set.json"
                        manifest.write_text("{}", encoding="utf-8")
                    return publication

                with (
                    patch.object(
                        controller._project_files_service,
                        "prompt_project_files_action",
                        return_value=True,
                    ),
                    patch(
                        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(str(target), "COREX Project (*.cxproj)"),
                    ),
                    patch.object(host.serializer, "commit_staged_document", commit_then_corrupt),
                ):
                    result = controller.save_project_as()
                self.assertEqual(result.status, "committed_not_adopted")
                self.assertEqual(
                    result.reason_code,
                    "save_committed_not_adopted_verification_failed",
                )
                self.assertEqual(host.project_path, str(source))
                self.assertTrue(host.model.active_workspace.dirty)

    def test_publication_uncertain_retains_source_live_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.cxproj"
            source.write_bytes(b"source-before")
            target = root / "target" / "candidate.cxproj"
            target.parent.mkdir(parents=True)
            host = _ProjectHostStub(
                project_path=str(source),
                persistent_document=self._plain_document("proj-uncertain"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            real_link = serializer_module.os.link
            real_fact = serializer_module._publication_target_fact  # noqa: SLF001
            probes = 0

            def publish_then_raise(source_path, destination_path) -> None:  # noqa: ANN001
                real_link(source_path, destination_path)
                if Path(destination_path) == target:
                    raise OSError("raised after publication")

            def unreadable_after_attempt(path):  # noqa: ANN001, ANN202
                nonlocal probes
                probes += 1
                if probes > 1:
                    raise OSError("unreadable")
                return real_fact(path)

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch.object(serializer_module.os, "link", publish_then_raise),
                patch.object(
                    serializer_module,
                    "_publication_target_fact",
                    unreadable_after_attempt,
                ),
            ):
                result = controller.save_project_as()
            self.assertEqual(result.status, "committed_not_adopted")
            self.assertEqual(host.project_path, str(source))
            self.assertTrue(target.exists())

    def test_gc_and_notification_failures_do_not_change_save_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "saved.cxproj"
            host = _ProjectHostStub(
                project_path="",
                persistent_document=self._plain_document("proj-gc"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            target_key = controller._document_service._normalized_absolute_path(
                target
            )
            artifact_candidate = "nodes/Old [11111111]/out/old.bin"
            image_candidate = "a" * 64
            controller._document_service._deferred_artifact_cleanup[target_key] = (
                artifact_candidate,
            )
            controller._document_service._deferred_image_cleanup[target_key] = (
                image_candidate,
            )
            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch.object(
                    host.execution_client,
                    "collect_project_solution_garbage",
                    side_effect=OSError("gc failed"),
                ),
                patch.object(
                    ProjectArtifactStore,
                    "collect_project_save_garbage",
                    side_effect=OSError("artifact gc failed"),
                ),
                patch(
                    "ea_node_editor.ui.shell.controllers.project_session_services_support.document_io_service.collect_project_image_garbage",
                    side_effect=OSError("image gc failed"),
                ),
                patch.object(
                    controller._session_service,
                    "persist_session",
                    side_effect=OSError("notification failed"),
                ),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved")
            self.assertTrue(target.is_file())
            self.assertEqual(host.project_path, str(target))
            self.assertEqual(
                controller._document_service._deferred_artifact_cleanup[target_key],
                (artifact_candidate,),
            )
            self.assertEqual(
                controller._document_service._deferred_image_cleanup[target_key],
                (image_candidate,),
            )
            self.assertEqual(
                len(controller._document_service._deferred_solution_cleanup),
                1,
            )

            with patch.object(
                controller._project_files_service,
                "prompt_project_files_action",
                return_value=True,
            ):
                retry = controller.save_project()
            self.assertEqual(retry.status, "saved", retry.reason_code)
            self.assertNotIn(
                target_key,
                controller._document_service._deferred_artifact_cleanup,
            )
            self.assertNotIn(
                target_key,
                controller._document_service._deferred_image_cleanup,
            )
            self.assertEqual(
                len(controller._document_service._deferred_solution_cleanup),
                1,
            )

    def test_autosave_during_staging_remains_runtime_only_and_does_not_drift_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "saved.cxproj"
            host = _ProjectHostStub(
                project_path="",
                persistent_document=self._plain_document("proj-autosave"),
            )
            controller = ProjectSessionController(host)  # type: ignore[arg-type]
            real_stage = host.serializer.stage_document
            observed_live_pointers: list[object] = []

            def stage_then_autosave(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                staged = real_stage(*args, **kwargs)
                observed_live_pointers.append(
                    host.model.project.metadata.get("solution_store")
                )
                controller.autosave_tick()
                observed_live_pointers.append(
                    host.model.project.metadata.get("solution_store")
                )
                return staged

            with (
                patch.object(
                    controller._project_files_service,
                    "prompt_project_files_action",
                    return_value=True,
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target), "COREX Project (*.cxproj)"),
                ),
                patch.object(host.serializer, "stage_document", stage_then_autosave),
            ):
                result = controller.save_project_as()

            self.assertEqual(result.status, "saved", result.reason_code)
            self.assertEqual(observed_live_pointers, [None, None])
            self.assertIn("solution_store", host.model.project.metadata)

    def test_save_guard_rejects_reentry_and_project_replacement(self) -> None:
        host = _ProjectHostStub(
            project_path="",
            persistent_document=self._plain_document("proj-guard"),
        )
        controller = ProjectSessionController(host)  # type: ignore[arg-type]
        self.assertTrue(controller._document_service._save_guard.acquire(False))
        try:
            result = controller.save_project()
            self.assertEqual(result.reason_code, "save_in_progress")
            self.assertFalse(controller.new_project())
            self.assertFalse(controller.open_project_path("missing.cxproj"))
            with self.assertRaisesRegex(RuntimeError, "save_in_progress"):
                controller._install_project(
                    ProjectData(project_id="imported", name="Imported"),
                    project_path="",
                )
        finally:
            controller._document_service._save_guard.release()


if __name__ == "__main__":
    unittest.main()
