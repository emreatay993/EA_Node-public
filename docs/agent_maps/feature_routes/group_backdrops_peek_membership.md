# Group Backdrops, Peek, And Membership

## Purpose
Use this for Group geometry, membership, collapse/peek behavior, collision avoidance, and Group workflows.

## Start Here
- `ea_node_editor/graph/group_backdrop_geometry.py`
- `ea_node_editor/graph/group_backdrop_mutation_ops.py`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui_qml/graph_scene_mutation/group_backdrop_ops.py`
- `ea_node_editor/ui_qml/graph_scene_mutation/collision_avoidance_ops.py`
- `ea_node_editor/ui_qml/components/graph/passive/GraphGroupBackdropSurface.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasRootLayers.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasNodeDelegate.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHostGestureLayer.qml`
- `tests/main_window_shell/group_backdrop_integration.py`

## Input Layer Notes
- Groups render as a visual layer under edges plus a transparent input overlay above edges. Keep edge click, context, and hover-cursor routing explicit in the input overlay path so edges inside a Group remain selectable while empty Group areas still drag/select the Group.
- Groups publish the same cardinal neutral passive flow ports as other passive annotation nodes. The under-edge visual host suppresses port rows; the above-edge input overlay host owns visible/clickable port handles so handles stay above edges without drawing duplicates.
- Group live-resize edge redraw is conditional: unconnected Groups keep the no-redraw fast path, while Groups with connected visible ports request edge redraw so endpoint anchors follow the resized backdrop.
- Live drag offsets for Groups must update both rendered hosts for the same backdrop id: the under-edge visual host and the above-edge input overlay host. If only one host is offset, the non-moving host leaves title text behind until drag release.
- `GraphCanvas.edgeAtScreen(...)` is the non-mutating edge hover/hit probe; `GraphCanvas.handleEdgePressAtScreen(...)` is the mutating press delegation path.
- Group-backdrop wrap transactions are graph-owned in `group_backdrop_mutation_ops.py`; scene helpers should call that operation directly and keep membership fields derived in payload projection.
- The display name is `Group`, registered as `passive.annotation.group_backdrop` under `Utilities > Canvas`. Its hidden title defaults to empty; an untitled selected Group shows `Double click to edit title`, and double-click opens the shared title editor. It has no body/rich-text content, Inspector-editable properties, or shadow.
- `tests/qml_quick/tst_graph_node_host.qml` owns the four pure-QML Group host checks: chrome/shadow suppression, untitled edit prompt, icon-independent collapsed title, and long-title width. `tests/test_group_backdrop_contracts.py` retains the seven catalogue, model, metric, serialization, and scene-projection checks.
- The focused mounted-shell integration checks share the existing `main_window__shell_basics_and_search__workspace_actions` child. They retain the real Library add/drop route, shortcut noncollision, Peek menu eligibility, current `Group` fallback, direct/nested/outside peek visibility, editing, explicit exit, and click-away dismissal without reviving the obsolete 12-test shard.

## Focused Verification
```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_CONTROLS_STYLE = "Basic"
& (Join-Path $env:QT_ROOT "bin\qmltestrunner.exe") -input tests/qml_quick/tst_graph_node_host.qml -eventdelay 0 -keydelay 0 -mousedelay 0 -o -,txt
Remove-Item Env:QT_QPA_PLATFORM, Env:QT_QUICK_CONTROLS_STYLE -ErrorAction SilentlyContinue
.\venv\Scripts\python.exe -m pytest tests/test_group_backdrop_contracts.py tests/test_group_backdrop_membership.py tests/test_group_backdrop_interactions.py tests/test_graph_action_contracts.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_shell_isolation_phase.py -k "main_window__shell_basics_and_search__workspace_actions" --ignore=venv -q -n 0
```

## Breadcrumbs
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)
- [Graph Scene Payload And Projection](graph_scene_payload_and_projection.md)

## Update Triggers
Update when Group geometry, membership rules, peek/collapse UI, collision avoidance, or Group input-layer routing changes.

## 2026-07-11 Performance Ownership

- Comment badges publish through the sparse visible badge model. Multi-drag membership freezes once at gesture start and shared canvas scheduling carries scalar offsets; do not restore per-node timers or the retired inert hover repeater.

## 2026-07-14 Insertion Publication

- Adding a node or Group backdrop among expanded backdrops recomputes membership and occupied bounds from cached candidates, then publishes only the addition and changed membership rows.
- Active Group Peek, any collapsed backdrop, or stale/incomplete cache state keeps the full scene rebuild because visible membership or proxy edge ownership can change.
