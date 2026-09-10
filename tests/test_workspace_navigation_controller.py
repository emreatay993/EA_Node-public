# Purpose: Direct owner tests for workspace/view navigation, search, framing, and focus.
# Map: feature_routes/workspace_tabs_library_context_menus
# Tests: tests/test_workspace_navigation_controller.py
from tests.workspace_controller_suites import (
    ProjectSessionWorkspaceSurfaceTests,
    WorkspaceNavigationControllerCloseViewTests,
    WorkspaceNavigationControllerCreationTests,
    WorkspaceViewNavOpsMutationServiceTests,
)
from tests.workspace_controller_unit.core_ops import (
    WorkspaceNavigationControllerCoreTests,
)

__all__ = [
    "ProjectSessionWorkspaceSurfaceTests",
    "WorkspaceNavigationControllerCloseViewTests",
    "WorkspaceNavigationControllerCoreTests",
    "WorkspaceNavigationControllerCreationTests",
    "WorkspaceViewNavOpsMutationServiceTests",
]
