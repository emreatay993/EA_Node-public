# Media Viewer Content Fullscreen QA Matrix

- Updated: `2026-09-07`
- Scope: shell-owned content fullscreen for Media Panel and supported viewer surfaces, including Model Viewer retargeting and cleanup.

## Locked Scope

- Content fullscreen is a transient in-app shell overlay and is never persisted to `.cxproj`.
- Media and viewer entry points use surface buttons and `F11`; `Esc`, `F11`, and the close button exit.
- Live Model Viewer fullscreen retargets the existing native widget and restores it to the node viewport without creating a second widget.

## Current Automated Verification

| Coverage Area | Requirement Anchors | Command | Status |
|---|---|---|---|
| Fullscreen bridge and media projection | `REQ-UI-040` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_media_panel_qml_surface.py --ignore=venv -q` | `NOT RUN` |
| Surface controls and viewer retargeting | `REQ-UI-040`, `REQ-QA-039` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_controls.py tests/test_viewer_surface_contract.py tests/test_viewer_host_service.py tests/test_embedded_viewer_overlay_manager.py --ignore=venv -q` | `NOT RUN` |

## Manual Desktop Checks

1. Open image, PDF, and video Media Panel fullscreen and verify the expected renderer, controls, and close paths.
2. Activate Model Viewer, enter fullscreen, and verify the same native widget returns inline with camera and selection state preserved.
3. Delete the viewer node or switch workspace while live and verify no orphaned overlay remains.

## Residual Risks

- Real PyVista/VTK/QtInteractor behavior and media visual quality still require native desktop validation.
