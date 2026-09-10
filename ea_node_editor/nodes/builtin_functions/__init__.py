# Purpose: Aggregate inert decorated built-in source without importing callables.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_builtin_function_infrastructure.py

from __future__ import annotations

from ea_node_editor.nodes.builtin_functions import (
    ai_agent,
    ai_vector_database,
    core_value,
    data_control,
    engineering_fem,
    engineering_geometry,
    engineering_imports,
    engineering_viewer,
    filesystem,
    integrations_email,
    integrations_file_io,
    integrations_process,
    integrations_spreadsheet,
    integrations_ssh_sftp,
    plot_signal,
    reporting,
    rich_values,
    security,
    spatial,
    unit_math,
    viewer_viewport,
)


def source_modules() -> tuple[tuple[str, str], ...]:
    """Return fixed bundle members; family writers only replace SOURCE strings."""

    return (
        ("core_value.py", core_value.SOURCE),
        ("unit_math.py", unit_math.SOURCE),
        ("spatial.py", spatial.SOURCE),
        ("plot_signal.py", plot_signal.SOURCE),
        ("integrations_file_io.py", integrations_file_io.SOURCE),
        ("integrations_process.py", integrations_process.SOURCE),
        ("integrations_email.py", integrations_email.SOURCE),
        ("integrations_spreadsheet.py", integrations_spreadsheet.SOURCE),
        ("integrations_ssh_sftp.py", integrations_ssh_sftp.SOURCE),
        ("data_control.py", data_control.SOURCE),
        ("engineering_imports.py", engineering_imports.SOURCE),
        ("engineering_viewer.py", engineering_viewer.SOURCE),
        ("filesystem.py", filesystem.SOURCE),
        ("viewer_viewport.py", viewer_viewport.SOURCE),
        ("engineering_geometry.py", engineering_geometry.SOURCE),
        ("engineering_fem.py", engineering_fem.SOURCE),
        ("ai_vector_database.py", ai_vector_database.SOURCE),
        ("ai_agent.py", ai_agent.SOURCE),
        ("reporting.py", reporting.SOURCE),
        ("security.py", security.SOURCE),
        ("rich_values.py", rich_values.SOURCE),
    )


__all__ = ["source_modules"]
