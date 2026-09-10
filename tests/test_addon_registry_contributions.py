from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons import registry_contributions
from ea_node_editor.nodes import package_schema, plugin_generation
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec
from ea_node_editor.nodes.plugin_contracts import (
    ArtifactDescriptor,
    PluginAvailability,
    PluginBackendDescriptor,
    PluginContractManifest,
    PluginDescriptor,
    PluginProvenance,
    RuntimeBackendSpec,
    SurfaceCapabilitySpec,
    ToolchainRequirementSpec,
    ToolchainSpec,
)
from ea_node_editor.nodes.registry import NodeRegistry, PythonFunctionEntry
from ea_node_editor.runtime_contracts import DataTypeFamilySpec, DataTypeSpec
from ea_node_editor.ui_qml.node_title_icon_sources import (
    resolve_node_title_icon_source,
)


def _write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def _packet_descriptor(type_id: str, display_name: str) -> PluginDescriptor:
    class PacketBackendPlugin:
        def spec(self):  # noqa: ANN201
            return NodeTypeSpec(
                type_id=type_id,
                display_name=display_name,
                category_path=("Packet Tests",),
                icon="packet",
                ports=(),
                properties=(),
            )

        def execute(self, ctx):  # noqa: ANN001, ANN201
            return NodeResult()

    return PluginDescriptor(
        spec=PacketBackendPlugin().spec(),
        factory=PacketBackendPlugin,
    )


def _typed_packet_descriptor(
    node_type_id: str,
    data_type_id: str,
) -> PluginDescriptor:
    spec = NodeTypeSpec(
        type_id=node_type_id,
        display_name="Typed Packet",
        category_path=("Packet Tests",),
        icon="packet",
        ports=(PortSpec("value", "out", "data", data_type_id),),
        properties=(),
    )

    class TypedPacketPlugin:
        def spec(self):  # noqa: ANN201
            return spec

        def execute(self, ctx):  # noqa: ANN001, ANN201
            return NodeResult()

    return PluginDescriptor(spec=spec, factory=TypedPacketPlugin)


def _packet_data_type_contract(
    *,
    family_id: str = "packet_plugin",
    type_id: str = "Packet.Plugin.Value",
) -> tuple[tuple[DataTypeFamilySpec, ...], tuple[DataTypeSpec, ...]]:
    return (
        (DataTypeFamilySpec(family_id, "Packet", "data.packet", "packet"),),
        (
            DataTypeSpec(
                type_id,
                "Packet Value",
                family_id,
                lambda value: True,
                parents=(GRAPH_DATA_TYPE_ID,),
            ),
        ),
    )


def _function_source(type_id: str) -> str:
    return f"""import corex
@corex.node(id={type_id!r}, name="Static Node", category=("Tests",))
@corex.input("value", value_type=float)
@corex.output("result", value_type=float)
def static_node(ctx, value):
    return {{"result": value}}
"""


def _function_backend(
    *,
    owner_id: str,
    type_id: str,
    source: str | None = None,
    descriptors: tuple[PluginDescriptor, ...] = (),
    availability=None,  # noqa: ANN001
    provenance: PluginProvenance | None = None,
) -> PluginBackendDescriptor:
    return PluginBackendDescriptor(
        plugin_id=owner_id,
        display_name="Function Backend",
        get_availability=(
            availability
            if availability is not None
            else lambda: PluginAvailability.available()
        ),
        load_descriptors=lambda: descriptors,
        load_function_sources=lambda: (
            ("functions.py", source or _function_source(type_id)),
        ),
        function_type_ids=(type_id,),
        provenance=provenance,
    )


def test_live_addon_contribution_dispatch_does_not_aggregate_ignored_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collections = (
        SimpleNamespace(backends=("first",), source="first.source"),
        SimpleNamespace(backends=("second",), source="second.source"),
    )
    calls: list[tuple[object, NodeRegistry, str, Path]] = []
    registry = NodeRegistry()
    monkeypatch.setattr(
        "ea_node_editor.addons.catalog.live_addon_backend_collections",
        lambda **_kwargs: collections,
    )

    def register(backends, target, source, *, generation_root):  # noqa: ANN001
        calls.append((backends, target, source, generation_root))
        return ["ignored"]

    monkeypatch.setattr(registry_contributions, "register_plugin_backends", register)

    result = registry_contributions.register_live_addon_contributions(
        registry,
        preferences_document={},
        generation_root=tmp_path,
    )

    assert result is None
    assert calls == [
        (("first",), registry, "first.source", tmp_path),
        (("second",), registry, "second.source", tmp_path),
    ]


def test_plugin_backend_function_contract_rejects_inconsistent_fields() -> None:
    fields = {
        "plugin_id": "packet.functions",
        "display_name": "Packet Functions",
        "get_availability": lambda: PluginAvailability.available(),
        "load_descriptors": lambda: (),
    }
    with pytest.raises(TypeError, match="load_function_sources"):
        PluginBackendDescriptor(
            **fields,
            load_function_sources="not callable",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="function_type_ids must be a tuple"):
        PluginBackendDescriptor(
            **fields,
            load_function_sources=lambda: (("node.py", ""),),
            function_type_ids=["packet.function"],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be unique"):
        PluginBackendDescriptor(
            **fields,
            load_function_sources=lambda: (("node.py", ""),),
            function_type_ids=("packet.function", "packet.function"),
        )
    with pytest.raises(ValueError, match="trimmed"):
        PluginBackendDescriptor(
            **fields,
            load_function_sources=lambda: (("node.py", ""),),
            function_type_ids=(" packet.function",),
        )
    with pytest.raises(ValueError, match="declared together"):
        PluginBackendDescriptor(**fields, function_type_ids=("packet.function",))
    with pytest.raises(ValueError, match="declared together"):
        PluginBackendDescriptor(
            **fields,
            load_function_sources=lambda: (("node.py", ""),),
        )


def test_plugin_backend_functions_are_static_deterministic_and_worker_compatible(
    tmp_path: Path,
) -> None:
    owner_id = "packet.functions"
    type_id = "packet.function"
    marker = tmp_path / "executed.txt"
    package_root = tmp_path / "trusted-package"
    icon_path = _write_text(package_root / "icons" / "node.svg", "<svg/>")
    provenance = PluginProvenance(
        kind="package",
        source_path=package_root / "catalog.py",
        package_root=package_root,
        package_name="trusted-package",
    )
    availability_calls = 0

    def availability() -> PluginAvailability:
        nonlocal availability_calls
        availability_calls += 1
        return PluginAvailability.available()

    source = f"""import corex
from pathlib import Path
Path({str(marker)!r}).write_text("executed", encoding="utf-8")

@corex.node(id={type_id!r}, name="Static Node", category=("Tests",), icon="icons/node.svg")
@corex.text("setting", default="", _property_group="Configuration", _inspector_visible=False)
@corex.output("result", value_type=float)
def static_node(ctx, settings):
    return {{"result": float(bool(settings.setting))}}
"""
    descriptor = _packet_descriptor("packet.descriptor", "Packet Descriptor")
    backend = _function_backend(
        owner_id=owner_id,
        type_id=type_id,
        source=source,
        descriptors=(descriptor,),
        availability=availability,
        provenance=provenance,
    )

    first = NodeRegistry()
    loaded = registry_contributions.register_plugin_backends(
        (backend,), first, "packet.functions", generation_root=tmp_path / "first"
    )

    assert availability_calls == 1
    assert loaded == [descriptor.spec.type_id, type_id]
    assert not marker.exists()
    assert first.descriptor_or_none(descriptor.spec.type_id) is not None
    entry = first.get_entry(type_id)
    assert isinstance(entry, PythonFunctionEntry)
    assert entry.provenance is provenance
    assert (
        resolve_node_title_icon_source(entry.spec.icon, provenance=entry.provenance)
        == icon_path.resolve().as_uri()
    )
    bundle = first.plugin_bundle_refs()[0]
    assert bundle.owner_id == owner_id
    assert tuple(ref.bundle_id for ref in bundle.functions) == (owner_id,)
    assert Path(bundle.approved_generation_root) != package_root
    assert (
        Path(bundle.approved_generation_root) / bundle.functions[0].module_relative_path
    ).is_file()
    generation = plugin_generation.read_verified_plugin_generation(bundle)
    package = package_schema.ValidatedPackage(
        package_schema.validate_package_manifest(generation.manifest),
        dict(generation.members),
    )
    declarations = package_schema.validated_package_declarations(
        package,
        filename_prefix=owner_id,
        owner_id=owner_id,
        allow_internal_metadata=True,
    )
    assert tuple(item.spec.type_id for _path, item in declarations) == (type_id,)
    assert not marker.exists()

    second = NodeRegistry()
    registry_contributions.register_plugin_backends(
        (backend,), second, "packet.functions", generation_root=tmp_path / "second"
    )
    assert first.plugin_fingerprint() == second.plugin_fingerprint()
    assert first.contract_fingerprint() == second.contract_fingerprint()
    assert (
        first.plugin_bundle_refs()[0].approved_generation_root
        != second.plugin_bundle_refs()[0].approved_generation_root
    )


@pytest.mark.parametrize(
    "sources",
    [
        [("list.py", _function_source("packet.function"))],
        (("../escape.py", _function_source("packet.function")),),
        (
            ("duplicate.py", _function_source("packet.function")),
            ("DUPLICATE.py", _function_source("packet.other")),
        ),
        (("bytes.py", b"not source text"),),
        (("large.py", " " * (package_schema.PLUGIN_SOURCE_LIMIT + 1)),),
    ],
    ids=(
        "list-container",
        "parent-traversal",
        "casefold-duplicate",
        "bytes-source",
        "oversized-source",
    ),
)
def test_plugin_backend_function_sources_reject_path_duplicate_and_size_bounds(
    tmp_path: Path,
    sources: object,
) -> None:
    backend = PluginBackendDescriptor(
        plugin_id="packet.functions",
        display_name="Packet Functions",
        get_availability=lambda: PluginAvailability.available(),
        load_descriptors=lambda: (),
        load_function_sources=lambda: sources,  # type: ignore[return-value]
        function_type_ids=("packet.function",),
    )
    registry = NodeRegistry()

    assert (
        registry_contributions.register_plugin_backends(
            (backend,),
            registry,
            "packet.functions",
            generation_root=tmp_path / "generations",
        )
        == []
    )
    assert registry.spec_or_none("packet.function") is None
    assert registry.plugin_bundle_refs() == ()


def test_plugin_backend_function_mismatch_and_unavailability_contribute_nothing(
    tmp_path: Path,
) -> None:
    source_calls = 0

    def unavailable_sources() -> tuple[tuple[str, str], ...]:
        nonlocal source_calls
        source_calls += 1
        return (("functions.py", _function_source("packet.unavailable")),)

    mismatch = _function_backend(
        owner_id="packet.mismatch",
        type_id="packet.expected",
        source=_function_source("packet.actual"),
    )
    unavailable = PluginBackendDescriptor(
        plugin_id="packet.unavailable",
        display_name="Unavailable Functions",
        get_availability=lambda: PluginAvailability.missing_dependency("packet"),
        load_descriptors=lambda: (),
        load_function_sources=unavailable_sources,
        function_type_ids=("packet.unavailable",),
    )
    registry = NodeRegistry()

    assert (
        registry_contributions.register_plugin_backends(
            (mismatch, unavailable),
            registry,
            "packet.functions",
            generation_root=tmp_path / "generations",
        )
        == []
    )
    assert source_calls == 0
    assert registry.all_specs() == []
    assert registry.plugin_bundle_refs() == ()


def test_plugin_backend_owner_replacement_removes_old_functions_and_descriptors(
    tmp_path: Path,
) -> None:
    owner_id = "packet.replace"
    registry = NodeRegistry()
    old_backend = _function_backend(
        owner_id=owner_id,
        type_id="packet.old_function",
        descriptors=(_packet_descriptor("packet.old_descriptor", "Old"),),
    )
    new_backend = _function_backend(
        owner_id=owner_id,
        type_id="packet.new_function",
        descriptors=(_packet_descriptor("packet.new_descriptor", "New"),),
    )
    registry_contributions.register_plugin_backends(
        (old_backend,),
        registry,
        "packet.replace",
        generation_root=tmp_path / "generations",
    )
    old_fingerprint = registry.plugin_fingerprint()

    loaded = registry_contributions.register_plugin_backends(
        (new_backend,),
        registry,
        "packet.replace",
        generation_root=tmp_path / "generations",
    )

    assert loaded == ["packet.new_descriptor", "packet.new_function"]
    assert registry.spec_or_none("packet.old_descriptor") is None
    assert registry.spec_or_none("packet.old_function") is None
    assert registry.spec_or_none("packet.new_descriptor") is not None
    assert registry.spec_or_none("packet.new_function") is not None
    assert tuple(bundle.owner_id for bundle in registry.plugin_bundle_refs()) == (
        owner_id,
    )
    assert registry.plugin_fingerprint() != old_fingerprint


def test_plugin_bundle_and_fingerprint_failures_roll_back_the_whole_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    owner_id = "packet.atomic_functions"
    type_id = "packet.atomic_function"
    registry = NodeRegistry()
    backend = _function_backend(owner_id=owner_id, type_id=type_id)
    registry_contributions.register_plugin_backends(
        (backend,), registry, owner_id, generation_root=tmp_path / "generations"
    )
    entry = registry.get_entry(type_id)
    assert isinstance(entry, PythonFunctionEntry)
    bundle = registry.plugin_bundle_refs()[0]
    before = (
        tuple(registry.all_specs()),
        registry.plugin_bundle_refs(),
        registry.plugin_fingerprint(),
        registry.contract_fingerprint(),
    )

    with pytest.raises(ValueError, match="must match Python function entries"):
        registry.register_plugin_bundle(
            None,
            (),
            owner_id=owner_id,
            replace_owner=True,
            python_function_entries=(entry,),
            plugin_bundle=type(bundle)(
                owner_id=bundle.owner_id,
                version=bundle.version,
                generation_id=bundle.generation_id,
                bundle_digest=bundle.bundle_digest,
                approved_generation_root=bundle.approved_generation_root,
                functions=(),
            ),
        )
    assert (
        tuple(registry.all_specs()),
        registry.plugin_bundle_refs(),
        registry.plugin_fingerprint(),
        registry.contract_fingerprint(),
    ) == before

    monkeypatch.setattr(
        "ea_node_editor.nodes.registry.plugin_fingerprint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("fingerprint failed")
        ),
    )
    with pytest.raises(ValueError, match="fingerprint failed"):
        registry.register_plugin_bundle(
            None,
            (),
            owner_id=owner_id,
            replace_owner=True,
            python_function_entries=(entry,),
            plugin_bundle=bundle,
        )
    assert (
        tuple(registry.all_specs()),
        registry.plugin_bundle_refs(),
        registry.plugin_fingerprint(),
        registry.contract_fingerprint(),
    ) == before


def test_register_plugin_backends_redacts_availability_and_failure_details(
    tmp_path: Path,
    caplog,
) -> None:
    private_detail = f"secret-token at {tmp_path / 'private' / 'backend.py'}"

    def fail_descriptors() -> tuple[PluginDescriptor, ...]:
        raise RuntimeError(private_detail)

    unavailable = PluginBackendDescriptor(
        plugin_id="packet.unavailable",
        display_name="Unavailable Backend",
        get_availability=lambda: PluginAvailability.missing_dependency(
            private_detail,
            summary=private_detail,
        ),
        load_descriptors=lambda: (),
    )
    failing = PluginBackendDescriptor(
        plugin_id=str(tmp_path / "private" / "failing_backend.py"),
        display_name="Failing Backend",
        get_availability=lambda: PluginAvailability.available("available"),
        load_descriptors=fail_descriptors,
    )
    caplog.set_level(logging.INFO, logger=registry_contributions.__name__)

    loaded = registry_contributions.register_plugin_backends(
        (unavailable, failing), NodeRegistry(), tmp_path / "private" / "backend.py"
    )

    assert loaded == []
    assert "Plugin backend packet.unavailable skipped [unavailable]" in caplog.text
    assert "Plugin backend plugin:opaque:" in caplog.text
    assert "[backend_load]" in caplog.text
    assert private_detail not in caplog.text
    assert str(tmp_path) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_plugin_failure_logs_omit_hostile_dynamic_exception_class_names(
    tmp_path: Path,
    caplog,
) -> None:
    hostile_name = f"SecretClass\n{tmp_path / 'private' / 'exception.py'}\t"
    hostile_exception = type(hostile_name, (Exception,), {})

    def fail_descriptors() -> tuple[PluginDescriptor, ...]:
        raise hostile_exception("plugin-controlled message")

    backend = PluginBackendDescriptor(
        plugin_id="packet.hostile_exception",
        display_name="Hostile Exception",
        get_availability=lambda: PluginAvailability.available("available"),
        load_descriptors=fail_descriptors,
    )
    caplog.set_level(logging.WARNING, logger=registry_contributions.__name__)
    loaded = registry_contributions.register_plugin_backends(
        (backend,), NodeRegistry(), tmp_path / "private" / "backend.py"
    )

    assert loaded == []
    assert (
        "Plugin backend packet.hostile_exception failed [backend_load]" in caplog.text
    )
    assert "SecretClass" not in caplog.text
    assert str(tmp_path) not in caplog.text
    assert "plugin-controlled message" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_plugin_backend_failure_does_not_leave_partial_type_contribution() -> None:
    families, data_types = _packet_data_type_contract(
        family_id="packet_invalid",
        type_id="Packet.Invalid.Value",
    )
    backend = PluginBackendDescriptor(
        plugin_id="packet.invalid",
        display_name="Invalid Backend",
        get_availability=lambda: PluginAvailability.available("available"),
        load_descriptors=lambda: (
            _typed_packet_descriptor("packet.invalid", "Packet.Unknown"),
        ),
        load_function_sources=lambda: (
            ("functions.py", _function_source("packet.invalid_function")),
        ),
        function_type_ids=("packet.invalid_function",),
        data_type_families=families,
        data_types=data_types,
    )
    registry = NodeRegistry()

    loaded = registry_contributions.register_plugin_backends(
        (backend,), registry, "packet.invalid"
    )

    assert loaded == []
    assert registry.all_specs() == []
    assert registry.plugin_bundle_refs() == ()
    assert registry.data_types.get("Packet.Invalid.Value") is None
    assert registry.plugin_contract_manifest("packet.invalid") is None


def test_plugin_backend_type_conflict_does_not_leave_partial_descriptor() -> None:
    registry = NodeRegistry()
    owner_families, owner_types = _packet_data_type_contract(
        family_id="packet_owner",
        type_id="Packet.Shared.Value",
    )
    registry.register_plugin_bundle(
        PluginContractManifest(
            data_type_families=owner_families,
            data_types=owner_types,
        ),
        (),
        owner_id="packet.owner",
    )
    conflict_families, conflict_types = _packet_data_type_contract(
        family_id="packet_conflict",
        type_id="Packet.Shared.Value",
    )
    backend = PluginBackendDescriptor(
        plugin_id="packet.conflict",
        display_name="Conflicting Backend",
        get_availability=lambda: PluginAvailability.available("available"),
        load_descriptors=lambda: (
            _typed_packet_descriptor("packet.conflict", "Packet.Shared.Value"),
        ),
        data_type_families=conflict_families,
        data_types=conflict_types,
    )
    loaded = registry_contributions.register_plugin_backends(
        (backend,), registry, "packet.conflict"
    )

    assert loaded == []
    assert registry.spec_or_none("packet.conflict") is None
    assert registry.data_types.owner_of("Packet.Shared.Value") == "packet.owner"
    assert not any(
        record.get("family_id") == "packet_conflict"
        for record in registry.data_types.snapshot()
    )


def test_plugin_backend_descriptor_publishes_toolchain_runtime_artifact_and_surface_contracts() -> (
    None
):
    toolchain = ToolchainSpec(
        toolchain_id="packet.python",
        display_name="Packet Python",
        kind="python",
        language="python",
        requirements=(
            ToolchainRequirementSpec(
                requirement_id="packet.optional.lib",
                kind="python_module",
                import_name="packet_optional",
                version_spec=">=1.0",
                optional=True,
            ),
        ),
    )
    artifact = ArtifactDescriptor(
        artifact_id="packet.compiled.extension",
        kind="shared_library",
        path="build/packet_node.pyd",
        runtime_backend_id="packet.external",
        toolchain_id=toolchain.toolchain_id,
        platform_tags=("win_amd64",),
    )
    surface = SurfaceCapabilitySpec(
        capability_id="packet.viewer_surface",
        surface_family="viewer",
        runtime_backend_id="packet.external",
        fullscreen=True,
        input_modes=("pointer", "keyboard"),
    )
    runtime_backend = RuntimeBackendSpec(
        backend_id="packet.external",
        display_name="Packet External Runtime",
        kind="external_process",
        adapter_module="packet_runtime.adapter",
        adapter_factory="create_backend",
        transport="json-rpc",
        transport_revision=1,
        toolchain_ids=(toolchain.toolchain_id,),
        artifact_ids=(artifact.artifact_id,),
        surface_capability_ids=(surface.capability_id,),
    )
    backend = PluginBackendDescriptor(
        plugin_id="packet.contracts",
        display_name="Packet Contracts",
        get_availability=lambda: PluginAvailability.available("ready"),
        load_descriptors=lambda: (
            _packet_descriptor("packet.contracts", "Packet Contracts"),
        ),
        runtime_backends=(runtime_backend,),
        toolchains=(toolchain,),
        artifacts=(artifact,),
        surface_capabilities=(surface,),
    )
    registry = NodeRegistry()

    loaded = registry_contributions.register_plugin_backends(
        (backend,), registry, "packet.contracts"
    )

    assert loaded == ["packet.contracts"]
    assert backend.contract_manifest == PluginContractManifest(
        runtime_backends=(runtime_backend,),
        toolchains=(toolchain,),
        artifacts=(artifact,),
        surface_capabilities=(surface,),
    )
