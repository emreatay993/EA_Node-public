from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import generate_agent_route_index as agent_indexer
from scripts import generate_qml_navigation_index as indexer
from scripts import nav


REPO_ROOT = Path(__file__).resolve().parents[1]


class QmlNavigationIndexTests(unittest.TestCase):
    def test_live_repository_qml_routes_have_exact_bounded_owners(self) -> None:
        qml_entries = json.loads(
            (REPO_ROOT / "docs" / "qml_navigation_index.json").read_text(
                encoding="utf-8"
            )
        )["entries"]
        route_index = agent_indexer.build_index_data(REPO_ROOT)
        routes = [
            agent_indexer.route_entry_to_dict(entry) for entry in route_index.entries
        ]
        map_entries = [entry for entry in routes if entry["kind"] != "qml_component"]
        qml_routes = [entry for entry in routes if entry["kind"] == "qml_component"]

        self.assertEqual(len(qml_entries), 180)
        self.assertEqual(len(qml_routes), 180)
        self.assertEqual(len({entry["path"] for entry in qml_entries}), 180)
        self.assertEqual(len({entry["component_name"] for entry in qml_entries}), 180)

        qml_route_by_path = {
            entry["qml_candidates"][0]: entry
            for entry in qml_routes
            if entry["qml_candidates"]
        }
        for component in qml_entries:
            component_name = component["component_name"]
            with self.subTest(component=component_name):
                path = component["path"]
                qml_route = qml_route_by_path[path]
                owners = nav.find_owner_routes(routes, component_name)
                self.assertTrue(owners)
                self.assertTrue(all(owner["kind"] != "qml_component" for owner in owners))

                explicit_owners = [
                    entry
                    for entry in map_entries
                    if any(
                        str(candidate).replace("\\", "/").rstrip("/") == path
                        for field in (
                            "source_candidates",
                            "qml_candidates",
                            "start_here",
                        )
                        for candidate in entry[field]
                    )
                ]
                primary_owner = owners[0]
                if explicit_owners:
                    self.assertIn(
                        primary_owner["map_path"],
                        {entry["map_path"] for entry in explicit_owners},
                    )
                    feature_owners = [
                        entry for entry in explicit_owners if entry["kind"] == "feature_route"
                    ]
                    if feature_owners:
                        self.assertEqual(primary_owner["kind"], "feature_route")
                else:
                    self.assertEqual(primary_owner["map_path"], qml_route["map_path"])

                capsules = nav.build_owner_capsules(owners, component_name)
                self.assertTrue(capsules)
                self.assertEqual(capsules[0].get("path"), path)

                focused_test = capsules[0].get("focused_test")
                if focused_test:
                    self.assertTrue((REPO_ROOT / focused_test).is_file(), focused_test)
                    self.assertTrue(
                        focused_test in primary_owner["test_candidates"]
                        or focused_test in nav._verification_test_paths(primary_owner)
                    )
                if focused_test == "tests/test_script_editor_dock.py":
                    self.assertIn(
                        component_name,
                        {"ScriptCodeEditorPane", "ScriptEditorOverlay"},
                    )

                distinct_paths = {
                    str(value)
                    for capsule in capsules
                    for field in ("owner_map", "path", "focused_test")
                    if (value := capsule.get(field))
                }
                for capsule in capsules:
                    distinct_paths.update(capsule.get("do_not_start_here", []))
                self.assertLessEqual(len(distinct_paths), nav.MAX_DEFAULT_PATHS)

                for as_json in (False, True):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        nav._emit_owner_capsules(
                            component_name, capsules, as_json
                        )
                    self.assertLessEqual(
                        len(captured.getvalue().encode("utf-8")),
                        nav.MAX_DEFAULT_OUTPUT_BYTES,
                    )

    def test_parse_qml_file_extracts_navigation_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            qml_path = repo_root / "ea_node_editor" / "ui_qml" / "components" / "graph" / "Widget.qml"
            delegate_path = (
                repo_root
                / "ea_node_editor"
                / "ui_qml"
                / "components"
                / "graph_canvas"
                / "GraphCanvasNodeDelegate.qml"
            )
            qml_path.parent.mkdir(parents=True)
            delegate_path.parent.mkdir(parents=True)
            qml_path.write_text(
                "\n".join(
                    [
                        "import QtQuick 2.15",
                        "import \"../graph_canvas\" as GraphCanvas",
                        "",
                        "Item {",
                        "    id: root",
                        "    objectName: \"widgetRoot\"",
                        "    property var sceneModel: []",
                        "    readonly property int visibleCount: nodeRepeater.count",
                        "    signal activated(string nodeId)",
                        "    visible: visibleCount > 0",
                        "    onWidthChanged: hostForNodeId(\"width\")",
                        "    Keys.onReturnPressed: activated(\"keyboard\")",
                        "",
                        "    function hostForNodeId(nodeId) { return null }",
                        "",
                        "    Connections {",
                        "        target: bridgeTarget",
                        "        function onSelectionChanged() { root.activated(\"selection\") }",
                        "    }",
                        "",
                        "    Repeater {",
                        "        id: nodeRepeater",
                        "        model: root.sceneModel",
                        "        delegate: GraphCanvas.GraphCanvasNodeDelegate {}",
                        "    }",
                        "",
                        "    Loader {",
                        "        sourceComponent: detailComponent",
                        "    }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            delegate_path.write_text("Item {}\n", encoding="utf-8")

            entry = indexer.parse_qml_file(qml_path, repo_root)
            index_data = indexer.build_index_data(repo_root)
            indexed_entry = next(item for item in index_data.entries if item.component_name == "Widget")

        self.assertEqual(entry.component_name, "Widget")
        self.assertEqual(entry.path, "ea_node_editor/ui_qml/components/graph/Widget.qml")
        self.assertEqual(
            entry.aliases,
            (
                "Widget",
                "Widget.qml",
                "ea_node_editor/ui_qml/components/graph/Widget.qml",
                "ea_node_editor\\ui_qml\\components\\graph\\Widget.qml",
            ),
        )
        self.assertEqual(entry.root_component, "Item")
        self.assertIn("QtQuick 2.15", entry.imports)
        self.assertIn(indexer.SymbolRef("root", 5), entry.ids)
        self.assertIn(indexer.SymbolRef("widgetRoot", 6), entry.object_names)
        self.assertIn(indexer.TypedSymbolRef("var", "sceneModel", 7), entry.properties)
        self.assertIn(indexer.TypedSymbolRef("int", "visibleCount", 8), entry.properties)
        self.assertIn(indexer.SymbolRef("activated", 9), entry.signals)
        self.assertIn(indexer.DetailRef("binding", "visible", 10, "visibleCount > 0"), entry.property_bindings)
        self.assertIn(indexer.DetailRef("handler", "onWidthChanged", 11), entry.signal_handlers)
        self.assertIn(indexer.DetailRef("handler", "Keys.onReturnPressed", 12), entry.signal_handlers)
        self.assertIn(indexer.SymbolRef("hostForNodeId", 14), entry.functions)
        self.assertIn(indexer.DetailRef("target", "bridgeTarget", 17, "target: bridgeTarget"), entry.connections)
        self.assertIn(indexer.SymbolRef("Repeater", 21), entry.instantiated_components)
        self.assertIn(indexer.SymbolRef("Loader", 27), entry.instantiated_components)
        self.assertTrue(any(ref.kind == "model" and "root.sceneModel" in ref.detail for ref in entry.dynamic_refs))
        self.assertTrue(any(ref.kind == "delegate" and ref.detail == "GraphCanvas.GraphCanvasNodeDelegate" for ref in entry.dynamic_refs))
        self.assertTrue(any(ref.kind == "sourceComponent" for ref in entry.dynamic_refs))
        self.assertIn(
            indexer.DetailRef(
                "localComponent",
                "GraphCanvas.GraphCanvasNodeDelegate",
                24,
                "ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml",
            ),
            indexed_entry.local_component_refs,
        )

    def test_build_index_ignores_dependency_and_cache_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            live_path = repo_root / "ea_node_editor" / "ui_qml" / "Live.qml"
            cache_path = repo_root / "ea_node_editor" / "ui_qml" / "__pycache__" / "Cached.qml"
            vendor_path = repo_root / "ea_node_editor" / "ui_qml" / "node_modules" / "Vendor.qml"
            live_path.parent.mkdir(parents=True)
            cache_path.parent.mkdir(parents=True)
            vendor_path.parent.mkdir(parents=True)
            live_path.write_text("Item {}\n", encoding="utf-8")
            cache_path.write_text("Item {}\n", encoding="utf-8")
            vendor_path.write_text("Item {}\n", encoding="utf-8")

            index_data = indexer.build_index_data(repo_root)

        self.assertEqual(len(index_data.entries), 1)
        self.assertEqual(index_data.entries[0].path, "ea_node_editor/ui_qml/Live.qml")

    def test_main_writes_index_and_check_detects_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            output_path = repo_root / "docs" / "qml_navigation_index.md"
            json_path = repo_root / "docs" / "qml_navigation_index.json"
            qml_root = repo_root / "qml"
            qml_root.mkdir()
            (qml_root / "Root.qml").write_text(
                "\n".join(
                    [
                        "import QtQuick 2.15",
                        "Item {",
                        "    id: root",
                        "    objectName: \"rootObject\"",
                        "    property string title: \"\"",
                        "    color: title",
                        "    signal accepted()",
                        "    onVisibleChanged: refresh()",
                        "    function refresh() { return true }",
                        "    Loader {",
                        '        source: "Pane.qml"',
                        "        sourceComponent: paneComponent",
                        "    }",
                        "    Rectangle {",
                        "        color: root.title",
                        "    }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            captured = io.StringIO()
            with redirect_stdout(captured):
                write_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--json-output",
                        str(json_path),
                        "--qml-root",
                        "qml",
                    ]
                )
            self.assertEqual(write_code, 0)
            self.assertIn("Wrote docs/qml_navigation_index.md", captured.getvalue())
            markdown = output_path.read_text(encoding="utf-8")
            json_text = json_path.read_text(encoding="utf-8")
            json_payload = json.loads(json_text)
            self.assertIn("### `Root.qml`", markdown)
            self.assertIn(
                "- Agent route aliases: `Root`, `Root.qml`, `qml/Root.qml`, `qml\\Root.qml`",
                markdown,
            )
            self.assertEqual(json_payload["version"], 3)
            self.assertEqual(json_payload["summary"]["qml_files"], 1)
            self.assertNotIn("lines", json_payload["summary"])
            self.assertEqual(json_payload["summary"]["signal_handlers"], 1)
            self.assertEqual(json_payload["summary"]["property_bindings"], 2)
            self.assertEqual(json_payload["entries"][0]["path"], "qml/Root.qml")
            self.assertEqual(
                json_payload["entries"][0]["aliases"],
                ["Root", "Root.qml", "qml/Root.qml", "qml\\Root.qml"],
            )
            self.assertEqual(json_payload["entries"][0]["imports"], ["QtQuick 2.15"])
            self.assertIn({"name": "root"}, json_payload["entries"][0]["ids"])
            self.assertIn(
                {"name": "rootObject"},
                json_payload["entries"][0]["object_names"],
            )
            self.assertIn(
                {"kind": "string", "name": "title"},
                json_payload["entries"][0]["properties"],
            )
            self.assertIn(
                {"kind": "binding", "name": "color", "targets": ["title"]},
                json_payload["entries"][0]["property_bindings"],
            )
            self.assertIn(
                {
                    "kind": "binding",
                    "name": "color",
                    "targets": ["root.title"],
                },
                json_payload["entries"][0]["property_bindings"],
            )
            self.assertIn({"name": "accepted"}, json_payload["entries"][0]["signals"])
            self.assertIn(
                {"kind": "handler", "name": "onVisibleChanged"},
                json_payload["entries"][0]["signal_handlers"],
            )
            self.assertIn({"name": "refresh"}, json_payload["entries"][0]["functions"])
            self.assertIn(
                {"kind": "source", "targets": ["Pane.qml"]},
                json_payload["entries"][0]["dynamic_refs"],
            )
            self.assertIn(
                {"kind": "sourceComponent", "targets": ["paneComponent"]},
                json_payload["entries"][0]["dynamic_refs"],
            )
            symbol_anchors = json_payload["entries"][0]["symbol_anchors"]
            self.assertIn(
                {
                    "anchor": "RootPropertyTitle",
                    "kind": "property",
                    "name": "title",
                    "detail": "string",
                },
                symbol_anchors,
            )
            self.assertIn(
                {
                    "anchor": "RootHandlerOnVisibleChanged",
                    "kind": "handler",
                    "name": "onVisibleChanged",
                },
                symbol_anchors,
            )
            self.assertNotIn("line_count", json_payload["entries"][0])
            self.assertNotIn("(L", markdown)

            with redirect_stdout(io.StringIO()):
                check_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--json-output",
                        str(json_path),
                        "--qml-root",
                        "qml",
                        "--check",
                    ]
                )
            self.assertEqual(check_code, 0)

            output_path.write_text("stale\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                stale_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--json-output",
                        str(json_path),
                        "--qml-root",
                        "qml",
                        "--check",
                    ]
                )
            self.assertEqual(stale_code, 1)

            output_path.write_text(markdown, encoding="utf-8")
            json_path.write_text("stale\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                stale_json_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--json-output",
                        str(json_path),
                        "--qml-root",
                        "qml",
                        "--check",
                    ]
                )
            self.assertEqual(stale_json_code, 1)

    def test_render_is_invariant_to_comments_blank_lines_and_non_symbol_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            qml_root = repo_root / "qml"
            qml_root.mkdir()
            (qml_root / "Foo.qml").write_text(
                "import QtQuick 2.15\nItem {}\n",
                encoding="utf-8",
            )
            qml_path = qml_root / "Stable.qml"
            qml_path.write_text(
                "\n".join(
                    [
                        "import QtQuick 2.15",
                        "Item {",
                        "    id: root",
                        '    property string label: "before"',
                        '    color: "red"',
                        '    description: "2.15"',
                        '    Repeater { model: ["Foo"] }',
                        '    function refresh() { return "before" }',
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            roots = (Path("qml"),)
            before_data = indexer.build_index_data(repo_root, qml_roots=roots)
            before_markdown = indexer.render_markdown(before_data, qml_roots=roots)
            before_json = indexer.render_json(before_data, qml_roots=roots)
            stable_entry = next(
                entry for entry in before_data.entries if entry.component_name == "Stable"
            )
            self.assertFalse(stable_entry.local_component_refs)

            qml_path.write_text(
                "\n".join(
                    [
                        "// leading comment",
                        "",
                        "",
                        "import QtQuick 2.15",
                        "Item {",
                        "    id: root",
                        '    property string label: "after"',
                        '    color: "blue"',
                        '    description: "2.16"',
                        '    Repeater { model: ["Bar"] }',
                        '    function refresh() { return "after" }',
                        "}",
                    ]
                ),
                encoding="utf-8",
            )
            after_data = indexer.build_index_data(repo_root, qml_roots=roots)

        self.assertEqual(
            before_markdown,
            indexer.render_markdown(after_data, qml_roots=roots),
        )
        self.assertEqual(before_json, indexer.render_json(after_data, qml_roots=roots))


if __name__ == "__main__":
    unittest.main()
