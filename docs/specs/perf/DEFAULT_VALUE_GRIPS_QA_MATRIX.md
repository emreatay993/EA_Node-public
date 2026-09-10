# Default Value Grips QA Matrix

- Updated: `2026-07-19`
- Scope: explicit property-backed input defaults, unwired runtime fallback, outlined grips and embedded editors, active-node port-lock removal, view-local optional filtering, atomic Ctrl-drag endpoint reassignment, and preservation of unavailable add-on plus passive-object locks.

## Locked Scope

- `PortSpec.uses_property_default` / `in_port(..., uses_property_default=...)` is the only opt-in. Registry validation requires a compatible same-key `PropertySpec`; matching names alone do not create defaults. The shipped built-in/add-on catalogue marks each audited input/property pair explicitly.
- `NodeInstance.properties` is the only default-value store. With no enabled incoming wire, runtime constructs the declared Item/List/Tree `DataTree` and then applies input modifiers. Enabled incoming value, `None`, empty, or failure settlements override the saved default; disabled-only wires do not.
- Opted-in input payloads expose `default_property` with property/editor metadata and `overridden_by_input`. Unwired defaults render as outlined-green grips. Supported inline editors reuse existing property controls and commit paths; connected inputs hide the editor without clearing the property, and disconnect restores it.
- Active-node `locked_ports`, `hide_locked_ports`, lock chrome, lock toggles, lock gestures, lock pruning, and lock-aware runtime payloads are removed. `hide_optional_ports`, unavailable add-on placeholders, and passive-object locks remain.
- Ctrl-drag moves one unambiguous edge endpoint atomically, Ctrl+Shift appends, and blank release disconnects only that edge. Edge identity/state/metadata and unaffected ordering survive; cancel or invalid release is a no-op.
- `.cxproj` has no new field or schema bump. Existing properties and `hide_optional_ports` round-trip; obsolete active-lock keys are not written.

## Automated Verification

| Coverage Area | Requirement Anchors | Command |
|---|---|---|
| Explicit default declaration, validation, built-in adoption, and Process Run JSON-list default | `REQ-GRAPH-019`, `AC-REQ-GRAPH-019-01` | `.\venv\Scripts\python.exe -m pytest tests/test_registry_validation.py tests/test_process_run_node.py tests/test_window_library_inspector.py --ignore=venv -q` |
| Item/List/Tree fallback, enabled-wire precedence, falsey values, modifier order, persistence omission, and optional filtering | `REQ-GRAPH-019`, `REQ-PERSIST-021` | `.\venv\Scripts\python.exe -m pytest tests/test_default_port_values.py tests/test_dataflow_execution_runtime.py tests/test_serializer.py tests/test_port_availability.py --ignore=venv -q` |
| Atomic endpoint move/disconnect, replacement versus append, metadata/order preservation, rollback, and undo | `REQ-GRAPH-020`, `REQ-UI-048` | `.\venv\Scripts\python.exe -m pytest tests/graph_track_b/scene_model_graph_scene_suite.py tests/test_graph_scene_bridge_bind_regression.py tests/test_data_tree_ui.py --ignore=venv -q` |
| Default-grip payload/chrome, editor reuse, override/restoration, active-lock removal, and locked-placeholder preservation | `REQ-UI-034`, `REQ-UI-036`, `REQ-UI-037`, `REQ-PERF-012` | `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests/test_graph_surface_input_contract.py tests/test_graph_surface_input_controls.py tests/test_graph_surface_input_inline.py tests/test_port_flow_state.py --ignore=venv -q` |
| Requirements, proof links, renamed maps, and generated route index | `REQ-QA-034`, `AC-REQ-QA-034-01` | `.\venv\Scripts\python.exe -m pytest tests/test_traceability_checker.py --ignore=venv -q` |

## Final Closeout Commands

| Command | Purpose |
|---|---|
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | Requirement, acceptance, and traceability alignment |
| `.\venv\Scripts\python.exe scripts/check_markdown_links.py` | Renamed proof/map link integrity |
| `.\venv\Scripts\python.exe scripts/check_agent_maps.py` | Map banners, coverage, and generated route-index integrity |
| `.\venv\Scripts\python.exe scripts/run_verification.py --mode fast --summarize-output` | Cross-route closeout after all implementation slices land |

## 2026-07-19 Execution Results

| Command | Result | Notes |
|---|---|---|
| `.\venv\Scripts\python.exe -m unittest tests.test_traceability_checker -q` | PASS | All 89 traceability assertions passed after the requirement/proof rename. |
| `.\venv\Scripts\python.exe scripts/check_traceability.py` | PASS | Requirement, acceptance, and traceability rows align. |
| `.\venv\Scripts\python.exe scripts/check_markdown_links.py` | PASS | Renamed proof and route links resolve. |
| `.\venv\Scripts\python.exe scripts/check_agent_maps.py` | PASS | Regenerated route/source indexes cite existing paths. |

Feature-focused and `fast` results are recorded by the final integration run after the backend and QML slices settle; this matrix does not reuse historical port-lock packet results as proof of the replacement feature.

## Remaining Manual Smoke Checks

1. Add an active node with a declared default and confirm its unwired grip is outlined green, the embedded editor commits through the existing property path, and the same value remains editable in the inspector without a duplicate canvas body/group row.
2. Connect the input and confirm the wire overrides the property while hiding the embedded editor; disconnect and confirm the same saved value and editor return immediately.
3. Verify slider, toggle, text/number, dropdown, path, color, and textarea defaults where declared; a blank or unsupported editor must leave only the outlined grip.
4. Verify required inputs without defaults stay yellow, invalid types alone render red, normal drop replaces, Shift-drop appends, Ctrl-drag reconnects, Ctrl+Shift appends, and blank Ctrl-drag release disconnects without opening Quick Insert.
5. Save/reopen and duplicate a workspace: property defaults and `hide_optional_ports` survive, active lock fields do not reappear, and unavailable add-on placeholders plus passive-object locks remain locked.

## Residual Desktop-Only Validation

- Offscreen tests cannot judge final outlined-green contrast, dense-row editor spacing, pointer feel, or editor-versus-canvas drag arbitration on a physical Windows display.
- Manual desktop acceptance should confirm edge selection is understandable before Ctrl-dragging a socket with more than one incident edge.

## Residual Risks

- External installed add-ons must opt in explicitly; add-ons that only happen to use matching port/property names retain ordinary inputs.
- Unsupported `inline_editor` metadata intentionally renders no embedded control until an existing shared editor supports it.
