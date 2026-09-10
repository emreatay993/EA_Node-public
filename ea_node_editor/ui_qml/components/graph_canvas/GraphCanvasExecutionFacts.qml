import QtQml 2.15

// Shared-by-reference execution facts for the graph canvas.
//
// Pass this object by reference (canvas -> host -> layers/overlays) instead of
// re-drilling each lookup through per-item properties. New execution-state
// facts are added HERE (paired with the @pyqtProperty in
// graph_canvas_state/execution_state_props.py); consumers read
// executionFacts.<fact> directly.
QtObject {
    id: facts
    property var stateBridge: null

    readonly property var failedNodeLookup: facts.stateBridge
        ? facts.stateBridge.failed_node_lookup
        : ({})
    readonly property string failedNodeTitle: facts.stateBridge
        ? String(facts.stateBridge.failed_node_title || "")
        : ""
    readonly property var runningNodeLookup: facts.stateBridge
        ? facts.stateBridge.running_node_lookup
        : ({})
    readonly property var completedNodeLookup: facts.stateBridge
        ? facts.stateBridge.completed_node_lookup
        : ({})
    readonly property var warningNodeLookup: facts.stateBridge
        && typeof facts.stateBridge.warning_node_lookup !== "undefined"
        ? facts.stateBridge.warning_node_lookup
        : ({})
    readonly property var runningNodeStartedAtMsLookup: facts.stateBridge
        ? facts.stateBridge.running_node_started_at_ms_lookup
        : ({})
    readonly property var nodeElapsedMsLookup: facts.stateBridge
        ? facts.stateBridge.node_elapsed_ms_lookup
        : ({})
    readonly property var nodeRunCountLookup: facts.stateBridge
        && typeof facts.stateBridge.node_run_count_lookup !== "undefined"
        ? facts.stateBridge.node_run_count_lookup
        : ({})
    // The single normalization point for the elapsed-time unit preference.
    readonly property string nodeElapsedTimeUnit: facts.stateBridge
        && facts.stateBridge.graphics_node_elapsed_time_unit !== undefined
        ? (String(facts.stateBridge.graphics_node_elapsed_time_unit || "seconds").toLowerCase().trim() || "seconds")
        : "seconds"
    readonly property var freshRunNodeLookup: facts.stateBridge
        && typeof facts.stateBridge.fresh_run_node_lookup !== "undefined"
        ? facts.stateBridge.fresh_run_node_lookup
        : ({})
    readonly property var nodeSolutionFreshnessLookup: facts.stateBridge
        && typeof facts.stateBridge.node_solution_freshness_lookup !== "undefined"
        ? facts.stateBridge.node_solution_freshness_lookup
        : ({})
    readonly property var propertyPresentationLookup: facts.stateBridge
        && typeof facts.stateBridge.property_presentation_lookup !== "undefined"
        ? facts.stateBridge.property_presentation_lookup
        : ({})
    readonly property var portFlowStateLookup: facts.stateBridge
        && typeof facts.stateBridge.port_flow_state_lookup !== "undefined"
        ? facts.stateBridge.port_flow_state_lookup
        : ({})
    readonly property var portValuePreviewLookup: facts.stateBridge
        && typeof facts.stateBridge.port_value_preview_lookup !== "undefined"
        ? facts.stateBridge.port_value_preview_lookup
        : ({})
    readonly property var nodeDiagnosticLookup: facts.stateBridge
        && typeof facts.stateBridge.node_diagnostic_lookup !== "undefined"
        ? facts.stateBridge.node_diagnostic_lookup
        : ({})
    readonly property var mediaPanelSourceLookup: facts.stateBridge
        && typeof facts.stateBridge.media_panel_source_lookup !== "undefined"
        ? facts.stateBridge.media_panel_source_lookup
        : ({})
    readonly property int nodeExecutionRevision: facts.stateBridge
        ? Number(facts.stateBridge.node_execution_revision)
        : 0
    readonly property bool selectedRunPreviewBeforeRun: facts.stateBridge
        && facts.stateBridge.selected_run_preview_before_run !== undefined
        ? Boolean(facts.stateBridge.selected_run_preview_before_run)
        : true
    readonly property var selectedRunPreviewRows: facts.stateBridge
        && facts.stateBridge.selected_run_preview_rows !== undefined
        ? facts.stateBridge.selected_run_preview_rows
        : []
    readonly property var selectedRunPreviewNodeLookup: facts.stateBridge
        && facts.stateBridge.selected_run_preview_node_lookup !== undefined
        ? facts.stateBridge.selected_run_preview_node_lookup
        : ({})
    readonly property bool selectedRunPreviewVisible: facts.stateBridge
        && facts.stateBridge.selected_run_preview_visible !== undefined
        ? Boolean(facts.stateBridge.selected_run_preview_visible)
        : false
    readonly property int selectedRunPreviewRevision: facts.stateBridge
        && facts.stateBridge.selected_run_preview_revision !== undefined
        ? Number(facts.stateBridge.selected_run_preview_revision)
        : 0
}
