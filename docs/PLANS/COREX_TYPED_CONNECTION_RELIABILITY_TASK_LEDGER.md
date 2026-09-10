# COREX Typed Connection Reliability - Task Ledger

Plan: [COREX Typed Connection Reliability](../PLAN_COREX_TYPED_CONNECTION_RELIABILITY.md)

## Approved decisions

- Graph legality remains unchanged for assignable, convertible, and
  runtime-checked relations.
- The graph owns structured compatibility; Quick Insert owns recommendation.
- Blank connection Quick Insert hides broad/runtime fallbacks; explicit search
  reveals them with text labels.
- Repo-owned/public authoring and projection fail closed instead of inventing
  global Any.
- Unrelated metadata, generators, catalogues, fixtures, and type expansion are excluded.
- No runtime-red wire redesign, compatibility shim, or insertion rollback.
- No commit or push without separate explicit authorization.
- Implementation inventory correction: the exact default-resolved repo-owned Any
  inventory is 20, not the planning count of 17. Existing
  `mars.batch_solve.files`, `mars.run_job.files`, and `mars.time_history.files`
  deliberately emit filename-to-`RuntimeArtifactRef` maps. Their explicit Any
  contract and runtime shape are pinned by existing MARS tests; no current
  precise type fits and MARS implementation remains unchanged.

## Baseline

- Repository: the `EA_Node_Editor` working checkout
- Branch: `main`
- Starting HEAD: `b3719075aaef9dc3315d98aab77f9432fc97805a`
- Implementation authorized: `2026-09-03`
- Pre-existing dirty paths:
  - `M docs/specs/INDEX.md` - user-owned Physical Simulation registration
  - `?? docs/PLAN_COREX_Physical_Simulation_Backend.md`
  - `?? scripts/Strain_Gage_Positioning/modular_version/strain_candidate_points.csv`
- Protected untracked plan SHA-256:
  `F1709CD27CDD97141E354AB0644B3602F8EA43EBEFBB294B0C5FA4578C6788F2`
- The two untracked user files must not be edited, moved, staged, or deleted.
- The existing `docs/specs/INDEX.md` hunk must be preserved when adding the new
  plan registration.
- During T06 an external unrelated commit advanced HEAD to
  `5312999b42f2f060af029cadda84b04348dee13f` (viewer binder cleanup and its test
  only). This task preserves that commit and reviews its own worktree diff.
- Protected CSV SHA-256 captured by independent verification:
  `468C04C09DF327871ED6CD947EF58E8F26412D632A1E969C3C56303DFC44061B`.

## Tasks

| ID | Status | Owner | Preconditions | Allowed scope | Changed paths | Focused evidence | Review / next action | Commit if authorized |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T00 | ACCEPTED | `/root` | Implementation authorization | Plan, ledger, exact index line | Plan and ledger created; index registration added while preserving the user hunk | Markdown links PASS; `git diff --check` PASS; protected hash unchanged | T01 unblocked | none |
| T01 | ACCEPTED | `/root/typed_connection_implementer` | T00 accepted | Type catalogue, core types, graph compatibility/warnings, focused tests | runtime type/core exports; core_data_types; effective_ports; invariant_kernel; route_payload; five focused test modules | 74 core/type/graph passed; 4 warning/export tests passed; 4 declared-collection tests passed; Ruff and diff check PASS | Root inspected complete diff; T02 unblocked | none |
| T02 | ACCEPTED | `/root/typed_connection_implementer` | T01 accepted | Repo-owned metadata, declaration parsers, catalogue, focused tests | Eleven primary types; four accepted tuples; plugin/Python parsers; current catalogue/loader; focused tests | 168 + 114 + 115 + 1 tests passed, 77 subtests; audit/accepted-Any leak/reuse/migration exact checks 4 passed; Ruff/diff PASS | Root reviewed declarations/catalogue/audit; exact Any count 20; T03 unblocked | none |
| T03 | ACCEPTED | `/root/typed_connection_implementer` | T01-T02 accepted | Workflow/Library/QML preview projection, focused tests | codec/publication guard; Library projection/presenter; QML preview; necessary Quick Insert missing-type guards; focused tests | 77 tests + 12 subtests; package IO 6 tests; Ruff/diff PASS | Root reviewed strict publish/tolerant load/default-port flow; T04 unblocked | none |
| T04 | ACCEPTED | `/root/typed_connection_implementer` | T01-T03 accepted | Quick Insert, presenter, drop controller, overlay, focused tests | Quick Insert tiers/payload/rank; presenter/state; ordinary/workflow selected-key revalidation; overlay; projection/controller/shell/isolation tests; published pin-key mapping restricted to Quick Insert | REV-02 failed-before both subcases; after fix 2+4 subtests; controller/workflow/projection39+21; offscreen shell14+4; isolation2; Ruff/diff PASS | Independent re-review accepts REV-01/02, no residual findings | none |
| T05 | ACCEPTED | `/root/typed_connection_implementer` | T01-T04 accepted | Persistence proof, specs/guides/maps/indexes, ledger | serializer load proof; three guides; architecture; requirements/traceability; nine maps/coverage; generated indexes | 80 tests + 22 subtests; hygiene 132 + 258 subtests; traceability/links/maps/index freshness/Ruff/diff PASS | Root reviewed load proof and docs; T06 unblocked | none |
| T06 | ACCEPTED | `/root/typed_connection_reviewer` + `/root/typed_connection_verifier` | T01-T05 implemented; independent review accepted | Final read-only verification and ledger closeout | Three stale test fixtures corrected; injected registry isolated under tmp_path; production unchanged | Complete fast4765 passed/2 skipped (main4547, serial218); desktop PASS; focused/QML/docs/index/Ruff/diff PASS; all review findings closed | Complete; no commit or push | none |

## Review findings

| ID | Finding | Owner resolution | Evidence | Status |
| --- | --- | --- | --- | --- |
| REV-01 | P1: normally published workflows lack explicit endpoint IDs, so restricted Quick Insert enters an empty endpoint path and inserts without connecting | Original writer mapped original child-pin keys through the existing paste map onto the pasted root shell, with parent/pin-type checks; no unrestricted fallback | Real publish-to-Quick-Insert regression failed before fix in both directions; afterward 1 test+2 subtests passed; reviewer accepts restricted mapping | CLOSED |
| REV-02 | P2: unconditional published-shell endpoint synthesis changes ordinary Library port/edge drops from the existing chooser to first-match wiring | Added explicit map_published_shell_ports flag only for restricted Quick Insert port requests; ordinary/explicit-endpoint routing preserved | Real ordinary published-workflow port/edge drop chooses second input; failed-before/passing-after; independent re-review accepts with no residual finding | CLOSED |
| REV-03 | P2: injected trusted test bundle used the default user plugin-generation cache | Helper now requires generation_root; both tests isolate APPDATA under tmp_path and pass approved generation directory | Exact reuse2/full module35 pass; root quarantined exactly two test-only generations; independent re-review accepts | CLOSED |

## Completion record

- Bounded generated maintenance: source/test index now includes the baseline
  tracked `tests/test_managed_tooltip_lifecycle.py`; QML indexes refresh baseline
  ManagedToolTip and GraphCanvasActionRouter entries plus intended Quick Insert
  object names. Those baseline source files were not edited.
- Test-cache cleanup: two verified test-only injected generations were moved
  from the normal plugin cache to recoverable temporary quarantine
  `corex-typed-connection-cache-quarantine-20260903` under the OS temporary directory.
  Source hashes remained identical; no user generation was moved or deleted.
- Final focused checks: independent 232 contract/metadata + 221 authoring/projection + 10 offscreen QML/shell passed, with 97 subtests; affected controller/workflow/projection69+21 also passed
- Fast verification: PASS, exit0, 4765 tests passed and 2 skipped. Main phase4547 passed/2 skipped in383.22s; serial phase218 passed in89.89s. Final logs: `artifacts/verification_logs/20260903_234822/`. Exact four former failures independently passed after test-only fixture corrections.
- Desktop smoke: PASS via actual Windows mouse/key input on isolated canonical bootstrap: Geometry Group precise match, searched Panel broad match and mouse edge, reverse Scene, Python Script Any empty hint, searched Logger runtime-check/Enter edge, Escape, field focus, outside dismissal, right-edge clamp. Only owned PIDs stopped; no manual save. Automatic recovery remains only in isolated temporary app data because cleanup was blocked by tool policy.
- Maps / traceability / Markdown: PASS, including all three generated-index freshness checks and changed-Python Ruff/diff hygiene
- Independent review: accepted after REV-01 and REV-02 fixes; no residual findings; static only
- Implementation-acceptance HEAD: `5312999b42f2f060af029cadda84b04348dee13f`; no commit was made before the later publication authorization below.
- Remaining pre-existing dirty paths at acceptance: original Physical Simulation index line and both untracked user files preserved; protected plan/CSV/frozen-catalogue hashes unchanged.

## Publication

The user authorized scoped commits to `main` and a push on 2026-09-04.
The publication preflight found `HEAD == origin/main` at `5312999b`, so no
unrelated ahead commit was included. Publication changes no production content.

| Task group | Commit |
| --- | --- |
| T01 compatibility and types | `ed016ce736596323eef300b76ad68de74e327e8b` |
| T02 metadata and explicit declarations | `02f73451bc37f96691764482b694f665da09e009` |
| T03 Library/workflow projection | `9528d87c1c44739b03c0c03604c89d5e057424ee` |
| T04 Quick Insert and selected-port revalidation | `c9bfe906bf9e4a33301ceea78cf23734cb67fc5d` |
| T00/T05/T06 documentation, load proof, and acceptance | This documentation commit |

The existing Physical Simulation index hunk is excluded from staging. The
Physical Simulation plan, strain-candidate CSV, and later untracked
`docs/PLANS/COREX_CAD_IMPORT_COLLAPSED_FACES_PLAN.md` remain untouched and
untracked. Final push/remote-parity evidence is reported in the publication
handoff rather than adding a process-only follow-up commit.

## Mandatory resume protocol

After context compaction, handoff, or a long pause, before any edit or new
assignment:

1. Reread the latest user request.
2. Reread the entire plan from beginning to end.
3. Reread this entire ledger.
4. Reread repository `AGENTS.md`.
5. Check repository root, branch, HEAD, and `git status --short`.
6. Inspect active/staged diffs and task-owned untracked files.
7. Reconcile recorded evidence and unresolved review rows.
8. Inspect live agents and confirm at most one writer.
9. State current task, satisfied dependencies, next owner, and proving check.
10. Only then resume.
