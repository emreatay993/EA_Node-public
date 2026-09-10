from __future__ import annotations

import json
import tempfile
import unittest
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from unittest import mock

import pyvista

from ea_node_editor.common.scene_protocol import (
    COREX_SCENE_DATA_TYPE,
    COREX_SCENE_HANDLE_KIND,
    ENGINEERING_SELECTION_DATA_TYPE,
    ENGINEERING_SELECTION_SCHEMA,
)
from ea_node_editor.execution.viewer_backend_engineering import ENGINEERING_VIEWER_BACKEND_ID
from ea_node_editor.execution.handle_registry import StaleHandleError
from ea_node_editor.execution.prepared_scene_runtime import PreparedSceneRuntime
from ea_node_editor.execution.viewer_messages import (
    CloseViewerSessionCommand,
)
from ea_node_editor.execution.worker_services import WorkerServices
from tests.typed_handle_support import core_worker_services
from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.engineering_viewer import (
    _composition_fingerprint,
    _require_scene,
    _selection_output_for_scene,
    execute_engineering_viewer,
)
from ea_node_editor.nodes.builtins import geometry_primitives
from ea_node_editor.nodes.builtins.geometry_primitives import (
    GEOMETRY_GROUP_DATA_TYPE_ID,
    GEOMETRY_GROUP_HANDLE_KIND,
    OCP_BODY_DATA_TYPE_ID,
    OCP_BODY_HANDLE_KIND,
    execute_construct_geometry_group,
    execute_cylinder,
)
from ea_node_editor.nodes.builtins.rich_value_nodes import PLANE_DATA_TYPE_ID
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError
from ea_node_editor.nodes.instance_resolution import resolve_instance_ports
from ea_node_editor.nodes.core_data_types import VIEWER_SESSION_DATA_TYPE_ID
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    Interval1D,
    RuntimeHandleRef,
    TypedInlineValue,
)


class EngineeringViewerNodeTests(unittest.TestCase):
    def test_dynamic_callback_fingerprints_are_trusted_and_deterministic(self) -> None:
        from ea_node_editor.nodes.builtins.engineering_viewer import resolve_scene_input_ports
        from ea_node_editor.nodes.function_plugin import _stable_fingerprint_value
        from ea_node_editor.nodes.registry import PythonFunctionEntry

        first, second = build_builtin_registry(), build_builtin_registry()
        self.assertIsInstance(first.get_entry("model.viewer"), PythonFunctionEntry)
        self.assertEqual(first.plugin_fingerprint(), second.plugin_fingerprint())
        self.assertEqual(first.contract_fingerprint(), second.contract_fingerprint())
        with self.assertRaises(TypeError):
            _stable_fingerprint_value(resolve_scene_input_ports)

    def test_empty_ports_wait_and_invalid_supplied_values_identify_the_port(self) -> None:
        context = ExecutionContext(
            run_id="run", node_id="viewer", workspace_id="ws", inputs={},
            properties={"scene_input_ids": ["scene_1", "scene_2"]},
            emit_log=lambda *_args: None,
        )
        with self.assertRaisesRegex(NodeInputNotReadyError, "at least one scene"):
            execute_engineering_viewer(context)
        context.inputs["scene_2"] = 42
        context.node_port_labels = {"scene_2": "Housing"}
        with self.assertRaisesRegex(TypeError, r"Housing \(scene_2\)"):
            execute_engineering_viewer(context)

    def test_three_scene_inputs_ignore_gaps_and_keep_duplicate_sources_distinct(self) -> None:
        references = {
            key: RuntimeHandleRef(
                data_type_id=COREX_SCENE_DATA_TYPE, schema_version=1,
                handle_id=key, kind=COREX_SCENE_HANDLE_KIND,
                owner_scope="run:test", worker_generation=1,
                metadata={"source": {"sha256": fingerprint * 64}},
            )
            for key, fingerprint in (("cad", "a"), ("fe", "b"))
        }
        context = ExecutionContext(
            run_id="run", node_id="viewer", workspace_id="ws",
            inputs={"scene_2": references["cad"], "scene_4": references["fe"], "scene_5": references["cad"]},
            properties={"scene_input_ids": [f"scene_{n}" for n in range(1, 6)]},
            emit_log=lambda *_args: None,
            node_port_labels={"scene_2": "Housing", "scene_5": "Housing"},
        )
        with mock.patch("ea_node_editor.nodes.builtins.engineering_viewer._open_engineering_viewer_session") as opened:
            execute_engineering_viewer(context)
        arguments = opened.call_args.kwargs
        self.assertEqual(list(arguments["scenes"]), ["scene_2", "scene_4", "scene_5"])
        self.assertIs(arguments["scenes"]["scene_2"], arguments["scenes"]["scene_5"])
        self.assertEqual(arguments["labels"], {"scene_2": "Housing", "scene_4": "Scene 4", "scene_5": "Housing"})

    def test_scene_guard_rejects_correct_kind_with_wrong_semantic_type(self) -> None:
        spoof = RuntimeHandleRef(
            data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
            schema_version=1,
            handle_id="spoof-scene",
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="run:spoof",
            worker_generation=1,
        )

        with self.assertRaisesRegex(TypeError, "engineering_scene"):
            _require_scene(spoof, label="scene")

    def test_spec_exposes_dynamic_scenes_session_and_saved_selection_contracts(self) -> None:
        spec = build_builtin_registry().get_spec("model.viewer")
        ports = {port.key: port for port in resolve_instance_ports(spec, {"scene_input_ids": ["scene_1", "scene_2"]})}

        self.assertEqual(spec.type_id, "model.viewer")
        self.assertEqual(spec.display_name, "Model Viewer")
        self.assertEqual(ports["scene_1"].data_type, COREX_SCENE_DATA_TYPE)
        self.assertEqual(
            ports["scene_1"].accepted_data_types,
            (OCP_BODY_DATA_TYPE_ID, GEOMETRY_GROUP_DATA_TYPE_ID),
        )
        self.assertEqual(ports["scene_2"].data_type, COREX_SCENE_DATA_TYPE)
        self.assertEqual(ports["scene_2"].accepted_data_types, ports["scene_1"].accepted_data_types)
        self.assertFalse(ports["scene_1"].required)
        self.assertFalse(ports["scene_2"].required)
        self.assertNotIn("overlay", ports)
        self.assertEqual(spec.solution_reuse_scope, "session")
        self.assertEqual(ports["session"].data_type, VIEWER_SESSION_DATA_TYPE_ID)
        self.assertEqual(ports["selections"].data_type, ENGINEERING_SELECTION_DATA_TYPE)
        self.assertEqual(spec.surface_family, "viewer")
        properties = {prop.key: prop for prop in spec.properties}
        self.assertEqual(properties["representation"].default, "surface_with_edges")
        self.assertIn("wireframe_visible_edges", properties["representation"].enum_values)
        self.assertFalse(properties["show_attribute_colors"].default)
        self.assertTrue(properties["show_orientation_triad"].default)
        self.assertTrue(properties["show_view_cube"].default)
        self.assertFalse(properties["show_world_axes"].default)

    def test_execute_materializes_primary_and_overlay_in_one_viewer_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            primary_path = root / "primary.vtu"
            overlay_path = root / "overlay.vtu"
            primary = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            primary.point_data["stress"] = list(range(primary.n_points))
            primary.save(primary_path)
            overlay = pyvista.ImageData(
                dimensions=(2, 2, 2)
            ).cast_to_unstructured_grid()
            overlay.save(overlay_path)
            services = core_worker_services()
            services._prepared_scene_runtime = PreparedSceneRuntime(  # noqa: SLF001
                services,
                cache_root=root / "cache",
            )
            primary_ref = services.prepared_scene_runtime.prepare_fe_scene(
                primary_path,
                length_unit="mm",
            )
            overlay_ref = services.prepared_scene_runtime.prepare_fe_scene(
                overlay_path,
                length_unit="m",
            )
            primary_fingerprint = primary_ref.metadata["source"]["sha256"]
            context = ExecutionContext(
                run_id="run-engineering-viewer",
                node_id="node-engineering-viewer",
                workspace_id="workspace-engineering-viewer",
                inputs={"scene_1": primary_ref, "scene_2": overlay_ref},
                properties={
                    "scene_input_ids": ["scene_1", "scene_2"],
                    "show_mesh_edges": True,
                    "representation": "surface",
                    "show_attribute_colors": True,
                    "show_orientation_triad": False,
                    "show_view_cube": False,
                    "show_world_axes": True,
                    "scene_styles": {"scene_2": {"opacity": 0.35, "color": "#ff9f43"}},
                    "viewer_background": "theme",
                    "saved_selections": {
                        "schema": ENGINEERING_SELECTION_SCHEMA,
                        "scene_fingerprint": _composition_fingerprint({"scene_1": primary_fingerprint, "scene_2": overlay_ref.metadata["source"]["sha256"]}),
                        "published_name": "bolt_faces",
                        "selections": [
                            {
                                "name": "bolt_faces",
                                "scene_fingerprint": _composition_fingerprint({"scene_1": primary_fingerprint, "scene_2": overlay_ref.metadata["source"]["sha256"]}),
                                "entities": [
                                    {
                                        "layer_id": "scene_1",
                                        "source_fingerprint": primary_fingerprint,
                                        "entity_kind": "fe_node",
                                        "entity_id": f"block:0/node:{value}",
                                    }
                                    for value in (0, 1)
                                ],
                            }
                        ],
                    },
                },
                emit_log=lambda _level, _message: None,
                worker_services=services,
            )

            result = execute_engineering_viewer(context)

        session_ref = result.outputs["session"]
        self.assertIsInstance(session_ref, RuntimeHandleRef)
        self.assertEqual(session_ref.data_type_id, VIEWER_SESSION_DATA_TYPE_ID)
        self.assertEqual(session_ref.kind, COREX_VIEWER_SESSION_HANDLE_KIND)
        self.assertEqual(
            set(session_ref.metadata),
            {"workspace_id", "node_id", "session_id", "backend_id"},
        )
        session = services.resolve_handle(
            session_ref,
            expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
            expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
        )
        selections = result.outputs["selections"]
        self.assertEqual(session["backend_id"], ENGINEERING_VIEWER_BACKEND_ID)
        self.assertEqual(session["live_open_status"], "ready")
        self.assertEqual(session["options"]["live_mode"], "proxy")
        self.assertEqual(len(session["transport"]["layers"]), 2)
        self.assertEqual(session["transport"]["layers"][1]["scale_factor"], 1000.0)
        self.assertEqual(session["summary"]["source_kind"], "fe")
        self.assertTrue(session["summary"]["capabilities"]["model_tree"])
        self.assertTrue(session["options"]["show_attribute_colors"])
        self.assertFalse(session["options"]["show_orientation_triad"])
        self.assertFalse(session["options"]["show_view_cube"])
        self.assertTrue(session["options"]["show_world_axes"])
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
            self.assertTrue(session["summary"]["capabilities"][capability])
        self.assertEqual(selections["schema"], ENGINEERING_SELECTION_SCHEMA)
        self.assertEqual(selections["published_name"], "bolt_faces")
        self.assertEqual(
            [
                entity["entity_id"]
                for entity in selections["selections"][0]["entities"]
            ],
            ["block:0/node:0", "block:0/node:1"],
        )
        self.assertEqual(len(selections["selections"]), 1)

    def test_execute_materializes_ocp_body_in_memory_and_preserves_lifetime(
        self,
    ) -> None:
        services = WorkerServices()
        services.bind_data_types(build_builtin_registry().data_types)
        run_id = "run-ocp-body-viewer"
        workspace_id = "workspace-ocp-body-viewer"
        disposed: list[int] = []
        original_close = geometry_primitives._OcpBodyRecord.close  # noqa: SLF001

        def counted_close(record) -> None:  # noqa: ANN001
            disposed.append(id(record))
            original_close(record)

        with mock.patch.object(
            geometry_primitives._OcpBodyRecord,  # noqa: SLF001
            "close",
            counted_close,
        ):
            cylinder_context = ExecutionContext(
                run_id=run_id,
                node_id="node-cylinder",
                workspace_id=workspace_id,
                inputs={
                    "plane": TypedInlineValue(
                        PLANE_DATA_TYPE_ID,
                        1,
                        {
                            "origin": [0.0, 0.0, 0.0],
                            "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                            "normal": [0.0, 0.0, 1.0],
                        },
                    ),
                    "radius": 2.0,
                    "interval": Interval1D(0.0, 5.0),
                },
                properties={},
                emit_log=lambda _level, _message: None,
                worker_services=services,
            )
            body_ref = execute_cylinder(cylinder_context).outputs["body"]
            body_record = services.resolve_handle(
                body_ref,
                expected_data_type=OCP_BODY_DATA_TYPE_ID,
                expected_kind=OCP_BODY_HANDLE_KIND,
            )
            viewer_context = ExecutionContext(
                run_id=run_id,
                node_id="node-model-viewer",
                workspace_id=workspace_id,
                inputs={"scene_1": body_ref},
                properties={},
                emit_log=lambda _level, _message: None,
                worker_services=services,
            )

            result = execute_engineering_viewer(viewer_context)
            session_ref = result.outputs["session"]
            session = services.resolve_handle(
                session_ref,
                expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
                expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
            )
            primary = session["transport"]["layers"][0]
            asset = primary["display_asset"]
            shared_memory_name = asset["name"]

            self.assertEqual(session["live_open_status"], "ready")
            self.assertEqual(asset["storage"], "shared_memory")
            self.assertEqual(primary["display_path"], "")
            self.assertTrue(
                all(not item["path"] for item in primary["geometry_assets"])
            )
            self.assertEqual(disposed, [])
            json.dumps(body_ref.metadata, allow_nan=False)
            json.dumps(session_ref.metadata, allow_nan=False)
            json.dumps(session, allow_nan=False)
            attachment = SharedMemory(name=shared_memory_name, create=False)
            attachment.close()

            record = services.viewer_session_service._sessions[  # noqa: SLF001
                (workspace_id, session_ref.metadata["session_id"])
            ]
            native_source_ref = record.source_refs["native_source:scene_1"]
            prepared_scene_ref = record.source_refs["scene:scene_1"]
            self.assertEqual(native_source_ref.handle_id, body_ref.handle_id)
            self.assertIs(
                services.resolve_handle(
                    native_source_ref,
                    expected_data_type=OCP_BODY_DATA_TYPE_ID,
                    expected_kind=OCP_BODY_HANDLE_KIND,
                ),
                body_record,
            )

            services.cleanup_run(run_id)

            with self.assertRaises(StaleHandleError):
                services.resolve_handle(body_ref)
            self.assertIsNotNone(body_record.shape)
            self.assertIsNotNone(services.resolve_handle(prepared_scene_ref))
            self.assertIs(
                services.resolve_handle(native_source_ref),
                body_record,
            )

            services.viewer_session_service.close_session(
                CloseViewerSessionCommand(
                    workspace_id=workspace_id,
                    node_id="node-model-viewer",
                    session_id=session_ref.metadata["session_id"],
                )
            )

            self.assertEqual(disposed, [id(body_record)])
            self.assertIsNone(body_record.shape)
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=shared_memory_name, create=False)

    def test_geometry_group_viewer_preserves_ordered_native_lifetime(self) -> None:
        registry = build_builtin_registry()
        services = WorkerServices()
        services.bind_data_types(registry.data_types)
        run_id = "run-geometry-group-viewer"
        workspace_id = "workspace-geometry-group-viewer"
        body_disposals: list[int] = []
        group_disposals: list[int] = []
        original_body_close = geometry_primitives._OcpBodyRecord.close  # noqa: SLF001
        original_group_close = (  # noqa: SLF001
            geometry_primitives._GeometryGroupRecord.close
        )

        def counted_body_close(record) -> None:  # noqa: ANN001
            body_disposals.append(id(record))
            original_body_close(record)

        def counted_group_close(record) -> None:  # noqa: ANN001
            group_disposals.append(id(record))
            original_group_close(record)

        with (
            mock.patch.object(
                geometry_primitives._OcpBodyRecord,  # noqa: SLF001
                "close",
                counted_body_close,
            ),
            mock.patch.object(
                geometry_primitives._GeometryGroupRecord,  # noqa: SLF001
                "close",
                counted_group_close,
            ),
        ):
            body_refs = []
            body_records = []
            for index, origin_x in enumerate((0.0, 10.0)):
                context = ExecutionContext(
                    run_id=run_id,
                    node_id=f"node-cylinder-{index}",
                    workspace_id=workspace_id,
                    inputs={
                        "plane": TypedInlineValue(
                            PLANE_DATA_TYPE_ID,
                            1,
                            {
                                "origin": [origin_x, 0.0, 0.0],
                                "axes": [
                                    [1.0, 0.0, 0.0],
                                    [0.0, 1.0, 0.0],
                                ],
                                "normal": [0.0, 0.0, 1.0],
                            },
                        ),
                        "radius": 2.0,
                        "interval": Interval1D(0.0, 5.0),
                    },
                    properties={},
                    emit_log=lambda _level, _message: None,
                    worker_services=services,
                )
                body_ref = execute_cylinder(context).outputs["body"]
                body_refs.append(body_ref)
                body_records.append(
                    services.resolve_handle(
                        body_ref,
                        expected_data_type=OCP_BODY_DATA_TYPE_ID,
                        expected_kind=OCP_BODY_HANDLE_KIND,
                    )
                )

            group_context = ExecutionContext(
                run_id=run_id,
                node_id="node-construct-geometry-group",
                workspace_id=workspace_id,
                inputs={
                    "name": "Primary Geometry Group",
                    "geometry": body_refs,
                    "tolerances": [],
                },
                properties={},
                emit_log=lambda _level, _message: None,
                worker_services=services,
            )
            group_ref = execute_construct_geometry_group(group_context).outputs["group"]
            group_record = services.resolve_handle(
                group_ref,
                expected_data_type=GEOMETRY_GROUP_DATA_TYPE_ID,
                expected_kind=GEOMETRY_GROUP_HANDLE_KIND,
            )
            self.assertEqual(group_record.name, "Primary Geometry Group")
            self.assertEqual(group_record.tolerances, (0.0, 0.0))
            self.assertEqual(
                [ref.handle_id for ref in group_record.child_leases],
                [ref.handle_id for ref in body_refs],
            )

            viewer_context = ExecutionContext(
                run_id=run_id,
                node_id="node-model-viewer",
                workspace_id=workspace_id,
                inputs={"scene_1": group_ref},
                properties={},
                emit_log=lambda _level, _message: None,
                worker_services=services,
            )
            result = execute_engineering_viewer(viewer_context)
            session_ref = result.outputs["session"]
            session = services.resolve_handle(
                session_ref,
                expected_data_type=VIEWER_SESSION_DATA_TYPE_ID,
                expected_kind=COREX_VIEWER_SESSION_HANDLE_KIND,
            )
            primary = session["transport"]["layers"][0]
            asset = primary["display_asset"]
            shared_memory_name = asset["name"]

            self.assertEqual(session["live_open_status"], "ready")
            self.assertEqual(asset["storage"], "shared_memory")
            self.assertEqual(primary["display_path"], "")
            self.assertTrue(
                all(not item["path"] for item in primary["geometry_assets"])
            )
            self.assertEqual(body_disposals, [])
            self.assertEqual(group_disposals, [])
            json.dumps(group_ref.metadata, allow_nan=False)
            json.dumps(session_ref.metadata, allow_nan=False)
            json.dumps(session, allow_nan=False)
            attachment = SharedMemory(name=shared_memory_name, create=False)
            attachment.close()

            session_record = services.viewer_session_service._sessions[  # noqa: SLF001
                (workspace_id, session_ref.metadata["session_id"])
            ]
            native_source_ref = session_record.source_refs["native_source:scene_1"]
            prepared_scene_ref = session_record.source_refs["scene:scene_1"]
            self.assertEqual(native_source_ref.handle_id, group_ref.handle_id)
            self.assertIs(services.resolve_handle(native_source_ref), group_record)
            self.assertEqual(
                prepared_scene_ref.metadata["source"]["source_path"],
                "memory://corex/GeometryGroup",
            )

            services.cleanup_run(run_id)

            for body_ref in body_refs:
                with self.assertRaises(StaleHandleError):
                    services.resolve_handle(body_ref)
            with self.assertRaises(StaleHandleError):
                services.resolve_handle(group_ref)
            self.assertFalse(group_record.closed)
            self.assertEqual(body_disposals, [])
            self.assertEqual(group_disposals, [])
            self.assertIsNotNone(services.resolve_handle(prepared_scene_ref))
            self.assertIs(services.resolve_handle(native_source_ref), group_record)
            for child_ref, body_record in zip(
                group_record.child_leases,
                body_records,
                strict=True,
            ):
                self.assertIs(services.resolve_handle(child_ref), body_record)
                self.assertIsNotNone(body_record.shape)

            services.viewer_session_service.close_session(
                CloseViewerSessionCommand(
                    workspace_id=workspace_id,
                    node_id="node-model-viewer",
                    session_id=session_ref.metadata["session_id"],
                )
            )

            self.assertEqual(group_disposals, [id(group_record)])
            self.assertEqual(
                body_disposals,
                [id(body_records[1]), id(body_records[0])],
            )
            self.assertTrue(group_record.closed)
            self.assertEqual(group_record.child_leases, ())
            self.assertTrue(all(record.shape is None for record in body_records))
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=shared_memory_name, create=False)

    def test_unbound_or_changed_selection_fingerprints_are_not_published(self) -> None:
        saved = {
            "schema": ENGINEERING_SELECTION_SCHEMA,
            "scene_fingerprint": "",
            "published_name": "faces",
            "selections": [
                {
                    "name": "faces",
                    "entity_kind": "face",
                    "entity_ids": ["1"],
                }
            ],
        }

        result = _selection_output_for_scene(
            saved,
            layer_fingerprints={"scene_1": "a" * 64},
        )

        self.assertEqual(result["scene_fingerprint"], _composition_fingerprint({"scene_1": "a" * 64}))
        self.assertEqual(result["published_name"], "")
        self.assertEqual(result["selections"], [])

    def test_replaced_overlay_entities_are_not_published(self) -> None:
        fingerprint = _composition_fingerprint({"scene_1": "a" * 64, "scene_2": "b" * 64})
        saved = {
            "schema": ENGINEERING_SELECTION_SCHEMA,
            "scene_fingerprint": fingerprint,
            "published_name": "overlay_elements",
            "selections": [
                {
                    "name": "overlay_elements",
                    "scene_fingerprint": fingerprint,
                    "entities": [
                        {
                            "layer_id": "scene_2",
                            "source_fingerprint": "b" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": "block:2/element:9",
                        }
                    ],
                }
            ],
        }

        result = _selection_output_for_scene(
            saved,
            layer_fingerprints={"scene_1": "a" * 64, "scene_2": "c" * 64},
        )

        self.assertEqual(result["scene_fingerprint"], _composition_fingerprint({"scene_1": "a" * 64, "scene_2": "c" * 64}))
        self.assertEqual(result["published_name"], "")
        self.assertEqual(result["selections"], [])

    def test_current_overlay_entities_remain_publishable_for_the_scene(self) -> None:
        fingerprint = _composition_fingerprint({"scene_1": "a" * 64, "scene_2": "b" * 64})
        saved = {
            "schema": ENGINEERING_SELECTION_SCHEMA,
            "scene_fingerprint": fingerprint,
            "published_name": "overlay_elements",
            "selections": [
                {
                    "name": "overlay_elements",
                    "scene_fingerprint": fingerprint,
                    "entities": [
                        {
                            "layer_id": "scene_2",
                            "source_fingerprint": "b" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": "block:2/element:9",
                        }
                    ],
                }
            ],
        }

        result = _selection_output_for_scene(
            saved,
            layer_fingerprints={"scene_1": "a" * 64, "scene_2": "b" * 64},
        )

        self.assertEqual(result["published_name"], "overlay_elements")
        self.assertEqual(
            result["selections"][0]["entities"][0]["source_fingerprint"],
            "b" * 64,
        )

    def test_mixed_selection_keeps_only_entities_from_current_layers(self) -> None:
        fingerprint = _composition_fingerprint({"scene_1": "a" * 64, "scene_2": "b" * 64})
        saved = {
            "schema": ENGINEERING_SELECTION_SCHEMA,
            "scene_fingerprint": fingerprint,
            "published_name": "mixed",
            "selections": [
                {
                    "name": "mixed",
                    "scene_fingerprint": fingerprint,
                    "entities": [
                        {
                            "layer_id": "scene_1",
                            "source_fingerprint": "a" * 64,
                            "entity_kind": "cad_face",
                            "entity_id": "part:1/face:2",
                        },
                        {
                            "layer_id": "scene_2",
                            "source_fingerprint": "b" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": "block:2/element:9",
                        },
                        {
                            "layer_id": "scene_2",
                            "source_fingerprint": "c" * 64,
                            "entity_kind": "fe_element",
                            "entity_id": "block:2/element:10",
                        },
                    ],
                }
            ],
        }

        result = _selection_output_for_scene(
            saved,
            layer_fingerprints={"scene_1": "a" * 64, "scene_2": "b" * 64},
        )

        self.assertEqual(result["published_name"], "mixed")
        self.assertEqual(
            [
                (entity["layer_id"], entity["source_fingerprint"])
                for entity in result["selections"][0]["entities"]
            ],
            [("scene_1", "a" * 64), ("scene_2", "b" * 64)],
        )


if __name__ == "__main__":
    unittest.main()
