from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type
from collections.abc import Mapping
from typing import Any

from ea_node_editor.nodes.builtins.passive_flow_ports import CARDINAL_PASSIVE_FLOW_PORTS
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.file_dialog_filters import NOTEBOOK_FILES_FILTER
from ea_node_editor.nodes.node_specs import PropertySpec

JUPYTER_NOTEBOOK_CATEGORY = "Code"
JUPYTER_NOTEBOOK_TYPE_ID = "code.jupyter_notebook"
JUPYTER_NOTEBOOK_SURFACE_FAMILY = "jupyter"
JUPYTER_NOTEBOOK_SURFACE_VARIANT = "notebook"

JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY = "notebook_ref"
JUPYTER_NOTEBOOK_KERNEL_NAME_PROPERTY = "kernel_name"
JUPYTER_NOTEBOOK_FRONTEND_PROPERTY = "frontend"
JUPYTER_NOTEBOOK_AUTOSTART_PROPERTY = "autostart"
JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY = "server_state"
JUPYTER_NOTEBOOK_SHOW_TITLE_PROPERTY = "show_title"
JUPYTER_NOTEBOOK_SHOW_FRAME_PROPERTY = "show_frame"
JUPYTER_NOTEBOOK_PREVIEW_REF_PROPERTY = "preview_ref"

JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK = "notebook"
JUPYTER_NOTEBOOK_FRONTEND_LAB = "lab"
JUPYTER_NOTEBOOK_FRONTENDS = (
    JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK,
    JUPYTER_NOTEBOOK_FRONTEND_LAB,
)

# Connection/secret keys are never written to the project document. The live
# server URL, token, and port are rebuilt at runtime for each session (see the
# jupyter_host server manager), so persisting them would only leak secrets and
# point a reopened project at a dead port.
_JUPYTER_NOTEBOOK_FORBIDDEN_SERVER_STATE_KEYS = frozenset(
    {
        "token",
        "url",
        "base_url",
        "port",
        "password",
        "host",
        "hostname",
        "cookie",
        "cookies",
        "xsrf",
        "authorization",
    }
)


def normalize_jupyter_notebook_frontend(value: Any) -> str:
    normalized = str(value or JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK).strip().lower()
    return normalized if normalized in JUPYTER_NOTEBOOK_FRONTENDS else JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK


def sanitize_jupyter_notebook_server_state(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text.strip().lower() in _JUPYTER_NOTEBOOK_FORBIDDEN_SERVER_STATE_KEYS:
            continue
        sanitized[key_text] = item
    return sanitized


def normalize_jupyter_notebook_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY,
        JUPYTER_NOTEBOOK_KERNEL_NAME_PROPERTY,
        JUPYTER_NOTEBOOK_FRONTEND_PROPERTY,
        JUPYTER_NOTEBOOK_AUTOSTART_PROPERTY,
        JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY,
        JUPYTER_NOTEBOOK_SHOW_TITLE_PROPERTY,
        JUPYTER_NOTEBOOK_SHOW_FRAME_PROPERTY,
        JUPYTER_NOTEBOOK_PREVIEW_REF_PROPERTY,
    }
    normalized = {
        str(key): item
        for key, item in properties.items()
        if str(key) in allowed_keys
    }
    normalized[JUPYTER_NOTEBOOK_FRONTEND_PROPERTY] = normalize_jupyter_notebook_frontend(
        normalized.get(JUPYTER_NOTEBOOK_FRONTEND_PROPERTY)
    )
    normalized[JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY] = sanitize_jupyter_notebook_server_state(
        normalized.get(JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY, {})
    )
    return normalized


class _JupyterNotebookNodePlugin:
    def execute(self, _ctx: ExecutionContext) -> NodeResult:
        return NodeResult(outputs={})


@builtin_node_type(
    type_id=JUPYTER_NOTEBOOK_TYPE_ID,
    display_name="Jupyter Notebook",
    category_path=(JUPYTER_NOTEBOOK_CATEGORY,),
    description="Interactive Jupyter notebook hosted on the canvas via an embedded local kernel server.",
    keywords=("jupyter", "notebook", "python"),
    ports=CARDINAL_PASSIVE_FLOW_PORTS,
    properties=(
        PropertySpec(
            JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY,
            "str",
            "",
            "Notebook",
            inspector_editor="path",
            group="Source",
            file_filter=NOTEBOOK_FILES_FILTER,
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_KERNEL_NAME_PROPERTY,
            "str",
            "",
            "Kernel",
            group="Kernel",
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_FRONTEND_PROPERTY,
            "enum",
            JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK,
            "Front-End",
            enum_values=JUPYTER_NOTEBOOK_FRONTENDS,
            inspector_editor="enum",
            group="Display",
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_AUTOSTART_PROPERTY,
            "bool",
            True,
            "Auto-start Kernel",
            group="Kernel",
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY,
            "json",
            {},
            "Server State",
            inspector_visible=False,
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_SHOW_TITLE_PROPERTY,
            "bool",
            True,
            "Show Title",
            inspector_visible=False,
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_SHOW_FRAME_PROPERTY,
            "bool",
            True,
            "Show Frame",
            inspector_visible=False,
        ),
        PropertySpec(
            JUPYTER_NOTEBOOK_PREVIEW_REF_PROPERTY,
            "json",
            {},
            "Preview Reference",
            inspector_visible=False,
        ),
    ),
    collapsible=False,
    runtime_behavior="passive",
    surface_family=JUPYTER_NOTEBOOK_SURFACE_FAMILY,
    surface_variant=JUPYTER_NOTEBOOK_SURFACE_VARIANT,
    render_quality={
        "supported_quality_tiers": ["full", "proxy"],
    },
)
class JupyterNotebookNodePlugin(_JupyterNotebookNodePlugin):
    pass


JUPYTER_NOTEBOOK_NODE_PLUGINS = (JupyterNotebookNodePlugin,)
JUPYTER_NOTEBOOK_NODE_DESCRIPTORS = tuple(
    plugin_descriptor(plugin)
    for plugin in JUPYTER_NOTEBOOK_NODE_PLUGINS
)


__all__ = [
    "JUPYTER_NOTEBOOK_AUTOSTART_PROPERTY",
    "JUPYTER_NOTEBOOK_CATEGORY",
    "JUPYTER_NOTEBOOK_FRONTEND_LAB",
    "JUPYTER_NOTEBOOK_FRONTEND_NOTEBOOK",
    "JUPYTER_NOTEBOOK_FRONTEND_PROPERTY",
    "JUPYTER_NOTEBOOK_FRONTENDS",
    "JUPYTER_NOTEBOOK_KERNEL_NAME_PROPERTY",
    "JUPYTER_NOTEBOOK_NODE_DESCRIPTORS",
    "JUPYTER_NOTEBOOK_NODE_PLUGINS",
    "JUPYTER_NOTEBOOK_NOTEBOOK_REF_PROPERTY",
    "JUPYTER_NOTEBOOK_PREVIEW_REF_PROPERTY",
    "JUPYTER_NOTEBOOK_SERVER_STATE_PROPERTY",
    "JUPYTER_NOTEBOOK_SHOW_FRAME_PROPERTY",
    "JUPYTER_NOTEBOOK_SHOW_TITLE_PROPERTY",
    "JUPYTER_NOTEBOOK_SURFACE_FAMILY",
    "JUPYTER_NOTEBOOK_SURFACE_VARIANT",
    "JUPYTER_NOTEBOOK_TYPE_ID",
    "JupyterNotebookNodePlugin",
    "normalize_jupyter_notebook_frontend",
    "normalize_jupyter_notebook_properties",
    "sanitize_jupyter_notebook_server_state",
]
