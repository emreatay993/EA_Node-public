from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import verification_manifest as manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_traceability.py"
VERIFICATION_MANIFEST_PATH = REPO_ROOT / "scripts" / "verification_manifest.py"
PROJECT_MANAGED_FILES_QA_MATRIX = REPO_ROOT / "docs/specs/perf/PROJECT_MANAGED_FILES_QA_MATRIX.md"
PROJECT_MANAGED_FILES_FINAL_REGRESSION_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest "
    "tests/test_project_artifact_store.py tests/test_project_artifact_resolution.py "
    "tests/test_pdf_preview_provider.py tests/test_project_save_as_flow.py "
    "tests/test_app_preferences_import_defaults.py tests/test_project_file_issues.py "
    "tests/test_project_files_dialog.py tests/test_execution_artifact_refs.py "
    "tests/test_integrations_track_f.py tests/test_process_run_node.py "
    "tests/test_graph_output_mode_ui.py tests/test_shell_project_session_controller.py "
    "--ignore=venv -q"
)
PROJECT_MANAGED_FILES_TRACEABILITY_COMMAND = "./venv/Scripts/python.exe scripts/check_traceability.py"

PROJECT_MANAGED_FILES_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/10_ARCHITECTURE.md": {
        "REQ-ARCH-014": (".cxproj", "<project-stem>.data/workspaces", "in/", "out/", "tmp/"),
        "REQ-ARCH-015": ("metadata.artifact_store", "saved://<artifact_id>", "temp://<artifact_id>"),
    },
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-028": ("Project Files...", "temporary", "broken"),
        "REQ-UI-029": (
            "Save As",
            "self-contained",
            "refuse to replace",
            "reopened, verified, and adopted",
        ),
        "REQ-UI-030": ("managed_copy", "external_link", "File Read", "Excel Read"),
        "REQ-UI-031": ("Process Run", "memory", "stored", "status chip"),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-022": ("RuntimeArtifactRef", "ExecutionContext.resolve_path_value()", "runtime_artifact_ref()"),
    },
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
        "REQ-NODE-023": ("RuntimeArtifactRef", "same run", "runtime-snapshot"),
        "REQ-NODE-024": ("io.process_run", "memory", "stored", "automatic size-based switching"),
    },
    "docs/specs/requirements/50_EXECUTION_ENGINE.md": {
        "REQ-EXEC-010": ("RuntimeArtifactRef", "artifact_ref", "saved://...", "temp://..."),
        "REQ-EXEC-011": ("runtime-snapshot", "project artifact metadata", "same run"),
        "REQ-EXEC-012": ("Process Run", "temporary refs", "non-zero failure or cancellation"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-015": (".cxproj", "<project-stem>.data/workspaces", "in/", "out/", "tmp/"),
        "REQ-PERSIST-016": ("metadata.artifact_store", "saved://<artifact_id>", "temp://<artifact_id>"),
        "REQ-PERSIST-017": (
            "tmp/",
            "copy-on-write",
            "atomically replace only the currently bound `.cxproj`",
            "bounded orphan cleanup",
        ),
        "REQ-PERSIST-018": (
            "Save As",
            "create-new/no-clobber",
            "referenced saved and temporary artifacts",
            "committed reopen",
        ),
        "REQ-PERSIST-019": ("crash-only", "clean close", "temporary tmp data"),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-021": ("PROJECT_MANAGED_FILES", "runtime artifact refs", "Process Run", "full artifact manager"),
        "REQ-QA-022": ("PROJECT_MANAGED_FILES_QA_MATRIX.md", "final aggregate regression command", "traceability gate"),
        "AC-REQ-QA-021-01": (PROJECT_MANAGED_FILES_FINAL_REGRESSION_COMMAND,),
        "AC-REQ-QA-022-01": (PROJECT_MANAGED_FILES_TRACEABILITY_COMMAND, "PROJECT_MANAGED_FILES_QA_MATRIX.md"),
    },
}

PROJECT_MANAGED_FILES_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-ARCH-014": ("artifact_store.py", "test_project_artifact_store.py", "round_trip_cases.py"),
    "REQ-UI-028": ("project_files_dialog.py", "test_project_files_dialog.py", "test_shell_project_session_controller.py"),
    "REQ-NODE-022": ("Runtime artifact-ref SDK helpers", "test_execution_artifact_refs.py"),
    "REQ-NODE-023": ("Stored-output runtime artifact refs", "test_integrations_track_f.py"),
    "REQ-EXEC-010": ("protocol_codec.py", "test_execution_artifact_refs.py", "test_process_client.py"),
    "REQ-PERSIST-015": ("Canonical `.cxproj` plus sibling `.data` layout", "test_project_artifact_store.py"),
    "REQ-QA-021": ("PROJECT_MANAGED_FILES_QA_MATRIX.md", "test_graph_output_mode_ui.py", "test_shell_project_session_controller.py"),
    "AC-REQ-QA-021-01": (PROJECT_MANAGED_FILES_FINAL_REGRESSION_COMMAND, "PROJECT_MANAGED_FILES_QA_MATRIX.md"),
    "AC-REQ-QA-022-01": (PROJECT_MANAGED_FILES_TRACEABILITY_COMMAND, "tests/test_traceability_checker.py"),
}

PROJECT_MANAGED_FILES_QA_MATRIX_TOKENS = (
    "Project Managed Files QA Matrix",
    "## Locked Scope",
    "saved://<artifact_id>",
    "temp://<artifact_id>",
    PROJECT_MANAGED_FILES_FINAL_REGRESSION_COMMAND,
    PROJECT_MANAGED_FILES_TRACEABILITY_COMMAND,
    "## Future-Scope Deferrals",
    "no full artifact-manager pane",
    "Process Run",
)

CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_QA_MATRIX.md"
)
CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/10_ARCHITECTURE.md": {
        "REQ-ARCH-016": ("registry-driven", "ViewerHostService", "native scene objects"),
        "AC-REQ-ARCH-016-01": ("worker-side scene authority", "engineering-backend"),
    },
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-032": ("model.viewer", "viewerSessionBridge", "rerun_required"),
    },
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
        "REQ-NODE-026": ("model.viewer", "ViewerSessionService", "rerun-required"),
    },
    "docs/specs/requirements/50_EXECUTION_ENGINE.md": {
        "REQ-EXEC-013": ("engineering backend", "queue-safe viewer protocol payloads"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-020": (".cxproj", "session-scoped transport bundles"),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-023": ("engineering scene transport", "model.viewer"),
    },
}
CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-ARCH-016": ("viewer_backend_engineering.py", "engineering_viewer_widget_binder.py"),
    "REQ-UI-032": ("engineering_viewer_widget_binder.py", "GraphViewerSurface.qml"),
    "REQ-NODE-026": ("viewer_session_service.py", "GraphViewerSurface.qml"),
    "REQ-EXEC-013": ("viewer_backend_engineering.py", "test_execution_viewer_protocol.py"),
    "REQ-PERSIST-020": ("project_session_services.py", "viewer_backend_engineering.py"),
    "REQ-QA-023": ("test_engineering_viewer_backend.py", "test_engineering_viewer_widget_binder.py"),
}
CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_QA_MATRIX_TOKENS = (
    "Cross-Process Viewer Backend Framework QA Matrix",
    "## Locked Scope",
    "model.viewer",
    "ViewerHostService",
    "ViewerWidgetBinderRegistry",
    "engineering viewer binder",
    "rerun required",
    "transport revision",
)

ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md"
)
ADDON_MANAGER_BACKEND_PREPARATION_INDEX_TOKENS = (
    "[ADDON_MANAGER_BACKEND_PREPARATION QA Matrix](perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md)",
)
ADDON_MANAGER_BACKEND_PREPARATION_PUBLIC_DOC_TOKENS: dict[str, tuple[str, ...]] = {
    "README.md": ("Add-On Manager", "Variant 4 inspector-style drawer"),
    "ARCHITECTURE.md": ("## Add-on backend preparation", "Variant 4 inspector-style right drawer"),
}
ADDON_MANAGER_BACKEND_PREPARATION_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-041": ("Add-On Manager", "Variant 4 inspector-style right drawer"),
        "REQ-UI-042": ("locked Mockup B placeholders", "Load missing add-ons"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-023": ("app preferences", "locked unavailable-add-on projections"),
    },
    "docs/specs/requirements/70_INTEGRATIONS.md": {
        "REQ-INT-011": ("stable id, name, version", "hot_apply", "restart_required"),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-040": ("Tabular", "MARS", "Variant 4 manager surface"),
        "REQ-QA-041": ("Tabular", "MARS", "menu open/toggle/projection flows"),
    },
}
ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-041": ("addon_manager_presenter.py", "AddOnManagerPane.qml"),
    "REQ-UI-042": ("registry_normalization.py", "GraphNodeHost.qml"),
    "REQ-PERSIST-023": ("app_preferences.py", "project_codec.py"),
    "REQ-INT-011": ("tabular_data/{function_nodes.py,catalog.py}", "mars/{function_nodes.py,catalog.py}"),
    "REQ-QA-040": ("ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",),
}
ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_TOKENS = (
    "Add-On Manager Backend Preparation QA Matrix",
    "## Locked Scope",
    "## Current Automated Verification",
    "Variant 4 inspector-style right drawer",
    "Mockup B placeholders",
    "Tabular Data",
    "MARS",
)


COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX = (
    REPO_ROOT / manifest.COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND = (
    manifest.COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND = (
    manifest.COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND = (
    manifest.COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_INDEX_TOKENS = (
    "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP QA Matrix",
    "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PUBLIC_DOC_TOKENS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
        "ea_node_editor.bootstrap",
        "Validation and reload parse source without executing it.",
        "locked projections",
        "Public plugins do not import COREX internals.",
    ),
    "ARCHITECTURE.md": (
        "## Current focused contracts",
        "focused bridges",
        "current-schema",
        "17-name top-level `corex` SDK",
        "immutable content-addressed generation",
        "snapshot-only",
        "typed transport/session",
        "ea_node_editor.ui.perf.performance_harness",
        "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
    ),
}
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/10_ARCHITECTURE.md": {
        "REQ-ARCH-008": ("current-schema-normalization", "schema validation", "normalization"),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-003": ("category_path", "derived display labels", "not a compatibility alias"),
        "REQ-NODE-007": ("category_path=", "derived display labels", "presentation only"),
        "AC-REQ-NODE-003-01": ("derived category display", "descendant nodes"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-004": (
            "`.cxproj` v5",
            "supported migration inputs",
            "`.cxproj` v4",
            "without compatibility shims",
        ),
        "REQ-PERSIST-005": (
            "delete known control edges",
            "nested fragments and workflows",
            "default surviving edges",
            "`input_order`",
            "Item access",
            "no modifiers or Principal",
        ),
        "REQ-PERSIST-023": ("locked unavailable-add-on projections", "projection payloads"),
        "AC-REQ-PERSIST-023-01": ("current-schema", "unavailable-add-on locked projection"),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-042": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["REQ-QA-042"],
        "AC-REQ-QA-042-01": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["AC-REQ-QA-042-01"],
    },
}
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-NODE-002": (
        "Exactly 68 function-backed built-ins",
        "nodes/builtin_functions/",
        "nodes/function_plugin.py",
        "retained trusted descriptors/helpers",
        "test_remaining_builtin_function_migration.py",
    ),
    "REQ-NODE-035": (
        "builtin_functions/{engineering_imports.py,engineering_viewer.py}",
        "builtins/{engineering_imports.py,engineering_viewer.py}",
        "test_remaining_builtin_function_migration.py",
    ),
    "REQ-INT-002": (
        "builtin_functions/integrations_*.py",
        "ssh_sftp_values.py",
        "test_builtin_integration_function_migration.py",
    ),
    "REQ-INT-006": (
        "External process runner function",
        "integrations_process.py::process_run",
        "process_subprocess_policy.py",
    ),
    "REQ-INT-007": (
        "nodes/builtin_functions/__init__.py",
        "io.path_pointer",
        "io.folder_explorer",
    ),
    "REQ-QA-042": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["REQ-QA-042"],
    "AC-REQ-QA-042-01": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["AC-REQ-QA-042-01"],
    "AC-REQ-QA-018-01": ("ea_node_editor.ui.perf.performance_harness",),
    "REQ-PERF-001": ("ea_node_editor/ui/perf/performance_harness.py",),
    "REQ-PERF-002": ("ea_node_editor/ui/perf/performance_harness.py",),
    "REQ-PERF-003": ("ea_node_editor/ui/perf/performance_harness.py",),
}
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_ROW_FORBIDDEN_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-INT-006": ("compatibility export",),
}
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_TOKENS = (
    "COREX No-Legacy Architecture Cleanup QA Matrix",
    "## Locked Scope",
    "## Packet Outcomes",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-04-24 Execution Results",
    "## Manual Smoke Guidance",
    "## Residual Risks",
    "focused bridges",
    "explicit source contracts",
    "current-schema persistence",
    "descriptor-only plugins/add-ons",
    "snapshot-only runtime payloads",
    "typed viewer transport",
    "canonical launch/import paths",
    "P01_no_legacy_guardrails_WRAPUP.md",
    "P13_launch_package_import_shim_cleanup_WRAPUP.md",
    "P14_docs_traceability_closeout_WRAPUP.md",
    "c413beae3eab13eb40aaceb86bd143587900d6de",
    "dfd3ab4b746a13628f4eb2d803bd653809092d89",
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND,
)

COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md"
)
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_run_script.py --ignore=venv"
)
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_markdown_links.py"
)
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_INDEX_TOKENS = (
    "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE QA Matrix",
    "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md",
)
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_PUBLIC_DOC_TOKENS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "COREX Clean Architecture Restructure QA Matrix",
        "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md",
        "ea_node_editor.bootstrap",
    ),
    "ARCHITECTURE.md": (
        "## Current focused contracts",
        "clean-architecture restructure",
        "runtime_contracts",
        "graph-owned domain APIs",
        "COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md",
    ),
    "docs/GETTING_STARTED.md": (
        r".\venv\Scripts\python.exe -m ea_node_editor.bootstrap",
        "corex-node-editor",
        "ea_node_editor.bootstrap:main",
        "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md",
    ),
    "docs/PACKAGING_WINDOWS.md": (
        "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.md",
        "ARCHITECTURE_REFACTOR_QA_MATRIX.md",
    ),
}
COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX_TOKENS = (
    "COREX Clean Architecture Restructure QA Matrix",
    "## Locked Scope",
    "## Final Ownership Boundaries",
    "## Packet Outcomes",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-04-25 Execution Results",
    "## Produced Artifacts",
    "## Manual Smoke Guidance",
    "## Residual Risks",
    "COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_STATUS.md",
    "P01_runtime_contracts_WRAPUP.md",
    "P11_cross_cutting_services_WRAPUP.md",
    "P12_docs_traceability_closeout_WRAPUP.md",
    "2283635deb1d65f1973720c3f500a5c1620d6ac9",
    "b1fc5fb3b359be5bf940ff0d23dddab10b4194f0",
    "codex/corex-clean-architecture-restructure/p12-docs-traceability-closeout",
    "runtime_contracts",
    "graph-owned domain APIs",
    "ea_node_editor.ui.shell.composition",
    "descriptor-first plugin discovery",
    COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_PYTEST_COMMAND,
    COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_TRACEABILITY_COMMAND,
    COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_MARKDOWN_COMMAND,
)

COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md"
)
COREX_ARCHITECTURE_MODERNIZATION_WRAPUP_DOC = (
    "docs/specs/work_packets/corex_architecture_modernization/"
    "P12_closeout_traceability_WRAPUP.md"
)
COREX_ARCHITECTURE_MODERNIZATION_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_run_script.py --ignore=venv -q"
)
COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)
COREX_ARCHITECTURE_MODERNIZATION_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_markdown_links.py"
)
COREX_ARCHITECTURE_MODERNIZATION_FULL_DRY_RUN_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --dry-run"
)
COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\run_verification.py --mode full"
)
COREX_ARCHITECTURE_MODERNIZATION_REVIEW_GATE_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
COREX_ARCHITECTURE_MODERNIZATION_INDEX_TOKENS = (
    "COREX_ARCHITECTURE_MODERNIZATION QA Matrix",
    "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
)
COREX_ARCHITECTURE_MODERNIZATION_PUBLIC_DOC_TOKENS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "COREX Architecture Modernization QA Matrix",
        "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
        "headless Corex kernel",
        "execution backend policy",
    ),
    "ARCHITECTURE.md": (
        "## Current focused contracts",
        "dependency-free public function/decorator SDK",
        "corex-runtime",
        "RuntimeBackendSpec",
        "immutable content-addressed generation",
        "COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md",
        "process worker",
    ),
}
COREX_ARCHITECTURE_MODERNIZATION_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-046": (
            "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
            "headless Corex kernel",
            "QML shell client",
            "strict current `.cxproj`",
            "execution backend policy",
        ),
        "AC-REQ-QA-046-01": (
            COREX_ARCHITECTURE_MODERNIZATION_PYTEST_COMMAND,
            COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_COMMAND,
            COREX_ARCHITECTURE_MODERNIZATION_MARKDOWN_COMMAND,
            COREX_ARCHITECTURE_MODERNIZATION_FULL_DRY_RUN_COMMAND,
            COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND,
            COREX_ARCHITECTURE_MODERNIZATION_REVIEW_GATE_COMMAND,
            "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
        ),
    },
}
COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-QA-046": (
        "ARCHITECTURE.md",
        "README.md",
        "docs/specs/INDEX.md",
        "docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
        COREX_ARCHITECTURE_MODERNIZATION_WRAPUP_DOC,
        "scripts/check_traceability.py",
        "tests/test_traceability_checker.py",
        "tests/test_markdown_hygiene.py",
        "tests/test_run_script.py",
    ),
    "AC-REQ-QA-046-01": (
        COREX_ARCHITECTURE_MODERNIZATION_PYTEST_COMMAND,
        COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_COMMAND,
        COREX_ARCHITECTURE_MODERNIZATION_MARKDOWN_COMMAND,
        COREX_ARCHITECTURE_MODERNIZATION_FULL_DRY_RUN_COMMAND,
        COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND,
        COREX_ARCHITECTURE_MODERNIZATION_REVIEW_GATE_COMMAND,
        "docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
    ),
}
COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_TOKENS = (
    "COREX Architecture Modernization QA Matrix",
    "## Locked Scope",
    "## Final Architecture Baseline",
    "## Packet Outcomes",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-05-01 Execution Results",
    "## Produced Artifacts",
    "## Manual Smoke Guidance",
    "## Residual Risks",
    "headless Corex kernel",
    "strict current `.cxproj`",
    "RuntimeBackendSpec",
    "ToolchainSpec",
    "ArtifactDescriptor",
    "SurfaceCapabilitySpec",
    "execution backend policy",
    "P01_requirements_adrs_WRAPUP.md",
    "P11_execution_backends_WRAPUP.md",
    "P12_closeout_traceability_WRAPUP.md",
    "a1e9e580e4ae295988145ee590fbf178da56083f",
    "eb0d114d2e9d0179d1e9dc63ec8b2069aebe6171",
    "codex/corex-architecture-modernization/p12-closeout-traceability",
    COREX_ARCHITECTURE_MODERNIZATION_PYTEST_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_MARKDOWN_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_FULL_DRY_RUN_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_REVIEW_GATE_COMMAND,
)

GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md"
)
GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P01_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest "
    "tests/test_graphics_settings_preferences.py tests/test_graphics_settings_dialog.py "
    "tests/graph_track_b/qml_preference_bindings.py "
    "tests/main_window_shell/shell_basics_and_search.py --ignore=venv -q"
)
GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P02_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest "
    "tests/graph_track_b/qml_preference_bindings.py tests/test_flow_edge_labels.py "
    "--ignore=venv -q"
)
GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_TEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)

GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-033": (
            "Crossing style",
            "graphics.canvas.edge_crossing_style",
            "none",
            "gap_break",
            "global-only",
        ),
        "AC-REQ-UI-033-01": (
            "Crossing style",
            "Gap break",
            "app-wide choice",
            "hit testing",
            "stored graph data",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "REQ-PERF-009": (
            "graphics.canvas.edge_crossing_style",
            "screen space",
            "previewed and selected edges",
            "visible-edge order",
        ),
        "AC-REQ-PERF-009-01": (
            "qml_preference_bindings.py",
            "test_flow_edge_labels.py",
            "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-026": (
            "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
            "edge_crossing_style",
            "manual desktop checks",
            "desktop-only validation",
            "traceability gate",
        ),
        "AC-REQ-QA-026-01": (
            GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P01_COMMAND,
            GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P02_COMMAND,
            GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_TEST_COMMAND,
            GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_COMMAND,
            "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
        ),
    },
}

GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-033": (
        "graphics_settings_dialog.py",
        "GraphCanvas.qml",
        "EdgeLayer.qml",
        "tests/test_graphics_settings_preferences.py",
    ),
    "AC-REQ-UI-033-01": (
        "tests/test_graphics_settings_dialog.py",
        "tests/graph_track_b/qml_preference_bindings.py",
        "tests/main_window_shell/shell_basics_and_search.py",
    ),
    "REQ-PERF-009": (
        "EdgeMath.js",
        "EdgeLayer.qml",
        "tests/test_flow_edge_labels.py",
        "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
    ),
    "AC-REQ-PERF-009-01": (
        "tests/graph_track_b/qml_preference_bindings.py",
        "tests/test_flow_edge_labels.py",
        "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
    ),
    "REQ-QA-026": (
        "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
        "tests/test_traceability_checker.py",
        "scripts/check_traceability.py",
    ),
    "AC-REQ-QA-026-01": (
        GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_TEST_COMMAND,
        GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_COMMAND,
        "GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.md",
    ),
}

GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX_TOKENS = (
    "Global Gap Break Edge Crossing Variant QA Matrix",
    "## Locked Scope",
    "edge_crossing_style",
    "Crossing style",
    GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P01_COMMAND,
    GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_P02_COMMAND,
    GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_TEST_COMMAND,
    GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_COMMAND,
    "P01_edge_crossing_preference_pipeline_WRAPUP.md",
    "P02_gap_break_renderer_adoption_WRAPUP.md",
    "render-only decoration",
    "## Remaining Manual Smoke Checks",
    "## Residual Desktop-Only Validation",
)
NODE_EXECUTION_VISUALIZATION_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/NODE_EXECUTION_VISUALIZATION_QA_MATRIX.md"
)

NODE_EXECUTION_VISUALIZATION_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-034": (
            "run-scoped progress",
            "completion",
            "failure",
            "elapsed-time",
            "error inspection",
            "red/pink",
            "error badge",
            "yellow",
            "gray",
            "filled green",
            "outlined green",
            "invalid type only",
            "session-only",
            "second execution-state channel",
        ),
        "REQ-UI-048": (
            "remove every execution/failure grip",
            "control Settings row",
            "control-edge animation",
            "preserving passive `flow`",
        ),
        "AC-REQ-UI-034-01": (
            "node progress/completion/failure/error inspection",
            "red/pink",
            "yellow waiting",
            "gray no-data",
            "filled-green success",
            "outlined-green unwired defaults",
            "no runtime-failure coloring",
        ),
    },
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
        "REQ-NODE-027": (
            "running",
            "completion",
            "failure",
            "elapsed-time",
            "data wires shall never represent runtime failure or progress",
            "Session-only",
            "no project fields",
            "second execution-state channel",
        ),
        "AC-REQ-NODE-027-01": (
            "node progress/completion/failure/elapsed diagnostics remain available",
            "data wires receive no runtime-failure or progress state",
            "session-only",
            "project persistence does not expand",
        ),
    },
    "docs/specs/requirements/50_EXECUTION_ENGINE.md": {
        "REQ-EXEC-007": (
            "run/node lifecycle events",
            "state transitions",
            "completion",
            "failure",
            "started_at_epoch_ms",
            "elapsed_ms",
            "actual plugin execution time",
        ),
        "AC-REQ-EXEC-007-01": (
            "tests/test_execution_worker.py",
            "tests/test_process_client.py",
            "started_at_epoch_ms",
            "elapsed_ms",
            "shell-side fallback timing",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "REQ-PERF-010": (
            "existing edge geometry",
            "spatial index",
            "centerline hit target",
            "output cache",
            "execution-state revision",
            "160-character samples",
            "full runtime values",
            "second cache",
        ),
        "AC-REQ-PERF-010-01": (
            "shared hit geometry",
            "hittable disabled/empty edges",
            "exact preview bounds",
            "no full QML values",
            "no duplicate output cache",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-027": (
            "DataTree ordering/merge/modifiers/markers",
            "dependency Run/Run Selected",
            "empty/failure propagation",
            "complete removal of retired control ports/nodes/actions",
        ),
        "REQ-QA-028": (
            "no control grips or Settings state",
            "edge Enable/Ctrl+E/toolbar",
            "locked node status colors",
            "no second cache",
        ),
        "AC-REQ-QA-027-01": (
            "owning focused",
            "traceability",
            "Markdown links",
            "agent-map checks",
            "run_verification.py --mode fast --summarize-output",
        ),
        "AC-REQ-QA-028-01": (
            "focused QML",
            "node error treatment",
            "absence of control surfaces",
        ),
    },
}

NODE_EXECUTION_VISUALIZATION_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-EXEC-007": (
        "lifecycle events",
        "tests/test_execution_worker.py",
        "tests/test_process_client.py",
    ),
    "AC-REQ-EXEC-007-01": (
        "tests/test_execution_worker.py",
        "tests/test_process_client.py",
    ),
    "REQ-UI-034": (
        "Node-only",
        "invalid-type-only red wires",
        "shell execution projection",
        "QML host tests",
    ),
    "AC-REQ-UI-034-01": (
        "red/pink failed node",
        "yellow waiting",
        "gray no-data",
        "no runtime-failure wire red",
    ),
    "REQ-NODE-027": (
        "Node-only runtime visualization",
        "session-only elapsed/output facts",
        "no data-wire failure/progress state",
    ),
    "AC-REQ-NODE-027-01": (
        "node lifecycle diagnostics",
        "data wires have no runtime-failure/progress state",
        "caches remain transient",
    ),
    "REQ-PERF-010": (
        "Existing geometry/spatial-index/culling/cache/revision reuse",
        "no duplicate hit geometry",
        "full QML values",
        "second cache",
    ),
    "AC-REQ-PERF-010-01": (
        "shared hit geometry",
        "hittable disabled/empty edges",
        "exact preview bounds",
    ),
    "REQ-QA-027": (
        "Coordinated SDK/graph/persistence/compiler/scheduler/catalog/integration dataflow gate",
        "one final fast summarized verification run",
    ),
    "REQ-QA-028": (
        "control-surface absence",
        "replacement/append",
        "Enable/Ctrl+E",
        "active-data structure",
        "status colors",
    ),
    "AC-REQ-QA-027-01": (
        "Owning focused suites pass once",
        "traceability/Markdown/agent-map checks pass",
        "run_verification.py --mode fast --summarize-output",
    ),
    "AC-REQ-QA-028-01": (
        "Focused QML grip-hover",
        "absence of control surfaces",
    ),
}

NODE_EXECUTION_VISUALIZATION_QA_MATRIX_TOKENS = (
    "Node Execution Visualization QA Matrix",
    "node_started",
    "node_settled",
    "elapsed_ms",
    "session-only",
    "data wires",
    "runtime failure or progress",
    "tests/test_shell_run_controller.py",
    "tests/test_run_controller_unit.py",
    "## Final Closeout Commands",
)
NODE_EXECUTION_VISUALIZATION_QA_MATRIX_FORBIDDEN_TOKENS = (
    "authored control-edge",
    "execution_edge_progress",
    "node_completed",
    "`exec` / `completed` control-edge",
    "`On Failure`",
)

NESTED_NODE_CATEGORIES_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/NESTED_NODE_CATEGORIES_QA_MATRIX.md"
)
NESTED_NODE_CATEGORIES_INDEX_TOKENS = (
    "NESTED_NODE_CATEGORIES QA Matrix",
    "NESTED_NODE_CATEGORIES_QA_MATRIX.md",
)
NESTED_NODE_CATEGORIES_PUBLIC_DOC_TOKENS: dict[str, tuple[str, ...]] = {
    "docs/GETTING_STARTED.md": ("corex.node", "category_path", "NESTED_NODE_CATEGORIES_QA_MATRIX.md"),
}
NESTED_NODE_CATEGORIES_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-006": ("normalized category path", "descendant-inclusive", "category_key"),
        "AC-REQ-UI-006-01": ("Engineering > Import", "Engineering > Viewer"),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-003": ("category_path", "descendant-inclusive", "category_paths()"),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-033": ("NESTED_NODE_CATEGORIES_QA_MATRIX.md", "nested Engineering taxonomy"),
    },
}
NESTED_NODE_CATEGORIES_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-006": ("category_paths.py", "library_projection.py", "NESTED_NODE_CATEGORIES_QA_MATRIX.md"),
    "AC-REQ-UI-006-01": ("bridge_qml_boundaries.py", "drop_connect_and_workflow_io.py"),
    "REQ-NODE-003": ("category_paths.py", "test_registry_validation.py"),
    "REQ-QA-033": ("NESTED_NODE_CATEGORIES_QA_MATRIX.md", "tests/test_traceability_checker.py"),
}
NESTED_NODE_CATEGORIES_QA_MATRIX_TOKENS = (
    "Nested Node Categories QA Matrix",
    "## Locked Scope",
    "category_path: tuple[str, ...]",
    "`1..10`",
    "` > `",
    "Descendant filters",
    "Engineering > Import",
    "Engineering > Viewer",
    "Custom Workflows",
)

SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P01_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_graphics_settings_preferences.py "
    r"-k graph_typography_preferences --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P02_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/main_window_shell/bridge_contracts_graph_canvas.py tests/test_main_window_shell.py "
    r"-k graph_typography_bridge --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P03_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/main_window_shell/bridge_qml_boundaries.py tests/graph_track_b/qml_preference_bindings.py "
    r"-k graph_typography_qml_contract --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_SHELL_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_shell_run_controller.py -k graph_typography_host_chrome --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_PASSIVE_HOST_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/graph_surface/passive_host_interaction_suite.py -k graph_typography_host_chrome "
    r"--ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_QML_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/graph_track_b/qml_preference_bindings.py -k graph_typography_host_chrome "
    r"--ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_INLINE_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_graph_surface_input_inline.py tests/graph_track_b/qml_preference_bindings.py "
    r"-k graph_typography_inline_edge --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_EDGE_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_flow_edge_labels.py tests/graph_track_b/qml_preference_bindings.py "
    r"-k graph_typography_inline_edge --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_PASSIVE_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/graph_surface/passive_host_interaction_suite.py -k graph_typography_inline_edge "
    r"--ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P06_DIALOG_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_graphics_settings_dialog.py tests/test_graphics_settings_preferences.py "
    r"-k graph_typography_dialog --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_P06_SHELL_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/main_window_shell/shell_basics_and_search.py tests/graph_track_b/qml_preference_bindings.py "
    r"-k graph_typography_dialog --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_TEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)

SHARED_GRAPH_TYPOGRAPHY_CONTROL_INDEX_TOKENS = (
    "SHARED_GRAPH_TYPOGRAPHY_CONTROL QA Matrix",
    "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
)

SHARED_GRAPH_TYPOGRAPHY_CONTROL_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-035": (
            "graphics.typography.graph_label_pixel_size",
            "defaulting to `10`",
            "clamping to `8..50`",
            "GraphSharedTypography",
            "visual_style.font_size",
            "visual_style.font_weight",
            "graph-theme typography schema",
            ".cxproj",
        ),
        "AC-REQ-UI-035-01": (
            "Theme > Typography",
            "host-chrome",
            "passive-host",
            "shared role hierarchy",
            "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "REQ-PERF-011": (
            "deterministic metric alignment",
            "graph_label_pixel_size",
            "standard_metrics.py",
            "existing graph-canvas payload refresh or revision seam",
            "second typography-only invalidation channel",
            "stale clipping/label-width drift",
        ),
        "AC-REQ-PERF-011-01": (
            "bridge_qml_boundaries.py",
            "qml_preference_bindings.py",
            "test_flow_edge_labels.py",
            "8..50",
            "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-032": (
            "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
            "`P01` through `P06`",
            "manual desktop checks",
            "`PERSISTENT_NODE_ELAPSED_TIMES`",
            "desktop-only validation",
            "traceability gate",
        ),
        "AC-REQ-QA-032-01": (
            SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_TEST_COMMAND,
            SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_COMMAND,
            "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
        ),
    },
}

SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-035": (
        "settings.py",
        "app_preferences.py",
        "graphics_settings_dialog.py",
        "GraphSharedTypography.qml",
        "GraphNodeHeaderLayer.qml",
        "GraphNodePortsLayer.qml",
        "GraphInlinePropertiesLayer.qml",
        "GraphNodeHost.qml",
        "EdgeFlowLabelLayer.qml",
        "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
    ),
    "AC-REQ-UI-035-01": (
        "tests/test_graphics_settings_dialog.py",
        "tests/test_graphics_settings_preferences.py",
        "tests/test_shell_run_controller.py",
        "tests/test_graph_surface_input_inline.py",
        "tests/test_flow_edge_labels.py",
        "tests/graph_surface/passive_host_interaction_suite.py",
        "tests/graph_track_b/qml_preference_bindings.py",
        "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
    ),
    "REQ-PERF-011": (
        "standard_metrics.py",
        "graph_scene_payload/",
        "GraphCanvasPreferenceFacts.qml",
        "GraphSharedTypography.qml",
        "tests/main_window_shell/bridge_qml_boundaries.py",
        "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
    ),
    "AC-REQ-PERF-011-01": (
        "tests/main_window_shell/bridge_qml_boundaries.py",
        "tests/graph_track_b/qml_preference_bindings.py",
        "tests/test_flow_edge_labels.py",
        "SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
    ),
    "REQ-QA-032": (
        "docs/specs/INDEX.md",
        "docs/specs/perf/SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
        "docs/specs/requirements/20_UI_UX.md",
        "docs/specs/requirements/80_PERFORMANCE.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        "tests/test_traceability_checker.py",
        "scripts/check_traceability.py",
    ),
    "AC-REQ-QA-032-01": (
        SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_TEST_COMMAND,
        SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_COMMAND,
        "docs/specs/perf/SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.md",
    ),
}

SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX_TOKENS = (
    "Shared Graph Typography Control QA Matrix",
    "## Locked Scope",
    "graphics.typography.graph_label_pixel_size",
    "default `10`",
    "`8..50`",
    "GraphSharedTypography.qml",
    "visual_style.font_size",
    "visual_style.font_weight",
    "PERSISTENT_NODE_ELAPSED_TIMES",
    "second typography-only invalidation channel",
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P01_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P02_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P03_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_SHELL_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_PASSIVE_HOST_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P04_QML_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_INLINE_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_EDGE_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P05_PASSIVE_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P06_DIALOG_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_P06_SHELL_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_TEST_COMMAND,
    SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_COMMAND,
    "Accepted `P01` packet commit `af6d24a665b0910bfec54259424c89e3a9840593`",
    "Accepted `P06` packet commit `cd409e0cffd8d6e7c41a94f9dd70bee336c75965`",
    "## Final Closeout Commands",
    "## 2026-04-09 Execution Results",
    "## Remaining Manual Smoke Checks",
    "## Residual Desktop-Only Validation",
    "## Residual Risks",
)
DEFAULT_VALUE_GRIPS_QA_MATRIX = REPO_ROOT / "docs/specs/perf/DEFAULT_VALUE_GRIPS_QA_MATRIX.md"
DEFAULT_VALUE_GRIPS_T01_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py "
    r"tests/test_process_run_node.py tests/test_window_library_inspector.py --ignore=venv -q"
)
DEFAULT_VALUE_GRIPS_T02_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_default_port_values.py "
    r"tests/test_dataflow_execution_runtime.py tests/test_serializer.py "
    r"tests/test_port_availability.py --ignore=venv -q"
)
DEFAULT_VALUE_GRIPS_T03_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/graph_track_b/scene_model_graph_scene_suite.py "
    r"tests/test_graph_scene_bridge_bind_regression.py tests/test_data_tree_ui.py --ignore=venv -q"
)
DEFAULT_VALUE_GRIPS_T04_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py "
    r"tests/test_graph_surface_input_inline.py tests/test_port_flow_state.py --ignore=venv -q"
)
DEFAULT_VALUE_GRIPS_TRACEABILITY_TEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
DEFAULT_VALUE_GRIPS_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)

DEFAULT_VALUE_GRIPS_INDEX_TOKENS = (
    "Default Value Grips QA Matrix",
    "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
)

DEFAULT_VALUE_GRIPS_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-034": (
            "without a declared property default",
            "unwired property-default inputs outlined green",
        ),
        "REQ-UI-036": (
            "`default_property`",
            "`overridden_by_input`",
            "outlined-green default grip",
            "existing property commit path",
            "keep the embedded editor visible but muted and disabled",
            "safe upstream value",
            "neutral placeholder",
            "saved authored property",
            "restore that authored value immediately on disconnect",
            "shall not appear as duplicate canvas body/group rows",
        ),
        "REQ-UI-037": (
            "hide_optional_ports",
            "retired active-node `hide_locked_ports`",
            "unavailable add-on placeholder locks",
            "passive-object locking",
        ),
        "REQ-UI-048": (
            "Ctrl-drag",
            "Ctrl+Shift",
            "Blank release",
            "leave the graph unchanged",
        ),
        "AC-REQ-UI-036-01": (
            "outlined default grips",
            "property retention while overridden",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
        "AC-REQ-UI-037-01": (
            "complete active-lock chrome/gesture removal",
            "unchanged unavailable add-on plus passive-object locking",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/30_GRAPH_MODEL.md": {
        "REQ-GRAPH-019": (
            "PortSpec.uses_property_default",
            "NodeInstance.properties",
            "Any enabled incoming wire",
            "Disabled-only wires",
            "`0`, `0.0`, `False`, and `\"\"`",
        ),
        "REQ-GRAPH-020": (
            "`rewire_edges(...)`",
            "`request_rewire_edges(edge_ids, ...)`",
            "one validated mutation and one history snapshot",
            "preserve every moved edge's identity",
            "append-requested release",
            "leave the original graph unchanged",
            "active-node lock state and `hide_locked_ports` are removed",
        ),
        "AC-REQ-GRAPH-019-01": (
            "Item/List/Tree default construction",
            "enabled-wire precedence",
            "falsey-value retention",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
        "AC-REQ-GRAPH-020-01": (
            "atomic batch move/disconnect",
            "one-step undo",
            "absence of active lock state",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-021": (
            "existing `NodeInstance.properties` field",
            "Active-node `locked_ports` and `hide_locked_ports` shall not be written",
            "without a schema bump",
            "Unavailable add-on placeholder metadata",
        ),
        "AC-REQ-PERSIST-021-01": (
            "serializer and default-value regressions",
            "obsolete active-lock keys are omitted on write",
            "unavailable add-on and passive-object locks still round-trip",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "REQ-PERF-012": (
            "existing graph-scene payload",
            "reuse existing row controls",
            "reuse existing socket/edge hit geometry",
            "second default store",
            "history framework",
        ),
        "AC-REQ-PERF-012-01": (
            "focused default-value",
            "preserved host-row/socket geometry",
            "single-mutation Ctrl-drag history",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-034": (
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
            "explicit typed defaults",
            "atomic Ctrl-drag endpoint reassignment",
            "unavailable add-on/passive-lock preservation",
            "feature-owned traceability gate",
        ),
        "AC-REQ-QA-034-01": (
            DEFAULT_VALUE_GRIPS_TRACEABILITY_TEST_COMMAND,
            DEFAULT_VALUE_GRIPS_TRACEABILITY_COMMAND,
            "check_markdown_links.py",
            "check_agent_maps.py",
            "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        ),
    },
}

DEFAULT_VALUE_GRIPS_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-036": (
        "GraphNodeHost.qml",
        "GraphNodePortsLayer.qml",
        "graph_scene_payload/",
        "tests/test_graph_surface_input_controls.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-UI-036-01": (
        "tests/test_graph_surface_input_contract.py",
        "tests/test_graph_surface_input_controls.py",
        "tests/test_graph_surface_input_inline.py",
        "tests/test_port_flow_state.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-UI-037": (
        "graph_canvas_state/",
        "GraphCanvasPreferenceFacts.qml",
        "tests/graph_surface/pointer_and_modal_suite.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-UI-037-01": (
        "tests/test_graph_scene_bridge_bind_regression.py",
        "tests/test_port_availability.py",
        "tests/test_passive_graph_surface_host.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-GRAPH-019": (
        "node_specs.py",
        "registry.py",
        "tests/test_default_port_values.py",
        "tests/test_dataflow_execution_runtime.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-GRAPH-019-01": (
        "tests/test_registry_validation.py",
        "tests/test_default_port_values.py",
        "tests/test_dataflow_execution_runtime.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-GRAPH-020": (
        "validated_mutation.py",
        "graph_scene_payload/",
        "graph_scene_mutation_history.py",
        "GraphCanvasInteractionState.qml",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-GRAPH-020-01": (
        "tests/test_graph_scene_bridge_bind_regression.py",
        "tests/graph_track_b/scene_model_graph_scene_suite.py",
        "tests/test_data_tree_ui.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-PERSIST-021": (
        "records.py",
        "workspace_state.py",
        "project_codec.py",
        "tests/test_serializer.py",
        "tests/test_default_port_values.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-PERSIST-021-01": (
        "tests/test_serializer.py",
        "tests/test_default_port_values.py",
        "tests/test_port_availability.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-PERF-012": (
        "graph_scene_payload/",
        "GraphNodeHost.qml",
        "GraphCanvasInteractionState.qml",
        "tests/test_graph_surface_input_controls.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "AC-REQ-PERF-012-01": (
        "tests/test_graph_scene_bridge_bind_regression.py",
        "tests/test_graph_surface_input_controls.py",
        "tests/graph_surface/pointer_and_modal_suite.py",
        "DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
    "REQ-QA-034": (
        "docs/specs/INDEX.md",
        "docs/specs/perf/DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
        "docs/specs/requirements/20_UI_UX.md",
        "docs/specs/requirements/30_GRAPH_MODEL.md",
        "docs/specs/requirements/60_PERSISTENCE.md",
        "docs/specs/requirements/80_PERFORMANCE.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        "tests/test_traceability_checker.py",
        "scripts/check_traceability.py",
    ),
    "AC-REQ-QA-034-01": (
        DEFAULT_VALUE_GRIPS_TRACEABILITY_TEST_COMMAND,
        DEFAULT_VALUE_GRIPS_TRACEABILITY_COMMAND,
        "docs/specs/perf/DEFAULT_VALUE_GRIPS_QA_MATRIX.md",
    ),
}

DEFAULT_VALUE_GRIPS_QA_MATRIX_TOKENS = (
    "Default Value Grips QA Matrix",
    "## Locked Scope",
    "PortSpec.uses_property_default",
    "NodeInstance.properties",
    "hide_optional_ports",
    "Ctrl-drag",
    "unavailable add-on placeholders",
    DEFAULT_VALUE_GRIPS_T01_COMMAND,
    DEFAULT_VALUE_GRIPS_T02_COMMAND,
    DEFAULT_VALUE_GRIPS_T03_COMMAND,
    DEFAULT_VALUE_GRIPS_T04_COMMAND,
    DEFAULT_VALUE_GRIPS_TRACEABILITY_TEST_COMMAND,
    DEFAULT_VALUE_GRIPS_TRACEABILITY_COMMAND,
    "## Final Closeout Commands",
    "## 2026-07-19 Execution Results",
    "## Remaining Manual Smoke Checks",
    "## Residual Desktop-Only Validation",
    "## Residual Risks",
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P01_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_node_title_icon_sources.py "
    r"tests/test_registry_validation.py tests/test_passive_visual_metadata.py "
    r"-k title_icon --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P02_DIALOG_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_graphics_settings_preferences.py tests/test_graphics_settings_dialog.py "
    r"-k graph_node_icon_size --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P02_BRIDGE_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/main_window_shell/bridge_contracts_graph_canvas.py "
    r"tests/main_window_shell/bridge_qml_boundaries.py tests/test_main_window_shell.py "
    r"tests/test_shell_run_controller.py tests/graph_track_b/qml_preference_bindings.py "
    r"-k graph_node_icon_size --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P03_HEADER_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/graph_surface/inline_editor_suite.py "
    r"tests/graph_surface/passive_host_interaction_suite.py "
    r"tests/graph_track_b/qml_preference_rendering_suite.py "
    r"-k title_icon --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P03_COMMENT_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_group_backdrop_collapse.py "
    r"tests/main_window_shell/shell_runtime_contracts.py "
    r"tests/test_icon_registry.py tests/test_group_backdrop_contracts.py "
    r"-k title_icon --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P04_ASSET_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_node_title_icon_assets.py "
    r"tests/test_registry_validation.py -k title_icon --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_P04_CATALOG_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py "
    r"tests/test_passive_node_contracts.py tests/test_passive_flowchart_catalog.py "
    r"-k title_icon --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_TEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)

TITLE_ICONS_FOR_NON_PASSIVE_NODES_INDEX_TOKENS = (
    "TITLE_ICONS_FOR_NON_PASSIVE_NODES QA Matrix",
    "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
)

TITLE_ICONS_FOR_NON_PASSIVE_NODES_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-038": (
            "leading local title icon only for `active` and `compile_only` nodes",
            "supported local `.svg`, `.png`, `.jpg`, or `.jpeg` file",
            "passive nodes remain iconless",
            "`uiIcons` / `comment.svg`",
            "`icon_theme_aware`",
            "repo-managed SVG title icons track the active header text color",
            "`graph_node_icon_pixel_size_override`",
            "`null` mode follows `graph_label_pixel_size`",
            "`8..50`",
        ),
        "AC-REQ-UI-038-01": (
            "active and `compile_only` headers render the path-backed icon",
            "eligible repo-managed SVG title icons tint from `headerTextColor`",
            "passive titles stay iconless",
            "centered/elided title behavior",
            "automatic/custom icon-size modes",
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-028": (
            "Private `NodeTypeSpec.icon` remains the normalized metadata field",
            "local image-path reference only",
            "repo-managed node-title icon asset root",
            "approved provenance root",
            "symbolic names",
            "`icon_theme_aware=True`",
            "Passive flowchart library visuals",
        ),
        "AC-REQ-NODE-028-01": (
            "node-title icon resolver",
            "safe provenance resolution",
            "built-in asset-path packaging",
            "repo-managed SVG `icon_theme_aware` derivation",
            "passive icon exclusion",
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-022": (
            "derived live `icon_source` and `icon_theme_aware` values shall not serialize into `.cxproj` project files",
            "`graphics.typography.graph_node_icon_pixel_size_override`",
            "nullable app-global integer",
            "`null` mode follows `graph_label_pixel_size`",
            "`8..50`",
        ),
        "AC-REQ-PERSIST-022-01": (
            "payload-contract",
            "`icon_source` and `icon_theme_aware` remain derived/live-only",
            "app preferences",
            "does not widen `.cxproj` persistence",
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "REQ-PERF-013": (
            "existing graph-scene payload, shared header, and shared typography seams",
            "already-derived local `icon_source`, derived `icon_theme_aware`, active `headerTextColor`",
            "centered/elided title reserve math",
            "collapsed group exception",
            "repo-managed SVG title icons to theme-tint from the header text color",
            "plugin/add-on image colors authored/untinted by default",
            "remote image loading",
            "second icon-specific invalidation path",
        ),
        "AC-REQ-PERF-013-01": (
            "tests/graph_surface/inline_editor_suite.py",
            "tests/graph_surface/passive_host_interaction_suite.py",
            "tests/qml_quick/tst_graph_node_host.qml",
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-037": (
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
            "`P01` through `P04`",
            "canonical `docs/specs/INDEX.md` registration",
            "theme-aware repo-managed SVG rendering",
            "theme-aware repo-managed SVG rendering plus PNG/JPG/JPEG fixture coverage where available",
            "collapsed group icon preservation",
            "traceability gate",
        ),
        "AC-REQ-QA-037-01": (
            TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_TEST_COMMAND,
            TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_COMMAND,
            "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        ),
    },
}

TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-038": (
        "graphics_settings_dialog.py",
        "graph_canvas_state/",
        "GraphNodeHeaderLayer.qml",
        "GraphNodeHost.qml",
        "GraphSharedTypography.qml",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "AC-REQ-UI-038-01": (
        "tests/test_graphics_settings_dialog.py",
        "tests/test_graphics_settings_preferences.py",
        "tests/test_graph_canvas_split_bridges.py",
        "tests/graph_surface/inline_editor_suite.py",
        "tests/graph_surface/passive_host_interaction_suite.py",
        "tests/graph_track_b/qml_preference_rendering_suite.py",
        "tests/qml_quick/tst_graph_node_host.qml",
        "tests/test_group_backdrop_contracts.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "REQ-NODE-028": (
        "node_title_icon_sources.py",
        "graph_scene_payload/",
        "assets/node_title_icons",
        "tests/test_node_title_icon_sources.py",
        "tests/test_node_title_icon_assets.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "AC-REQ-NODE-028-01": (
        "tests/test_node_title_icon_sources.py",
        "tests/test_registry_validation.py",
        "tests/test_passive_visual_metadata.py",
        "tests/test_node_title_icon_assets.py",
        "tests/test_passive_node_contracts.py",
        "tests/test_passive_flowchart_catalog.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "REQ-PERSIST-022": (
        "app_preferences.py",
        "settings.py",
        "graph_scene_payload/",
        "tests/test_graphics_settings_preferences.py",
        "tests/test_node_title_icon_sources.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "AC-REQ-PERSIST-022-01": (
        "tests/test_graphics_settings_preferences.py",
        "tests/test_graph_canvas_split_bridges.py",
        "tests/test_main_window_shell.py",
        "tests/test_node_title_icon_sources.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "REQ-PERF-013": (
        "GraphNodeHeaderLayer.qml",
        "GraphNodeHost.qml",
        "GraphSharedTypography.qml",
        "node_title_icon_sources.py",
        "tests/graph_track_b/qml_preference_rendering_suite.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "AC-REQ-PERF-013-01": (
        "tests/graph_surface/inline_editor_suite.py",
        "tests/graph_surface/passive_host_interaction_suite.py",
        "tests/graph_track_b/qml_preference_rendering_suite.py",
        "tests/qml_quick/tst_graph_node_host.qml",
        "tests/test_group_backdrop_contracts.py",
        "TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
    "REQ-QA-037": (
        "docs/specs/INDEX.md",
        "docs/specs/perf/TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
        "docs/specs/requirements/20_UI_UX.md",
        "docs/specs/requirements/40_NODE_SDK.md",
        "docs/specs/requirements/60_PERSISTENCE.md",
        "docs/specs/requirements/80_PERFORMANCE.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        "tests/test_traceability_checker.py",
        "scripts/check_traceability.py",
    ),
    "AC-REQ-QA-037-01": (
        TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_TEST_COMMAND,
        TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_COMMAND,
        "docs/specs/perf/TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.md",
    ),
}

TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX_TOKENS = (
    "Title Icons for Non-Passive Nodes QA Matrix",
    "## Locked Scope",
    "`NodeTypeSpec.icon` remains the authoring field",
    "`icon_theme_aware`",
    "`headerTextColor`",
    "`uiIcons` / `comment.svg`",
    "`graphics.typography.graph_node_icon_pixel_size_override`",
    "node-library tiles",
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P01_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P02_DIALOG_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P02_BRIDGE_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P03_HEADER_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P03_COMMENT_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P04_ASSET_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_P04_CATALOG_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_TEST_COMMAND,
    TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_COMMAND,
    "Accepted `P01` packet commit `bfb953365082f1d96371fe919e92e995875b43f0`",
    "Accepted `P04` packet commit `33090d22b59e01b45fb37521cd283cc53dce8548`",
    "## Final Closeout Commands",
    "## 2026-04-13 Execution Results",
    "## Remaining Manual Smoke Checks",
    "## Residual Desktop-Only Validation",
    "## Residual Risks",
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md"
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_FINAL_REGRESSION_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_dead_code_hygiene.py tests/test_run_verification.py "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py "
    "tests/test_shell_isolation_phase.py --ignore=venv -q"
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX = (
    REPO_ROOT / manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC
)
ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND
)
ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND
)
ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND
)

ARCHITECTURE_MAINTAINABILITY_REFACTOR_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-025": (
            "scripts/check_markdown_links.py",
            "docs/PACKAGING_WINDOWS.md",
            "docs/PILOT_RUNBOOK.md",
            "docs/specs/INDEX.md",
            "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
        ),
        "AC-REQ-QA-025-01": (
            ARCHITECTURE_MAINTAINABILITY_REFACTOR_FINAL_REGRESSION_COMMAND,
            ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_COMMAND,
            ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND,
            "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
        ),
    },
}

ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-QA-025": (
        "ARCHITECTURE.md",
        "docs/PACKAGING_WINDOWS.md",
        "docs/PILOT_RUNBOOK.md",
        "docs/specs/INDEX.md",
        "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
        "scripts/check_markdown_links.py",
        "tests/test_shell_isolation_phase.py",
        "tests/test_markdown_hygiene.py",
    ),
    "AC-REQ-QA-025-01": (
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_FINAL_REGRESSION_COMMAND,
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_COMMAND,
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND,
        "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
    ),
}

ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_TOKENS = (
    "Architecture Maintainability Refactor QA Matrix",
    "## Locked Scope",
    "## Shell Isolation Contract",
    ARCHITECTURE_MAINTAINABILITY_REFACTOR_FINAL_REGRESSION_COMMAND,
    ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_COMMAND,
    ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND,
    "docs/PACKAGING_WINDOWS.md",
    "docs/PILOT_RUNBOOK.md",
    "ARCHITECTURE_REFACTOR_QA_MATRIX.md",
    "RC_PACKAGING_REPORT.md",
    "PILOT_SIGNOFF.md",
    "tests/shell_isolation_runtime.py",
    "tests/shell_isolation_main_window_targets.py",
    "tests/shell_isolation_controller_targets.py",
    "tests/test_markdown_hygiene.py",
    "## Remaining Manual and Windows-Only Checks",
    "## Historical References",
)
ARCHITECTURE_RESIDUAL_REFACTOR_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-029": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["REQ-QA-029"],
        "AC-REQ-QA-029-01": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["AC-REQ-QA-029-01"],
    },
}

ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-QA-029": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["REQ-QA-029"],
    "AC-REQ-QA-029-01": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["AC-REQ-QA-029-01"],
}

ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_TOKENS = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_REQUIRED_TOKENS
)
UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md"
)
UI_CONTEXT_SCALABILITY_REFACTOR_FINAL_PYTEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py "
    "tests/test_run_verification.py --ignore=venv -q"
)
UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)
UI_CONTEXT_SCALABILITY_REFACTOR_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-030": (
            "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
            "P07",
            "context-budget",
            "P08",
            "subsystem-doc",
            "CONTEXT_BUDGET_RULES.json",
            "SUBSYSTEM_PACKET_INDEX.md",
            "FEATURE_PACKET_TEMPLATE.md",
            "not a required future coding gate",
        ),
        "AC-REQ-QA-030-01": (
            UI_CONTEXT_SCALABILITY_REFACTOR_FINAL_PYTEST_COMMAND,
            UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_COMMAND,
            UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND,
            "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
        ),
    },
}
UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-QA-030": (
        "docs/specs/INDEX.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
        "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
        "docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md",
        "docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md",
        "scripts/check_traceability.py",
        "tests/test_traceability_checker.py",
        "tests/test_markdown_hygiene.py",
        "tests/test_run_verification.py",
    ),
    "AC-REQ-QA-030-01": (
        UI_CONTEXT_SCALABILITY_REFACTOR_FINAL_PYTEST_COMMAND,
        UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_COMMAND,
        UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND,
        "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
    ),
}
UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_TOKENS = (
    "UI Context Scalability Refactor QA Matrix",
    "## Locked Scope",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-04-05 Execution Results",
    "## Remaining Manual Desktop Checks",
    "## Residual Risks",
    "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
    "docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md",
    "scripts/check_context_budgets.py",
    "tests/test_run_verification.py",
    UI_CONTEXT_SCALABILITY_REFACTOR_FINAL_PYTEST_COMMAND,
    UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_COMMAND,
    UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND,
    "P01_shell_window_facade_collapse_WRAPUP.md",
    "P02_presenter_family_split_WRAPUP.md",
    "P03_graph_scene_bridge_packet_split_WRAPUP.md",
    "P04_graph_canvas_root_packetization_WRAPUP.md",
    "P05_edge_renderer_packet_split_WRAPUP.md",
    "P06_viewer_surface_isolation_WRAPUP.md",
    "P07_context_budget_guardrails_WRAPUP.md",
    "P08_subsystem_packet_docs_WRAPUP.md",
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_FINAL_PYTEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py "
    "tests/test_run_verification.py --ignore=venv -q"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)
UI_CONTEXT_SCALABILITY_FOLLOWUP_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-031": (
            "UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md",
            "P01",
            "guardrail",
            "P08",
            "packet-doc",
            "UI_CONTEXT_SCALABILITY_FOLLOWUP_MANIFEST.md",
            "UI_CONTEXT_SCALABILITY_FOLLOWUP_STATUS.md",
            "packet wrap-up evidence",
            "CONTEXT_BUDGET_RULES.json",
            "SUBSYSTEM_PACKET_INDEX.md",
            "FEATURE_PACKET_TEMPLATE.md",
        ),
        "AC-REQ-QA-031-01": (
            UI_CONTEXT_SCALABILITY_FOLLOWUP_FINAL_PYTEST_COMMAND,
            UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND,
            UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND,
            "UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md",
        ),
    },
}
UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-QA-031": (
        "docs/specs/INDEX.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        "docs/specs/perf/UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md",
        "docs/specs/work_packets/ui_context_scalability_followup/UI_CONTEXT_SCALABILITY_FOLLOWUP_MANIFEST.md",
        "docs/specs/work_packets/ui_context_scalability_followup/UI_CONTEXT_SCALABILITY_FOLLOWUP_STATUS.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P01_guardrail_catalog_expansion_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P02_shell_session_surface_split_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P03_graph_geometry_facade_split_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P04_graph_scene_mutation_packet_split_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P05_main_window_bridge_test_packetization_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P06_graph_surface_test_packetization_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P07_track_b_test_packetization_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_followup/P08_canonical_ui_test_packet_docs_WRAPUP.md",
        "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
        "docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md",
        "docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md",
        "scripts/check_traceability.py",
        "tests/test_traceability_checker.py",
        "tests/test_markdown_hygiene.py",
        "tests/test_run_verification.py",
    ),
    "AC-REQ-QA-031-01": (
        UI_CONTEXT_SCALABILITY_FOLLOWUP_FINAL_PYTEST_COMMAND,
        UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND,
        UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND,
        "UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.md",
    ),
}
UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX_TOKENS = (
    "UI Context Scalability Follow-Up QA Matrix",
    "## Locked Scope",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-04-05 Execution Results",
    "## Remaining Manual Desktop Checks",
    "## Residual Risks",
    "UI_CONTEXT_SCALABILITY_FOLLOWUP_MANIFEST.md",
    "UI_CONTEXT_SCALABILITY_FOLLOWUP_STATUS.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
    "docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/MAIN_WINDOW_SHELL_TEST_PACKET.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/GRAPH_SURFACE_TEST_PACKET.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/TRACK_B_TEST_PACKET.md",
    manifest.CONTEXT_BUDGET_CHECK_COMMAND,
    manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_PYTEST_COMMAND,
    manifest.FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_FAST_DRY_RUN_COMMAND,
    UI_CONTEXT_SCALABILITY_FOLLOWUP_FINAL_PYTEST_COMMAND,
    UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_COMMAND,
    UI_CONTEXT_SCALABILITY_FOLLOWUP_MARKDOWN_COMMAND,
    "P01_guardrail_catalog_expansion_WRAPUP.md",
    "P02_shell_session_surface_split_WRAPUP.md",
    "P03_graph_geometry_facade_split_WRAPUP.md",
    "P04_graph_scene_mutation_packet_split_WRAPUP.md",
    "P05_main_window_bridge_test_packetization_WRAPUP.md",
    "P06_graph_surface_test_packetization_WRAPUP.md",
    "P07_track_b_test_packetization_WRAPUP.md",
    "P08_canonical_ui_test_packet_docs_WRAPUP.md",
)


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def replace_text(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8-sig").replace(old, new), encoding="utf-8")


def update_markdown_table_result(path: Path, command: str, new_result: str, new_notes: str | None = None) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    command_cell = f"`{command}`"
    for index, line in enumerate(lines):
        if not line.startswith(f"| {command_cell} |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        cells[1] = new_result
        if new_notes is not None and len(cells) > 2:
            cells[2] = new_notes
        lines[index] = "| " + " | ".join(cells) + " |"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"Command row not found: {command}")


def remove_token_from_traceability_row(path: Path, row_id: str, token: str) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"| {row_id} |"):
            continue
        lines[index] = line.replace(token, "").replace(", ,", ",")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"Traceability row not found: {row_id}")


def remove_token_from_requirement_line(path: Path, requirement_id: str, token: str) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"- `{requirement_id}`:"):
            continue
        lines[index] = line.replace(token, "").replace("  ", " ")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"Requirement line not found: {requirement_id}")


def parse_requirement_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^- `([^`]+)`: (.+)$", line.strip())
        if match is not None:
            parsed[match.group(1)] = match.group(2)
    return parsed


def parse_markdown_table(text: str) -> list[dict[str, str]]:
    table_lines = [line for line in text.splitlines() if line.startswith("|")]
    if len(table_lines) < 2:
        raise AssertionError("Markdown table not found.")
    headers = [cell.strip() for cell in table_lines[0].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def requirement_line(path: Path, requirement_id: str) -> str:
    requirements = parse_requirement_lines(path.read_text(encoding="utf-8-sig"))
    body = requirements.get(requirement_id)
    if body is None:
        raise AssertionError(f"Requirement line not found: {requirement_id}")
    return body


def traceability_row(path: Path, row_id: str) -> str:
    rows = parse_markdown_table(path.read_text(encoding="utf-8-sig"))
    for row in rows:
        if row.get("Requirement ID") == row_id:
            return row.get("Implementation Artifact", "")
    raise AssertionError(f"Traceability row not found: {row_id}")


COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_INTEGRATED_COMMAND = (
    r"$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest "
    r"tests/test_corex_web_host_assets.py tests/test_corex_web_surface_bridge.py "
    r"tests/test_excalidraw_board_node.py tests/test_content_fullscreen_bridge.py "
    r"tests/test_graph_surface_input_controls.py tests/test_passive_graph_surface_host.py "
    r"tests/test_packaging_configuration.py --ignore=venv -q"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_DOCS_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_run_verification.py "
    r"tests/test_pytest_defaults.py --ignore=venv -q"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_markdown_links.py"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_FAST_COMMAND = (
    r".\venv\Scripts\python.exe scripts/run_verification.py --mode fast"
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_run_verification.py "
    r"tests/test_pytest_defaults.py --ignore=venv -q"
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_markdown_links.py"
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND = (
    COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_INDEX_TOKENS = (
    "[COREX_EXCALIDRAW_WEB_HOST_LAYER QA Matrix](perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md)",
    "COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md",
    "COREX_EXCALIDRAW_REAL_EDITOR_STATUS.md",
    "[COREX_EXCALIDRAW_REAL_EDITOR QA Evidence](perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md)",
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-044": (
            "excalidraw.board",
            "contentFullscreenBridge",
            "WebEngine is required",
            "local/offline packaged assets",
            "managed image imports",
            "artifact-backed previews",
            "no external browser launch",
        ),
        "AC-REQ-UI-044-01": (
            "compact web-board surface",
            "fullscreen web editor payload",
            "managed image import",
            "artifact-backed preview",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-030": (
            "excalidraw.board",
            'runtime_behavior="passive"',
            'surface_family="web"',
            "excalidraw_state",
            "excalidraw_preview_ref",
            "excalidraw_state.files[*].artifact_ref",
            "arbitrary third-party web UI registration",
        ),
        "AC-REQ-NODE-030-01": (
            "excalidraw.board",
            "managed image imports",
            "execution snapshots",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
        "REQ-NODE-031": (
            "execution-free",
            "WebEngine",
            "managed image import",
            "fullscreen editor",
            "worker execution path",
        ),
        "AC-REQ-NODE-031-01": (
            "flattened execution graphs",
            "no execution-worker WebEngine behavior",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-024": (
            "excalidraw_state",
            "excalidraw_state.files[*].artifact_ref",
            "excalidraw_preview_ref",
            "project artifact store",
            "data:image",
            "WebEngine availability",
        ),
        "AC-REQ-PERSIST-024-01": (
            "hidden project property",
            "managed imported images",
            "embedded `data:image` payloads",
            "embedded binary previews",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/70_INTEGRATIONS.md": {
        "REQ-INT-014": (
            "PyQt6-WebEngine",
            "local/offline",
            "@excalidraw/excalidraw@0.18.1",
            "WebSurfaceBridge",
            "managed image imports",
            "artifact-backed previews",
            "remote rooms",
            "arbitrary third-party web UI registration",
        ),
        "AC-REQ-INT-014-01": (
            "required runtime dependency",
            "local/offline real editor asset loading",
            "managed image import",
            "preview artifact behavior",
            "package-data/frozen inclusion",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-045": (
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
            "COREX_EXCALIDRAW_REAL_EDITOR",
            "`P01` through `P05` proof",
            "exact `P06` docs/proof commands",
            "no collaboration",
            "no remote rooms",
            "no external browser launch",
            "no execution-worker WebEngine behavior",
            "no arbitrary third-party web UI registration",
        ),
        "AC-REQ-QA-045-01": (
            COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND,
        ),
    },
}
COREX_EXCALIDRAW_WEB_HOST_LAYER_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-044": (
        "GraphWebBoardSurface.qml",
        "content_fullscreen_bridge.py",
        "WebEditorHost.qml",
        "web/excalidraw_host/src/main.tsx",
        "P01_js_host_bundle_WRAPUP.md",
        "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "AC-REQ-UI-044-01": (
        "tests/test_content_fullscreen_bridge.py",
        "tests/test_corex_web_surface_bridge.py",
        "tests/test_passive_graph_surface_host.py",
        "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
        "P06_docs_traceability_closeout_WRAPUP.md",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "REQ-NODE-030": (
        "nodes/builtins/excalidraw.py",
        "tests/test_excalidraw_board_node.py",
        "tests/test_passive_runtime_wiring.py",
        "tests/test_project_save_as_flow.py",
        "P04_persistence_save_as_refs_WRAPUP.md",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "AC-REQ-NODE-030-01": (
        "managed-image artifact-ref",
        "tests/test_project_save_as_flow.py",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "REQ-NODE-031": (
        "execution/runtime_snapshot.py",
        "web_host/bridge.py",
        "no execution-worker WebEngine behavior",
        "tests/test_passive_runtime_wiring.py",
        "P02_artifact_backed_web_bridge_WRAPUP.md",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "AC-REQ-NODE-031-01": (
        "WebEngine/WebChannel/import/preview/fullscreen behavior remains shell-only",
        "tests/test_content_fullscreen_bridge.py",
        "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
    ),
    "REQ-PERSIST-024": (
        "project_codec.py",
        "common/artifact_refs.py",
        "web_host/bridge.py",
        "round_trip_cases.py",
        "tests/test_content_fullscreen_bridge.py",
        "tests/test_project_save_as_flow.py",
        "P02_artifact_backed_web_bridge_WRAPUP.md",
        "P04_persistence_save_as_refs_WRAPUP.md",
        "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
    "AC-REQ-PERSIST-024-01": (
        "excalidraw_state.files[*].artifact_ref",
        "no `data:image` payloads",
        "tests/test_project_save_as_flow.py",
        "P04_persistence_save_as_refs_WRAPUP.md",
    ),
    "REQ-INT-014": (
        "web/excalidraw_host/package.json",
        "web/excalidraw_host/src/main.tsx",
        "scripts/build_excalidraw_host.ps1",
        "web_host/assets.py",
        "web_host/webengine.py",
        "web_host/bridge.py",
        "web_assets/excalidraw_host/index.html",
        "P01_js_host_bundle_WRAPUP.md",
        "P02_artifact_backed_web_bridge_WRAPUP.md",
        "P05_packaging_and_static_asset_proof_WRAPUP.md",
        "tests/test_packaging_configuration.py",
    ),
    "AC-REQ-INT-014-01": (
        "managed image import",
        "artifact-backed preview",
        "no external/collaboration/remote-room/execution-worker/arbitrary-web expansion proof",
        "tests/test_project_save_as_flow.py",
        "P05_packaging_and_static_asset_proof_WRAPUP.md",
    ),
    "REQ-QA-045": (
        "docs/specs/INDEX.md",
        "docs/specs/perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        "COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md",
        "P06_docs_traceability_closeout_WRAPUP.md",
        "tests/test_traceability_checker.py",
        "tests/test_run_verification.py",
        "tests/test_pytest_defaults.py",
        "scripts/verification_manifest.py",
    ),
    "AC-REQ-QA-045-01": (
        COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
        COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
        COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
        "P06_docs_traceability_closeout_WRAPUP.md",
        "docs/specs/perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
    ),
}
COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX_TOKENS = (
    "COREX Excalidraw Web Host Layer QA Matrix",
    "## Locked Scope",
    'runtime_behavior="passive"',
    "local/offline packaged files",
    "real local/offline Excalidraw editor",
    "managed image imports",
    "artifact-backed previews",
    "no execution semantics",
    "third-party plugin web UIs",
    "## Historical Host-Layer Baseline",
    "## Retained Automated Verification",
    "109733f7a302deabca330baa10a3b6c75859a046",
    "78a2374abc579f69a70dbe068c616b1d6db2046b",
    "11369373e7f4d5a2865a71631448a5a92d4b39ea",
    "f77facd2e0a9642e55a8705ef05912aa6b12c944",
    "1e00c761857b4b22930e5b83943cbdd728ebbab7",
    "0d5775d29230aef29c91ab7fb2d640c682fafedf",
    "d35085d2fd66a7bacab2c4fcf5be5e43a938997b",
    "## Real Editor Follow-Up",
    "186c7cdac24958d23e18aaf49d7c6458b0581bbc",
    "0b795f01cbda87b052709e816c185884114419f1",
    "855be262aa61974b325efd0e05c2846cd4c4fdec",
    "88f82d7f421ec01b32e5fe35c3d1dbd07c40c73e",
    "486f8cad07d125e8afc3204aa99effdbd796aea8",
    COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
    COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
    COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
    "Ready for manual testing",
    "## Residual Risks",
)

CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX = (
    REPO_ROOT / "docs/specs/perf/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md"
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FOCUSED_WEB_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_webengine_navigation_policy.py "
    r"tests/test_web_page_viewer_node.py tests/test_content_fullscreen_bridge.py "
    r"tests/test_corex_web_host_assets.py --ignore=venv -q"
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\check_traceability.py"
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\check_markdown_links.py"
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FAST_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast"
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_REVIEW_GATE_COMMAND = (
    CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MARKDOWN_COMMAND
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_INDEX_TOKENS = (
    "[CHROMIUM_WEBSITE_HTML_VIEWER_NODE QA Matrix](perf/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md)",
)
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-046": (
            "web.page_viewer",
            "web_page",
            "WebEngine-unavailable",
            "QWebChannel",
            "Excalidraw `web_editor`",
        ),
        "AC-REQ-UI-046-01": (
            "WebPageHost",
            "bridge-free",
            "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-033": (
            "web.page_viewer",
            'runtime_behavior="passive"',
            'surface_family="web"',
            "start_location",
            "persist_browser_state",
            "browser automation",
        ),
        "AC-REQ-NODE-033-01": (
            "web.page_viewer",
            "safe configuration/browser-state properties",
            "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/70_INTEGRATIONS.md": {
        "REQ-INT-016": (
            "Qt WebEngine",
            "web_page",
            "`.cxproj`",
            "Excalidraw `WebSurfaceBridge`",
        ),
        "AC-REQ-INT-016-01": (
            "URL/local HTML normalization",
            "bridge-free generic pages",
            "`.cxproj` persistence",
            "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/90_QA_ACCEPTANCE.md": {
        "REQ-QA-048": (
            "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
            "`P01` through `P04` verification commands",
            "exact `P05` focused web",
            "Excalidraw `web_editor` separation",
            "browser automation",
            "arbitrary third-party web UI registration",
        ),
        "AC-REQ-QA-048-01": (
            CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FOCUSED_WEB_COMMAND,
            CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_COMMAND,
            CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MARKDOWN_COMMAND,
            CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FAST_COMMAND,
            CHROMIUM_WEBSITE_HTML_VIEWER_NODE_REVIEW_GATE_COMMAND,
        ),
    },
}
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_ROW_TOKENS: dict[str, tuple[str, ...]] = {
    "REQ-UI-046": (
        "ContentFullscreenOverlay.qml",
        "WebPageHost.qml",
        "WebPageDetachedWindow.qml",
        "content_fullscreen_bridge.py",
        "P02_generic_web_surfaces_WRAPUP.md",
        "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
    ),
    "AC-REQ-UI-046-01": (
        "invalid-location denial",
        "WebEngine-unavailable fallback",
        "bridge-free separation from Excalidraw",
        "tests/test_corex_web_surface_bridge.py",
    ),
    "REQ-NODE-033": (
        "nodes/builtins/web_viewer.py",
        "surface_contracts.py",
        "tests/test_web_page_viewer_node.py",
        "P03_web_page_viewer_node_WRAPUP.md",
    ),
    "AC-REQ-NODE-033-01": (
        "passive-runtime exclusion",
        "serializer round-trip",
        "safe persisted browser-property proof",
        "tests/test_serializer.py",
    ),
    "REQ-INT-016": (
        "web_host/navigation_policy.py",
        "WebPageHost.qml",
        "tests/test_webengine_navigation_policy.py",
        "P01_webengine_foundation_and_policy_WRAPUP.md",
        "P04_offline_intranet_hardening_WRAPUP.md",
    ),
    "AC-REQ-INT-016-01": (
        "URL/local HTML normalization",
        "relative local asset loading",
        ".cxproj",
    ),
    "REQ-QA-048": (
        "docs/specs/INDEX.md",
        "docs/specs/perf/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
        "CHROMIUM_WEBSITE_HTML_VIEWER_NODE_STATUS.md",
        "P05_closeout_and_future_hooks_WRAPUP.md",
        "tests/test_markdown_hygiene.py",
    ),
    "AC-REQ-QA-048-01": (
        CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FOCUSED_WEB_COMMAND,
        CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_COMMAND,
        CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MARKDOWN_COMMAND,
        CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FAST_COMMAND,
        "docs/specs/perf/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.md",
    ),
}
CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX_TOKENS = (
    "Chromium Website HTML Viewer Node QA Matrix",
    "## Locked Scope",
    "`web.page_viewer`",
    '`content_kind="web_page"`',
    "WebPageHost.qml",
    "Excalidraw `web_editor`",
    "privileged QWebChannel graph/project bridge",
    "WebNavigationDecision",
    "persist_browser_state",
    "## Future Consumer Contract",
    "3fae0d141838eee7a4d625bbc92efb073203d531",
    "0b94a9a737333d24909b7775fcec7a40fab468ac",
    "7507cdc2278c2f395703bebc47f7149cbbffc8e3",
    "2239fc67c8c583a9e1605b8eede0c9af01e7d92b",
    CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FOCUSED_WEB_COMMAND,
    CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_COMMAND,
    CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MARKDOWN_COMMAND,
    CHROMIUM_WEBSITE_HTML_VIEWER_NODE_FAST_COMMAND,
    "Ready for manual testing",
    "arbitrary third-party web UI registration",
)


class TraceabilityCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_module("verification_manifest_for_traceability_tests", VERIFICATION_MANIFEST_PATH)
        cls.checker = load_module("check_traceability_for_tests", CHECKER_PATH)

    def test_checker_uses_manifest_owned_audit_catalogs(self) -> None:
        self.assertTrue(
            set(self.manifest.PROOF_AUDIT_REQUIRED_ARTIFACTS).issubset(self.checker.REQUIRED_ARTIFACTS)
        )
        self.assertIn(
            "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
            self.checker.REQUIRED_ARTIFACTS,
        )
        self.assertEqual((), self.checker.P08_REQUIRED_ARTIFACTS)
        manifest_rules = {
            path: (rule.required, rule.forbidden)
            for path, rule in self.manifest.GENERIC_DOCUMENT_RULES.items()
        }
        checker_rules = {
            path: (rule.required, rule.forbidden)
            for path, rule in self.checker.GENERIC_DOCUMENT_RULES.items()
        }
        self.assertEqual(manifest_rules, checker_rules)

    def test_corex_excalidraw_web_host_packaging_commands_are_manifest_owned(self) -> None:
        self.assertEqual(
            r".\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py "
            r"tests/test_traceability_checker.py tests/test_corex_web_host_assets.py --ignore=venv -q",
            self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_P06_VERIFICATION_COMMAND,
        )
        self.assertEqual(
            r".\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py "
            r'-k "web or webengine or asset" --ignore=venv -q',
            self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_P06_REVIEW_GATE_COMMAND,
        )
        self.assertIn(
            r".\scripts\build_windows_package.ps1 -PackageProfile web -Clean -SkipSmoke",
            self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_COMMANDS,
        )
        self.assertIn(
            r".\scripts\build_windows_installer.ps1 -PackageProfile web",
            self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_COMMANDS,
        )
        self.assertIn("ea_node_editor.spec", self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_ARTIFACTS)
        self.assertIn(
            "tests/test_corex_web_host_assets.py",
            self.manifest.COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_ARTIFACTS,
        )

    def test_corex_excalidraw_real_editor_closeout_commands_are_manifest_owned(self) -> None:
        self.assertEqual(
            COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
            self.manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
        )
        self.assertEqual(
            COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
            self.manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
        )
        self.assertEqual(
            COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
            self.manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
        )
        self.assertEqual(
            COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND,
            self.manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND,
        )
        self.assertIn(
            "docs/specs/work_packets/corex_excalidraw_real_editor/P05_packaging_and_static_asset_proof_WRAPUP.md",
            self.manifest.COREX_EXCALIDRAW_REAL_EDITOR_PACKET_WRAPUPS,
        )

    def test_corex_excalidraw_web_host_spec_index_registers_packet_set(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in COREX_EXCALIDRAW_WEB_HOST_LAYER_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_corex_excalidraw_web_host_requirements_record_locked_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in COREX_EXCALIDRAW_WEB_HOST_LAYER_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_corex_excalidraw_web_host_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in COREX_EXCALIDRAW_WEB_HOST_LAYER_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_corex_excalidraw_web_host_qa_matrix_records_commands_and_manual_checks(self) -> None:
        text = COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_chromium_website_html_viewer_node_spec_index_registers_packet_set(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in CHROMIUM_WEBSITE_HTML_VIEWER_NODE_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_chromium_website_html_viewer_node_requirements_record_locked_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in CHROMIUM_WEBSITE_HTML_VIEWER_NODE_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_chromium_website_html_viewer_node_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in CHROMIUM_WEBSITE_HTML_VIEWER_NODE_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_chromium_website_html_viewer_node_qa_matrix_records_commands_and_manual_checks(
        self,
    ) -> None:
        text = CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in CHROMIUM_WEBSITE_HTML_VIEWER_NODE_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_novice_plugin_sdk_traceability_and_pending_acceptance_matrix(self) -> None:
        traceability_path = REPO_ROOT / self.manifest.TRACEABILITY_MATRIX_DOC
        for row_id in (
            "REQ-UI-065",
            "AC-REQ-UI-065-01",
            "REQ-NODE-050",
            "AC-REQ-NODE-050-01",
            "REQ-NODE-051",
            "AC-REQ-NODE-051-01",
            "REQ-EXEC-028",
            "AC-REQ-EXEC-028-01",
            "REQ-PERSIST-031",
            "AC-REQ-PERSIST-031-01",
            "REQ-INT-021",
            "AC-REQ-INT-021-01",
            "REQ-QA-055",
            "AC-REQ-QA-055-01",
        ):
            row_text = traceability_row(traceability_path, row_id)
            for token in self.manifest.TRACEABILITY_ROW_REQUIRED_TOKENS[row_id]:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing {token!r}")

        matrix_path = REPO_ROOT / self.manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC
        text = matrix_path.read_text(encoding="utf-8-sig")
        for token in self.manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_REQUIRED_TOKENS:
            self.assertIn(token, text)
        for gate in self.manifest.COREX_NOVICE_PLUGIN_SDK_PASSED_GATES:
            self.assertRegex(
                text,
                rf"(?m)^\| {re.escape(gate)} \| .* \| `PASS` \|",
            )
        for gate in self.manifest.COREX_NOVICE_PLUGIN_SDK_TRANSITIONAL_GATES:
            self.assertRegex(
                text,
                rf"(?m)^\| {re.escape(gate)} \| .* \| `(?:PENDING / NOT RUN|PASS)` \|",
            )

    def make_repo_fixture(self, root: Path) -> None:
        required_paths = set(self.checker.REQUIRED_ARTIFACTS)
        required_paths.update(self.checker.P08_REQUIRED_ARTIFACTS)
        required_paths.update(self.checker.P10_REQUIREMENT_DOC_TOKENS.keys())
        required_paths.update(ADDON_MANAGER_BACKEND_PREPARATION_REQUIREMENT_TOKENS.keys())
        for relative_path in required_paths:
            source = REPO_ROOT / relative_path
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def test_audit_repository_passes_for_current_repo(self) -> None:
        self.assertEqual([], self.checker.audit_repository(REPO_ROOT))

    def test_planned_requirement_registry_matches_current_repo(self) -> None:
        self.assertEqual(19, len(self.manifest.PLANNED_REQUIREMENT_OWNERS))
        self.assertEqual(
            "PARTIAL",
            next(
                status
                for opportunity_id, _title, _requirements, status in self.manifest.CAPABILITY_GROUPS
                if opportunity_id == "SYN-OPP-0002"
            ),
        )
        self.assertEqual([], self.checker.audit_repository(REPO_ROOT))

    def test_incremental_solution_plan_is_registered_complete(self) -> None:
        plan = (
            REPO_ROOT
            / "docs/PLAN_COREX_INCREMENTAL_EXECUTION_AND_SOLUTION_SNAPSHOTS.md"
        ).read_text(encoding="utf-8")
        index = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8")
        self.assertIn("Status: **COMPLETED — T01–T09 ACCEPTED**", plan)
        self.assertIn(
            "[COREX Incremental Execution And Solution Snapshots]"
            "(../PLAN_COREX_INCREMENTAL_EXECUTION_AND_SOLUTION_SNAPSHOTS.md) — "
            "`COMPLETED — T01–T09 ACCEPTED`",
            index,
        )

    def test_audit_repository_reports_missing_planned_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)
            matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            lines = matrix.read_text(encoding="utf-8-sig").splitlines()
            matrix.write_text(
                "\n".join(line for line in lines if not line.startswith("| `REQ-ARCH-020` |"))
                + "\n",
                encoding="utf-8",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: missing planned row: REQ-ARCH-020",
            issues,
        )

    def test_audit_repository_reports_wrong_planned_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)
            matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            replace_text(
                matrix,
                "| `REQ-ARCH-020` | `AC-REQ-ARCH-020-01` | `10_ARCHITECTURE` |",
                "| `REQ-ARCH-020` | `AC-REQ-ARCH-020-01` | `20_UI_UX` |",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: planned row REQ-ARCH-020 has wrong owner",
            issues,
        )

    def test_audit_repository_reports_duplicate_requirement_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)
            ui_requirements = repo_root / "docs/specs/requirements/20_UI_UX.md"
            ui_requirements.write_text(
                ui_requirements.read_text(encoding="utf-8-sig")
                + "\n- `REQ-ARCH-020`: Duplicate definition for regression coverage.\n",
                encoding="utf-8",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertTrue(
            any("duplicate requirement definition: REQ-ARCH-020" in issue for issue in issues),
            issues,
        )

    def test_audit_repository_reports_non_exact_planned_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)
            matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            replace_text(
                matrix,
                "| `REQ-ARCH-020` | `AC-REQ-ARCH-020-01` | `10_ARCHITECTURE` | `PLANNED` |",
                "| `REQ-ARCH-020` | `AC-REQ-ARCH-020-01` | `10_ARCHITECTURE` | `PLANNING` |",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: planned row REQ-ARCH-020 "
            "has wrong Capability Status: PLANNING",
            issues,
        )

    def test_audit_repository_rejects_planned_implementation_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)
            matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            lines = matrix.read_text(encoding="utf-8-sig").splitlines()
            for index, line in enumerate(lines):
                if line.startswith("| `REQ-ARCH-020` |"):
                    lines[index] = line.replace(
                        "`NO IMPLEMENTATION PROOF`",
                        "`tests/test_fake_implementation.py`",
                    )
                    break
            matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: planned row REQ-ARCH-020 "
            "has wrong Implementation Proof: tests/test_fake_implementation.py",
            issues,
        )

    def test_audit_repository_reports_missing_required_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            (repo_root / self.manifest.GRAPH_CANVAS_PERF_MATRIX_DOC).unlink()

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"Missing required artifact: {self.manifest.GRAPH_CANVAS_PERF_MATRIX_DOC}",
            issues,
        )

    def test_audit_repository_reports_structured_perf_and_row_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            graph_canvas_doc = repo_root / self.manifest.GRAPH_CANVAS_PERF_MATRIX_DOC
            update_markdown_table_result(
                graph_canvas_doc,
                self.manifest.proof_audit_command(),
                "Pending",
                "Proof audit was not rerun",
            )
            replace_text(graph_canvas_doc, "Status: `PASS`", "Status: `PENDING`")

            track_h_doc = repo_root / self.manifest.TRACK_H_BENCHMARK_REPORT_DOC
            replace_text(track_h_doc, "Scenario: `heavy_media`", "Scenario: `synthetic_exec`")
            replace_text(
                track_h_doc,
                "artifacts/graph_canvas_perf_docs/track_h_benchmark_report.json",
                "artifacts/graph_canvas_perf_docs/report.json",
            )
            replace_text(
                track_h_doc,
                "artifacts/graph_canvas_interaction_perf_p09_desktop_reference/track_h_benchmark_report.json",
                "artifacts/graph_canvas_interaction_perf_p09_desktop_reference/report.json",
            )

            traceability_matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            remove_token_from_traceability_row(
                traceability_matrix,
                "AC-REQ-QA-018-01",
                "artifacts/graph_canvas_perf_docs/track_h_benchmark_report.json",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            f"{self.manifest.GRAPH_CANVAS_PERF_MATRIX_DOC}: 2026-03-21 Execution Results command "
            f"{self.manifest.proof_audit_command()} has unexpected result: Pending",
            issues,
        )
        self.assertIn(
            f"{self.manifest.GRAPH_CANVAS_PERF_MATRIX_DOC}: graph-canvas perf matrix missing fact: "
            "Status: `PASS`",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACK_H_BENCHMARK_REPORT_DOC}: track-h benchmark report missing fact: "
            "Scenario: `heavy_media`",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACK_H_BENCHMARK_REPORT_DOC}: track-h benchmark report missing fact: "
            f"{self.checker.GRAPH_CANVAS_CANONICAL_REPORT_JSON}",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACK_H_BENCHMARK_REPORT_DOC}: track-h benchmark report missing fact: "
            "artifacts/graph_canvas_interaction_perf_p09_desktop_reference/track_h_benchmark_report.json",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: row AC-REQ-QA-018-01 missing implementation "
            "artifact text: artifacts/graph_canvas_perf_docs/track_h_benchmark_report.json",
            issues,
        )

    def test_audit_repository_reports_graphics_and_performance_requirement_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            remove_token_from_requirement_line(
                repo_root / "docs/specs/requirements/20_UI_UX.md",
                "REQ-UI-016",
                "Graphics Settings",
            )
            remove_token_from_requirement_line(
                repo_root / "docs/specs/requirements/40_NODE_SDK.md",
                "REQ-NODE-016",
                "render_quality",
            )
            remove_token_from_requirement_line(
                repo_root / "docs/specs/requirements/60_PERSISTENCE.md",
                "REQ-PERSIST-011",
                "passive node library display mode",
            )
            remove_token_from_requirement_line(
                repo_root / self.manifest.QA_ACCEPTANCE_DOC,
                "REQ-QA-018",
                "scenario",
            )

            traceability_matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            remove_token_from_traceability_row(
                traceability_matrix,
                "REQ-UI-016",
                "graphics_settings_dialog.py",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            "docs/specs/requirements/20_UI_UX.md: requirement REQ-UI-016 missing fact: "
            "Graphics Settings",
            issues,
        )
        self.assertIn(
            "docs/specs/requirements/40_NODE_SDK.md: requirement REQ-NODE-016 missing fact: "
            "render_quality",
            issues,
        )
        self.assertIn(
            "docs/specs/requirements/60_PERSISTENCE.md: requirement REQ-PERSIST-011 missing fact: "
            "passive node library display mode",
            issues,
        )
        self.assertIn(
            f"{self.manifest.QA_ACCEPTANCE_DOC}: requirement REQ-QA-018 missing fact: scenario",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: row REQ-UI-016 missing implementation "
            "artifact text: graphics_settings_dialog.py",
            issues,
        )

    def test_audit_repository_reports_shell_phase_doc_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            readme_path = repo_root / "README.md"
            replace_text(
                readme_path,
                "dedicated fresh-process shell-isolation phase",
                "shell-wrapper suites for isolated `unittest` execution",
            )

            qa_path = repo_root / self.manifest.QA_ACCEPTANCE_DOC
            replace_text(
                qa_path,
                self.manifest.SHELL_ISOLATION_SPEC.test_path,
                "tests/test_shell_wrapper_phase.py",
            )
            qa_path.write_text(
                qa_path.read_text(encoding="utf-8-sig")
                + "\n"
                + "`REQ-QA-015`: the four shell-wrapper modules `tests.test_main_window_shell`, "
                + "`tests.test_script_editor_dock`, `tests.test_shell_run_controller`, and "
                + "`tests.test_shell_project_session_controller` shall remain on explicit "
                + "fresh-process `unittest` execution inside the documented `full` workflow rather "
                + "than the pytest phases.\n",
                encoding="utf-8",
            )

            verification_matrix = repo_root / self.manifest.VERIFICATION_SPEED_MATRIX_DOC
            replace_text(
                verification_matrix,
                "`54 passed in 831.67s`",
                "831.67 seconds",
            )
            verification_matrix.write_text(
                verification_matrix.read_text(encoding="utf-8-sig")
                + "\nadds `-n auto` only when `pytest-xdist` is importable in the project venv\n",
                encoding="utf-8",
            )

            traceability_matrix = repo_root / self.manifest.TRACEABILITY_MATRIX_DOC
            remove_token_from_traceability_row(
                traceability_matrix,
                "REQ-QA-015",
                self.manifest.SHELL_ISOLATION_SPEC.test_path,
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            "README.md: missing required text: dedicated fresh-process shell-isolation phase",
            issues,
        )
        self.assertIn(
            "README.md: found stale text: shell-wrapper suites for isolated `unittest` execution",
            issues,
        )
        self.assertIn(
            f"{self.manifest.QA_ACCEPTANCE_DOC}: found stale text: the four shell-wrapper modules "
            "`tests.test_main_window_shell`, `tests.test_script_editor_dock`, "
            "`tests.test_shell_run_controller`, and `tests.test_shell_project_session_controller` "
            "shall remain on explicit fresh-process `unittest` execution",
            issues,
        )
        self.assertIn(
            f"{self.manifest.QA_ACCEPTANCE_DOC}: requirement REQ-QA-015 missing fact: {self.manifest.SHELL_ISOLATION_SPEC.test_path}",
            issues,
        )
        self.assertIn(
            f"{self.manifest.VERIFICATION_SPEED_MATRIX_DOC}: dedicated shell-isolation benchmark result is not a pytest timing summary: 831.67 seconds",
            issues,
        )
        self.assertIn(
            f"{self.manifest.VERIFICATION_SPEED_MATRIX_DOC}: found stale text: adds `-n auto` only when `pytest-xdist` is importable in the project venv",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: row REQ-QA-015 missing implementation "
            f"artifact text: {self.manifest.SHELL_ISOLATION_SPEC.test_path}",
            issues,
        )

    def test_audit_repository_reports_release_doc_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            replace_text(
                repo_root / "README.md",
                "scripts/check_markdown_links.py",
                "scripts/check_docs.py",
            )
            replace_text(
                repo_root / "docs/specs/INDEX.md",
                "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
                "ARCHITECTURE_MAINTAINABILITY_REFACTOR_MATRIX.md",
            )
            update_markdown_table_result(
                repo_root / "docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
                ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND,
                "Pending",
                "Markdown links were not rerun after the doc refresh",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            "README.md: missing required text: scripts/check_markdown_links.py",
            issues,
        )
        self.assertIn(
            "docs/specs/INDEX.md: missing required text: ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
            issues,
        )
        self.assertIn(
            "docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md: "
            "2026-03-28 Execution Results command "
            f"{ARCHITECTURE_MAINTAINABILITY_REFACTOR_MARKDOWN_COMMAND} has unexpected result: Pending",
            issues,
        )

    def test_audit_repository_reports_ui_context_closeout_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            self.make_repo_fixture(repo_root)

            replace_text(
                repo_root / "docs/specs/INDEX.md",
                "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
                "UI_CONTEXT_SCALABILITY_REFACTOR_MATRIX.md",
            )
            remove_token_from_requirement_line(
                repo_root / self.manifest.QA_ACCEPTANCE_DOC,
                "REQ-QA-030",
                "CONTEXT_BUDGET_RULES.json",
            )
            update_markdown_table_result(
                repo_root / "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
                UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND,
                "Pending",
                "Markdown links were not rerun after the UI closeout refresh",
            )
            remove_token_from_traceability_row(
                repo_root / self.manifest.TRACEABILITY_MATRIX_DOC,
                "REQ-QA-030",
                "tests/test_run_verification.py",
            )

            issues = self.checker.audit_repository(repo_root)

        self.assertIn(
            "docs/specs/INDEX.md: spec index registration missing fact: "
            "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
            issues,
        )
        self.assertIn(
            f"{self.manifest.QA_ACCEPTANCE_DOC}: requirement REQ-QA-030 missing fact: "
            "CONTEXT_BUDGET_RULES.json",
            issues,
        )
        self.assertIn(
            "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md: "
            "2026-04-05 Execution Results command "
            f"{UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND} has unexpected result: Pending",
            issues,
        )
        self.assertIn(
            f"{self.manifest.TRACEABILITY_MATRIX_DOC}: row REQ-QA-030 missing implementation "
            "artifact text: tests/test_run_verification.py",
            issues,
        )


    def test_project_managed_files_docs_record_final_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in PROJECT_MANAGED_FILES_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_project_managed_files_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in PROJECT_MANAGED_FILES_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_project_managed_files_qa_matrix_records_final_commands_and_deferrals(self) -> None:
        text = PROJECT_MANAGED_FILES_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in PROJECT_MANAGED_FILES_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_cross_process_viewer_backend_framework_docs_record_closeout_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_cross_process_viewer_backend_framework_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_cross_process_viewer_backend_framework_qa_matrix_records_commands_and_manual_checks(
        self,
    ) -> None:
        text = CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in CROSS_PROCESS_VIEWER_BACKEND_FRAMEWORK_QA_MATRIX_TOKENS:
            self.assertIn(token, text)








    def test_addon_manager_backend_preparation_spec_index_registers_packet_set(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in ADDON_MANAGER_BACKEND_PREPARATION_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_addon_manager_backend_preparation_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, tokens in ADDON_MANAGER_BACKEND_PREPARATION_PUBLIC_DOC_TOKENS.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for token in tokens:
                self.assertIn(token, text, msg=f"{relative_path} missing token {token!r}")

        for (
            relative_path,
            requirement_tokens,
        ) in ADDON_MANAGER_BACKEND_PREPARATION_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(
                        token,
                        body,
                        msg=f"{relative_path} {requirement_id} missing token {token!r}",
                    )

    def test_addon_manager_backend_preparation_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_addon_manager_backend_preparation_qa_matrix_records_commands_and_manual_checks(
        self,
    ) -> None:
        text = ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

        issues: list[str] = []
        verification_rows = self.checker.table_after_heading(
            text,
            relative_path="docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
            heading="Current Automated Verification",
            issues=issues,
        )
        self.assertEqual([], issues)
        self.assertIsNotNone(verification_rows)
        assert verification_rows is not None
        for command in self.checker.ADDON_MANAGER_BACKEND_PREPARATION_VERIFICATION_COMMANDS:
            row = self.checker.find_row(
                verification_rows,
                column="Command",
                predicate=lambda value, command=command: self.checker.strip_code_fence(value)
                == command,
            )
            self.assertIsNotNone(row, command)
            assert row is not None
            self.assertIn(self.checker.strip_code_fence(row["Status"]), {"PASS", "FAIL", "NOT RUN"})

        for heading, result_column in (
            ("Final Closeout Commands", None),
            ("2026-09-07 Execution Results", "Result"),
        ):
            issues = []
            rows = self.checker.table_after_heading(
                text,
                relative_path="docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
                heading=heading,
                issues=issues,
            )
            self.assertEqual([], issues)
            self.assertIsNotNone(rows)
            assert rows is not None
            for command in self.checker.ADDON_MANAGER_BACKEND_PREPARATION_AUDIT_COMMANDS:
                row = self.checker.find_row(
                    rows,
                    column="Command",
                    predicate=lambda value, command=command: self.checker.strip_code_fence(value)
                    == command,
                )
                self.assertIsNotNone(row, f"{heading}: {command}")
                if row is not None and result_column is not None:
                    self.assertEqual("PASS", self.checker.strip_code_fence(row[result_column]))

    def test_corex_no_legacy_architecture_cleanup_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_corex_no_legacy_architecture_cleanup_docs_record_final_scope_tokens(self) -> None:
        for relative_path, tokens in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PUBLIC_DOC_TOKENS.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for token in tokens:
                self.assertIn(token, text, msg=f"{relative_path} missing token {token!r}")

        for relative_path, requirement_tokens in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_corex_no_legacy_architecture_cleanup_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")
            for token in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_ROW_FORBIDDEN_TOKENS.get(row_id, ()):
                self.assertNotIn(token, row_text, msg=f"traceability row {row_id} has stale token {token!r}")

    def test_corex_no_legacy_architecture_cleanup_qa_matrix_records_commands_and_manual_checks(
        self,
    ) -> None:
        text = COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_corex_clean_architecture_restructure_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_corex_clean_architecture_restructure_public_docs_record_closeout_scope_tokens(
        self,
    ) -> None:
        for relative_path, tokens in COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_PUBLIC_DOC_TOKENS.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for token in tokens:
                self.assertIn(token, text, msg=f"{relative_path} missing token {token!r}")

    def test_corex_clean_architecture_restructure_qa_matrix_records_commands_and_artifacts(
        self,
    ) -> None:
        text = COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in COREX_CLEAN_ARCHITECTURE_RESTRUCTURE_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_corex_architecture_modernization_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in COREX_ARCHITECTURE_MODERNIZATION_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_corex_architecture_modernization_public_docs_record_closeout_scope_tokens(
        self,
    ) -> None:
        for relative_path, tokens in COREX_ARCHITECTURE_MODERNIZATION_PUBLIC_DOC_TOKENS.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for token in tokens:
                self.assertIn(token, text, msg=f"{relative_path} missing token {token!r}")

        for relative_path, requirement_tokens in COREX_ARCHITECTURE_MODERNIZATION_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_corex_architecture_modernization_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_corex_architecture_modernization_qa_matrix_records_commands_and_artifacts(
        self,
    ) -> None:
        text = COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_global_gap_break_edge_crossing_variant_docs_record_closeout_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_global_gap_break_edge_crossing_variant_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_global_gap_break_edge_crossing_variant_qa_matrix_records_commands_and_manual_checks(self) -> None:
        text = GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in GLOBAL_GAP_BREAK_EDGE_CROSSING_VARIANT_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_node_execution_visualization_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in NODE_EXECUTION_VISUALIZATION_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_node_execution_visualization_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in NODE_EXECUTION_VISUALIZATION_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_node_execution_visualization_qa_matrix_records_node_only_contract(self) -> None:
        text = NODE_EXECUTION_VISUALIZATION_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in NODE_EXECUTION_VISUALIZATION_QA_MATRIX_TOKENS:
            self.assertIn(token, text)
        for token in NODE_EXECUTION_VISUALIZATION_QA_MATRIX_FORBIDDEN_TOKENS:
            self.assertNotIn(token, text)

    def test_nested_node_categories_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in NESTED_NODE_CATEGORIES_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_nested_node_categories_public_docs_record_authoring_change(self) -> None:
        for relative_path, tokens in NESTED_NODE_CATEGORIES_PUBLIC_DOC_TOKENS.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for token in tokens:
                self.assertIn(token, text, msg=f"{relative_path} missing token {token!r}")

    def test_nested_node_categories_requirements_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in NESTED_NODE_CATEGORIES_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_nested_node_categories_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in NESTED_NODE_CATEGORIES_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_nested_node_categories_qa_matrix_records_commands_and_manual_checks(self) -> None:
        text = NESTED_NODE_CATEGORIES_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in NESTED_NODE_CATEGORIES_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_shared_graph_typography_control_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in SHARED_GRAPH_TYPOGRAPHY_CONTROL_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_shared_graph_typography_control_docs_record_closeout_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in SHARED_GRAPH_TYPOGRAPHY_CONTROL_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_shared_graph_typography_control_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in SHARED_GRAPH_TYPOGRAPHY_CONTROL_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_shared_graph_typography_control_qa_matrix_records_commands_and_manual_checks(self) -> None:
        text = SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in SHARED_GRAPH_TYPOGRAPHY_CONTROL_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_default_value_grips_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in DEFAULT_VALUE_GRIPS_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_default_value_grips_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in DEFAULT_VALUE_GRIPS_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_default_value_grips_traceability_rows_reference_proof(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in DEFAULT_VALUE_GRIPS_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_default_value_grips_qa_matrix_records_commands_and_manual_checks(self) -> None:
        text = DEFAULT_VALUE_GRIPS_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in DEFAULT_VALUE_GRIPS_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_title_icons_for_non_passive_nodes_spec_index_registers_qa_matrix(self) -> None:
        text = (REPO_ROOT / "docs/specs/INDEX.md").read_text(encoding="utf-8-sig")
        for token in TITLE_ICONS_FOR_NON_PASSIVE_NODES_INDEX_TOKENS:
            self.assertIn(token, text)

    def test_title_icons_for_non_passive_nodes_docs_record_closeout_scope_tokens(self) -> None:
        for (
            relative_path,
            requirement_tokens,
        ) in TITLE_ICONS_FOR_NON_PASSIVE_NODES_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_title_icons_for_non_passive_nodes_traceability_rows_reference_packet_artifacts(
        self,
    ) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in TITLE_ICONS_FOR_NON_PASSIVE_NODES_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_title_icons_for_non_passive_nodes_qa_matrix_records_commands_and_manual_checks(
        self,
    ) -> None:
        text = TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in TITLE_ICONS_FOR_NON_PASSIVE_NODES_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_architecture_maintainability_refactor_docs_record_final_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in ARCHITECTURE_MAINTAINABILITY_REFACTOR_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_architecture_maintainability_refactor_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in ARCHITECTURE_MAINTAINABILITY_REFACTOR_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_architecture_maintainability_refactor_qa_matrix_records_commands_and_boundaries(self) -> None:
        text = ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_architecture_residual_refactor_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in ARCHITECTURE_RESIDUAL_REFACTOR_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_architecture_residual_refactor_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_architecture_residual_refactor_qa_matrix_records_commands_and_boundaries(self) -> None:
        text = ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_ui_context_scalability_refactor_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in UI_CONTEXT_SCALABILITY_REFACTOR_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_ui_context_scalability_refactor_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_ui_context_scalability_refactor_qa_matrix_records_commands_and_guardrails(self) -> None:
        text = UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_ui_context_scalability_followup_docs_record_closeout_scope_tokens(self) -> None:
        for relative_path, requirement_tokens in UI_CONTEXT_SCALABILITY_FOLLOWUP_REQUIREMENT_TOKENS.items():
            path = REPO_ROOT / relative_path
            for requirement_id, tokens in requirement_tokens.items():
                body = requirement_line(path, requirement_id)
                for token in tokens:
                    self.assertIn(token, body, msg=f"{relative_path} {requirement_id} missing token {token!r}")

    def test_ui_context_scalability_followup_traceability_rows_reference_packet_artifacts(self) -> None:
        traceability_path = REPO_ROOT / "docs/specs/requirements/TRACEABILITY_MATRIX.md"
        for row_id, tokens in UI_CONTEXT_SCALABILITY_FOLLOWUP_TRACEABILITY_ROW_TOKENS.items():
            row_text = traceability_row(traceability_path, row_id)
            for token in tokens:
                self.assertIn(token, row_text, msg=f"traceability row {row_id} missing token {token!r}")

    def test_ui_context_scalability_followup_qa_matrix_records_commands_and_guardrails(self) -> None:
        text = UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX.read_text(encoding="utf-8-sig")
        for token in UI_CONTEXT_SCALABILITY_FOLLOWUP_QA_MATRIX_TOKENS:
            self.assertIn(token, text)

    def test_current_execution_architecture_rejects_retired_program_a_terms(self) -> None:
        current_execution_docs = (
            "ARCHITECTURE.md",
            "docs/architecture_diagrams/component_map.mmd",
            "docs/architecture_diagrams/runtime_pipeline.mmd",
            "docs/architecture_diagrams/run_sequence.mmd",
            "docs/specs/requirements/50_EXECUTION_ENGINE.md",
            "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        )
        retired_terms = (
            "execution/protocol.py",
            "execution/{protocol.py",
            "execution/client.py",
            "execution/{client.py",
            "execution/headless_runtime.py",
            "execution/{headless_runtime.py",
            "node_completed",
            "RunController.handle_execution_event",
            "Run events and logs stream to RunController",
            "AGREEMENT --> EXEC[ProcessExecutionClient]",
            "participant EC as ProcessExecutionClient",
            "EC->>RC: event callback",
            "W->>EC: node_started / node_completed / log",
            "REC->>RPC: append error log and update notifications",
        )
        for relative_path in current_execution_docs:
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for term in retired_terms:
                self.assertNotIn(term, text, msg=f"{relative_path} retains retired current-route term {term!r}")

        required_current_terms = {
            "ARCHITECTURE.md": (
                "CorexRuntime",
                "ExecutionBackendClient",
                "RunEventController",
                "RunProjectionController",
                "ViewerSessionBridge direct consumer",
            ),
            "docs/architecture_diagrams/component_map.mmd": (
                "CorexRuntime",
                "ExecutionBackendClient",
                "RunEventController",
                "RunProjectionController",
                "ViewerSessionBridge direct consumer",
            ),
            "docs/architecture_diagrams/runtime_pipeline.mmd": (
                "CorexRuntime",
                "ExecutionBackendClient",
                "RunEventController",
                "RunProjectionController",
                "ViewerSessionBridge consumes the event directly",
            ),
            "docs/architecture_diagrams/run_sequence.mmd": (
                "participant CR as CorexRuntime",
                "participant BC as ExecutionBackendClient",
                "participant REC as RunEventController",
                "participant RPC as RunProjectionController",
                "REC->>VS: direct viewer delivery",
            ),
            "docs/specs/requirements/50_EXECUTION_ENGINE.md": (
                "`CorexRuntime`",
                "`ExecutionBackendClient`",
                "`RunEventController`",
                "`RunProjectionController`",
                "one direct viewer-event delivery",
            ),
            "docs/specs/requirements/TRACEABILITY_MATRIX.md": (
                "execution/{runtime.py,client_common.py,backend_client.py}",
                "ui/shell/controllers/{run_event_controller.py,run_projection_controller.py}",
                "ui_qml/viewer_session_bridge.py",
            ),
        }
        for relative_path, terms in required_current_terms.items():
            text = (REPO_ROOT / relative_path).read_text(encoding="utf-8-sig")
            for term in terms:
                self.assertIn(term, text, msg=f"{relative_path} missing current-route term {term!r}")


if __name__ == "__main__":
    unittest.main()
