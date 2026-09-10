# COREX Unified Media Panel — Clean-Break Implementation and Orchestration Plan

Status: **COMPLETED — T01–T10 ACCEPTED**

## Summary

Replace the separate Image, PDF, and Video Panel nodes with one active `media.panel` whose renderer is derived from its current source. Keep Mail Panel separate.

The unified panel supports Browse mode, using a persisted local or project-managed source, and Input mode, using one connected Path, String, or Image value. Input exposure selects authority. When exposed, Browse and every source-replacing action are disabled; the authored source never becomes a runtime fallback. Any waiting, running, empty, failed, blocked, stale, invalid, or unsupported input clears the old preview and shows an explicit state.

This document is the sole task ledger and implementation source of truth. Do not create packet manifests, status files, or prompt archives.

## Orchestration Rules

- The root agent remains the orchestrator. It assigns work, inspects every returned diff and result, updates this ledger, routes review findings, and runs final acceptance.
- Only one implementation writer may be active at a time. A read-only reviewer may start only after that writer stops.
- Finish repository exploration before the next writer starts. If implementation uncovers uncertain ownership, stop writing, return the task to `PLANNED` or `BLOCKED`, finish one focused read-only exploration, and then reassign.
- Every assignment must state goal, preconditions, allowed write scope, forbidden paths, deliverables, verification, and stopping point.
- Before and after each handoff, record the actual agent, status, changed paths, commands, results, open findings, and next owner in the ledger.
- Reviewers never edit. Findings return to the original writer unless the orchestrator explicitly reassigns ownership.
- To reassign: stop or wait for the writer at a message boundary, confirm no edit/test command remains active, inspect `git status` and the scoped diff, record partial work/evidence, clear the old owner, then assign the remaining scope.
- After context compaction, reread the latest user request, this entire plan and ledger, `git status --short`, the active task diff/evidence, and current subagent handoffs before issuing any new instruction.
- A task reaches `COMPLETE` only when deliverables exist, focused verification passes, the orchestrator inspects the diff, and assigned review findings are resolved.
- Do not commit or push unless the user separately requests it.

## Baseline

- Branch: `main`.
- Pre-existing user changes to preserve:
  - modified `docs/specs/INDEX.md`, adding the Physical Simulation plan;
  - untracked `docs/PLAN_COREX_Physical_Simulation_Backend.md`.
- The media implementation must not edit the Physical Simulation plan. Any index update must preserve its existing registration.
- Navigation owners checked during planning: media, passive surfaces, port availability/defaults, floating toolbar, execution visualization, fullscreen, clipboard/history, preferences, persistence, and generated-index maps.
- Planning established that `accepted_data_types`, hidden output ports, per-instance exposure, undoable wire pruning, and `ImageValue` preview adaptation already exist; no new generic type or execution protocol is required.

## Task Ledger

| Task | Status | Actual owner | Evidence / next action |
| --- | --- | --- | --- |
| T01 Canonical plan and baseline | COMPLETE | `/root` | Baseline inspected; canonical plan created; existing Physical Simulation work preserved. |
| T02 Node/runtime contract | COMPLETE | `/root/t02_media_contract_writer` | T09 malformed-URL fix complete; fail-closed classifier/worker/resolver regressions pass with `132 passed, 104 subtests passed`. |
| T03 Contract review | COMPLETE | `/root/t03_media_contract_reviewer` | Initial 1 high/2 medium findings fixed by T02 owner; re-review accepted with no residual findings. |
| T04 Preferences and creation | COMPLETE | `/root/t04_media_preferences_writer` | App preferences v8, Media Panel settings UI, renamed projections, central exposure overrides, and explicit-connect behavior implemented; root rerun: `159 passed, 64 subtests passed`. |
| T05 Source projection and fullscreen | COMPLETE | `/root/t05_media_projection_writer` | T10 fast fix complete: optional edge-signal hookup preserves production refresh and lightweight hosts; root prior-failure modules `8 passed`. |
| T06 QML dispatcher and renderers | COMPLETE | `/root/t06_media_qml_writer` | T09 fixes completed: guarded node-open, local-only Open, unified managed-rename release, and same-source fullscreen state preservation; QML probes `4 passed`, lifecycle `1 passed`, both QuickTests pass. |
| T07 Integration adoption and cleanup | COMPLETE | `/root/t07_media_integration_writer` | Residual atomicity fixed: failed creation restores exact dirty/revision; unchanged exposed-source writes short-circuit; clean/pre-dirty rollback and owning suites pass. |
| T08 Tests, specifications, and indexes | COMPLETE | `/root/t08_media_tests_docs_writer` | Shell ownership/verification manifests reconciled; full shell isolation `58 passed`; maps, traceability, links, generated indexes, manifest contracts, and diff checks pass. |
| T09 Independent final review | COMPLETE | `/root/t09_media_final_reviewer` | Accepted for T10 after all initial and residual findings were re-reviewed; privacy/unrelated-work checks pass. |
| T10 Acceptance and closeout | COMPLETE | `/root` | Focused `315 passed, 66 subtests`; fast `3947 passed, 2 skipped` + serial `225 passed`; QML Quick pass; GUI `599 passed, 1 skipped` + serial `17 passed, 1 skipped`; slow `46 passed`; shell isolation `58 passed`; native Windows Media Panel QML smoke `4 passed`; hygiene/index/frozen-reference audits pass. |

## Key Changes

### Unified Node Contract

- Add active sink `media.panel`, display name `Media Panel`, category `Media`, surface family `media`, variant `media_panel`.
- Remove live registrations and aliases for `passive.media.image_panel`, `passive.media.pdf_panel`, and `passive.media.video_panel`.
- Keep `passive.media.mail_panel` unchanged in a clearly named passive-mail owner.
- Rename the unified authored property to `source`; retain `source_path` only for Mail Panel.
- Never persist `media_kind`; derive `image`, `pdf`, or `video` from the effective source.
- Keep a static superset of mode settings so switching modes does not erase state. Current-mode toolbar/fullscreen controls own editing; irrelevant settings remain dormant.
- Remove `unfocused_behavior` and do not use `instance_spec_resolver`.

Declare the ports exactly as follows:

```text
source:
  direction: in
  kind: data
  primary type: COREX.DataTypes.Path
  accepted types: COREX.DataTypes.String, COREX.DataTypes.Image
  access: Item
  required: false
  uses_property_default: false
  spec default exposed: true

_surface_source:
  direction: out
  kind: data
  type: COREX.DataTypes.Any
  exposed: false
```

- Require exactly one runtime item. Multi-item/List/Tree execution fails explicitly.
- Accept supported local paths, `file://` sources, project artifact references, current HTTP/HTTPS media URLs with recognized suffixes, and exact immutable `ImageValue` instances.
- Return the validated input through `_surface_source`; reuse existing settlement/output-cache transport.
- Browse mode reads `source` directly without a run. Input mode never consumes it as a property default.

### Effective Source Contract

Add one Python-owned source resolver and QML-safe `mediaPanelSourceLookup`. Each QML record contains:

```text
authority: property | input
input_exposed: bool
input_connected: bool
state: ready | waiting | running | empty | failed | stale | invalid
media_kind: image | pdf | video | ""
source_ref: string
resolved_source_url: string
preview_source_url: string
message: string
```

- Raw runtime values remain Python-only for actions and Project Review Deck.
- Only `ready` publishes preview URLs.
- Every non-ready state clears the old renderer and explains the state.
- Input authority never falls back to dormant `source`.
- Source or mode changes never resize the node automatically.

### Toolbar and Editing

- Add a checked `Show Source Input` / `Hide Source Input` floating-toolbar action whose state comes from graph exposure.
- Use existing undoable `set_exposed_port`; hiding a connected port prunes its wire in the same history action and Undo restores both.
- When exposed, disable Source editing, Browse, Internalize, Repair, crop Save/Replace, and trim Replace.
- Keep display-only actions, fullscreen, Open Source, frame capture, and supported trim Copy available.
- Trim Copy and frame capture create seeded, input-hidden Media Panels.
- Revalidate effective identity, mode, authority, and local-source availability immediately before any source-replacing commit.

### Preferences and Creation

Replace `graphics.image_nodes` with:

```text
graphics.media_panel.show_title
graphics.media_panel.show_frame
graphics.media_panel.autoplay_animations
graphics.media_panel.source_input_exposed
```

- Default `source_input_exposed` to `true`.
- Bump app preferences from v7 to v8 and migrate the three appearance values.
- Rename the settings section to `Media Panel`; label the checkbox `Expose Source input on blank Media Panels`.
- Preference changes affect future blank creations only.
- Extend central creation with `exposed_port_overrides`.
- Blank library/radial/direct creation uses the preference.
- Explicit drop-connect forces `source=True`.
- OS paste/drop, frame capture, and trim-copy force `source=False` so supplied content displays immediately.
- Load, graph-fragment paste, custom workflow insertion, undo, and redo preserve serialized exposure.
- Never infer exposure from `property_overrides`; staged sources may be written in `after_create`.

### Renderer and Fullscreen Architecture

- Make `GraphMediaPanelSurface.qml` a thin common dispatcher.
- Extract image, PDF, and video renderers with a shared source-state/action/interaction/aspect-lock/release interface.
- The dispatcher owns Source, Browse, Internalize, Repair, Open, exposure, title/frame, and fullscreen actions. Renderers own only mode behavior.
- Use exact terminal moves for long QML files before editing.
- Add stable `media_panel` metrics and a panel-like surface capability for resizing, locking, and generic Run suppression.
- Make the resize handle consume the loaded renderer’s aspect-lock capability instead of static Image Panel identity.
- Use fullscreen `content_kind="media"`; derive `media_payload.media_kind` dynamically.
- Inline and fullscreen use the same source resolution and refresh on execution, edge, exposure, node, and workspace changes.
- Stop/unload previous PDF, video, or animated renderers before replacement.

### Clean-Break Adoption

- Centralize image/PDF/video suffixes, combined filter, and source classification in the existing file-filter owner; remove clipboard-local duplicates.
- Replace old type-based checks in clipboard/drop, fullscreen, PDF shortcuts, crop, trim, timestamp links, Project Review Deck, file repair, performance fixtures, bootstrap, and tests.
- Project Review Deck uses the effective source; materialize `ImageValue` only in its existing temporary export area and never fall back from non-ready input.
- Remove graph-owned PDF type/page special casing; preview/fullscreen own clamping.
- Add no `.cxproj` migration, old-type alias, or compatibility shim.
- Preserve the frozen 133-row pre-cutover catalogue byte-for-byte. Apply a structural current-catalog overlay after the documentation overlay.
- Expected retained counts after the migration: 139 repo-owned nodes, 76 built-in function entries, 53 internal exceptions, and 78 converted type IDs.

## Public Interface Changes

- Add `media.panel`; remove the three legacy panel IDs.
- Add optional `source` input and private `_surface_source` output.
- Add authored `source`; remove unified-node `source_path`.
- Add `graphics.media_panel.source_input_exposed=true` and rename image appearance preferences.
- Add `exposed_port_overrides` to central creation.
- Add `mediaPanelSourceLookup`.
- Change fullscreen top-level kind to `media`, with mode under `media_payload.media_kind`.
- Add no generic type-system, execution-protocol, or project-migration API.

## Execution Tasks

### T01 Canonical Plan and Baseline

- Goal: create this durable plan and ledger.
- Write scope: this file plus one additive `docs/specs/INDEX.md` registration.
- Verification: inspect diff and run `check_markdown_links.py`.
- Non-goals: production source, packet manifests, commits.

### T02 Node, Runtime, and Catalogue Contract

- Goal: replace the three declarations with the active contract and prove existing runtime support.
- Preconditions: T01 complete.
- Write scope: media/mail declarations, bootstrap, canonical file filters, structural catalogue overlay/loader, focused node/runtime tests.
- Deliverables: focused mail owner; exact node/port/property contract; one-item and source-syntax validation; combined filter/classifier; frozen fixture unchanged.
- Verification: media contract, registry, port/type enforcement, hidden-output settlement, cardinality, and catalogue count tests.
- Non-goals: preferences, QML, fullscreen, integration adoption.
- Packet: `P01 Core Media Contract`.

### T03 Independent Contract Review

- Goal: challenge T02 before UI work.
- Preconditions: T02 writer stopped and focused checks passed.
- Write scope: none.
- Deliverables: severity-ordered findings for compatibility, cardinality, hidden output, no fallback, old-ID removal, and catalogue integrity; route fixes to T02 owner.
- Verification: orchestrator diff review and rerun of affected checks.

### T04 Preferences and Central Creation

- Goal: implement the app default and explicit exposure overrides.
- Preconditions: T03 accepted.
- Write scope: settings/preferences, Graphics Settings, scene creation/context, focused tests.
- Deliverables: v8 migration, `graphics.media_panel`, creation API, all blank/drop-connect/seeded/serialized rules, non-retroactive preference.
- Verification: preference, dialog, creation, fragment/load, and undo tests.
- Non-goals: renderer/source resolution.
- Packet: `P02 Media Defaults And Creation`.

### T05 Effective Source, Inspector, and Fullscreen

- Goal: one authoritative resolver for Python, QML, actions, and fullscreen.
- Preconditions: T04 complete.
- Write scope: source resolver, execution-state projection, media payload, inspector/file-issue policy, fullscreen bridge, focused tests.
- Deliverables: `MediaPanelSourceResolution`, lookup, non-ready clearing, exposed-source editing suppression, dormant file-issue suppression, dynamic fullscreen refresh.
- Verification: all authority/state/ImageValue/inspector/file-repair/fullscreen cases.
- Non-goals: final renderer extraction.
- Packet: `P03 Effective Media Source`.

### T06 QML Dispatcher, Renderers, and Toolbar

- Goal: one intuitive panel with isolated renderers.
- Preconditions: T05 lookup stable.
- Write scope: media QML, surface contracts/metrics, host/resize behavior, fullscreen QML, focused QML tests.
- Deliverables: dispatcher, extracted renderers, common actions, runtime mode controls, stable geometry, lifecycle cleanup.
- Verification: loading, toolbar, disabled Browse, mode switching, PDF/video/animation release, no binding warnings.
- Non-goals: clipboard/presenter/deck integration.
- Packet: `P04 Media Surface`.

### T07 Integration Adoption and Legacy Removal

- Goal: make every workflow create or operate on `media.panel`.
- Preconditions: T06 complete.
- Write scope: clipboard/drop, presenter media actions, crop/trim/frame/timestamp, Project Review Deck, PDF policy removal, performance fixtures, focused tests.
- Deliverables: seeded creation overrides, effective-source actions, input-mode replacement denial, video/image derived actions, deck support, zero live old-ID behavior.
- Verification: clipboard, drop, crop, trim, capture, links, deck, file repair, serialization, and performance fixture tests.
- Non-goals: compatibility migration.
- Packet: `P05 Media Integration Adoption`.

### T08 Tests, Specifications, Maps, and Indexes

- Goal: align authoritative documentation, current catalogue, navigation, and proof.
- Preconditions: T07 complete.
- Write scope: media tests/fixtures, requirements, traceability, migration inventory, agent maps, generated route/source/QML indexes.
- Deliverables: consolidated tests; active unified requirement; exact counts; frozen fixture unchanged; updated maps/indexes; retired-reference audit.
- Verification: catalogue test, traceability, links, maps, generated checks, `git diff --check`.
- Non-goals: new behavior.
- Packet: `P06 Contract And Navigation Closeout`.

### T09 Independent Final Review

- Goal: independently verify the full change before broad acceptance.
- Preconditions: T08 complete; no writer active.
- Write scope: none for reviewer.
- Deliverables: review authority, execution, creation, persistence, fullscreen, QML lifecycle, action guards, catalogue, privacy, and unrelated churn; route fixes one owner at a time until no blocking/high findings remain.
- Verification: rerun affected focused suites after each fix.
- Packet: `P07 Independent Review`.

### T10 Acceptance and Closeout

- Goal: prove the integrated result and reconcile this ledger.
- Preconditions: T09 accepted.
- Write scope: this ledger and retained QA/spec evidence only.
- Deliverables: final status/diff inspection, focused/hygiene/GUI/full gates, display-attached smoke, exact evidence, remaining risks, final ledger status.
- Non-goals: commit, push, packaging, unrelated cleanup.
- Packet: `P08 Acceptance`.

## Verification Plan

Required scenarios include exact ports/exposure, Path/String/Image inputs, single-item enforcement, every non-ready state, no dormant fallback, disabled source editing while exposed, exposure undo/redo and wire pruning, preference creation rules, seeded immediate display, mode switching, stable geometry, fullscreen parity and lifecycle, crop/trim guards, capture/trim-copy creation, Project Review Deck effective sources, unchanged Mail, old-project rejection, and catalogue integrity.

Focused commands:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_media_panel.py tests/test_registry_validation.py tests/test_port_availability.py tests/test_execution_type_enforcement.py tests/test_port_flow_state.py tests/test_corex_contract_catalog.py -q
.\venv\Scripts\python.exe -m pytest tests/test_app_preferences.py tests/test_app_preferences_import_defaults.py tests/test_graphics_settings_preferences.py tests/test_graphics_settings_dialog.py -q
.\venv\Scripts\python.exe -m pytest tests/test_media_panel_source_resolution.py tests/test_pdf_preview_provider.py tests/test_content_fullscreen_bridge.py tests/test_video_trim.py tests/test_project_review_deck.py tests/main_window_shell/edit_clipboard_history.py tests/serializer/round_trip_cases.py -q
```

QML/offscreen gate:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_inline.py tests/test_passive_graph_surface_host.py tests/test_shell_window_lifecycle.py -q
$exitCode = $LASTEXITCODE
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
exit $exitCode
```

Generated/documentation closeout:

```powershell
.\venv\Scripts\python.exe .\scripts\generate_agent_route_index.py
.\venv\Scripts\python.exe .\scripts\generate_source_test_file_index.py
.\venv\Scripts\python.exe .\scripts\generate_qml_navigation_index.py
.\venv\Scripts\python.exe .\scripts\check_agent_maps.py
.\venv\Scripts\python.exe .\scripts\check_traceability.py
.\venv\Scripts\python.exe .\scripts\check_markdown_links.py
```

Broad acceptance:

```powershell
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast --summarize-output
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode gui --summarize-output
.\venv\Scripts\python.exe .\scripts\run_verification.py --mode full --summarize-output
```

Display-attached smoke covers blank panels under both preference states, exposure toggling, Path/String/Image execution, image/animation/PDF/video switching, invalid-state clearing, Browse restoration after hiding input, fullscreen refresh/cleanup, seeded creation, unchanged Mail, and absence of QML warnings or lingering media resources.

## Assumptions

- Breaking the three old IDs and their projects is accepted.
- Mail remains separate.
- String wires are accepted only when their value validates as a supported media source.
- Blank panels use the app default; populated automated creations intentionally override it.
- Exposure, not connection presence, selects authority and disables Browse.
- Invalid/non-ready input clears the old preview as a deliberate COREX rule.
- Mode settings persist but current renderer controls own presentation.
- Recognized HTTP/HTTPS media URLs remain supported; general web-page detection is out of scope.
- No filesystem watcher, MIME framework, generic union type, execution protocol, or compatibility layer is added.
- Existing Physical Simulation changes belong to the user and must remain intact.
