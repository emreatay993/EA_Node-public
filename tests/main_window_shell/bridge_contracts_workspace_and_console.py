from __future__ import annotations

import pytest

from tests.main_window_shell.bridge_support import (
    SharedUiSupportBoundaryTests as _SharedUiSupportBoundaryTests,
)
from tests.main_window_shell.bridge_support import (
    ShellWorkspaceBridgeTests as _ShellWorkspaceBridgeTests,
)

pytestmark = pytest.mark.xdist_group("p03_bridge_contracts")


class SharedUiSupportBoundaryTests(_SharedUiSupportBoundaryTests):
    __test__ = True


class ShellWorkspaceBridgeTests(_ShellWorkspaceBridgeTests):
    __test__ = True


__all__ = [
    "SharedUiSupportBoundaryTests",
    "ShellWorkspaceBridgeTests",
]
