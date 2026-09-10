"""Notebook file helpers for the embedded Jupyter host.

Kept separate from ``availability`` (which must stay import-cheap for the
payload path) because creating a blank notebook imports ``nbformat``. The
import is lazy so merely importing this module does not pull in nbformat.
"""

from __future__ import annotations

from pathlib import Path


def create_blank_notebook(path: str | Path, *, kernel_name: str = "") -> Path:
    """Write a minimal valid v4 notebook (one empty code cell) at ``path``."""

    import nbformat  # lazy: only needed when actually creating a notebook

    notebook = nbformat.v4.new_notebook()
    notebook.cells = [nbformat.v4.new_code_cell("")]
    kernel = str(kernel_name or "").strip()
    if kernel:
        notebook.metadata["kernelspec"] = {"name": kernel, "display_name": kernel}

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        nbformat.write(notebook, handle)
    return target


def relative_to_server_root(abs_path: str | Path, server_root: str | Path) -> str:
    """Return ``abs_path`` as a POSIX path relative to ``server_root``.

    Returns "" when the notebook is not located under the server root (the
    embedded server can only address files beneath its ``root_dir``).
    """

    try:
        resolved_path = Path(abs_path).resolve()
        resolved_root = Path(server_root).resolve()
    except OSError:
        return ""
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return ""


__all__ = [
    "create_blank_notebook",
    "relative_to_server_root",
]
