from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import check_agent_maps as gate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class AgentMapDriftGateTests(unittest.TestCase):
    def test_repo_agent_maps_cite_only_existing_paths(self) -> None:
        # The real navigation layer must stay drift-free. If this fails, an
        # agent map or the route index points at a file that no longer exists;
        # fix the citation (or regenerate the index) rather than skipping.
        problems = gate.check(gate.REPO_ROOT)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_normalize_path_token_recognizes_and_rejects(self) -> None:
        self.assertEqual(
            gate.normalize_path_token("ea_node_editor/nodes/registry.py"),
            "ea_node_editor/nodes/registry.py",
        )
        self.assertEqual(
            gate.normalize_path_token("tests/test_x.py::TestX::test_y"),
            "tests/test_x.py",
        )
        self.assertEqual(
            gate.normalize_path_token("ea_node_editor/foo.py:42"), "ea_node_editor/foo.py"
        )
        # Not repo paths: commands, dotted modules, bare words, globs, placeholders.
        self.assertIsNone(gate.normalize_path_token(".\\venv\\Scripts\\python.exe -m pytest"))
        self.assertIsNone(gate.normalize_path_token("ea_node_editor.graph"))
        self.assertIsNone(gate.normalize_path_token("registry"))
        self.assertIsNone(gate.normalize_path_token("ea_node_editor/nodes/*.py"))
        self.assertIsNone(gate.normalize_path_token("ea_node_editor/<kind>.py"))

    def test_missing_citation_is_detected_and_fixable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            # Minimal route index so check_route_index is satisfied; the map
            # citation is the only thing under test here.
            _write(repo_root / gate.ROUTE_INDEX_REL, '{"entries": []}\n')
            map_file = repo_root / "docs" / "agent_maps" / "subsystems" / "sample.md"
            _write(map_file, "# Sample\n\n- `ea_node_editor/nodes/ghost.py`\n")
            problems = gate.check(repo_root)
            self.assertTrue(any("ghost.py" in p for p in problems))

            captured = io.StringIO()
            with redirect_stdout(captured):
                code = gate.main(["--repo-root", str(repo_root)])
            self.assertEqual(code, 1)
            self.assertIn("FAIL", captured.getvalue())

            # Repoint to a real file -> gate passes.
            real = repo_root / "ea_node_editor" / "nodes" / "registry.py"
            _write(real, "x = 1\n")
            map_file.write_text(
                "# Sample\n\n- `ea_node_editor/nodes/registry.py`\n", encoding="utf-8"
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(gate.main(["--repo-root", str(repo_root)]), 0)


    def test_source_header_banners_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            _write(repo_root / gate.ROUTE_INDEX_REL, '{"entries": []}\n')
            _write(repo_root / "docs" / "agent_maps" / "subsystems" / "sample.md", "# Sample\n")
            _write(repo_root / "tests" / "test_sample.py", "x = 1\n")
            # A file whose Map/Tests headers resolve produces no problems.
            _write(
                repo_root / "ea_node_editor" / "good.py",
                "# Map: subsystems/sample\n# Tests: tests/test_sample.py\nx = 1\n",
            )
            self.assertEqual(gate.check_source_headers(repo_root), [])
            # Broken Map + Tests headers are both reported.
            _write(
                repo_root / "ea_node_editor" / "bad.py",
                "# Map: subsystems/ghost\n# Tests: tests/test_ghost.py\nx = 1\n",
            )
            problems = gate.check_source_headers(repo_root)
            self.assertTrue(any("Map" in p and "ghost" in p for p in problems))
            self.assertTrue(any("Tests" in p and "test_ghost" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
