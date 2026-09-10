# Purpose: Direct project-solution save/result/candidate/adoption/GC contract tests.
# Map: subsystems/execution.md
from __future__ import annotations

import pytest

import ea_node_editor.execution.project_solution as project_solution_module
from ea_node_editor.execution.project_solution import (
    ProjectSolutionAdoptionResult,
    ProjectSolutionCandidateResult,
    ProjectSolutionGcResult,
    ProjectSolutionSaveResult,
)


def test_project_solution_save_adoption_and_gc_result_shapes_are_strict() -> None:
    for reason in project_solution_module._PROJECT_SOLUTION_SAVE_REASONS:  # noqa: SLF001
        success = reason == "project_solution_save_staged"
        result = ProjectSolutionSaveResult(
            snapshot_token="1" * 64,
            solution_namespace_id="namespace",
            candidate_generation_id="2" * 32 if success else "",
            candidate_manifest_set_digest="3" * 64 if success else "",
            initially_protected_generations=(
                (("2" * 32, "3" * 64),) if success else ()
            ),
            reason_code=reason,
            diagnostic="" if success else "Save failed safely.",
        )
        assert bool(result.metadata_solution_store) is success
    with pytest.raises(ValueError, match="candidate generation"):
        ProjectSolutionSaveResult(
            snapshot_token="1" * 64,
            solution_namespace_id="namespace",
            candidate_generation_id="2" * 32,
            candidate_manifest_set_digest="3" * 64,
        )

    adopted = ProjectSolutionAdoptionResult(
        True,
        "project_solution_adopted",
    )
    failed = ProjectSolutionAdoptionResult(
        False,
        "project_solution_adoption_candidate_invalid",
        "Candidate invalid.",
    )
    assert adopted.adopted and not failed.adopted
    assert ProjectSolutionCandidateResult(
        True,
        "project_solution_candidate_prepared",
    ).prepared
    with pytest.raises(ValueError, match="candidate result"):
        ProjectSolutionCandidateResult(
            True,
            "project_solution_candidate_invalid",
            "Invalid.",
        )
    completed = ProjectSolutionGcResult(
        ("records/sha256/aa/" + "a" * 64 + ".json",),
        (),
        False,
        "project_solution_gc_completed",
    )
    partial = ProjectSolutionGcResult(
        (),
        (),
        True,
        "project_solution_gc_partial",
    )
    assert not completed.has_more and partial.has_more


@pytest.mark.parametrize("namespace", ("namespace", "n" * 4_096))
def test_project_solution_save_result_accepts_exact_namespace_bounds(
    namespace: str,
) -> None:
    result = ProjectSolutionSaveResult(
        snapshot_token="1" * 64,
        solution_namespace_id=namespace,
        reason_code="project_solution_save_io_error",
        diagnostic="Save failed safely.",
    )
    assert result.solution_namespace_id == namespace


@pytest.mark.parametrize(
    "namespace",
    (
        "",
        " ",
        " namespace",
        "namespace ",
        "name\nspace",
        "name\x7fspace",
        "n" * 4_097,
        None,
        1,
        b"namespace",
    ),
)
def test_project_solution_save_result_rejects_invalid_namespace_shapes(
    namespace: object,
) -> None:
    with pytest.raises(ValueError, match="solution_namespace_id"):
        ProjectSolutionSaveResult(
            snapshot_token="1" * 64,
            solution_namespace_id=namespace,  # type: ignore[arg-type]
            reason_code="project_solution_save_io_error",
            diagnostic="Save failed safely.",
        )

    with pytest.raises(ValueError, match="solution_namespace_id"):
        ProjectSolutionSaveResult(
            snapshot_token="1" * 64,
            solution_namespace_id=namespace,  # type: ignore[arg-type]
            candidate_generation_id="2" * 32,
            candidate_manifest_set_digest="3" * 64,
            initially_protected_generations=(("2" * 32, "3" * 64),),
        )
