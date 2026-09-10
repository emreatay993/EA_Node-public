# Passive, Media, And Tabular Surfaces

## Purpose
Use this for passive node QML surfaces, media/image/video/PDF/mail panels, tabular preview surfaces, and surface contracts.

## Start Here
- `ea_node_editor/ui_qml/surface_contracts.py`
- `ea_node_editor/ui_qml/graph_surface_metrics.py`
- `ea_node_editor/ui_qml/components/graph/passive/`
- `ea_node_editor/ui_qml/components/graph/surface_controls/`
- `ea_node_editor/ui_qml/components/graph/tabular/`
- `ea_node_editor/ui/mail_preview_provider.py`
- `ea_node_editor/passive_style_normalization.py`
- `ea_node_editor/text_style.py`
- `ea_node_editor/ui/media_panel_source.py` for current Media Panel source/mode resolution.
- `ea_node_editor/ui/media_video_state.py` for canonical Python video state.
- `ea_node_editor/ui_qml/components/graph/passive/GraphMediaVideoPlaybackCore.qml` for shared per-renderer video playback.

## Do Not Start Here
- Graph model internals for visual-only passive surface changes.
- Add-on loader code for tabular QML rendering-only changes.

## Common Changes
- Keep surface metric contracts and QML surface geometry aligned.
- Reusable passive prose text uses `GraphRichTextBlock.qml` for markdown/plain rendering, source editing, grouped typography popovers, searchable font-family selection, and Text-only internal style copy/paste. `GraphBareTextSurface.qml` wraps that shared block for the chrome-free annotation text node.
- `GraphRichTextBlock.qml` also owns app-created `corex-link:<link_id>` Markdown anchors for node-link hover/open behavior and delete unwrap while preserving ordinary user Markdown links.
- Rich-text slot fields are real node properties on adopter nodes: existing non-bare prose defaults to `plain` plus inherited style sentinels, while bare annotation text keeps its existing unprefixed `format` and style properties.
- Flowchart silhouettes are shared by graph nodes, drop previews, and passive library previews through `FlowchartShapeCanvas.qml`; update the metric JSON/JS contract, Python surface geometry, body-fallback behavior in `GraphFlowchartNodeSurface.qml`, and visual-polish tests when adding variants.
- Passive node `visual_style` gradients are normalized in `passive_style_normalization.py` and the passive style dialog; flowchart shapes consume the resolved body gradient through `FlowchartShapeCanvas.qml`.
- Route input-capable passive surfaces through surface controls and input layers.
- Panel Text/Data rendering lives in `GraphPanelSurface.qml`: keep its reference table alignment, 12 pt authored font semantics, authored-versus-connected copy source, empty/default sizing, content-driven auto-fit, DATA-mode host drag/wheel-scroll separation, and compact root-layer editor pinned by `tests/test_panel_surface.py`.
- For tabular surfaces, coordinate add-on data model, preview-provider selector payloads, add-on-owned property edit adapters, and QML preview routes; `selected_object` persists the sheet/key/dataset picker value, and selected table columns persist through `tabular_selected_columns` from inline/fullscreen column-selection UI.
- Tabular previews are async on cold caches: `GraphTabularPreviewSurface.qml` holds `previewPayload` as a refreshed property (nodeData change, late canvas/command bridge availability, plus a retry timer while `state === "loading"` or the bridge placeholder is retryable), and `TabularFullscreenSurface.qml` keeps the current rows on a `loading` window response and applies the worker result from the bridge's `tabularWindowReady` signal. Don't reintroduce synchronous describe bindings that can convert sources on the UI thread.
- Path source editors that support both `managed_copy` and `external_link` expose a Source storage dropdown and route through the shared shell path browse bridge; this includes the input-hidden Media Panel `source` property and Tabular Input's `path` property. Current storage is value-derived: blank/external paths show External, while `temp://` and `saved://` refs show Internal. Media Panel exposes `internalizeSource` only in Browse authority; input exposure disables source editing and replacement.
- Floating-toolbar chrome actions (`toggle_content_only`, `toggle_title`, `toggle_frame`) use hidden `show_title` / `show_frame` properties and the host chrome path. Media image transform/aspect/crop actions live in `GraphMediaImageRenderer.qml`, PDF page controls in `GraphMediaPdfRenderer.qml`, and shared video playback/seek/clip/bookmark/primer behavior in `GraphMediaVideoPlaybackCore.qml`; inline/fullscreen renderers retain host-specific actions and the dispatcher owns common source/exposure/fullscreen actions.
- Media Panel video bookmarks, clip range, capture, timestamp, and trim controls use the unified hidden settings superset plus `MediaPanelActionService`-created staged outputs. Copy/capture create input-hidden `media.panel` nodes, while Replace is denied whenever Source input is exposed.
- Mail Panel previews keep the original `.eml`, `.msg`, or `.oft` as the source path and render provider-generated HTML through `GraphMailPanelSurface.qml`; `.msg` and `.oft` rich export depends on Outlook COM on Windows and should surface an unavailable/error state rather than storing preview artifacts in `.cxproj`. Fullscreen Mail renders the generated preview URL through `ContentFullscreenOverlay.qml` with Page/Width/100% zoom controls; inline Mail WebEngine stays render-only so host drag/select/resize remains available.
- OS clipboard paste creates populated input-hidden Media Panels for image/PDF/video sources, while `.eml`/`.msg`/`.oft` remains `passive.media.mail_panel`; tabular and annotation routing is unchanged.
- Media Panel PDF page-count refresh/navigation clamps view requests in the renderer/fullscreen routes without rewriting the authored `page_number`. Fullscreen reader controls live in `ContentFullscreenOverlay.qml`.
- `pdf_preview_provider.render_pdf_page_image(...)` is the Python rendering helper for non-QML consumers such as Project Review Deck export; pass the Media Panel's authored `page_number` and let preview metadata clamp the resolved page.
- `GraphSurfaceSearchableComboBox.qml` is the host-themed autocomplete control used by tabular selection-required surfaces; keep its embedded interactive rects aligned with other surface controls.
- `GraphNativeExplorerSurface.qml` rows expose a Windows-style right-click menu (`graphFolderExplorerRowContextMenu`): Open / Open with... plus reused non-destructive actions (Copy Path, Open in New Classic Explorer, Send to COREX as Path Pointer, Properties). Open/Open-with dispatch `folder_explorer_open` / `folder_explorer_open_with` through `_requestAction`; the OS launch itself is centralized in `ea_node_editor/platform_open.py`. Open-with is hidden for folders and the `..` row.
- `ea_node_editor/ui/dialogs/input_reference_dialog.py` documents user-facing passive/media/tabular surface gestures; update it when crop, video, folder explorer, table, or fullscreen controls change.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_passive_graph_surface_host.py tests/test_media_panel_qml_surface.py tests/test_passive_image_nodes.py tests/test_passive_node_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_media_panel.py tests/test_media_panel_source_resolution.py tests/test_media_video_state.py tests/test_content_fullscreen_bridge.py tests/test_video_trim.py tests/test_tabular_input_node.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_project_review_deck.py tests/test_pdf_preview_provider.py tests/test_mail_preview_provider.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py tests/graph_surface/passive_host_interaction_suite.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flowchart_surfaces.py tests/test_flowchart_visual_polish.py --ignore=venv -q
```

## Breadcrumbs
- [Passive Surface Loading And Contracts](../feature_routes/passive_surface_loading_contracts.md)
- [Surface Input And Inline Controls](../feature_routes/surface_input_and_inline_controls.md)
- [Media, Image, Video, PDF, And Mail Nodes](../feature_routes/media_image_video_pdf_refocus.md)
- [Tabular Data Add-on And Preview](../feature_routes/tabular_data_addon_preview.md)
- [Durable Node Linking](../feature_routes/durable_node_linking.md)

## Update Triggers
Update when passive surface contracts, rich-text `corex-link:` behavior, flowchart silhouettes/metrics, media/tabular QML, PDF/mail preview providers, tabular clipboard paste behavior, tabular property edit adapters, tabular selection persistence, surface controls, passive tests, or Help reference surface-control coverage change.

## 2026-07-11 Performance Ownership

- `.txt` delimiter sniffing reads at most `4096` characters. Mail preview owns a bounded stamp-keyed LRU; PDF caching remains intentionally outside this program.
