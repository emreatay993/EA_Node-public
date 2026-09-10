#!/usr/bin/env python3
"""Generate a map-first route index for agent navigation."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "agent_route_index.md"
DEFAULT_JSON_OUTPUT_PATH = REPO_ROOT / "docs" / "agent_route_index.json"
DEFAULT_MAPS_ROOT = REPO_ROOT / "docs" / "agent_maps"
DEFAULT_QML_INDEX_PATH = REPO_ROOT / "docs" / "qml_navigation_index.json"
DEFAULT_SOURCE_TEST_INDEX_PATH = REPO_ROOT / "docs" / "source_test_file_index.md"

MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<path>[^)#]+\.md)(?:#[^)]+)?\)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
TABLE_PATH_RE = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./\\:-]*")

SOURCE_PREFIXES = (
    "ea_node_editor/",
    "examples/",
    "scripts/",
    "web/excalidraw_host/",
)
IGNORED_MAP_NAMES = {".ds_store"}
MAX_CANDIDATES_PER_ENTRY = 80


@dataclass(frozen=True)
class RouteEntry:
    route_key: str
    kind: str
    title: str
    map_path: str
    source_candidates: tuple[str, ...]
    test_candidates: tuple[str, ...]
    qml_candidates: tuple[str, ...]
    keywords: tuple[str, ...]
    aliases: tuple[str, ...]
    focused_verification: tuple[str, ...]
    start_here: tuple[str, ...]
    do_not_start_here: tuple[str, ...]
    section_anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteIndex:
    entries: tuple[RouteEntry, ...]

    @property
    def map_entries(self) -> tuple[RouteEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind != "qml_component")

    @property
    def qml_entries(self) -> tuple[RouteEntry, ...]:
        return tuple(entry for entry in self.entries if entry.kind == "qml_component")


def display_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean_value = value.strip()
        if not clean_value or clean_value in seen:
            continue
        seen.add(clean_value)
        result.append(clean_value)
    return tuple(result)


def _limit(values: Iterable[str], limit: int = MAX_CANDIDATES_PER_ENTRY) -> tuple[str, ...]:
    return tuple(sorted(_dedupe(values), key=str.lower)[:limit])


def _slug(value: str) -> str:
    pieces = re.findall(r"[A-Za-z0-9]+", value.lower())
    return "-".join(pieces) or "route"


def _words(value: str) -> tuple[str, ...]:
    words: list[str] = []
    for token in WORD_RE.findall(value.replace("\\", "/")):
        for piece in re.findall(r"[A-Za-z0-9]+", token):
            if len(piece) >= 3:
                words.append(piece.lower())
    return _dedupe(words)


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            return match.group(1).strip()
    return fallback


def _route_kind(relative_map_path: str) -> str:
    parts = PurePosixPath(relative_map_path).parts
    if len(parts) >= 3 and parts[2] == "feature_routes":
        return "feature_route"
    if len(parts) >= 3 and parts[2] == "subsystems":
        return "subsystem"
    if len(parts) >= 3 and parts[2] == "testing":
        return "testing"
    stem = PurePosixPath(relative_map_path).stem.lower()
    if stem in {"index", "coverage", "maintenance"}:
        return stem
    return "map"


def _extract_backticks(text: str) -> tuple[str, ...]:
    # Backtick spans may wrap several paths across newlines (e.g. a list inside
    # one span, or a fenced block). Split each captured span into per-line tokens
    # so multi-path spans become individual candidates instead of one glued blob.
    tokens: list[str] = []
    for match in BACKTICK_RE.finditer(text):
        for piece in match.group(1).splitlines():
            piece = piece.strip()
            if piece:
                tokens.append(piece)
    return _dedupe(tokens)


def _extract_section_anchors(text: str) -> tuple[str, ...]:
    anchors: list[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            anchors.append(match.group(1).strip())
    return tuple(anchors)


def _extract_section_backticks(text: str, heading: str) -> tuple[str, ...]:
    """Return ordered inline-code tokens from one level-two map section."""
    tokens: list[str] = []
    in_section = False
    in_fence = False
    expected_heading = f"## {heading}".casefold()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped.casefold() == expected_heading
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in BACKTICK_RE.finditer(line):
            tokens.extend(
                piece.strip()
                for piece in match.group(1).splitlines()
                if piece.strip()
            )
    return _dedupe(tokens)


def _extract_lookup_aliases(text: str) -> tuple[str, ...]:
    aliases = list(_extract_section_backticks(text, "Lookup Aliases"))
    for line in text.splitlines():
        if line.strip().casefold().startswith("lookup aliases:"):
            aliases.extend(
                match.group(1).strip() for match in BACKTICK_RE.finditer(line)
            )
    return _dedupe(aliases)


def _looks_like_source_path(value: str) -> bool:
    normalized = value.replace("\\", "/").strip("./")
    return any(normalized.startswith(prefix) for prefix in SOURCE_PREFIXES)


def _looks_like_test_path(value: str) -> bool:
    normalized = value.replace("\\", "/").strip("./")
    return normalized.startswith("tests/")


def _looks_like_qml_path(value: str) -> bool:
    normalized = value.replace("\\", "/").strip("./")
    return normalized.endswith(".qml") and "ui_qml/" in normalized


def _extract_focused_verification(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    commands: list[str] = []
    in_section = False
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section and stripped != "## Focused Verification":
                break
            in_section = stripped == "## Focused Verification"
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped:
            commands.append(stripped)
    return _dedupe(commands)


def _resolve_map_link(maps_root: Path, base_path: Path, raw_link: str) -> str | None:
    link = raw_link.replace("\\", "/")
    if link.startswith(("http://", "https://", "#")):
        return None
    target = (base_path.parent / link).resolve()
    try:
        return target.relative_to(maps_root.parent.parent.resolve()).as_posix()
    except ValueError:
        return None


def _parse_source_test_index(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not path.is_file():
        return (), ()
    source_paths: list[str] = []
    test_paths: list[str] = []
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Source Code"):
            section = "source"
            continue
        if line.startswith("## Test Modules"):
            section = "test"
            continue
        match = TABLE_PATH_RE.match(line)
        if not match:
            continue
        if section == "source":
            source_paths.append(match.group("path"))
        elif section == "test":
            test_paths.append(match.group("path"))
    return tuple(source_paths), tuple(test_paths)


def _load_qml_entries(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return tuple(entry for entry in entries if isinstance(entry, dict))


def _candidate_paths_for_token(token: str, candidates: Sequence[str]) -> tuple[str, ...]:
    normalized = token.replace("\\", "/").strip("./")
    if not normalized or "*" in normalized:
        return ()
    if normalized.endswith("/"):
        prefix = normalized
    else:
        prefix = f"{normalized}/"
    matches = [
        path
        for path in candidates
        if path == normalized or path.startswith(prefix)
    ]
    return tuple(matches)


def _qml_paths_for_area_token(token: str, qml_paths: Sequence[str]) -> tuple[str, ...]:
    normalized = token.replace("\\", "/").strip("./")
    if normalized.startswith("components/"):
        prefix = f"ea_node_editor/ui_qml/{normalized}/"
    elif normalized == "components":
        prefix = "ea_node_editor/ui_qml/components/"
    elif normalized.startswith("ea_node_editor/ui_qml"):
        prefix = normalized.rstrip("/") + "/"
    else:
        return ()
    return tuple(path for path in qml_paths if path.startswith(prefix))


def _parse_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.startswith("| ---"):
        return ()
    cells = tuple(cell.strip() for cell in stripped.strip("|").split("|"))
    if len(cells) < 2 or cells[0].lower() in {"area", "module", "file or area", "family", "add-on", "packet set", "test family"}:
        return ()
    return cells


def _map_entries(repo_root: Path, maps_root: Path) -> dict[str, dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for path in sorted(maps_root.rglob("*.md"), key=lambda item: item.as_posix().lower()):
        if path.name.lower() in IGNORED_MAP_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        relative = display_path(path, repo_root)
        title = _title_from_markdown(text, path.stem.replace("_", " ").title())
        kind = _route_kind(relative)
        backticks = _extract_backticks(text)
        do_not_start_here = _extract_section_backticks(text, "Do Not Start Here")
        positive_backticks = tuple(
            token for token in backticks if token not in do_not_start_here
        )
        source_candidates = [value.replace("\\", "/").strip("./") for value in positive_backticks if _looks_like_source_path(value)]
        test_candidates = [value.replace("\\", "/").strip("./") for value in positive_backticks if _looks_like_test_path(value)]
        qml_candidates = [value.replace("\\", "/").strip("./") for value in positive_backticks if _looks_like_qml_path(value)]
        keywords = [
            *_words(title),
            *_words(path.stem),
            *(_words(item) for item in ()),
        ]
        flattened_keywords: list[str] = list(keywords)
        for token in positive_backticks:
            flattened_keywords.extend(_words(token))
        for heading in HEADING_RE.findall(text):
            flattened_keywords.extend(_words(heading))
        entries[relative] = {
            "route_key": f"{kind}:{_slug(relative.removeprefix('docs/agent_maps/').removesuffix('.md'))}",
            "kind": kind,
            "title": title,
            "map_path": relative,
            "source_candidates": list(_dedupe(source_candidates)),
            "test_candidates": list(_dedupe(test_candidates)),
            "qml_candidates": list(_dedupe(qml_candidates)),
            "keywords": list(_dedupe(flattened_keywords)),
            "aliases": list(_extract_lookup_aliases(text)),
            "focused_verification": list(_extract_focused_verification(text)),
            "start_here": list(_extract_section_backticks(text, "Start Here")),
            "do_not_start_here": list(do_not_start_here),
            "section_anchors": list(_extract_section_anchors(text)),
        }
    return entries


def _apply_coverage(
    repo_root: Path,
    maps_root: Path,
    entries: dict[str, dict[str, object]],
    source_paths: Sequence[str],
    test_paths: Sequence[str],
    qml_paths: Sequence[str],
) -> None:
    coverage_path = maps_root / "COVERAGE.md"
    if not coverage_path.is_file():
        return
    for line in coverage_path.read_text(encoding="utf-8").splitlines():
        cells = _parse_table_row(line)
        if len(cells) < 2:
            continue
        area_cell = cells[0]
        linked_map_paths: list[str] = []
        for cell in cells[1:3]:
            for match in MARKDOWN_LINK_RE.finditer(cell):
                resolved = _resolve_map_link(maps_root, coverage_path, match.group("path"))
                if resolved:
                    linked_map_paths.append(resolved)
        if not linked_map_paths:
            continue

        area_tokens = _extract_backticks(area_cell)
        area_keywords = list(_words(area_cell))
        for token in area_tokens:
            area_keywords.extend(_words(token))
        source_matches: list[str] = []
        test_matches: list[str] = []
        qml_matches: list[str] = []
        for token in area_tokens:
            source_matches.extend(_candidate_paths_for_token(token, source_paths))
            test_matches.extend(_candidate_paths_for_token(token, test_paths))
            qml_matches.extend(_qml_paths_for_area_token(token, qml_paths))

        for map_path in linked_map_paths:
            entry = entries.get(map_path)
            if entry is None:
                continue
            entry["keywords"] = list(_dedupe([*entry["keywords"], *area_keywords]))
            entry["source_candidates"] = list(
                _limit([*entry["source_candidates"], *source_matches])
            )
            entry["test_candidates"] = list(_limit([*entry["test_candidates"], *test_matches]))
            entry["qml_candidates"] = list(_limit([*entry["qml_candidates"], *qml_matches]))


def _infer_qml_map_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/components/graph/passive/" in normalized:
        return "docs/agent_maps/subsystems/passive_media_tabular_surfaces.md"
    if "/components/graph/plot/" in normalized or "/components/graph/viewer/" in normalized:
        return "docs/agent_maps/subsystems/viewer_surfaces.md"
    if "/components/web/" in normalized:
        return "docs/agent_maps/subsystems/web_assets_host_chromium_excalidraw.md"
    if "/components/shell/" in normalized or normalized.endswith("/MainShell.qml"):
        return "docs/agent_maps/subsystems/qml_shell_and_bridges.md"
    if "/components/graph" in normalized or "/components/graph_canvas/" in normalized:
        return "docs/agent_maps/subsystems/graph_canvas.md"
    return "docs/agent_maps/subsystems/qml_shell_and_bridges.md"


def _qml_route_entries(qml_entries: Sequence[dict[str, object]]) -> tuple[RouteEntry, ...]:
    route_entries: list[RouteEntry] = []
    for entry in qml_entries:
        component_name = str(entry.get("component_name") or "")
        path = str(entry.get("path") or "")
        if not component_name or not path:
            continue
        aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
        keywords: list[str] = []
        for value in [component_name, path, str(entry.get("root_component") or ""), *aliases]:
            keywords.extend(_words(str(value)))
        for field in ("properties", "signals", "functions", "ids", "object_names"):
            values = entry.get(field)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict):
                    keywords.extend(_words(str(value.get("name") or "")))
                    keywords.extend(_words(str(value.get("kind") or "")))
        route_entries.append(
            RouteEntry(
                route_key=f"qml:{_slug(component_name)}",
                kind="qml_component",
                title=f"{component_name}.qml",
                map_path=_infer_qml_map_path(path),
                source_candidates=(path,),
                test_candidates=(),
                qml_candidates=(path,),
                keywords=_dedupe(keywords),
                aliases=(),
                focused_verification=(),
                start_here=(),
                do_not_start_here=(),
                section_anchors=(),
            )
        )
    return tuple(sorted(route_entries, key=lambda item: item.route_key))


def build_index_data(
    repo_root: Path,
    maps_root: Path | None = None,
    qml_index_path: Path | None = None,
    source_test_index_path: Path | None = None,
) -> RouteIndex:
    maps_root = maps_root or repo_root / "docs" / "agent_maps"
    qml_index_path = qml_index_path or repo_root / "docs" / "qml_navigation_index.json"
    source_test_index_path = source_test_index_path or repo_root / "docs" / "source_test_file_index.md"

    source_paths, test_paths = _parse_source_test_index(source_test_index_path)
    qml_entries = _load_qml_entries(qml_index_path)
    qml_paths = tuple(str(entry.get("path")) for entry in qml_entries if entry.get("path"))
    mutable_entries = _map_entries(repo_root, maps_root)
    _apply_coverage(repo_root, maps_root, mutable_entries, source_paths, test_paths, qml_paths)

    map_route_entries = tuple(
        RouteEntry(
            route_key=str(entry["route_key"]),
            kind=str(entry["kind"]),
            title=str(entry["title"]),
            map_path=str(entry["map_path"]),
            source_candidates=tuple(entry["source_candidates"]),
            test_candidates=tuple(entry["test_candidates"]),
            qml_candidates=tuple(entry["qml_candidates"]),
            keywords=tuple(entry["keywords"]),
            aliases=tuple(entry["aliases"]),
            focused_verification=tuple(entry["focused_verification"]),
            start_here=tuple(entry["start_here"]),
            do_not_start_here=tuple(entry["do_not_start_here"]),
            section_anchors=tuple(entry["section_anchors"]),
        )
        for entry in mutable_entries.values()
    )
    entries = tuple(sorted([*map_route_entries, *_qml_route_entries(qml_entries)], key=lambda item: item.route_key))
    return RouteIndex(entries=entries)


def route_entry_to_dict(entry: RouteEntry) -> dict[str, object]:
    return {
        "route_key": entry.route_key,
        "kind": entry.kind,
        "title": entry.title,
        "map_path": entry.map_path,
        "source_candidates": list(entry.source_candidates),
        "test_candidates": list(entry.test_candidates),
        "qml_candidates": list(entry.qml_candidates),
        "keywords": list(entry.keywords),
        "aliases": list(entry.aliases),
        "focused_verification": list(entry.focused_verification),
        "start_here": list(entry.start_here),
        "do_not_start_here": list(entry.do_not_start_here),
        "section_anchors": list(entry.section_anchors),
    }


def render_json(index_data: RouteIndex) -> str:
    payload = {
        "version": 2,
        "summary": {
            "entries": len(index_data.entries),
            "map_entries": len(index_data.map_entries),
            "qml_component_entries": len(index_data.qml_entries),
        },
        "entries": [route_entry_to_dict(entry) for entry in index_data.entries],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _format_count(value: int) -> str:
    return str(value) if value else "-"


def _format_keywords(keywords: Sequence[str], max_items: int = 10) -> str:
    if not keywords:
        return "_None_"
    visible = ", ".join(f"`{keyword}`" for keyword in keywords[:max_items])
    extra = len(keywords) - max_items
    if extra > 0:
        visible += f", ... +{extra} more"
    return visible


def render_markdown(index_data: RouteIndex) -> str:
    lines = [
        "# Agent Route Index",
        "",
        "Generated by `./venv/Scripts/python.exe ./scripts/generate_agent_route_index.py`.",
        "Do not edit this file by hand; rerun the generator instead.",
        "",
        "## Purpose",
        "",
        "This index is the machine-readable companion to `docs/agent_maps/`. Use it to find likely owner maps, source files, tests, and QML components before broad repository search.",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Route entries | {len(index_data.entries)} |",
        f"| Agent-map entries | {len(index_data.map_entries)} |",
        f"| QML component entries | {len(index_data.qml_entries)} |",
        "",
        "## Agent Map Routes",
        "",
        "| Route key | Kind | Map | Source | Tests | QML | Keywords |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for entry in index_data.map_entries:
        lines.append(
            f"| `{entry.route_key}` | `{entry.kind}` | `{entry.map_path}` | "
            f"{_format_count(len(entry.source_candidates))} | "
            f"{_format_count(len(entry.test_candidates))} | "
            f"{_format_count(len(entry.qml_candidates))} | "
            f"{_format_keywords(entry.keywords)} |"
        )

    lines.extend(
        [
            "",
            "## QML Component Routes",
            "",
            "| Route key | Component | Owner map | Path | Keywords |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for entry in index_data.qml_entries:
        path = entry.qml_candidates[0] if entry.qml_candidates else ""
        lines.append(
            f"| `{entry.route_key}` | `{entry.title}` | `{entry.map_path}` | "
            f"`{path}` | {_format_keywords(entry.keywords, max_items=8)} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="repository root to scan")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="markdown file to write")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT_PATH), help="JSON sidecar to write")
    parser.add_argument("--maps-root", default="docs/agent_maps", help="agent maps root")
    parser.add_argument("--qml-index", default="docs/qml_navigation_index.json", help="QML navigation JSON input")
    parser.add_argument(
        "--source-test-index",
        default="docs/source_test_file_index.md",
        help="source/test file index input",
    )
    parser.add_argument("--check", action="store_true", help="fail if outputs are missing or stale")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output)
    json_output_path = Path(args.json_output)
    maps_root = Path(args.maps_root)
    qml_index_path = Path(args.qml_index)
    source_test_index_path = Path(args.source_test_index)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    if not json_output_path.is_absolute():
        json_output_path = repo_root / json_output_path
    if not maps_root.is_absolute():
        maps_root = repo_root / maps_root
    if not qml_index_path.is_absolute():
        qml_index_path = repo_root / qml_index_path
    if not source_test_index_path.is_absolute():
        source_test_index_path = repo_root / source_test_index_path

    index_data = build_index_data(
        repo_root,
        maps_root=maps_root,
        qml_index_path=qml_index_path,
        source_test_index_path=source_test_index_path,
    )
    markdown = render_markdown(index_data)
    json_text = render_json(index_data)

    if args.check:
        if not output_path.is_file():
            print(f"FAIL: {display_path(output_path, repo_root)} is missing.")
            return 1
        if not json_output_path.is_file():
            print(f"FAIL: {display_path(json_output_path, repo_root)} is missing.")
            return 1
        if output_path.read_text(encoding="utf-8") != markdown:
            print(f"FAIL: {display_path(output_path, repo_root)} is not up to date.")
            return 1
        if json_output_path.read_text(encoding="utf-8") != json_text:
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
    json_output_path.write_text(json_text, encoding="utf-8")
    print(
        "Wrote "
        f"{display_path(output_path, repo_root)} with {len(index_data.entries)} route entries."
    )
    print(f"Wrote {display_path(json_output_path, repo_root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
