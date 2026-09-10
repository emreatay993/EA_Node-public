from __future__ import annotations

import importlib
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ea_node_editor.addons.tabular_data import loader_cache_service as tabular_loader_module
from ea_node_editor.ui import app_icon as app_icon_module
from ea_node_editor.ui import splash as splash_module
from ea_node_editor.ui.mail_preview_provider import (
    set_mail_preview_project_context_provider,
)
from ea_node_editor.ui.media_preview_provider import (
    set_media_preview_project_context_provider,
)
from ea_node_editor.ui.pdf_preview_provider import (
    set_pdf_preview_project_context_provider,
)
from ea_node_editor.ui.theme import styles as theme_styles_module


bootstrap_module = importlib.import_module("ea_node_editor.bootstrap")
app_module = importlib.import_module("ea_node_editor.app")
shell_composition_module = importlib.import_module("ea_node_editor.ui.shell.composition")
shell_composition_bootstrap_module = importlib.import_module("ea_node_editor.ui.shell.composition.bootstrap")
shell_presenters_module = importlib.import_module("ea_node_editor.ui.shell.presenters")
registry_loader_module = importlib.import_module("ea_node_editor.ui.splash.registry_loader")
opening_screen_module = importlib.import_module("ea_node_editor.ui.splash.opening_screen")
shell_window_module = importlib.import_module("ea_node_editor.ui.shell.window")


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


class MainBootstrapTests(unittest.TestCase):
    def test_private_mechanical_owner_dispatches_before_app_bootstrap(self) -> None:
        with patch.object(
            bootstrap_module.sys,
            "argv",
            ["corex.exe", "--private-mechanical-owner", "--owner-child", "7", "token", "C:/spool"],
        ), patch("ea_node_editor.addons.mechanical.owner_process._child", return_value=19) as child:
            self.assertEqual(bootstrap_module.main(), 19)
        child.assert_called_once_with(7, "token", "C:/spool")

    def test_root_source_launcher_is_retired(self) -> None:
        self.assertFalse((Path(__file__).resolve().parents[1] / "main.py").exists())

    def test_console_script_targets_package_bootstrap(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_text = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('corex-node-editor = "ea_node_editor.bootstrap:main"', pyproject_text)

    def test_shell_launcher_targets_package_bootstrap_module(self) -> None:
        run_script_path = Path(__file__).resolve().parents[1] / "scripts" / "run.sh"
        run_script_text = run_script_path.read_text(encoding="utf-8")

        self.assertIn("-m ea_node_editor.bootstrap", run_script_text)
        self.assertNotIn("find_worktree_python", run_script_text)
        self.assertNotIn(" main.py", run_script_text)

    def test_preferred_python_prefers_local_venv_over_shared_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            local_python = _touch(repo_root / "venv" / "Scripts" / "python.exe")
            shared_python = _touch(Path(temp_dir) / "shared" / "venv" / "Scripts" / "python.exe")

            with patch.object(bootstrap_module, "_find_worktree_python", return_value=shared_python):
                self.assertEqual(bootstrap_module._preferred_python(repo_root), local_python)

    def test_preferred_python_discovers_shared_worktree_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            shared_root = Path(temp_dir) / "shared-worktree"
            shared_python = _touch(shared_root / "venv" / "Scripts" / "python.exe")

            fake_git_output = "\n".join(
                (
                    f"worktree {repo_root}",
                    "HEAD abcdef1234567890",
                    "branch refs/heads/main",
                    f"worktree {shared_root}",
                    "HEAD 1234567890abcdef",
                    "branch refs/heads/codex/shared",
                )
            )

            fake_result = types.SimpleNamespace(stdout=fake_git_output)
            with patch.object(bootstrap_module.subprocess, "run", return_value=fake_result):
                self.assertEqual(bootstrap_module._preferred_python(repo_root), shared_python)

    def test_bootstrap_reexecs_once_and_honors_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "repo"
            preferred_python = _touch(repo_root / "venv" / "Scripts" / "python.exe")
            current_python = _touch(Path(temp_dir) / "system" / "python.exe")
            exec_calls: list[tuple[str, list[str], dict[str, str]]] = []

            def _fake_execvpe(file: str, args: list[str], env: dict[str, str]) -> None:
                exec_calls.append((file, args, env))
                raise AssertionError("bootstrap should re-exec exactly once")

            with patch.object(bootstrap_module, "__file__", str(repo_root / "ea_node_editor" / "bootstrap.py")), patch.object(
                bootstrap_module.sys, "executable", str(current_python)
            ), patch.object(
                bootstrap_module.sys, "argv", ["-m", "--example-flag", "value"]
            ), patch.object(bootstrap_module.os, "execvpe", side_effect=_fake_execvpe), patch.object(
                bootstrap_module.os, "chdir"
            ) as chdir_mock, patch.dict(bootstrap_module.os.environ, {}, clear=False), patch.object(
                bootstrap_module, "_preferred_python", return_value=preferred_python
            ):
                with self.assertRaises(AssertionError):
                    bootstrap_module._bootstrap_python(
                        "ea_node_editor.execution.runtime_cli"
                    )

            self.assertEqual(len(exec_calls), 1)
            self.assertEqual(exec_calls[0][0], str(preferred_python))
            self.assertEqual(
                exec_calls[0][1],
                [
                    str(preferred_python),
                    "-m",
                    "ea_node_editor.execution.runtime_cli",
                    "--example-flag",
                    "value",
                ],
            )
            self.assertEqual(exec_calls[0][2][bootstrap_module._BOOTSTRAP_SENTINEL], "1")
            chdir_mock.assert_called_once_with(repo_root)

            with patch.object(bootstrap_module, "__file__", str(repo_root / "ea_node_editor" / "bootstrap.py")), patch.object(
                bootstrap_module.sys, "executable", str(current_python)
            ), patch.object(
                bootstrap_module.sys, "argv", ["-m", "--example-flag", "value"]
            ), patch.object(bootstrap_module.os, "execvpe") as execvpe_mock, patch.dict(
                bootstrap_module.os.environ, {bootstrap_module._BOOTSTRAP_SENTINEL: "1"}, clear=False
            ), patch.object(bootstrap_module, "_preferred_python", return_value=preferred_python):
                bootstrap_module._bootstrap_python(
                    "ea_node_editor.execution.runtime_cli"
                )

            execvpe_mock.assert_not_called()

    def test_bootstrap_skips_reexec_for_frozen_package_runs(self) -> None:
        with patch.object(bootstrap_module.sys, "frozen", True, create=True), patch.object(
            bootstrap_module, "_preferred_python"
        ) as preferred_python_mock, patch.object(bootstrap_module.os, "execvpe") as execvpe_mock:
            bootstrap_module._bootstrap_python()

        preferred_python_mock.assert_not_called()
        execvpe_mock.assert_not_called()

    def test_bootstrap_owns_windows_qquick_controls_style_default(self) -> None:
        with patch.object(bootstrap_module.sys, "platform", "win32"), patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            bootstrap_module.configure_qquick_controls_runtime()
            self.assertEqual(os.environ["QT_QUICK_CONTROLS_STYLE"], "Basic")

        with patch.object(bootstrap_module.sys, "platform", "win32"), patch.dict(
            os.environ,
            {"QT_QUICK_CONTROLS_STYLE": "Material"},
            clear=True,
        ):
            bootstrap_module.configure_qquick_controls_runtime()
            self.assertEqual(os.environ["QT_QUICK_CONTROLS_STYLE"], "Material")


class AppBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.prepare_qt_application_attributes()
        self.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        set_media_preview_project_context_provider(None)
        set_mail_preview_project_context_provider(None)
        set_pdf_preview_project_context_provider(None)
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_prepare_qt_application_attributes_configures_webengine_and_high_dpi_policy(self) -> None:
        with patch.object(QtGui.QGuiApplication, "instance", return_value=None), patch.object(
            QtGui.QGuiApplication,
            "setHighDpiScaleFactorRoundingPolicy",
        ) as set_rounding_policy_mock, patch.object(
            app_module,
            "_initialize_qt_webengine_quick",
        ) as initialize_webengine_quick_mock:
            app_module.prepare_qt_application_attributes()

        self.assertTrue(QApplication.testAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts))
        self.assertFalse(QApplication.testAttribute(Qt.ApplicationAttribute.AA_Use96Dpi))
        initialize_webengine_quick_mock.assert_called_once_with()
        set_rounding_policy_mock.assert_called_once_with(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    def test_register_bundled_application_fonts_makes_caveat_available(self) -> None:
        app_module._register_bundled_application_fonts()

        self.assertIn("Caveat", QtGui.QFontDatabase.families())

    def test_build_and_show_shell_window_uses_composition_root(self) -> None:
        fake_window = Mock()
        preferences_document = {"graphics": {"theme": {"theme_id": "packet-theme"}}}

        with patch.object(
            app_module,
            "_load_startup_preferences_document",
            return_value=preferences_document,
        ) as load_preferences_mock, patch.object(
            shell_composition_module,
            "create_shell_window",
            return_value=fake_window,
        ) as create_shell_window_mock:
            self.assertIs(app_module.build_and_show_shell_window(), fake_window)

        load_preferences_mock.assert_called_once_with()
        create_shell_window_mock.assert_called_once_with(preferences_document=preferences_document)
        fake_window.show.assert_called_once_with()

    def test_create_shell_window_builds_composition_before_bootstrap(self) -> None:
        composition = object()
        preferences_document = {"graphics": {"theme": {"theme_id": "packet-theme"}}}
        with patch.object(
            shell_composition_bootstrap_module,
            "build_shell_window_composition",
            return_value=composition,
        ) as build_composition_mock, patch.object(
            shell_composition_bootstrap_module,
            "bootstrap_shell_window",
        ) as bootstrap_mock:
            window = shell_composition_module.create_shell_window(preferences_document=preferences_document)

        self.assertIsInstance(window, shell_window_module.ShellWindow)
        build_composition_mock.assert_called_once_with(
            window,
            registry=None,
            preferences_document=preferences_document,
        )
        bootstrap_mock.assert_called_once_with(window, composition)
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_registry_loader_builds_default_registry_with_preloaded_preferences_document(self) -> None:
        preferences_document = {"addons": {"states": {"tests.addon": {"enabled": False, "pending_restart": False}}}}
        sentinel_registry = object()
        captured: list[object] = []

        loader = registry_loader_module.RegistryLoader(preferences_document=preferences_document)
        loader.ready.connect(captured.append)

        with patch.object(
            registry_loader_module,
            "build_default_registry",
            return_value=sentinel_registry,
        ) as build_registry_mock:
            loader._worker.run()

        build_registry_mock.assert_called_once_with(preferences_document=preferences_document)
        self.assertEqual(captured, [sentinel_registry])

    def test_opening_splash_boot_completion_stops_before_ready_label(self) -> None:
        self.assertEqual(
            len(opening_screen_module.BOOT_STEP_DETAILS),
            len(opening_screen_module.BOOT_STEPS),
        )
        self.assertEqual(opening_screen_module.BOOT_STEPS[-2], "Preparing add-ons")
        self.assertIn("optional integrations", opening_screen_module.BOOT_STEP_DETAILS[-2])

        splash = opening_screen_module.OpeningSplash()
        captured: list[str] = []
        splash.boot_completed.connect(lambda: captured.append("done"))

        try:
            for _ in range(len(opening_screen_module.BOOT_STEPS) - 1):
                splash._advance_step()
                self.app.processEvents()

            self.assertEqual(captured, ["done"])
            self.assertEqual(
                opening_screen_module.BOOT_STEPS[splash._step_index],
                opening_screen_module.BOOT_STEPS[-2],
            )

            splash._advance_step()
            self.app.processEvents()

            self.assertEqual(captured, ["done"])

            splash.mark_ready()

            self.assertEqual(
                opening_screen_module.BOOT_STEPS[splash._step_index],
                opening_screen_module.BOOT_STEPS[-1],
            )
        finally:
            splash.close()
            splash.deleteLater()
            self.app.sendPostedEvents()
            self.app.processEvents()

    def test_opening_splash_uses_normal_window_z_order(self) -> None:
        splash = opening_screen_module.OpeningSplash()

        try:
            flags = splash.windowFlags()

            self.assertTrue(flags & Qt.WindowType.SplashScreen)
            self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
            self.assertFalse(flags & Qt.WindowType.WindowStaysOnTopHint)
        finally:
            splash.close()
            splash.deleteLater()
            self.app.sendPostedEvents()
            self.app.processEvents()

    def test_opening_splash_enlarges_only_the_emblem_about_its_center(self) -> None:
        def render(splash):
            image = QtGui.QImage(720, 440, QtGui.QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            splash._animation_ms = 1000
            splash.render(image)
            return image

        def mark_bounds(splash):
            image = QtGui.QImage(720, 440, QtGui.QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            splash._paint_mark(painter)
            painter.end()
            pixels = image.constBits().asstring(image.sizeInBytes())
            positions = [i for i, alpha in enumerate(pixels[3::4]) if alpha >= 128]
            xs, ys = [i % 720 for i in positions], [i // 720 for i in positions]
            return QtCore.QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

        reference = opening_screen_module.OpeningSplash(mark_size=172)
        enlarged = opening_screen_module.OpeningSplash()
        try:
            reference_frame, enlarged_frame = render(reference), render(enlarged)
            # Everything below the emblem, including the wordmark, stays fixed.
            self.assertEqual(reference_frame.copy(0, 210, 720, 230), enlarged_frame.copy(0, 210, 720, 230))
            before, after = mark_bounds(reference), mark_bounds(enlarged)
            self.assertAlmostEqual(after.width() / before.width(), 1.15, delta=0.02)
            self.assertAlmostEqual(after.height() / before.height(), 1.15, delta=0.02)
            self.assertLessEqual((before.center() - after.center()).manhattanLength(), 1)
        finally:
            reference.close()
            enlarged.close()

    def test_opening_splash_ambient_motion_does_not_advance_boot_and_stops_on_finish(self) -> None:
        splash = opening_screen_module.OpeningSplash()
        window = QtWidgets.QWidget()
        for widget in (splash, window):
            widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        completed = Mock()
        splash.boot_completed.connect(completed)
        try:
            splash.show_centered()
            splash._shown_timer = Mock(elapsed=Mock(return_value=12000), isValid=Mock(return_value=True))
            splash._advance_animation()
            self.assertEqual(splash._step_index, 0)
            completed.assert_not_called()
            self.assertTrue(splash._animation_timer.isActive())
            splash.set_busy_message("Building workspace", "Restoring interface state.")
            self.assertIn("Restoring interface state.", splash.accessibleDescription())
            splash.mark_ready()
            self.assertTrue(splash.accessibleDescription().startswith("Ready."))
            splash.finish(window, min_visible_ms=0)
            self.assertTrue(window.isVisible())
            self.assertFalse(splash.isVisible())
            self.assertFalse(splash._animation_timer.isActive())
            self.assertFalse(splash._boot_timer.isActive())
        finally:
            window.close()
            splash.close()

    def test_build_shell_window_composition_returns_typed_contract(self) -> None:
        window = shell_window_module.ShellWindow(_defer_bootstrap=True)

        composition = shell_composition_module.build_shell_window_composition(window)
        services = composition.services

        self.assertIsInstance(composition, shell_composition_module.ShellWindowComposition)
        self.assertEqual(tuple(composition.__dataclass_fields__), ("services",))
        self.assertIsInstance(services, shell_composition_module.ShellServices)
        self.assertIsInstance(services.state, shell_composition_module.ShellStateDependencies)
        self.assertIsInstance(services.primitives, shell_composition_module.ShellPrimitiveDependencies)
        self.assertIsInstance(services.controllers, shell_composition_module.ShellControllerDependencies)
        self.assertIsInstance(services.presenters, shell_composition_module.ShellPresenterDependencies)
        self.assertIsInstance(services.runtime, shell_composition_module.ShellRuntimeDependencies)
        self.assertIsInstance(services.context_bridges, shell_composition_module.ShellContextBridgeDependencies)
        self.assertIsInstance(
            services.presenters.graph_canvas_host_presenter,
            shell_presenters_module.GraphCanvasHostPresenter,
        )
        # Controllers and presenters receive the ShellWindow directly; the
        # forwarding host-adapter layer is retired.
        self.assertIs(services.library_workspace.workspace_selection_context._host, window)
        self.assertIs(services.library_workspace.workspace_edit_controller._host, window)
        self.assertIs(
            services.library_workspace.workspace_drop_connect_controller._host,
            window,
        )
        self.assertIs(
            services.library_workspace.workspace_edit_controller.mutation_ui_effects,
            services.library_workspace.mutation_ui_effects,
        )
        self.assertIs(
            services.library_workspace.workspace_drop_connect_controller.mutation_ui_effects,
            services.library_workspace.mutation_ui_effects,
        )
        self.assertIs(services.controllers.project_session_controller._host, window)
        self.assertIs(services.controllers.run_projection_controller._host, window)
        self.assertIs(services.controllers.run_controller._host, window)
        self.assertIs(
            services.controllers.run_controller._projection,
            services.controllers.run_projection_controller,
        )
        self.assertNotIsInstance(
            services.controllers.run_projection_controller,
            QtCore.QObject,
        )
        self.assertIs(services.presenters.shell_library_presenter._host, window)
        self.assertIs(services.presenters.shell_workspace_presenter._host, window)
        self.assertIs(services.presenters.shell_inspector_presenter._host, window)
        self.assertIs(services.presenters.canvas_export_presenter._host, window)
        self.assertNotIsInstance(
            services.presenters.canvas_export_presenter,
            QtCore.QObject,
        )
        self.assertIs(services.presenters.graph_canvas_host_presenter._host, window)
        context_bindings = dict(services.qml_context.qml_context_property_bindings)
        self.assertIs(context_bindings["viewerSessionBridge"], services.runtime.viewer_session_bridge)
        self.assertIs(context_bindings["viewerHostService"], services.runtime.viewer_host_service)
        self.assertNotIn("shell_services", window.__dict__)
        self.assertNotIn("_shell_context_bridges", window.__dict__)
        self.assertNotIn("_shell_qml_context_property_bindings", window.__dict__)
        self.assertNotIn("_shell_qml_host_bindings", window.__dict__)
        self.assertNotIn("shell_context", window.__dict__)
        self.assertNotIn("viewer_session_bridge", window.__dict__)
        self.assertNotIn("viewer_host_service", window.__dict__)
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_shell_window_composition_attaches_one_services_reference(self) -> None:
        window = shell_window_module.ShellWindow(_defer_bootstrap=True)
        composition = shell_composition_module.build_shell_window_composition(window)

        composition.attach(window)

        self.assertIs(window.shell_services, composition.services)
        self.assertNotIn("_shell_context_bridges", window.__dict__)
        self.assertNotIn("_shell_qml_context_property_bindings", window.__dict__)
        self.assertNotIn("_shell_qml_host_bindings", window.__dict__)
        self.assertNotIn("shell_context", window.__dict__)
        self.assertIs(window.viewer_session_bridge, composition.services.runtime.viewer_session_bridge)
        self.assertIs(window.viewer_host_service, composition.services.runtime.viewer_host_service)
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_bootstrap_shell_window_uses_single_explicit_attach_point(self) -> None:
        host = Mock()
        composition = Mock(spec=shell_composition_module.ShellWindowComposition)
        timer_dependencies = Mock()

        with patch.object(shell_composition_bootstrap_module, "_configure_shell_window_host") as configure_mock, patch.object(
            shell_composition_bootstrap_module,
            "_run_shell_startup_sequence",
        ) as startup_mock, patch.object(
            shell_composition_bootstrap_module.ShellWindowBootstrapCoordinator,
            "create_timer_dependencies",
            return_value=timer_dependencies,
        ) as create_timer_mock, patch.object(
            shell_composition_bootstrap_module,
            "_finalize_shell_window_bootstrap",
            side_effect=lambda _host: startup_order.append("finalize"),
        ) as finalize_mock, patch.object(
            shell_composition_bootstrap_module,
            "_evaluate_open_workspace",
            side_effect=lambda _host: startup_order.append("evaluate"),
        ) as evaluate_mock:
            startup_order: list[str] = []
            shell_composition_module.bootstrap_shell_window(host, composition)

        configure_mock.assert_called_once_with(host)
        composition.attach.assert_called_once_with(host)
        startup_mock.assert_called_once_with(host)
        create_timer_mock.assert_called_once()
        timer_dependencies.attach.assert_called_once_with(host)
        finalize_mock.assert_called_once_with(host)
        evaluate_mock.assert_called_once_with(host)
        self.assertEqual(startup_order, ["finalize", "evaluate"])

    def test_startup_auto_evaluation_uses_the_restored_active_workspace(self) -> None:
        host = Mock()
        host.workspace_manager.active_workspace_id.return_value = "workspace_restored"

        shell_composition_bootstrap_module._evaluate_open_workspace(host)

        host.run_controller.evaluate_workspace_on_open.assert_called_once_with(
            "workspace_restored"
        )

    def test_shell_window_accepts_injected_composition_bundle(self) -> None:
        composition = object()
        with patch.object(shell_window_module, "build_shell_window_composition") as build_composition_mock, patch.object(
            shell_window_module,
            "bootstrap_shell_window",
        ) as bootstrap_mock:
            window = shell_window_module.ShellWindow(composition=composition)

        build_composition_mock.assert_not_called()
        bootstrap_mock.assert_called_once_with(window, composition)
        window.close()
        window.deleteLater()
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_shell_window_module_uses_explicit_window_state_mixins(self) -> None:
        shell_dir = Path(__file__).resolve().parents[1] / "ea_node_editor" / "ui" / "shell"
        window_path = shell_dir / "window.py"
        helper_path = shell_dir / "window_state_helpers.py"

        window_text = window_path.read_text(encoding="utf-8")

        self.assertFalse(helper_path.exists())
        self.assertNotIn("window_state_helpers", window_text)
        self.assertNotIn("locals().update", window_text)
        self.assertIn("ShellWindowContextPropertiesMixin", window_text)
        self.assertIn("ShellWindowRunAndStyleStateMixin", window_text)

    def test_run_applies_startup_theme_and_bootstraps_shell_window(self) -> None:
        fake_app = Mock()
        fake_app.exec.return_value = 17
        fake_splash = Mock()
        fake_loader = Mock()
        preferences_document = {"graphics": {"theme": {"theme_id": "packet-theme"}}}
        startup_order: list[str] = []

        def _create_application(_argv):  # noqa: ANN001
            startup_order.append("QApplication")
            return fake_app

        with patch.object(app_module.mp, "freeze_support") as freeze_support_mock, patch.object(
            tabular_loader_module,
            "_preload_native_tabular_runtime",
            side_effect=lambda: startup_order.append("pyarrow_preload"),
        ) as preload_native_runtime_mock, patch.object(
            QtWidgets,
            "QApplication",
            side_effect=_create_application,
        ) as app_ctor, patch.object(
            app_module,
            "_register_bundled_application_fonts",
            side_effect=lambda: startup_order.append("bundled_fonts"),
        ) as register_fonts_mock, patch.object(
            app_module,
            "_startup_theme_id",
            return_value="packet-theme",
        ) as startup_theme_mock, patch.object(
            app_module,
            "_load_startup_preferences_document",
            return_value=preferences_document,
        ), patch.object(
            theme_styles_module,
            "build_theme_stylesheet",
            side_effect=lambda theme_id: f"stylesheet:{theme_id}",
        ), patch.object(
            theme_styles_module,
            "build_theme_palette",
            side_effect=lambda theme_id: f"palette:{theme_id}",
        ), patch.object(
            app_icon_module,
            "apply_application_icon",
        ), patch.object(
            splash_module,
            "OpeningSplash",
            return_value=fake_splash,
        ) as splash_ctor, patch.object(
            splash_module,
            "RegistryLoader",
            return_value=fake_loader,
        ) as loader_ctor, patch.object(
            shell_composition_module,
            "create_shell_window",
        ) as create_shell_window_mock:
            self.assertEqual(app_module.run(), 17)

        freeze_support_mock.assert_called_once_with()
        preload_native_runtime_mock.assert_called_once_with()
        app_ctor.assert_called_once()
        self.assertEqual(startup_order, ["pyarrow_preload", "QApplication", "bundled_fonts"])
        fake_app.setApplicationName.assert_called_once_with("COREX Node Editor")
        register_fonts_mock.assert_called_once_with()
        fake_app.setStyleSheet.assert_called_once_with("stylesheet:packet-theme")
        fake_app.setPalette.assert_called_once_with("palette:packet-theme")
        startup_theme_mock.assert_called_once_with(preferences_document=preferences_document)
        splash_ctor.assert_called_once_with()
        fake_splash.show_centered.assert_called_once_with()
        loader_ctor.assert_called_once_with(preferences_document=preferences_document)
        fake_splash.boot_completed.connect.assert_called_once()
        fake_loader.ready.connect.assert_called_once()
        fake_loader.failed.connect.assert_called_once()
        fake_loader.start.assert_called_once_with()
        create_shell_window_mock.assert_not_called()
        fake_app.exec.assert_called_once_with()

    def test_run_registry_failure_falls_back_to_shell_build_with_preloaded_preferences_document(self) -> None:
        class _Signal:
            def __init__(self) -> None:
                self._callbacks: list[object] = []

            def connect(self, callback) -> None:  # noqa: ANN001
                self._callbacks.append(callback)

            def emit(self, *args, **kwargs) -> None:  # noqa: ANN003, ANN002
                for callback in list(self._callbacks):
                    callback(*args, **kwargs)

        class _SplashStub:
            def __init__(self) -> None:
                self.boot_completed = _Signal()
                self.finish = Mock()

            def show_centered(self) -> None:
                return None

        class _LoaderStub:
            def __init__(self) -> None:
                self.ready = _Signal()
                self.failed = _Signal()

            def start(self) -> None:
                return None

        fake_app = Mock()
        call_order: list[str] = []
        fake_window = Mock()
        fake_splash = _SplashStub()
        fake_splash.set_busy_message = Mock(side_effect=lambda *_args: call_order.append("set_busy_message"))
        fake_splash.mark_ready = Mock(side_effect=lambda: call_order.append("mark_ready"))
        fake_splash.finish = Mock(side_effect=lambda *_args, **_kwargs: call_order.append("finish"))
        fake_loader = _LoaderStub()
        preferences_document = {"graphics": {"theme": {"theme_id": "packet-theme"}}}

        def _exec() -> int:
            fake_splash.boot_completed.emit()
            self.assertEqual(call_order, [])
            fake_loader.failed.emit("traceback")
            return 17

        def _create_shell_window(**_kwargs):  # noqa: ANN003
            call_order.append("create_shell_window")
            return fake_window

        def _single_shot(delay_ms, callback):  # noqa: ANN001
            call_order.append(f"singleShot:{delay_ms}")
            callback()

        fake_app.exec.side_effect = _exec

        with patch.object(app_module.mp, "freeze_support"), patch.object(
            tabular_loader_module,
            "_preload_native_tabular_runtime",
        ) as preload_native_runtime_mock, patch.object(
            QtWidgets,
            "QApplication",
            return_value=fake_app,
        ), patch.object(
            app_module,
            "_startup_theme_id",
            return_value="packet-theme",
        ), patch.object(
            app_module,
            "_load_startup_preferences_document",
            return_value=preferences_document,
        ), patch.object(
            theme_styles_module,
            "build_theme_stylesheet",
            side_effect=lambda theme_id: f"stylesheet:{theme_id}",
        ), patch.object(
            app_icon_module,
            "apply_application_icon",
        ), patch.object(
            splash_module,
            "OpeningSplash",
            return_value=fake_splash,
        ), patch.object(
            splash_module,
            "RegistryLoader",
            return_value=fake_loader,
        ), patch.object(
            shell_composition_module,
            "create_shell_window",
            side_effect=_create_shell_window,
        ) as create_shell_window_mock, patch.object(
            QtCore.QTimer,
            "singleShot",
            side_effect=_single_shot,
        ) as single_shot_mock:
            self.assertEqual(app_module.run(), 17)

        preload_native_runtime_mock.assert_called_once_with()
        create_shell_window_mock.assert_called_once_with(
            registry=None,
            preferences_document=preferences_document,
        )
        fake_splash.set_busy_message.assert_called_once_with(
            "Building workspace",
            "Preparing the main workspace and restoring interface state.",
        )
        fake_splash.mark_ready.assert_called_once_with()
        fake_splash.finish.assert_called_once_with(fake_window, min_visible_ms=0)
        single_shot_mock.assert_called_once()
        self.assertEqual(single_shot_mock.call_args.args[0], app_module.READY_HANDOFF_VISIBLE_MS)
        self.assertEqual(
            call_order,
            ["set_busy_message", "create_shell_window", "mark_ready", "singleShot:1000", "finish"],
        )

    def test_shell_window_configuration_applies_title_size_and_icon(self) -> None:
        host = Mock()
        with patch.object(shell_composition_bootstrap_module, "apply_window_icon") as apply_window_icon_mock:
            shell_composition_bootstrap_module._configure_shell_window_host(host)

        host.setWindowTitle.assert_called_once_with("COREX Node Editor")
        host.resize.assert_called_once_with(1600, 900)
        apply_window_icon_mock.assert_called_once_with(host)


if __name__ == "__main__":
    unittest.main()
