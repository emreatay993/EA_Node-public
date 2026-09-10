from __future__ import annotations

from pathlib import Path

import pytest

from ea_node_editor.graph.model import GraphModel
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.function_plugin import PythonFunctionRef
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.nodes.plugin_contracts import PluginDescriptor, PluginProvenance
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui_qml.graph_scene_payload import GraphScenePayloadBuilder
from ea_node_editor.ui_qml.node_title_icon_sources import (
    resolve_node_title_icon_source,
    title_icon_presentation_for_node_payload,
    title_icon_source_for_node_payload,
    title_icon_theme_aware_for_node_payload,
)


class _Plugin:
    def __init__(self, spec: NodeTypeSpec) -> None:
        self._spec = spec

    def spec(self) -> NodeTypeSpec:
        return self._spec

    def execute(self, _ctx) -> NodeResult:  # noqa: ANN001
        return NodeResult()


def _spec(
    type_id: str,
    icon: str,
    *,
    runtime_behavior: str = "active",
    show_title_icon: bool = False,
) -> NodeTypeSpec:
    return NodeTypeSpec(
        type_id=type_id,
        display_name=type_id.rsplit(".", 1)[-1].replace("_", " ").title(),
        category_path=("Tests",),
        icon=icon,
        ports=(PortSpec("value", "out", "data", 'COREX.DataTypes.Any'),),
        properties=(),
        runtime_behavior=runtime_behavior,  # type: ignore[arg-type]
        show_title_icon=show_title_icon,
    )


def _factory(spec: NodeTypeSpec):
    return lambda: _Plugin(spec)


def test_title_icon_resolver_accepts_supported_absolute_local_paths(tmp_path: Path) -> None:
    for suffix in (".svg", ".PNG", ".jpg", ".JPEG"):
        icon_path = tmp_path / f"icon{suffix}"
        icon_path.write_bytes(b"icon")

        assert resolve_node_title_icon_source(str(icon_path)) == icon_path.resolve().as_uri()


def test_title_icon_resolver_rejects_invalid_icon_values(tmp_path: Path) -> None:
    unsupported_path = tmp_path / "icon.gif"
    unsupported_path.write_bytes(b"icon")
    missing_path = tmp_path / "missing.svg"

    for value in (
        "",
        "warning",
        "https://example.test/icon.svg",
        "data:image/svg+xml;base64,PHN2Zy8+",
        str(unsupported_path),
        str(missing_path),
    ):
        assert resolve_node_title_icon_source(value) == ""


def test_title_icon_resolver_rejects_unreadable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    icon_path = tmp_path / "unreadable.svg"
    icon_path.write_bytes(b"icon")
    real_open = Path.open

    def _raise_for_icon(path: Path, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if path.resolve(strict=False) == icon_path.resolve():
            raise OSError("permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _raise_for_icon)

    assert resolve_node_title_icon_source(str(icon_path)) == ""


def test_title_icon_resolver_resolves_builtin_relative_paths_from_asset_root(tmp_path: Path) -> None:
    asset_root = tmp_path / "node_title_icons"
    icon_path = asset_root / "core" / "start.svg"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"icon")
    outside_path = tmp_path / "outside.svg"
    outside_path.write_bytes(b"icon")

    assert (
        resolve_node_title_icon_source("core/start.svg", asset_root=asset_root)
        == icon_path.resolve().as_uri()
    )
    assert resolve_node_title_icon_source("../outside.svg", asset_root=asset_root) == ""


def test_title_icon_resolver_resolves_plugin_relative_paths_from_file_and_package_roots(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin_root"
    package_root = tmp_path / "package_root"
    file_icon_path = plugin_root / "icons" / "file.svg"
    package_icon_path = package_root / "icons" / "package.png"
    file_icon_path.parent.mkdir(parents=True)
    package_icon_path.parent.mkdir(parents=True)
    file_icon_path.write_bytes(b"icon")
    package_icon_path.write_bytes(b"icon")

    file_provenance = PluginProvenance(
        kind="file",
        source_path=plugin_root / "file_plugin.py",
    )
    package_provenance = PluginProvenance(
        kind="package",
        source_path=package_root / "package_plugin.py",
        package_root=package_root,
        package_name="package_root",
    )

    assert (
        resolve_node_title_icon_source("icons/file.svg", provenance=file_provenance)
        == file_icon_path.resolve().as_uri()
    )
    assert (
        resolve_node_title_icon_source("icons/package.png", provenance=package_provenance)
        == package_icon_path.resolve().as_uri()
    )


def test_title_icon_resolver_rejects_absolute_paths_for_plugin_provenance(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin_root"
    icon_path = plugin_root / "icons" / "absolute.svg"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"icon")

    provenance = PluginProvenance(
        kind="file",
        source_path=plugin_root / "file_plugin.py",
    )

    assert resolve_node_title_icon_source(str(icon_path), provenance=provenance) == ""


def test_title_icon_resolver_does_not_fallback_to_base_assets_for_plugin_paths(tmp_path: Path) -> None:
    base_asset_root = tmp_path / "base" / "node_title_icons"
    base_icon_path = base_asset_root / "core" / "play_arrow.svg"
    base_icon_path.parent.mkdir(parents=True)
    base_icon_path.write_bytes(b"icon")

    plugin_root = tmp_path / "plugin_root"
    plugin_root.mkdir()
    provenance = PluginProvenance(
        kind="file",
        source_path=plugin_root / "file_plugin.py",
    )

    assert (
        resolve_node_title_icon_source(
            "core/play_arrow.svg",
            provenance=provenance,
            asset_root=base_asset_root,
        )
        == ""
    )


def test_title_icon_source_for_node_payload_allows_only_active_and_compile_only_specs(
    tmp_path: Path,
) -> None:
    icon_path = tmp_path / "node.svg"
    icon_path.write_bytes(b"icon")

    active_spec = _spec("tests.title_icon.active", str(icon_path), runtime_behavior="active")
    compile_only_spec = _spec(
        "tests.title_icon.compile_only",
        str(icon_path),
        runtime_behavior="compile_only",
    )
    passive_spec = _spec("tests.title_icon.passive", str(icon_path), runtime_behavior="passive")

    assert title_icon_source_for_node_payload(active_spec) == icon_path.resolve().as_uri()
    assert title_icon_source_for_node_payload(compile_only_spec) == icon_path.resolve().as_uri()
    assert title_icon_source_for_node_payload(passive_spec) == ""


def test_title_icon_presentation_resolves_source_and_theme_awareness_together() -> None:
    spec = _spec("tests.title_icon.presentation", "core/start.svg")

    presentation = title_icon_presentation_for_node_payload(spec)

    assert presentation.source == title_icon_source_for_node_payload(spec)
    assert presentation.theme_aware == title_icon_theme_aware_for_node_payload(spec)


def test_title_icon_source_for_passive_spec_honors_show_title_icon_opt_in(
    tmp_path: Path,
) -> None:
    """Passive specs that set ``show_title_icon=True`` render their icon.

    Default-passive suppression exists for flowchart/planning/annotation/
    media families that draw their own body art; data-source-style passive
    nodes (``io.path_pointer``) opt back in via this flag.
    """
    icon_path = tmp_path / "passive.svg"
    icon_path.write_bytes(b"icon")

    opted_in = _spec(
        "tests.title_icon.passive.opted_in",
        str(icon_path),
        runtime_behavior="passive",
        show_title_icon=True,
    )
    default = _spec(
        "tests.title_icon.passive.default",
        str(icon_path),
        runtime_behavior="passive",
    )

    assert title_icon_source_for_node_payload(opted_in) == icon_path.resolve().as_uri()
    assert title_icon_source_for_node_payload(default) == ""


def test_title_icon_theme_awareness_marks_repo_owned_svg_assets_only(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "node_title_icons"
    icon_path = asset_root / "core" / "start.svg"
    png_icon_path = asset_root / "core" / "start.png"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"icon")
    png_icon_path.write_bytes(b"icon")

    active_svg = _spec("tests.title_icon.theme_svg", "core/start.svg")
    active_png = _spec("tests.title_icon.theme_png", "core/start.png")
    passive_svg = _spec(
        "tests.title_icon.theme_passive",
        "core/start.svg",
        runtime_behavior="passive",
    )
    passive_opt_in_svg = _spec(
        "tests.title_icon.theme_passive_opt_in",
        "core/start.svg",
        runtime_behavior="passive",
        show_title_icon=True,
    )

    assert title_icon_theme_aware_for_node_payload(active_svg, asset_root=asset_root)
    assert not title_icon_theme_aware_for_node_payload(active_png, asset_root=asset_root)
    assert not title_icon_theme_aware_for_node_payload(passive_svg, asset_root=asset_root)
    assert title_icon_theme_aware_for_node_payload(passive_opt_in_svg, asset_root=asset_root)
    assert not title_icon_theme_aware_for_node_payload(
        active_svg,
        provenance=PluginProvenance(
            kind="file",
            source_path=tmp_path / "plugin.py",
        ),
        asset_root=asset_root,
    )
    assert not title_icon_theme_aware_for_node_payload(
        _spec("tests.title_icon.theme_absolute", str(icon_path)),
        asset_root=asset_root,
    )


def test_title_icon_scene_payload_uses_registry_provenance_without_persistence_fields(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    active_icon_path = plugin_root / "icons" / "active.svg"
    compile_icon_path = plugin_root / "icons" / "compile.svg"
    active_icon_path.parent.mkdir(parents=True)
    active_icon_path.write_bytes(b"active")
    compile_icon_path.write_bytes(b"compile")
    provenance = PluginProvenance(
        kind="file",
        source_path=plugin_root / "plugin.py",
    )
    active_spec = _spec("tests.title_icon.active_payload", "icons/active.svg")
    compile_spec = _spec(
        "tests.title_icon.compile_payload",
        "icons/compile.svg",
        runtime_behavior="compile_only",
    )
    missing_spec = _spec("tests.title_icon.missing_payload", "icons/missing.svg")

    registry = NodeRegistry()
    for spec in (active_spec, compile_spec, missing_spec):
        registry.register_descriptor(
            PluginDescriptor(
                spec=spec,
                factory=_factory(spec),
                provenance=provenance,
            )
        )

    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    for index, spec in enumerate((active_spec, compile_spec, missing_spec)):
        model.add_node(workspace_id, spec.type_id, spec.display_name, 80.0 + index * 160.0, 90.0)

    builder = GraphScenePayloadBuilder()
    nodes_payload, _backdrops, _minimap, _edges = builder.rebuild_partitioned_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )
    payload_by_type = {payload["type_id"]: payload for payload in nodes_payload}

    assert payload_by_type[active_spec.type_id]["icon_source"] == active_icon_path.resolve().as_uri()
    assert payload_by_type[compile_spec.type_id]["icon_source"] == compile_icon_path.resolve().as_uri()
    assert payload_by_type[missing_spec.type_id]["icon_source"] == ""
    assert not payload_by_type[active_spec.type_id]["icon_theme_aware"]
    assert not payload_by_type[compile_spec.type_id]["icon_theme_aware"]
    assert not payload_by_type[missing_spec.type_id]["icon_theme_aware"]
    first_node = model.active_workspace.nodes[next(iter(model.active_workspace.nodes))]
    assert not hasattr(first_node, "icon_source")


def test_title_icon_scene_payload_marks_builtin_svg_icons_theme_aware() -> None:
    spec = _spec("tests.title_icon.builtin_theme_payload", "core/data_object.svg")
    registry = NodeRegistry()
    registry.register_descriptor(
        PluginDescriptor(
            spec=spec,
            factory=_factory(spec),
        )
    )

    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    model.add_node(workspace_id, spec.type_id, spec.display_name, 80.0, 90.0)

    builder = GraphScenePayloadBuilder()
    nodes_payload, _backdrops, _minimap, _edges = builder.rebuild_partitioned_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )

    payload = nodes_payload[0]
    assert payload["icon_source"].endswith("/ea_node_editor/assets/node_title_icons/core/data_object.svg")
    assert payload["icon_theme_aware"]


def test_title_icon_scene_payload_uses_public_function_package_provenance(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / ("a" * 64)
    icon_path = package_root / "assets" / "node.svg"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"icon")
    spec = _spec("custom.title_icon.1234abcd", "assets/node.svg")
    provenance = PluginProvenance(
        kind="package",
        source_path=package_root / "nodes.py",
        package_root=package_root,
        package_name="title_icons",
    )
    registry = NodeRegistry()
    registry.register_python_function(
        spec,
        PythonFunctionRef(
            bundle_id="plugin:package:title_icons",
            bundle_digest="a" * 64,
            module_relative_path="nodes.py",
            function_name="title_icon",
            source_digest="b" * 64,
        ),
        provenance=provenance,
    )
    model = GraphModel()
    workspace_id = model.active_workspace.workspace_id
    model.add_node(workspace_id, spec.type_id, spec.display_name, 80.0, 90.0)

    nodes_payload, _backdrops, _minimap, _edges = GraphScenePayloadBuilder().rebuild_partitioned_models(
        model=model,
        registry=registry,
        workspace_id=workspace_id,
        scope_path=(),
        graph_theme_bridge=None,
    )

    assert nodes_payload[0]["icon_source"] == icon_path.resolve().as_uri()
    assert not nodes_payload[0]["icon_theme_aware"]


def test_repo_owned_addon_uses_central_theme_aware_asset_from_registry_provenance(
    tmp_path: Path,
) -> None:
    from ea_node_editor.nodes.bootstrap import build_default_registry

    registry = build_default_registry(
        include_public_plugins=False,
        addon_runtime_config=(("mechanical.corex", True),),
        generation_root=tmp_path / "generations",
    )
    spec = registry.get_spec("mechanical.open_model")
    provenance = registry.provenance_or_none(spec.type_id)

    presentation = title_icon_presentation_for_node_payload(
        spec,
        provenance=provenance,
    )

    assert presentation.source.endswith(
        "/ea_node_editor/assets/node_title_icons/mechanical/open.svg"
    )
    assert presentation.theme_aware


def test_external_package_cannot_spoof_repo_owned_central_icon_fallback(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "external_generation"
    external_icon = package_root / "mechanical" / "open.svg"
    external_icon.parent.mkdir(parents=True)
    external_icon.write_bytes(b"external")
    provenance = PluginProvenance(
        kind="package",
        source_path=package_root / "nodes.py",
        package_root=package_root,
        package_name="mechanical",
    )
    spoofed = _spec("mechanical.open_model", "mechanical/open.svg")

    presentation = title_icon_presentation_for_node_payload(
        spoofed,
        provenance=provenance,
    )
    assert presentation.source == external_icon.resolve().as_uri()
    assert not presentation.theme_aware

    external_icon.unlink()
    presentation = title_icon_presentation_for_node_payload(
        spoofed,
        provenance=provenance,
    )
    assert presentation.source == ""
    assert not presentation.theme_aware
