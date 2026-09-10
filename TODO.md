# TODO Ideas

## Open

### Composite Toolbox and Composite Bolted Joint Strength Calculation Tool

- Define a new composites-focused toolbox that groups laminate/stacking/preload-related utilities
- Add a composite bolted joint strength calculation node/tool with inputs for laminate properties, fastener geometry, edge distance, bearing/bypass criteria, and output design checks
- Capture implementation plan and success criteria once requirements settle

### PDF Panel Ctrl+F Search in Fullscreen

- Add keyboard shortcut handling for `Ctrl+F` in fullscreen PDF panel mode
- Show a focused search bar/overlay in fullscreen with match navigation (next/prev) and result count
- Ensure search respects PDF panel zoom/content focus and is dismissed cleanly without breaking fullscreen navigation


## Implemented

### Windows-style "Open" and "Open with..." File Actions

**Status:** Implemented on `main`

**Summary:**
- OS launch logic is centralized in `ea_node_editor/platform_open.py` (`open_path_with_default_handler` for "Open", `open_path_with_app_chooser` for the "Open with..." picker), with safe handling of missing/invalid paths and a `QDesktopServices` fallback
- The Folder Explorer node gains a Windows-style row right-click menu: Open, Open with..., Copy Path, Open in New Classic Explorer, Send to COREX as Path Pointer, Properties (destructive cut/copy/paste/rename/delete remain out of scope)
- The Path Pointer node exposes an "Open" floating-toolbar button that expands into an Open / Open with... sub-toolbar; both dispatch the new `open_node_path` / `open_node_path_with` graph actions
- Folders open in the OS file explorer; "Open with..." is hidden/disabled for folders and the `..` parent row
- Failures surface to the user (folder-explorer error text; graph hint for the Path Pointer toolbar)

### Shell/Scene/QML Boundary Ownership Refactor

**Status:** Implemented via the `SHELL_SCENE_BOUNDARY` packet set

**Summary:**
- QML shell-owned library/search/hint, workspace/run/title/console, inspector, and GraphCanvas host concerns now route through focused bridge facades instead of growing `ShellWindow` further
- `GraphCanvas.qml` keeps its stable root contract while using `graphCanvasBridge` for shell-owned canvas integration
- `GraphSceneBridge` keeps its public slot/property contract while delegating scope/selection, mutation/history, and payload/theme/media responsibilities to focused helper modules
- Original packet-history regression commands remain recorded in `docs/specs/work_packets/shell_scene_boundary/SHELL_SCENE_BOUNDARY_QA_MATRIX.md`, and the current architecture-closeout regression slice plus residual seams are recorded in `docs/specs/work_packets/arch_fourth_pass/ARCH_FOURTH_PASS_QA_MATRIX.md`

### Image Crop Button on Image Panel Node

**Status:** Implemented on `main`

**Summary:**
- Image panel nodes expose a hover-only crop button in the top-right corner
- Clicking the button enters inline crop mode with free-form edge/corner handles
- Crop parameters are stored as hidden node properties (`crop_x`, `crop_y`, `crop_w`, `crop_h`)
- Cropping is non-destructive and applied at render time without modifying the source image on disk
- Crop mode locks host drag/resize/port interactions and owns the cursor until editing ends

### Graph-Surface Input Routing Pattern

**Status:** Implemented via the `GRAPH_SURFACE_INPUT` packet set

**Summary:**
- `GraphNodeHost.qml` keeps node-body drag/select/open/context routing underneath the loaded surface instead of above it
- `GraphNodeSurfaceLoader.qml` publishes `embeddedInteractiveRects` for local control ownership and `blocksHostInteraction` for whole-surface modal locks
- Shared graph-surface buttons and editors live under `ea_node_editor/ui_qml/components/graph/surface_controls/` so future surfaces can reuse the locked interaction pattern
- Hover-only affordances now use hover-safe primitives instead of invisible click-swallowing overlays or host hover-proxy shims
- Final regression coverage and the approved shell fallback are recorded in `docs/specs/perf/GRAPH_SURFACE_INPUT_QA_MATRIX.md`

### Drag-and-Drop Tab Reordering

**Status:** Implemented on `main`

**Summary:**
- Workspace tabs and view tabs can be reordered via drag
- Reordering animates tab displacement while dragging
- Custom tab order persists across sessions
- Output/Errors/Warnings tabs remain excluded

### Ungroup Subnode Action

**Status:** Implemented on `main`

**Summary:**
- "Ungroup Subnode" is available in the right-click context menu with destructive styling
- "UNGROUP" is available in the inspector for selected `core.subnode` nodes
- Both entry points call the existing ungroup action without a confirmation dialog







