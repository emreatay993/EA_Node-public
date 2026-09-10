# Signal Plot scientific inputs

## Approved outcome

Direct Tabular Data Input and Python Script connections to Signal Plot, native
NumPy/pandas interfaces in scripts, and execution-owned normalization into
explicit X/Y traces. COREX owns immutable array/table values internally and
automatically converts them to isolated native NumPy/pandas objects at script
boundaries. Built-in readers share immutable values; script outputs publish new
snapshots.

| Input | Automatic interpretation |
| --- | --- |
| Numeric list, 1D ndarray, pandas Series | Y against sample index |
| One numeric table column | Y against sample index |
| Multiple matrix/table columns | First numeric/datetime column is X; remaining numeric columns are Y |
| Numeric DataTree branches | One independent indexed signal per branch |

Skip text/Boolean columns in automatic mapping, preserve row order, derive labels
from column names, and permit explicit X/Y selection and sample-index override.
Typed datetime X is supported, timezone-aware axes display UTC, and arbitrary
strings are not guessed as dates. Indexes survive transport but do not become X.

## Tasks and acceptance

### T01 - Immutable scientific runtime values and native script interfaces

- COREX-owned immutable array/table values with shared owned buffers and a
  versioned data-only codec. Automatically snapshot exact ndarray, Series, and
  DataFrame script outputs; materialize native objects at script input boundaries.
  No pickle, arbitrary classes, or changes to JSON collection validators.
- Concrete canonical array/table type IDs usable by scripts (or intentional Any),
  item-access outputs and lazy dependency loading. Guarantee isolation at mutable
  script boundaries, not by copying for every built-in consumer. Copy-on-write or
  zero-copy views are optimizations, not the ownership guarantee.
- Preserve standard numeric/Boolean/complex/datetime/timedelta/fixed-string
  ndarray dtypes; pandas primitive, nullable numeric/Boolean/string, text-object,
  and timezone-aware datetime columns; flat indexes, RangeIndex, names, order,
  missing values, dtype, and shape.
- Reject object ndarray, arbitrary objects, subclasses, MultiIndex, categorical,
  and custom extension types. Object pandas text permits only strings/missing.
- Preflight exact fields, shape, dtype, lengths and allocation bounds. Limit
  decoded content to 256 MiB/value and 512 MiB/codec operation (including masks,
  indexes and strings). Preserve existing session-reuse budget and recomputation.
  Scientific results remain durable-ineligible in this change.
- Prove codec round trips/rejections, Script-to-Script types, sibling mutation
  isolation, and process/external workers.

### T02 - Shared source loading and normalization

- Promote reusable column loading from generic plot code into the tabular owner
  and update existing callers without altering their plotting defaults.
- One execution-owned source normalizer for immutable/native/plain numeric inputs,
  DataTrees, and existing table/array/window/slice references.
- A rectangular nested list in one graph item is a matrix; separate numeric
  branches remain independent signals. Expand container tree items and retain
  tree/item order.
- Honor selected columns/windows/slices; load only needed columns; preserve
  alignment and gaps. Reject ragged/higher-dimensional data, invalid explicit
  selections, and absent numeric Y. Log Y requires positive finite samples.
- Prove equivalent native/file-backed traces and input/error edge cases.

### T03 - Signal Plot renderer and controls

- Keep plot.signal, Values, Tree access, existing style controls and Image output;
  declare concrete accepted numeric/collection/COREX-array-table/reference types.
- Add Data controls: Automatic/Sample index/Column X mode, X column, Y columns.
  Named selectors are exact names; positional selectors are zero-based internally
  and one-based in UI. Duplicate names require positions. Blank Y is automatic.
- Reuse searchable/list controls and property projection. Obtain schema from
  cached tabular metadata/current accepted upstream results, never source IO or
  script execution during inspector projection. Refresh on current output changes;
  allow authored selections before data exists.
- Render explicit numeric/datetime X, derived/overridden labels, UTC datetime
  axes, numeric X interval and optional ISO-8601 datetime bounds.
- Maximum rendered points defaults to 4000 per trace; 0 selects full resolution.
  Extend shared min/max reduction with gap preservation without changing generic
  caller behavior; preserve order/extrema/endpoints, warn on reduction, and fail
  clearly if the budget cannot represent gap topology. Never reduce source data.
- Prove control persistence/undo/schema refresh, rendering, datetimes and reduction.

Implementation routing: Signal Plot needs its own early property-adapter branch;
do not add it to the generic plot branch that creates unrelated axis/backend
controls. Canonical selectors are exact str names or int positions (never parse a
display label as an index). Reuse existing enum/list label-code fields, preserving
exact case and whitespace for these selectors. Dynamic inline options need the
same metadata enrichment as inspector options. Add cached column descriptions
when the tabular source is already opened, and consult current retained output
records only. Existing generic `_tabular_column_options` performs IO and must not
be reused. Inspector refresh follows accepted-output/freshness changes.

### T04 - Integration and closeout

- Runnable tabular/NumPy/pandas examples and usage documentation.
- Initial and repeated execution of two million rows by four numeric columns;
  record elapsed/peak memory, bounded rendering, complete source values, and
  existing oversized-reuse recomputation.
- Python Script is already classified `solution_reuse_scope='never'` for
  untrusted user code. Preserve this policy: the real script benchmark verifies
  repeated recomputation; a separate trusted reusable test fixture verifies
  small-result reuse and the exact 64 MiB `reuse_payload_budget_exceeded` path.
- Verify concrete/Any/ref connection legality and reject unrelated types.
- Focused suites first, then summarized fast integration. Update agent maps,
  route index when citations change, catalog contracts and guides. Run agent-map,
  traceability, Markdown-link and relevant documentation hygiene checks.
- One implementation writer per stage; independent review of substantial runtime
  and integration changes. User requested committing this work to main and pushing
  after completion. Preserve pre-existing edits and exclude them from publication.

## Progress

| Task | Status | Owner | Accepted evidence / next action |
| --- | --- | --- | --- |
| T01 | Accepted | runtime_values_impl | runtime_values_review accepted: 51 scientific/process/external tests; 236 typed/catalog tests; 19 fidelity probes; final 72-test adapter/identity gate passed. |
| T02 | Accepted | signal_inputs_impl | signal_inputs_review accepted final 32 normalizer tests, prior 49 normalization/input and 59 shared tabular/generic tests, plus independent edge probes |
| T03 | Accepted | signal_controls_impl | signal_controls_review approved: 154 writer-focused Python, 32 independent Python, 39 QML checks, QtCore-only and real-window focus/selection/readonly checks passed |
| T04 | Accepted with baseline gate failures | signal_closeout_impl | signal_final_review approved; eight 2M-row runs passed; final parallel fast 4678 passed / 3 skipped / 3 independently reproduced baseline failures; serial fast 220 passed; maps, traceability, links and focused hygiene passed |

Feature implementation and focused acceptance are complete. Broad verification
remains qualified by three failures reproduced on the starting commit; see the
[retained QA report](specs/perf/SIGNAL_PLOT_SCIENTIFIC_INPUTS_QA.md) for exact
failures, benchmark measurements, supported scope, and reproduction commands.

## Baseline and constraints

Baseline commit: 56c4d0b2ffc92b4b9e48d5fb1167eacb665b1e54.

T01 interface: `runtime_contracts/scientific_values.py` owns ArrayValue
(`to_numpy(copy=False)`), TableValue (`kind`, `column_names`, `columns`,
`row_count`, `column_values(position)`), and native script adapters. Type IDs are
COREX.DataTypes.ArrayValue, COREX.DataTypes.TableValue and
COREX.DataTypes.SeriesValue (a TableValue variant). The codec is
`runtime_contracts/scientific_codec.py`. T02 provides
`normalize_signal_inputs(..., x_mode='auto', x_column='', y_columns=(),
logarithmic_y=False)` and `SignalTrace(x, y, label, x_kind)`.

T02 caches a complete `metadata.column_schema` list of `{name, dtype}` during
source opening; omit the entire field if final merged ref metadata exceeds the
existing 64 KiB bound. Explicit window/slice refs override base preview hints.
Positional selection supports duplicate Parquet columns. Missing schema in
source-direct text requires execution-time numeric inspection, never date guessing.

T03 selectors use JSON-backed declared properties and shared UI metadata
enrichment so mixed exact string/int values survive graph property validation;
do not declare a string-only list and coerce integer positions into names.

Unrelated working-tree changes are preserved and excluded from publication. The
implementation target is the current EA_Node_Editor checkout.

Inputs fit RAM (up to a few million rows). Out-of-RAM transport, solver-specific conversion,
categorical axes, new interactive chart surfaces, and durable native-object
persistence are outside scope. No compatibility aliases or public Python-library
subclass/view/attrs guarantees are required.
