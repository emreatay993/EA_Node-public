import QtQuick 2.15
import QtQuick.Controls 2.15
import ".." as GraphShared
import "../../common" as Common
import "../surface_controls" as SurfaceControls

// Compact Select source: [name][dropdown][settings] with one centered output.
GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphSelectSurface"

    readonly property string nodeId: host && host.nodeData ? String(host.nodeData.node_id || "") : ""
    readonly property string nodeTitle: host && host.nodeData ? String(host.nodeData.title || "") : ""
    readonly property var options: propRaw("options", [])
    readonly property var optionNames: _optionNames()
    readonly property int selectedIndex: _clampedIndex(propNumber("selected_index", 0))
    readonly property real pillRadius: height * 0.5
    readonly property real portGutterReserve: host
        ? Math.max(10.0, Number(host.surfaceMetrics.body_right_margin || 0.0))
        : 10.0
    readonly property color pillBorderColor: host ? host.outlineColor : "#4a4f5a"
    readonly property color nameSectionColor: Qt.alpha(pillBorderColor, 0.12)
    readonly property color dividerColor: Qt.alpha(pillBorderColor, 0.55)
    readonly property color nameTextColor: host ? host.headerTextColor : "#f0f2f5"

    property bool selectSettingsEditorOpen: false
    readonly property var selectSettingsPayload: ({
        "options": surface.options,
        "selected_index": surface.selectedIndex
    })
    readonly property var embeddedInteractiveRects: []
        .concat(optionCombo.embeddedInteractiveRects || [])
        .concat(settingsButton.embeddedInteractiveRects || [])
    readonly property var surfaceActions: []
    implicitHeight: host ? Number(host.surfaceMetrics.default_height || 0) : 0

    function _clampedIndex(index) {
        var count = surface.optionNames.length;
        return count > 0 ? Math.max(0, Math.min(count - 1, Math.round(Number(index) || 0))) : -1;
    }

    function _optionNames() {
        var names = [];
        var rows = surface.options;
        if (!rows || rows.length === undefined)
            return names;
        for (var index = 0; index < rows.length; ++index) {
            var row = rows[index] || ({});
            names.push(String(row.name === undefined || row.name === null ? "" : row.name));
        }
        return names;
    }

    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
    }

    function dispatchSurfaceAction(actionId) {
        if (String(actionId || "") === "select_edit_settings") {
            surface.selectSettingsEditorOpen = true;
            return true;
        }
        return false;
    }

    function acceptSelectSettings(payload) {
        surface.selectSettingsEditorOpen = false;
        if (!surface.host || !surface.host.canvasItem || !surface.nodeId.length)
            return false;
        var canvasItem = surface.host.canvasItem;
        if (!canvasItem.commitNodeSurfaceProperties)
            return false;
        return Boolean(canvasItem.commitNodeSurfaceProperties(surface.nodeId, payload || ({})));
    }

    function cancelSelectSettings() {
        surface.selectSettingsEditorOpen = false;
    }

    Item {
        id: nameSection
        objectName: "graphSelectNameSection"
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.topMargin: 1
        anchors.bottomMargin: 1
        anchors.leftMargin: 1
        width: Math.max(nameLabel.implicitWidth + 26.0, 82.0)

        Item {
            id: nameSectionFillClip
            objectName: "graphSelectNameSectionFillClip"
            anchors.fill: parent
            clip: true

            Rectangle {
                id: nameSectionFill
                objectName: "graphSelectNameSectionFill"
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                width: parent.width + Math.max(0.0, surface.pillRadius - 1.0)
                radius: Math.max(0.0, surface.pillRadius - 1.0)
                color: surface.nameSectionColor
                antialiasing: true
            }
        }

        Text {
            id: nameLabel
            objectName: "graphSelectNameLabel"
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 16.0
            anchors.rightMargin: 8.0
            text: surface.nodeTitle
            elide: Text.ElideNone
            color: surface.nameTextColor
            font.pixelSize: host && host.graphSharedTypography
                ? host.graphSharedTypography.nodeTitlePixelSize
                : 12
            font.weight: host && host.graphSharedTypography
                ? host.graphSharedTypography.nodeTitleFontWeight
                : Font.Bold
            renderType: host ? host.nodeTextRenderType : Text.CurveRendering

            HoverHandler {
                id: nameHelpHover
                enabled: !!surface.host && surface.host.nodeHelpTooltipText.length > 0
            }

            Common.ManagedToolTip {
                objectName: "graphSelectHelpToolTip"
                policyBridge: surface.host ? surface.host.nodeHelpTooltipPolicyBridge : null
                category: "general"
                active: nameHelpHover.hovered
                text: surface.host ? surface.host.nodeHelpTooltipText : ""
                textFormat: Text.RichText
                delay: 400
                screenStablePositioning: true
                screenStablePlacement: surface.host ? surface.host.nodeHelpTooltipPlacement : "below"
                anchorScale: surface.host ? surface.host.nodeHelpTooltipAnchorScale : 1.0
                screenGap: 8
            }
        }
    }

    Rectangle {
        id: nameDivider
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: nameSection.right
        width: 1
        color: surface.dividerColor
    }

    SurfaceControls.GraphSurfaceButton {
        id: settingsButton
        objectName: "graphSelectSettingsButton"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: surface.portGutterReserve + 4.0
        width: 28
        height: 28
        host: surface.host
        enabled: !!surface.host && !surface.host.graphReadOnly
        iconOnly: true
        iconName: "settings"
        iconSize: 18
        iconSourceResolver: surface._iconSource
        tooltipText: "Select settings"
        baseFillColor: "transparent"
        baseBorderColor: "transparent"
        idleBorderWidth: 0
        onClicked: {
            if (surface.host)
                surface.host.dispatchSurfaceAction("select_edit_settings");
        }
    }

    SurfaceControls.GraphSurfaceComboBox {
        id: optionCombo
        objectName: "graphSelectComboBox"
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: nameDivider.right
        anchors.right: settingsButton.left
        anchors.leftMargin: 10.0
        anchors.rightMargin: 6.0
        height: 28
        host: surface.host
        enabled: !!surface.host && !surface.host.graphReadOnly && surface.optionNames.length > 0
        model: surface.optionNames
        currentIndex: surface.selectedIndex
        Accessible.name: "Selected value"
        onControlStarted: {
            if (surface.host && surface.nodeId.length)
                surface.host.surfaceControlInteractionStarted(surface.nodeId);
        }
        onActivated: function(index) {
            if (surface.host && surface.nodeId.length)
                surface.host.inlinePropertyCommitted(surface.nodeId, "selected_index", index);
        }
    }
}
