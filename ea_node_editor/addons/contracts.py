# Purpose: Define discovered add-on state and presentation records.
# Map: subsystems/addons.md
# Tests: tests/test_addon_catalog.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ea_node_editor.nodes.plugin_contracts import (
    AddOnApplyPolicy,
    AddOnManifest,
    ArtifactDescriptor,
    PluginAvailability,
    RuntimeBackendSpec,
    SurfaceCapabilitySpec,
    ToolchainSpec,
)
from ea_node_editor.runtime_contracts import (
    DataConversionSpec,
    DataTypeFamilySpec,
    DataTypeSpec,
)

AddOnRecordState = Literal[
    "installed",
    "disabled",
    "unavailable",
    "pending_restart",
]


@dataclass(slots=True, frozen=True)
class AddOnState:
    enabled: bool = True
    pending_restart: bool = False


@dataclass(slots=True, frozen=True)
class AddOnRecord:
    manifest: AddOnManifest
    state: AddOnState = field(default_factory=AddOnState)
    availability: PluginAvailability = field(
        default_factory=PluginAvailability.available,
    )
    provided_node_type_ids: tuple[str, ...] = ()

    @property
    def addon_id(self) -> str:
        return self.manifest.addon_id

    @property
    def display_name(self) -> str:
        return self.manifest.display_name

    @property
    def apply_policy(self) -> AddOnApplyPolicy:
        return self.manifest.apply_policy

    @property
    def vendor(self) -> str:
        return self.manifest.vendor

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def summary(self) -> str:
        return self.manifest.summary

    @property
    def details(self) -> str:
        return self.manifest.details

    @property
    def runtime_backends(self) -> tuple[RuntimeBackendSpec, ...]:
        return self.manifest.runtime_backends

    @property
    def toolchains(self) -> tuple[ToolchainSpec, ...]:
        return self.manifest.toolchains

    @property
    def artifacts(self) -> tuple[ArtifactDescriptor, ...]:
        return self.manifest.artifacts

    @property
    def surface_capabilities(self) -> tuple[SurfaceCapabilitySpec, ...]:
        return self.manifest.surface_capabilities

    @property
    def data_type_families(self) -> tuple[DataTypeFamilySpec, ...]:
        return self.manifest.data_type_families

    @property
    def data_types(self) -> tuple[DataTypeSpec, ...]:
        return self.manifest.data_types

    @property
    def data_conversions(self) -> tuple[DataConversionSpec, ...]:
        return self.manifest.data_conversions

    @property
    def status(self) -> AddOnRecordState:
        if not self.availability.is_available:
            return "unavailable"
        if self.state.pending_restart:
            return "pending_restart"
        if not self.state.enabled:
            return "disabled"
        return "installed"


__all__ = ["AddOnRecord", "AddOnRecordState", "AddOnState"]
