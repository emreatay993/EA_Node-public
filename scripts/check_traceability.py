#!/usr/bin/env python3
"""Validate the packet-owned verification traceability layer."""

from __future__ import annotations

from pathlib import Path
import re
import sys

try:
    import verification_manifest as manifest
except ModuleNotFoundError:
    import scripts.verification_manifest as manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_REQUIRED_ARTIFACTS = manifest.PROOF_AUDIT_REQUIRED_ARTIFACTS
GENERIC_DOCUMENT_RULES = manifest.GENERIC_DOCUMENT_RULES
OLD_SHELL_TAIL_RESULT_PATTERN = re.compile(r"^`\d+\.\d+s` mean across `\d+` reps$")
SHELL_ISOLATION_RESULT_PATTERN = re.compile(r"^`\d+ passed in \d+\.\d+s`$")

P10_TRACEABILITY_TEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q"
)
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC
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
UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_DOC = (
    "docs/specs/perf/UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md"
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
ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_DOC = (
    "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md"
)
ADDON_MANAGER_BACKEND_PREPARATION_CATALOG_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_addon_catalog.py "
    r"tests/test_addon_state_changes.py tests/test_tabular_addon_catalog.py "
    r"tests/test_mars_nodes.py --ignore=venv -q"
)
ADDON_MANAGER_BACKEND_PREPARATION_REGISTRY_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_registry_replacement.py "
    r"tests/test_addon_manager_install.py --ignore=venv -q"
)
ADDON_MANAGER_BACKEND_PREPARATION_SURFACE_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_serializer.py "
    r"tests/test_registry_validation.py tests/test_graph_surface_input_contract.py "
    r"tests/test_passive_graph_surface_host.py --ignore=venv -q"
)
ADDON_MANAGER_BACKEND_PREPARATION_SHELL_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_main_window_shell.py "
    r"tests/main_window_shell/shell_basics_and_search.py "
    r"tests/main_window_shell/bridge_qml_boundaries.py --ignore=venv -q"
)
ADDON_MANAGER_BACKEND_PREPARATION_VERIFICATION_COMMANDS = (
    ADDON_MANAGER_BACKEND_PREPARATION_CATALOG_COMMAND,
    ADDON_MANAGER_BACKEND_PREPARATION_REGISTRY_COMMAND,
    ADDON_MANAGER_BACKEND_PREPARATION_SURFACE_COMMAND,
    ADDON_MANAGER_BACKEND_PREPARATION_SHELL_COMMAND,
)
ADDON_MANAGER_BACKEND_PREPARATION_CLOSEOUT_PYTEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py "
    "tests/test_markdown_hygiene.py --ignore=venv -q"
)
ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
ADDON_MANAGER_BACKEND_PREPARATION_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)
ADDON_MANAGER_BACKEND_PREPARATION_AUDIT_COMMANDS = (
    ADDON_MANAGER_BACKEND_PREPARATION_CLOSEOUT_PYTEST_COMMAND,
    ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_COMMAND,
    ADDON_MANAGER_BACKEND_PREPARATION_MARKDOWN_COMMAND,
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC = (
    manifest.COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC
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
COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_DOC = (
    "docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md"
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
COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC = (
    manifest.COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND = (
    manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND = (
    manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND = (
    manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND
)
COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND = (
    manifest.COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND
)
# Work-packet manifests, status ledgers, and wrap-up docs under
# docs/specs/work_packets/ were pruned in commit 0b426a31 and are recorded only
# in git history; existence checks below cover retained artifacts only, while
# path-text tokens in retained docs stay frozen as historical evidence.
REQUIRED_ARTIFACTS = (
    *BASE_REQUIRED_ARTIFACTS,
    *manifest.REQUIREMENT_DEFINITION_DOCS,
    UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_DOC,
    manifest.ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
    ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_DOC,
    COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_DOC,
    COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC,
)
P08_REQUIRED_ARTIFACTS: tuple[str, ...] = ()
GRAPH_CANVAS_CANONICAL_REPORT_DIR = manifest.GRAPH_CANVAS_REPORT_DIR
GRAPH_CANVAS_CANONICAL_REPORT_MD = manifest.TRACK_H_BENCHMARK_ARTIFACT
GRAPH_CANVAS_CANONICAL_REPORT_JSON = (
    f"{GRAPH_CANVAS_CANONICAL_REPORT_DIR}/track_h_benchmark_report.json"
)
P09_DESKTOP_REFERENCE_REPORT_MD = (
    "artifacts/graph_canvas_interaction_perf_p09_desktop_reference/TRACK_H_BENCHMARK_REPORT.md"
)
P09_DESKTOP_REFERENCE_REPORT_JSON = (
    "artifacts/graph_canvas_interaction_perf_p09_desktop_reference/track_h_benchmark_report.json"
)
GRAPH_CANVAS_OFFSCREEN_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe "
    "-m ea_node_editor.ui.perf.performance_harness "
    "--nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 "
    "--baseline-runs 3 --scenario heavy_media "
    f"--report-dir {GRAPH_CANVAS_CANONICAL_REPORT_DIR}"
)
GRAPH_CANVAS_INTERACTIVE_COMMAND = (
    "./venv/Scripts/python.exe "
    "-m ea_node_editor.ui.perf.performance_harness "
    "--nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 "
    "--baseline-runs 3 --baseline-mode interactive --baseline-tag desktop_reference "
    "--scenario heavy_media --qt-platform windows "
    "--report-dir artifacts/graph_canvas_interaction_perf_p09_desktop_reference"
)

P10_REQUIREMENT_DOC_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-016": ("Graphics Settings", "grid", "shell-theme", "graph-theme"),
        "AC-REQ-UI-016-01": ("snap-to-grid", "shell-theme", "graph-theme"),
        "REQ-UI-041": (
            "Add-On Manager",
            "Variant 4 inspector-style right drawer",
            "focus_addon_id",
            "`About` / `Dependencies` / `Nodes` / `Changelog`",
        ),
        "REQ-UI-042": (
            "locked Mockup B placeholders",
            "`LOCKED` badge",
            "`Load missing add-ons`",
            "drag, and resize mutations",
        ),
        "AC-REQ-UI-041-01": (
            "main-window shell",
            "Variant 4 drawer fidelity",
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-UI-042-01": (
            "locked placeholders",
            "blocked mutation gestures",
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-016": (
            "render_quality",
            "supported_quality_tiers",
            "safe defaults",
        ),
        "AC-REQ-NODE-016-01": ("render_quality", "graph-surface payload", "safe defaults"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-011": ("passive node library display mode", "user_data_dir()", "last_session.json"),
        "AC-REQ-PERSIST-011-01": ("unrelated sibling settings", "last_session.json"),
        "REQ-PERSIST-023": (
            "pending-restart intent",
            "locked unavailable-add-on projections",
            "rebind them when the add-on returns",
            "projection payloads",
        ),
        "AC-REQ-PERSIST-023-01": (
            "plugin-loader",
            "locked projection",
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
    },
    "docs/specs/requirements/80_PERFORMANCE.md": {
        "AC-REQ-PERF-002-01": (
            "scenario",
            "media_surface_count",
            "GraphCanvas.qml",
        ),
        "AC-REQ-PERF-002-02": (
            "--baseline-runs 3 --scenario heavy_media",
            GRAPH_CANVAS_CANONICAL_REPORT_DIR,
            "desktop/manual exit-gate status",
            "desktop_reference",
        ),
        "AC-REQ-PERF-003-01": (
            GRAPH_CANVAS_CANONICAL_REPORT_DIR,
            "3-run heavy-media benchmark workflow",
        ),
    },
}
P10_REQUIREMENT_DOC_TOKENS.update(
    {
        "docs/specs/requirements/20_UI_UX.md": {
            **P10_REQUIREMENT_DOC_TOKENS["docs/specs/requirements/20_UI_UX.md"],
            "REQ-UI-044": (
                "real local/offline Excalidraw editor",
                "managed image imports",
                "artifact-backed previews",
                "no external browser launch",
            ),
            "AC-REQ-UI-044-01": (
                "managed image import",
                "artifact-backed preview",
                "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
            ),
        },
        "docs/specs/requirements/40_NODE_SDK.md": {
            **P10_REQUIREMENT_DOC_TOKENS["docs/specs/requirements/40_NODE_SDK.md"],
            "REQ-NODE-030": (
                "excalidraw.board",
                "excalidraw_state",
                "excalidraw_preview_ref",
                "excalidraw_state.files[*].artifact_ref",
                "arbitrary third-party web UI registration",
            ),
            "AC-REQ-NODE-030-01": (
                "managed image imports",
                "artifact refs",
                "execution snapshots",
            ),
        },
        "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
            "REQ-NODE-031": (
                "execution-free",
                "managed image import",
                "preview export",
                "worker execution path",
            ),
            "AC-REQ-NODE-031-01": (
                "real local/offline web editor",
                "no execution-worker WebEngine behavior",
                "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
            ),
        },
        "docs/specs/requirements/60_PERSISTENCE.md": {
            **P10_REQUIREMENT_DOC_TOKENS["docs/specs/requirements/60_PERSISTENCE.md"],
            "REQ-PERSIST-024": (
                "excalidraw_state.files[*].artifact_ref",
                "excalidraw_preview_ref",
                "data:image",
                "Save As",
            ),
            "AC-REQ-PERSIST-024-01": (
                "managed imported images",
                "artifact refs",
                "embedded `data:image` payloads",
                "fullscreen/WebEngine state stays transient",
            ),
        },
        "docs/specs/requirements/70_INTEGRATIONS.md": {
            "REQ-INT-014": (
                "real editor layer",
                "@excalidraw/excalidraw@0.18.1",
                "managed image imports",
                "artifact-backed previews",
                "external browsers",
                "remote rooms",
                "collaboration services",
                "execution-worker web semantics",
            ),
            "AC-REQ-INT-014-01": (
                "local/offline real editor asset loading",
                "managed image import",
                "preview artifact behavior",
                "execution-worker WebEngine",
                "arbitrary plugin web UI expansion",
            ),
        },
    }
)

P10_QA_ACCEPTANCE_REQUIREMENT_TOKENS = {
    "REQ-QA-009": ("graphics-settings", "theme", "canvas preference behavior"),
    "REQ-QA-011": ("supported quality-tier metadata", "passive-node"),
    "REQ-QA-018": (
        "scenario",
        "canonical artifact path",
        "desktop/manual exit-gate status",
    ),
    "AC-REQ-QA-018-01": (
        GRAPH_CANVAS_OFFSCREEN_COMMAND,
        manifest.proof_audit_command(),
        manifest.GRAPH_CANVAS_PERF_MATRIX_DOC,
        manifest.TRACK_H_BENCHMARK_REPORT_DOC,
        GRAPH_CANVAS_CANONICAL_REPORT_MD,
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
        P09_DESKTOP_REFERENCE_REPORT_MD,
    ),
}
QA_ACCEPTANCE_REQUIREMENT_TOKENS = dict(manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS)
QA_ACCEPTANCE_REQUIREMENT_TOKENS.update(P10_QA_ACCEPTANCE_REQUIREMENT_TOKENS)
QA_ACCEPTANCE_REQUIREMENT_TOKENS.update(
    {
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
        "REQ-QA-040": (
            "ADDON_MANAGER_BACKEND_PREPARATION",
            "generic add-on contract and persisted state model",
            "Mockup B locked-node behavior",
            "Variant 4 manager surface",
            "marketplace",
        ),
        "REQ-QA-041": (
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
            "Tabular",
            "MARS",
            "menu open/toggle/projection flows",
            "disabled update/install/restart actions",
        ),
        "AC-REQ-QA-040-01": (
            "tests/test_addon_catalog.py",
            "tests/test_engineering_viewer_widget_binder.py",
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-QA-041-01": (
            ADDON_MANAGER_BACKEND_PREPARATION_CLOSEOUT_PYTEST_COMMAND,
            ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_COMMAND,
            ADDON_MANAGER_BACKEND_PREPARATION_MARKDOWN_COMMAND,
            "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-QA-042": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["REQ-QA-042"],
        "AC-REQ-QA-042-01": manifest.QA_ACCEPTANCE_REQUIREMENT_TOKENS["AC-REQ-QA-042-01"],
        "REQ-QA-046": (
            "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
            "`P00` through `P12`",
            "headless Corex kernel",
            "QML shell client",
            "strict current `.cxproj`",
            "explicit extension contracts",
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
    }
)
QA_ACCEPTANCE_REQUIREMENT_TOKENS.update(
    {
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
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
    }
)
QA_ACCEPTANCE_CURRENT_CLOSEOUT_EVIDENCE_TOKENS = (
    COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_DOC,
    COREX_ARCHITECTURE_MODERNIZATION_WRAPUP_DOC,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC,
    *manifest.ARCHITECTURE_RESIDUAL_REFACTOR_CURRENT_EVIDENCE_TOKENS,
    UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_DOC,
    ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_DOC,
    COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC,
    manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC,
    "docs/specs/work_packets/corex_excalidraw_real_editor/COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json",
    "docs/specs/work_packets/ui_context_scalability_refactor/SUBSYSTEM_PACKET_INDEX.md",
    "docs/specs/work_packets/ui_context_scalability_refactor/FEATURE_PACKET_TEMPLATE.md",
)

GRAPH_CANVAS_PERF_MATRIX_REQUIRED_TOKENS = (
    "GraphCanvas.qml",
    "--baseline-runs 3 --scenario heavy_media",
    GRAPH_CANVAS_CANONICAL_REPORT_DIR,
    "## Desktop/Manual Exit Gate",
    "Status: `PASS`",
    P09_DESKTOP_REFERENCE_REPORT_MD,
)
GRAPH_CANVAS_PERF_MATRIX_AUDIT_COMMANDS = (
    P10_TRACEABILITY_TEST_COMMAND,
    GRAPH_CANVAS_OFFSCREEN_COMMAND,
    GRAPH_CANVAS_INTERACTIVE_COMMAND,
    manifest.proof_audit_command(),
)
GRAPH_CANVAS_PERF_MATRIX_RESULT_COMMANDS = (
    P10_TRACEABILITY_TEST_COMMAND,
    manifest.proof_audit_command(),
)
GRAPH_CANVAS_TRACK_H_REPORT_REQUIRED_TOKENS = (
    "GraphCanvas.qml",
    GRAPH_CANVAS_OFFSCREEN_COMMAND,
    GRAPH_CANVAS_INTERACTIVE_COMMAND,
    GRAPH_CANVAS_CANONICAL_REPORT_MD,
    GRAPH_CANVAS_CANONICAL_REPORT_JSON,
    "Scenario: `heavy_media`",
    "Media surface count: `6`",
    "## 2026-03-21 Offscreen Snapshot",
    "## Windows Desktop Exit Gate",
    "Status: `PASS`",
    P09_DESKTOP_REFERENCE_REPORT_MD,
    P09_DESKTOP_REFERENCE_REPORT_JSON,
    manifest.GRAPH_CANVAS_PERF_MATRIX_DOC,
)
GRAPH_CANVAS_TRACK_H_REPORT_FORBIDDEN_TOKENS = (
    "Historical offscreen harness baseline restored from repo",
    "`P04`",
    "P08 did not rerun the performance harness.",
    "Interactive desktop/GPU validation remains required",
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_REQUIRED_TOKENS = (
    "## Locked Scope",
    "## Shell Isolation Contract",
    "## Final Verification Commands",
    "## Focused Narrow Reruns",
    "## 2026-03-28 Execution Results",
    "## Remaining Manual and Windows-Only Checks",
    "## Historical References",
    "## Residual Risks",
    manifest.PACKAGING_WINDOWS_DOC,
    manifest.PILOT_RUNBOOK_DOC,
    manifest.ARCHITECTURE_REFACTOR_QA_MATRIX_DOC,
    "tests/shell_isolation_runtime.py",
    "tests/shell_isolation_main_window_targets.py",
    "tests/shell_isolation_controller_targets.py",
    "RC_PACKAGING_REPORT.md",
    "PILOT_SIGNOFF.md",
    manifest.MARKDOWN_HYGIENE_TEST,
)
ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS = (
    manifest.DOCS_RELEASE_TRACEABILITY_PYTEST_COMMAND,
    manifest.proof_audit_command(),
    f"{manifest.LOCAL_VENV_PYTHON_DISPLAY} {manifest.CHECK_MARKDOWN_LINKS_SCRIPT}",
)
ARCHITECTURE_DOC_REQUIRED_TOKENS = (
    "docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
    manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC,
    "## Current focused contracts",
    "dependency-free public function/decorator SDK",
    "static declaration parsing",
    "process worker",
    "focused bridges",
    "current-schema",
    "17-name top-level `corex` SDK",
    "immutable content-addressed generation",
    "snapshot-only",
    "typed transport/session",
    "ea_node_editor.ui.perf.performance_harness",
    "locked unavailable-add-on surfaces",
    "## Add-on backend preparation",
    "Variant 4 inspector-style right drawer",
    "locked unavailable-add-on surfaces",
    "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
)
SPEC_INDEX_REQUIRED_TOKENS = (
    *manifest.ARCHITECTURE_RESIDUAL_REFACTOR_SPEC_INDEX_TOKENS,
    "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
    "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
    "UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX.md",
    "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
    "COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md",
    "PLUGIN_AUTHORING_GUIDE.md",
    "PLUGIN_MIGRATION_GUIDE.md",
    "COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md",
    "COREX_EXCALIDRAW_REAL_EDITOR_STATUS.md",
    "COREX_EXCALIDRAW_REAL_EDITOR QA Evidence",
    "PLAN_COREX_INCREMENTAL_EXECUTION_AND_SOLUTION_SNAPSHOTS.md",
    "COMPLETED — T01–T09 ACCEPTED",
)
COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_REQUIRED_TOKENS = (
    "COREX Excalidraw Web Host Layer QA Matrix",
    "`COREX_EXCALIDRAW_REAL_EDITOR`",
    "real local/offline Excalidraw editor",
    "managed image imports",
    "artifact-backed previews",
    "ProjectArtifactStore",
    "no execution semantics",
    "no external browser launch",
    "remote rooms",
    "collaboration services",
    "execution-worker WebEngine behavior",
    "arbitrary third-party plugin web UIs",
    "## Historical Host-Layer Baseline",
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
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_REQUIRED_TOKENS = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_REQUIRED_TOKENS
)
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_AUDIT_COMMANDS = (
    manifest.ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_AUDIT_COMMANDS
)
UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_REQUIRED_TOKENS = (
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
UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS = (
    UI_CONTEXT_SCALABILITY_REFACTOR_FINAL_PYTEST_COMMAND,
    UI_CONTEXT_SCALABILITY_REFACTOR_TRACEABILITY_COMMAND,
    UI_CONTEXT_SCALABILITY_REFACTOR_MARKDOWN_COMMAND,
)
README_CURRENT_TOKENS = (
    "COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
    "headless Corex kernel",
    "execution backend policy",
    "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
    "Add-On Manager",
    "Variant 4 inspector-style drawer",
    "ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
)
ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_REQUIRED_TOKENS = (
    "Add-On Manager Backend Preparation QA Matrix",
    "## Locked Scope",
    "## Current Automated Verification",
    "## Final Closeout Commands",
    "## 2026-09-07 Execution Results",
    "## Manual Desktop Checks",
    "## Residual Risks",
    "Variant 4 inspector-style right drawer",
    "Mockup B placeholders",
    "Tabular Data",
    "MARS",
    *ADDON_MANAGER_BACKEND_PREPARATION_VERIFICATION_COMMANDS,
    *ADDON_MANAGER_BACKEND_PREPARATION_AUDIT_COMMANDS,
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_REQUIRED_TOKENS = (
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
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_AUDIT_COMMANDS = (
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND,
)
COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_REQUIRED_TOKENS = (
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
    "QML shell as one client",
    "strict current `.cxproj`",
    "canonical graph action IDs",
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
COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_AUDIT_COMMANDS = (
    COREX_ARCHITECTURE_MODERNIZATION_PYTEST_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_TRACEABILITY_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_MARKDOWN_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_FULL_DRY_RUN_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND,
    COREX_ARCHITECTURE_MODERNIZATION_REVIEW_GATE_COMMAND,
)

P10_TRACEABILITY_ROW_REQUIRED_TOKENS = {
    "REQ-UI-016": (
        "graphics_settings_dialog.py",
        "show_graphics_settings_dialog",
        "tests/test_graphics_settings_preferences.py",
    ),
    "AC-REQ-UI-016-01": (
        "tests/test_graphics_settings_preferences.py",
        "tests/test_shell_theme.py",
        "tests/test_main_window_shell.py",
    ),
    "REQ-NODE-016": (
        "spec_validation.py",
        "instance_resolution.py",
        "property_coercion.py",
        "property_normalization.py",
        "tests/test_property_normalization.py",
        "tests/test_spec_validation.py",
        "graph_scene_payload/",
        "tests/test_graph_surface_input_contract.py",
        "tests/test_passive_node_contracts.py",
    ),
    "AC-REQ-NODE-016-01": (
        "tests/test_spec_validation.py",
        "tests/test_property_coercion.py",
        "tests/test_property_normalization.py",
        "tests/test_graph_surface_input_contract.py",
        "tests/test_passive_node_contracts.py",
        "tests/test_registry_validation.py",
    ),
    "REQ-PERSIST-011": (
        "tests/test_graphics_settings_preferences.py",
        "tests/main_window_shell/shell_basics_and_search.py",
    ),
    "AC-REQ-PERSIST-011-01": (
        "tests/test_shell_project_session_controller.py",
        "tests/main_window_shell/shell_basics_and_search.py",
    ),
    "REQ-PERF-001": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
    ),
    "REQ-PERF-002": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
        "GraphCanvas.qml",
    ),
    "REQ-PERF-003": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
        "load",
    ),
    "REQ-QA-009": (
        "shell_runtime_contracts.py",
        "bridge_qml_boundaries.py",
        "tests/test_graphics_settings_dialog.py",
    ),
    "REQ-QA-011": (
        "tests/test_graph_surface_input_contract.py",
        "tests/test_passive_node_contracts.py",
        "tests/test_passive_graph_surface_host.py",
    ),
    "REQ-QA-018": (
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
        P09_DESKTOP_REFERENCE_REPORT_JSON,
        manifest.CHECK_TRACEABILITY_SCRIPT,
    ),
    "AC-REQ-PERF-002-01": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "tests/test_track_h_perf_harness.py",
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
    ),
    "AC-REQ-PERF-003-01": (
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_CANONICAL_REPORT_DIR,
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
    ),
    "AC-REQ-PERF-002-02": (
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_CANONICAL_REPORT_DIR,
        P09_DESKTOP_REFERENCE_REPORT_JSON,
    ),
    "AC-REQ-QA-018-01": (
        GRAPH_CANVAS_OFFSCREEN_COMMAND,
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_CANONICAL_REPORT_MD,
        GRAPH_CANVAS_CANONICAL_REPORT_JSON,
        P09_DESKTOP_REFERENCE_REPORT_MD,
        manifest.CHECK_TRACEABILITY_SCRIPT,
    ),
}
TRACEABILITY_ROW_REQUIRED_TOKENS = dict(manifest.TRACEABILITY_ROW_REQUIRED_TOKENS)
TRACEABILITY_ROW_REQUIRED_TOKENS.update(P10_TRACEABILITY_ROW_REQUIRED_TOKENS)
TRACEABILITY_ROW_REQUIRED_TOKENS.update(
    {
        "REQ-QA-030": (
            "docs/specs/INDEX.md",
            "docs/specs/requirements/90_QA_ACCEPTANCE.md",
            "docs/specs/requirements/TRACEABILITY_MATRIX.md",
            UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_DOC,
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
        "REQ-UI-041": (
            "window.py",
            "window_actions.py",
            "addon_manager_presenter.py",
            "MainShell.qml",
            "AddOnManagerPane.qml",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-UI-041-01": (
            "tests/test_main_window_shell.py",
            "tests/main_window_shell/shell_basics_and_search.py",
            "tests/main_window_shell/bridge_qml_boundaries.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-UI-042": (
            "graph/registry_normalization.py",
            "project_codec.py",
            "graph_scene_payload/",
            "GraphNodeHost.qml",
            "GraphNodeHeaderLayer.qml",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-UI-042-01": (
            "tests/test_serializer.py",
            "tests/test_serializer_schema_migration.py",
            "tests/test_graph_surface_input_contract.py",
            "tests/test_graph_surface_input_controls.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-PERSIST-023": (
            "app_preferences.py",
            "settings.py",
            "project_codec.py",
            "graph/registry_normalization.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-PERSIST-023-01": (
            "tests/test_plugin_loader.py",
            "tests/test_serializer.py",
            "tests/test_registry_validation.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-INT-011": (
            "catalog.py",
            "registry_contributions.py",
            "plugin_contracts.py",
            "function_bundle.py",
            "addon_manager_presenter.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "AC-REQ-INT-011-01": (
            "tests/test_addon_registry_contributions.py",
            "tests/test_main_window_shell.py",
            "tests/main_window_shell/shell_basics_and_search.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-QA-040": (
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
            "20_UI_UX.md",
            "60_PERSISTENCE.md",
            "70_INTEGRATIONS.md",
            "tests/test_traceability_checker.py",
            "scripts/check_traceability.py",
        ),
        "AC-REQ-QA-040-01": (
            "tests/test_addon_catalog.py",
            "tests/test_engineering_viewer_widget_binder.py",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-QA-041": (
            "ARCHITECTURE.md",
            "README.md",
            "docs/specs/INDEX.md",
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
            "tests/test_traceability_checker.py",
            "tests/test_markdown_hygiene.py",
            "scripts/check_markdown_links.py",
        ),
        "AC-REQ-QA-041-01": (
            ADDON_MANAGER_BACKEND_PREPARATION_CLOSEOUT_PYTEST_COMMAND,
            ADDON_MANAGER_BACKEND_PREPARATION_TRACEABILITY_COMMAND,
            ADDON_MANAGER_BACKEND_PREPARATION_MARKDOWN_COMMAND,
            "docs/specs/perf/ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX.md",
        ),
        "REQ-QA-042": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["REQ-QA-042"],
        "AC-REQ-QA-042-01": manifest.TRACEABILITY_ROW_REQUIRED_TOKENS["AC-REQ-QA-042-01"],
        "REQ-QA-046": (
            "ARCHITECTURE.md",
            "README.md",
            "docs/specs/INDEX.md",
            "docs/specs/requirements/10_ARCHITECTURE.md",
            "docs/specs/requirements/50_EXECUTION_ENGINE.md",
            "docs/specs/requirements/70_INTEGRATIONS.md",
            "docs/specs/requirements/90_QA_ACCEPTANCE.md",
            "docs/specs/perf/COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX.md",
            "docs/specs/work_packets/corex_architecture_modernization/"
            "COREX_ARCHITECTURE_MODERNIZATION_MANIFEST.md",
            "docs/specs/work_packets/corex_architecture_modernization/"
            "COREX_ARCHITECTURE_MODERNIZATION_STATUS.md",
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
            COREX_ARCHITECTURE_MODERNIZATION_WRAPUP_DOC,
        ),
    }
)
TRACEABILITY_ROW_REQUIRED_TOKENS.update(
    {
        "REQ-UI-044": (
            "GraphWebBoardSurface.qml",
            "WebEditorHost.qml",
            "web/excalidraw_host/src/main.tsx",
            "tests/test_corex_web_surface_bridge.py",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
            "P01_js_host_bundle_WRAPUP.md",
            "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
        ),
        "AC-REQ-UI-044-01": (
            "tests/test_content_fullscreen_bridge.py",
            "tests/test_corex_web_surface_bridge.py",
            "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
            "P06_docs_traceability_closeout_WRAPUP.md",
        ),
        "REQ-NODE-030": (
            "nodes/builtins/excalidraw.py",
            "tests/test_project_save_as_flow.py",
            "P04_persistence_save_as_refs_WRAPUP.md",
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
            "P02_artifact_backed_web_bridge_WRAPUP.md",
        ),
        "AC-REQ-NODE-031-01": (
            "WebEngine/WebChannel/import/preview/fullscreen behavior remains shell-only",
            "tests/test_content_fullscreen_bridge.py",
            "P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
        ),
        "REQ-PERSIST-024": (
            "common/artifact_refs.py",
            "web_host/bridge.py",
            "tests/test_project_save_as_flow.py",
            "P02_artifact_backed_web_bridge_WRAPUP.md",
            "P04_persistence_save_as_refs_WRAPUP.md",
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
            "web_host/bridge.py",
            "P01_js_host_bundle_WRAPUP.md",
            "P02_artifact_backed_web_bridge_WRAPUP.md",
            "P05_packaging_and_static_asset_proof_WRAPUP.md",
        ),
        "AC-REQ-INT-014-01": (
            "managed image import",
            "artifact-backed preview",
            "no external/collaboration/remote-room/execution-worker/arbitrary-web expansion proof",
            "tests/test_project_save_as_flow.py",
            "P05_packaging_and_static_asset_proof_WRAPUP.md",
        ),
        "REQ-QA-045": (
            "COREX_EXCALIDRAW_REAL_EDITOR_MANIFEST.md",
            "P06_docs_traceability_closeout_WRAPUP.md",
            "tests/test_pytest_defaults.py",
            "scripts/verification_manifest.py",
            "COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md",
        ),
        "AC-REQ-QA-045-01": (
            COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
            "P06_docs_traceability_closeout_WRAPUP.md",
        ),
    }
)

P10_TRACEABILITY_ROW_FORBIDDEN_TOKENS = {
    "AC-REQ-QA-018-01": ("ea_node_editor.telemetry.performance_harness",),
}
TRACEABILITY_ROW_FORBIDDEN_TOKENS = dict(manifest.TRACEABILITY_ROW_FORBIDDEN_TOKENS)
TRACEABILITY_ROW_FORBIDDEN_TOKENS.update(P10_TRACEABILITY_ROW_FORBIDDEN_TOKENS)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`") and len(stripped) >= 2:
        return stripped[1:-1]
    return stripped


def strip_worktree_ignore_args(command: str) -> str:
    stripped = command
    for arg in manifest.worktree_pytest_ignore_args():
        stripped = stripped.replace(f" {arg}", "")
    return stripped


def extract_section(text: str, heading: str) -> str | None:
    match = re.search(
        rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return None
    return match.group("body").strip("\n")


def parse_markdown_table(section_text: str) -> list[dict[str, str]] | None:
    table_lines: list[str] = []
    in_table = False
    for line in section_text.splitlines():
        if line.startswith("|"):
            table_lines.append(line)
            in_table = True
            continue
        if in_table:
            break
    if len(table_lines) < 2:
        return None

    headers = [cell.strip() for cell in table_lines[0].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def parse_traceability_rows(matrix_text: str) -> dict[str, dict[str, str]]:
    """Parse the top-level requirement traceability table by requirement id."""

    rows = parse_markdown_table(matrix_text)
    if rows is None:
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for row in rows:
        row_id = strip_code_fence(row.get("Requirement ID", ""))
        if row_id:
            parsed[row_id] = row
    return parsed


def table_after_heading(
    text: str,
    *,
    relative_path: str,
    heading: str,
    issues: list[str],
) -> list[dict[str, str]] | None:
    section = extract_section(text, heading)
    if section is None:
        issues.append(f"{relative_path}: missing section: {heading}")
        return None
    rows = parse_markdown_table(section)
    if rows is None:
        issues.append(f"{relative_path}: missing markdown table in section: {heading}")
        return None
    return rows


def find_row(
    rows: list[dict[str, str]],
    *,
    column: str,
    predicate,
) -> dict[str, str] | None:
    for row in rows:
        value = row.get(column, "")
        if predicate(value):
            return row
    return None


def require_tokens(
    text: str,
    tokens: tuple[str, ...],
    *,
    relative_path: str,
    label: str,
    issues: list[str],
) -> None:
    for token in tokens:
        if token not in text:
            issues.append(f"{relative_path}: {label} missing fact: {token}")


def require_command_result(
    rows: list[dict[str, str]],
    *,
    relative_path: str,
    heading: str,
    predicate,
    label: str,
    issues: list[str],
) -> dict[str, str] | None:
    row = find_row(rows, column="Command", predicate=lambda value: predicate(strip_code_fence(value)))
    if row is None:
        issues.append(f"{relative_path}: {heading} missing command row: {label}")
        return None
    result = strip_code_fence(row.get("Result", ""))
    if result != "PASS":
        issues.append(
            f"{relative_path}: {heading} command {label} has unexpected result: {result}"
        )
    return row


def parse_requirement_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^- `([^`]+)`: (.+)$", line.strip())
        if match is not None:
            parsed[match.group(1)] = match.group(2)
    return parsed


def audit_requirement_tokens(
    text: str,
    relative_path: str,
    requirement_tokens: dict[str, tuple[str, ...]],
    issues: list[str],
) -> None:
    requirements = parse_requirement_lines(text)
    for requirement_id, tokens in requirement_tokens.items():
        body = requirements.get(requirement_id)
        if body is None:
            issues.append(f"{relative_path}: missing requirement line: {requirement_id}")
            continue
        require_tokens(
            body,
            tokens,
            relative_path=relative_path,
            label=f"requirement {requirement_id}",
            issues=issues,
        )


def audit_generic_document_rule(
    *,
    relative_path: str,
    text: str,
    rule: manifest.DocumentRule,
    issues: list[str],
) -> None:
    for snippet in rule.required:
        if snippet not in text:
            issues.append(f"{relative_path}: missing required text: {snippet}")
    for snippet in rule.forbidden:
        if snippet in text:
            issues.append(f"{relative_path}: found stale text: {snippet}")


def audit_qa_acceptance(text: str, relative_path: str, issues: list[str]) -> None:
    audit_requirement_tokens(text, relative_path, QA_ACCEPTANCE_REQUIREMENT_TOKENS, issues)
    current_closeout_evidence = extract_section(text, "Current Closeout Evidence")
    if current_closeout_evidence is None:
        issues.append(f"{relative_path}: missing section: Current Closeout Evidence")
    else:
        require_tokens(
            current_closeout_evidence,
            QA_ACCEPTANCE_CURRENT_CLOSEOUT_EVIDENCE_TOKENS,
            relative_path=relative_path,
            label="Current Closeout Evidence",
            issues=issues,
        )


def audit_requirement_doc(text: str, relative_path: str, issues: list[str]) -> None:
    requirement_tokens = dict(P10_REQUIREMENT_DOC_TOKENS.get(relative_path, {}))
    requirement_tokens.update(
        manifest.NOVICE_PLUGIN_SDK_REQUIREMENT_TOKENS.get(relative_path, {})
    )
    if not requirement_tokens:
        return
    audit_requirement_tokens(text, relative_path, requirement_tokens, issues)


def audit_verification_speed_matrix(text: str, relative_path: str, issues: list[str]) -> None:
    for forbidden in manifest.VERIFICATION_SPEED_FORBIDDEN_TOKENS:
        if forbidden in text:
            issues.append(f"{relative_path}: found stale text: {forbidden}")

    workflow_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Approved Verification Workflow",
        issues=issues,
    )
    if workflow_rows is not None:
        for mode in manifest.MODE_NAMES:
            row = find_row(
                workflow_rows,
                column="Mode",
                predicate=lambda value, mode=mode: strip_code_fence(value) == mode,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Approved Verification Workflow missing mode row: {mode}"
                )
                continue
            command = strip_code_fence(row.get("Command", ""))
            expected_command = manifest.run_verification_command(mode)
            if command != expected_command:
                issues.append(
                    f"{relative_path}: Approved Verification Workflow row {mode} has unexpected command: {command}"
                )
            require_tokens(
                row.get("Notes", ""),
                manifest.VERIFICATION_SPEED_WORKFLOW_NOTE_TOKENS[mode],
                relative_path=relative_path,
                label=f"workflow row {mode}",
                issues=issues,
            )

    shell_rules = extract_section(text, "Locked Shell Isolation Rules")
    if shell_rules is None:
        issues.append(f"{relative_path}: missing section: Locked Shell Isolation Rules")
    else:
        shell_rule_command = manifest.shell_isolation_pytest_command()
        require_tokens(
            shell_rules,
            tuple(
                token
                for token in manifest.VERIFICATION_SPEED_SHELL_RULE_TOKENS
                if token != shell_rule_command
            ),
            relative_path=relative_path,
            label="Locked Shell Isolation Rules",
            issues=issues,
        )
        if (
            shell_rule_command not in shell_rules
            and strip_worktree_ignore_args(shell_rule_command) not in shell_rules
        ):
            issues.append(
                f"{relative_path}: Locked Shell Isolation Rules missing fact: "
                f"{shell_rule_command}"
            )

    benchmark_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Published Shell-Tail Benchmark Evidence",
        issues=issues,
    )
    if benchmark_rows is not None:
        old_row = find_row(
            benchmark_rows,
            column="Workflow Shape",
            predicate=lambda value: value == "Old sequential shell-tail baseline",
        )
        if old_row is None:
            issues.append(
                f"{relative_path}: Published Shell-Tail Benchmark Evidence missing row: Old sequential shell-tail baseline"
            )
        elif not OLD_SHELL_TAIL_RESULT_PATTERN.match(old_row.get("Recorded Result", "")):
            issues.append(
                f"{relative_path}: old shell-tail benchmark result is not a timed mean summary: {old_row.get('Recorded Result', '')}"
            )

        dedicated_row = find_row(
            benchmark_rows,
            column="Workflow Shape",
            predicate=lambda value: value == "Dedicated shell-isolation phase",
        )
        if dedicated_row is None:
            issues.append(
                f"{relative_path}: Published Shell-Tail Benchmark Evidence missing row: Dedicated shell-isolation phase"
            )
        else:
            result = dedicated_row.get("Recorded Result", "")
            if not SHELL_ISOLATION_RESULT_PATTERN.match(result):
                issues.append(
                    f"{relative_path}: dedicated shell-isolation benchmark result is not a pytest timing summary: {result}"
                )

    environment_notes = extract_section(text, "Current Environment Notes")
    if environment_notes is None:
        issues.append(f"{relative_path}: missing section: Current Environment Notes")
    else:
        require_tokens(
            environment_notes,
            manifest.VERIFICATION_SPEED_ENVIRONMENT_NOTE_TOKENS,
            relative_path=relative_path,
            label="Current Environment Notes",
            issues=issues,
        )

    proof_audit = extract_section(text, "Companion Proof Audit")
    if proof_audit is None:
        issues.append(f"{relative_path}: missing section: Companion Proof Audit")
    else:
        require_tokens(
            proof_audit,
            manifest.VERIFICATION_SPEED_COMPANION_PROOF_TOKENS,
            relative_path=relative_path,
            label="Companion Proof Audit",
            issues=issues,
        )

    baseline_status = extract_section(text, "Current Baseline Status")
    if baseline_status is None:
        issues.append(f"{relative_path}: missing section: Current Baseline Status")
    else:
        require_tokens(
            baseline_status,
            manifest.VERIFICATION_SPEED_BASELINE_REQUIRED_TOKENS,
            relative_path=relative_path,
            label="Current Baseline Status",
            issues=issues,
        )
        for forbidden in manifest.VERIFICATION_SPEED_BASELINE_FORBIDDEN_TOKENS:
            if forbidden in baseline_status:
                issues.append(f"{relative_path}: found stale text: {forbidden}")

    result_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-03-18 Verification Results",
        issues=issues,
    )
    if result_rows is not None:
        require_command_result(
            result_rows,
            relative_path=relative_path,
            heading="2026-03-18 Verification Results",
            predicate=lambda command: command == manifest.VERIFICATION_SPEED_RESULT_COMMANDS[0],
            label=manifest.VERIFICATION_SPEED_RESULT_COMMANDS[0],
            issues=issues,
        )
        require_command_result(
            result_rows,
            relative_path=relative_path,
            heading="2026-03-18 Verification Results",
            predicate=lambda command: (
                (
                    command.startswith(manifest.VERIFICATION_SPEED_SHELL_RESULT_COMMAND_PREFIX)
                    or command.startswith(
                        strip_worktree_ignore_args(
                            manifest.VERIFICATION_SPEED_SHELL_RESULT_COMMAND_PREFIX
                        )
                    )
                )
                and all(
                    token in command
                    for token in manifest.VERIFICATION_SPEED_SHELL_RESULT_REQUIRED_TOKENS
                )
            ),
            label=manifest.SHELL_ISOLATION_SPEC.test_path,
            issues=issues,
        )
        require_command_result(
            result_rows,
            relative_path=relative_path,
            heading="2026-03-18 Verification Results",
            predicate=lambda command: command == manifest.VERIFICATION_SPEED_RESULT_COMMANDS[1],
            label=manifest.VERIFICATION_SPEED_RESULT_COMMANDS[1],
            issues=issues,
        )


def audit_graph_canvas_perf_matrix(text: str, relative_path: str, issues: list[str]) -> None:
    require_tokens(
        text,
        GRAPH_CANVAS_PERF_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="graph-canvas perf matrix",
        issues=issues,
    )

    approved_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Approved Regression Commands",
        issues=issues,
    )
    if approved_rows is not None:
        for command in GRAPH_CANVAS_PERF_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                approved_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Approved Regression Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-03-21 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in GRAPH_CANVAS_PERF_MATRIX_RESULT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-03-21 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_track_h_report(text: str, relative_path: str, issues: list[str]) -> None:
    require_tokens(
        text,
        GRAPH_CANVAS_TRACK_H_REPORT_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="track-h benchmark report",
        issues=issues,
    )
    for forbidden in GRAPH_CANVAS_TRACK_H_REPORT_FORBIDDEN_TOKENS:
        if forbidden in text:
            issues.append(f"{relative_path}: found stale text: {forbidden}")


def audit_architecture_maintainability_refactor_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="architecture-maintainability-refactor qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Verification Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Verification Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-03-28 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-03-28 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_architecture_doc(text: str, relative_path: str, issues: list[str]) -> None:
    require_tokens(
        text,
        ARCHITECTURE_DOC_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="architecture closeout discovery",
        issues=issues,
    )


def audit_readme_doc(text: str, relative_path: str, issues: list[str]) -> None:
    require_tokens(
        text,
        README_CURRENT_TOKENS,
        relative_path=relative_path,
        label="readme current architecture",
        issues=issues,
    )






def audit_spec_index(text: str, relative_path: str, issues: list[str]) -> None:
    require_tokens(
        text,
        SPEC_INDEX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="spec index registration",
        issues=issues,
    )
    rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Capability Roadmap Status",
        issues=issues,
    )
    if rows is None:
        return
    if len(rows) != len(manifest.CAPABILITY_GROUPS):
        issues.append(
            f"{relative_path}: planned capability table has {len(rows)} rows; "
            f"expected {len(manifest.CAPABILITY_GROUPS)}"
        )
    for (
        opportunity_id,
        capability,
        requirement_ids,
        expected_status,
    ) in manifest.CAPABILITY_GROUPS:
        row = find_row(
            rows,
            column="Research opportunity",
            predicate=lambda value, expected=opportunity_id: strip_code_fence(value) == expected,
        )
        if row is None:
            issues.append(f"{relative_path}: missing planned capability group: {opportunity_id}")
            continue
        if row.get("COREX capability") != capability:
            issues.append(f"{relative_path}: planned capability {opportunity_id} has wrong title")
        requirement_text = row.get("Requirements", "")
        for requirement_id in requirement_ids:
            if f"`{requirement_id}`" not in requirement_text:
                issues.append(
                    f"{relative_path}: planned capability {opportunity_id} missing requirement: "
                    f"{requirement_id}"
                )
        if strip_code_fence(row.get("Status", "")) != expected_status:
            issues.append(f"{relative_path}: planned capability {opportunity_id} has wrong status")


def audit_corex_novice_plugin_sdk_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="novice function-plugin SDK QA matrix",
        issues=issues,
    )
    rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Pending Acceptance Gates",
        issues=issues,
    )
    if rows is None:
        return
    allowed_results = {"PENDING / NOT RUN", "PARTIAL", "FAIL", "PASS"}
    for gate in (
        *manifest.COREX_NOVICE_PLUGIN_SDK_PASSED_GATES,
        *manifest.COREX_NOVICE_PLUGIN_SDK_TRANSITIONAL_GATES,
    ):
        row = find_row(rows, column="Gate", predicate=lambda value, gate=gate: value == gate)
        if row is None:
            issues.append(f"{relative_path}: missing acceptance gate row: {gate}")
            continue
        result = strip_code_fence(row.get("Result", ""))
        if result not in allowed_results:
            issues.append(f"{relative_path}: acceptance gate {gate} has invalid result: {result}")
        evidence = strip_code_fence(row.get("Evidence", ""))
        if result == "PASS" and (not evidence or "not run" in evidence.casefold()):
            issues.append(f"{relative_path}: acceptance gate {gate} claims PASS without evidence")


def audit_architecture_residual_refactor_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="architecture-residual-refactor qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-04-04 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-04-04 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_ui_context_scalability_refactor_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="ui-context-scalability-refactor qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-04-05 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_AUDIT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-04-05 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )




def audit_addon_manager_backend_preparation_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="addon-manager-backend-preparation qa matrix",
        issues=issues,
    )

    verification_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Current Automated Verification",
        issues=issues,
    )
    if verification_rows is not None:
        for command in ADDON_MANAGER_BACKEND_PREPARATION_VERIFICATION_COMMANDS:
            row = find_row(
                verification_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Current Automated Verification missing command row: {command}"
                )
                continue
            status = strip_code_fence(row.get("Status", ""))
            if status not in {"PASS", "FAIL", "NOT RUN"}:
                issues.append(
                    f"{relative_path}: Current Automated Verification command {command} "
                    f"has invalid status: {status}"
                )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in ADDON_MANAGER_BACKEND_PREPARATION_AUDIT_COMMANDS:
            if find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            ) is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-09-07 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in ADDON_MANAGER_BACKEND_PREPARATION_AUDIT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-09-07 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_corex_no_legacy_architecture_cleanup_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="corex-no-legacy-architecture-cleanup qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-04-24 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_AUDIT_COMMANDS:
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-04-24 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_corex_architecture_modernization_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="corex-architecture-modernization qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_AUDIT_COMMANDS:
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )

    execution_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="2026-05-01 Execution Results",
        issues=issues,
    )
    if execution_rows is not None:
        for command in COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_AUDIT_COMMANDS:
            if command == COREX_ARCHITECTURE_MODERNIZATION_FULL_COMMAND:
                row = find_row(
                    execution_rows,
                    column="Command",
                    predicate=lambda value, command=command: strip_code_fence(value) == command,
                )
                if row is None:
                    issues.append(
                        f"{relative_path}: 2026-05-01 Execution Results missing command row: {command}"
                    )
                    continue
                result = strip_code_fence(row.get("Result", ""))
                notes = row.get("Notes", "")
                if result == "PASS":
                    continue
                if result == "FAIL" and "Owner:" in notes and "Reproduction:" in notes:
                    continue
                issues.append(
                    f"{relative_path}: 2026-05-01 Execution Results command {command} "
                    "must pass or record Owner/Reproduction residual-risk notes"
                )
                continue
            require_command_result(
                execution_rows,
                relative_path=relative_path,
                heading="2026-05-01 Execution Results",
                predicate=lambda value, command=command: value == command,
                label=command,
                issues=issues,
            )


def audit_corex_excalidraw_real_editor_qa_matrix(
    text: str,
    relative_path: str,
    issues: list[str],
) -> None:
    require_tokens(
        text,
        COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_REQUIRED_TOKENS,
        relative_path=relative_path,
        label="corex-excalidraw-real-editor qa matrix",
        issues=issues,
    )

    final_rows = table_after_heading(
        text,
        relative_path=relative_path,
        heading="Final Closeout Commands",
        issues=issues,
    )
    if final_rows is not None:
        for command in (
            COREX_EXCALIDRAW_REAL_EDITOR_P06_DOCS_PYTEST_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_TRACEABILITY_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_MARKDOWN_COMMAND,
            COREX_EXCALIDRAW_REAL_EDITOR_P06_REVIEW_GATE_COMMAND,
        ):
            row = find_row(
                final_rows,
                column="Command",
                predicate=lambda value, command=command: strip_code_fence(value) == command,
            )
            if row is None:
                issues.append(
                    f"{relative_path}: Final Closeout Commands missing command row: {command}"
                )


def find_traceability_row(matrix_text: str, row_id: str) -> dict[str, str] | None:
    return parse_traceability_rows(matrix_text).get(row_id)


def audit_traceability_rows(matrix_text: str, issues: list[str]) -> None:
    rows = parse_traceability_rows(matrix_text)
    if not rows:
        issues.append(f"{manifest.TRACEABILITY_MATRIX_DOC}: missing requirement traceability table")
        return

    for row_id, required_tokens in TRACEABILITY_ROW_REQUIRED_TOKENS.items():
        row = rows.get(row_id)
        if row is None:
            issues.append(f"{manifest.TRACEABILITY_MATRIX_DOC}: missing row: {row_id}")
            continue
        implementation_artifacts = row.get("Implementation Artifact", "")
        for token in required_tokens:
            if token not in implementation_artifacts:
                issues.append(
                    f"{manifest.TRACEABILITY_MATRIX_DOC}: row {row_id} missing implementation "
                    f"artifact text: {token}"
                )
        for token in TRACEABILITY_ROW_FORBIDDEN_TOKENS.get(row_id, ()):
            if token in implementation_artifacts:
                issues.append(
                    f"{manifest.TRACEABILITY_MATRIX_DOC}: row {row_id} found stale implementation "
                    f"artifact text: {token}"
                )


def traceability_identifiers(matrix_text: str) -> list[str]:
    identifiers: list[str] = []
    for line in matrix_text.splitlines():
        if not line.startswith("|"):
            continue
        for cell in line.strip().strip("|").split("|")[:2]:
            identifier = strip_code_fence(cell)
            if re.fullmatch(r"(?:AC-)?REQ-[A-Z]+-\d+(?:-\d+)?", identifier):
                identifiers.append(identifier)
    return identifiers


def audit_planned_traceability_rows(matrix_text: str, issues: list[str]) -> None:
    relative_path = manifest.TRACEABILITY_MATRIX_DOC
    rows = table_after_heading(
        matrix_text,
        relative_path=relative_path,
        heading="Planned / Unimplemented Requirements",
        issues=issues,
    )
    if rows is None:
        return

    expected_headers = (
        "Requirement ID",
        "Acceptance Criterion",
        "Spec Module",
        *manifest.PLANNED_REQUIREMENT_STATUSES,
    )
    if rows and tuple(rows[0]) != expected_headers:
        issues.append(f"{relative_path}: planned requirement table has unexpected columns")

    parsed: dict[str, dict[str, str]] = {}
    for row in rows:
        requirement_id = strip_code_fence(row.get("Requirement ID", ""))
        if requirement_id in parsed:
            issues.append(f"{relative_path}: duplicate planned row: {requirement_id}")
        elif requirement_id:
            parsed[requirement_id] = row

    expected_ids = set(manifest.PLANNED_REQUIREMENT_OWNERS)
    for requirement_id in sorted(set(parsed) - expected_ids):
        issues.append(f"{relative_path}: unexpected planned row: {requirement_id}")
    for requirement_id, owner in manifest.PLANNED_REQUIREMENT_OWNERS.items():
        row = parsed.get(requirement_id)
        if row is None:
            issues.append(f"{relative_path}: missing planned row: {requirement_id}")
            continue
        acceptance_id = f"AC-{requirement_id}-01"
        if strip_code_fence(row.get("Acceptance Criterion", "")) != acceptance_id:
            issues.append(
                f"{relative_path}: planned row {requirement_id} has wrong acceptance criterion"
            )
        if strip_code_fence(row.get("Spec Module", "")) != owner:
            issues.append(f"{relative_path}: planned row {requirement_id} has wrong owner")
        for column, expected in manifest.PLANNED_REQUIREMENT_STATUSES.items():
            actual = strip_code_fence(row.get(column, ""))
            if actual != expected:
                issues.append(
                    f"{relative_path}: planned row {requirement_id} has wrong {column}: {actual}"
                )

    seen: set[str] = set()
    for identifier in traceability_identifiers(matrix_text):
        if identifier in seen:
            issues.append(f"{relative_path}: duplicate traceability identifier: {identifier}")
        seen.add(identifier)


def audit_planned_requirement_definitions(repo_root: Path, issues: list[str]) -> None:
    locations: dict[str, list[str]] = {}
    for relative_path in manifest.REQUIREMENT_DEFINITION_DOCS:
        path = repo_root / relative_path
        if not path.exists():
            continue
        for line in read_text(path).splitlines():
            match = re.match(r"^- `([^`]+)`: (.+)$", line.strip())
            if match is not None:
                locations.setdefault(match.group(1), []).append(relative_path)

    for requirement_id, owner in manifest.PLANNED_REQUIREMENT_OWNERS.items():
        expected_path = manifest.PLANNED_REQUIREMENT_DOCS[owner]
        for identifier in (requirement_id, f"AC-{requirement_id}-01"):
            found = locations.get(identifier, [])
            if not found:
                issues.append(f"{expected_path}: missing planned requirement definition: {identifier}")
            elif found != [expected_path]:
                issues.append(
                    f"{expected_path}: planned requirement {identifier} has wrong or duplicate "
                    f"definitions: {', '.join(found)}"
                )

    for identifier, found in locations.items():
        if len(found) > 1:
            issues.append(
                f"duplicate requirement definition: {identifier}: {', '.join(found)}"
            )


SPECIAL_DOCUMENT_AUDITORS = {
    "ARCHITECTURE.md": audit_architecture_doc,
    "README.md": audit_readme_doc,
    manifest.SPEC_INDEX_DOC: audit_spec_index,
    "docs/specs/requirements/20_UI_UX.md": audit_requirement_doc,
    "docs/specs/requirements/40_NODE_SDK.md": audit_requirement_doc,
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": audit_requirement_doc,
    "docs/specs/requirements/60_PERSISTENCE.md": audit_requirement_doc,
    "docs/specs/requirements/80_PERFORMANCE.md": audit_requirement_doc,
    "docs/specs/requirements/70_INTEGRATIONS.md": audit_requirement_doc,
    manifest.QA_ACCEPTANCE_DOC: audit_qa_acceptance,
    manifest.VERIFICATION_SPEED_MATRIX_DOC: audit_verification_speed_matrix,
    manifest.GRAPH_CANVAS_PERF_MATRIX_DOC: audit_graph_canvas_perf_matrix,
    manifest.TRACK_H_BENCHMARK_REPORT_DOC: audit_track_h_report,
    manifest.ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC: audit_architecture_maintainability_refactor_qa_matrix,
    ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC: audit_architecture_residual_refactor_qa_matrix,
    UI_CONTEXT_SCALABILITY_REFACTOR_QA_MATRIX_DOC: audit_ui_context_scalability_refactor_qa_matrix,
    ADDON_MANAGER_BACKEND_PREPARATION_QA_MATRIX_DOC: audit_addon_manager_backend_preparation_qa_matrix,
    COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC: audit_corex_no_legacy_architecture_cleanup_qa_matrix,
    COREX_ARCHITECTURE_MODERNIZATION_QA_MATRIX_DOC: audit_corex_architecture_modernization_qa_matrix,
    COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC: audit_corex_excalidraw_real_editor_qa_matrix,
    manifest.COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC: audit_corex_novice_plugin_sdk_qa_matrix,
}


def audit_repository(repo_root: Path) -> list[str]:
    issues: list[str] = []
    matrix_text: str | None = None

    for relative_path in REQUIRED_ARTIFACTS:
        path = repo_root / relative_path
        if not path.exists():
            issues.append(f"Missing required artifact: {relative_path}")
    for relative_path in P08_REQUIRED_ARTIFACTS:
        path = repo_root / relative_path
        if not path.exists():
            issues.append(f"Missing required artifact: {relative_path}")
    audited_documents = set(GENERIC_DOCUMENT_RULES) | set(SPECIAL_DOCUMENT_AUDITORS)
    for relative_path in audited_documents:
        path = repo_root / relative_path
        if not path.exists():
            continue
        text = read_text(path)
        if relative_path == manifest.TRACEABILITY_MATRIX_DOC:
            matrix_text = text
        rule = GENERIC_DOCUMENT_RULES.get(relative_path)
        if rule is not None:
            audit_generic_document_rule(
                relative_path=relative_path,
                text=text,
                rule=rule,
                issues=issues,
            )
        auditor = SPECIAL_DOCUMENT_AUDITORS.get(relative_path)
        if auditor is not None:
            auditor(text, relative_path, issues)

    if matrix_text is None:
        matrix_path = repo_root / manifest.TRACEABILITY_MATRIX_DOC
        if matrix_path.exists():
            matrix_text = read_text(matrix_path)

    if matrix_text is None:
        issues.append(f"Missing required artifact: {manifest.TRACEABILITY_MATRIX_DOC}")
        return issues

    audit_traceability_rows(matrix_text, issues)
    audit_planned_traceability_rows(matrix_text, issues)
    audit_planned_requirement_definitions(repo_root, issues)
    return issues


def main() -> int:
    issues = audit_repository(REPO_ROOT)
    if issues:
        print("TRACEABILITY CHECK FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("TRACEABILITY CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
