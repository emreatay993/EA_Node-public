from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILTINS_ROOT = PROJECT_ROOT / "ea_node_editor" / "nodes" / "builtins"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ea_node_editor.nodes.bootstrap import build_builtin_registry  # noqa: E402
from ea_node_editor.nodes.builtins.icon_catalog import BUILTIN_NODE_ICONS  # noqa: E402
from ea_node_editor.ui_qml.node_title_icon_sources import (  # noqa: E402
    NODE_TITLE_ICON_ASSET_ROOT,
    SUPPORTED_NODE_TITLE_ICON_SUFFIXES,
    resolve_node_title_icon_source,
)


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_file_backed_icon(icon: str) -> bool:
    return Path(icon).suffix.casefold() in SUPPORTED_NODE_TITLE_ICON_SUFFIXES


def _uses_iconless_visual_contract(spec) -> bool:  # noqa: ANN001 - registry spec
    return spec.type_id == "core.trigger" or (
        spec.runtime_behavior == "passive" and spec.surface_family == "flowchart"
    )


def _inline_icon_offenders() -> list[str]:
    offenders: list[str] = []
    for path in sorted(BUILTINS_ROOT.glob("*.py")):
        if path.name in {"__init__.py", "icon_catalog.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) not in {"NodeTypeSpec", "node_type", "builtin_node_type", "builtin_node_type_spec"}:
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
    return offenders


def main() -> int:
    errors: list[str] = []

    offenders = _inline_icon_offenders()
    if offenders:
        errors.append("built-in node modules define inline node icons:\n" + "\n".join(f"  {item}" for item in offenders))

    for spec in build_builtin_registry().all_specs():
        if _uses_iconless_visual_contract(spec):
            if spec.type_id in BUILTIN_NODE_ICONS or spec.icon:
                errors.append(
                    f"{spec.type_id!r} must use the iconless visual contract"
                )
            continue
        expected_icon = BUILTIN_NODE_ICONS.get(spec.type_id)
        if expected_icon is None:
            errors.append(f"missing BUILTIN_NODE_ICONS entry for registered built-in {spec.type_id!r}")
            continue
        if spec.icon != expected_icon:
            errors.append(f"{spec.type_id!r} spec.icon={spec.icon!r} does not match catalog {expected_icon!r}")

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
    if inventory != expected_inventory:
        missing = sorted(expected_inventory - inventory)
        extra = sorted(inventory - expected_inventory)
        if missing:
            errors.append("missing title-icon assets:\n" + "\n".join(f"  {item}" for item in missing))
        if extra:
            errors.append("unreferenced title-icon assets:\n" + "\n".join(f"  {item}" for item in extra))

    for type_id, icon in BUILTIN_NODE_ICONS.items():
        if not _is_file_backed_icon(icon):
            continue
        expected_path = NODE_TITLE_ICON_ASSET_ROOT / icon
        if not expected_path.is_file():
            errors.append(f"{type_id!r} references missing asset {icon!r}")
            continue
        resolved = resolve_node_title_icon_source(icon)
        if resolved != expected_path.resolve().as_uri():
            errors.append(f"{type_id!r} icon {icon!r} did not resolve to its local asset")

    if errors:
        print("Node title icon validation failed:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("Node title icon validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
