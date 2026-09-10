#!/usr/bin/env python3
"""Validate local markdown links across the active canonical docs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_DOC_GLOBS = (
    "README.md",
    "ARCHITECTURE.md",
    "docs/GETTING_STARTED.md",
    "docs/PACKAGING_WINDOWS.md",
    "docs/PILOT_RUNBOOK.md",
    "docs/specs/INDEX.md",
    "docs/specs/requirements/*.md",
    "docs/specs/perf/*.md",
)
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
TITLE_SUFFIX_PATTERN = re.compile(r"^(?P<target>\S+?)(?:\s+(?:\"[^\"]*\"|'[^']*'))?$")
SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(frozen=True)
class LinkReference:
    line_number: int
    target: str


def iter_markdown_documents(repo_root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in MARKDOWN_DOC_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file():
                paths.add(path.resolve())
    return tuple(sorted(paths))


def iter_link_references(text: str) -> tuple[LinkReference, ...]:
    refs: list[LinkReference] = []
    in_code_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        for match in LINK_PATTERN.finditer(line):
            refs.append(LinkReference(line_number=line_number, target=match.group(1).strip()))
    return tuple(refs)


def normalize_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    title_match = TITLE_SUFFIX_PATTERN.match(target)
    if title_match is not None:
        target = title_match.group("target")
    return target


def is_external_target(target: str) -> bool:
    if target.startswith(("http://", "https://", "mailto:", "data:")):
        return True
    if SCHEME_PATTERN.match(target) and not re.match(r"^[A-Za-z]:[\\\\/]", target):
        return True
    return False


def heading_anchor_slug(heading: str) -> str:
    collapsed = re.sub(r"[`*_]+", "", heading.strip().lower())
    collapsed = re.sub(r"[^a-z0-9\- ]+", "", collapsed)
    collapsed = re.sub(r"\s+", "-", collapsed)
    collapsed = re.sub(r"-{2,}", "-", collapsed)
    return collapsed.strip("-")


def markdown_heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    in_code_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        match = HEADING_PATTERN.match(line.strip())
        if match is None:
            continue
        anchor = heading_anchor_slug(match.group(2))
        if anchor:
            anchors.add(anchor)
    return anchors


def resolve_target(source_path: Path, target: str) -> tuple[Path, str] | None:
    normalized = normalize_target(target)
    if not normalized or is_external_target(normalized):
        return None

    path_part, _, fragment = normalized.partition("#")
    resolved_fragment = unquote(fragment).strip().lower()

    if not path_part:
        resolved_path = source_path
    else:
        decoded_path = unquote(path_part)
        candidate = Path(decoded_path)
        if candidate.is_absolute():
            resolved_path = candidate
        else:
            resolved_path = (source_path.parent / candidate).resolve()
    return resolved_path, resolved_fragment


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def audit_markdown_file(path: Path, repo_root: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8-sig")
    anchor_cache: dict[Path, set[str]] = {}

    for ref in iter_link_references(text):
        resolved = resolve_target(path, ref.target)
        if resolved is None:
            continue
        target_path, fragment = resolved
        if not target_path.exists():
            issues.append(
                f"{display_path(path, repo_root)}:{ref.line_number}: broken markdown link target: {ref.target}"
            )
            continue
        if fragment and target_path.is_file() and target_path.suffix.lower() == ".md":
            anchors = anchor_cache.get(target_path)
            if anchors is None:
                anchors = markdown_heading_anchors(target_path.read_text(encoding="utf-8-sig"))
                anchor_cache[target_path] = anchors
            if fragment not in anchors:
                issues.append(
                    f"{display_path(path, repo_root)}:{ref.line_number}: missing markdown heading anchor "
                    f"for {display_path(target_path, repo_root)}#{fragment}"
                )
    return issues


def audit_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    issues: list[str] = []
    for path in iter_markdown_documents(repo_root):
        issues.extend(audit_markdown_file(path, repo_root))
    return issues


def main() -> int:
    issues = audit_repository(REPO_ROOT)
    if issues:
        print("MARKDOWN LINK CHECK FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("MARKDOWN LINK CHECK PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
