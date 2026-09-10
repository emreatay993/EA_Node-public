from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from ea_node_editor.jupyter_host import is_jupyter_available
from ea_node_editor.jupyter_host.notebook_files import (
    create_blank_notebook,
    relative_to_server_root,
)
from ea_node_editor.jupyter_host.server_manager import (
    JupyterServerHandle,
    JupyterServerManager,
    JupyterServerRegistry,
)


class JupyterServerHandleUrlTests(unittest.TestCase):
    """Pure URL formatting -- no server required."""

    def test_notebook_frontend_targets_single_document_with_token(self) -> None:
        handle = JupyterServerHandle(base_url="http://127.0.0.1:8123", token="tok en/+", port=8123)

        url = handle.notebook_url(relative_path="jupyter/notebooks/Node 1/analysis.ipynb")

        self.assertTrue(url.startswith("http://127.0.0.1:8123/notebooks/"))
        self.assertIn("analysis.ipynb", url)
        self.assertIn(f"token={quote('tok en/+')}", url)
        # The space/slash in the relative path must be percent-encoded.
        self.assertNotIn(" ", url)

    def test_lab_frontend_uses_doc_tree_route(self) -> None:
        handle = JupyterServerHandle(base_url="http://127.0.0.1:8123", token="abc", port=8123)

        url = handle.notebook_url(relative_path="x.ipynb", frontend="lab")

        self.assertTrue(url.startswith("http://127.0.0.1:8123/doc/tree/x.ipynb"))
        self.assertIn("token=abc", url)


@unittest.skipUnless(is_jupyter_available(), "embedded Jupyter stack not installed")
class JupyterServerManagerIntegrationTests(unittest.TestCase):
    """Live server lifecycle -- starts a real jupyter_server subprocess."""

    def test_server_starts_serves_status_and_shuts_down_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = JupyterServerManager(server_root=Path(temp_dir))
            try:
                handle = manager.ensure_running()
                self.assertTrue(manager.is_running())
                self.assertTrue(handle.base_url.startswith("http://127.0.0.1:"))
                self.assertGreater(handle.port, 0)
                self.assertTrue(handle.token)

                # The status endpoint must answer 200 for the issued token.
                status_url = f"{handle.base_url}/api/status?token={quote(handle.token)}"
                request = urllib.request.Request(
                    status_url, headers={"Authorization": f"token {handle.token}"}
                )
                with urllib.request.urlopen(request, timeout=5.0) as response:
                    self.assertEqual(int(response.status), 200)

                # ensure_running is idempotent: same handle, same process.
                self.assertIs(manager.ensure_running(), handle)
            finally:
                process = manager._process  # noqa: SLF001 - test asserts no orphan remains
                manager.shutdown()

            self.assertFalse(manager.is_running())
            self.assertIsNotNone(process)
            self.assertIsNotNone(process.poll())  # process actually exited

            # The port is no longer served after shutdown.
            with self.assertRaises((urllib.error.URLError, OSError)):
                urllib.request.urlopen(status_url, timeout=2.0)  # noqa: S310 - loopback only

    def test_registry_reuses_manager_per_root_and_shutdown_all_is_clean(self) -> None:
        registry = JupyterServerRegistry()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager_a = registry.manager_for(root)
            manager_b = registry.manager_for(root)
            self.assertIs(manager_a, manager_b)

            manager_a.ensure_running()
            self.assertTrue(manager_a.is_running())

            registry.shutdown_all()
            self.assertFalse(manager_a.is_running())

    def test_server_serves_blank_project_notebook_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            notebook_path = root / "jupyter" / "notebooks" / "analysis.ipynb"
            create_blank_notebook(notebook_path)
            relative_path = relative_to_server_root(notebook_path, root)
            self.assertEqual(relative_path, "jupyter/notebooks/analysis.ipynb")

            manager = JupyterServerManager(server_root=root)
            try:
                handle = manager.ensure_running()
                contents_url = (
                    f"{handle.base_url}/api/contents/{quote(relative_path)}"
                    f"?token={quote(handle.token)}"
                )
                request = urllib.request.Request(
                    contents_url, headers={"Authorization": f"token {handle.token}"}
                )
                with urllib.request.urlopen(request, timeout=5.0) as response:
                    self.assertEqual(int(response.status), 200)
                    body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(body["type"], "notebook")
                self.assertEqual(body["name"], "analysis.ipynb")
            finally:
                manager.shutdown()


class NotebookFileHelperTests(unittest.TestCase):
    def test_relative_to_server_root_handles_outside_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            inside = root / "a" / "b.ipynb"
            self.assertEqual(relative_to_server_root(inside, root), "a/b.ipynb")
            outside = Path(temp_dir) / "elsewhere" / "c.ipynb"
            self.assertEqual(relative_to_server_root(outside, root), "")

    @unittest.skipUnless(is_jupyter_available(), "embedded Jupyter stack not installed")
    def test_create_blank_notebook_writes_valid_v4_document(self) -> None:
        import nbformat

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "blank.ipynb"
            created = create_blank_notebook(path, kernel_name="python3")
            self.assertTrue(created.is_file())
            notebook = nbformat.read(str(created), as_version=4)
            self.assertEqual(notebook.nbformat, 4)
            self.assertEqual(len(notebook.cells), 1)
            self.assertEqual(notebook.metadata["kernelspec"]["name"], "python3")


if __name__ == "__main__":
    unittest.main()
