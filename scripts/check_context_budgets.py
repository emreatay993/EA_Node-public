#!/usr/bin/env python3
"""Report packet-owned context budgets for historical UI hotspot files.

The default mode is informational. Use ``--enforce`` only when intentionally
rerunning the old UI context-scalability packet diagnostics.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES_PATH = (
    REPO_ROOT
    / "docs"
    / "specs"
    / "work_packets"
    / "ui_context_scalability_refactor"
    / "CONTEXT_BUDGET_RULES.json"
)
RULES_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ContextBudgetRule:
    path: str
    owner_packet: str
    owner_label: str
    max_lines: int


@dataclass(frozen=True)
class ContextBudgetResult:
    rule: ContextBudgetRule
    actual_lines: int | None
    file_exists: bool

    @property
    def passed(self) -> bool:
        return self.file_exists and self.actual_lines is not None and self.actual_lines <= self.rule.max_lines

    @property
    def failure_message(self) -> str:
        owner = f"[{self.rule.owner_packet}:{self.rule.owner_label}]"
        if not self.file_exists:
            return f"{owner} {self.rule.path} is missing."
        assert self.actual_lines is not None
        return (
            f"{owner} {self.rule.path} is {self.actual_lines} lines "
            f"(cap {self.rule.max_lines})."
        )


def _require_mapping(payload: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return payload


def _require_nonempty_str(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string.")
    return value


def _require_positive_int(value: Any, *, context: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{context} must be a positive integer.")
    return value


def load_rules(rules_path: Path = DEFAULT_RULES_PATH) -> tuple[ContextBudgetRule, ...]:
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    rules_root = _require_mapping(payload, context="context budget rules")
    schema_version = rules_root.get("schema_version")
    if schema_version != RULES_SCHEMA_VERSION:
        raise ValueError(
            "context budget rules schema_version must equal "
            f"{RULES_SCHEMA_VERSION}, got {schema_version!r}."
        )

    raw_rules = rules_root.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("context budget rules must contain a non-empty rules list.")

    seen_paths: set[str] = set()
    rules: list[ContextBudgetRule] = []
    for index, raw_rule in enumerate(raw_rules):
        rule_payload = _require_mapping(raw_rule, context=f"rules[{index}]")
        path = _require_nonempty_str(rule_payload.get("path"), context=f"rules[{index}].path")
        if path in seen_paths:
            raise ValueError(f"Duplicate context budget rule path: {path}")
        seen_paths.add(path)
        rules.append(
            ContextBudgetRule(
                path=path,
                owner_packet=_require_nonempty_str(
                    rule_payload.get("owner_packet"),
                    context=f"rules[{index}].owner_packet",
                ),
                owner_label=_require_nonempty_str(
                    rule_payload.get("owner_label"),
                    context=f"rules[{index}].owner_label",
                ),
                max_lines=_require_positive_int(
                    rule_payload.get("max_lines"),
                    context=f"rules[{index}].max_lines",
                ),
            )
        )
    return tuple(rules)


def line_count_for_file(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def evaluate_rules(
    repo_root: Path = REPO_ROOT,
    rules: Sequence[ContextBudgetRule] | None = None,
) -> tuple[ContextBudgetResult, ...]:
    active_rules = load_rules() if rules is None else tuple(rules)
    results: list[ContextBudgetResult] = []
    for rule in active_rules:
        target_path = repo_root / Path(rule.path)
        if not target_path.is_file():
            results.append(
                ContextBudgetResult(
                    rule=rule,
                    actual_lines=None,
                    file_exists=False,
                )
            )
            continue
        results.append(
            ContextBudgetResult(
                rule=rule,
                actual_lines=line_count_for_file(target_path),
                file_exists=True,
            )
        )
    return tuple(results)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repository root to validate",
    )
    parser.add_argument(
        "--rules",
        default=str(DEFAULT_RULES_PATH),
        help="JSON ruleset path",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="return a failing exit code when a guarded hotspot exceeds its historical budget",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root)
    rules_path = Path(args.rules)
    try:
        rules = load_rules(rules_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    results = evaluate_rules(repo_root, rules)
    failures = [result for result in results if not result.passed]
    if failures:
        for result in failures:
            prefix = "FAIL" if args.enforce else "WARN"
            print(f"{prefix}: {result.failure_message}")
        prefix = "FAIL" if args.enforce else "WARN"
        print(
            f"{prefix}: context budget diagnostics found "
            f"{len(failures)} of {len(results)} guarded hotspots outside historical budgets."
        )
        if args.enforce:
            return 1
        return 0

    print(f"PASS: context budget diagnostics satisfied for {len(results)} guarded hotspots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
