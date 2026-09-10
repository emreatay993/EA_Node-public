from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pyvista

from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_DATA_TYPE,
    COREX_SCENE_HANDLE_KIND,
    COREX_SCENE_SCHEMA,
    ENGINEERING_SELECTION_SCHEMA,
    SCENE_IMPORTER_VERSION,
    SceneDescriptor,
    normalize_engineering_selection_set,
    validate_engineering_selection_topology,
    validate_scene_bundle,
)
from ea_node_editor.execution.prepared_scene_runtime import (
    PreparedScene,
    PreparedSceneRuntime,
    _CadMetadata,
)
from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.execution.worker_services import WorkerServices
from tests.typed_handle_support import core_worker_services
from ea_node_editor.graph.effective_ports import ports_compatible
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.engineering_imports import execute_engineering_import
from ea_node_editor.nodes.execution_context import ExecutionContext


def _write_vtu(path: Path) -> None:
    dataset = pyvista.ImageData(dimensions=(2, 2, 2)).cast_to_unstructured_grid()
    dataset.point_data["temperature"] = list(range(dataset.n_points))
    dataset.save(path)


def _services(cache_root: Path) -> WorkerServices:
    services = core_worker_services()
    services._prepared_scene_runtime = PreparedSceneRuntime(  # noqa: SLF001
        services,
        cache_root=cache_root,
    )
    return services


def _write_xcaf_step(path: Path) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
    from OCP.gp import gp_Trsf, gp_Vec

    document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())
    part_shape = BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape()
    part_label = shape_tool.AddShape(part_shape, False)
    TDataStd_Name.Set_s(part_label, TCollection_ExtendedString("Named Box"))
    color_tool.SetColor(
        part_label,
        Quantity_Color(0.2, 0.4, 0.6, Quantity_TOC_RGB),
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
    )
    face_explorer = TopExp_Explorer(part_shape, TopAbs_FACE)
    face_label = shape_tool.AddSubShape(
        part_label,
        TopoDS.Face_s(face_explorer.Current()),
    )
    color_tool.SetColor(
        face_label,
        Quantity_Color(0.9, 0.1, 0.2, Quantity_TOC_RGB),
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
    )
    layer_tool.SetLayer(part_label, TCollection_ExtendedString("Primary Layer"))
    assembly_label = shape_tool.NewShape()
    TDataStd_Name.Set_s(
        assembly_label,
        TCollection_ExtendedString("Named Assembly"),
    )
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(10.0, 0.0, 0.0))
    instance_label = shape_tool.AddComponent(
        assembly_label,
        part_label,
        TopLoc_Location(transform),
    )
    TDataStd_Name.Set_s(
        instance_label,
        TCollection_ExtendedString("Named Box Instance"),
    )
    shape_tool.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)
    if (
        writer.Transfer(document) is False
        or writer.Write(str(path)).name != "IFSelect_RetDone"
    ):
        raise RuntimeError("Could not create STEP/XCAF test input.")


def _valid_scene_bundle() -> dict[str, object]:
    return {
        "schema": COREX_SCENE_SCHEMA,
        "scene_id": f"scene:{'a' * 64}",
        "source_kind": "fe",
        "source": {
            "source_path": "result.vtu",
            "resolved_path": str(Path("result.vtu").resolve()),
            "source_format": ".vtu",
            "size_bytes": 12,
            "modified_time_ns": 34,
            "sha256": "a" * 64,
        },
        "display_artifact_path": "result.vtu",
        "display_format": ".vtu",
        "cache_manifest_path": "result.scene.json",
        "dataset_kind": "UnstructuredGrid",
        "point_count": 8,
        "cell_count": 1,
        "block_count": 1,
        "bounds": [0, 1, 0, 1, 0, 1],
        "length_unit": "mm",
        "coordinate_system": "model",
        "importer_version": SCENE_IMPORTER_VERSION,
        "point_arrays": ["temperature"],
        "cell_arrays": [],
        "hierarchy": [
            {
                "id": "scene:root",
                "parent_id": "",
                "name": "result.vtu",
                "kind": "scene",
                "visible": True,
            }
        ],
        "geometry_assets": [
            {
                "id": "geometry:full",
                "role": "full",
                "path": "result.vtu",
                "format": ".vtu",
                "content": "mesh",
                "attribute_colors": {
                    "available": False,
                    "array_name": "",
                    "valid_mask_name": "",
                    "association": "",
                    "component_count": 0,
                    "encoding": "",
                    "source": "",
                    "fallback_rgba": [208, 215, 222, 255],
                    "unsupported_reason": "No direct colors.",
                },
                "entity_arrays": {},
            },
            {
                "id": "selection:mesh_identity",
                "role": "selection_identity",
                "path": "result.selection.vtu",
                "format": ".vtu",
                "content": "mesh",
                "attribute_colors": {
                    "available": False,
                    "array_name": "",
                    "valid_mask_name": "",
                    "association": "",
                    "component_count": 0,
                    "encoding": "",
                    "source": "",
                    "fallback_rgba": [208, 215, 222, 255],
                    "unsupported_reason": "Selection-only asset.",
                },
                "entity_arrays": {
                    "block_index": "corex_block_index",
                    "node_index": "corex_node_index",
                    "element_index": "corex_element_index",
                },
            },
            {
                "id": "selection:element_faces",
                "role": "element_faces",
                "path": "result.element_faces.vtp",
                "format": ".vtp",
                "content": "element_faces",
                "attribute_colors": {
                    "available": False,
                    "array_name": "",
                    "valid_mask_name": "",
                    "association": "",
                    "component_count": 0,
                    "encoding": "",
                    "source": "",
                    "fallback_rgba": [208, 215, 222, 255],
                    "unsupported_reason": "Selection-only asset.",
                },
                "entity_arrays": {
                    "block_index": "corex_block_index",
                    "element_index": "corex_element_index",
                    "element_face_index": "corex_element_face_index",
                },
            },
            {
                "id": "selection:topology",
                "role": "selection_topology",
                "path": "result.selection_topology.json",
                "format": ".json",
                "content": "selection_topology",
                "schema": "corex.selection_topology.v1",
                "sha256": "b" * 64,
                "attribute_colors": {
                    "available": False,
                    "array_name": "",
                    "valid_mask_name": "",
                    "association": "",
                    "component_count": 0,
                    "encoding": "",
                    "source": "",
                    "fallback_rgba": [208, 215, 222, 255],
                    "unsupported_reason": "Non-renderable metadata.",
                },
                "entity_arrays": {},
            },
        ],
        "topology_mappings": {},
        "result_fields": [
            {
                "name": "temperature",
                "location": "point",
                "component_count": 1,
                "components": ["value"],
                "data_type": "float64",
                "unit": "K",
                "deformation_candidate": False,
            }
        ],
        "time_steps": [],
        "deformation": {
            "available": False,
            "enabled": False,
            "scale_factor": 1.0,
            "field_name": "",
            "location": "",
        },
        "capabilities": ["geometry"],
        "provenance": {"importer": "tests"},
    }


def _context(*, path: Path, services: WorkerServices) -> ExecutionContext:
    return ExecutionContext(
        run_id="run_engineering_import",
        node_id="node_engineering_import",
        workspace_id="workspace_engineering_import",
        inputs={},
        properties={"path": str(path), "length_unit": "mm"},
        emit_log=lambda _level, _message: None,
        worker_services=services,
    )


class PreparedSceneRuntimeTests(unittest.TestCase):
    def test_ocp_shape_prepares_memory_scene_without_geometry_files(self) -> None:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            services = _services(root / "cache")
            shape = BRepPrimAPI_MakeCylinder(2.0, 5.0).Shape()
            source_identity = "ocp-body:abc:worker-generation:1"
            expected_fingerprint = hashlib.sha256(
                source_identity.encode("utf-8")
            ).hexdigest()

            scene_ref = services.prepared_scene_runtime.prepare_cad_shape(
                shape,
                source_identity=source_identity,
                owner_scope="run:ocp-shape",
            )
            prepared = services.resolve_handle(
                scene_ref,
                expected_data_type=COREX_SCENE_DATA_TYPE,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )

            self.assertEqual(list(root.rglob("*")), [])
            self.assertIsInstance(prepared, PreparedScene)
            self.assertIs(prepared.exact_model, shape)
            self.assertEqual(prepared.descriptor.storage, "memory")
            self.assertEqual(prepared.descriptor.display_artifact_path, "")
            self.assertEqual(prepared.descriptor.cache_manifest_path, "")
            self.assertEqual(prepared.descriptor.display_format, ".vtp")
            self.assertEqual(prepared.descriptor.length_unit, "m")
            self.assertEqual(
                prepared.descriptor.source.sha256,
                expected_fingerprint,
            )
            self.assertEqual(
                prepared.descriptor.scene_id,
                f"scene:{expected_fingerprint}",
            )
            self.assertTrue(
                prepared.descriptor.source.source_path.startswith(
                    "memory://corex/OCPBody"
                )
            )
            self.assertTrue(
                prepared.descriptor.source.resolved_path.endswith(
                    expected_fingerprint
                )
            )
            self.assertTrue(
                all(not asset["path"] for asset in prepared.descriptor.geometry_assets)
            )
            for array_name in (
                "corex_part_index",
                "corex_body_index",
                "corex_face_index",
            ):
                self.assertIn(array_name, prepared.dataset.cell_data)
            self.assertTrue(np.all(prepared.dataset.cell_data["corex_body_index"] == 1))
            self.assertGreater(
                len(np.unique(prepared.dataset.cell_data["corex_face_index"])),
                1,
            )
            encoded_metadata = json.dumps(scene_ref.metadata, allow_nan=False)
            self.assertIn('"storage": "memory"', encoded_metadata)
            self.assertNotIn("shared_memory", encoded_metadata)
            self.assertNotIn("TopoDS", encoded_metadata)
            self.assertNotIn(".vtp", encoded_metadata)
            self.assertNotIn("cache_manifest_path", scene_ref.metadata)

    def test_fe_vtu_prepares_neutral_scene_and_reuses_unchanged_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")

            first_ref = services.prepared_scene_runtime.prepare_fe_scene(
                source_path, length_unit="mm"
            )
            second_ref = services.prepared_scene_runtime.prepare_fe_scene(
                source_path, length_unit="mm"
            )
            prepared = services.resolve_handle(
                first_ref, expected_kind=COREX_SCENE_HANDLE_KIND
            )

            self.assertEqual(first_ref.handle_id, second_ref.handle_id)
            self.assertIsInstance(prepared, PreparedScene)
            self.assertEqual(prepared.descriptor.schema, COREX_SCENE_SCHEMA)
            self.assertEqual(prepared.descriptor.source_kind, "fe")
            self.assertEqual(prepared.descriptor.source.source_format, ".vtu")
            self.assertEqual(prepared.descriptor.source.source_path, str(source_path))
            self.assertEqual(
                prepared.descriptor.source.resolved_path, str(source_path.resolve())
            )
            self.assertEqual(
                prepared.descriptor.display_artifact_path, str(source_path.resolve())
            )
            self.assertEqual(prepared.descriptor.display_format, ".vtu")
            self.assertEqual(prepared.descriptor.length_unit, "mm")
            self.assertEqual(len(prepared.descriptor.source.sha256), 64)
            self.assertEqual(prepared.descriptor.point_count, 8)
            self.assertEqual(prepared.descriptor.cell_count, 1)
            self.assertIn("temperature", prepared.descriptor.point_arrays)
            self.assertEqual(prepared.descriptor.hierarchy[0]["id"], "scene:root")
            self.assertEqual(prepared.descriptor.geometry_assets[0]["role"], "full")
            assets = {
                asset["role"]: asset for asset in prepared.descriptor.geometry_assets
            }
            selection_topology = json.loads(
                Path(assets["selection_topology"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                selection_topology["blocks"][0]["element_face_id_array"], ""
            )
            self.assertTrue(
                selection_topology["blocks"][0]["element_face_id_unsupported_reason"]
            )
            self.assertEqual(
                prepared.descriptor.result_fields[0]["name"], "temperature"
            )
            self.assertIn("scalar_results", prepared.descriptor.capabilities)
            self.assertEqual(
                prepared.descriptor.provenance["source_sha256"],
                prepared.descriptor.source.sha256,
            )
            manifest_path = Path(prepared.descriptor.cache_manifest_path)
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["scene"]["schema"], COREX_SCENE_SCHEMA)
            self.assertEqual(manifest["import_settings"]["length_unit"], "mm")
            self.assertEqual(first_ref.metadata["schema"], COREX_SCENE_SCHEMA)
            self.assertEqual(
                first_ref.metadata["source"]["source_path"],
                source_path.name,
            )
            self.assertEqual(
                first_ref.metadata["point_count"],
                prepared.descriptor.point_count,
            )
            self.assertNotIn(
                "cache_manifest_path",
                first_ref.metadata,
            )
            self.assertEqual(services.prepared_scene_runtime.cache_size, 1)

    def test_cache_hit_leases_same_handle_once_per_requesting_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")
            runtime = services.prepared_scene_runtime

            first_a = runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                owner_scope="run:scene_a",
            )
            repeated_a = runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                owner_scope="run:scene_a",
            )
            first_b = runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                owner_scope="run:scene_b",
            )
            cached_ref = next(iter(runtime._cache.values()))  # noqa: SLF001

            self.assertEqual(
                {first_a.handle_id, repeated_a.handle_id, first_b.handle_id},
                {cached_ref.handle_id},
            )
            self.assertEqual(first_a.owner_scope, "run:scene_a")
            self.assertEqual(first_b.owner_scope, "run:scene_b")
            for owner_scope in (
                cached_ref.owner_scope,
                "run:scene_a",
                "run:scene_b",
            ):
                self.assertEqual(
                    services.handle_registry.lease_count(
                        cached_ref,
                        owner_scope=owner_scope,
                    ),
                    1,
                )

            services.cleanup_run("scene_a")
            self.assertEqual(
                services.handle_registry.lease_count(
                    cached_ref,
                    owner_scope="run:scene_a",
                ),
                0,
            )
            self.assertIsInstance(
                services.resolve_handle(
                    cached_ref,
                    expected_kind=COREX_SCENE_HANDLE_KIND,
                ),
                PreparedScene,
            )
            self.assertIsInstance(
                services.resolve_handle(
                    first_b,
                    expected_kind=COREX_SCENE_HANDLE_KIND,
                ),
                PreparedScene,
            )

    def test_concurrent_same_signature_uses_one_cached_handle_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")
            runtime = services.prepared_scene_runtime
            start = threading.Barrier(3)
            refs: list[object] = []
            errors: list[BaseException] = []

            def prepare() -> None:
                try:
                    start.wait(timeout=5.0)
                    refs.append(
                        runtime.prepare_fe_scene(
                            source_path,
                            length_unit="mm",
                        )
                    )
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = tuple(
                threading.Thread(target=prepare, daemon=True)
                for _index in range(2)
            )
            for thread in threads:
                thread.start()
            start.wait(timeout=5.0)
            for thread in threads:
                thread.join(timeout=10.0)

            self.assertFalse(errors)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(refs), 2)
            self.assertEqual({ref.handle_id for ref in refs}, {refs[0].handle_id})
            self.assertEqual(runtime.cache_size, 1)
            self.assertEqual(services.handle_registry.active_handle_count, 1)
            cached_ref = next(iter(runtime._cache.values()))  # noqa: SLF001
            self.assertEqual(
                services.handle_registry.lease_count(
                    cached_ref,
                    owner_scope=cached_ref.owner_scope,
                ),
                1,
            )

    def test_reset_waits_for_inflight_prepare_and_leaves_no_late_handle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")
            runtime = services.prepared_scene_runtime
            prepare_entered = threading.Event()
            allow_prepare = threading.Event()
            reset_attempted = threading.Event()
            prepared_refs: list[object] = []
            released_counts: list[int] = []
            errors: list[BaseException] = []
            previous_generation = services.worker_generation
            original_read = runtime._read_display_dataset  # noqa: SLF001

            def blocked_read(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
                prepare_entered.set()
                if not allow_prepare.wait(timeout=10.0):
                    raise TimeoutError("prepare release was not signaled")
                return original_read(*args, **kwargs)

            def prepare() -> None:
                try:
                    prepared_refs.append(
                        runtime.prepare_fe_scene(
                            source_path,
                            length_unit="mm",
                        )
                    )
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            def reset() -> None:
                reset_attempted.set()
                try:
                    released_counts.append(services.reset())
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            with mock.patch.object(
                runtime,
                "_read_display_dataset",
                side_effect=blocked_read,
            ):
                prepare_thread = threading.Thread(target=prepare, daemon=True)
                prepare_thread.start()
                self.assertTrue(prepare_entered.wait(timeout=5.0))
                reset_thread = threading.Thread(target=reset, daemon=True)
                reset_thread.start()
                self.assertTrue(reset_attempted.wait(timeout=5.0))
                allow_prepare.set()
                prepare_thread.join(timeout=15.0)
                reset_thread.join(timeout=15.0)

            self.assertFalse(errors)
            self.assertFalse(prepare_thread.is_alive())
            self.assertFalse(reset_thread.is_alive())
            self.assertEqual(released_counts, [1])
            self.assertEqual(runtime.cache_size, 0)
            self.assertEqual(services.handle_registry.active_handle_count, 0)
            self.assertEqual(services.worker_generation, previous_generation + 1)
            self.assertEqual(len(prepared_refs), 1)
            self.assertEqual(
                prepared_refs[0].worker_generation,
                previous_generation,
            )
            with self.assertRaisesRegex(
                StaleHandleError,
                "worker_generation is stale",
            ):
                services.resolve_handle(prepared_refs[0])

    def test_descriptor_replacement_releases_only_old_cache_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")
            runtime = services.prepared_scene_runtime

            old_run_ref = runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                owner_scope="run:scene_old",
            )
            old_cache_ref = next(iter(runtime._cache.values()))  # noqa: SLF001
            prepared = services.resolve_handle(
                old_run_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            manifest_path = Path(prepared.descriptor.cache_manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["scene"]["scene_id"] = "replacement-scene"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            replacement_ref = runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                owner_scope="run:scene_new",
            )
            replacement_cache_ref = next(  # noqa: SLF001
                iter(runtime._cache.values())
            )

            self.assertNotEqual(old_run_ref.handle_id, replacement_ref.handle_id)
            self.assertEqual(
                services.handle_registry.lease_count(
                    old_run_ref,
                    owner_scope=old_cache_ref.owner_scope,
                ),
                0,
            )
            self.assertEqual(
                services.handle_registry.lease_count(
                    old_run_ref,
                    owner_scope="run:scene_old",
                ),
                1,
            )
            self.assertIsInstance(
                services.resolve_handle(
                    old_run_ref,
                    expected_kind=COREX_SCENE_HANDLE_KIND,
                ),
                PreparedScene,
            )
            self.assertEqual(
                services.handle_registry.lease_count(
                    replacement_ref,
                    owner_scope=replacement_cache_ref.owner_scope,
                ),
                1,
            )

    def test_reset_releases_cache_leases_and_continues_after_warning(self) -> None:
        services = _services(Path(tempfile.gettempdir()) / "corex_scene_lease_test")
        runtime = services.prepared_scene_runtime
        disposed: list[str] = []
        warnings: list[str] = []

        def fail_disposal() -> None:
            disposed.append("failed")
            raise RuntimeError("private cleanup detail")

        for signature, dispose in (
            ("failure", fail_disposal),
            ("success", lambda: disposed.append("success")),
        ):
            runtime._cache[signature] = services.register_handle(  # noqa: SLF001
                object(),
                data_type_id=COREX_SCENE_DATA_TYPE,
                kind=COREX_SCENE_HANDLE_KIND,
                owner_scope=f"cache:prepared_scene:{signature}",
                dispose=dispose,
            )

        runtime.reset(warn=warnings.append)

        self.assertEqual(runtime.cache_size, 0)
        self.assertCountEqual(disposed, ["failed", "success"])
        self.assertEqual(
            warnings,
            ["Runtime handle automatic disposal failed."],
        )

    def test_scene_contract_rejects_malformed_or_live_payloads(self) -> None:
        valid = _valid_scene_bundle()
        self.assertEqual(validate_scene_bundle(valid)["length_unit"], "mm")
        self.assertNotIn("storage", SceneDescriptor.from_payload(valid).to_payload())
        self.assertEqual(
            SceneDescriptor.from_payload(valid).to_payload()["scene_id"],
            valid["scene_id"],
        )
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_scene_bundle({**valid, "schema": "other"})
        with self.assertRaisesRegex(ValueError, "bounds"):
            validate_scene_bundle({**valid, "bounds": [0, 1]})
        with self.assertRaisesRegex(ValueError, "hierarchy"):
            validate_scene_bundle({**valid, "hierarchy": []})
        malformed_asset = dict(valid["geometry_assets"][0])
        malformed_asset["content"] = "feature_edges"
        with self.assertRaisesRegex(ValueError, "content"):
            validate_scene_bundle(
                {
                    **valid,
                    "geometry_assets": [malformed_asset, *valid["geometry_assets"][1:]],
                }
            )
        malformed_colors = dict(valid["geometry_assets"][0])
        malformed_colors["attribute_colors"] = {
            **malformed_colors["attribute_colors"],
            "available": True,
            "array_name": "RGB",
            "association": "point",
            "component_count": 2,
            "encoding": "uint8",
            "source": "vtk_array",
            "unsupported_reason": "",
        }
        with self.assertRaisesRegex(ValueError, "component_count"):
            validate_scene_bundle(
                {
                    **valid,
                    "geometry_assets": [
                        malformed_colors,
                        *valid["geometry_assets"][1:],
                    ],
                }
            )
        malformed_entity_arrays = dict(valid["geometry_assets"][0])
        malformed_entity_arrays["content"] = "surface"
        malformed_entity_arrays["entity_arrays"] = {
            "part_index": "part_id",
            "face_index": "face_id",
        }
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_scene_bundle(
                {
                    **valid,
                    "geometry_assets": [
                        malformed_entity_arrays,
                        *valid["geometry_assets"][1:],
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "selection_identity"):
            validate_scene_bundle(
                {
                    **valid,
                    "geometry_assets": [
                        asset
                        for asset in valid["geometry_assets"]
                        if asset["role"] != "selection_identity"
                    ],
                }
            )
        with self.assertRaisesRegex(ValueError, "importer_version"):
            validate_scene_bundle({**valid, "importer_version": 3})
        with self.assertRaisesRegex(TypeError, "JSON-safe"):
            validate_scene_bundle({**valid, "live_object": object()})

    def test_selection_contract_rejects_wrong_schema_and_fingerprint_mismatch(
        self,
    ) -> None:
        fingerprint = "a" * 64
        valid = {
            "schema": ENGINEERING_SELECTION_SCHEMA,
            "scene_fingerprint": fingerprint,
            "published_name": "faces",
            "selections": [
                {
                    "name": "faces",
                    "entities": [
                        {
                            "layer_id": "primary",
                            "source_fingerprint": "b" * 64,
                            "entity_kind": "cad_face",
                            "entity_id": "part:1/face:2",
                        },
                        {
                            "layer_id": "primary",
                            "source_fingerprint": "b" * 64,
                            "entity_kind": "cad_face",
                            "entity_id": "part:1/face:1",
                        },
                    ],
                }
            ],
        }
        normalized = normalize_engineering_selection_set(valid)

        self.assertEqual(normalized["published_name"], "faces")
        self.assertEqual(
            [item["entity_id"] for item in normalized["selections"][0]["entities"]],
            ["part:1/face:1", "part:1/face:2"],
        )
        self.assertEqual(
            set(normalized["selections"][0]),
            {"name", "entities", "scene_fingerprint"},
        )
        with self.assertRaisesRegex(ValueError, "schema"):
            normalize_engineering_selection_set({**valid, "schema": "other"})
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_engineering_selection_set(
                {
                    **valid,
                    "selections": [
                        {
                            **valid["selections"][0],
                            "scene_fingerprint": "b" * 64,
                        }
                    ],
                }
            )
        missing_source_fingerprint = copy.deepcopy(valid)
        missing_source_fingerprint["selections"][0]["entities"][0][
            "source_fingerprint"
        ] = ""
        with self.assertRaisesRegex(ValueError, "source_fingerprint"):
            normalize_engineering_selection_set(missing_source_fingerprint)
        legacy = copy.deepcopy(valid)
        legacy["selections"][0] = {
            "name": "faces",
            "entity_kind": "cad_face",
            "entity_ids": ["part:1/face:1"],
        }
        with self.assertRaisesRegex(ValueError, "structured entities"):
            normalize_engineering_selection_set(legacy)
        invalid_id = copy.deepcopy(valid)
        invalid_id["selections"][0]["entities"][0]["entity_id"] = "face:2"
        with self.assertRaisesRegex(ValueError, "incomplete or unsupported"):
            normalize_engineering_selection_set(invalid_id)

    def test_selection_topology_requires_semantic_evidence(self) -> None:
        capabilities = {
            "cad_vertex_selection": {
                "available": False,
                "unsupported_reason": "FE sources do not define CAD vertices.",
            },
            "cad_edge_selection": {
                "available": False,
                "unsupported_reason": "FE sources do not define CAD edges.",
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
            "fe_element_face_selection": {"available": True, "unsupported_reason": ""},
            "fe_element_selection": {"available": True, "unsupported_reason": ""},
            "tangent_edge_propagation": {
                "available": False,
                "unsupported_reason": "CAD topology is required.",
            },
            "tangent_face_propagation": {
                "available": False,
                "unsupported_reason": "CAD topology is required.",
            },
        }
        payload = {
            "schema": "corex.selection_topology.v1",
            "parts": [],
            "blocks": [
                {
                    "block_index": 0,
                    "block_id": "block:0.1",
                    "point_id_array": "GlobalNodeId",
                    "cell_id_array": "GlobalElementId",
                    "point_count": 8,
                    "cell_count": 1,
                    "exterior_element_face_count": 6,
                    "element_face_id_array": "",
                    "element_face_id_unsupported_reason": "No authored face numbers.",
                }
            ],
            "edge_continuity": [],
            "face_continuity": [],
            "capabilities": capabilities,
        }

        normalized = validate_engineering_selection_topology(payload)
        self.assertEqual(normalized["blocks"][0]["block_index"], 0)
        missing_evidence = copy.deepcopy(payload)
        missing_evidence["capabilities"]["cad_vertex_selection"] = {
            "available": True,
            "unsupported_reason": "",
        }
        with self.assertRaisesRegex(
            ValueError, "does not match exact topology evidence"
        ):
            validate_engineering_selection_topology(missing_evidence)
        string_boolean = copy.deepcopy(payload)
        string_boolean["capabilities"]["fe_node_selection"]["available"] = "yes"
        with self.assertRaisesRegex(ValueError, "availability must be boolean"):
            validate_engineering_selection_topology(string_boolean)

    def test_selection_topology_rejects_invalid_cad_relationships(self) -> None:
        payload = {
            "schema": "corex.selection_topology.v1",
            "parts": [
                {
                    "part_index": 1,
                    "hierarchy_id": "cad:part:1",
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
                            "edge_ids": ["part:1/edge:1"],
                            "body_ids": ["part:1/body:1"],
                        }
                    ],
                    "bodies": [
                        {
                            "id": "part:1/body:1",
                            "part_index": 1,
                            "body_index": 1,
                            "body_kind": "surface",
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
                    "unsupported_reason": "CAD sources do not define FE faces.",
                },
                "fe_element_selection": {
                    "available": False,
                    "unsupported_reason": "CAD sources do not define FE elements.",
                },
                "tangent_edge_propagation": {
                    "available": False,
                    "unsupported_reason": "No adjacent edges.",
                },
                "tangent_face_propagation": {
                    "available": False,
                    "unsupported_reason": "No adjacent faces.",
                },
            },
        }
        validate_engineering_selection_topology(payload)

        unknown_reference = copy.deepcopy(payload)
        unknown_reference["parts"][0]["faces"][0]["edge_ids"] = ["part:1/edge:2"]
        with self.assertRaisesRegex(ValueError, "unknown reference"):
            validate_engineering_selection_topology(unknown_reference)

        nonreciprocal = copy.deepcopy(payload)
        nonreciprocal["parts"][0]["edges"][0]["face_ids"] = []
        with self.assertRaisesRegex(ValueError, "not reciprocal"):
            validate_engineering_selection_topology(nonreciprocal)

    def test_fe_cache_key_changes_when_source_metadata_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")

            first_ref = services.prepared_scene_runtime.prepare_fe_scene(
                source_path, length_unit="mm"
            )
            replacement = pyvista.ImageData(
                dimensions=(3, 2, 2)
            ).cast_to_unstructured_grid()
            replacement.save(source_path)
            second_ref = services.prepared_scene_runtime.prepare_fe_scene(
                source_path, length_unit="mm"
            )

            self.assertNotEqual(first_ref.handle_id, second_ref.handle_id)
            self.assertEqual(services.prepared_scene_runtime.cache_size, 2)

    def test_cad_stl_uses_source_as_display_artifact_without_ocp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "part.stl"
            pyvista.Cube().triangulate().save(source_path)
            services = _services(Path(temp_dir) / "cache")

            scene_ref = services.prepared_scene_runtime.prepare_cad_scene(
                source_path, length_unit="mm"
            )
            prepared = services.resolve_handle(
                scene_ref, expected_kind=COREX_SCENE_HANDLE_KIND
            )

            self.assertEqual(prepared.descriptor.source_kind, "cad")
            self.assertEqual(prepared.descriptor.source.source_format, ".stl")
            self.assertEqual(
                prepared.descriptor.display_artifact_path, str(source_path.resolve())
            )
            self.assertGreater(prepared.descriptor.cell_count, 0)
            self.assertEqual(
                {asset["role"] for asset in prepared.descriptor.geometry_assets},
                {"coarse", "full"},
            )
            assets = {
                asset["role"]: asset for asset in prepared.descriptor.geometry_assets
            }
            self.assertEqual(assets["coarse"]["format"], ".vtp")
            self.assertEqual(assets["full"]["format"], ".stl")
            self.assertEqual({asset["content"] for asset in assets.values()}, {"mesh"})
            self.assertNotIn("topological_edges", prepared.descriptor.capabilities)

    def test_step_reports_clear_missing_ocp_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "part.step"
            source_path.write_text("ISO-10303-21;", encoding="utf-8")
            services = _services(Path(temp_dir) / "cache")

            with mock.patch.dict(sys.modules, {"OCP": None}):
                with self.assertRaisesRegex(RuntimeError, "cadquery-ocp"):
                    services.prepared_scene_runtime.prepare_cad_scene(
                        source_path, length_unit="mm"
                    )

    def test_step_xcaf_preserves_metadata_topology_units_and_two_lods(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "part.step"
            try:
                _write_xcaf_step(source_path)
            except ModuleNotFoundError:
                self.skipTest("cadquery-ocp-novtk is not installed")
            services = _services(temp_path / "cache")
            runtime = services.prepared_scene_runtime
            scene_ref = runtime.prepare_cad_scene(
                source_path,
                workspace_id="workspace_engineering_import",
            )
            prepared = services.resolve_handle(
                scene_ref, expected_kind=COREX_SCENE_HANDLE_KIND
            )
            display_path = Path(prepared.descriptor.display_artifact_path)

            self.assertEqual(prepared.descriptor.source.source_path, str(source_path))
            self.assertEqual(prepared.descriptor.source.source_format, ".step")
            self.assertEqual(
                prepared.descriptor.importer_version, SCENE_IMPORTER_VERSION
            )
            self.assertEqual(prepared.descriptor.display_format, ".vtp")
            self.assertEqual(prepared.descriptor.length_unit, "mm")
            self.assertNotEqual(display_path, source_path)
            self.assertTrue(display_path.is_file())
            assets = {
                asset["role"]: asset for asset in prepared.descriptor.geometry_assets
            }
            self.assertEqual(
                set(assets),
                {
                    "coarse",
                    "full",
                    "topology_edges",
                    "topology_vertices",
                    "selection_topology",
                },
            )
            self.assertTrue(Path(assets["coarse"]["path"]).is_file())
            self.assertTrue(Path(assets["full"]["path"]).is_file())
            self.assertTrue(Path(assets["topology_edges"]["path"]).is_file())
            self.assertTrue(Path(assets["topology_vertices"]["path"]).is_file())
            self.assertTrue(Path(assets["selection_topology"]["path"]).is_file())
            self.assertEqual(assets["full"]["content"], "surface")
            self.assertEqual(assets["topology_edges"]["content"], "topological_edges")
            self.assertTrue(assets["full"]["attribute_colors"]["available"])
            surface = pyvista.read(assets["full"]["path"])
            topology_edges = pyvista.read(assets["topology_edges"]["path"])
            topology_vertices = pyvista.read(assets["topology_vertices"]["path"])
            self.assertEqual(surface.bounds.x_min, 10.0)
            self.assertEqual(surface.bounds.x_max, 12.0)
            self.assertEqual(topology_edges.n_cells, 12)
            self.assertEqual(
                set(surface.cell_data),
                {
                    "corex_part_index",
                    "corex_body_index",
                    "corex_face_index",
                    "corex_source_rgba",
                    "corex_source_color_valid",
                },
            )
            self.assertEqual(
                set(topology_edges.cell_data),
                {
                    "corex_part_index",
                    "corex_edge_index",
                    "corex_source_rgba",
                    "corex_source_color_valid",
                },
            )
            self.assertEqual(
                len(np.unique(topology_edges.cell_data["corex_edge_index"])),
                12,
            )
            self.assertEqual(topology_vertices.n_cells, 8)
            self.assertEqual(
                set(topology_vertices.cell_data),
                {"corex_part_index", "corex_vertex_index"},
            )
            topology_payload = json.loads(
                Path(assets["selection_topology"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(topology_payload["schema"], "corex.selection_topology.v1")
            self.assertEqual(len(topology_payload["parts"][0]["vertices"]), 8)
            self.assertEqual(len(topology_payload["parts"][0]["edges"]), 12)
            self.assertEqual(len(topology_payload["parts"][0]["faces"]), 6)
            self.assertEqual(len(topology_payload["parts"][0]["bodies"]), 1)
            self.assertEqual(
                topology_payload["parts"][0]["bodies"][0]["body_kind"],
                "solid",
            )
            self.assertTrue(topology_payload["edge_continuity"])
            self.assertTrue(topology_payload["face_continuity"])
            self.assertTrue(
                all(
                    0.0 <= record["angular_deviation_degrees"] <= 90.0
                    for record in topology_payload["face_continuity"]
                )
            )
            self.assertEqual(
                hashlib.sha256(
                    Path(assets["selection_topology"]["path"]).read_bytes()
                ).hexdigest(),
                assets["selection_topology"]["sha256"],
            )
            valid_colors = surface.cell_data["corex_source_rgba"][
                surface.cell_data["corex_source_color_valid"].astype(bool)
            ]
            self.assertIn((51, 102, 153, 255), {tuple(value) for value in valid_colors})
            self.assertTrue(
                any(
                    np.allclose(value, np.asarray([230, 26, 51, 255]), atol=1)
                    for value in valid_colors
                )
            )
            assembly = next(
                item
                for item in prepared.descriptor.hierarchy
                if item["name"] == "Named Assembly"
            )
            instance = next(
                item
                for item in prepared.descriptor.hierarchy
                if item["name"] == "Named Box Instance"
            )
            self.assertEqual(assembly["kind"], "assembly")
            self.assertEqual(instance["kind"], "instance")
            self.assertEqual(instance["parent_id"], assembly["id"])
            self.assertEqual(instance["layers"], ["Primary Layer"])
            self.assertAlmostEqual(instance["color"]["rgba"][0], 0.2, places=5)
            self.assertEqual(
                len(prepared.descriptor.topology_mappings["faces"]["entities"]),
                6,
            )
            self.assertEqual(
                len(prepared.descriptor.topology_mappings["edges"]["entities"]),
                12,
            )
            self.assertEqual(
                len(prepared.descriptor.topology_mappings["vertices"]["entities"]),
                8,
            )
            self.assertEqual(
                len(prepared.descriptor.topology_mappings["bodies"]["entities"]),
                1,
            )
            self.assertEqual(list((temp_path / "cache").rglob("*.stl")), [])
            services.reset()
            self.assertTrue(display_path.exists())

    def test_cad_body_identity_includes_shells_and_surfaces_without_double_counting(
        self,
    ) -> None:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.TopAbs import TopAbs_SHELL
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        solid = BRepPrimAPI_MakeBox(2.0, 3.0, 4.0).Shape()
        shell_explorer = TopExp_Explorer(solid, TopAbs_SHELL)
        self.assertTrue(shell_explorer.More())
        shell = TopoDS.Shell_s(shell_explorer.Current())
        surface = BRepBuilderAPI_MakeFace(
            gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            0.0,
            2.0,
            0.0,
            3.0,
        ).Face()

        solid_bodies = PreparedSceneRuntime._cad_body_shapes(solid)  # noqa: SLF001
        shell_bodies = PreparedSceneRuntime._cad_body_shapes(shell)  # noqa: SLF001
        surface_bodies = PreparedSceneRuntime._cad_body_shapes(surface)  # noqa: SLF001
        self.assertEqual([record[0] for record in solid_bodies], ["solid"])
        self.assertEqual([record[0] for record in shell_bodies], ["shell"])
        self.assertEqual([record[0] for record in surface_bodies], ["surface"])
        sheet_dataset, _has_colors = PreparedSceneRuntime._cad_surface_dataset(  # noqa: SLF001
            surface,
            Path("sheet.brep"),
            linear_deflection=0.01,
            cad_metadata=_CadMetadata(),
        )
        self.assertEqual(set(sheet_dataset.cell_data["corex_body_index"]), {1})
        sheet_topology = PreparedSceneRuntime._cad_selection_topology(  # noqa: SLF001
            surface,
            Path("sheet.brep"),
            cad_metadata=_CadMetadata(),
        )
        self.assertEqual(
            sheet_topology["parts"][0]["bodies"][0]["body_kind"], "surface"
        )
        self.assertTrue(
            sheet_topology["capabilities"]["cad_body_selection"]["available"]
        )
        self.assertFalse(
            sheet_topology["capabilities"]["tangent_face_propagation"]["available"]
        )

    def test_durable_manifest_reuses_lods_and_regenerates_a_missing_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "cached.step"
            try:
                _write_xcaf_step(source_path)
            except ModuleNotFoundError:
                self.skipTest("cadquery-ocp-novtk is not installed")
            cache_root = root / "cache"
            first_services = _services(cache_root)
            first_ref = first_services.prepared_scene_runtime.prepare_cad_scene(
                source_path,
                workspace_id="workspace-cache",
            )
            first = first_services.resolve_handle(
                first_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            topology_edge_path = Path(
                next(
                    asset["path"]
                    for asset in first.descriptor.geometry_assets
                    if asset["role"] == "topology_edges"
                )
            )
            selection_topology_path = Path(
                next(
                    asset["path"]
                    for asset in first.descriptor.geometry_assets
                    if asset["role"] == "selection_topology"
                )
            )
            manifest_path = Path(first.descriptor.cache_manifest_path)

            second_services = _services(cache_root)
            second_runtime = second_services.prepared_scene_runtime
            with mock.patch.object(
                second_runtime,
                "_write_cad_lods",
                wraps=second_runtime._write_cad_lods,  # noqa: SLF001
            ) as write_lods:
                second_runtime.prepare_cad_scene(
                    source_path,
                    workspace_id="workspace-cache",
                )
            write_lods.assert_not_called()

            topology_edge_path.unlink()
            third_services = _services(cache_root)
            third_runtime = third_services.prepared_scene_runtime
            with mock.patch.object(
                third_runtime,
                "_write_cad_lods",
                wraps=third_runtime._write_cad_lods,  # noqa: SLF001
            ) as write_lods:
                third_runtime.prepare_cad_scene(
                    source_path,
                    workspace_id="workspace-cache",
                )
            write_lods.assert_called_once()
            self.assertTrue(topology_edge_path.is_file())

            selection_topology_path.write_text("{}", encoding="utf-8")
            fourth_services = _services(cache_root)
            fourth_runtime = fourth_services.prepared_scene_runtime
            with mock.patch.object(
                fourth_runtime,
                "_write_cad_lods",
                wraps=fourth_runtime._write_cad_lods,  # noqa: SLF001
            ) as write_lods:
                fourth_runtime.prepare_cad_scene(
                    source_path,
                    workspace_id="workspace-cache",
                )
            write_lods.assert_called_once()
            self.assertNotEqual(
                selection_topology_path.read_text(encoding="utf-8"), "{}"
            )

            invalid_topology = json.loads(
                selection_topology_path.read_text(encoding="utf-8")
            )
            invalid_topology["parts"][0]["vertices"][0]["edge_ids"] = []
            selection_topology_path.write_text(
                json.dumps(invalid_topology, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            invalid_checksum = hashlib.sha256(
                selection_topology_path.read_bytes()
            ).hexdigest()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            topology_asset = next(
                asset
                for asset in manifest["scene"]["geometry_assets"]
                if asset["role"] == "selection_topology"
            )
            topology_asset["sha256"] = invalid_checksum
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            fifth_services = _services(cache_root)
            fifth_runtime = fifth_services.prepared_scene_runtime
            with mock.patch.object(
                fifth_runtime,
                "_write_cad_lods",
                wraps=fifth_runtime._write_cad_lods,  # noqa: SLF001
            ) as write_lods:
                fifth_runtime.prepare_cad_scene(
                    source_path,
                    workspace_id="workspace-cache",
                )
            write_lods.assert_called_once()
            validate_engineering_selection_topology(
                json.loads(selection_topology_path.read_text(encoding="utf-8"))
            )

    def test_import_rechecks_source_before_manifest_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "changing.vtu"
            _write_vtu(source_path)
            services = _services(root / "cache")
            runtime = services.prepared_scene_runtime
            original_read = runtime._read_display_dataset  # noqa: SLF001

            def read_then_change(path: Path, *, source_kind: str):  # noqa: ANN202
                result = original_read(path, source_kind=source_kind)
                source_path.write_bytes(source_path.read_bytes() + b"\n")
                return result

            with mock.patch.object(
                runtime,
                "_read_display_dataset",
                side_effect=read_then_change,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "Source changed during FE import"
                ):
                    runtime.prepare_fe_scene(
                        source_path,
                        length_unit="mm",
                        workspace_id="workspace-changing",
                    )
            self.assertEqual(list((root / "cache").rglob("*.scene.json")), [])

    def test_interrupted_cad_lod_write_removes_transaction_temps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            services = _services(root / "cache")
            runtime = services.prepared_scene_runtime
            display_paths = runtime._display_artifact_paths(  # noqa: SLF001
                "d" * 64,
                workspace_id="workspace-interrupted",
            )
            calls = 0

            def build_then_fail(*_args: object, **kwargs: object):  # noqa: ANN202
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("interrupted")
                self.assertGreater(float(kwargs["linear_deflection"]), 0.0)
                return pyvista.Cube().triangulate(), False

            with mock.patch.object(
                runtime,
                "_cad_surface_dataset",
                side_effect=build_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    runtime._write_cad_lods(  # noqa: SLF001
                        object(),
                        root / "part.step",
                        display_paths,
                        cad_metadata=mock.Mock(),
                    )
            self.assertEqual(list((root / "cache").rglob("*.vtp")), [])
            self.assertEqual(list((root / "cache").rglob("*.tmp*")), [])

    def test_interrupted_fe_selection_write_removes_all_committed_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_paths = {
                "identity": root / "selection_mesh.vtu",
                "element_faces": root / "element_faces.vtp",
                "selection_topology": root / "selection_topology.json",
            }
            dataset = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            original_write = PreparedSceneRuntime._write_dataset_atomic  # noqa: SLF001
            calls = 0

            def write_then_fail(value: object, output_path: Path) -> None:
                nonlocal calls
                calls += 1
                original_write(value, output_path)
                if calls == 2:
                    raise RuntimeError("interrupted FE selection write")

            with mock.patch.object(
                PreparedSceneRuntime,
                "_write_dataset_atomic",
                side_effect=write_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted FE"):
                    PreparedSceneRuntime._write_fe_selection_assets(  # noqa: SLF001
                        dataset,
                        output_paths,
                    )
            self.assertTrue(all(not path.exists() for path in output_paths.values()))

    def test_fe_nested_hierarchy_source_ids_components_and_deformation_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "nested.vtm"
            leaf = pyvista.ImageData(dimensions=(2, 2, 2)).cast_to_unstructured_grid()
            leaf.point_data["GlobalNodeId"] = np.arange(1, leaf.n_points + 1)
            leaf.cell_data["GlobalElementId"] = np.arange(1, leaf.n_cells + 1)
            leaf.cell_data["SolverFaceIds"] = np.asarray(
                [[101, 102, 103, 104, 105, 106]],
                dtype=np.int32,
            )
            leaf.point_data["Displacement"] = np.zeros((leaf.n_points, 3))
            leaf.point_data["StressTensor"] = np.zeros((leaf.n_points, 6))
            pyvista.MultiBlock({"Assembly": pyvista.MultiBlock({"Body": leaf})}).save(
                source_path
            )
            services = _services(root / "cache")

            scene_ref = services.prepared_scene_runtime.prepare_fe_scene(
                source_path,
                length_unit="mm",
                workspace_id="workspace-nested",
            )
            prepared = services.resolve_handle(
                scene_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )

            hierarchy = {item["id"]: item for item in prepared.descriptor.hierarchy}
            self.assertEqual(hierarchy["block:0"]["name"], "Assembly")
            self.assertEqual(hierarchy["block:0.0"]["parent_id"], "block:0")
            source_map = prepared.descriptor.topology_mappings["blocks"][0]
            self.assertEqual(source_map["block_index"], 0)
            self.assertEqual(source_map["block_id"], "block:0.0")
            self.assertEqual(source_map["point_id_array"], "GlobalNodeId")
            self.assertEqual(source_map["cell_id_array"], "GlobalElementId")
            assets = {
                asset["role"]: asset for asset in prepared.descriptor.geometry_assets
            }
            identity = pyvista.read(assets["selection_identity"]["path"])
            element_faces = pyvista.read(assets["element_faces"]["path"])
            self.assertEqual(
                set(assets["selection_identity"]["entity_arrays"]),
                {"block_index", "node_index", "element_index"},
            )
            self.assertIn("corex_block_index", identity.point_data)
            self.assertIn("corex_node_index", identity.point_data)
            self.assertIn("corex_element_index", identity.cell_data)
            self.assertEqual(element_faces.n_cells, 6)
            self.assertEqual(
                set(element_faces.cell_data),
                {
                    "corex_block_index",
                    "corex_element_index",
                    "corex_element_face_index",
                    "SolverFaceIds",
                },
            )
            self.assertEqual(
                set(element_faces.cell_data["SolverFaceIds"]),
                {101, 102, 103, 104, 105, 106},
            )
            topology_asset = assets["selection_topology"]
            topology_payload = json.loads(
                Path(topology_asset["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                topology_payload["blocks"],
                [
                    {
                        "block_index": 0,
                        "block_id": "block:0.0",
                        "point_id_array": "GlobalNodeId",
                        "cell_id_array": "GlobalElementId",
                        "point_count": leaf.n_points,
                        "cell_count": leaf.n_cells,
                        "exterior_element_face_count": 6,
                        "element_face_id_array": "SolverFaceIds",
                        "element_face_id_unsupported_reason": "",
                    }
                ],
            )
            self.assertTrue(
                topology_payload["capabilities"]["fe_node_selection"]["available"]
            )
            self.assertTrue(
                topology_payload["capabilities"]["fe_element_selection"]["available"]
            )
            self.assertTrue(
                topology_payload["capabilities"]["fe_element_face_selection"][
                    "available"
                ]
            )
            fields = {
                field["name"]: field for field in prepared.descriptor.result_fields
            }
            self.assertEqual(
                fields["StressTensor"]["components"],
                ["xx", "yy", "zz", "xy", "yz", "xz"],
            )
            self.assertTrue(prepared.descriptor.deformation["available"])
            self.assertFalse(prepared.descriptor.deformation["enabled"])
            self.assertEqual(prepared.descriptor.deformation["scale_factor"], 1.0)

    def test_fe_direct_color_metadata_accepts_rgba_and_rejects_vector_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            colored_path = root / "colored.vtu"
            colored = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            colored.point_data["RGBA"] = np.tile(
                np.asarray([[10, 20, 30, 255]], dtype=np.uint8),
                (colored.n_points, 1),
            )
            colored.point_data["Displacement"] = np.zeros((colored.n_points, 3))
            colored.cell_data["MaterialId"] = np.ones(colored.n_cells, dtype=np.int32)
            colored.save(colored_path)
            services = _services(root / "cache")

            colored_ref = services.prepared_scene_runtime.prepare_fe_scene(
                colored_path,
                length_unit="mm",
                workspace_id="workspace-colors",
            )
            colored_scene = services.resolve_handle(
                colored_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            color_metadata = colored_scene.descriptor.geometry_assets[0][
                "attribute_colors"
            ]
            self.assertTrue(color_metadata["available"])
            self.assertEqual(color_metadata["array_name"], "RGBA")
            self.assertEqual(color_metadata["association"], "point")
            self.assertEqual(color_metadata["component_count"], 4)
            self.assertEqual(color_metadata["encoding"], "uint8")

            vector_only_path = root / "vector-only.vtu"
            vector_only = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            vector_only.point_data["Displacement"] = np.zeros((vector_only.n_points, 3))
            vector_only.cell_data["MaterialId"] = np.ones(
                vector_only.n_cells,
                dtype=np.int32,
            )
            vector_only.save(vector_only_path)
            vector_ref = services.prepared_scene_runtime.prepare_fe_scene(
                vector_only_path,
                length_unit="mm",
                workspace_id="workspace-colors",
            )
            vector_scene = services.resolve_handle(
                vector_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            unsupported = vector_scene.descriptor.geometry_assets[0]["attribute_colors"]
            self.assertFalse(unsupported["available"])
            self.assertIn("RGB", unsupported["unsupported_reason"])

    def test_fe_reader_retains_lazy_time_and_array_selection_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "series.xdmf"
            source_path.write_text("<Xdmf/>", encoding="utf-8")
            dataset = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            dataset.point_data["Displacement"] = np.zeros((dataset.n_points, 3))
            dataset.point_data["Temperature"] = np.arange(dataset.n_points)

            class StatefulReader:
                time_values = (0.0, 1.0)
                point_array_names = ("Displacement", "Temperature")
                cell_array_names: tuple[str, ...] = ()

                def __init__(self) -> None:
                    self.active_time = 0.0
                    self.enabled_point_arrays: list[str] = []
                    self.cell_arrays_disabled = False

                def read(self):  # noqa: ANN202
                    return dataset

                def set_active_time_value(self, value: float) -> None:
                    self.active_time = value

                def disable_all_point_arrays(self) -> None:
                    self.enabled_point_arrays.clear()

                def enable_point_array(self, name: str) -> None:
                    self.enabled_point_arrays.append(name)

                def disable_all_cell_arrays(self) -> None:
                    self.cell_arrays_disabled = True

                def enable_cell_array(self, _name: str) -> None:
                    return

            reader = StatefulReader()
            services = _services(root / "cache")
            with mock.patch.object(pyvista, "get_reader", return_value=reader):
                scene_ref = services.prepared_scene_runtime.prepare_fe_scene(
                    source_path,
                    length_unit="mm",
                    workspace_id="workspace-series",
                )
            prepared = services.resolve_handle(
                scene_ref,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )

            self.assertEqual(prepared.descriptor.time_steps, (0.0, 1.0))
            self.assertTrue(prepared.descriptor.provenance["lazy_time_loading"])
            prepared.read_state(
                time_value=1.0,
                point_arrays=("Displacement",),
                cell_arrays=(),
            )
            self.assertEqual(reader.active_time, 1.0)
            self.assertEqual(reader.enabled_point_arrays, ["Displacement"])
            self.assertTrue(reader.cell_arrays_disabled)

    def test_unsupported_extension_fails_before_reader_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.unknown"
            source_path.write_text("unsupported", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsupported FE import format"):
                _services(
                    Path(temp_dir) / "cache"
                ).prepared_scene_runtime.prepare_fe_scene(
                    source_path,
                    length_unit="mm",
                )

    def test_unitless_file_requires_an_explicit_length_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "part.stl"
            pyvista.Cube().triangulate().save(source_path)

            with self.assertRaisesRegex(ValueError, "Choose Length Unit"):
                _services(
                    Path(temp_dir) / "cache"
                ).prepared_scene_runtime.prepare_cad_scene(source_path)


class EngineeringImportNodeTests(unittest.TestCase):
    def test_builtin_specs_use_neutral_scene_contract_and_path_pointer_compatibility(
        self,
    ) -> None:
        registry = build_builtin_registry()
        path_pointer = registry.get_spec("io.path_pointer")
        fe_import = registry.get_spec("engineering.fe_import")
        cad_import = registry.get_spec("engineering.cad_import")

        pointer_path = next(port for port in path_pointer.ports if port.key == "path")
        for spec in (fe_import, cad_import):
            input_path = next(port for port in spec.ports if port.key == "path")
            output_scene = next(port for port in spec.ports if port.key == "scene")
            path_property = next(prop for prop in spec.properties if prop.key == "path")
            self.assertTrue(
                ports_compatible(
                    pointer_path,
                    input_path,
                    data_types=registry.data_types,
                )
            )
            self.assertTrue(input_path.required)
            self.assertEqual(output_scene.data_type, COREX_SCENE_DATA_TYPE)
            self.assertTrue(path_property.file_filter)

    def test_fe_import_node_emits_scene_handle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "result.vtu"
            _write_vtu(source_path)
            services = _services(Path(temp_dir) / "cache")

            context = _context(path=source_path, services=services)
            result = execute_engineering_import(context, source_kind="fe")
            repeated = execute_engineering_import(context, source_kind="fe")

            self.assertNotIn("exec_out", result.outputs)
            scene_ref = result.outputs["scene"]
            cached_ref = next(  # noqa: SLF001
                iter(services.prepared_scene_runtime._cache.values())
            )
            self.assertEqual(scene_ref.kind, COREX_SCENE_HANDLE_KIND)
            self.assertEqual(scene_ref.owner_scope, "run:run_engineering_import")
            self.assertEqual(
                repeated.outputs["scene"].handle_id,
                scene_ref.handle_id,
            )
            self.assertEqual(
                services.handle_registry.lease_count(
                    cached_ref,
                    owner_scope=cached_ref.owner_scope,
                ),
                1,
            )
            self.assertEqual(
                services.handle_registry.lease_count(
                    scene_ref,
                    owner_scope=scene_ref.owner_scope,
                ),
                1,
            )
            self.assertIsInstance(
                services.resolve_handle(
                    scene_ref, expected_kind=COREX_SCENE_HANDLE_KIND
                ),
                PreparedScene,
            )

    def test_fe_import_node_prefers_connected_path_input_over_browse_property(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "connected.vtu"
            _write_vtu(source_path)
            services = _services(root / "cache")
            context = _context(path=root / "missing.vtu", services=services)
            context.inputs["path"] = str(source_path)

            result = execute_engineering_import(context, source_kind="fe")

            prepared = services.resolve_handle(
                result.outputs["scene"],
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
            self.assertEqual(
                prepared.descriptor.source.resolved_path,
                str(source_path.resolve()),
            )


if __name__ == "__main__":
    unittest.main()
