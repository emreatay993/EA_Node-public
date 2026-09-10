import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property var workspaceBridgeRef: typeof shellWorkspaceBridge !== "undefined" ? shellWorkspaceBridge : null
    property var viewBridgeRef
    property var scriptEditorBridgeRef
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    Layout.fillWidth: true
    Layout.preferredHeight: 38
    color: themePalette.toolbar_bg
    border.color: themePalette.border

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 6

        ShellButton {
            objectName: "shellRunToolbarRunPauseResumeButton"
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
            readonly property string runControlMode: root.workspaceBridgeRef.active_workspace_run_control_mode
            iconName: runControlMode
            tooltipCategory: "general"
            enabled: root.workspaceBridgeRef.active_workspace_can_run
                || root.workspaceBridgeRef.active_workspace_can_pause
            onClicked: {
                if (runControlMode === "run")
                    root.workspaceBridgeRef.request_run_workflow()
                else
                    root.workspaceBridgeRef.request_toggle_run_pause()
            }
        }
        ShellButton {
            objectName: "shellRunToolbarStopButton"
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
            iconName: "stop"
            tooltipCategory: "general"
            enabled: root.workspaceBridgeRef.active_workspace_can_stop
            onClicked: root.workspaceBridgeRef.request_stop_workflow()
        }
        ShellButton {
            objectName: "shellRunToolbarAutoButton"
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
            iconName: "rotate-clockwise"
            text: "Auto"
            tooltipText: "Run ready data-only nodes after connection or property changes"
            tooltipCategory: "general"
            selectedStyle: root.workspaceBridgeRef.auto_run_enabled
            onClicked: root.workspaceBridgeRef.request_toggle_auto_run()
        }
        Rectangle {
            Layout.preferredWidth: 1
            Layout.preferredHeight: 22
            Layout.alignment: Qt.AlignVCenter
            color: root.themePalette.border
        }
        Row {
            id: scopeBreadcrumbRow
            objectName: "shellRunToolbarScopeBreadcrumb"
            readonly property int breadcrumbCount: root.workspaceBridgeRef.active_scope_breadcrumb_items.length
            readonly property int maxBreadcrumbWidth: Math.max(128, Math.min(460, root.width * 0.36))
            readonly property int crumbMaxWidth: Math.max(
                54,
                Math.min(
                    210,
                    Math.floor((maxBreadcrumbWidth - 90) / Math.max(1, breadcrumbCount))
                )
            )

            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: Math.min(implicitWidth, maxBreadcrumbWidth)
            Layout.maximumWidth: maxBreadcrumbWidth
            spacing: 5
            clip: true

            Text {
                text: "Scope"
                color: root.themePalette.muted_fg
                font.pixelSize: 10
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }

            Rectangle {
                width: 1
                height: 16
                color: Qt.alpha(root.themePalette.border, 0.84)
                anchors.verticalCenter: parent.verticalCenter
            }

            Repeater {
                model: root.workspaceBridgeRef.active_scope_breadcrumb_items
                delegate: Row {
                    id: scopeBreadcrumbDelegate

                    readonly property string crumbLabel: String(modelData.label || "")
                    readonly property bool activeCrumb: index === root.workspaceBridgeRef.active_scope_breadcrumb_items.length - 1

                    spacing: 5

                    Text {
                        visible: index > 0
                        text: "/"
                        color: Qt.alpha(root.themePalette.muted_fg, 0.62)
                        font.pixelSize: 12
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    TextMetrics {
                        id: crumbLabelMetrics
                        text: scopeBreadcrumbDelegate.crumbLabel
                        font.pixelSize: 11
                        font.bold: scopeBreadcrumbDelegate.activeCrumb
                    }

                    Item {
                        width: Math.max(
                            scopeBreadcrumbDelegate.activeCrumb ? 70 : 42,
                            Math.min(
                                scopeBreadcrumbRow.crumbMaxWidth + (scopeBreadcrumbDelegate.activeCrumb ? 30 : 0),
                                Math.ceil(crumbLabelMetrics.advanceWidth) + 4
                            )
                        )
                        height: 24
                        anchors.verticalCenter: parent.verticalCenter

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: scopeBreadcrumbDelegate.crumbLabel
                            color: scopeBreadcrumbDelegate.activeCrumb
                                ? root.themePalette.tab_selected_fg
                                : root.themePalette.tab_fg
                            font.pixelSize: 11
                            font.bold: scopeBreadcrumbDelegate.activeCrumb
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignLeft
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            width: Math.min(
                                parent.width,
                                Math.ceil(crumbLabelMetrics.advanceWidth)
                            )
                            height: scopeBreadcrumbDelegate.activeCrumb ? 2 : 1
                            radius: height / 2
                            color: scopeBreadcrumbDelegate.activeCrumb
                                ? root.themePalette.accent
                                : Qt.alpha(root.themePalette.border, 0.0)
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.workspaceBridgeRef.request_open_scope_breadcrumb(
                                String(modelData.node_id || "")
                            )
                        }
                    }
                }
            }
        }
        Item { Layout.fillWidth: true }
        Text {
            id: projectFileLabel
            objectName: "shellRunToolbarProjectFileName"
            readonly property int maxLabelWidth: Math.max(96, Math.min(280, root.width * 0.22))

            Layout.alignment: Qt.AlignVCenter
            Layout.preferredWidth: Math.min(implicitWidth, maxLabelWidth)
            Layout.maximumWidth: maxLabelWidth
            text: root.workspaceBridgeRef.project_file_name
            color: root.themePalette.muted_fg
            font.pixelSize: 12
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideMiddle
        }
        Text {
            text: "Zoom: " + Math.round(root.viewBridgeRef.zoom_value * 100) + "%"
            color: root.themePalette.muted_fg
            font.pixelSize: 12
        }
        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: root.themePalette.border }
        ShellButton {
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
            text: root.scriptEditorBridgeRef.visible ? "Hide Script" : "Script"
            selectedStyle: root.scriptEditorBridgeRef.visible
            onClicked: root.workspaceBridgeRef.set_script_editor_panel_visible()
        }
    }
}
