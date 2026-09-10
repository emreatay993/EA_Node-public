from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.shell_isolation_runtime import load_target_registry


ROOT = Path(__file__).resolve().parents[1]
LEDGER = (
    ROOT / "docs/specs/perf/COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR_QA_MATRIX.md"
)
PLAN = ROOT / "docs/PLAN_COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR.md"

TASK_STATUSES = {
    "NOT STARTED",
    "IN PROGRESS",
    "ACCEPTED",
    "ACCEPTED NO-OP",
    "BLOCKED",
}
FINAL_DISPOSITIONS = {
    "retained",
    "moved_to_owner",
    "replaced_by_owner_test",
    "replaced_by_qml_quick",
    "retained_real_shell_lifecycle",
    "redundant_existing_owner_proof",
    "deleted_obsolete_behavior",
}
PENDING_DISPOSITION = "pending_migration"
MIGRATION_HEADER = (
    "Program",
    "Owning task",
    "ID kind",
    "Old ID / selector / target",
    "Behavior guarded",
    "Production owner",
    "Phase / isolation",
    "Disposition",
    "Replacement IDs / selectors",
    "Assertion equivalence",
    "Collecting commit",
    "Execution result",
    "Accepted commit",
)
PHASES_BY_KIND = {
    "python": {
        "fast.pytest",
        "fast.serial.pytest",
        "gui.pytest",
        "gui.serial.pytest",
        "slow.pytest",
    },
    "qml_quick": {"gui.qml_quick / qmltestrunner"},
    "shell_target": {"full.shell_isolation / child process"},
}
COMMIT_RE = re.compile(r"^(?:This commit|[0-9a-f]{8,40})$")
RETAINED_TASK_IDS = ("T00", *(f"T{index:02d}" for index in range(7, 27)))
# 7f5304b4 removed these exact rows with the retired graph product. Its parent
# a7da1170 records every one as ACCEPTED; absence alone never grants acceptance.
RETIRED_ACCEPTED_TASK_IDS = tuple(f"T{index:02d}" for index in range(1, 7))


def _table(text: str, heading: str) -> tuple[list[str], list[list[str]]]:
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    table = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|") and not re.match(r"^\|\s*-", line)
    ]
    return table[0], table[1:]


def _top_status(text: str) -> str:
    match = re.search(r"(?m)^Status: `([^`]+)`$", text)
    assert match is not None
    return match.group(1)


def _task_statuses(rows: list[list[str]]) -> dict[str, str]:
    return {row[0].split()[0]: row[2] for row in rows}


def _validate_tasks(rows: list[list[str]]) -> list[int]:
    assert all(len(row) == 9 for row in rows)
    task_ids = [row[0].split()[0] for row in rows]
    statuses = [row[2] for row in rows]
    assert task_ids == list(RETAINED_TASK_IDS)
    assert set(statuses) <= TASK_STATUSES

    active = [
        index
        for index, status in enumerate(statuses)
        if status in {"IN PROGRESS", "BLOCKED"}
    ]
    assert len(active) <= 1
    boundary = (
        active[0]
        if active
        else next(
            (index for index, status in enumerate(statuses) if status == "NOT STARTED"),
            len(statuses),
        )
    )
    assert all(
        status in {"ACCEPTED", "ACCEPTED NO-OP"} for status in statuses[:boundary]
    )
    if active:
        assert all(status == "NOT STARTED" for status in statuses[boundary + 1 :])
    else:
        assert all(status == "NOT STARTED" for status in statuses[boundary:])

    for row in rows:
        status = row[2]
        if status not in {"ACCEPTED", "ACCEPTED NO-OP"}:
            continue
        writer, focused, performance, review, commit = (
            row[3],
            row[5],
            row[6],
            row[7],
            row[8],
        )
        assert all(
            value not in {"", "Pending", "N/A"}
            for value in (writer, focused, performance, review)
        )
        if status == "ACCEPTED":
            assert COMMIT_RE.fullmatch(commit)
        else:
            assert commit == "N/A — accepted no-op"

    status_by_id = dict(zip(task_ids, statuses, strict=True))
    if status_by_id["T13"] not in {"ACCEPTED", "ACCEPTED NO-OP"}:
        assert all(
            status_by_id[task_id] == "NOT STARTED"
            for task_id in RETAINED_TASK_IDS
            if int(task_id[1:]) > 13
        )
    return active


def _valid_old_id(kind: str, old_id: str) -> bool:
    if kind == "python":
        return old_id.startswith("tests/") and "::" in old_id
    if kind == "qml_quick":
        return (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*::test_[A-Za-z0-9_]+", old_id)
            is not None
        )
    if kind == "shell_target":
        return (
            re.fullmatch(
                r"(?:main_window|script_editor|run_controller|project_session)__[a-z0-9_]+",
                old_id,
            )
            is not None
        )
    return False


def _validate_migrations(rows: list[list[str]], task_status: dict[str, str]) -> None:
    assert len({(row[2], row[3]) for row in rows}) == len(rows)
    for row in rows:
        assert len(row) == len(MIGRATION_HEADER)
        assert all(cell != "" for cell in row)
        (
            program,
            owning_task,
            kind,
            old_id,
            _behavior,
            production_owner,
            phase,
            disposition,
            replacement,
            equivalence,
            collecting,
            result,
            accepted,
        ) = row
        assert program in {"A", "B"}
        assert owning_task in task_status or owning_task in RETIRED_ACCEPTED_TASK_IDS
        task_number = int(owning_task[1:])
        assert (program == "A" and 1 <= task_number <= 12) or (
            program == "B" and 14 <= task_number <= 25
        )
        assert kind in PHASES_BY_KIND
        assert _valid_old_id(kind, old_id)
        assert phase in PHASES_BY_KIND[kind]
        assert disposition in FINAL_DISPOSITIONS | {PENDING_DISPOSITION}

        na_columns = {index for index, value in enumerate(row) if value == "N/A"}
        legal_na: set[int] = set()
        if disposition == "deleted_obsolete_behavior":
            legal_na.update({5, 8})
        if disposition in {"retained", "retained_real_shell_lifecycle"}:
            legal_na.add(8)
        assert na_columns <= legal_na
        if production_owner == "N/A":
            assert disposition == "deleted_obsolete_behavior"

        owner_status = task_status.get(owning_task)
        if owner_status is None:
            assert owning_task in RETIRED_ACCEPTED_TASK_IDS
            owner_status = "ACCEPTED"
        if disposition == PENDING_DISPOSITION:
            assert owner_status in {"NOT STARTED", "IN PROGRESS"}
            continue

        assert equivalence not in {"Pending", "N/A"}
        assert collecting not in {"Pending", "N/A"}
        assert result not in {"Pending", "N/A"}
        assert accepted not in {"Pending", "N/A"}
        assert COMMIT_RE.fullmatch(collecting)
        assert COMMIT_RE.fullmatch(accepted)
        if disposition in {
            "moved_to_owner",
            "replaced_by_owner_test",
            "replaced_by_qml_quick",
            "redundant_existing_owner_proof",
        }:
            assert replacement not in {"Pending", "N/A"}

    if task_status["T13"] in {"ACCEPTED", "ACCEPTED NO-OP"}:
        assert all(row[7] != PENDING_DISPOSITION for row in rows if row[0] == "A")
    if task_status["T25"] in {"ACCEPTED", "ACCEPTED NO-OP"}:
        assert all(row[7] != PENDING_DISPOSITION for row in rows)


def _validate_status_sync(
    plan_text: str, ledger_text: str, task_rows: list[list[str]], active: list[int]
) -> None:
    status = _top_status(plan_text)
    assert status == _top_status(ledger_text)
    statuses = [row[2] for row in task_rows]
    if active:
        index = active[0]
        task_id = task_rows[index][0].split()[0]
        assert status == f"{statuses[index]} — {task_id}"
        return
    if statuses[-1] in {"ACCEPTED", "ACCEPTED NO-OP"}:
        assert status == "COMPLETED — T00–T26 ACCEPTED"
        return
    next_index = next(
        index for index, value in enumerate(statuses) if value == "NOT STARTED"
    )
    assert next_index > 0
    next_task_id = task_rows[next_index][0].split()[0]
    previous_task_id = task_rows[next_index - 1][0].split()[0]
    assert status == (
        f"CHECKPOINT — {previous_task_id} ACCEPTED; NEXT {next_task_id}"
    )


def _validate_documents(plan_text: str, ledger_text: str) -> None:
    task_header, task_rows = _table(ledger_text, "## Task Ledger")
    assert task_header[:3] == ["Task", "Program", "Status"]
    active = _validate_tasks(task_rows)
    migration_header, migration_rows = _table(ledger_text, "## Test Migration Ledger")
    assert tuple(migration_header) == MIGRATION_HEADER
    _validate_migrations(migration_rows, _task_statuses(task_rows))
    _validate_status_sync(plan_text, ledger_text, task_rows, active)


def test_plan_and_ledger_are_complete_and_synchronized() -> None:
    _validate_documents(
        PLAN.read_text(encoding="utf-8"),
        LEDGER.read_text(encoding="utf-8"),
    )


def test_completed_t26_checkpoint_is_valid() -> None:
    plan_text = PLAN.read_text(encoding="utf-8")
    ledger_text = LEDGER.read_text(encoding="utf-8")
    checkpoint = "COMPLETED — T00–T26 ACCEPTED"
    assert _top_status(plan_text) == checkpoint
    assert _top_status(ledger_text) == checkpoint
    _validate_documents(plan_text, ledger_text)


def test_accepted_task_requires_complete_evidence() -> None:
    _, rows = _table(LEDGER.read_text(encoding="utf-8"), "## Task Ledger")
    rows[0][5] = "Pending"
    with pytest.raises(AssertionError):
        _validate_tasks(rows)


def test_task_ledger_rejects_any_other_missing_retained_row() -> None:
    _, rows = _table(LEDGER.read_text(encoding="utf-8"), "## Task Ledger")
    rows.pop(1)
    with pytest.raises(AssertionError):
        _validate_tasks(rows)


def test_plan_and_ledger_status_drift_is_rejected() -> None:
    with pytest.raises(AssertionError):
        _validate_documents(
            PLAN.read_text(encoding="utf-8").replace(
                "Status: `COMPLETED — T00–T26 ACCEPTED`",
                "Status: `CHECKPOINT — T13 ACCEPTED; NEXT T14`",
                1,
            ),
            LEDGER.read_text(encoding="utf-8"),
        )


def _pending_row() -> list[str]:
    return [
        "A",
        "T01",
        "python",
        "tests/test_example.py::test_case",
        "Behavior",
        "ea_node_editor.owner",
        "fast.pytest",
        PENDING_DISPOSITION,
        "Pending",
        "Pending",
        "Pending",
        "Pending",
        "Pending",
    ]


def _not_started_statuses() -> dict[str, str]:
    return {f"T{index:02d}": "NOT STARTED" for index in range(27)}


def test_migration_rejects_missing_required_fields() -> None:
    row = _pending_row()
    row[4] = ""
    with pytest.raises(AssertionError):
        _validate_migrations([row], _not_started_statuses())


@pytest.mark.parametrize(
    ("kind", "phase"),
    (("invalid", "fast.pytest"), ("python", "gui.qml_quick / qmltestrunner")),
)
def test_migration_rejects_invalid_kind_or_phase(kind: str, phase: str) -> None:
    row = _pending_row()
    row[2], row[6] = kind, phase
    with pytest.raises(AssertionError):
        _validate_migrations([row], _not_started_statuses())


def test_pending_migration_is_illegal_after_owner_acceptance() -> None:
    statuses = _not_started_statuses()
    statuses["T01"] = "ACCEPTED"
    with pytest.raises(AssertionError):
        _validate_migrations([_pending_row()], statuses)


@pytest.mark.parametrize("evidence_index", (10, 11, 12))
def test_final_migration_rejects_pending_evidence(evidence_index: int) -> None:
    row = _pending_row()
    row[7] = "moved_to_owner"
    row[8] = "tests/test_owner.py::test_case"
    row[9] = "Same assertions at direct owner"
    row[10] = row[12] = "This commit"
    row[11] = "PASS"
    row[evidence_index] = "Pending"
    with pytest.raises(AssertionError):
        _validate_migrations([row], _not_started_statuses())


def test_recovery_and_protected_baselines_remain_explicit() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    anchors = (
        "1. `AGENTS.md`",
        "2. `docs/PLAN_COREX_RUNTIME_REGISTRY_PRESENTATION_REFACTOR.md`",
        "3. this QA matrix",
        "4. `git status --short --branch`",
        "5. `git log -1 --oneline`",
        "6. the next `IN PROGRESS` or `NOT STARTED` task row below",
        "7. current active-agent state",
    )
    positions = [text.index(anchor) for anchor in anchors]
    assert positions == sorted(positions)
    for digest in (
        "43BFA388899097D924301BED29BBB57935512498237BCC7AF6EFDF9FF631D431",
        "F1709CD27CDD97141E354AB0644B3602F8EA43EBEFBB294B0C5FA4578C6788F2",
        "468C04C09DF327871ED6CD947EF58E8F26412D632A1E969C3C56303DFC44061B",
    ):
        assert digest in text


def _text_inventory(text: str, heading: str) -> set[str]:
    fenced = text.split(heading, 1)[1].split("```text", 1)[1].split("```", 1)[0]
    return {line.strip() for line in fenced.splitlines() if line.strip()}


def test_t25_live_and_removed_inventories_have_exact_ledger_membership() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    _, rows = _table(text, "## Test Migration Ledger")
    t25_rows = [row for row in rows if row[0] == "B" and row[1] == "T25"]
    shell_rows = [row for row in t25_rows if row[2] == "shell_target"]
    live_rows = [
        row
        for row in shell_rows
        if row[7] in {"retained", "retained_real_shell_lifecycle"}
    ]
    removed_rows = [row for row in shell_rows if row not in live_rows]
    live_ids = {row[3] for row in live_rows}
    removed_ids = {row[3] for row in removed_rows}
    registry = load_target_registry()
    baseline_ids = _text_inventory(text, "### Shell-isolation target inventory")

    assert live_ids == set(registry)
    assert baseline_ids - live_ids == removed_ids
    assert live_ids - baseline_ids == {
        "main_window__lifecycle__composition_context_provider_action_identity",
        "main_window__lifecycle__fullscreen_media_handoff",
        "main_window__lifecycle__native_parenting",
        "main_window__lifecycle__project_reset_timer_cancellation",
        "main_window__lifecycle__repeated_mount_close_teardown",
        "main_window__lifecycle__viewer_reparent_restore",
        "script_editor__test_canvas_port_edits_preserve_dirty_drafts_and_refresh_clean_editor",
    }
    assert removed_ids == {
        "main_window__bridge_local_pack__contracts_and_library_qml",
        "main_window__bridge_local_pack__remaining_qml_and_runtime",
        "main_window__graph_canvas_host_subprocess",
        "project_session__test_recent_project_paths_are_owned_by_explicit_session_state",
        "run_controller__test_failure_focus_reveals_parent_chain_when_present",
        "run_controller__test_node_settled_failure_centers_failed_node_and_retains_root_error_details",
        "run_controller__test_stale_run_events_do_not_mutate_active_run_ui",
        "run_controller__test_stream_log_events_are_scoped_to_active_run",
    }

    lifecycle_ids = {
        row[3] for row in live_rows if row[7] == "retained_real_shell_lifecycle"
    }
    assert lifecycle_ids == {
        "main_window__lifecycle__composition_context_provider_action_identity",
        "main_window__lifecycle__fullscreen_media_handoff",
        "main_window__lifecycle__native_parenting",
        "main_window__lifecycle__project_reset_timer_cancellation",
        "main_window__lifecycle__repeated_mount_close_teardown",
        "main_window__lifecycle__viewer_reparent_restore",
        "project_session__test_recovery_prompt_is_deferred_until_main_window_is_visible",
    }
    assert len(live_rows) - len(lifecycle_ids) == 43
    for row in live_rows:
        assert row[5] != "N/A"
        assert (
            "Child execution remains serial under the manifest-owned hard timeout."
            in row[9]
        )
        assert row[6] == "full.shell_isolation / child process"

    for target in registry.values():
        command = target.command
        if command[1:3] == ("-m", "pytest"):
            assert command[3:5] == ("-n", "0")
        else:
            assert "-n" not in command

    removed_python_ids = {row[3] for row in t25_rows if row[2] == "python"}
    assert removed_python_ids == _text_inventory(
        text,
        "### Accepted-T24 Python IDs removed or renamed by T25",
    )


def test_t25_direct_owner_cohort_is_exact_and_reproducible() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    section = text.split("### Reproducible 102-ID direct-owner cohort", 1)[1].split(
        "| Evidence | Result |", 1
    )[0]
    text_blocks = re.findall(r"```text\n(.*?)```", section, flags=re.DOTALL)
    modules = tuple(line for line in text_blocks[0].splitlines() if line)
    node_ids = tuple(line for line in text_blocks[1].splitlines() if line)

    assert modules == (
        "tests/test_frame_rate_sampler.py",
        "tests/main_window_shell/test_bridge_contracts.py",
        "tests/main_window_shell/test_qml_shell_roots.py",
        "tests/test_mutation_ui_effects.py",
        "tests/test_run_event_controller.py",
        "tests/test_project_session_controller_unit.py",
        "tests/test_shell_window_lifecycle.py",
    )
    assert len(node_ids) == len(set(node_ids)) == 102
    assert hashlib.sha256("\n".join(node_ids).encode()).hexdigest().upper() == (
        "539E8B44B53CDF81E52CA4F46FBFFCCB8B31E9363E0FF0020EF8981B63D3298A"
    )
