# Purpose: Prove the unified Media Panel declaration and source validation.
# Map: feature_routes/media_image_video_pdf_refocus.md
# Tests: tests/test_media_panel.py

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.media_panel import (
    MEDIA_PANEL_TYPE_ID,
    MediaPanelNodePlugin,
)
from ea_node_editor.nodes.execution_context import (
    ExecutionContext,
    NodeInputNotReadyError,
)
from ea_node_editor.nodes.file_dialog_filters import (
    MEDIA_FILES_FILTER,
    is_supported_media_source_reference,
    media_kind_from_source,
)
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.runtime_contracts import DataTree, ImageValue, RuntimeArtifactRef
from tests.test_dataflow_execution_runtime import (
    _output_tree,
    _registry as _runtime_registry,
    _run,
    _settled,
    _source,
)

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)
def _context(
    source: object,
    *,
    iteration_count: int = 1,
    path_resolver=lambda _value: None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run",
        node_id="media",
        workspace_id="workspace",
        inputs={"source": source},
        properties={"source": "dormant.png"},
        emit_log=lambda _level, _message: None,
        iteration_count=iteration_count,
        path_resolver=path_resolver,
    )


def test_media_panel_has_exact_active_contract_and_static_settings_superset() -> None:
    registry = build_builtin_registry()
    spec = registry.spec_or_none(MEDIA_PANEL_TYPE_ID)
    assert spec is not None
    assert (spec.display_name, spec.category_path) == ("Media Panel", ("Media",))
    assert (spec.runtime_behavior, spec.surface_family, spec.surface_variant) == (
        "active",
        "media",
        "media_panel",
    )
    assert tuple(port.key for port in spec.ports) == ("source", "_surface_source")
    source, surface_source = spec.ports
    assert (
        source.direction,
        source.kind,
        source.data_type,
        source.accepted_data_types,
        source.data_access,
        source.required,
        source.uses_property_default,
        source.exposed,
    ) == (
        "in",
        "data",
        "COREX.DataTypes.Path",
        ("COREX.DataTypes.String", "COREX.DataTypes.Image"),
        "item",
        False,
        False,
        True,
    )
    assert (
        surface_source.direction,
        surface_source.kind,
        surface_source.data_type,
        surface_source.exposed,
    ) == ("out", "data", "COREX.DataTypes.Any", False)
    assert tuple(prop.key for prop in spec.properties) == (
        "source",
        "fit_mode",
        "animation_playback_mode",
        "lock_aspect_ratio",
        "show_title",
        "show_frame",
        "crop_x",
        "crop_y",
        "crop_w",
        "crop_h",
        "rotation_degrees",
        "mirror_horizontal",
        "mirror_vertical",
        "page_number",
        "auto_play",
        "loop",
        "muted",
        "volume",
        "playback_rate",
        "position_ms",
        "timeline_bookmarks",
        "clip_enabled",
        "clip_start_ms",
        "clip_end_ms",
    )
    assert MEDIA_FILES_FILTER == next(
        prop.file_filter for prop in spec.properties if prop.key == "source"
    )
    assert not (
        {"source_path", "media_kind", "unfocused_behavior"}
        & {prop.key for prop in spec.properties}
    )
    assert next(prop for prop in spec.properties if prop.key == "source").inspector_visible
    assert all(
        not prop.inspector_visible for prop in spec.properties if prop.key != "source"
    )


def test_registry_keeps_media_panel_and_mail_as_separate_nodes() -> None:
    registry = build_builtin_registry()
    assert len(registry.all_specs()) == 129
    assert registry.spec_or_none(MEDIA_PANEL_TYPE_ID) is not None
    mail = registry.spec_or_none("passive.media.mail_panel")
    assert mail is not None
    assert mail.runtime_behavior == "passive"
    assert tuple(port.key for port in mail.ports) == ("top", "right", "bottom", "left")
    assert tuple(prop.key for prop in mail.properties) == (
        "source_path",
        "show_title",
        "show_frame",
    )


@pytest.mark.parametrize(
    ("source", "kind"),
    (
        (r"C:\media\image.PNG", "image"),
        ("file:///C:/media/document.pdf", "pdf"),
        ("https://example.test/video.mp4?token=1", "video"),
        (Path("clip.webm"), "video"),
    ),
)
def test_media_source_classification_and_execution(source: object, kind: str) -> None:
    assert media_kind_from_source(source) == kind
    result = MediaPanelNodePlugin().execute(_context(source))
    assert result.outputs == {
        "_surface_source": str(source) if isinstance(source, Path) else source
    }


@pytest.mark.parametrize("source", ("saved://managed_media", "temp://staged_media"))
def test_project_media_reference_syntax(source: str) -> None:
    assert is_supported_media_source_reference(source)


def _artifact(format: str) -> RuntimeArtifactRef:
    return RuntimeArtifactRef.staged(
        f"media_{format}",
        data_type_id="COREX.DataTypes.Path",
        schema_version=1,
        format=format,
        size_bytes=1,
        sha256="0" * 64,
        provenance="corex.test.media_panel",
    )


def test_typed_project_artifact_is_resolved_verified_and_preserved() -> None:
    artifact = _artifact("mp4")
    resolved: list[object] = []

    def resolver(value: object) -> Path:
        resolved.append(value)
        return Path("resolved/video.mp4")

    result = MediaPanelNodePlugin().execute(
        _context(artifact, path_resolver=resolver)
    )
    assert resolved == [artifact]
    assert result.outputs["_surface_source"] is artifact


def test_typed_project_artifact_rejects_unsupported_declared_format() -> None:
    artifact = _artifact("txt")
    resolved: list[object] = []

    def resolver(value: object) -> Path:
        resolved.append(value)
        return Path("resolved/video.mp4")

    with pytest.raises(ValueError, match="Media Panel source"):
        MediaPanelNodePlugin().execute(_context(artifact, path_resolver=resolver))
    assert resolved == [artifact]


def test_exact_image_value_is_returned_without_copying_bytes() -> None:
    image = ImageValue.from_png(_PNG_BYTES)
    result = MediaPanelNodePlugin().execute(_context(image))
    assert result.outputs["_surface_source"] is image


@pytest.mark.parametrize(
    "source",
    (
        "",
        "notes.txt",
        "ftp://example.test/video.mp4",
        "data:image/png;base64,AAAA",
        "javascript:alert('/image.png')",
        "mailto:user@example.png",
        "https:/example.test/image.png",
        "http:example.test/image.png",
        "https:///image.png",
        "1http://example.test/image.png",
        "saved://bad/id",
        object(),
    ),
)
def test_empty_or_unsupported_source_never_falls_back_to_authored_property(
    source: object,
) -> None:
    error = NodeInputNotReadyError if source == "" else ValueError
    with pytest.raises(error):
        MediaPanelNodePlugin().execute(_context(source))


@pytest.mark.parametrize(
    ("source", "kind"),
    (
        (r"C:\media\image.png", "image"),
        (r"C:relative\document.pdf", "pdf"),
        (r"\\server\share\video.mp4", "video"),
    ),
)
def test_windows_drive_and_unc_paths_are_not_mistaken_for_uri_schemes(
    source: str, kind: str
) -> None:
    assert media_kind_from_source(source) == kind


@pytest.mark.parametrize(
    "source",
    (
        "http://[invalid/image.png",
        "https://example.test:not-a-port/video.mp4",
    ),
)
def test_malformed_url_classification_is_total(source: str) -> None:
    assert media_kind_from_source(source) == ""
    assert not is_supported_media_source_reference(source)


def test_malformed_path_reference_classification_is_total() -> None:
    class BrokenPath:
        def __fspath__(self):  # noqa: ANN204
            raise ValueError("malformed reference")

    assert media_kind_from_source(BrokenPath()) == ""


def test_media_panel_rejects_multi_item_execution_explicitly() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        MediaPanelNodePlugin().execute(_context("image.png", iteration_count=2))
    with pytest.raises(ValueError, match="exactly one item"):
        MediaPanelNodePlugin().execute(
            _context(DataTree.from_list(("image.png", "document.pdf")))
        )


def test_media_panel_source_mutation_requires_hidden_source_input() -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id=MEDIA_PANEL_TYPE_ID,
        title="Media Panel",
        x=0.0,
        y=0.0,
        properties={**registry.default_properties(MEDIA_PANEL_TYPE_ID), "source": "old.png"},
        exposed_ports={"source": True, "_surface_source": False},
    )

    with pytest.raises(PermissionError, match="Source input is exposed"):
        mutations.set_node_property(node.node_id, "source", "new.png")
    with pytest.raises(PermissionError, match="Source input is exposed"):
        mutations.set_node_properties(
            node.node_id,
            {"source": "new.png", "fit_mode": "cover"},
        )
    assert node.properties["source"] == "old.png"
    assert node.properties["fit_mode"] == "contain"

    assert mutations.set_exposed_port(node.node_id, "source", False)
    assert mutations.set_node_property(node.node_id, "source", "new.png") == "new.png"
    assert node.properties["source"] == "new.png"


@pytest.mark.parametrize("pre_dirty", (False, True))
def test_unchanged_exposed_media_source_is_an_exact_noop(pre_dirty: bool) -> None:
    registry = build_builtin_registry()
    model = GraphModel()
    workspace = model.active_workspace
    mutations = model.validated_mutations(workspace.workspace_id, registry)
    node = mutations.add_node(
        type_id=MEDIA_PANEL_TYPE_ID,
        title="Media Panel",
        x=0.0,
        y=0.0,
        properties={**registry.default_properties(MEDIA_PANEL_TYPE_ID), "source": "same.png"},
        exposed_ports={"source": True, "_surface_source": False},
    )
    workspace.dirty = pre_dirty
    workspace.mutation_revision = 137 if pre_dirty else 113
    before_node_ids = set(workspace.nodes)
    before_edges = dict(workspace.edges)
    before_metadata = dict(model.project.metadata)

    assert mutations.set_node_property(node.node_id, "source", "same.png") == "same.png"
    assert mutations.set_node_properties(node.node_id, {"source": "same.png"}) == {}

    assert set(workspace.nodes) == before_node_ids
    assert workspace.edges == before_edges
    assert model.project.metadata == before_metadata
    assert workspace.dirty is pre_dirty
    assert workspace.mutation_revision == (137 if pre_dirty else 113)


def test_hidden_surface_output_settles_and_multi_item_runtime_fails_atomically() -> (
    None
):
    registry = _runtime_registry()

    single_model = GraphModel()
    single_workspace = single_model.active_workspace
    source = single_model.add_node(
        single_workspace.workspace_id,
        "core.constant",
        "Source",
        0,
        0,
        properties={"value": "image.png"},
    )
    panel = single_model.add_node(
        single_workspace.workspace_id,
        MEDIA_PANEL_TYPE_ID,
        "Media",
        100,
        0,
    )
    single_model.add_edge(
        single_workspace.workspace_id,
        source.node_id,
        "value",
        panel.node_id,
        "source",
    )
    settled = _settled(
        _run(single_model, registry, run_id="media_single"), panel.node_id
    )
    assert _output_tree(settled, "_surface_source") == DataTree.from_item("image.png")

    multi_model = GraphModel()
    multi_workspace = multi_model.active_workspace
    multi_source = _source(
        multi_model,
        "Sources",
        [[[0], ["image.png", "document.pdf"]]],
    )
    multi_panel = multi_model.add_node(
        multi_workspace.workspace_id,
        MEDIA_PANEL_TYPE_ID,
        "Media",
        100,
        0,
    )
    multi_model.add_edge(
        multi_workspace.workspace_id,
        multi_source.node_id,
        "tree",
        multi_panel.node_id,
        "source",
    )
    failed = _settled(
        _run(multi_model, registry, run_id="media_multi"), multi_panel.node_id
    )
    assert failed["status"] == "failed"
    assert "exactly one runtime item" in failed["errors"][0]["error"]
