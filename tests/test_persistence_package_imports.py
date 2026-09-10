from __future__ import annotations

import subprocess
import sys
import unittest
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PersistencePackageImportTests(unittest.TestCase):
    def _run_python(self, script: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_graph_model_import_does_not_hit_persistence_cycle(self) -> None:
        result = self._run_python(
            "from ea_node_editor.graph.model import GraphModel; print(GraphModel.__name__)"
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout,
        )
        self.assertEqual(result.stdout.strip(), "GraphModel")

    def test_persistence_imports_use_concrete_modules(self) -> None:
        result = self._run_python(
            "from ea_node_editor.persistence.project_codec import JsonProjectCodec; "
            "from ea_node_editor.persistence.migration import JsonProjectMigration; "
            "from ea_node_editor.persistence.serializer import JsonProjectSerializer; "
            "from ea_node_editor.persistence.session_store import SessionAutosaveStore; "
            "from ea_node_editor.persistence.solution_repository import SolutionRepository; "
            "print(','.join(["
            "JsonProjectCodec.__name__, "
            "JsonProjectMigration.__name__, "
            "JsonProjectSerializer.__name__, "
            "SessionAutosaveStore.__name__, "
            "SolutionRepository.__name__]))"
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout,
        )
        self.assertEqual(
            result.stdout.strip(),
            "JsonProjectCodec,JsonProjectMigration,JsonProjectSerializer,SessionAutosaveStore,SolutionRepository",
        )

    def test_persistence_package_root_has_no_lazy_barrel(self) -> None:
        result = self._run_python(
            "import ea_node_editor.persistence as persistence; "
            "print(hasattr(persistence, '__getattr__')); "
            "print(getattr(persistence, '__all__', None))"
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout,
        )
        self.assertEqual(result.stdout.splitlines(), ["False", "[]"])
