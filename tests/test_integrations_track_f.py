from __future__ import annotations

import csv
import json
import queue
import smtplib
import tempfile
import types
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from ea_node_editor.execution.protocol_codec import (
    coerce_start_run_command,
)
from ea_node_editor.execution.worker import run_workflow
from ea_node_editor.execution.runtime_snapshot import build_runtime_snapshot
from ea_node_editor.addons.tabular_data.input_node import execute_tabular_input
from ea_node_editor.graph.boundary_adapters import _fallback_node_size
from ea_node_editor.graph.model import GraphModel
from ea_node_editor.graph.records import NodeInstance
from ea_node_editor.graph.validated_mutation import ValidatedGraphMutation
from ea_node_editor.nodes.bootstrap import build_builtin_registry, build_default_registry
from ea_node_editor.nodes.builtin_functions.integrations_email import (
    SOURCE as EMAIL_SOURCE,
)
from ea_node_editor.nodes.builtin_functions.integrations_file_io import (
    SOURCE as FILE_IO_SOURCE,
)
from ea_node_editor.nodes.builtin_functions.integrations_process import (
    SOURCE as PROCESS_SOURCE,
)
from ea_node_editor.nodes.builtin_functions.integrations_spreadsheet import (
    SOURCE as SPREADSHEET_SOURCE,
)
from ea_node_editor.nodes.builtins import integrations_email, integrations_spreadsheet
from ea_node_editor.nodes.builtins.core import PythonScriptNodePlugin
from ea_node_editor.nodes.builtins.integrations_file_io import (
    FILE_IO_NODE_DESCRIPTORS,
    FolderExplorerNodePlugin,
    PathPointerNodePlugin,
    _FOLDER_EXPLORER_DEFAULT_HEIGHT_PX,
    _FOLDER_EXPLORER_DEFAULT_WIDTH_PX,
    _PATH_POINTER_CHAR_WIDTH_PX,
    _PATH_POINTER_MAX_WIDTH_PX,
    _PATH_POINTER_WIDTH_CHROME_PX,
    execute_file_read,
    execute_file_write,
)
from ea_node_editor.nodes.builtins.integrations_email import execute_email_send
from ea_node_editor.nodes.builtins.integrations_spreadsheet import (
    execute_excel_read,
    execute_excel_write,
)
from ea_node_editor.nodes.readiness import evaluate_node_readiness
from ea_node_editor.nodes.function_plugin import (
    INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
    PythonFunctionAdapter,
)
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.nodes.registry import PythonFunctionEntry
from ea_node_editor.nodes.execution_context import ExecutionContext, NodeResult
from ea_node_editor.runtime_contracts.value_refs import (
    RuntimeArtifactRef,
)
from ea_node_editor.runtime_contracts.value_codec import deserialize_runtime_value
from ea_node_editor.platform_paths import default_user_desktop_path
from ea_node_editor.runtime_contracts import DataTree, PATH_DATA_TYPE_ID, TabularDataRef
from ea_node_editor.ui.folder_explorer import FolderExplorerFilesystemService
from ea_node_editor.ui_qml.graph_geometry.anchors import surface_port_local_point
from ea_node_editor.ui_qml.graph_geometry.standard_metrics import (
    _STANDARD_INLINE_ENUM_COMBO_MIN_WIDTH,
    _STANDARD_INLINE_ROW_HORIZONTAL_MARGIN,
    node_surface_metrics,
    resolved_node_surface_size,
)
from tests.repo_owned_catalog_fixture import load_current_repo_owned_catalog


def _context(
    *,
    inputs: dict | None = None,
    properties: dict | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        run_id="run_test",
        node_id="node_test",
        workspace_id="ws_test",
        inputs=dict(inputs or {}),
        properties=dict(properties or {}),
        emit_log=lambda _level, _message: None,
        trigger={},
    )


def _decorated_transform(body: str) -> str:
    indented = "\n".join(f"    {line}" for line in body.splitlines())
    return (
        "@corex.node\n"
        "@corex.input(\"payload\", value_type=corex.Any)\n"
        "@corex.output(\"result\", value_type=corex.Any)\n"
        "def run(ctx, payload):\n"
        f"{indented}\n"
        "    return {\"result\": result}\n"
    )


class IntegrationNodesTrackFTests(unittest.TestCase):
    def test_converted_function_specs_match_frozen_catalog_exactly(self) -> None:
        converted_ids = {
            "io.file_read",
            "io.file_write",
            "io.image_import",
            "io.image_export",
            "io.process_run",
            "io.email_send",
            "io.excel_read",
            "io.excel_write",
        }
        source_modules = (
            ("integrations_file_io.py", FILE_IO_SOURCE),
            ("integrations_process.py", PROCESS_SOURCE),
            ("integrations_email.py", EMAIL_SOURCE),
            ("integrations_spreadsheet.py", SPREADSHEET_SOURCE),
        )
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch(
            "ea_node_editor.nodes.builtin_functions.source_modules",
            return_value=source_modules,
        ):
            registry = build_builtin_registry(
                generation_root=Path(temp_dir) / "generations"
            )

        fixture = load_current_repo_owned_catalog()
        expected = {
            row["spec"]["type_id"]: row["spec"]
            for row in fixture
            if row["spec"]["type_id"] in converted_ids
        }
        self.assertEqual(set(expected), converted_ids)
        for type_id in sorted(converted_ids):
            self.assertEqual(
                json.loads(json.dumps(asdict(registry.get_spec(type_id)))),
                expected[type_id],
            )
            self.assertIsInstance(registry.get_entry(type_id), PythonFunctionEntry)
            self.assertIsNone(registry.descriptor_or_none(type_id))

    def test_external_effect_inputs_use_tree_access_without_reclassifying_readers(
        self,
    ) -> None:
        registry = build_default_registry()
        effect_specs = tuple(
            registry.get_spec(type_id)
            for type_id in (
                "io.file_write",
                "io.email_send",
                "io.process_run",
                "io.excel_write",
            )
        )
        for spec in effect_specs:
            inputs = [port for port in spec.ports if port.direction == "in"]
            self.assertTrue(inputs, spec.type_id)
            self.assertTrue(
                all(port.data_access == "tree" for port in inputs), spec.type_id
            )

        self.assertEqual(registry.get_spec("io.file_read").ports[0].data_access, "item")
        self.assertEqual(registry.get_spec("io.excel_read").ports[0].data_access, "item")
        self.assertTrue(registry.get_spec("io.file_read").ports[0].required)
        self.assertTrue(registry.get_spec("io.excel_read").ports[0].required)

    def test_process_and_email_readiness_is_declared_centrally(self) -> None:
        registry = build_default_registry()
        process_spec = registry.get_spec("io.process_run")
        process_ports = {port.key: port for port in process_spec.ports}
        self.assertTrue(process_ports["command"].required)
        self.assertTrue(process_ports["command"].uses_property_default)

        email_spec = registry.get_spec("io.email_send")
        email_properties = {prop.key: prop.default for prop in email_spec.properties}
        email_issues = evaluate_node_readiness(
            email_spec,
            port_has_value={},
            overridden_port_keys=(),
            properties=email_properties,
        )
        self.assertEqual(
            {issue.target_keys for issue in email_issues},
            {("sender",), ("to",)},
        )
        email_properties["username"] = "user"
        authenticated_issues = evaluate_node_readiness(
            email_spec,
            port_has_value={},
            overridden_port_keys=(),
            properties=email_properties,
        )
        self.assertIn(
            ("password",), {issue.target_keys for issue in authenticated_issues}
        )

    def test_excel_csv_read_write_success_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "rows.csv"
            rows = [
                {"b": "2", "a": "1"},
                {"a": "3", "b": "4"},
            ]

            write_result = execute_excel_write(
                _context(inputs={"rows": rows}, properties={"path": str(output_path)})
            )
            self.assertEqual(write_result.outputs["written_path"], str(output_path))
            self.assertTrue(output_path.exists())

            read_result = execute_excel_read(
                _context(properties={"path": str(output_path)})
            )
            self.assertEqual(
                read_result.outputs["rows"],
                [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}],
            )

    def test_excel_xlsx_dependency_gated_when_openpyxl_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            read_path = Path(temp_dir) / "input.xlsx"
            read_path.write_text("placeholder", encoding="utf-8")
            write_path = Path(temp_dir) / "output.xlsx"
            with mock.patch.object(integrations_spreadsheet, "_openpyxl", None):
                with self.assertRaises(RuntimeError) as read_error:
                    execute_excel_read(
                        _context(properties={"path": str(read_path)})
                    )
                self.assertIn("openpyxl", str(read_error.exception).lower())

                with self.assertRaises(RuntimeError) as write_error:
                    execute_excel_write(
                        _context(
                            inputs={"rows": [{"name": "x"}]},
                            properties={"path": str(write_path)},
                        )
                    )
                message = str(write_error.exception).lower()
                self.assertIn("openpyxl", message)
                self.assertIn("runtime mode: source", message)
                self.assertIn("csv remains supported", message)

    def test_excel_xlsx_dependency_message_in_packaged_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            read_path = Path(temp_dir) / "input.xlsx"
            read_path.write_text("placeholder", encoding="utf-8")
            with (
                mock.patch.object(integrations_spreadsheet, "_openpyxl", None),
                mock.patch.object(
                    integrations_spreadsheet.sys,
                    "frozen",
                    True,
                    create=True,
                ),
            ):
                with self.assertRaises(RuntimeError) as read_error:
                    execute_excel_read(
                        _context(properties={"path": str(read_path)})
                    )
        message = str(read_error.exception).lower()
        self.assertIn("runtime mode: packaged", message)
        self.assertIn("rebuild package", message)
        self.assertIn("csv remains supported", message)

    def test_file_read_write_text_and_json_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            text_path = temp_path / "message.txt"
            json_path = temp_path / "payload.json"

            execute_file_write(
                _context(
                    inputs={"text": "hello world"},
                    properties={"path": str(text_path), "as_json": False},
                )
            )
            text_result = execute_file_read(
                _context(properties={"path": str(text_path)})
            )
            self.assertEqual(text_result.outputs["text"], "hello world")
            quoted_text_result = execute_file_read(
                _context(properties={"path": f'"{text_path}"'})
            )
            self.assertEqual(quoted_text_result.outputs["text"], "hello world")

            payload = {"z": 2, "a": 1}
            execute_file_write(
                _context(
                    inputs={"data": payload},
                    properties={"path": str(json_path), "as_json": True},
                )
            )
            json_result = execute_file_read(
                _context(properties={"path": str(json_path)})
            )
            self.assertEqual(
                json_result.outputs["text"],
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            )

    def test_file_write_rejects_non_finite_json_before_overwriting_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "payload.json"
            path.write_text("sentinel", encoding="utf-8")
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "serialize payload as JSON"):
                        execute_file_write(
                            _context(
                                inputs={"data": {"value": value}},
                                properties={"path": str(path), "as_json": True},
                            )
                        )
                    self.assertEqual(path.read_text(encoding="utf-8"), "sentinel")

    def test_email_send_with_mocked_smtp(self) -> None:
        class FakeSMTP:
            instances: list["FakeSMTP"] = []

            def __init__(self, *, host: str, port: int, timeout: int) -> None:
                self.host = host
                self.port = port
                self.timeout = timeout
                self.started_tls = False
                self.login_args: tuple[str, str] | None = None
                self.messages = []
                FakeSMTP.instances.append(self)

            def __enter__(self) -> "FakeSMTP":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
                return None

            def starttls(self) -> None:
                self.started_tls = True

            def login(self, username: str, password: str) -> None:
                self.login_args = (username, password)

            def send_message(self, message) -> None:  # noqa: ANN001
                self.messages.append(message)

        declaration = discover_plugin_declarations(
            EMAIL_SOURCE,
            filename="integrations_email.py",
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )[0]
        namespace: dict[str, object] = {}
        exec(compile(EMAIL_SOURCE, "integrations_email.py", "exec"), namespace)  # noqa: S102
        adapter = PythonFunctionAdapter(
            declaration.spec,
            namespace[declaration.function_name],  # type: ignore[arg-type]
        )
        properties = {prop.key: prop.default for prop in declaration.spec.properties}
        properties.update(
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 2525,
                "username": "user",
                "password": "pass",
                "sender": "from@example.com",
                "to": "a@example.com, b@example.com",
                "use_tls": True,
            }
        )
        with mock.patch.object(integrations_email.smtplib, "SMTP", FakeSMTP):
            result = adapter.execute(
                _context(inputs={"subject": "", "body": ""}, properties=properties)
            )

        self.assertTrue(result.outputs["sent"])
        smtp = FakeSMTP.instances[-1]
        self.assertEqual(
            (smtp.host, smtp.port, smtp.timeout), ("smtp.example.com", 2525, 10)
        )
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("user", "pass"))
        self.assertEqual(len(smtp.messages), 1)
        self.assertEqual(smtp.messages[0]["From"], "from@example.com")
        self.assertEqual(smtp.messages[0]["To"], "a@example.com, b@example.com")
        self.assertEqual(smtp.messages[0]["Subject"], "")
        self.assertEqual(smtp.messages[0].get_content().strip(), "")

    def test_email_send_backend_errors_remain_failures(self) -> None:
        class FailingSMTP:
            def __init__(self, **_kwargs) -> None:
                return None

            def __enter__(self) -> "FailingSMTP":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
                return None

            def send_message(self, _message) -> None:  # noqa: ANN001
                raise smtplib.SMTPException("boom")

        with mock.patch.object(integrations_email.smtplib, "SMTP", FailingSMTP):
            with self.assertRaises(RuntimeError) as smtp_error:
                execute_email_send(
                    _context(
                        properties={
                            "smtp_host": "localhost",
                            "smtp_port": 25,
                            "sender": "from@example.com",
                            "to": "to@example.com",
                        }
                    )
                )
        self.assertIn("smtp error", str(smtp_error.exception).lower())

    def test_function_shell_replays_helper_warnings_in_order(self) -> None:
        declaration = discover_plugin_declarations(
            EMAIL_SOURCE,
            filename="integrations_email.py",
            allow_reserved_ids=True,
            owner_id=INTERNAL_BUILTIN_FUNCTION_OWNER_ID,
        )[0]
        namespace: dict[str, object] = {}
        exec(compile(EMAIL_SOURCE, "integrations_email.py", "exec"), namespace)  # noqa: S102
        namespace["execute_email_send"] = lambda _ctx: NodeResult(
            outputs={"sent": True},
            warnings=("first", "second"),
        )
        adapter = PythonFunctionAdapter(
            declaration.spec,
            namespace[declaration.function_name],  # type: ignore[arg-type]
        )
        properties = {prop.key: prop.default for prop in declaration.spec.properties}
        properties.update({"sender": "from@example.com", "to": "to@example.com"})

        result = adapter.execute(_context(properties=properties))

        self.assertEqual(result.warnings, ("first", "second"))
        self.assertEqual(
            tuple(warning.code for warning in result.plugin_warnings),
            ("email_send", "email_send"),
        )

    def test_file_and_excel_error_messages_are_clear(self) -> None:
        with self.assertRaises(ValueError) as file_error:
            execute_file_read(_context())
        self.assertIn("file path", str(file_error.exception).lower())

        with tempfile.TemporaryDirectory() as temp_dir:
            bad_path = Path(temp_dir) / "unsupported.bin"
            bad_path.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError) as excel_error:
                execute_excel_read(
                    _context(properties={"path": str(bad_path)})
                )
        self.assertIn("supports only", str(excel_error.exception).lower())

    def test_tabular_data_input_returns_lazy_csv_ref_without_eager_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "rows.csv"
            source.write_text("name,value\nalpha,1\n", encoding="utf-8")

            result = execute_tabular_input(
                _context(properties={"path": str(source)})
            )

        self.assertNotIn("exec_out", result.outputs)
        self.assertIsInstance(result.outputs["table_data"], TabularDataRef)
        self.assertNotIn("rows", result.outputs)
        self.assertNotIn("pandas", result.outputs)
        self.assertNotIn("polars", result.outputs)
        self.assertNotIn("numpy", result.outputs)


class PathPointerNodeTests(unittest.TestCase):
    """Tests for ``io.path_pointer`` (Variant B from the design mockup)."""

    def test_path_pointer_file_mode_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "hello.txt"
            file_path.write_text("hi", encoding="utf-8")
            result = PathPointerNodePlugin().execute(
                _context(
                    properties={
                        "mode": "file",
                        "path": str(file_path),
                        "must_exist": True,
                    }
                )
            )
            self.assertEqual(result.outputs["path"], str(file_path))
            self.assertIs(result.outputs["exists"], True)

    def test_path_pointer_folder_mode_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder_path = Path(temp_dir)
            result = PathPointerNodePlugin().execute(
                _context(
                    properties={
                        "mode": "folder",
                        "path": str(folder_path),
                        "must_exist": True,
                    }
                )
            )
            self.assertEqual(result.outputs["path"], str(folder_path))
            self.assertIs(result.outputs["exists"], True)

    def test_path_pointer_missing_raises_when_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "does_not_exist.rst"
            with self.assertRaises(FileNotFoundError) as cm:
                PathPointerNodePlugin().execute(
                    _context(
                        properties={
                            "mode": "file",
                            "path": str(missing),
                            "must_exist": True,
                        }
                    )
                )
            self.assertIn("does not exist", str(cm.exception).lower())

    def test_path_pointer_missing_tolerated_when_not_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "does_not_exist.rst"
            result = PathPointerNodePlugin().execute(
                _context(
                    properties={
                        "mode": "file",
                        "path": str(missing),
                        "must_exist": False,
                    }
                )
            )
            self.assertEqual(result.outputs["path"], str(missing))
            self.assertIs(result.outputs["exists"], False)

    def test_path_pointer_mode_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "data.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError) as file_as_folder:
                PathPointerNodePlugin().execute(
                    _context(
                        properties={
                            "mode": "folder",
                            "path": str(file_path),
                            "must_exist": True,
                        }
                    )
                )
            self.assertIn("folder", str(file_as_folder.exception).lower())

            with self.assertRaises(ValueError) as folder_as_file:
                PathPointerNodePlugin().execute(
                    _context(
                        properties={
                            "mode": "file",
                            "path": str(temp_dir),
                            "must_exist": True,
                        }
                    )
                )
            self.assertIn("file", str(folder_as_file.exception).lower())

    def test_path_pointer_empty_path_tolerated_when_not_must_exist(self) -> None:
        result = PathPointerNodePlugin().execute(
            _context(properties={"mode": "file", "path": "", "must_exist": False})
        )
        self.assertEqual(result.outputs, {"path": "", "exists": False})

    def test_path_pointer_empty_path_raises_when_must_exist(self) -> None:
        with self.assertRaises(ValueError) as cm:
            PathPointerNodePlugin().execute(
                _context(properties={"mode": "file", "path": "", "must_exist": True})
            )
        self.assertIn("non-empty", str(cm.exception).lower())

    def test_path_pointer_invalid_mode_raises(self) -> None:
        with self.assertRaises(ValueError) as cm:
            PathPointerNodePlugin().execute(
                _context(
                    properties={"mode": "url", "path": "whatever", "must_exist": False}
                )
            )
        self.assertIn("'file' or 'folder'", str(cm.exception))

    def test_path_pointer_registered_in_default_registry(self) -> None:
        """Smoke test: node is discoverable from the default registry with expected spec."""
        registry = build_default_registry()
        spec = registry.spec_or_none("io.path_pointer")
        self.assertIsNotNone(spec)
        # Ports: both outputs, passive (no exec_in/out)
        port_keys = {port.key for port in spec.ports}
        self.assertEqual(port_keys, {"path", "exists"})
        for port in spec.ports:
            self.assertEqual(port.direction, "out")
        # All properties live in the single "Source" group
        self.assertEqual(
            {prop.key for prop in spec.properties},
            {"mode", "path", "must_exist", "show_full_path"},
        )
        for prop in spec.properties:
            self.assertEqual(
                prop.group, "Source", f"property {prop.key} not in Source group"
            )
        self.assertEqual(spec.runtime_behavior, "passive")
        # Folder icon requested by the user.
        self.assertEqual(spec.icon, "integrations/folder.svg")
        # Passive nodes suppress title icons by default; Path Pointer opts
        # back in so the folder glyph actually renders in the node header.
        self.assertTrue(spec.show_title_icon)

    def test_path_pointer_show_full_path_property_defaults_to_false(self) -> None:
        spec = PathPointerNodePlugin().spec()
        show_full = next(p for p in spec.properties if p.key == "show_full_path")
        self.assertEqual(show_full.type, "bool")
        self.assertEqual(show_full.default, False)
        self.assertEqual(show_full.inspector_editor, "toggle")
        self.assertEqual(show_full.group, "Source")


class FolderExplorerNodeTests(unittest.TestCase):
    """Tests for the passive ``io.folder_explorer`` node contract."""

    def test_folder_explorer_registered_in_file_io_descriptor_chain(self) -> None:
        descriptor_type_ids = {
            descriptor.spec.type_id for descriptor in FILE_IO_NODE_DESCRIPTORS
        }
        self.assertIn("io.folder_explorer", descriptor_type_ids)

        registry = build_default_registry()
        spec = registry.spec_or_none("io.folder_explorer")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.type_id, "io.folder_explorer")
        self.assertEqual(spec.display_name, "Folder Explorer")
        self.assertEqual(spec.category_path, ("Input / Output",))
        self.assertEqual(spec.runtime_behavior, "passive")
        self.assertEqual(spec.icon, "integrations/folder.svg")
        self.assertTrue(spec.show_title_icon)

        self.assertEqual(len(spec.ports), 1)
        current_port = spec.ports[0]
        self.assertEqual(current_port.key, "current")
        self.assertEqual(current_port.direction, "out")
        self.assertEqual(current_port.kind, "data")
        self.assertEqual(current_port.data_type, PATH_DATA_TYPE_ID)
        self.assertEqual(current_port.side, "")
        self.assertTrue(current_port.exposed)

        self.assertEqual(len(spec.properties), 1)
        current_path = spec.properties[0]
        self.assertEqual(current_path.key, "current_path")
        self.assertEqual(current_path.type, "path")
        self.assertEqual(current_path.default, default_user_desktop_path())
        self.assertEqual(current_path.inline_editor, "")
        self.assertEqual(current_path.inspector_editor, "path")
        self.assertEqual(current_path.group, "Source")

    def test_folder_explorer_defaults_to_desktop_path_and_larger_bottom_port_layout(
        self,
    ) -> None:
        spec = FolderExplorerNodePlugin().spec()
        node = NodeInstance(
            node_id="folder-node",
            type_id="io.folder_explorer",
            title="Folder Explorer",
            x=0.0,
            y=0.0,
            properties={},
        )

        width, height = resolved_node_surface_size(node, spec)
        port_x, port_y = surface_port_local_point(
            node, spec, "current", width=width, height=height
        )

        self.assertGreaterEqual(width, _FOLDER_EXPLORER_DEFAULT_WIDTH_PX)
        self.assertGreaterEqual(height, _FOLDER_EXPLORER_DEFAULT_HEIGHT_PX)
        self.assertGreaterEqual(port_x, width - 16.0)
        self.assertGreaterEqual(port_y, height - 32.0)

        result = FolderExplorerNodePlugin().execute(_context(properties={}))
        self.assertEqual(
            Path(result.outputs["current"]).resolve(strict=False),
            Path(default_user_desktop_path()),
        )

    def test_folder_explorer_outputs_current_folder_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = FolderExplorerNodePlugin().execute(
                _context(properties={"current_path": temp_dir})
            )
        self.assertEqual(result.outputs, {"current": temp_dir})

    def test_folder_explorer_created_node_current_path_drives_real_temp_listing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Assets").mkdir()
            (root / "readme.txt").write_text("hello", encoding="utf-8")
            model = GraphModel()
            node = model.add_node(
                model.active_workspace.workspace_id,
                "io.folder_explorer",
                "Folder Explorer",
                100.0,
                160.0,
                properties={"current_path": str(root)},
            )

            result = FolderExplorerNodePlugin().execute(
                _context(properties=node.properties)
            )
            listing = FolderExplorerFilesystemService().list_directory(
                result.outputs["current"]
            )

        self.assertEqual(
            Path(result.outputs["current"]).resolve(strict=False),
            root.resolve(strict=False),
        )
        self.assertEqual(listing.directory_path, str(root.resolve(strict=False)))
        self.assertEqual(
            [entry.name for entry in listing.entries], ["Assets", "readme.txt"]
        )

    def test_folder_explorer_rejects_non_folder_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            with self.assertRaises(FileNotFoundError) as missing_error:
                FolderExplorerNodePlugin().execute(
                    _context(properties={"current_path": str(missing)})
                )
            self.assertIn("does not exist", str(missing_error.exception).lower())

            file_path = Path(temp_dir) / "file.txt"
            file_path.write_text("not a folder", encoding="utf-8")
            with self.assertRaises(ValueError) as file_error:
                FolderExplorerNodePlugin().execute(
                    _context(properties={"current_path": str(file_path)})
                )
            self.assertIn("folder", str(file_error.exception).lower())


class PathPointerWidthResolverTests(unittest.TestCase):
    """Tests for the dynamic node width when ``show_full_path`` is toggled."""

    @staticmethod
    def _node(
        properties: dict | None = None, *, custom_width: float | None = None
    ) -> types.SimpleNamespace:
        """Lightweight NodeInstance stand-in — resolver only reads these attrs."""
        return types.SimpleNamespace(
            properties=dict(properties or {}),
            custom_width=custom_width,
            custom_height=None,
        )

    def _spec(self):
        return PathPointerNodePlugin().spec()

    def test_show_full_path_false_returns_base_width(self) -> None:
        node = self._node(
            {"show_full_path": False, "path": "C:/some/very/long/path/here.rst"}
        )
        width, height = _fallback_node_size(node, self._spec())
        # Base default width is 240 (no custom_width set).
        self.assertEqual(width, 240.0)
        self.assertEqual(height, 160.0)

    def test_show_full_path_true_expands_width_for_long_path(self) -> None:
        long_path = "C:/runs/job_042/results/deep/nested/folder/file.rst"  # 52 chars
        node = self._node({"show_full_path": True, "path": long_path})
        width, _height = _fallback_node_size(node, self._spec())
        # Must be wider than the default 240 for a 52-char path.
        self.assertGreater(width, 240.0)
        # And wide enough to fit the path plus the graph row chrome.
        expected_width = (
            _PATH_POINTER_WIDTH_CHROME_PX + _PATH_POINTER_CHAR_WIDTH_PX * len(long_path)
        )
        self.assertGreaterEqual(width, expected_width)

    def test_show_full_path_true_expands_standard_surface_size_for_graph_payload(
        self,
    ) -> None:
        long_path = "C:/runs/job_042/results/deep/nested/folder/file.rst"
        node = NodeInstance(
            node_id="path_pointer",
            type_id="io.path_pointer",
            title="Path Pointer",
            x=0.0,
            y=0.0,
            properties={"show_full_path": True, "path": long_path},
        )
        width, _height = resolved_node_surface_size(node, self._spec())
        expected_width = (
            _PATH_POINTER_WIDTH_CHROME_PX + _PATH_POINTER_CHAR_WIDTH_PX * len(long_path)
        )
        self.assertGreaterEqual(width, expected_width)

    def test_folder_mode_standard_surface_width_fits_inline_mode_dropdown(self) -> None:
        node = NodeInstance(
            node_id="path_pointer",
            type_id="io.path_pointer",
            title="Path Pointer",
            x=0.0,
            y=0.0,
            properties={"mode": "folder", "path": "", "show_full_path": False},
        )

        spec = self._spec()
        metrics = node_surface_metrics(node, spec)
        width, _height = resolved_node_surface_size(
            node,
            spec,
            surface_metrics=metrics,
        )
        available_control_width = (
            width
            - metrics.body_left_margin
            - metrics.body_right_margin
            - 2.0 * _STANDARD_INLINE_ROW_HORIZONTAL_MARGIN
        )

        self.assertEqual(width, metrics.default_width)
        self.assertGreaterEqual(width, metrics.min_width)
        self.assertGreaterEqual(
            available_control_width,
            _STANDARD_INLINE_ENUM_COMBO_MIN_WIDTH,
        )

    def test_show_full_path_true_uses_tight_width_for_typical_absolute_path(
        self,
    ) -> None:
        path = "C:/Users/user/Documents/COREX/examples/custom_workflows/demo.cxproj"
        node = self._node({"show_full_path": True, "path": path})
        width, _height = _fallback_node_size(node, self._spec())
        self.assertLessEqual(width, 925.0)

    def test_show_full_path_true_short_path_does_not_shrink_below_base(self) -> None:
        node = self._node({"show_full_path": True, "path": "a.txt"})
        width, _height = _fallback_node_size(node, self._spec())
        # Base width (240) already fits a 5-char path; width must not shrink.
        self.assertEqual(width, 240.0)

    def test_show_full_path_true_respects_user_custom_width_when_larger(self) -> None:
        node = self._node(
            {"show_full_path": True, "path": "a.txt"},
            custom_width=500.0,
        )
        width, _height = _fallback_node_size(node, self._spec())
        # User's drag-resize wider than computed must win.
        self.assertEqual(width, 500.0)

    def test_show_full_path_true_empty_path_returns_base_width(self) -> None:
        node = self._node({"show_full_path": True, "path": ""})
        width, _height = _fallback_node_size(node, self._spec())
        self.assertEqual(width, 240.0)

    def test_show_full_path_true_width_is_capped(self) -> None:
        node = self._node({"show_full_path": True, "path": "x" * 5000})
        width, _height = _fallback_node_size(node, self._spec())
        # Very long paths are capped so the graph remains navigable.
        self.assertLessEqual(width, _PATH_POINTER_MAX_WIDTH_PX)
        self.assertGreater(width, 240.0)

    def test_toggle_off_restores_last_user_custom_width(self) -> None:
        """Per user intent: flipping show_full_path off reverts to default, or user's last resize."""
        # User resized to 320 before ever turning the toggle on.
        node = self._node(
            {"show_full_path": False, "path": "C:/very/long/path.rst"},
            custom_width=320.0,
        )
        width, _h = _fallback_node_size(node, self._spec())
        self.assertEqual(width, 320.0)

    def test_path_pointer_resolver_does_not_affect_other_node_types(self) -> None:
        """Sanity: the per-type override is keyed by type_id and must not leak."""
        other_spec = build_default_registry().get_spec("io.file_read")
        node = self._node(
            {"show_full_path": True, "path": "C:/anything/at/all.txt"},
            custom_width=200.0,
        )
        width, _h = _fallback_node_size(node, other_spec)
        # File Read has no override, so base/custom width is returned untouched.
        self.assertEqual(width, 200.0)


class IntegrationFlowSmokeTests(unittest.TestCase):
    _data_types = build_default_registry().data_types

    @classmethod
    def _output_tree(cls, event: dict, port_key: str) -> DataTree:
        tree = deserialize_runtime_value(
            event["outputs"][port_key]["value"],
            catalog=cls._data_types,
        )
        assert isinstance(tree, DataTree)
        return tree

    @classmethod
    def _output_value(cls, event: dict, port_key: str) -> object:
        return cls._output_tree(event, port_key).branches[0][1][0]

    def _run_model(self, model: GraphModel, workspace_id: str) -> list[dict]:
        return self._run_model_with_runtime_snapshot(model, workspace_id)

    def _run_model_with_runtime_snapshot(
        self,
        model: GraphModel,
        workspace_id: str,
        *,
        project_path: str = "",
    ) -> list[dict]:
        event_queue: queue.Queue = queue.Queue()
        registry = build_default_registry()
        runtime_snapshot = build_runtime_snapshot(
            model.project,
            workspace_id=workspace_id,
            registry=registry,
        )
        run_workflow(
            coerce_start_run_command(
                {
                    "run_id": "run_smoke",
                    "workspace_id": workspace_id,
                    "project_path": project_path,
                    "runtime_snapshot": runtime_snapshot,
                    "trigger": {},
                    "plugin_bundles": registry.plugin_bundle_refs(),
                    "plugin_fingerprint": registry.plugin_fingerprint(),
                    "registry_contract_fingerprint": registry.contract_fingerprint(),
                    "addon_runtime_config": registry.addon_runtime_config(),
                },
                catalog=registry.data_types,
            ),
            event_queue,
        )
        events: list[dict] = []
        while not event_queue.empty():
            events.append(event_queue.get())
        return events

    def test_smoke_excel_input_python_transform_excel_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_csv = temp_path / "input.csv"
            output_csv = temp_path / "output.csv"
            with input_csv.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["name", "count"])
                writer.writeheader()
                writer.writerow({"name": "alpha", "count": "1"})

            model = GraphModel()
            workspace = model.active_workspace
            mutations = ValidatedGraphMutation(
                model,
                workspace.workspace_id,
                build_default_registry(),
            )
            excel_read = mutations.add_node(
                type_id="io.excel_read",
                title="Excel Read",
                x=120,
                y=0,
                properties={"path": str(input_csv)},
            )
            script = model.add_node(
                workspace.workspace_id,
                "core.python_script",
                "Python Script",
                240,
                0,
                properties={
                    "script": _decorated_transform(
                        "row = payload or {}\n"
                        "result = {\n"
                        "    'name': str(row.get('name', '')).upper(),\n"
                        "    'count': int(row.get('count', 0)) + 1,\n"
                        "}\n"
                    )
                },
            )
            excel_write = model.add_node(
                workspace.workspace_id,
                "io.excel_write",
                "Excel Write",
                360,
                0,
                properties={"path": str(output_csv)},
            )

            model.add_edge(
                workspace.workspace_id,
                excel_read.node_id,
                "rows",
                script.node_id,
                "payload",
            )
            model.add_edge(
                workspace.workspace_id,
                script.node_id,
                "result",
                excel_write.node_id,
                "rows",
            )

            events = self._run_model(model, workspace.workspace_id)
            event_types = [event["type"] for event in events]
            self.assertIn("run_completed", event_types)
            self.assertNotIn("run_failed", event_types)

            with output_csv.open("r", encoding="utf-8", newline="") as handle:
                written_rows = list(csv.DictReader(handle))
            self.assertEqual(written_rows, [{"count": "2", "name": "ALPHA"}])

    def test_smoke_file_input_python_transform_file_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.txt"
            output_path = temp_path / "output.txt"
            input_path.write_text("hello workflow", encoding="utf-8")

            model = GraphModel()
            workspace = model.active_workspace
            mutations = ValidatedGraphMutation(
                model,
                workspace.workspace_id,
                build_default_registry(),
            )
            file_read = mutations.add_node(
                type_id="io.file_read",
                title="File Read",
                x=120,
                y=0,
                properties={"path": str(input_path)},
            )
            script = model.add_node(
                workspace.workspace_id,
                "core.python_script",
                "Python Script",
                240,
                0,
                properties={
                    "script": _decorated_transform(
                        "result = str(payload).upper()"
                    )
                },
            )
            file_write = model.add_node(
                workspace.workspace_id,
                "io.file_write",
                "File Write",
                360,
                0,
                properties={"path": str(output_path)},
            )

            model.add_edge(
                workspace.workspace_id,
                file_read.node_id,
                "text",
                script.node_id,
                "payload",
            )
            model.add_edge(
                workspace.workspace_id,
                script.node_id,
                "result",
                file_write.node_id,
                "text",
            )

            events = self._run_model(model, workspace.workspace_id)
            event_types = [event["type"] for event in events]
            self.assertIn("run_completed", event_types)
            self.assertNotIn("run_failed", event_types)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "HELLO WORKFLOW")

    def test_smoke_file_write_blank_path_stages_managed_output_for_downstream_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "managed_file_output.cxproj"

            model = GraphModel()
            workspace = model.active_workspace
            script = model.add_node(
                workspace.workspace_id,
                "core.python_script",
                "Python Script",
                120,
                0,
                properties={
                    "script": _decorated_transform(
                        "result = 'managed output payload'"
                    )
                },
            )
            file_write = model.add_node(
                workspace.workspace_id,
                "io.file_write",
                "File Write",
                240,
                0,
                properties={"path": "", "as_json": False},
            )
            file_read = model.add_node(
                workspace.workspace_id,
                "io.file_read",
                "File Read",
                360,
                0,
            )

            model.add_edge(
                workspace.workspace_id,
                script.node_id,
                "result",
                file_write.node_id,
                "text",
            )
            model.add_edge(
                workspace.workspace_id,
                file_write.node_id,
                "written_path",
                file_read.node_id,
                "path",
            )

            events = self._run_model_with_runtime_snapshot(
                model,
                workspace.workspace_id,
                project_path=str(project_path),
            )

            event_types = [event["type"] for event in events]
            self.assertIn("run_completed", event_types)
            self.assertNotIn("run_failed", event_types)

            write_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == file_write.node_id
            )
            written_ref = self._output_value(write_completed, "written_path")
            self.assertIsInstance(written_ref, RuntimeArtifactRef)
            self.assertEqual(written_ref.scope, "staged")

            read_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == file_read.node_id
            )
            self.assertEqual(
                self._output_value(read_completed, "text"),
                "managed output payload",
            )

            staged_files = list(
                project_path.with_name("managed_file_output.data").rglob("*.txt")
            )
            self.assertTrue(staged_files)

    def test_connected_blank_file_write_path_overrides_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            project_path = temp_path / "connected_blank_path.cxproj"
            configured_path = temp_path / "sentinel.txt"
            configured_path.write_text("sentinel", encoding="utf-8")

            model = GraphModel()
            workspace = model.active_workspace
            blank_path = model.add_node(
                workspace.workspace_id,
                "core.python_script",
                "Blank Path",
                120,
                0,
                properties={"script": _decorated_transform("result = ''")},
            )
            payload = model.add_node(
                workspace.workspace_id,
                "core.constant",
                "Payload",
                120,
                100,
                properties={"value": "managed from connected blank"},
            )
            file_write = model.add_node(
                workspace.workspace_id,
                "io.file_write",
                "File Write",
                240,
                0,
                properties={"path": str(configured_path), "as_json": False},
            )
            model.add_edge(
                workspace.workspace_id,
                blank_path.node_id,
                "result",
                file_write.node_id,
                "path",
            )
            model.add_edge(
                workspace.workspace_id,
                payload.node_id,
                "value",
                file_write.node_id,
                "text",
            )

            events = self._run_model_with_runtime_snapshot(
                model,
                workspace.workspace_id,
                project_path=str(project_path),
            )

            self.assertNotIn("run_failed", {event["type"] for event in events})
            write_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == file_write.node_id
            )
            written_ref = self._output_value(write_completed, "written_path")
            self.assertIsInstance(written_ref, RuntimeArtifactRef)
            self.assertEqual(written_ref.scope, "staged")
            self.assertEqual(configured_path.read_text(encoding="utf-8"), "sentinel")
            staged_files = list(
                project_path.with_name("connected_blank_path.data").rglob("*.txt")
            )
            self.assertEqual(len(staged_files), 1)
            self.assertEqual(
                staged_files[0].read_text(encoding="utf-8"),
                "managed from connected blank",
            )

    def test_smoke_excel_write_blank_path_stages_managed_output_for_downstream_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "managed_excel_output.cxproj"

            model = GraphModel()
            workspace = model.active_workspace
            first_row = model.add_node(
                workspace.workspace_id,
                "core.constant",
                "First Row",
                120,
                0,
                properties={"value": {"name": "alpha", "count": 1}},
            )
            second_row = model.add_node(
                workspace.workspace_id,
                "core.constant",
                "Second Row",
                120,
                100,
                properties={"value": {"name": "beta", "count": 2}},
            )
            excel_write = model.add_node(
                workspace.workspace_id,
                "io.excel_write",
                "Excel Write",
                240,
                0,
                properties={"path": ""},
            )
            excel_read = model.add_node(
                workspace.workspace_id,
                "io.excel_read",
                "Excel Read",
                360,
                0,
            )

            model.add_edge(
                workspace.workspace_id,
                first_row.node_id,
                "value",
                excel_write.node_id,
                "rows",
            )
            model.add_edge(
                workspace.workspace_id,
                second_row.node_id,
                "value",
                excel_write.node_id,
                "rows",
            )
            model.add_edge(
                workspace.workspace_id,
                excel_write.node_id,
                "written_path",
                excel_read.node_id,
                "path",
            )

            events = self._run_model_with_runtime_snapshot(
                model,
                workspace.workspace_id,
                project_path=str(project_path),
            )

            event_types = [event["type"] for event in events]
            self.assertIn("run_completed", event_types)
            self.assertNotIn("run_failed", event_types)

            write_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == excel_write.node_id
            )
            written_ref = self._output_value(write_completed, "written_path")
            self.assertIsInstance(written_ref, RuntimeArtifactRef)
            self.assertEqual(written_ref.scope, "staged")

            read_completed = next(
                event
                for event in events
                if event.get("type") == "node_settled"
                and event.get("node_id") == excel_read.node_id
            )
            self.assertEqual(
                list(self._output_tree(read_completed, "rows").branches[0][1]),
                [
                    {"count": "1", "name": "alpha"},
                    {"count": "2", "name": "beta"},
                ],
            )

            staged_files = list(
                project_path.with_name("managed_excel_output.data").rglob("*.csv")
            )
            self.assertTrue(staged_files)

    def test_python_script_default_output_is_input_payload(self) -> None:
        result = PythonScriptNodePlugin().execute(
            _context(
                inputs={"payload": {"x": 1}},
                properties={"script": _decorated_transform("result = payload")},
            )
        )
        self.assertEqual(result.outputs["result"], {"x": 1})


if __name__ == "__main__":
    unittest.main()
