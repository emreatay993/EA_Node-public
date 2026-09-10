# Purpose: Declare COREX Reporting flowchart types and nodes.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_reporting_nodes.py

from __future__ import annotations

import html
import re
from types import MappingProxyType

from ea_node_editor.common.payload_tools import (
    INLINE_PAYLOAD_MAX_BYTES,
    copy_json_safe,
)
from ea_node_editor.nodes.core_data_types import (
    GRAPH_DATA_TYPE_ID,
)
from ea_node_editor.nodes.plugin_contracts import (
    PluginContractManifest,
)
from ea_node_editor.runtime_contracts import DataTypeSpec, TypedInlineValue


COREX_REPORTING_OWNER_ID = "corex.reporting"
COREX_REPORTING_OWNER_VERSION = "1"

FLOWCHART_NODE_DATA_TYPE_ID = "COREX.Reporting.FlowchartNode"
MARKDOWN_FLOWCHART_NODE_TYPE_ID = "reporting.markdown_flowchart_node"
MARKDOWN_FLOWCHART_TYPE_ID = "reporting.markdown_flowchart"


_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_PAYLOAD_KEYS = frozenset({"text", "input_nodes", "shape", "link_type", "link_text"})
_SAFE_MERMAID_LABEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSAFE_MERMAID_ID = re.compile(r"[^A-Za-z0-9_]")


def is_flowchart_node_payload(value: object) -> bool:
    if type(value) is not dict:
        return False
    try:
        copy_json_safe(
            value,
            field_name="flowchart node payload",
            max_encoded_bytes=INLINE_PAYLOAD_MAX_BYTES,
        )
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError):
        return False

    pending = [value]
    while pending:
        item = pending.pop()
        if (
            type(item) is not dict
            or len(item) != len(_PAYLOAD_KEYS)
            or any(type(key) is not str or key not in _PAYLOAD_KEYS for key in item)
        ):
            return False
        if type(item["text"]) is not str or type(item["link_text"]) is not str:
            return False
        if type(item["shape"]) is not int or not 0 <= item["shape"] <= 8:
            return False
        if type(item["link_type"]) is not int or not 0 <= item["link_type"] <= 3:
            return False
        children = item["input_nodes"]
        if type(children) is not list:
            return False
        if any(type(child) is not dict for child in children):
            return False
        pending.extend(children)
    return True


def _require_flowchart_node(value: object) -> dict[str, object]:
    if (
        type(value) is not TypedInlineValue
        or value.data_type_id != FLOWCHART_NODE_DATA_TYPE_ID
        or value.schema_version != 1
        or not is_flowchart_node_payload(value.payload)
    ):
        raise ValueError("Flowchart Node input is invalid")
    return value.payload


def make_flowchart_node_value(
    *,
    text: object,
    input_nodes: object = None,
    shape: object = 0,
    link_type: object = 0,
    link_text: object = "",
) -> TypedInlineValue:
    if type(text) is not str or type(link_text) is not str:
        raise ValueError("flowchart text inputs must be strings")
    if type(shape) is not int or not 0 <= shape <= 8:
        raise ValueError("flowchart shape must be an integer from 0 to 8")
    if type(link_type) is not int or not 0 <= link_type <= 3:
        raise ValueError("flowchart link type must be an integer from 0 to 3")
    children = [] if input_nodes is None else input_nodes
    if type(children) is not list:
        raise ValueError("flowchart input nodes must be a list")
    payload = {
        "text": text,
        "input_nodes": [_require_flowchart_node(child) for child in children],
        "shape": shape,
        "link_type": link_type,
        "link_text": link_text,
    }
    if not is_flowchart_node_payload(payload):
        raise ValueError("Flowchart Node payload is invalid")
    return TypedInlineValue(FLOWCHART_NODE_DATA_TYPE_ID, 1, payload)


def _escaped_mermaid_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return (
        html.escape(normalized, quote=True)
        .replace("|", "&#124;")
        .replace("\n", "<br/>")
    )


def _mermaid_label(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = _escaped_mermaid_text(text)
    return escaped if _SAFE_MERMAID_LABEL.fullmatch(normalized) else f'"{escaped}"'


def _mermaid_id_base(text: str) -> str:
    normalized = text.replace("\r\n", "_").replace("\r", "_").replace("\n", "_")
    result = _UNSAFE_MERMAID_ID.sub("_", normalized).strip("_") or "node"
    return f"node_{result}" if result[0].isdigit() else result


def render_flowchart(nodes: list[TypedInlineValue], direction: int) -> str:
    if type(direction) is not int or direction not in {0, 1}:
        raise ValueError("flowchart direction must be 0 or 1")
    payloads = [_require_flowchart_node(node) for node in nodes]
    allocated_ids: dict[str, str] = {}
    claimed_ids: dict[str, str] = {}
    lines: list[str] = []
    seen_lines: set[str] = set()

    def node_id(text: str) -> str:
        known = allocated_ids.get(text)
        if known is not None:
            return known
        base = _mermaid_id_base(text)
        candidate = base
        suffix = 2
        while candidate in claimed_ids and claimed_ids[candidate] != text:
            candidate = f"{base}_{suffix}"
            suffix += 1
        allocated_ids[text] = candidate
        claimed_ids[candidate] = text
        return candidate

    def expression(payload: dict[str, object]) -> str:
        text = payload["text"]
        shape = payload["shape"]
        identifier = node_id(text)
        label = _mermaid_label(text)
        if shape == 0 and label == text and identifier == text:
            return identifier
        wrappers = (
            ("[", "]"),
            ("(", ")"),
            ("([", "])"),
            ("[[", "]]"),
            ("[(", ")]"),
            ("((", "))"),
            (">", "]"),
            ("{", "}"),
            ("{{", "}}"),
        )
        opening, closing = wrappers[shape]
        return f"{identifier}{opening}{label}{closing}"

    def add_line(line: str) -> None:
        if line not in seen_lines:
            seen_lines.add(line)
            lines.append(line)

    def visit(payload: dict[str, object], *, top_level: bool) -> None:
        children = payload["input_nodes"]
        for child in children:
            visit(child, top_level=False)
            token = ("-->", "---", "-.->", "==>")[payload["link_type"]]
            label = payload["link_text"]
            if label:
                token += f"|{_escaped_mermaid_text(label)}|"
            add_line(f"{expression(child)} {token} {expression(payload)}")
        if top_level and not children:
            add_line(expression(payload))

    for payload in payloads:
        visit(payload, top_level=True)
    orientation = "TD" if direction == 0 else "LR"
    body = "\n".join(f"    {line}" for line in lines)
    separator = "\n" if body else ""
    return f"```mermaid\ngraph {orientation}{separator}{body}\n```\n"


COREX_REPORTING_DATA_TYPES = (
    DataTypeSpec(
        FLOWCHART_NODE_DATA_TYPE_ID,
        "Flowchart Node",
        "container",
        is_flowchart_node_payload,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="never",
        sensitivity="normal",
        payload_schema_version=1,
        implementation_version="1",
    ),
)


COREX_REPORTING_CONTRACT_MANIFEST = PluginContractManifest(
    data_types=COREX_REPORTING_DATA_TYPES,
)


__all__ = [
    "FLOWCHART_NODE_DATA_TYPE_ID",
    "MARKDOWN_FLOWCHART_NODE_TYPE_ID",
    "MARKDOWN_FLOWCHART_TYPE_ID",
    "COREX_REPORTING_CONTRACT_MANIFEST",
    "COREX_REPORTING_DATA_TYPES",
    "COREX_REPORTING_OWNER_ID",
    "COREX_REPORTING_OWNER_VERSION",
    "is_flowchart_node_payload",
    "make_flowchart_node_value",
    "render_flowchart",
]
