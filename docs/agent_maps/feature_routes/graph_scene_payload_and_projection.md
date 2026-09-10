# Graph Scene Payload And Projection

## Purpose
Use this for graph scene payload construction, state projection, data-port/edge presentation facts, bounded previews, and QML scene publication.

## Lookup Aliases
- `graph scene projection`
- `bounded rich preview`
- `settings band geometry`
- `grouped inline property projection`

## Start Here
- `ea_node_editor/ui_qml/graph_scene_payload/factory.py`
- `ea_node_editor/ui_qml/graph_scene_payload/` — payload construction package:
  - `kinds/` — **the insertion point for kind-specific payload fields.** One module per node kind (`media_panel`, `plot`, `web_page`, `excalidraw`, `viewer`, `group_backdrop`); `kinds/__init__.py` resolves contributors per `(type_id, family, variant)` (cached, registration order frozen). A new payload field for kind X = edit `kinds/<kind>.py` + the consuming surface QML, nothing else.
  - `factory.py` — kind-independent base assembly (`_GraphSceneNodePayloadFactory.build_node_payload`) + frozen `PayloadBuildContext` handed to contributors. New build inputs are added to the context once, not threaded through signatures.
  - `normalize.py` — pure normalization helpers (crop rects, fit modes, source URLs, bookmarks)
  - `theme_inputs.py` — graph theme/typography/pixel-size readers
  - `backdrop_partitioner.py` — group-backdrop partitioning of payload models
  - `builder.py` — `GraphScenePayloadBuilder` composition root (targeted delta rebuilds also dispatch through `kinds/`)
  - `fullscreen.py` — `build_content_fullscreen_*` payloads
- `ea_node_editor/ui_qml/graph_canvas_state/`
- `ea_node_editor/ui/support/node_presentation.py`
- `ea_node_editor/ui/shell/presenters/library_presenter.py`
- `ea_node_editor/ui/shell/inspector_projection.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/policy.py`
- `ea_node_editor/ui_qml/graph_scene/policy_bridge.py`
- `ea_node_editor/ui_qml/graph_scene_bridge.py`
- `tests/test_graph_scene_bridge_bind_regression.py`
- `ea_node_editor/ui_qml/graph_canvas_visible_model.py`
- `ea_node_editor/ui_qml/graph_scene/`
- `ea_node_editor/ui_qml/graph_scene_mutation/`
- `ea_node_editor/ui/shell/controllers/mutation_ui_effects.py`
- `ea_node_editor/ui_qml/components/graph/GraphNodeSurfaceMetrics.js`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasOptionsMenu.qml`
- `tests/test_graph_scene_presentation_facts.py`
- `tests/test_data_type_ui_projection.py`
- `tests/test_flow_edge_labels.py`
- `tests/graph_track_b/scene_model_graph_scene_suite.py`

## Port Presentation Notes
- Payload contributors must not perform data I/O. The plot kind publishes a
  `series_signature` + cached `render_revision` (one `stat()` per tabular
  source); heavy series builds happen in `PlotAutoPreviewService` which
  refreshes single nodes via `publish_node_title_payload_delta`. Targeted
  full-node payload rebuilds can pass previous payloads and changed-field
  metadata; the plot contributor may reuse an existing `plot_surface` only for
  known non-rendering graph `node.title` deltas, while plot property/source
  changes keep the signature/stat recompute path. See
  `tests/test_tabular_perf_guards.py` for the zero-I/O regression guard.
- Each scene payload build and library-registry refresh creates one compact data-type presentation projection from one catalog `snapshot()` and one `fingerprint()`, then reuses it across all ports. Per-port QML facts are limited to the canonical type ID, bounded display/family/color/icon/access/generation fields, and at most eight accepted labels of 160 characters each; assignability, conversions, compatibility edges, and the catalog graph never enter a port payload. Library rows retain authored primary/accepted IDs only for Python-owned Quick Insert compatibility.
- `GraphSceneMutationPolicy.compatible_endpoint_snapshot(...)` resolves current in-scope effective ports and target accepted-type unions against the active catalog, returning only the catalog fingerprint, candidate role, and compatible endpoint identities. QML loads that fingerprinted snapshot once when a real wire drag activates and fails closed on malformed or generation-mismatched data; graph-owned commit validation remains unchanged.
- Standard port payloads expose read-only `data_access`, sparse modifier checks, Principal eligibility/selection, and bounded runtime status/preview facts. Edge payloads expose durable `enabled`, `input_order`, invalid-type state, and source access. Standard data edges incident to an `active` or `compile_only` node additionally expose derived `active_data_wire` and normalized `visual_style.display_mode`; their projection no longer exposes `stroke_count`. Passive-only and `flow` edges retain their existing `stroke_count` projection and style behavior. Spec-declared active-node settings groups publish ordered group rows plus a host-owned bottom band; collapsed real child inputs keep their topology but hide their handles and share a display-only aggregate presentation anchor, while expanded children return to distinct real anchors. Outputs stay top-level. The retired execution-control Settings row and compact execution endpoints remain absent.
- Nodes with declared dynamic groups project generic `dynamic_port_groups` entries containing `id`, `direction`, ordered `port_keys`, `can_insert`, `removable_port_keys`, and `rename_mode`, all derived from resolved instance ports. Callback objects and backing-property editors never enter QML.
- Dynamic insert/remove/rename publishes the affected node payload plus targeted incident-edge topology deltas. Python `standard_metrics.py` and QML `GraphNodeSurfaceMetrics.js` keep zero-port Add targets and dynamic-control bottom padding geometrically aligned.
- Grouped inline properties are removed from the ordinary inline body and projected inside their group items. Paired port/property rows reuse the normal `overridden_by_input` fact so a connected input disables its local editor. `tests/test_graph_scene_presentation_facts.py` owns two-group anchor/topology coverage; `tests/test_viewer_surface_contract.py` owns specialized-body preservation.
- Standard width metrics measure top-level port columns separately from full-width settings rows. Group headers always reserve their text/chevron width; only expanded groups contribute editor/child-label widths, including side-by-side color and toggle controls. The visible-row regression lives in `tests/test_graph_scene_presentation_facts.py`.
- `uses_content_sizing` makes ordinary active/compile-only standard cards derive width and height from current content, ignoring saved custom dimensions in presentation. Dedicated media/viewer/preview/compact surfaces and passive nodes retain their sizing behavior. Port anchors use the same resolved size; settings toggles, minimap bounds, and connections follow the fitted payload. Existing authored properties and serialized dimensions are not rewritten during projection. The real-canvas regression in `tests/graph_surface/passive_host_interaction_suite.py` covers repeated settings toggles and connected endpoints at enlarged typography.
- The scene injects the app's `keep_expanded_node_width` preference into the builder/factory. Shared metrics optionally measure settings width as if all groups were expanded; current height, group positions, output properties, and per-node persistence remain independent. Full/targeted/addition/connection/library payloads and fallback ordinary-card bounds consume the same precomputed metrics.
- Python Script declaration controls use the same resolved-spec projection. Source-backed input/output groups reference its ordinary resolved plain ports in the generic dynamic-port payload; default-backed controls retain their normal settings projection. No script-specific renderer facts or callbacks enter QML.
- Every projected inline/default property keeps `value` as the authored property and exposes `display_value`, `display_value_available`, `overridden_by_input`, `condition_enabled`, and `editor_enabled` as explicit presentation facts. Safe upstream values may replace only the display; unavailable/invalid values use a neutral disabled placeholder. `interval_1d` projects `{start, end}` plus `minimum`, `maximum`, `step`, and `interval_direction`; `searchable=True` is forwarded for enum dispatch. QML must not infer these rules from visual state.
- An empty `inline_editor` reserves zero editor height in the shared standard metrics calculator. Default-backed ports without a rendered editor retain ordinary single-row spacing and their default-value payload; visible editors still expand rows. The real-host input-controls probe covers Process Run, Email Send, and Construct Design, including node-height and anchor parity.
- Sensitive property values are sanitized through `qml_safe_spec_property_value` before either the full node-property payload or inline-property items reach QML. Only `{has_value, scope}` may cross this boundary; persisted DPAPI envelope fields and plaintext are forbidden.
- Preview helpers derive only from the cache record named by `NodeSolutionFact.retained_record_id`: Item safe value; List count plus up to eight indexed values; Tree branch/item counts plus up to eight paths and eight items per shown branch; each text sample is at most 160 characters. Expired retained records may project stale bounded previews, while Panel display/copy requires a current retained fact. Every displayed/copied item still passes through the same callback-free projector, so full DataTrees, arrays, tables, handles, or plugin values never enter scene payloads.
- Every execution preview state also carries the fixed `{kind, text, swatches, thumbnail_ref}` DTO. Plane, Color Map (at most eight swatches), Node Visual, and Agent Model have current bounded typed-inline projections. Typed carriers require the exact production catalog/spec records and valid schema/carrier/payload facts; count-allowlisted handle metadata and artifact labels remain identity/path/hash/provenance-free. Secret and SSH Host runtime markers become unavailable recursively before string conversion, including in Panel rows/copy. Thumbnail production, rendering, file/network/model I/O, and automatic surface selection remain absent.
- `hide_optional_ports` is a view-local payload filter for unused optional ports: connected optional rows stay visible, while hidden rows are also removed from node/minimap geometry.
- Every port payload dict carries `flow_state`, resolved per port by `ea_node_editor/ui/support/port_flow_state.py`. Current non-empty values are filled green, authored defaults outlined green, required waiting inputs yellow, empty/inactive/never-run outputs gray, and `data_type_warning` red. Disabled edges contribute no runtime value. Pinned by `tests/test_port_flow_state.py`.
- Each active-node payload also carries QML-safe readiness port/property labels and required/any-of/conditional rules from its validated `NodeTypeSpec`. `ExecutionStateProps` feeds those primitive facts into the shared evaluator for immediate post-insertion diagnostics; it must not infer business prerequisites or serialize plugin objects.
- Node payloads project canonical help fields from the registered spec, and visible port payloads project `label or key`, authored descriptions, direction/type facts, and safe status summaries for canvas tooltips. Never serialize raw runtime strings, paths, arrays, handles, or plugin objects into these help fields.
- Title-icon projection asks the registry for provenance for both trusted descriptors and public function entries. Public package provenance points at the immutable validated generation so payload builders never resolve package assets from mutable install roots.
- Inline property items also project `minimum`/`maximum`/`step` (slider inline editor range roles) from `PropertySpec` via `ui/support/node_presentation.py::build_inline_property_items`.
- Scene mutation helpers route graph edits through `ValidatedGraphMutation`, `GraphRecordMutation`, and focused graph operation modules; do not reintroduce the retired workspace mutation service path.
- Scene mutation helpers own model payload rebuilds, targeted node/edge deltas, scene selection notifications, and history replay deltas. Shell-side refresh aftermath for workspace edit actions is centralized in `MutationUiEffects` and should not absorb scene publication logic.
- `EmbeddedViewerOverlayManager` consumes the existing `node_delta_payload` rather than treating every `nodes_changed` emission as a full native-overlay rebuild: unrelated node IDs skip viewer sync, viewer position/resize reasons use transform-only sync, affected viewer content/removal and unknown/full-rebuild payloads keep the safe full path.
- Compact-pill title changes for Boolean Toggle, Number Slider, Select, and Trigger update the title and fitted `x`/`width` together through the scene mutation path. The fitted geometry preserves the node's right edge, and the combined edit is one undoable persisted mutation; do not publish a second resize history entry from QML after the rename.
- Node `visual_style` is passive-only in the active scene: style mutations on active and `compile_only` nodes are ignored without a history entry, and their scene payloads omit the field. Edge `visual_style` remains durable and only its normalized `display_mode` is projected for active-data wire presentation. Passive and unresolved node styles keep the existing projection path.
- Edge structural delta entries in `graph_scene/context.py` shallow-copy cached edge payload dictionaries; consumers treat those payloads as read-only, so do not reintroduce `copy.deepcopy` on the per-edge delta hot path without a mutating consumer.
- Node mutations (remove/move/resize/geometry) that reference a node the model cannot resolve in the active workspace/scope must call `_resync_scene_after_stale_mutation()` instead of silently returning: the request came from a rendered visual, so the scene is stale and a full rebuild flushes phantom rows and their QML delegates. `GraphInteractions.remove_node` routes its "Node not found" branch through `scene.remove_node` for the same resync. Pinned by `tests/test_graph_scene_stale_view_resync.py`.
- Targeted payload-cache writes must never trust `node_payload_location_by_id` blindly: resolve slots through `_GraphScenePayloadCache.resolve_node_payload_slot()` / `resolve_minimap_payload_slot()`, which verify the slot still holds the keyed node. On mismatch (the duplicate/phantom-node corruption signature) the `replace_cached_*` helpers return `None` and publish paths fall back to `rebuild_models()` plus a `payload_cache_slot_identity_mismatch` mutation counter; `slot_identity_mismatch_count` is surfaced via the payload-cache counters. Do not add new keyed writes that index the collections directly.
- Durable node link mutations publish targeted node payload updates with ordered `links` and `link_count`; keep cached selected-node payloads and graph-scene visible node payloads synchronized.
- Node comment mutations publish targeted node payload updates with ordered `comments`, `comment_count`, and `comment_badge`; keep cached selected-node payloads and graph-scene visible node payloads synchronized.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_graph_scene_presentation_facts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_scene_bridge_bind_regression.py tests/graph_track_b/scene_model_graph_scene_suite.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/qml_preference_bindings.py tests/test_plot_node_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_output_mode_ui.py tests/test_graph_action_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_graph_scene_stale_view_resync.py tests/test_graph_scene_payload_slot_guards.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_port_flow_state.py tests/test_repo_owned_node_documentation.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_tree_ui.py tests/test_graph_surface_input_controls.py -k "dataflow or port_and_edge_authoring" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_flow_edge_labels.py tests/graph_track_b/scene_model_graph_scene_suite.py -k "active_data_wire or display_modes or request_rewire_edges" --ignore=venv -q
```

## Breadcrumbs
- [QML Bridge Wiring](qml_bridge_wiring.md)
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)
- [Durable Node Linking](durable_node_linking.md)
- [SSH/SFTP Nodes](ssh_sftp_nodes.md)

## Update Triggers
Update when payload fields, compact data-type projection/catalog generation, compatible-endpoint snapshots, dynamic-port groups, geometry, authored/display/condition/sensitive presentation, Interval 1D or searchable-enum projection, access/modifier/Principal or edge-enabled/display-mode projection, bounded node/port rich previews, compact-pill title/geometry mutations, durable node link/comment projection, active-data wire presentation, projection ownership, scene mutation routing, plot embedded-render suppression metadata, or scene bridge tests change.

## 2026-07-11 Performance Ownership

- `GraphScenePayloadBuilder` creates one frozen presentation-facts record per invocation and reuses effective ports, metrics, bounds, icon/minimap facts, and endpoint anchors across node/backdrop/minimap/edge builders.
- Canvas inline properties and Inspector properties use the same registered `PropertyEditAdapterContext` route. Accepted-output refresh compares only selector-facing metadata and defers publication while the corresponding editor has focus.
- Stable title/position/connection payloads patch keyed cache slots. Single structural edge add/remove updates canonical sorted edge arrays and incident/pair/source-port/target-port indexes incrementally; bulk, endpoint, partial, identity, and builder-fallback cases reindex through the existing path.
- Visible publication uses `replace_existing_payloads` only when IDs and visibility are stable; sparse comment/link badges are separate from the full visible-node model.

## 2026-07-14 Node Insertion Performance

- Single-node additions validate and build only the requested in-scope node, then append its visible row through one Qt insert transaction instead of recomposing the visible model.
- Fragment paste publishes one batch addition delta for inserted active-scope nodes and internal edges. Expanded Group backdrops update affected membership and occupied-bounds payloads in the same delta; Group Peek, collapsed backdrops, stale caches, and identity mismatches retain the full-rebuild fallback.
- Insertions update selection state before publication but defer the selection notification until the new rows are present. `GraphCanvasStateBridge` reuses those rows when selection membership is already satisfied, removes deselected offscreen-only rows directly, and retains the full viewport query for dirty/deferred models or newly selected offscreen nodes that are not represented.
- Pure node-addition deltas append endpoint and minimap projections without rebinding the complete endpoint model. The retained QML edge cache accepts the same validated addition delta; removals, mixed updates, locked/proxy additions, stale caches, and ambiguous payload identity keep the conservative full-projection fallback.
