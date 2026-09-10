# Port Availability And Default Values

## Purpose
Use this for static and resolved instance-port availability, dynamic-port groups, explicit property-backed input defaults, declarative readiness, Item/List/Tree fallback assembly, optional-port filtering, default-grip projection, and wire interaction rules.

## Start Here
- `ea_node_editor/nodes/node_specs.py`
- `ea_node_editor/nodes/decorators.py`
- `ea_node_editor/nodes/registry.py`
- `ea_node_editor/nodes/instance_resolution.py`
- `ea_node_editor/nodes/property_normalization.py`
- `ea_node_editor/nodes/readiness.py`
- `ea_node_editor/graph/effective_ports.py`
- `ea_node_editor/graph/invariant_kernel.py`
- `ea_node_editor/graph/validated_mutation.py`
- `ea_node_editor/ui/port_availability.py`
- `ea_node_editor/ui/graph_interactions.py`
- `ea_node_editor/ui/shell/controllers/workspace_edit_controller.py`
- `ea_node_editor/ui_qml/graph_scene_payload/`
- `ea_node_editor/ui_qml/graph_scene_mutation/policy.py`
- `ea_node_editor/ui_qml/graph_scene/policy_bridge.py`
- `ea_node_editor/ui_qml/graph_scene_mutation_history.py`
- `ea_node_editor/ui_qml/graph_scene/command_bridge.py`
- `ea_node_editor/ui_qml/graph_scene/state_support.py`
- `ea_node_editor/ui_qml/graph_canvas_command/scene_mutation_ops.py`
- `ea_node_editor/ui_qml/graph_canvas_command/node_creation_ops.py`
- `ea_node_editor/ui_qml/graph_canvas_state/execution_state_props.py`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortsLayer.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortRow.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodePortContextMenu.qml`
- `ea_node_editor/ui_qml/components/graph_canvas/GraphCanvasInteractionState.qml`
- `tests/test_registry_validation.py`
- `tests/test_property_normalization.py`
- `tests/test_default_port_values.py`
- `tests/test_port_availability.py`
- `tests/test_port_flow_state.py`
- `tests/test_data_type_ui_projection.py`
- `tests/test_graph_type_enforcement.py`
- `tests/test_execution_type_enforcement.py`
- `tests/test_viewer_viewport.py`
- `tests/test_media_panel.py`
- `tests/test_media_panel_creation_preferences.py`

## Dataflow Port Notes
- Active ports are `data`; unrelated passive connectors remain `flow`. Unavailable add-on placeholders and passive-object locks are separate contracts and remain locked where declared.
- `ea_node_editor.nodes.instance_resolution.resolve_instance_ports` is the shared resolver for graph invariants, scene projection, readiness, and worker execution. It combines static ports with each dynamic group's ordered ordinary `PortSpec` values from the same normalized current properties; dynamic ports are data-only and cannot use property defaults or static readiness declarations. `nodes/property_normalization.py` owns generic defaults/coercion, dynamic backing-property updates, and exact Select/Number Slider/Web normalization; `NodeRegistry` keeps only catalog/spec lookup plus the three intentional normalization API entry points.
- Stable dynamic keys carry presentation, readiness/flow-state, endpoint, modifier, and Principal identity. Label-mode rename changes only the sparse display label and preserves wires; key-mode rename and removal prune the old key's wires and sparse state through graph-owned mutation.
- Dynamic add controls use a 19px center interval and 24px keyboard-accessible targets. Remove controls sit 18px from the socket with a 20px-wide target/hover circle, leaving 1px beside the enlarged socket. Standard/viewer bottom metrics reserve the resting add dot, allowing hover targets to extend beyond the chrome. Socket hit areas retain outward padding without covering the controls. Python label-column measurements include removable controls; QML consumes those columns and shared JavaScript intervals. Keep Python/JavaScript metrics and the real-canvas dynamic-handle probes aligned.
- `GraphNodePortRow.qml` is the direct shared delegate for one input or output. It derives side, notch mirror, label alignment, default capability, and resize-hover behavior from direction and owns shared geometry, grip state, gestures, dynamic remove, label/edit, general tooltip/accessibility, and interactive rectangles. `GraphNodePortContextMenu.qml` owns the access, modifier, Principal, and dynamic insert/rename/remove descriptors in a shared `ShellContextPopup`; it calls the existing layer methods through one explicit `portsLayer`. `GraphNodePortsLayer.qml` retains models, dynamic-group scheduling/mutations, notch cache/source, aggregate rectangles, context/edit state, add controls, the menu anchor/open request, and the minimal input/output-only children. There is no per-port/menu registry, action framework, edge scan, Loader, Timer, Connection, or Binding added by these owners.
- `PortSpec.uses_property_default` and the public `in_port(..., uses_property_default=...)` helper are explicit opt-ins. Registry validation requires a compatible same-key `PropertySpec`; matching names alone do not create defaults. Keep the audited built-in/add-on pairs aligned with their actual same-key properties rather than maintaining a parallel allowlist.
- Media Panel deliberately has a same-key authored `source` property and optional Source input with `uses_property_default=False`. Per-instance exposure selects source authority; hiding the port prunes its wire in the same undoable mutation, while creation-time `exposed_port_overrides` selects blank/connect/seeded behavior without inferring from property values.
- `PortSpec.required` has no optional-by-omission default for active data inputs. Use `required=True` for one unconditional input, `required=False` for an optional input or a port governed by `ReadinessRequirementSpec`, and declare any-of/conditional property or port groups on `NodeTypeSpec.readiness_requirements`.
- With no enabled incoming wire, runtime assembly converts the authored property to the declared Item/List/Tree `DataTree` and applies normal input modifiers. Enabled incoming settlement overrides it; disabled-only wires do not. Falsey authored values remain valid.
- An exact built-in `TypedInlineValue` property default takes the bounded typed
  path: registry validation calls `validate_carrier` directly, and the worker
  validates it against the candidate input types before returning the same
  object unchanged. Construct View uses this path for its Point3D/Vector3D
  defaults. Wrong type identity, schema, or payload rejects; handles,
  artifacts, markers, subclasses, native values, Interval1D handling, and
  conversions are not widened.
- Scene input payloads expose `default_property` only for opted-in active inputs, including key/value/type/editor metadata and `overridden_by_input`. Unwired defaults render as outlined-green grips and reuse existing property editor/commit paths; enabled incoming wires keep the editor visible but muted and disabled, show a safe upstream value or neutral unavailable placeholder, and never delete the authored property.
- Property presentation keeps authored and display facts separate. `value` is the saved local property; `display_value` is a bounded safe upstream projection only when `display_value_available` is true. `overridden_by_input`, `condition_enabled`, and `editor_enabled` make connection and `PropertyConditionSpec` state explicit. A wired or condition-disabled row stays visible with its grip and topology, while its local editor is disabled; disabled edges restore authored behavior.
- Runtime settled-value overlay recomputes declarative `enabled_when` from current source values, then combines it with distinct adapter-owned `adapter_condition_enabled` / `adapter_condition_reason` facts before applying canvas policy and wire override. It must not re-enable an add-on's contextually inapplicable editor, or retain stale declarative/wire disablement after current state changes.
- Normal active-data drop validates first and atomically replaces every incoming wire at that input. Shift-drop appends in persisted order. `GraphCanvasCommandBridge.request_rewire_edges(...)` routes the ordered Ctrl-drag bundle through `GraphInteractions.rewire_edges(...)` and the scene batch mutation/history path; Ctrl+Shift copies only the sole or explicitly selected edge, while blank release disconnects the moved bundle. Before forwarding a new endpoint, `GraphInteractions` runs `unavailable_connection_reason(...)` for every proposed connection; a blocked member rejects the complete request.
- `GraphSceneMutationPolicy.compatible_endpoint_snapshot(...)` resolves the current effective ports, candidate direction, primary/accepted target union, conversions, and runtime-check compatibility against the active catalog. QML requests one fingerprinted snapshot when a real wire drag activates, reuses it for move/release, and rejects malformed or generation-mismatched results; `ValidatedGraphMutation` and `GraphInvariantKernel` still revalidate the commit.
- Port availability stays distinct from type validity. Payload normalization publishes `availability_warning`/`availability_reason`, while `graph_geometry/route_payload.py` owns edge-level `data_type_warning`/`data_type_warning_reason`; either warning blocks settlement, but availability never creates a type warning and edge type reasons do not become port text.
- Runtime availability is cleared by exact solution invalidation IDs and prepared recompute IDs. Mutation-time workspace clears were removed from `graph_interactions.py` and `WorkspaceEditController`; workspace-wide clears remain only for true project/workspace replacement, and rejected late settlements cannot republish availability.
- `hide_optional_ports` keeps connected optional rows visible and filters only unused optional rows from the active-view payload and row geometry. Active-node `hide_locked_ports`, locked-row chrome, lock gestures, and lock-aware edge rejection are retired.
- Registry edge pruning reuses a per-pass `RegistryValidationPassMemo`; duplicate connections, input capacity, exposed/hidden ports, and subnode pin ports still resolve through graph-owned invariant checks.
- Dynamic-port and subnode semantic property edits validate every resolved primary/accepted data-type ID against the active registry before writing. A valid semantic change prunes only incident wires that the catalog now marks incompatible or unresolved; a failed preflight leaves properties, topology, order, revision, and history unchanged.

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py tests/test_default_port_values.py tests/test_port_availability.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_data_type_ui_projection.py tests/test_graph_type_enforcement.py --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py tests/test_execution_type_enforcement.py tests/test_viewer_viewport.py --ignore=venv -q
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py tests/test_graph_surface_input_inline.py tests/test_port_flow_state.py --ignore=venv -q
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
```

## Breadcrumbs
- [Nodes, Registry, Built-ins, And Plugin Loading](../subsystems/nodes_registry_builtins.md)
- [Execution Snapshot, Client, Worker, And Protocol](../subsystems/execution.md)
- [Graph Domain, Mutation, Transforms, And Hierarchy](../subsystems/graph_domain.md)
- [Graph Canvas Rendering, Input, And Viewport](../subsystems/graph_canvas.md)

## Update Triggers
Update when dynamic group declarations/resolution/stable-key behavior, explicit default/readiness/condition declarations, registry validation, typed-inline or native runtime fallback conversion, authored/display presentation facts, effective-port compatibility snapshots, availability/type-warning separation, optional filtering, default/waiting grip payload or chrome, batch edge rewire/copy, or focused tests change.
