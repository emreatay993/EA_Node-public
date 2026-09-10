# Viewer Session, Native Overlay, And Fullscreen

## Purpose
Use this for execution viewer sessions, native overlay lifecycle, fullscreen content, and viewer host surfaces.

## Lookup Aliases
- `viewer session ownership`
- `fullscreen toolbar click`
- `engineering viewer shared memory`

## Start Here
- `ea_node_editor/ui_qml/viewer_session_bridge.py`
- `ea_node_editor/ui_qml/viewer_host_service.py`
- `ea_node_editor/ui_qml/engineering_viewer_widget_binder.py`
- `ea_node_editor/ui/plot_preview_cache_provider.py`
- `ea_node_editor/ui_qml/embedded_viewer_overlay_manager.py`
- `ea_node_editor/ui_qml/viewer_control_bridge.py`
- `ea_node_editor/ui_qml/content_fullscreen_bridge.py`
- `ea_node_editor/ui_qml/ContentFullscreenOverlay.qml`
- `ea_node_editor/ui/media_panel_source.py`
- `ea_node_editor/ui_qml/components/graph/passive/GraphMediaVideoFullscreenRenderer.qml`
- `ea_node_editor/ui_qml/components/shell/PythonScriptGuidePane.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurfaceBody.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/GraphViewerSurface.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/ViewerSelectionControls.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/ViewerToolButton.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/ViewerQuickControls.qml`
- `ea_node_editor/ui_qml/components/graph/viewer/ViewerSidePanel.qml`
- `ea_node_editor/ui_qml/components/graph/tabular/TabularFullscreenSurface.qml`
- `ea_node_editor/execution/backend_client.py`
- `ea_node_editor/execution/worker.py`
- `ea_node_editor/execution/viewer_messages.py`
- `ea_node_editor/execution/protocol_codec.py`
- `ea_node_editor/execution/worker_protocol.py`
- `ea_node_editor/execution/viewer_session_service.py`
- `ea_node_editor/nodes/viewer_runtime_contracts.py`
- `tests/test_viewer_session_bridge.py`
- `tests/test_content_fullscreen_bridge.py`
- `tests/test_content_fullscreen_bridge_lifecycle.py`
- `tests/test_viewer_control_bridge.py`
- `tests/test_viewer_host_service.py`
- `tests/test_viewer_surface_contract.py`
- `tests/test_backend_client.py`
- `tests/test_process_client.py`
- `tests/test_external_python_client.py`
- `tests/test_trusted_client.py`
- `tests/test_execution_worker.py`
- `tests/test_execution_viewer_service.py`
- `tests/test_engineering_viewer_node.py`
- `tests/test_engineering_viewer_widget_binder.py`

## Do Not Start Here
- `ea_node_editor/ui_qml/graph_scene_bridge.py` for viewer-session and fullscreen-toolbar ownership.

## Related Help Reference
- `ea_node_editor/ui/dialogs/input_reference_dialog.py` documents user-facing fullscreen and media fullscreen keys. Update it when overlay close keys, PDF page navigation controls, video controls, or fullscreen surface gestures change.

## Routing Notes
- `_ViewerSessionProjection` contains the execution-owned canonical session model. Command methods publish responsive phase, option, playback, and error hints through `_ViewerPendingDisplay`; the next authoritative worker event replaces that pending display and is normalized once in `_apply_authoritative_projection`. QML reads project the stored canonical model plus pending display without recoercing it.
- Viewer node outputs are `RuntimeHandleRef` values with semantic ID `COREX.Viewer.Session`, kind `corex.viewer_session`, and identity-only metadata (`workspace_id`, `node_id`, `session_id`, `backend_id`). `ViewerSessionBridge` decodes NodeSettled values with the injected active catalog and sends an idempotent `open_viewer_session` command for the worker-owned authoritative projection; it does not accept or project a raw session dictionary.
- Each worker session owns a collision-safe cache scope and leases source/materialized handles into it. Alias inputs deduplicate, replacement acquires new ownership before releasing the prior ref, and run cleanup leaves the active viewer lease alive. Explicit close completes cleanup and reports disposer failures; invalidation/reset warn and continue while releasing all owned refs.
- Model Viewer authoritative opens carry `scene_order`, `scene_labels`, and flat
  `scene:<id>`/`native_source:<id>` references. Removed scene keys release their
  leases after replacements have been acquired; identity-only opens still merge.
  Engineering transport v2 contains ordered layers with stable IDs. The binder
  keys actors and selection sources by ID, not display name, and the sidebar
  edits `scene_styles` through ViewerControlBridge. Export receives live ID-based
  visibility and appearance; scene-specific queries carry the selected layer ID.
- Engineering sessions may hold both a memory-backed prepared scene and its
  native OCPBody or Geometry Group source. The binder accepts the backend's bounded,
  hashed shared-memory VTK XML descriptor, deep-copies the reconstructed
  dataset before closing its attachment, and retains the existing file-backed
  path as fallback. Shared-memory unlinking remains backend/session cleanup,
  never QML ownership.
- Backend viewer routing prefers explicit `run_id`, then `(workspace_id, session_id)`, then workspace ownership. Only an unowned open may use a unique active backend or default-process fallback; update, close, materialize, and query fail closed when ownership is absent or stale. Opens are provisional and request-ordered so the newest pending request wins, a late older success cannot replace it, and a failed open removes only its own request before restoring the next pending request or baseline owner. Process/external/trusted generation retirement clears viewer requests and ownership before successor events are accepted; trusted events carry their source generation, worker resets release session scopes and transports, close/shutdown clear owners, and completed-run ownership is capped at 64.
- Every viewer command/response includes workspace and node invalidation epochs. Runs stage immutable participant-local process/trusted/external snapshots plus an independent high-level/Bridge projection after backend ensure/recycle. Worker context installation is separate from snapshot validation/adoption; the Bridge's sole partial-run projection is `adopt_committed_invalidation(...)`, while true global resets use `project_all_run_required(...)` and legacy direct worker runs keep service-global invalidation. Worker preflight validates only the selected concrete snapshot/digest, emits `run_preflight_accepted` first, and waits for the identity-bound parent commit; `viewer_invalidation_committed` carries the projection digest. The sealed commit follows high-level invalidation/active then child state-before-viewer lock order, sends a pre-encoded payload through a pinned transport without callbacks or lock reacquisition, and applies all local plans or none. Concrete responses validate locally and translate to projection epochs before callbacks. The irreversible post-delivery finalizer publishes adoption before draining buffered events and always clears its gate. Delivery failure/cancel/timeout/preflight failure leaves Bridge/client/service state unchanged; committed post-delivery failures retain invalidation. Only a fresh selected service may align its selected concrete workspace baseline. Project/load/reset remains workspace-global, with project load covering old and incoming workspace IDs.
- Registry publication refuses active/pending viewer sessions and shares the execution admission guard with new viewer opens. Once idle, `ViewerSessionBridge.replace_data_types(...)` moves the bridge to the accepted frozen catalog in the same reversible shell transaction.
- Runtime composition injects execution-client, active-workspace, and live workspace providers into `ViewerSessionBridge`; active-workspace/workspace/model/registry providers plus preferences, the save callback, and direct viewer-host reference into `ViewerControlBridge`; QML-engine/save/bookmark callbacks into `ViewerHostService`; and the active-workspace provider into `PlotHostService`. The four classes store no `_shell_window` and perform no shell service discovery; QObject `parent=host` is lifecycle ownership only.
- Exactly two construction-cycle callbacks are late-bound: viewer overlay camera capture resolves the later `ViewerHostService`, and viewer-host PageUp/PageDown bookmark cycling resolves the later `ViewerControlBridge`. Preview capture/cache remains host-owned; do not route it through the session bridge or hide either callback in a shell facade, adapter, or dependency bag.
- Viewer and plot hosts each construct their own plain `NativePresentationHandoff`. The shared owner gates demotion on the expected preview source plus one render frame, rejects stale timeout serials, disconnects when idle/cancelled/shut down, and queues completion outside `afterRendering`. Capture plus viewer-session demotion or plot-overlay release remain distinct host callbacks; do not merge host state, binders, windows, backend policy, or overlay geometry.
- The same composition root supplies `ContentFullscreenBridge` with live model, registry, active-workspace, and project-context providers plus its exact scene/viewer/run/script/dialog/trim/Web-artifact owners. The bridge stores no `ShellWindow`, policy service, aggregate dependency bag, or compatibility alias. Candidate workspace/name/node/title/type facts are frozen together for each open.
- `ViewerHostService` and `PlotHostService` receive the content bridge directly, connect once during construction, retain that connection across reset, and disconnect at terminal shutdown. Dynamic model/registry providers remain live across replacement, and scene/manager workspace disagreement still fails closed.
- Fullscreen and detached viewer content share
  `components/graph/viewer/ViewerQuickControls.qml` below the native viewport
  and `ViewerSidePanel.qml` on its right. The quick strip groups Render Mode,
  View, Camera, and Docking in that order and uses a horizontal Flickable with
  chevrons. The viewport Rectangle keeps
  `objectName: "contentFullscreenViewerViewport"` because the overlay manager
  resolves it by name to pin the same native widget.
- Script-editor fullscreen keeps the shared `ScriptCodeEditorPane.qml` and adds
  only a fullscreen Guide toggle plus `PythonScriptGuidePane.qml`. The guide is
  a local, theme-aware rich-HTML document; it must not create a second editor,
  browser host, PDF pipeline, or executable help surface.
- Node-scoped viewer writes go through `ViewerControlBridge`: normalize and
  mutate node properties through the scene bridge, then synchronize the live
  viewer session. It owns viewer options, camera bookmarks, saved engineering
  selections, query, and export. `ContentFullscreenBridge` owns fullscreen
  lifecycle and payload selection only.
- Camera bookmarks persist in `camera_bookmarks`; their current cycle index is
  runtime-only. Applying a bookmark restores the complete camera/projection
  state and synchronizes `parallel_projection`. `PageUp`/`PageDown` cycle with
  wraparound in both QML focus and the native viewer event filter.
- `ViewerHostService` owns one detached QWidget per workspace/node and reparents
  the same native widget with priority `fullscreen > detached > inline`.
  Detach/fullscreen/redock, repeated-open focus, and cleanup on reset/session or
  project loss must never create a second renderer. Before a retained native
  widget changes top-level parents, the host calls the binder's optional
  `prepare_for_reparent` hook, then calls `refresh_after_attach` after the new
  presentation owns it. Detached windows show the destination before the child
  and refresh so VTK widgets can rebind to the current interactor. A retryable
  post-attach result remains pending and is never published as a ready overlay;
  a terminal refresh failure releases the bad attachment and preserves the real
  host error.
- Content fullscreen terminal shutdown disconnects scene topology/node/workspace and execution notifications, drops queued tabular identities, destroys the active Web bridge without close/export persistence, rejects late work, and cannot recreate lazy providers. Normal user close still owns authored video/Web state persistence before terminal project/window teardown.
- Detached windows hold their session live through viewer presentation holds:
  `ViewerHostService.open_detached_viewer` acquires
  `ViewerSessionBridge.add_viewer_presentation_hold(node_id)` (pending and
  window paths) and every close/dock/reset path releases it. Held presentation
  keys stay `live_mode=full` in `_desired_live_mode_map` even when canvas
  gestures call `clear_viewer_focus()` or the inline surface deactivates
  embedded interaction — without the hold the session demotes to proxy and the
  host sync closes the detached window as `node_unavailable`.
  `detached_viewer_active` also reports pending detach requests so the
  Detach/Dock toolbar button toggles correctly before the window materializes.
- Inline viewers start in proxy with no native widget or warm-up. Selection,
  hover, and single-click remain proxy; only a left-button double-click inside
  the proxy viewport requests inline live mode. Selection/background loss
  clears that explicit activation, and reselecting does not reactivate it.
- Transient canvas pan/wheel/box zoom, node drag/resize, and wire drag keep the
  explicitly activated session at `live_mode=full` and send zero worker
  live-mode updates. QML and the host locally suppress the native overlay by
  hiding it, marking its geometry unready, and disabling widget updates, then
  restore the same widget after the gesture. After true demotion, at most one
  widget previously created by explicit inline activation may remain hidden
  and non-updating for unchanged
  session/transport reactivation. Fullscreen- or detached-only widgets are not
  eligible; close/delete/reset/invalidation/backend or transport identity
  change/workspace loss/shutdown releases retained state. Do not add a viewer
  pool or parking-container handoff.
- `GraphViewerSurfaceBody.qml` defers embedded-interaction sync
  (`_queueEmbeddedInteractionSync` → `Qt.callLater`) because
  `ViewerHostService.set_embedded_interaction_active` re-emits
  `ViewerSessionBridge.sessions_changed`; calling it synchronously from the
  `embeddedInteractionActive` change handler re-enters the still-updating
  `bridgeSessionProjectionSeed` binding and logs
  `Binding loop detected for property "bridgeSessionProjectionSeed"`. Overlay
  activation handoff therefore settles one event-loop pass after a
  selection/session flip.
- Fullscreen viewer shortcuts (Space, Left/Right, Home, R) are handled twice on purpose: a viewer branch in the overlay's `Keys.onPressed` for QML focus, and a `_FullscreenShortcutFilter` installed by `ViewerHostService` on the fullscreen-target native widget because the overlay manager focuses the QtInteractor, which consumes key events before QML. `ViewerSessionBridge` provides `step_back`/`set_step_index`; camera/stat slots (`viewer_render_stats`, `apply_standard_view`, `reset_overlay_camera`, `camera_state_snapshot`, `apply_overlay_camera_state`, `export_viewer_screenshot`) live on `ViewerHostService`. Update `input_reference_dialog.py` when these keys change.
- Project install/open/new flows reset `ViewerHostService` before `ViewerSessionBridge.project_loaded(...)` reseeds project viewer projections, so fixed `(workspace_id, node_id)` viewer keys cannot reuse stale native overlays, preview-cache entries, or cached view state from a previous project instance.
- `EmbeddedViewerOverlayManager._sync_impl` computes overlay rects from `mapToItem` state, so before computing it forces `ensurePolished()` up the viewport's ancestor chain and geometry-observes every chain link from `graphNodeViewerViewport` up to the node card — not just the two endpoints. Positioners apply repositions in the polish pass (frame boundary), which can land after the queued zero-delay sync, and a reposition of an intermediate container (e.g. the viewer body Column shifting the viewport row when the status strip re-wraps on width change) fires no geometry signal on the card or the viewport itself. Keep both mechanisms when touching overlay sync or viewer body layout; `test_live_overlay_geometry_tracks_rendered_resize_preview_state` is the regression gate.
- Fullscreen Media Panel uses stable top-level `content_kind="media"` and derives image/PDF/video from `media_payload.media_kind`. The bridge and inline dispatcher share `resolve_media_panel_source`; non-ready source transitions clear URLs and unload the prior renderer while the overlay stays open with an explicit message.
- Fullscreen PDF display lives in `ContentFullscreenOverlay.qml` as a QML `PdfDocument` plus `PdfMultiPageView` bound to the media payload's `resolved_source_url`. The overlay owns clamping/search/zoom/fit/rotation/navigation and clears the document source on release; graph mutation no longer rewrites the authored page value.
- Fullscreen animated images use a loader-owned `AnimatedImage` bound to the payload's resolved local-file URL. Fullscreen always animates supported multi-frame media, ignores the saved inline playback mode, and owns playback exclusively until close; static/single-frame/unsupported/corrupt images remain provider-backed.
- Fullscreen web page display first tries to reuse the already-loaded graph `WebPageHost`. `ContentFullscreenOverlay.qml` looks up the matching `graphNodeWebPageHost` by active node id, attaches its live `WebEngineView` into `contentFullscreenBorrowedWebPageViewport`, and restores it on close. The standalone fullscreen `WebPageHost` is the fallback for cold opens, unavailable inline hosts, and non-borrowable states.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_native_presentation_handoff.py tests/test_viewer_session_bridge.py tests/test_execution_viewer_service.py tests/test_viewer_control_bridge.py tests/test_viewer_host_service.py tests/test_viewer_preview_cache_provider.py tests/test_embedded_viewer_overlay_manager.py tests/test_viewer_surface_contract.py tests/test_viewer_surface_host.py tests/test_execution_viewer_protocol.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_content_fullscreen_bridge_lifecycle.py tests/test_media_panel_qml_surface.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_shell_isolation_phase.py -k "main_window__lifecycle__fullscreen_media_handoff" --ignore=venv -q -n 0
.\venv\Scripts\python.exe -m pytest tests/main_window_shell/shell_runtime_contracts.py -k content_fullscreen --ignore=venv -q
```

## Breadcrumbs
- [Viewer Surfaces, Native Overlays, And Fullscreen](../subsystems/viewer_surfaces.md)
- [Neutral CAD/FE Engineering Viewer](neutral_cad_fe_engineering_viewer.md)

## Update Triggers
Update when viewer bridge, worker-side session-handle lease ownership, host service, engineering viewer binder, viewer preview cache provider, overlay manager, fullscreen bridge, Python Script fullscreen guide, fullscreen tabular persistence, viewer protocol, or Help reference fullscreen coverage changes.

## 2026-07-11 Performance Ownership

- Viewer/plot binders and pools allocate once on first use behind stable bridges. `ContentFullscreenOverlay` uses a retained loader and must restore the same live native viewer/overlay object after close or workspace changes.
