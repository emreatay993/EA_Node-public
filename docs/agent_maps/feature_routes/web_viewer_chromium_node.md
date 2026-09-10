# Web Viewer And Chromium Website Node

## Purpose
Use this for Chromium website viewer nodes, web host services, web surface bridge behavior, and web QML components.

## Start Here
- `ea_node_editor/nodes/builtins/web_viewer.py`
- `ea_node_editor/web_host/`
- `ea_node_editor/ui_qml/components/web/`
- `ea_node_editor/ui_qml/components/web/WebPageAddressPopover.qml`
- `ea_node_editor/ui_qml/components/web/WebPageDetachedWindow.qml`
- `ea_node_editor/ui_qml/components/web/WebPageHost.qml`
- `ea_node_editor/ui_qml/components/web/WebPageRetentionStore.qml`
- `ea_node_editor/ui_qml/components/web/WebPageStatusPane.qml`
- `ea_node_editor/ui_qml/components/web/WebPageToolbar.qml`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui/shell/host_presenter.py`
- `ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardPreviewViewport.qml`

## Notes
- `web.page_viewer` local HTML internal copies use `start_location` project artifact refs (`temp://` / `saved://`) and resolve them to local `file://` URLs only for WebEngine loading.
- Shared canvas paste/drop import creates `web.page_viewer` nodes by setting `start_location` for local HTML files, non-media HTTP(S) URLs, and rich clipboard links with exactly one remote `href`. General browser-selected HTML snippets stay text annotations even when the clipboard also carries a source-page URL. Ask mode retains the useful URL/text/media alternatives through `CanvasImportController`; URL strings never pass through filesystem path resolution.
- Graph-surface Local HTML storage actions reuse the media source storage popover and `browseNodePropertyPath(..., source_mode)`. Checked state is value-derived with `SourceStorageModeUtils.js`: `temp://` and `saved://` refs show Internal, other values show External. `ShellInspectorPresenter` must explicitly allow `managed_copy` / `external_link` for `web.page_viewer.start_location`; do not depend on file-repair tracking for this property because it can also hold remote URLs.
- `display_mode` is web-specific: `responsive` keeps the WebEngine viewport at browser-default zoom; graph-inline `fit_width` also stays at native zoom so pages remain readable and reflow or scroll inside the card; `fit_page` and non-graph `fit_width` compute document metrics from the live WebEngine page and apply zoom. Keep it separate from image/video `fit_mode` semantics.
- Local HTML browse filters are declared on the Web Page Viewer's `start_location` `PropertySpec.file_filter`; keep shell browse forwarding generic.
- Graph-surface Web Page Viewer exposes the same floating-toolbar content-only/title/frame chrome toggles as media panels, backed by hidden `show_title` / `show_frame` properties and `GraphNodeHostLayout.qml` host chrome state.
- Web Page Viewer fullscreen should not create a second browser when the graph surface already has a live page. `WebPageHost.qml` exposes `attachWebEngineToFullscreen(...)` / `releaseFullscreenWebEngine()` for the overlay to borrow the existing WebEngine item; `ContentFullscreenOverlay.qml` only falls back to its own fullscreen `WebPageHost` when no matching live graph host can be borrowed.
- Web Page Viewer detach should also move, not clone, a live graph browser. `WebPageHost.qml` exposes `attachWebEngineToDetached(...)` / `releaseDetachedWebEngine()`; `WebPageDetachedWindow.qml` borrows the live `WebEngineView`, shows a detached placeholder on the canvas, and only uses a standalone detached host for cold opens where no live graph browser exists.
- Workspace switching should not reload visible graph Web Page Viewer cards. `GraphCanvasStateBridge.scene_workspace_changing` opens the parking window before visible delegates are cleared; `GraphCanvasRootLayers.qml` owns a `WebPageRetentionStore` above node delegates; `WebPageHost.qml` parks live graph `WebEngineView` items there during workspace switches, pauses/mutes them while hidden, and reclaims them by `(workspace_id, node_id)` when the same visible node is recreated. Keep this live-session retention separate from `.cxproj` persistence and from `browser_state` URL/zoom storage.
- Canvas/project-review export should not grab an empty web card immediately after a workspace switch. `GraphCanvasRootLayers.exportCanvasBasePng(...)` asks visible `WebPageHost.qml` surfaces to prepare for export, waits a short web-settle window, and lets the host show its hidden `preview_ref` image through `image://local-media-preview` when WebEngine is unavailable or still loading.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py tests/test_web_page_retention_store.py tests/test_web_page_viewer_node.py tests/test_corex_web_host_assets.py --ignore=venv -q
```

## Breadcrumbs
- [Web Assets, Web Host, Chromium, And Excalidraw](../subsystems/web_assets_host_chromium_excalidraw.md)
- [Excalidraw Web Host And Real Editor](excalidraw_web_host_real_editor.md)

## Update Triggers
Update when web node definitions, local HTML browse filters, web host bridge APIs, web components, or web tests change.
