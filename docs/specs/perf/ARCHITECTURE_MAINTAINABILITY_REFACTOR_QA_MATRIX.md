# Architecture Maintainability Refactor QA Matrix

- Updated: `2026-03-28`
- Packet set: `ARCHITECTURE_MAINTAINABILITY_REFACTOR` (`P01` through `P13`)
- Scope: final verification, docs, and traceability closeout for the maintainability refactor packet set.

## Locked Scope

- The active closeout proof for this packet set lives in `ARCHITECTURE.md`, `README.md`, `docs/specs/INDEX.md`, `docs/specs/requirements/90_QA_ACCEPTANCE.md`, `docs/specs/requirements/TRACEABILITY_MATRIX.md`, `docs/specs/perf/VERIFICATION_SPEED_QA_MATRIX.md`, and this matrix.
- `scripts/verification_manifest.py` is the canonical source for the packet-owned verification command set, shell-isolation catalog contract, and doc-audit anchors.
- `scripts/check_traceability.py` audits semantic drift across the active closeout docs, and `scripts/check_markdown_links.py` audits local Markdown links across those same canonical surfaces.
- `docs/PACKAGING_WINDOWS.md` and `docs/PILOT_RUNBOOK.md` remain the operator runbooks for Windows packaging, signing, and packaged-pilot reruns; this packet records their follow-up status but does not claim fresh Windows evidence.
- `docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md` is retained as a historical pointer because some older docs outside the P13 write scope still link to it.

## Shell Isolation Contract

- `./venv/Scripts/python.exe scripts/run_verification.py --mode full` remains the only documented top-level runner for the full verification workflow.
- The dedicated shell-isolation phase is `tests/test_shell_isolation_phase.py`; it launches fresh child interpreters via `tests/shell_isolation_runtime.py` instead of running shell-backed suites inside the main pytest interpreter.
- `scripts/verification_manifest.py` owns `SHELL_ISOLATION_SPEC`, `SHELL_ISOLATION_CATALOG_SPECS`, the catalog module names, and the target-id prefixes that the runtime enforces.
- The active manifest-owned target catalogs are `tests/shell_isolation_main_window_targets.py` and `tests/shell_isolation_controller_targets.py`.
- Focused child reruns should flow through the manifest-owned pytest arg builder or the runtime target catalogs instead of duplicating ad hoc shell commands in docs.

## Final Verification Commands

| Coverage Area | Command | Expected Coverage |
|---|---|---|
| Packet-owned docs and structural proof | `./venv/Scripts/python.exe -m pytest tests/test_dead_code_hygiene.py tests/test_run_verification.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_shell_isolation_phase.py --ignore=venv -q` | Revalidates the AST-backed helper-boundary checks, the runner/manifest contract, traceability parsing, markdown-link hygiene, and the centralized shell-isolation phase |
| Traceability gate | `./venv/Scripts/python.exe scripts/check_traceability.py` | Confirms the refreshed closeout docs, requirements, spec index, QA matrices, and historical pointers stay aligned |
| Markdown link gate | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Confirms the active Markdown docs resolve to existing local targets and valid heading anchors |

## Focused Narrow Reruns

| Coverage Area | Command | When To Use It |
|---|---|---|
| Runner and shell-isolation contract | `./venv/Scripts/python.exe -m pytest tests/test_run_verification.py tests/test_shell_isolation_phase.py --ignore=venv -q` | Use after editing `scripts/verification_manifest.py`, `scripts/run_verification.py`, or the shell-isolation runtime/target files |
| Traceability and proof docs | `./venv/Scripts/python.exe -m pytest tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_dead_code_hygiene.py --ignore=venv -q` | Use after editing `ARCHITECTURE.md`, `README.md`, spec docs, perf matrices, or traceability rows |
| Semantic proof audit | `./venv/Scripts/python.exe scripts/check_traceability.py` | Use as the review gate after any closeout-doc or traceability edit |
| Markdown links only | `./venv/Scripts/python.exe scripts/check_markdown_links.py` | Use after editing local Markdown links, especially spec-index, requirements, or QA-matrix references |

## 2026-03-28 Execution Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe -m pytest tests/test_dead_code_hygiene.py tests/test_run_verification.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py tests/test_shell_isolation_phase.py --ignore=venv -q` | PASS | Packet-owned verification suite passed in the project venv (`58 passed, 3 subtests passed`) after the structural proof and docs closeout refresh |
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | Canonical-doc drift audit passed after the maintainability closeout docs, QA matrix, and traceability refresh |
| `./venv/Scripts/python.exe scripts/check_markdown_links.py` | PASS | Active canonical Markdown docs resolved to existing local targets and valid headings |

## Remaining Manual and Windows-Only Checks

1. Base packaging rerun: execute `.\scripts\build_windows_package.ps1 -PackageProfile base -Clean`, confirm `artifacts\pyinstaller\dist\base\COREX_Node_Editor\COREX_Node_Editor.exe` exists, and retain the generated dependency matrix under `artifacts\releases\packaging\base\`.
2. Base installer rerun: execute `.\scripts\build_windows_installer.ps1 -PackageProfile base`, then confirm the latest `installer_manifest.json` and `installer_validation.json` under `artifacts\releases\installer\base\<run_id>\` record `package_profile: base`.
3. Signing rerun with real certificate material: execute `.\scripts\sign_release_artifacts.ps1 -PackageProfile base -VerifyOnly` for snapshot capture, then rerun with `-CertThumbprint` and `-TimestampServer` when release credentials are available.
4. Pilot rerun: follow `docs/PILOT_RUNBOOK.md` against a freshly built packaged candidate and record new evidence instead of reusing archived `2026-03-01` snapshots.
5. Native Windows shell verification: if shell-backed regressions reproduce only on native desktop QML sessions, rerun the manifest-owned `full` workflow on a native Windows host before treating the closeout as representative of packaged-shell behavior.

## Historical References

- `docs/specs/perf/ARCHITECTURE_REFACTOR_QA_MATRIX.md` is a historical pointer retained for older links outside the P13 write scope.
- `docs/specs/perf/RC_PACKAGING_REPORT.md` is an archived `2026-03-01` packaging smoke snapshot kept for historical context only.
- `docs/specs/perf/PILOT_SIGNOFF.md` is an archived `2026-03-01` packaged desktop pilot snapshot kept for historical context only.
- Neither archived report nor the pointer matrix substitutes for fresh package, installer, signing, or pilot evidence.

## Residual Risks

- Windows packaging, signing, and pilot evidence were not rerun in this packet.
- `docs/GETTING_STARTED.md`, `docs/PACKAGING_WINDOWS.md`, and `docs/PILOT_RUNBOOK.md` still reference the historical pointer path because they are outside this packet's write scope; the pointer file now redirects readers to this current matrix.
- The shell-isolation catalog is intentionally targeted rather than exhaustive; `test_recovery_prompt_is_skipped_when_autosave_matches_restored_session` is left out of the isolated child catalog because its autosave cleanup assertion is not stable in fresh child-process mode on this branch.
- The structural proof layer catches doc drift and shell-isolation contract drift, but it does not generate fresh packaged-build or desktop/GPU evidence by itself.
