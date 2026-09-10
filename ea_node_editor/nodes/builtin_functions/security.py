# Purpose: Hold inert decorated source for Windows authentication.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_security_contracts.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.security_contracts import (
    execute_windows_authentication,
)


@corex.node(
    id="security.windows_authentication",
    name="Windows Authentication",
    category=("Security",),
    icon="badge",
    description="Creates a run-scoped Windows identity reference.",
    keywords=("windows", "authentication", "identity", "user"),
)
@corex.output(
    "authentication",
    value_type="COREX.DataTypes.WindowsIdentity",
    label="Authentication",
    description="Run-scoped Windows identity reference.",
)
@corex.output(
    "current_user",
    value_type="COREX.DataTypes.String",
    label="Current user",
    description="Current Windows user name.",
)
def windows_authentication(ctx):
    return execute_windows_authentication(ctx)
"""

__all__ = ["SOURCE"]
