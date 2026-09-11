# Edge Routing, Labels, And Progress

## Purpose
Use this for edge routing, retained edge layers, active-data Item/List/Tree/Empty structure and display styling, enabled/invalid states, labels, hit testing, gap/break variants, and edge performance.

## Start Here
- `ea_node_editor/ui_qml/edge_routing.py`
- `ea_node_editor/ui_qml/graph_geometry/route_payload.py`
- `ea_node_editor/ui_qml/graph_scene_payload/normalize.py`
- `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeScenegraphLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeSnapshotCache.js`
- `ea_node_editor/ui_qml/components/graph/EdgePaintPolicy.js`
- `ea_node_editor/ui_qml/components/graph/EdgeCanvasLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeRetainedLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeFlowLabelLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeHitTestOverlay.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphEdgeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/GraphSharedTypography.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasActionRouter.qml`
- `ea_node_editor/ui_qml/graph_canvas_command/`
- `ea_node_editor/ui_qml/graph_scene_mutation/selection_and_scope_ops.py`
- `ea_node_editor/ui_qml/components/graph/EdgeMath.js`
- `tests/test_data_type_ui_projection.py`
- `tests/test_flow_edge_labels.py`
- `tests/test_graph_surface_input_controls.py`
- `tests/graph_track_b/scene_model_graph_scene_suite.py`
- `tests/graph_track_b/qml_preference_rendering_suite.py`

## Focused Verification
- `GraphNodeSurfaceMetrics.js` uses projected port-row heights for standard, viewer, and media endpoints so edge rendering stays aligned with node grips at custom graph text sizes. The real-canvas regression is in `tests/graph_surface/passive_host_interaction_suite.py`.
- `active_data_wire` is true only for standard data edges incident to an `active` or `compile_only` node. Its source `data_access` renders Item solid, List round-dotted, Tree rounded-dashed, and Empty as double hairlines with hollow endpoints. Passive-only and `flow` edges keep the legacy payload and appearance.
- `graph_geometry/route_payload.py::_data_type_warning_reason` owns the stable edge-level `data_type_warning` and reason derived from graph-owned all-member forwarding compatibility and resolved endpoints. It accepts assignable, convertible, runtime-check, and the target input's ordered accepted-type union; incompatible, unresolved, or missing endpoints warn. Quick Insert recommendation tiers never alter this static legality. `graph_scene_payload/normalize.py` publishes separate availability warning/reason fields and never converts availability into a type warning. Structurally valid flow edges do not warn, and edge type reasons stay out of port text.
- Edge warning projection reuses invocation-scoped `GraphTypeResolver` facts with port descriptions. Upstream edits publish all downstream pruning and warning changes through the scene delta owner; existing Type Error rendering is unchanged. `tests/test_type_forwarding_ui.py` owns chain refresh and warning coverage.
- Ordinary execution failure never turns a data wire red. Execution/control-edge flash and the simplified control connector overlay are removed; selection, preview, labels, routing, and crossing styles remain independent effects.
- Edge Enable is checked in the edge context menu and selected-edge floating toolbar and toggles through Ctrl+E. Disabled edges retain canonical identity, order, selection, label, and hit testing.
- `visual_style.display_mode` is normalized to Default, Faint, or Hidden by graph-owned batch mutation. Faint preserves hit geometry/tooltips; Hidden leaves endpoint arcs and logical-route marquee intersection but no body click hit, then reveals the full blue route when selected. Disabled active-data wires keep their structure with a centred X; direct selection preserves it, selected-node incidence adds a blue fade, and invalid type keeps the input-centred red gradient.
- `GraphCanvasInputLayers.qml` owns held-W wire marquee and Ctrl+Left/Ctrl+Right endpoint navigation. `GraphCanvasContextMenus.qml`, `GraphCanvasOptionsMenu.qml`, and `GraphCanvasActionRouter.qml` keep single- and selected-wire display menus plus endpoint jump actions aligned with this route.
- Edge `visual_style.path_mode` can force the scene payload route to `pipe` or `bezier`; missing/empty keeps the existing auto pipe-vs-bezier routing.
- Edge label and visual-style edits publish targeted updated-edge deltas; `EdgeSnapshotCache.js` clears dirty-edge geometry, snapshots, and spatial-index entries so forced path-mode routes remain hittable for inline label editing.
- `EdgePaintPolicy.js` is the pure renderer-neutral owner for flow/standard stroke, dash, structure, display-mode, marker, drag-preview, and gradient-stop facts. Canvas and retained renderers call it directly; `EdgeMath.js` owns shared edge anchors. Retained rendering must not reference Canvas implementation methods.
- Default flow-edge label backing stays transparent; `EdgeCanvasLayer.qml` adds a label-sized break range to the existing broken-edge paint path so the edge is visually discontinuous under the label. Explicit `label_background_color` styles still draw their chosen backing color.
- Edge pan/drag/flash performance gates live in `EdgeSnapshotCache.js`, `EdgeRetainedLayer.qml`, and `EdgeFlowLabelLayer.qml`: viewport spatial queries use a single cell-range cache, dirty hit tests call `ensureSpatialIndex`, retained entries gate unchanged `contentKey`s, and flow-label model sync skips unchanged `edgeData` references.
- `EdgeCanvasLayer.qml` exposes `canvasStateBridgeRef` from `EdgeLayer.sceneBridge`; inline edge typography and flow-label shared roles depend on that bridge projection.

```powershell
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/qml_preference_rendering_suite.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py -k "paint_policy or active_data_wire_renderers" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_output_mode_ui.py tests/test_flow_edge_labels.py tests/test_edge_snapshot_spatial_index.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py tests/test_graph_surface_input_controls.py tests/graph_track_b/scene_model_graph_scene_suite.py -k "active_data_wire or display_mode or request_rewire_edges or ctrl_drag" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_tree_ui.py tests/test_graph_surface_input_controls.py -k "port_and_edge_authoring or edge" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py -k "type_warning or availability_annotation" --ignore=venv -q
```

## Breadcrumbs
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)
- [Node Execution Visualization](node_execution_visualization.md)

## Update Triggers
Update when edge paint-policy ownership, path geometry, active-data structure/display/disabled/selection/error styling, type-reason/availability-warning separation, labels, inline label editing, selected-edge toolbar controls, Ctrl+E routing, wire marquee/jump actions, hit testing, or edge performance routes change.

## 2026-07-11 Performance Ownership

- Endpoint anchors come from invocation-scoped presentation facts. Stable style/label/geometry changes replace cached payloads without reindex; related lane siblings replace in place around one sorted structural insert/remove.
