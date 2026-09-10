# Plugin Migration Guide

COREX is pre-release, so the novice function SDK is a clean break. Old public
class, descriptor, factory, executable-manifest, and import-based discovery
APIs are unsupported; there is no adapter or compatibility shim.

## Migrate source declarations

Rewrite each ordinary executable node as a top-level function that imports
`corex` and uses only the 17 public names documented in the
[Plugin Authoring Guide](PLUGIN_AUTHORING_GUIDE.md#public-api).

```python
import corex


@corex.node(
    id="custom.scale_value.1234abcd",
    name="Scale Value",
    category=("Custom", "Math"),
)
@corex.input("value", value_type=float, required=True)
@corex.number("factor", default=2.0)
@corex.output("result", value_type=float)
def scale_value(ctx, value, settings):
    return {"result": value * settings.factor}
```

Preserve existing node IDs, port keys, and property/control keys when saved
projects must continue to open. Rename presentation text freely. Remove public
class instances, descriptor lists, factories, executable package manifests,
and imports from COREX internals.

Public functions return an output mapping, not a result wrapper. With controls,
read values from the immutable final `settings` parameter. `port=True` creates
an optional override input but the effective value still appears in `settings`.
Do not convert a trusted dynamic-topology, passive/custom-surface,
backend-manifest, or handle/session node into a fake function; those remain
internal implementation exceptions.

## Make port types explicit

Every `@corex.input` and `@corex.output` requires explicit `value_type=`.
Declarations that previously omitted it now fail at the decorator's source
location. Add the actual supported type, or use `value_type=corex.Any` only when
the port deliberately accepts or produces generic dynamic values. COREX does
not rewrite source or retain an implicit-Any compatibility shim.

Blank connection Quick Insert now recommends precise matches. Legal fallback
connections remain searchable as `Broad data match` or `Checked at runtime`.
Existing projects open against the current registry; newly incompatible edges
are removed in memory and mark the workspace dirty, without overwriting the
source file until the user saves.

## Node package schema 1

Schema-1 archives and installed directories are rejected with this exact
message:

```text
Node package schema 1 is unsupported. Use schema 2; see docs/PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1.
```

There is no in-place schema upgrade. Recover the original source, rewrite it to
the public function API, place the `.py` file directly in the plugin folder,
validate/reload it, then export a new schema-2 `.cxpkg`. Export generates source
hashes and the node identity/function inventory; do not hand-maintain a second
copy of node metadata.

Schema 2 requires `schema_version`, `name`, `version`, `modules`, `sources`,
`assets`, and `nodes`, rejects unknown or undeclared members, and permits only
root-level Python sources plus supported image assets. The complete manifest
and security rules are in
[Package schema 2](PLUGIN_AUTHORING_GUIDE.md#package-schema-2).

## Reload compatibility

A reload can retain open instances when it only changes presentation metadata,
adds outputs, adds optional inputs, or adds controls whose defaults are valid.
COREX refuses the reload before mutation when an open instance would lose a
port/property, change port direction/type/shape/requiredness, change a property
type, invalidate a saved value, or collide with another node ID.

Source is selected by the last successful reload. Validation and reload do not
execute it; execution uses the pinned immutable generation in a process worker.
If a bundled import is absent, the declared node remains visible but locked.

## Choose a different extension when needed

- Keep a one-project synchronous transform in **Core > Python Script**; its
  source and applied declaration live in `.cxproj`.
- Use a **Custom Workflow** when the reusable behavior is already a graph.
- Keep advanced host services in trusted internal code.

External/native runners, automatic dependency installation, background source
watching, a marketplace, and generated `.py`/`.pyi` typing companions are not
implemented.
