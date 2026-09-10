# CAD Import: Collapsed Faces

## Summary

Status: planned; no implementation changes made.

Allow CAD Import to prepare an assembly containing proven collapsed planar
faces, while preserving the original CAD topology and exact identities.

Read-only diagnosis of the supplied assembly found 247 part occurrences. One
definition, used by eight occurrences, contains three unmeshable planar faces:
24 face occurrences in total. Their boundary edges coincide, their planar UV
width is zero to floating-point precision, and their computed areas are zero
or approximately 1e-18 in the imported coordinate units. OpenCascade reports
self-intersecting wires and unorientable faces.

The actual coarse and full mesh settings, plus a ten-times-finer setting, all
leave these faces without triangles. Default `ShapeFix_Face` on independent
copies does not repair them. `ShapeAnalysis_CheckSmallFace.CheckStripFace`,
using each face's existing tolerance, identifies all three; an adjacent ordinary
face does not pass that check.

COREX currently requires every exact face to appear in the display triangles.
The resulting generic face/body identity error hides this specific condition.
The diagnosis does not establish that the remaining import stages already pass.

## Key Changes

- Classify only missing-triangulation planar faces as collapsed when native
  strip/spot analysis at the existing face tolerance proves that condition.
  Do not infer collapse from area alone, increase tolerances, or omit arbitrary
  self-intersecting faces. An analysis error remains an import failure.
- Retain every original face, edge, body, part identity, and relationship in
  the exact model and selection topology. Add a validated face-level
  `displayable: false` marker and a fixed collapsed-face reason for the proven
  cases. An absent marker means ordinary displayable geometry.
- Require display triangles for every displayable face. Keep exact checks for
  canonical IDs, observed cell identities, body coverage, edges, vertices,
  asset hashes, and topology relationships. Do not generate fake triangles.
- Derive the classification once per preparation and reuse it for both display
  detail levels, the selection sidecar, and diagnostics. Do not introduce a
  persistent recovery service or cache. Reuse across repeated definitions only
  through exact native identity if useful; occurrence IDs stay distinct.
- Report the count of collapsed faces and affected occurrences through the
  existing node warning mechanism. Persist the diagnostic with the prepared
  scene so cold and cached imports report the same warning.
- Give unexplained mesh omissions an actionable error with a bounded list of
  affected part/face IDs and native status, distinct from a body-mapping error.
- Increment `SCENE_IMPORTER_VERSION` when implementing the changed generated
  topology semantics so old scene caches cannot bypass the new checks.

## Public Interface Changes

CAD Import keeps its current ports and settings. A successful affected import
reports, for example: "Imported CAD with 24 collapsed faces in 8 part
occurrences. These faces have no display surface; original CAD topology is
retained." Ordinary faces remain selectable. Collapsed faces remain exact
topology records but cannot be picked from display triangles.

No automatic CAD healing, source-file rewrite, dependency upgrade, general
partial-import mode, or new user setting is included.

## Execution Tasks

### T01 — Handle collapsed faces consistently

- **Goal:** Prepare both display detail levels without losing original CAD
  identity or accepting unexplained missing surfaces.
- **Preconditions:** Reconfirm the diagnosis on the installed OCP version;
  preserve concurrent work in the checkout.
- **Conservative write scope:**
  `ea_node_editor/execution/prepared_scene_runtime.py`,
  `ea_node_editor/common/scene_protocol.py`,
  `ea_node_editor/execution/viewer_backend_engineering.py`,
  `tests/test_engineering_import_nodes.py`, and
  `tests/test_engineering_viewer_backend.py`.
- **Deliverables:** Native classification, one shared classification result,
  validated displayability metadata, strict coverage rules, actionable failure
  messages, cache-version update, and focused regression tests.
- **Verification:** A synthetic assembly with repeated located components and
  collapsed planar faces succeeds. A non-collapsed unmeshable face still fails.
  Invalid markers and missing ordinary face/body/edge identities still fail.
- **Non-goals:** Repairing source topology, changing exact exports or mass
  properties, skipping whole components, handling bodies with no displayable
  faces, or optimizing unrelated CAD preparation code.
- **Packetization notes:** One coupled implementation task; no packet set.

### T02 — Report the condition through CAD Import

- **Goal:** Make the successful import and any remaining failure understandable.
- **Preconditions:** T01 classification and cached metadata are available.
- **Conservative write scope:**
  `ea_node_editor/nodes/builtins/engineering_imports.py`,
  `ea_node_editor/execution/prepared_scene_runtime.py`, and
  `tests/test_engineering_import_nodes.py`.
- **Deliverables:** Bounded diagnostic metadata exposed by the existing scene
  handle and returned as `NodeResult` warnings. Reuse the existing reserved
  CAD Import declaration's `ctx.warn` forwarding.
- **Verification:** Cold and cached imports return the same warning; ordinary
  CAD and FE imports do not acquire a collapsed-face warning.
- **Non-goals:** QML changes, a diagnostics subsystem, or new import controls.
- **Packetization notes:** Same implementation owner; depends on T01.

### T03 — Verify the supplied assembly and record the result

- **Goal:** Prove the user's CAD Import to Model Viewer workflow succeeds.
- **Preconditions:** T01 and T02 pass their focused checks.
- **Conservative write scope:** The two focused test modules if a discovered
  regression needs coverage; this plan; the neutral CAD/FE route map and
  `docs/agent_maps/COVERAGE.md`. Regenerate navigation indexes only if citations
  change. Keep the source assembly and diagnostic geometry outside the repo.
- **Deliverables:** Full cold import and cached reimport of the supplied file;
  both surface detail levels, edge and vertex assets, selection sidecar, and
  Model Viewer materialization verified. Record any later-stage blocker as
  unresolved rather than counting surface preparation as complete.
- **Verification:** See Test Plan. Confirm all 247 occurrences remain and exactly
  the diagnosed 24 face occurrences are marked non-displayable. Confirm the
  input file hash is unchanged and ordinary face/body/edge picking works.
- **Non-goals:** Broad performance work, packaging, commits, or publication.
- **Packetization notes:** Focused acceptance closeout; no separate agent team.

## Work Packet Conversion Map

None. Execute directly in T01, T02, T03 order.

## Test Plan

Use synthetic CAD geometry for committed tests; do not commit the supplied
assembly or extracts from it.

1. Prove missing collapsed faces are represented consistently across coarse and
   full meshes and topology, including repeated translated part occurrences.
2. Reject a finite-extent self-intersecting face even when signed area cancels
   to zero; also reject an ordinary face with a missing triangulation. This
   protects against turning the classification into a general skip rule.
3. Retain strict canonical-array, body/edge/vertex coverage, sidecar-hash,
   malformed-marker, and interrupted-write cleanup tests.
4. Check import warning parity after disk-cache reload and preserve exact
   native topology through recovery. A scene with no displayable surfaces
   continues to fail clearly.
5. Run the affected tests first, then the owning suites once:

   ```powershell
   .\venv\Scripts\python.exe -m pytest -n 0 tests/test_engineering_import_nodes.py tests/test_engineering_viewer_backend.py -q
   ```

6. Run the supplied-file cold/cache import and a source-app CAD Import to Model
   Viewer check. Inspect normal geometry and selections in both detail levels;
   this is the acceptance gate for the requested fix.
7. After implementation map/document updates, run agent-map, traceability,
   Markdown-link checks, and `git diff --check`.

## Assumptions

- The original CAD geometry must remain authoritative. Displayability does not
  imply that invalid source faces have become valid CAD geometry.
- Native small-face analysis is already available in the pinned OCP dependency.
  Its use is limited to failed planar faces at existing model tolerances.
  See the [OpenCascade small-face analysis reference](https://dev.opencascade.org/doc/refman/html/class_shape_analysis___check_small_face.html).
- All eight affected occurrences refer to one exact part definition; identity
  must remain occurrence-specific even if classification work is shared.
- Entirely non-displayable bodies and unrelated meshing defects remain explicit
  errors in this bounded change.

Navigation used: the agent-map index and coverage, neutral CAD/FE viewer route,
the exact error anchor in the prepared-scene runtime, its two callers, the CAD
Import declaration/helper, and the focused import/backend tests. Discovery was
limited to those owners; no QML or broad source scan was needed. This planning
document alone changes no source/test ownership or agent-map citations.
