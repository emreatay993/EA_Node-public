# Node Execution Visualization

## Purpose
Use this for node execution state projection, declarative readiness diagnostics, fixed active-node semantic colors, non-glow progress overlays, retained runtime facts, and per-port grip flow state.

## Lookup Aliases
- `grip flow state`
- `live port runtime state`
- `per-port execution states`
- `bounded rich preview`

## Start Here
- `ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py` - owning Qt projection for workspace-scoped runtime facts.
- `ea_node_editor/nodes/readiness.py` - shared pure prerequisite evaluator and structured issue contract.
- `ea_node_editor/ui_qml/components/graph/GraphNodeHeaderLayer.qml` - warning/error badges and the structured warning hover table.
- [Port-flow semantic resolver](../../../ea_node_editor/ui/support/port_flow_state.py) - pure topology/runtime grip-state resolution.
- `ea_node_editor/ui/shell/state.py` - ShellRunState session caches and revisions.
- `ea_node_editor/ui/shell/controllers/run_controller.py` - command/Auto/Trigger/history behavior.
- `ea_node_editor/ui/shell/controllers/run_event_controller.py` - sole shell runtime-event filtering, routing, logs, viewer adoption/reset, and terminal transitions.
- `ea_node_editor/ui/shell/controllers/run_projection_controller.py` - execution-state, accepted-cache, solution-fact, availability, timing, warning, failure, and status projection.
- `ea_node_editor/ui/support/solution_output_cache.py` - bounded retained-record-ID cache selection and eviction.
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasExecutionFacts.qml` - shared-by-reference QML facts object.
- `tests/test_port_flow_state.py` - focused port-flow semantic and projection proof.
- `tests/test_data_type_ui_projection.py` - bounded type projection, warning separation, and rich-preview security proof.
- `ea_node_editor/ui/media_panel_source.py` and `tests/test_media_panel_source_resolution.py` - effective Media Panel runtime/source-state projection.

## Do Not Start Here
- `ea_node_editor/execution/run_messages.py` and `ea_node_editor/execution/protocol_codec.py` - inspect the worker event contract only when the retained event lacks a required fact; do not scan the execution package by default.
- `ea_node_editor/graph/effective_ports.py` - authored/effective topology, not live execution-state ownership.
- Do not begin in the generic tests directory; use the focused test above.

## Runtime Fact Matrix

| Fact | Event or state owner | Projection and QML consumer | Freshness and limits |
| --- | --- | --- | --- |
| Node lifecycle | `node_started` / typed `node_settled` update ShellRunState running, completed, warning, start-time, and elapsed fields through `RunProjectionController`. Solution freshness comes only from `NodeSolutionFact`. | ExecutionStateProps running/completed/warning/start-time plus `node_solution_freshness_lookup` -> GraphCanvasExecutionFacts. | Workspace-scoped; missing freshness means `never`, and the generic current/expired fact has no styling consumer in this task. |
| Node run count | Each store-accepted settlement increments a separate monotonic session counter. | `node_run_count_lookup` -> GraphCanvasExecutionFacts.nodeRunCountLookup -> shared node-help tooltip footer. | Independent of bounded cache eviction; session-only and workspace-scoped. |
| Settled result | Runtime-enriched `node_settled` names the exact retained record ID/key/digest/disposition only when the store accepted it. | `solution_output_cache.retained_output_record(...)` selects that record for port/property/Panel/media/fullscreen/command/presenter/deck consumers. | Maximum two records per node, 4,096/512 MiB per workspace, and 16,384/2 GiB globally; oldest unpinned eviction is deterministic and unfit payloads become metadata-only. |
| Failure focus | Node-scoped failed settlements and fatal `run_failed` records shell failure focus. | Failed lookup/revision/title -> GraphCanvasExecutionFacts -> fixed red/pink body, badge, error inspection, and status navigation. | Requires a workspace and node id; fatal worker/timeout paths should preserve both when known. Ordinary data wires never turn red for execution failure. |
| Port flow / grip state | Settled node outputs are retained by run and workspace; the pure resolver combines typed current/non-empty results with scene node/edge payloads. | `port_flow_state_lookup` -> GraphCanvasExecutionFacts.portFlowStateLookup -> GraphNodeHost.resolvedPortFlowState. | Filled green output = current value, outlined green input = an unwired declared property default, yellow = unresolved required input without a default, gray = empty/inactive/never-run, red = invalid type only. Disabled edges contribute no value and do not suppress a property default. |
| Bounded rich preview | `ExecutionStateProps` derives the fixed `{kind, text, swatches, thumbnail_ref}` DTO from the existing output cache. | Port/edge help payloads and Panel display/copy consume the same safe projection. | Fail-closed exact safe built-ins only, capped at 160 characters, 8 items/swatches, and depth 3 with control stripping and no callbacks/I/O. Plane, Color Map, Node Visual, and Agent Model have bounded typed-inline projections; Color Map alone emits up to eight swatches. Thumbnail production remains dormant, and preview data never selects a surface. |
| Warning diagnostics | The shared evaluator consumes projected required/any-of/conditional rules, normalized properties, enabled-edge overrides, and current port-presence facts; retained worker warning messages are then merged and deduped. | Scene readiness payload + `ShellRunState.runtime_warning_messages_by_workspace_id` -> ExecutionStateProps -> GraphCanvasExecutionFacts.nodeDiagnosticLookup -> fixed yellow body and header warning badge. | Rows expose `severity`, `code`, target keys/labels, optional primary port key/label, and display message. The existing 240 ms zoom-stable `ManagedToolTip` renders a grammatical count, divider, zero-based indices, and wrapped messages. Failure still outranks warning chrome. No raw output values are projected. |
| Selected-run preview | RunController builds workspace-scoped rows, node states, blocked state, and a revision before execution. | Selected-run preview properties -> GraphCanvasExecutionFacts -> preview overlay; active node chrome remains neutral. | Session-only and active-workspace guarded; it is a pre-run projection, not a worker event. |

## Settled Event To Grip Chain

The order is `generation callback` -> `CorexRuntime` store handling/enrichment -> execution event stream -> `ShellWindow.execution_event` -> one queued `RunEventController.handle_execution_event` connection -> run-state routing through `RunProjectionController` -> one direct `ViewerSessionBridge.handle_viewer_execution_event` delivery -> retained-record cache/fact and viewer projection. `ViewerSessionBridge` has no second signal subscription; its existing epoch/request filters remain authoritative.

Stale records are ignored for current grip flow. Typed EMPTY remains distinct from a value containing explicit `None`; incoming edge `data_type_warning` is the only red invalidity fact. A separate `availability_warning` also blocks settlement without becoming a type warning or moving its edge-owned reason into port text.

## Common Changes
- `solution_output_cache.current_output_value(...)` exposes only the current accepted, available output for schema projection. Signal Plot's inspector and inline selectors consume this callback and refresh on accepted-output/freshness changes; stale/missing records do not trigger IO or script execution.
- Exact catalog-validated ImageValue outputs project a bounded `thumbnail` rich-preview DTO. SHA-keyed entries reuse the existing `viewer-preview-cache` image provider under the reserved `image-value` workspace key; runtime solution reset clears those entries and bytes never enter QML payloads.
- `ExecutionStateProps.media_panel_source_lookup` uses the injected read-only project source plus existing run-state/output caches. It publishes only the bounded source-resolution DTO; raw Path/String/Image values stay Python-only. Node, edge, execution, workspace, and exposure changes reuse the existing `port_flow_state_changed` notification path.

- Data-port grip state, bounded preview, and per-node retained run count are projected from typed settled results in the existing output cache. Keep these lookups on the shared `GraphCanvasExecutionFacts.qml` object; `GraphNodeHost.qml` consumes them but does not own the projection route. Do not drill them through each host or add a second runtime-value cache.
- Rich previews never call custom `repr`/`str`, iterators, mappings, or file/network/model providers. Typed carriers require the exact production `DataTypeCatalog`, exact `DataTypeSpec` records read without overridable catalog callbacks, and valid type/schema/carrier/payload facts. Engineering/FEM/geometry/mesh handles may expose only allowlisted integer counts; artifacts expose only the catalog label plus `artifact`, never IDs, refs, scopes, hashes, paths, provenance, or transport identity.
- Secret and SSH Host runtime markers become unavailable recursively before key/value string conversion, including nested containers and hostile non-string keys. Panel display rows and both copy modes route each item through this same callback-free projector.
- Warning diagnostics call the same evaluator as `NodeExecutor`; do not rebuild prerequisite semantics from `optional` or grip color. Evaluator issues can also mark implicated visible ports waiting, while retained worker warnings are merged without duplicate rows. An unwired declared default uses the outlined-green `default` state. A completion arriving after invalidation must not repopulate warning caches. `GraphNodeHost.isWarningChromeNode` combines transient warning state with retained diagnostics; failed state outranks the yellow body, selected active blue fill outranks it while retaining the warning badge, and running alone does not add a body color.
- Active and `compile_only` node body/outline/title/port-label/inline-control colors resolve from the fixed light/dark palette in `GraphNodeHostTheme.qml`, not graph-theme or per-instance colors. State priority is selected, reserved disabled, failed, warning, then neutral. Selected active nodes use the fixed blue fill/outline without a glow; diagnostic badges remain visible. The disabled palette is test-resolvable preparation only and adds no model, command, persistence, or execution state.
- `GraphNodeChromeBackground.qml` contains no active-node lifecycle, selected-run-preview, or selection halo/pulse/flash/glow. Running retains only its existing non-glow progress/elapsed presentation; completed and `freshRunNodeLookup` states render the neutral body. Passive selected outline/glow remains graph-theme-owned, including the shape-aware flowchart path.
- `fresh_run_node_lookup` is now a derived current-only compatibility projection over `NodeSolutionFact`; no mutable shell fresh-node set or per-record stale flag remains. Expired retained records stay inspectable through the selector, while current flow/Panel/media rendering requires a current fact.
- Red failure chrome is driven by `run_failed.node_id` through shell failure focus and `GraphCanvasStateBridge.failed_node_lookup`; keep fatal worker-death and timeout paths node-scoped when the active node is known.
- The shared header renders warning/error indicators as filled circles centered on the top border near the right corner, outside the title layout. Warnings retain their structured hover table; error icons retain an accessible execution-halted label and hover hint. Neither diagnostic state reduces title width or changes node geometry.
- Unhandled `run_failed` is reported only through the fixed red/pink body (`focus_failed_node` failure focus) plus the console error/traceback log; never open a modal dialog (e.g. `QMessageBox`) from execution-event handlers, since the nested event loop inside the queued slot freezes then crashes the app.
- `RunEventController.handle_execution_event` catches and logs its own run-state faults so the app stays alive instead of aborting, then independently calls the viewer bridge's direct consumer. Viewer-delivery faults are separately logged and cannot prevent an already-routed projection or terminal transition. Do not add a ShellWindow/viewer self-registration wrapper, second subscription, timer, `Qt.callLater`, or another queued hop (no `sys.excepthook` is installed).
- Python Script failure tracebacks reaching the console are sanitized to the user's `<script>` frames by default; the hidden Ctrl+Alt+Shift+D developer-mode toggle (gated by the `COREX_DEV_MODE` env capability and stored on `ShellRunState.developer_mode_active`) restores full host tracebacks for the session.
- Python Script `BaseException` failures, including `SystemExit` and `KeyboardInterrupt`, should still surface as node-scoped failed settlements or fatal events so visualization stays tied to the script node.
- Python Script `timeout_sec` kills are fatal process-isolated failures and should still include the running script node ID for canvas highlighting.
- Execution/control edge flash animation and every active-node execution glow are removed. Edge rendering reflects data structure, enabled/empty state, selection, and type validity only; node-level running progress plus warning/error body fills remain.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_port_flow_state.py tests/test_process_client.py tests/test_execution_worker.py tests/test_shell_run_controller.py tests/test_passive_runtime_wiring.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_projection_controller.py -k "runtime_warning_messages" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_run_event_controller.py --ignore=venv -q
.\venv\Scripts\python.exe -m unittest tests.test_passive_graph_surface_host.PassiveGraphSurfaceHostTests.test_graph_node_host_persistent_diagnostic_uses_warning_badge_and_execution_precedence -v
.\venv\Scripts\python.exe -m pytest tests/test_port_flow_state.py tests/test_data_tree_ui.py tests/test_run_controller_unit.py tests/test_media_panel_source_resolution.py -k "settled or preview or empty or failure or media_panel" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/graph_surface/passive_host_interaction_suite.py tests/graph_track_b/qml_preference_bindings.py tests/graph_track_b/qml_preference_rendering_suite.py tests/test_node_restyle_mockup.py --ignore=venv -q
```

## Breadcrumbs
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)
- [Edge Routing, Labels, And Progress](edge_routing_labels_progress.md)

## Update Triggers
Update when typed settlement events, bounded rich-preview DTO/security, availability/type-warning separation, node-scoped fatal failure handling, fixed active-node palettes/state precedence, non-glow running progress, passive selection glow, property-default/waiting grip states, or run visualization tests change.

## 2026-05-29 status-bar node jump update

- Status-bar clicks route to the existing workspace navigation and failed-node focus paths to jump to failed, running, warning, or completed execution nodes.
- Failed/error targets prefer the recorded failed workspace and node; running, warning, completed, and auto targets use the active execution workspace when present and otherwise fall back to the active workspace.

## 2026-05-29 status bar layout switch update

- Execution status navigation remains shared across both status-bar layout options; layout selection changes only visual grouping and does not add a second status action path.
