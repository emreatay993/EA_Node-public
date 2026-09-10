from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtCore import QObject, pyqtSignal

from ea_node_editor.execution.run_messages import (
    NodeSettledEvent,
)
from ea_node_editor.execution.protocol_codec import (
    dict_to_event,
)
from ea_node_editor.runtime_contracts.settled_results import (
    RootExecutionError,
    SettledPortResult,
)
from ea_node_editor.runtime_contracts.solution_records import (
    NodeSolutionFact,
    SolutionDisposition,
    SolutionFreshness,
    SolutionResidency,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.runtime_contracts import DataTree, ImageValue
from ea_node_editor.ui.image_value_preview_provider import (
    set_active_image_value_preview_provider,
)
from ea_node_editor.ui.media_panel_source import resolve_media_panel_source
from ea_node_editor.ui.plot_preview_cache_provider import ViewerPreviewCacheImageProvider
from ea_node_editor.ui.shell.presenters.inspector_presenter import ShellInspectorPresenter
from ea_node_editor.ui.shell.inspector_projection import (
    build_selected_node_property_items,
)
from ea_node_editor.persistence.file_issues import collect_node_file_issues
from ea_node_editor.ui_qml.graph_canvas_state import GraphCanvasStateBridge
from tests.test_dataflow_execution_runtime import (
    _registry as _runtime_registry,
    _run,
    _settled,
)


_IMAGE_PATH = Path(__file__).parent / "fixtures" / "passive_nodes" / "reference_preview.png"


def _node(*, source: str = "", exposed: bool = True):
    return SimpleNamespace(
        node_id="media-1",
        type_id="media.panel",
        title="Media Panel",
        properties={"source": source, "page_number": 1},
        exposed_ports={"source": exposed},
        port_labels={},
    )


def _workspace(node, *, connected: bool = False):  # noqa: ANN001
    edges = {}
    if connected:
        edges["edge-1"] = SimpleNamespace(
            enabled=True,
            source_node_id="source-1",
            source_port_key="value",
            target_node_id=node.node_id,
            target_port_key="source",
        )
    return SimpleNamespace(
        workspace_id="workspace-1",
        nodes={node.node_id: node},
        edges=edges,
    )


def _run_state(*, result=None, state: str = "", stale: bool = False):  # noqa: ANN001
    state_ids = {"media-1"} if state else set()
    records = {}
    if result is not None:
        records = {
            "workspace-1": {
                "media-1": {
                    "run-1": {
                        "record_id": "run-1",
                        "observed_at_epoch_ms": 1.0,
                        "outputs": {"_surface_source": result},
                    }
                }
            }
        }
    return SimpleNamespace(
        node_execution_workspace_id="workspace-1",
        running_node_ids=state_ids if state == "running" else set(),
        completed_node_ids=state_ids if state == "completed" else set(),
        empty_node_ids=state_ids if state == "empty" else set(),
        failed_node_ids=state_ids if state == "failed" else set(),
        blocked_node_ids=state_ids if state == "blocked" else set(),
        root_errors_by_node_id={},
        cached_node_output_records_by_workspace_id=records,
        node_solution_facts_by_workspace_id=(
            {
                "workspace-1": {
                    "media-1": NodeSolutionFact(
                        project_id="project",
                        workspace_id="workspace-1",
                        node_id="media-1",
                        freshness=(
                            SolutionFreshness.EXPIRED
                            if stale
                            else SolutionFreshness.CURRENT
                        ),
                        revision=1,
                        retained_record_id="run-1",
                        retained_solution_key="a" * 64,
                        residency=SolutionResidency.SESSION,
                        expiration_reason_code="graph_changed" if stale else "",
                        expiration_root_node_ids=("media-1",) if stale else (),
                        last_disposition=SolutionDisposition.RECOMPUTED,
                    )
                }
            }
            if result is not None
            else {}
        ),
    )


def _value_result(value):  # noqa: ANN001
    return SettledPortResult(status="value", value=DataTree.from_item(value))


class _CanvasSource(QObject):
    graphics_preferences_changed = pyqtSignal()
    snap_to_grid_changed = pyqtSignal()


class _ExecutionSource(QObject):
    run_failure_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.run_state = _run_state()


class _SceneSource(QObject):
    nodes_changed = pyqtSignal()
    edges_changed = pyqtSignal()
    selection_changed = pyqtSignal()
    workspace_changed = pyqtSignal(str)

    def __init__(self, workspace_id: str) -> None:
        super().__init__()
        self.workspace_id = workspace_id
        self.selected_node_lookup = {}


def test_property_authority_resolves_local_media_without_a_run() -> None:
    node = _node(source=str(_IMAGE_PATH), exposed=False)
    resolution = resolve_media_panel_source(node=node, workspace=_workspace(node))

    assert resolution.authority == "property"
    assert resolution.state == "ready"
    assert resolution.media_kind == "image"
    assert resolution.source_ref == str(_IMAGE_PATH)
    assert resolution.resolved_source_url.startswith("file:")
    assert resolution.preview_source_url.startswith("image://local-media-preview/")


def test_exposed_input_never_falls_back_to_authored_source() -> None:
    node = _node(source=str(_IMAGE_PATH), exposed=True)

    unwired = resolve_media_panel_source(node=node, workspace=_workspace(node))
    wired = resolve_media_panel_source(
        node=node,
        workspace=_workspace(node, connected=True),
        run_state=_run_state(),
    )

    assert unwired.to_qml_payload() == {
        "authority": "input",
        "input_exposed": True,
        "input_connected": False,
        "state": "waiting",
        "media_kind": "",
        "source_ref": "",
        "resolved_source_url": "",
        "preview_source_url": "",
        "message": "Connect a Path, String, or Image value to Source.",
    }
    assert wired.authority == "input"
    assert wired.input_connected
    assert wired.state == "waiting"
    assert wired.source_ref == ""


def test_input_runtime_states_clear_every_source_url() -> None:
    node = _node(source=str(_IMAGE_PATH), exposed=True)
    workspace = _workspace(node, connected=True)
    failed = SettledPortResult(
        status="failed",
        errors=(RootExecutionError(error="Media Panel source must be supported."),),
    )
    cases = (
        (_run_state(state="running"), "running"),
        (_run_state(result=SettledPortResult(status="empty")), "empty"),
        (_run_state(result=failed, state="failed"), "invalid"),
        (_run_state(state="blocked"), "failed"),
        (_run_state(result=_value_result(str(_IMAGE_PATH)), state="failed"), "failed"),
        (_run_state(result=_value_result(str(_IMAGE_PATH)), stale=True), "stale"),
        (
            _run_state(
                result=SettledPortResult(
                    status="value",
                    value=DataTree.from_list([str(_IMAGE_PATH), str(_IMAGE_PATH)]),
                )
            ),
            "invalid",
        ),
        (_run_state(result=_value_result("notes.txt")), "invalid"),
        (_run_state(result=_value_result("http://[invalid/image.png")), "invalid"),
        (_run_state(result=_value_result(str(_IMAGE_PATH.with_name("missing.png")))), "stale"),
    )

    for run_state, expected_state in cases:
        resolution = resolve_media_panel_source(
            node=node,
            workspace=workspace,
            run_state=run_state,
        )
        assert resolution.state == expected_state
        assert resolution.media_kind == ""
        assert resolution.source_ref == ""
        assert resolution.resolved_source_url == ""
        assert resolution.preview_source_url == ""
        assert resolution.message


def test_metadata_only_runtime_record_is_unavailable_not_empty_media() -> None:
    node = _node(source=str(_IMAGE_PATH), exposed=True)
    run_state = _run_state(
        result=_value_result(str(_IMAGE_PATH)),
        state="completed",
    )
    run_state.cached_node_output_records_by_workspace_id["workspace-1"]["media-1"][
        "run-1"
    ]["outputs_available"] = False

    resolution = resolve_media_panel_source(
        node=node,
        workspace=_workspace(node, connected=True),
        run_state=run_state,
    )

    assert resolution.state == "unavailable"
    assert resolution.source_ref == ""


def test_malformed_url_worker_failure_resolves_as_controlled_invalid() -> None:
    malformed = "http://[invalid/image.png"
    registry = _runtime_registry()
    model = GraphModel()
    workspace = model.active_workspace
    source = model.add_node(
        workspace.workspace_id,
        "core.constant",
        "Malformed Source",
        0,
        0,
        properties={"value": malformed},
    )
    panel = model.add_node(
        workspace.workspace_id,
        "media.panel",
        "Media Panel",
        100,
        0,
    )
    model.add_edge(
        workspace.workspace_id,
        source.node_id,
        "value",
        panel.node_id,
        "source",
    )

    event = dict_to_event(
        _settled(_run(model, registry, run_id="malformed_media_url"), panel.node_id),
        catalog=registry.data_types,
    )
    assert isinstance(event, NodeSettledEvent)
    result = event.outputs["_surface_source"]
    assert result.status == "failed"
    assert result.errors
    assert result.errors[0].error.startswith("Media Panel source must be an Image value")
    assert "Invalid IPv6" not in result.errors[0].error

    node = _node(exposed=True)
    resolution = resolve_media_panel_source(
        node=node,
        workspace=_workspace(node, connected=True),
        run_state=_run_state(result=result, state="failed"),
    )
    assert resolution.state == "invalid"
    assert resolution.message == result.errors[0].error


def test_path_string_remote_and_image_value_inputs_resolve_ready() -> None:
    node = _node(exposed=True)
    workspace = _workspace(node, connected=True)
    remote = resolve_media_panel_source(
        node=node,
        workspace=workspace,
        run_state=_run_state(result=_value_result("https://example.test/clip.mp4")),
    )
    assert remote.state == "ready"
    assert remote.media_kind == "video"
    assert remote.resolved_source_url == "https://example.test/clip.mp4"

    provider = ViewerPreviewCacheImageProvider()
    set_active_image_value_preview_provider(provider)
    try:
        value = ImageValue.from_png(_IMAGE_PATH.read_bytes())
        image = resolve_media_panel_source(
            node=node,
            workspace=workspace,
            run_state=_run_state(result=_value_result(value)),
        )
    finally:
        set_active_image_value_preview_provider(None)

    assert image.state == "ready"
    assert image.media_kind == "image"
    assert image.raw_value is value
    assert image.source_ref == ""
    assert image.preview_source_url.startswith("image://viewer-preview-cache/")
    assert "encoded_bytes" not in image.to_qml_payload()


def test_state_bridge_uses_project_source_and_invalidates_media_lookup() -> None:
    node = _node(source=str(_IMAGE_PATH), exposed=False)
    workspace = _workspace(node)
    project = SimpleNamespace(
        workspaces={workspace.workspace_id: workspace},
        metadata={},
    )
    canvas_source = _CanvasSource()
    execution_source = _ExecutionSource()
    scene_source = _SceneSource(workspace.workspace_id)
    bridge = GraphCanvasStateBridge(
        session_state=canvas_source,
        snap_to_grid_changed_signal=canvas_source.snap_to_grid_changed,
        snap_grid_size=20.0,
        app_preferences_source=canvas_source,
        execution_source=execution_source,
        project_source=SimpleNamespace(
            model=SimpleNamespace(project=project),
            project_path="",
        ),
        scene_bridge=scene_source,
    )
    notifications = 0

    def _record_notification() -> None:
        nonlocal notifications
        notifications += 1

    bridge.port_flow_state_changed.connect(_record_notification)

    lookup = bridge.media_panel_source_lookup

    assert lookup[node.node_id]["state"] == "ready"
    assert set(lookup[node.node_id]) == {
        "authority",
        "input_exposed",
        "input_connected",
        "state",
        "media_kind",
        "source_ref",
        "resolved_source_url",
        "preview_source_url",
        "message",
    }

    scene_source.nodes_changed.emit()
    scene_source.edges_changed.emit()
    scene_source.workspace_changed.emit(workspace.workspace_id)
    execution_source.node_execution_state_changed.emit()
    assert notifications == 4


def test_exposed_source_is_disabled_and_has_no_dormant_file_issue(tmp_path: Path) -> None:
    registry = build_default_registry()
    spec = registry.get_spec("media.panel")
    missing = str(tmp_path / "missing.png")
    node = _node(source=missing, exposed=True)
    workspace = _workspace(node)

    source_item = next(
        item
        for item in build_selected_node_property_items(
            node=node,
            spec=spec,
            subnode_pin_type_ids=set(),
            workspace_nodes=workspace.nodes,
            workspace_edges=workspace.edges,
        )
        if item["key"] == "source"
    )
    assert not source_item["editor_enabled"]
    assert not source_item["file_issue_active"]
    assert collect_node_file_issues(
        node=node,
        spec=spec,
        project_path=None,
        project_metadata=None,
    ) == {}

    node.exposed_ports["source"] = False
    issues = collect_node_file_issues(
        node=node,
        spec=spec,
        project_path=None,
        project_metadata=None,
    )
    assert issues["source"].issue_kind == "external_missing"

    node.properties["source"] = "https://example.test/reference.pdf"
    assert collect_node_file_issues(
        node=node,
        spec=spec,
        project_path=None,
        project_metadata=None,
    ) == {}


class _InspectorController:
    def __init__(self, node, spec):  # noqa: ANN001
        self.node = node
        self.spec = spec
        self.commits: list[tuple[str, object]] = []

    def selected_node_context(self):  # noqa: ANN201
        return self.node, self.spec

    def set_selected_node_property(self, key: str, value: object) -> None:
        self.commits.append((key, value))


class _InspectorHost(QObject):
    selected_node_changed = pyqtSignal()
    workspace_state_changed = pyqtSignal()
    node_execution_state_changed = pyqtSignal()

    def __init__(self, node, spec):  # noqa: ANN001
        super().__init__()
        controller = _InspectorController(node, spec)
        self.workspace_selection_context = controller
        self.workspace_edit_controller = controller
        self._SUBNODE_PIN_TYPE_IDS = set()


def test_inspector_commit_guard_rechecks_source_exposure() -> None:
    registry = build_default_registry()
    spec = registry.get_spec("media.panel")
    node = _node(exposed=True)
    host = _InspectorHost(node, spec)
    presenter = ShellInspectorPresenter(host)
    try:
        presenter.set_selected_node_property("source", "C:/blocked.png")
        assert host.workspace_edit_controller.commits == []

        node.exposed_ports["source"] = False
        presenter.set_selected_node_property("source", "C:/accepted.png")
        assert host.workspace_edit_controller.commits == [
            ("source", "C:/accepted.png")
        ]
    finally:
        presenter.shutdown()
