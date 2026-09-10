# Purpose: Define node-plugin, add-on, backend, and atomic contribution manifests.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_loader.py
# Landmarks: PluginContractManifest; AddOnManifest; PluginBackendDescriptor

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Protocol, TypeVar

from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.nodes.node_specs import NodeRenderQualitySpec, NodeTypeSpec
from ea_node_editor.runtime_contracts import (
    DataConversionSpec,
    DataTypeFamilySpec,
    DataTypeSpec,
)

PluginProvenanceKind = Literal["runtime", "file", "package"]
PluginAvailabilityState = Literal["available", "missing_dependency"]
AddOnApplyPolicy = Literal["hot_apply", "restart_required"]
RuntimeBackendKind = Literal["python", "external_process", "rust", "cpp", "foreign"]
ToolchainKind = Literal["python", "external_process", "rust", "cpp", "foreign"]
ToolchainRequirementKind = Literal["python_module", "library", "compiler", "executable"]
ArtifactKind = Literal[
    "python_module",
    "source_tree",
    "executable",
    "shared_library",
    "static_library",
    "wasm_module",
    "data_bundle",
]

_SUPPORTED_RUNTIME_BACKEND_KINDS = {"python", "external_process", "rust", "cpp", "foreign"}
_SUPPORTED_TOOLCHAIN_KINDS = {"python", "external_process", "rust", "cpp", "foreign"}
_SUPPORTED_TOOLCHAIN_REQUIREMENT_KINDS = {"python_module", "library", "compiler", "executable"}
_SUPPORTED_ARTIFACT_KINDS = {
    "python_module",
    "source_tree",
    "executable",
    "shared_library",
    "static_library",
    "wasm_module",
    "data_bundle",
}
_SUPPORTED_RUNTIME_BEHAVIORS = {"active", "passive", "compile_only"}

_T = TypeVar("_T")


def _normalize_trimmed_string(
    field_name: str,
    value: object,
    *,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if normalized != value:
        raise ValueError(f"{field_name} must be a trimmed string")
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    return normalized


def _normalize_token(
    field_name: str,
    value: object,
    *,
    allowed: set[str],
) -> str:
    normalized = _normalize_trimmed_string(field_name, value)
    if normalized not in allowed:
        raise ValueError(f"{field_name} has invalid value: {normalized}")
    return normalized


def _normalize_string_tuple(
    field_name: str,
    value: object,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if value is None:
        raw_values: Sequence[object] = ()
    elif isinstance(value, str):
        raw_values = (value,)
    elif isinstance(value, Sequence):
        raw_values = value
    else:
        raise TypeError(f"{field_name} must be a sequence of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_value in enumerate(raw_values):
        item = _normalize_trimmed_string(f"{field_name}[{index}]", raw_value)
        if item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} must contain at least one value")
    return tuple(normalized)


def _normalize_string_dict(field_name: str, value: Mapping[str, object] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _normalize_trimmed_string(f"{field_name}.key", str(raw_key))
        normalized[key] = str(raw_value)
    return normalized


def _coerce_spec_tuple(
    field_name: str,
    value: object,
    spec_type: type[_T],
) -> tuple[_T, ...]:
    if value is None:
        return ()
    if isinstance(value, spec_type):
        raw_values: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_values = value
    else:
        raise TypeError(f"{field_name} must be a sequence of {spec_type.__name__} values")

    normalized: list[_T] = []
    for index, item in enumerate(raw_values):
        if isinstance(item, spec_type):
            normalized.append(item)
            continue
        from_value = getattr(spec_type, "from_value", None)
        if callable(from_value):
            normalized.append(from_value(item))
            continue
        raise TypeError(f"{field_name}[{index}] must be a {spec_type.__name__}")
    return tuple(normalized)


class NodePlugin(Protocol):
    def spec(self) -> NodeTypeSpec:
        ...

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        ...


@dataclass(slots=True, frozen=True)
class PluginProvenance:
    kind: PluginProvenanceKind
    source_path: Path | None = None
    package_root: Path | None = None
    package_name: str = ""


@dataclass(slots=True, frozen=True)
class ToolchainRequirementSpec:
    requirement_id: str
    kind: ToolchainRequirementKind
    display_name: str = ""
    import_name: str = ""
    command: str = ""
    version_spec: str = ""
    optional: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _normalize_trimmed_string("toolchain_requirement.requirement_id", self.requirement_id),
        )
        object.__setattr__(
            self,
            "kind",
            _normalize_token(
                "toolchain_requirement.kind",
                self.kind,
                allowed=_SUPPORTED_TOOLCHAIN_REQUIREMENT_KINDS,
            ),
        )
        for field_name in ("display_name", "import_name", "command", "version_spec"):
            object.__setattr__(
                self,
                field_name,
                _normalize_trimmed_string(
                    f"toolchain_requirement.{field_name}",
                    getattr(self, field_name),
                    allow_empty=True,
                ),
            )
        object.__setattr__(self, "optional", bool(self.optional))

    @classmethod
    def from_value(cls, value: object) -> "ToolchainRequirementSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("toolchain requirement must be a ToolchainRequirementSpec or mapping")
        return cls(
            requirement_id=value.get("requirement_id"),  # type: ignore[arg-type]
            kind=value.get("kind"),  # type: ignore[arg-type]
            display_name=str(value.get("display_name", "")),
            import_name=str(value.get("import_name", "")),
            command=str(value.get("command", "")),
            version_spec=str(value.get("version_spec", "")),
            optional=bool(value.get("optional", False)),
        )


@dataclass(slots=True, frozen=True)
class ToolchainSpec:
    toolchain_id: str
    display_name: str
    kind: ToolchainKind
    language: str = ""
    requirements: tuple[ToolchainRequirementSpec, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "toolchain_id", _normalize_trimmed_string("toolchain.toolchain_id", self.toolchain_id))
        object.__setattr__(self, "display_name", _normalize_trimmed_string("toolchain.display_name", self.display_name))
        object.__setattr__(
            self,
            "kind",
            _normalize_token("toolchain.kind", self.kind, allowed=_SUPPORTED_TOOLCHAIN_KINDS),
        )
        object.__setattr__(
            self,
            "language",
            _normalize_trimmed_string("toolchain.language", self.language, allow_empty=True),
        )
        object.__setattr__(
            self,
            "requirements",
            _coerce_spec_tuple("toolchain.requirements", self.requirements, ToolchainRequirementSpec),
        )
        object.__setattr__(
            self,
            "notes",
            _normalize_trimmed_string("toolchain.notes", self.notes, allow_empty=True),
        )

    @classmethod
    def from_value(cls, value: object) -> "ToolchainSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("toolchain must be a ToolchainSpec or mapping")
        return cls(
            toolchain_id=value.get("toolchain_id"),  # type: ignore[arg-type]
            display_name=value.get("display_name"),  # type: ignore[arg-type]
            kind=value.get("kind"),  # type: ignore[arg-type]
            language=str(value.get("language", "")),
            requirements=value.get("requirements", ()),  # type: ignore[arg-type]
            notes=str(value.get("notes", "")),
        )


@dataclass(slots=True, frozen=True)
class ArtifactDescriptor:
    artifact_id: str
    kind: ArtifactKind
    path: str = ""
    runtime_backend_id: str = ""
    toolchain_id: str = ""
    formats: tuple[str, ...] = ()
    platform_tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _normalize_trimmed_string("artifact.artifact_id", self.artifact_id))
        object.__setattr__(
            self,
            "kind",
            _normalize_token("artifact.kind", self.kind, allowed=_SUPPORTED_ARTIFACT_KINDS),
        )
        for field_name in ("path", "runtime_backend_id", "toolchain_id"):
            object.__setattr__(
                self,
                field_name,
                _normalize_trimmed_string(
                    f"artifact.{field_name}",
                    getattr(self, field_name),
                    allow_empty=True,
                ),
            )
        object.__setattr__(self, "formats", _normalize_string_tuple("artifact.formats", self.formats))
        object.__setattr__(
            self,
            "platform_tags",
            _normalize_string_tuple("artifact.platform_tags", self.platform_tags),
        )
        object.__setattr__(self, "metadata", _normalize_string_dict("artifact.metadata", self.metadata))

    @classmethod
    def from_value(cls, value: object) -> "ArtifactDescriptor":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("artifact descriptor must be an ArtifactDescriptor or mapping")
        return cls(
            artifact_id=value.get("artifact_id"),  # type: ignore[arg-type]
            kind=value.get("kind"),  # type: ignore[arg-type]
            path=str(value.get("path", "")),
            runtime_backend_id=str(value.get("runtime_backend_id", "")),
            toolchain_id=str(value.get("toolchain_id", "")),
            formats=value.get("formats", ()),  # type: ignore[arg-type]
            platform_tags=value.get("platform_tags", ()),  # type: ignore[arg-type]
            metadata=dict(value.get("metadata", {})),  # type: ignore[arg-type]
        )


@dataclass(slots=True, frozen=True)
class SurfaceCapabilitySpec:
    capability_id: str
    surface_family: str
    surface_variant: str = ""
    runtime_backend_id: str = ""
    qml_component: str = ""
    fullscreen: bool = False
    input_modes: tuple[str, ...] = ()
    render_quality: NodeRenderQualitySpec = field(default_factory=NodeRenderQualitySpec)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _normalize_trimmed_string("surface_capability.capability_id", self.capability_id),
        )
        object.__setattr__(
            self,
            "surface_family",
            _normalize_trimmed_string("surface_capability.surface_family", self.surface_family),
        )
        for field_name in ("surface_variant", "runtime_backend_id", "qml_component"):
            object.__setattr__(
                self,
                field_name,
                _normalize_trimmed_string(
                    f"surface_capability.{field_name}",
                    getattr(self, field_name),
                    allow_empty=True,
                ),
            )
        object.__setattr__(self, "fullscreen", bool(self.fullscreen))
        object.__setattr__(
            self,
            "input_modes",
            _normalize_string_tuple("surface_capability.input_modes", self.input_modes),
        )
        object.__setattr__(
            self,
            "render_quality",
            NodeRenderQualitySpec.from_value(self.render_quality),
        )

    @classmethod
    def from_value(cls, value: object) -> "SurfaceCapabilitySpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("surface capability must be a SurfaceCapabilitySpec or mapping")
        return cls(
            capability_id=value.get("capability_id"),  # type: ignore[arg-type]
            surface_family=value.get("surface_family"),  # type: ignore[arg-type]
            surface_variant=str(value.get("surface_variant", "")),
            runtime_backend_id=str(value.get("runtime_backend_id", "")),
            qml_component=str(value.get("qml_component", "")),
            fullscreen=bool(value.get("fullscreen", False)),
            input_modes=value.get("input_modes", ()),  # type: ignore[arg-type]
            render_quality=value.get("render_quality"),  # type: ignore[arg-type]
        )


@dataclass(slots=True, frozen=True)
class RuntimeBackendSpec:
    backend_id: str
    display_name: str
    kind: RuntimeBackendKind
    adapter_module: str = ""
    adapter_factory: str = ""
    transport: str = ""
    transport_revision: int = 0
    runtime_behaviors: tuple[str, ...] = ("active",)
    toolchain_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    surface_capability_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_id", _normalize_trimmed_string("runtime_backend.backend_id", self.backend_id))
        object.__setattr__(
            self,
            "display_name",
            _normalize_trimmed_string("runtime_backend.display_name", self.display_name),
        )
        object.__setattr__(
            self,
            "kind",
            _normalize_token("runtime_backend.kind", self.kind, allowed=_SUPPORTED_RUNTIME_BACKEND_KINDS),
        )
        for field_name in ("adapter_module", "adapter_factory", "transport"):
            object.__setattr__(
                self,
                field_name,
                _normalize_trimmed_string(
                    f"runtime_backend.{field_name}",
                    getattr(self, field_name),
                    allow_empty=True,
                ),
            )
        object.__setattr__(self, "transport_revision", int(self.transport_revision))
        runtime_behaviors = _normalize_string_tuple(
            "runtime_backend.runtime_behaviors",
            self.runtime_behaviors,
            allow_empty=False,
        )
        invalid_behaviors = set(runtime_behaviors) - _SUPPORTED_RUNTIME_BEHAVIORS
        if invalid_behaviors:
            invalid = ", ".join(sorted(invalid_behaviors))
            raise ValueError(f"runtime_backend.runtime_behaviors has invalid value(s): {invalid}")
        object.__setattr__(self, "runtime_behaviors", runtime_behaviors)
        object.__setattr__(
            self,
            "toolchain_ids",
            _normalize_string_tuple("runtime_backend.toolchain_ids", self.toolchain_ids),
        )
        object.__setattr__(
            self,
            "artifact_ids",
            _normalize_string_tuple("runtime_backend.artifact_ids", self.artifact_ids),
        )
        object.__setattr__(
            self,
            "surface_capability_ids",
            _normalize_string_tuple("runtime_backend.surface_capability_ids", self.surface_capability_ids),
        )

    @classmethod
    def from_value(cls, value: object) -> "RuntimeBackendSpec":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("runtime backend must be a RuntimeBackendSpec or mapping")
        return cls(
            backend_id=value.get("backend_id"),  # type: ignore[arg-type]
            display_name=value.get("display_name"),  # type: ignore[arg-type]
            kind=value.get("kind"),  # type: ignore[arg-type]
            adapter_module=str(value.get("adapter_module", "")),
            adapter_factory=str(value.get("adapter_factory", "")),
            transport=str(value.get("transport", "")),
            transport_revision=int(value.get("transport_revision", 0)),
            runtime_behaviors=value.get("runtime_behaviors", ("active",)),  # type: ignore[arg-type]
            toolchain_ids=value.get("toolchain_ids", ()),  # type: ignore[arg-type]
            artifact_ids=value.get("artifact_ids", ()),  # type: ignore[arg-type]
            surface_capability_ids=value.get("surface_capability_ids", ()),  # type: ignore[arg-type]
        )


@dataclass(slots=True, frozen=True)
class PluginContractManifest:
    runtime_backends: tuple[RuntimeBackendSpec, ...] = ()
    toolchains: tuple[ToolchainSpec, ...] = ()
    artifacts: tuple[ArtifactDescriptor, ...] = ()
    surface_capabilities: tuple[SurfaceCapabilitySpec, ...] = ()
    data_type_families: tuple[DataTypeFamilySpec, ...] = ()
    data_types: tuple[DataTypeSpec, ...] = ()
    data_conversions: tuple[DataConversionSpec, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_backends",
            _coerce_spec_tuple("contract_manifest.runtime_backends", self.runtime_backends, RuntimeBackendSpec),
        )
        object.__setattr__(
            self,
            "toolchains",
            _coerce_spec_tuple("contract_manifest.toolchains", self.toolchains, ToolchainSpec),
        )
        object.__setattr__(
            self,
            "artifacts",
            _coerce_spec_tuple("contract_manifest.artifacts", self.artifacts, ArtifactDescriptor),
        )
        object.__setattr__(
            self,
            "surface_capabilities",
            _coerce_spec_tuple(
                "contract_manifest.surface_capabilities",
                self.surface_capabilities,
                SurfaceCapabilitySpec,
            ),
        )
        object.__setattr__(
            self,
            "data_type_families",
            _coerce_spec_tuple(
                "contract_manifest.data_type_families",
                self.data_type_families,
                DataTypeFamilySpec,
            ),
        )
        object.__setattr__(
            self,
            "data_types",
            _coerce_spec_tuple(
                "contract_manifest.data_types",
                self.data_types,
                DataTypeSpec,
            ),
        )
        object.__setattr__(
            self,
            "data_conversions",
            _coerce_spec_tuple(
                "contract_manifest.data_conversions",
                self.data_conversions,
                DataConversionSpec,
            ),
        )

    @classmethod
    def from_value(cls, value: object) -> "PluginContractManifest":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("plugin contract manifest must be a PluginContractManifest, mapping, or None")
        return cls(
            runtime_backends=value.get("runtime_backends", ()),  # type: ignore[arg-type]
            toolchains=value.get("toolchains", ()),  # type: ignore[arg-type]
            artifacts=value.get("artifacts", ()),  # type: ignore[arg-type]
            surface_capabilities=value.get("surface_capabilities", ()),  # type: ignore[arg-type]
            data_type_families=value.get("data_type_families", ()),  # type: ignore[arg-type]
            data_types=value.get("data_types", ()),  # type: ignore[arg-type]
            data_conversions=value.get("data_conversions", ()),  # type: ignore[arg-type]
        )


@dataclass(slots=True, frozen=True)
class PluginDescriptor:
    spec: NodeTypeSpec
    factory: Callable[[], NodePlugin]
    provenance: PluginProvenance | None = None


@dataclass(slots=True, frozen=True)
class AddOnManifest:
    addon_id: str
    display_name: str
    apply_policy: AddOnApplyPolicy
    vendor: str = ""
    version: str = ""
    summary: str = ""
    details: str = ""
    dependencies: tuple[str, ...] = ()
    runtime_backends: tuple[RuntimeBackendSpec, ...] = ()
    toolchains: tuple[ToolchainSpec, ...] = ()
    artifacts: tuple[ArtifactDescriptor, ...] = ()
    surface_capabilities: tuple[SurfaceCapabilitySpec, ...] = ()
    data_type_families: tuple[DataTypeFamilySpec, ...] = ()
    data_types: tuple[DataTypeSpec, ...] = ()
    data_conversions: tuple[DataConversionSpec, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "addon_id", _normalize_trimmed_string("add_on.addon_id", self.addon_id))
        object.__setattr__(self, "display_name", _normalize_trimmed_string("add_on.display_name", self.display_name))
        object.__setattr__(
            self,
            "apply_policy",
            _normalize_token("add_on.apply_policy", self.apply_policy, allowed={"hot_apply", "restart_required"}),
        )
        for field_name in ("vendor", "version", "summary", "details"):
            object.__setattr__(
                self,
                field_name,
                _normalize_trimmed_string(
                    f"add_on.{field_name}",
                    getattr(self, field_name),
                    allow_empty=True,
                ),
            )
        object.__setattr__(self, "dependencies", _normalize_string_tuple("add_on.dependencies", self.dependencies))
        object.__setattr__(
            self,
            "runtime_backends",
            _coerce_spec_tuple("add_on.runtime_backends", self.runtime_backends, RuntimeBackendSpec),
        )
        object.__setattr__(
            self,
            "toolchains",
            _coerce_spec_tuple("add_on.toolchains", self.toolchains, ToolchainSpec),
        )
        object.__setattr__(
            self,
            "artifacts",
            _coerce_spec_tuple("add_on.artifacts", self.artifacts, ArtifactDescriptor),
        )
        object.__setattr__(
            self,
            "surface_capabilities",
            _coerce_spec_tuple("add_on.surface_capabilities", self.surface_capabilities, SurfaceCapabilitySpec),
        )
        object.__setattr__(
            self,
            "data_type_families",
            _coerce_spec_tuple(
                "add_on.data_type_families",
                self.data_type_families,
                DataTypeFamilySpec,
            ),
        )
        object.__setattr__(
            self,
            "data_types",
            _coerce_spec_tuple("add_on.data_types", self.data_types, DataTypeSpec),
        )
        object.__setattr__(
            self,
            "data_conversions",
            _coerce_spec_tuple(
                "add_on.data_conversions",
                self.data_conversions,
                DataConversionSpec,
            ),
        )

    @property
    def contract_manifest(self) -> PluginContractManifest:
        return PluginContractManifest(
            runtime_backends=self.runtime_backends,
            toolchains=self.toolchains,
            artifacts=self.artifacts,
            surface_capabilities=self.surface_capabilities,
            data_type_families=self.data_type_families,
            data_types=self.data_types,
            data_conversions=self.data_conversions,
        )


@dataclass(slots=True, frozen=True)
class PluginAvailability:
    state: PluginAvailabilityState
    summary: str = ""
    missing_dependencies: tuple[str, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.state == "available"

    @classmethod
    def available(cls, summary: str = "") -> "PluginAvailability":
        return cls(state="available", summary=summary)

    @classmethod
    def missing_dependency(
        cls,
        *dependencies: str,
        summary: str = "",
    ) -> "PluginAvailability":
        return cls(
            state="missing_dependency",
            summary=summary,
            missing_dependencies=tuple(str(dependency) for dependency in dependencies if str(dependency).strip()),
        )


@dataclass(slots=True, frozen=True)
class PluginBackendDescriptor:
    plugin_id: str
    display_name: str
    get_availability: Callable[[], PluginAvailability]
    load_descriptors: Callable[[], tuple[PluginDescriptor, ...]]
    provenance: PluginProvenance | None = None
    addon_manifest: AddOnManifest | None = None
    runtime_backends: tuple[RuntimeBackendSpec, ...] = ()
    toolchains: tuple[ToolchainSpec, ...] = ()
    artifacts: tuple[ArtifactDescriptor, ...] = ()
    surface_capabilities: tuple[SurfaceCapabilitySpec, ...] = ()
    data_type_families: tuple[DataTypeFamilySpec, ...] = ()
    data_types: tuple[DataTypeSpec, ...] = ()
    data_conversions: tuple[DataConversionSpec, ...] = ()
    load_function_sources: Callable[[], tuple[tuple[str, str], ...]] | None = None
    function_type_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "plugin_id", _normalize_trimmed_string("plugin_backend.plugin_id", self.plugin_id))
        object.__setattr__(
            self,
            "display_name",
            _normalize_trimmed_string("plugin_backend.display_name", self.display_name),
        )
        if not callable(self.get_availability):
            raise TypeError("plugin_backend.get_availability must be callable")
        if not callable(self.load_descriptors):
            raise TypeError("plugin_backend.load_descriptors must be callable")
        if self.load_function_sources is not None and not callable(
            self.load_function_sources
        ):
            raise TypeError("plugin_backend.load_function_sources must be callable")
        if not isinstance(self.function_type_ids, tuple):
            raise TypeError("plugin_backend.function_type_ids must be a tuple")
        function_type_ids = tuple(
            _normalize_trimmed_string(
                f"plugin_backend.function_type_ids[{index}]",
                type_id,
            )
            for index, type_id in enumerate(self.function_type_ids)
        )
        if len(function_type_ids) != len(set(function_type_ids)):
            raise ValueError("plugin_backend.function_type_ids must be unique")
        if bool(function_type_ids) != (self.load_function_sources is not None):
            raise ValueError(
                "plugin_backend function sources and type ids must be declared together"
            )
        object.__setattr__(self, "function_type_ids", function_type_ids)
        if self.addon_manifest is not None and not isinstance(self.addon_manifest, AddOnManifest):
            raise TypeError("plugin_backend.addon_manifest must be an AddOnManifest")
        object.__setattr__(
            self,
            "runtime_backends",
            _coerce_spec_tuple("plugin_backend.runtime_backends", self.runtime_backends, RuntimeBackendSpec),
        )
        object.__setattr__(
            self,
            "toolchains",
            _coerce_spec_tuple("plugin_backend.toolchains", self.toolchains, ToolchainSpec),
        )
        object.__setattr__(
            self,
            "artifacts",
            _coerce_spec_tuple("plugin_backend.artifacts", self.artifacts, ArtifactDescriptor),
        )
        object.__setattr__(
            self,
            "surface_capabilities",
            _coerce_spec_tuple(
                "plugin_backend.surface_capabilities",
                self.surface_capabilities,
                SurfaceCapabilitySpec,
            ),
        )
        object.__setattr__(
            self,
            "data_type_families",
            _coerce_spec_tuple(
                "plugin_backend.data_type_families",
                self.data_type_families,
                DataTypeFamilySpec,
            ),
        )
        object.__setattr__(
            self,
            "data_types",
            _coerce_spec_tuple(
                "plugin_backend.data_types",
                self.data_types,
                DataTypeSpec,
            ),
        )
        object.__setattr__(
            self,
            "data_conversions",
            _coerce_spec_tuple(
                "plugin_backend.data_conversions",
                self.data_conversions,
                DataConversionSpec,
            ),
        )

    @property
    def contract_manifest(self) -> PluginContractManifest:
        return PluginContractManifest(
            runtime_backends=self.runtime_backends,
            toolchains=self.toolchains,
            artifacts=self.artifacts,
            surface_capabilities=self.surface_capabilities,
            data_type_families=self.data_type_families,
            data_types=self.data_types,
            data_conversions=self.data_conversions,
        )
