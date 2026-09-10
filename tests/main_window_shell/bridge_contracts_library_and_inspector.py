from __future__ import annotations

import pytest

from tests.main_window_shell.bridge_support import (
    ShellInspectorBridgeTests as _ShellInspectorBridgeTests,
)
from tests.main_window_shell.bridge_support import (
    ShellLibraryBridgeTests as _ShellLibraryBridgeTests,
)

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")


class ShellLibraryBridgeTests(_ShellLibraryBridgeTests):
    __test__ = True


class ShellInspectorBridgeTests(_ShellInspectorBridgeTests):
    __test__ = True


__all__ = [
    "ShellLibraryBridgeTests",
    "ShellInspectorBridgeTests",
]
