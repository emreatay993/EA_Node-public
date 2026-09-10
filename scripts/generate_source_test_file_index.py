#!/usr/bin/env python3
"""Generate a stable path index for source files and test modules."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "docs" / "source_test_file_index.md"
DEFAULT_SOURCE_ROOTS = (
    Path("corex"),
    Path("ea_node_editor"),
    Path("web/excalidraw_host"),
)
DEFAULT_TEST_ROOTS = (Path("tests"),)
DEFAULT_SOURCE_SUFFIXES = (
    ".py",
    ".pyi",
    ".qml",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".css",
    ".html",
)
DEFAULT_TEST_SUFFIXES = (".py",)
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


@dataclass(frozen=True)
class FileEntry:
    path: str


@dataclass(frozen=True)
class IndexData:
    source_entries: tuple[FileEntry, ...]
    test_entries: tuple[FileEntry, ...]

    @property
    def total_files(self) -> int:
        return len(self.source_entries) + len(self.test_entries)

def _normalize_suffixes(suffixes: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for suffix in suffixes:
        clean_suffix = suffix.strip().lower()
        if not clean_suffix:
            continue
        if not clean_suffix.startswith("."):
            clean_suffix = f".{clean_suffix}"
        normalized.append(clean_suffix)
    return tuple(dict.fromkeys(normalized))


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


def _parse_csv_suffixes(raw_suffixes: str, defaults: Sequence[str]) -> tuple[str, ...]:
    if not raw_suffixes.strip():
        return _normalize_suffixes(defaults)
    return _normalize_suffixes(raw_suffixes.split(","))


def display_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


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


def _git_visible_files(repo_root: Path, roots: Sequence[Path]) -> tuple[Path, ...] | None:
    repo_root_resolved = repo_root.resolve()
    pathspecs: list[str] = []
    for root in roots:
        root_path = root if root.is_absolute() else repo_root_resolved / root
        try:
            relative_root = root_path.resolve().relative_to(repo_root_resolved)
        except ValueError:
            return None
        pathspecs.append(relative_root.as_posix() or ".")

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root_resolved),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                *pathspecs,
            ],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return tuple(
        repo_root_resolved / Path(raw_path.decode("utf-8", errors="surrogateescape"))
        for raw_path in completed.stdout.split(b"\0")
        if raw_path
    )


def iter_indexable_files(
    repo_root: Path,
    roots: Sequence[Path],
    suffixes: Sequence[str],
) -> tuple[Path, ...]:
    normalized_suffixes = _normalize_suffixes(suffixes)
    seen: set[Path] = set()
    files: list[Path] = []

    candidates = _git_visible_files(repo_root, roots)
    if candidates is None:
        fallback_candidates: list[Path] = []
        for root in roots:
            root_path = root if root.is_absolute() else repo_root / root
            if root_path.exists():
                fallback_candidates.extend(_iter_files_pruning_excluded_dirs(root_path, repo_root))
        candidates = tuple(fallback_candidates)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in normalized_suffixes:
            continue
        resolved = candidate.resolve()
        try:
            relative_path = resolved.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if is_excluded_path(relative_path):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(resolved)

    return tuple(sorted(files, key=lambda path: display_path(path, repo_root).lower()))


def collect_entries(
    repo_root: Path,
    roots: Sequence[Path],
    suffixes: Sequence[str],
) -> tuple[FileEntry, ...]:
    return tuple(
        FileEntry(path=display_path(path, repo_root))
        for path in iter_indexable_files(repo_root, roots, suffixes)
    )


def build_index_data(
    repo_root: Path,
    source_roots: Sequence[Path] = DEFAULT_SOURCE_ROOTS,
    test_roots: Sequence[Path] = DEFAULT_TEST_ROOTS,
    source_suffixes: Sequence[str] = DEFAULT_SOURCE_SUFFIXES,
    test_suffixes: Sequence[str] = DEFAULT_TEST_SUFFIXES,
) -> IndexData:
    return IndexData(
        source_entries=collect_entries(repo_root, source_roots, source_suffixes),
        test_entries=collect_entries(repo_root, test_roots, test_suffixes),
    )


def _format_path_list(paths: Sequence[Path]) -> str:
    return ", ".join(f"`{path.as_posix()}`" for path in paths)


def _format_suffix_list(suffixes: Sequence[str]) -> str:
    return ", ".join(f"`{suffix}`" for suffix in _normalize_suffixes(suffixes))


def _render_entry_table(entries: Sequence[FileEntry]) -> list[str]:
    if not entries:
        return ["_No files found._"]
    lines = ["| Path |", "| --- |"]
    for entry in entries:
        lines.append(f"| `{entry.path}` |")
    return lines


def render_markdown(
    index_data: IndexData,
    source_roots: Sequence[Path] = DEFAULT_SOURCE_ROOTS,
    test_roots: Sequence[Path] = DEFAULT_TEST_ROOTS,
    source_suffixes: Sequence[str] = DEFAULT_SOURCE_SUFFIXES,
    test_suffixes: Sequence[str] = DEFAULT_TEST_SUFFIXES,
) -> str:
    lines = [
        "# Source And Test File Index",
        "",
        "Generated by `./venv/Scripts/python.exe ./scripts/generate_source_test_file_index.py`.",
        "Do not edit this file by hand; rerun the generator instead.",
        "",
        "## Scope",
        "",
        f"- Source roots: {_format_path_list(source_roots)}",
        f"- Test roots: {_format_path_list(test_roots)}",
        f"- Source suffixes: {_format_suffix_list(source_suffixes)}",
        f"- Test suffixes: {_format_suffix_list(test_suffixes)}",
        "- Excludes cache, build, dependency, worktree mirror, and generated Excalidraw bundle paths.",
        "- In Git worktrees, uses `git ls-files --cached --others --exclude-standard` so ignored local files stay out.",
        "",
        "## Summary",
        "",
        "| Category | Files |",
        "| --- | ---: |",
        f"| Source code | {len(index_data.source_entries)} |",
        f"| Test modules | {len(index_data.test_entries)} |",
        f"| Total | {index_data.total_files} |",
        "",
        "## Source Code",
        "",
        *_render_entry_table(index_data.source_entries),
        "",
        "## Test Modules",
        "",
        *_render_entry_table(index_data.test_entries),
        "",
    ]
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
        "--source-root",
        action="append",
        dest="source_roots",
        help="source root to scan; may be repeated or comma-separated",
    )
    parser.add_argument(
        "--test-root",
        action="append",
        dest="test_roots",
        help="test root to scan; may be repeated or comma-separated",
    )
    parser.add_argument(
        "--source-suffixes",
        default=",".join(DEFAULT_SOURCE_SUFFIXES),
        help="comma-separated source file suffixes",
    )
    parser.add_argument(
        "--test-suffixes",
        default=",".join(DEFAULT_TEST_SUFFIXES),
        help="comma-separated test file suffixes",
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

    source_roots = _parse_csv_paths(args.source_roots, DEFAULT_SOURCE_ROOTS)
    test_roots = _parse_csv_paths(args.test_roots, DEFAULT_TEST_ROOTS)
    source_suffixes = _parse_csv_suffixes(args.source_suffixes, DEFAULT_SOURCE_SUFFIXES)
    test_suffixes = _parse_csv_suffixes(args.test_suffixes, DEFAULT_TEST_SUFFIXES)
    index_data = build_index_data(
        repo_root,
        source_roots=source_roots,
        test_roots=test_roots,
        source_suffixes=source_suffixes,
        test_suffixes=test_suffixes,
    )
    markdown = render_markdown(
        index_data,
        source_roots=source_roots,
        test_roots=test_roots,
        source_suffixes=source_suffixes,
        test_suffixes=test_suffixes,
    )

    if args.check:
        if not output_path.is_file():
            print(f"FAIL: {display_path(output_path, repo_root)} is missing.")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != markdown:
            print(f"FAIL: {display_path(output_path, repo_root)} is not up to date.")
            return 1
        print(f"PASS: {display_path(output_path, repo_root)} is up to date.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(
        "Wrote "
        f"{display_path(output_path, repo_root)} with {index_data.total_files} files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
