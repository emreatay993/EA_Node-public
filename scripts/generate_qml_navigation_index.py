#!/usr/bin/env python3
"""Generate a compact QML navigation index for agent routing."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "qml_navigation_index.md"
DEFAULT_JSON_OUTPUT_PATH = REPO_ROOT / "docs" / "qml_navigation_index.json"
DEFAULT_QML_ROOTS = (Path("ea_node_editor/ui_qml"),)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "node_modules",
    "venv",
    ".venv",
}
EXCLUDED_RELATIVE_PREFIXES = (
    (".claude", "worktrees"),
    ("ea_node_editor", "web_assets", "excalidraw_host"),
)
MAX_LIST_ITEMS = 18
SCHEMA_VERSION = 3

_IMPORT_RE = re.compile(r"^\s*import\s+(.+?)\s*$")
_ROOT_OR_COMPONENT_RE = re.compile(r"^\s*([A-Za-z_][\w.]*)(?:\s+as\s+\w+)?\s*\{")
_ID_RE = re.compile(r"\bid\s*:\s*([A-Za-z_]\w*)")
_OBJECT_NAME_RE = re.compile(r'\bobjectName\s*:\s*"([^"]+)"')
_PROPERTY_RE = re.compile(
    r"\b(?:default\s+)?(?:required\s+)?(?:readonly\s+)?property\s+"
    r"(?P<kind>alias|[A-Za-z_][\w.<>]*)\s+(?P<name>[A-Za-z_]\w*)"
)
_SIGNAL_RE = re.compile(r"\bsignal\s+([A-Za-z_]\w*)\s*\(")
_FUNCTION_RE = re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\(")
_MODEL_RE = re.compile(r"\bmodel\s*:\s*(.+)")
_DELEGATE_RE = re.compile(r"\bdelegate\s*:\s*(.+)")
_SOURCE_RE = re.compile(r"\b(source|sourceComponent)\s*:\s*(.+)")
_HANDLER_RE = re.compile(r"(?<![\w.])(?P<name>(?:[A-Za-z_]\w*\.)?on[A-Z]\w*)\s*:")
_CONNECTION_TARGET_RE = re.compile(r"\btarget\s*:\s*(.+)")
_PROPERTY_BINDING_RE = re.compile(r"^(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*:\s*(?P<detail>.+)$")
_COMPONENT_REF_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\b")
_PROPERTY_BINDING_SKIP_NAMES = {
    "id",
    "objectName",
    "model",
    "delegate",
    "source",
    "sourceComponent",
    "target",
}
_DYNAMIC_RELATIONSHIP_KINDS = {"model", "delegate", "source", "sourceComponent"}
_COMPONENT_RELATIONSHIP_KINDS = {"delegate", "sourceComponent"}
_RELATIONSHIP_KEYWORDS = {
    "as",
    "const",
    "else",
    "false",
    "function",
    "if",
    "instanceof",
    "let",
    "new",
    "null",
    "return",
    "true",
    "typeof",
    "undefined",
    "var",
}


@dataclass(frozen=True)
class SymbolRef:
    name: str
    line: int


@dataclass(frozen=True)
class TypedSymbolRef:
    kind: str
    name: str
    line: int


@dataclass(frozen=True)
class DynamicRef:
    kind: str
    line: int
    detail: str


@dataclass(frozen=True)
class DetailRef:
    kind: str
    name: str
    line: int
    detail: str = ""


@dataclass(frozen=True)
class SymbolAnchorSpec:
    anchor: str
    kind: str
    name: str
    line: int
    detail: str = ""


@dataclass(frozen=True)
class QmlComponentEntry:
    path: str
    component_name: str
    aliases: tuple[str, ...]
    root_component: str
    imports: tuple[str, ...]
    ids: tuple[SymbolRef, ...]
    object_names: tuple[SymbolRef, ...]
    properties: tuple[TypedSymbolRef, ...]
    signals: tuple[SymbolRef, ...]
    functions: tuple[SymbolRef, ...]
    instantiated_components: tuple[SymbolRef, ...]
    dynamic_refs: tuple[DynamicRef, ...]
    signal_handlers: tuple[DetailRef, ...] = ()
    connections: tuple[DetailRef, ...] = ()
    property_bindings: tuple[DetailRef, ...] = ()
    local_component_refs: tuple[DetailRef, ...] = ()


@dataclass(frozen=True)
class QmlNavigationIndex:
    entries: tuple[QmlComponentEntry, ...]

    @property
    def repeater_count(self) -> int:
        return sum(1 for entry in self.entries for ref in entry.dynamic_refs if ref.kind == "Repeater")

    @property
    def loader_count(self) -> int:
        return sum(1 for entry in self.entries for ref in entry.dynamic_refs if ref.kind == "Loader")


def display_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _parse_csv_paths(raw_paths: Sequence[str] | None, defaults: Sequence[Path]) -> tuple[Path, ...]:
    if raw_paths is None:
        return tuple(defaults)
    parsed: list[Path] = []
    for raw_path in raw_paths:
        for part in raw_path.split(","):
            cleaned = part.strip()
            if cleaned:
                parsed.append(Path(cleaned))
    return tuple(parsed)


def is_excluded_path(relative_path: Path) -> bool:
    parts = tuple(part.lower() for part in relative_path.parts)
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True
    for prefix in EXCLUDED_RELATIVE_PREFIXES:
        if parts[: len(prefix)] == prefix:
            return True
    return False


def _iter_files_pruning_excluded_dirs(root_path: Path, repo_root: Path) -> Iterable[Path]:
    if root_path.is_file():
        yield root_path
        return

    repo_root_resolved = repo_root.resolve()
    for current_dir, dir_names, file_names in os.walk(root_path):
        current_path = Path(current_dir)
        kept_dir_names: list[str] = []
        for dir_name in dir_names:
            child_dir = current_path / dir_name
            if dir_name.lower() in EXCLUDED_DIR_NAMES:
                continue
            try:
                relative_child = child_dir.resolve().relative_to(repo_root_resolved)
            except ValueError:
                kept_dir_names.append(dir_name)
                continue
            if is_excluded_path(relative_child):
                continue
            kept_dir_names.append(dir_name)
        dir_names[:] = kept_dir_names

        for file_name in file_names:
            yield current_path / file_name


def iter_qml_files(repo_root: Path, qml_roots: Sequence[Path]) -> tuple[Path, ...]:
    seen: set[Path] = set()
    files: list[Path] = []

    for qml_root in qml_roots:
        root_path = qml_root if qml_root.is_absolute() else repo_root / qml_root
        if not root_path.exists():
            continue
        for candidate in _iter_files_pruning_excluded_dirs(root_path, repo_root):
            if candidate.suffix.lower() != ".qml" or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            try:
                relative_path = resolved.relative_to(repo_root.resolve())
            except ValueError:
                continue
            if is_excluded_path(relative_path) or resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)

    return tuple(sorted(files, key=lambda path: display_path(path, repo_root).lower()))


def _without_inline_comment(text: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            return text[:index].rstrip()
        index += 1
    return text.rstrip()


def _clean_qml_lines(text: str) -> tuple[tuple[int, str], ...]:
    cleaned: list[tuple[int, str]] = []
    in_block_comment = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        while True:
            if in_block_comment:
                end_index = line.find("*/")
                if end_index < 0:
                    line = ""
                    break
                line = line[end_index + 2 :]
                in_block_comment = False
                continue
            start_index = line.find("/*")
            if start_index < 0:
                break
            end_index = line.find("*/", start_index + 2)
            if end_index < 0:
                line = line[:start_index]
                in_block_comment = True
                break
            line = line[:start_index] + line[end_index + 2 :]
        stripped = _without_inline_comment(line).strip()
        if stripped:
            cleaned.append((line_number, stripped))
    return tuple(cleaned)


def _dedupe_symbol_refs(refs: Iterable[SymbolRef]) -> tuple[SymbolRef, ...]:
    seen: set[str] = set()
    result: list[SymbolRef] = []
    for ref in refs:
        if ref.name in seen:
            continue
        seen.add(ref.name)
        result.append(ref)
    return tuple(result)


def _dedupe_typed_symbol_refs(refs: Iterable[TypedSymbolRef]) -> tuple[TypedSymbolRef, ...]:
    seen: set[tuple[str, str]] = set()
    result: list[TypedSymbolRef] = []
    for ref in refs:
        key = (ref.kind, ref.name)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return tuple(result)


def _dedupe_dynamic_refs(refs: Iterable[DynamicRef]) -> tuple[DynamicRef, ...]:
    seen: set[tuple[str, int, str]] = set()
    result: list[DynamicRef] = []
    for ref in refs:
        key = (ref.kind, ref.line, ref.detail)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return tuple(result)


def _dedupe_detail_refs(refs: Iterable[DetailRef]) -> tuple[DetailRef, ...]:
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    result: list[DetailRef] = []
    for ref in refs:
        stable_detail = (
            ref.detail.replace("\\", "/") if ref.kind == "localComponent" else ""
        )
        stable_targets = (
            _stable_relationship_targets(ref.detail)
            if ref.kind == "binding"
            else ()
        )
        key = (ref.kind, ref.name, stable_detail, stable_targets)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return tuple(result)


def _component_aliases(entry_path: str, component_name: str) -> tuple[str, ...]:
    filename = f"{component_name}.qml"
    windows_path = entry_path.replace("/", "\\")
    candidates = (component_name, filename, entry_path, windows_path)
    return tuple(dict.fromkeys(candidates))


def _clean_qml_value(value: str) -> str:
    cleaned = value.strip()
    if "{" in cleaned:
        cleaned = cleaned.split("{", 1)[0].strip()
    return cleaned.rstrip("}").strip()


def _mask_string_literals(value: str) -> tuple[str, tuple[str, ...]]:
    """Mask quoted text while retaining literal values for path detection."""
    masked: list[str] = []
    literals: list[str] = []
    index = 0
    while index < len(value):
        quote = value[index]
        if quote not in {'"', "'", "`"}:
            masked.append(quote)
            index += 1
            continue

        masked.append(" ")
        index += 1
        literal: list[str] = []
        while index < len(value):
            char = value[index]
            if char == "\\" and index + 1 < len(value):
                literal.append(value[index + 1])
                index += 2
                continue
            if char == quote:
                index += 1
                break
            literal.append(char)
            index += 1
        literals.append("".join(literal))
    return "".join(masked), tuple(literals)


def _normalized_relationship_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith(("data:", "http://", "https://")):
        return ""
    normalized = normalized.split("?", 1)[0].split("#", 1)[0]
    if "/" not in normalized and not re.search(r"\.[A-Za-z][A-Za-z0-9]{0,7}$", normalized):
        return ""
    return re.sub(r"(?<!:)/{2,}", "/", normalized)


def _stable_relationship_targets(value: str) -> tuple[str, ...]:
    """Extract stable identifiers and paths without retaining literal source."""
    masked, literals = _mask_string_literals(value)
    targets: list[str] = []
    for literal in literals:
        if path := _normalized_relationship_path(literal):
            targets.append(path)
    for match in _COMPONENT_REF_RE.finditer(masked):
        candidate = match.group(0)
        if candidate.casefold() not in _RELATIONSHIP_KEYWORDS:
            targets.append(candidate)
    return tuple(dict.fromkeys(targets))


def _is_property_declaration(line: str) -> bool:
    return bool(_PROPERTY_RE.search(line))


def _component_ref_candidates(value: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in _COMPONENT_REF_RE.finditer(_clean_qml_value(value)):
        candidate = match.group(0)
        if candidate in {"true", "false", "null", "undefined"}:
            continue
        candidates.append(candidate)
        if "." in candidate:
            candidates.append(candidate.rsplit(".", 1)[-1])
    return tuple(dict.fromkeys(candidates))


def _local_component_sources(
    ref: DynamicRef,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if ref.kind == "source":
        _masked, literals = _mask_string_literals(ref.detail)
        sources: list[tuple[str, tuple[str, ...]]] = []
        for literal in literals:
            path = _normalized_relationship_path(literal)
            if path.casefold().endswith(".qml"):
                sources.append((path, (Path(path).stem,)))
        return tuple(sources)
    if ref.kind not in _COMPONENT_RELATIONSHIP_KINDS:
        return ()

    masked, _literals = _mask_string_literals(ref.detail)
    return tuple(
        (target, _component_ref_candidates(target))
        for target in _stable_relationship_targets(masked)
    )


def _root_component(cleaned_lines: Sequence[tuple[int, str]]) -> str:
    for _line_number, line in cleaned_lines:
        if line.startswith(("import ", "pragma ")):
            continue
        match = _ROOT_OR_COMPONENT_RE.match(line)
        if match:
            return match.group(1)
    return ""


def parse_qml_file(path: Path, repo_root: Path) -> QmlComponentEntry:
    text = path.read_text(encoding="utf-8-sig")
    cleaned_lines = _clean_qml_lines(text)
    imports: list[str] = []
    ids: list[SymbolRef] = []
    object_names: list[SymbolRef] = []
    properties: list[TypedSymbolRef] = []
    signals: list[SymbolRef] = []
    functions: list[SymbolRef] = []
    instantiated_components: list[SymbolRef] = []
    dynamic_refs: list[DynamicRef] = []
    signal_handlers: list[DetailRef] = []
    connections: list[DetailRef] = []
    property_bindings: list[DetailRef] = []
    component_stack: list[str] = []

    for line_number, line in cleaned_lines:
        if import_match := _IMPORT_RE.match(line):
            imports.append(import_match.group(1).strip())
            continue

        component_name_for_line = ""
        if component_match := _ROOT_OR_COMPONENT_RE.match(line):
            component_name_for_line = component_match.group(1)

        for match in _ID_RE.finditer(line):
            ids.append(SymbolRef(match.group(1), line_number))
        for match in _OBJECT_NAME_RE.finditer(line):
            object_names.append(SymbolRef(match.group(1), line_number))
        for match in _PROPERTY_RE.finditer(line):
            properties.append(TypedSymbolRef(match.group("kind"), match.group("name"), line_number))
        for match in _SIGNAL_RE.finditer(line):
            signals.append(SymbolRef(match.group(1), line_number))
        for match in _FUNCTION_RE.finditer(line):
            functions.append(SymbolRef(match.group(1), line_number))
        for match in _HANDLER_RE.finditer(line):
            signal_handlers.append(DetailRef("handler", match.group("name"), line_number))

        in_connections = "Connections" in component_stack or component_name_for_line == "Connections"
        if target_match := _CONNECTION_TARGET_RE.search(line):
            if in_connections:
                target = _clean_qml_value(target_match.group(1))
                if target:
                    connections.append(DetailRef("target", target, line_number, line))

        if binding_match := _PROPERTY_BINDING_RE.match(line):
            binding_name = binding_match.group("name")
            binding_detail = _clean_qml_value(binding_match.group("detail"))
            is_handler_binding = any(ref.line == line_number for ref in signal_handlers)
            if (
                binding_name not in _PROPERTY_BINDING_SKIP_NAMES
                and not is_handler_binding
                and not _is_property_declaration(line)
                and binding_detail
            ):
                property_bindings.append(
                    DetailRef("binding", binding_name, line_number, binding_detail)
                )

        if component_name_for_line:
            component_name = component_name_for_line
            if component_name and component_name[0].isupper():
                instantiated_components.append(SymbolRef(component_name, line_number))
            if component_name in {"Repeater", "Loader", "ListView", "Instantiator", "Component"}:
                dynamic_refs.append(DynamicRef(component_name, line_number, line))

        if model_match := _MODEL_RE.search(line):
            dynamic_refs.append(DynamicRef("model", line_number, _clean_qml_value(model_match.group(1))))
        if delegate_match := _DELEGATE_RE.search(line):
            dynamic_refs.append(DynamicRef("delegate", line_number, _clean_qml_value(delegate_match.group(1))))
        if source_match := _SOURCE_RE.search(line):
            dynamic_refs.append(
                DynamicRef(source_match.group(1), line_number, _clean_qml_value(source_match.group(2)))
            )

        if component_name_for_line and line.count("{") > line.count("}"):
            component_stack.append(component_name_for_line)
        leading_close = re.match(r"^}+", line)
        close_count = len(leading_close.group(0)) if leading_close else 0
        for _ in range(close_count):
            if component_stack:
                component_stack.pop()

    root_component = _root_component(cleaned_lines)
    instantiated = tuple(
        ref for ref in _dedupe_symbol_refs(instantiated_components) if ref.name != root_component
    )
    entry_path = display_path(path, repo_root)
    return QmlComponentEntry(
        path=entry_path,
        component_name=path.stem,
        aliases=_component_aliases(entry_path, path.stem),
        root_component=root_component,
        imports=tuple(dict.fromkeys(imports)),
        ids=_dedupe_symbol_refs(ids),
        object_names=_dedupe_symbol_refs(object_names),
        properties=_dedupe_typed_symbol_refs(properties),
        signals=_dedupe_symbol_refs(signals),
        functions=_dedupe_symbol_refs(functions),
        instantiated_components=instantiated,
        dynamic_refs=_dedupe_dynamic_refs(dynamic_refs),
        signal_handlers=_dedupe_detail_refs(signal_handlers),
        connections=_dedupe_detail_refs(connections),
        property_bindings=_dedupe_detail_refs(property_bindings),
    )


def _resolve_local_component_refs(entries: Sequence[QmlComponentEntry]) -> tuple[QmlComponentEntry, ...]:
    by_name: dict[str, list[QmlComponentEntry]] = {}
    for entry in entries:
        by_name.setdefault(entry.component_name, []).append(entry)

    resolved_entries: list[QmlComponentEntry] = []
    for entry in entries:
        refs: list[DetailRef] = []
        source_refs: list[tuple[int, str, tuple[str, ...]]] = [
            *(
                (ref.line, ref.name, _component_ref_candidates(ref.name))
                for ref in entry.instantiated_components
            ),
            *(
                (ref.line, name, candidates)
                for ref in entry.dynamic_refs
                for name, candidates in _local_component_sources(ref)
            ),
        ]
        for line, relationship_name, candidate_names in source_refs:
            for candidate_name in candidate_names:
                target_entries = by_name.get(candidate_name, ())
                for target_entry in target_entries:
                    if target_entry.path == entry.path:
                        continue
                    refs.append(
                        DetailRef(
                            "localComponent",
                            relationship_name,
                            line,
                            target_entry.path,
                        )
                    )
        resolved_entries.append(
            replace(entry, local_component_refs=_dedupe_detail_refs(refs))
        )
    return tuple(resolved_entries)


def build_index_data(
    repo_root: Path,
    qml_roots: Sequence[Path] = DEFAULT_QML_ROOTS,
) -> QmlNavigationIndex:
    entries = tuple(parse_qml_file(path, repo_root) for path in iter_qml_files(repo_root, qml_roots))
    return QmlNavigationIndex(
        entries=_resolve_local_component_refs(entries)
    )


def _format_path_list(paths: Sequence[Path]) -> str:
    return ", ".join(f"`{path.as_posix()}`" for path in paths)


def _format_aliases(aliases: Sequence[str]) -> str:
    if not aliases:
        return "_None_"
    return ", ".join(f"`{alias}`" for alias in aliases)


def _format_symbol_refs(refs: Sequence[SymbolRef], *, max_items: int = MAX_LIST_ITEMS) -> str:
    if not refs:
        return "_None_"
    items = [f"`{ref.name}`" for ref in refs[:max_items]]
    if len(refs) > max_items:
        items.append(f"... +{len(refs) - max_items} more")
    return ", ".join(items)


def _format_typed_symbol_refs(
    refs: Sequence[TypedSymbolRef], *, max_items: int = MAX_LIST_ITEMS
) -> str:
    if not refs:
        return "_None_"
    items = [f"`{ref.name}: {ref.kind}`" for ref in refs[:max_items]]
    if len(refs) > max_items:
        items.append(f"... +{len(refs) - max_items} more")
    return ", ".join(items)


def _format_imports(imports: Sequence[str], *, max_items: int = MAX_LIST_ITEMS) -> str:
    if not imports:
        return "_None_"
    items = [f"`{import_value}`" for import_value in imports[:max_items]]
    if len(imports) > max_items:
        items.append(f"... +{len(imports) - max_items} more")
    return ", ".join(items)


def _format_dynamic_refs(refs: Sequence[DynamicRef], *, max_items: int = MAX_LIST_ITEMS) -> str:
    unique_refs = _unique_dynamic_relationship_refs(refs)
    if not unique_refs:
        return "_None_"
    items: list[str] = []
    for ref in unique_refs[:max_items]:
        targets = _dynamic_relationship_targets(ref)
        target_text = " -> " + ", ".join(f"`{target}`" for target in targets) if targets else ""
        items.append(f"`{ref.kind}`{target_text}")
    if len(unique_refs) > max_items:
        items.append(f"... +{len(unique_refs) - max_items} more")
    return "; ".join(items)


def _format_detail_refs(
    refs: Sequence[DetailRef],
    *,
    max_items: int = MAX_LIST_ITEMS,
    include_detail: bool = False,
    include_targets: bool = False,
) -> str:
    if not refs:
        return "_None_"
    items: list[str] = []
    for ref in refs[:max_items]:
        detail = f": `{ref.detail}`" if include_detail and ref.detail else ""
        targets = _stable_relationship_targets(ref.detail) if include_targets else ()
        target_text = " -> " + ", ".join(f"`{target}`" for target in targets) if targets else ""
        items.append(f"`{ref.kind}` `{ref.name}`{detail}{target_text}")
    if len(refs) > max_items:
        items.append(f"... +{len(refs) - max_items} more")
    return "; ".join(items)


def _format_compact_symbol_names(refs: Sequence[SymbolRef], *, max_items: int = 8) -> str:
    if not refs:
        return "_None_"
    items = [f"`{ref.name}`" for ref in refs[:max_items]]
    if len(refs) > max_items:
        items.append(f"... +{len(refs) - max_items} more")
    return ", ".join(items)


def _format_compact_dynamic_kinds(refs: Sequence[DynamicRef], *, max_items: int = 8) -> str:
    if not refs:
        return "_None_"
    seen: set[str] = set()
    items: list[str] = []
    for ref in refs:
        if ref.kind in seen:
            continue
        seen.add(ref.kind)
        items.append(f"`{ref.kind}`")
        if len(items) >= max_items:
            break
    if len(seen) < len({ref.kind for ref in refs}):
        items.append("...")
    return ", ".join(items)


def _symbol_ref_to_dict(ref: SymbolRef) -> dict[str, str]:
    return {"name": ref.name}


def _typed_symbol_ref_to_dict(ref: TypedSymbolRef) -> dict[str, str]:
    return {"kind": ref.kind, "name": ref.name}


def _dynamic_relationship_targets(ref: DynamicRef) -> tuple[str, ...]:
    if ref.kind not in _DYNAMIC_RELATIONSHIP_KINDS:
        return ()
    return _stable_relationship_targets(ref.detail)


def _unique_dynamic_relationship_refs(
    refs: Sequence[DynamicRef],
) -> tuple[DynamicRef, ...]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[DynamicRef] = []
    for ref in refs:
        key = (ref.kind, _dynamic_relationship_targets(ref))
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return tuple(result)


def _dynamic_ref_to_dict(ref: DynamicRef) -> dict[str, object]:
    payload: dict[str, object] = {"kind": ref.kind}
    if targets := _dynamic_relationship_targets(ref):
        payload["targets"] = list(targets)
    return payload


def _detail_ref_to_dict(
    ref: DetailRef,
    *,
    include_detail: bool = False,
    include_targets: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {"kind": ref.kind, "name": ref.name}
    if include_detail and ref.detail:
        payload["detail"] = ref.detail
    if include_targets and (targets := _stable_relationship_targets(ref.detail)):
        payload["targets"] = list(targets)
    return payload


def _symbol_anchor_to_dict(ref: SymbolAnchorSpec) -> dict[str, str]:
    payload = {
        "anchor": ref.anchor,
        "kind": ref.kind,
        "name": ref.name,
    }
    if ref.detail and ref.kind in {"property", "localComponent"}:
        payload["detail"] = ref.detail
    return payload


def _entry_to_dict(entry: QmlComponentEntry, class_name: str) -> dict[str, object]:
    return {
        "path": entry.path,
        "component_name": entry.component_name,
        "aliases": list(entry.aliases),
        "root_component": entry.root_component,
        "imports": list(entry.imports),
        "ids": [_symbol_ref_to_dict(ref) for ref in entry.ids],
        "object_names": [_symbol_ref_to_dict(ref) for ref in entry.object_names],
        "properties": [_typed_symbol_ref_to_dict(ref) for ref in entry.properties],
        "signals": [_symbol_ref_to_dict(ref) for ref in entry.signals],
        "functions": [_symbol_ref_to_dict(ref) for ref in entry.functions],
        "instantiated_components": [
            _symbol_ref_to_dict(ref) for ref in entry.instantiated_components
        ],
        "dynamic_refs": [
            _dynamic_ref_to_dict(ref)
            for ref in _unique_dynamic_relationship_refs(entry.dynamic_refs)
        ],
        "signal_handlers": [_detail_ref_to_dict(ref) for ref in entry.signal_handlers],
        "connections": [_detail_ref_to_dict(ref) for ref in entry.connections],
        "property_bindings": [
            _detail_ref_to_dict(ref, include_targets=True)
            for ref in entry.property_bindings
        ],
        "local_component_refs": [
            _detail_ref_to_dict(ref, include_detail=True)
            for ref in entry.local_component_refs
        ],
        "symbol_anchors": [
            _symbol_anchor_to_dict(ref) for ref in _symbol_anchor_specs(entry, class_name)
        ],
    }


def render_json(
    index_data: QmlNavigationIndex,
    qml_roots: Sequence[Path] = DEFAULT_QML_ROOTS,
) -> str:
    class_names = _anchor_class_names(index_data.entries)
    payload = {
        "version": SCHEMA_VERSION,
        "generated_by": "scripts/generate_qml_navigation_index.py",
        "qml_roots": [path.as_posix() for path in qml_roots],
        "summary": {
            "qml_files": len(index_data.entries),
            "repeater_constructs": index_data.repeater_count,
            "loader_constructs": index_data.loader_count,
            "signal_handlers": sum(len(entry.signal_handlers) for entry in index_data.entries),
            "connections": sum(len(entry.connections) for entry in index_data.entries),
            "property_bindings": sum(len(entry.property_bindings) for entry in index_data.entries),
            "local_component_refs": sum(len(entry.local_component_refs) for entry in index_data.entries),
        },
        "entries": [_entry_to_dict(entry, class_names[entry.path]) for entry in index_data.entries],
    }
    return json.dumps(payload, indent=2, ensure_ascii=True) + "\n"


def _pascal_identifier(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return "Component"
    identifier = "".join(word[:1].upper() + word[1:] for word in words)
    if identifier[0].isdigit():
        identifier = f"Qml{identifier}"
    return identifier


def _anchor_class_names(entries: Sequence[QmlComponentEntry]) -> dict[str, str]:
    used: set[str] = set()
    names: dict[str, str] = {}
    for entry in entries:
        base_name = _pascal_identifier(entry.component_name)
        class_name = base_name
        if class_name in used:
            family_name = _pascal_identifier(Path(entry.path).parent.as_posix())
            class_name = f"{family_name}{base_name}"
        suffix = 2
        unique_name = class_name
        while unique_name in used:
            unique_name = f"{class_name}{suffix}"
            suffix += 1
        used.add(unique_name)
        names[entry.path] = unique_name
    return names


def _entry_symbol_refs(entry: QmlComponentEntry) -> tuple[DetailRef, ...]:
    refs: list[DetailRef] = []
    refs.extend(DetailRef("id", ref.name, ref.line) for ref in entry.ids)
    refs.extend(DetailRef("objectName", ref.name, ref.line) for ref in entry.object_names)
    refs.extend(DetailRef("property", ref.name, ref.line, ref.kind) for ref in entry.properties)
    refs.extend(DetailRef("signal", ref.name, ref.line) for ref in entry.signals)
    refs.extend(DetailRef("function", ref.name, ref.line) for ref in entry.functions)
    refs.extend(DetailRef("instantiates", ref.name, ref.line) for ref in entry.instantiated_components)
    refs.extend(
        DetailRef(f"dynamic.{ref.kind}", ref.detail or ref.kind, ref.line, ref.detail)
        for ref in entry.dynamic_refs
    )
    refs.extend(entry.signal_handlers)
    refs.extend(entry.connections)
    refs.extend(entry.property_bindings)
    refs.extend(entry.local_component_refs)
    return _dedupe_detail_refs(refs)


def _entry_route_anchor_refs(entry: QmlComponentEntry) -> tuple[DetailRef, ...]:
    refs: list[DetailRef] = []
    refs.extend(DetailRef("property", ref.name, ref.line, ref.kind) for ref in entry.properties)
    refs.extend(DetailRef("signal", ref.name, ref.line) for ref in entry.signals)
    refs.extend(DetailRef("function", ref.name, ref.line) for ref in entry.functions)
    refs.extend(entry.signal_handlers)
    refs.extend(entry.connections)
    refs.extend(entry.local_component_refs)
    return _dedupe_detail_refs(refs)


def _symbol_anchor_specs(entry: QmlComponentEntry, component_class_name: str) -> tuple[SymbolAnchorSpec, ...]:
    used: set[str] = set()
    specs: list[SymbolAnchorSpec] = []
    for ref in _entry_route_anchor_refs(entry):
        base_name = f"{component_class_name}{_pascal_identifier(ref.kind)}{_pascal_identifier(ref.name)}"
        anchor = base_name
        suffix = 2
        while anchor in used:
            anchor = f"{base_name}{suffix}"
            suffix += 1
        used.add(anchor)
        specs.append(
            SymbolAnchorSpec(
                anchor=anchor,
                kind=ref.kind,
                name=ref.name,
                line=ref.line,
                detail=ref.detail,
            )
        )
    return tuple(specs)


def _component_family(path: str) -> str:
    parts = Path(path).parts
    if "components" not in parts:
        return Path(path).parent.as_posix()
    index = parts.index("components")
    family_parts = parts[index + 1 : -1]
    if not family_parts:
        return "components"
    return "components/" + "/".join(family_parts)


def render_markdown(
    index_data: QmlNavigationIndex,
    qml_roots: Sequence[Path] = DEFAULT_QML_ROOTS,
) -> str:
    family_counts: dict[str, int] = {}
    for entry in index_data.entries:
        family = _component_family(entry.path)
        family_counts[family] = family_counts.get(family, 0) + 1

    lines = [
        "# QML Navigation Index",
        "",
        "Generated by `./venv/Scripts/python.exe ./scripts/generate_qml_navigation_index.py`.",
        "Do not edit this file by hand; rerun the generator instead.",
        "",
        "## Purpose",
        "",
        "This compact index gives agents deterministic aliases for QML components, "
        "symbols, dynamic constructs, and local component relationships.",
        "",
        "## Scope",
        "",
        f"- QML roots: {_format_path_list(qml_roots)}",
        "- Extracts imports, root component, ids, object names, properties, signals, functions, "
        "handlers, Connections targets, property bindings, instantiated components, local component "
        "refs, and dynamic model/delegate/loader constructs.",
        "- Excludes cache, build, dependency, worktree mirror, and generated Excalidraw bundle paths.",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| QML files | {len(index_data.entries)} |",
        f"| Repeater constructs | {index_data.repeater_count} |",
        f"| Loader constructs | {index_data.loader_count} |",
        f"| Signal handlers | {sum(len(entry.signal_handlers) for entry in index_data.entries)} |",
        f"| Connections targets | {sum(len(entry.connections) for entry in index_data.entries)} |",
        f"| Property bindings | {sum(len(entry.property_bindings) for entry in index_data.entries)} |",
        f"| Local component refs | {sum(len(entry.local_component_refs) for entry in index_data.entries)} |",
        "",
        "## Component Families",
        "",
        "| Family | Components |",
        "| --- | ---: |",
    ]
    for family, count in sorted(family_counts.items(), key=lambda item: item[0].lower()):
        lines.append(f"| `{family}` | {count} |")

    lines.extend(
        [
            "",
            "## Component Quick Anchors",
            "",
            "| Component | Path | Root | Instantiates | Dynamic constructs |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for entry in index_data.entries:
        lines.append(
            f"| `{entry.component_name}.qml` | `{entry.path}` | "
            f"`{entry.root_component or 'unknown'}` | "
            f"{_format_compact_symbol_names(entry.instantiated_components)} | "
            f"{_format_compact_dynamic_kinds(entry.dynamic_refs)} |"
        )

    lines.extend(["", "## Component Details", ""])
    for entry in index_data.entries:
        lines.extend(
            [
                f"### `{entry.component_name}.qml`",
                "",
                f"- Path: `{entry.path}`",
                f"- Root component: `{entry.root_component or 'unknown'}`",
                f"- Agent route aliases: {_format_aliases(entry.aliases)}",
                f"- Imports: {_format_imports(entry.imports)}",
                f"- IDs: {_format_symbol_refs(entry.ids)}",
                f"- Object names: {_format_symbol_refs(entry.object_names)}",
                f"- Properties: {_format_typed_symbol_refs(entry.properties)}",
                f"- Signals: {_format_symbol_refs(entry.signals)}",
                f"- Functions: {_format_symbol_refs(entry.functions)}",
                f"- Instantiates: {_format_symbol_refs(entry.instantiated_components)}",
                f"- Dynamic constructs: {_format_dynamic_refs(entry.dynamic_refs)}",
                f"- Signal handlers: {_format_detail_refs(entry.signal_handlers)}",
                f"- Connections: {_format_detail_refs(entry.connections)}",
                "- Property bindings: "
                f"{_format_detail_refs(entry.property_bindings, include_targets=True)}",
                "- Local component refs: "
                f"{_format_detail_refs(entry.local_component_refs, include_detail=True)}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repository root to scan",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="markdown file to write",
    )
    parser.add_argument(
        "--json-output",
        default=str(DEFAULT_JSON_OUTPUT_PATH),
        help="machine-readable JSON sidecar to write",
    )
    parser.add_argument(
        "--qml-root",
        action="append",
        dest="qml_roots",
        help="QML root to scan; may be repeated or comma-separated",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the output file is missing or not up to date",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    json_output_path = Path(args.json_output)
    if not json_output_path.is_absolute():
        json_output_path = repo_root / json_output_path

    qml_roots = _parse_csv_paths(args.qml_roots, DEFAULT_QML_ROOTS)
    index_data = build_index_data(repo_root, qml_roots=qml_roots)
    markdown = render_markdown(index_data, qml_roots=qml_roots)
    json_index = render_json(index_data, qml_roots=qml_roots)

    if args.check:
        if not output_path.is_file():
            print(f"FAIL: {display_path(output_path, repo_root)} is missing.")
            return 1
        if not json_output_path.is_file():
            print(f"FAIL: {display_path(json_output_path, repo_root)} is missing.")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != markdown:
            print(f"FAIL: {display_path(output_path, repo_root)} is not up to date.")
            return 1
        existing_json = json_output_path.read_text(encoding="utf-8")
        if existing_json != json_index:
            print(f"FAIL: {display_path(json_output_path, repo_root)} is not up to date.")
            return 1
        print(
            "PASS: "
            f"{display_path(output_path, repo_root)} and "
            f"{display_path(json_output_path, repo_root)} are up to date."
        )
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json_index, encoding="utf-8")
    print(
        "Wrote "
        f"{display_path(output_path, repo_root)} with {len(index_data.entries)} QML files."
    )
    print(f"Wrote {display_path(json_output_path, repo_root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
