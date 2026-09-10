#!/usr/bin/env python3
# Purpose: Fail when agent maps / the route index cite files that no longer
#          exist, so stale navigation can't silently send agents to ghost files.
# Map: subsystems/verification_testing_docs_hygiene
# Tests: tests/test_agent_maps_hygiene.py
"""Agent-map drift gate.

Validates that the committed navigation layer points at things that actually
exist on disk:

  1. Every repo path cited in backticks inside ``docs/agent_maps/**/*.md``
     resolves to a real file or directory.
  2. Every source/test/qml candidate in ``docs/agent_route_index.json``
     resolves (placeholders and globs are skipped).
  3. Every agent-map link in ``docs/agent_maps/COVERAGE.md`` targets a map
     file that exists.

Exit code is non-zero if any citation is broken. This is cheap to run and is
collected by ``run_verification.py --mode fast`` via
``tests/test_agent_maps_hygiene.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPS_ROOT_REL = "docs/agent_maps"
ROUTE_INDEX_REL = "docs/agent_route_index.json"
COVERAGE_REL = "docs/agent_maps/COVERAGE.md"

KNOWN_ROOTS = ("ea_node_editor", "tests", "scripts", "examples", "web", "docs")
BACKTICK_RE = re.compile(r"`([^`]+)`")
MARKDOWN_MAP_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<path>[^)#]+\.md)(?:#[^)]+)?\)")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_DISALLOWED = set(" \t<>*?\"{}|")

# In-file header banners (see AGENTS.md / the file-header convention):
#   # Map: feature_routes/<route>   (or subsystems/<name>, with or without .md)
#   # Tests: tests/<focused>.py[, tests/<other>.py]
# Validated bidirectionally so headers cannot rot into pointing at dead maps/tests.
_MAP_HEADER_RE = re.compile(r"^\s*(?:#|//)\s*Map:\s*(?P<value>\S.*?)\s*$")
_TESTS_HEADER_RE = re.compile(r"^\s*(?:#|//)\s*Tests:\s*(?P<value>\S.*?)\s*$")
_HEADER_SCAN_DIRS = ("ea_node_editor", "scripts")
_HEADER_SCAN_SUFFIXES = (".py", ".qml")
_HEADER_SCAN_SKIP_PARTS = {"__pycache__", "web_assets"}
_HEADER_SCAN_LINES = 40


def _backtick_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in BACKTICK_RE.finditer(text):
        for piece in match.group(1).splitlines():
            piece = piece.strip()
            if piece:
                tokens.append(piece)
    return tokens


def normalize_path_token(token: str) -> str | None:
    """Return a repo-relative path if ``token`` looks like one, else ``None``."""
    norm = token.replace("\\", "/").strip()
    if norm.startswith("./"):
        norm = norm[2:]
    norm = norm.split("#", 1)[0]  # drop markdown anchors
    norm = norm.split("::", 1)[0]  # drop pytest node ids
    norm = _LINE_SUFFIX_RE.sub("", norm)  # drop trailing :line refs
    norm = norm.rstrip("/")
    if not norm or "/" not in norm:
        return None
    if any(ch in _DISALLOWED for ch in norm):
        return None
    if "*" in norm or ".." in norm:
        return None
    if norm.split("/", 1)[0] not in KNOWN_ROOTS:
        return None
    return norm


def _iter_map_files(maps_root: Path) -> list[Path]:
    return sorted(maps_root.rglob("*.md"), key=lambda p: p.as_posix().lower())


def check_map_citations(repo_root: Path) -> list[str]:
    problems: list[str] = []
    maps_root = repo_root / MAPS_ROOT_REL
    for map_file in _iter_map_files(maps_root):
        rel_map = map_file.relative_to(repo_root).as_posix()
        for token in _backtick_tokens(map_file.read_text(encoding="utf-8")):
            path = normalize_path_token(token)
            if path is None:
                continue
            if not (repo_root / path).exists():
                problems.append(f"{rel_map}: cites missing path `{path}`")
    return problems


def check_route_index(repo_root: Path) -> list[str]:
    problems: list[str] = []
    index_path = repo_root / ROUTE_INDEX_REL
    if not index_path.is_file():
        return [f"{ROUTE_INDEX_REL}: missing (run scripts/generate_agent_route_index.py)"]
    data = json.loads(index_path.read_text(encoding="utf-8"))
    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue
        route_key = entry.get("route_key", "<unknown>")
        for field in ("source_candidates", "test_candidates", "qml_candidates"):
            for candidate in entry.get(field, []):
                path = normalize_path_token(str(candidate))
                if path is None:
                    continue
                if not (repo_root / path).exists():
                    problems.append(
                        f"{ROUTE_INDEX_REL}: route `{route_key}` {field} -> missing `{path}`"
                    )
    return problems


def check_coverage_links(repo_root: Path) -> list[str]:
    problems: list[str] = []
    coverage_path = repo_root / COVERAGE_REL
    if not coverage_path.is_file():
        return problems
    for raw in MARKDOWN_MAP_LINK_RE.findall(coverage_path.read_text(encoding="utf-8")):
        if raw.startswith(("http://", "https://")):
            continue
        target = (coverage_path.parent / raw.replace("\\", "/")).resolve()
        if not target.is_file():
            problems.append(f"{COVERAGE_REL}: links to missing map `{raw}`")
    return problems


def _map_header_resolves(repo_root: Path, value: str) -> bool:
    cleaned = value.strip().strip("`")
    if not cleaned:
        return False
    cleaned = cleaned.split()[0]
    rel = cleaned if cleaned.endswith(".md") else f"{cleaned}.md"
    if rel.startswith("docs/"):
        candidate = repo_root / rel
    else:
        candidate = repo_root / MAPS_ROOT_REL / rel
    return candidate.is_file()


def check_source_headers(repo_root: Path) -> list[str]:
    """Validate in-file `# Map:` / `# Tests:` header banners resolve."""
    problems: list[str] = []
    for base in _HEADER_SCAN_DIRS:
        root = repo_root / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in _HEADER_SCAN_SUFFIXES:
                continue
            if _HEADER_SCAN_SKIP_PARTS.intersection(path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES]
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(repo_root).as_posix()
            for line in lines:
                map_match = _MAP_HEADER_RE.match(line)
                if map_match and not _map_header_resolves(repo_root, map_match.group("value")):
                    problems.append(
                        f"{rel}: `# Map: {map_match.group('value')}` does not resolve to an agent map"
                    )
                tests_match = _TESTS_HEADER_RE.match(line)
                if tests_match:
                    for token in re.split(r"[,\s]+", tests_match.group("value")):
                        norm = normalize_path_token(token)
                        if norm and not (repo_root / norm).exists():
                            problems.append(f"{rel}: `# Tests: {token}` -> missing `{norm}`")
    return problems


def check(repo_root: Path = REPO_ROOT) -> list[str]:
    problems: list[str] = []
    problems.extend(check_map_citations(repo_root))
    problems.extend(check_route_index(repo_root))
    problems.extend(check_coverage_links(repo_root))
    problems.extend(check_source_headers(repo_root))
    # Stable, de-duplicated output.
    return sorted(dict.fromkeys(problems))


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="repository root")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    problems = check(repo_root)
    if problems:
        print(f"FAIL: {len(problems)} agent-map drift problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("PASS: agent maps and route index cite only existing paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
