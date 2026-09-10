from __future__ import annotations

from ea_node_editor.ui_qml.jupyter_server_bridge import JupyterServerBridge


def test_bridge_create_blank_emits_notebook_ref_assigned(qapp) -> None:  # noqa: ANN001
    calls: list[tuple[str, str]] = []

    def create_notebook(node_id: str = "", *, kernel_name: str = "") -> str:
        calls.append((node_id, kernel_name))
        return "temp://created_notebook"

    bridge = JupyterServerBridge(create_blank_notebook_artifact=create_notebook)
    assigned: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    bridge.notebookRefAssigned.connect(lambda node, ref: assigned.append((node, ref)))
    bridge.serverFailed.connect(lambda node, reason: failed.append((node, reason)))

    bridge.createBlankNotebook("node-create", "python3")

    assert not failed
    assert assigned == [("node-create", "temp://created_notebook")]
    assert calls == [("node-create", "python3")]


def test_bridge_create_blank_without_creator_reports_failure(qapp) -> None:  # noqa: ANN001
    bridge = JupyterServerBridge(shell_window=None)
    failed: list[tuple[str, str]] = []
    bridge.serverFailed.connect(lambda node, reason: failed.append((node, reason)))

    bridge.createBlankNotebook("node-x", "")

    assert failed and "project" in failed[-1][1].lower()
