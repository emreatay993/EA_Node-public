# Verification, Testing, And Docs Hygiene

## Purpose
Use this for verification mode selection, pytest defaults, shell isolation, docs/link hygiene, traceability checks, static hygiene checks, and verification manifests.

## Start Here
- `scripts/run_verification.py`
- `scripts/verification_manifest.py`
- `ea_node_editor/pytest_defaults.py`
- `tests/conftest.py`
- `tests/test_run_verification.py`
- `tests/test_traceability_checker.py`
- `tests/test_markdown_hygiene.py`
- `tests/test_agent_route_index.py`
- `tests/test_dead_code_hygiene.py`
- `tests/test_novice_plugin_sdk_docs.py`
- `tests/test_repo_owned_node_documentation.py`
- `tests/repo_owned_catalog_fixture.py`
- `tests/fixtures/node_catalog/current_repo_owned_catalog.json`
- `scripts/nav.py`
- `tests/test_nav_cli.py`
- `scripts/check_traceability.py`
- `scripts/check_markdown_links.py`
- `scripts/generate_agent_route_index.py`
- `docs/agent_route_index.md`
- `docs/agent_route_index.json`
- `scripts/generate_source_test_file_index.py`
- `docs/source_test_file_index.md`
- `scripts/generate_qml_navigation_index.py`
- `docs/qml_navigation_index.md`
- `docs/qml_navigation_index.json`
- `docs/specs/perf/COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md`

## Do Not Start Here
- Broad `pytest` without checking verification mode ownership.
- Shell-backed direct commands unless doing a focused manual rerun.

## Common Changes
- Update `verification_manifest.py` with docs when verification workflow facts change.
- Keep planned requirement owners and exact unimplemented statuses in `verification_manifest.py`; `check_traceability.py` rejects missing, duplicate, misowned, or proof-bearing planned rows.
- Keep fast-mode xdist exclusions and the `fast.serial.pytest` target list in
  `scripts/verification_manifest.py`; do not leave them only in baseline notes.
- Keep shell-isolation coverage in the dedicated full-mode phase.
- For docs-only changes, prefer markdown/link checks and targeted hygiene tests.
- Keep generated-metadata tracking and dead-code guardrails in focused hygiene tests, not broad lint phases.
- The no-legacy guardrail inventory owns the T16 clean break: the former nodes
  public barrels, entry-point/class/descriptor discovery, executable manifests,
  and project entry point must stay absent. `test_architecture_boundaries.py`
  separately pins the exact dependency-free 17-name `corex` export surface.
- Keep `scripts/nav.py find` joined to generated QML component metadata so UI terms and QML symbols resolve to the map-owned source path, focused test, and verification command.
- Keep task-language aliases neutral and exact. Put each alias on the narrowest owning map, cite the exact live file that should open first, and place its smallest route-owned proving test in `Start Here` and `Focused Verification`.
- When a QML component has a feature owner, cite its exact repository path on that feature map so the explicit owner beats the inferred subsystem. Omit a focused test when no route-owned test is defensible instead of borrowing an unrelated test from another surface.
- Public executable plugin examples live under `docs/examples/` and are parsed,
  packaged, and run through the real process-worker path by
  `tests/test_novice_plugin_sdk_docs.py`. The internal visual-control fixture
  lives under `tests/fixtures/node_controls/` and is not public authoring
  guidance.
- The generated T17 documentation overlay augments the frozen pre-cutover
  catalog only in documentation tests; it is not runtime registry metadata.
- Register `COREX_NOVICE_PLUGIN_SDK_QA_MATRIX.md` from the spec index and keep
  any outstanding full-verification or package-smoke gate visible until it
  passes.
- Regenerate `docs/agent_route_index.md` and `docs/agent_route_index.json` with their script when agent maps, coverage rows, QML metadata, or source/test inventory change.
- Regenerate `docs/source_test_file_index.md` with its script when refreshing the stable source/test path inventory; current lines are resolved on demand with `scripts/nav.py line`.
- Regenerate `docs/qml_navigation_index.md` and `docs/qml_navigation_index.json` with their script when QML component routing metadata changes.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_run_verification.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_agent_route_index.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_dead_code_hygiene.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_novice_plugin_sdk_docs.py tests/test_repo_owned_node_documentation.py --ignore=venv -q
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py --check
.\venv\Scripts\python.exe .\scripts\generate_source_test_file_index.py --check
.\venv\Scripts\python.exe .\scripts\generate_qml_navigation_index.py --check
```

## Breadcrumbs
- [Verification Runner](../testing/verification_runner.md)
- [Shell Isolation Tests](../testing/shell_isolation_tests.md)
- [Docs, Traceability, And Hygiene Tests](../testing/docs_traceability_hygiene.md)

## Update Triggers
Update when verification mode commands, pytest defaults, shell-isolation ownership, documentation-example validation, docs hygiene, static hygiene, navigation alias/path/test maintenance, generated navigation indexes, or traceability checks change.
