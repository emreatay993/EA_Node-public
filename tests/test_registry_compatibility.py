from __future__ import annotations

import copy
from dataclasses import replace
from typing import Mapping

import pytest

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.records import EdgeInstance, NodeInstance
from ea_node_editor.graph.registry_compatibility import check_registry_compatibility
from ea_node_editor.graph.workspace_state import WorkspaceData
from ea_node_editor.nodes.node_specs import (
    DynamicPortGroupSpec,
    NodeTypeSpec,
    PortSpec,
    PropertySpec,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.runtime_contracts import (
    DataTypeSpec,
    GRAPH_DATA_TYPE_ID,
    INTERVAL_1D_GRAPH_DATA_TYPE_ID,
    Interval1D,
    RuntimeArtifactRef,
    TypedInlineValue,
)

_INLINE_TYPE_ID = "Tests.Compatibility.Inline"
_OTHER_INLINE_TYPE_ID = "Tests.Compatibility.OtherInline"
_ARTIFACT_TYPE_ID = "Tests.Compatibility.Artifact"
_OTHER_ARTIFACT_TYPE_ID = "Tests.Compatibility.OtherArtifact"


def _registry(
    *specs: NodeTypeSpec,
    data_types: tuple[DataTypeSpec, ...] = (),
) -> NodeRegistry:
    registry = NodeRegistry()
    if data_types:
        registry.data_types.register_many(
            types=data_types,
            owner_id="tests.registry.compatibility",
        )
    for spec in specs:
        registry.register_descriptor(spec, lambda: None)  # type: ignore[arg-type]
    return registry


def _inline_type(
    type_id: str = _INLINE_TYPE_ID,
    *,
    sensitivity: str = "normal",
) -> DataTypeSpec:
    return DataTypeSpec(
        type_id,
        type_id.rsplit(".", 1)[-1],
        "graph",
        lambda value: isinstance(value, dict) and value.get("ok") is True,
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"inline"}),
        persistence="inline",
        sensitivity=sensitivity,  # type: ignore[arg-type]
    )


def _artifact_type(type_id: str = _ARTIFACT_TYPE_ID) -> DataTypeSpec:
    return DataTypeSpec(
        type_id,
        type_id.rsplit(".", 1)[-1],
        "graph",
        lambda value: isinstance(value, RuntimeArtifactRef),
        parents=(GRAPH_DATA_TYPE_ID,),
        carriers=frozenset({"artifact"}),
        persistence="saved_artifact",
    )


def _runtime_artifact(type_id: str = _ARTIFACT_TYPE_ID) -> RuntimeArtifactRef:
    return RuntimeArtifactRef.managed(
        "artifact",
        data_type_id=type_id,
        schema_version=1,
        format="bin",
        size_bytes=1,
        sha256="1" * 64,
        provenance="registry-compatibility-test",
    )


def _spec(
    *,
    type_id: str = "tests.compatible",
    ports: tuple[PortSpec, ...] = (),
    properties: tuple[PropertySpec, ...] = (),
    **changes,
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name=str(changes.pop("display_name", "Compatible")),
        category_path=changes.pop("category_path", ("Tests",)),
        icon=str(changes.pop("icon", "")),
        ports=ports,
        properties=properties,
        **changes,
    )


def _node(
    node_id: str,
    type_id: str,
    *,
    properties: dict[str, object] | None = None,
) -> NodeInstance:
    return NodeInstance(
        node_id=node_id,
        type_id=type_id,
        title=node_id,
        x=0.0,
        y=0.0,
        properties=dict(properties or {}),
    )


def _project(*workspaces: WorkspaceData, project_id: str = "project") -> ProjectData:
    return ProjectData(
        project_id=project_id,
        name=project_id,
        workspaces={workspace.workspace_id: workspace for workspace in workspaces},
    )


def _report_for(
    current: NodeTypeSpec | tuple[NodeTypeSpec, ...],
    candidate: NodeTypeSpec | tuple[NodeTypeSpec, ...],
    project: ProjectData,
):
    current_specs = current if isinstance(current, tuple) else (current,)
    candidate_specs = candidate if isinstance(candidate, tuple) else (candidate,)
    return check_registry_compatibility(
        current_registry=_registry(*current_specs),
        candidate_registry=_registry(*candidate_specs),
        projects=project,
    )


def _report_for_with_data_types(
    current: NodeTypeSpec,
    candidate: NodeTypeSpec,
    project: ProjectData,
    *,
    current_data_types: tuple[DataTypeSpec, ...],
    candidate_data_types: tuple[DataTypeSpec, ...] | None = None,
):
    return check_registry_compatibility(
        current_registry=_registry(current, data_types=current_data_types),
        candidate_registry=_registry(
            candidate,
            data_types=candidate_data_types or current_data_types,
        ),
        projects=project,
    )


def test_compatible_additions_and_presentation_changes_are_read_only() -> None:
    current = _spec(
        ports=(
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.Double",
                required=False,
            ),
            PortSpec("result", "out", "data", "COREX.DataTypes.Double"),
        ),
        properties=(
            PropertySpec(
                "factor",
                "float",
                2.0,
                "Factor",
                minimum=0.0,
                maximum=10.0,
                inline_editor="slider",
            ),
        ),
    )
    candidate = replace(
        current,
        display_name="Renamed",
        description="Presentation-only change.",
        keywords=("new",),
        category_path=("Moved",),
        ports=(
            *current.ports,
            PortSpec("summary", "out", "data", "COREX.DataTypes.String"),
            PortSpec(
                "optional",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=False,
            ),
            PortSpec(
                "threshold",
                "in",
                "data",
                "COREX.DataTypes.Double",
                required=False,
                uses_property_default=True,
            ),
        ),
        properties=(
            *current.properties,
            PropertySpec(
                "threshold",
                "float",
                1.0,
                "Threshold",
                minimum=0.0,
                maximum=5.0,
                inline_editor="slider",
            ),
            PropertySpec("note", "str", "", "Note"),
        ),
    )
    workspace = WorkspaceData(
        workspace_id="ws",
        name="Workspace",
        nodes={"node": _node("node", current.type_id, properties={"factor": 3.0})},
    )
    project = _project(workspace)
    before = copy.deepcopy(project)
    revisions = (project.project_document_revision, workspace.mutation_revision)

    report = _report_for(current, candidate, project)

    assert report.compatible
    assert report.issues == ()
    assert project == before
    assert revisions == (project.project_document_revision, workspace.mutation_revision)


@pytest.mark.parametrize(
    ("candidate_port", "expected_code"),
    (
        (None, "port_removed"),
        (
            PortSpec(
                "value",
                "out",
                "data",
                "COREX.DataTypes.Any",
                required=False,
            ),
            "port_direction_changed",
        ),
        (
            PortSpec("value", "in", "flow", "flow", required=False),
            "port_kind_changed",
        ),
        (
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.String",
                required=False,
            ),
            "port_data_type_changed",
        ),
        (
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=False,
                accepted_data_types=("COREX.DataTypes.String",),
            ),
            "port_accepted_data_types_changed",
        ),
        (
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=False,
                data_access="list",
            ),
            "port_access_changed",
        ),
        (
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=True,
            ),
            "port_requiredness_changed",
        ),
        (
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=False,
                exposed=False,
            ),
            "port_exposure_changed",
        ),
    ),
)
def test_existing_effective_port_contract_changes_are_rejected(
    candidate_port: PortSpec | None,
    expected_code: str,
) -> None:
    current_port = PortSpec(
        "value",
        "in",
        "data",
        "COREX.DataTypes.Any",
        required=False,
    )
    current = _spec(ports=(current_port,))
    candidate = replace(
        current,
        ports=() if candidate_port is None else (candidate_port,),
    )
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={"node": _node("node", current.type_id)},
        )
    )

    report = _report_for(current, candidate, project)

    assert not report.compatible
    assert expected_code in {issue.code for issue in report.issues}


def test_multiplicity_and_property_default_pairing_changes_are_rejected() -> None:
    flow_current = _spec(
        type_id="tests.flow",
        ports=(
            PortSpec(
                "flow",
                "in",
                "flow",
                "flow",
                required=False,
                allow_multiple_connections=True,
            ),
        ),
    )
    flow_candidate = replace(
        flow_current,
        ports=(
            replace(flow_current.ports[0], allow_multiple_connections=False),
        ),
    )
    paired_current = _spec(
        type_id="tests.paired",
        ports=(
            PortSpec(
                "value",
                "in",
                "data",
                "COREX.DataTypes.String",
                required=False,
            ),
        ),
        properties=(PropertySpec("value", "str", "", "Value"),),
    )
    paired_candidate = replace(
        paired_current,
        ports=(replace(paired_current.ports[0], uses_property_default=True),),
    )
    workspace = WorkspaceData(
        workspace_id="ws",
        name="Workspace",
        nodes={
            "flow": _node("flow", flow_current.type_id),
            "paired": _node("paired", paired_current.type_id, properties={"value": "x"}),
        },
    )

    report = _report_for(
        (flow_current, paired_current),
        (flow_candidate, paired_candidate),
        _project(workspace),
    )

    assert {issue.code for issue in report.issues} == {
        "port_multiplicity_changed",
        "port_property_default_pairing_changed",
    }


def test_missing_type_removed_property_type_change_and_required_input_are_rejected() -> None:
    current = _spec(
        type_id="tests.changed",
        properties=(
            PropertySpec("removed", "str", "", "Removed"),
            PropertySpec("typed", "str", "", "Typed"),
        ),
    )
    candidate = replace(
        current,
        ports=(
            PortSpec(
                "required",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=True,
            ),
        ),
        properties=(PropertySpec("typed", "int", 0, "Typed"),),
    )
    missing = _spec(type_id="tests.missing")
    workspace = WorkspaceData(
        workspace_id="ws",
        name="Workspace",
        nodes={
            "changed": _node(
                "changed",
                current.type_id,
                properties={"removed": "saved", "typed": "saved"},
            ),
            "missing": _node("missing", missing.type_id),
        },
    )

    report = _report_for((current, missing), candidate, _project(workspace))

    assert {issue.code for issue in report.issues} == {
        "node_type_missing",
        "property_removed",
        "property_type_changed",
        "required_input_added",
    }


def test_new_control_requires_a_valid_default() -> None:
    current = _spec()
    candidate = replace(
        current,
        properties=(
            PropertySpec(
                "count",
                "int",
                0,
                "Count",
                minimum=5,
                maximum=10,
                inline_editor="slider",
            ),
        ),
    )
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={"node": _node("node", current.type_id)},
        )
    )

    report = _report_for(current, candidate, project)

    assert [issue.code for issue in report.issues] == [
        "new_property_default_invalid"
    ]


def test_omitted_existing_property_uses_candidate_default_for_compatibility() -> None:
    current = _spec(
        properties=(PropertySpec("count", "int", 2, "Count", minimum=0),),
    )
    candidate = replace(
        current,
        properties=(PropertySpec("count", "int", 2, "Count", minimum=5),),
    )
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={"node": _node("node", current.type_id)},
        )
    )

    report = _report_for(current, candidate, project)

    assert [issue.code for issue in report.issues] == ["property_value_invalid"]


def test_property_storage_metadata_changes_are_rejected_without_mutation() -> None:
    inline_types = (
        _inline_type(),
        _inline_type(_OTHER_INLINE_TYPE_ID),
    )
    current = _spec(
        properties=(
            PropertySpec(
                "payload",
                "json",
                TypedInlineValue(_INLINE_TYPE_ID, 1, {"ok": True}),
                "Payload",
                persistence_data_type_id=_INLINE_TYPE_ID,
            ),
            PropertySpec(
                "secret_removed",
                "json",
                {},
                "Secret Removed",
                inline_editor="secret",
                inspector_editor="secret",
                sensitive=True,
                sensitive_scope_key="scope_a",
            ),
            PropertySpec(
                "secret_scope",
                "json",
                {},
                "Secret Scope",
                inline_editor="secret",
                inspector_editor="secret",
                sensitive=True,
                sensitive_scope_key="scope_a",
            ),
            PropertySpec("scope_a", "enum", "a", "Scope A", enum_values=("a",)),
            PropertySpec("scope_b", "enum", "b", "Scope B", enum_values=("b",)),
        ),
    )
    candidate = replace(
        current,
        properties=(
            replace(
                current.properties[0],
                default=TypedInlineValue(_OTHER_INLINE_TYPE_ID, 1, {"ok": True}),
                persistence_data_type_id=_OTHER_INLINE_TYPE_ID,
            ),
            replace(
                current.properties[1],
                inline_editor="",
                inspector_editor="",
                sensitive=False,
                sensitive_scope_key="",
            ),
            replace(current.properties[2], sensitive_scope_key="scope_b"),
            *current.properties[3:],
        ),
    )
    workspace = WorkspaceData(
        workspace_id="ws",
        name="Workspace",
        nodes={"node": _node("node", current.type_id)},
        dirty=True,
        mutation_revision=7,
    )
    project = _project(workspace)
    project.project_document_revision = 5
    before = copy.deepcopy(project)
    state = (project.project_document_revision, workspace.mutation_revision, workspace.dirty)

    report = _report_for_with_data_types(
        current,
        candidate,
        project,
        current_data_types=inline_types,
    )

    assert {(issue.member_key, issue.code) for issue in report.issues} == {
        ("payload", "property_persistence_data_type_changed"),
        ("secret_removed", "property_sensitivity_changed"),
        ("secret_removed", "property_sensitive_scope_changed"),
        ("secret_scope", "property_sensitive_scope_changed"),
    }
    assert project == before
    assert state == (
        project.project_document_revision,
        workspace.mutation_revision,
        workspace.dirty,
    )


def test_property_data_type_storage_contract_change_is_rejected() -> None:
    prop = PropertySpec(
        "payload",
        "json",
        TypedInlineValue(_INLINE_TYPE_ID, 1, {"ok": True}),
        "Payload",
        persistence_data_type_id=_INLINE_TYPE_ID,
    )
    spec = _spec(properties=(prop,))
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={"node": _node("node", spec.type_id)},
        )
    )

    report = _report_for_with_data_types(
        spec,
        spec,
        project,
        current_data_types=(_inline_type(sensitivity="normal"),),
        candidate_data_types=(_inline_type(sensitivity="sensitive"),),
    )

    assert [issue.code for issue in report.issues] == [
        "property_data_type_storage_changed"
    ]


@pytest.mark.parametrize(
    ("value", "compatible"),
    (
        (TypedInlineValue(_INLINE_TYPE_ID, 1, {"ok": True}), True),
        (TypedInlineValue(_INLINE_TYPE_ID, 1, {"ok": False}), False),
        (TypedInlineValue(_INLINE_TYPE_ID, 2, {"ok": True}), False),
    ),
)
def test_typed_inline_property_values_use_candidate_catalog(
    value: object,
    compatible: bool,
) -> None:
    prop = PropertySpec(
        "payload",
        "json",
        TypedInlineValue(_INLINE_TYPE_ID, 1, {"ok": True}),
        "Payload",
        persistence_data_type_id=_INLINE_TYPE_ID,
    )
    spec = _spec(properties=(prop,))
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={
                "node": _node("node", spec.type_id, properties={"payload": value})
            },
        )
    )

    report = _report_for_with_data_types(
        spec,
        spec,
        project,
        current_data_types=(_inline_type(),),
    )

    assert report.compatible is compatible


@pytest.mark.parametrize(
    ("value", "compatible"),
    (
        ("saved://artifact", True),
        (_runtime_artifact(), True),
        ("saved://bad/id", False),
        (_runtime_artifact(_OTHER_ARTIFACT_TYPE_ID), False),
    ),
)
def test_artifact_property_values_use_candidate_catalog(
    value: object,
    compatible: bool,
) -> None:
    prop = PropertySpec(
        "artifact",
        "path",
        "",
        "Artifact",
        persistence_data_type_id=_ARTIFACT_TYPE_ID,
    )
    spec = _spec(properties=(prop,))
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={
                "node": _node("node", spec.type_id, properties={"artifact": value})
            },
        )
    )

    report = _report_for_with_data_types(
        spec,
        spec,
        project,
        current_data_types=(_artifact_type(), _artifact_type(_OTHER_ARTIFACT_TYPE_ID)),
    )

    assert report.compatible is compatible


@pytest.mark.parametrize(
    ("current_prop", "candidate_prop", "saved_value"),
    (
        (
            PropertySpec(
                "value",
                "int",
                2,
                "Value",
                minimum=0,
                maximum=10,
                inline_editor="slider",
            ),
            PropertySpec(
                "value",
                "int",
                5,
                "Value",
                minimum=5,
                maximum=10,
                inline_editor="slider",
            ),
            2,
        ),
        (
            PropertySpec(
                "value",
                "enum",
                "b",
                "Value",
                enum_values=("a", "b"),
                inline_editor="enum",
            ),
            PropertySpec(
                "value",
                "enum",
                "a",
                "Value",
                enum_values=("a",),
                inline_editor="enum",
            ),
            "b",
        ),
        (
            PropertySpec(
                "value",
                "json",
                ["b"],
                "Value",
                inline_editor="list",
                list_item_type="enum",
                list_item_enum_values=("A", "B"),
                list_item_enum_codes=("a", "b"),
            ),
            PropertySpec(
                "value",
                "json",
                ["a"],
                "Value",
                inline_editor="list",
                list_item_type="enum",
                list_item_enum_values=("A",),
                list_item_enum_codes=("a",),
            ),
            ["b"],
        ),
        (
            PropertySpec(
                "value",
                "interval_1d",
                Interval1D(3.0, 1.0),
                "Value",
                inline_editor="interval_fields",
            ),
            PropertySpec(
                "value",
                "interval_1d",
                Interval1D(1.0, 3.0),
                "Value",
                minimum=0.0,
                maximum=10.0,
                inline_editor="interval_slider",
                interval_direction="increasing",
            ),
            Interval1D(3.0, 1.0),
        ),
    ),
)
def test_saved_values_invalidated_by_control_rules_are_rejected(
    current_prop: PropertySpec,
    candidate_prop: PropertySpec,
    saved_value: object,
) -> None:
    current = _spec(properties=(current_prop,))
    candidate = replace(current, properties=(candidate_prop,))
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={
                "node": _node(
                    "node",
                    current.type_id,
                    properties={"value": saved_value},
                )
            },
        )
    )

    report = _report_for(current, candidate, project)

    assert [issue.code for issue in report.issues] == ["property_value_invalid"]


@pytest.mark.parametrize(
    ("prop", "saved_value"),
    (
        (PropertySpec("value", "json", {}, "Value"), {1: "not-json"}),
        (PropertySpec("value", "json", {}, "Value"), {"number": float("nan")}),
        (
            PropertySpec(
                "value",
                "json",
                [],
                "Value",
                inline_editor="list",
                list_item_type="int",
            ),
            [True],
        ),
        (
            PropertySpec(
                "value",
                "interval_1d",
                Interval1D(1.0, 2.0),
                "Value",
                minimum=0.0,
                maximum=10.0,
                inline_editor="interval_slider",
                interval_direction="increasing",
                persistence_data_type_id=INTERVAL_1D_GRAPH_DATA_TYPE_ID,
            ),
            Interval1D(2.0, 1.0),
        ),
    ),
)
def test_invalid_generic_json_list_and_interval_values_are_rejected(
    prop: PropertySpec,
    saved_value: object,
) -> None:
    spec = _spec(properties=(prop,))
    project = _project(
        WorkspaceData(
            workspace_id="ws",
            name="Workspace",
            nodes={
                "node": _node(
                    "node",
                    spec.type_id,
                    properties={"value": saved_value},
                )
            },
        )
    )

    report = _report_for(spec, spec, project)

    assert [issue.code for issue in report.issues] == ["property_value_invalid"]


def test_candidate_invalid_edges_and_flow_cardinality_are_reported() -> None:
    source = _spec(
        type_id="tests.source",
        ports=(PortSpec("out", "out", "flow", "flow"),),
    )
    target = _spec(
        type_id="tests.target",
        ports=(
            PortSpec(
                "in",
                "in",
                "flow",
                "flow",
                required=False,
                allow_multiple_connections=True,
            ),
        ),
    )
    invalid_target = replace(
        target,
        ports=(
            PortSpec(
                "in",
                "in",
                "data",
                "COREX.DataTypes.Any",
                required=False,
            ),
        ),
    )
    cardinality_target = replace(
        target,
        ports=(replace(target.ports[0], allow_multiple_connections=False),),
    )
    workspace = WorkspaceData(
        workspace_id="ws",
        name="Workspace",
        nodes={
            "source_a": _node("source_a", source.type_id),
            "source_b": _node("source_b", source.type_id),
            "target": _node("target", target.type_id),
        },
        edges={
            "edge_a": EdgeInstance("edge_a", "source_a", "out", "target", "in"),
            "edge_b": EdgeInstance("edge_b", "source_b", "out", "target", "in"),
        },
    )
    project = _project(workspace)

    invalid_report = _report_for((source, target), (source, invalid_target), project)
    cardinality_report = _report_for(
        (source, target),
        (source, cardinality_target),
        project,
    )

    assert {
        issue.edge_id
        for issue in invalid_report.issues
        if issue.code == "candidate_invalid_edge"
    } == {"edge_a", "edge_b"}
    assert [
        issue.edge_id
        for issue in cardinality_report.issues
        if issue.code == "candidate_edge_cardinality"
    ] == ["edge_b"]


def _dynamic_ports(properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    values = properties.get("ports", [])
    if not isinstance(values, list):
        return ()
    return tuple(
        PortSpec(str(value), "out", "data", "COREX.DataTypes.Any")
        for value in values
    )


def _no_dynamic_ports(_properties: Mapping[str, object]) -> tuple[PortSpec, ...]:
    return ()


def _dynamic_spec(resolver) -> NodeTypeSpec:
    return _spec(
        type_id="tests.dynamic",
        properties=(
            PropertySpec("ports", "json", ["result"], "Ports", inspector_visible=False),
        ),
        dynamic_port_groups=(
            DynamicPortGroupSpec(
                "outputs",
                "ports",
                "out",
                resolver,
                lambda _properties: "new",
            ),
        ),
    )


def test_dynamic_effective_ports_cover_multiple_projects_and_workspaces() -> None:
    current = _dynamic_spec(_dynamic_ports)
    candidate = _dynamic_spec(_no_dynamic_ports)
    project_a = _project(
        WorkspaceData(
            workspace_id="ws_a",
            name="A",
            nodes={
                "node_a": _node(
                    "node_a",
                    current.type_id,
                    properties={"ports": ["a"]},
                )
            },
        ),
        WorkspaceData(
            workspace_id="ws_b",
            name="B",
            nodes={
                "node_b": _node(
                    "node_b",
                    current.type_id,
                    properties={"ports": ["b"]},
                )
            },
        ),
        project_id="project_a",
    )
    project_b = _project(
        WorkspaceData(
            workspace_id="ws_c",
            name="C",
            nodes={
                "node_c": _node(
                    "node_c",
                    current.type_id,
                    properties={"ports": ["c"]},
                )
            },
        ),
        project_id="project_b",
    )

    report = check_registry_compatibility(
        current_registry=_registry(current),
        candidate_registry=_registry(candidate),
        projects=(project_a, project_b),
    )

    removed = [issue for issue in report.issues if issue.code == "port_removed"]
    assert {(issue.project_id, issue.workspace_id, issue.member_key) for issue in removed} == {
        ("project_a", "ws_a", "a"),
        ("project_a", "ws_b", "b"),
        ("project_b", "ws_c", "c"),
    }
