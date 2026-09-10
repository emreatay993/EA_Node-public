# Purpose: Hold inert decorated source for the Process Run integration.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_process_run_node.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.integrations_process import execute_process_run


@corex.node(
    id="io.process_run",
    name="Process Run",
    category=("Input / Output",),
    icon="integrations/terminal.svg",
    description="Executes an external command and captures stdout/stderr.",
    keywords=("process", "command", "subprocess"),
)
@corex.text(
    "command",
    default="",
    label="Command",
    port=True,
    _inline_editor="",
    _port_description="Executable or shell command; overrides the configured Command property.",
    _port_label="",
    _port_required=True,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.String",
)
@corex.text(
    "args",
    default="",
    label="Args",
    port=True,
    _inline_editor="",
    _property_default=[],
    _property_type="json",
    _port_description="Argument list passed to the command.",
    _port_label="",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.StringList",
)
@corex.input(
    "stdin_text",
    value_type="COREX.DataTypes.String",
    structure="tree",
    required=False,
    label="",
    description="Optional text written to the process standard input.",
)
@corex.output(
    "stdout",
    value_type=corex.Any,
    label="",
    description="Text captured from standard output, or a stored transcript reference.",
)
@corex.output(
    "stderr",
    value_type=corex.Any,
    label="",
    description="Text captured from standard error, or a stored transcript reference.",
)
@corex.output(
    "exit_code",
    value_type=int,
    label="",
    description="Numeric process exit code.",
)
@corex.dropdown(
    "output_mode",
    default="memory",
    options=("memory", "stored"),
    label="Output Mode",
)
@corex.path(
    "cwd",
    default="",
    label="Working Directory",
    _inline_editor="",
)
@corex.text(
    "env",
    default="",
    label="Environment",
    _inline_editor="",
    _property_default={},
    _property_type="json",
)
@corex.number(
    "timeout_sec",
    default=60.0,
    label="Timeout (sec)",
    _inline_editor="",
)
@corex.number(
    "termination_grace_sec",
    default=0.6,
    label="Termination Grace (sec)",
    _inline_editor="",
)
@corex.number(
    "core_hint",
    default=0,
    label="Core Hint",
    _inline_editor="",
)
@corex.number(
    "thread_hint",
    default=0,
    label="Thread Hint",
    _inline_editor="",
)
@corex.number(
    "memory_mb_hint",
    default=0,
    label="Memory Hint (MB)",
    _inline_editor="",
)
@corex.switch(
    "shell",
    default=False,
    label="Use Shell",
    _inline_editor="",
)
@corex.switch(
    "fail_on_nonzero",
    default=True,
    label="Fail on Non-zero",
    _inline_editor="",
)
@corex.text(
    "encoding",
    default="utf-8",
    label="Encoding",
    _inline_editor="",
)
def process_run(ctx, stdin_text, settings):
    result = execute_process_run(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="process_run")
    return dict(result.outputs)
"""

__all__ = ["SOURCE"]
