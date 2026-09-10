from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ea_node_editor.nodes.node_specs import NodeTypeSpec
from ea_node_editor.nodes.plugin_contracts import PluginProvenance
from ea_node_editor.ui.shell.controllers.workspace_io_ops import WorkspaceIOOps


class _SignalStub:
    def __init__(self) -> None:
        self.calls = 0

    def emit(self) -> None:
        self.calls += 1


class _RegistryStub:
    def __init__(self) -> None:
        self._specs: dict[str, object] = {}
        self._provenance: dict[str, PluginProvenance] = {}

    def add_available(self, type_id: str) -> None:
        self._specs[type_id] = SimpleNamespace(type_id=type_id)

    def add_plugin_spec(self, spec: NodeTypeSpec, provenance: PluginProvenance) -> None:
        self._specs[spec.type_id] = spec
        self._provenance[spec.type_id] = provenance

    def all_specs(self) -> list[object]:
        return list(self._specs.values())

    def provenance_or_none(self, type_id: str) -> PluginProvenance | None:
        return self._provenance.get(type_id)

    def spec_or_none(self, type_id: str) -> object | None:
        return self._specs.get(type_id)


class _ControllerStub:
    def __init__(self) -> None:
        self._definitions: list[dict[str, object]] = []

    def _custom_workflow_definitions(self) -> list[dict[str, object]]:
        return list(self._definitions)

    def _set_custom_workflow_definitions(self, definitions: list[dict[str, object]]) -> None:
        self._definitions = list(definitions)

    def _prompt_custom_workflow_export_definition(
        self,
        definitions: list[dict[str, object]],
    ) -> dict[str, object] | None:
        if not definitions:
            return None
        return definitions[0]


class _HostStub:
    def __init__(self) -> None:
        self.registry = _RegistryStub()
        self.node_library_changed = _SignalStub()
        self.project_meta_changed = _SignalStub()
        self.registry_replacement_coordinator = _RegistryReplacementCoordinatorStub(self)


class _RegistryReplacementCoordinatorStub:
    def __init__(self, host: _HostStub) -> None:
        self._host = host
        self._manifest = None
        self._available_node_ids: tuple[str, ...] = ()

    def prepare(self, manifest, *available_node_ids: str) -> None:  # noqa: ANN001
        self._manifest = manifest
        self._available_node_ids = tuple(available_node_ids)

    def import_package(self, _path: Path):  # noqa: ANN201
        for type_id in self._available_node_ids:
            self._host.registry.add_available(type_id)
        self._host.node_library_changed.emit()
        return SimpleNamespace(
            applied=True,
            report=SimpleNamespace(issues=()),
            registry=self._host.registry,
            package_manifest=self._manifest,
        )


class WorkspaceIONodePackageTests(unittest.TestCase):
    def test_import_node_package_reports_success_when_declared_nodes_become_available(self) -> None:
        host = _HostStub()
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]
        manifest = SimpleNamespace(name="packet_pkg", version="2.0.0", nodes=["packet.alpha"])
        host.registry_replacement_coordinator.prepare(manifest, "packet.alpha")

        with (
            patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=("C:/tmp/packet_pkg.cxpkg", "Node Package (*.cxpkg)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
        ):
            ops.import_node_package()

        self.assertEqual(host.node_library_changed.calls, 1)
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)
        self.assertIn("with 1 node(s)", info_mock.call_args.args[2])
        self.assertIn("now available in the Node Library", info_mock.call_args.args[2])

    def test_import_node_package_accepts_already_available_declared_nodes(self) -> None:
        host = _HostStub()
        host.registry.add_available("packet.alpha")
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]
        manifest = SimpleNamespace(name="packet_pkg", version="2.1.0", nodes=["packet.alpha"])
        host.registry_replacement_coordinator.prepare(manifest, "packet.alpha")

        with (
            patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=("C:/tmp/packet_pkg.cxpkg", "Node Package (*.cxpkg)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
        ):
            ops.import_node_package()

        self.assertEqual(host.node_library_changed.calls, 1)
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)
        self.assertIn("already available", info_mock.call_args.args[2])

    def test_import_node_package_warns_when_declared_nodes_remain_unavailable(self) -> None:
        host = _HostStub()
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]
        manifest = SimpleNamespace(name="packet_pkg", version="2.0.0", nodes=["packet.alpha"])
        host.registry_replacement_coordinator.prepare(manifest)

        with (
            patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=("C:/tmp/packet_pkg.cxpkg", "Node Package (*.cxpkg)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
        ):
            ops.import_node_package()

        self.assertEqual(host.node_library_changed.calls, 1)
        self.assertEqual(info_mock.call_count, 0)
        self.assertEqual(warning_mock.call_count, 1)
        self.assertEqual(warning_mock.call_args.args[1], "Import Incomplete")
        self.assertIn("not currently available", warning_mock.call_args.args[2])

    def test_import_node_package_allows_approved_no_node_outcome(self) -> None:
        host = _HostStub()
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]
        manifest = SimpleNamespace(name="packet_pkg", version="2.0.0", nodes=[])
        host.registry_replacement_coordinator.prepare(manifest)

        with (
            patch(
                "PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=("C:/tmp/packet_pkg.cxpkg", "Node Package (*.cxpkg)"),
            ),
            patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
            patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
        ):
            ops.import_node_package()

        self.assertEqual(host.node_library_changed.calls, 1)
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)
        self.assertIn("declares no node types", info_mock.call_args.args[2])

    def test_export_node_package_passes_explicit_package_sources(self) -> None:
        host = _HostStub()
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]

        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            package_dir = plugins_root / "packet_pkg"
            package_dir.mkdir(parents=True, exist_ok=True)
            (package_dir / "helper.py").write_text('DISPLAY_NAME = "Packet"\n', encoding="utf-8")
            (package_dir / "package_plugin.py").write_text("VALUE = 'plugin'\n", encoding="utf-8")
            (package_dir / "node_package.json").write_text(
                json.dumps(
                    {
                        "name": "packet_pkg",
                        "schema_version": 2,
                        "version": "3.2.1",
                        "author": "Packet Tests",
                        "description": "Exportable package",
                        "modules": ["package_plugin.py"],
                        "sources": [
                            {"path": "helper.py", "sha256": "0" * 64},
                            {"path": "package_plugin.py", "sha256": "0" * 64},
                        ],
                        "assets": [],
                        "nodes": [
                            {
                                "id": "packet.alpha",
                                "module": "package_plugin.py",
                                "function": "packet_alpha",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            host.registry.add_plugin_spec(
                NodeTypeSpec(
                    type_id="packet.alpha",
                    display_name="Packet",
                    category_path=("Packet Tests",),
                    icon="packet",
                    ports=(),
                    properties=(),
                ),
                PluginProvenance(
                    kind="package",
                    source_path=(package_dir / "package_plugin.py").resolve(),
                    package_root=package_dir.resolve(),
                    package_name="packet_pkg",
                ),
            )

            with (
                patch(
                    "ea_node_editor.ui.shell.controllers.workspace_io_ops.plugins_dir",
                    return_value=plugins_root,
                ),
                patch(
                    "PyQt6.QtWidgets.QInputDialog.getText",
                    return_value=("packet_pkg_export", True),
                ),
                patch(
                    "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
                    return_value=(str(Path(temp_dir) / "exports" / "packet_pkg_export.cxpkg"), "Node Package (*.cxpkg)"),
                ),
                patch(
                    "ea_node_editor.nodes.package_manager.export_package",
                    return_value=Path(temp_dir) / "exports" / "packet_pkg_export.cxpkg",
                ) as export_mock,
                patch("PyQt6.QtWidgets.QMessageBox.information") as info_mock,
                patch("PyQt6.QtWidgets.QMessageBox.warning") as warning_mock,
            ):
                ops.export_node_package()

        self.assertEqual(export_mock.call_count, 1)
        export_sources, manifest, output_path = export_mock.call_args.args
        export_assets = export_mock.call_args.kwargs["assets"]
        self.assertEqual(
            [source.archive_name for source in export_sources],
            ["helper.py", "package_plugin.py"],
        )
        self.assertEqual(export_assets, [])
        self.assertEqual(manifest.name, "packet_pkg_export")
        self.assertEqual(manifest.version, "3.2.1")
        self.assertEqual(manifest.author, "Packet Tests")
        self.assertEqual(manifest.description, "Exportable package")
        self.assertEqual(manifest.nodes, ["packet.alpha"])
        self.assertEqual(output_path, Path(temp_dir) / "exports" / "packet_pkg_export.cxpkg")
        self.assertEqual(info_mock.call_count, 1)
        self.assertEqual(warning_mock.call_count, 0)

    def test_custom_workflow_and_node_package_import_filters_remain_separate(self) -> None:
        host = _HostStub()
        ops = WorkspaceIOOps(host, _ControllerStub())  # type: ignore[arg-type]
        dialog_calls: list[tuple[str, str]] = []

        def _fake_get_open_file_name(
            _parent: object,
            title: str,
            _directory: str,
            file_filter: str,
        ) -> tuple[str, str]:
            dialog_calls.append((title, file_filter))
            return ("", file_filter)

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", side_effect=_fake_get_open_file_name):
            ops.import_custom_workflow()
            ops.import_node_package()

        self.assertEqual(
            dialog_calls,
            [
                ("Import Custom Workflow", "Custom Workflow (*.cxwf)"),
                ("Import Node Package", "Node Package (*.cxpkg)"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
