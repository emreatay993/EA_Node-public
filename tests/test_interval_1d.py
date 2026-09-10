from __future__ import annotations

import json
import math

import pytest

from ea_node_editor.execution.runtime_snapshot import RuntimeSnapshot
from ea_node_editor.graph.fragment_payloads import build_graph_fragment_payload
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.record_payloads import (
    node_instance_from_mapping,
    node_instance_to_mapping,
)
from ea_node_editor.graph.transform_fragment_ops import (
    build_subtree_fragment_payload_data,
    insert_graph_fragment,
)
from ea_node_editor.persistence.project_codec import JsonProjectCodec
from ea_node_editor.runtime_contracts import (
    INTERVAL_1D_DATA_TYPE,
    DataTree,
    Interval1D,
    coerce_interval_1d,
    deserialize_runtime_value,
    serialize_runtime_value,
)
from ea_node_editor.settings import SCHEMA_VERSION
from ea_node_editor.ui.shell.runtime_history import RuntimeGraphHistory

_MARKER_KEY = "__ea_runtime_value__"


def _interval_model(value: Interval1D) -> tuple[GraphModel, str, str]:
    model = GraphModel()
    workspace = model.active_workspace
    node = model.add_node(
        workspace.workspace_id,
        "tests.interval_holder",
        "Interval Holder",
        10.0,
        20.0,
        properties={"result_bound": value, "unchanged": {"values": [1, 2, 3]}},
    )
    return model, workspace.workspace_id, node.node_id


def test_interval_accepts_ordered_finite_numeric_endpoints() -> None:
    increasing = Interval1D(0, 10)
    decreasing = Interval1D(10, 0)
    equal = Interval1D(5, 5)

    assert increasing == Interval1D(0.0, 10.0)
    assert decreasing == Interval1D(10.0, 0.0)
    assert equal == Interval1D(5.0, 5.0)
    assert coerce_interval_1d(decreasing) is decreasing


@pytest.mark.parametrize(
    ("start", "end", "error"),
    [
        (True, 0, TypeError),
        (0, False, TypeError),
        ("0", 1, TypeError),
        (0, object(), TypeError),
        (math.nan, 0, ValueError),
        (0, math.inf, ValueError),
        (-math.inf, 0, ValueError),
    ],
)
def test_interval_rejects_invalid_endpoints(
    start: object,
    end: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        Interval1D(start, end)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        (0.0, 1.0),
        [0.0, 1.0],
        {"start": 0.0, "end": 1.0},
        {_MARKER_KEY: INTERVAL_1D_DATA_TYPE, "start": 0.0, "end": 1.0},
    ],
)
def test_public_coercion_rejects_untyped_pairs_and_marker_mappings(
    value: object,
) -> None:
    with pytest.raises(TypeError):
        coerce_interval_1d(value)


def test_runtime_marker_is_exact_and_preserves_decreasing_order() -> None:
    value = Interval1D(10, 0)

    payload = serialize_runtime_value(value)

    assert payload == {
        _MARKER_KEY: INTERVAL_1D_DATA_TYPE,
        "start": 10.0,
        "end": 0.0,
    }
    assert deserialize_runtime_value(payload) == value
    assert serialize_runtime_value(deserialize_runtime_value(payload)) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {_MARKER_KEY: INTERVAL_1D_DATA_TYPE, "start": 0.0},
        {_MARKER_KEY: INTERVAL_1D_DATA_TYPE, "end": 1.0},
        {_MARKER_KEY: INTERVAL_1D_DATA_TYPE, "start": True, "end": 1.0},
        {_MARKER_KEY: INTERVAL_1D_DATA_TYPE, "start": 0.0, "end": math.inf},
        {
            _MARKER_KEY: INTERVAL_1D_DATA_TYPE,
            "start": 0.0,
            "end": 1.0,
            "extra": "not allowed",
        },
    ],
)
def test_runtime_codec_rejects_malformed_interval_markers(
    payload: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        deserialize_runtime_value(payload)
    with pytest.raises((TypeError, ValueError)):
        serialize_runtime_value(payload)


def test_runtime_codec_recurses_through_data_tree_and_nested_containers() -> None:
    decreasing = Interval1D(10, 0)
    equal = Interval1D(5, 5)
    tree = DataTree({(2,): (decreasing, {"nested": [equal]})})

    payload = serialize_runtime_value({"tree": tree, "items": (decreasing, equal)})
    restored = deserialize_runtime_value(payload)

    assert restored["tree"] == tree
    assert restored["tree"][(2,)][0] == Interval1D(10, 0)
    assert restored["tree"][(2,)][1]["nested"][0] == equal
    assert restored["items"] == [decreasing, equal]


def test_node_property_payload_round_trip_keeps_other_properties_unchanged() -> None:
    model, workspace_id, node_id = _interval_model(Interval1D(10, 0))
    node = model.project.workspaces[workspace_id].nodes[node_id]

    payload = node_instance_to_mapping(node)
    restored = node_instance_from_mapping(json.loads(json.dumps(payload)))

    assert payload["properties"]["result_bound"] == {
        _MARKER_KEY: INTERVAL_1D_DATA_TYPE,
        "start": 10.0,
        "end": 0.0,
    }
    assert restored is not None
    assert restored.properties == node.properties
    assert restored.properties["unchanged"] == {"values": [1, 2, 3]}


def test_project_fragment_history_duplication_and_runtime_snapshot_preserve_order() -> (
    None
):
    value = Interval1D(10, 0)
    model, workspace_id, node_id = _interval_model(value)
    workspace = model.project.workspaces[workspace_id]
    node = workspace.nodes[node_id]

    duplicate_workspace = workspace.clone("ws_duplicate", "Duplicate")
    assert duplicate_workspace.nodes[node_id].properties["result_bound"] == value

    history = RuntimeGraphHistory()
    before = history.capture_workspace(workspace)
    node.properties["result_bound"] = Interval1D(0, 10)
    workspace.mark_dirty()
    assert history.record_action(workspace_id, "interval-edit", before, workspace)
    assert history.undo_workspace(workspace_id, workspace) is not None
    assert workspace.nodes[node_id].properties["result_bound"] == value
    assert history.redo_workspace(workspace_id, workspace) is not None
    assert workspace.nodes[node_id].properties["result_bound"] == Interval1D(0, 10)
    workspace.nodes[node_id].properties["result_bound"] = value
    workspace.mark_dirty()

    fragment_data = build_subtree_fragment_payload_data(
        workspace=workspace,
        selected_node_ids=[node_id],
    )
    assert fragment_data is not None
    fragment = build_graph_fragment_payload(**fragment_data)
    inserted_ids = insert_graph_fragment(
        model=model,
        workspace_id=workspace_id,
        fragment_payload=json.loads(json.dumps(fragment)),
        delta_x=100.0,
        delta_y=100.0,
    )
    assert len(inserted_ids) == 1
    assert workspace.nodes[inserted_ids[0]].properties["result_bound"] == value

    codec = JsonProjectCodec()
    document = codec.to_persistent_document(model.project)
    assert document["schema_version"] == SCHEMA_VERSION
    loaded = codec.from_document(json.loads(json.dumps(document)))
    assert (
        loaded.workspaces[workspace_id].nodes[node_id].properties["result_bound"]
        == value
    )

    runtime_document = RuntimeSnapshot.from_project_data(model.project).to_document()
    runtime_snapshot = RuntimeSnapshot.from_mapping(
        json.loads(json.dumps(runtime_document))
    )
    runtime_node = runtime_snapshot.workspace(workspace_id).nodes_by_id[node_id]
    assert runtime_node.properties["result_bound"] == value
