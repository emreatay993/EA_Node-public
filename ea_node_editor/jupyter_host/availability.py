"""Lazy Jupyter server-stack availability checks.

Mirrors ``ea_node_editor.web_host.webengine.check_webengine_available``: the
node always registers, but the surface degrades gracefully when the optional
Jupyter stack is not installed. Detection uses ``importlib.util.find_spec`` so
the (heavy) Jupyter modules are never imported just to answer "is it here?".
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

# The embedded server needs a server (``jupyter_server``), a single-document
# front-end (``notebook`` v7), and a kernel (``ipykernel``). All three must be
# importable for the live surface to come up.
_REQUIRED_JUPYTER_MODULES = ("jupyter_server", "notebook", "ipykernel")


@dataclass(frozen=True)
class JupyterAvailability:
    """Result of probing the optional embedded-Jupyter stack."""

    available: bool
    reason: str = ""
    module_name: str = ""

    def __bool__(self) -> bool:
        return self.available

    def as_payload(self) -> dict[str, bool | str]:
        """Return a UI-safe payload without importing the Jupyter stack."""

        return {
            "jupyter_available": bool(self.available),
            "jupyter_reason": str(self.reason or ""),
            "jupyter_module_name": str(self.module_name or ""),
        }


def check_jupyter_available() -> JupyterAvailability:
    """Probe the embedded-Jupyter stack and report missing pieces without raising."""

    for module_name in _REQUIRED_JUPYTER_MODULES:
        try:
            found = importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError) as exc:
            return JupyterAvailability(
                available=False,
                reason=str(exc),
                module_name=module_name,
            )
        if not found:
            return JupyterAvailability(
                available=False,
                reason=f"Required module '{module_name}' is not installed.",
                module_name=module_name,
            )
    return JupyterAvailability(available=True)


def is_jupyter_available() -> bool:
    """Return whether the optional embedded-Jupyter stack can be imported."""

    return check_jupyter_available().available


__all__ = [
    "JupyterAvailability",
    "check_jupyter_available",
    "is_jupyter_available",
]
