from __future__ import annotations

import ast
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 project venv
    import tomli as tomllib

from ea_node_editor.nodes.bootstrap import build_builtin_registry
from ea_node_editor.nodes.builtins.icon_catalog import BUILTIN_NODE_ICONS
from ea_node_editor.ui_qml.node_title_icon_sources import (
    NODE_TITLE_ICON_ASSET_ROOT,
    SUPPORTED_NODE_TITLE_ICON_SUFFIXES,
    resolve_node_title_icon_source,
    title_icon_source_for_node_payload,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
SPEC_PATH = PROJECT_ROOT / "ea_node_editor.spec"
BUILTINS_ROOT = PROJECT_ROOT / "ea_node_editor" / "nodes" / "builtins"

_EXPECTED_PACKAGE_DATA_PATTERNS = {
    "assets/node_title_icons/**/*.svg",
    "assets/node_title_icons/**/*.png",
    "assets/node_title_icons/**/*.jpg",
    "assets/node_title_icons/**/*.jpeg",
}


def _is_file_backed_icon(icon: str) -> bool:
    return Path(icon).suffix.casefold() in SUPPORTED_NODE_TITLE_ICON_SUFFIXES


def _uses_iconless_visual_contract(spec) -> bool:  # noqa: ANN001 - test helper mirrors loose descriptor inputs.
    return spec.type_id == "core.trigger" or (
        spec.runtime_behavior == "passive" and spec.surface_family == "flowchart"
    )


class NodeTitleIconAssetTests(unittest.TestCase):
    def test_ssh_sftp_icons_replace_retired_hpc_assets(self) -> None:
        self.assertEqual(
            {
                type_id: BUILTIN_NODE_ICONS[type_id]
                for type_id in (
                    "ssh_sftp.secret",
                    "ssh_sftp.host",
                    "ssh_sftp.run_command",
                    "ssh_sftp.run_script",
                    "ssh_sftp.upload",
                    "ssh_sftp.download",
                )
            },
            {
                "ssh_sftp.secret": "ssh_sftp/lock.svg",
                "ssh_sftp.host": "ssh_sftp/server.svg",
                "ssh_sftp.run_command": "ssh_sftp/terminal.svg",
                "ssh_sftp.run_script": "ssh_sftp/code.svg",
                "ssh_sftp.upload": "ssh_sftp/cloud_upload.svg",
                "ssh_sftp.download": "ssh_sftp/cloud_download.svg",
            },
        )
        self.assertTrue(
            {"hpc.submit", "hpc.monitor", "hpc.fetch_result"}.isdisjoint(BUILTIN_NODE_ICONS)
        )
        self.assertFalse((NODE_TITLE_ICON_ASSET_ROOT / "hpc").exists())

    def test_registered_builtin_specs_use_central_icon_catalog(self) -> None:
        self.assertTrue(BUILTIN_NODE_ICONS)
        observed_type_ids = set()

        for spec in build_builtin_registry().all_specs():
            if _uses_iconless_visual_contract(spec):
                self.assertNotIn(spec.type_id, BUILTIN_NODE_ICONS)
                self.assertEqual(spec.icon, "")
                self.assertEqual(title_icon_source_for_node_payload(spec), "")
                continue

            observed_type_ids.add(spec.type_id)
            self.assertIn(spec.type_id, BUILTIN_NODE_ICONS)
            self.assertEqual(spec.icon, BUILTIN_NODE_ICONS[spec.type_id])

            if _is_file_backed_icon(spec.icon):
                asset_path = NODE_TITLE_ICON_ASSET_ROOT / spec.icon
                self.assertTrue(asset_path.is_file(), msg=f"missing asset for {spec.type_id}: {asset_path}")
                self.assertIn(asset_path.suffix.casefold(), SUPPORTED_NODE_TITLE_ICON_SUFFIXES)
                self.assertEqual(resolve_node_title_icon_source(spec.icon), asset_path.resolve().as_uri())
                if spec.runtime_behavior in {"active", "compile_only"} or spec.show_title_icon:
                    self.assertEqual(title_icon_source_for_node_payload(spec), asset_path.resolve().as_uri())
                else:
                    self.assertEqual(title_icon_source_for_node_payload(spec), "")

        self.assertTrue(observed_type_ids.issubset(BUILTIN_NODE_ICONS))

    def test_title_icon_assets_exist_for_all_file_backed_catalog_entries(self) -> None:
        self.assertEqual(NODE_TITLE_ICON_ASSET_ROOT, PROJECT_ROOT / "ea_node_editor" / "assets" / "node_title_icons")

        for type_id, icon in BUILTIN_NODE_ICONS.items():
            if not _is_file_backed_icon(icon):
                continue
            with self.subTest(type_id=type_id):
                asset_path = NODE_TITLE_ICON_ASSET_ROOT / icon
                self.assertTrue(asset_path.is_file(), msg=f"missing asset for {type_id}: {asset_path}")
                self.assertEqual(resolve_node_title_icon_source(icon), asset_path.resolve().as_uri())

    def test_title_icon_asset_inventory_matches_catalog_file_paths(self) -> None:
        self.assertTrue(NODE_TITLE_ICON_ASSET_ROOT.is_dir())
        inventory = {
            asset_path.relative_to(NODE_TITLE_ICON_ASSET_ROOT).as_posix()
            for asset_path in NODE_TITLE_ICON_ASSET_ROOT.rglob("*")
            if asset_path.is_file()
            and asset_path.suffix.casefold() in SUPPORTED_NODE_TITLE_ICON_SUFFIXES
        }

        expected_inventory = {
            icon
            for icon in BUILTIN_NODE_ICONS.values()
            if _is_file_backed_icon(icon)
        }
        self.assertEqual(inventory, expected_inventory)
        self.assertTrue(
            all(Path(relative_path).suffix.casefold() in SUPPORTED_NODE_TITLE_ICON_SUFFIXES for relative_path in inventory)
        )

    def test_symbolic_icon_names_remain_unrendered_without_local_asset_paths(self) -> None:
        symbolic_icons = {
            icon
            for icon in BUILTIN_NODE_ICONS.values()
            if not _is_file_backed_icon(icon)
        }
        self.assertTrue(symbolic_icons)
        for icon_name in symbolic_icons:
            with self.subTest(icon_name=icon_name):
                self.assertEqual(resolve_node_title_icon_source(icon_name), "")

    def test_builtin_node_modules_do_not_define_node_icons_inline(self) -> None:
        offenders: list[str] = []
        for path in sorted(BUILTINS_ROOT.glob("*.py")):
            if path.name in {"__init__.py", "icon_catalog.py"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                if func_name not in {"NodeTypeSpec", "node_type", "builtin_node_type", "builtin_node_type_spec"}:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "icon":
                        if (
                            path.name in {"core.py", "passive_flowchart.py"}
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value == ""
                        ):
                            continue
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{keyword.lineno}")

        self.assertEqual(offenders, [])

    def test_title_icon_packaging_metadata_includes_node_title_icon_assets(self) -> None:
        pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
        package_data = set(pyproject["tool"]["setuptools"]["package-data"]["ea_node_editor"])
        self.assertTrue(_EXPECTED_PACKAGE_DATA_PATTERNS.issubset(package_data))

        spec_text = SPEC_PATH.read_text(encoding="utf-8")
        for pattern in _EXPECTED_PACKAGE_DATA_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, spec_text)
