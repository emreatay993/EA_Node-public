# Floating Toolbar And Checked States

## Purpose
Use this for graph node, flow-edge, and selection-envelope floating toolbar actions, checked-state projection, hover/selection visibility, toolbar positioning, quick edge-style popovers and popup lifecycle, inline edge-label editing, and zoom-aware tooltip placement that keeps popups clear of toolbar hit targets.

Subnode scope entry is a contextual node toolbar action (`open_subnode_scope` / `Enter Subnode`) rather than a persistent header badge or common action; keep `GraphNodeHost.qml` `contextNodeActions`, `GraphNodeFloatingToolbar.qml`, and graph-canvas action routing aligned.

Surface-local toolbar actions with `kind: "surface"` or `kind: "media"` dispatch directly through `GraphNodeHost.dispatchSurfaceAction(...)`; keep this path intact for passive text formatting actions, media controls, tabular source browse controls, and similar surface-owned controls.

The Panel surface exposes exactly six direct surface actions: increase/decrease font size, align left/right, and fit width/height. Their labels, explanatory tooltips, order, and semantic icons mirror the reference help, with separators after decrease and align-right. `GraphNodeHost.availableActions` returns only these six actions for Panel, without generic common-node actions. They are owned by `GraphPanelSurface.qml` and use the same surface-dispatch path; no global graph action IDs or toolbar-specific state bridge are involved.

Node floating toolbars open for exactly one selected node by default. `GraphNodeHost.qml` gates legacy hover reveal with the default-off app-wide `graphics.canvas.node_floating_toolbar_opens_on_hover` preference projected as `prefs.nodeFloatingToolbarOpensOnHover`; keep `toolbarPointerInside` active so the pointer can enter an open toolbar.

`GraphNodeFloatingToolbar.qml` publishes its flipped side and effective zoom to
`GraphNodeHost.qml`; node help, warning, and port tooltips use that state to
stay on the opposite side of the toolbar.

Passive `passive.*` hosts add a checked Lock action. A locked host normally closes/releases the toolbar and stops hit testing; Edit -> Interact with Locked Objects temporarily permits selection so the reduced Zoom/Unlock toolbar can be used.

Node specs project their shared `collapsible` capability into scene payloads. Unlocked, editable collapsible nodes receive one common Expand/Collapse floating-toolbar action from `GraphActionPresentation.js`; `GraphCanvasActionRouter.qml` routes it through the existing scene collapse mutation, so no surface or node type owns a duplicate implementation.

Collapsing hides the body but retains its surface while the floating toolbar is active, preserving live surface actions and dispatch (including Open Script) even when selecting an already-collapsed node. Closing the toolbar releases the collapsed surface; render-activation limits still apply. Hidden bodies publish no input rectangles or interaction locks, and viewer/plot embedded activity requires body visibility.

Expand/Collapse use the registered `node-expand`/`node-collapse` vertical arrows. Run uses the `node-run` circled play symbol on node and selection toolbars. Run's options button uses the existing `settings` gear through its action's `menu_icon` field, rendered at the primary icon size; menus without an override retain the dropdown chevron.

Text annotation toolbar icons resolve through `ui/icon_registry.py` and `ui_qml/components/shell/icons/`; keep `GraphBareTextSurface.qml` action icon names in the registered kebab-case `uiIcons` namespace.

Text annotation formatting uses grouped surface actions (`popoverActions`) rendered by `GraphNodeToolbarPopoverHost.qml` as toolbar-local compact popovers. The font-size group uses the owner's dedicated `font_size` layout with a validated integer field, slider, and `-` / `+` steppers. The font-family group uses the `font_family` searchable list layout, including Default clearing and surface-dispatched family selection. The text-style group owns emphasis plus markdown bulleted/numbered list toggles. Slider movement sends `text_font_size_preview:*` for local draft rendering and release/close flushes the final style commit through the text surface. Keep grouped popover controls surface-dispatched and include the owner's popover rect in the toolbar hit area. `tst_graph_node_toolbar_popover_host.qml` owns direct panel/focus/position/callback behavior; `tst_graph_surface_controls.qml` retains primary-button/open delegation, toolbar chrome, tooltip, checked-state, and binding-loop integration.

Node floating-toolbar popovers use level-aware sizing tokens owned by `GraphNodeToolbarPopoverHost.qml` and exposed through live compatibility reads on `GraphNodeFloatingToolbar.qml`: `_popoverControlHeight`, `_popoverIconSize`, `_popoverTextPixelSize`, `_popoverHorizontalPadding`, `_popoverVerticalPadding`, and `_popoverRadius`. Source-storage dropdowns, browse buttons, font-size controls, PDF page controls, and font-family search/list rows should consume these tokens instead of fixed `*_sizeScale` heights or primary-toolbar padding.

`GraphNodeToolbarPopoverHost.qml` keeps popover placement in toolbar coordinates through `_positionActionPopover`; implicit width/height handlers call the thresholded `_positionActionPopoverIfSizeMoved()` wrapper so text entry does not reposition on sub-pixel size churn. `GraphNodeFloatingToolbar.qml` retains the toolbar anchor/chrome placement and passes itself as the explicit owner for dispatch and coordinate mapping.

PDF media controls use the toolbar's `pdf_page` popover layout: a Navigate action opens previous/next page buttons around a validated page-number field that dispatches `pdf_page_set:*` to the PDF surface.

Text annotation copy/paste style buttons are surface actions (`text_copy_style`, `text_paste_style`) owned by `GraphBareTextSurface.qml`; paste applies a local draft immediately and prefers a bulk node-property commit.

## Start Here
- `ea_node_editor/ui_qml/components/graph/GraphActionPresentation.js`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeToolbarPopoverHost.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphEdgeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphSelectionEnvelopeOverlay.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasActionRouter.qml`
- `ea_node_editor/ui_qml/graph_canvas_command/`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeOverlayToolbarLayer.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/toolbar_positioning.js`
- `ea_node_editor/ui_qml/components/graph/EdgeFlowLabelLayer.qml`
- `ea_node_editor/ui_qml/components/graph/GraphSharedTypography.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphPanelSurface.qml`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui/shell/graph_action_contracts.py`

`GraphActionPresentation.js` shapes action fields, child menu/popover arrays,
checked indexes, stable filter ordering, node grouping, and edge toolbar choices
only when authoritative action lists or popover state change. Toolbar position,
anchor and hover grace remain in `GraphNodeFloatingToolbar.qml`; focus, draft
flush, panel callbacks and action-popover lifecycle live in the direct
`GraphNodeToolbarPopoverHost.qml` child. None are presentation-model dependencies.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_floating_toolbar_positioning.py tests/test_graph_action_contracts.py --ignore=venv -q
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_surface_controls.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_node_toolbar_popover_host.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_inline.py -k "floating_toolbar" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py -k "toolbar or label" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_passive_graph_surface_host.py -k timestamp --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_panel_surface.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_canvas_split_bridges.py --ignore=venv -q
```

## Breadcrumbs
- [Graph Actions And Context Menus](graph_actions_and_context_menus.md)
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)

## Update Triggers
Update when toolbar action state, checked-state projection, positioning, selection-envelope actions, flow-edge quick style controls, inline edge label editing, or toolbar tests change.
