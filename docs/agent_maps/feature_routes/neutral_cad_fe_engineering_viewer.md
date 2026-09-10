# Neutral CAD/FE Engineering Viewer

## Purpose
Use this route for neutral engineering geometry, prepared scenes, viewer
sessions, selection, clipping, export, and the shared fullscreen/detached host.

## Lookup Aliases
- `viewer settings expansion`

## Start Here
- `ea_node_editor/nodes/builtin_functions/engineering_imports.py`
- `ea_node_editor/nodes/builtin_functions/engineering_viewer.py`
- `ea_node_editor/nodes/builtin_functions/engineering_geometry.py`
- `ea_node_editor/nodes/builtins/engineering_viewer.py`
- `ea_node_editor/nodes/builtins/geometry_primitives.py`
- `ea_node_editor/execution/prepared_scene_runtime.py`
- `ea_node_editor/execution/viewer_session_service.py`
- `ea_node_editor/ui_qml/viewer_session_bridge.py`
- `ea_node_editor/ui_qml/components/graph/viewer/`
- `tests/test_engineering_viewer_example_project.py`

## Behavior
- Model Viewer accepts supported engineering carriers and produces an owned
  prepared scene without exposing live worker objects to QML.
- Model Viewer uses the existing dynamic input group (`scene_input_ids`): one
  initial Scene 1 socket, add/remove/label editing, and optional empty slots.
  Each socket accepts Scene, OCP Body, or Geometry Group. `scene_styles` persists
  per-ID opacity/color; the sidebar selects a scene and Auto restores its colors.
  Ports, actors, selections, queries, and export use stable scene IDs, not names.
- The exact trusted function registration adds its dynamic group in both GUI
  and worker registries. Model Viewer remains session-reusable; public callbacks
  are not admitted into function fingerprints. ExecutionContext carries copied
  node port labels so viewer labels match authored graph labels.
- Engineering transport v2 uses ordered `layers`, flat per-scene/native source
  leases, and a composition selection fingerprint. Source coordinates remain
  unchanged and display units follow the first populated port. Removed source
  handles are released on authoritative scene replacement; identity-only opens
  preserve the active session. There is no old overlay contract or migration.
- CAD/FE Import, Model Viewer, Cylinder, Construct Geometry Group, and Deconstruct Mesh
  Face are inert reserved-bundle declarations; the existing trusted helpers
  retain file validation, prepared-scene work, native geometry, and session ownership.
- CAD Import and FE Import receive trusted registry-owned file provenance for their `path` input. Content hashing is bounded and link/reparse-safe; connected path inputs bind through upstream solution keys instead. This metadata remains private to the shipped registry.
- Viewer sessions own camera, selection, clipping, display options, and export
  state through validated handles.
- Model Viewer starts as a lightweight proxy without native warm-up. Selection,
  hover, and single-click do not activate it; a proxy-viewport double-click is
  the only inline activation gesture, and selection/background loss demotes it.
- Fullscreen and detached views acquire explicit presentation holds. Only a
  widget previously activated inline may be retained hidden for reactivation.
- Fullscreen and detached views retarget the same session rather than creating
  a second authoritative viewer.
- Optional topology remains lazy, asynchronous, and cached; points remain the
  fast default.
- CAD datasets keep identity arrays for selection but clear them as active
  display scalars, and the inline viewer hides result/step footer pills for CAD;
  new Model Viewer nodes default to shaded exact body edges.
- Static Structural result geometry uses actual selected-set displacement when
  deformation is available and never claims deformed evidence from reference
  geometry.

## Boundaries
- Keep CAD/FE preparation in execution and UI projection in the viewer bridge.
- Keep project serialization limited to stable configuration and saved view
  facts; native scene and worker identities never persist.
- Keep identifiers, comments, tests, maps, and verification records functional.

## Focused Tests
- `tests/test_engineering_viewer_backend.py`
- `tests/test_engineering_viewer_node.py`
- `tests/test_engineering_viewer_widget_binder.py`
- `tests/test_viewer_session_bridge.py`
- `tests/test_viewer_control_bridge.py`
- `tests/test_content_fullscreen_bridge.py`
- `tests/test_remaining_builtin_function_migration.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_engineering_viewer_example_project.py -q
.\venv\Scripts\python.exe -m pytest tests/test_engineering_viewer_backend.py tests/test_engineering_viewer_node.py tests/test_viewer_session_bridge.py tests/test_viewer_control_bridge.py -q
```
