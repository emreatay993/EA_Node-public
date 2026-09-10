# Tooltips And Tooltip Tiers

## Purpose
Use this for tooltip manager behavior, tooltip policy tiers, central tooltip copy, shell tooltip presentation, and tooltip tier packet evidence.

## Start Here
- `ea_node_editor/ui/shell/tooltip_manager.py`
- `ea_node_editor/ui/shell/tooltip_policy.py`
- `ea_node_editor/ui/tooltips/`
- `ea_node_editor/ui/tooltips/viewer.json`
- `ea_node_editor/ui_qml/components/common/TooltipCopy.js`
- `ea_node_editor/ui_qml/components/common/ManagedToolTip.qml`
- `ea_node_editor/ui_qml/components/graph/GraphNodeHeaderLayer.qml` - schema-backed node help and warning-diagnostic badge tooltips.
- `ea_node_editor/ui_qml/components/graph/GraphNodePortsLayer.qml` - schema-backed port help plus status-only flow summaries.
- `tests/test_passive_graph_surface_host.py`

## Focused Verification
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_tooltip_copy_registry.py --ignore=venv -q
.\venv\Scripts\python.exe -m unittest tests.test_select_surface.SelectSurfaceTests.test_select_pill_renders_and_dropdown_commits_selected_index -v
.\venv\Scripts\python.exe -m unittest tests.test_boolean_toggle_surface.BooleanToggleSurfaceTests.test_pill_toggle_renders_and_commits -v
.\venv\Scripts\python.exe -m pytest tests/graph_surface/number_slider_suite.py::PassiveNumberSliderSurfaceTests::test_pill_surface_renders_row_and_suppresses_standard_header -q
.\venv\Scripts\python.exe -m pytest tests/test_passive_graph_surface_host.py -k "ports_use_projected_input_state or family_accent_binding" --ignore=venv -q
.\venv\Scripts\python.exe -m pytest tests/test_markdown_hygiene.py --ignore=venv -q
```

Viewer capability-disabled copy belongs in `viewer.json`; shared viewer
controls must keep disabled items hoverable and show the exact unavailable
reason.

`ManagedToolTip` owns explicit shell-themed QML tooltip chrome using the
`themeBridge` palette and a rounded card. Its implicit width is capped by
`maximumTextWidth`, so plain and rich text content receives a bounded width and
wraps. QML callers use it instead of the native `ToolTip` control.
`ManagedToolTip` renders as a popup window
(`popupType: Popup.Window` with a negative bottom inset carrying the shadow
tail) so tooltips stack above native embedded-surface overlays (plots,
viewers, web pages); platforms without popup-window support fall back to the
in-scene item.

Because that popup is a real top-level OS window, `ManagedToolTip` owns its own
dismissal lifecycle: Qt does not withdraw a windowed popup when the application
loses focus, when the host window is minimized, or when a hover-exit event is
never delivered, so an unguarded tooltip can survive as a floating window over
the desktop and over other applications. `managedVisible` therefore also
requires `Qt.application.active`, an anchor window that is not
`Window.Hidden`, and a visible anchor item, and the control carries a bounded
`timeout` as a backstop. Use `Qt.application.active` and never
`Window.active` here: under `QQuickWidget` the QML scene lives in a
`QQuickWidgetOffscreenWindow` that the window manager never activates, so
`Window.active` is permanently `false` and would suppress every tooltip.
An internal watchdog closes an open tooltip when its anchor item travels more
than `anchorMoveThreshold` in scene coordinates (canvas pan, node drag, view
switch); Qt delivers no pointer event when an item moves out from under a
stationary cursor, so both `MouseArea.containsMouse` and `HoverHandler.hovered`
stay stuck true in that case and callers cannot detect it themselves.

Node and port descriptions are dynamic schema data, and execution diagnostics
are dynamic runtime data. They stay out of the static copy registry and use
`ManagedToolTip` with `general`, `inactive`, or `warning` category policy.
Graph-node header and port tooltips use the host's published floating-toolbar
side and zoom, placing themselves on the opposite side with an 8 px gap.
Node help combines the display name, category path, description, keywords, and
an optional retained run-count footer. It uses explicit RichText formatting for
the bold title, muted category, description/keywords spacing, divider, and
optional footer. Port help uses the same hierarchy for a bold label, muted
direction/type/access metadata, authored description, divider, and status or
preview footer. Ordinary action/control and inactive tooltips remain plain text.
The compact title-owning Data/Control pills (Number Slider, Boolean Toggle,
Select, and Trigger) reuse that same header-owned Help text and policy instead
of duplicating metadata formatting; the Trigger pill binds it to both its
centered button tooltip and a whole-pill hover tooltip.
Port grips and visible labels share authored description, direction/type/family/access,
up to eight bounded accepted-type labels, and availability/inactive state; the same
bounded summary feeds the existing port `MouseArea` accessibility name and description.
Edge type-warning reasons remain edge-owned and do not enter port text. Status-only
summaries (`Empty`, `Set`, `Connected`, `Available`, or `No current output`) never
expose raw retained output values. Visible
labels keep this documentation under `general` even when a port is inactive;
the grip/indicator keeps the separate inactive-reason tooltip under `inactive`.
Neutral passive-flow ports intentionally publish no tooltip; they are visual
connection grips without data or execution semantics.

## Breadcrumbs
- [UI Shell, Controllers, And Presenters](../subsystems/ui_shell.md)
- [Retained Work-Packet QA Evidence And Spec Navigation](work_packet_docs_status_qa.md)

## Update Triggers
Update when tooltip manager APIs, policy tiers, central copy files, port type/availability/accessibility summaries, shell display behavior, `ManagedToolTip` popup-window lifecycle guards, or tooltip packet proof changes.

## 2026-07-11 Performance Ownership

- Tooltip/category projection is computed once per existing policy/theme revision. Tooltip wording remains centralized and unchanged by the cache.
