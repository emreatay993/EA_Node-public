# Shared Graph Typography

## Purpose
Use this for shared typography controls, node header text, flow-edge labels and inline label editors, passive surface text, graph style presets, and typography QA evidence.

## Start Here
- `ea_node_editor/ui_qml/components/graph/GraphSharedTypography.qml`
- `ea_node_editor/ui_qml/components/common/FontFamilyOptions.js`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHeaderLayer.qml`
- `ea_node_editor/ui_qml/components/graph/EdgeFlowLabelLayer.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphEdgeFloatingToolbar.qml`
- `ea_node_editor/ui_qml/components/graph/passive/`
- `ea_node_editor/graph_theme_defaults.py`
- `ea_node_editor/passive_style_normalization.py`
- `ea_node_editor/text_style.py`
- `ea_node_editor/app.py`
- `ea_node_editor/assets/fonts/`

## Notes
- Warning/error circles straddle the upper-right node border and reserve no title width. The shared header keeps title/icon sizing independent of diagnostics; the persistent-diagnostic host probe covers full titles at 8–50px label sizes and clamps undersized saved widths.
- `GraphRichTextBlock.qml` is the canonical reusable markdown/plain rendering, source editing, style toolbar, and style copy/paste owner for prose-oriented passive graph text.
- Bare annotation text stores whole-object text properties as node properties and normalizes shared text settings through `text_style.py`; `GraphBareTextSurface.qml` is now a thin wrapper around the reusable rich-text block.
- Bare annotation text does not expose the generic passive `visual_style` context actions; its colors and typography stay on the property-owned floating-toolbar path.
- Annotation note body/subtitle, planning card body, and non-timestamp flowchart body/cube text use prefixed rich-text slot fields such as `body_format`, `body_font_size`, and `body_text_color`. Groups have no rich-text slot fields.
- Existing non-bare prose slots default to `plain` format and inherited visual style sentinels so old literal markdown-like text and passive style authority stay stable until users change rich-text style.
- Bare annotation text defaults to centered horizontal alignment and middle vertical alignment; its inline editor should preserve the same visual alignment when editing.
- New bare annotation Text nodes default to the bundled Caveat family; existing nodes retain their saved font family, and an empty legacy family still follows Qt's application font.
- Empty bare-text `text_color` means auto; `GraphBareTextSurface.qml` chooses black or white from the current canvas background variant/theme color.
- `GraphBareTextSurface.qml` follows the node-title text path by using the host `nodeTextRenderType` (`Text.CurveRendering`) and Qt's application font when no explicit font family is set.
- App-created inline node links are Markdown anchors with `corex-link:<link_id>` hrefs. `GraphRichTextBlock.qml` detects those anchors for shared node-link hover/open behavior and should leave ordinary Markdown links on the existing path.
- `GraphRichTextBlock.qml` keeps display-mode prose drag-friendly by omitting ordinary text from `embeddedInteractiveRects` until the editor is visible. Host double-click still enters editing through the normal text bounds, while `corex-link:` text keeps a display pointer target so link hover cards and opening still work.
- Bare annotation text exposes common whole-object typography controls through grouped floating-toolbar popovers for size, font family, emphasis, markdown list formatting, alignment, wrapping, and color; the size popover supports validated integer entry, slider control, and 1-point steppers, and font-family options come from the shared QML font-family helper with a Default clear option.
- Text style copy/paste uses `normalize_text_annotation_style_payload` and copies visual typography/color/layout properties only, excluding text content and markdown/plain format; reusable rich-text slots map those copied logical style keys to their prefixed node-property keys.
- Recent text colors are app-wide graphics typography preferences, not project `.cxproj` state.
- Graph-node header titles, inline labels, driven-by-input helper labels, badges, and locked-placeholder text/icons should consume `host.graphSharedTypography` roles. Do not add hardcoded graph label or node title icon pixel sizes in new node-surface QML; use `nodeTitlePixelSize`, `nodeTitleIconPixelSize`, `inlinePropertyPixelSize`, `badgePixelSize`, or `badgeIconPixelSize` as appropriate.
- Targeted graph-scene payload refresh paths must pass the active `graph_theme_bridge` and resolve graph typography through `_graph_label_pixel_size(...)` / `_graph_node_icon_pixel_size(...)`, matching full scene rebuilds.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_passive_style_dialogs.py tests/test_flowchart_visual_polish.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py -k "typography or toolbar" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py tests/test_group_backdrop_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_main_bootstrap.py tests/test_text_style_normalization.py tests/test_passive_node_contracts.py tests/test_packaging_configuration.py --ignore=venv -q
```

## Breadcrumbs
- [Graphics Settings, Themes, And Preferences](graphics_settings_themes_preferences.md)
- [Passive Surface Loading And Contracts](passive_surface_loading_contracts.md)
- [Durable Node Linking](durable_node_linking.md)

## Update Triggers
Update when typography tokens, app-owned font families, graph text rendering, reusable rich-text slot fields, `corex-link:` inline link handling, passive style normalization, or typography tests change.
