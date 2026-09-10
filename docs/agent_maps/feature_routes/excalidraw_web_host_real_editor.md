# Excalidraw Web Host And Real Editor

## Purpose
Use this for Excalidraw host assets, real local/offline editor integration, web bundle rebuilds, and Excalidraw node behavior.

## Start Here
- `ea_node_editor/nodes/builtins/excalidraw.py`
- `web/excalidraw_host/`
- `ea_node_editor/web_assets/excalidraw_host/`
- `ea_node_editor/ui_qml/components/graph/passive/GraphWebBoardSurface.qml`
- `ea_node_editor/ui_qml/components/web/WebEditorHost.qml`
- `scripts/build_excalidraw_host.ps1`
- `tests/test_corex_web_surface_bridge.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py --ignore=venv -q
.\scripts\build_excalidraw_host.ps1
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py --ignore=venv -q
```

## Breadcrumbs
- [Web Assets, Web Host, Chromium, And Excalidraw](../subsystems/web_assets_host_chromium_excalidraw.md)
- [Web Viewer And Chromium Website Node](web_viewer_chromium_node.md)

## Update Triggers
Update when Excalidraw source assets, generated bundles, offline URL rules, or Excalidraw node behavior changes.
