# Plan: Node Execution Visualization (Running / Completed States)

## Context

Users cannot currently see which nodes are executing during a workflow run. The only existing
per-node execution feedback is the **failure pulse** — a red pulsing glow on the node that
caused `run_failed`. This plan adds real-time **running** (blue pulse) and **completed**
(green flash) visualization by replicating the failure pulse architecture end-to-end.

**Approach:** Alternative A (Glowing Border Pulse) + Alternative E elapsed timer.

**Visual Reference (source of truth for design):**
[`docs/node_execution_visualization_alternatives.html`](node_execution_visualization_alternatives.html)
— Open this HTML file in a browser to see the exact target visual for each node state
(idle, running, completed). All color values, animation timings, halo sizes, and border
widths in this plan are derived from that reference. When in doubt about how something
should look, the HTML file is authoritative.

---

## Architecture Overview

The failure pulse data flows through this chain — we replicate it exactly:

```
Worker Process (NodeStartedEvent / NodeCompletedEvent)
  -> ExecutionClient.subscribe -> ShellWindow.execution_event signal
  -> RunController.handle_execution_event()
  -> ShellWindow state mutation + signal emission
  -> GraphCanvasStateBridge (pyqtProperty with notify)
  -> GraphCanvas.qml (readonly property bound to bridge)
  -> GraphNodeHost.qml (per-node boolean lookup)
  -> GraphNodeChromeBackground.qml (halo + animation)
```

No worker-side changes needed — `node_started` and `node_completed` events are already emitted.

---

## Step 1: Add Execution Node State to `ShellRunState`

**File:** `ea_node_editor/ui/shell/state.py` (lines 52-60)

Add fields after `failure_focus_revision`:

```python
@dataclass(slots=True)
class ShellRunState:
    active_run_id: str = ""
    active_run_workspace_id: str = ""
    engine_state_value: Literal["ready", "running", "paused", "error"] = "ready"
    failed_node_id: str = ""
    failed_workspace_id: str = ""
    failed_node_title: str = ""
    failure_focus_revision: int = 0
    # --- NEW: execution visualization ---
    running_node_ids: set[str] = field(default_factory=set)
    running_node_workspace_id: str = ""
    completed_node_ids: set[str] = field(default_factory=set)
    completed_node_workspace_id: str = ""
    node_execution_revision: int = 0
    node_execution_timestamps: dict[str, float] = field(default_factory=dict)
    # Maps node_id -> monotonic start time (seconds) for elapsed timer
```

**Why sets instead of single IDs:** Unlike failure (only one failed node), multiple nodes could
theoretically be running simultaneously in future parallel execution, and many nodes accumulate
as "completed" during a run. Using `set[str]` for both keeps the model forward-compatible.

---

## Step 2: Add Signal + State Methods to `ShellWindow`

**File:** `ea_node_editor/ui/shell/window.py`

### 2a. Add signal (near line 147, after `run_failure_changed`):

```python
run_failure_changed = pyqtSignal()       # existing (line 147)
node_execution_state_changed = pyqtSignal()  # NEW
```

### 2b. Add state mutation methods (after `clear_run_failure_focus` at line 876):

```python
def set_node_running(self, workspace_id: str, node_id: str) -> None:
    """Mark a node as currently running. Called on node_started event."""
    import time
    state = self.run_state
    normalized_wid = str(workspace_id or "").strip()
    normalized_nid = str(node_id or "").strip()
    if not normalized_nid:
        return
    state.running_node_workspace_id = normalized_wid
    state.running_node_ids.add(normalized_nid)
    state.node_execution_timestamps[normalized_nid] = time.monotonic()
    state.node_execution_revision += 1
    self.node_execution_state_changed.emit()

def set_node_completed(self, workspace_id: str, node_id: str) -> None:
    """Move node from running to completed. Called on node_completed event."""
    state = self.run_state
    normalized_wid = str(workspace_id or "").strip()
    normalized_nid = str(node_id or "").strip()
    if not normalized_nid:
        return
    state.running_node_ids.discard(normalized_nid)
    state.completed_node_workspace_id = normalized_wid
    state.completed_node_ids.add(normalized_nid)
    state.node_execution_revision += 1
    self.node_execution_state_changed.emit()

def clear_node_execution_state(self) -> None:
    """Reset all running/completed tracking. Called on run_started, run_completed,
    run_stopped, run_failed (fatal)."""
    state = self.run_state
    if not (state.running_node_ids or state.completed_node_ids):
        return
    state.running_node_ids.clear()
    state.running_node_workspace_id = ""
    state.completed_node_ids.clear()
    state.completed_node_workspace_id = ""
    state.node_execution_timestamps.clear()
    state.node_execution_revision += 1
    self.node_execution_state_changed.emit()
```

---

## Step 3: Dispatch Events in `RunController`

**File:** `ea_node_editor/ui/shell/controllers/run_controller.py`

### 3a. Handle `node_started` and `node_completed` (modify lines 125-129):

Current code (lines 125-129):
```python
if event_type == "run_started":
    self._host.clear_run_failure_focus()

if event_type in {"run_started", "node_started", "node_completed"}:
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)
```

Replace with:
```python
if event_type == "run_started":
    self._host.clear_run_failure_focus()
    self._host.clear_node_execution_state()

if event_type == "node_started":
    self._host.set_node_running(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)

elif event_type == "node_completed":
    self._host.set_node_completed(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)

elif event_type == "run_started":
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)
```

**Wait — ordering matters.** The original uses `if` (not `elif`) so `run_started` hits both
the clear and the set_run_ui_state. Restructure carefully:

```python
if event_type == "run_started":
    self._host.clear_run_failure_focus()
    self._host.clear_node_execution_state()
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)

elif event_type == "node_started":
    self._host.set_node_running(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)

elif event_type == "node_completed":
    self._host.set_node_completed(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)
```

But `event_type == "run_started"` is followed by more `if` checks below (for `"log"`,
`"run_completed"`, etc.). So we need to keep the structure compatible. The cleanest approach:
keep the first `if event_type == "run_started"` block (line 125-126), then replace
the compound `if event_type in {...}` at line 128 with individual dispatches.

**Exact edit:**

Replace lines 125-129:
```python
if event_type == "run_started":
    self._host.clear_run_failure_focus()

if event_type in {"run_started", "node_started", "node_completed"}:
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)
```

With:
```python
if event_type == "run_started":
    self._host.clear_run_failure_focus()
    self._host.clear_node_execution_state()

if event_type == "node_started":
    self._host.set_node_running(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )

if event_type == "node_completed":
    self._host.set_node_completed(
        event.get("workspace_id", ""),
        event.get("node_id", ""),
    )

if event_type in {"run_started", "node_started", "node_completed"}:
    self.set_run_ui_state("running", "Running", 1, 0, 0, 0)
```

### 3b. Clear on run end (modify existing handlers):

At the `run_completed` handler (line 137-138), add clear:
```python
elif event_type == "run_completed":
    self._host.clear_node_execution_state()   # ADD THIS
    self.set_run_ui_state("ready", "Completed", 0, 0, 1, 0, clear_run=True)
```

**Note:** Do NOT clear on `run_failed` — keep the last running node highlighted alongside
the failure pulse so users can see where execution was when it failed. Only clear on
fatal failures (line 152-153) where the worker resets:
```python
if bool(event.get("fatal", False)):
    self._invalidate_viewer_sessions_for_worker_reset()
    self._host.clear_node_execution_state()  # ADD THIS
```

At the `run_stopped` handler (line 156-157), add clear:
```python
elif event_type == "run_stopped":
    self._host.clear_node_execution_state()   # ADD THIS
    self.set_run_ui_state("ready", "Stopped", 0, 0, 0, 0, clear_run=True)
```

---

## Step 4: Expose Through `GraphCanvasStateBridge`

**File:** `ea_node_editor/ui_qml/graph_canvas_state_bridge.py`

### 4a. Add signal (near line 79):

```python
failure_highlight_changed = pyqtSignal()        # existing (line 79)
node_execution_highlight_changed = pyqtSignal()  # NEW
```

### 4b. Connect signal in `__init__` (after line 107):

```python
_connect_signal(shell_window, "node_execution_state_changed", self.node_execution_highlight_changed.emit)
```

### 4c. Add properties (after `failed_node_title` at line 263):

```python
@pyqtProperty("QVariantMap", notify=node_execution_highlight_changed)
def running_node_lookup(self) -> dict[str, bool]:
    shell_window = self._shell_window
    if shell_window is None:
        return {}
    run_state = getattr(shell_window, "run_state", None)
    workspace_manager = getattr(shell_window, "workspace_manager", None)
    if run_state is None or workspace_manager is None:
        return {}
    workspace_id = str(getattr(run_state, "running_node_workspace_id", "") or "").strip()
    active_workspace_id = str(workspace_manager.active_workspace_id() or "").strip()
    if not workspace_id or workspace_id != active_workspace_id:
        return {}
    return {nid: True for nid in run_state.running_node_ids}

@pyqtProperty("QVariantMap", notify=node_execution_highlight_changed)
def completed_node_lookup(self) -> dict[str, bool]:
    shell_window = self._shell_window
    if shell_window is None:
        return {}
    run_state = getattr(shell_window, "run_state", None)
    workspace_manager = getattr(shell_window, "workspace_manager", None)
    if run_state is None or workspace_manager is None:
        return {}
    workspace_id = str(getattr(run_state, "completed_node_workspace_id", "") or "").strip()
    active_workspace_id = str(workspace_manager.active_workspace_id() or "").strip()
    if not workspace_id or workspace_id != active_workspace_id:
        return {}
    return {nid: True for nid in run_state.completed_node_ids}

@pyqtProperty(int, notify=node_execution_highlight_changed)
def node_execution_revision(self) -> int:
    shell_window = self._shell_window
    if shell_window is None:
        return 0
    run_state = getattr(shell_window, "run_state", None)
    if run_state is None:
        return 0
    return int(getattr(run_state, "node_execution_revision", 0))

@pyqtProperty("QVariantMap", notify=node_execution_highlight_changed)
def running_node_timestamps(self) -> dict[str, float]:
    """Start timestamps (monotonic seconds) for running nodes — used for elapsed timer."""
    shell_window = self._shell_window
    if shell_window is None:
        return {}
    run_state = getattr(shell_window, "run_state", None)
    if run_state is None:
        return {}
    return dict(getattr(run_state, "node_execution_timestamps", {}))
```

---

## Step 5: Thread Properties Through `GraphCanvas.qml`

**File:** `ea_node_editor/ui_qml/components/GraphCanvas.qml`

After `failedNodeTitle` (line 44), add:

```qml
readonly property var runningNodeLookup: root._canvasStateBridgeRef
    ? root._canvasStateBridgeRef.running_node_lookup
    : ({})
readonly property var completedNodeLookup: root._canvasStateBridgeRef
    ? root._canvasStateBridgeRef.completed_node_lookup
    : ({})
readonly property int nodeExecutionRevision: root._canvasStateBridgeRef
    ? Number(root._canvasStateBridgeRef.node_execution_revision)
    : 0
readonly property var runningNodeTimestamps: root._canvasStateBridgeRef
    ? root._canvasStateBridgeRef.running_node_timestamps
    : ({})
```

---

## Step 6: Add Per-Node Properties in `GraphNodeHost.qml`

**File:** `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml`

### 6a. Add lookup access (after `failedNodeLookup` at line 66):

```qml
readonly property var runningNodeLookup: canvasItem ? canvasItem.runningNodeLookup : ({})
readonly property var completedNodeLookup: canvasItem ? canvasItem.completedNodeLookup : ({})
```

### 6b. Add boolean state (after `isFailedNode` at line 70):

```qml
readonly property bool isRunningNode: !!nodeData
    && Boolean(runningNodeLookup[String(nodeData.node_id || "")])
readonly property bool isCompletedNode: !!nodeData
    && Boolean(completedNodeLookup[String(nodeData.node_id || "")])
readonly property int executionPulseRevision: canvasItem
    ? Number(canvasItem.nodeExecutionRevision || 0) : 0
```

### 6c. Add theme colors (after failure colors at line 143):

```qml
readonly property color runningOutlineColor: themeState.runningOutlineColor
readonly property color runningGlowColor: themeState.runningGlowColor
readonly property color completedOutlineColor: themeState.completedOutlineColor
readonly property color completedGlowColor: themeState.completedGlowColor
```

### 6d. Update z-ordering (line 496):

Current:
```qml
z: card.isFailedNode ? 32 : (card.isSelected ? 30 : 20)
```

New:
```qml
z: card.isFailedNode ? 32 : (card.isRunningNode ? 31 : (card.isSelected ? 30 : 20))
```

### 6e. Update `_forceRenderActive` (lines 472-482 area):

Add `|| card.isRunningNode || card.isCompletedNode` to the existing condition so that
running/completed nodes are never culled from the viewport.

### 6f. Elapsed timer support (after executionPulseRevision):

```qml
readonly property var runningNodeTimestamps: canvasItem
    ? canvasItem.runningNodeTimestamps : ({})
readonly property real nodeStartTimestamp: {
    var ts = runningNodeTimestamps[String(nodeData ? nodeData.node_id || "" : "")]
    return ts !== undefined ? Number(ts) : 0.0
}
```

---

## Step 7: Add Theme Colors in `GraphNodeHostTheme.qml`

**File:** `ea_node_editor/ui_qml/components/graph/GraphNodeHostTheme.qml`

After failure colors (line 71), add:

```qml
readonly property color runningOutlineColor: "#4A9EFF"
readonly property color runningGlowColor: "#6EC6FF"
readonly property color completedOutlineColor: "#4ADE80"
readonly property color completedGlowColor: "#86EFAC"
```

Color rationale:
- Running: Blue (`#4A9EFF` / `#6EC6FF`) — universally associated with "in progress"
- Completed: Green (`#4ADE80` / `#86EFAC`) — universally associated with "success/done"
- Red (existing failure) is left untouched

---

## Step 8: Add Running/Completed Halos in `GraphNodeChromeBackground.qml`

**File:** `ea_node_editor/ui_qml/components/graph/GraphNodeChromeBackground.qml`

This is the core visual change. Add **parallel** animation structures for running and
completed states, following the exact pattern of the failure pulse.

### 8a. Add running pulse progress property (after line 8):

```qml
property real runningPulseProgress: 0.0
property real completedFlashProgress: 0.0
```

### 8b. Add running pulse animation (after `failurePulseAnimation`, around line 42):

```qml
SequentialAnimation {
    id: runningPulseAnimation
    loops: Animation.Infinite
    running: root.host ? root.host.isRunningNode : false

    NumberAnimation {
        target: root
        property: "runningPulseProgress"
        from: 0.0
        to: 1.0
        duration: 1400
        easing.type: Easing.InOutSine
    }

    NumberAnimation {
        target: root
        property: "runningPulseProgress"
        from: 1.0
        to: 0.0
        duration: 1400
        easing.type: Easing.InOutSine
    }

    onRunningChanged: {
        if (!running)
            root.runningPulseProgress = 0.0;
    }
}
```

**Design choice:** Running pulse uses a slower (1400ms x2 = 2.8s cycle), smooth sine wave
breathing effect — distinct from the sharper 920ms failure pulse. This makes it feel calm
and "working" rather than alarming.

### 8c. Add completed flash animation:

```qml
SequentialAnimation {
    id: completedFlashAnimation
    loops: 1
    running: false

    NumberAnimation {
        target: root
        property: "completedFlashProgress"
        from: 0.0
        to: 1.0
        duration: 300
        easing.type: Easing.OutCubic
    }

    PauseAnimation { duration: 600 }

    NumberAnimation {
        target: root
        property: "completedFlashProgress"
        from: 1.0
        to: 0.0
        duration: 500
        easing.type: Easing.InCubic
    }
}
```

### 8d. Trigger completed flash on state change:

```qml
Connections {
    target: root.host

    function onIsCompletedNodeChanged() {
        if (root.host && root.host.isCompletedNode) {
            root.completedFlashProgress = 0.0;
            completedFlashAnimation.restart();
        }
    }
}
```

### 8e. Add running halo (after `failurePulseHalo`, before `cardChrome`):

```qml
Rectangle {
    id: runningHalo
    objectName: "graphNodeRunningHalo"
    visible: root.host ? root.host.isRunningNode : false
    anchors.fill: parent
    anchors.margins: -6
    z: 1
    color: root.host
        ? Qt.alpha(root.host.runningGlowColor, 0.06)
        : "transparent"
    border.width: 2
    border.color: root.host
        ? Qt.alpha(root.host.runningOutlineColor,
            0.5 + (root.runningPulseProgress * 0.4))
        : "transparent"
    radius: root.host ? root.host.resolvedCornerRadius + 6 : 0
    opacity: 0.6 + (root.runningPulseProgress * 0.4)
}

Rectangle {
    id: runningPulseHalo
    objectName: "graphNodeRunningPulseHalo"
    visible: root.host ? root.host.isRunningNode : false
    anchors.fill: parent
    anchors.margins: -9
    z: 2
    color: "transparent"
    border.width: 1.5
    border.color: root.host
        ? Qt.alpha(root.host.runningGlowColor,
            Math.max(0.0, 0.5 * root.runningPulseProgress))
        : "transparent"
    radius: root.host ? root.host.resolvedCornerRadius + 9 : 0
    opacity: root.runningPulseProgress * 0.6
    scale: 1.0 + (root.runningPulseProgress * 0.06)
    transformOrigin: Item.Center
}
```

### 8f. Add completed flash halo:

```qml
Rectangle {
    id: completedFlashHalo
    objectName: "graphNodeCompletedFlashHalo"
    visible: root.completedFlashProgress > 0.01
    anchors.fill: parent
    anchors.margins: -6
    z: 1
    color: "transparent"
    border.width: 2
    border.color: root.host
        ? Qt.alpha(root.host.completedGlowColor, root.completedFlashProgress * 0.7)
        : "transparent"
    radius: root.host ? root.host.resolvedCornerRadius + 6 : 0
    opacity: root.completedFlashProgress
    scale: 1.0 + ((1.0 - root.completedFlashProgress) * 0.04)
    transformOrigin: Item.Center
}
```

### 8g. Update `cardChrome` border (modify lines 109-118):

Current:
```qml
border.width: root.host
    ? (root.host.isFailedNode ? Math.max(root.host.resolvedBorderWidth, 2.4) : root.host.resolvedBorderWidth)
    : 0
border.color: root.host
    ? (root.host.isFailedNode
        ? root.host.failureOutlineColor
        : (root.host.isSelected ? root.host.selectedOutlineColor : root.host.outlineColor))
    : "transparent"
```

New (failure takes priority, then running, then selected, then default):
```qml
border.width: root.host
    ? (root.host.isFailedNode
        ? Math.max(root.host.resolvedBorderWidth, 2.4)
        : (root.host.isRunningNode
            ? Math.max(root.host.resolvedBorderWidth, 2.0)
            : root.host.resolvedBorderWidth))
    : 0
border.color: root.host
    ? (root.host.isFailedNode
        ? root.host.failureOutlineColor
        : (root.host.isRunningNode
            ? root.host.runningOutlineColor
            : (root.host.isSelected
                ? root.host.selectedOutlineColor
                : root.host.outlineColor)))
    : "transparent"
```

---

## Step 9: Add Elapsed Timer Below Running Nodes

**File:** `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml`

Add a `Text` element anchored below the node, inside the host item (near the chrome
background instantiation at line 506-509):

```qml
Text {
    id: elapsedTimerLabel
    objectName: "graphNodeElapsedTimer"
    visible: card.isRunningNode && card.nodeStartTimestamp > 0
    anchors.top: parent.bottom
    anchors.topMargin: 4
    anchors.horizontalCenter: parent.horizontalCenter
    font.pixelSize: 10
    font.family: card.themeState ? card.themeState.fontFamily : "Segoe UI"
    color: card.runningOutlineColor
    opacity: 0.85

    property real elapsed: 0.0

    Timer {
        id: elapsedTicker
        interval: 100
        repeat: true
        running: elapsedTimerLabel.visible
        onTriggered: {
            var now = Date.now() / 1000.0;
            // nodeStartTimestamp is monotonic; we need a reference offset.
            // The bridge should supply wall-clock time or we compute delta from
            // when the Timer first started. Simplest: compute from QML side.
            parent.elapsed += 0.1;
        }
    }

    text: elapsed < 60
        ? elapsed.toFixed(1) + "s"
        : Math.floor(elapsed / 60) + "m " + (elapsed % 60).toFixed(0) + "s"

    // Reset elapsed when node changes running state
    Connections {
        target: card
        function onIsRunningNodeChanged() {
            elapsedTimerLabel.elapsed = 0.0;
        }
    }
}
```

**Alternative (simpler) approach for the timer:**
Instead of using Python monotonic timestamps across the bridge (which requires clock
synchronization), use a pure QML Timer that starts counting when `isRunningNode` becomes
true and resets when it becomes false. This avoids the timestamp bridge entirely and the
`node_execution_timestamps` field in `ShellRunState` / bridge can be omitted for the initial
implementation. Add it later if you need to show elapsed time for completed nodes too.

---

## Step 10: Update Completed Node Border (Static Green, No Animation)

Completed nodes should show a **static** green border (no pulse) until the run ends.
This is already handled by Step 8g's `border.color` chain, but we need to add the
completed state. Update the border.color chain:

```qml
border.color: root.host
    ? (root.host.isFailedNode
        ? root.host.failureOutlineColor
        : (root.host.isRunningNode
            ? root.host.runningOutlineColor
            : (root.host.isCompletedNode
                ? root.host.completedOutlineColor
                : (root.host.isSelected
                    ? root.host.selectedOutlineColor
                    : root.host.outlineColor))))
    : "transparent"
```

---

## Files Modified (Summary)

| File | Change |
|------|--------|
| `ea_node_editor/ui/shell/state.py` | Add running/completed fields to `ShellRunState` |
| `ea_node_editor/ui/shell/window.py` | Add `node_execution_state_changed` signal + 3 methods |
| `ea_node_editor/ui/shell/controllers/run_controller.py` | Dispatch `node_started`/`node_completed` to new methods; clear on run end |
| `ea_node_editor/ui_qml/graph_canvas_state_bridge.py` | Add signal + 4 pyqtProperties |
| `ea_node_editor/ui_qml/components/GraphCanvas.qml` | Thread 4 new properties from bridge |
| `ea_node_editor/ui_qml/components/graph/GraphNodeHost.qml` | Add lookups, booleans, colors, z-order, timer |
| `ea_node_editor/ui_qml/components/graph/GraphNodeHostTheme.qml` | Add 4 hardcoded color constants |
| `ea_node_editor/ui_qml/components/graph/GraphNodeChromeBackground.qml` | Add running pulse + completed flash halos + border logic |

---

## Verification

### Unit Tests

**File:** `tests/test_run_controller_unit.py`

Add tests:

1. `test_node_started_event_marks_node_running` — Verify `set_node_running()` is called
   with correct workspace_id and node_id when a `node_started` event is dispatched.

2. `test_node_completed_event_marks_node_completed` — Verify `set_node_completed()` is
   called, node moves from running to completed sets.

3. `test_run_completed_clears_execution_state` — Verify `clear_node_execution_state()` is
   called on `run_completed`.

4. `test_run_stopped_clears_execution_state` — Same for `run_stopped`.

5. `test_run_started_clears_previous_execution_state` — Verify a new run clears stale state.

The test file already uses a `_FakeHost` stub (line ~60-110) — add `set_node_running`,
`set_node_completed`, and `clear_node_execution_state` methods to it, tracking calls.

### Bridge Tests

**File:** `tests/main_window_shell/bridge_contracts.py` or new test file

1. `test_running_node_lookup_returns_correct_ids` — Set `run_state.running_node_ids` and
   verify `running_node_lookup` returns `{node_id: True}`.

2. `test_running_node_lookup_filters_by_workspace` — Verify returns `{}` when workspace
   doesn't match.

3. `test_completed_node_lookup_returns_correct_ids` — Same for completed.

4. `test_node_execution_revision_increments` — Verify revision counter.

### Manual Visual Verification

1. Open the node editor, create a simple 3-node chain (e.g., Read File -> Transform -> Write).
2. Click Run.
3. Observe: each node should flash blue while running, then settle to green border when done.
4. If a node fails, verify the red failure pulse still takes priority over blue/green.
5. Click Run again — verify all green/blue state clears before the new run starts.
6. Verify the elapsed timer counts up below the running node and disappears when done.
7. Test at different zoom levels — halos should be visible even when zoomed out.

### Run Existing Tests

```bash
pytest -n auto tests/test_run_controller_unit.py
pytest -n auto tests/main_window_shell/
```
