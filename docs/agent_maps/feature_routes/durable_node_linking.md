# Durable Node Linking

## Purpose
Use this for durable node link records, persisted node comment threads, inspector link/comment rows, graph hover link cards, node comment count pills/popovers, app-created rich-text `corex-link:` anchors, and linking/comment feature icon/theme ownership.

## Start Here
- `ea_node_editor/graph/node_links.py`
- `ea_node_editor/common/optimization_links.py`
- `ea_node_editor/graph/node_comments.py`
- `ea_node_editor/graph/records.py`
- `ea_node_editor/graph/record_payloads.py`
- `ea_node_editor/graph/record_mutation_ops.py`
- `ea_node_editor/persistence/project_codec.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/selection_and_scope_ops.py`
- `ea_node_editor/ui_qml/graph_canvas_command/`
- `ea_node_editor/ui_qml/graph_scene/context.py`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui/shell/presenters/inspector_presenter.py`
- `ea_node_editor/ui/shell/inspector_projection.py`
- `ea_node_editor/ui_qml/shell_inspector_bridge.py`
- `ea_node_editor/ui_qml/MainShell.qml`
- `ea_node_editor/ui_qml/components/GraphCanvas.qml`
- `ea_node_editor/ui_qml/components/common/NodeLinkEditorForm.qml`
- `ea_node_editor/ui_qml/components/shell/WorkspaceCenterPane.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorNodeLinksSection.qml`
- `ea_node_editor/ui_qml/components/shell/InspectorNodeCommentsSection.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeLinkHoverLayer.qml`
- `ea_node_editor/ui_qml/components/graph/overlay/GraphNodeCommentPopoverLayer.qml`
- `ea_node_editor/ui_qml/components/graph/passive/GraphRichTextBlock.qml`
- `ea_node_editor/ui/icon_registry.py`
- `ea_node_editor/ui_qml/components/shell/icons/TABLER_SOURCES.txt`
- `tests/test_parameter_setup_pool_links.py`

## Visual References
- `mockups/linking_feature/ConceptD_InspectorList.qml` for the inspector list concept.
- `mockups/linking_feature/ConceptE_HoverBadge.qml` for the graph hover badge concept.
- `mockups/linking_feature/LinkCard.qml`, `LinkGlyph.qml`, and `ThemePalette.qml` for card, glyph, and theme-token reference.
- `mockups/comment_badge_showcase/ConceptA_CountPill.qml`, `CommentGlyph.qml`, and `ThemePalette.qml` for the production node comment Count Pill, glyph, and token reference.

## Ownership Notes
- Durable node links are graph-owned node metadata. `NodeLinkRecord` entries live in ordered `NodeInstance.links` and should be mutated through graph-owned upsert, remove, and move operations.
- Parameter Setup-to-Pool semantics reuse those persisted node-link records with exact shared role tokens from `common/optimization_links.py`; the context-menu/command/history path creates or removes the links as ordinary undoable graph mutations, and execution consumes them only as hidden ordering metadata.
- Node comments are graph-owned node metadata. `NodeCommentRecord` entries live in `NodeInstance.comments`, persist as `.cxproj` node payload `comments`, and should be mutated through graph-owned upsert, delete, resolve/reopen, pin, resolve-all, and mark-read operations.
- Node comment scene payloads project `comments`, `comment_count`, and `comment_badge = { count, open_count, resolved_all, unread, preview_comments }`; do not use `link_count`, `unresolved`, or arbitrary node properties for comment state.
- Node links use flat payload fields: `target` remains the target node ID string, and node links additionally carry `target_node_id` plus `target_workspace_id`. Non-node links keep the old string-only target behavior.
- `.cxproj` node payloads persist ordered link lists. Current and old documents without link data should load with `links: []`; legacy node links with only `target` default their `target_workspace_id` to the owning workspace during decode.
- Graph scene node payloads project both ordered `links` and `link_count`; targeted mutation publication should keep cached node payloads synchronized.
- Inspector rows, node/workspace picker options, and hidden target IDs are shell-inspector bridge data. QML should use `inspectorBridgeRef`, not retired shell-window helper calls.
- `NodeLinkEditorForm.qml` is the shared inspector/canvas editor: it owns all five link kinds (Web, File, Folder, Workspace, Node), searchable structured targets, hidden IDs, target autofill/reset, validation, and pick-mode draft suspension. `InspectorNodeLinksSection.qml` remains the inspector list/save owner and saves through `upsert_selected_node_link`.
- Canvas Add Link is create-only and opens `GraphNodeLinkHoverLayer.qml` through `GraphCanvas.requestAddNodeLinkForNode` and `GraphCanvasRootLayers.qml`; the editable-node right-click row and link-hover-card Add link button both use that route. It no longer redirects the user to the inspector.
- `GraphNodeLinkHoverLayer.qml` keeps the source workspace/node and mounts the create editor in the existing anchored, viewport-clamped link card. Save uses `upsert_node_link` on that source; failed saves or missing targets retain the draft, and a removed source aborts it.
- Target picking is owner-aware: `MainShell.qml` distinguishes inspector and canvas picks, `WorkspaceCenterPane.qml` handles node/tab selections, and canvas picks return to the original source workspace/node before applying a picked target or resuming a cancelled draft. A target workspace-tab pick does not activate that workspace.
- Cross-workspace node link opening should route through `jump_to_graph_node(target_workspace_id, target_node_id)`. Same-workspace canvas opening should continue through the graph-scene command bridge so node-specific behavior such as video timestamp links remains intact.
- Hover badges/cards live in the graph canvas overlay path through `GraphNodeLinkHoverLayer.qml`; keep card visuals theme-aware, rooted in the mockup references above, and synchronized with the current visible scene model so removed nodes or links cannot leave stale cards behind.
- Node comment Count Pill and canvas popover live in `GraphNodeCommentPopoverLayer.qml`, mounted from `GraphCanvasRootLayers.qml`; keep the 18 px pill, 9 px radius, `content + 16` width, 4 px glyph/text gap, bottom-edge straddle, `nodeRight - pillWidth - gripZone - 10` placement, and 16 px resize-grip clearance aligned with Concept A.
- The popover card uses RectangularShadow chrome, a header X close button (`graphNodeCommentPopoverCloseButton`), author-initial avatars, status chips, relative timestamps (shared CommentFormat helper in `ea_node_editor/ui_qml/components/common/`), and hover-revealed icon-only per-comment actions (`reply`, `edit`, `pin`/`pin-off`, `check`/`rotate-clockwise`, `delete` via `uiIcons` + `ManagedToolTip`); footer primaries (Post/Save, New, Resolve all) stay text buttons.
- The Inspector comment editor is `InspectorNodeCommentsSection.qml`; it is synchronized with the canvas popover through the same graph-owned comment records, not a separate draft store, and mirrors the popover's avatar/chip/timestamp meta rows and icon-only per-comment actions via InspectorButton.
- App-created inline links use Markdown anchors like `[label](corex-link:<link_id>)`. `GraphRichTextBlock.qml` owns hover/open routing for those anchors while preserving ordinary Markdown links.
- Deleting a durable link record should unwrap exact generated `corex-link:<link_id>` anchors on the same node back to plain label text. Editing a record should not rewrite anchor labels.
- Link icons must be registered Tabler-style shell icons consumed through `uiIcons.sourceSized(...)`; keep SVG provenance in `TABLER_SOURCES.txt`.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_icon_registry.py tests/test_inspector_projection.py tests/test_serializer.py::SerializerPortLockingTests tests/main_window_shell/bridge_contracts_library_and_inspector.py tests/test_graph_canvas_split_bridges.py tests/main_window_shell/bridge_qml_boundaries.py::ShellInspectorBridgeQmlBoundaryTests tests/main_window_shell/bridge_qml_boundaries.py::GraphCanvasQmlBoundaryTests::test_graph_canvas_root_layers_mount_node_link_hover_layer --ignore=venv -q
$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/main_window_shell/view_library_inspector.py::MainWindowShellViewLibraryInspectorTests::test_qml_selected_node_inspector_shows_node_link_rows tests/main_window_shell/view_library_inspector.py::MainWindowShellViewLibraryInspectorTests::test_selected_node_link_picker_options_cover_all_workspaces_and_store_hidden_ids tests/main_window_shell/view_library_inspector.py::MainWindowShellViewLibraryInspectorTests::test_qml_node_link_target_pick_fills_hidden_ids_and_saves_without_raw_id_entry --ignore=venv -q; $exitCode = $LASTEXITCODE; Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue; exit $exitCode
.\venv\Scripts\python.exe -m pytest tests/test_graph_node_link_hover_layer.py tests/test_graph_surface_input_controls.py -k "link or node_context_menu_routes_editors" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/scene_model_graph_scene_suite.py::GraphSceneBridgeTrackBTests::test_node_link_mutations_publish_targeted_node_payload --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_track_b/scene_model_graph_scene_suite.py::GraphSceneBridgeTrackBTests::test_node_comment_mutations_publish_targeted_node_payload_and_persist tests/main_window_shell/bridge_qml_boundaries.py::GraphCanvasQmlBoundaryTests::test_graph_canvas_root_layers_mount_node_comment_count_pill_layer --ignore=venv -q
```

## Breadcrumbs
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)
- [Persistence, Documents, Artifacts, And Migrations](../subsystems/persistence.md)
- [QML Bridge Wiring](qml_bridge_wiring.md)
- [Graph Scene Payload And Projection](graph_scene_payload_and_projection.md)
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)
- [Shared Graph Typography](shared_graph_typography.md)
- [Assets, Icons, Title Icons, And Theme Assets](../subsystems/assets_icons_theme.md)

## Update Triggers
Update when node link/comment record shape, semantic Parameter Setup-to-Pool link roles, serialization/defaulting, mutation/history behavior, inspector/canvas shared link-editor or target-pick routing, hover badge/card or count-pill/popover QML, `corex-link:` rich-text handling, icon provenance, or linking/comment feature tests change.

## 2026-07-11 Performance Ownership

- Link/comment count badges consume the sparse badge projection; full visible-node payloads remain the owner of durable link/comment content. Keep wording/persistence behavior unchanged when optimizing badge publication.
