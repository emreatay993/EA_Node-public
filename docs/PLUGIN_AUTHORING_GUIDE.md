# Plugin Authoring Guide

Use a plugin when a Python node should be reusable across projects. A loose
plugin is one UTF-8 `.py` file in the COREX plugin folder; package it as
`.cxpkg` only when you need multiple source files or image assets.

## Choose the right extension

| Use | Best for | Saved with | Update action |
| --- | --- | --- | --- |
| **Python Script** | One project-local synchronous transform | The `.cxproj` node | Click **Apply** |
| **Plugin** | Reusable Python function nodes | Plugin folder or `.cxpkg` | **Reload Plugins** |
| **Custom Workflow** | Reusing a graph as a node | A `.cxwf` workflow | Save/reload the workflow |

Python Script has its own compact contract in the
[Python Script guide](PYTHON_SCRIPT_GUIDE.md). Custom Workflows compose existing
nodes; they do not expose a Python API.

## Create the first plugin

1. Start COREX and choose **File > New Plugin...**.
2. Enter the visible name. COREX generates a safe filename, function name, and
   one stable ID such as `custom.strain_conditioner.a7c31e9b`.
3. Edit the generated source. Keep the generated ID when renaming the node.
4. Click **Validate**. Validation reports file, line, column, node ID, source
   digest, and dependency availability without importing or executing the file.
5. Click **Save** (or press Ctrl+S), then **Reload**. You can also use
   **File > Reload Plugins** after editing a saved file outside COREX.

The editor saves only direct-child `.py` files under
`%APPDATA%\COREX_Node_Editor\plugins\`. It does not overwrite an existing file
or silently replace a file changed by another program.

This complete dependency-free example returns `37` with its defaults:
[strain_conditioner_plugin.py](examples/strain_conditioner_plugin.py).

## Public API

Plugin source imports one public module:

```python
import corex
```

Its complete public surface is:

```text
node, input, output,
text, text_area, number, switch, dropdown, slider,
color, path, interval, list,
Any, Image, Color, Interval
```

Internal registry types, factories, descriptors, manifests, and private
decorator fields are not public authoring APIs.

## Declare a node

```python
import corex


@corex.node(
    id="custom.scale_value.1234abcd",
    name="Scale Value",
    category=("Custom", "Math"),
    description="Scale a value.",
    keywords=("scale", "multiply"),
)
@corex.input("value", value_type=float, required=True, label="Value")
@corex.number("factor", default=2.0, label="Factor", port=True)
@corex.output("result", value_type=float, label="Result")
def scale_value(ctx, value, settings):
    return {"result": value * settings.factor}
```

`@corex.node` must be the first decorator. A public plugin ID has the form
`custom.<readable-slug>.<8-lowercase-hex>`. `id`, `name`, and `category` are
required; `description`, `keywords`, and `icon` are optional. One file may
contain several top-level node functions with unique IDs and function names.
Both `def` and `async def` are valid for plugins.

Every `@corex.input` and `@corex.output` requires explicit `value_type=`.
Omission produces a source-located declaration error; it never defaults to Any.
Use `value_type=corex.Any` only for an intentionally generic or dynamic port.
Inputs and outputs also accept `structure`, `label`, and `description`.
Inputs also accept `required` and `section`. `structure` is exactly `"item"`,
`"list"`, or `"tree"`. Use Python `bool`, `int`, `float`, and `str`, one of
`corex.Any`, `corex.Image`, `corex.Color`, `corex.Interval`, or a registered
canonical type-ID string.

Choose the narrowest registered type that describes the values the port really
produces or accepts. Blank connection Quick Insert shows precise type matches;
legal broad and runtime-checked matches require a search and are labeled
`Broad data match` or `Checked at runtime`. This recommendation policy does not
prohibit an otherwise graph-legal manual connection.

## Scientific array and table values

Public plugins can declare `COREX.DataTypes.ArrayValue`,
`COREX.DataTypes.TableValue`, and `COREX.DataTypes.SeriesValue` canonical type-ID
strings for ndarray, DataFrame and Series. Keep item access for the whole
container, or use intentional `corex.Any`. COREX snapshots native outputs into
immutable owned values and supplies isolated native NumPy/pandas objects at
public plugin inputs. Built-in readers share the immutable internal values.
See [scientific values and limits](SIGNAL_PLOT_GUIDE.md#native-numpy-and-pandas-in-scripts).

## Add controls

Controls create saved settings. Every control accepts `name`, `default`,
`label`, `description`, `section`, and `port`. `port=True` also creates an
optional input; a connected value overrides the saved setting without replacing
it.

| Decorator | Additional fields |
| --- | --- |
| `corex.text`, `corex.text_area` | Text defaults |
| `corex.number` | `minimum`, `maximum`, `step` |
| `corex.switch` | Boolean default |
| `corex.dropdown` | `options`, optional integer `codes`, `searchable` |
| `corex.slider` | Required `minimum` and `maximum`, optional `step` |
| `corex.color` | Colour default |
| `corex.path` | `file_filter` |
| `corex.interval` | `minimum`, `maximum`, `step`, `direction` |
| `corex.list` | `item_type`, `options`, `codes`, bounds and `step` |

Decorator arguments and referenced same-file constants must resolve entirely
to literal scalars, lists, tuples, dictionaries, or `None`. Calls,
comprehensions, arithmetic, f-strings, environment reads, imported aliases,
arbitrary attributes, unknown fields, and private fields are rejected.

## Function and settings rules

Without controls, the function signature is `def node_name(ctx, input_one, ...)`.
With any controls, add `settings` as the final parameter. Controls never become
direct parameters. Do not use default arguments, positional-only or
keyword-only parameters, `*args`, or `**kwargs`.

`settings` is immutable. Read fields directly or copy them:

```python
factor = settings.factor
snapshot = settings.to_dict()
```

Nested mappings become read-only mappings, sequences become tuples, and sets
become frozensets. `to_dict()` returns a defensive deep mutable copy. Unknown
attributes are reported with a nearest-name suggestion.

For a `port=True` control, override selection uses input presence, not
truthiness. Connected `None`, `False`, `0`, `""`, and empty containers are real
supplied values. A disconnected optional ordinary input is passed as `None`.

## Return outputs and warnings

Return a mapping whose string keys are declared outputs. Undeclared keys and
non-mapping returns fail. An omitted declared output settles EMPTY; an explicit
`None` is a published Item value.

```python
if clipped:
    ctx.warn("Samples were clipped.", code="clipped_samples")
return {"result": result}
```

Warning messages are non-empty and at most 2048 characters. Codes are at most
64 characters, begin with a lowercase letter, and may contain lowercase
letters, digits, `_`, `.`, and `-`. Calls keep their order across sequential
data-tree iterations.

## Validation, generations, and reload

Validate, reload, import, and export parse plugin source statically. They never
execute plugin code. A successful reload copies validated members into an
immutable content-addressed generation. Process workers verify its SHA-256
identity and import from that generation, never from the mutable author file.
Editing source after reload has no effect until the next successful reload.

Reload is refused during an active run, viewer request, or viewer session. It
also refuses changes that would invalidate an open graph: removed ports or
properties, changed port direction/type/shape/requiredness, changed property
types, invalid saved values, or ID conflicts. Presentation changes, new
outputs, new optional inputs, and new valid controls are compatible. A refused
reload leaves the current registry, files, graphs, and workers unchanged.

Imports that are absent from the bundled runtime keep the node visible but
locked with `<module> is not included in this COREX bundle.` COREX does not
install dependencies or mutate Python environments for plugins.

## Package schema 2

Use **File > Export Node Package...** to create a deterministic `.cxpkg`. The
generated `node_package.json` has exactly these fields:

```json
{
  "schema_version": 2,
  "name": "strain_tools",
  "version": "1.0.0",
  "author": "",
  "description": "",
  "modules": ["nodes.py"],
  "sources": [{"path": "nodes.py", "sha256": "<lowercase-sha256>"}],
  "assets": [],
  "nodes": [
    {
      "id": "custom.strain_conditioner.a7c31e9b",
      "module": "nodes.py",
      "function": "strain_conditioner"
    }
  ]
}
```

All seven fields are required and unknown fields reject. `modules` lists files
scanned for declarations. `sources` lists every root-level Python source,
including helpers. `assets` permits `.svg`, `.png`, `.jpg`, and `.jpeg` files.
`nodes` is generated identity inventory. Dependencies are not a manifest field.

Limits are 64 KiB for the manifest, 256 KiB per Python source, 4 MiB per asset,
128 total members including the manifest, and 16 MiB total expanded content.
Paths use `/`, remain relative, and are case-insensitively unique on Windows.
Encrypted entries, links, reparse points, hard-linked members, absolute paths,
traversal, backslashes, dot segments, undeclared members, unsupported assets,
and nested Python packages reject. The archive digest covers canonical manifest
JSON plus sorted member paths and exact bytes; archive order and timestamps are
deterministic.

Use **File > Import Node Package...** to validate and atomically install a
package. Schema 1 is unsupported; see the
[migration guide](PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1).

## Examples and current limits

- [Strain Conditioner](examples/strain_conditioner_plugin.py) is dependency-free
  and executable in the process worker.
- [Signal Plot Style](examples/signal_plot_function_plugin.py) demonstrates
  sections, paired control inputs, mappings, and ordered warnings without
  requiring a plotting dependency.

Public plugin functions currently run only in COREX process workers. External
or native runners, dependency installation, background file watching,
marketplace distribution, and generated Python typing companions are not
implemented.
