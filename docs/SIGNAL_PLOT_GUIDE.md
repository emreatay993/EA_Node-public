# Signal Plot scientific inputs

Connect **Tabular Data Input > Table / Array** or **Python Script > result** to
**Signal Plot > Values**. Signal Plot returns an immutable PNG **Image**; connect
it to Media Panel for display or Image Export to write a file.

The [runnable example](../examples/signal_plot_scientific.README.md) generates
CSV, NumPy and pandas workflows. NumPy and pandas must be installed in the chosen
execution Python environment. Tabular formats retain their existing optional
dependency requirements.

## Automatic mapping

| Input | X | Y |
| --- | --- | --- |
| Numeric list, 1D ndarray or Series | Sample index | Values |
| One numeric matrix/table column | Sample index | That column |
| Multiple matrix/table columns | First numeric or typed datetime column | Other numeric columns |
| Numeric DataTree branches | Independent sample index per branch | One trace per branch |

Text and Boolean columns are skipped in automatic mapping. Row order and missing
samples are preserved. A rectangular nested list inside one graph item is a
matrix; numeric items in separate DataTree branches stay separate signals.
Container items in a tree expand in branch/item order. Ragged matrices, arrays
above two dimensions and inputs with no numeric Y fail with a clear error.

Pandas indexes survive transport but are never chosen as X. Put an index into a
column in your script when it should become the horizontal axis. Strings are not
guessed as dates: convert a datetime column explicitly in pandas first.

## Choose columns and ranges

The **Data** controls are **X mode**, **X column**, **Y columns**, and
**Maximum rendered points**. X mode offers Automatic, Sample index, or Column.
Blank Y columns means automatic selection. Column names are exact, including
case and whitespace; repeated names require a positional choice. Positions are
displayed from one in the UI and stored as zero-based integers. A numeric-looking
string remains a column name, not a position. Saved `x_column` values are exact
strings or integers; `y_columns` is an ordered list of those selectors.

Dropdown suggestions use cached source schema and current accepted upstream
outputs. Opening the inspector does not read files or execute scripts. Selections
can be authored before data is available; an invalid explicit selection fails at
execution. When an upstream result changes, current schema suggestions refresh.

Numeric X uses **X axis interval**. Typed datetime X uses optional ISO-8601
**Datetime X start/end** bounds (`x_datetime_start`, `x_datetime_end`); timezone-aware
axes display UTC. Mixed numeric/datetime traces on one axis are rejected. Derived
column labels can be overridden with **Labels**. Logarithmic Y requires positive,
finite samples; other samples become gaps.

## Full data and rendered points

The default `max_points=4000` limits each rendered trace, preserving endpoints,
extrema, sample order and gaps. A warning reports the original and rendered point
counts. If the requested budget cannot represent the gap topology, rendering
fails clearly. Set **Maximum rendered points** to `0` for full resolution.
Reduction never edits the source values or changes downstream consumers.

Source selection is separate from rendering reduction. Tabular selected columns,
table windows and array slices are honored before mapping. Direct ArrayDataRef
inputs honor Tabular Data Input's authored array slice, whose default is the
50-row/50-column preview selection. Increase that selection for more data, or use
Array Slice 2D: its explicit bounds override the base hints and `row_limit=0`
means all remaining rows. Table windows have the same zero-full row-limit rule.
Signal Plot adds no independent source preview cap; existing materialization and
memory limits still apply.

## Native NumPy and pandas in scripts

Use an item-access output and a concrete type ID, or intentional `corex.Any`:

```python
@corex.node
@corex.output("result", value_type="COREX.DataTypes.TableValue")
def run(ctx):
    import numpy as np
    import pandas as pd
    time = np.arange(10000) * 0.01
    return {"result": pd.DataFrame({"time": time, "signal": np.sin(time)})}
```

`COREX.DataTypes.ArrayValue` represents ndarray, `COREX.DataTypes.TableValue`
represents DataFrame, and `COREX.DataTypes.SeriesValue` represents Series. These
are registered type-ID strings, not new `corex` aliases. The ndarray/DataFrame
is one graph item; `structure="list"` would describe an outer graph list instead.

COREX snapshots exact native outputs into immutable owned buffers. Built-in
readers share those values. At Python Script and public plugin input boundaries,
COREX automatically supplies isolated native ndarray, DataFrame and Series
objects. Mutating one script input cannot alter the producer or a sibling input;
returning a changed object publishes a new snapshot. Public plugins use the same
types and conversions; follow the [plugin guide](PLUGIN_AUTHORING_GUIDE.md) for
their function signature and settings rules.

Transport preserves standard numeric, Boolean, complex, datetime, timedelta and
fixed-string ndarray dtypes. Pandas supports primitive and nullable numeric,
Boolean/string columns, text-object columns containing only strings/missing
values, timezone-aware datetimes, flat indexes, RangeIndex, names and order.
Transport support is broader than plotting: complex, timedelta and text values
are not numeric Y signals. Object/structured ndarray, arbitrary objects,
subclasses, MultiIndex, categorical and custom extension types are rejected.

The data-only codec validates fields, dtypes, shapes, lengths and allocation
bounds before decoding. Limits are 256 MiB decoded content per value and 512 MiB
per codec operation, including masks, indexes and strings. There is no pickle.
Scientific values remain ineligible for durable result storage.

Session reuse retains its separate 64 MiB encoded accepted-output budget.
Oversized reusable results recompute. Python Script already has a never-reuse
policy, so its source and dependent plot recompute on repeated runs even for
small inputs. The current factory-based script implementation is first rejected
for reuse with `implementation_identity_unavailable`; this precedes the
never-reuse check. See the [measured closeout](specs/perf/SIGNAL_PLOT_SCIENTIFIC_INPUTS_QA.md)
for the process/runtime workload and the separate trusted-fixture reuse proof.
