# Python Script Nodes

`Core > Python Script` lets you add a small, local Python transform to a
workflow. Put the declarations and `run` function in the script editor, then
click **Apply**. COREX reads the declarations to create the node ports and
controls; it does not run your script while it is applying the draft.

Open the editor fullscreen from the Python Script node's code toolbar button,
then click **Guide** beside Apply/Revert for the theme-aware HTML reference. It
uses styled code cards, callouts, and tables and can be closed without changing
the current draft.

This guide is only for the built-in Python Script node. Its source is stored in
the project and its function is synchronous. Editor changes take effect on
**Apply**; canvas port handles update the same source immediately. Use the [Plugin Authoring Guide](PLUGIN_AUTHORING_GUIDE.md) when a
node should be reusable across projects.

## Choose the workflow Python runtime

Open **Workflow Settings > Environment** to choose where the whole workflow
runs. **Application Default Python Executable** is saved for COREX on this PC;
**Workflow Override** is saved in the current project and wins when non-empty.
Use either native **Browse** button to select an executable.

| Setting | Effective runtime |
| --- | --- |
| Workflow Override set | That project executable |
| Workflow Override blank, Application Default set | The application default |
| Both blank | The built-in process-isolated runtime |

**Create / Repair Managed Runtime** prepares COREX's managed environment and
fills the application default. **Clear Application Default** clears only that
default; **Inherit Application Default** clears only the workflow override.
There is no PATH search, per-node interpreter, or project force-built-in option
while an application default is set.

External Python is trusted local execution, not a sandbox, and it runs every
node in the workflow—not just Python Script nodes. A user-managed interpreter
must import `ea_node_editor.execution.stdio_worker`; it can still be rejected by
the normal startup handshake when its runtime contracts do not agree with the
desktop app. Changes apply to the next run and do not alter an active run.

On **OK**, COREX saves the application default first, then updates the live
project workflow settings and requests its existing best-effort session save.
Cancel or an app-preference write failure leaves the project unchanged. The
later session save is not a cross-store transaction, so a session-store failure
may leave the app preference and live project update in place.

API and headless callers can supply an explicit execution policy. Explicit
process, trusted, or auto policy ignores both stored Python paths. Explicit
external policy uses its own path; when it omits one, only the project Workflow
Override may fill it—the application default is shell-only.

## Start with a pass-through

Insert **Core > Python Script**, open its script editor, replace the draft with
this, and click **Apply**:

```python
@corex.node
@corex.input("payload", value_type=corex.Any)
@corex.output("result", value_type=corex.Any)
def run(ctx, payload):
    return {"result": payload}
```

`payload` is now an input socket and `result` is an output socket. The `run`
function receives the input and returns a mapping whose keys are declared
outputs.

## Declare ports

The green handles add `@corex.input` or `@corex.output` declarations with
`value_type=corex.Any`; input additions also add the matching `run` parameter.
The red handles remove the corresponding declaration and input parameter.
They work on plain input/output ports; decorator-backed controls remain edited
in the source. Apply or Revert an existing editor draft before using the handles.

Each handle click is one undoable edit, including source, ports, and removed
wires. Existing comments, decorator options, settings, and function logic are
preserved. After removing a port, update any references or returned output keys
in your function body before running. The handles do not rewrite your logic.
Port-label rename changes only the displayed label, not the Python identifier.

Put `@corex.node` directly above one synchronous function named `run`. Every
other declaration sits between it and the function. The source order is the
display order for inputs and controls; outputs stay at the top level.

```python
@corex.node
@corex.input("samples", value_type=float, structure="list", required=True)
@corex.output("average", value_type=float)
def run(ctx, samples):
    return {"average": sum(samples) / len(samples)}
```

Every `@corex.input` and `@corex.output` requires explicit `value_type=`.
Omission produces a source-located Apply error and leaves the applied node
unchanged. Use `value_type=corex.Any` only for an intentionally generic or
dynamic port; no type is inferred from the port name or function body.

`@corex.input` also accepts `structure=`, `required=`, `label=`,
`description=`, and `section=`. `@corex.output` accepts the same fields except
`required` and `section`. Names must be ordinary Python identifiers and cannot
be reused.

Use a built-in type, a supported alias, or a registered canonical type ID:

```python
@corex.input("enabled", value_type=bool)
@corex.input("title", value_type=str)
@corex.input("image", value_type=corex.Image)
@corex.output("colour", value_type=corex.Color)
@corex.output("catalog_text", value_type="COREX.DataTypes.String")
```

The built-ins are `bool`, `int`, `float`, and `str`. The aliases are
`corex.Any`, `corex.Image`, `corex.Color`, and `corex.Interval`. A canonical
type-ID string must already be registered or Apply reports an error.

Blank connection Quick Insert shows precise type matches. Legal broad or
runtime-checked matches appear after a search, labeled `Broad data match` or
`Checked at runtime`; manual graph-legal connections remain available.

`structure` describes the outer shape, independently of the element type:

| Structure | `run` receives or returns |
| --- | --- |
| `"item"` (default) | One value |
| `"list"` | One branch as a non-string sequence |
| `"tree"` | The complete `DataTree` topology |

Use `required=True` for an input that must be wired before the node can run.
Inputs are optional by default.

## NumPy and pandas values

Return an exact ndarray, DataFrame or Series as one graph item. Use
`value_type="COREX.DataTypes.ArrayValue"`, `"COREX.DataTypes.TableValue"`, or
`"COREX.DataTypes.SeriesValue"`, respectively; intentional `corex.Any` also
works. Keep the default `structure="item"` for the whole scientific container.
These values can connect directly to Signal Plot's Values input.

COREX stores immutable snapshots internally and automatically supplies isolated
native NumPy/pandas objects to script inputs. Input mutation affects only that
script; returning a result publishes a fresh snapshot. Scientific results are
not durable project values, and Python Script retains its existing never-reuse
policy. The [Signal Plot guide](SIGNAL_PLOT_GUIDE.md#native-numpy-and-pandas-in-scripts)
contains a complete DataFrame example, dtype support and memory limits.

## Add a control

A control decorator creates a project-local saved setting and a direct `run`
parameter. Add
`port=True` when the setting should also have an optional input socket: a wire
temporarily overrides the saved value, and disconnecting restores that value.

```python
@corex.node
@corex.output("caption", value_type=str)
@corex.text("title", default="My plot", section="Style", port=True)
@corex.slider(
    "line_width", default=2.0, minimum=0.5, maximum=8.0, step=0.5,
    section="Style", port=True,
)
def run(ctx, title, line_width):
    return {"caption": f"{title} ({line_width}px)"}
```

All controls accept `label=`, `description=`, `section=`, and `port=` in
addition to the fields shown below. Defaults and decorator options must be
literals: write `options=("A", "B")`, not a function call or variable.

| Decorator | Use |
| --- | --- |
| `@corex.text("name", default="")` | One-line text |
| `@corex.text_area("notes", default="")` | Multi-line text |
| `@corex.number("count", default=1, minimum=0, maximum=10, step=1)` | Integer or floating-point field |
| `@corex.switch("enabled", default=True)` | Boolean switch |
| `@corex.dropdown("mode", options=("Fast", "Accurate"))` | Fixed text choices |
| `@corex.slider("width", default=2.0, minimum=0.5, maximum=8.0, step=0.5)` | Bounded integer or floating-point slider |
| `@corex.color("line_color", default="#4f8cff")` | Colour text value and colour editor |
| `@corex.path("output_file", default="", file_filter="CSV (*.csv)")` | File path field |
| `@corex.interval("range", default=(0.0, 1.0))` | Two endpoint fields |
| `@corex.list("labels", default=["A"], item_type=str)` | Typed editable list |

`@corex.slider` always needs `minimum` and `maximum`. `@corex.number` can be
unbounded. For an integer-backed dropdown, give each display label an integer
code; `run` receives the code, so the default is a code too:

```python
@corex.dropdown(
    "legend_position",
    default=1,
    options=("Upper left", "Upper right", "Lower right"),
    codes=(0, 1, 2),
)
```

Text dropdowns can use `searchable=True`. Integer-backed dropdowns cannot be
searchable.

An interval without bounds uses two fields and may have `default=None`. Add
both `minimum` and `maximum` plus a non-null default to use the bounded range
slider. Its direction is explicit and preserved; use `"increasing"` or
`"decreasing"`.

```python
@corex.interval("window", default=(10.0, 0.0))
@corex.interval(
    "x_range",
    default=(0.0, 10.0),
    minimum=0.0,
    maximum=10.0,
    step=0.1,
    direction="increasing",
)
```

Lists require a literal list default. `item_type=` can be `str`, `int`,
`float`, or `corex.Color`. A fixed-choice list uses `options=`; it may also use
integer `codes=` in the same way as a dropdown.

```python
@corex.list("line_widths", default=[1.0, 2.0], item_type=float)
@corex.list("series", default=["A"], options=("A", "B", "C"))
```

## Organize the node

Add `section="Style"` (or another label) to inputs and controls. Sections are
created in first-use order and start collapsed. Outputs do not belong to a
section. A section only changes presentation: the ports and wires remain real
graph topology while it is collapsed.

The same-key control/input created by `port=True` shows one setting plus one
optional input. While that input is wired, the local editor is disabled and
shows the safe upstream display value when available. The authored setting is
not overwritten. Disconnecting restores it immediately.

When a new script is applied, valid same-key settings and compatible same-key
wires stay. Removed, renamed, direction-changed, type-incompatible, or
structure-incompatible sockets are pruned with their wire state. A retained
setting whose value no longer validates is reset to its declared default.

## Write `run`

`run` must use plain required parameters: `ctx` first, followed by every
declared input and every control exactly once. It cannot be `async`, have a
default parameter, a positional-only or keyword-only parameter, `*args`, or
`**kwargs`. Keeping the parameters in declaration order makes the script easy
to scan.

Return a mapping of declared output names to values. You may omit a declared
output to leave it unset; returning an undeclared output key fails the run.
Return the mapping directly; internal runtime result types are not part of this
authoring surface.

`ctx` provides `log_info(message)`, `log_warning(message)`, and
`log_error(message)` for the run console. Set the node's **Timeout (sec)**
property to a positive value to enforce the existing process-isolated timeout;
`0` leaves it disabled.

The complete, parser-validated Signal Plot-style example is
[python_script_decorated_signal_plot.py](examples/python_script_decorated_signal_plot.py).
It deliberately returns a text summary so it can be copied without a plotting
library; connect its `series` input to a real data source and replace the body
with your renderer when you need an image. Change both the declaration and the
returned key together:

```python
@corex.node
@corex.input("series", value_type=corex.Any, structure="tree", required=True)
@corex.output("image", value_type=corex.Image)
def run(ctx, series):
    image = render_plot(series)
    return {"image": image}
```

## Apply, errors, and old scripts

Editor drafts update a Python Script node when you click **Apply**; canvas port
edits apply their source changes immediately. Both paths read decorators with a
bounded, literal-only AST pass without importing the script or executing decorator
expressions.

An invalid draft stays dirty, shows a line-and-column error in the console, and
leaves the last applied source, ports, settings, wires, and collapsed-section
state untouched. A valid Apply is one graph/history action, so undo restores
the prior shape. Explicit Run actions first use a valid pending Apply; automatic
runs keep using the last applied script.

The old assignment-style script is removed. Convert this:

```python
result = payload
```

to the pass-through script at the top of this page. Every input, output, and
local setting is declared in the source, including ports added with canvas handles.

## Limits

Python Script declarations do not update while you type. There are no output
sections, asynchronous `run` functions, varargs, secret defaults, or arbitrary
decorator expressions. Python Script source stays in its `.cxproj`; it is not a
plugin file and cannot be exported as a node package. Use a
[plugin](PLUGIN_AUTHORING_GUIDE.md) for reusable package metadata or behavior
outside this compact local-script surface.
