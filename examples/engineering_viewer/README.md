# Model Viewer capabilities example

`engineering_viewer_capabilities.cxproj` is a self-contained walkthrough of the
fullscreen and detached Model Viewer controls. Its managed sidecar contains
a colored XCAF STEP assembly and an FE mesh with source-authored RGBA, scalar, and
vector arrays.

## Run it

1. Launch COREX with `.\venv\Scripts\python.exe -m ea_node_editor.bootstrap`.
2. Open `examples/engineering_viewer/engineering_viewer_capabilities.cxproj`.
3. Run the workflow.
4. Select **Detach** on the inline viewer, or enter fullscreen, to show the complete
   bottom control strip and right-side advanced panel.

The CAD assembly uses Scene 1 and the RGBA FE sphere uses Scene 2. Both inputs
use millimetres and are stored as project-managed sources. The sphere has a
per-scene opacity of 0.32; new scene ports default to fully opaque.

Use the input-side `+` to add scenes (zoom in for on-node controls), or the port
context menu to insert/remove them and edit their labels. Empty ports are ignored;
at least one connected scene is needed. Each port accepts a prepared CAD/FE scene,
OCP Body, or Geometry Group. The sidebar scene selector controls opacity and a
solid `#RRGGBB` color override; Auto restores source coloring. Hide/show and isolate
remain per-scene, while the camera, representation, and clipping are shared.
Scene coordinates are preserved and units are converted to the first populated
scene's units. Old overlay connections/settings are not automatically migrated.

## Guided tour

1. **Image #1 — Orientation and layout:** drag the model, click the bottom-left
   view cube, drag the bottom-right triad, and compare them with the RGB world axes.
   Narrow the detached window to see the bottom strip's overflow chevrons.
2. **Image #2 — Solid render modes:** try Wireframe, Visible Edges, Shaded, and
   Shaded with Body Edges. The STEP layer supplies true CAD topological edges;
   the viewer never substitutes tessellation feature edges for that exact asset.
3. **Image #3 — Mesh render modes:** toggle Mesh/Facet Edges independently, then
   toggle Attribute Colors. The FE layer uses a strict `uint8` RGBA point array;
   `Temperature`, `Displacement`, and `MaterialId` demonstrate that scalar, vector,
   and ID arrays are not mistaken for direct colors.
4. **Image #4 — View controls:** select a face or mesh entity, then use Fit Selection
   and Isolate. Shift+Isolate refreshes the isolated set; activating Isolate again
   restores the previous visibility.
5. **Image #5 — UI controls:** toggle the orientation triad, view cube, and world
   axes independently.
6. **Image #6 — Saved views:** the project starts with `ISO Perspective` and
   `Front Orthographic`. Apply, rename, reorder, or delete them; save another view;
   use PageUp and PageDown to cycle with wrapping.
7. **Image #7 — Projection and docking:** switch Perspective/Orthographic, detach,
   enter fullscreen from detached, close fullscreen to return to detached, and dock
   the same live viewer back into the node. Camera and selection should remain
   unchanged because every presentation reparents one native widget.
8. **Image #8 — Selection and toolbar layout:** use the top selection strip to switch
   among the capability-supported CAD and FE entity filters. With CAD Edge or CAD
   Face active, the tangent control expands adjacent entities using the app-wide
   angle tolerance (default `5` degrees, editable from `0` through `90`). Then compare
   the bottom strip's four groups: **Render Mode**,
   **View**, **Camera**, and **Docking**, with viewer display toggles kept inside
   Render Mode/View.

## Selection workflow

1. Choose **CAD Face** in the top strip and click a STEP face without dragging.
   Pan and rotate gestures must not create a new highlight.
2. Choose **CAD Edge** or **CAD Face**, keep the tangent tolerance at `5` degrees,
   and click a source entity to exercise exact topology expansion. Change the
   tolerance to confirm the same app-wide value is used in fullscreen and detached
   presentations.
3. Choose an FE filter to see CAD-only filters and tangent expansion disable with
   their capability reason when the active source cannot provide exact identity.
4. Save the current selection, rename it, publish it, and rerun the workflow. Saved
   selections use structured `engineering_selection_set.v2` references containing
   the layer, source fingerprint, canonical entity kind, and stable entity ID.

## Limits worth noticing

- Full controls intentionally appear only in fullscreen and detached modes; inline
  stays compact and exposes Detach.
- Fit Selection is disabled until something is selected.
- The active selection filter is runtime-only. It is not a persisted Viewer-node
  property; the tangent angle is intentionally an app-wide preference.
- Unsupported source-specific modes are disabled with a reason instead of being
  approximated. CAD body edges come only from the STEP layer; FE facets remain a
  separate control.
- Fit/isolate state is temporary. Saved views and orientation-aid visibility persist
  on the Viewer node.

Regenerate the project and both source files with:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_engineering_viewer_capabilities_example.py
```
