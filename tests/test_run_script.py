from __future__ import annotations

import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUN_SCRIPT = _REPO_ROOT / "scripts" / "run.sh"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_BOOTSTRAP = _REPO_ROOT / "ea_node_editor" / "bootstrap.py"


class RunScriptTests(unittest.TestCase):
    def test_run_script_launches_package_bootstrap(self) -> None:
        text = _RUN_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('PYTHON_BIN="${EA_NODE_EDITOR_PYTHON:-python}"', text)
        self.assertIn('exec "${PYTHON_BIN}" -m ea_node_editor.bootstrap "$@"', text)
        self.assertNotIn("main.py", text)

    def test_headless_runtime_console_script_uses_bootstrap_without_gui_app(self) -> None:
        text = _PYPROJECT.read_text(encoding="utf-8")
        bootstrap_text = _BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn('corex-runtime = "ea_node_editor.bootstrap:headless_main"', text)
        self.assertIn('def headless_main() -> int:', bootstrap_text)
        self.assertIn('"ea_node_editor.execution.runtime_cli"', bootstrap_text)


if __name__ == "__main__":
    unittest.main()
