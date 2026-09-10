from __future__ import annotations

import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_node_editor.telemetry.startup_profile import is_autoquit, phase, summary

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ea_node_editor.app_preferences import AppPreferencesStore
    from ea_node_editor.nodes.registry import NodeRegistry
    from ea_node_editor.ui.shell.window import ShellWindow

READY_HANDOFF_VISIBLE_MS = 1000
BUNDLED_APPLICATION_FONT_FILENAMES = ("Caveat-Regular.ttf", "Caveat-Bold.ttf")
_qt_webengine_quick_initialized = False


def _initialize_qt_webengine_quick() -> bool:
    """Initialize Qt WebEngine Quick before QApplication when it is usable."""

    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    from ea_node_editor.web_host.webengine import is_webengine_disabled_for_offscreen_platform

    global _qt_webengine_quick_initialized
    if _qt_webengine_quick_initialized:
        return True
    if QApplication.instance() is not None or QGuiApplication.instance() is not None:
        return False
    if is_webengine_disabled_for_offscreen_platform():
        return False
    try:
        from PyQt6.QtWebEngineQuick import QtWebEngineQuick
    except Exception as exc:  # noqa: BLE001
        logger.debug("QtWebEngineQuick is unavailable during startup initialization: %s", exc)
        return False
    QtWebEngineQuick.initialize()
    _qt_webengine_quick_initialized = True
    return True


def prepare_qt_application_attributes() -> None:
    """Set process-wide Qt attributes that must precede QApplication creation."""

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_Use96Dpi, False)
    _initialize_qt_webengine_quick()
    if QGuiApplication.instance() is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )


def _register_bundled_application_fonts() -> None:
    """Register COREX-owned font families before QML queries them."""

    from PyQt6.QtGui import QFontDatabase

    font_dir = Path(__file__).with_name("assets") / "fonts"
    for filename in BUNDLED_APPLICATION_FONT_FILENAMES:
        if QFontDatabase.addApplicationFont(str(font_dir / filename)) < 0:
            logger.warning("Could not register bundled font: %s", filename)


def _load_startup_preferences_document(*, store: AppPreferencesStore | None = None) -> dict[str, Any]:
    from ea_node_editor.app_preferences import (
        AppPreferencesStore,
        default_app_preferences_document,
        normalize_app_preferences_document,
    )

    try:
        return normalize_app_preferences_document((store or AppPreferencesStore()).load_document())
    except Exception:  # noqa: BLE001
        return default_app_preferences_document()


def _startup_theme_id(*, preferences_document: Any = None) -> str:
    from ea_node_editor.app_preferences import resolve_startup_theme_id

    if isinstance(preferences_document, dict):
        return resolve_startup_theme_id(graphics=preferences_document.get("graphics"))
    return resolve_startup_theme_id()


def build_and_show_shell_window() -> ShellWindow:
    from ea_node_editor.ui.shell.composition import create_shell_window

    preferences_document = _load_startup_preferences_document()
    window = create_shell_window(preferences_document=preferences_document)
    window.show()
    return window


def _run_function_plugin_package_smoke() -> None:
    import tempfile
    import threading

    from ea_node_editor.execution.process_client import ProcessExecutionClient
    from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
    from ea_node_editor.execution.solution_identity import corex_build_digest
    from ea_node_editor.graph.model import GraphModel
    from ea_node_editor.nodes.bootstrap import build_plugin_candidate_registry
    from ea_node_editor.runtime_contracts import DataTree, deserialize_runtime_value
    from ea_node_editor.settings import plugin_generations_dir, plugins_dir

    type_id = "custom.package_smoke.1234abcd"
    expected_value = 37
    if len(corex_build_digest()) != 64:
        raise RuntimeError("Packaged COREX build identity smoke failed.")
    previous_appdata = os.environ.get("APPDATA")
    try:
        with tempfile.TemporaryDirectory(prefix="corex-function-plugin-smoke-") as temp_dir:
            root = Path(temp_dir)
            os.environ["APPDATA"] = str(root / "appdata")
            project_dir = root / "project"
            project_dir.mkdir()
            (plugins_dir() / "package_smoke.py").write_text(
                f'''import corex


@corex.node(id={type_id!r}, name="Package Smoke", category=("Tests",))
@corex.output("result", value_type=int)
def package_smoke(ctx):
    return {{"result": {expected_value}}}
''',
                encoding="utf-8",
            )
            registry = build_plugin_candidate_registry(
                generation_root=plugin_generations_dir(),
            )
            if registry.python_function_ref_or_none(type_id) is None:
                raise RuntimeError("Packaged function-plugin smoke was not discovered.")

            model = GraphModel()
            workspace = model.active_workspace
            node = model.add_node(
                workspace.workspace_id,
                type_id,
                "Package Smoke",
                0,
                0,
            )
            snapshot = build_runtime_snapshot(
                model.project,
                workspace_id=workspace.workspace_id,
                registry=registry,
            )
            events: list[dict[str, object]] = []
            terminal = threading.Event()

            def collect(event: dict[str, object]) -> None:
                events.append(event)
                if event.get("type") in {"run_completed", "run_failed", "run_stopped"}:
                    terminal.set()

            client = ProcessExecutionClient()
            client.subscribe(collect)
            try:
                client.start_run(
                    str(project_dir / "package_smoke.cxproj"),
                    workspace.workspace_id,
                    {"runtime_snapshot": snapshot},
                    data_types=registry.data_types,
                    plugin_bundles=registry.plugin_bundle_refs(),
                    plugin_fingerprint=registry.plugin_fingerprint(),
                    registry_contract_fingerprint=registry.contract_fingerprint(),
                    addon_runtime_config=registry.addon_runtime_config(),
                )
                if not terminal.wait(timeout=30.0):
                    raise RuntimeError("Packaged function-plugin smoke timed out.")
            finally:
                client.shutdown()

            if not any(event.get("type") == "run_completed" for event in events):
                raise RuntimeError(f"Packaged function-plugin smoke failed: {events!r}")
            settled = next(
                (
                    event
                    for event in events
                    if event.get("type") == "node_settled"
                    and event.get("node_id") == node.node_id
                ),
                None,
            )
            if settled is None:
                raise RuntimeError("Packaged function-plugin smoke did not settle its node.")
            tree = deserialize_runtime_value(
                settled["outputs"]["result"]["value"],
                catalog=registry.data_types,
            )
            if not isinstance(tree, DataTree) or tree.branches != (
                ((0,), (expected_value,)),
            ):
                raise RuntimeError("Packaged function-plugin smoke returned the wrong value.")
    finally:
        if previous_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = previous_appdata


def run() -> int:
    with phase("run.mp.freeze_support"):
        mp.freeze_support()
    if os.environ.get("EA_FUNCTION_PLUGIN_PACKAGE_SMOKE") == "1":
        _run_function_plugin_package_smoke()
        print("Function plugin process-worker smoke passed: 37", flush=True)
        return 0
    if os.environ.get("EA_SIGNAL_PLOT_PACKAGE_SMOKE") == "1":
        from ea_node_editor.execution.signal_plot_renderer import render_signal_plot
        from ea_node_editor.runtime_contracts import DataTree

        image, warnings = render_signal_plot(
            {
                "values": DataTree((((0,), (0.0, 1.0, 0.5)),)),
                "marker_shapes": [0],
            }
        )
        if warnings or (image.width, image.height) != (600, 400):
            raise RuntimeError("Packaged Signal Plot smoke returned an invalid default render.")
        print(f"Signal Plot native PNG smoke passed: {image.sha256}", flush=True)
        return 0
    # PyArrow native extensions must finish loading before Qt Quick constructs
    # an engine. Keep this explicit even when shell services become lazy.
    with phase("run.preload_native_tabular_runtime"):
        from ea_node_editor.addons.tabular_data.loader_cache_service import (
            _preload_native_tabular_runtime,
        )

        _preload_native_tabular_runtime()
    startup_preferences_document = _load_startup_preferences_document()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    with phase("run.QApplication"):
        prepare_qt_application_attributes()
        app = QApplication(sys.argv)
        app.setApplicationName("COREX Node Editor")
        _register_bundled_application_fonts()
    with phase("run.apply_application_icon"):
        from ea_node_editor.ui.app_icon import apply_application_icon

        apply_application_icon(app)
    with phase("run.theme_stylesheet"):
        from ea_node_editor.ui.theme.styles import build_theme_palette, build_theme_stylesheet

        startup_theme_id = _startup_theme_id(preferences_document=startup_preferences_document)
        app.setStyleSheet(build_theme_stylesheet(startup_theme_id))
        app.setPalette(build_theme_palette(startup_theme_id))

    with phase("run.splash_show"):
        from ea_node_editor.ui.splash import OpeningSplash, RegistryLoader

        splash = OpeningSplash()
        splash.show_centered()

    # Coordinator state: we need both the splash's boot animation to finish
    # AND the background registry build to complete before starting the
    # main-thread shell construction. Whichever arrives second fires _build.
    state: dict[str, object] = {
        "boot_done": False,
        "registry": None,  # NodeRegistry | None (None until arrived or failed)
        "registry_arrived": False,
        "built": False,
    }

    loader = RegistryLoader(preferences_document=startup_preferences_document)

    def _maybe_build() -> None:
        if state["built"] or not state["boot_done"] or not state["registry_arrived"]:
            return
        state["built"] = True
        registry = state["registry"]
        splash.set_busy_message(
            "Building workspace",
            "Preparing the main workspace and restoring interface state.",
        )
        app.processEvents()
        with phase("run.create_shell_window"):
            from ea_node_editor.ui.shell.composition import create_shell_window

            window = create_shell_window(
                registry=registry,  # type: ignore[arg-type]
                preferences_document=startup_preferences_document,
            )
        splash.mark_ready()
        app.processEvents()

        def _finish_startup() -> None:
            splash.finish(window, min_visible_ms=0)
            if is_autoquit():
                QTimer.singleShot(500, lambda: (summary(), app.quit()))

        QTimer.singleShot(READY_HANDOFF_VISIBLE_MS, _finish_startup)

    def _on_boot_completed() -> None:
        state["boot_done"] = True
        _maybe_build()

    def _on_registry_ready(registry: NodeRegistry) -> None:
        state["registry"] = registry
        state["registry_arrived"] = True
        _maybe_build()

    def _on_registry_failed(tb: str) -> None:
        # Fall back to the main-thread build — slow, but keeps the app bootable.
        logger.error("Registry load failed; falling back to main-thread build.\n%s", tb)
        state["registry"] = None
        state["registry_arrived"] = True
        _maybe_build()

    splash.boot_completed.connect(_on_boot_completed)
    loader.ready.connect(_on_registry_ready)
    loader.failed.connect(_on_registry_failed)
    loader.start()

    return app.exec()
