# Surface Input And Inline Controls

## Purpose
Use this for inline editors, surface controls, editable passive surfaces, text/path/color controls, and surface interactive regions.

## Lookup Aliases
- `inline list height`
- `list editor`
- `expandable inline controls`
- `standard inline property row height`
- `standard_inline_property_row_height`
- `signal plot inline control height`

## Start Here
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceListEditor.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeSettingsGroupsLayer.qml`
- `ea_node_editor/ui_qml/graph_geometry/standard_metrics.py`
- `ea_node_editor/ui_qml/components/graph/GraphInlinePropertiesLayer.qml`
- `ea_node_editor/nodes/builtin_functions/data_control.py`
- `ea_node_editor/nodes/builtins/data_control.py`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortsLayer.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortRow.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasSurfaceEditorOverlays.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphBooleanToggleSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphNumberSliderSettingsPopover.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphNumberSliderSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphTriggerSurface.qml`
- `ea_node_editor/ui_qml/components/graph/GraphStandardNodeSurface.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceButton.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceCheckBox.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceColorEditor.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceComboBox.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceDoubleClickTarget.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceInlineTextEditor.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceInteractiveRegion.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceIntervalFields.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceIntervalSlider.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfacePathEditor.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceSlider.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceTextArea.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceTextareaEditor.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceTextField.qml`
- `ea_node_editor/ui_qml/components/graph/surface_controls/SurfaceControlGeometry.js`
- `ea_node_editor/ui_qml/components/graph/surface_controls/`
- `ea_node_editor/ui_qml/components/graph/surface_controls/GraphSurfaceSearchableComboBox.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphSelectSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphSelectSettingsPopover.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphPanelSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphPanelEditorPopover.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeSurfaceMetrics.js`
- `ea_node_editor/ui_qml/components/shell/InspectorEditableComboBox.qml`
- `ea_node_editor/ui_qml/components/common/SecretEditor.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeSurfaceBridge.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInputLayers.qml`
- `tests/test_graph_surface_input_inline.py`
- `tests/graph_surface/inline_editor_suite.py`
- `tests/qml_quick/tst_graph_surface_controls.qml`
- `tests/qml_quick/tst_signal_selectors.qml`
- `tests/test_select_surface.py`
- `tests/test_panel_surface.py`
- `tests/qml_quick/tst_secret_editor.qml`
- `tests/test_sensitive_property_controls.py`

## Related Help Reference
- `ea_node_editor/ui/dialogs/input_reference_dialog.py` documents user-facing inline editor, textarea, port-label, and focused editor controls. Update it when commit/cancel keys or surface-control mouse behavior change.

## Routing Notes
- Panel's authored `value` remains literal text in the canvas/document. When the execution artifact service admits that property as a verified `RuntimeArtifactRef`, `nodes/builtins/data_control.py::execute_panel` preserves the carrier in its output rather than stringifying the dataclass. Ordinary text/number parsing and connected-input passthrough remain unchanged; `tests/test_canvas_import_runtime.py` covers Panel-to-Media execution and saved references.
- Shared searchable combos and list editors preserve exact string/int selector codes, authored unknown names, case and whitespace. Labels remain display-only; one-based positional labels never become stored names. Scalar selector text drafts survive inspector/model refresh and commit through the existing property route; programmatic refresh and read-only disablement do not commit drafts. Local filtering ranks exact, prefix, then substring matches in source order and exposes at most 50 filtered suggestions.
- `GraphSurfaceListEditor.qml` is the shared bounded ListView editor for string, integer, float, integer-backed enum, and color lists; numeric items may use declared slider bounds and every edit commits the complete ordered array.
- `GraphSurfaceIntervalFields.qml` is the shared nullable unbounded Interval1D editor with finite increasing endpoint fields and an explicit Auto action. Both controls inherit the existing connected-input disabling, accessibility, and embedded-interaction routing through `GraphInlinePropertiesLayer.qml`.
- Surface-owned embedded interactive rects claim host body input through `GraphNodeHostInteractionState.surfaceClaimsBodyInteractionAt(...)`. Keep `GraphNodeHostGestureLayer` cursor suppression aligned with that same predicate so live previews and inline controls do not inherit the host open-hand drag cursor.
- `GraphCanvasNodeSurfaceBridge.prepareNodeSurfaceControlInteraction(...)` clears transient canvas gestures and viewer focus without changing graph selection. Embedded control start and commit paths carry an explicit node ID; keep them selection-neutral while ordinary node body/header clicks continue through `nodeClicked`.
- `GraphNodeSettingsGroupsLayer.qml` is the shared renderer for spec-declared active-node settings groups. Header clicks own their pointer event and route through `GraphCanvasNodeDelegate` to the production `GraphCanvasCommandBridge`/`SceneMutationOps` facade, which forwards `set_node_settings_group_expanded` to the scene command source. Host width and height animate for 180 ms with InOutCubic easing, captured header/port positions, rapid retargeting, and lightweight-canvas motion disable. Controls clip to their revealed group and card bounds; transitional member grips remain visible while connected edges converge into aggregate sockets on collapse, with their editors/labels suppressed. Tagged animation geometry in the existing canvas overlay keeps EdgeLayer anchors aligned without taking ownership of manual resize previews, and clears on finish/cancel/removal. Python and QML reserve the same list/interval row heights. The layer reuses `GraphInlinePropertiesLayer.qml`, suppresses paired-port duplicate labels, and hides during node-global collapse without changing per-group state.
- Decorator-defined Python Script controls arrive here as ordinary resolved `PropertySpec` and `SettingsGroupSpec` records. Reuse the existing inline editors and paired-port override facts; do not add a Python-Script-specific QML control or editor route.
- Active settings transitions refresh incident edge snapshots immediately so Canvas-painted and retained wires match the current socket frame; other geometry retains the existing scheduled redraw path. Tests must compare renderer snapshots/items and sampled painted wire pixels as well as fresh anchor calculations, since deferred paint can otherwise lag by one frame.
- `GraphNodePortsLayer.qml` owns metadata-driven dynamic-group state/scheduling, Add controls, mutations, aggregate interactive rectangles, and context/edit coordination; `GraphNodePortRow.qml` owns the shared per-port Remove control, label/editor, grip interaction, and interactive rectangles. The two direct Repeater instances retain only their real direction-specific slash/default/padlock/inactive-tooltip children. Inline controls require a writable graph, an unlocked expanded node, and zoom `>= 0.95`; node/port context menus retain low-zoom and zero-port access. Connector and action hit targets stay separate, dynamic controls use 26 px interaction targets with tooltips, Tab focus/keyboard activation, and accessible names, and no node-specific port editor or standalone reorder action exists.
- Display-mode `GraphRichTextBlock.qml` prose should not publish an embedded rect for ordinary text. Let host single-click/drag/double-click routing stay active through the normal text bounds, and publish the full editor rect only while editing. `corex-link:` markdown is the exception that may publish a display pointer target for hover/open behavior.
- `passive.annotation.text` uses `GraphRichTextBlock.qml`'s rendered/editor content measurement to auto-fit height. Its resize handles accept horizontal movement only; live editing and width drags preview the measured height before the normal resize finish commits geometry.
- Host-themed searchable combos should mirror inspector autocomplete behavior while publishing their input rectangle through `embeddedInteractiveRects`, so typing and dropdown interaction do not become canvas drag/zoom gestures.
- Keep inline dropdown popup sizing and pointer-state feedback in `GraphSurfaceComboBox.qml` and `GraphSurfaceSearchableComboBox.qml`; both shared controls own compact popup row height, popup width, scroll limits, delegate padding, hover visuals, and press visuals for current and future surface dropdowns.
- Standard one-line text, number, path, enum, and color controls publish `textFitWidth`; `GraphInlinePropertiesLayer.qml` combines the widest eligible row with stable label and row chrome for right-handle fit-to-displayed-text. Path measurement follows the current filename/full-path display mode without changing it. Toggle, textarea, rich, and custom surfaces do not participate.
- Source-storage dropdowns use `SourceStorageModeUtils.js` for the shared `temp://` / `saved://` equals Internal rule. Keep that helper aligned with inspector `path_current_source_mode` projection and floating-toolbar `source_storage` popovers.
- The boolean inline editor (`GraphSurfaceCheckBox.qml`) renders as a pill toggle switch but keeps its `CheckBox` base, `controlStarted`, and the `resolvedIndicatorFillColor`/`resolvedIndicatorBorderColor` checked→accent semantics pinned by `tests/qml_quick/tst_graph_surface_controls.qml`. `data.boolean_toggle` reuses it inside `GraphBooleanToggleSurface.qml`; its real-host geometry and commit path are pinned by `tests/test_boolean_toggle_surface.py`.
- Boolean Toggle, Number Slider, Panel, and Select declarations live in the inert
  reserved function source. Keep normalization, warnings, and size-resolver side
  effects in `nodes/builtins/data_control.py`; bootstrap must import that helper
  module even though it no longer contributes descriptors.
- The four compact-pill surfaces—Boolean Toggle, Number Slider, Select, and Trigger—derive their node width from the full title instead of eliding the label. A rename may grow or shrink the pill, shifts `x` left or right to preserve the node's right edge, and reaches history/persistence as one atomic title-plus-geometry mutation rather than a follow-up resize entry.
- `GraphCanvasSurfaceEditorOverlays.qml` is the one canvas owner for Web Address, Timestamp, Number Slider, Select, and Panel host/open state, placement, surface Connections, outside-click cancellation, and commit/cancel callbacks. Its root is the existing `webPageAddressOverlayLayer`; the four other exact layer Items live inside it. `GraphCanvasRootLayers.qml` retains only live aliases plus `openSurfaceActionOverlayForHost(...)` delegation, so no second overlay state exists.
- `data.select` reuses `GraphSurfaceComboBox.qml` and `GraphSurfaceButton.qml` in `GraphSelectSurface.qml`. Both controls publish embedded interactive rectangles, while the compact title reuses the shared node-help tooltip text and policy. The gear action opens `GraphSelectSettingsPopover.qml` through the shared surface-editor overlay owner; row/header checks support protected multi-delete, a single checked row can move up/down without losing its checked state, Cancel/close stay draft-only, and OK commits ordered Name/Value options plus `selected_index` in one undoable property-map mutation. `tests/test_select_surface.py` owns the real-host dropdown, tooltip, elapsed suppression, and real-canvas dialog paths.
- `data.panel` renders through `GraphPanelSurface.qml` and opens `GraphPanelEditorPopover.qml` through the shared surface-editor overlay owner after `GraphNodeHost.dispatchSurfaceAction("panel_edit")`; setting only the surface-local editor flag does not open the canvas overlay. Display mode publishes no embedded interactive rectangle, preserving node select/drag gestures. Populated Data mode adds a local double-tap handler inside its `ListView`, because the flickable otherwise consumes the host gesture. The compact editor keeps Text/Data, multiline value, and Auto-resize changes in a draft; Cancel or Escape discards them and OK or Enter commits the complete property map once. Shift+Enter inserts a line break.
- `core.trigger` reuses `GraphSurfaceButton.qml` in `GraphTriggerSurface.qml` as a centered, rename-following click button (no name section or divider). The button publishes its embedded interactive rectangle, carries the shared node-help tooltip, and emits `host.triggerNodeRequested` instead of a property commit. Real-host geometry, tooltip, and click routing are pinned by `tests/test_trigger_surface.py`.
- The `"slider"` inline editor (`GraphSurfaceSlider.qml`) requires `PropertySpec.minimum`/`maximum` (int/float property, optional `step`; validated in `nodes/registry.py`) and projects those roles through `ui/support/node_presentation.py::build_inline_property_items`. It commits on release only (one `inlinePropertyCommitted` = one undo entry); `GraphInlinePropertiesLayer.qml` restores payload value updates via a `Binding` gated on `!pressed` because interactive sliders break declarative value bindings.
- `prop_interval_1d(...)` projects `inline_editor="interval_slider"` into the shared `GraphSurfaceIntervalSlider.qml`; increasing declarations place Start left/End right, decreasing declarations preserve their semantic order while mapping physical handles, and a local drag never changes the authored direction. The shared graph and Inspector controls consume `display_value`, `display_value_available`, `editor_enabled`, and `interval_direction`; do not create a per-node range editor. `searchable=True` selects `GraphSurfaceSearchableComboBox.qml`, while ordinary enums stay on `GraphSurfaceComboBox.qml`.
- The `secret` editor projects redacted state into shared `SecretEditor.qml`; graph and Inspector callers expose masked Replace/Clear actions only and commit through dedicated secret bridge methods. Never prefill the field or route plaintext through the generic property setter.
- Text annotation font family uses the shared QML font-family options helper in both the inspector's `font_family` editor and the floating toolbar's searchable `font_family` popover.
- `tests/qml_quick/tst_graph_surface_controls.qml` owns the pure-QML floating-toolbar and selection-envelope checks alongside the shared controls. `tests/test_graph_surface_input_controls.py` continues to own Python bridge, model, payload, source, and provider facts; do not restore per-test `QQmlEngine` wrappers there for behavior already covered by QuickTest.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_inline.py tests/graph_surface/inline_editor_suite.py tests/test_graph_surface_input_controls.py --ignore=venv -q
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui --dry-run
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_surface_controls.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m pytest tests/test_boolean_toggle_surface.py tests/graph_surface/number_slider_suite.py tests/test_select_surface.py tests/test_trigger_surface.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_panel_surface.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_sensitive_property_controls.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_surface/passive_host_interaction_suite.py --ignore=venv -q
```

Mechanical's production adoption is locked by `tests/mechanical_catalogue/test_controls.py` (52 typed inputs, 22 outputs, named groups and contextual disabled states) and `tests/mechanical_catalogue/test_visuals.py` (real GraphCanvas/GraphSceneBridge clicks, connected anchors, keyboard editors and display-attached render matrices).
Fresh grouped-node expansion defaults are declaration metadata on `NodeTypeSpec`; the normal type-creation path initializes them once, while graph persistence/fragments retain explicit instance state. Mechanical expands each primary section and keeps each advanced section collapsed without QML or type-ID branches.

## Breadcrumbs
- [Passive Surface Loading And Contracts](passive_surface_loading_contracts.md)
- [Graph Canvas Input Layers](graph_canvas_input_layers.md)
- [SSH/SFTP Nodes](ssh_sftp_nodes.md)

## Update Triggers
Update when inline edit controls, shared dynamic-port controls or geometry, scalar/Interval 1D/secret editors, compact-pill title sizing, searchable surface controls, interactive region contracts, surface editors, inline tests, or Help reference editor-control coverage change.
