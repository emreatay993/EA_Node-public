import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import EA.NodeEditor 1.0

Rectangle {
    id: root
    objectName: "addonManagerPane"
    property var requestBridge: typeof addonManagerBridge !== "undefined" ? addonManagerBridge : null
    property var workspaceBridge: typeof shellWorkspaceBridge !== "undefined" ? shellWorkspaceBridge : null
    property var viewerHostServiceRef: typeof viewerHostService !== "undefined" ? viewerHostService : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphThemeBridgeRef: typeof graphThemeBridge !== "undefined" ? graphThemeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property var graphNodePalette: root.graphThemeBridgeRef
        ? root.graphThemeBridgeRef.node_palette
        : ({})
    readonly property var graphEdgePalette: root.graphThemeBridgeRef
        ? root.graphThemeBridgeRef.edge_palette
        : ({})
    readonly property var graphPortKindPalette: root.graphThemeBridgeRef
        ? root.graphThemeBridgeRef.port_kind_palette
        : ({})
    readonly property var graphPortStatePalette: root.graphThemeBridgeRef
        ? root.graphThemeBridgeRef.port_state_palette
        : ({})
    readonly property color nodeCardBg: graphNodePalette.card_bg || themePalette.panel_bg
    readonly property color nodeHeaderFg: graphNodePalette.header_fg || themePalette.panel_title_fg
    readonly property color nodeCardBorder: graphNodePalette.card_border || themePalette.border
    readonly property color warningColor: graphEdgePalette.warning_stroke || "#E8A838"
    readonly property color completedColor: graphPortStatePalette.valid || "#67D487"
    readonly property var selectedAddon: controller.selectedAddon
    color: themePalette.app_bg
    border.color: themePalette.border
    border.width: 1
    radius: 6
    clip: true
    focus: visible

    Keys.onEscapePressed: controller.requestClose()

    function rowAccent(row) {
        if (!row)
            return themePalette.border
        if (row.pendingRestart)
            return warningColor
        return themePalette.accent
    }

    function statusText(row) {
        if (!row)
            return ""
        if (row.pendingRestart)
            return "Pending restart"
        if (row.unavailable)
            return "Unavailable"
        return row.enabled ? "Enabled" : "Disabled"
    }

    function badgeFill(tone) {
        if (tone === "warn")
            return Qt.alpha(warningColor, 0.14)
        if (tone === "core")
            return Qt.alpha(themePalette.accent, 0.14)
        return Qt.alpha(completedColor, 0.14)
    }

    function badgeBorder(tone) {
        if (tone === "warn")
            return Qt.alpha(warningColor, 0.38)
        if (tone === "core")
            return Qt.alpha(themePalette.accent, 0.38)
        return Qt.alpha(completedColor, 0.38)
    }

    function badgeForeground(tone) {
        if (tone === "warn")
            return warningColor
        if (tone === "core")
            return themePalette.accent
        return completedColor
    }

    ShellAddOnManagerBridge {
        id: controller
        objectName: "shellAddOnManagerBridge"
        requestBridge: root.requestBridge
        workspaceBridge: root.workspaceBridge
        viewerHostServiceRef: root.viewerHostServiceRef
    }

    Rectangle {
        id: managerToolbar
        objectName: "addonManagerToolbar"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 54
        color: themePalette.toolbar_bg
        border.color: themePalette.border

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 14
                Layout.preferredHeight: 14
                radius: 3
                color: themePalette.accent
            }

            Text {
                id: toolbarTitle
                objectName: "addonManagerTitle"
                text: "Manage Add-Ons"
                color: themePalette.panel_title_fg
                font.pixelSize: 13
                font.bold: true
            }

            Text {
                objectName: "addonManagerSummary"
                text: controller.summaryText
                color: themePalette.muted_fg
                font.pixelSize: 11
                font.family: "Consolas"
            }

            Rectangle {
                id: pendingBadge
                objectName: "addonManagerPendingBadge"
                visible: controller.pendingRestartCount > 0
                Layout.preferredHeight: 22
                Layout.preferredWidth: pendingBadgeLabel.implicitWidth + 16
                radius: 11
                color: Qt.alpha(warningColor, 0.16)
                border.color: Qt.alpha(warningColor, 0.55)

                Text {
                    id: pendingBadgeLabel
                    anchors.centerIn: parent
                    text: controller.pendingRestartCount + " pending restart"
                    color: warningColor
                    font.pixelSize: 10
                    font.bold: true
                }
            }

            Item {
                Layout.fillWidth: true
            }

            ShellButton {
                objectName: "addonManagerCheckUpdatesButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                text: "Check for updates"
                enabled: false
            }

            ShellButton {
                objectName: "addonManagerInstallFromFileButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                text: "Install from File..."
                enabled: false
            }

        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: managerToolbar.bottom
        anchors.bottom: parent.bottom
        color: themePalette.app_bg

        RowLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
                id: listPane
                Layout.preferredWidth: 340
                Layout.fillHeight: true
                color: themePalette.panel_bg
                border.color: themePalette.border

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        color: themePalette.panel_bg
                        border.color: themePalette.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            anchors.topMargin: 6
                            anchors.bottomMargin: 6
                            spacing: 4

                            Repeater {
                                model: [
                                    { "id": "all", "label": "All" },
                                    { "id": "enabled", "label": "Enabled" },
                                    { "id": "disabled", "label": "Disabled" }
                                ]

                                delegate: Rectangle {
                                    objectName: "addonManagerFilter" + modelData.label + "Button"
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    radius: 3
                                    readonly property bool isActive: controller.statusFilter === modelData.id
                                    color: themePalette.panel_alt_bg
                                    border.color: isActive ? themePalette.accent : themePalette.border
                                    border.width: 1

                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.label
                                        color: parent.isActive ? themePalette.accent : themePalette.app_fg
                                        font.pixelSize: 11
                                        font.bold: parent.isActive
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: controller.setStatusFilter(modelData.id)
                                    }
                                }
                            }
                        }
                    }

                    ScrollView {
                        id: listScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: listScroll.availableWidth
                            spacing: 0

                            Rectangle {
                                objectName: "addonManagerEmptyListState"
                                visible: controller.rowCount === 0
                                width: parent.width
                                height: 120
                                color: "transparent"

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 6

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "No add-ons registered"
                                        color: themePalette.panel_title_fg
                                        font.pixelSize: 12
                                        font.bold: true
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "This build has not published any add-on contracts yet."
                                        color: themePalette.muted_fg
                                        font.pixelSize: 11
                                    }
                                }
                            }

                            Repeater {
                                model: controller.filteredRows

                                delegate: Rectangle {
                                    id: rowCard
                                    objectName: "addonManagerRow"
                                    width: parent.width
                                    height: 52
                                    color: modelData.selected
                                        ? themePalette.inspector_selected_bg
                                        : "transparent"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        width: 3
                                        color: modelData.selected
                                            ? themePalette.accent
                                            : "transparent"
                                    }

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        height: 1
                                        color: themePalette.border
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: controller.selectAddon(String(modelData.addonId || ""))
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 10
                                        anchors.topMargin: 8
                                        anchors.bottomMargin: 8
                                        spacing: 8

                                        Rectangle {
                                            Layout.preferredWidth: 22
                                            Layout.preferredHeight: 22
                                            radius: 3
                                            color: nodeCardBg

                                            Rectangle {
                                                anchors.left: parent.left
                                                anchors.top: parent.top
                                                anchors.bottom: parent.bottom
                                                width: 3
                                                color: root.rowAccent(modelData)
                                            }

                                            Text {
                                                anchors.centerIn: parent
                                                text: String(modelData.iconGlyph || "A")
                                                color: nodeHeaderFg
                                                font.pixelSize: 11
                                                font.bold: true
                                            }
                                        }

                                        Column {
                                            Layout.fillWidth: true
                                            spacing: 1

                                            Text {
                                                objectName: "addonManagerRowTitle"
                                                width: parent.width
                                                text: String(modelData.displayName || "")
                                                color: themePalette.panel_title_fg
                                                font.pixelSize: 12
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }

                                            Row {
                                                spacing: 6

                                                Text {
                                                    text: String(modelData.categoryLabel || "")
                                                        + (String(modelData.version || "").length > 0
                                                            ? " \u00B7 v" + String(modelData.version || "")
                                                            : "")
                                                    color: themePalette.muted_fg
                                                    font.pixelSize: 10
                                                    font.family: "Consolas"
                                                }

                                                Text {
                                                    text: "\u00B7"
                                                    color: themePalette.muted_fg
                                                    font.pixelSize: 10
                                                }

                                                Text {
                                                    text: modelData.supportsHotApply ? "HOT" : "RESTART"
                                                    color: modelData.supportsHotApply
                                                        ? completedColor
                                                        : warningColor
                                                    font.pixelSize: 9
                                                    font.bold: true
                                                    font.letterSpacing: 0.4
                                                }
                                            }
                                        }

                                        Rectangle {
                                            Layout.preferredWidth: 7
                                            Layout.preferredHeight: 7
                                            radius: 3.5
                                            color: modelData.pendingRestart
                                                ? warningColor
                                                : (modelData.enabled
                                                    ? completedColor
                                                    : themePalette.muted_fg)
                                        }

                                        Switch {
                                            id: rowToggle
                                            objectName: "addonManagerRowToggle"
                                            Layout.preferredHeight: 18
                                            scale: 0.72
                                            enabled: !modelData.unavailable && !controller.installing
                                            checked: Boolean(modelData.enabled)
                                            onToggled: controller.setAddonEnabled(
                                                String(modelData.addonId || ""),
                                                checked
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: detailPane
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: themePalette.app_bg
                border.color: themePalette.border

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        id: detailHeader
                        Layout.fillWidth: true
                        Layout.preferredHeight: selectedStateColumn.implicitHeight + 28
                        color: themePalette.panel_bg
                        border.color: themePalette.border

                        ColumnLayout {
                            id: selectedStateColumn
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 10

                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: controller.hasSelection ? headerRow.implicitHeight : emptyHeader.implicitHeight

                                RowLayout {
                                    id: headerRow
                                    anchors.fill: parent
                                    spacing: 12
                                    visible: controller.hasSelection

                                    Rectangle {
                                        Layout.preferredWidth: 42
                                        Layout.preferredHeight: 42
                                        radius: 6
                                        color: nodeCardBg
                                        border.color: nodeCardBorder

                                        Rectangle {
                                            anchors.left: parent.left
                                            anchors.top: parent.top
                                            anchors.bottom: parent.bottom
                                            width: 4
                                            color: themePalette.accent
                                        }

                                        Text {
                                            anchors.centerIn: parent
                                            text: String(selectedAddon.iconGlyph || "A")
                                            color: nodeHeaderFg
                                            font.pixelSize: 18
                                            font.bold: true
                                        }
                                    }

                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 3

                                        Flow {
                                            width: parent.width
                                            spacing: 8

                                            Text {
                                                objectName: "addonManagerDetailTitle"
                                                text: String(selectedAddon.displayName || "")
                                                color: themePalette.panel_title_fg
                                                font.pixelSize: 18
                                                font.bold: true
                                            }

                                            Text {
                                                text: String(selectedAddon.version || "").length > 0
                                                    ? "v" + String(selectedAddon.version || "")
                                                    : ""
                                                color: themePalette.muted_fg
                                                font.pixelSize: 11
                                                font.family: "Consolas"
                                                anchors.bottom: undefined
                                                y: 6
                                            }

                                            Repeater {
                                                model: selectedAddon.statusBadges || []

                                                delegate: Rectangle {
                                                    height: 18
                                                    width: detailBadgeText.implicitWidth + 10
                                                    radius: 2
                                                    color: root.badgeFill(String(modelData.tone || "core"))
                                                    border.color: root.badgeBorder(String(modelData.tone || "core"))
                                                    y: 5

                                                    Text {
                                                        id: detailBadgeText
                                                        anchors.centerIn: parent
                                                        text: String(modelData.label || "")
                                                        color: root.badgeForeground(String(modelData.tone || "core"))
                                                        font.pixelSize: 9
                                                        font.bold: true
                                                        font.letterSpacing: 0.4
                                                    }
                                                }
                                            }

                                            Rectangle {
                                                visible: controller.hasSelection
                                                height: 18
                                                width: policyLabel.implicitWidth + 12
                                                radius: 2
                                                color: selectedAddon.supportsHotApply
                                                    ? Qt.alpha(completedColor, 0.14)
                                                    : Qt.alpha(warningColor, 0.14)
                                                border.color: selectedAddon.supportsHotApply
                                                    ? Qt.alpha(completedColor, 0.38)
                                                    : Qt.alpha(warningColor, 0.38)
                                                y: 5

                                                Text {
                                                    id: policyLabel
                                                    anchors.centerIn: parent
                                                    text: String(selectedAddon.policyBadgeLabel || "")
                                                    color: selectedAddon.supportsHotApply
                                                        ? completedColor
                                                        : warningColor
                                                    font.pixelSize: 9
                                                    font.bold: true
                                                    font.letterSpacing: 0.4
                                                }
                                            }
                                        }

                                        Row {
                                            spacing: 6
                                            topPadding: 4

                                            Text {
                                                text: String(selectedAddon.vendor || "")
                                                color: themePalette.muted_fg
                                                font.pixelSize: 11
                                            }

                                            Text {
                                                visible: String(selectedAddon.addonId || "").length > 0
                                                text: "\u00B7"
                                                color: themePalette.muted_fg
                                                font.pixelSize: 11
                                            }

                                            Text {
                                                text: String(selectedAddon.addonId || "")
                                                color: themePalette.muted_fg
                                                font.pixelSize: 11
                                                font.family: "Consolas"
                                            }
                                        }
                                    }

                                    RowLayout {
                                        spacing: 6

                                        ShellButton {
                                            objectName: "addonManagerFallbackWorkflowSettingsButton"
                                            themeBridgeRef: root.themeBridgeRef
                                            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                                            uiIconsRef: root.uiIconsRef
                                            text: "Preferences..."
                                            enabled: controller.hasSelection
                                            onClicked: controller.requestOpenWorkflowSettings()
                                        }

                                        ShellButton {
                                            objectName: "addonManagerPrimaryToggleButton"
                                            themeBridgeRef: root.themeBridgeRef
                                            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                                            uiIconsRef: root.uiIconsRef
                                            text: controller.installing
                                                ? "Installing..."
                                                : (Boolean(selectedAddon.unavailable) && Boolean(selectedAddon.installable)
                                                    ? String(selectedAddon.installActionLabel || "Install")
                                                    : (Boolean(selectedAddon.enabled) ? "Disable" : "Enable"))
                                            selectedStyle: !Boolean(selectedAddon.enabled)
                                            enabled: controller.hasSelection
                                                && !controller.installing
                                                && (!Boolean(selectedAddon.unavailable) || Boolean(selectedAddon.installable))
                                            onClicked: {
                                                if (Boolean(selectedAddon.unavailable) && Boolean(selectedAddon.installable))
                                                    controller.installSelectedAddon();
                                                else
                                                    controller.toggleSelectedAddon();
                                            }
                                        }
                                    }
                                }

                                Text {
                                    id: emptyHeader
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: !controller.hasSelection
                                    text: "No add-on selected"
                                    color: themePalette.panel_title_fg
                                    font.pixelSize: 14
                                    font.bold: true
                                }
                            }

                            Text {
                                objectName: "addonManagerInstallProgressText"
                                visible: controller.installing && controller.installProgressText.length > 0
                                Layout.fillWidth: true
                                Layout.leftMargin: 12
                                Layout.rightMargin: 12
                                text: controller.installProgressText
                                wrapMode: Text.WordWrap
                                maximumLineCount: 3
                                elide: Text.ElideMiddle
                                color: themePalette.muted_fg
                                font.pixelSize: 11
                            }

                            Rectangle {
                                objectName: "addonManagerPendingBanner"
                                visible: Boolean(selectedAddon.pendingRestart)
                                Layout.fillWidth: true
                                Layout.preferredHeight: pendingBannerText.implicitHeight + 16
                                radius: 3
                                color: Qt.alpha(warningColor, 0.10)
                                border.color: Qt.alpha(warningColor, 0.35)

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    width: 3
                                    color: warningColor
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 14
                                    anchors.rightMargin: 12
                                    spacing: 10

                                    Text {
                                        text: "!"
                                        color: warningColor
                                        font.pixelSize: 14
                                        font.bold: true
                                    }

                                    Text {
                                        id: pendingBannerText
                                        Layout.fillWidth: true
                                        wrapMode: Text.WordWrap
                                        text: "Pending change \u2014 this add-on registers native descriptors at startup. Restart the runtime to apply."
                                        color: themePalette.app_fg
                                        font.pixelSize: 11
                                    }

                                    ShellButton {
                                        objectName: "addonManagerRestartRuntimeButton"
                                        themeBridgeRef: root.themeBridgeRef
                                        graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                                        uiIconsRef: root.uiIconsRef
                                        text: "Restart now"
                                        enabled: false
                                    }
                                }
                            }

                            Rectangle {
                                objectName: "addonManagerErrorBanner"
                                visible: controller.lastError.length > 0
                                Layout.fillWidth: true
                                Layout.preferredHeight: errorBannerText.implicitHeight + 18
                                radius: 4
                                color: Qt.alpha(themePalette.inspector_danger_bg, 0.9)
                                border.color: themePalette.inspector_danger_border

                                Text {
                                    id: errorBannerText
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    wrapMode: Text.WordWrap
                                    text: controller.lastError
                                    color: themePalette.inspector_danger_fg
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: themePalette.panel_bg
                        border.color: themePalette.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            spacing: 0

                            Repeater {
                                model: [
                                    { "id": "about", "label": "About" },
                                    { "id": "dependencies", "label": "Dependencies" },
                                    { "id": "nodes", "label": "Nodes" },
                                    { "id": "changelog", "label": "Changelog" }
                                ]

                                delegate: Rectangle {
                                    objectName: "addonManagerTab" + modelData.label
                                    Layout.preferredWidth: tabLabel.implicitWidth + 28
                                    Layout.fillHeight: true
                                    color: "transparent"
                                    border.color: "transparent"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        height: 2
                                        color: controller.activeTab === modelData.id
                                            ? themePalette.accent
                                            : "transparent"
                                    }

                                    Text {
                                        id: tabLabel
                                        anchors.centerIn: parent
                                        text: modelData.label
                                        color: controller.activeTab === modelData.id
                                            ? themePalette.panel_title_fg
                                            : themePalette.muted_fg
                                        font.pixelSize: 11
                                        font.bold: controller.activeTab === modelData.id
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: controller.hasSelection
                                        onClicked: controller.setActiveTab(modelData.id)
                                    }
                                }
                            }
                        }
                    }

                    ScrollView {
                        id: detailScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: detailScroll.availableWidth
                            spacing: 14
                            padding: 20

                            Rectangle {
                                objectName: "addonManagerDetailEmptyState"
                                visible: !controller.hasSelection
                                width: parent.width
                                height: 120
                                radius: 6
                                color: themePalette.inspector_card_bg
                                border.color: themePalette.border

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 6

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "Select an add-on to inspect it."
                                        color: themePalette.panel_title_fg
                                        font.pixelSize: 13
                                        font.bold: true
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "About, dependencies, node registrations, and restart state appear here."
                                        color: themePalette.muted_fg
                                        font.pixelSize: 11
                                    }
                                }
                            }

                            Column {
                                visible: controller.hasSelection && controller.activeTab === "about"
                                width: parent.width
                                spacing: 0

                                Text {
                                    width: parent.width
                                    text: String(selectedAddon.details || selectedAddon.summary || "")
                                    wrapMode: Text.WordWrap
                                    color: themePalette.app_fg
                                    font.pixelSize: 13
                                    lineHeight: 1.6
                                    bottomPadding: 16
                                }

                                GridLayout {
                                    columns: 4
                                    rowSpacing: 12
                                    columnSpacing: 12
                                    width: parent.width

                                    Repeater {
                                        model: selectedAddon.aboutFacts || []

                                        delegate: Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: factColumn.implicitHeight + 20
                                            radius: 6
                                            color: themePalette.inspector_card_bg
                                            border.color: themePalette.border

                                            Rectangle {
                                                visible: String(modelData.label || "") === "Activation"
                                                anchors.left: parent.left
                                                anchors.top: parent.top
                                                anchors.bottom: parent.bottom
                                                width: 3
                                                color: selectedAddon.supportsHotApply
                                                    ? completedColor
                                                    : warningColor
                                            }

                                            Column {
                                                id: factColumn
                                                anchors.left: parent.left
                                                anchors.right: parent.right
                                                anchors.verticalCenter: parent.verticalCenter
                                                anchors.leftMargin: 12
                                                anchors.rightMargin: 12
                                                spacing: 4

                                                Text {
                                                    text: String(modelData.label || "").toUpperCase()
                                                    color: themePalette.muted_fg
                                                    font.pixelSize: 10
                                                    font.bold: true
                                                    font.letterSpacing: 0.5
                                                }

                                                Text {
                                                    width: parent.width
                                                    text: String(modelData.value || "")
                                                    color: themePalette.app_fg
                                                    font.pixelSize: 13
                                                    font.family: "Consolas"
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }

                                Item {
                                    width: parent.width
                                    height: 20
                                }

                                Text {
                                    width: parent.width
                                    text: "PYTHON REQUIREMENT"
                                    color: themePalette.muted_fg
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    bottomPadding: 8
                                }

                                Rectangle {
                                    width: parent.width
                                    height: pythonRequirementText.implicitHeight + 16
                                    radius: 4
                                    color: themePalette.console_bg
                                    border.color: themePalette.border

                                    Text {
                                        id: pythonRequirementText
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        wrapMode: Text.WordWrap
                                        text: String(selectedAddon.pythonRequirement || "")
                                        color: themePalette.app_fg
                                        font.pixelSize: 12
                                        font.family: "Consolas"
                                    }
                                }

                                Item {
                                    width: parent.width
                                    height: 20
                                }

                                Text {
                                    width: parent.width
                                    text: "RUNTIME FACTS"
                                    color: themePalette.muted_fg
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    bottomPadding: 8
                                }

                                Column {
                                    width: parent.width
                                    spacing: 4

                                    Text {
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                        text: String(selectedAddon.policyCopy || "")
                                        color: themePalette.app_fg
                                        font.pixelSize: 12
                                        lineHeight: 1.5
                                    }

                                    Text {
                                        width: parent.width
                                        wrapMode: Text.WordWrap
                                        text: String(selectedAddon.availabilitySummary || "")
                                        color: themePalette.muted_fg
                                        font.pixelSize: 12
                                        lineHeight: 1.5
                                    }
                                }
                            }

                            Column {
                                visible: controller.hasSelection && controller.activeTab === "dependencies"
                                width: parent.width
                                spacing: 0

                                Text {
                                    width: parent.width
                                    text: "PYTHON PACKAGES REQUIRED"
                                    color: themePalette.muted_fg
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    bottomPadding: 10
                                }

                                Column {
                                    width: parent.width
                                    spacing: 4
                                    visible: (selectedAddon.dependencyItems || []).length > 0

                                    Repeater {
                                        model: selectedAddon.dependencyItems || []

                                        delegate: Rectangle {
                                            width: parent.width
                                            height: 32
                                            radius: 4
                                            color: themePalette.inspector_card_bg
                                            border.color: themePalette.border

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 10
                                                anchors.rightMargin: 10
                                                spacing: 10

                                                Rectangle {
                                                    Layout.preferredWidth: 6
                                                    Layout.preferredHeight: 6
                                                    radius: 3
                                                    color: Boolean(modelData.satisfied)
                                                        ? completedColor
                                                        : warningColor
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: String(modelData.name || "")
                                                    color: themePalette.app_fg
                                                    font.pixelSize: 12
                                                    font.family: "Consolas"
                                                }

                                                Text {
                                                    text: String(modelData.statusLabel || "")
                                                    color: Boolean(modelData.satisfied)
                                                        ? themePalette.muted_fg
                                                        : warningColor
                                                    font.pixelSize: 10
                                                    font.family: "Consolas"
                                                }
                                            }
                                        }
                                    }
                                }

                                Text {
                                    visible: (selectedAddon.dependencyItems || []).length === 0
                                    width: parent.width
                                    text: "No external dependencies."
                                    color: themePalette.muted_fg
                                    font.pixelSize: 12
                                }

                                Item {
                                    width: parent.width
                                    height: 20
                                }

                                Text {
                                    width: parent.width
                                    text: "AVAILABILITY"
                                    color: themePalette.muted_fg
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    bottomPadding: 8
                                }

                                Text {
                                    width: parent.width
                                    wrapMode: Text.WordWrap
                                    text: String(selectedAddon.availabilitySummary || "")
                                    color: themePalette.app_fg
                                    font.pixelSize: 12
                                    lineHeight: 1.5
                                }

                                Item {
                                    visible: (selectedAddon.missingDependencies || []).length > 0
                                    width: parent.width
                                    height: 14
                                }

                                Rectangle {
                                    visible: (selectedAddon.missingDependencies || []).length > 0
                                    width: parent.width
                                    height: missingDepsBox.implicitHeight + 20
                                    radius: 4
                                    color: Qt.alpha(warningColor, 0.10)
                                    border.color: Qt.alpha(warningColor, 0.35)

                                    Column {
                                        id: missingDepsBox
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.leftMargin: 12
                                        anchors.rightMargin: 12
                                        spacing: 6

                                        Text {
                                            text: "MISSING DEPENDENCIES"
                                            color: warningColor
                                            font.pixelSize: 10
                                            font.bold: true
                                            font.letterSpacing: 0.5
                                        }

                                        Text {
                                            width: parent.width
                                            wrapMode: Text.WordWrap
                                            text: (selectedAddon.missingDependencies || []).join(", ")
                                            color: themePalette.app_fg
                                            font.pixelSize: 12
                                            font.family: "Consolas"
                                        }
                                    }
                                }
                            }

                            Column {
                                visible: controller.hasSelection && controller.activeTab === "nodes"
                                width: parent.width
                                spacing: 10

                                Text {
                                    visible: (selectedAddon.nodeItems || []).length > 0
                                    width: parent.width
                                    text: "Showing " + String(Math.min((selectedAddon.nodeItems || []).length, selectedAddon.nodeCount || 0))
                                        + " of " + String(selectedAddon.nodeCount || 0)
                                        + " descriptors registered by this add-on."
                                    color: themePalette.muted_fg
                                    font.pixelSize: 11
                                }

                                Rectangle {
                                    visible: (selectedAddon.nodeItems || []).length > 0
                                    width: parent.width
                                    height: nodeItemsColumn.implicitHeight
                                    radius: 6
                                    color: "transparent"
                                    border.color: themePalette.border
                                    clip: true

                                    Column {
                                        id: nodeItemsColumn
                                        width: parent.width
                                        spacing: 0

                                        Repeater {
                                            model: selectedAddon.nodeItems || []

                                            delegate: Rectangle {
                                                width: parent.width
                                                height: 38
                                                color: index % 2 === 0 ? themePalette.panel_alt_bg : themePalette.panel_bg

                                                Rectangle {
                                                    visible: index < (selectedAddon.nodeItems || []).length - 1
                                                    anchors.left: parent.left
                                                    anchors.right: parent.right
                                                    anchors.bottom: parent.bottom
                                                    height: 1
                                                    color: themePalette.border
                                                }

                                                RowLayout {
                                                    anchors.fill: parent
                                                    anchors.leftMargin: 12
                                                    anchors.rightMargin: 12
                                                    spacing: 10

                                                    Rectangle {
                                                        Layout.preferredWidth: 18
                                                        Layout.preferredHeight: 18
                                                        radius: 3
                                                        color: nodeCardBg

                                                        Rectangle {
                                                            anchors.left: parent.left
                                                            anchors.top: parent.top
                                                            anchors.bottom: parent.bottom
                                                            width: 2
                                                            color: themePalette.accent
                                                        }

                                                        Text {
                                                            anchors.centerIn: parent
                                                            text: String(modelData.displayName || "").length > 0
                                                                ? String(modelData.displayName || "").slice(0, 1).toUpperCase()
                                                                : "N"
                                                            color: nodeHeaderFg
                                                            font.pixelSize: 10
                                                            font.bold: true
                                                        }
                                                    }

                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: String(modelData.displayName || "")
                                                        color: themePalette.app_fg
                                                        font.pixelSize: 12
                                                        elide: Text.ElideRight
                                                    }

                                                    Text {
                                                        Layout.preferredWidth: 100
                                                        text: String(modelData.runtimeBehavior || "")
                                                        color: themePalette.muted_fg
                                                        font.pixelSize: 10
                                                        font.family: "Consolas"
                                                        elide: Text.ElideRight
                                                    }

                                                    Text {
                                                        Layout.preferredWidth: 200
                                                        text: String(modelData.typeId || "")
                                                        color: themePalette.muted_fg
                                                        font.pixelSize: 10
                                                        font.family: "Consolas"
                                                        elide: Text.ElideLeft
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    visible: (selectedAddon.nodeItems || []).length === 0
                                    width: parent.width
                                    height: 70
                                    radius: 6
                                    color: themePalette.inspector_card_bg
                                    border.color: themePalette.border

                                    Text {
                                        anchors.centerIn: parent
                                        text: "This add-on does not currently publish node descriptors."
                                        color: themePalette.muted_fg
                                        font.pixelSize: 12
                                    }
                                }
                            }

                            Column {
                                visible: controller.hasSelection && controller.activeTab === "changelog"
                                width: parent.width
                                spacing: 22

                                Repeater {
                                    model: selectedAddon.changelogEntries || []

                                    delegate: Column {
                                        width: parent.width
                                        spacing: 6

                                        Row {
                                            spacing: 10

                                            Text {
                                                text: String(modelData.versionLabel || "")
                                                color: themePalette.accent
                                                font.pixelSize: 12
                                                font.bold: true
                                                font.family: "Consolas"
                                            }

                                            Text {
                                                text: String(modelData.dateLabel || "")
                                                color: themePalette.muted_fg
                                                font.pixelSize: 11
                                            }
                                        }

                                        Text {
                                            width: parent.width
                                            text: String(modelData.title || "")
                                            color: themePalette.panel_title_fg
                                            font.pixelSize: 12
                                            font.bold: true
                                        }

                                        Repeater {
                                            model: modelData.bullets || []

                                            delegate: Row {
                                                width: parent.width
                                                spacing: 8
                                                leftPadding: 8

                                                Text {
                                                    text: "•"
                                                    color: themePalette.muted_fg
                                                    font.pixelSize: 12
                                                }

                                                Text {
                                                    width: parent.width - 24
                                                    wrapMode: Text.WordWrap
                                                    text: String(modelData || "")
                                                    color: themePalette.app_fg
                                                    font.pixelSize: 12
                                                    lineHeight: 1.55
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
        }
    }
}
