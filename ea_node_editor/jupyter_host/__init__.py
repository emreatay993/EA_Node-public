"""Embedded Jupyter server host.

This package owns the lifecycle of the project-scoped Jupyter server that backs
the ``code.jupyter_notebook`` node, plus the lightweight availability probe used
by the scene-payload builder. The availability check is import-cheap and Qt-free
so it is safe to call on the payload-build thread and in headless tests; the
server manager (subprocess lifecycle) lives alongside it but is imported lazily.
"""

from __future__ import annotations

from ea_node_editor.jupyter_host.availability import (
    JupyterAvailability,
    check_jupyter_available,
    is_jupyter_available,
)

__all__ = [
    "JupyterAvailability",
    "check_jupyter_available",
    "is_jupyter_available",
]
