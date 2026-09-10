# Graph Canvas Feature Recipes

## Purpose
Step-by-step recipes for the three most common graph-canvas feature classes after the 2026-06 canvas-pipeline decomposition. Each recipe lists the exact files to edit; if you find yourself editing a file not listed here for one of these feature classes, you are probably re-introducing a pass-through (see `tests/test_qml_drill_budget.py` and the frozen-surface snapshot in `tests/test_graph_canvas_surface_snapshot.py`).

These feature classes require **zero edits** to: `GraphCanvas.qml`, `GraphNodeHost.qml`, `GraphCanvasNodeDelegate.qml`, `graph_scene_bridge.py`, `shell_context_bootstrap.py`. `GraphCanvas.qml` already composes the focused state, command, and viewport owners directly.

## Start Here
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml`
- `tests/test_graph_canvas_surface_snapshot.py`
- `tests/test_qml_drill_budget.py`
- `tests/test_graph_canvas_command_ops_modules.py`
- `tests/test_bridge_mixin_meta_registration.py`

## Recipe A — New payload field for a node kind

Files (2; +1 one-time registration if the kind has no contributor yet):
1. `ea_node_editor/ui_qml/graph_scene_payload/kinds/<kind>.py` — add/extend `contribute(payload, ctx)` (or `normalize_properties` for property normalization). New build inputs go on `factory.PayloadBuildContext` once, never threaded through signatures.
2. The consuming surface QML (e.g. `components/graph/passive/GraphMediaVideoRenderer.qml`) — read `host.nodeData.<field>`.
3. *(one-time)* `kinds/__init__.py` — register the kind's contributor in `kind_dispatch_for_spec` if this is the kind's first contribution. Registration order is frozen; append within the existing dispatch checks.

Measured (P10 dogfood, media-panel demo field, `git diff --name-only`):
```
ea_node_editor/ui/media_panel_source.py
ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py
ea_node_editor/ui_qml/components/graph/passive/GraphMediaVideoRenderer.qml
```

## Recipe B — New persisted canvas preference (canvas + options menu)

`AppPreferencesController` owns storage/normalization, `ShellWorkspacePresenter` owns persisted graphics projection/mutation, and graph-canvas session facts/commands use direct search-scope state/controller plus the selected-run preference owner. Do not restore an aggregate canvas source.

Files (4 canvas-pipeline files; storage/presenter outside the pipeline unchanged):
1. `ea_node_editor/ui_qml/graph_canvas_command/graphics_settings_ops.py` — one `@pyqtSlot` forward to the graphics source.
2. `ea_node_editor/ui_qml/graph_canvas_state/graphics_preferences_props.py` — one `@pyqtProperty` from the graphics source (notify `graphics_preferences_changed`).
3. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml` — one readonly fact.
4. The consumer (e.g. a `GraphCanvasOptionsMenu.qml` row) — read `root.canvasPrefs.<fact>`.

Measured (P10 dogfood, demo-marker preference):
```
ea_node_editor/ui_qml/graph_canvas_command/graphics_settings_ops.py
ea_node_editor/ui_qml/graph_canvas_state/graphics_preferences_props.py
ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasPreferenceFacts.qml
ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasOptionsMenu.qml
```

## Recipe C — New per-node visual state (lookup → badge/tint)

Files (3):
1. `ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py` — one `@pyqtProperty` lookup (notify `node_execution_state_changed` or a dedicated signal in the same mixin).
2. `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml` — one readonly fact.
3. The consuming layer/surface (e.g. `components/graph/GraphNodeChromeBackground.qml`) — derive per-node state from `host.executionFacts.<lookup>[nodeId]`.

Measured (P10 dogfood, demo-highlight lookup; before the campaign the equivalent change — commit `9f78b6e9`, nodeElapsedTimeUnit — touched 5 QML files plus Python):
```
ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py
ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml
ea_node_editor/ui_qml/components/graph/GraphNodeChromeBackground.qml
```

## Guard rails
- `tests/test_graph_canvas_surface_snapshot.py` — the QML-visible focused-owner surface is frozen (additions allowed, removals/renames fail; regenerate with `--write`).
- `tests/test_qml_drill_budget.py` — two-way ratchet on pass-through drilling (`canvasItem.` in `GraphNodeHost.qml`, `rootBindings.` in `GraphCanvas.qml` pinned at 0).
- `tests/test_graph_canvas_command_ops_modules.py` — every command-mixin slot must register on the composed bridge; no cross-domain name collisions.
- `tests/test_bridge_mixin_meta_registration.py` — pins the PyQt6 mixin meta-object guarantees the bridge packages rely on.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_surface_snapshot.py tests/test_qml_drill_budget.py tests/test_graph_canvas_command_ops_modules.py tests/test_bridge_mixin_meta_registration.py --ignore=venv -q
```

## Breadcrumbs
- [Graph Scene Payload And Projection](graph_scene_payload_and_projection.md)
- [QML Bridge Wiring](qml_bridge_wiring.md)
- [Node Execution Visualization](node_execution_visualization.md)
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)

## Update Triggers
Update when the kinds registry, the facts objects, the per-domain bridge packages, or the guard-rail tests change shape.
