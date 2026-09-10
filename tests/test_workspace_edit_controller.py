# Purpose: Direct owner tests for workspace edits, clipboard, history, and mutation aftermath.
# Map: feature_routes/clipboard_undo_redo_mutation_history
# Tests: tests/test_workspace_edit_controller.py
from tests.workspace_controller_suites import (
    WorkspaceDirectControllerCompositionTests,
    WorkspaceEditControllerEffectsTests,
)
from tests.workspace_controller_unit.core_ops import (
    WorkspaceEditControllerCoreTests,
    WorkspaceEditControllerNodeChangeTests,
)

__all__ = [
    "WorkspaceDirectControllerCompositionTests",
    "WorkspaceEditControllerCoreTests",
    "WorkspaceEditControllerEffectsTests",
    "WorkspaceEditControllerNodeChangeTests",
]
