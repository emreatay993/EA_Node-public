from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.ui.shell.controllers.workspace_view_nav_ops import WorkspaceViewNavOps
from ea_node_editor.ui.shell.inspector_projection import build_selected_node_property_items
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from tests.passive_property_editor_fixtures import (
    PASSIVE_EDITOR_FIXTURE_TYPE_ID,
    register_passive_editor_fixture,
)


class PassivePropertyEditorModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_registry()
        register_passive_editor_fixture(self.registry)
        self.model = GraphModel()
        self.workspace_id = self.model.active_workspace.workspace_id
        self.scene = GraphSceneBridge()
        self.scene.set_workspace(self.model, self.registry, self.workspace_id)

    def _property_items_for_type(self, type_id: str) -> dict[str, dict[str, object]]:
        node_id = self.scene.add_node_from_type(type_id, 0.0, 0.0)
        workspace = self.model.project.workspaces[self.workspace_id]
        node = workspace.nodes[node_id]
        spec = self.registry.get_spec(type_id)
        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
        )
        return {str(item["key"]): item for item in items}

    def _property_items_for_node(
        self,
        node_id: str,
        *,
        project_path: str | None = None,
    ) -> dict[str, dict[str, object]]:
        workspace = self.model.project.workspaces[self.workspace_id]
        node = workspace.nodes[node_id]
        spec = self.registry.get_spec(node.type_id)
        items = build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
            workspace_nodes=workspace.nodes,
            workspace_edges=workspace.edges,
            project_path=project_path,
        )
        return {str(item["key"]): item for item in items}

    def test_sdk_driven_editor_modes_follow_property_metadata_not_property_keys(self) -> None:
        items = self._property_items_for_type(PASSIVE_EDITOR_FIXTURE_TYPE_ID)

        self.assertEqual(items["notes_blob"]["editor_mode"], "textarea")
        self.assertEqual(items["media_ref"]["editor_mode"], "path")
        self.assertEqual(items["accent_color"]["editor_mode"], "color")
        self.assertEqual(items["caption"]["editor_mode"], "text")

    def test_existing_logger_property_editor_modes_remain_text_and_enum(self) -> None:
        items = self._property_items_for_type("core.logger")

        self.assertEqual(items["message"]["editor_mode"], "text")
        self.assertEqual(items["level"]["editor_mode"], "enum")

    def test_planning_family_long_form_fields_use_textarea(self) -> None:
        task_items = self._property_items_for_type("passive.planning.task_card")
        risk_items = self._property_items_for_type("passive.planning.risk_card")
        decision_items = self._property_items_for_type("passive.planning.decision_card")

        self.assertEqual(task_items["body"]["editor_mode"], "textarea")
        self.assertEqual(risk_items["body"]["editor_mode"], "textarea")
        self.assertEqual(risk_items["mitigation"]["editor_mode"], "textarea")
        self.assertEqual(decision_items["body"]["editor_mode"], "textarea")
        self.assertEqual(decision_items["outcome"]["editor_mode"], "textarea")
        self.assertEqual(task_items["owner"]["editor_mode"], "text")
        self.assertEqual(task_items["status"]["editor_mode"], "enum")

    def test_annotation_family_uses_textarea_only_for_body_fields(self) -> None:
        sticky_items = self._property_items_for_type("passive.annotation.sticky_note")
        callout_items = self._property_items_for_type("passive.annotation.callout")
        section_items = self._property_items_for_type("passive.annotation.section_header")
        text_items = self._property_items_for_type("passive.annotation.text")

        self.assertEqual(sticky_items["body"]["editor_mode"], "textarea")
        self.assertEqual(callout_items["body"]["editor_mode"], "textarea")
        self.assertEqual(text_items["text"]["editor_mode"], "textarea")
        self.assertEqual(text_items["text_color"]["editor_mode"], "color")
        self.assertEqual(text_items["background_color"]["editor_mode"], "color")
        self.assertEqual(sticky_items["title"]["editor_mode"], "text")
        self.assertEqual(section_items["title"]["editor_mode"], "text")
        self.assertEqual(section_items["subtitle"]["editor_mode"], "text")

    def test_flowchart_family_exposes_text_title_editor(self) -> None:
        decision_items = self._property_items_for_type("passive.flowchart.decision")
        database_items = self._property_items_for_type("passive.flowchart.database")
        decision_spec = self.registry.get_spec("passive.flowchart.decision")
        decision_body = next(prop for prop in decision_spec.properties if prop.key == "body")

        self.assertEqual(decision_items["title"]["editor_mode"], "text")
        self.assertEqual(decision_items["title"]["value"], "Decision")
        self.assertEqual(decision_items["body"]["editor_mode"], "textarea")
        self.assertEqual(decision_items["body"]["value"], "Decision")
        self.assertEqual(database_items["title"]["editor_mode"], "text")
        self.assertEqual(database_items["title"]["value"], "Database")
        self.assertEqual(database_items["body"]["editor_mode"], "textarea")
        self.assertEqual(database_items["body"]["value"], "Database")
        self.assertTrue(WorkspaceViewNavOps._property_is_content_searchable(decision_body))

    def test_tabular_data_source_uses_editable_combo_with_scanned_objects(self) -> None:
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl is not installed")
        if self.registry.spec_or_none("tabular.input") is None:
            self.skipTest("tabular.input add-on is not registered in the default registry")

        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "book.xlsx"
            workbook = openpyxl.Workbook()
            workbook.active.title = "First"
            workbook["First"].append(["name", "value"])
            second = workbook.create_sheet("Second")
            second.append(["name", "value"])
            workbook.save(source)

            node_id = self.scene.add_node_from_type("tabular.input", 0.0, 0.0)
            self.scene.set_node_property(node_id, "path", str(source))
            items = self._property_items_for_node(node_id)

        self.assertEqual(items["selected_object"]["editor_mode"], "editable_combo")
        self.assertEqual(items["selected_object"]["enum_values"], ["First", "Second"])
        self.assertEqual(items["selected_object"].get("placeholder_text"), "Select a sheet, key, or dataset")

    def test_tabular_data_source_selector_remains_editable_without_a_path(self) -> None:
        if self.registry.spec_or_none("tabular.input") is None:
            self.skipTest("tabular.input add-on is not registered in the default registry")

        node_id = self.scene.add_node_from_type("tabular.input", 0.0, 0.0)
        items = self._property_items_for_node(node_id)

        self.assertEqual(items["selected_object"]["editor_mode"], "editable_combo")
        self.assertEqual(items["selected_object"]["enum_values"], [])
        self.assertEqual(items["selected_object"].get("placeholder_text"), "Choose a tabular data file first")


if __name__ == "__main__":
    unittest.main()
