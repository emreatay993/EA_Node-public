from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.node_specs import (
    NodeTypeSpec,
    PortSpec,
    SettingsGroupItemSpec,
    SettingsGroupSpec,
)
from ea_node_editor.nodes.builtins.excalidraw import (
    EXCALIDRAW_BOARD_TYPE_ID,
    EXCALIDRAW_PREVIEW_REF_PROPERTY,
    EXCALIDRAW_STATE_PROPERTY,
)
from ea_node_editor.nodes.builtins.jupyter_notebook import JUPYTER_NOTEBOOK_TYPE_ID
from ea_node_editor.common.artifact_refs import (
    format_managed_artifact_ref,
    format_staged_artifact_ref,
)
from ea_node_editor.persistence.project_codec import (
    collect_project_artifact_references,
    rewrite_project_artifact_refs,
)
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.settings import SCHEMA_VERSION
from ea_node_editor.workspace.manager import WorkspaceManager


class SerializerRoundTripMixin:
    def test_load_prunes_only_incompatible_typed_edge_without_rewriting_source(self) -> None:
        registry = build_builtin_registry()
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace
        mutations = model.validated_mutations(workspace_id=workspace.workspace_id, registry=registry)
        nodes = {
            type_id: mutations.add_node(
                type_id=type_id, title=type_id, x=float(index * 100), y=0.0,
                properties=registry.default_properties(type_id),
            )
            for index, type_id in enumerate((
                "geometry.construct_group", "io.file_write", "core.constant",
                "fea.force", "fea.load_container", "data.panel",
            ))
        }
        valid_edges = [
            mutations.add_edge(
                source_node_id=nodes[source_type].node_id, source_port_key=source_port,
                target_node_id=nodes[target_type].node_id, target_port_key=target_port,
            )
            for source_type, source_port, target_type, target_port in (
                ("core.constant", "value", "io.file_write", "data"),
                ("fea.force", "load", "fea.load_container", "load"),
                ("core.constant", "value", "data.panel", "input"),
            )
        ]
        document = serializer.to_persistent_document(model.project)
        self.assertEqual(document["schema_version"], SCHEMA_VERSION)
        workspace_doc = document["workspaces"][0]
        workspace_doc["dirty"] = False
        clean = serializer.from_document(json.loads(json.dumps(document)))
        self.assertFalse(clean.workspaces[workspace.workspace_id].dirty)
        obsolete_edge = {
            **workspace_doc["edges"][0],
            "edge_id": "old_geometry_to_file_write",
            "source_node_id": nodes["geometry.construct_group"].node_id,
            "source_port_key": "group",
            "target_node_id": nodes["io.file_write"].node_id,
            "target_port_key": "data",
            "input_order": 1,
        }
        workspace_doc["edges"].append(obsolete_edge)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "typed_connections.cxproj"
            path.write_text(json.dumps(document), encoding="utf-8")
            original_bytes = path.read_bytes()
            loaded = serializer.load(str(path))
            loaded_workspace = loaded.workspaces[workspace.workspace_id]
            expected_edge_ids = {edge.edge_id for edge in valid_edges}
            self.assertEqual(set(loaded_workspace.edges), expected_edge_ids)
            self.assertEqual(set(loaded_workspace.nodes), set(workspace.nodes))
            self.assertTrue(loaded_workspace.dirty)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertIn(obsolete_edge["edge_id"], {edge["edge_id"] for edge in json.loads(original_bytes)["workspaces"][0]["edges"]})
            serializer.save(str(path), loaded)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual({edge["edge_id"] for edge in saved["workspaces"][0]["edges"]}, expected_edge_ids)

    def test_round_trip_omits_removed_settings_section_state(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(workspace.workspace_id, "core.logger", "Logger", 10.0, 20.0)
        serializer = JsonProjectSerializer(build_default_registry())

        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(
            item for item in document["workspaces"] if item["workspace_id"] == workspace.workspace_id
        )
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        self.assertEqual(node_doc["expanded_settings_group_ids"], [])
        self.assertNotIn("settings_section_expanded", node_doc)
        self.assertNotIn("advanced_section_expanded", node_doc)

        node_doc["settings_section_expanded"] = True
        node_doc["advanced_section_expanded"] = True
        reserialized = serializer.to_persistent_document(
            serializer.from_document(document)
        )
        reserialized_node = next(
            item
            for item in reserialized["workspaces"][0]["nodes"]
            if item["node_id"] == node.node_id
        )
        self.assertNotIn("settings_section_expanded", reserialized_node)
        self.assertNotIn("advanced_section_expanded", reserialized_node)
        self.assertEqual(reserialized_node["expanded_settings_group_ids"], [])

    def test_round_trip_preserves_and_normalizes_expanded_settings_group_ids(self) -> None:
        registry = build_default_registry()
        spec = NodeTypeSpec(
            type_id="tests.settings_group_state",
            display_name="Settings Group State",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "in", "data", 'COREX.DataTypes.Any', required=False),),
            properties=(),
            settings_groups=(
                SettingsGroupSpec(
                    group_id="options",
                    label="Options",
                    items=(SettingsGroupItemSpec(port_key="value"),),
                ),
            ),
        )
        registry.register_descriptor(spec, lambda: object())
        serializer = JsonProjectSerializer(registry)
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(workspace.workspace_id, spec.type_id, spec.display_name, 10.0, 20.0)
        model.set_node_expanded_settings_group_ids(
            workspace.workspace_id,
            node.node_id,
            ("options",),
        )

        document = serializer.to_persistent_document(model.project)
        node_doc = next(item for item in document["workspaces"][0]["nodes"] if item["node_id"] == node.node_id)
        self.assertEqual(node_doc["expanded_settings_group_ids"], ["options"])

        node_doc["expanded_settings_group_ids"] = ["missing", "options", "options"]
        loaded = serializer.from_document(document)
        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.expanded_settings_group_ids, ("options",))
        reserialized = serializer.to_persistent_document(loaded)
        reserialized_node = next(
            item for item in reserialized["workspaces"][0]["nodes"] if item["node_id"] == node.node_id
        )
        self.assertEqual(reserialized_node["expanded_settings_group_ids"], ["options"])

        missing_state_document = serializer.to_persistent_document(model.project)
        missing_state_node = next(
            item for item in missing_state_document["workspaces"][0]["nodes"] if item["node_id"] == node.node_id
        )
        missing_state_node.pop("expanded_settings_group_ids")
        defaulted = serializer.from_document(missing_state_document)
        self.assertEqual(
            defaulted.workspaces[workspace.workspace_id].nodes[node.node_id].expanded_settings_group_ids,
            (),
        )

    def test_round_trip_preserves_workspace_view_and_graph(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        view = model.create_view(workspace.workspace_id, name="V2")
        model.set_active_view(workspace.workspace_id, view.view_id)
        node_a = model.add_node(workspace.workspace_id, "core.constant", "Constant", 10, 20)
        node_b = model.add_node(workspace.workspace_id, "core.logger", "Logger", 80, 120)
        edge = model.add_edge(workspace.workspace_id, node_a.node_id, "as_text", node_b.node_id, "message")

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        self.assertEqual(loaded.active_workspace_id, workspace.workspace_id)
        loaded_ws = loaded.workspaces[workspace.workspace_id]
        self.assertEqual(loaded_ws.active_view_id, view.view_id)
        self.assertIn(node_a.node_id, loaded_ws.nodes)
        self.assertIn(node_b.node_id, loaded_ws.nodes)
        self.assertIn(edge.edge_id, loaded_ws.edges)

    def test_round_trip_preserves_custom_view_order(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        first_view_id = workspace.active_view_id
        second_view_id = model.create_view(workspace.workspace_id, name="Inspection").view_id
        third_view_id = model.create_view(workspace.workspace_id, name="Review").view_id
        model.move_view(workspace.workspace_id, 2, 0)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_workspace = loaded.workspaces[workspace.workspace_id]
        self.assertEqual(list(loaded_workspace.views), [third_view_id, first_view_id, second_view_id])
        self.assertEqual(loaded_workspace.active_view_id, third_view_id)

    def test_image_animation_playback_mode_round_trips_and_invalid_values_normalize(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Animated Image",
            25.0,
            45.0,
            properties={"source": "", "animation_playback_mode": "pause"},
            exposed_ports={"source": False},
        )
        serializer = JsonProjectSerializer(build_default_registry())

        document = serializer.to_document(model.project)
        loaded = serializer.from_document(document)
        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.properties["animation_playback_mode"], "pause")

        workspace_doc = next(
            item for item in document["workspaces"] if item["workspace_id"] == workspace.workspace_id
        )
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        node_doc["properties"]["animation_playback_mode"] = "invalid"
        invalid_loaded = serializer.from_document(document)
        invalid_node = invalid_loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(invalid_node.properties["animation_playback_mode"], "auto")

        node_doc["properties"].pop("animation_playback_mode")
        sparse_loaded = serializer.from_document(document)
        sparse_node = sparse_loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(sparse_node.properties.get("animation_playback_mode", "auto"), "auto")

    def test_round_trip_artifact_ref_helpers_collect_and_rewrite_persistent_document(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            25.0,
            45.0,
            properties={
                "source": format_staged_artifact_ref("pending_output"),
                "fallback": format_managed_artifact_ref("existing_asset"),
                "gallery": [format_staged_artifact_ref("pending_gallery")],
            },
        )
        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_persistent_document(model.project)
        refs = collect_project_artifact_references(doc)

        self.assertEqual(refs.managed_ids, frozenset({"existing_asset"}))
        self.assertEqual(
            refs.staged_ids,
            frozenset({"pending_output", "pending_gallery"}),
        )

        rewritten = rewrite_project_artifact_refs(
            doc,
            {
                format_staged_artifact_ref("pending_output"): format_managed_artifact_ref("pending_output"),
            },
        )
        workspace_doc = next(ws for ws in rewritten["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        resolved_node = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(
            resolved_node["properties"],
            {
                "source": format_managed_artifact_ref("pending_output"),
                "fallback": format_managed_artifact_ref("existing_asset"),
                "gallery": [format_staged_artifact_ref("pending_gallery")],
            },
        )

    def test_round_trip_persists_visual_style_only_for_passive_nodes(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node_a = model.add_node(workspace.workspace_id, "core.constant", "Constant", 10, 20)
        node_b = model.add_node(workspace.workspace_id, "core.logger", "Logger", 80, 120)
        passive_node = model.add_node(
            workspace.workspace_id,
            "passive.flowchart.process",
            "Process",
            320,
            120,
        )
        node_a.visual_style = {"fill": "#102030", "badge": {"shape": "pill"}}
        node_b.visual_style = {"outline": {"width": 2}}
        passive_node.visual_style = {"fill": "#405060"}
        edge = model.add_edge(workspace.workspace_id, node_a.node_id, "as_text", node_b.node_id, "message")
        edge.label = "Primary path"
        edge.visual_style = {"stroke": "dashed", "arrow": {"kind": "none"}}

        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_document(model.project)
        workspace_doc = next(ws for ws in doc["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        active_node_docs = [
            item for item in workspace_doc["nodes"] if item["node_id"] in {node_a.node_id, node_b.node_id}
        ]
        passive_node_doc = next(
            item for item in workspace_doc["nodes"] if item["node_id"] == passive_node.node_id
        )
        edge_doc = next(item for item in workspace_doc["edges"] if item["edge_id"] == edge.edge_id)

        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            doc["metadata"]["ui"]["passive_style_presets"],
            {"node_presets": [], "edge_presets": []},
        )
        self.assertEqual(
            doc["metadata"]["artifact_store"],
            {"artifacts": {}, "staged": {}},
        )
        self.assertTrue(all("visual_style" not in item for item in active_node_docs))
        self.assertEqual(passive_node_doc["visual_style"], {"fill": "#405060"})
        self.assertEqual(edge_doc["label"], "Primary path")
        self.assertEqual(edge_doc["visual_style"], {"stroke": "dashed", "arrow": {"kind": "none"}})

        loaded = serializer.from_document(doc)
        loaded_ws = loaded.workspaces[workspace.workspace_id]

        self.assertEqual(loaded_ws.nodes[node_a.node_id].visual_style, {})
        self.assertEqual(loaded_ws.nodes[node_b.node_id].visual_style, {})
        self.assertEqual(loaded_ws.nodes[passive_node.node_id].visual_style, {"fill": "#405060"})
        self.assertEqual(loaded_ws.edges[edge.edge_id].label, "Primary path")
        self.assertEqual(
            loaded_ws.edges[edge.edge_id].visual_style,
            {"stroke": "dashed", "arrow": {"kind": "none"}},
        )

    def test_round_trip_normalizes_project_local_passive_style_presets(self) -> None:
        model = GraphModel()
        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_document(model.project)
        doc["metadata"]["ui"]["passive_style_presets"] = {
            "node_presets": [
                {
                    "preset_id": "NodePresetBad",
                    "name": " Flow Warm ",
                    "style": {
                        "fill_color": "#112233",
                        "border_width": "2.5",
                        "ignored": True,
                    },
                },
                {
                    "preset_id": "",
                    "name": " ",
                    "style": {
                        "text_color": "#445566",
                        "font_size": "15",
                    },
                },
            ],
            "edge_presets": [
                {
                    "preset_id": "edge_preset_deadbeef",
                    "name": " Link ",
                    "style": {
                        "stroke_color": "#abcdef",
                        "stroke_width": "3",
                        "stroke_pattern": "dashed",
                        "arrow_head": "open",
                        "ignored": "value",
                    },
                },
                {
                    "preset_id": "edge_preset_deadbeef",
                    "name": "",
                    "style": {
                        "label_text_color": "#010203",
                        "label_background_color": "#AABBCC",
                    },
                },
            ],
        }

        loaded = serializer.from_document(doc)
        presets = loaded.metadata["ui"]["passive_style_presets"]

        self.assertEqual(len(presets["node_presets"]), 2)
        self.assertRegex(presets["node_presets"][0]["preset_id"], r"^node_preset_[0-9a-f]{8}$")
        self.assertRegex(presets["node_presets"][1]["preset_id"], r"^node_preset_[0-9a-f]{8}$")
        self.assertNotEqual(presets["node_presets"][0]["preset_id"], presets["node_presets"][1]["preset_id"])
        self.assertEqual(presets["node_presets"][0]["name"], "Flow Warm")
        self.assertEqual(presets["node_presets"][1]["name"], "Node Preset 2")
        self.assertEqual(
            presets["node_presets"][0]["style"],
            {
                "fill_color": "#112233",
                "border_width": 2.5,
                "ignored": True,
            },
        )
        self.assertEqual(
            presets["node_presets"][1]["style"],
            {
                "text_color": "#445566",
                "font_size": 15,
            },
        )

        self.assertEqual(len(presets["edge_presets"]), 2)
        self.assertEqual(presets["edge_presets"][0]["preset_id"], "edge_preset_deadbeef")
        self.assertRegex(presets["edge_presets"][1]["preset_id"], r"^edge_preset_[0-9a-f]{8}$")
        self.assertNotEqual(presets["edge_presets"][0]["preset_id"], presets["edge_presets"][1]["preset_id"])
        self.assertEqual(presets["edge_presets"][0]["name"], "Link")
        self.assertEqual(presets["edge_presets"][1]["name"], "Edge Preset 2")
        self.assertEqual(
            presets["edge_presets"][0]["style"],
            {
                "stroke_color": "#abcdef",
                "stroke_width": 3.0,
                "stroke_pattern": "dashed",
                "arrow_head": "open",
            },
        )
        self.assertEqual(
            presets["edge_presets"][1]["style"],
            {
                "label_text_color": "#010203",
                "label_background_color": "#AABBCC",
            },
        )

        saved_doc = serializer.to_document(loaded)
        self.assertEqual(saved_doc["metadata"]["ui"]["passive_style_presets"], presets)

    def test_round_trip_preserves_media_panel_image_properties_and_size(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            25.0,
            45.0,
            properties={
                "source": r"C:\fixtures\diagram.png",
                "fit_mode": "cover",
            },
        )
        model.set_node_size(workspace.workspace_id, node.node_id, 348.0, 258.0)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "media.panel")
        self.assertEqual(
            loaded_node.properties,
            {
                "source": r"C:\fixtures\diagram.png",
                "fit_mode": "cover",
            },
        )
        self.assertEqual(loaded_node.custom_width, 348.0)
        self.assertEqual(loaded_node.custom_height, 258.0)

    def test_round_trip_preserves_passive_annotation_text_properties_and_size(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "passive.annotation.text",
            "Text",
            25.0,
            45.0,
            properties={
                "text": "**Markdown** note",
                "format": "markdown",
                "font_size": 22,
                "font_weight": "bold",
                "italic": True,
                "text_color": "#AABBCC",
                "horizontal_alignment": "center",
                "wrap_mode": "anywhere",
            },
        )
        model.set_node_size(workspace.workspace_id, node.node_id, 300.0, 120.0)
        model.set_node_locked(workspace.workspace_id, node.node_id, True)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "passive.annotation.text")
        self.assertEqual(loaded_node.properties["text"], "**Markdown** note")
        self.assertEqual(loaded_node.properties["font_size"], 22)
        self.assertEqual(loaded_node.properties["font_weight"], "bold")
        self.assertTrue(loaded_node.properties["italic"])
        self.assertEqual(loaded_node.properties["text_color"], "#AABBCC")
        self.assertEqual(loaded_node.properties["horizontal_alignment"], "center")
        self.assertEqual(loaded_node.properties["wrap_mode"], "anywhere")
        self.assertEqual(loaded_node.custom_width, 300.0)
        self.assertEqual(loaded_node.custom_height, 120.0)
        self.assertTrue(loaded_node.locked)

    def test_round_trip_preserves_reusable_rich_text_slot_properties(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "passive.planning.task_card",
            "Task",
            25.0,
            45.0,
            properties={
                "title": "Task",
                "body": "**Markdown** body",
                "body_format": "markdown",
                "body_font_size": 24,
                "body_font_weight": "bold",
                "body_text_color": "#112233",
                "status": "todo",
            },
        )

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "passive.planning.task_card")
        self.assertEqual(loaded_node.properties["body"], "**Markdown** body")
        self.assertEqual(loaded_node.properties["body_format"], "markdown")
        self.assertEqual(loaded_node.properties["body_font_size"], 24)
        self.assertEqual(loaded_node.properties["body_font_weight"], "bold")
        self.assertEqual(loaded_node.properties["body_text_color"], "#112233")

    def test_round_trip_preserves_folder_explorer_current_path(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "io.folder_explorer",
            "Folder Explorer",
            25.0,
            45.0,
            properties={"current_path": r"C:\fixtures\folder"},
        )

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "io.folder_explorer")
        self.assertEqual(
            loaded_node.properties,
            {"current_path": r"C:\fixtures\folder"},
        )

    def test_round_trip_preserves_excalidraw_board_state_and_preview_ref(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        excalidraw_state = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {
                    "id": "rect-1",
                    "type": "rectangle",
                    "x": 24,
                    "y": 32,
                }
            ],
            "appState": {"viewBackgroundColor": "#ffffff"},
        }
        preview_artifact_id = "excalidraw_board_preview"
        preview_ref = {
            "artifact_ref": format_managed_artifact_ref(preview_artifact_id),
            "mime_type": "image/png",
        }
        node = model.validated_mutations(workspace.workspace_id, registry).add_node(
            type_id=EXCALIDRAW_BOARD_TYPE_ID,
            title="Excalidraw Board",
            x=25.0,
            y=45.0,
            properties={
                EXCALIDRAW_STATE_PROPERTY: excalidraw_state,
                EXCALIDRAW_PREVIEW_REF_PROPERTY: preview_ref,
            },
        )
        model.project.metadata["artifact_store"] = {
            "artifacts": {
                preview_artifact_id: {
                    "relative_path": (
                        "nodes/Excalidraw Board [11111111]/out/"
                        "excalidraw_board_preview.png"
                    ),
                },
            },
        }

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(node_doc["properties"][EXCALIDRAW_STATE_PROPERTY], excalidraw_state)
        self.assertEqual(node_doc["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY], preview_ref)
        serialized_preview_ref = json.dumps(node_doc["properties"][EXCALIDRAW_PREVIEW_REF_PROPERTY])
        self.assertNotIn("data:image", serialized_preview_ref)
        self.assertNotIn("base64", serialized_preview_ref)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, EXCALIDRAW_BOARD_TYPE_ID)
        self.assertEqual(loaded_node.properties[EXCALIDRAW_STATE_PROPERTY], excalidraw_state)
        self.assertEqual(loaded_node.properties[EXCALIDRAW_PREVIEW_REF_PROPERTY], preview_ref)

    def test_round_trip_preserves_jupyter_notebook_ref_and_promotes_staged_on_save(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        notebook_ref = format_staged_artifact_ref("pending_jupyter_notebook")
        server_state = {"zoom": 1.2, "scroll_top": 40, "last_frontend": "lab"}
        node = model.validated_mutations(workspace.workspace_id, registry).add_node(
            type_id=JUPYTER_NOTEBOOK_TYPE_ID,
            title="Analysis Notebook",
            x=25.0,
            y=45.0,
            properties={
                "notebook_ref": notebook_ref,
                "frontend": "lab",
                "server_state": server_state,
            },
        )

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)

        # The .ipynb participates in Save-As promotion (staged -> managed copy).
        refs = collect_project_artifact_references(document)
        self.assertIn("pending_jupyter_notebook", refs.staged_ids)
        rewritten = rewrite_project_artifact_refs(
            document,
            {notebook_ref: format_managed_artifact_ref("pending_jupyter_notebook")},
        )
        rewritten["metadata"]["artifact_store"] = {
            "artifacts": {
                "pending_jupyter_notebook": {
                    "relative_path": (
                        "nodes/Analysis Notebook [11111111]/in/"
                        "pending_jupyter_notebook.ipynb"
                    ),
                },
            },
            "staged": {},
        }
        rewritten_ws = next(
            ws for ws in rewritten["workspaces"] if ws["workspace_id"] == workspace.workspace_id
        )
        rewritten_node = next(
            item for item in rewritten_ws["nodes"] if item["node_id"] == node.node_id
        )
        self.assertEqual(
            rewritten_node["properties"]["notebook_ref"],
            format_managed_artifact_ref("pending_jupyter_notebook"),
        )

        # Full save/load preserves the notebook ref, frontend, and UI server state.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save_document(str(path), rewritten)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, JUPYTER_NOTEBOOK_TYPE_ID)
        self.assertEqual(
            loaded_node.properties["notebook_ref"],
            format_managed_artifact_ref("pending_jupyter_notebook"),
        )
        self.assertEqual(loaded_node.properties["frontend"], "lab")
        self.assertEqual(loaded_node.properties["server_state"], server_state)

    def test_load_preserves_sparse_media_panel_properties_while_coercing_present_values(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        serializer = JsonProjectSerializer(build_default_registry())
        doc = serializer.to_document(model.project)
        workspace_doc = next(ws for ws in doc["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        workspace_doc["nodes"].append(
            {
                "node_id": "node_media_panel_sparse",
                "type_id": "media.panel",
                "title": "Media Panel",
                "x": 25.0,
                "y": 45.0,
                "collapsed": False,
                "properties": {
                    "source": r"C:\fixtures\diagram.png",
                    "fit_mode": "cover",
                    "crop_w": "0.5",
                    "crop_h": None,
                },
                "exposed_ports": {},
                "visual_style": {},
                "parent_node_id": None,
                "custom_width": 348.0,
                "custom_height": 258.0,
            }
        )

        loaded = serializer.from_document(doc)

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes["node_media_panel_sparse"]
        self.assertEqual(
            loaded_node.properties,
            {
                "source": r"C:\fixtures\diagram.png",
                "fit_mode": "cover",
                "crop_w": 0.5,
                "crop_h": 1.0,
            },
        )

    def test_round_trip_preserves_media_panel_pdf_properties_and_size(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            40.0,
            60.0,
            properties={
                "source": r"C:\fixtures\manual.pdf",
                "page_number": 4,
            },
        )
        model.set_node_size(workspace.workspace_id, node.node_id, 312.0, 428.0)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "media.panel")
        self.assertEqual(
            loaded_node.properties,
            {
                "source": r"C:\fixtures\manual.pdf",
                "page_number": 4,
            },
        )
        self.assertEqual(loaded_node.custom_width, 312.0)
        self.assertEqual(loaded_node.custom_height, 428.0)

    def test_round_trip_preserves_media_panel_video_properties_and_position(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            40.0,
            60.0,
            properties={
                "source": r"C:\fixtures\clip.mp4",
                "fit_mode": "cover",
                "auto_play": True,
                "loop": True,
                "muted": True,
                "volume": 0.35,
                "playback_rate": 1.5,
                "position_ms": 42000,
                "timeline_bookmarks": [{"id": "key-frame", "label": "Key frame", "position_ms": 42000}],
                "clip_enabled": True,
                "clip_start_ms": 40000,
                "clip_end_ms": 50000,
            },
        )
        model.set_node_size(workspace.workspace_id, node.node_id, 380.0, 300.0)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.type_id, "media.panel")
        self.assertEqual(
            loaded_node.properties,
            {
                "source": r"C:\fixtures\clip.mp4",
                "fit_mode": "cover",
                "auto_play": True,
                "loop": True,
                "muted": True,
                "volume": 0.35,
                "playback_rate": 1.5,
                "position_ms": 42000,
                "timeline_bookmarks": [{"id": "key-frame", "label": "Key frame", "position_ms": 42000}],
                "clip_enabled": True,
                "clip_start_ms": 40000,
                "clip_end_ms": 50000,
            },
        )
        self.assertEqual(loaded_node.custom_width, 380.0)
        self.assertEqual(loaded_node.custom_height, 300.0)

    def test_round_trip_preserves_workspace_order_active_workspace_and_view_cameras(self) -> None:
        model = GraphModel()
        manager = WorkspaceManager(model)
        first = manager.active_workspace_id()
        second = manager.create_workspace("Second")
        manager.move_workspace(1, 0)
        manager.set_active_workspace(second)

        first_ws = model.project.workspaces[first]
        first_v1 = first_ws.views[first_ws.active_view_id]
        first_v1.zoom = 1.1
        first_v1.pan_x = 10.0
        first_v1.pan_y = 20.0
        first_v2 = model.create_view(first, name="V2")
        model.project.workspaces[first].views[first_v2.view_id].zoom = 1.8
        model.project.workspaces[first].views[first_v2.view_id].pan_x = 150.0
        model.project.workspaces[first].views[first_v2.view_id].pan_y = -45.0
        model.set_active_view(first, first_v2.view_id)

        second_ws = model.project.workspaces[second]
        second_v1 = second_ws.views[second_ws.active_view_id]
        second_v1.zoom = 0.85
        second_v1.pan_x = -12.0
        second_v1.pan_y = 34.0
        second_v2 = model.create_view(second, name="V2")
        model.project.workspaces[second].views[second_v2.view_id].zoom = 2.2
        model.project.workspaces[second].views[second_v2.view_id].pan_x = 300.0
        model.project.workspaces[second].views[second_v2.view_id].pan_y = 99.0
        model.set_active_view(second, second_v2.view_id)

        serializer = JsonProjectSerializer(build_default_registry())
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project.cxproj"
            serializer.save(str(path), model.project)
            loaded = serializer.load(str(path))

        self.assertEqual(loaded.metadata.get("workspace_order"), [second, first])
        self.assertEqual(loaded.active_workspace_id, second)
        self.assertEqual(loaded.workspaces[first].active_view_id, first_v2.view_id)
        self.assertEqual(loaded.workspaces[second].active_view_id, second_v2.view_id)
        self.assertEqual(loaded.workspaces[first].views[first_v1.view_id].zoom, 1.1)
        self.assertEqual(loaded.workspaces[first].views[first_v1.view_id].pan_x, 10.0)
        self.assertEqual(loaded.workspaces[first].views[first_v1.view_id].pan_y, 20.0)
        self.assertEqual(loaded.workspaces[first].views[first_v2.view_id].zoom, 1.8)
        self.assertEqual(loaded.workspaces[first].views[first_v2.view_id].pan_x, 150.0)
        self.assertEqual(loaded.workspaces[first].views[first_v2.view_id].pan_y, -45.0)
        self.assertEqual(loaded.workspaces[second].views[second_v1.view_id].zoom, 0.85)
        self.assertEqual(loaded.workspaces[second].views[second_v1.view_id].pan_x, -12.0)
        self.assertEqual(loaded.workspaces[second].views[second_v1.view_id].pan_y, 34.0)
        self.assertEqual(loaded.workspaces[second].views[second_v2.view_id].zoom, 2.2)
        self.assertEqual(loaded.workspaces[second].views[second_v2.view_id].pan_x, 300.0)
        self.assertEqual(loaded.workspaces[second].views[second_v2.view_id].pan_y, 99.0)


class SerializerArtifactRoundTripPacketTests(unittest.TestCase):
    def test_round_trip_preserves_project_artifact_store_metadata_and_string_refs(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        artifact_id = "image_panel_source"
        managed_ref = format_managed_artifact_ref(artifact_id)
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            25.0,
            45.0,
            properties={
                "source": managed_ref,
                "fit_mode": "contain",
            },
        )
        model.project.metadata["artifact_store"] = {
            "artifacts": {
                artifact_id: {
                    "relative_path": "nodes/Media Panel [11111111]/in/media/node_media_panel/source.png",
                }
            }
        }

        serializer = JsonProjectSerializer(build_default_registry())
        document = serializer.to_persistent_document(model.project)
        workspace_doc = next(ws for ws in document["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(document["schema_version"], SCHEMA_VERSION)
        self.assertEqual(node_doc["properties"]["source"], managed_ref)
        self.assertEqual(
            document["metadata"]["artifact_store"],
            {
                "artifacts": {
                    artifact_id: {
                        "relative_path": "nodes/Media Panel [11111111]/in/media/node_media_panel/source.png",
                    }
                },
                "staged": {},
            },
        )

        loaded = serializer.from_document(document)
        loaded_node = loaded.workspaces[workspace.workspace_id].nodes[node.node_id]
        self.assertEqual(loaded_node.properties["source"], managed_ref)
        self.assertEqual(
            loaded.metadata["artifact_store"],
            {
                "artifacts": {
                    artifact_id: {
                        "relative_path": "nodes/Media Panel [11111111]/in/media/node_media_panel/source.png",
                    }
                },
                "staged": {},
            },
        )

    def test_collect_and_rewrite_artifact_refs_from_persistent_document(self) -> None:
        model = GraphModel()
        workspace = model.active_workspace
        node = model.add_node(
            workspace.workspace_id,
            "media.panel",
            "Media Panel",
            25.0,
            45.0,
            properties={
                "source": format_staged_artifact_ref("pending_output"),
                "fallback": format_managed_artifact_ref("existing_asset"),
                "gallery": [format_staged_artifact_ref("pending_gallery")],
            },
        )
        serializer = JsonProjectSerializer(build_default_registry())
        document = serializer.to_persistent_document(model.project)
        refs = collect_project_artifact_references(document)

        self.assertEqual(refs.managed_ids, frozenset({"existing_asset"}))
        self.assertEqual(
            refs.staged_ids,
            frozenset({"pending_output", "pending_gallery"}),
        )

        rewritten = rewrite_project_artifact_refs(
            document,
            {
                format_staged_artifact_ref("pending_output"): format_managed_artifact_ref("pending_output"),
            },
        )
        workspace_doc = next(ws for ws in rewritten["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        resolved_node = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)

        self.assertEqual(
            resolved_node["properties"],
            {
                "source": format_managed_artifact_ref("pending_output"),
                "fallback": format_managed_artifact_ref("existing_asset"),
                "gallery": [format_staged_artifact_ref("pending_gallery")],
            },
        )

    def test_collect_and_rewrite_excalidraw_nested_artifact_refs_from_persistent_document(self) -> None:
        registry = build_default_registry()
        model = GraphModel()
        workspace = model.active_workspace
        image_ref = format_staged_artifact_ref("pending_excalidraw_image")
        preview_ref = format_staged_artifact_ref("pending_excalidraw_preview")
        managed_ref = format_managed_artifact_ref("existing_excalidraw_image")
        excalidraw_state = {
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
                },
                {
                    "id": "file-existing",
                    "mimeType": "image/png",
                    "artifact_ref": managed_ref,
                },
            ],
            "appState": {"viewBackgroundColor": "#ffffff"},
        }
        preview_payload = {
            "artifact_ref": preview_ref,
            "mime_type": "image/png",
        }
        node = model.validated_mutations(workspace.workspace_id, registry).add_node(
            type_id=EXCALIDRAW_BOARD_TYPE_ID,
            title="Excalidraw Board",
            x=25.0,
            y=45.0,
            properties={
                EXCALIDRAW_STATE_PROPERTY: excalidraw_state,
                EXCALIDRAW_PREVIEW_REF_PROPERTY: preview_payload,
            },
        )

        serializer = JsonProjectSerializer(registry)
        document = serializer.to_persistent_document(model.project)
        refs = collect_project_artifact_references(document)

        self.assertEqual(refs.managed_ids, frozenset({"existing_excalidraw_image"}))
        self.assertEqual(
            refs.staged_ids,
            frozenset({"pending_excalidraw_image", "pending_excalidraw_preview"}),
        )

        rewritten = rewrite_project_artifact_refs(
            document,
            {
                image_ref: format_managed_artifact_ref("pending_excalidraw_image"),
                preview_ref: format_managed_artifact_ref("pending_excalidraw_preview"),
            },
        )
        workspace_doc = next(ws for ws in rewritten["workspaces"] if ws["workspace_id"] == workspace.workspace_id)
        node_doc = next(item for item in workspace_doc["nodes"] if item["node_id"] == node.node_id)
        properties = node_doc["properties"]
        serialized_properties = json.dumps(properties, sort_keys=True)

        self.assertEqual(
            properties[EXCALIDRAW_STATE_PROPERTY]["files"][0]["artifact_ref"],
            format_managed_artifact_ref("pending_excalidraw_image"),
        )
        self.assertEqual(
            properties[EXCALIDRAW_STATE_PROPERTY]["files"][1]["artifact_ref"],
            managed_ref,
        )
        self.assertEqual(
            properties[EXCALIDRAW_PREVIEW_REF_PROPERTY]["artifact_ref"],
            format_managed_artifact_ref("pending_excalidraw_preview"),
        )
        self.assertNotIn("data:image", serialized_properties)
        self.assertNotIn("base64", serialized_properties)
