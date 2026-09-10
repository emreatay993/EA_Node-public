# Verification Speed QA Matrix

- Updated: `2026-07-24`
- Packet set: `VERIFICATION_SPEED` (`P01` through `P06`)
- Scope: published developer-facing verification workflow after the dedicated
  shell-isolation phase rollout, explicit max-parallel worker policy, and
  proof-layer refresh.

## Approved Verification Workflow

The normal implementation loop is the smallest affected test module, class, or
node ID, followed by the owning route suite once after the last related task
when adjacent proof is useful. Runner modes are integration lanes: use `fast`
for cross-route or shared-infrastructure changes, uncertain impact, or requested
integration closeout; `gui` for broad multi-surface QML work; `slow` for
performance closeout; and `full` for shell-wide composition, release confidence,
or explicit requests.

| Mode | Command | Coverage | Notes |
|---|---|---|---|
| `fast` | `./venv/Scripts/python.exe scripts/run_verification.py --mode fast` | Broad non-GUI integration lane for tests that are not marked `gui` or `slow` | Runs `fast.pytest` first with `pytest -o faulthandler_timeout=120 -m "not gui and not slow"` and ignores the shell-backed modules plus `tests/test_shell_isolation_phase.py`; when `pytest-xdist` is importable in the project venv, resolves workers as `psutil.cpu_count(logical=True)` else `os.cpu_count()` else `1`, then passes `-n <resolved_count> --dist load` while deselecting known xdist-sensitive fast targets. Then runs `fast.serial.pytest` for those targets without xdist |
| `gui` | `./venv/Scripts/python.exe scripts/run_verification.py --mode gui` | Authoritative pure-QML QuickTest directory, parallel QML-heavy pytest slice marked `gui and not slow`, then its proven-contention serial targets | Runs `gui.qml_quick` before pytest with offscreen/Basic controls and zero input delays. `gui.pytest` uses `-o faulthandler_timeout=300`; resolves workers as `psutil.cpu_count(logical=True)` else `os.cpu_count()` else `1`, caps that value at `6`, and passes `-n <gui_resolved_count> --dist load` when `pytest-xdist` is available. `gui.serial.pytest` then runs one DOCX selector and `tests/test_viewer_surface_contract.py` outside xdist. Otherwise it prints the serial fallback notice. Both slices ignore the shell-backed modules plus `tests/test_shell_isolation_phase.py` |
| `slow` | `./venv/Scripts/python.exe scripts/run_verification.py --mode slow` | Slow pytest slice marked `slow` | Serial by design, uses `pytest -o faulthandler_timeout=600 -m slow`, and still ignores the shell-backed modules plus `tests/test_shell_isolation_phase.py` |
| `full` | `./venv/Scripts/python.exe scripts/run_verification.py --mode full` | Runs `fast.pytest`, `fast.serial.pytest`, `gui.qml_quick`, `gui.pytest`, `gui.serial.pytest`, and `slow` first, then the dedicated fresh-process shell-isolation phase | Use `--dry-run` to inspect the exact subprocess commands before execution; with `pytest-xdist`, the current exact 49-target shell catalog runs through `./venv/Scripts/python.exe -m pytest -o faulthandler_timeout=330 --ignore=venv tests/test_shell_isolation_phase.py -q -n 4 --dist load`, with a 360-second hard limit on each child; without xdist, the same phase runs serially |

## Locked Shell Isolation Rules

- The non-shell pytest phases always pass
  `--ignore=tests/test_main_window_shell.py`,
  `--ignore=tests/main_window_shell/shell_basics_and_search.py`,
  `--ignore=tests/test_script_editor_dock.py`,
  `--ignore=tests/test_shell_run_controller.py`,
  `--ignore=tests/test_shell_project_session_controller.py`,
  `--ignore=tests/test_shell_window_lifecycle_isolated.py`, and
  `--ignore=tests/test_shell_isolation_phase.py`.
- The `fast.pytest` xdist phase additionally deselects
  `tests/test_execution_client.py::ProcessExecutionClientTests` and
  `tests/test_workspace_library_controller_unit.py::WorkspaceLibraryControllerCoreOpsTests::test_paste_nodes_from_clipboard_is_noop_when_clipboard_is_missing`;
  `fast.serial.pytest` runs those same targets serially afterward.
- The dedicated shell-isolation phase is
  `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest -o faulthandler_timeout=330 --ignore=venv tests/test_shell_isolation_phase.py -q -n 4 --dist load`
  when `pytest-xdist` is available. The manifest caps the outer phase at four
  workers even when the host worker resolver reports a larger value.
- For traceability, the generic command-rendering template remains
  `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest -o faulthandler_timeout=330 --ignore=venv tests/test_shell_isolation_phase.py -q -n <resolved_count> --dist load`.
  The uncapped candidate resolves through `psutil.cpu_count(logical=True)`,
  else `os.cpu_count()`, else `1`; for this shell phase, `<resolved_count>` is
  then clamped to the manifest-owned maximum of four.
- If `pytest-xdist` is unavailable, `scripts/run_verification.py` falls back to
  serial pytest for the dedicated shell-isolation phase and preserves the same
  fresh-process child-command model.
- Each `tests/test_shell_isolation_phase.py` target launches its own child
  process through `tests/shell_isolation_runtime.py`, so QML shell state is
  not shared across catalog entries even when xdist schedules targets in
  parallel. `scripts/verification_manifest.py` owns that contract through
  `SHELL_ISOLATION_SPEC` and `SHELL_ISOLATION_CATALOG_SPECS`. The final catalog
  has 47 targets; the phase's 330-second pytest faulthandler watchdog provides
  diagnostics before each child's manifest-owned 360-second hard timeout.
- The direct module-level shell commands remain supported for focused manual
  reruns, but they are not the documented `full` workflow:
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.test_main_window_shell -v`
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.main_window_shell.shell_basics_and_search -v`
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.test_script_editor_dock -v`
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.test_shell_run_controller -v`
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.test_shell_project_session_controller -v`
  - `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m unittest tests.test_shell_window_lifecycle_isolated -v`
- Do not replace the dedicated shell-isolation phase with `unittest discover`,
  shared `ShellWindow()` reuse, or shell coverage folded back into the earlier
  pytest phases.

## Baseline Timings From The Packet Manifest

| Baseline Measurement | Recorded Value | Why It Matters |
|---|---|---|
| `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest -q --durations=30` | about `193.88s` for `450` collected tests | Establishes the pre-packet baseline that motivated the split verification workflow |
| `tests/test_main_window_shell.py` | about `100.12s` | Shows why shell-backed coverage stayed out of the default pytest phases before the dedicated shell-isolation phase was introduced |
| `tests/test_shell_project_session_controller.py` | about `25.11s` | Confirms that another shell-backed module was expensive enough to justify a separate shell-isolation phase |
| Fresh `ShellWindow()` construction | about `870ms` | Startup cost is dominated by QML shell loading through `QQuickWidget.setSource(...)`, not registry bootstrap |

## Published Shell-Tail Benchmark Evidence

| Workflow Shape | Recorded Result | Notes |
|---|---|---|
| Old sequential shell-tail baseline | `77.776s` mean across `3` reps | Retained as historical traceability only; it is not comparable to the final 47-target catalog and is not used for a speed claim |
| Dedicated shell-isolation phase | `54 passed in 831.67s` | First of three current four-worker correctness samples; all samples are recorded below |

The final catalog contains 47 child-process targets. Seven phase-owned
catalog/ownership tests make the complete phase result 54 pytest passes. All
three final four-worker samples passed:

| Sample | Outer wall time | Complete result | Slowest target sample |
|---:|---:|---|---:|
| 1 | `831.67s` | `54 passed` | `179.39s` |
| 2 | `773.94s` | `54 passed` | `158.35s` |
| 3 | `839.30s` | `54 passed` | `250.08s` |

P06 deadline acceptance is **FAILED**. Applying the deadline formula to the
slowest `250.08s` target produces a rounded `510s` requirement, which exceeds
the allowed `360s` maximum. All three phases nevertheless completed under the
bootstrap-owned 360-second child hard cap. No rerun or target split was
performed because the user stopped further broad evidence runs. These samples
prove correctness of the bounded four-worker phase, not a stable performance
improvement; no shell speedup percentage is accepted or published.

## Current Environment Notes

- Run the workflow with the project-local interpreter:
  `./venv/Scripts/python.exe`. The repo uses a Windows-style virtualenv layout
  even when opened from `bash`.
- `scripts/run_verification.py` applies `QT_QPA_PLATFORM=offscreen` to its
  child verification commands, so the top-level runner invocations do not need
  extra environment variables.
- The `gui.qml_quick` phase also applies `QT_QUICK_CONTROLS_STYLE=Basic` and
  runs `tests/qml_quick` with zero event, key, and mouse delays before Python
  GUI pytest. It is required in `gui` and `full`; `fast` and `slow` never
  discover or require the external Qt SDK.
- The final QML probe-worker hard deadline is 60 seconds. Focused GUI
  subprocess helpers use a 180-second hard deadline and normalize partial
  output when reporting a timeout.
- The runner resolves `qmltestrunner` from explicit `QT_ROOT/bin` before
  `PATH`, probes the sibling `qtpaths6` or `qtpaths`, and requires the SDK and
  PyQt Qt major/minor versions to match. Patch drift is accepted. Missing or
  incompatible tooling is a hard error for real `gui`/`full` runs, while
  `--dry-run` prints a placeholder command and setup notice.
- No tracked CI workflow exists in this repository. Any external job invoking
  `gui` or `full` must provision the matching Qt Quick Test SDK and expose it
  through `QT_ROOT` or `PATH`.
- `scripts/run_verification.py` applies phase-specific pytest faulthandler
  watchdogs through `-o faulthandler_timeout=...`: `fast=120`, `gui=300`,
  `slow=600`, and shell isolation `330`. The pytest watchdog is per test item
  and xdist workers inherit it; shell child processes have a separate
  360-second hard limit.
- `scripts/run_verification.py` now preflights the project venv's direct
  `pytest` dependencies before phase execution. If a partial install leaves
  `iniconfig`, `exceptiongroup`, or another direct dependency missing, the
  runner installs the missing package into `venv` and retries before it hands
  off to the manifest-owned pytest command.
- `pytest-xdist` is declared in `pyproject.toml` and `requirements.txt`. The
  recorded closeout host had 12 logical processors across 8 physical cores,
  31.75 GB total memory with 14.54 GB available, 700 processes including 216
  Python processes, PyQt/Qt `6.11.0`, and Qt SDK `6.11.1`. The general resolver
  uses `psutil.cpu_count(logical=True)`, else `os.cpu_count()`, else `1`, and
  therefore reported 12 workers here, while the manifest kept GUI at six and
  the outer shell-isolation phase at four. If the plugin is unavailable,
  `scripts/run_verification.py` falls back to serial pytest and prints the
  runner notice.

## Companion Proof Audit

- `./venv/Scripts/python.exe scripts/check_traceability.py` validates the
  packet-owned proof layer in `README.md`, `ARCHITECTURE.md`,
  `docs/GETTING_STARTED.md`, `docs/PACKAGING_WINDOWS.md`,
  `docs/PILOT_RUNBOOK.md`, `docs/specs/INDEX.md`,
  `docs/specs/requirements/TRACEABILITY_MATRIX.md`, and the packet-owned docs
  under `docs/specs/perf/`.
- `./venv/Scripts/python.exe scripts/check_markdown_links.py` validates the
  local Markdown links inside the same active canonical docs.
- The current public closeout evidence for those proof layers is summarized in
  `README.md`, `ARCHITECTURE.md`, `docs/specs/INDEX.md`,
  `docs/specs/perf/ARCHITECTURE_MAINTAINABILITY_REFACTOR_QA_MATRIX.md`, and
  `docs/specs/requirements/TRACEABILITY_MATRIX.md`.
- Run both doc guards after editing verification docs, archived QA evidence
  summaries, release docs, or packet-owned traceability references.

## 2026-07-22 Authoritative Qt Quick Test Rollout

- Runner: `C:\Qt\6.11.1\msvc2022_64\bin\qmltestrunner.exe` using QtTest and
  Qt `6.11.1`; project PyQt runtime: Qt `6.11.0`. The accepted compatibility
  rule requires matching major/minor versions and permits patch-only drift.
- Command shape: `QT_QPA_PLATFORM=offscreen`,
  `QT_QUICK_CONTROLS_STYLE=Basic`, then
  `qmltestrunner.exe -input tests/qml_quick -eventdelay 0 -keydelay 0
  -mousedelay 0 -o -,txt`.
- Acceptance was evaluated independently for each migration group: equivalent
  assertions, three consecutive passing cold-process runs, no new warnings,
  and a QuickTest median no greater than 50% of its Python baseline.

| Migration group | Python serial wall-time samples | Python median | QuickTest serial wall-time samples | QuickTest median | Speedup | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Original ten `GraphNodeHost` probes | `9.4286121s`, `12.8468803s`, `13.5866017s` | `12.847s` | `0.5084168s`, `0.7319858s`, `0.8713773s` | `0.732s` | `17.55x` | accepted |
| Nine graph-surface control probes | `41.243s`, `22.488s`, `30.195s` | `30.195s` | `0.4832829s`, `0.4987064s`, `0.7401219s` | `0.4987064s` | `60.55x` | accepted |
| Eight flowchart-host probes | `37.541527s`, `61.420329s`, `56.061706s` | `56.061706s` | `1.212871s`, `1.539805s`, `1.838391s` | `1.539805s` | `36.41x` | accepted |

- In the original rollout snapshot, the host file reported `12` passes per
  benchmark run, the controls file reported `11`, and the selected flowchart
  group reported `10`; these totals include each `TestCase` init/cleanup pair.
  The complete two-file directory then reported `31` passes for `27` test
  functions plus four lifecycle functions. The current post-P03 inventory is
  recorded below.
- The original and flowchart runs emitted only the known `ManagedToolTip`
  accessibility and missing-font-directory warnings. The controls runs emitted
  only the known missing-font-directory warning. No migration introduced a new
  warning family.
- The flowchart Python baseline was measured after repairing stale test-only
  `surface_spec`/required fixture data. The QML rollout also retained the small
  Repeater/path-editor teardown guards needed for deterministic object cleanup.
- `tests/qml_quick/tst_graph_node_host.qml` now owns the accepted host and
  flowchart behavior; `tests/qml_quick/tst_graph_surface_controls.qml` owns the
  accepted pure-QML control behavior. Python remains authoritative for bridges,
  graph models, registries, media/providers, platform behavior, static source
  contracts, and QML-worker lifecycle/crash recovery.
- The accepted directory is now the required `gui.qml_quick` phase before
  `gui.pytest`, which is followed by `gui.serial.pytest`, in both `gui` and
  `full`. The serial phase owns exactly one DOCX selector and
  `tests/test_viewer_surface_contract.py`; graph-surface coverage remains in the
  parallel GUI/QML lanes. No Python wrapper, CMake target, custom C++ harness,
  dependency, or separate verification mode was added.
- Final real GUI closeout passed on `2026-07-23` in
  `artifacts/verification_logs/20260723_015608`: native `gui.qml_quick` exited
  successfully, six-worker `gui.pytest` passed `669` tests with `1` skipped in
  `407.47s`, and `gui.serial.pytest` passed `20` tests in `26.21s`. The native
  runner's summarized log is empty on this Windows host, so the exact
  then-expected `31`-pass count comes from the accepted per-file runs and static
  directory inventory rather than that final log.

## 2026-07-23 P03 Candidate Migration Baselines

The P03 baseline used Windows `10.0.26200`, Python `3.10.0`, PyQt/Qt `6.11.0`,
pytest `9.0.3`, and repository revision
`d3ee63beff959360902a1b57f2f9aaecdaabace2`. Every sample launched a fresh
project-venv Python process with `QT_QPA_PLATFORM=offscreen`,
`QT_QUICK_CONTROLS_STYLE=Basic`, `--ignore=venv -q -n 0`, and no other
repository test process active. The values below are outer `Measure-Command`
wall times, not pytest's internal elapsed time.

| Candidate migration group | Assertions moved | Python baseline selector | Python wall-time samples | Python median | Maximum accepted QuickTest median |
| --- | ---: | --- | --- | ---: | ---: |
| Node floating toolbar | `17` | `tests/test_graph_surface_input_controls.py::GraphNodeFloatingToolbarProbeTests` | `13.7672293s`, `14.7639750s`, `13.9543547s` | `13.9543547s` | `6.9771774s` |
| Selection envelope | `5` | `tests/test_graph_surface_input_controls.py::GraphSelectionEnvelopeOverlayProbeTests` | measured together with the floating-toolbar selector above | included above | included above |
| Planning and annotation hosts | `3` | `tests/test_planning_annotation_catalog.py::PlanningAnnotationSurfaceQmlTests` | `8.9078755s`, `8.3044472s`, `11.3103963s` | `8.9078755s` | `4.4539378s` |
| Library flowchart visual | `1` | `tests/test_flowchart_surfaces.py::FlowchartSurfaceQmlTests::test_library_flowchart_visual_fits_multi_document_to_metadata_aspect_ratio` | `5.1930506s`, `5.1363433s`, `4.8687146s` | `5.1363433s` | `2.5681717s` |
| Group backdrop hosts | `4` | four former `GroupBackdropSurfaceQmlTests` node IDs | `5.3758784s`, `6.2520628s`, `8.3863759s` | `6.2520628s` | `3.1260314s` |

- The controls threshold applies to the combined `17 + 5` selector because
  both classes shared the same cold-process benchmark command.
- The four Group baseline node IDs were
  `test_graph_node_host_loads_group_backdrop_without_body_or_shadow`,
  `test_selected_untitled_group_shows_prompt_and_edits_an_empty_title`,
  `test_collapsed_group_backdrop_ignores_node_icon_source_for_title_contract`,
  and
  `test_collapsed_group_backdrop_width_fits_long_title_with_stale_metrics`.
- All Python baseline selectors passed in all three repetitions. Their
  successful child-probe output was suppressed by the wrappers, so the absence
  of a warning section is not treated as proof that those runs were
  warning-free.
- P03 moves exactly `30` pure-QML assertions into the existing QuickTest
  files: `22` into `tst_graph_surface_controls.qml` and `8` into
  `tst_graph_node_host.qml`. It removes the superseded per-test Python launch
  wrappers without adding a harness, module, dependency, or verification mode.
- Python remains authoritative for bridge/model/provider and source contracts.
  In particular, all seven Group catalogue/model/serialization tests remain in
  `tests/test_group_backdrop_contracts.py`; planning catalogue/metric facts and
  flowchart geometry/drop-preview integration also remain in Python.
- The current static QuickTest inventory is `60` test functions across the two
  files, expected to report `64` passes including the four `TestCase`
  init/cleanup functions. Focused correctness passed `36` controls results,
  `28` node-host results, and `44` retained Python tests during implementation.
- P06-A records the candidate QuickTest cold-process timing samples below. All
  four median gates and warning classifications pass after the Group test
  context supplies the application-owned `uiIcons.sourceSized(...)` dependency.

### P06-A Uncontaminated QuickTest Acceptance Timing

- Runner: `C:\Qt\6.11.1\msvc2022_64\bin\qmltestrunner.exe`, QtTest/Qt
  `6.11.1`, against the project PyQt Qt `6.11.0` runtime.
- Environment: `QT_QPA_PLATFORM=offscreen`,
  `QT_QUICK_CONTROLS_STYLE=Basic`, and zero event/key/mouse delays.
- Before each recorded sample, the process table contained no other
  `EA_Node_Editor` pytest, `qmltestrunner`, or verification-runner process.
- Each sample launched a fresh native process. `qmltestrunner` received
  explicit class-qualified positional filters in the form
  `TestCaseName::test_function`; no unselected function in the owning file ran.
- Command shape:
  `qmltestrunner.exe -input <owning-file> -eventdelay 0 -keydelay 0
  -mousedelay 0 -o <temporary-log>,txt <class-qualified-filter>...`.
  The runner's native temporary text log was read after process exit and
  deleted immediately. This was necessary because this Windows runner bypassed
  PowerShell capture when `-o -,txt` targeted stdout.
- Two pre-recording filter/logger diagnostics are excluded from the acceptance
  samples: the unqualified 22-name controls filter was rejected before any test
  ran (`exit 22`, zero output), and a class-qualified stdout-logger launch
  exited successfully in `1.4152815s` but produced no auditable pass/warning
  stream through PowerShell. The table contains exactly the subsequent three
  native-text-log acceptance processes per group.
- The controls filter list was the explicit `GraphSurfaceControls::` prefix
  applied to all `17` `test_floating_toolbar_*` functions and all `5`
  `test_selection_envelope_*` functions. The other explicit sets were the
  three planning/annotation names, the one library-flowchart name, and the four
  Group names recorded in the P03 baseline section above, all with the
  `GraphNodeHost::` prefix.
- Process wall time is the acceptance measurement. The selected-function count
  excludes `initTestCase` and `cleanupTestCase`; those unavoidable lifecycle
  lines remain visible separately in each process log and are not reported as
  migrated tests.

| Migration group | Candidate process wall samples | Candidate median | Recorded 50% Python cap | Median versus cap | Per-run pass output | Timing classification |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `22` controls | `1.2372896s`, `1.5565145s`, `1.7618653s` | `1.5565145s` | `6.9771774s` | `5.4206629s` below; `22.31%` of cap | `22` selected plus `2` lifecycle; totals `24 passed`, `0 failed/skipped/blacklisted` in every run (`1135ms`, `1416ms`, `1514ms` internal) | pass |
| `3` planning/annotation | `0.3368323s`, `0.1992465s`, `0.2957109s` | `0.2957109s` | `4.4539378s` | `4.1582269s` below; `6.64%` of cap | `3` selected plus `2` lifecycle; totals `5 passed`, `0 failed/skipped/blacklisted` in every run (`166ms`, `98ms`, `167ms` internal) | pass |
| `1` library flowchart | `0.2476822s`, `0.1908591s`, `0.3030865s` | `0.2476822s` | `2.5681717s` | `2.3204895s` below; `9.64%` of cap | `1` selected plus `2` lifecycle; totals `3 passed`, `0 failed/skipped/blacklisted` in every run (`18ms`, `22ms`, `53ms` internal) | pass |
| `4` Group backdrop | `1.0501404s`, `1.1047080s`, `1.1991643s` | `1.1047080s` | `3.1260314s` | `2.0213234s` below; `35.34%` of cap | `4` selected plus `2` lifecycle; totals `6 passed`, `0 failed/skipped/blacklisted` in every run (`613ms`, `681ms`, `780ms` internal) | pass |

Warning output was stable across all three runs of each group:

| Migration group | Warnings per run | Classification |
| --- | ---: | --- |
| `22` controls | `1` | Known SDK warning: `QFontDatabase: Cannot find font directory C:/Qt/6.11.1/msvc2022_64/lib/fonts.` |
| `3` planning/annotation | `4` | The same known SDK font warning plus `3` previously known `ManagedToolTip` accessibility warnings from `GraphNodeHeaderLayer.qml:546`. |
| `1` library flowchart | `1` | Known SDK font warning only. |
| `4` Group backdrop | `6` | The known SDK font warning plus `5` previously known `ManagedToolTip` accessibility warnings. The earlier two `ReferenceError: uiIcons is not defined` warnings are gone after the QuickTest context added the minimal existing-style `sourceSized(...)` stub required by `GraphNodeHeaderLayer.qml:155`. |

The post-fix Group samples above supersede its earlier
`1.0078494s`/`1.1472115s`/`1.0449649s` timing set because that set still emitted
the unresolved `uiIcons` warning family. All four process-wall timing gates now
pass with only the already documented SDK-font and `ManagedToolTip` warning
families, so the P03/P06-A migration is warning-clean under the recorded
acceptance rules.

## 2026-07-23 P04 Flowchart Drop-Preview Worker Migration

P04 kept both full-`GraphCanvas` drop-preview probes in Python while replacing
their duplicate raw `subprocess.run([sys.executable, "-c", ...])` launchers
with the existing crash-isolated `run_qml_probe` worker. Each request still
receives fresh script globals and a fresh `QQmlEngine`; after its assertions it
explicitly detaches and deferred-deletes the canvas, closes/deletes its window
when one exists, then deferred-deletes the engine.

The raw and candidate measurements used the same P03 host environment and
fresh-process serial command shape described above. Before every sample, the
process table contained no other `EA_Node_Editor` pytest, `qmltestrunner`, or
verification-runner process.

| Probe node ID | Raw subprocess wall samples | Raw median | Shared-worker wall samples | Shared-worker median | Median change | Result |
| --- | --- | ---: | --- | ---: | ---: | --- |
| `tests/test_flowchart_surfaces.py::FlowchartSurfaceQmlTests::test_graph_canvas_drop_preview_reuses_flowchart_silhouette_component` | `4.8696255s`, `9.8562295s`, `12.4178835s` | `9.8562295s` | `6.4147061s`, `8.2536998s`, `7.1439379s` | `7.1439379s` | `2.7122916s` lower (`27.52%`, `1.38x`) | accepted |
| `tests/test_flowchart_visual_polish.py::FlowchartVisualPolishQmlTests::test_flowchart_drop_preview_matches_family_and_hides_port_labels` | `9.7720597s`, `7.3997232s`, `11.8590735s` | `9.7720597s` | `11.9065910s`, `8.8971980s`, `7.8778580s` | `8.8971980s` | `0.8748617s` lower (`8.95%`, `1.10x`) | accepted |

- Both acceptance medians are strictly below their own raw-launch baseline.
  All twelve timing invocations passed.
- A direct fresh-process invocation ran the two exact flowchart test methods in
  order, captured the existing `_worker_process` object and PID after the first,
  and asserted the same object and PID after the second. It printed
  `P04_REUSE_PROOF|same_object=True|pid=37028|alive=True`; the PID is
  run-specific. No production instrumentation was added.
- A separate serial pytest invocation selected both flowchart node IDs followed
  by
  `GraphSurfaceProbeRunnerTests::test_worker_reuse_and_probe_state_reset`;
  it passed `3` tests in `3.98s`. The runner-owned test independently captures
  `_worker_process` after its first request and asserts object identity after
  its second request.
- The complete `tests/test_graph_surface_probe_runner.py` lifecycle,
  state-reset, timeout, worker-death, cleanup-death, diagnostic-log, and restart
  suite passed `7` tests in `5.40s`.
- No helper module, harness, production hook, dependency, or verification mode
  was added. PDF, flow-edge, graph-track, media, and viewer coverage was not
  changed.

## 2026-07-24 P05/P06 Final Integration Closeout

P05 finalized the bounded failure-diagnostic policy: QML probe workers have a
60-second hard deadline, isolated GUI subprocesses have a 180-second hard
deadline, and shell targets pair a 330-second pytest faulthandler diagnostic
with a 360-second child-process hard limit. The outer shell phase is capped at
four workers for its 47-target catalog. Focused timeout-reporting, worker
restart, shell-command ownership, and catalog-completeness checks passed after
those changes.

P06 shell deadline acceptance failed because the final `250.08s` slowest-target
sample computes to a rounded `510s` deadline, above the `360s` maximum. All
three complete phases still passed under the bootstrap hard cap; no rerun or
target split followed because the user stopped further broad evidence runs.

P06 also did not produce a valid GUI aggregate speed comparison:

| Observation | QuickTest | GUI pytest | Outer wall time | Classification |
|---|---|---|---:|---|
| Detached baseline at `d3ee63beff959360902a1b57f2f9aaecdaabace2` | passed | `2 failed, 667 passed, 1 skipped, 48 errors`; the error fanout came from missing local result fixtures | `542.324s` | invalid/inconclusive baseline |
| Candidate attempt 1 | not accepted as an aggregate | `5 failed` | `551.267s` | incomplete |
| Candidate attempt 2 | not accepted as an aggregate | `4 failed` | `588.854s` | incomplete |
| Candidate attempt 3 | QuickTest reached pass | `1 failed` | `652.155s` | incomplete |

- Because the detached baseline was invalid, and each candidate observation
  still contained failures, these one-off wall times do not support a median,
  percentage improvement, or regression percentage.
- Focused fixes resolved the candidate-owned failures they targeted, and the
  current complete QuickTest phase passed without introducing a new warning
  family beyond the already recorded SDK-font and `ManagedToolTip` warnings.
- The final broad GUI rerun was interrupted/skipped at the user's request after
  the focused fixes. The aggregate GUI workflow is therefore not claimed
  passing, and no aggregate speedup is claimed.

## Current Baseline Status

- `./venv/Scripts/python.exe -m pytest tests/test_serializer.py -k passive_image_panel_properties_and_size -q`
  passed on `2026-03-18`, so the earlier passive image-panel serializer caveat
  is retired.
- The latest broad `fast` closeout attempt on `2026-07-23` was inconclusive: it
  reached `96%`, emitted a faulthandler diagnostic from the unrelated
  `test_group_backdrop_contracts` QML worker, and did not terminate after its
  remaining workers completed. No task-owned assertion failure was reported,
  but the aggregate `fast` workflow is not claimed green from that run.
- The GUI aggregate remains invalid/inconclusive for the P06 reasons above.
  This document plus `docs/specs/requirements/TRACEABILITY_MATRIX.md` carry the
  current public closeout evidence and residual-risk summary. Do not claim the
  aggregate workflow green or publish a speed percentage without a clean,
  comparable rerun.
- P06 shell deadline acceptance is failed, despite all three final phases
  completing successfully under the existing 360-second bootstrap hard cap.
- The former sentence `No known out-of-scope verification baseline failures remain`
  is superseded by the missing-local-result-fixture baseline recorded
  above; it is retained here only as a traceability marker, not a current
  acceptance claim.

## 2026-03-18 Verification Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe scripts/run_verification.py --mode full --dry-run` | PASS | The historical command-shape check passed; its old shell arguments are superseded by the current four-worker, 330-second diagnostic, and 360-second hard-limit contract above. |
| `QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest -o faulthandler_timeout=330 --ignore=venv tests/test_shell_isolation_phase.py -q -n 4 --dist load` | PASS | The retained command identity now shows the current arguments. Its three 54-pass results are dated 2026-07-24 in the final evidence above, not 2026-03-18. |
| `./venv/Scripts/python.exe -m pytest tests/test_serializer.py -k passive_image_panel_properties_and_size -q` | PASS | The previous serializer spot-check caveat no longer reproduces in the current project venv |

## 2026-03-20 ARCH_FIFTH_PASS Closeout Results

| Command | Result | Notes |
|---|---|---|
| `./venv/Scripts/python.exe scripts/check_traceability.py` | PASS | The packet-owned proof audit passed after the spec index links, architecture snapshot, traceability matrix anchors, and fifth-pass closeout matrix were refreshed. |
| `./venv/Scripts/python.exe scripts/run_verification.py --mode fast --dry-run` | PASS | The dry-run output kept the manifest-owned `fast` workflow, ignore list, and worker-resolution behavior aligned with the refreshed proof docs. |
