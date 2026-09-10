"""Windowless shell composition and Qt Quick host policy tests."""

from tests.shell_window_lifecycle_support import (
    test_qtquick_backend_override_accepts_auto_and_rejects_unknown,
    test_qtquick_backend_override_selection_preserves_offscreen_software,
    test_shell_composition_uses_explicit_feature_owned_bundles,
    test_shell_workspace_manager_adapter_exposes_only_workspace_and_view_surface,
    test_windows_desktop_keeps_qquickwidget_default_and_d3d11_backend,
)

__all__ = [name for name in globals() if name.startswith("test_")]
