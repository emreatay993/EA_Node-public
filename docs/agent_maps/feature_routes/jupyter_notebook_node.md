# Jupyter Notebook Node

## Purpose
Use this for the `code.jupyter_notebook` canvas node: embedded Jupyter server lifecycle, the notebook surface + server-ready bridge, and `.ipynb` artifact persistence. Architecturally it is "the `web.page_viewer` node whose embedded `WebEngineView` points at a project-scoped local Jupyter server instead of an arbitrary URL".

## Start Here
- `ea_node_editor/nodes/builtins/jupyter_notebook.py`
- `ea_node_editor/jupyter_host/`
- `ea_node_editor/ui_qml/jupyter_server_bridge.py`
- `ea_node_editor/ui_qml/components/graph/jupyter/GraphJupyterNotebookSurface.qml`
- `ea_node_editor/ui_qml/graph_scene_payload/kinds/jupyter.py`
- `ea_node_editor/ui_qml/graph_scene_payload/fullscreen.py`
- `ea_node_editor/ui_qml/surface_contracts.py`
- `ea_node_editor/ui/shell/composition/runtime_services.py`
- `ea_node_editor/ui/shell/controllers/project_session_controller.py`
- `ea_node_editor/ui/shell/controllers/project_session_services_support/project_files_service.py`

## Notes
- The embedded server runs as a SEPARATE subprocess (`python -m jupyter_server`, loopback + token), never imported into the Qt process. `JupyterServerManager`/`JupyterServerRegistry` own one server per project root (server root = project staging dir); teardown is wired in `window.py` `_teardown_qml_surface` plus an `atexit` fallback.
- The tokened localhost URL is built at runtime and is NEVER persisted — only the `.ipynb` `notebook_ref` (a `temp://`/`saved://` artifact ref) is. So reopening a project rebuilds the URL against a fresh session/token.
- The INLINE graph payload's resolved notebook path is empty for managed/staged refs (the contributor has no project context — same as the web viewer). So the surface passes `notebook_ref` to `JupyterServerBridge.ensureServer`, and the BRIDGE resolves it via `shell_window.project_path` + `model.project.metadata` → `ProjectArtifactResolver`. Do not rely on a resolved path in the inline payload.
- Server start blocks ~seconds on a health poll, so the bridge resolves the ref on the UI thread then starts the server on a `QThreadPool` worker, returning the URL via a queued `serverReady(node_id, url)` signal (`serverFailed` on error).
- Create-new rides the same managed-artifact pipeline as open-existing: `composition/runtime_services.py` injects `ProjectSessionController.create_blank_notebook_artifact(...)` into `JupyterServerBridge`; the controller delegates to `ProjectFilesService`, which stages a blank `nbformat` v4 notebook and returns a `temp://` ref. The surface commits it via `host.inlinePropertyCommitted`. Staged refs resolve through a staging-root hint set by `ensure_staging_root` and persisted into project metadata.
- `surface_family="jupyter"` is registry-validated — it must be in `NodeRegistry._SUPPORTED_SURFACE_FAMILIES` (and the `SurfaceFamily` Literal), not just the surface-contracts dispatch.
- The icon `"code"` is a symbolic name resolved by `icon_registry.py` `_ICON_SPECS` in the library palette; passive nodes suppress the title icon, so no `node_title_icons` asset is needed.
- Graceful degradation: the node always registers. When `check_jupyter_available()` / `check_webengine_available()` is false, or no notebook is selected, the surface shows a status pane (no `WebEngineView`).
- Fullscreen is a live-view handoff, not a second browser session: `GraphJupyterNotebookSurface.qml` exposes the standard surface fullscreen action plus `attachWebEngineToFullscreen` / `releaseFullscreenWebEngine`, and `ContentFullscreenOverlay.qml` borrows the inline `WebEngineView` for `content_kind="jupyter_notebook"`. Cold fullscreen without a ready inline notebook deliberately shows a non-browser placeholder rather than starting another Jupyter frontend.
- Frozen-build caveat: the server cannot launch `python -m jupyter_server` against the bundled exe; a frozen build needs a configured external interpreter with the Jupyter stack, otherwise the surface degrades to "Jupyter unavailable".

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_jupyter_notebook_node.py tests/test_jupyter_server_manager.py tests/test_jupyter_server_bridge.py tests/test_jupyter_notebook_surface.py tests/test_jupyter_create_blank.py --ignore=venv -q
```

## Breadcrumbs
- [Web Viewer And Chromium Website Node](web_viewer_chromium_node.md)
- [Media Image Video PDF Refocus](media_image_video_pdf_refocus.md)

## Update Triggers
Update when the Jupyter node spec, server manager lifecycle, server-ready bridge API, notebook surface, or `.ipynb` persistence/staging changes.

## 2026-07-11 Performance Ownership

- The Jupyter bridge remains stable at startup; server/worker internals allocate once on first notebook use and shutdown remains safe before initialization.
