# COREX Tabular Data Input Node Mockups

This folder contains four implementation-faithful mockup directions for modernizing the `Tabular Data Input` node.

- `index.html` is the interactive mockup chooser.
- `_shots/variant-a.png` shows Inline Preview Plus.
- `_shots/variant-b.png` shows Guided Setup.
- `_shots/variant-c.png` shows Fullscreen Workbench.
- `_shots/variant-d.png` shows Compact Canvas First.

## Options

| Option | Direction | Best fit |
| --- | --- | --- |
| A. Inline Preview Plus | Polish the current graph node surface with clearer source, preview, output, and cache state. | Default recommendation, lowest implementation risk. |
| B. Guided Setup | Make incomplete and blocked states feel intentional through inspector-led recovery. | Onboarding, archive selection, dependency errors. |
| C. Fullscreen Workbench | Invest in the shell-owned fullscreen table surface for professional data inspection. | Search, filter, sort, paging, schema, quality review. |
| D. Compact Canvas First | Keep data-source nodes small while preserving readiness and output state. | Dense graphs and batch workflows. |

## Constraints Preserved

- Dark Stitch shell, compact Qt/QML workstation layout, cyan selected node outline, graph grid, side panes, console, status strip, and minimap.
- Inline preview remains bounded to 50 rows by 50 columns.
- Table data is read-only.
- Search, filter, sort, row paging, and column paging are represented as backend-routed operations.
- Empty or blocked graph surfaces do not expose an inline browse call-to-action.
- Source, selection, parsing, cache, and safety controls remain inspector-owned.
- Fullscreen preview remains shell-owned and transient.
