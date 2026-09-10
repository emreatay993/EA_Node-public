# Web Assets, Web Host, Chromium, And Excalidraw

## Purpose
Use this for local web assets, the web host, Chromium website viewer nodes, Excalidraw host/editor, and related generated bundles.

## Start Here
- `ea_node_editor/nodes/builtins/web_viewer.py`
- `ea_node_editor/web_assets/`
- `ea_node_editor/web_host/`
- `ea_node_editor/nodes/builtins/excalidraw.py`
- `ea_node_editor/ui_qml/components/web/`
- `web/excalidraw_host/`

## Do Not Start Here
- Remote URLs in generated bundles; local bundles must remain self-contained.
- Generic viewer route before checking WebEngine/web host specifics.

## Common Changes
- Rebuild Excalidraw host assets with the repo script when web host sources change.
- Keep web viewer node metadata aligned with QML/web bridge surfaces.
- Validate generated assets do not introduce remote URL references.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_corex_web_host_assets.py tests/test_corex_web_surface_bridge.py --ignore=venv -q
```

## Breadcrumbs
- [Web Viewer And Chromium Website Node](../feature_routes/web_viewer_chromium_node.md)
- [Excalidraw Web Host And Real Editor](../feature_routes/excalidraw_web_host_real_editor.md)

## Update Triggers
Update when web host assets, Excalidraw bundle rules, Chromium viewer nodes, or web component routes change.
