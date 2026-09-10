from __future__ import annotations

import json
from unittest import mock

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory
from ea_node_editor.ui.shell.inspector_projection import (
    build_selected_node_property_items,
)
from ea_node_editor.ui_qml.graph_scene_bridge import GraphSceneBridge
from ea_node_editor.ui_qml.graph_scene_payload.builder import GraphScenePayloadBuilder
import ea_node_editor.ui_qml.graph_scene_mutation.selection_and_scope_ops as selection_ops
from ea_node_editor.ui_qml.shell_inspector_bridge import ShellInspectorBridge


_CIPHERTEXT = "opaque-ciphertext"
_ENVELOPE = {
    "schema": "corex.protected_secret.v1",
    "provider": "windows_dpapi",
    "scope": "CurrentUser",
    "ciphertext_b64": _CIPHERTEXT,
}


class _SensitiveNode:
    def spec(self) -> NodeTypeSpec:
        return NodeTypeSpec(
            type_id="tests.sensitive_controls",
            display_name="Sensitive Controls",
            category_path=("Tests",),
            icon="",
            ports=(PortSpec("value", "out", "data", 'COREX.DataTypes.Any'),),
            properties=(
                PropertySpec(
                    "scope",
                    "enum",
                    "Current user",
                    "Scope",
                    enum_values=("Current user", "All users on this machine"),
                    inline_editor="enum",
                ),
                PropertySpec(
                    "protected_value",
                    "json",
                    {},
                    "Value",
                    description="Stored with Windows data protection.",
                    inspector_editor="secret",
                    sensitive=True,
                    sensitive_scope_key="scope",
                ),
            ),
        )

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _scene(*, protected_value=None):
    registry = NodeRegistry()
    registry.register(_SensitiveNode)
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "tests.sensitive_controls",
        "Sensitive Controls",
        0.0,
        0.0,
        properties={
            "scope": "Current user",
            "protected_value": (
                dict(_ENVELOPE) if protected_value is None else protected_value
            ),
        },
    )
    return registry, model, workspace, node


def test_sensitive_scene_and_inspector_projections_never_publish_envelope() -> None:
    registry, model, workspace, node = _scene()
    builder = GraphScenePayloadBuilder()
    node_payloads, _backdrops, _minimap, _edges = builder.rebuild_partitioned_models(
        model=model,
        registry=registry,
        workspace_id=workspace.workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )
    payload = next(item for item in node_payloads if item["node_id"] == node.node_id)
    expected_state = {"has_value": True, "scope": "CurrentUser"}
    assert payload["properties"]["protected_value"] == expected_state
    assert all(
        item["key"] != "protected_value" for item in payload["inline_properties"]
    )

    inspector = build_selected_node_property_items(
        node=node,
        spec=registry.get_spec(node.type_id),
        subnode_pin_type_ids=set(),
        workspace_id=workspace.workspace_id,
        workspace_nodes=workspace.nodes,
        workspace_edges=workspace.edges,
        property_edit_adapters=(),
    )
    secret_item = next(item for item in inspector if item["key"] == "protected_value")
    assert secret_item["value"] == expected_state
    assert secret_item["display_value"] == expected_state
    assert secret_item["editor_mode"] == "secret"
    assert secret_item["help_text"] == "Stored with Windows data protection."

    projected = json.dumps({"scene": payload, "inspector": inspector}, default=str)
    assert _CIPHERTEXT not in projected
    assert "ciphertext_b64" not in projected


def test_secret_replace_clear_and_scope_reprotect_are_history_safe() -> None:
    registry, model, workspace, node = _scene(protected_value={})
    scene = GraphSceneBridge()
    history = RuntimeGraphHistory()
    scene.set_workspace(model, registry, workspace.workspace_id)
    scene.bind_runtime_history(history)
    plaintext = "plaintext-must-not-enter-history"

    with mock.patch.object(
        selection_ops,
        "protect_secret",
        return_value=dict(_ENVELOPE),
    ):
        assert scene.set_node_secret(node.node_id, "protected_value", plaintext)

    assert node.properties["protected_value"] == _ENVELOPE
    assert plaintext not in repr(history._undo_stacks)
    assert history.undo_depth(workspace.workspace_id) == 1

    scene.set_node_property(node.node_id, "protected_value", {"plaintext": plaintext})
    assert node.properties["protected_value"] == _ENVELOPE
    assert history.undo_depth(workspace.workspace_id) == 1

    with mock.patch.object(
        selection_ops,
        "reprotect_secret",
        side_effect=RuntimeError("reprotect failed"),
    ):
        with pytest.raises(RuntimeError, match="reprotect failed"):
            scene.set_node_property(
                node.node_id,
                "scope",
                "All users on this machine",
            )
    assert node.properties["scope"] == "Current user"
    assert node.properties["protected_value"] == _ENVELOPE
    assert history.undo_depth(workspace.workspace_id) == 1

    reprotected = {**_ENVELOPE, "scope": "LocalMachine", "ciphertext_b64": "new-opaque"}
    with mock.patch.object(
        selection_ops,
        "reprotect_secret",
        return_value=reprotected,
    ):
        scene.set_node_property(
            node.node_id,
            "scope",
            "All users on this machine",
        )
    assert node.properties["scope"] == "All users on this machine"
    assert node.properties["protected_value"] == reprotected
    assert history.undo_depth(workspace.workspace_id) == 2
    assert plaintext not in repr(history._undo_stacks)

    assert scene.clear_node_secret(node.node_id, "protected_value")
    assert node.properties["protected_value"] == {}
    assert history.undo_depth(workspace.workspace_id) == 3


def test_malformed_stored_secret_is_redacted_and_can_be_cleared() -> None:
    registry, model, workspace, node = _scene(
        protected_value={"malformed": "opaque-marker"}
    )
    inspector = build_selected_node_property_items(
        node=node,
        spec=registry.get_spec(node.type_id),
        subnode_pin_type_ids=set(),
        workspace_id=workspace.workspace_id,
        workspace_nodes=workspace.nodes,
        workspace_edges=workspace.edges,
        property_edit_adapters=(),
    )
    secret_item = next(item for item in inspector if item["key"] == "protected_value")
    assert secret_item["value"] == {"has_value": True, "scope": ""}
    assert "opaque-marker" not in json.dumps(inspector)

    scene = GraphSceneBridge()
    scene.set_workspace(model, registry, workspace.workspace_id)
    assert scene.clear_node_secret(node.node_id, "protected_value")
    assert node.properties["protected_value"] == {}


class _InspectorSource(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    inspector_state_changed = pyqtSignal()

    selected_node_id = "node-1"
    selected_node_property_items = [
        {"key": "scope", "reprotects_sensitive_properties": True}
    ]

    def __init__(self) -> None:
        super().__init__()
        self.property_calls = []

    def set_selected_node_property(self, key, value) -> None:  # noqa: ANN001
        self.property_calls.append((key, value))


class _SecretScene:
    def __init__(self) -> None:
        self.calls = []

    def set_node_secret(self, node_id: str, key: str, plaintext: str) -> bool:
        self.calls.append(("replace", node_id, key, plaintext))
        return True

    def clear_node_secret(self, node_id: str, key: str) -> bool:
        self.calls.append(("clear", node_id, key))
        return True

    def set_node_property(self, node_id: str, key: str, value) -> None:  # noqa: ANN001
        self.calls.append(("property", node_id, key, value))


def test_inspector_secret_commands_use_dedicated_scene_channel() -> None:
    source = _InspectorSource()
    scene = _SecretScene()
    bridge = ShellInspectorBridge(
        inspector_source=source,
        scene_bridge=scene,  # type: ignore[arg-type]
    )

    assert bridge.set_selected_node_secret("protected_value", "plain")
    assert bridge.clear_selected_node_secret("protected_value")
    bridge.set_selected_node_property("scope", "All users on this machine")
    assert scene.calls == [
        ("replace", "node-1", "protected_value", "plain"),
        ("clear", "node-1", "protected_value"),
        ("property", "node-1", "scope", "All users on this machine"),
    ]
    assert source.property_calls == []
