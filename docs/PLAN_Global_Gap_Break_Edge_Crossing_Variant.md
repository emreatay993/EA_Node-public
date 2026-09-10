# Global Gap-Break Edge Crossing Variant

## Summary
- Add a canvas-wide graphics preference `edge_crossing_style` with values `none` and `gap_break`, defaulting to `none`.
- Apply the first implementation to all edges in the shared QML edge renderer, not as persisted per-edge style.
- Use a deterministic over/under rule: selected or previewed edges render over others; everything else keeps the existing stable payload order.
- Keep crossing gaps render-only. Hit-testing, culling, arrowheads, and label anchors continue to use the original full edge geometry.

## Key Changes
- Extend the graphics preferences pipeline with `graphics.canvas.edge_crossing_style`, including normalization, shell/window presenter exposure, canvas state bridge exposure, and a `GraphCanvas.edgeCrossingStyle` QML property.
- Add a `Crossing style` control to Graphics Settings on the canvas/visual page with `None` and `Gap break`.
- Keep Python edge payload persistence unchanged. Compute crossing decoration entirely in `EdgeLayer.qml` from visible snapshots so project files and graph model schemas stay untouched.
- In `EdgeLayer.qml`, add an internal crossing-decoration pass that only runs when `edgeCrossingStyle === "gap_break"` and the canvas is in full-fidelity rendering.
- Build the final draw order before crossing detection: non-selected edges in current payload order, then previewed/selected edges appended in their existing relative order.
- Extend `EdgeMath.js` with helpers to:
  - sample bezier routes into polylines,
  - reuse pipe routes directly,
  - broad-phase prune by intersecting bounds,
  - detect segment intersections,
  - reject endpoint/near-anchor crossings,
  - merge nearby break ranges on the under edge.
- Express gap size in screen space and convert it to scene units by zoom so the break stays visually stable.
- Render under edges as multiple subpaths with skipped ranges, then render over edges normally.

## Public Interfaces
- New graphics setting: `graphics.canvas.edge_crossing_style`
- New normalized values: `none`, `gap_break`
- New shell/canvas-exposed property chain: `graphics_edge_crossing_style` to `GraphCanvas.edgeCrossingStyle`
- Internal visible-edge snapshots may gain `crossingBreaks` metadata for rendering/tests; no `.cxproj` schema change and no per-edge persistence change

## Test Plan
- Preferences tests:
  - default/invalid normalization for `edge_crossing_style`
  - graphics settings dialog load/save coverage for the new control
  - QML preference-binding coverage from host preference changes into `GraphCanvas` and `EdgeLayer`
- Renderer tests:
  - `none` preserves current snapshot/render behavior
  - `gap_break` produces break metadata only on under edges
  - selected/previewed edges win crossings over non-selected edges
  - pipe/pipe and bezier-involved crossings both produce valid breaks
- Interaction tests:
  - `edgeAtScreen()` still uses full geometry and remains stable across zoom
  - flow labels and label anchors remain attached to original geometry

## Assumptions
- Default rollout preserves current visuals until the setting is enabled.
- The first version is global for all edges, not theme-specific and not configurable per edge.
- Gaps are visual-only; clicking through a visible break still selects the underlying edge.
- Stable non-selected ordering continues to come from the existing payload order derived from `scope_edges(...).sort(key=edge_id)`.
