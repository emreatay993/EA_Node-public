import QtQuick 2.15
import QtQuick.Controls 2.15
import "../../ui_qml/components/graph" as Graph
import "../../ui_qml/components/graph/surface_controls" as SurfaceControls

// Review gallery for the COREX node restyle.
// Card chrome / grip dots are lightweight mocks driven by the REAL Python
// token values (injected as mockupPalettes); inline controls are the REAL
// surface_controls components running against a stub host, so what renders
// here is what ships. Grip fill/outline mapping mirrors GraphNodePortsLayer.
Rectangle {
    id: gallery
    color: mockupThemeFilter === "light" ? "#e9edf2" : "#16181d"

    readonly property var flowStates: [
        { state: "flowing", label: "Flowing (connected, data)" },
        { state: "default", label: "Default value used" },
        { state: "waiting", label: "Waiting for required input" },
        { state: "idle", label: "Idle output (no data)" },
        { state: "invalid", label: "Invalid data" },
        { state: "invalid_muted", label: "Invalid + wire off (reserved)" }
    ]
    readonly property var semanticStates: [
        { state: "default", label: "Default" },
        { state: "running", label: "Running" },
        { state: "warning", label: "Warning" },
        { state: "error", label: "Error" },
        { state: "disabled", label: "Disabled" }
    ]

    // Edge-centered grip, mirroring GraphNodeHost flow-state colors. Hollow
    // states use the card color as an opaque interior (no notch).
    component GripDot: Rectangle {
        id: grip
        property var pal: null
        property string flowState: "flowing"
        width: 10
        height: 10
        radius: width / 2
        border.width: 1.6
        color: {
            if (!grip.pal)
                return "transparent";
            if (grip.flowState === "flowing")
                return grip.pal.port_state.valid;
            if (grip.flowState === "invalid")
                return grip.pal.port_state.invalid_fill;
            if (grip.flowState === "invalid_muted")
                return grip.pal.port_state.invalid_muted_fill;
            return grip.pal.node.card_bg;
        }
        border.color: {
            if (!grip.pal)
                return "#67D487";
            if (grip.flowState === "waiting")
                return grip.pal.port_state.waiting_outline;
            if (grip.flowState === "idle")
                return grip.pal.port_state.idle_outline;
            if (grip.flowState === "invalid" || grip.flowState === "invalid_muted")
                return grip.pal.port_state.invalid_border;
            return grip.pal.port_state.valid;
        }
    }

    component SemanticNodeCard: Rectangle {
        id: semanticCard
        required property string themeId
        required property string stateId
        required property string stateLabel
        required property bool selected
        objectName: "semanticNodeCard_" + themeId + "_" + stateId + "_" + (selected ? "selected" : "unselected")
        readonly property string resolvedState: semanticTheme.activeSemanticState
        readonly property color resolvedStartColor: semanticTheme.bodyGradientStartColor
        readonly property color resolvedEndColor: semanticTheme.bodyGradientEndColor
        readonly property color resolvedOutlineColor: semanticTheme.outlineColor
        readonly property color resolvedTitleColor: semanticTheme.headerTextColor
        readonly property color resolvedPortColor: semanticTheme.portLabelColor
        height: 66
        radius: 7
        border.width: selected || stateId === "warning" || stateId === "error" ? 2 : 1
        border.color: semanticTheme.outlineColor
        color: semanticTheme.surfaceColor
        gradient: Gradient {
            GradientStop { position: 0.0; color: semanticTheme.bodyGradientStartColor }
            GradientStop { position: 1.0; color: semanticTheme.bodyGradientEndColor }
        }

        Item {
            id: semanticHost
            visible: false
            property var nodeData: ({"type_id": "core.logger", "visual_style": {}})
            property var nodePalette: mockupPalettes[semanticCard.themeId].node
            property var prefs: ({"activeThemeId": semanticCard.themeId === "light" ? "stitch_light" : "stitch_dark"})
            property bool isPassiveNode: false
            property bool isSelected: semanticCard.selected
            property bool isDisabledNode: semanticCard.stateId === "disabled"
            property bool isFailedNode: semanticCard.stateId === "error"
            property bool isWarningChromeNode: semanticCard.stateId === "warning"
            property bool isFlowchartSurface: false
            property bool lockedPlaceholderActive: false
            property bool usesCardinalNeutralFlowHandles: false
            property bool isCompactPillSurface: false

            function _styleString(value) { return value === undefined || value === null ? "" : String(value); }
            function _styleNumber(value, fallback) {
                var numeric = Number(value);
                return isFinite(numeric) ? numeric : Number(fallback);
            }
        }

        Graph.GraphNodeHostTheme {
            id: semanticTheme
            host: semanticHost
        }

        Text {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.margins: 7
            text: semanticCard.stateLabel
            color: semanticTheme.headerTextColor
            font.pixelSize: 10
            font.bold: true
        }

        Text {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: 7
            text: "Input"
            color: semanticTheme.portLabelColor
            font.pixelSize: 9
        }

        Text {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 7
            text: "Output"
            color: semanticTheme.portLabelColor
            font.pixelSize: 9
        }

        Rectangle {
            visible: semanticCard.stateId === "warning" || semanticCard.stateId === "error"
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 5
            width: 14
            height: 14
            radius: 7
            color: semanticCard.stateId === "error"
                ? semanticTheme.failureOutlineColor
                : semanticTheme.warningOutlineColor

            Text {
                anchors.centerIn: parent
                text: "!"
                color: "#FFFFFF"
                font.pixelSize: 9
                font.bold: true
            }
        }
    }

    Row {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 24

        Repeater {
            model: mockupThemeFilter === "both" ? ["dark", "light"] : [mockupThemeFilter]

            delegate: Rectangle {
                id: panel
                readonly property string themeId: modelData
                readonly property var pal: mockupPalettes[themeId]
                width: (gallery.width - 36 - (mockupThemeFilter === "both" ? 24 : 0))
                    / (mockupThemeFilter === "both" ? 2 : 1)
                height: gallery.height - 36
                color: themeId === "light" ? "#e9edf2" : "#16181d"
                radius: 10

                Graph.GraphSharedTypography {
                    id: panelTypography
                }

                // Stub host satisfying the surface_controls host contract.
                Item {
                    id: stubHost
                    visible: false
                    readonly property color surfaceColor: panel.pal.node.card_bg
                    readonly property color headerTextColor: panel.pal.node.header_fg
                    readonly property color outlineColor: panel.pal.node.card_border
                    readonly property color selectedOutlineColor: panel.pal.node.card_selected_border
                    readonly property color inlineRowColor: panel.pal.node.inline_row_bg
                    readonly property color inlineRowBorderColor: panel.pal.node.inline_row_border
                    readonly property color inlineLabelColor: panel.pal.node.inline_label_fg
                    readonly property color inlineInputTextColor: panel.pal.node.inline_input_fg
                    readonly property color inlineInputBackgroundColor: panel.pal.node.inline_input_bg
                    readonly property color inlineInputBorderColor: panel.pal.node.inline_input_border
                    readonly property color inlineDrivenTextColor: panel.pal.node.inline_driven_fg
                    readonly property color portLabelColor: panel.pal.node.port_label_fg
                    readonly property var graphSharedTypography: panelTypography
                    readonly property int nodeTextRenderType: Text.CurveRendering
                }

                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 14

                    Text {
                        text: panel.themeId === "light" ? "Light theme" : "Dark theme"
                        color: panel.themeId === "light" ? "#1b2733" : "#f0f4fb"
                        font.pixelSize: 13
                        font.bold: true
                    }

                    Column {
                        id: semanticMatrix
                        width: parent.width
                        spacing: 5

                        Text {
                            text: "Fixed active-node semantic colors"
                            color: panel.themeId === "light" ? "#1b2733" : "#f0f4fb"
                            font.pixelSize: 11
                            font.bold: true
                        }

                        Repeater {
                            model: [false, true]

                            delegate: Column {
                                id: semanticStateRow
                                readonly property bool selectedRow: Boolean(modelData)
                                width: semanticMatrix.width
                                spacing: 3

                                Text {
                                    text: semanticStateRow.selectedRow ? "Selected" : "Unselected"
                                    color: panel.themeId === "light" ? "#43515d" : "#c7ced8"
                                    font.pixelSize: 9
                                }

                                Row {
                                    width: parent.width
                                    spacing: 6

                                    Repeater {
                                        model: gallery.semanticStates.length

                                        SemanticNodeCard {
                                            required property int index
                                            width: (semanticMatrix.width - 24) / 5
                                            themeId: panel.themeId
                                            stateId: gallery.semanticStates[index].state
                                            stateLabel: gallery.semanticStates[index].label
                                            selected: semanticStateRow.selectedRow
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ---- Node card mock (chrome tokens + real controls) ----
                    Rectangle {
                        id: card
                        width: Math.min(320, parent.width)
                        height: cardColumn.implicitHeight + 14
                        radius: 9
                        color: panel.pal.node.card_bg
                        border.width: 1
                        border.color: panel.pal.node.card_border

                        Column {
                            id: cardColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            spacing: 6

                            Item {
                                width: parent.width
                                height: 32

                                Row {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 12
                                    spacing: 6

                                    Rectangle {
                                        width: 14
                                        height: 14
                                        radius: 4
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: panel.pal.node.header_fg
                                        Text {
                                            anchors.centerIn: parent
                                            text: "◆"
                                            color: panel.pal.node.card_bg
                                            font.pixelSize: 8
                                        }
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Convert to Quad Mesh"
                                        color: panel.pal.node.header_fg
                                        font.pixelSize: panelTypography.nodeTitlePixelSize
                                        font.weight: panelTypography.nodeTitleFontWeight
                                    }
                                }
                            }

                            // Port rows demoing every grip flow state.
                            Repeater {
                                model: gallery.flowStates

                                delegate: Item {
                                    width: cardColumn.width
                                    height: 18

                                    GripDot {
                                        id: rowGrip
                                        pal: panel.pal
                                        flowState: modelData.state
                                        anchors.verticalCenter: parent.verticalCenter
                                        x: -width / 2
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        x: rowGrip.x + rowGrip.width + 6
                                        text: modelData.label
                                        color: panel.pal.node.port_label_fg
                                        font.pixelSize: panelTypography.portLabelPixelSize
                                        font.weight: panelTypography.portLabelFontWeight
                                    }
                                }
                            }

                            // Output row (right edge grip).
                            Item {
                                width: cardColumn.width
                                height: 18

                                GripDot {
                                    id: outputGrip
                                    pal: panel.pal
                                    flowState: "flowing"
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: parent.width - width / 2
                                }

                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: outputGrip.x - width - 6
                                    text: "Mesh"
                                    color: panel.pal.node.port_label_fg
                                    font.pixelSize: panelTypography.portLabelPixelSize
                                    font.weight: panelTypography.portLabelFontWeight
                                }
                            }

                            // Inline rows hosting the REAL surface controls.
                            Column {
                                width: parent.width - 24
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 6

                                Row {
                                    spacing: 8
                                    Text {
                                        width: 92
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Merge faces"
                                        color: panel.pal.node.inline_label_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                    SurfaceControls.GraphSurfaceCheckBox {
                                        host: stubHost
                                        checked: false
                                    }
                                    SurfaceControls.GraphSurfaceCheckBox {
                                        host: stubHost
                                        checked: true
                                    }
                                }

                                Row {
                                    spacing: 8
                                    Text {
                                        width: 92
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Symmetry axis"
                                        color: panel.pal.node.inline_label_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                    SurfaceControls.GraphSurfaceComboBox {
                                        width: 120
                                        host: stubHost
                                        model: ["Off", "X axis", "Y axis", "Z axis"]
                                    }
                                }

                                Row {
                                    spacing: 8
                                    Text {
                                        width: 92
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Edge length"
                                        color: panel.pal.node.inline_label_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                    SurfaceControls.GraphSurfaceTextField {
                                        width: 120
                                        host: stubHost
                                        text: "2.5"
                                    }
                                }

                                Row {
                                    spacing: 8
                                    Text {
                                        width: 92
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Adaptative size"
                                        color: panel.pal.node.inline_label_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                    SurfaceControls.GraphSurfaceSlider {
                                        width: 100
                                        anchors.verticalCenter: parent.verticalCenter
                                        host: stubHost
                                        from: 0
                                        to: 100
                                        value: 35
                                    }
                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "35"
                                        color: panel.pal.node.inline_input_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                }
                            }

                            // Settings expander row preview (restyled in Phase C).
                            Item {
                                width: parent.width - 24
                                anchors.horizontalCenter: parent.horizontalCenter
                                height: 22

                                Text {
                                    id: settingsLabel
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Settings"
                                    color: panel.pal.node.port_label_fg
                                    font.pixelSize: panelTypography.portLabelPixelSize
                                }

                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: settingsLabel.right
                                    anchors.leftMargin: 8
                                    anchors.right: settingsChevron.left
                                    anchors.rightMargin: 8
                                    height: 1
                                    color: Qt.alpha(panel.pal.node.port_label_fg, 0.25)
                                }

                                Rectangle {
                                    id: settingsChevron
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.right: parent.right
                                    width: 16
                                    height: 16
                                    radius: width / 2
                                    color: "transparent"
                                    border.width: 1
                                    border.color: Qt.alpha(panel.pal.node.port_label_fg, 0.4)

                                    Text {
                                        anchors.centerIn: parent
                                        text: "⌄"
                                        color: panel.pal.node.port_label_fg
                                        font.pixelSize: 10
                                        anchors.verticalCenterOffset: -2
                                    }
                                }
                            }
                        }
                    }

                    // ---- Grip state legend ----
                    Rectangle {
                        width: Math.min(320, parent.width)
                        height: legendColumn.implicitHeight + 20
                        radius: 9
                        color: panel.pal.node.card_bg
                        border.width: 1
                        border.color: panel.pal.node.card_border

                        Column {
                            id: legendColumn
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 6

                            Text {
                                text: "Grip states"
                                color: panel.pal.node.header_fg
                                font.pixelSize: panelTypography.inlinePropertyPixelSize
                                font.bold: true
                            }

                            Repeater {
                                model: gallery.flowStates

                                delegate: Row {
                                    spacing: 8

                                    GripDot {
                                        pal: panel.pal
                                        flowState: modelData.state
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.label
                                        color: panel.pal.node.inline_label_fg
                                        font.pixelSize: panelTypography.inlinePropertyPixelSize
                                    }
                                }
                            }
                        }
                    }

                }
            }
        }
    }
}
