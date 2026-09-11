# Excalidraw Web Host And Real Editor

## Purpose
Use this for Excalidraw host assets, real local/offline editor integration, web bundle rebuilds, and Excalidraw node behavior.

## Start Here
- `ea_node_editor/nodes/builtins/excalidraw.py`
- `web/excalidraw_host/`
- `web/excalidraw_host/src/snapshot-controller.ts`
- `ea_node_editor/web_assets/excalidraw_host/`
- `ea_node_editor/common/board_snapshot.py`
- `ea_node_editor/web_host/bridge.py`
- `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
- `ea_node_editor/ui_qml/board_snapshot_sessions.py`
- `ea_node_editor/ui_qml/graph_scene_payload/kinds/excalidraw.py`
- `ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardSurface.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardPreviewViewport.qml`
- `ea_node_editor/ui_qml/components/web/WebEditorHost.qml`
- `scripts/build_excalidraw_host.ps1`
- `tests/test_corex_web_surface_bridge.py`
- `tests/test_content_fullscreen_bridge.py`
- `web/excalidraw_host/tests/snapshot-controller.test.ts`

## Snapshot Lifecycle
- `SnapshotController` owns the idle debounce, independent scene save, one in-flight export, timeout, retry, and close completion. It exports a PNG through the editor library with a maximum edge of 2048 pixels; no secondary renderer approximates drawing elements.
- `_FullscreenWebSurfaceBridge` gates saves and snapshot commits by revision and attempt. The WebChannel endpoint is `commit_snapshot`; keep it distinct from the base artifact bridge's `export_preview` Qt slot to avoid inherited overload dispatch bypassing the revision gate.
- The artifact bridge decodes and validates the PNG before staging. Snapshot publication participates in artifact rollback, and saves are acknowledged only after the owning graph accepts the drawing. Failed commits preserve drawing state and existing artifact bytes.
- Normal close waits for the current drawing and snapshot. After an error, explicit save-and-close-without-preview or save-and-reload actions first require the current drawing to reach the graph. A never-started editor can exit natively; a terminated renderer offers explicit recovery from the saved drawing. Retired bridge slots and callbacks cannot mutate or close a later editor.
- `board_scene_digest` identifies visual content across temporary-to-saved artifact promotion and editor-only metadata changes. The payload contributor publishes whether the stored preview matches the current drawing.
- `board_snapshot_sessions.py` owns live progress identity by editor session, workspace object, and node. Restored or retired progress becomes actionable unavailable state rather than showing an indefinite update.
- Canvas previews use native QML `Image` only. An edit hides the old image immediately; updating, empty, and unavailable states remain explicit. Missing/corrupt images expose **Open editor to retry**. An older artifact may remain stored for recovery but is never displayed as current.
- Keep active editor lifetime stable across content-equivalent project saves; intentional project/node teardown still releases the host. No node-port or execution contract is owned by this snapshot path.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py --ignore=venv -q
.\scripts\build_excalidraw_host.ps1
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_content_fullscreen_bridge_lifecycle.py --ignore=venv -q
node --experimental-transform-types --test web/excalidraw_host/tests/snapshot-controller.test.ts
```

The standalone controller tests use Node's type transformation (verified with Node 24).

`tests/graph_surface/p03_passive_host_entrypoint_suite.py` owns actual QML checks for current, stale, updating, empty, missing, and corrupt previews. A real WebChannel probe is needed when changing Qt slot dispatch; direct Python calls do not prove which inherited slot Chromium invokes.

## Breadcrumbs
- [Web Assets, Web Host, Chromium, And Excalidraw](../subsystems/web_assets_host_chromium_excalidraw.md)
- [Web Viewer And Chromium Website Node](web_viewer_chromium_node.md)

## Update Triggers
Update when Excalidraw source assets, generated bundles, offline URL rules, or Excalidraw node behavior changes.
