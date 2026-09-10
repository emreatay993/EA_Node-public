# Unified Canvas Paste and Drop

Status: IMPLEMENTATION COMPLETE; native Windows cross-window drag acceptance
remains pending. No packaging or publication was performed.

## Approved behaviour

- One app preference, `graphics.interaction.canvas_import_mode`, accepts
  `automatic` (default) and `ask`. It applies immediately, survives restart,
  appears in Canvas Options and Graphics Settings > Interaction > Paste and
  Drop, and never becomes project settings.
- Paste and new-node drops share classification: image/PDF/video sources to
  Media Panel; local mail to Mail Panel; local HTML and ordinary HTTP(S) URLs
  to Web Viewer; folders/other files to Path Pointer; raw media to an internally
  staged Media Panel; copied tables to Tabular Data Input; ordinary text to
  plain Text Annotation; formatted text to the existing Markdown conversion.
- Process every batch item and preserve HTTP(S) URLs and literal text. Do not
  extract document contents, OCR, or video/mail text. Media imports hide Source.
- Ask every time opens Add to Canvas for one or many items. Each row shows its
  source and applicable Insert as choices, defaulting to the detected type.
  Alternatives include the appropriate media/web/mail/path node, plain Text
  Annotation, Panel, table data/Markdown, and Skip. Set all to offers shared
  available choices plus Detected type and Skip; individual overrides follow.
- Plain Text and Panel use literal paths/URLs/copied text. Panel uses text mode
  with number parsing disabled. For raw media without a path, those choices
  stage an internal copy after confirmation and store its exact managed ref.
- Show unavailable-node reasons, including disabled add-ons; do not silently
  substitute another representation. Cancel/Escape makes no changes. Do not
  remember row choices or change the mode in the import dialog.
- Preserve native graph-fragment MIME priority, graph copy/paste, library
  insertion, editor text paste, and explicit existing-node path replacement.
  Include new-node path drops from the COREX Folder Explorer.
- Paste at viewport centre with cascade; drop at release position; insert in
  the active workspace/scope. Revalidate the captured destination after a
  dialog. Group successful batch nodes into one Undo action. Roll back a failed
  item's node/artifact work, retain successes, and report failures together.
- Reuse registry-backed graph mutation and project staging. Use explicit shell
  composition and one CanvasImportController plus a native Qt chooser. Remove
  superseded classifiers and table-only dialog routes. Larger cleanup is
  authorized; Ponytail is disabled for this task.

## Execution and acceptance

One implementation writer per checkout. T02 writes the primary checkout; T03
writes an isolated `C:/Users/user/cx-canvas-import-prefs` worktree using the
already-settled preference key. The coordinator integrates their disjoint
changes and maintains this table; each substantial task receives independent review.
Preserve concurrent filesystem, port-contract, runtime, and documentation work.

| Task | Owner / scope | Status | Evidence / next action |
| --- | --- | --- | --- |
| T01 | canvas_import_t01; shared input snapshot, classification, and choice model | ACCEPTED | 47 input tests; independent review accepted classification fixes; included in final 113-test suite |
| T02 | canvas_import_t02; import controller, chooser, graph batch/staging, clipboard/drop integration | ACCEPTED | Initial UI/batch review plus runtime follow-up accepted; 71 owner tests + 25 subtests; real staged/saved/SaveAs process and strict-reference tests passed |
| T03 | canvas_import_t03; isolated preference worktree | ACCEPTED / INTEGRATED | 16 preference tests including native-discovered menu overflow; existing route 144 tests + 125 subtests; independent review accepted |
| T04 | coordinator; integration, maps/spec/help, focused and fast checks, desktop smoke | IMPLEMENTED; DESKTOP DRAG GATE PENDING | Snapshot, help, maps, requirements and navigation integrated; final evidence and limitations below |

## Verification requirements

- Automatic mapping via both gestures, mixed batches, intact literal text and
  URLs, HTML versus raw text/table alternatives, unavailable nodes.
- Chooser per-row/bulk/skip/default/cancel behaviour and raw-media explanation.
- Nested scope, captured destination invalidation, one-step batch Undo/Redo,
  per-item rollback, visible failures, existing graph clipboard priority.
- Managed screenshot references through Save, reopen, and Save As.
- Preference synchronization, restart, invalid/missing defaults, dialog Cancel
  and reset defaults, no project-settings persistence.
- Focused tests, isolated clipboard shell groups, then fast integration with
  summarized logs. Update maps/help/spec proof and run agent-map, traceability,
  and Markdown checks; regenerate route indexes from updated maps.
- Windows desktop smoke: Explorer file/folder drops, Ctrl+V, screenshot, web
  URL, copied Excel cells, both modes. Distinguish offscreen/injected-event
  evidence from physical Windows drag-and-drop acceptance.

Planning baseline: 36 shell cases across three isolated groups and 22 drop/media
checks passed across runs. A transient concurrent port-field mismatch passed
on rerun. Existing defects were malformed dropped HTTP URLs, only the first
dropped item being used, and gesture-dependent/mixed-file classification.

## Final verification

Verification date: 2026-09-06. Counts below overlap; do not add route-owner and
integration counts as if they were distinct tests.

| Check | Result |
| --- | --- |
| Shared inputs, controller/dialog, preferences, real-process runtime, bridge snapshot | 113 passed with `pytest tests/test_canvas_import_inputs.py tests/test_canvas_import_controller.py tests/test_canvas_import_preferences.py tests/test_canvas_import_runtime.py tests/test_graph_canvas_surface_snapshot.py -q -n 0` |
| Isolated clipboard shell groups | 36 passed (18 basics, 10 artifacts, 8 history); logs `artifacts/canvas_import_t02_shell_{basics,artifacts,history}.log` |
| Input-reference help | 2 passed, 4 subtests passed; `pytest tests/main_window_shell/shell_basics_and_search.py -k keyboard_mouse_reference_dialog -q -n 0` |
| Runtime/staging owner follow-up | 71 passed, 25 subtests passed; independent reviewer also passed the two real-process/security tests |
| Fast main, final run | 4,850 passed, 4 skipped, 4 failures; four-worker runner invocation, no configuration change |
| Fast serial phase | 220 passed |
| Failed backend cases rerun together in isolation | 2 passed, 3 subtests passed |
| Traceability, Markdown and agent-map hygiene tests | 116 passed, 15 subtests passed |
| Agent maps, traceability, Markdown links, whitespace | Passed; route and source/test indexes regenerated |

Fast logs: `artifacts/verification_logs/20260906_174141/`. The two persistent
failures are the port-context Menu ownership assertion and QML navigation
175/176 count, independently reproduced on the original HEAD and recorded in
[File System Nodes](PLAN_COREX_FILESYSTEM_NODES.md). The two backend failures
in the parallel run passed together with `-n 0`; this is rerun evidence, not
an all-green broad lane. Existing unrelated assertions were not weakened.

### Windows desktop evidence

Synthetic fixtures, disposable app profiles, and logs are under the ignored
`artifacts/canvas_import_smoke/20260906_161512/` directory. Source bootstrap
used the normal desktop QQuickWidget host, without an offscreen platform.
The user's existing COREX window/project was left untouched.

- Explorer Ctrl+C / canvas Ctrl+V imported all nine fixture items in Automatic:
  three Media Panels, one Mail Panel, one Web Viewer, and four Path Pointers.
  The nine-row Ask chooser, Set all to Panel, and Cancel were observed; Cancel
  retained the original nine nodes.
- Restart confirmed Ask persisted in both the gear and full Graphics Settings.
  Live switching worked. Native-discovered gear overflow and a clipped Add to
  Canvas button were fixed; the menu footer and full button label are reachable.
- Real Excel A1:B2 clipboard cells became a ready Tabular Data Input directly
  in Automatic, and the exact Markdown table in Ask.
- Fresh Alt+Print screenshot paste rendered a Media Panel in Automatic and a
  literal managed-reference Panel in Ask, with no artifact execution errors.
- A copied URL became Web Viewer in Automatic and literal Panel text in Ask.
  Autosave retained `%20`, query, fragment, and the copied newline in Panel
  text, with text mode and number parsing disabled.
- Screenshot Save/reopen/Save As and connected Panel-to-Media execution are
  proved by real-process integration tests, not a native file-dialog smoke.

Native screenshot execution exposed a missing staged runtime descriptor. The
accepted fix registers the existing Path descriptor during project staging;
the authored-property boundary validates canonical registered references,
descriptor/path trust, and byte integrity. Strict output/resolve rejection
remains unchanged. Panel carries the admitted runtime reference while its
authored property remains literal. Old synthetic smoke assets without those
descriptors remain rejected; no migration or relaxed fallback was added.

### Remaining acceptance limitations

- Physical Explorer-to-COREX dragging in both modes still needs manual
  confirmation: the Windows automation tool rejects endpoints outside its
  source window. Native Qt event tests cover both supported shell hosts, but
  do not establish physical cross-window Windows drag acceptance. The dedicated
  test window and fixture Explorer window were left available for this check.
- The desktop stderr log includes inspector/toolbar QML warnings outside this
  import change. A hidden-source imported Media Panel can also show the
  existing source-waiting warning even while its passive preview renders.
- No packaging, commit, push, or release claim is part of this result.
