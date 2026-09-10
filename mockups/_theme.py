"""Shared theme + faithful demo data for the COREX node-creation-wizard mockups.

Every mockup loads COREX's *real* stylesheet so the look-and-feel is identical to
the shipped app. Nothing here mutates app state -- the mockups are visual only.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

# --- make `ea_node_editor` importable when run as `python mockups/run_all.py` ---
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ea_node_editor.ui.theme.registry import resolve_theme_tokens  # noqa: E402
from ea_node_editor.ui.theme.styles import build_theme_stylesheet  # noqa: E402

THEME_ID = "stitch_dark"
APP_NAME = "COREX Node Editor"

# Real default body for a Python Script node (from PYTHON_SCRIPT_CREATION_PROFILE).
PYTHON_SCRIPT_DEFAULT_SOURCE = (
    "# input_data is provided by the engine\n"
    "# Set output_data to publish result\n"
    "output_data = input_data\n"
)


def tokens():
    """Resolved stitch_dark ThemeTokens (exact hex values used by the app)."""
    return resolve_theme_tokens(THEME_ID)


def apply_corex_theme(app) -> None:
    """Apply the real COREX stylesheet, app name and window icon to a QApplication."""
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(build_theme_stylesheet(THEME_ID))
    try:  # icon assets are optional for a mockup -- never block on them
        from ea_node_editor.ui.app_icon import apply_application_icon

        apply_application_icon(app)
    except Exception:
        pass


def apply_window_icon(window) -> None:
    try:
        from ea_node_editor.ui.app_icon import apply_window_icon as _aw

        _aw(window)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Faithful node-creation content (mirrors the real WizardSpec / PortSpec model)
# --------------------------------------------------------------------------- #

PORT_EXEC = "exec"
PORT_DATA = "data"


@dataclass
class Port:
    key: str
    kind: str = PORT_DATA          # "exec" | "data"
    data_type: str = "any"
    required: bool = False


@dataclass
class WizField:
    """One wizard input -- mirrors ea_node_editor WizardInputSpec."""

    key: str
    label: str
    kind: str                       # string|category_path|port_list|python_source|enum|bool|path
    default: object = ""
    required: bool = False
    options: tuple = ()             # for enum
    help: str = ""


@dataclass
class FlowSpec:
    """A complete creation scenario the mockups render."""

    flow_id: str
    title: str
    subtitle: str
    icon_glyph: str                 # simple glyph stand-in for the real SVG icon
    fields: list = field(default_factory=list)
    preview_inputs: tuple = (Port("payload"),)
    preview_outputs: tuple = (Port("result"),)


# Real fields of PYTHON_SCRIPT_CREATION_PROFILE (ea_node_editor/nodes/builtins/core.py:281)
def python_script_flow() -> FlowSpec:
    return FlowSpec(
        flow_id="python",
        title="Python Script Node",
        subtitle="Custom › Python",
        icon_glyph="{ }",
        fields=[
            WizField("node_name", "Name", "string", "", required=True,
                     help="User-facing node title. Required."),
            WizField("category_path", "Category", "category_path", ("Custom", "Python"),
                     help="Where the node appears in the library tree."),
            WizField("input_ports", "Inputs", "port_list", (Port("payload"),),
                     help="Input ports exposed by the generated node."),
            WizField("output_ports", "Outputs", "port_list", (Port("result"),),
                     help="Output ports the node publishes."),
            WizField("source_template", "Initial Source", "python_source",
                     PYTHON_SCRIPT_DEFAULT_SOURCE, required=True,
                     help="Initial Python body. input_data in, output_data out."),
        ],
        preview_inputs=(Port("payload"),),
        preview_outputs=(Port("result"),),
    )


# Representative real built-in node templates (ea_node_editor/nodes/builtins/*).
GENERIC_TEMPLATES = [
    {
        "type_id": "core.python_script", "name": "Python Script", "category": ("Core",),
        "glyph": "{ }", "desc": "Script-backed node running a Python body.",
        "inputs": [Port("exec_in", PORT_EXEC, "exec", True), Port("payload")],
        "outputs": [Port("result"), Port("exec_out", PORT_EXEC, "exec"),
                    Port("on_failed", PORT_EXEC, "exec")],
    },
    {
        "type_id": "core.branch", "name": "If / Else Branch", "category": ("Core",),
        "glyph": "<>", "desc": "Routes execution by a boolean condition.",
        "inputs": [Port("exec_in", PORT_EXEC, "exec", True), Port("condition", PORT_DATA, "bool")],
        "outputs": [Port("true_out", PORT_EXEC, "exec"), Port("false_out", PORT_EXEC, "exec")],
    },
    {
        "type_id": "core.logger", "name": "Logger", "category": ("Core",),
        "glyph": "::", "desc": "Logs a message and passes execution through.",
        "inputs": [Port("exec_in", PORT_EXEC, "exec", True), Port("message")],
        "outputs": [Port("message"), Port("exec_out", PORT_EXEC, "exec")],
    },
    {
        "type_id": "core.constant", "name": "Constant", "category": ("Core",),
        "glyph": "=", "desc": "Emits a fixed value.",
        "inputs": [],
        "outputs": [Port("value"), Port("as_text", PORT_DATA, "str")],
    },
    {
        "type_id": "core.start", "name": "Start", "category": ("Core",),
        "glyph": "▶", "desc": "Graph entry point.",
        "inputs": [],
        "outputs": [Port("exec_out", PORT_EXEC, "exec"), Port("trigger", PORT_EXEC, "exec")],
    },
    {
        "type_id": "engineering.fe_import", "name": "FE Import", "category": ("Engineering", "Import"),
        "glyph": "⊙", "desc": "Imports a neutral finite-element file as a prepared COREX scene.",
        "inputs": [Port("path", PORT_DATA, "COREX.DataTypes.Path", True)],
        "outputs": [Port("scene", PORT_DATA, "COREX.Engineering.Scene")],
    },
    {
        "type_id": "integrations.file_io.read", "name": "Read File",
        "category": ("Integrations", "File IO"), "glyph": "↓",
        "desc": "Reads a file from disk.",
        "inputs": [Port("exec_in", PORT_EXEC, "exec", True), Port("path", PORT_DATA, "str", True)],
        "outputs": [Port("content", PORT_DATA, "str"), Port("exec_out", PORT_EXEC, "exec")],
    },
    {
        "type_id": "flowchart.process", "name": "Process (Flowchart)",
        "category": ("Flowchart",), "glyph": "▭", "desc": "Passive flowchart shape.",
        "inputs": [Port("in", PORT_DATA, "flow")],
        "outputs": [Port("out", PORT_DATA, "flow")],
    },
]


def generic_flow(template: dict | None = None) -> FlowSpec:
    """A generic custom-node scenario, optionally seeded from a chosen template."""
    tpl = template or GENERIC_TEMPLATES[0]
    cat = " › ".join(tpl["category"])
    return FlowSpec(
        flow_id="generic",
        title=f"New {tpl['name']}",
        subtitle=cat,
        icon_glyph=tpl["glyph"],
        fields=[
            WizField("display_name", "Display Name", "string", f"My {tpl['name']}",
                     required=True, help="User-facing node title. Required."),
            WizField("category_path", "Category", "category_path", tpl["category"],
                     help="Library tree placement."),
            WizField("icon", "Icon", "string", "core/code.svg",
                     help="SVG icon path relative to the theme icon set."),
            WizField("description", "Description", "string", tpl["desc"],
                     help="Tooltip / help text shown in the library."),
            WizField("input_ports", "Input Ports", "port_list", tuple(tpl["inputs"]),
                     help="PortSpec list: key, kind (exec/data), data_type, required."),
            WizField("output_ports", "Output Ports", "port_list", tuple(tpl["outputs"]),
                     help="PortSpec list the node publishes."),
            WizField("runtime_behavior", "Runtime", "enum", "active",
                     options=("active", "passive", "compile_only"),
                     help="active executes, passive is visual-only, compile_only stages."),
            WizField("surface_family", "Surface", "enum", "standard",
                     options=("standard", "flowchart", "planning", "annotation",
                              "group_backdrop", "media", "viewer"),
                     help="Visual rendering family for the node chrome."),
        ],
        preview_inputs=tuple(tpl["inputs"]) or (Port("in"),),
        preview_outputs=tuple(tpl["outputs"]) or (Port("out"),),
    )


# Wizard step grouping shared by the stepped + sidebar designs.
def steps_for(flow: FlowSpec) -> list[tuple[str, list[WizField]]]:
    """Group a flow's fields into named wizard steps/sections."""
    by_key = {f.key: f for f in flow.fields}
    if flow.flow_id == "python":
        return [
            ("Identity", [by_key["node_name"], by_key["category_path"]]),
            ("Ports", [by_key["input_ports"], by_key["output_ports"]]),
            ("Source", [by_key["source_template"]]),
        ]
    return [
        ("Identity", [by_key["display_name"], by_key["category_path"],
                      by_key["icon"], by_key["description"]]),
        ("Ports", [by_key["input_ports"], by_key["output_ports"]]),
        ("Behavior", [by_key["runtime_behavior"], by_key["surface_family"]]),
    ]
