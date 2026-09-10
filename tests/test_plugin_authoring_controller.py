from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from ea_node_editor.graph.registry_compatibility import (
    RegistryCompatibilityIssue,
    RegistryCompatibilityReport,
)
from ea_node_editor.nodes.plugin_authoring import (
    PluginAuthoringDiagnostic,
    PluginAuthoringSummary,
    PluginIdentity,
    PluginValidationReport,
)
from ea_node_editor.nodes import plugin_authoring
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui.shell.controllers import plugin_authoring_controller as module
from ea_node_editor.ui.shell.controllers.plugin_authoring_controller import (
    PluginAuthoringController,
)
from ea_node_editor.ui.shell.window_actions import (
    build_window_menu_bar,
    create_window_actions,
)
from ea_node_editor.ui.shell.window_state.run_and_style_state import (
    ShellWindowRunAndStyleStateMixin,
)


@pytest.fixture(scope="module", autouse=True)
def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Coordinator:
    def __init__(self) -> None:
        self.calls = 0
        self.result = SimpleNamespace(
            applied=True,
            report=RegistryCompatibilityReport(),
            registry=NodeRegistry(),
        )
        self.error: BaseException | None = None

    def reload_plugins(self):  # noqa: ANN201
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class _Host:
    def __init__(self) -> None:
        self.registry = NodeRegistry()
        self.registry_replacement_coordinator = _Coordinator()


class _ActionController:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def show_dialog(self) -> None:
        self.calls.append("show")

    def reload_plugins(self) -> None:
        self.calls.append("reload")


class _RunActionController:
    def __init__(self) -> None:
        self.calls = 0

    def run_workflow(self) -> None:
        self.calls += 1


class _ActionWindow(QMainWindow, ShellWindowRunAndStyleStateMixin):
    def __init__(self) -> None:
        super().__init__()
        self.recent_project_paths: list[str] = []
        self.plugin_authoring_controller = _ActionController()
        self.run_controller = _RunActionController()
        self.workspace_edit_controller = SimpleNamespace(
            undo=lambda: False,
            redo=lambda: False,
        )
        self.workspace_navigation_controller = SimpleNamespace(
            create_workspace=lambda: None,
            frame_all=lambda: False,
            frame_selection=lambda: False,
            center_on_selection=lambda: False,
            create_view=lambda: None,
            duplicate_active_workspace=lambda: None,
            rename_active_workspace=lambda: None,
            close_active_workspace=lambda: None,
            switch_workspace_by_offset=lambda _offset: None,
        )
        self.workspace_package_io_controller = SimpleNamespace(
            import_node_package=lambda: None,
            export_node_package=lambda: None,
            import_custom_workflow=lambda: None,
            export_custom_workflow=lambda: None,
        )

    def __getattr__(self, _name: str):  # noqa: ANN204
        return lambda *_args, **_kwargs: None


def _identity() -> PluginIdentity:
    return PluginIdentity(
        visible_name="New Plugin",
        slug="new_plugin",
        filename="new_plugin.py",
        function_name="new_plugin",
        node_id="custom.new_plugin.a1b2c3d4",
    )


def _report(*, success: bool = True) -> PluginValidationReport:
    return PluginValidationReport(
        success=success,
        diagnostics=()
        if success
        else (
            PluginAuthoringDiagnostic(
                filename="new_plugin.py",
                line=3,
                column=4,
                severity="error",
                message="invalid draft",
            ),
        ),
        summary=PluginAuthoringSummary(
            1 if success else 0,
            1 if success else 0,
            "d" * 64 if success else "",
            0,
        ),
    )


def _open_controller(monkeypatch) -> tuple[_Host, PluginAuthoringController]:  # noqa: ANN001
    monkeypatch.setattr(module, "new_plugin_identity", lambda _name: _identity())
    host = _Host()
    controller = PluginAuthoringController(host)
    controller.show_dialog()
    return host, controller


def _close(controller: PluginAuthoringController) -> None:
    dialog = controller.dialog
    if dialog is not None:
        dialog.close()
        app = QApplication.instance()
        assert app is not None
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def _use_saved_root(monkeypatch, root: Path) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        module,
        "save_plugin_draft",
        lambda source, filename, *, expected_source: plugin_authoring.save_plugin_draft(
            source,
            filename,
            expected_source=expected_source,
            root=root,
        ),
    )
    monkeypatch.setattr(
        module,
        "read_saved_plugin_draft",
        lambda path: plugin_authoring.read_saved_plugin_draft(path, root=root),
    )
    monkeypatch.setattr(module, "validate_plugin_draft", lambda *_args: _report())


def test_one_identity_updates_only_the_pristine_template(monkeypatch) -> None:  # noqa: ANN001
    calls = 0

    def create_identity(_name: str) -> PluginIdentity:
        nonlocal calls
        calls += 1
        return _identity()

    monkeypatch.setattr(module, "new_plugin_identity", create_identity)
    controller = PluginAuthoringController(_Host())
    dialog = controller.show_dialog()
    try:
        dialog.visible_name_edit.setText("Scale Value")
        generated = dialog.editor.toPlainText()

        assert "name='Scale Value'" in generated
        assert "custom.new_plugin.a1b2c3d4" in generated

        dialog.editor.appendPlainText("# user edit")
        edited = dialog.editor.toPlainText()
        dialog.visible_name_edit.setText("Do Not Rewrite")

        assert dialog.editor.toPlainText() == edited
        assert controller.show_dialog() is dialog
        assert dialog.draft().node_id == "custom.new_plugin.a1b2c3d4"
        assert calls == 1
    finally:
        _close(controller)


def test_visible_name_suggests_filename_until_manual_edits(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(module, "new_plugin_identity", lambda _name: _identity())
    controller = PluginAuthoringController(_Host())
    dialog = controller.show_dialog()
    try:
        dialog.visible_name_edit.setText("Scale Value")

        assert dialog.filename_edit.text() == "scale_value.py"
        assert "name='Scale Value'" in dialog.editor.toPlainText()
        assert dialog.draft().node_id == "custom.new_plugin.a1b2c3d4"

        dialog.filename_edit.setFocus()
        QTest.keyClick(
            dialog.filename_edit,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        QTest.keyClicks(dialog.filename_edit, "manual.py")
        dialog.visible_name_edit.setText("Another Name")

        assert dialog.filename_edit.text() == "manual.py"
        assert "name='Another Name'" in dialog.editor.toPlainText()

        dialog.editor.appendPlainText("# owned source")
        owned_source = dialog.editor.toPlainText()
        dialog.visible_name_edit.setText("Final Name")

        assert dialog.editor.toPlainText() == owned_source
        assert dialog.filename_edit.text() == "manual.py"
    finally:
        _close(controller)


def test_closed_dialog_is_deleted_and_next_action_gets_one_fresh_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:  # noqa: ANN001
    identities = [
        _identity(),
        PluginIdentity(
            visible_name="New Plugin",
            slug="new_plugin",
            filename="new_plugin.py",
            function_name="new_plugin",
            node_id="custom.new_plugin.11223344",
        ),
    ]
    calls = 0

    def create_identity(_name: str) -> PluginIdentity:
        nonlocal calls
        identity = identities[calls]
        calls += 1
        return identity

    monkeypatch.setattr(module, "new_plugin_identity", create_identity)
    _use_saved_root(monkeypatch, tmp_path)
    controller = PluginAuthoringController(_Host())
    first = controller.show_dialog()
    assert controller.save_draft()
    assert controller.saved_path == tmp_path / "new_plugin.py"
    assert first.filename_edit.isReadOnly()

    first.close()
    app = QApplication.instance()
    assert app is not None
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

    assert controller.dialog is None
    assert controller.saved_path is None
    assert sip.isdeleted(first)

    second = controller.show_dialog()
    try:
        assert second is not first
        assert second.draft().node_id == "custom.new_plugin.11223344"
        assert not second.filename_edit.isReadOnly()
        assert not second.reload_button.isEnabled()
        assert controller.show_dialog() is second
        assert calls == 2
    finally:
        _close(controller)


def test_save_validates_and_unsaved_source_refuses_reload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    saved_path = tmp_path / "new_plugin.py"
    saved_calls: list[tuple[str, str, str | None]] = []

    def save(source: str, filename: str, *, expected_source: str | None) -> Path:
        saved_calls.append((source, filename, expected_source))
        return saved_path

    monkeypatch.setattr(
        module,
        "save_plugin_draft",
        save,
    )
    monkeypatch.setattr(module, "validate_plugin_draft", lambda *_args: _report())
    try:
        assert not dialog.reload_button.isEnabled()
        assert dialog.reload_status_label.text() == "Save changes before reloading."

        assert controller.save_draft()
        assert saved_calls == [(dialog.editor.toPlainText(), "new_plugin.py", None)]
        assert controller.saved_path == saved_path
        assert dialog.reload_button.isEnabled()

        dialog.editor.appendPlainText("# changed")

        assert not dialog.reload_button.isEnabled()
        assert not controller.reload_draft()
        assert host.registry_replacement_coordinator.calls == 0
        assert dialog.reload_status_label.text() == "Save changes before reloading."
    finally:
        _close(controller)


def test_first_save_collision_repeat_save_and_external_changes_are_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    collision_root = tmp_path / "collision"
    collision_root.mkdir()
    collision = collision_root / "new_plugin.py"
    collision.write_text("external", encoding="utf-8")
    _use_saved_root(monkeypatch, collision_root)
    _host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    try:
        assert not controller.save_draft()
        assert controller.saved_path is None
        assert collision.read_text(encoding="utf-8") == "external"
        assert list(collision_root.glob("*.py")) == [collision]
    finally:
        _close(controller)

    saved_root = tmp_path / "saved"
    saved_root.mkdir()
    _use_saved_root(monkeypatch, saved_root)
    _host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    try:
        original = dialog.editor.toPlainText()
        assert controller.save_draft()
        destination = saved_root / "new_plugin.py"
        assert dialog.filename_edit.isReadOnly()
        assert destination.read_text(encoding="utf-8") == original

        dialog.editor.appendPlainText("# second save")
        second = dialog.editor.toPlainText()
        assert controller.save_draft()
        assert destination.read_text(encoding="utf-8") == second

        dialog.filename_edit.setText("other.py")
        dialog.editor.appendPlainText("# filename changed")
        assert not controller.save_draft()
        assert destination.read_text(encoding="utf-8") == second
        assert not (saved_root / "other.py").exists()

        dialog.filename_edit.setText("new_plugin.py")
        destination.write_text("external mutation", encoding="utf-8")
        assert not controller.save_draft()
        assert destination.read_text(encoding="utf-8") == "external mutation"

        destination.unlink()
        assert not controller.save_draft()
        assert not destination.exists()
        assert list(saved_root.glob("*.py")) == []
    finally:
        _close(controller)


@pytest.mark.parametrize("tamper", ("mutation", "deletion", "hardlink"))
def test_reload_attests_actual_saved_file_before_coordinator(
    tmp_path: Path,
    monkeypatch,
    tamper: str,
) -> None:
    root = tmp_path / tamper
    root.mkdir()
    _use_saved_root(monkeypatch, root)
    host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    try:
        assert controller.save_draft()
        destination = root / "new_plugin.py"
        if tamper == "mutation":
            destination.write_text("external", encoding="utf-8")
        elif tamper == "deletion":
            destination.unlink()
        else:
            try:
                os.link(destination, root / "linked.py")
            except OSError:
                pytest.skip("hard links are unavailable")

        assert not controller.reload_draft()
        assert host.registry_replacement_coordinator.calls == 0
        assert not dialog.reload_button.isEnabled()
        assert dialog.reload_status_label.text() == "Save changes before reloading."
        assert dialog.diagnostics_tree.topLevelItemCount() == 1
    finally:
        _close(controller)


def test_reload_refuses_reparse_saved_path_before_coordinator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _use_saved_root(monkeypatch, tmp_path)
    host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    try:
        assert controller.save_draft()
        destination = tmp_path / "new_plugin.py"
        monkeypatch.setattr(
            plugin_authoring,
            "is_reparse_point",
            lambda path: Path(path) == destination,
        )

        assert not controller.reload_draft()
        assert host.registry_replacement_coordinator.calls == 0
        assert dialog.diagnostics_tree.topLevelItemCount() == 1
    finally:
        _close(controller)


def test_validate_only_projects_diagnostics_and_preserves_registry(monkeypatch) -> None:  # noqa: ANN001
    host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    current_registry = host.registry
    invalid = _report(success=False)
    monkeypatch.setattr(module, "validate_plugin_draft", lambda *_args: invalid)
    monkeypatch.setattr(
        module,
        "save_plugin_draft",
        lambda *_args: pytest.fail("validate must not save"),
    )
    try:
        assert controller.validate_draft() is invalid
        assert host.registry is current_registry
        assert host.registry_replacement_coordinator.calls == 0
        assert dialog.diagnostics_tree.topLevelItem(0).text(7) == "invalid draft"
    finally:
        _close(controller)


def test_dialog_reload_uses_coordinator_and_projects_success_refusal_and_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    host, controller = _open_controller(monkeypatch)
    dialog = controller.dialog
    assert dialog is not None
    current_registry = host.registry
    monkeypatch.setattr(
        module,
        "save_plugin_draft",
        lambda *_args, **_kwargs: tmp_path / "new_plugin.py",
    )
    monkeypatch.setattr(
        module,
        "read_saved_plugin_draft",
        lambda _path: dialog.editor.toPlainText(),
    )
    monkeypatch.setattr(module, "validate_plugin_draft", lambda *_args: _report())
    try:
        assert controller.save_draft()
        assert controller.reload_draft()
        assert host.registry_replacement_coordinator.calls == 1
        assert dialog.status_label.text() == "Plugins are current."

        issue = RegistryCompatibilityIssue(
            code="node_type_missing",
            message="Node type is still used by an open project.",
            project_id="project",
            workspace_id="workspace",
            node_id="node",
        )
        host.registry_replacement_coordinator.result = SimpleNamespace(
            applied=False,
            report=RegistryCompatibilityReport((issue,)),
            registry=host.registry,
        )
        assert not controller.reload_draft()
        assert dialog.diagnostics_tree.topLevelItem(0).text(7) == issue.message

        host.registry_replacement_coordinator.error = RuntimeError(
            "Cannot replace the registry while a viewer session is active"
        )
        assert not controller.reload_draft()
        assert "viewer session is active" in dialog.diagnostics_tree.topLevelItem(0).text(7)
        assert host.registry is current_registry

        host.registry_replacement_coordinator.error = RuntimeError(
            f"private coordinator path: {tmp_path}"
        )
        assert not controller.reload_draft()
        assert dialog.diagnostics_tree.topLevelItem(0).text(7) == "Plugin reload failed."
        assert str(tmp_path) not in dialog.reload_status_label.text()
    finally:
        _close(controller)


def test_file_reload_and_open_folder_use_bounded_native_feedback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    host = _Host()
    controller = PluginAuthoringController(host)
    messages: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: messages.append(("information", title, text)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, text: messages.append(("warning", title, text)),
    )

    assert controller.reload_plugins()
    assert messages[-1][1] == "Plugins Reloaded"
    assert "bundle(s)" in messages[-1][2]
    assert "Digest:" in messages[-1][2]
    assert "Unavailable nodes:" in messages[-1][2]

    issue = RegistryCompatibilityIssue(
        code="node_type_missing",
        message="Open project uses this node.",
        project_id="project",
        workspace_id="workspace",
    )
    host.registry_replacement_coordinator.result = SimpleNamespace(
        applied=False,
        report=RegistryCompatibilityReport((issue,)),
        registry=host.registry,
    )
    assert not controller.reload_plugins()
    assert messages[-1] == (
        "warning",
        "Reload Plugins Refused",
        "The plugins are incompatible with the open project.\n\n- Open project uses this node.",
    )

    host.registry_replacement_coordinator.error = RuntimeError(
        f"private path: {tmp_path}"
    )
    assert not controller.reload_plugins()
    assert messages[-1] == (
        "warning",
        "Reload Plugins Failed",
        "Plugin reload failed.",
    )
    assert str(tmp_path) not in messages[-1][2]

    host.registry_replacement_coordinator.error = RuntimeError(
        "Cannot replace the registry during an active run"
    )
    assert not controller.reload_plugins()
    assert messages[-1][2] == "Cannot replace the registry during an active run"

    monkeypatch.setattr(module, "plugins_dir", lambda: tmp_path)
    opened: list[Path] = []
    monkeypatch.setattr(
        module.platform_open,
        "open_path_with_default_handler",
        lambda path: opened.append(path) or True,
    )
    assert controller.open_plugins_folder()
    assert opened == [tmp_path]

    monkeypatch.setattr(module.platform_open, "open_path_with_default_handler", lambda _path: False)
    assert not controller.open_plugins_folder()
    assert messages[-1][1] == "Open Plugins Folder Failed"

    monkeypatch.setattr(module, "plugins_dir", lambda: (_ for _ in ()).throw(OSError(tmp_path)))
    assert not controller.open_plugins_folder()
    assert messages[-1] == (
        "warning",
        "Open Plugins Folder Failed",
        "The plugins folder could not be opened.",
    )

    monkeypatch.setattr(module, "plugins_dir", lambda: tmp_path)
    monkeypatch.setattr(
        module.platform_open,
        "open_path_with_default_handler",
        lambda _path: (_ for _ in ()).throw(RuntimeError(tmp_path)),
    )
    assert not controller.open_plugins_folder()
    assert str(tmp_path) not in messages[-1][2]


def test_file_menu_orders_and_wires_plugin_actions_with_bool_signal_argument() -> None:
    window = _ActionWindow()
    try:
        create_window_actions(window)  # type: ignore[arg-type]
        build_window_menu_bar(window)  # type: ignore[arg-type]
        file_menu = next(
            action.menu()
            for action in window.menuBar().actions()
            if action.text() == "&File"
        )
        actions = [action for action in file_menu.actions() if not action.isSeparator()]
        labels = [action.text() for action in actions]
        project_index = labels.index("Project Files...")
        workflow_index = labels.index("Import Custom Workflow...")

        assert labels[project_index + 1 : workflow_index] == [
            "New Plugin...",
            "Reload Plugins",
        ]
        assert actions[project_index + 1] is window.action_new_plugin
        assert actions[project_index + 2] is window.action_reload_plugins

        window.action_new_plugin.trigger()
        window.action_reload_plugins.trigger()
        window.show_plugin_authoring_dialog(True)
        window.reload_plugins(True)

        assert window.plugin_authoring_controller.calls == [
            "show",
            "reload",
            "show",
            "reload",
        ]
        assert window.run_controller.calls == 0
    finally:
        window.close()
        window.deleteLater()
