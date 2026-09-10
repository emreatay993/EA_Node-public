from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import check_context_budgets as guardrails


EXPECTED_RULES = {
    "ea_node_editor/ui/shell/window.py": ("P01", "shell-window-facade", 900),
    "ea_node_editor/ui/shell/presenters/__init__.py": ("P02", "presenter-family", 120),
    "ea_node_editor/ui/shell/presenters/library_presenter.py": ("P02", "presenter-family", 450),
    "ea_node_editor/ui/shell/presenters/workspace_presenter.py": ("P02", "presenter-family", 450),
    "ea_node_editor/ui/shell/presenters/inspector_presenter.py": ("P02", "presenter-family", 450),
    "ea_node_editor/ui/shell/presenters/canvas_export_presenter.py": ("P02", "presenter-family", 450),
    "ea_node_editor/ui/shell/presenters/graph_canvas_host_presenter.py": ("P02", "presenter-family", 450),
    "ea_node_editor/ui_qml/graph_scene_bridge.py": ("P03", "graph-scene-bridge", 300),
    "ea_node_editor/ui_qml/components/GraphCanvas.qml": ("P04", "graph-canvas-root", 700),
    "ea_node_editor/ui_qml/components/graph/EdgeLayer.qml": ("P05", "edge-renderer", 700),
    "ea_node_editor/ui_qml/viewer_session_bridge.py": ("P06", "viewer-surface", 550),
    "ea_node_editor/execution/viewer_session_service.py": ("P06", "viewer-surface", 700),
    "ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurface.qml": (
        "P06",
        "viewer-surface",
        600,
    ),
    "ea_node_editor/ui/shell/controllers/project_session_services.py": ("P02", "shell-session-surface", 23),
    "ea_node_editor/ui_qml/graph_surface_metrics.py": (
        "P03",
        "graph-geometry-facade",
        251,
    ),
    "ea_node_editor/ui_qml/edge_routing.py": ("P03", "graph-geometry-facade", 326),
    "ea_node_editor/ui_qml/graph_scene_mutation_history.py": (
        "P04",
        "graph-scene-mutation",
        328,
    ),
    "tests/main_window_shell/bridge_contracts.py": (
        "P05",
        "main-window-bridge-regression",
        61,
    ),
    "tests/test_passive_graph_surface_host.py": ("P06", "graph-surface-regression", 20),
    "tests/test_graph_surface_input_contract.py": ("P06", "graph-surface-regression", 24),
    "tests/graph_track_b/qml_preference_bindings.py": ("P07", "track-b-regression", 41),
    "tests/graph_track_b/scene_and_model.py": ("P07", "track-b-regression", 78),
}


class ContextBudgetGuardrailTests(unittest.TestCase):
    def test_ruleset_remains_loadable_for_optional_historical_diagnostics(self) -> None:
        rules = guardrails.load_rules()
        self.assertGreaterEqual(len(rules), len(EXPECTED_RULES))
        self.assertTrue(all(rule.path for rule in rules))
        self.assertTrue(all(rule.owner_packet for rule in rules))
        self.assertTrue(all(rule.owner_label for rule in rules))
        self.assertTrue(all(rule.max_lines > 0 for rule in rules))

    @unittest.skip("Context-budget pass/fail is no longer a release verification gate.")
    def test_guardrail_script_passes_against_current_repo(self) -> None:
        results = guardrails.evaluate_rules()
        self.assertEqual(len(EXPECTED_RULES), len(results))
        self.assertTrue(all(result.passed for result in results))

        captured = io.StringIO()
        with redirect_stdout(captured):
            return_code = guardrails.main([])

        self.assertEqual(0, return_code)
        self.assertIn(
            "PASS: context budget guardrails satisfied for 23 guarded hotspots.",
            captured.getvalue(),
        )

    def test_guardrail_script_reports_budget_overruns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            sample_path = repo_root / "pkg" / "sample.py"
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            sample_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            rules_path = repo_root / "rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "rule_set": "tests",
                        "rules": [
                            {
                                "path": "pkg/sample.py",
                                "owner_packet": "P99",
                                "owner_label": "temp-rule",
                                "max_lines": 2,
                            }
                        ],
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            captured = io.StringIO()
            with redirect_stdout(captured):
                return_code = guardrails.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--rules",
                        str(rules_path),
                    ]
                )

        self.assertEqual(0, return_code)
        self.assertIn(
            "WARN: [P99:temp-rule] pkg/sample.py is 3 lines (cap 2).",
            captured.getvalue(),
        )

    def test_guardrail_script_can_still_enforce_budget_overruns_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            sample_path = repo_root / "pkg" / "sample.py"
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            sample_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            rules_path = repo_root / "rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "rule_set": "tests",
                        "rules": [
                            {
                                "path": "pkg/sample.py",
                                "owner_packet": "P99",
                                "owner_label": "temp-rule",
                                "max_lines": 2,
                            }
                        ],
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            captured = io.StringIO()
            with redirect_stdout(captured):
                return_code = guardrails.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--rules",
                        str(rules_path),
                        "--enforce",
                    ]
                )

            self.assertEqual(1, return_code)
            self.assertIn(
                "FAIL: [P99:temp-rule] pkg/sample.py is 3 lines (cap 2).",
                captured.getvalue(),
            )

    def test_guardrail_script_reports_missing_hotspots_without_blocking_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            rules_path = repo_root / "rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "rule_set": "tests",
                        "rules": [
                            {
                                "path": "pkg/missing.py",
                                "owner_packet": "P99",
                                "owner_label": "temp-rule",
                                "max_lines": 2,
                            }
                        ],
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            captured = io.StringIO()
            with redirect_stdout(captured):
                return_code = guardrails.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--rules",
                        str(rules_path),
                    ]
                )

            self.assertEqual(0, return_code)
            self.assertIn(
                "WARN: [P99:temp-rule] pkg/missing.py is missing.",
                captured.getvalue(),
            )


if __name__ == "__main__":
    unittest.main()
