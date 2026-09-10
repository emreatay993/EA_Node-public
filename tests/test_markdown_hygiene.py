from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import verification_manifest as manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_markdown_links.py"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
PLAN_TEMPLATE_PATH = REPO_ROOT / "PLANS_TO_IMPLEMENT" / "PLAN_TEMPLATE.md"
PLAN_REPO_OVERLAY_PATH = REPO_ROOT / "PLANS_TO_IMPLEMENT" / "PLAN_REPO_OVERLAY.md"
IN_PROGRESS_PLANS_ROOT = REPO_ROOT / "PLANS_TO_IMPLEMENT" / "in_progress"
LEGACY_IN_PROGRESS_PLAN_NAMES = {
    "Core Web Host Layer For Excalidraw.md",
}


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_text(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class MarkdownHygieneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load_module("check_markdown_links_for_tests", CHECKER_PATH)

    def test_audit_repository_passes_for_current_repo(self) -> None:
        self.assertEqual([], self.checker.audit_repository(REPO_ROOT))

    def test_agents_guidance_keeps_bounded_evidence_first_navigation(self) -> None:
        agents_text = AGENTS_PATH.read_text(encoding="utf-8")

        self.assertIn("bounded source search", agents_text)
        self.assertIn("docs/agent_maps/INDEX.md", agents_text)
        self.assertIn("docs/agent_route_index.md", agents_text)
        self.assertIn("Verify ownership against current source before editing", agents_text)
        self.assertIn("Before broad source or test searches", agents_text)
        self.assertIn("route index plus maps", agents_text)
        self.assertIn("why narrower evidence is insufficient", agents_text)
        self.assertIn("cap the results", agents_text)

    def test_spec_index_registers_architecture_residual_matrix_link(self) -> None:
        spec_index_text = (REPO_ROOT / "docs" / "specs" / "INDEX.md").read_text(
            encoding="utf-8-sig"
        )
        matrix_text = (REPO_ROOT / manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC).read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "[ARCHITECTURE_RESIDUAL_REFACTOR QA Matrix](perf/ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# Architecture Residual Refactor QA Matrix"))

    def test_spec_index_registers_capability_statuses_without_proof_links(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        section = text.split("## Capability Roadmap Status", 1)[1].split(
            "\n## ", 1
        )[0]
        for opportunity_number in range(1, 9):
            self.assertIn(f"SYN-OPP-{opportunity_number:04d}", section)
        self.assertIn("`PLANNED`", section)
        self.assertIn("`PARTIAL`", section)
        self.assertNotIn("QA_MATRIX", section)
        self.assertNotIn("Implementation Artifact", section)

    def test_spec_index_registers_ui_context_scalability_matrix_link(self) -> None:
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = REPO_ROOT / "docs" / "specs" / "perf" / "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md"
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[UI_CONTEXT_SCALABILITY_REFACTOR QA Matrix](perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# UI Context Scalability Refactor QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_spec_index_registers_ui_context_scalability_followup_packet_set(self) -> None:
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT / "docs" / "specs" / "perf" / "UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[UI_CONTEXT_SCALABILITY_FOLLOWUP QA Matrix](perf/UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# UI Context Scalability Follow-Up QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))


    def test_readme_and_spec_index_link_addon_manager_backend_preparation_matrix(self) -> None:
        readme_path = REPO_ROOT / "README.md"
        readme_text = readme_path.read_text(encoding="utf-8-sig")
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT / "docs" / "specs" / "perf" / "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[Add-On Manager Backend Preparation QA Matrix](docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md)",
            readme_text,
        )
        self.assertIn(
            "[ADDON_MANAGER_BACKEND_PREPARATION QA Matrix](perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# Add-On Manager Backend Preparation QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(readme_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_readme_and_spec_index_link_corex_no_legacy_architecture_cleanup_matrix(self) -> None:
        readme_path = REPO_ROOT / "README.md"
        readme_text = readme_path.read_text(encoding="utf-8-sig")
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT / "docs" / "specs" / "perf" / "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[COREX No-Legacy Architecture Cleanup QA Matrix](docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md)",
            readme_text,
        )
        self.assertIn(
            "[COREX_NO_LEGACY_ARCHITECTURE_CLEANUP QA Matrix](perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# COREX No-Legacy Architecture Cleanup QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(readme_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_spec_index_links_corex_excalidraw_web_host_layer_matrix(self) -> None:
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT / "docs" / "specs" / "perf" / "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[COREX_EXCALIDRAW_WEB_HOST_LAYER QA Matrix](perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertIn("COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md", spec_index_text)
        self.assertIn(
            "[COREX_EXCALIDRAW_REAL_EDITOR QA Evidence](perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# COREX Excalidraw Web Host Layer QA Matrix"))
        self.assertIn("real local/offline Excalidraw editor", matrix_text)
        self.assertIn("managed image imports", matrix_text)
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_spec_index_links_chromium_website_html_viewer_node_matrix(self) -> None:
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT / "docs" / "specs" / "perf" / "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[CHROMIUM_WEBSITE_HTML_VIEWER_NODE QA Matrix](perf/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# Chromium Website HTML Viewer Node QA Matrix"))
        self.assertIn("generic bridge-free `web_page` surface route", matrix_text)
        self.assertIn("Ready for manual testing", matrix_text)
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_readme_getting_started_and_spec_index_link_corex_clean_architecture_restructure_matrix(
        self,
    ) -> None:
        readme_path = REPO_ROOT / "README.md"
        readme_text = readme_path.read_text(encoding="utf-8-sig")
        getting_started_path = REPO_ROOT / "docs" / "GETTING_STARTED.md"
        getting_started_text = getting_started_path.read_text(encoding="utf-8-sig")
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT
            / "docs"
            / "specs"
            / "perf"
            / "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[COREX Clean Architecture Restructure QA Matrix](docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md)",
            readme_text,
        )
        self.assertIn(
            "[docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md](./specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md)",
            getting_started_text,
        )
        self.assertIn(
            "[COREX_CLEAN_ARCHITECTURE_RESTRUCTURE QA Matrix](perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# COREX Clean Architecture Restructure QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(readme_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(getting_started_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_readme_and_spec_index_link_corex_architecture_modernization_matrix(
        self,
    ) -> None:
        readme_path = REPO_ROOT / "README.md"
        readme_text = readme_path.read_text(encoding="utf-8-sig")
        spec_index_path = REPO_ROOT / "docs" / "specs" / "INDEX.md"
        spec_index_text = spec_index_path.read_text(encoding="utf-8-sig")
        matrix_path = (
            REPO_ROOT
            / "docs"
            / "specs"
            / "perf"
            / "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md"
        )
        matrix_text = matrix_path.read_text(encoding="utf-8-sig")

        self.assertIn(
            "[COREX Architecture Modernization QA Matrix](docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md)",
            readme_text,
        )
        self.assertIn(
            "[COREX_ARCHITECTURE_MODERNIZATION QA Matrix](perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md)",
            spec_index_text,
        )
        self.assertTrue(matrix_text.startswith("# COREX Architecture Modernization QA Matrix"))
        self.assertEqual([], self.checker.audit_markdown_file(readme_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(spec_index_path, REPO_ROOT))
        self.assertEqual([], self.checker.audit_markdown_file(matrix_path, REPO_ROOT))

    def test_architecture_registers_current_navigation_authorities(self) -> None:
        architecture_text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8-sig")

        self.assertIn(
            "[`docs/agent_maps/INDEX.md`](docs/agent_maps/INDEX.md)",
            architecture_text,
        )
        self.assertIn(
            "[`docs/specs/INDEX.md`](docs/specs/INDEX.md)",
            architecture_text,
        )
        self.assertIn(
            "Historical work-packet records live in Git history",
            architecture_text,
        )

    def test_plan_template_defines_focused_and_expanded_shapes(self) -> None:
        template_text = PLAN_TEMPLATE_PATH.read_text(encoding="utf-8-sig")

        required_snippets = (
            "## Required Authoring Rules",
            "## Focused Change Skeleton",
            "## Expanded Task Skeleton",
            "## Execution Tasks",
            "## Work Packet Conversion Map (only when explicitly requested)",
            "Conservative write scope",
            "Every verification command must appear exactly once",
            "Conditional closeout",
        )

        for snippet in required_snippets:
            self.assertIn(snippet, template_text)

        self.assertNotIn("docs/specs/INDEX.md", template_text)
        self.assertNotIn("ui_context_scalability_refactor", template_text)
        self.assertEqual([], self.checker.audit_markdown_file(PLAN_TEMPLATE_PATH, REPO_ROOT))

    def test_plan_repo_overlay_registers_focused_verification_policy(self) -> None:
        overlay_text = PLAN_REPO_OVERLAY_PATH.read_text(encoding="utf-8-sig")

        required_snippets = (
            "## Local Planning Entry Points",
            "## Local Packetization Defaults",
            "## Local Verification Defaults",
            "## Local Ownership Notes",
            "[docs/specs/INDEX.md](../docs/specs/INDEX.md)",
            "[docs/agent_maps/INDEX.md](../docs/agent_maps/INDEX.md)",
            "a menu, not a mandatory bundle",
            "Do not create a packet map, `P00`",
        )

        for snippet in required_snippets:
            self.assertIn(snippet, overlay_text)

        self.assertEqual([], self.checker.audit_markdown_file(PLAN_REPO_OVERLAY_PATH, REPO_ROOT))

    def test_in_progress_plans_use_a_supported_plan_shape(self) -> None:
        focused_headings = ("## Summary", "## Change", "## Verification", "## Assumptions")
        expanded_headings = (
            "## Summary",
            "## Key Changes",
            "## Public Interface Changes",
            "## Execution Tasks",
            "## Test Plan",
            "## Assumptions",
        )

        plan_paths = sorted(IN_PROGRESS_PLANS_ROOT.glob("*.md"))
        if not plan_paths:
            return

        for path in plan_paths:
            with self.subTest(path=path.name):
                if path.name in LEGACY_IN_PROGRESS_PLAN_NAMES:
                    continue

                text = path.read_text(encoding="utf-8-sig")

                legacy_design_note = "## Context" in text and (
                    "## Outcome" in text or "\nOutcome:" in text
                )
                if legacy_design_note:
                    continue

                is_focused = all(heading in text for heading in focused_headings)
                is_expanded = all(heading in text for heading in expanded_headings)
                self.assertTrue(is_focused or is_expanded)

                self.assertEqual([], self.checker.audit_markdown_file(path, REPO_ROOT))

    def test_audit_repository_reports_missing_local_markdown_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_text(repo_root, "README.md", "[Broken](docs/missing.md)\n")

            issues = self.checker.audit_repository(repo_root)

        self.assertEqual(
            ["README.md:1: broken markdown link target: docs/missing.md"],
            issues,
        )

    def test_audit_repository_reports_missing_markdown_heading_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_text(
                repo_root,
                "README.md",
                "[Setup](docs/GETTING_STARTED.md#missing-anchor)\n",
            )
            write_text(
                repo_root,
                "docs/GETTING_STARTED.md",
                "# Getting Started\n\n## Actual Heading\n",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertEqual(
            [
                "README.md:1: missing markdown heading anchor for "
                "docs/GETTING_STARTED.md#missing-anchor"
            ],
            issues,
        )

    def test_audit_repository_ignores_code_fence_and_external_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_text(
                repo_root,
                "README.md",
                "```md\n[Ignored](docs/missing.md)\n```\n"
                "[External](https://example.com)\n",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
