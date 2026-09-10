# COREX Change Locality QA Matrix

- Updated: `2026-07-16`
- Evaluated base HEAD: `6a1d7737d8c26044f5746ab430d550fb9c7305d0`
- Evaluated tree: the shared working tree was intentionally dirty with the uncommitted `T01` through `T07` implementation; unrelated changes were preserved.
- Plan: [`docs/PLAN_COREX_Change_Locality_and_Breadcrumb_Reduction.md`](../../PLAN_COREX_Change_Locality_and_Breadcrumb_Reduction.md), SHA-256 `4b081ddd697b9c5fa437b0802ca0c603c00a551fac0daa9a7e0e9ed04b8443e7`
- Owner corpus: [`tests/fixtures/nav_owner_corpus.json`](../../../tests/fixtures/nav_owner_corpus.json), SHA-256 `1ae9c746c66f221a7967928b86c1bc004bc19eb66e0e92decd05119edfab9893`
- Overall status: **PARTIAL - task-owned evidence PASS; final fast verification FAIL on out-of-scope optional catalog/live-discovery drift**

## Decision Summary

The accepted locality implementation is complete. Compact owner lookup meets the plan's accuracy and output caps, performance-harness proof is filterable and recoverable, committed navigation outputs no longer carry volatile line metadata, script-editor width has one interactive hop, package-internal `nodes.types` imports are zero, and viewer command paths no longer write canonical phase/options/transport/playback state or discover capture through the shell.

All task-owned focused checks pass. The required final-state fast run was not green: it reported `2343 passed`, `2 skipped`, and one failure because a retired optional operator catalog did not match live discovery in the installed environment. The catalog, its generator, and its test were unchanged by this implementation and outside this plan's authorized scope, so this matrix records that historical environment failure without relabeling it as task-owned.

The graph-scene primary-owner gate is false: the corpus replay keeps every primary owner in the top three. The separate duplication/>5-production-files gate is **NOT MEASURED** because the five-path capsule cap is not an implementation replay. No affirmative trigger evidence was produced, so the conservative decision is **DEFER**: no graph-scene consolidation plan or implementation is created by this closeout.

## Task Closeout

| Task | Status | Current retained evidence |
|---|---|---|
| `T01` owner-first navigation | PASS | Owning suite: `17 passed` plus `10` corpus subtests. Final corpus result: top-1 `10/10`, top-3 `10/10`, maximum text/JSON output `406`/`564` UTF-8 bytes and `5` paths; agent-map check passed. |
| `T02` focused performance proof | PASS | `tests/test_track_h_perf_harness.py`: `36 passed` in `27.14 s`. A minimal offscreen `create_edge` smoke exited `0`, recorded exactly one selected sample plus the pointer-gesture limitation, and emitted bounded progress. Disposable smoke artifacts were removed. |
| `T03` stable navigation artifacts | PASS | Final combined navigation suite: `34 passed` plus `17` subtests. Source, QML, and route generator checks passed; only the route index was regenerated during this closeout after map changes. |
| `T04` script-editor width locality | PASS | Final executable QML boundary run: `36 passed`, `935` subtests. Interactive path is `ScriptEditorOverlay.qml -> ScriptEditorModel.set_width`; snapshot/restore remains on the project/session path. |
| `T05` direct node contract imports | PASS | Plan suite: `114 passed`, `36` subtests; four-package import smoke passed; AST count is `0` internal `ea_node_editor.nodes.types` imports. The external facade retains its curated `93`-name SDK `__all__`. |
| `T06` viewer pending/authoritative state | PASS | Viewer suite: `99 passed`, `26` subtests; engineering-viewer performance tests: `2 passed`. Canonical phase/options/transport/playback command-path writes and raw shell capture lookups are both `0`; request/command/backend state and locally captured camera presentation remain intentional. |
| `T07` measurement closeout | PARTIAL | This matrix, spec/map registration, final route-index regeneration, corpus replay, and focused checks pass without expanding graph scope. The required final-state fast run completed but failed on the unrelated optional catalog drift recorded below. |

The task-owned focused commands above produced inline console evidence; no focused-task log files were retained. This matrix is the durable retained summary of the final program-wide fast run; the detailed log pointer below is a local ignored diagnostic only.

## Owner Corpus Measurements

| Metric | Before | After final route regeneration | Result |
|---|---:|---:|---|
| Top-1 primary owner | **NOT CAPTURED** - no retained pre-change measurement | `10/10` | PASS; target at least `8/10` |
| Top-3 primary owner | **NOT CAPTURED** - no retained pre-change measurement | `10/10` | PASS; target `10/10` |
| Maximum default output | **NOT CAPTURED** - no retained pre-change measurement | text `406` / JSON `564` UTF-8 bytes | PASS; cap `4096` bytes |
| Maximum paths returned | **NOT CAPTURED** - no retained pre-change measurement | `5` | PASS; cap `5` |
| Retrieval calls before opening the primary owner | **NOT CAPTURED** - no retained pre-change measurement | `1` | PASS; one `nav.py find` call per case |

Before values are deliberately not reconstructed from the audit narrative, cached token totals, or the pre-change implementation. No retained per-query measurement existed.

## Focused Performance Harness Behavior

| Gate | Evidence | Result |
|---|---|---|
| Selected mutation scenario | The owning filter test records only `create_edge`; the fresh offscreen smoke records exactly one `create_edge` sample and none of the other six cases. | PASS |
| Bounded progress | The runner emits one flushed mutation-scenario record and one bounded record per repeated baseline run. The fresh smoke emits the selected scenario and run-completion records without dumping report JSON. | PASS |
| Partial-result recovery | The simulated native child failure retains `baseline_run_01.json` and `baseline_run_03.json`, writes `baseline_run_02.failed.json`, and aggregates `2` completed plus `1` failed run as `partial_failure`. | PASS |
| Bounded comparison | The comparison test keeps UTF-8 stdout below `4096` bytes, includes only the fixed load, pan/zoom, steady-drag, selected mutation, and RSS scalar rows, and excludes `baseline_series` and raw samples. | PASS |
| Measurement semantics | Reports state that `create_edge` measures programmatic production mutation dispatch through the first rendered frame, not pointer travel, port hit-testing, or a real pointer gesture. | PASS |

The fresh smoke is offscreen/software regression evidence only; it is not display-attached performance acceptance. Its disposable report directory was removed after the values above were checked.

## Locality And Authority Gates

| Gate | Before | After | Proof |
|---|---:|---:|---|
| Script-editor interactive width semantic hops | `7` | `1` | Direct release-only call to `ScriptEditorModel.set_width`; no width forwarding symbol remains on shell presenter/controller/document-I/O surfaces. |
| Package-internal `ea_node_editor.nodes.types` imports | `57` | `0` | Package-wide AST ratchet with an empty whitelist; retained SDK identity assertions cover defining modules and facade exports. |
| Viewer command-path writes to canonical phase/options/transport/playback state | Not used as a numeric baseline | `0` | `test_command_paths_do_not_write_canonical_viewer_state`; request/command/backend state and locally captured camera presentation remain intentional, while `_apply_authoritative_projection` is the sole normalization owner. |
| Raw shell lookup for viewer capture capability | Present | `0` | Runtime composition injects camera/preview capture callables; bridge source contains no `getattr(shell_window, "viewer_host_service"...)`. |

No `.cxproj` schema, graph action ID, execution protocol, viewer worker protocol, plugin descriptor, or user-visible behavior was intentionally changed.

## Graph Consolidation Decision

| Proceed gate from the plan | Final evidence | Triggered? |
|---|---|---|
| A representative replay still requires more than five production files because the same state or policy fact is duplicated. | The corpus proves owner lookup only. Its default five-path cap cannot measure how many production files an implementation replay requires, and no qualifying implementation replay was recorded. | **NOT MEASURED** |
| The primary owner misses the top three after owner-first navigation and stable artifacts. | Final replay: top-3 `10/10`. | No |

Decision: **DEFER** graph-scene consolidation because no affirmative trigger evidence was produced. The duplication/>5-production-files gate remains unmeasured; the closeout does not create a follow-up graph plan.

## Final Verification

| Command or gate | Result | Evidence location |
|---|---|---|
| T03 combined navigation suite | PASS - `34 passed`, `17` subtests | Inline console |
| Source navigation generator `--check` | PASS | Inline console |
| QML navigation generator `--check` | PASS | Inline console |
| Agent route generator `--check` | PASS | Inline console |
| Final corpus replay | PASS - top-1/top-3 `10/10`, max text/JSON `406`/`564` bytes, max `5` paths, max `1` call | Metrics retained in this matrix |
| Fresh offscreen `create_edge` smoke | PASS - one selected sample, two bounded progress lines, limitation present; disposable report removed | Inline console |
| `scripts/check_traceability.py` | PASS | Inline console |
| `scripts/check_markdown_links.py` | PASS | Inline console |
| `scripts/check_agent_maps.py` | PASS | Inline console |
| `scripts/run_verification.py --mode fast --summarize-output` | FAIL - `1 failed`, `2343 passed`, `2 skipped`, `12 warnings` in `166.17 s` | Local ignored diagnostic: `artifacts/verification_logs/20260716_045016/01_fast.pytest.log`; durable summary retained here |
| Exact failed optional-catalog test rerun | FAIL - `1 failed`, `4 warnings` in `12.78 s` | Inline console |
| `git diff --check` | PASS | Inline console; line-ending warnings only |

## Residual Risks And Non-Goals

- Dynamic imports are outside the static `nodes.types` AST ratchet; no current package use was found.
- Untracked external plugins could have imported incidental `nodes.types` attributes that were never in its public `__all__`; the pre-release compatibility policy does not retain those aliases without a current SDK requirement.
- The retired optional catalog was `3,875,286` bytes while the environment's live rendering was `3,918,459` bytes and included `maximum`/`minimum` fields absent from the asset. The catalog, generator, and test were unchanged by this implementation; no clean base checkout was tested. It was the sole final-fast failure in that historical run.
- Offscreen/software harness smoke does not replace display-attached acceptance for performance-affecting work.
- The corpus is intentionally ten labeled tasks. Expand it only when a new lookup failure cannot be represented by the existing sample.
- Graph-scene consolidation, a second ownership manifest, SQLite indexing, a general barrel detector, dashboards, and new runner/checker rules remain out of scope.
