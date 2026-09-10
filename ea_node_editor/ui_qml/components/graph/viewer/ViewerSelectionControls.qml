import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../shell"
import "../../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: selectionControls

    objectName: "viewerSelectionControls"
    property var themePalette: typeof themeBridge !== "undefined" ? themeBridge.palette : ({})
    property string nodeId: ""
    property var fullscreenBridgeRef: null
    property var sessionBridgeRef: typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge : null
    property var controlBridgeRef: typeof viewerControlBridge !== "undefined" ? viewerControlBridge : null
    property var hostServiceRef: typeof viewerHostService !== "undefined" ? viewerHostService : null
    property bool detachedPresentation: false
    property bool presentationVisible: true
    property var sessionState: {
        var revision = sessionBridgeRef ? sessionBridgeRef.sessions_model : [];
        void(revision);
        return sessionBridgeRef && sessionBridgeRef.session_state && nodeId.length
            ? sessionBridgeRef.session_state(nodeId) : ({});
    }

    readonly property var sessionSummary: sessionState.summary || ({})
    readonly property var capabilities: sessionSummary.capabilities || ({})
    readonly property bool engineeringViewer: String(sessionSummary.viewer_kind || "") === "engineering_scene"
    readonly property var supportedFilters: capabilities.supported_selection_filters
        || sessionSummary.supported_selection_filters
        || []
    readonly property var selectionSnapshot: {
        var revision = hostServiceRef ? hostServiceRef.viewer_overlay_revision : 0;
        void(revision);
        if (!hostServiceRef || !hostServiceRef.viewer_selection_snapshot || !nodeId.length)
            return ({});
        return hostServiceRef.viewer_selection_snapshot(nodeId) || ({});
    }
    property real tangentAngleDegrees: 5
    readonly property string activeFilter: {
        var value = String(selectionSnapshot.selection_filter || "");
        if (value.length > 0)
            return value;
        value = String(sessionSummary.default_selection_filter || "");
        if (filterSupported(value))
            return value;
        return filterSupported("cad_body") ? "cad_body" : "fe_element";
    }
    readonly property bool tangentFilterActive: activeFilter === "cad_edge" || activeFilter === "cad_face"

    implicitHeight: presentationVisible && engineeringViewer ? 42 : 0
    visible: presentationVisible && engineeringViewer
    color: themePalette.panel_bg || "#20242b"
    border.color: themePalette.input_border || "#3d4652"
    border.width: 1
    clip: true

    function filterEntry(value) {
        for (var index = 0; index < supportedFilters.length; ++index) {
            var entry = supportedFilters[index];
            if (entry && String(entry.id || "") === String(value || ""))
                return entry;
        }
        return null;
    }

    function filterSupported(value) {
        var entry = filterEntry(value);
        return Boolean(entry && entry.available);
    }

    function filterReason(value) {
        var entry = filterEntry(value);
        return String(entry && entry.unsupported_reason
            ? entry.unsupported_reason
            : TooltipCopy.text(tooltipCopyBridge, "viewer.selection.unsupported"));
    }

    function setSelectionFilter(value) {
        if (!filterSupported(value) || !hostServiceRef || !hostServiceRef.set_viewer_selection_filter)
            return false;
        return Boolean(hostServiceRef.set_viewer_selection_filter(nodeId, value));
    }

    function normalizedTangentAngle(value) {
        var number = Number(value);
        return isFinite(number) ? Math.max(0, Math.min(90, number)) : 5;
    }

    function refreshTangentAngle() {
        tangentAngleDegrees = controlBridgeRef && controlBridgeRef.viewer_tangent_selection_angle_degrees
            ? normalizedTangentAngle(controlBridgeRef.viewer_tangent_selection_angle_degrees()) : 5;
    }

    function setTangentAngle(value) {
        return controlBridgeRef && controlBridgeRef.set_viewer_tangent_selection_angle_degrees
            ? Boolean(controlBridgeRef.set_viewer_tangent_selection_angle_degrees(normalizedTangentAngle(value)))
            : false;
    }

    function scrollBy(amount) {
        selectionFlick.contentX = Math.max(
            0,
            Math.min(selectionFlick.contentWidth - selectionFlick.width, selectionFlick.contentX + amount)
        );
    }

    Component.onCompleted: refreshTangentAngle()
    onControlBridgeRefChanged: refreshTangentAngle()

    Connections {
        target: selectionControls.controlBridgeRef
        ignoreUnknownSignals: true
        function onViewerTangentSelectionAngleChanged(value) {
            selectionControls.tangentAngleDegrees = selectionControls.normalizedTangentAngle(value);
        }
    }

    component FilterButton: ViewerToolButton {
        required property string filterValue
        required property string labelText
        required property string filterIcon
        actionEnabled: selectionControls.filterSupported(filterValue)
        selectedStyle: selectionControls.activeFilter === filterValue
        checkable: true
        iconName: filterIcon
        accessibleName: labelText + " selection filter"
        tooltipText: actionEnabled
            ? TooltipCopy.text(tooltipCopyBridge, "viewer.selection." + filterValue)
            : selectionControls.filterReason(filterValue)
        tooltipCategory: "general"
        onClicked: selectionControls.setSelectionFilter(filterValue)
    }

    ViewerToolButton {
        id: leftChevron
        objectName: "viewerSelectionControlsLeftChevron"
        anchors.left: parent.left
        anchors.leftMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        buttonWidth: 28
        iconSize: 16
        iconName: "navigate-previous"
        accessibleName: "Scroll selection filters left"
        tooltipText: accessibleName
        visible: selectionFlick.contentX > 1
        z: 3
        onClicked: selectionControls.scrollBy(-180)
    }

    Flickable {
        id: selectionFlick
        objectName: "viewerSelectionControlsFlickable"
        anchors.fill: parent
        anchors.leftMargin: leftChevron.visible ? 36 : 10
        anchors.rightMargin: rightChevron.visible ? 36 : 10
        contentWidth: selectionRow.implicitWidth
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        RowLayout {
            id: selectionRow
            height: selectionFlick.height
            spacing: 5

            Text {
                text: "Selection"
                color: selectionControls.themePalette.muted_fg || "#aeb7c2"
                font.pixelSize: 11
                font.bold: true
                Layout.leftMargin: 2
                Layout.rightMargin: 3
            }

            Text {
                text: "CAD"
                color: selectionControls.themePalette.muted_fg || "#aeb7c2"
                font.pixelSize: 10
            }
            FilterButton {
                objectName: "viewerSelectCadVertexButton"
                filterValue: "cad_vertex"
                labelText: "Vertex"
                filterIcon: "viewer-select-vertex"
            }
            FilterButton {
                objectName: "viewerSelectCadEdgeButton"
                filterValue: "cad_edge"
                labelText: "Edge"
                filterIcon: "viewer-select-edge"
            }
            FilterButton {
                objectName: "viewerSelectCadFaceButton"
                filterValue: "cad_face"
                labelText: "Face"
                filterIcon: "viewer-select-face"
            }
            FilterButton {
                objectName: "viewerSelectCadBodyButton"
                filterValue: "cad_body"
                labelText: "Body"
                filterIcon: "viewer-select-body"
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 24
                color: selectionControls.themePalette.input_border || "#3d4652"
            }

            Text {
                text: "FE"
                color: selectionControls.themePalette.muted_fg || "#aeb7c2"
                font.pixelSize: 10
            }
            FilterButton {
                objectName: "viewerSelectFeNodeButton"
                filterValue: "fe_node"
                labelText: "Node"
                filterIcon: "viewer-select-node"
            }
            FilterButton {
                objectName: "viewerSelectFeElementFaceButton"
                filterValue: "fe_element_face"
                labelText: "Element face"
                filterIcon: "viewer-select-element-face"
            }
            FilterButton {
                objectName: "viewerSelectFeElementButton"
                filterValue: "fe_element"
                labelText: "Element"
                filterIcon: "viewer-select-element"
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 24
                color: selectionControls.themePalette.input_border || "#3d4652"
            }

            ViewerToolButton {
                objectName: "viewerSelectTangentButton"
                iconName: "viewer-select-tangent"
                actionEnabled: selectionControls.tangentFilterActive
                selectedStyle: selectionControls.tangentFilterActive
                accessibleName: "Tangent selection angle"
                tooltipText: actionEnabled
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.selection.tangent")
                    : TooltipCopy.text(tooltipCopyBridge, "viewer.selection.tangent_unavailable")
                tooltipCategory: "general"
                onClicked: tangentAngleSpin.forceActiveFocus()
            }
            Text {
                text: "Tangent"
                color: selectionControls.tangentFilterActive
                    ? (selectionControls.themePalette.tab_fg || "#f3f5f7")
                    : Qt.alpha(selectionControls.themePalette.muted_fg || "#aeb7c2", 0.55)
                font.pixelSize: 10
            }
            SpinBox {
                id: tangentAngleSpin
                objectName: "viewerSelectionTangentAngleSpinBox"
                Layout.preferredWidth: 76
                Layout.preferredHeight: 30
                from: 0
                to: 90
                stepSize: 1
                editable: true
                enabled: selectionControls.tangentFilterActive
                value: Math.round(selectionControls.tangentAngleDegrees)
                textFromValue: function(number, locale) { return Number(number).toLocaleString(locale, "f", 0) + "\u00B0"; }
                valueFromText: function(text, locale) {
                    var parsed = Number(String(text).replace("\u00B0", "").replace(",", "."));
                    return isFinite(parsed) ? Math.max(0, Math.min(90, parsed)) : 5;
                }
                Accessible.name: "Tangent selection angle in degrees"
                onValueModified: selectionControls.setTangentAngle(value)
            }
        }
    }

    ViewerToolButton {
        id: rightChevron
        objectName: "viewerSelectionControlsRightChevron"
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        buttonWidth: 28
        iconSize: 16
        iconName: "navigate-next"
        accessibleName: "Scroll selection filters right"
        tooltipText: accessibleName
        visible: selectionFlick.contentWidth > selectionFlick.width
            && selectionFlick.contentX < selectionFlick.contentWidth - selectionFlick.width - 1
        z: 3
        onClicked: selectionControls.scrollBy(180)
    }
}
