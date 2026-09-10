# Signal Plot scientific inputs: integration evidence

This records the [scientific-input implementation](../../PLAN_SIGNAL_PLOT_SCIENTIFIC_INPUTS.md)
and [usage contract](../../SIGNAL_PLOT_GUIDE.md). Measurements are local regression
evidence, not a display-attached release acceptance or a universal performance
budget.

## Workload and method

`scripts/benchmark_signal_plot.py --scientific --rows 2000000` creates one
Python Script connected directly to Signal Plot. It runs both exact ndarray and
DataFrame sources through ProcessExecutionClient and CorexRuntime, twice each.
Each source contains 2,000,000 rows by four float64 columns: sample index, sine,
cosine and ramp. Automatic mapping produces three Y traces with explicit X.

Elapsed time covers dispatch, source execution, scientific transport and PNG
rendering through terminal delivery (including backend cleanup for CorexRuntime).
Host registry/model construction and post-run full-source comparisons are outside
the timer. The memory sampler records the highest observed sum of parent and
recursive child RSS at 10 ms intervals; this includes retained runtime state and
may count shared pages more than once. It is neither an allocation delta nor an
exact unsampled operating-system peak.

Each run compares every source sample in all four columns against its expected
value after plotting. Renderer warnings confirm each original 2,000,000-point
trace is reduced to at most 4000 points; focused renderer tests additionally
capture the actual XY arguments, including gap preservation and zero-full mode.
The old Matplotlib/XY comparison explicitly uses full resolution on both sides.

## Measurements

Measured on 2026-09-06 with Windows build 26200, Python 3.11.6, NumPy 2.4.6,
pandas 3.0.5 and psutil 7.2.2. The host has 34,088,108,032 bytes of RAM and an
Intel Family 6 Model 154 CPU. Times are single initial/repeated observations,
not p95 estimates.

| Route | Source | Initial seconds | Repeat seconds | Initial peak RSS bytes | Repeat peak RSS bytes |
| --- | --- | --- | --- | --- | --- |
| ProcessExecutionClient | ndarray | 6.217 | 3.589 | 1,170,518,016 | 1,229,111,296 |
| ProcessExecutionClient | DataFrame | 6.736 | 3.956 | 1,126,404,096 | 1,199,607,808 |
| CorexRuntime | ndarray | 12.868 | 7.333 | 1,471,574,016 | 1,683,062,784 |
| CorexRuntime | DataFrame | 12.118 | 7.830 | 1,436,471,296 | 1,648,005,120 |

All eight runs passed full sample comparisons and returned 600-by-400 ImageValues.
The three rendered traces contained **3997, 3996 and 3998 points** in every run.
Direct process runs reported `legacy_direct_run`; CorexRuntime reported the
script implementation-identity reason and the plot's initial
`execution_generation_unavailable` / repeated `upstream_recompute_required`.
Faster repeated runs still recomputed both script and plot.

## Reuse policy and exact budget proof

Python Script retains its existing `solution_reuse_scope='never'` classification.
Its factory-based entry currently fails the earlier implementation-identity
check with `implementation_identity_unavailable`; its dependent Signal Plot
reports `upstream_recompute_required`. Both nodes recompute on repeated runs.
The direct NPY reference pipeline separately proves complete authored row
selection and repeated images; its source currently reports `no_reusable_record`.
Neither policy is weakened to make a benchmark reuse its results.

The test-only trusted session producer from `tests/test_solution_store_session.py`
provides the separate cache proof. The small 32-by-4 immutable array is retained
and accepted with `reusable_record_accepted`. The 2,000,000-by-4 array is a valid,
reuse-eligible session record, but preparation rejects its encoded payload with
exactly `reuse_payload_budget_exceeded` and schedules execution. The unchanged
budget is 67,108,864 bytes; 64,000,000 raw float64 bytes require over 85,333,333
base64 bytes before envelope metadata. No malformed-payload or
`accepted_output_invalid` result counts as passing this check.

The recorded small and large preparation checks took 0.317 s and 4.830 s,
respectively; sampled combined RSS was 371,671,040 and 1,141,862,400 bytes. Both
checks passed, including reuse-eligible retained records and a completed repeat
fixture settlement with all source values intact. The fixture supplies trusted
settlement events; the separate eight-run workload above proves real execution
and transport.

## Verification outcome

The 21 scientific integration tests passed, covering both process/runtime native
routes, a generated CSV/NumPy/pandas project with Media Panels, an NPY reference
pipeline, concrete/Any/reference connection legality, unrelated-type rejection,
and small/oversized trusted reuse. All eight catalog checks passed after the
Signal Plot migration-inventory row was updated with the six new controls.

Final `fast.pytest`: **4678 passed, 3 skipped, 3 failed in 348.74 s**. All three
failures were independently reproduced with clean Python imports on baseline
commit `56c4d0b2ffc92b4b9e48d5fb1167eacb665b1e54`:

| Existing failing check | Baseline failure |
| --- | --- |
| `test_graph_node_port_context_menu_is_the_direct_menu_owner_without_growth` | Expects one Menu; existing owner is ShellContextPopup |
| `test_live_repository_qml_routes_have_exact_bounded_owners` | Expects 175 entries; the baseline index already has 176 |
| `test_dynamic_port_graph_payload_carries_port_flow_state` | Fixture omits `dynamic_names` before its custom resolver reads it |

These tests and their production owners were left unchanged. The full fast
command therefore still exits nonzero; this is not a green whole-repository
acceptance claim. Baseline evidence is retained locally in
`artifacts/verification_logs/signal_plot_scientific/baseline.xml`.

The canonical `fast.serial.pytest` phase was executed explicitly because the
parallel failure stops the normal runner before that phase: **220 passed in
98.32 s**, including scientific process/external transport. That module now
follows the existing manifest-owned serial route used by ProcessClientTests;
it remains part of fast/full coverage with unchanged timeouts and success checks.

Before that route adoption, a parallel run had six failures: the three baseline
checks, a scientific external-start protocol rejection, and visual/worker
lifecycle timeouts. The latter two passed focused checks and the final parallel
run. The scientific startup rejection's precise cause was not established;
98 agreement/reuse/integration tests, eight parallel worker cases, and the
complete serial phase passed. No timeout relaxation or production lifecycle
refactor was used to make those checks pass.

The integration sweep also exposed eager traversal of hostile container
subclasses at native script boundaries. Conversion now leaves those objects to
the original consumer validators; 60 scientific/spatial/transform checks passed.
The new QCore/process/external probes passed with deliberately contaminated
Python environment variables using test-only clean environment setup. Exact
contract/navigation checks passed (8 tests, 37 subtests), documentation/verification
hygiene passed (154 tests, 19 subtests), and the final manifest routing checks
passed (42 tests, 4 subtests). Agent-map, traceability, Markdown-link and scoped
Ruff checks passed. Independent implementation and follow-up reviews found no
blocking issues.

## Reproduce

Run from the repository root with the project interpreter:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_signal_plot_scientific_example.py
.\venv\Scripts\python.exe -m pytest tests/test_signal_plot_scientific_integration.py -n 0 -m "not slow" -q
.\venv\Scripts\python.exe -m pytest tests/test_signal_plot_scientific_integration.py -n 0 -k budget -s -q
.\venv\Scripts\python.exe .\scripts\benchmark_signal_plot.py --scientific --rows 2000000
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
.\venv\Scripts\python.exe -m pytest tests/test_run_verification.py tests/test_traceability_checker.py tests/test_markdown_hygiene.py -n 0 -q
```

If the baseline parallel failures still stop `fast`, execute the same canonical
serial phase explicitly without changing its target list:

```powershell
.\venv\Scripts\python.exe -c "from pathlib import Path; from scripts.run_verification import build_commands, run_command_summarized; phase = next(c for c in build_commands('fast') if c.phase == 'fast.serial.pytest'); raise SystemExit(run_command_summarized(phase, log_path=Path('artifacts/verification_logs/signal_plot_scientific/fast_serial.txt'), failure_tail_lines=50))"
```

Full raw logs stay under the ignored `artifacts/verification_logs/` root. The
generated `.cxproj` and adjacent `.data` folder are local runnable artifacts;
the maintained source is `scripts/generate_signal_plot_scientific_example.py`.

## Scope and limitations

The codec bounds are 256 MiB decoded content per scientific value and 512 MiB
per operation. Existing 64 MiB accepted-reuse and source materialization limits
remain independent. Scientific results are durable-ineligible. Arbitrary native
classes, out-of-RAM transport, categorical axes and a new interactive chart
surface are outside this change. The historical catalog JSON/hash is untouched;
the effective fixture supplies the missing optional `property_editor=None`
field for old dynamic groups without replacing present values.
