from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import generate_source_test_file_index as indexer


class SourceTestFileIndexTests(unittest.TestCase):
    def test_collect_entries_lists_paths_and_ignores_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            (repo_root / "src" / "__pycache__").mkdir(parents=True)
            (repo_root / "src" / "a.py").write_text("one\n\ntwo\n", encoding="utf-8")
            (repo_root / "src" / "view.qml").write_text("Item {}\n", encoding="utf-8")
            (repo_root / "src" / "__pycache__" / "cached.py").write_text(
                "ignore\n",
                encoding="utf-8",
            )
            (repo_root / "src" / "notes.md").write_text("ignore\n", encoding="utf-8")

            entries = indexer.collect_entries(
                repo_root,
                roots=(Path("src"),),
                suffixes=(".py", ".qml"),
            )

        self.assertEqual(
            entries,
            (
                indexer.FileEntry(path="src/a.py"),
                indexer.FileEntry(path="src/view.qml"),
            ),
        )

    def test_default_exclusions_skip_generated_and_vendor_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            public_sdk_path = repo_root / "corex" / "__init__.py"
            live_path = repo_root / "ea_node_editor" / "live.py"
            generated_path = (
                repo_root
                / "ea_node_editor"
                / "web_assets"
                / "excalidraw_host"
                / "chunk.js"
            )
            vendor_path = repo_root / "web" / "excalidraw_host" / "node_modules" / "dep.js"
            public_sdk_path.parent.mkdir(parents=True)
            live_path.parent.mkdir(parents=True)
            generated_path.parent.mkdir(parents=True)
            vendor_path.parent.mkdir(parents=True)
            public_sdk_path.write_text("Any = object()\n", encoding="utf-8")
            live_path.write_text("print('live')\n", encoding="utf-8")
            generated_path.write_text("console.log('generated')\n", encoding="utf-8")
            vendor_path.write_text("console.log('vendor')\n", encoding="utf-8")

            index_data = indexer.build_index_data(repo_root)

        self.assertEqual(
            index_data.source_entries,
            (
                indexer.FileEntry("corex/__init__.py"),
                indexer.FileEntry("ea_node_editor/live.py"),
            ),
        )
        self.assertEqual(index_data.test_entries, ())

    def test_git_inventory_skips_locally_excluded_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            source_root = repo_root / "src"
            source_root.mkdir()
            (source_root / "live.py").write_text("live\n", encoding="utf-8")
            (source_root / "local_only.py").write_text("local\n", encoding="utf-8")
            (repo_root / ".git" / "info" / "exclude").write_text(
                "src/local_only.py\n",
                encoding="utf-8",
            )

            entries = indexer.collect_entries(
                repo_root,
                roots=(Path("src"),),
                suffixes=(".py",),
            )

        self.assertEqual(entries, (indexer.FileEntry("src/live.py"),))

    def test_render_is_invariant_to_file_content_and_line_count_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            source_path = repo_root / "src" / "module.py"
            test_path = repo_root / "tests" / "test_module.py"
            source_path.parent.mkdir()
            test_path.parent.mkdir()
            source_path.write_text("value = 1\n", encoding="utf-8")
            test_path.write_text("def test_value():\n    assert True\n", encoding="utf-8")

            before = indexer.render_markdown(
                indexer.build_index_data(
                    repo_root,
                    source_roots=(Path("src"),),
                    test_roots=(Path("tests"),),
                ),
                source_roots=(Path("src"),),
                test_roots=(Path("tests"),),
            )
            source_path.write_text(
                "# leading comment\n\nvalue = 2\nextra = 'non-symbol text'\n",
                encoding="utf-8",
            )
            test_path.write_text(
                "# leading comment\n\n\ndef test_value():\n    assert False\n",
                encoding="utf-8",
            )
            after = indexer.render_markdown(
                indexer.build_index_data(
                    repo_root,
                    source_roots=(Path("src"),),
                    test_roots=(Path("tests"),),
                ),
                source_roots=(Path("src"),),
                test_roots=(Path("tests"),),
            )

        self.assertEqual(before, after)

    def test_main_writes_index_and_check_detects_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            output_path = repo_root / "docs" / "source_test_file_index.md"
            (repo_root / "src").mkdir()
            (repo_root / "tests").mkdir()
            (repo_root / "src" / "module.py").write_text("one\n", encoding="utf-8")
            (repo_root / "tests" / "test_module.py").write_text("one\ntwo\n", encoding="utf-8")

            captured = io.StringIO()
            with redirect_stdout(captured):
                write_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--source-root",
                        "src",
                        "--test-root",
                        "tests",
                    ]
                )
            self.assertEqual(write_code, 0)
            self.assertIn("Wrote docs/source_test_file_index.md", captured.getvalue())
            markdown = output_path.read_text(encoding="utf-8")
            self.assertNotIn("| Lines |", markdown)
            self.assertIn("| `src/module.py` |", markdown)

            with redirect_stdout(io.StringIO()):
                check_code = indexer.main(
                    [
                        "--repo-root",
                        str(repo_root),
                        "--output",
                        str(output_path),
                        "--source-root",
                        "src",
                        "--test-root",
                        "tests",
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
                        "--source-root",
                        "src",
                        "--test-root",
                        "tests",
                        "--check",
                    ]
                )
            self.assertEqual(stale_code, 1)


if __name__ == "__main__":
    unittest.main()
