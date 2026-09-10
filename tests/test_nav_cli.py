from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import generate_agent_route_index as indexer
from scripts import nav


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "tests" / "fixtures" / "nav_owner_corpus.json"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ROUTE_ENTRIES = [
    {
        "route_key": "feature_route:feature-routes-plotter-nodes",
        "kind": "feature_route",
        "title": "Plotter Nodes",
        "map_path": "docs/agent_maps/feature_routes/plotter_nodes.md",
        "source_candidates": ["ea_node_editor/nodes/builtins/plot/generic.py"],
        "test_candidates": ["tests/test_plotter_nodes.py"],
        "qml_candidates": [],
        "keywords": ["plotter", "plot", "nodes"],
        "aliases": ["plotter nodes"],
        "focused_verification": ["pytest tests/test_plotter_nodes.py"],
        "start_here": [
            "ea_node_editor/nodes/builtins/plot/generic.py",
            "tests/test_plotter_nodes.py",
        ],
        "do_not_start_here": ["ea_node_editor/ui_qml/"],
        "section_anchors": ["Plotter Nodes"],
    },
    {
        "route_key": "subsystem:subsystems-graph-domain",
        "kind": "subsystem",
        "title": "Graph Domain",
        "map_path": "docs/agent_maps/subsystems/graph_domain.md",
        "source_candidates": ["ea_node_editor/graph/records.py"],
        "test_candidates": [],
        "qml_candidates": [],
        "keywords": ["graph", "domain", "mutation"],
        "aliases": [],
        "focused_verification": [],
        "start_here": ["ea_node_editor/graph/records.py"],
        "do_not_start_here": [],
        "section_anchors": [],
    },
]

QML_ROUTE_ENTRIES = [
    {
        "route_key": "feature_route:feature-routes-workspace-ui",
        "kind": "feature_route",
        "title": "Workspace UI",
        "map_path": "docs/agent_maps/feature_routes/workspace_ui.md",
        "source_candidates": [
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        ],
        "test_candidates": ["tests/test_quick_insert.py"],
        "qml_candidates": [
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        ],
        "keywords": ["workspace", "library"],
        "aliases": [],
        "focused_verification": ["pytest tests/test_quick_insert.py -q"],
        "start_here": [
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        ],
        "do_not_start_here": [],
        "section_anchors": [],
    },
    {
        "route_key": "qml:connectionquickinsertoverlay",
        "kind": "qml_component",
        "title": "ConnectionQuickInsertOverlay.qml",
        "map_path": "docs/agent_maps/subsystems/qml_shell_and_bridges.md",
        "source_candidates": [
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        ],
        "test_candidates": [],
        "qml_candidates": [
            "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml"
        ],
        "keywords": [
            "connectionquickinsertoverlay",
            "opennodebrowserrequested",
        ],
        "aliases": [],
        "focused_verification": [],
        "start_here": [],
        "do_not_start_here": [],
        "section_anchors": [],
    },
]

QML_ENTRIES = [
    {
        "component_name": "ManagedToolTip",
        "path": "ea_node_editor/ui_qml/components/common/ManagedToolTip.qml",
        "aliases": ["ManagedToolTip", "ManagedToolTip.qml"],
        "root_component": "ToolTip",
        "symbol_anchors": [
            {
                "anchor": "ManagedToolTipPropertyPolicyBridge",
                "kind": "property",
                "name": "policyBridge",
            }
        ],
    },
    {
        "component_name": "ConnectionQuickInsertOverlay",
        "path": "ea_node_editor/ui_qml/components/shell/ConnectionQuickInsertOverlay.qml",
        "aliases": ["ConnectionQuickInsertOverlay", "ConnectionQuickInsertOverlay.qml"],
        "root_component": "Rectangle",
        "signals": [{"name": "openNodeBrowserRequested"}],
        "symbol_anchors": [],
    },
]


class NavSearchTests(unittest.TestCase):
    def test_search_routes_ranks_exact_route_key_first(self) -> None:
        results = nav.search_routes(ROUTE_ENTRIES, "plotter-nodes")
        self.assertTrue(results)
        self.assertEqual(results[0]["route_key"], "feature_route:feature-routes-plotter-nodes")

    def test_search_routes_filters_non_matches(self) -> None:
        self.assertEqual(nav.search_routes(ROUTE_ENTRIES, "nonexistent-xyz"), [])

    def test_search_routes_requires_every_meaningful_query_token(self) -> None:
        self.assertEqual(nav.search_routes(ROUTE_ENTRIES, "plotter mutation"), [])

    def test_short_tokens_remain_meaningful_and_empty_tokens_never_match(self) -> None:
        short_entry = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:short",
            "keywords": ["ui", "io", "id", "qt"],
            "do_not_start_here": [],
        }
        for token in ("ui", "io", "id", "qt"):
            with self.subTest(token=token):
                self.assertEqual(nav.search_routes([short_entry], token), [short_entry])
        self.assertEqual(nav.search_routes([short_entry], "the and"), [])
        self.assertEqual(nav.search_source(["ea_node_editor/a.py"], [], [], "the"), [])

    def test_do_not_start_here_is_not_positive_route_evidence(self) -> None:
        self.assertEqual(nav.search_routes(ROUTE_ENTRIES, "ui"), [])

    def test_search_routes_returns_all_tied_top_owners(self) -> None:
        first = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:first",
            "map_path": "docs/agent_maps/feature_routes/first.md",
            "aliases": ["shared lookup"],
        }
        second = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:second",
            "map_path": "docs/agent_maps/feature_routes/second.md",
            "aliases": ["shared lookup"],
        }
        results = nav.search_routes([first, second], "shared lookup")
        self.assertEqual(
            [item["route_key"] for item in results],
            ["feature_route:first", "feature_route:second"],
        )

    def test_search_routes_skips_qml_kind(self) -> None:
        mixed = [*ROUTE_ENTRIES, {"route_key": "qml:x", "kind": "qml_component", "title": "plotter"}]
        results = nav.search_routes(mixed, "plotter")
        self.assertTrue(all(r.get("kind") != "qml_component" for r in results))

    def test_find_owner_routes_prefers_direct_route_to_inferred_qml_fallback(self) -> None:
        direct = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:direct-control",
            "title": "Direct Control",
            "map_path": "docs/agent_maps/feature_routes/direct_control.md",
            "keywords": ["shared", "control"],
            "aliases": [],
        }
        inferred = {
            **ROUTE_ENTRIES[1],
            "route_key": "subsystem:qml-fallback",
            "title": "QML Fallback",
            "map_path": "docs/agent_maps/subsystems/qml_fallback.md",
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:sharedcontrol",
            "title": "SharedControl.qml",
            "map_path": inferred["map_path"],
            "source_candidates": ["ea_node_editor/ui_qml/SharedControl.qml"],
            "qml_candidates": ["ea_node_editor/ui_qml/SharedControl.qml"],
            "keywords": ["shared", "control"],
        }

        owners = nav.find_owner_routes([direct, inferred, component], "shared control")

        self.assertEqual(owners[0]["map_path"], direct["map_path"])

    def test_exact_route_keeps_qml_evidenced_secondary_not_unrelated_direct(self) -> None:
        path = "ea_node_editor/ui_qml/EvidenceControl.qml"
        primary = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:primary",
            "map_path": "docs/agent_maps/feature_routes/primary.md",
            "aliases": ["shared control"],
        }
        secondary = {
            **ROUTE_ENTRIES[1],
            "route_key": "subsystem:evidenced-secondary",
            "map_path": "docs/agent_maps/subsystems/evidenced_secondary.md",
            "keywords": ["shared", "control"],
            "source_candidates": [path],
            "qml_candidates": [path],
            "start_here": [path],
        }
        unrelated = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:unrelated-direct",
            "map_path": "docs/agent_maps/feature_routes/unrelated_direct.md",
            "keywords": ["shared", "control"],
            "aliases": [],
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:evidencecontrol",
            "title": "EvidenceControl.qml",
            "source_candidates": [path],
            "qml_candidates": [path],
            "keywords": ["shared", "control"],
        }

        owners = nav.find_owner_routes(
            [primary, secondary, unrelated, component], "shared control"
        )

        self.assertEqual(
            [owner["map_path"] for owner in owners],
            [primary["map_path"], secondary["map_path"]],
        )

    def test_find_owner_routes_prefers_explicit_feature_to_inferred_subsystem(self) -> None:
        path = "ea_node_editor/ui_qml/components/graph_canvas/PreferenceFacts.qml"
        feature = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:preference-facts",
            "title": "Preference Facts Recipe",
            "map_path": "docs/agent_maps/feature_routes/preference_facts.md",
            "source_candidates": [path],
            "qml_candidates": [path],
            "keywords": [],
            "aliases": [],
            "start_here": [],
        }
        inferred = {
            **ROUTE_ENTRIES[1],
            "route_key": "subsystem:graph-canvas",
            "title": "Graph Canvas",
            "map_path": "docs/agent_maps/subsystems/graph_canvas.md",
            "start_here": ["PreferenceFacts.qml"],
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:preferencefacts",
            "title": "PreferenceFacts.qml",
            "map_path": inferred["map_path"],
            "source_candidates": [path],
            "qml_candidates": [path],
            "keywords": ["preferencefacts"],
        }

        owners = nav.find_owner_routes([feature, inferred, component], "PreferenceFacts")

        self.assertEqual(owners[0]["map_path"], feature["map_path"])
        self.assertEqual(owners[0]["_nav_evidence_paths"], [path])

    def test_exact_qml_inferred_owner_outranks_broad_direct_feature(self) -> None:
        path = "ea_node_editor/ui_qml/components/graph_canvas/ViewportController.qml"
        broad_feature = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:broad-viewport",
            "title": "Broad Viewport Feature",
            "map_path": "docs/agent_maps/feature_routes/broad_viewport.md",
            "keywords": ["viewport", "controller"],
            "aliases": [],
        }
        inferred = {
            **ROUTE_ENTRIES[1],
            "route_key": "subsystem:graph-canvas",
            "title": "Graph Canvas",
            "map_path": "docs/agent_maps/subsystems/graph_canvas.md",
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:viewportcontroller",
            "title": "ViewportController.qml",
            "map_path": inferred["map_path"],
            "source_candidates": [path],
            "qml_candidates": [path],
            "keywords": ["viewportcontroller"],
        }

        owners = nav.find_owner_routes(
            [broad_feature, inferred, component], "ViewportController"
        )
        capsule = nav.build_owner_capsules(owners, "ViewportController")[0]

        self.assertEqual(owners[0]["map_path"], inferred["map_path"])
        self.assertTrue(owners[0]["_nav_exact_qml_match"])
        self.assertEqual(capsule["path"], path)

    def test_find_owner_routes_is_deterministic_for_semantic_ties(self) -> None:
        second = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:second",
            "map_path": "docs/agent_maps/feature_routes/second.md",
            "aliases": ["shared lookup"],
        }
        first = {
            **second,
            "route_key": "feature_route:first",
            "map_path": "docs/agent_maps/feature_routes/first.md",
        }

        owners = nav.find_owner_routes([second, first], "shared lookup")

        self.assertEqual(
            [owner["route_key"] for owner in owners],
            ["feature_route:first", "feature_route:second"],
        )

    def test_find_owner_routes_handles_no_match_short_tokens_and_avoid_paths(self) -> None:
        short_entry = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:short",
            "keywords": ["ui", "io", "id", "qt"],
            "aliases": [],
            "do_not_start_here": ["ea_node_editor/forbidden/only_marker.py"],
        }
        for token in ("ui", "io", "id", "qt"):
            with self.subTest(token=token):
                self.assertEqual(
                    nav.find_owner_routes([short_entry], token)[0],
                    {
                        **short_entry,
                        "_nav_direct_match": True,
                        "_nav_exact_qml_match": False,
                        "_nav_confidence": "advisory",
                    },
                )
        self.assertEqual(nav.find_owner_routes([short_entry], "only marker"), [])
        self.assertEqual(nav.find_owner_routes([short_entry], "the and"), [])
        self.assertEqual(nav.find_owner_routes([short_entry], "missing"), [])

    def test_search_qml_matches_component_and_alias(self) -> None:
        by_name = nav.search_qml(QML_ENTRIES, "ManagedToolTip")
        self.assertEqual(by_name[0]["component_name"], "ManagedToolTip")
        self.assertTrue(nav.search_qml(QML_ENTRIES, "managedtooltip.qml"))

    def test_search_qml_matches_generated_symbol_metadata(self) -> None:
        results = nav.search_qml(QML_ENTRIES, "open node browser requested")
        self.assertEqual(results[0]["component_name"], "ConnectionQuickInsertOverlay")

    def test_search_source_reports_owner_maps(self) -> None:
        source = ["ea_node_editor/nodes/builtins/plot/generic.py"]
        tests = ["tests/test_plotter_nodes.py"]
        items = nav.search_source(source, tests, ROUTE_ENTRIES, "generic")
        self.assertEqual(items[0]["path"], "ea_node_editor/nodes/builtins/plot/generic.py")
        self.assertIn(
            "docs/agent_maps/feature_routes/plotter_nodes.md", items[0]["owner_maps"]
        )


class NavCliTests(unittest.TestCase):
    def _make_repo(self, temp_dir: str) -> Path:
        repo_root = Path(temp_dir)
        _write(
            repo_root / nav.ROUTE_INDEX_REL,
            json.dumps(
                {"version": 1, "entries": [*ROUTE_ENTRIES, *QML_ROUTE_ENTRIES]}
            ),
        )
        _write(
            repo_root / nav.QML_INDEX_REL,
            json.dumps({"version": 3, "entries": QML_ENTRIES}),
        )
        _write(
            repo_root / nav.SOURCE_TEST_INDEX_REL,
            "\n".join(
                [
                    "## Source Code",
                    "| Path |",
                    "| --- |",
                    "| `ea_node_editor/nodes/builtins/plot/generic.py` |",
                    "## Test Modules",
                    "| Path |",
                    "| --- |",
                    "| `tests/test_plotter_nodes.py` |",
                ]
            ),
        )
        return repo_root

    def test_route_json_output_is_valid_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(["--repo-root", str(repo_root), "route", "plotter", "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(captured.getvalue())
            self.assertEqual(
                payload[0]["map_path"], "docs/agent_maps/feature_routes/plotter_nodes.md"
            )

    def test_find_defaults_to_compact_owner_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(["--repo-root", str(repo_root), "find", "plot"])
            self.assertEqual(code, 0)
            out = captured.getvalue()
            self.assertIn("No confident owner. Advisory candidate:", out)
            self.assertIn("tests/test_plotter_nodes.py", out)
            self.assertNotIn("== Source/Test ==", out)

    def test_find_labels_exact_alias_as_exact_owner_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    ["--repo-root", str(repo_root), "find", "plotter", "nodes"]
                )
            self.assertEqual(code, 0)
            self.assertTrue(captured.getvalue().startswith("Exact owner match:"))

    def test_find_routes_qml_component_to_owning_map_and_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    ["--repo-root", str(repo_root), "find", "quick", "insert"]
                )
            self.assertEqual(code, 0)
            out = captured.getvalue()
            self.assertIn("docs/agent_maps/feature_routes/workspace_ui.md", out)
            self.assertIn("ConnectionQuickInsertOverlay.qml", out)
            self.assertIn("tests/test_quick_insert.py", out)

    def test_find_prefers_exact_route_aliases_before_qml_owner_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            exact_z = {
                **ROUTE_ENTRIES[0],
                "route_key": "feature_route:exact-z",
                "title": "Exact Z",
                "map_path": "docs/agent_maps/feature_routes/exact_z.md",
                "aliases": ["bounded rich preview"],
            }
            exact_a = {
                **ROUTE_ENTRIES[0],
                "route_key": "feature_route:exact-a",
                "title": "Exact A",
                "map_path": "docs/agent_maps/feature_routes/exact_a.md",
                "aliases": ["bounded rich preview"],
            }
            competing_qml = {
                **QML_ROUTE_ENTRIES[1],
                "route_key": "qml:boundedrichpreview",
                "title": "BoundedRichPreview.qml",
                "keywords": ["bounded", "rich", "preview"],
            }
            _write(
                repo_root / nav.ROUTE_INDEX_REL,
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            *ROUTE_ENTRIES,
                            QML_ROUTE_ENTRIES[0],
                            competing_qml,
                            exact_z,
                            exact_a,
                        ],
                    }
                ),
            )

            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "find",
                        "bounded",
                        "rich",
                        "preview",
                        "--json",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(captured.getvalue())
            self.assertEqual(
                [owner["owner_map"] for owner in payload["owners"]],
                [
                    "docs/agent_maps/feature_routes/exact_a.md",
                    "docs/agent_maps/feature_routes/exact_z.md",
                ],
            )
            self.assertNotIn(
                "docs/agent_maps/feature_routes/workspace_ui.md",
                [owner["owner_map"] for owner in payload["owners"]],
            )

    def test_multiple_exact_aliases_select_distinct_owner_paths(self) -> None:
        list_path = "ea_node_editor/ui_qml/components/graph/ListEditor.qml"
        metrics_path = "ea_node_editor/ui_qml/graph_geometry/standard_metrics.py"
        target_test = "tests/test_shared_surface.py"
        owner = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:shared-surface",
            "title": "Shared Surface",
            "map_path": "docs/agent_maps/feature_routes/shared_surface.md",
            "aliases": ["list editor", "standard metrics"],
            "start_here": [
                "ea_node_editor/ui_qml/components/graph/",
                list_path,
                metrics_path,
                target_test,
            ],
            "focused_verification": [f"pytest {target_test} -q"],
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:listeditor",
            "title": "ListEditor.qml",
            "map_path": QML_ROUTE_ENTRIES[1]["map_path"],
            "source_candidates": [list_path],
            "qml_candidates": [list_path],
            "keywords": ["list", "editor"],
        }

        for query, expected_path in (
            ("list editor", list_path),
            ("standard metrics", metrics_path),
        ):
            with self.subTest(query=query):
                routes = nav.find_owner_routes([owner, component], query)
                capsule = nav.build_owner_capsules(routes, query)[0]
                self.assertEqual(capsule["owner_map"], owner["map_path"])
                self.assertEqual(capsule["path"], expected_path)
                self.assertEqual(capsule["focused_test"], target_test)
                self.assertEqual(
                    capsule["verification"], f"pytest {target_test} -q"
                )

    def test_fuzzy_qml_match_does_not_override_exact_alias_path_affinity(self) -> None:
        list_path = "ea_node_editor/ui_qml/components/graph/ListEditor.qml"
        inline_path = "ea_node_editor/ui_qml/components/graph/InlineProperties.qml"
        owner = {
            **ROUTE_ENTRIES[0],
            "route_key": "feature_route:shared-surface",
            "title": "Shared Surface",
            "map_path": "docs/agent_maps/feature_routes/shared_surface.md",
            "aliases": ["inline list height"],
            "start_here": [list_path, inline_path],
            "source_candidates": [list_path, inline_path],
            "qml_candidates": [list_path, inline_path],
            "focused_verification": [],
        }
        component = {
            **QML_ROUTE_ENTRIES[1],
            "route_key": "qml:inlineproperties",
            "title": "InlineProperties.qml",
            "map_path": QML_ROUTE_ENTRIES[1]["map_path"],
            "source_candidates": [inline_path],
            "qml_candidates": [inline_path],
            "keywords": ["inline", "list", "height"],
        }

        routes = nav.find_owner_routes([owner, component], "inline list height")
        capsule = nav.build_owner_capsules(routes, "inline list height")[0]

        self.assertNotIn("_nav_evidence_paths", routes[0])
        self.assertEqual(capsule["path"], list_path)

    def test_one_owner_selects_tests_by_per_query_affinity(self) -> None:
        fullscreen_test = "tests/test_content_fullscreen_bridge.py"
        session_test = "tests/test_viewer_session_bridge.py"
        owner = {
            **ROUTE_ENTRIES[0],
            "aliases": ["fullscreen toolbar click", "viewer session ownership"],
            "start_here": [fullscreen_test, session_test],
            "focused_verification": [
                f"pytest {fullscreen_test} -q",
                f"pytest {session_test} -q",
            ],
        }

        for query, expected_test in (
            ("fullscreen toolbar click", fullscreen_test),
            ("viewer session ownership", session_test),
        ):
            with self.subTest(query=query):
                route = nav.find_owner_routes([owner], query)
                capsule = nav.build_owner_capsules(route, query)[0]
                self.assertEqual(capsule["focused_test"], expected_test)
                self.assertEqual(
                    capsule["verification"], f"pytest {expected_test} -q"
                )

    def test_exact_qml_test_affinity_omits_unrelated_and_keeps_script_editor(self) -> None:
        script_test = "tests/test_script_editor_dock.py"
        inferred = {
            **ROUTE_ENTRIES[1],
            "route_key": "subsystem:qml-shell",
            "title": "QML Shell",
            "map_path": "docs/agent_maps/subsystems/qml_shell.md",
            "start_here": [script_test],
            "focused_verification": [f"pytest {script_test} -q"],
        }
        for component_name, expects_test in (
            ("InspectorPropertyEditor", False),
            ("ScriptEditorOverlay", True),
        ):
            path = f"ea_node_editor/ui_qml/{component_name}.qml"
            component = {
                **QML_ROUTE_ENTRIES[1],
                "route_key": f"qml:{component_name.lower()}",
                "title": f"{component_name}.qml",
                "map_path": inferred["map_path"],
                "source_candidates": [path],
                "qml_candidates": [path],
                "keywords": [component_name.lower()],
            }
            with self.subTest(component=component_name):
                routes = nav.find_owner_routes([inferred, component], component_name)
                capsule = nav.build_owner_capsules(routes, component_name)[0]
                self.assertEqual(capsule["path"], path)
                if expects_test:
                    self.assertEqual(capsule["focused_test"], script_test)
                else:
                    self.assertNotIn("focused_test", capsule)
                    self.assertNotIn("verification", capsule)

    def test_find_expand_preserves_broad_discovery_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    ["--repo-root", str(repo_root), "find", "plot", "--expand"]
                )
            self.assertEqual(code, 0)
            out = captured.getvalue()
            self.assertIn("== Routes ==", out)
            self.assertIn("== Source/Test ==", out)

    def test_find_default_json_is_a_compact_owner_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    ["--repo-root", str(repo_root), "find", "plotter", "--json"]
                )
            self.assertEqual(code, 0)
            payload = json.loads(captured.getvalue())
            self.assertEqual(payload["query"], "plotter")
            self.assertEqual(payload["confidence"], "advisory")
            self.assertEqual(len(payload["owners"]), 1)
            self.assertEqual(
                payload["owners"][0]["owner_map"],
                "docs/agent_maps/feature_routes/plotter_nodes.md",
            )
            self.assertLessEqual(
                len(captured.getvalue().encode("utf-8")), nav.MAX_DEFAULT_OUTPUT_BYTES
            )

    def test_find_no_match_json_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = nav.main(
                    ["--repo-root", str(repo_root), "find", "missing", "--json"]
                )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(captured.getvalue()),
                {"query": "missing", "confidence": "none", "owners": []},
            )

    def test_no_matches_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            captured = io.StringIO()
            with redirect_stdout(captured):
                nav.main(["--repo-root", str(repo_root), "route", "zzz-no-match"])
            self.assertIn("No matches.", captured.getvalue())

    def test_line_resolves_current_map_qml_and_source_locations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            map_path = repo_root / "docs" / "agent_maps" / "sample.md"
            qml_path = repo_root / "ea_node_editor" / "ui_qml" / "Sample.qml"
            source_path = repo_root / "ea_node_editor" / "sample.py"
            _write(map_path, "# Sample\n\n## Start Here\n")
            _write(qml_path, "Item {\n    property string title: \"sample\"\n}\n")
            _write(source_path, "def build_sample():\n    return True\n")

            cases = (
                ("docs/agent_maps/sample.md", "Start Here", 3),
                ("ea_node_editor/ui_qml/Sample.qml", "title", 2),
                ("ea_node_editor/sample.py", "build_sample", 1),
            )
            for selected_path, anchor, expected_line in cases:
                with self.subTest(path=selected_path):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        code = nav.main(
                            [
                                "--repo-root",
                                str(repo_root),
                                "line",
                                selected_path,
                                anchor,
                                "--json",
                            ]
                        )
                    self.assertEqual(code, 0)
                    payload = json.loads(captured.getvalue())
                    self.assertEqual(payload["line"], expected_line)
                    self.assertEqual(payload["path"], selected_path)

    def test_qml_anchor_output_round_trips_to_exact_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = self._make_repo(temp_dir)
            qml_path = repo_root / QML_ENTRIES[0]["path"]
            _write(qml_path, "Item {\n    property var policyBridge: null\n}\n")

            captured = io.StringIO()
            with redirect_stdout(captured):
                nav.main(
                    ["--repo-root", str(repo_root), "qml", "ManagedToolTip"]
                )
            self.assertIn("symbols: policyBridge", captured.getvalue())
            self.assertNotIn("ManagedToolTipPropertyPolicyBridge", captured.getvalue())

            result = nav.resolve_current_line(
                repo_root,
                QML_ENTRIES[0]["path"],
                "ManagedToolTipPropertyPolicyBridge",
            )
            self.assertIsNotNone(result)
            self.assertEqual(result["line"], 2)

    def test_line_resolution_is_exact_and_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside_dir:
            repo_root = self._make_repo(temp_dir)
            qml_path = repo_root / "ea_node_editor/ui_qml/Exact.qml"
            _write(
                qml_path,
                "\n".join(
                    (
                        "Item {",
                        "    // commentOnly width",
                        "    property real defaultPanelWidth: parent.width",
                        "    width: 42",
                        "    property real panelWidth: 0",
                        "}",
                    )
                ),
            )

            width = nav.resolve_current_line(repo_root, str(qml_path), "width")
            self.assertIsNotNone(width)
            self.assertEqual(width["line"], 4)
            self.assertIsNone(nav.resolve_current_line(repo_root, str(qml_path), "PANELWIDTH"))
            self.assertIsNone(nav.resolve_current_line(repo_root, str(qml_path), "commentOnly"))
            with self.assertRaisesRegex(ValueError, "must not be blank"):
                nav.resolve_current_line(repo_root, str(qml_path), "   ")

            outside_path = Path(outside_dir) / "outside.py"
            _write(outside_path, "outside = True\n")
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                nav.resolve_current_line(repo_root, str(outside_path), "outside")
            traversal = Path("..") / Path(outside_dir).name / outside_path.name
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                nav.resolve_current_line(repo_root, str(traversal), "outside")

    def test_tied_owner_budget_keeps_primary_capsule_complete(self) -> None:
        entries = []
        for index in range(5):
            entries.append(
                {
                    **ROUTE_ENTRIES[0],
                    "route_key": f"feature_route:tied-{index}",
                    "title": f"Tied Owner {index}",
                    "map_path": f"docs/agent_maps/feature_routes/tied_{index}.md",
                    "start_here": [
                        f"ea_node_editor/tied_{index}.py",
                        f"tests/test_tied_{index}.py",
                    ],
                    "test_candidates": [f"tests/test_tied_{index}.py"],
                    "focused_verification": [
                        f"pytest tests/test_tied_{index}.py -q"
                    ],
                    "do_not_start_here": [],
                }
            )

        capsules = nav.build_owner_capsules(entries, "shared")
        self.assertEqual(capsules[0]["owner_map"], entries[0]["map_path"])
        self.assertEqual(capsules[0]["path"], "ea_node_editor/tied_0.py")
        self.assertEqual(capsules[0]["focused_test"], "tests/test_tied_0.py")
        self.assertIn("verification", capsules[0])
        paths = {
            str(value)
            for capsule in capsules
            for field in ("owner_map", "path", "focused_test")
            if (value := capsule.get(field))
        }
        self.assertLessEqual(len(paths), nav.MAX_DEFAULT_PATHS)
        for as_json in (False, True):
            captured = io.StringIO()
            with redirect_stdout(captured):
                nav._emit_owner_capsules("shared", capsules, as_json)
            self.assertLessEqual(
                len(captured.getvalue().encode("utf-8")),
                nav.MAX_DEFAULT_OUTPUT_BYTES,
            )
            if not as_json:
                self.assertTrue(
                    captured.getvalue().startswith(
                        "No confident owner. Advisory candidates:"
                    )
                )

    def test_capsule_prefers_exact_evidence_and_omits_unrelated_test(self) -> None:
        evidence_path = "ea_node_editor/ui_qml/components/graph/ExactControl.qml"
        entry = {
            **ROUTE_ENTRIES[0],
            "start_here": [
                "ea_node_editor/ui_qml/components/graph/",
                "ea_node_editor/ui_qml/components/graph/Unrelated.qml",
                "tests/test_script_editor_dock.py",
            ],
            "test_candidates": ["tests/test_script_editor_dock.py"],
            "focused_verification": ["pytest tests/test_script_editor_dock.py -q"],
            "_nav_evidence_paths": [evidence_path],
            "_nav_direct_match": False,
        }

        capsule = nav.build_owner_capsules([entry], "list geometry")[0]

        self.assertEqual(capsule["path"], evidence_path)
        self.assertNotIn("focused_test", capsule)
        self.assertNotIn("verification", capsule)

    def test_capsule_uses_exact_file_before_start_here_directory(self) -> None:
        entry = {
            **ROUTE_ENTRIES[0],
            "start_here": [
                "ea_node_editor/ui_qml/components/graph/",
                "ea_node_editor/ui_qml/components/graph/ExactControl.qml",
            ],
            "focused_verification": [],
            "test_candidates": [],
        }

        capsule = nav.build_owner_capsules([entry], "unrelated")[0]

        self.assertEqual(
            capsule["path"],
            "ea_node_editor/ui_qml/components/graph/ExactControl.qml",
        )


class NavOwnerCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        index_data = indexer.build_index_data(REPO_ROOT)
        cls.entries = [indexer.route_entry_to_dict(entry) for entry in index_data.entries]
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    def test_all_canonical_map_titles_resolve_through_default_find(self) -> None:
        map_entries = [
            entry for entry in self.entries if entry.get("kind") != "qml_component"
        ]
        self.assertEqual(len(map_entries), 67)
        for entry in map_entries:
            with self.subTest(route=entry["route_key"]):
                owners = nav.find_owner_routes(self.entries, entry["title"])
                self.assertTrue(owners)
                self.assertEqual(owners[0]["map_path"], entry["map_path"])

    def test_new_task_owner_contracts(self) -> None:
        new_case_ids = {f"CL-{number}" for number in range(14, 21)}
        for case in self.corpus["cases"]:
            if case["id"] not in new_case_ids:
                continue
            with self.subTest(case=case["id"]):
                captured = io.StringIO()
                with redirect_stdout(captured):
                    code = nav.main(
                        [
                            "--repo-root",
                            str(REPO_ROOT),
                            "find",
                            *case["query"].split(),
                            "--json",
                        ]
                    )
                self.assertEqual(code, 0)
                owners = json.loads(captured.getvalue())["owners"]
                expected_maps = [case["primary_owner"], *case["secondary_owners"]]
                self.assertEqual(
                    [owner["owner_map"] for owner in owners],
                    expected_maps,
                )
                self.assertEqual(owners[0].get("path"), case["primary_path"])
                self.assertEqual(
                    owners[0].get("focused_test"), case["focused_test"]
                )

    def test_owner_corpus_accuracy_and_default_output_budgets(self) -> None:
        cases = self.corpus["cases"]
        self.assertEqual(self.corpus["version"], 1)
        self.assertGreaterEqual(len(cases), 10)

        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertLessEqual(len(case["secondary_owners"]), 2)
                owners = nav.find_owner_routes(self.entries, case["query"])
                owner_maps = [entry["map_path"] for entry in owners]
                expected_maps = [case["primary_owner"], *case["secondary_owners"]]
                self.assertEqual(owner_maps, expected_maps)

                captured = io.StringIO()
                with redirect_stdout(captured):
                    code = nav.main(
                        [
                            "--repo-root",
                            str(REPO_ROOT),
                            "find",
                            *case["query"].split(),
                            "--json",
                        ]
                    )
                self.assertEqual(code, 0)
                cli_owners = json.loads(captured.getvalue())["owners"]
                self.assertEqual(
                    [owner["owner_map"] for owner in cli_owners],
                    expected_maps,
                )
                capsules = nav.build_owner_capsules(owners, case["query"])
                paths: set[str] = set()
                for capsule in capsules:
                    for field in ("owner_map", "path", "focused_test"):
                        if capsule.get(field):
                            paths.add(str(capsule[field]))
                    paths.update(capsule.get("do_not_start_here", []))
                self.assertLessEqual(len(paths), nav.MAX_DEFAULT_PATHS)

                for as_json in (False, True):
                    captured = io.StringIO()
                    with redirect_stdout(captured):
                        nav._emit_owner_capsules(case["query"], capsules, as_json)
                    self.assertLessEqual(
                        len(captured.getvalue().encode("utf-8")),
                        nav.MAX_DEFAULT_OUTPUT_BYTES,
                    )

                primary_capsule = capsules[0]
                if expected_primary_path := case.get("primary_path"):
                    self.assertEqual(
                        primary_capsule.get("path"), expected_primary_path
                    )
                self.assertEqual(
                    primary_capsule.get("focused_test"), case["focused_test"]
                )
                self.assertNotIn(
                    primary_capsule.get("path"), case["not_first_paths"]
                )


if __name__ == "__main__":
    unittest.main()
