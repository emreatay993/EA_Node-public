# UI Context Scalability Review

- Date: `2026-04-04`
- Repository: `EA_Node_Editor`
- Review mode: read-only architecture assessment focused on UI feature context cost and subagent packetization readiness

## Verdict

The UI architecture is `functional but context-expensive`.

The repository already has real package boundaries and stronger architecture notes than most desktop-app codebases, but routine UI work still pulls too much context because a few umbrella files retain too much authority:

- `ea_node_editor/ui/shell/window.py` still combines Qt host duties with too much packet-owned UI workflow state.
- `ea_node_editor/ui/shell/presenters.py` still carries multiple presenter families in one file.
- `ea_node_editor/ui_qml/graph_scene_bridge.py` still mixes bridge composition with state-support responsibilities.
- `ea_node_editor/ui_qml/components/GraphCanvas.qml` still exposes a broad root with too much root-local wiring.
- `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml` still combines geometry, caching, labels, rendering, and hit testing.
- viewer-specific surface and session behavior still spills into generic graph-editing context.
- the repo has no machine-enforced context budgets or subsystem packet contracts, so new work can drift back into umbrella files.

## Current Hotspots

Repository measurements taken on `2026-04-04`:

- `ea_node_editor/ui_qml`: `117` packet-owned `.py` / `.qml` / `.js` files, about `29,925` lines
- `ea_node_editor/ui`: `66` packet-owned `.py` / `.qml` / `.js` files, about `18,638` lines

Largest packet-relevant files:

- `ea_node_editor/ui/shell/window.py`: about `1,564` lines
- `ea_node_editor/ui/shell/presenters.py`: about `1,361` lines
- `ea_node_editor/ui_qml/components/graph/EdgeLayer.qml`: about `1,534` lines
- `ea_node_editor/ui_qml/graph_scene_bridge.py`: about `846` lines
- `ea_node_editor/ui_qml/components/GraphCanvas.qml`: about `780` lines of root orchestration plus helper forwarding
- `ea_node_editor/ui_qml/viewer_session_bridge.py`: about `1,371` lines
- `ea_node_editor/execution/viewer_session_service.py`: about `1,403` lines

## Highest-Priority Refactors

1. Reduce `ShellWindow` to a lifecycle-first Qt facade and stop routing new feature logic through it.
2. Replace the monolithic presenter file with one presenter per file behind a curated import surface.
3. Split graph-scene bridge support code away from the public bridge composition surface.
4. Reduce `GraphCanvas.qml` to composition and stable public root contract only.
5. Split edge rendering into focused helpers for math, cache or cull logic, labels, and hit testing.
6. Isolate viewer-specific UI or session behavior so ordinary canvas features do not drag the viewer stack into scope.
7. Add machine-enforced context budgets and packet contracts so future UI work cannot silently recreate umbrella files.

## Packetization Intent

The packet set below turns those findings into a sequential program:

- `P01` shrinks the shell window surface.
- `P02` splits the presenter family.
- `P03` packetizes graph-scene bridge support code.
- `P04` reduces the graph-canvas root.
- `P05` packetizes edge rendering.
- `P06` isolates viewer-specific surface and bridge context.
- `P07` adds machine-enforced context budgets.
- `P08` publishes subsystem packet contracts for future feature work.
- `P09` closes with verification, QA evidence, and docs updates.
