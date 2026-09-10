"""Canonical verification workflow facts for runner, tests, and proof audits."""

from __future__ import annotations

from dataclasses import dataclass

LOCAL_VENV_PYTHON_DISPLAY = "./venv/Scripts/python.exe"
RUN_VERIFICATION_SCRIPT = "scripts/run_verification.py"
CHECK_TRACEABILITY_SCRIPT = "scripts/check_traceability.py"
CHECK_MARKDOWN_LINKS_SCRIPT = "scripts/check_markdown_links.py"
CHECK_CONTEXT_BUDGETS_SCRIPT = "scripts/check_context_budgets.py"
CONTEXT_BUDGET_RULES_PATH = (
    "docs/specs/work_packets/ui_context_scalability_refactor/CONTEXT_BUDGET_RULES.json"
)
CONTEXT_BUDGET_GUARDRAILS_TEST = "tests/test_context_budget_guardrails.py"
OFFSCREEN_ENV = {"QT_QPA_PLATFORM": "offscreen"}
QML_QUICK_PHASE_KEY = "qml_quick"
QML_QUICK_PHASE = "gui.qml_quick"
QML_QUICK_INPUT_PATH = "tests/qml_quick"
QML_QUICK_ARGS = (
    "-input",
    QML_QUICK_INPUT_PATH,
    "-eventdelay",
    "0",
    "-keydelay",
    "0",
    "-mousedelay",
    "0",
    "-o",
    "-,txt",
)
QML_QUICK_ENV = {
    "QT_QPA_PLATFORM": "offscreen",
    "QT_QUICK_CONTROLS_STYLE": "Basic",
}
WORKTREE_PYTEST_IGNORE_PATHS = ("venv",)
SHELL_WINDOW_LIFECYCLE_TEST_PATH = "tests/test_shell_window_lifecycle_isolated.py"
SHELL_LIFECYCLE_TRUTH = "deterministic in-process shell window teardown"
SHELL_LIFECYCLE_SHARED_WINDOW_SCOPE = "repeated create/show/close cycles inside one isolated child process"

MODE_NAMES = ("fast", "gui", "slow", "full")
MAX_GUI_PARALLEL_WORKERS = 6
MAX_SHELL_ISOLATION_PARALLEL_WORKERS = 4
CONTEXT_BUDGET_PHASE_KEY = "context_budgets"
CONTEXT_BUDGET_PHASE = "fast.context_budgets"
CONTEXT_BUDGET_CHECK_COMMAND = f"{LOCAL_VENV_PYTHON_DISPLAY} {CHECK_CONTEXT_BUDGETS_SCRIPT}"
P07_CONTEXT_BUDGET_PYTEST_COMMAND = (
    f"{LOCAL_VENV_PYTHON_DISPLAY} -m pytest "
    f"{CONTEXT_BUDGET_GUARDRAILS_TEST} tests/test_run_verification.py --ignore=venv -q"
)
P07_CONTEXT_BUDGET_VERIFICATION_COMMANDS = (
    CONTEXT_BUDGET_CHECK_COMMAND,
    P07_CONTEXT_BUDGET_PYTEST_COMMAND,
)
P07_CONTEXT_BUDGET_REVIEW_GATE_COMMAND = CONTEXT_BUDGET_CHECK_COMMAND
P07_CONTEXT_BUDGET_ARTIFACTS = (
    CHECK_CONTEXT_BUDGETS_SCRIPT,
    CONTEXT_BUDGET_RULES_PATH,
    CONTEXT_BUDGET_GUARDRAILS_TEST,
)
FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_PYTEST_COMMAND = (
    f"{LOCAL_VENV_PYTHON_DISPLAY} -m pytest "
    f"{CONTEXT_BUDGET_GUARDRAILS_TEST} tests/test_run_verification.py --ignore=venv -q"
)
FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_FAST_DRY_RUN_COMMAND = (
    f"{LOCAL_VENV_PYTHON_DISPLAY} {RUN_VERIFICATION_SCRIPT} --mode fast --dry-run"
)
FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_VERIFICATION_COMMANDS = (
    CONTEXT_BUDGET_CHECK_COMMAND,
    FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_PYTEST_COMMAND,
    FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_FAST_DRY_RUN_COMMAND,
)
FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_REVIEW_GATE_COMMAND = CONTEXT_BUDGET_CHECK_COMMAND
FOLLOWUP_P01_GUARDRAIL_CATALOG_EXPANSION_ARTIFACTS = (
    CHECK_CONTEXT_BUDGETS_SCRIPT,
    RUN_VERIFICATION_SCRIPT,
    "scripts/verification_manifest.py",
    CONTEXT_BUDGET_RULES_PATH,
    CONTEXT_BUDGET_GUARDRAILS_TEST,
    "tests/test_run_verification.py",
)

PACKAGING_WINDOWS_DOC = "docs/PACKAGING_WINDOWS.md"
COREX_EXCALIDRAW_WEB_HOST_LAYER_P06_VERIFICATION_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py "
    r"tests/test_traceability_checker.py tests/test_corex_web_host_assets.py --ignore=venv -q"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_P06_REVIEW_GATE_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_packaging_configuration.py "
    r'-k "web or webengine or asset" --ignore=venv -q'
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_WEB_PACKAGE_COMMAND = (
    r".\scripts\build_windows_package.ps1 -PackageProfile web -Clean -SkipSmoke"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_WEB_INSTALLER_COMMAND = (
    r".\scripts\build_windows_installer.ps1 -PackageProfile web"
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_COMMANDS = (
    COREX_EXCALIDRAW_WEB_HOST_LAYER_WEB_PACKAGE_COMMAND,
    COREX_EXCALIDRAW_WEB_HOST_LAYER_WEB_INSTALLER_COMMAND,
)
COREX_EXCALIDRAW_WEB_HOST_LAYER_PACKAGING_ARTIFACTS = (
    "pyproject.toml",
    "ea_node_editor.spec",
    "scripts/build_windows_package.ps1",
    "scripts/build_windows_installer.ps1",
    "tests/test_packaging_configuration.py",
    "tests/test_corex_web_host_assets.py",
)
COREX_EXCALIDRAW_REAL_EDITOR_QA_MATRIX_DOC = (
    "docs/specs/perf/COREX_EXCALIDRAW_WEB_HOST_LAYER_QA_MATRIX.md"
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
COREX_EXCALIDRAW_REAL_EDITOR_PACKET_WRAPUPS = (
    "docs/specs/work_packets/corex_excalidraw_real_editor/P01_js_host_bundle_WRAPUP.md",
    "docs/specs/work_packets/corex_excalidraw_real_editor/P02_artifact_backed_web_bridge_WRAPUP.md",
    "docs/specs/work_packets/corex_excalidraw_real_editor/P03_fullscreen_lifecycle_and_preview_WRAPUP.md",
    "docs/specs/work_packets/corex_excalidraw_real_editor/P04_persistence_save_as_refs_WRAPUP.md",
    "docs/specs/work_packets/corex_excalidraw_real_editor/P05_packaging_and_static_asset_proof_WRAPUP.md",
)
PILOT_RUNBOOK_DOC = "docs/PILOT_RUNBOOK.md"
SPEC_INDEX_DOC = "docs/specs/INDEX.md"
QA_ACCEPTANCE_DOC = "docs/specs/requirements/90_QA_ACCEPTANCE.md"
TRACEABILITY_MATRIX_DOC = "docs/specs/requirements/TRACEABILITY_MATRIX.md"
VERIFICATION_SPEED_MATRIX_DOC = "docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md"
GRAPH_CANVAS_PERF_MATRIX_DOC = "docs/specs/perf/GRAPH_CANVAS_PERF_QA_MATRIX.md"
TRACK_H_BENCHMARK_REPORT_DOC = "docs/specs/perf/TRACK_H_BENCHMARK_REPORT.md"
GRAPH_SURFACE_INPUT_MATRIX_DOC = "docs/specs/perf/GRAPH_SURFACE_INPUT_QA_MATRIX.md"
ARCHITECTURE_REFACTOR_QA_MATRIX_DOC = "docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md"
ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC = (
    "docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md"
)
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC = (
    "docs/specs/perf/ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md"
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC = (
    "docs/specs/perf/COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md"
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_dead_code_hygiene.py --ignore=venv -q"
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_traceability.py"
)
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND = (
    r".\venv\Scripts\python.exe scripts/check_markdown_links.py"
)
COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC = (
    "docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md"
)
COREX_NOVICE_PLUGIN_SDK_FOCUSED_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_novice_plugin_sdk_docs.py "
    r"tests/test_repo_owned_node_documentation.py tests/test_corex_contract_catalog.py "
    r"tests/test_node_title_icon_assets.py tests/test_builtin_function_migration.py "
    r"tests/test_remaining_builtin_function_migration.py tests/test_architecture_boundaries.py "
    r"tests/test_dead_code_hygiene.py --ignore=venv -q"
)
COREX_NOVICE_PLUGIN_SDK_HYGIENE_PYTEST_COMMAND = (
    r".\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py "
    r"tests/test_markdown_hygiene.py tests/test_agent_route_index.py "
    r"tests/test_source_test_file_index.py tests/test_qml_navigation_index.py "
    r"--ignore=venv -q"
)
COREX_NOVICE_PLUGIN_SDK_FULL_COMMAND = (
    r".\venv\Scripts\python.exe .\scripts\run_verification.py "
    r"--mode full --summarize-output"
)
COREX_NOVICE_PLUGIN_SDK_PACKAGE_COMMAND = (
    r".\scripts\build_windows_package.ps1 -PackageProfile base -Clean"
)
CURRENT_CLOSEOUT_QA_MATRIX_DOC = COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC
MARKDOWN_HYGIENE_TEST = "tests/test_markdown_hygiene.py"

ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest "
    "tests/test_architecture_boundaries.py tests/test_shell_isolation_phase.py "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q"
)
ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_traceability.py"
)
ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND = (
    "./venv/Scripts/python.exe scripts/check_markdown_links.py"
)
ARCHITECTURE_RESIDUAL_REFACTOR_PACKET_WRAPUPS = (
    "P01_shell_host_surface_retirement_WRAPUP.md",
    "P02_shell_lifecycle_isolation_hardening_WRAPUP.md",
    "P03_graph_scene_bridge_decomposition_WRAPUP.md",
    "P04_viewer_projection_authority_split_WRAPUP.md",
    "P05_runtime_snapshot_boundary_decoupling_WRAPUP.md",
    "P06_graph_mutation_service_decoupling_WRAPUP.md",
    "P07_shared_runtime_contract_extraction_WRAPUP.md",
)
ARCHITECTURE_RESIDUAL_REFACTOR_SPEC_INDEX_TOKENS = (
    "ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md",
)
ARCHITECTURE_RESIDUAL_REFACTOR_CURRENT_EVIDENCE_TOKENS = (
    ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC,
)

SERIALIZER_BASELINE_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_serializer.py -k passive_image_panel_properties_and_size -q"
)
TRACK_H_REGRESSION_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest "
    "tests/test_track_h_perf_harness.py tests/test_traceability_checker.py -q"
)
GRAPH_CANVAS_SNAPSHOT_COMMAND = (
    "QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe "
    "-m ea_node_editor.ui.perf.performance_harness "
    "--nodes 120 --edges 320 --load-iterations 1 --interaction-samples 10 "
    "--baseline-runs 1 --report-dir artifacts/graph_canvas_perf_docs"
)
GRAPH_CANVAS_STRESS_1200_BASELINE_COMMAND = (
    r".\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness "
    r"--stress-fixture real --load-iterations 1 --interaction-samples 20 "
    r"--baseline-runs 3 "
    r"--report-dir artifacts/graph_canvas_stress_1200_baseline"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_COMMAND = (
    r".\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness "
    r"--stress-fixture real --load-iterations 1 --interaction-samples 5 "
    r"--baseline-runs 1 --capture-qsg-info "
    r"--report-dir artifacts/graph_canvas_stress_1200_display_diagnostics"
)
GRAPH_CANVAS_STRESS_1200_FINAL_COMMAND = (
    r".\venv\Scripts\python.exe -m ea_node_editor.ui.perf.performance_harness "
    r"--stress-fixture real --load-iterations 1 --interaction-samples 20 "
    r"--baseline-runs 3 "
    r"--report-dir artifacts/graph_canvas_stress_1200_final"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_COMMAND = (
    r"$env:QSG_INFO='1'; .\venv\Scripts\python.exe "
    r"-m ea_node_editor.ui.perf.performance_harness --stress-fixture real "
    r"--qml-host qquickview_container --qsg-rhi-backend d3d11 "
    r"--qt-platform windows --baseline-mode interactive --load-iterations 1 "
    r"--interaction-samples 20 --baseline-runs 3 "
    r"--report-dir artifacts/graph_canvas_stress_1200_display_final; "
    r"Remove-Item Env:QSG_INFO -ErrorAction SilentlyContinue"
)
DOCS_RELEASE_TRACEABILITY_PYTEST_COMMAND = (
    "./venv/Scripts/python.exe -m pytest "
    "tests/test_dead_code_hygiene.py tests/test_run_verification.py "
    "tests/test_traceability_checker.py tests/test_markdown_hygiene.py "
    "tests/test_shell_isolation_phase.py --ignore=venv -q"
)
GRAPH_CANVAS_REPORT_DIR = "artifacts/graph_canvas_perf_docs"
TRACK_H_BENCHMARK_ARTIFACT = "artifacts/graph_canvas_perf_docs/TRACK_H_BENCHMARK_REPORT.md"
GRAPH_CANVAS_STRESS_1200_REPORT_DIR = "artifacts/graph_canvas_stress_1200_baseline"
GRAPH_CANVAS_STRESS_1200_BENCHMARK_ARTIFACT = (
    "artifacts/graph_canvas_stress_1200_baseline/TRACK_H_BENCHMARK_REPORT.md"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_REPORT_DIR = (
    "artifacts/graph_canvas_stress_1200_display_diagnostics"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_ARTIFACT = (
    "artifacts/graph_canvas_stress_1200_display_diagnostics/TRACK_H_BENCHMARK_REPORT.md"
)
GRAPH_CANVAS_STRESS_1200_FINAL_REPORT_DIR = "artifacts/graph_canvas_stress_1200_final"
GRAPH_CANVAS_STRESS_1200_FINAL_BENCHMARK_ARTIFACT = (
    "artifacts/graph_canvas_stress_1200_final/TRACK_H_BENCHMARK_REPORT.md"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_REPORT_DIR = (
    "artifacts/graph_canvas_stress_1200_display_final"
)
GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_BENCHMARK_ARTIFACT = (
    "artifacts/graph_canvas_stress_1200_display_final/TRACK_H_BENCHMARK_REPORT.md"
)

XDIST_RESOLUTION_TOKENS = (
    "psutil.cpu_count(logical=True)",
    "os.cpu_count()",
    "1",
)

PROOF_AUDIT_REQUIRED_ARTIFACTS = (
    "ARCHITECTURE.md",
    "README.md",
    "docs/GETTING_STARTED.md",
    PACKAGING_WINDOWS_DOC,
    PILOT_RUNBOOK_DOC,
    SPEC_INDEX_DOC,
    "docs/specs/requirements/80_PERFORMANCE.md",
    QA_ACCEPTANCE_DOC,
    TRACEABILITY_MATRIX_DOC,
    CURRENT_CLOSEOUT_QA_MATRIX_DOC,
    ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC,
    ARCHITECTURE_REFACTOR_QA_MATRIX_DOC,
    GRAPH_CANVAS_PERF_MATRIX_DOC,
    "docs/specs/perf/PASSIVE_NODES_VISUAL_CHECKLIST.md",
    GRAPH_SURFACE_INPUT_MATRIX_DOC,
    VERIFICATION_SPEED_MATRIX_DOC,
    TRACK_H_BENCHMARK_REPORT_DOC,
    "docs/specs/perf/RC_PACKAGING_REPORT.md",
    "docs/specs/perf/PILOT_SIGNOFF.md",
    "scripts/build_windows_package.ps1",
    "scripts/build_windows_installer.ps1",
    CHECK_MARKDOWN_LINKS_SCRIPT,
    "scripts/run_verification.py",
    "scripts/sign_release_artifacts.ps1",
    "scripts/verification_manifest.py",
    "scripts/check_traceability.py",
    "tests/conftest.py",
    MARKDOWN_HYGIENE_TEST,
    "tests/test_dead_code_hygiene.py",
    "tests/test_run_verification.py",
    "tests/test_traceability_checker.py",
    "tests/test_shell_isolation_phase.py",
)


@dataclass(frozen=True)
class PytestPhaseSpec:
    """One non-shell pytest phase in the verification workflow."""

    mode: str
    phase: str
    marker_expression: str
    uses_xdist: bool
    faulthandler_timeout_seconds: int | None
    worker_cap: int | None = None


@dataclass(frozen=True)
class ShellIsolationSpec:
    """Dedicated shell-isolation phase metadata."""

    phase: str
    test_path: str
    target_catalog_paths: tuple[str, ...]
    shell_module_paths: tuple[str, ...]
    shell_module_names: tuple[str, ...]
    faulthandler_timeout_seconds: int
    target_timeout_seconds: int


@dataclass(frozen=True)
class ShellIsolationCatalogSpec:
    """One manifest-owned shell-isolation target catalog."""

    label: str
    module_path: str
    module_name: str
    target_id_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class ShellIsolationOwnershipSpec:
    """Manifest-owned ownership rule for shell-isolated regression surfaces."""

    source_path: str
    coverage_kind: str
    owner_name: str | None = None
    covered_names: tuple[str, ...] = ()
    excluded_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationSuiteSpec:
    """One verification suite and its runner/marker behavior."""

    key: str
    phase: str | None = None
    marker_name: str | None = None
    marker_expression: str | None = None
    uses_xdist: bool = False
    worker_cap: int | None = None
    non_shell_ignore: bool = False
    shell_isolation: bool = False
    faulthandler_timeout_seconds: int | None = None


@dataclass(frozen=True)
class VerificationTestPathSpec:
    """One test path and every verification suite that owns it."""

    path: str
    suites: tuple[str, ...]


@dataclass(frozen=True)
class DocumentRule:
    """Required and forbidden text snippets for a packet-owned proof document."""

    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoLegacyGuardrailSurface:
    """One no-legacy cleanup surface tracked by packet guardrails."""

    category: str
    owner_packet: str
    path: str
    names: tuple[str, ...]
    expectation: str


COREX_NO_LEGACY_GUARDRAIL_PRESENT = "present"
COREX_NO_LEGACY_GUARDRAIL_ABSENT = "absent"
COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT = "path_absent"
COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_WRAPUP_DOC = (
    "docs/specs/work_packets/corex_no_legacy_architecture_cleanup/"
    "P01_no_legacy_guardrails_WRAPUP.md"
)
COREX_NO_LEGACY_REQUIRED_GUARDRAIL_CATEGORIES = (
    "graph_canvas_bridge_edge_adapter",
    "graph_canvas_qml_compat_aliases",
    "graph_canvas_qml_legacy_view_alias",
    "legacy_nodes_public_decorator_barrel",
    "legacy_nodes_types_barrel",
    "legacy_plugin_entry_point_provenance_discovery",
    "legacy_plugin_executable_module_class_probing",
    "legacy_plugin_descriptor_discovery",
    "legacy_plugin_project_entry_point",
    "current_project_schema_validation",
    "current_preference_schema_validation",
    "telemetry_import_shim",
    "package_lazy_import_shims",
    "runtime_project_doc_trigger_compatibility",
    "runtime_project_path_artifact_context",
)
COREX_NO_LEGACY_GUARDRAIL_OWNER_PACKETS = {
    "graph_canvas_bridge_edge_adapter": "P02",
    "graph_canvas_qml_compat_aliases": "P02",
    "graph_canvas_qml_legacy_view_alias": "P02",
    "legacy_nodes_public_decorator_barrel": "P16",
    "legacy_nodes_types_barrel": "P16",
    "legacy_plugin_entry_point_provenance_discovery": "P16",
    "legacy_plugin_executable_module_class_probing": "P16",
    "legacy_plugin_descriptor_discovery": "P16",
    "legacy_plugin_project_entry_point": "P16",
    "current_project_schema_validation": "P06",
    "current_preference_schema_validation": "P06",
    "telemetry_import_shim": "P13",
    "package_lazy_import_shims": "P13",
    "runtime_project_doc_trigger_compatibility": "P11",
    "runtime_project_path_artifact_context": "P11",
}
COREX_NO_LEGACY_GUARDRAIL_INVENTORY = (
    NoLegacyGuardrailSurface(
        category="graph_canvas_bridge_edge_adapter",
        owner_packet="P02",
        path="ea_node_editor/ui_qml/graph_canvas_bridge.py",
        names=(),
        expectation=COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="graph_canvas_qml_compat_aliases",
        owner_packet="P02",
        path="ea_node_editor/ui_qml/components/GraphCanvas.qml",
        names=(
            "_canvasShellCompatRef",
            "_canvasSceneCompatRef",
            "_canvasViewCompatRef",
            "_canvasCompatBridgeRef",
            "graphCanvasFacade",
            "canvasFacadeRef",
            "_facadeService",
            "graphCanvasFacadeAdapter",
            "_canvasStateBridgeRef",
            "_canvasViewStateBridgeRef",
        ),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="graph_canvas_qml_legacy_view_alias",
        owner_packet="P02",
        path="ea_node_editor/ui_qml/components/GraphCanvas.qml",
        names=("_legacyCanvasViewBridgeRef",),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_nodes_public_decorator_barrel",
        owner_packet="P16",
        path="ea_node_editor/nodes/__init__.py",
        names=(
            "node_type",
            "in_port",
            "out_port",
            "prop_str",
            "prop_int",
            "prop_float",
            "prop_interval_1d",
            "prop_bool",
            "prop_enum",
            "prop_json",
        ),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_nodes_types_barrel",
        owner_packet="P16",
        path="ea_node_editor/nodes/types.py",
        names=(),
        expectation=COREX_NO_LEGACY_GUARDRAIL_PATH_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_plugin_entry_point_provenance_discovery",
        owner_packet="P16",
        path="ea_node_editor/nodes/plugin_contracts.py",
        names=("entry_point", "entry_point_name", "distribution_name"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_plugin_entry_point_provenance_discovery",
        owner_packet="P16",
        path="ea_node_editor/nodes/plugin_loader.py",
        names=("EntryPoint", "entry_points", "ea_node_editor.plugins"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_plugin_executable_module_class_probing",
        owner_packet="P16",
        path="ea_node_editor/nodes/plugin_loader.py",
        names=(
            "module_from_spec",
            "exec_module",
            "_legacy_plugin_spec",
            "_register_plugin_classes",
            "__node_type_spec__",
        ),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_plugin_descriptor_discovery",
        owner_packet="P16",
        path="ea_node_editor/nodes/plugin_loader.py",
        names=("PLUGIN_DESCRIPTORS", "discover_package_plugins", "descriptor_overrides"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="legacy_plugin_project_entry_point",
        owner_packet="P16",
        path="pyproject.toml",
        names=("ea_node_editor.plugins",),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="current_project_schema_validation",
        owner_packet="P06",
        path="ea_node_editor/persistence/migration.py",
        names=("JsonProjectMigration", "migrate"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_PRESENT,
    ),
    NoLegacyGuardrailSurface(
        category="current_preference_schema_validation",
        owner_packet="P06",
        path="ea_node_editor/app_preferences.py",
        names=("APP_PREFERENCES_VERSION", "normalize_app_preferences_document"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_PRESENT,
    ),
    NoLegacyGuardrailSurface(
        category="telemetry_import_shim",
        owner_packet="P13",
        path="ea_node_editor/telemetry/performance_harness.py",
        names=("_IMPLEMENTATION_MODULE",),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="package_lazy_import_shims",
        owner_packet="P13",
        path="ea_node_editor/persistence/__init__.py",
        names=("__getattr__",),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="runtime_project_doc_trigger_compatibility",
        owner_packet="P11",
        path="ea_node_editor/execution/runtime_snapshot.py",
        names=("sanitize_execution_trigger",),
        expectation=COREX_NO_LEGACY_GUARDRAIL_ABSENT,
    ),
    NoLegacyGuardrailSurface(
        category="runtime_project_path_artifact_context",
        owner_packet="P11",
        path="ea_node_editor/execution/worker_runtime.py",
        names=("load_runtime_snapshot", "resolve_runtime_artifact_store"),
        expectation=COREX_NO_LEGACY_GUARDRAIL_PRESENT,
    ),
)


FAST_SUITE_KEY = "fast"
FAST_SERIAL_SUITE_KEY = "fast_serial"
GUI_SUITE_KEY = "gui"
GUI_SERIAL_SUITE_KEY = "gui_serial"
SLOW_SUITE_KEY = "slow"
SHELL_SUITE_KEY = "shell"
SHELL_ISOLATION_PHASE_KEY = "shell_isolation"
SHELL_ISOLATION_PHASE_TEST = "tests/test_shell_isolation_phase.py"
FAST_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS = 120
GUI_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS = 300
SLOW_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS = 600
SHELL_ISOLATION_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS = 330
SHELL_ISOLATION_TARGET_TIMEOUT_SECONDS = 360

VERIFICATION_SUITE_SPECS = (
    VerificationSuiteSpec(
        key=FAST_SUITE_KEY,
        phase="fast.pytest",
        marker_expression="not gui and not slow",
        uses_xdist=True,
        faulthandler_timeout_seconds=FAST_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    ),
    VerificationSuiteSpec(
        key=FAST_SERIAL_SUITE_KEY,
        phase="fast.serial.pytest",
        marker_expression="not gui and not slow",
        faulthandler_timeout_seconds=FAST_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    ),
    VerificationSuiteSpec(
        key=GUI_SUITE_KEY,
        phase="gui.pytest",
        marker_name="gui",
        marker_expression="gui and not slow",
        uses_xdist=True,
        worker_cap=MAX_GUI_PARALLEL_WORKERS,
        faulthandler_timeout_seconds=GUI_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    ),
    VerificationSuiteSpec(
        key=GUI_SERIAL_SUITE_KEY,
        phase="gui.serial.pytest",
        marker_expression="gui and not slow",
        faulthandler_timeout_seconds=GUI_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    ),
    VerificationSuiteSpec(
        key=SLOW_SUITE_KEY,
        phase="slow.pytest",
        marker_name="slow",
        marker_expression="slow",
        faulthandler_timeout_seconds=SLOW_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    ),
    VerificationSuiteSpec(
        key=SHELL_SUITE_KEY,
        non_shell_ignore=True,
    ),
    VerificationSuiteSpec(
        key=SHELL_ISOLATION_PHASE_KEY,
        phase="full.shell_isolation.pytest",
        worker_cap=MAX_SHELL_ISOLATION_PARALLEL_WORKERS,
        non_shell_ignore=True,
        shell_isolation=True,
    ),
)
VERIFICATION_SUITE_SPECS_BY_KEY = {spec.key: spec for spec in VERIFICATION_SUITE_SPECS}

FAST_SERIAL_PYTEST_TARGETS = (
    "tests/test_plugin_loader.py::test_bootstrap_import_keeps_builtin_and_public_plugin_routes_lazy",
    (
        "tests/test_external_python_client.py::ExternalPythonSelectionTests::"
        "test_execution_backend_client_uses_application_default_python_policy_for_external_worker"
    ),
    (
        "tests/test_external_python_client.py::ExternalPythonSelectionTests::"
        "test_execution_backend_client_uses_workflow_python_executable_for_external_worker"
    ),
    (
        "tests/test_backend_client.py::BackendSelectionIntegrationTests::"
        "test_headless_runtime_loads_project_selects_workspace_and_runs_without_qapplication"
    ),
    "tests/test_runtime_cli.py::test_runtime_cli_module_help",
    "tests/test_process_client.py::ProcessClientTests",
    "tests/test_scientific_worker_transport.py",
    (
        "tests/test_managed_runtime.py::ManagedRuntimeTests::"
        "test_run_command_streams_output_before_process_finishes"
    ),
    "tests/test_mars_function_migration.py::test_t14_all_three_functions_execute_through_worker_runtime",
    (
        "tests/test_process_run_node.py::ProcessRunNodeTests::"
        "test_stop_run_cancels_active_process_node"
    ),
    "tests/test_mcf_dpf_section_resultants_gui.py",
    "tests/test_jupyter_server_manager.py::JupyterServerManagerIntegrationTests",
    "tests/test_project_file_issues.py",
    (
        "tests/test_workspace_edit_controller.py::"
        "WorkspaceEditControllerCoreTests::"
        "test_paste_nodes_from_clipboard_is_noop_when_clipboard_is_missing"
    ),
)
GUI_SERIAL_PYTEST_TARGETS = (
    (
        "tests/test_docx_rendering_comparison.py::"
        "test_docx_rendering_comparison_single_renderer_smoke"
    ),
    "tests/test_viewer_surface_contract.py",
    "tests/test_flow_edge_labels.py",
)

VERIFICATION_TEST_PATH_SPECS = (
    VerificationTestPathSpec(
        "tests/test_main_window_shell.py",
        (GUI_SUITE_KEY, SHELL_SUITE_KEY),
    ),
    VerificationTestPathSpec(
        "tests/main_window_shell/shell_basics_and_search.py",
        (SHELL_SUITE_KEY,),
    ),
    VerificationTestPathSpec(
        "tests/test_script_editor_dock.py",
        (GUI_SUITE_KEY, SHELL_SUITE_KEY),
    ),
    VerificationTestPathSpec(
        "tests/test_shell_run_controller.py",
        (GUI_SUITE_KEY, SHELL_SUITE_KEY),
    ),
    VerificationTestPathSpec(
        "tests/test_shell_project_session_controller.py",
        (GUI_SUITE_KEY, SHELL_SUITE_KEY),
    ),
    VerificationTestPathSpec(SHELL_ISOLATION_PHASE_TEST, (SHELL_ISOLATION_PHASE_KEY,)),
    VerificationTestPathSpec("tests/test_content_fullscreen_bridge.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_engineering_viewer_widget_binder.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_flow_edge_labels.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_flowchart_surfaces.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_flowchart_visual_polish.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_surface_input_contract.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_surface_input_controls.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_surface_input_inline.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_theme_editor_dialog.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_theme_shell.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graph_track_b.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_graphics_settings_dialog.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_passive_graph_surface_host.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_passive_image_nodes.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_passive_style_dialogs.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_passive_style_presets.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_pdf_preview_provider.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_planning_annotation_catalog.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec(SHELL_WINDOW_LIFECYCLE_TEST_PATH, (SHELL_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_shell_theme.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_viewer_control_bridge.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_viewer_host_service.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_viewer_surface_contract.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_viewer_surface_host.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_workflow_settings_dialog.py", (GUI_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_tabular_benchmark_workbench.py", (SLOW_SUITE_KEY,)),
    VerificationTestPathSpec("tests/test_track_h_perf_harness.py", (SLOW_SUITE_KEY,)),
)


def verification_suite_spec(suite_key: str) -> VerificationSuiteSpec:
    """Return the manifest-owned suite spec for one suite key."""

    return VERIFICATION_SUITE_SPECS_BY_KEY[suite_key]


def suite_test_paths(suite_key: str) -> tuple[str, ...]:
    """Return test paths owned by one verification suite."""

    return tuple(
        spec.path
        for spec in VERIFICATION_TEST_PATH_SPECS
        if suite_key in spec.suites
    )


def _pytest_target_path(target: str) -> str:
    return target.split("::", 1)[0]


def fast_serial_pytest_targets() -> tuple[str, ...]:
    """Return fast tests that should run serially rather than under xdist."""

    return FAST_SERIAL_PYTEST_TARGETS


def fast_serial_pytest_paths() -> tuple[str, ...]:
    """Return file paths that contain manifest-owned serial-fast targets."""

    return tuple(dict.fromkeys(_pytest_target_path(target) for target in FAST_SERIAL_PYTEST_TARGETS))


def fast_serial_pytest_deselect_args() -> tuple[str, ...]:
    """Return pytest arguments that keep serial-fast targets out of xdist."""

    return tuple(f"--deselect={target}" for target in FAST_SERIAL_PYTEST_TARGETS)


def gui_serial_pytest_targets() -> tuple[str, ...]:
    """Return GUI tests that should run serially rather than under xdist."""

    return GUI_SERIAL_PYTEST_TARGETS


def gui_serial_pytest_deselect_args() -> tuple[str, ...]:
    """Return pytest arguments that keep serial GUI targets out of xdist."""

    return tuple(f"--deselect={target}" for target in GUI_SERIAL_PYTEST_TARGETS)


def pytest_marker_path_sets() -> dict[str, frozenset[str]]:
    """Return marker names and the paths that should receive each marker."""

    marked_paths: dict[str, set[str]] = {}
    for suite_spec in VERIFICATION_SUITE_SPECS:
        if suite_spec.marker_name is None:
            continue
        marked_paths.setdefault(suite_spec.marker_name, set()).update(
            suite_test_paths(suite_spec.key)
        )
    return {
        marker_name: frozenset(paths)
        for marker_name, paths in sorted(marked_paths.items())
    }


def non_shell_pytest_ignore_paths() -> tuple[str, ...]:
    """Return tests that must run outside non-shell pytest phases."""

    ignored_suite_keys = tuple(
        spec.key for spec in VERIFICATION_SUITE_SPECS if spec.non_shell_ignore
    )
    return tuple(
        path_spec.path
        for path_spec in VERIFICATION_TEST_PATH_SPECS
        if any(suite_key in path_spec.suites for suite_key in ignored_suite_keys)
    )


def heavy_parallelism_test_paths() -> frozenset[str]:
    """Return focused direct-pytest targets that should not get default xdist."""

    heavy_suite_keys = {
        spec.key
        for spec in VERIFICATION_SUITE_SPECS
        if (spec.marker_name is not None or spec.non_shell_ignore)
        and not spec.shell_isolation
    }
    heavy_paths = {
        path_spec.path
        for path_spec in VERIFICATION_TEST_PATH_SPECS
        if any(suite_key in path_spec.suites for suite_key in heavy_suite_keys)
    }
    heavy_paths.update(fast_serial_pytest_paths())
    return frozenset(heavy_paths)


SHELL_BACKED_TEST_PATHS = suite_test_paths(SHELL_SUITE_KEY)
SHELL_BACKED_TEST_MODULES = tuple(
    path.removesuffix(".py").replace("/", ".") for path in SHELL_BACKED_TEST_PATHS
)
NON_SHELL_PYTEST_IGNORES = non_shell_pytest_ignore_paths()
_PYTEST_MARKER_PATH_SETS = pytest_marker_path_sets()
GUI_TEST_PATHS = tuple(sorted(_PYTEST_MARKER_PATH_SETS["gui"]))
SLOW_TEST_PATHS = tuple(sorted(_PYTEST_MARKER_PATH_SETS["slow"]))

PYTEST_PHASE_SPECS = tuple(
    PytestPhaseSpec(
        mode=spec.key,
        phase=spec.phase,
        marker_expression=spec.marker_expression,
        uses_xdist=spec.uses_xdist,
        faulthandler_timeout_seconds=spec.faulthandler_timeout_seconds,
        worker_cap=spec.worker_cap,
    )
    for spec in VERIFICATION_SUITE_SPECS
    if spec.phase is not None and spec.marker_expression is not None
)
PYTEST_PHASE_SPECS_BY_MODE = {spec.mode: spec for spec in PYTEST_PHASE_SPECS}

SHELL_ISOLATION_CATALOG_SPECS = (
    ShellIsolationCatalogSpec(
        label="main-window",
        module_path="tests/shell_isolation_main_window_targets.py",
        module_name="tests.shell_isolation_main_window_targets",
        target_id_prefixes=("main_window__",),
    ),
    ShellIsolationCatalogSpec(
        label="controllers",
        module_path="tests/shell_isolation_controller_targets.py",
        module_name="tests.shell_isolation_controller_targets",
        target_id_prefixes=(
            "script_editor__",
            "run_controller__",
            "project_session__",
        ),
    ),
)
SHELL_ISOLATION_TARGET_CATALOG_PATHS = tuple(
    spec.module_path for spec in SHELL_ISOLATION_CATALOG_SPECS
)
_SHELL_ISOLATION_SUITE_SPEC = verification_suite_spec(SHELL_ISOLATION_PHASE_KEY)
_SHELL_ISOLATION_TEST_PATHS = suite_test_paths(SHELL_ISOLATION_PHASE_KEY)
if _SHELL_ISOLATION_SUITE_SPEC.phase is None:
    raise ValueError("The shell-isolation suite must define a verification phase.")
if len(_SHELL_ISOLATION_TEST_PATHS) != 1:
    raise ValueError("The shell-isolation suite must own exactly one phase test path.")

SHELL_ISOLATION_SPEC = ShellIsolationSpec(
    phase=_SHELL_ISOLATION_SUITE_SPEC.phase,
    test_path=_SHELL_ISOLATION_TEST_PATHS[0],
    target_catalog_paths=SHELL_ISOLATION_TARGET_CATALOG_PATHS,
    shell_module_paths=SHELL_BACKED_TEST_PATHS,
    shell_module_names=SHELL_BACKED_TEST_MODULES,
    faulthandler_timeout_seconds=SHELL_ISOLATION_PYTEST_FAULTHANDLER_TIMEOUT_SECONDS,
    target_timeout_seconds=SHELL_ISOLATION_TARGET_TIMEOUT_SECONDS,
)

SHELL_ISOLATION_OWNERSHIP_SPECS = (
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/group_backdrop_integration.py",
        coverage_kind="method_targets",
        owner_name="MainWindowShellGroupBackdropIntegrationTests",
        covered_names=(
            "test_group_library_add_drop_and_current_empty_title_fallback",
            "test_plain_c_wrap_shortcut_does_not_collide_with_group_shortcuts",
            "test_peek_inside_action_is_collapsed_group_only",
            "test_comment_peek_filters_members_keeps_scope_and_supports_both_exit_paths",
        ),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/test_main_window_shell.py",
        coverage_kind="class_targets",
        excluded_names=(
            "MainWindowShellContextBootstrapTests",
            "MainWindowGraphCanvasSplitBridgeTests",
            "ShellWorkspaceBridgeQmlBoundaryTests",
            "GraphCanvasQmlBoundaryTests",
            "MainWindowNodeExecutionCanvasTests",
            "MainWindowShellHostFacadeDelegationTests",
        ),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/drop_connect_and_workflow_io.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/edit_clipboard_history.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/passive_image_nodes.py",
        coverage_kind="class_targets",
        covered_names=("MainWindowShellPassiveImageNodesTests",),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/passive_pdf_nodes.py",
        coverage_kind="class_targets",
        covered_names=("MainWindowShellPassivePdfNodesTests",),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/passive_property_editors.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/passive_style_context_menus.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/shell_basics_and_search.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/shell_runtime_contracts.py",
        coverage_kind="class_targets",
        covered_names=(
            "MainWindowShellTelemetryTests",
            "MainWindowShellBootstrapCompositionTests",
            "MainWindowShellContextBootstrapTests",
            "MainWindowShellHostProtocolStateTests",
            "_MainWindowShellGraphCanvasHostDirectTests",
        ),
        excluded_names=("FrameRateSamplerTests",),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/main_window_shell/view_library_inspector.py",
        coverage_kind="module_target",
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/test_script_editor_dock.py",
        coverage_kind="method_targets",
        owner_name="ScriptEditorDockTests",
        covered_names=(
            "test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor",
            "test_script_editor_binds_to_selected_python_script_node",
            "test_script_editor_state_persists_in_metadata",
            "test_script_editor_exposes_cursor_diagnostics_and_dirty_state",
            "test_set_script_editor_panel_visible_focuses_editor_for_script_node",
            "test_script_apply_failure_keeps_draft_dirty",
            "test_numeric_overflow_draft_stays_dirty_and_leaves_graph_unchanged",
            "test_script_apply_failure_draft_survives_panel_reopen",
            "test_script_draft_survives_same_node_property_refresh",
        ),
        excluded_names=("test_script_editor_panel_width_persists_in_metadata",),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/test_shell_run_controller.py",
        coverage_kind="method_targets",
        owner_name="ShellRunControllerTests",
        excluded_names=(
            "test_node_execution_visualization_shell_events_drive_graph_node_chrome_states",
            "test_node_execution_visualization_failure_priority_overrides_completed_chrome",
            "test_node_settled_failure_hides_elapsed_timer_for_failed_running_node",
            "test_viewer_session_bridge_context_property_exists_and_rerun_invalidates_current_workspace",
            "test_shell_context_bridge_fallbacks_wrap_shell_window_with_focused_sources",
            "test_fatal_run_failed_event_invalidates_viewer_sessions_as_worker_reset",
            "test_node_settled_artifact_ref_payload_keeps_run_ui_running",
            "test_new_run_clears_failed_node_highlight_before_start",
            "test_developer_mode_toggle_is_gated_by_capability",
            "test_run_carries_developer_mode_only_when_capability_and_active",
            "test_warning_node_settled_event_marks_golden_chrome_and_logs_without_failure_focus",
        ),
    ),
    ShellIsolationOwnershipSpec(
        source_path="tests/test_shell_project_session_controller.py",
        coverage_kind="scenario_targets",
        owner_name="ShellProjectSessionControllerTests",
        covered_names=(
            "test_session_restore_recovers_workspace_order_active_workspace_and_view_camera",
            "test_open_project_rejects_saved_node_when_startup_preferences_disable_addon",
            "test_autosave_tick_writes_snapshot_and_keeps_valid_project_doc",
            "test_recovery_prompt_accept_loads_newer_autosave",
            "test_recovery_prompt_reject_keeps_empty_startup_project_and_discards_autosave",
            "test_restore_session_handles_corrupted_session_and_autosave_files",
            "test_recovery_prompt_is_deferred_until_main_window_is_visible",
        ),
        excluded_names=(
            "test_saved_project_reopen_seeds_run_required_viewer_projection_without_persisting_live_transport",
            "test_session_restore_recovers_unsaved_temp_staged_refs_without_autosave",
            "test_recovery_prompt_accept_recovers_unsaved_temp_staged_refs",
            "test_session_restore_keeps_saved_project_recent_but_starts_empty",
            "test_clean_close_discards_staged_scratch_and_clears_unsaved_root_hint",
            "test_explicit_save_promotes_referenced_staged_refs",
            "test_save_as_default_copy_switches_project_path_and_excludes_staging",
            "test_new_project_uses_navigation_controller_surface_without_workspace_library_facade",
            "test_project_files_menu_action_triggers_dialog",
            "test_save_prompt_receives_project_file_summary_before_saving",
            "test_open_project_path_can_abort_when_project_files_summary_has_staged_and_broken_entries",
            "test_recovery_prompt_receives_project_file_summary_for_recovered_project",
        ),
    ),
    ShellIsolationOwnershipSpec(
        source_path=SHELL_WINDOW_LIFECYCLE_TEST_PATH,
        coverage_kind="function_targets",
        covered_names=(
            "test_application_inactive_clears_immediately_and_cancels_queued_deactivation",
            "test_close_releases_viewer_host_service_overlay_manager",
            "test_close_skips_deferred_autosave_recovery_after_teardown_starts",
            "test_content_fullscreen_bridge_closes_during_project_reset_lifecycle",
            "test_content_fullscreen_overlay_closes_open_state_with_escape_and_f11",
            "test_content_fullscreen_overlay_exposes_viewer_viewport_placeholder_contract",
            "test_content_fullscreen_overlay_owns_animated_image_playback",
            "test_content_fullscreen_overlay_preserves_cropped_image_source_aspect",
            "test_content_fullscreen_overlay_renders_image_media_and_keeps_node_state_read_only",
            "test_content_fullscreen_overlay_renders_pdf_media_blocks_background_and_close_button",
            "test_content_fullscreen_overlay_renders_video_media_and_persists_close_state",
            "test_create_shell_window_factory_tracks_application_state_signal_for_teardown",
            "test_empty_shell_configures_tabular_policy_without_allocating_shared_service",
            "test_shared_shell_reset_reapplies_tabular_policy_after_service_reset",
            "test_shell_window_can_use_opt_in_qquickview_container_host",
            "test_shell_window_close_allows_repeated_in_process_cycles",
            "test_shell_window_exposes_qtquick_backend_debug_payload",
            "test_window_deactivate_coalesces_duplicate_events_and_clears_unowned_focus",
        ),
    ),
)

RUN_VERIFICATION_MODE_SEQUENCE = {
    "fast": ("fast", FAST_SERIAL_SUITE_KEY),
    "gui": (QML_QUICK_PHASE_KEY, "gui", GUI_SERIAL_SUITE_KEY),
    "slow": ("slow",),
    "full": (
        "fast",
        FAST_SERIAL_SUITE_KEY,
        QML_QUICK_PHASE_KEY,
        "gui",
        GUI_SERIAL_SUITE_KEY,
        "slow",
        SHELL_ISOLATION_PHASE_KEY,
    ),
}


def non_shell_pytest_ignore_args() -> tuple[str, ...]:
    """Return the documented pytest ignore arguments for non-shell phases."""

    return tuple(f"--ignore={path}" for path in NON_SHELL_PYTEST_IGNORES)


def worktree_pytest_ignore_args() -> tuple[str, ...]:
    """Return pytest ignore arguments required by packet worktrees."""

    return tuple(f"--ignore={path}" for path in WORKTREE_PYTEST_IGNORE_PATHS)


def pytest_faulthandler_timeout_args(timeout_seconds: int | None) -> tuple[str, ...]:
    """Return pytest config override args for one phase's faulthandler timeout."""

    if timeout_seconds is None:
        return ()
    return ("-o", f"faulthandler_timeout={timeout_seconds}")


def run_verification_command(mode: str, *, dry_run: bool = False) -> str:
    """Return the documented developer-facing verification command."""

    argv = [LOCAL_VENV_PYTHON_DISPLAY, RUN_VERIFICATION_SCRIPT, "--mode", mode]
    if dry_run:
        argv.append("--dry-run")
    return " ".join(argv)


def shell_isolation_phase_pytest_args(
    worker_count: int | str | None = "<resolved_count>",
) -> tuple[str, ...]:
    """Return argv for the dedicated shell-isolation pytest phase."""

    argv = (
        "-m",
        "pytest",
        *pytest_faulthandler_timeout_args(SHELL_ISOLATION_SPEC.faulthandler_timeout_seconds),
        *worktree_pytest_ignore_args(),
        SHELL_ISOLATION_PHASE_TEST,
        "-q",
    )
    if worker_count is not None:
        return (*argv, "-n", str(worker_count), "--dist", "load")
    return argv


def shell_isolation_pytest_command(worker_count: int | str | None = "<resolved_count>") -> str:
    """Return the documented dedicated shell-isolation pytest command."""

    argv = [
        "QT_QPA_PLATFORM=offscreen",
        LOCAL_VENV_PYTHON_DISPLAY,
        *shell_isolation_phase_pytest_args(worker_count),
    ]
    return " ".join(argv)


def shell_isolation_target_catalog_module_names() -> tuple[str, ...]:
    """Return the target catalog module names for shell-isolated child runs."""

    return tuple(spec.module_name for spec in SHELL_ISOLATION_CATALOG_SPECS)


def shell_isolation_target_id_prefixes() -> tuple[str, ...]:
    """Return the owned target-id prefixes across all shell-isolation catalogs."""

    return tuple(
        prefix
        for spec in SHELL_ISOLATION_CATALOG_SPECS
        for prefix in spec.target_id_prefixes
    )


def shell_isolation_ownership_specs_by_path() -> dict[str, ShellIsolationOwnershipSpec]:
    """Return manifest-owned shell-isolation ownership rules keyed by source path."""

    return {spec.source_path: spec for spec in SHELL_ISOLATION_OWNERSHIP_SPECS}


def shell_isolation_target_pytest_args(*nodeids: str) -> tuple[str, ...]:
    """Return argv for one or more shell-isolated pytest child targets."""

    if not nodeids:
        raise ValueError("shell_isolation_target_pytest_args requires at least one nodeid.")
    return ("-m", "pytest", *worktree_pytest_ignore_args(), *nodeids, "-q")


def shell_direct_unittest_commands() -> tuple[str, ...]:
    """Return the focused module-level shell rerun commands."""

    return tuple(
        f"QT_QPA_PLATFORM=offscreen {LOCAL_VENV_PYTHON_DISPLAY} -m unittest {module_name} -v"
        for module_name in SHELL_BACKED_TEST_MODULES
    )


def proof_audit_command() -> str:
    """Return the canonical proof-audit command."""

    return f"{LOCAL_VENV_PYTHON_DISPLAY} {CHECK_TRACEABILITY_SCRIPT}"


GENERIC_DOCUMENT_RULES: dict[str, DocumentRule] = {
    "README.md": DocumentRule(
        required=(
            CHECK_TRACEABILITY_SCRIPT,
            CHECK_MARKDOWN_LINKS_SCRIPT,
            "Graph Surface Input QA Matrix",
            "Verification Speed QA Matrix",
            "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
            "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
            "dedicated fresh-process shell-isolation phase",
            "ea_node_editor.bootstrap",
            SHELL_ISOLATION_SPEC.test_path,
            "proof-audit command",
            "SHELL_ISOLATION_CATALOG_SPECS",
            "fast.serial.pytest",
        ),
        forbidden=(
            "Only the retained `PROJECT_MANAGED_FILES` packet window",
            "serializer caveat.",
            "shell-wrapper suites for isolated `unittest` execution",
        ),
    ),
    "docs/GETTING_STARTED.md": DocumentRule(
        required=(
            CHECK_TRACEABILITY_SCRIPT,
            CHECK_MARKDOWN_LINKS_SCRIPT,
            SHELL_ISOLATION_SPEC.test_path,
            XDIST_RESOLUTION_TOKENS[0],
            "ARCHITECTURE_REFACTOR_QA_MATRIX.md",
            "dedicated fresh-process",
            "serializer spot-check",
            "no longer carries that",
            "benchmark evidence",
            "fast.serial.pytest",
        ),
        forbidden=(
            "Only the retained `PROJECT_MANAGED_FILES` packet window",
            "remains a separate persistence follow-up",
            "isolated module-level",
        ),
    ),
    "ARCHITECTURE.md": DocumentRule(
        required=(
            CHECK_TRACEABILITY_SCRIPT,
            CHECK_MARKDOWN_LINKS_SCRIPT,
            CURRENT_CLOSEOUT_QA_MATRIX_DOC,
            "focused bridges",
            "17-name top-level `corex` SDK",
            "immutable content-addressed generation",
            "snapshot-only",
            "ea_node_editor.ui.perf.performance_harness",
            "tests/shell_isolation_runtime.py",
        ),
        forbidden=(
            "The P12 closeout sweep",
            "ea_node_editor.telemetry.performance_harness",
            "project_path rebuild",
            "constructor fallback preserved",
            "`main.py` is a launcher shim",
            "durable compatibility through serializer + migration",
        ),
    ),
    SPEC_INDEX_DOC: DocumentRule(
        required=(
            "ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md",
            "COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX.md",
            "ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md",
            "PROJECT_MANAGED_FILES_QA_MATRIX.md",
            "COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md",
            "PLUGIN_AUTHORING_GUIDE.md",
            "PLUGIN_MIGRATION_GUIDE.md",
            "historical pointer",
        ),
        forbidden=(),
    ),
    PACKAGING_WINDOWS_DOC: DocumentRule(
        required=(
            ".\\scripts\\build_windows_package.ps1 -PackageProfile base -Clean",
            ".\\scripts\\build_windows_package.ps1 -PackageProfile viewer -Clean -SkipSmoke",
            ".\\scripts\\build_windows_package.ps1 -PackageProfile full -Clean -SkipSmoke",
            "artifacts\\pyinstaller\\dist\\base\\COREX_Node_Editor\\",
            "artifacts\\pyinstaller\\dist\\viewer\\COREX_Node_Editor\\",
            "artifacts\\pyinstaller\\dist\\full\\COREX_Node_Editor\\",
            ".\\scripts\\build_windows_installer.ps1 -PackageProfile base",
            ".\\scripts\\build_windows_installer.ps1 -PackageProfile full",
            ".\\scripts\\sign_release_artifacts.ps1 -PackageProfile base -VerifyOnly",
            ".\\scripts\\sign_release_artifacts.ps1 -PackageProfile full -VerifyOnly",
            "artifacts\\releases\\signing\\base\\",
            "artifacts\\releases\\signing\\full\\",
            "tests/test_packaging_configuration.py",
        ),
        forbidden=(
            "RC3",
            "artifacts\\pyinstaller\\dist\\COREX_Node_Editor\\COREX_Node_Editor.exe",
        ),
    ),
    PILOT_RUNBOOK_DOC: DocumentRule(
        required=(
            "build_windows_package.ps1 -PackageProfile base -Clean",
            "build_windows_installer.ps1 -PackageProfile base",
            "artifacts\\pyinstaller\\dist\\base\\COREX_Node_Editor\\COREX_Node_Editor.exe",
            "Package Profile: <base|viewer|web|full>",
            "artifacts\\pyinstaller\\dist\\full\\COREX_Node_Editor\\COREX_Node_Editor.exe",
            "ARCHITECTURE_REFACTOR_QA_MATRIX.md",
            "PILOT_SIGNOFF.md",
        ),
        forbidden=(
            "RC1",
            "PILOT_BACKLOG.md",
        ),
    ),
    ARCHITECTURE_REFACTOR_QA_MATRIX_DOC: DocumentRule(
        required=(
            "Historical pointer",
            ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
        ),
        forbidden=(
            "## 2026-03-27 Execution Results",
            "tests/test_packaging_configuration.py",
        ),
    ),
    QA_ACCEPTANCE_DOC: DocumentRule(
        forbidden=(
            "the four shell-wrapper modules `tests.test_main_window_shell`, "
            "`tests.test_script_editor_dock`, `tests.test_shell_run_controller`, and "
            "`tests.test_shell_project_session_controller` shall remain on explicit "
            "fresh-process `unittest` execution",
            "on separate `unittest` commands after the pytest phases",
        ),
    ),
    GRAPH_SURFACE_INPUT_MATRIX_DOC: DocumentRule(
        required=(
            "## Shell Verification Policy",
            "Both module-level shell wrappers passed directly",
        ),
        forbidden=(
            "wrapper instability (`code 5`)",
            "approved fresh-process fallback completed",
        ),
    ),
    "docs/specs/requirements/80_PERFORMANCE.md": DocumentRule(
        required=(
            "GraphCanvas.qml",
            "GRAPH_CANVAS_PERF_QA_MATRIX.md",
            "performance_acceptance_result",
        ),
    ),
    "docs/specs/perf/RC_PACKAGING_REPORT.md": DocumentRule(
        required=(
            "Evidence Status: Archived 2026-03-01 packaging smoke snapshot.",
            "Current release proof lives in `docs/PACKAGING_WINDOWS.md` and "
            "`docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md`.",
            "## Archived 2026-03-01 Snapshot",
        ),
    ),
    "docs/specs/perf/PILOT_SIGNOFF.md": DocumentRule(
        required=(
            "Evidence Status: Archived 2026-03-01 packaged desktop pilot snapshot.",
            "Current pilot proof must be rerun from `docs/PILOT_RUNBOOK.md` and "
            "tracked in `docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md`.",
            "## Archived 2026-03-01 Snapshot",
        ),
    ),
}

QA_ACCEPTANCE_REQUIREMENT_TOKENS = {
    "REQ-QA-014": (RUN_VERIFICATION_SCRIPT, *MODE_NAMES),
    "REQ-QA-015": (SHELL_ISOLATION_SPEC.test_path, *SHELL_ISOLATION_SPEC.shell_module_names),
    "REQ-QA-016": ("pytest-xdist", *XDIST_RESOLUTION_TOKENS),
    "REQ-QA-017": ("baseline failures", "fully green aggregate"),
    "REQ-QA-018": ("GraphCanvas.qml", "interactive desktop/manual follow-up"),
    "REQ-QA-025": (
        CHECK_MARKDOWN_LINKS_SCRIPT,
        PACKAGING_WINDOWS_DOC,
        PILOT_RUNBOOK_DOC,
        SPEC_INDEX_DOC,
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
    ),
    "AC-REQ-QA-014-01": (
        run_verification_command("full", dry_run=True),
        VERIFICATION_SPEED_MATRIX_DOC,
    ),
    "AC-REQ-QA-015-01": (
        SHELL_ISOLATION_SPEC.test_path,
        *SHELL_ISOLATION_SPEC.shell_module_names,
    ),
    "AC-REQ-QA-016-01": (VERIFICATION_SPEED_MATRIX_DOC,),
    "AC-REQ-QA-018-01": (
        GRAPH_CANVAS_SNAPSHOT_COMMAND,
        proof_audit_command(),
        GRAPH_CANVAS_PERF_MATRIX_DOC,
        TRACK_H_BENCHMARK_REPORT_DOC,
    ),
    "AC-REQ-QA-025-01": (
        DOCS_RELEASE_TRACEABILITY_PYTEST_COMMAND,
        proof_audit_command(),
        f"{LOCAL_VENV_PYTHON_DISPLAY} {CHECK_MARKDOWN_LINKS_SCRIPT}",
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
    ),
    "REQ-QA-029": (
        "ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md",
        "`P01` through `P07`",
        "`P08`",
        "docs/specs/INDEX.md",
        "manual desktop checks inherited from the packet-set wrap-ups",
    ),
    "AC-REQ-QA-029-01": (
        ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND,
        ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND,
        ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND,
        "ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md",
    ),
    "REQ-QA-042": (
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC,
        "accepted `COREX_NO_LEGACY_ARCHITECTURE_CLEANUP` packet commits",
        "focused bridges",
        "explicit source contracts",
        "current-schema persistence",
        "descriptor-only plugins/add-ons",
        "snapshot-only runtime payloads",
        "typed viewer transport",
        "canonical launch/import paths",
    ),
    "AC-REQ-QA-042-01": (
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC,
    ),
    "REQ-QA-051": (
        "planned requirement",
        "NOT IMPLEMENTED",
        "NO IMPLEMENTATION PROOF",
        "NOT RELEASED",
    ),
    "AC-REQ-QA-051-01": (
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        "planned requirement",
    ),
    "REQ-QA-055": (
        COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC,
        "139-type migration inventory",
        "17-name public export set",
        "full summarized verification",
        "Windows package smoke",
        "NOT RUN",
    ),
    "AC-REQ-QA-055-01": (
        "task-owned parser",
        "check_traceability.py",
        "check_markdown_links.py",
        "check_agent_maps.py",
        "run_verification.py --mode full --summarize-output",
        "build_windows_package.ps1 -PackageProfile base -Clean",
        COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_DOC,
    ),
}

NOVICE_PLUGIN_SDK_REQUIREMENT_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/specs/requirements/20_UI_UX.md": {
        "REQ-UI-065": (
            "New Plugin...",
            "Reload Plugins",
            "no-clobber",
            "active run",
            "Plugin Authoring Guide",
        ),
        "AC-REQ-UI-065-01": ("Native-dialog", "static-declaration", "atomic-reload"),
    },
    "docs/specs/requirements/40_NODE_SDK.md": {
        "REQ-NODE-050": (
            "17 public names",
            "literal-only AST discovery",
            "76-function",
            "53-trusted-exception",
        ),
        "AC-REQ-NODE-050-01": ("exact 17-name export set", "hostile-source non-execution"),
    },
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md": {
        "REQ-NODE-051": (
            "isolated process worker",
            "immutable controls-only",
            "presence",
            "future and unimplemented",
        ),
        "AC-REQ-NODE-051-01": ("falsey override presence", "sequential ordered warnings"),
    },
    "docs/specs/requirements/50_EXECUTION_ENGINE.md": {
        "REQ-EXEC-028": (
            "PluginBundleRef",
            "registry-contract fingerprint",
            "digest-derived module names",
            "never import unused plugins",
        ),
        "AC-REQ-EXEC-028-01": ("exact-byte verification", "rejection of stale"),
    },
    "docs/specs/requirements/60_PERSISTENCE.md": {
        "REQ-PERSIST-031": (
            "shall never enter `.cxproj`",
            "Custom Workflow",
            "`REQ-PERSIST-030`",
            "refuse before any package file",
        ),
        "AC-REQ-PERSIST-031-01": ("no public-plugin source", "incompatible change"),
    },
    "docs/specs/requirements/70_INTEGRATIONS.md": {
        "REQ-INT-021": (
            "schema 2",
            "64 KiB",
            "16 MiB",
            "execute no public source",
            "exact `<module> is not included in this COREX bundle.` message",
        ),
        "AC-REQ-INT-021-01": ("deterministic-archive", "legacy-removal"),
    },
}

PLANNED_REQUIREMENT_STATUSES = {
    "Capability Status": "PLANNED",
    "Implementation Status": "NOT IMPLEMENTED",
    "Acceptance Status": "NOT RUN",
    "Implementation Proof": "NO IMPLEMENTATION PROOF",
    "Release Status": "NOT RELEASED",
}

PLANNED_REQUIREMENT_DOCS = {
    "10_ARCHITECTURE": "docs/specs/requirements/10_ARCHITECTURE.md",
    "20_UI_UX": "docs/specs/requirements/20_UI_UX.md",
    "40_NODE_SDK": "docs/specs/requirements/40_NODE_SDK.md",
    "45_NODE_EXECUTION_MODEL": "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md",
    "50_EXECUTION_ENGINE": "docs/specs/requirements/50_EXECUTION_ENGINE.md",
    "60_PERSISTENCE": "docs/specs/requirements/60_PERSISTENCE.md",
    "70_INTEGRATIONS": "docs/specs/requirements/70_INTEGRATIONS.md",
    "90_QA_ACCEPTANCE": "docs/specs/requirements/90_QA_ACCEPTANCE.md",
}

REQUIREMENT_DEFINITION_DOCS = (
    "docs/specs/requirements/10_ARCHITECTURE.md",
    "docs/specs/requirements/20_UI_UX.md",
    "docs/specs/requirements/30_GRAPH_MODEL.md",
    "docs/specs/requirements/40_NODE_SDK.md",
    "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md",
    "docs/specs/requirements/50_EXECUTION_ENGINE.md",
    "docs/specs/requirements/60_PERSISTENCE.md",
    "docs/specs/requirements/70_INTEGRATIONS.md",
    "docs/specs/requirements/80_PERFORMANCE.md",
    "docs/specs/requirements/90_QA_ACCEPTANCE.md",
)

PLANNED_REQUIREMENT_OWNERS = {
    "REQ-ARCH-020": "10_ARCHITECTURE",
    "REQ-UI-051": "20_UI_UX",
    "REQ-UI-052": "20_UI_UX",
    "REQ-UI-053": "20_UI_UX",
    "REQ-UI-054": "20_UI_UX",
    "REQ-UI-055": "20_UI_UX",
    "REQ-UI-056": "20_UI_UX",
    "REQ-UI-057": "20_UI_UX",
    "REQ-UI-058": "20_UI_UX",
    "REQ-NODE-036": "40_NODE_SDK",
    "REQ-NODE-037": "40_NODE_SDK",
    "REQ-EXEC-018": "50_EXECUTION_ENGINE",
    "REQ-EXEC-019": "50_EXECUTION_ENGINE",
    "REQ-EXEC-020": "50_EXECUTION_ENGINE",
    "REQ-EXEC-021": "50_EXECUTION_ENGINE",
    "REQ-EXEC-022": "50_EXECUTION_ENGINE",
    "REQ-PERSIST-025": "60_PERSISTENCE",
    "REQ-INT-018": "70_INTEGRATIONS",
    "REQ-INT-019": "70_INTEGRATIONS",
}

CAPABILITY_GROUPS = (
    (
        "SYN-OPP-0001",
        "Linked workflow instances",
        ("REQ-PERSIST-025", "REQ-UI-051"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0002",
        "Durable solution snapshots and incremental recomputation",
        ("REQ-EXEC-017", "REQ-PERSIST-026", "REQ-UI-052"),
        "PARTIAL",
    ),
    (
        "SYN-OPP-0003",
        "Unified workflow interface semantics",
        ("REQ-NODE-036", "REQ-UI-053"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0004",
        "Dependency and provenance inspector",
        ("REQ-EXEC-018", "REQ-UI-054"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0005",
        "Reproducible debug bundles",
        ("REQ-EXEC-019", "REQ-UI-055"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0006",
        "Secure remote execution",
        ("REQ-EXEC-020", "REQ-INT-018", "REQ-UI-056"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0007",
        "Solver-neutral FEA process contracts",
        ("REQ-NODE-037", "REQ-EXEC-021", "REQ-INT-019", "REQ-UI-057"),
        "PLANNED",
    ),
    (
        "SYN-OPP-0008",
        "Permissioned agent orchestration",
        ("REQ-ARCH-020", "REQ-EXEC-022", "REQ-UI-058"),
        "PLANNED",
    ),
)

VERIFICATION_SPEED_FORBIDDEN_TOKENS = (
    "isolated shell-wrapper `unittest` phase",
    "adds `-n auto` only when `pytest-xdist` is importable in the project venv",
)
VERIFICATION_SPEED_WORKFLOW_NOTE_TOKENS = {
    "fast": (
        "pytest-xdist",
        XDIST_RESOLUTION_TOKENS[0],
        "not gui and not slow",
        "fast.serial.pytest",
        SHELL_ISOLATION_SPEC.test_path,
    ),
    "gui": (
        "pytest-xdist",
        XDIST_RESOLUTION_TOKENS[0],
        str(MAX_GUI_PARALLEL_WORKERS),
        SHELL_ISOLATION_SPEC.test_path,
    ),
    "slow": ("Serial", SHELL_ISOLATION_SPEC.test_path),
    "full": ("--dry-run",),
}
VERIFICATION_SPEED_SHELL_RULE_TOKENS = (
    *non_shell_pytest_ignore_args(),
    shell_isolation_pytest_command(),
    *XDIST_RESOLUTION_TOKENS,
    *shell_direct_unittest_commands(),
)
VERIFICATION_SPEED_ENVIRONMENT_NOTE_TOKENS = (
    LOCAL_VENV_PYTHON_DISPLAY,
    "pytest-xdist",
    XDIST_RESOLUTION_TOKENS[0],
    str(MAX_GUI_PARALLEL_WORKERS),
)
VERIFICATION_SPEED_COMPANION_PROOF_TOKENS = (
    proof_audit_command(),
    CHECK_TRACEABILITY_SCRIPT,
)
VERIFICATION_SPEED_BASELINE_REQUIRED_TOKENS = (
    SERIALIZER_BASELINE_COMMAND,
    "retired",
    "No known out-of-scope verification baseline failures remain",
)
VERIFICATION_SPEED_BASELINE_FORBIDDEN_TOKENS = (
    "serializer baseline remains open",
    "still fails because passive image-panel round-trips add default crop fields",
)
VERIFICATION_SPEED_RESULT_COMMANDS = (
    run_verification_command("full", dry_run=True),
    SERIALIZER_BASELINE_COMMAND,
)
VERIFICATION_SPEED_SHELL_RESULT_COMMAND_PREFIX = shell_isolation_pytest_command(
    worker_count=None
)
VERIFICATION_SPEED_SHELL_RESULT_REQUIRED_TOKENS = ("--dist load",)

GRAPH_CANVAS_PERF_REQUIRED_TOKENS = (
    "## Locked Benchmark Contract",
    "GraphCanvas.qml",
    "## Desktop/Manual Follow-Up",
    "desktop/manual",
    "outstanding",
)
GRAPH_CANVAS_PERF_AUDIT_COMMANDS = (
    TRACK_H_REGRESSION_COMMAND,
    GRAPH_CANVAS_SNAPSHOT_COMMAND,
    GRAPH_CANVAS_STRESS_1200_BASELINE_COMMAND,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_COMMAND,
    GRAPH_CANVAS_STRESS_1200_FINAL_COMMAND,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_COMMAND,
    proof_audit_command(),
)

TRACK_H_REPORT_REQUIRED_TOKENS = (
    "GraphCanvas.qml",
    "offscreen regression snapshot",
    "`P04`",
    "display_diagnostics",
    "packet_verification_result",
    "performance_acceptance_result",
    GRAPH_CANVAS_SNAPSHOT_COMMAND,
    TRACK_H_BENCHMARK_ARTIFACT,
    GRAPH_CANVAS_STRESS_1200_BASELINE_COMMAND,
    GRAPH_CANVAS_STRESS_1200_BENCHMARK_ARTIFACT,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_COMMAND,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_ARTIFACT,
    GRAPH_CANVAS_STRESS_1200_FINAL_COMMAND,
    GRAPH_CANVAS_STRESS_1200_FINAL_BENCHMARK_ARTIFACT,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_COMMAND,
    GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_BENCHMARK_ARTIFACT,
    "## 2026-03-18 Offscreen Snapshot",
    GRAPH_CANVAS_PERF_MATRIX_DOC,
)
TRACK_H_REPORT_FORBIDDEN_TOKENS = (
    "Historical offscreen harness baseline restored from repo",
    "P08 did not rerun the performance harness.",
)


TRACEABILITY_ROW_REQUIRED_TOKENS = {
    "REQ-PERF-001": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "GraphCanvas.qml",
    ),
    "REQ-PERF-002": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "GraphCanvas.qml",
    ),
    "REQ-PERF-003": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "load",
    ),
    "AC-REQ-QA-001-02": (
        "RC_PACKAGING_REPORT.md",
        "archived `2026-03-01` build/smoke summary",
    ),
    "AC-REQ-QA-001-03": (
        "PILOT_SIGNOFF.md",
        "archived `2026-03-01` run",
    ),
    "REQ-QA-013": (
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        "GRAPH_SURFACE_INPUT_QA_MATRIX.md",
    ),
    "REQ-QA-014": (
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        "VERIFICATION_SPEED_QA_MATRIX.md",
    ),
    "REQ-QA-015": (
        SHELL_ISOLATION_PHASE_TEST,
        *SHELL_ISOLATION_TARGET_CATALOG_PATHS,
        "README.md",
        "docs/GETTING_STARTED.md",
        "VERIFICATION_SPEED_QA_MATRIX.md",
    ),
    "REQ-QA-016": (
        *XDIST_RESOLUTION_TOKENS[:2],
        "README.md",
        "docs/GETTING_STARTED.md",
        "VERIFICATION_SPEED_QA_MATRIX.md",
    ),
    "REQ-QA-017": (
        "VERIFICATION_SPEED_QA_MATRIX.md",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
    ),
    "REQ-QA-018": (
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        CHECK_TRACEABILITY_SCRIPT,
    ),
    "AC-REQ-UI-023-01": (
        "GRAPH_SURFACE_INPUT_QA_MATRIX.md",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
    ),
    "AC-REQ-QA-013-01": (
        "GRAPH_SURFACE_INPUT_QA_MATRIX.md",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
    ),
    "AC-REQ-QA-014-01": (
        run_verification_command("full", dry_run=True),
        RUN_VERIFICATION_SCRIPT,
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        "VERIFICATION_SPEED_QA_MATRIX.md",
    ),
    "AC-REQ-QA-015-01": (
        run_verification_command("full", dry_run=True),
        RUN_VERIFICATION_SCRIPT,
        SHELL_ISOLATION_PHASE_TEST,
        "README.md",
        "docs/GETTING_STARTED.md",
    ),
    "AC-REQ-QA-016-01": (
        RUN_VERIFICATION_SCRIPT,
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        "README.md",
        "docs/GETTING_STARTED.md",
        "VERIFICATION_SPEED_QA_MATRIX.md",
    ),
    "AC-REQ-QA-017-01": (
        "VERIFICATION_SPEED_QA_MATRIX.md",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
    ),
    "REQ-QA-025": (
        CHECK_TRACEABILITY_SCRIPT,
        CHECK_MARKDOWN_LINKS_SCRIPT,
        PACKAGING_WINDOWS_DOC,
        PILOT_RUNBOOK_DOC,
        SPEC_INDEX_DOC,
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
        "tests/test_shell_isolation_phase.py",
        MARKDOWN_HYGIENE_TEST,
    ),
    "AC-REQ-PERF-002-01": (
        "TRACK_H_BENCHMARK_REPORT.md",
        "tests/test_track_h_perf_harness.py",
        "2026-03-18",
    ),
    "AC-REQ-PERF-003-01": (
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_REPORT_DIR,
    ),
    "AC-REQ-PERF-002-02": (
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        GRAPH_CANVAS_STRESS_1200_DISPLAY_DIAGNOSTICS_REPORT_DIR,
        GRAPH_CANVAS_STRESS_1200_DISPLAY_FINAL_REPORT_DIR,
    ),
    "AC-REQ-QA-018-01": (
        GRAPH_CANVAS_REPORT_DIR,
        "GRAPH_CANVAS_PERF_QA_MATRIX.md",
        "TRACK_H_BENCHMARK_REPORT.md",
        CHECK_TRACEABILITY_SCRIPT,
    ),
    "AC-REQ-QA-025-01": (
        DOCS_RELEASE_TRACEABILITY_PYTEST_COMMAND,
        proof_audit_command(),
        f"{LOCAL_VENV_PYTHON_DISPLAY} {CHECK_MARKDOWN_LINKS_SCRIPT}",
        ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
    ),
    "REQ-QA-051": (
        SPEC_INDEX_DOC,
        TRACEABILITY_MATRIX_DOC,
        "scripts/verification_manifest.py",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
    ),
    "AC-REQ-QA-051-01": (
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        MARKDOWN_HYGIENE_TEST,
    ),
    "REQ-QA-029": (
        "docs/specs/INDEX.md",
        "docs/specs/requirements/90_QA_ACCEPTANCE.md",
        "docs/specs/requirements/TRACEABILITY_MATRIX.md",
        ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_DOC,
        "scripts/verification_manifest.py",
        "scripts/check_traceability.py",
        "tests/test_architecture_boundaries.py",
        "tests/test_shell_isolation_phase.py",
        "tests/test_markdown_hygiene.py",
        "tests/test_traceability_checker.py",
        "tests/shell_isolation_main_window_targets.py",
        "tests/shell_isolation_controller_targets.py",
    ),
    "AC-REQ-QA-029-01": (
        ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND,
        ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND,
        ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND,
        "ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX.md",
    ),
    "REQ-QA-042": (
        "ARCHITECTURE.md",
        "README.md",
        SPEC_INDEX_DOC,
        "docs/specs/requirements/10_ARCHITECTURE.md",
        "docs/specs/requirements/30_GRAPH_MODEL.md",
        "docs/specs/requirements/40_NODE_SDK.md",
        "docs/specs/requirements/45_NODE_EXECUTION_MODEL.md",
        "docs/specs/requirements/50_EXECUTION_ENGINE.md",
        "docs/specs/requirements/60_PERSISTENCE.md",
        "docs/specs/requirements/70_INTEGRATIONS.md",
        QA_ACCEPTANCE_DOC,
        TRACEABILITY_MATRIX_DOC,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC,
        "scripts/verification_manifest.py",
        CHECK_TRACEABILITY_SCRIPT,
        "tests/test_traceability_checker.py",
        MARKDOWN_HYGIENE_TEST,
        "tests/test_dead_code_hygiene.py",
    ),
    "AC-REQ-QA-042-01": (
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_PYTEST_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_TRACEABILITY_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_MARKDOWN_COMMAND,
        COREX_NO_LEGACY_ARCHITECTURE_CLEANUP_QA_MATRIX_DOC,
    ),
}

TRACEABILITY_ROW_REQUIRED_TOKENS.update(
    {
        "REQ-EXEC-017": (
            "solution_identity.py",
            "solution_store.py",
            "solution_backend.py",
            "project_solution.py",
            "runtime.py",
            "run_controller.py",
            "run_event_controller.py",
            "run_projection_controller.py",
            "viewer_session_bridge.py",
            "test_run_event_controller.py",
            "test_run_projection_controller.py",
            "test_shell_run_controller.py",
            "test_viewer_session_bridge.py",
            "test_viewer_host_service.py",
            "test_runtime.py",
        ),
        "AC-REQ-EXEC-017-01": (
            "test_disconnected_toggle_auto_run_preserves_current_viewer",
            "run_verification.py --mode fast --summarize-output",
            "4,472 passed, 2 skipped",
        ),
        "REQ-PERSIST-026": (
            "solution_backend.py",
            "project_solution.py",
            "solution_repository.py",
            "document_io_service.py",
            "mutable freshness",
            "never durable truth",
        ),
        "AC-REQ-PERSIST-026-01": (
            "test_solution_backend.py",
            "test_project_solution.py",
            "test_solution_repository.py",
            "test_project_save_as_flow.py",
            "run_verification.py --mode fast --summarize-output",
            "4,472 passed, 2 skipped",
        ),
        "REQ-UI-065": (
            "plugin_authoring.py",
            "plugin_authoring_dialog.py",
            "plugin_authoring_controller.py",
            "window_actions.py",
        ),
        "AC-REQ-UI-065-01": (
            "test_plugin_authoring.py",
            "test_plugin_authoring_dialog.py",
            "test_plugin_authoring_controller.py",
            "test_registry_replacement.py",
        ),
        "REQ-NODE-050": (
            "corex/__init__.py",
            "plugin_declaration.py",
            "plugin_loader.py",
            "PLUGIN_AUTHORING_GUIDE.md",
        ),
        "AC-REQ-NODE-050-01": (
            "test_plugin_declaration.py",
            "test_architecture_boundaries.py",
            "test_novice_plugin_sdk_docs.py",
            "test_corex_contract_catalog.py",
        ),
        "REQ-NODE-051": (
            "function_plugin.py",
            "execution_context.py",
            "plugin_worker_runtime.py",
        ),
        "AC-REQ-NODE-051-01": (
            "test_function_plugin.py",
            "test_execution_worker.py",
            "test_dataflow_execution_runtime.py",
        ),
        "REQ-EXEC-028": (
            "registry_agreement.py",
            "protocol_codec.py",
            "runtime_requests.py",
            "project_loader.py",
            "runtime.py",
            "plugin_worker_runtime.py",
            "worker_runtime.py",
            "plugin_generation.py",
        ),
        "AC-REQ-EXEC-028-01": (
            "test_registry_agreement.py",
            "test_run_messages.py",
            "test_protocol_codec.py",
            "test_client_common.py",
            "test_process_client.py",
            "test_external_python_client.py",
            "test_trusted_client.py",
            "test_backend_client.py",
            "test_execution_worker.py",
            "test_plugin_generation.py",
        ),
        "REQ-PERSIST-031": (
            "project_codec.py",
            "serializer.py",
            "custom_workflows",
            "registry_replacement.py",
        ),
        "AC-REQ-PERSIST-031-01": (
            "test_serializer.py",
            "test_dataflow_graph_persistence.py",
            "test_registry_replacement.py",
            "test_builtin_function_infrastructure.py",
        ),
        "REQ-INT-021": (
            "package_manager.py",
            "plugin_loader.py",
            "plugin_generation.py",
            "registry_replacement.py",
        ),
        "AC-REQ-INT-021-01": (
            "test_package_manager.py",
            "test_plugin_loader.py",
            "test_plugin_generation.py",
            "test_registry_replacement.py",
        ),
        "REQ-QA-055": (
            "PLAN_COREX_NOVICE_PLUGIN_SDK.md",
            "COREX_NOVICE_PLUGIN_SDK_MIGRATION_INVENTORY.md",
            "current_repo_owned_catalog.json",
            "COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md",
        ),
        "AC-REQ-QA-055-01": (
            COREX_NOVICE_PLUGIN_SDK_FOCUSED_PYTEST_COMMAND,
            COREX_NOVICE_PLUGIN_SDK_HYGIENE_PYTEST_COMMAND,
            COREX_NOVICE_PLUGIN_SDK_FULL_COMMAND,
            COREX_NOVICE_PLUGIN_SDK_PACKAGE_COMMAND,
        ),
        "AC-REQ-NODE-045-01": (
            "tests/fixtures/node_controls/signal_plot_style_node_controls.py",
            "tests/test_corex_node_controls_visual.py",
        ),
        "REQ-QA-052": (
            "tests/fixtures/node_controls/signal_plot_style_node_controls.py",
            "tests/test_corex_node_controls_visual.py",
        ),
    }
)

TRACEABILITY_ROW_FORBIDDEN_TOKENS = {
    "REQ-INT-006": ("compatibility export",),
    "AC-REQ-QA-013-01": ("approved fresh-process shell fallback",),
    "AC-REQ-QA-017-01": ("Recorded serializer baseline caveat",),
    "AC-REQ-QA-018-01": ("ea_node_editor.telemetry.performance_harness",),
    "AC-REQ-NODE-045-01": ("tests/test_signal_plot_style_node_controls_example.py",),
    "REQ-QA-052": (
        "docs/examples/signal_plot_style_node_controls.py",
        "tests/test_signal_plot_style_node_controls_example.py",
    ),
}

COREX_NOVICE_PLUGIN_SDK_PASSED_GATES: tuple[str, ...] = ()
COREX_NOVICE_PLUGIN_SDK_TRANSITIONAL_GATES = (
    "Full summarized verification",
    "Clean base Windows package",
    "Independent final diff/evidence review",
)
COREX_NOVICE_PLUGIN_SDK_QA_MATRIX_REQUIRED_TOKENS = (
    "COREX Novice Function Plugin SDK QA Matrix",
    "## Locked Scope",
    "## Current Inventory",
    "17 public `corex` exports",
    "139 classified type IDs",
    "78 converted type IDs",
    "53 trusted internal exceptions",
    "current_repo_owned_catalog.json",
    "surface_with_edges",
    "76 reserved built-in function entries",
    "## Public Documentation And Examples",
    "docs/PLUGIN_AUTHORING_GUIDE.md",
    "docs/PLUGIN_MIGRATION_GUIDE.md",
    "docs/examples/signal_plot_function_plugin.py",
    "docs/examples/strain_conditioner_plugin.py",
    "## Focused Closeout Results",
    COREX_NOVICE_PLUGIN_SDK_FOCUSED_PYTEST_COMMAND,
    COREX_NOVICE_PLUGIN_SDK_HYGIENE_PYTEST_COMMAND,
    "## Pending Acceptance Gates",
    COREX_NOVICE_PLUGIN_SDK_FULL_COMMAND,
    COREX_NOVICE_PLUGIN_SDK_PACKAGE_COMMAND,
)

ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_REQUIRED_TOKENS = (
    "Architecture Residual Refactor QA Matrix",
    "## Locked Scope",
    "## Retained Automated Verification",
    "## Final Closeout Commands",
    "## 2026-04-04 Execution Results",
    "## Remaining Manual Desktop Checks",
    "## Residual Risks",
    "docs/specs/INDEX.md",
    "docs/specs/requirements/90_QA_ACCEPTANCE.md",
    "docs/specs/requirements/TRACEABILITY_MATRIX.md",
    "scripts/verification_manifest.py",
    "scripts/check_traceability.py",
    "tests/test_architecture_boundaries.py",
    "tests/test_shell_isolation_phase.py",
    "tests/test_traceability_checker.py",
    MARKDOWN_HYGIENE_TEST,
    ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX_DOC,
    ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND,
    ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND,
    ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND,
    *ARCHITECTURE_RESIDUAL_REFACTOR_PACKET_WRAPUPS,
)
ARCHITECTURE_RESIDUAL_REFACTOR_QA_MATRIX_AUDIT_COMMANDS = (
    ARCHITECTURE_RESIDUAL_REFACTOR_TARGETED_REGRESSION_COMMAND,
    ARCHITECTURE_RESIDUAL_REFACTOR_TRACEABILITY_COMMAND,
    ARCHITECTURE_RESIDUAL_REFACTOR_MARKDOWN_COMMAND,
)
