from __future__ import annotations

import json

from ea_node_editor.custom_workflows.codec import (
    normalize_custom_workflow_metadata,
    upsert_custom_workflow_definition,
)
from ea_node_editor.custom_workflows.global_store import (
    load_global_custom_workflow_definitions,
    save_global_custom_workflow_definitions,
)
from ea_node_editor.runtime_contracts import (
    GRAPH_DATA_TYPE_ID,
    JSON_DATA_TYPE_ID,
    STRING_DATA_TYPE_ID,
)
from tests.workspace_controller_support import *  # noqa: F401,F403


class WorkflowLibraryControllerPublishTests(WorkspaceDirectControllerTestBase):
    def test_legacy_bad_preview_types_are_omitted_but_new_publication_rejects_them(self) -> None:
        fragment = self._valid_fragment_payload()
        base_port = {"key": "value", "direction": "out", "kind": "data"}
        for raw_type in (None, "", " ", 4, []):
            with self.subTest(data_type=raw_type):
                malformed = {**base_port, "data_type": raw_type}
                if raw_type is None:
                    malformed.pop("data_type")
                valid = {
                    **base_port,
                    "key": "valid",
                    "data_type": STRING_DATA_TYPE_ID,
                    "accepted_data_types": [STRING_DATA_TYPE_ID, JSON_DATA_TYPE_ID, JSON_DATA_TYPE_ID, None],
                }
                definitions = normalize_custom_workflow_metadata([
                    {"workflow_id": "wf_test", "name": "Retained", "ports": [malformed, valid], "fragment": fragment}
                ])
                self.assertEqual(len(definitions), 1)
                self.assertEqual(len(definitions[0]["fragment"]["nodes"]), 1)
                self.assertEqual([port["key"] for port in definitions[0]["ports"]], ["valid"])
                self.assertEqual(definitions[0]["ports"][0]["accepted_data_types"], [JSON_DATA_TYPE_ID])
                with self.assertRaisesRegex(ValueError, "requires a non-empty data_type string"):
                    upsert_custom_workflow_definition([], name="Invalid", ports=[malformed], fragment=fragment)

    def test_publication_type_error_leaves_definitions_and_signals_unchanged(self) -> None:
        host = _PublishHostStub()
        controller = compose_workspace_controllers(host).workflow
        shell = host.model.add_node(
            host.workspace_manager.active_workspace_id(),
            type_id="core.subnode", title="Shell", x=0.0, y=0.0,
            properties=host.registry.default_properties("core.subnode"),
        )
        snapshot = {
            "fragment": self._valid_fragment_payload(),
            "ports": [{"key": "bad", "direction": "out", "kind": "data"}],
        }
        with patch(
            "ea_node_editor.ui.shell.controllers.workflow_library_controller.build_subnode_custom_workflow_snapshot_data",
            return_value=snapshot,
        ):
            result = controller.publish_custom_workflow_from_shell(shell.node_id)
        self.assertFalse(result.ok)
        self.assertIn("data_type", result.message)
        self.assertEqual(host.model.project.metadata.get("custom_workflows", []), [])
        self.assertEqual(host.project_meta_changed.calls, 0)
        self.assertEqual(host.node_library_changed.calls, 0)

    def test_publish_custom_workflow_from_selected_subnode_persists_snapshot(
        self,
    ) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.workflow
        workspace_id = host.workspace_manager.active_workspace_id()

        shell = host.model.add_node(
            workspace_id,
            type_id="core.subnode",
            title="Reusable Shell",
            x=120.0,
            y=80.0,
            properties=host.registry.default_properties("core.subnode"),
            exposed_ports={},
        )
        pin = host.model.add_node(
            workspace_id,
            type_id="core.subnode_output",
            title="Subnode Output",
            x=260.0,
            y=120.0,
            properties=host.registry.default_properties("core.subnode_output"),
            exposed_ports={"pin": True},
        )
        pin.parent_node_id = shell.node_id
        pin.properties["label"] = "Payload Out"
        pin.properties["kind"] = "data"
        pin.properties["data_type"] = GRAPH_DATA_TYPE_ID
        pin.properties["accepted_data_types"] = [STRING_DATA_TYPE_ID]
        pin.properties["data_access"] = "tree"
        shell.exposed_ports[pin.node_id] = True
        host.scene._selected_node_id = shell.node_id

        published = controller.publish_custom_workflow_from_selected_subnode()

        self.assertTrue(published.ok)
        self.assertTrue(published.payload)
        definitions = host.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        definition = definitions[0]
        self.assertEqual(definition["name"], "Reusable Shell")
        self.assertEqual(definition["workflow_id"], f"wf_shell_{shell.node_id}")
        self.assertEqual(definition["revision"], 1)
        self.assertNotIn("source_shell_ref_id", definition)
        self.assertEqual(definition["ports"][0]["direction"], "out")
        self.assertEqual(definition["ports"][0]["kind"], "data")
        self.assertEqual(
            definition["ports"][0]["data_type"],
            GRAPH_DATA_TYPE_ID,
        )
        self.assertEqual(
            definition["ports"][0]["accepted_data_types"],
            [STRING_DATA_TYPE_ID],
        )
        self.assertEqual(definition["ports"][0]["data_access"], "tree")
        self.assertEqual(
            definition["fragment"]["kind"], "ea-node-editor/graph-fragment"
        )
        self.assertEqual(host.project_meta_changed.calls, 1)
        self.assertEqual(host.node_library_changed.calls, 1)
        library_items = controller.custom_workflow_library_items()
        self.assertEqual(len(library_items), 1)
        self.assertEqual(
            library_items[0]["type_id"], f"custom_workflow:wf_shell_{shell.node_id}"
        )

    def test_publish_custom_workflow_from_current_scope_updates_revision(self) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.workflow
        workspace_id = host.workspace_manager.active_workspace_id()

        shell = host.model.add_node(
            workspace_id,
            type_id="core.subnode",
            title="Scoped Shell",
            x=80.0,
            y=40.0,
            properties=host.registry.default_properties("core.subnode"),
            exposed_ports={},
        )
        pin = host.model.add_node(
            workspace_id,
            type_id="core.subnode_input",
            title="Subnode Input",
            x=30.0,
            y=100.0,
            properties=host.registry.default_properties("core.subnode_input"),
            exposed_ports={"pin": True},
        )
        pin.parent_node_id = shell.node_id
        pin.properties["label"] = "Payload A"
        shell.exposed_ports[pin.node_id] = True
        host.scene.active_scope_path = [shell.node_id]

        first_publish = controller.publish_custom_workflow_from_current_scope()
        self.assertTrue(first_publish.ok)

        pin.properties["label"] = "Payload B"
        second_publish = controller.publish_custom_workflow_from_current_scope()
        self.assertTrue(second_publish.ok)

        definitions = host.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        definition = definitions[0]
        self.assertEqual(definition["name"], "Scoped Shell")
        self.assertEqual(definition["revision"], 2)
        self.assertEqual(definition["ports"][0]["label"], "Payload B")


class WorkspacePackageIOControllerTests(WorkspaceDirectControllerTestBase):
    def test_export_custom_workflow_writes_eawf_payload(self) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.package
        definitions = [
            {
                "workflow_id": "wf_export",
                "name": "Workflow Export",
                "description": "Export test",
                "revision": 3,
                "ports": [
                    {
                        "key": "value",
                        "label": "Value",
                        "direction": "out",
                        "kind": "data",
                        "data_type": GRAPH_DATA_TYPE_ID,
                        "accepted_data_types": [],
                        "data_access": "item",
                    }
                ],
                "fragment": self._valid_fragment_payload(),
            }
        ]
        host.model.project.metadata["custom_workflows"] = definitions
        controller.prompt_custom_workflow_export_definition = lambda items: items[0]  # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "workflow_export"
            with (
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(target_path), "Custom Workflow (*.cxwf)"),
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
                patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
            ):
                controller.export_custom_workflow()

            saved_path = target_path.with_suffix(".cxwf")
            self.assertTrue(saved_path.exists())
            imported = import_custom_workflow_file(saved_path)

        self.assertEqual(imported["workflow_id"], "wf_export")
        self.assertEqual(imported["name"], "Workflow Export")
        self.assertEqual(imported["revision"], 3)
        self.assertEqual(imported["ports"][0]["label"], "Value")
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)

    def test_custom_workflow_export_label_hides_internal_workflow_id(self) -> None:
        label = WorkspacePackageIOController.custom_workflow_export_label(
            {
                "workflow_id": "wf_export",
                "name": "Workflow Export",
                "revision": 3,
            }
        )
        self.assertEqual(label, "Workflow Export (rev 3)")
        self.assertNotIn("wf_export", label)

    def test_import_custom_workflow_replaces_existing_definition_and_emits_signals(
        self,
    ) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.package
        host.model.project.metadata["custom_workflows"] = [
            {
                "workflow_id": "wf_sync",
                "name": "Old Name",
                "description": "old",
                "revision": 1,
                "ports": [
                    {
                        "key": "value",
                        "label": "Old",
                        "direction": "out",
                        "kind": "data",
                        "data_type": GRAPH_DATA_TYPE_ID,
                        "accepted_data_types": [],
                        "data_access": "item",
                    }
                ],
                "fragment": self._valid_fragment_payload(),
            }
        ]
        imported_definition = {
            "workflow_id": "wf_sync",
            "name": "Imported Name",
            "description": "new",
            "revision": 7,
            "ports": [
                {
                    "key": "payload",
                    "label": "Payload",
                    "direction": "in",
                    "kind": "data",
                    "data_type": JSON_DATA_TYPE_ID,
                    "accepted_data_types": [],
                    "data_access": "item",
                }
            ],
            "fragment": self._valid_fragment_payload(),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            import_path = export_custom_workflow_file(
                imported_definition, Path(temp_dir) / "import_target"
            )
            with (
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                    return_value=(str(import_path), "Custom Workflow (*.cxwf)"),
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
                patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
            ):
                controller.import_custom_workflow()

        definitions = host.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        self.assertEqual(
            definitions[0]["workflow_id"], imported_definition["workflow_id"]
        )
        self.assertEqual(definitions[0]["name"], imported_definition["name"])
        self.assertEqual(definitions[0]["revision"], imported_definition["revision"])
        self.assertEqual(definitions[0]["ports"], imported_definition["ports"])
        self.assertEqual(definitions[0]["fragment"]["version"], 2)
        self.assertEqual(host.project_meta_changed.calls, 1)
        self.assertEqual(host.node_library_changed.calls, 1)
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)

    def test_import_legacy_custom_workflow_shows_sorted_report_without_rewriting_source(
        self,
    ) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.package
        legacy_fragment = self._valid_fragment_payload()
        legacy_fragment["version"] = 1
        legacy_document = {
            "kind": "ea-node-editor/custom-workflow",
            "version": 1,
            "workflow": {
                "workflow_id": "wf_legacy_import",
                "name": "Legacy Import",
                "revision": 1,
                "ports": [],
                "fragment": legacy_fragment,
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            import_path = Path(temp_dir) / "legacy.cxwf"
            source_text = json.dumps(legacy_document)
            import_path.write_text(source_text, encoding="utf-8")
            with (
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                    return_value=(str(import_path), "Custom Workflow (*.cxwf)"),
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
                patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
            ):
                controller.import_custom_workflow()

            self.assertEqual(import_path.read_text(encoding="utf-8"), source_text)

        message = str(info_mock.call_args.args[2])
        self.assertIn("Migration report:", message)
        self.assertIn("Migrated custom workflow file version 1 to 2.", message)
        self.assertEqual(host.project_meta_changed.calls, 1)
        self.assertEqual(warning_mock.call_count, 0)


class WorkflowLibraryControllerPersistenceTests(WorkspaceDirectControllerTestBase):
    def test_delete_custom_workflow_removes_definition_and_emits_signals(self) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.workflow
        host.model.project.metadata["custom_workflows"] = [
            {
                "workflow_id": "wf_keep",
                "name": "Keep Me",
                "description": "",
                "revision": 1,
                "ports": [],
                "fragment": self._valid_fragment_payload(),
            },
            {
                "workflow_id": "wf_delete",
                "name": "Delete Me",
                "description": "",
                "revision": 1,
                "ports": [],
                "fragment": self._valid_fragment_payload(),
            },
        ]

        deleted = controller.delete_custom_workflow("wf_delete", "local")

        self.assertTrue(deleted.ok)
        self.assertTrue(deleted.payload)
        definitions = host.model.project.metadata.get("custom_workflows", [])
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["workflow_id"], "wf_keep")
        self.assertEqual(host.project_meta_changed.calls, 1)
        self.assertEqual(host.node_library_changed.calls, 1)

    def test_delete_custom_workflow_returns_false_when_definition_does_not_exist(
        self,
    ) -> None:
        host = _PublishHostStub()
        owners = compose_workspace_controllers(host)
        controller = owners.workflow
        host.model.project.metadata["custom_workflows"] = []

        deleted = controller.delete_custom_workflow("wf_missing", "local")

        self.assertFalse(deleted.ok)
        self.assertFalse(deleted.payload)
        self.assertEqual(host.project_meta_changed.calls, 0)
        self.assertEqual(host.node_library_changed.calls, 0)

    def test_set_custom_workflow_scope_local_to_global_persists_across_controllers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            global_store_path = Path(temp_dir) / "custom_workflows_global.json"
            with patch(
                "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
                return_value=global_store_path,
            ):
                host = _PublishHostStub()
                owners = compose_workspace_controllers(host)
                controller = owners.workflow
                host.model.project.metadata["custom_workflows"] = [
                    {
                        "workflow_id": "wf_shared",
                        "name": "Shared",
                        "description": "",
                        "revision": 2,
                        "ports": [],
                        "fragment": self._valid_fragment_payload(),
                    }
                ]

                moved = controller.set_custom_workflow_scope("wf_shared", "global")
                self.assertTrue(moved.ok)
                self.assertTrue(moved.payload)
                self.assertEqual(
                    host.model.project.metadata.get("custom_workflows", []), []
                )
                self.assertEqual(host.project_meta_changed.calls, 1)
                self.assertEqual(host.node_library_changed.calls, 1)
                self.assertEqual(len(load_global_custom_workflow_definitions()), 1)

                other_host = _PublishHostStub()
                other_controller = compose_workspace_controllers(other_host).workflow
                shared_items = [
                    item
                    for item in other_controller.custom_workflow_library_items()
                    if item.get("workflow_id") == "wf_shared"
                ]
                self.assertEqual(len(shared_items), 1)
                self.assertEqual(shared_items[0].get("workflow_scope"), "global")

    def test_legacy_global_store_shows_one_report_without_rewriting_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            global_store_path = Path(temp_dir) / "custom_workflows_global.json"
            fragment = self._valid_fragment_payload()
            fragment["version"] = 1
            legacy_store = {
                "kind": "ea-node-editor/custom-workflow-library",
                "version": 1,
                "custom_workflows": [
                    {
                        "workflow_id": "wf_legacy_global",
                        "name": "Legacy Global",
                        "revision": 1,
                        "ports": [],
                        "fragment": fragment,
                    }
                ],
            }
            source_text = json.dumps(legacy_store)
            global_store_path.write_text(source_text, encoding="utf-8")

            with (
                patch(
                    "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
                    return_value=global_store_path,
                ),
                patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
            ):
                host = _PublishHostStub()
                owners = compose_workspace_controllers(host)
                controller = owners.workflow
                first = controller.global_custom_workflow_definitions()
                second = controller.global_custom_workflow_definitions()

            self.assertEqual(
                [item["workflow_id"] for item in first], ["wf_legacy_global"]
            )
            self.assertEqual(second, first)
            self.assertEqual(info_mock.call_count, 1)
            self.assertIn(
                "Migrated global custom workflow store version 1 to 2.",
                str(info_mock.call_args.args[2]),
            )
            self.assertEqual(global_store_path.read_text(encoding="utf-8"), source_text)

    def test_set_custom_workflow_scope_global_to_local_moves_back_to_project_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            global_store_path = Path(temp_dir) / "custom_workflows_global.json"
            global_definition = {
                "workflow_id": "wf_global",
                "name": "Global",
                "description": "",
                "revision": 1,
                "ports": [],
                "fragment": self._valid_fragment_payload(),
            }

            with patch(
                "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
                return_value=global_store_path,
            ):
                save_global_custom_workflow_definitions([global_definition])
                host = _PublishHostStub()
                owners = compose_workspace_controllers(host)
                controller = owners.workflow

                moved = controller.set_custom_workflow_scope("wf_global", "local")
                self.assertTrue(moved.ok)
                self.assertTrue(moved.payload)
                definitions = host.model.project.metadata.get("custom_workflows", [])
                self.assertEqual(len(definitions), 1)
                self.assertEqual(definitions[0]["workflow_id"], "wf_global")
                self.assertEqual(host.project_meta_changed.calls, 1)
                self.assertEqual(host.node_library_changed.calls, 1)
                self.assertEqual(load_global_custom_workflow_definitions(), [])

    def test_global_custom_workflow_store_rejects_raw_list_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            global_store_path = Path(temp_dir) / "custom_workflows_global.json"
            with patch(
                "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
                return_value=global_store_path,
            ):
                global_store_path.write_text(
                    json.dumps(
                        [
                            {
                                "workflow_id": "wf_raw",
                                "name": "Raw",
                                "description": "",
                                "revision": 1,
                                "ports": [],
                                "fragment": self._valid_fragment_payload(),
                            }
                        ]
                    ),
                    encoding="utf-8",
                )

                self.assertEqual(load_global_custom_workflow_definitions(), [])

    def test_delete_custom_workflow_with_global_scope_removes_from_global_store_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            global_store_path = Path(temp_dir) / "custom_workflows_global.json"
            with patch(
                "ea_node_editor.custom_workflows.global_store.global_custom_workflows_path",
                return_value=global_store_path,
            ):
                save_global_custom_workflow_definitions(
                    [
                        {
                            "workflow_id": "wf_global_delete",
                            "name": "Global Delete",
                            "description": "",
                            "revision": 1,
                            "ports": [],
                            "fragment": self._valid_fragment_payload(),
                        }
                    ]
                )
                host = _PublishHostStub()
                owners = compose_workspace_controllers(host)
                controller = owners.workflow

                deleted = controller.delete_custom_workflow(
                    "wf_global_delete", "global"
                )

                self.assertTrue(deleted.ok)
                self.assertTrue(deleted.payload)
                self.assertEqual(load_global_custom_workflow_definitions(), [])
                self.assertEqual(host.project_meta_changed.calls, 0)
                self.assertEqual(host.node_library_changed.calls, 1)
