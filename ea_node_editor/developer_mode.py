from __future__ import annotations

import os

"""Developer-mode capability gate.

Developer mode lets engineers see full internal tracebacks (including host
frames) when a Python Script node fails, instead of the sanitized
script-only traceback end users get. It is double-gated:

1. Capability (ship-time): the ``COREX_DEV_MODE`` environment variable must be
   set to ``"1"`` when the process starts. Production builds ship without it,
   so the runtime toggle below can never turn developer mode on.
2. Activation (runtime): a hidden UI shortcut flips a per-session toggle, which
   only has any effect when the capability is enabled.

The variable is read once at import time so the gate cannot be flipped after
launch.
"""

_CAPABILITY_ENABLED = os.environ.get("COREX_DEV_MODE") == "1"


def developer_mode_capability_enabled() -> bool:
    """Return True when COREX_DEV_MODE was set at process start."""
    return _CAPABILITY_ENABLED
