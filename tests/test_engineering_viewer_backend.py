from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from unittest import mock

import pyvista

from ea_node_editor.common.scene_protocol import SceneDescriptor, SceneSourceMetadata
from ea_node_editor.execution.prepared_scene_runtime import (
    PreparedScene,
    PreparedSceneRuntime,
)
from ea_node_editor.execution.viewer_messages import (
    MaterializeViewerDataCommand,
    OpenViewerSessionCommand,
    ViewerDataMaterializedEvent,
)
from ea_node_editor.execution.viewer_backend import (
    ViewerBackendMaterializationRequest,
    ViewerBackendQueryRequest,
)
from ea_node_editor.execution.viewer_backend_engineering import (
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_VIEWER_BACKEND_ID,
    ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
    ENGINEERING_VIEWER_TRANSPORT_KIND,
    EngineeringViewerBackend,
)
from ea_node_editor.runtime_contracts import ENGINEERING_SCENE_DATA_TYPE_ID
from tests.typed_handle_support import core_worker_services


def _request(
    source_refs: dict[str, object],
    *,
    options: dict[str, object] | None = None,
    session_options: dict[str, object] | None = None,
    session_id: str = "session-engineering",
) -> ViewerBackendMaterializationRequest:
    return ViewerBackendMaterializationRequest(
        workspace_id="workspace-engineering",
        node_id="node-engineering",
        session_id=session_id,
        owner_scope=f"viewer:workspace-engineering:{session_id}",
        source_refs=source_refs,
        session_summary={"camera_state": {"position": [2.0, 3.0, 4.0]}},
        session_options=session_options or {},
        request_options=options or {},
        output_profile="memory",
    )


def _write_topology_asset(path: Path, payload: dict[str, object]) -> dict[str, object]:
    topology_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(topology_bytes)
    return {
        "id": "selection:topology",
        "role": "selection_topology",
        "path": str(path),
        "format": ".json",
        "content": "selection_topology",
        "schema": "corex.selection_topology.v1",
        "sha256": hashlib.sha256(topology_bytes).hexdigest(),
        "entity_arrays": {},
    }


def _write_cad_selection_source(
    root: Path,
) -> tuple[dict[str, object], dict[str, Path]]:
    root.mkdir(parents=True, exist_ok=True)
    full_path = root / "surface.full.vtp"
    edge_path = root / "topology_edges.vtp"
    vertex_path = root / "topology_vertices.vtp"
    topology_path = root / "selection_topology.json"

    surface = pyvista.PolyData(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        faces=[3, 0, 1, 2],
    )
    surface.cell_data["corex_part_index"] = [1]
    surface.cell_data["corex_body_index"] = [1]
    surface.cell_data["corex_face_index"] = [1]
    surface.save(full_path)

    edges = pyvista.Line((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    edges.cell_data["corex_part_index"] = [1]
    edges.cell_data["corex_edge_index"] = [1]
    edges.save(edge_path)

    vertices = pyvista.PolyData([(0.0, 0.0, 0.0)], verts=[1, 0])
    vertices.cell_data["corex_part_index"] = [1]
    vertices.cell_data["corex_vertex_index"] = [1]
    vertices.save(vertex_path)

    topology_asset = _write_topology_asset(
        topology_path,
        {
            "schema": "corex.selection_topology.v1",
            "parts": [
                {
                    "part_index": 1,
                    "hierarchy_id": "cad:body:0",
                    "vertices": [
                        {
                            "id": "part:1/vertex:1",
                            "part_index": 1,
                            "vertex_index": 1,
                            "edge_ids": ["part:1/edge:1"],
                        }
                    ],
                    "edges": [
                        {
                            "id": "part:1/edge:1",
                            "part_index": 1,
                            "edge_index": 1,
                            "vertex_ids": ["part:1/vertex:1"],
                            "face_ids": ["part:1/face:1"],
                        }
                    ],
                    "faces": [
                        {
                            "id": "part:1/face:1",
                            "part_index": 1,
                            "face_index": 1,
                            "body_ids": ["part:1/body:1"],
                            "edge_ids": ["part:1/edge:1"],
                        }
                    ],
                    "bodies": [
                        {
                            "id": "part:1/body:1",
                            "part_index": 1,
                            "body_index": 1,
                            "body_kind": "solid",
                            "face_ids": ["part:1/face:1"],
                        }
                    ],
                }
            ],
            "blocks": [],
            "edge_continuity": [],
            "face_continuity": [],
            "capabilities": {
                "cad_vertex_selection": {"available": True, "unsupported_reason": ""},
                "cad_edge_selection": {"available": True, "unsupported_reason": ""},
                "cad_face_selection": {"available": True, "unsupported_reason": ""},
                "cad_body_selection": {"available": True, "unsupported_reason": ""},
                "fe_node_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE nodes.",
                },
                "fe_element_face_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE element faces.",
                },
                "fe_element_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE elements.",
                },
                "tangent_edge_propagation": {
                    "available": False,
                    "unsupported_reason": "The topology has no adjacent edge pairs.",
                },
                "tangent_face_propagation": {
                    "available": False,
                    "unsupported_reason": "The topology has no adjacent face pairs.",
                },
            },
        },
    )
    source = {
        "display_artifact_path": str(full_path),
        "length_unit": "mm",
        "bounds": [0, 1, 0, 1, 0, 1],
        "geometry_assets": [
            {
                "id": "geometry:full",
                "role": "full",
                "path": str(full_path),
                "format": ".vtp",
                "content": "surface",
                "entity_arrays": {
                    "part_index": "corex_part_index",
                    "body_index": "corex_body_index",
                    "face_index": "corex_face_index",
                },
            },
            {
                "id": "geometry:topology_edges",
                "role": "topology_edges",
                "path": str(edge_path),
                "format": ".vtp",
                "content": "topological_edges",
                "entity_arrays": {
                    "part_index": "corex_part_index",
                    "edge_index": "corex_edge_index",
                },
            },
            {
                "id": "geometry:topology_vertices",
                "role": "topology_vertices",
                "path": str(vertex_path),
                "format": ".vtp",
                "content": "topological_vertices",
                "entity_arrays": {
                    "part_index": "corex_part_index",
                    "vertex_index": "corex_vertex_index",
                },
            },
            topology_asset,
        ],
    }
    return source, {
        "full": full_path,
        "edges": edge_path,
        "vertices": vertex_path,
        "topology": topology_path,
    }


def _write_fe_selection_source(root: Path) -> tuple[dict[str, object], dict[str, Path]]:
    root.mkdir(parents=True, exist_ok=True)
    identity_path = root / "selection_identity.vtu"
    faces_path = root / "element_faces.vtp"
    topology_path = root / "selection_topology.json"

    identity = pyvista.ImageData(dimensions=(2, 2, 2)).cast_to_unstructured_grid()
    identity.point_data["corex_block_index"] = [0] * identity.n_points
    identity.point_data["corex_node_index"] = list(range(identity.n_points))
    identity.cell_data["corex_block_index"] = [0] * identity.n_cells
    identity.cell_data["corex_element_index"] = list(range(identity.n_cells))
    identity.save(identity_path)

    faces = identity.extract_surface(algorithm=None)
    faces.cell_data["corex_block_index"] = [0] * faces.n_cells
    faces.cell_data["corex_element_index"] = [0] * faces.n_cells
    faces.cell_data["corex_element_face_index"] = list(range(faces.n_cells))
    faces.save(faces_path)

    topology_asset = _write_topology_asset(
        topology_path,
        {
            "schema": "corex.selection_topology.v1",
            "parts": [],
            "blocks": [
                {
                    "block_index": 0,
                    "block_id": "block:0",
                    "point_id_array": "",
                    "cell_id_array": "",
                    "point_count": identity.n_points,
                    "cell_count": identity.n_cells,
                    "exterior_element_face_count": faces.n_cells,
                    "element_face_id_array": "",
                    "element_face_id_unsupported_reason": "No authored face numbers.",
                }
            ],
            "edge_continuity": [],
            "face_continuity": [],
            "capabilities": {
                "cad_vertex_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD vertices.",
                },
                "cad_edge_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define exact CAD edges.",
                },
                "cad_face_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD faces.",
                },
                "cad_body_selection": {
                    "available": False,
                    "unsupported_reason": "FE sources do not define CAD bodies.",
                },
                "fe_node_selection": {"available": True, "unsupported_reason": ""},
                "fe_element_face_selection": {
                    "available": True,
                    "unsupported_reason": "",
                },
                "fe_element_selection": {"available": True, "unsupported_reason": ""},
                "tangent_edge_propagation": {
                    "available": False,
                    "unsupported_reason": "Tangent propagation requires exact CAD topology.",
                },
                "tangent_face_propagation": {
                    "available": False,
                    "unsupported_reason": "Tangent propagation requires exact CAD topology.",
                },
            },
        },
    )
    identity_arrays = {
        "block_index": "corex_block_index",
        "node_index": "corex_node_index",
        "element_index": "corex_element_index",
    }
    source = {
        "display_artifact_path": str(identity_path),
        "length_unit": "mm",
        "bounds": [0, 1, 0, 1, 0, 1],
        "geometry_assets": [
            {
                "id": "geometry:full",
                "role": "full",
                "path": str(identity_path),
                "format": ".vtu",
                "content": "mesh",
                "entity_arrays": {},
            },
            {
                "id": "selection:mesh_identity",
                "role": "selection_identity",
                "path": str(identity_path),
                "format": ".vtu",
                "content": "mesh",
                "entity_arrays": identity_arrays,
            },
            {
                "id": "selection:element_faces",
                "role": "element_faces",
                "path": str(faces_path),
                "format": ".vtp",
                "content": "element_faces",
                "entity_arrays": {
                    "block_index": "corex_block_index",
                    "element_index": "corex_element_index",
                    "element_face_index": "corex_element_face_index",
                },
            },
            topology_asset,
        ],
    }
    return source, {
        "identity": identity_path,
        "faces": faces_path,
        "topology": topology_path,
    }


class EngineeringViewerBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = core_worker_services()
        self.backend = EngineeringViewerBackend(self.services)
        self.addCleanup(self.backend.reset)

    def test_scene_queries_and_export_use_stable_ids_with_duplicate_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = self._prepared_scene_ref(root, name="first", dataset=pyvista.Cube())
            second = self._prepared_scene_ref(
                root, name="second", dataset=pyvista.Cube(center=(10, 0, 0))
            )
            source_refs = {
                "scene_order": ["a", "b", "c"],
                "scene_labels": {
                    "a": "Duplicate name",
                    "b": "Duplicate name",
                    "c": "Again",
                },
                "scene:a": first,
                "scene:b": second,
                "scene:c": first,
            }
            result = self.backend.materialize(_request(source_refs))
            self.assertEqual(result.live_open_status, "ready")
            self.assertEqual(
                [item["id"] for item in result.summary["model_tree"]],
                ["a:root", "b:root", "c:root"],
            )
            self.assertEqual(
                [layer["id"] for layer in result.transport["layers"]], ["a", "b", "c"]
            )

            def query(query_type, payload, active="a"):
                return self.backend.query(
                    ViewerBackendQueryRequest(
                        workspace_id="workspace-engineering",
                        session_id="session-engineering",
                        query_type=query_type,
                        payload=payload,
                        session_options={"active_scene_id": active},
                    )
                )

            selected = query(
                "entity_info", {"entity_kind": "scene", "entity_id": "root"}, active="b"
            )
            self.assertTrue(selected.supported, selected.explanation)
            self.assertEqual(selected.value["name"], "second")
            self.assertEqual(selected.value["layer_id"], "b")
            explicit = query(
                "entity_info",
                {
                    "entity": {
                        "entity_kind": "scene",
                        "entity_id": "root",
                        "layer_id": "c",
                    }
                },
                active="b",
            )
            self.assertEqual(explicit.value["name"], "first")
            self.assertEqual(explicit.value["layer_id"], "c")
            unknown = query("mass_properties", {"layer_id": "removed"})
            self.assertFalse(unknown.supported)
            mixed = query(
                "distance",
                {"entity_a": {"layer_id": "a"}, "entity_b": {"layer_id": "b"}},
            )
            self.assertFalse(mixed.supported)
            conflict = query(
                "entity_info", {"layer_id": "a", "entity": {"layer_id": "b"}}
            )
            self.assertFalse(conflict.supported)
            bounds = query("bounds", {}, active="b")
            self.assertEqual(bounds.value["bounds"], [-0.5, 10.5, -0.5, 0.5, -0.5, 0.5])
            exported = query(
                "export",
                {
                    "path": str(root / "visible.vtm"),
                    "format": "vtm",
                    "visible_layers": ["b", "c"],
                },
            )
            self.assertTrue(exported.supported, exported.explanation)
            self.assertEqual(exported.value["visible_layer_ids"], ["b", "c"])
            self.assertEqual(pyvista.read(root / "visible.vtm").n_blocks, 2)

    def test_scene_source_order_and_style_validation_fail_closed(self) -> None:
        for refs in (
            {"scene": {}},
            {"scene_order": []},
            {"scene_order": ["a", "a"], "scene:a": {}},
            {"scene_order": ["a"]},
        ):
            with self.subTest(refs=refs):
                result = self.backend.materialize(_request(refs))
                self.assertEqual(
                    result.live_open_blocker["code"], "scene_contract_invalid"
                )
        result = self.backend.materialize(
            _request(
                {"scene_order": ["a"], "scene:a": {"display_path": "test.vtp"}},
                session_options={"scene_styles": {"a": {"opacity": float("nan")}}},
            )
        )
        self.assertEqual(result.live_open_blocker["code"], "scene_contract_invalid")

    def test_same_session_scene_replacements_advance_revisions_and_release_old_assets(
        self,
    ) -> None:
        service = self.services.viewer_session_service
        identity = {
            "workspace_id": "workspace-engineering",
            "node_id": "node-engineering",
            "session_id": "session-replacements",
            "backend_id": ENGINEERING_VIEWER_BACKEND_ID,
        }
        revisions = []
        previous_asset_names = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for replacement in range(4):
                with self.subTest(replacement=replacement):
                    source_name = f"source-{replacement}"
                    ref = self._prepared_scene_ref(
                        root,
                        name=source_name,
                        dataset=pyvista.Cube(center=(replacement * 10.0, 0.0, 0.0)),
                    )
                    opened = service.open_session(
                        OpenViewerSessionCommand(
                            **identity,
                            data_refs={
                                "scene_order": ["a", "b", "c"],
                                "scene:a": ref,
                                "scene:b": ref,
                                "scene:c": ref,
                            },
                        )
                    )
                    if revisions:
                        self.assertGreater(opened.transport_revision, revisions[-1])
                    for name in previous_asset_names:
                        with self.assertRaises(FileNotFoundError):
                            SharedMemory(name=name)
                    materialized = service.materialize_data(
                        MaterializeViewerDataCommand(**identity)
                    )
                    self.assertIsInstance(materialized, ViewerDataMaterializedEvent)
                    self.assertEqual(materialized.live_open_status, "ready")
                    self.assertGreater(
                        materialized.transport_revision, opened.transport_revision
                    )
                    self.assertEqual(
                        materialized.transport["transport_revision"],
                        materialized.transport_revision,
                    )
                    self.assertEqual(
                        [
                            layer["scene_id"]
                            for layer in materialized.transport["layers"]
                        ],
                        [source_name] * 3,
                    )
                    revisions.append(materialized.transport_revision)
                    previous_asset_names = [
                        layer["display_asset"]["name"]
                        for layer in materialized.transport["layers"]
                    ]
            service._backend_registry.reset()
            for name in previous_asset_names:
                with self.assertRaises(FileNotFoundError):
                    SharedMemory(name=name)
        self.assertEqual(revisions, [1, 3, 5, 7])

    def test_gltf_auto_preserves_authored_face_colors_and_per_scene_opacity(
        self,
    ) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dataset = pyvista.Cube().triangulate()
            dataset.cell_data["corex_source_rgba"] = np.tile(
                np.asarray([[255, 0, 0, 255], [0, 255, 0, 128]], dtype=np.uint8),
                (dataset.n_cells // 2, 1),
            )
            ref = self._prepared_scene_ref(root, name="colored", dataset=dataset)
            source_refs = {"scene_order": ["a", "b"], "scene:a": ref, "scene:b": ref}
            materialized = self.backend.materialize(
                _request(
                    source_refs,
                    session_options={
                        "scene_styles": {"a": {"opacity": 0.2, "color": "#ff0000"}}
                    },
                )
            )
            self.assertNotIn("color", materialized.transport["layers"][0]["style"])
            self.assertEqual(
                materialized.transport["layers"][0]["style"]["opacity"], 1.0
            )
            layers = self.backend._visible_export_layers(
                source_refs=source_refs,
                transport=materialized.transport,
                payload={},
                session_options={
                    "scene_styles": {
                        "a": {"opacity": 0.5, "color": ""},
                        "b": {"opacity": 1.0, "color": "#0000ff"},
                    }
                },
            )
            with mock.patch("vtkmodules.vtkIOGeometry.vtkGLTFWriter") as writer_type:
                writer_type.return_value.Write.return_value = 1
                result = self.backend._write_gltf_export(
                    root / "colors.gltf",
                    export_format="gltf",
                    layers=layers,
                    session_options={},
                    display_state={},
                )
            self.assertIsNone(result)
            exported = writer_type.return_value.SetInputDataObject.call_args.args[0]
            auto_colors = exported[0][0].point_data["COLOR_0"]
            override_colors = exported[1][0].point_data["COLOR_0"]
            self.assertEqual(
                {tuple(value) for value in auto_colors.tolist()},
                {(255, 0, 0, 128), (0, 255, 0, 64)},
            )
            self.assertEqual(
                {tuple(value) for value in override_colors.tolist()}, {(0, 0, 255, 255)}
            )
            self.assertEqual(dataset.n_points, 8)
            self.assertNotIn("COLOR_0", dataset.point_data)

    def _prepared_scene_ref(
        self,
        root: Path,
        *,
        name: str,
        dataset: object,
    ) -> object:
        display_path = root / f"{name}.vtp"
        source_sha = hashlib.sha256(name.encode("utf-8")).hexdigest()
        descriptor = SceneDescriptor(
            scene_id=name,
            source_kind="cad",
            source=SceneSourceMetadata(
                source_path=f"{name}.stl",
                resolved_path=str(root / f"{name}.stl"),
                source_format=".stl",
                size_bytes=1,
                modified_time_ns=1,
                sha256=source_sha,
            ),
            display_artifact_path=str(display_path),
            display_format=".vtp",
            cache_manifest_path=str(root / f"{name}.json"),
            dataset_kind="polydata",
            point_count=int(getattr(dataset, "n_points", 0)),
            cell_count=int(getattr(dataset, "n_cells", 0)),
            block_count=1,
            bounds=tuple(float(value) for value in dataset.bounds),
            length_unit="mm",
            hierarchy=(
                {"id": "root", "name": name, "kind": "scene"},
            ),
            geometry_assets=(
                {
                    "id": "geometry:full",
                    "role": "full",
                    "path": str(display_path),
                    "format": ".vtp",
                    "content": "surface",
                    "attribute_colors": {
                        "available": True,
                        "array_name": "corex_source_rgba",
                        "valid_mask_name": "",
                        "association": "cell",
                        "component_count": 4,
                        "encoding": "uint8",
                        "source": "test",
                        "fallback_rgba": [208, 215, 222, 255],
                        "unsupported_reason": "",
                    },
                    "entity_arrays": {
                        "part_index": "corex_part_index",
                        "body_index": "corex_body_index",
                        "face_index": "corex_face_index",
                    },
                },
            ),
        )
        prepared = PreparedScene(descriptor=descriptor, dataset=dataset)
        return self.services.register_handle(
            prepared,
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope=f"cache:tests:{name}",
            metadata=PreparedSceneRuntime._handle_metadata(descriptor),
        )

    def _open_prepared_session(
        self,
        scene_ref: object,
        *,
        session_id: str,
        second_scene_ref: object | None = None,
    ) -> None:
        data_refs = {"scene_order": ["scene_1"], "scene:scene_1": scene_ref}
        if second_scene_ref is not None:
            data_refs["scene:scene_2"] = second_scene_ref
            data_refs["scene_order"].append("scene_2")
        service = self.services.viewer_session_service
        service.open_session(
            OpenViewerSessionCommand(
                workspace_id="workspace-engineering",
                node_id="node-engineering",
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                data_refs=data_refs,
                options={"representation": "surface", "show_mesh_edges": False},
            )
        )
        service.materialize_data(
            MaterializeViewerDataCommand(
                workspace_id="workspace-engineering",
                node_id="node-engineering",
                session_id=session_id,
                backend_id=ENGINEERING_VIEWER_BACKEND_ID,
            )
        )

    def test_prepared_scene_uses_owned_shared_memory_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            surface = pyvista.PolyData(
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                faces=[3, 0, 1, 2],
            )
            surface.cell_data["corex_source_rgba"] = [(10, 20, 30, 255)]
            surface.cell_data["corex_part_index"] = [1]
            surface.cell_data["corex_body_index"] = [1]
            surface.cell_data["corex_face_index"] = [1]
            scene_ref = self._prepared_scene_ref(
                root,
                name="shared-primary",
                dataset=surface,
            )

            first = self.backend.materialize(
                _request({"scene_order": ["scene_1"], "scene:scene_1": scene_ref})
            )
            second = self.backend.materialize(
                _request({"scene_order": ["scene_1"], "scene:scene_1": scene_ref})
            )
            forced = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": scene_ref},
                    options={"force_recompute": True},
                )
            )

            asset = first.transport["layers"][0]["display_asset"]
            self.assertEqual(
                set(asset),
                {
                    "schema",
                    "version",
                    "storage",
                    "name",
                    "byte_length",
                    "sha256",
                    "format",
                    "role",
                    "content",
                    "attribute_colors",
                    "entity_arrays",
                },
            )
            self.assertEqual(
                asset["schema"],
                ENGINEERING_VIEWER_SHARED_MEMORY_ASSET_SCHEMA,
            )
            self.assertEqual(asset["storage"], "shared_memory")
            self.assertEqual(asset["format"], "vtkxml-polydata")
            segment = SharedMemory(name=asset["name"], create=False)
            try:
                payload = bytes(segment.buf[: asset["byte_length"]])
            finally:
                segment.close()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), asset["sha256"])
            from vtkmodules.vtkIOXML import vtkXMLPolyDataReader

            reader = vtkXMLPolyDataReader()
            reader.SetReadFromInputString(True)
            reader.SetInputString(payload)
            reader.Update()
            round_trip = pyvista.wrap(reader.GetOutput())
            self.assertEqual(round_trip.n_points, surface.n_points)
            self.assertEqual(round_trip.n_cells, surface.n_cells)
            self.assertIn("corex_source_rgba", round_trip.cell_data)
            self.assertIn("corex_face_index", round_trip.cell_data)
            self.assertNotIn(asset["name"], json.dumps(scene_ref.metadata))
            self.assertEqual(second.transport_revision, first.transport_revision)
            self.assertEqual(
                second.transport["layers"][0]["display_asset"]["name"],
                asset["name"],
            )
            forced_name = forced.transport["layers"][0]["display_asset"]["name"]
            self.assertNotEqual(forced_name, asset["name"])

            self.backend.release_session_transport(
                workspace_id="workspace-engineering",
                session_id="session-engineering",
            )
            self.backend.release_session_transport(
                workspace_id="workspace-engineering",
                session_id="session-engineering",
            )
            for name in (asset["name"], forced_name):
                with self.assertRaises(FileNotFoundError):
                    SharedMemory(name=name, create=False)

    def test_shared_memory_partial_failure_and_scope_cleanup_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            primary_ref = self._prepared_scene_ref(
                root,
                name="partial-primary",
                dataset=pyvista.Cube().triangulate(),
            )
            overlay_ref = self._prepared_scene_ref(
                root,
                name="partial-overlay",
                dataset=pyvista.Sphere(theta_resolution=8, phi_resolution=8),
            )
            real_shared_memory = SharedMemory
            created_names: list[str] = []

            def allocate(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                if created_names:
                    raise OSError("simulated allocation failure")
                segment = real_shared_memory(*args, **kwargs)
                created_names.append(segment.name)
                return segment

            with mock.patch(
                "ea_node_editor.execution.viewer_backend_engineering.SharedMemory",
                side_effect=allocate,
            ):
                failed = self.backend.materialize(
                    _request(
                        {
                            "scene_order": ["scene_1", "scene_2"],
                            "scene:scene_1": primary_ref,
                            "scene:scene_2": overlay_ref,
                        },
                        session_id="session-partial",
                    )
                )

            self.assertEqual(failed.live_open_status, "blocked")
            self.assertEqual(
                failed.live_open_blocker["code"],
                "shared_memory_transport_unavailable",
            )
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=created_names[0], create=False)

            workspace_ready = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": primary_ref},
                    session_id="session-workspace",
                )
            )
            workspace_name = workspace_ready.transport["layers"][0]["display_asset"][
                "name"
            ]
            self.backend.release_workspace_transport(
                workspace_id="workspace-engineering"
            )
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=workspace_name, create=False)

            reset_ready = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": primary_ref},
                    session_id="session-reset",
                )
            )
            reset_name = reset_ready.transport["layers"][0]["display_asset"]["name"]
            self.backend.reset()
            self.backend.reset()
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=reset_name, create=False)

    def test_large_prepared_scene_metadata_is_bounded_while_viewer_resolves_full_descriptor(
        self,
    ) -> None:
        descriptor = SceneDescriptor(
            scene_id="scene-large",
            source_kind="fe",
            source=SceneSourceMetadata(
                source_path="large.vtu",
                resolved_path="large.vtu",
                source_format=".vtu",
                size_bytes=1,
                modified_time_ns=1,
                sha256="a" * 64,
            ),
            display_artifact_path="large.vtu",
            display_format=".vtu",
            cache_manifest_path="large.json",
            dataset_kind="unstructured",
            point_count=20_000,
            cell_count=20_000,
            block_count=20_000,
            bounds=(0.0, 1.0, 0.0, 1.0, 0.0, 1.0),
            length_unit="mm",
            point_arrays=tuple(f"point_{index}" for index in range(20_000)),
            cell_arrays=tuple(f"cell_{index}" for index in range(20_000)),
            hierarchy=tuple(
                {"id": f"block:{index}", "name": f"Block {index}"}
                for index in range(20_000)
            ),
            topology_mappings={
                "blocks": tuple({"id": index} for index in range(20_000))
            },
        )
        metadata = PreparedSceneRuntime._handle_metadata(descriptor)
        encoded = json.dumps(
            metadata,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        self.assertLess(len(encoded), 64 * 1024)
        self.assertNotIn("topology_mappings", metadata)
        for key in ("point_arrays", "cell_arrays", "hierarchy"):
            self.assertEqual(metadata[f"{key}_count"], 20_000)
            self.assertLessEqual(len(metadata[f"{key}_sample"]), 16)
            self.assertNotIn(key, metadata)

        prepared = PreparedScene(descriptor=descriptor, dataset=object())
        scene_ref = self.services.register_handle(
            prepared,
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="cache:tests:large_scene",
            metadata=metadata,
        )
        resolved = self.backend._resolve_prepared_scene(scene_ref)

        self.assertIs(resolved, prepared)
        self.assertEqual(len(resolved.descriptor.point_arrays), 20_000)
        self.assertEqual(len(resolved.descriptor.topology_mappings["blocks"]), 20_000)

    def test_plain_scene_mappings_build_ordered_three_scene_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            primary = root / "mesh.vtu"
            overlay = root / "selection.vtp"
            primary.write_text("primary", encoding="utf-8")
            overlay.write_text("overlay", encoding="utf-8")
            first_source = {
                "display_path": str(primary),
                "length_unit": "mm",
                "bounds": [0, 1, 0, 1, 0, 1],
                "style": {"scalars": "stress", "cmap": "viridis"},
            }
            source = {
                "scene_order": ["scene_1", "scene_2", "scene_3"],
                "scene_labels": {"scene_2": "Selection"},
                "scene:scene_1": first_source,
                "scene:scene_2": {
                    "display_path": str(overlay),
                    "style": {"color": "#00ff00"},
                    "length_unit": "mm",
                    "bounds": [0, 1, 0, 1, 0, 1],
                },
                "scene:scene_3": first_source,
            }
            styles = {"scene_styles": {"scene_2": {"opacity": 0.2, "color": "#ff0000"}}}
            first = self.backend.materialize(_request(source, session_options=styles))
            second = self.backend.materialize(_request(source, session_options=styles))
            forced = self.backend.materialize(
                _request(
                    source, options={"force_recompute": True}, session_options=styles
                )
            )

        self.assertEqual(first.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(first.live_open_status, "ready")
        self.assertEqual(first.transport["kind"], ENGINEERING_VIEWER_TRANSPORT_KIND)
        self.assertEqual(
            first.transport["layers"][0]["display_path"], str(primary.resolve())
        )
        self.assertEqual(first.transport["layers"][0]["style"]["scalars"], "stress")
        self.assertEqual(first.transport["layers"][1]["name"], "Selection")
        self.assertEqual(first.transport["layers"][1]["style"]["opacity"], 1.0)
        self.assertEqual(first.transport["schema"], "ea.corex.engineering_scene.v2")
        self.assertNotIn("primary", first.transport)
        self.assertNotIn("overlays", first.transport)
        self.assertEqual(
            [layer["id"] for layer in first.transport["layers"]],
            ["scene_1", "scene_2", "scene_3"],
        )
        self.assertEqual(first.transport["layers"][2]["style"]["opacity"], 1.0)
        self.assertEqual(first.transport["layers"][1]["style"]["color"], "#00ff00")
        self.assertTrue(
            all(layer["style"]["pickable"] for layer in first.transport["layers"])
        )
        self.assertEqual(first.summary["scene_layer_count"], 3)
        self.assertEqual(first.camera_state, {"position": [2.0, 3.0, 4.0]})
        self.assertEqual(first.transport_revision, 1)
        self.assertEqual(second.transport_revision, 1)
        self.assertEqual(forced.transport_revision, 2)

    def test_scene_bounds_are_combined_in_first_scene_display_units_for_fit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            primary_path = root / "primary.vtk"
            overlay_path = root / "overlay.vtk"
            primary_path.write_text("primary", encoding="utf-8")
            overlay_path.write_text("overlay", encoding="utf-8")
            result = self.backend.materialize(
                _request(
                    {
                        "scene_order": ["scene_1", "scene_2"],
                        "scene:scene_1": {
                            "display_path": str(primary_path),
                            "length_unit": "mm",
                            "bounds": [0, 10, 0, 10, 0, 10],
                        },
                        "scene:scene_2": {
                            "display_path": str(overlay_path),
                            "length_unit": "m",
                            "bounds": [0.02, 0.03, 0.02, 0.03, 0.02, 0.03],
                        },
                    }
                )
            )

        self.assertEqual(result.transport["layers"][1]["scale_factor"], 1000.0)
        self.assertEqual(
            result.transport["display_bounds"], [0.0, 30.0, 0.0, 30.0, 0.0, 30.0]
        )
        self.assertEqual(result.transport["fit"]["center"], [15.0, 15.0, 15.0])
        self.assertAlmostEqual(result.transport["fit"]["diagonal"], 30.0 * (3.0**0.5))

    def test_corex_scene_handle_uses_display_artifact_path_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            display_path = Path(temporary_directory) / "prepared.stl"
            display_path.write_text("solid prepared", encoding="utf-8")
            scene_ref = self.services.register_handle(
                {
                    "display_artifact_path": str(display_path),
                    "display_format": ".stl",
                    "source_kind": "cad",
                    "length_unit": "mm",
                    "bounds": [0, 1, 0, 1, 0, 1],
                },
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                owner_scope="cache:tests:engineering_scene",
            )

            result = self.backend.materialize(
                _request({"scene_order": ["scene_1"], "scene:scene_1": scene_ref})
            )

        self.assertEqual(result.live_open_status, "ready")
        self.assertEqual(
            result.transport["layers"][0]["display_path"], str(display_path.resolve())
        )
        self.assertEqual(result.summary["scene_layers"][0]["display_format"], "stl")

    def test_missing_display_file_returns_blocked_transport(self) -> None:
        missing = Path(tempfile.gettempdir()) / "corex_missing_engineering_scene.vtu"
        missing.unlink(missing_ok=True)

        result = self.backend.materialize(
            _request(
                {
                    "scene_order": ["scene_1"],
                    "scene:scene_1": {
                        "display_path": str(missing),
                        "length_unit": "mm",
                    },
                }
            )
        )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(result.live_open_blocker["code"], "display_file_missing")
        self.assertTrue(result.live_open_blocker["rerun_required"])
        self.assertEqual(result.transport, {})

    def test_exact_assets_project_capabilities_and_track_edge_file_revision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            coarse_path = root / "surface.coarse.vtp"
            full_path = root / "surface.full.vtp"
            edge_path = root / "topology_edges.vtp"
            coarse_path.write_text("coarse", encoding="utf-8")
            full_path.write_text("full", encoding="utf-8")
            edge_path.write_text("edges", encoding="utf-8")
            colors = {
                "available": True,
                "array_name": "corex_source_rgba",
                "valid_mask_name": "corex_source_color_valid",
                "association": "cell",
                "component_count": 4,
                "encoding": "uint8",
                "source": "xcaf",
                "fallback_rgba": [208, 215, 222, 255],
                "unsupported_reason": "",
            }
            source = {
                "display_artifact_path": str(full_path),
                "length_unit": "mm",
                "bounds": [0, 1, 0, 1, 0, 1],
                "geometry_assets": [
                    {
                        "id": "geometry:coarse",
                        "role": "coarse",
                        "path": str(coarse_path),
                        "format": ".vtp",
                        "content": "surface",
                        "attribute_colors": colors,
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "face_index": "corex_face_index",
                        },
                    },
                    {
                        "id": "geometry:full",
                        "role": "full",
                        "path": str(full_path),
                        "format": ".vtp",
                        "content": "surface",
                        "attribute_colors": colors,
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "face_index": "corex_face_index",
                        },
                    },
                    {
                        "id": "geometry:topology_edges",
                        "role": "topology_edges",
                        "path": str(edge_path),
                        "format": ".vtp",
                        "content": "topological_edges",
                        "attribute_colors": colors,
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "edge_index": "corex_edge_index",
                        },
                    },
                ],
            }

            first = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-exact-assets",
                )
            )
            second = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-exact-assets",
                )
            )
            edge_path.write_text("edges changed and longer", encoding="utf-8")
            changed = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-exact-assets",
                )
            )

        self.assertEqual(first.live_open_status, "ready")
        primary = first.transport["layers"][0]
        self.assertEqual(
            primary["interaction_display_path"], str(coarse_path.resolve())
        )
        self.assertEqual(primary["topological_edge_path"], str(edge_path.resolve()))
        self.assertEqual(primary["attribute_colors"]["array_name"], "corex_source_rgba")
        self.assertEqual(primary["entity_arrays"]["face_index"], "corex_face_index")
        self.assertTrue(first.summary["capabilities"]["topological_edges"])
        self.assertTrue(first.summary["capabilities"]["attribute_colors"])
        self.assertIn("surface_with_edges", first.summary["supported_render_modes"])
        self.assertEqual(first.transport_revision, 1)
        self.assertEqual(second.transport_revision, 1)
        self.assertEqual(changed.transport_revision, 2)

    def test_missing_declared_topology_edge_asset_blocks_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            full_path = root / "surface.full.vtp"
            missing_edge_path = root / "missing.topology_edges.vtp"
            full_path.write_text("full", encoding="utf-8")
            result = self.backend.materialize(
                _request(
                    {
                        "scene_order": ["scene_1"],
                        "scene:scene_1": {
                            "display_artifact_path": str(full_path),
                            "length_unit": "mm",
                            "bounds": [0, 1, 0, 1, 0, 1],
                            "geometry_assets": [
                                {
                                    "id": "geometry:full",
                                    "role": "full",
                                    "path": str(full_path),
                                    "format": ".vtp",
                                    "content": "surface",
                                },
                                {
                                    "id": "geometry:topology_edges",
                                    "role": "topology_edges",
                                    "path": str(missing_edge_path),
                                    "format": ".vtp",
                                    "content": "topological_edges",
                                },
                            ],
                        },
                    }
                )
            )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(result.live_open_blocker["code"], "topology_edge_file_missing")
        self.assertTrue(result.live_open_blocker["rerun_required"])

    def test_v4_scene_missing_required_selection_asset_blocks_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "mesh.vtu"
            pyvista.ImageData(dimensions=(2, 2, 2)).cast_to_unstructured_grid().save(
                source_path
            )
            scene_ref = self.services.prepared_scene_runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-v4-missing-asset",
            )
            prepared = self.services.resolve_handle(
                scene_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            descriptor = prepared.descriptor.to_payload()
            descriptor["geometry_assets"] = [
                asset
                for asset in descriptor["geometry_assets"]
                if asset["role"] != "selection_identity"
            ]

            result = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": descriptor},
                    session_id="session-v4-missing-selection-asset",
                )
            )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(result.live_open_blocker["code"], "scene_contract_invalid")
        self.assertTrue(result.live_open_blocker["rerun_required"])
        self.assertIn("selection_identity", result.live_open_blocker["reason"])

    def test_selection_topology_projects_exact_filters_and_rejects_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            full_path = root / "surface.full.vtp"
            edge_path = root / "topology_edges.vtp"
            vertex_path = root / "topology_vertices.vtp"
            topology_path = root / "selection_topology.json"
            surface = pyvista.PolyData(
                [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                faces=[3, 0, 1, 2],
            )
            surface.cell_data["corex_part_index"] = [1]
            surface.cell_data["corex_body_index"] = [1]
            surface.cell_data["corex_face_index"] = [1]
            surface.save(full_path)
            edges = pyvista.Line((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
            edges.cell_data["corex_part_index"] = [1]
            edges.cell_data["corex_edge_index"] = [1]
            edges.save(edge_path)
            vertices = pyvista.PolyData([(0.0, 0.0, 0.0)], verts=[1, 0])
            vertices.cell_data["corex_part_index"] = [1]
            vertices.cell_data["corex_vertex_index"] = [1]
            vertices.save(vertex_path)
            topology_payload = {
                "schema": "corex.selection_topology.v1",
                "parts": [
                    {
                        "part_index": 1,
                        "hierarchy_id": "cad:body:0",
                        "vertices": [
                            {
                                "id": "part:1/vertex:1",
                                "part_index": 1,
                                "vertex_index": 1,
                                "edge_ids": ["part:1/edge:1"],
                            }
                        ],
                        "edges": [
                            {
                                "id": "part:1/edge:1",
                                "part_index": 1,
                                "edge_index": 1,
                                "vertex_ids": ["part:1/vertex:1"],
                                "face_ids": ["part:1/face:1"],
                            }
                        ],
                        "faces": [
                            {
                                "id": "part:1/face:1",
                                "part_index": 1,
                                "face_index": 1,
                                "body_ids": ["part:1/body:1"],
                                "edge_ids": ["part:1/edge:1"],
                            }
                        ],
                        "bodies": [
                            {
                                "id": "part:1/body:1",
                                "part_index": 1,
                                "body_index": 1,
                                "body_kind": "solid",
                                "face_ids": ["part:1/face:1"],
                            }
                        ],
                    }
                ],
                "blocks": [],
                "edge_continuity": [],
                "face_continuity": [],
                "capabilities": {
                    "cad_vertex_selection": {
                        "available": True,
                        "unsupported_reason": "",
                    },
                    "cad_edge_selection": {"available": True, "unsupported_reason": ""},
                    "cad_face_selection": {"available": True, "unsupported_reason": ""},
                    "cad_body_selection": {"available": True, "unsupported_reason": ""},
                    "fe_node_selection": {
                        "available": False,
                        "unsupported_reason": "CAD sources do not define FE nodes.",
                    },
                    "fe_element_face_selection": {
                        "available": False,
                        "unsupported_reason": "CAD sources do not define FE element faces.",
                    },
                    "fe_element_selection": {
                        "available": False,
                        "unsupported_reason": "CAD sources do not define FE elements.",
                    },
                    "tangent_edge_propagation": {
                        "available": False,
                        "unsupported_reason": "The topology has no adjacent edge pairs.",
                    },
                    "tangent_face_propagation": {
                        "available": False,
                        "unsupported_reason": "The topology has no adjacent face pairs.",
                    },
                },
            }
            topology_bytes = json.dumps(
                topology_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            topology_path.write_bytes(topology_bytes)
            topology_asset = {
                "id": "selection:topology",
                "role": "selection_topology",
                "path": str(topology_path),
                "format": ".json",
                "content": "selection_topology",
                "schema": "corex.selection_topology.v1",
                "sha256": hashlib.sha256(topology_bytes).hexdigest(),
            }
            source = {
                "display_artifact_path": str(full_path),
                "length_unit": "mm",
                "bounds": [0, 1, 0, 1, 0, 1],
                "geometry_assets": [
                    {
                        "id": "geometry:full",
                        "role": "full",
                        "path": str(full_path),
                        "format": ".vtp",
                        "content": "surface",
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "body_index": "corex_body_index",
                            "face_index": "corex_face_index",
                        },
                    },
                    {
                        "id": "geometry:topology_edges",
                        "role": "topology_edges",
                        "path": str(edge_path),
                        "format": ".vtp",
                        "content": "topological_edges",
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "edge_index": "corex_edge_index",
                        },
                    },
                    {
                        "id": "geometry:topology_vertices",
                        "role": "topology_vertices",
                        "path": str(vertex_path),
                        "format": ".vtp",
                        "content": "topological_vertices",
                        "entity_arrays": {
                            "part_index": "corex_part_index",
                            "vertex_index": "corex_vertex_index",
                        },
                    },
                    topology_asset,
                ],
            }

            original_read_bytes = Path.read_bytes
            topology_reads: list[Path] = []

            def read_bytes_once(path: Path) -> bytes:
                if path == topology_path:
                    topology_reads.append(path)
                return original_read_bytes(path)

            with mock.patch.object(
                Path, "read_bytes", autospec=True, side_effect=read_bytes_once
            ):
                result = self.backend.materialize(
                    _request(
                        {"scene_order": ["scene_1"], "scene:scene_1": source},
                        session_id="session-selection-topology",
                    )
                )
            self.assertEqual(result.live_open_status, "ready")
            self.assertEqual(topology_reads, [topology_path])
            self.assertEqual(result.summary["default_selection_filter"], "cad_body")
            filters = {
                entry["id"]: entry
                for entry in result.summary["supported_selection_filters"]
            }
            self.assertTrue(filters["cad_vertex"]["available"])
            self.assertFalse(filters["fe_node"]["available"])
            self.assertEqual(
                result.summary["capabilities"]["selection_filter_reasons"]["fe_node"],
                "CAD sources do not define FE nodes.",
            )

            source_without_vertices = {
                **source,
                "geometry_assets": [
                    asset
                    for asset in source["geometry_assets"]
                    if asset["role"] != "topology_vertices"
                ],
            }
            unsupported = self.backend.materialize(
                _request(
                    {
                        "scene_order": ["scene_1"],
                        "scene:scene_1": source_without_vertices,
                    },
                    session_id="session-selection-topology-assets",
                )
            )
            self.assertEqual(unsupported.live_open_status, "blocked")
            self.assertEqual(
                unsupported.live_open_blocker["code"],
                "selection_topology_assets_mismatch",
            )

            topology_path.write_text("{}", encoding="utf-8")
            blocked = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-selection-topology",
                )
            )
            self.assertEqual(blocked.live_open_status, "blocked")
            self.assertEqual(
                blocked.live_open_blocker["code"], "selection_topology_mismatch"
            )

    def test_corrupt_exact_selection_asset_blocks_live_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source, paths = _write_cad_selection_source(Path(temporary_directory))
            paths["edges"].write_text("not a VTP file", encoding="utf-8")

            result = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-corrupt-selection-asset",
                )
            )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(
            result.live_open_blocker["code"],
            "selection_topology_assets_mismatch",
        )
        self.assertIn("topology_edges", result.live_open_blocker["reason"])

    def test_rechecks_topology_relationships_after_checksum_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source, paths = _write_cad_selection_source(Path(temporary_directory))
            topology = json.loads(paths["topology"].read_text(encoding="utf-8"))
            topology["parts"][0]["faces"][0]["edge_ids"] = ["part:1/edge:2"]
            topology_bytes = json.dumps(
                topology,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            paths["topology"].write_bytes(topology_bytes)
            topology_asset = next(
                asset
                for asset in source["geometry_assets"]
                if asset["role"] == "selection_topology"
            )
            topology_asset["sha256"] = hashlib.sha256(topology_bytes).hexdigest()

            result = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-invalid-topology-relationships",
                )
            )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(result.live_open_blocker["code"], "selection_topology_invalid")
        self.assertIn("unknown reference", result.live_open_blocker["reason"])

    def test_canonical_identity_values_must_cover_the_topology_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source, paths = _write_cad_selection_source(Path(temporary_directory))
            edges = pyvista.read(paths["edges"])
            edges.cell_data["corex_edge_index"] = [2]
            edges.save(paths["edges"])

            result = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-incomplete-canonical-identities",
                )
            )

        self.assertEqual(result.live_open_status, "blocked")
        self.assertEqual(
            result.live_open_blocker["code"],
            "selection_topology_assets_mismatch",
        )
        self.assertIn("identities for CAD edges", result.live_open_blocker["reason"])

    def test_cad_selection_assets_require_arrays_in_cell_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing_source, missing_paths = _write_cad_selection_source(
                root / "missing"
            )
            vertices = pyvista.read(missing_paths["vertices"])
            del vertices.cell_data["corex_vertex_index"]
            vertices.save(missing_paths["vertices"])

            missing = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": missing_source},
                    session_id="session-missing-selection-array",
                )
            )

            wrong_source, wrong_paths = _write_cad_selection_source(root / "wrong")
            surface = pyvista.read(wrong_paths["full"])
            del surface.cell_data["corex_face_index"]
            surface.point_data["corex_face_index"] = [1] * surface.n_points
            surface.save(wrong_paths["full"])
            wrong = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": wrong_source},
                    session_id="session-wrong-selection-association",
                )
            )

        self.assertEqual(missing.live_open_status, "blocked")
        self.assertEqual(
            missing.live_open_blocker["code"],
            "selection_topology_assets_mismatch",
        )
        self.assertIn("corex_vertex_index", missing.live_open_blocker["reason"])
        self.assertIn("is missing", missing.live_open_blocker["reason"])
        self.assertEqual(wrong.live_open_status, "blocked")
        self.assertEqual(
            wrong.live_open_blocker["code"],
            "selection_topology_assets_mismatch",
        )
        self.assertIn("corex_face_index", wrong.live_open_blocker["reason"])
        self.assertIn("stored in point_data", wrong.live_open_blocker["reason"])

    def test_fe_selection_assets_validate_node_element_and_exterior_face_arrays(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source, paths = _write_fe_selection_source(root / "ready")
            ready = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": source},
                    session_id="session-fe-selection-ready",
                )
            )

            missing_source, missing_paths = _write_fe_selection_source(root / "missing")
            faces = pyvista.read(missing_paths["faces"])
            del faces.cell_data["corex_element_face_index"]
            faces.save(missing_paths["faces"])
            missing = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": missing_source},
                    session_id="session-fe-face-array-missing",
                )
            )

            wrong_source, wrong_paths = _write_fe_selection_source(root / "wrong")
            identity = pyvista.read(wrong_paths["identity"])
            del identity.point_data["corex_node_index"]
            identity.cell_data["corex_node_index"] = [0] * identity.n_cells
            identity.save(wrong_paths["identity"])
            wrong = self.backend.materialize(
                _request(
                    {"scene_order": ["scene_1"], "scene:scene_1": wrong_source},
                    session_id="session-fe-node-array-wrong-association",
                )
            )

        self.assertEqual(ready.live_open_status, "ready")
        filters = {
            entry["id"]: entry for entry in ready.summary["supported_selection_filters"]
        }
        self.assertTrue(filters["fe_node"]["available"])
        self.assertTrue(filters["fe_element_face"]["available"])
        self.assertTrue(filters["fe_element"]["available"])
        self.assertEqual(missing.live_open_status, "blocked")
        self.assertIn("corex_element_face_index", missing.live_open_blocker["reason"])
        self.assertEqual(wrong.live_open_status, "blocked")
        self.assertIn("corex_node_index", wrong.live_open_blocker["reason"])
        self.assertIn("stored in cell_data", wrong.live_open_blocker["reason"])

    def test_display_capabilities_include_additional_scene_topology_colors(
        self,
    ) -> None:
        capabilities = self.backend._display_capabilities(  # noqa: SLF001
            [
                {
                    "display_path": "primary.vtp",
                    "attribute_colors": {"available": False},
                    "geometry_assets": [],
                },
                {
                    "display_path": "overlay.vtp",
                    "topological_edge_path": "overlay.edges.vtp",
                    "attribute_colors": {"available": False},
                    "geometry_assets": [
                        {
                            "content": "topological_edges",
                            "attribute_colors": {"available": True},
                        }
                    ],
                },
            ],
        )

        self.assertTrue(capabilities["topological_edges"])
        self.assertTrue(capabilities["attribute_colors"])
        self.assertTrue(capabilities["topological_edge_colors"])
        for capability in (
            "camera_bookmarks",
            "fit_selection",
            "orientation_triad",
            "projection",
            "selection_isolate",
            "view_cube",
            "wireframe_visible_edges",
            "world_axes",
        ):
            self.assertTrue(capabilities[capability])
        self.assertIn(
            "surface_with_edges",
            self.backend._supported_render_modes(capabilities),  # noqa: SLF001
        )

    def test_viewer_session_service_registers_and_resets_backend(self) -> None:
        service = self.services.viewer_session_service
        registered = self.services.viewer_backend_registry.resolve(
            ENGINEERING_VIEWER_BACKEND_ID
        )
        self.assertIsInstance(registered, EngineeringViewerBackend)

        with tempfile.TemporaryDirectory() as temporary_directory:
            display_path = Path(temporary_directory) / "mesh.vtk"
            display_path.write_text("mesh", encoding="utf-8")
            request = _request(
                {
                    "scene_order": ["scene_1"],
                    "scene:scene_1": {
                        "display_path": str(display_path),
                        "length_unit": "mm",
                    },
                }
            )
            self.assertEqual(registered.materialize(request).transport_revision, 1)
            self.assertEqual(registered.materialize(request).transport_revision, 1)
            service.reset()
            self.assertEqual(registered.materialize(request).transport_revision, 1)

    def test_viewer_session_service_materializes_corex_scene_transport(self) -> None:
        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            display_path = Path(temporary_directory) / "prepared.vtm"
            display_path.write_text("scene", encoding="utf-8")
            scene_ref = self.services.register_handle(
                {
                    "display_artifact_path": str(display_path),
                    "length_unit": "mm",
                    "bounds": [0, 1, 0, 1, 0, 1],
                },
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind=COREX_SCENE_HANDLE_KIND,
                owner_scope="cache:tests:session_scene",
            )
            opened = service.open_session(
                OpenViewerSessionCommand(
                    request_id="open-engineering",
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering-service",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs={"scene_order": ["scene_1"], "scene:scene_1": scene_ref},
                )
            )
            materialized = service.materialize_data(
                MaterializeViewerDataCommand(
                    request_id="materialize-engineering",
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-engineering-service",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                )
            )

        self.assertEqual(opened.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
        self.assertIsInstance(materialized, ViewerDataMaterializedEvent)
        self.assertEqual(materialized.backend_id, ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(materialized.live_open_status, "ready")
        self.assertEqual(
            materialized.transport["kind"], ENGINEERING_VIEWER_TRANSPORT_KIND
        )

    def test_session_queries_measure_mesh_and_export_vtk(self) -> None:
        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "cube.stl"
            export_path = root / "cube.vtk"
            pyvista.Cube(x_length=2.0, y_length=3.0, z_length=4.0).triangulate().save(
                source_path
            )
            scene_ref = self.services.prepared_scene_runtime.prepare_cad_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-engineering",
            )
            service.open_session(
                OpenViewerSessionCommand(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-query",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs={"scene_order": ["scene_1"], "scene:scene_1": scene_ref},
                )
            )
            service.materialize_data(
                MaterializeViewerDataCommand(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-query",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                )
            )

            distance = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-query",
                query_type="distance",
                payload={"point_a": [0, 0, 0], "point_b": [3, 4, 0]},
            )
            properties = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-query",
                query_type="mass_properties",
            )
            exported = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-query",
                query_type="export",
                payload={"path": str(export_path), "format": "vtk"},
            )

            self.assertTrue(distance.supported)
            self.assertEqual(distance.value["distance"], 5.0)
            self.assertEqual(distance.value["length_unit"], "mm")
            self.assertTrue(properties.supported)
            self.assertEqual(properties.value["method"], "mesh_derived")
            self.assertAlmostEqual(properties.value["volume"], 24.0, places=4)
            self.assertTrue(exported.supported)
            self.assertTrue(export_path.is_file())

    def test_entity_queries_use_stable_topology_and_radius_is_not_inferred(
        self,
    ) -> None:
        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "cube.stl"
            pyvista.Cube().triangulate().save(source_path)
            scene_ref = self.services.prepared_scene_runtime.prepare_cad_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-engineering",
            )
            self._open_prepared_session(scene_ref, session_id="session-topology")

            point = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-topology",
                query_type="entity_info",
                payload={"entity_kind": "point", "entity_id": "0"},
            )
            cell = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-topology",
                query_type="entity_info",
                payload={"entity_kind": "cell", "entity_id": "0"},
            )
            face = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-topology",
                query_type="entity_info",
                payload={"entity_kind": "face", "entity_id": "0"},
            )
            radius = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-topology",
                query_type="radius",
                payload={"center": [0, 0, 0], "point": [1, 0, 0]},
            )

        self.assertTrue(point.supported, point.explanation)
        self.assertEqual(len(point.value["coordinates"]), 3)
        self.assertTrue(point.value["stable_for_source_fingerprint"])
        self.assertTrue(cell.supported, cell.explanation)
        self.assertGreater(len(cell.value["point_ids"]), 0)
        self.assertFalse(face.supported)
        self.assertFalse(radius.supported)
        self.assertIn("does not infer", radius.explanation)

    def test_fe_mass_properties_are_unavailable_without_physical_data(self) -> None:
        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "mesh.vtu"
            pyvista.Cube().cast_to_unstructured_grid().save(source_path)
            scene_ref = self.services.prepared_scene_runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-engineering",
            )
            self._open_prepared_session(scene_ref, session_id="session-fe-mass")
            result = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-fe-mass",
                query_type="mass_properties",
            )

        self.assertFalse(result.supported)
        self.assertIn("FE datasets", result.explanation)

    def test_vtm_and_glb_exports_honor_visible_layers_and_display_scale(self) -> None:
        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            primary_path = root / "primary.stl"
            overlay_path = root / "overlay.stl"
            vtm_path = root / "visible.vtm"
            glb_path = root / "visible.glb"
            hidden_path = root / "hidden.glb"
            pyvista.Cube().triangulate().save(primary_path)
            pyvista.Sphere(radius=0.25).triangulate().save(overlay_path)
            primary_ref = self.services.prepared_scene_runtime.prepare_cad_scene(
                primary_path,
                length_unit="mm",
                workspace_id="workspace-engineering",
            )
            overlay_ref = self.services.prepared_scene_runtime.prepare_cad_scene(
                overlay_path,
                length_unit="m",
                workspace_id="workspace-engineering",
            )
            self._open_prepared_session(
                primary_ref,
                second_scene_ref=overlay_ref,
                session_id="session-visible-export",
            )
            vtm = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-visible-export",
                query_type="export",
                payload={
                    "path": str(vtm_path),
                    "format": "vtm",
                    "layer_visibility": {"scene_1": False, "scene_2": True},
                },
            )
            glb = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-visible-export",
                query_type="export",
                payload={
                    "path": str(glb_path),
                    "format": "glb",
                    "layer_visibility": {"scene_1": False, "scene_2": True},
                },
            )
            hidden = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-visible-export",
                query_type="export",
                payload={
                    "path": str(hidden_path),
                    "format": "glb",
                    "layer_visibility": {"scene_1": False, "scene_2": False},
                },
            )

            self.assertTrue(vtm.supported, vtm.explanation)
            self.assertEqual(vtm.value["visible_layers"], ["Scene 2"])
            self.assertEqual(pyvista.read(vtm_path).n_blocks, 1)
            self.assertTrue(glb.supported, glb.explanation)
            self.assertEqual(glb_path.read_bytes()[:4], b"glTF")
            self.assertEqual(glb.value["visible_layers"], ["Scene 2"])
            self.assertFalse(hidden.supported)
            self.assertFalse(hidden_path.exists())

    def test_exact_step_mass_properties_and_round_trip_export(self) -> None:
        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        except ModuleNotFoundError:
            self.skipTest("cadquery-ocp-novtk is not installed")

        service = self.services.viewer_session_service
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "box.step"
            export_path = root / "box_export.step"
            shape = BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape()
            writer = STEPControl_Writer()
            writer.Transfer(shape, STEPControl_AsIs)
            self.assertEqual(writer.Write(str(source_path)), IFSelect_RetDone)

            scene_ref = self.services.prepared_scene_runtime.prepare_cad_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-engineering",
            )
            prepared = self.services.resolve_handle(
                scene_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            part_index = int(prepared.dataset.cell_data["corex_part_index"][0])
            face_index = int(prepared.dataset.cell_data["corex_face_index"][0])
            selected_face_id = f"part:{part_index}/face:{face_index}"
            self.assertIn(
                selected_face_id,
                {
                    entity["id"]
                    for entity in prepared.descriptor.topology_mappings["faces"][
                        "entities"
                    ]
                },
            )
            service.open_session(
                OpenViewerSessionCommand(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-exact-query",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                    data_refs={"scene_order": ["scene_1"], "scene:scene_1": scene_ref},
                )
            )
            service.materialize_data(
                MaterializeViewerDataCommand(
                    workspace_id="workspace-engineering",
                    node_id="node-engineering",
                    session_id="session-exact-query",
                    backend_id=ENGINEERING_VIEWER_BACKEND_ID,
                )
            )
            properties = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-exact-query",
                query_type="mass_properties",
            )
            selected_face = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-exact-query",
                query_type="entity_info",
                payload={"entity_kind": "face", "entity_id": selected_face_id},
            )
            exported = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-exact-query",
                query_type="export",
                payload={"path": str(export_path), "format": "step"},
            )
            hidden_export = service.query_session(
                workspace_id="workspace-engineering",
                session_id="session-exact-query",
                query_type="export",
                payload={
                    "path": str(root / "hidden.step"),
                    "format": "step",
                    "layer_visibility": {"scene_1": False},
                },
            )

            self.assertTrue(properties.supported, properties.explanation)
            self.assertEqual(properties.value["method"], "exact_brep")
            self.assertAlmostEqual(properties.value["surface_area"], 52.0, places=5)
            self.assertAlmostEqual(properties.value["volume"], 24.0, places=5)
            self.assertEqual(properties.value["center_of_mass"], [1.0, 1.5, 2.0])
            self.assertTrue(selected_face.supported, selected_face.explanation)
            self.assertEqual(selected_face.value["part_index"], part_index)
            self.assertEqual(selected_face.value["face_index"], face_index)
            self.assertTrue(exported.supported, exported.explanation)
            self.assertTrue(export_path.is_file())
            self.assertFalse(hidden_export.supported)


if __name__ == "__main__":
    unittest.main()
