# Purpose: Declare the COREX-owned MARS add-on, toolchain, runtime, and artifact metadata.
# Map: feature_routes/mars_solver_addon.md
# Tests: tests/test_mars_nodes.py

from __future__ import annotations

from ea_node_editor.nodes.plugin_contracts import (
    AddOnManifest,
    ArtifactDescriptor,
    RuntimeBackendSpec,
    ToolchainRequirementSpec,
    ToolchainSpec,
)

MARS_ADDON_ID = "mars.corex"
MARS_ADDON_VERSION = "1.0.0"
MARS_CATEGORY = "MARS"
MARS_DISTRIBUTION = "mars-modal-response-solver"
MARS_IMPORT_NAME = "mars_solver"
MARS_TOOLCHAIN_ID = "mars.managed_python_runtime"
MARS_RUNTIME_BACKEND_ID = "mars.batch_process"
MARS_RESULTS_ARTIFACT_ID = "mars.results"

MARS_TOOLCHAINS = (
    ToolchainSpec(
        toolchain_id=MARS_TOOLCHAIN_ID,
        display_name="COREX Python Environment",
        kind="python",
        language="python",
        requirements=(
            ToolchainRequirementSpec(
                requirement_id=MARS_DISTRIBUTION,
                kind="python_module",
                display_name="MARS Modal Response Solver",
                import_name=MARS_IMPORT_NAME,
            ),
            ToolchainRequirementSpec(
                requirement_id="MARSBatch",
                kind="executable",
                display_name="MARSBatch console entry point",
                command="MARSBatch",
            ),
        ),
        notes="MARS is installed into the Python environment selected by COREX.",
    ),
)

MARS_ARTIFACTS = (
    ArtifactDescriptor(
        artifact_id=MARS_RESULTS_ARTIFACT_ID,
        kind="data_bundle",
        runtime_backend_id=MARS_RUNTIME_BACKEND_ID,
        toolchain_id=MARS_TOOLCHAIN_ID,
        formats=("csv", "json"),
    ),
)

MARS_RUNTIME_BACKENDS = (
    RuntimeBackendSpec(
        backend_id=MARS_RUNTIME_BACKEND_ID,
        display_name="MARSBatch Process Runtime",
        kind="external_process",
        adapter_module="ea_node_editor.addons.mars.runtime",
        runtime_behaviors=("active",),
        toolchain_ids=(MARS_TOOLCHAIN_ID,),
        artifact_ids=(MARS_RESULTS_ARTIFACT_ID,),
    ),
)

MARS_ADDON_MANIFEST = AddOnManifest(
    addon_id=MARS_ADDON_ID,
    display_name="MARS",
    apply_policy="hot_apply",
    vendor="COREX",
    version=MARS_ADDON_VERSION,
    summary="Run MARS batch envelopes and node time histories from COREX.",
    details=(
        "Provides guided batch and time-history nodes plus a schema-v1 job runner. "
        "MARSBatch executes from COREX's Python environment and all outputs "
        "are captured as project-managed artifacts."
    ),
    dependencies=(MARS_DISTRIBUTION,),
    runtime_backends=MARS_RUNTIME_BACKENDS,
    toolchains=MARS_TOOLCHAINS,
    artifacts=MARS_ARTIFACTS,
)

__all__ = [
    "MARS_ADDON_ID",
    "MARS_ADDON_MANIFEST",
    "MARS_ADDON_VERSION",
    "MARS_ARTIFACTS",
    "MARS_CATEGORY",
    "MARS_DISTRIBUTION",
    "MARS_IMPORT_NAME",
    "MARS_RESULTS_ARTIFACT_ID",
    "MARS_RUNTIME_BACKEND_ID",
    "MARS_RUNTIME_BACKENDS",
    "MARS_TOOLCHAIN_ID",
    "MARS_TOOLCHAINS",
]
