import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "graphSearchOverlay"
    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property var graphSearchScopeOptions: [
        { "scopeId": "title", "label": "Title" },
        { "scopeId": "type", "label": "Node Type" },
        { "scopeId": "content", "label": "Content" },
        { "scopeId": "port", "label": "Port Label" }
    ]
    readonly property bool hasSubsetFilter: root.shellLibraryBridgeRef.graph_search_enabled_scopes.length
        < root.graphSearchScopeOptions.length

    function graphSearchScopeEnabled(scopeId) {
        return root.shellLibraryBridgeRef.graph_search_enabled_scopes.indexOf(scopeId) >= 0
    }

    function graphSearchFilterTooltip() {
        if (root.shellLibraryBridgeRef.graph_search_enabled_scopes.length === root.graphSearchScopeOptions.length)
            return "Search fields: All"
        var activeLabels = []
        for (var index = 0; index < root.graphSearchScopeOptions.length; ++index) {
            var option = root.graphSearchScopeOptions[index]
            if (root.graphSearchScopeEnabled(option.scopeId))
                activeLabels.push(option.label)
        }
        return "Search fields: " + activeLabels.join(", ")
    }

    function graphSearchMatchSummary(modelData) {
        var summary = String(modelData.workspace_name || "")
            + "  |  "
            + String(modelData.display_name || "")
            + "  |  "
            + String(modelData.instance_label || "")
            + "  |  Match: "
            + String(modelData.match_label || "")
        var matchScope = String(modelData.match_scope || "")
        if ((matchScope === "content" || matchScope === "port") && String(modelData.match_preview || "").length > 0)
            summary += "  |  " + String(modelData.match_preview || "")
        return summary
    }

    visible: root.shellLibraryBridgeRef.graph_search_open
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.verticalCenter: parent.verticalCenter
    width: Math.min(parent.width * 0.62, 760)
    height: graphSearchContent.implicitHeight + 20
    color: themePalette.panel_alt_bg
    border.color: themePalette.accent
    border.width: 1
    radius: 6
    z: 1100
    focus: visible
    activeFocusOnTab: visible

    onVisibleChanged: {
        if (!visible) {
            graphSearchFilterPopup.close()
            return
        }
        Qt.callLater(function() {
            graphSearchField.forceActiveFocus()
            graphSearchField.selectAll()
        })
    }

    Connections {
        target: root.shellLibraryBridgeRef
        function onGraph_search_changed() {
            var index = Number(root.shellLibraryBridgeRef.graph_search_highlight_index)
            if (!root.visible || index < 0 || index >= graphSearchResultsList.count)
                return
            graphSearchResultsList.positionViewAtIndex(index, ListView.Contain)
        }
    }

    Column {
        id: graphSearchContent
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 8

        RowLayout {
            width: parent.width

            Text {
                text: "Graph Search"
                color: root.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            Item { Layout.fillWidth: true }

            Text {
                text: "Esc to close"
                color: root.themePalette.muted_fg
                font.pixelSize: 11
            }
        }

        Row {
            id: graphSearchFieldRow
            width: parent.width
            spacing: 6

            TextField {
                id: graphSearchField
                objectName: "graphSearchField"
                width: parent.width - graphSearchFilterButton.width - graphSearchFieldRow.spacing
                placeholderText: "Search graph titles, types, content, or ports"
                text: root.shellLibraryBridgeRef.graph_search_query
                selectByMouse: true
                color: root.themePalette.input_fg
                placeholderTextColor: root.themePalette.muted_fg
                Keys.priority: Keys.BeforeItem
                background: Rectangle {
                    color: root.themePalette.input_bg
                    border.color: root.themePalette.input_border
                    radius: 4
                }
                onTextChanged: root.shellLibraryBridgeRef.set_graph_search_query(text)
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Up) {
                        root.shellLibraryBridgeRef.request_graph_search_move(-1)
                        event.accepted = true
                        return
                    }
                    if (event.key === Qt.Key_Down) {
                        root.shellLibraryBridgeRef.request_graph_search_move(1)
                        event.accepted = true
                        return
                    }
                    if (event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
                        root.shellLibraryBridgeRef.request_graph_search_accept()
                        event.accepted = true
                        return
                    }
                    if (event.key === Qt.Key_Escape) {
                        root.shellLibraryBridgeRef.request_close_graph_search()
                        event.accepted = true
                    }
                }
            }

            ShellButton {
                id: graphSearchFilterButton
                objectName: "graphSearchFilterButton"
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                anchors.verticalCenter: graphSearchField.verticalCenter
                iconName: "filter"
                selectedStyle: root.hasSubsetFilter
                tooltipText: root.graphSearchFilterTooltip()
                tooltipCategory: "tutorial"
                onClicked: {
                    if (graphSearchFilterPopup.visible)
                        graphSearchFilterPopup.close()
                    else
                        graphSearchFilterPopup.open()
                }
            }
        }

        Popup {
            id: graphSearchFilterPopup
            objectName: "graphSearchFilterPopup"
            parent: root
            x: graphSearchFieldRow.x + graphSearchFieldRow.width - width
            y: graphSearchFieldRow.y + graphSearchFieldRow.height + 4
            width: 172
            padding: 6
            modal: false
            focus: visible
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

            background: Rectangle {
                radius: 6
                color: root.themePalette.panel_bg
                border.color: root.themePalette.input_border
                border.width: 1
            }

            contentItem: Column {
                spacing: 4

                Repeater {
                    model: root.graphSearchScopeOptions

                    delegate: Rectangle {
                        id: scopeOptionRow
                        objectName: "graphSearchScopeToggle_" + String(modelData.scopeId || "")
                        readonly property string scopeId: String(modelData.scopeId || "")
                        readonly property string scopeLabel: String(modelData.label || "")
                        readonly property bool scopeEnabled: root.graphSearchScopeEnabled(scopeId)
                        width: graphSearchFilterPopup.width - graphSearchFilterPopup.padding * 2
                        height: 30
                        radius: 4
                        color: scopeToggleMouse.containsMouse ? root.themePalette.hover : "transparent"

                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 6
                            spacing: 8

                            Rectangle {
                                width: 16
                                height: 16
                                radius: 4
                                color: scopeOptionRow.scopeEnabled
                                    ? root.themePalette.accent
                                    : root.themePalette.input_bg
                                border.color: scopeOptionRow.scopeEnabled
                                    ? root.themePalette.accent
                                    : root.themePalette.input_border
                                border.width: 1

                                Text {
                                    anchors.centerIn: parent
                                    text: scopeOptionRow.scopeEnabled ? "✓" : ""
                                    color: scopeOptionRow.scopeEnabled
                                        ? root.themePalette.panel_bg
                                        : "transparent"
                                    font.pixelSize: 10
                                    font.bold: true
                                }
                            }

                            Text {
                                text: scopeOptionRow.scopeLabel
                                color: root.themePalette.input_fg
                                font.pixelSize: 11
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        MouseArea {
                            id: scopeToggleMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton
                            onClicked: {
                                root.shellLibraryBridgeRef.set_graph_search_scope_enabled(
                                    parent.scopeId,
                                    !parent.scopeEnabled
                                )
                                Qt.callLater(function() {
                                    if (root.visible)
                                        graphSearchField.forceActiveFocus()
                                })
                            }
                        }
                    }
                }
            }
        }

        ListView {
            id: graphSearchResultsList
            width: parent.width
            height: visible ? Math.min(
                320,
                Math.max(44, root.shellLibraryBridgeRef.graph_search_results.length * 44)
            ) : 0
            clip: true
            spacing: 2
            model: root.shellLibraryBridgeRef.graph_search_results
            visible: root.shellLibraryBridgeRef.graph_search_results.length > 0

            delegate: Rectangle {
                width: ListView.view.width
                height: 42
                radius: 3
                color: index === root.shellLibraryBridgeRef.graph_search_highlight_index
                    ? root.themePalette.accent_strong
                    : (resultMouse.containsMouse ? root.themePalette.hover : "transparent")
                border.width: index === root.shellLibraryBridgeRef.graph_search_highlight_index ? 1 : 0
                border.color: index === root.shellLibraryBridgeRef.graph_search_highlight_index
                    ? root.themePalette.accent
                    : "transparent"

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    anchors.topMargin: 4
                    anchors.bottomMargin: 4
                    spacing: 1

                    Text {
                        width: parent.width
                        text: String(modelData.node_title || "")
                        color: index === root.shellLibraryBridgeRef.graph_search_highlight_index
                            ? root.themePalette.tab_selected_fg
                            : root.themePalette.app_fg
                        font.pixelSize: 12
                        font.bold: index === root.shellLibraryBridgeRef.graph_search_highlight_index
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: root.graphSearchMatchSummary(modelData)
                        color: index === root.shellLibraryBridgeRef.graph_search_highlight_index
                            ? root.themePalette.tab_selected_fg
                            : root.themePalette.muted_fg
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: resultMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    onEntered: root.shellLibraryBridgeRef.request_graph_search_highlight(index)
                    onClicked: root.shellLibraryBridgeRef.request_graph_search_jump(index)
                }
            }
        }

        Text {
            visible: root.shellLibraryBridgeRef.graph_search_query.length > 0
                && root.shellLibraryBridgeRef.graph_search_results.length === 0
            text: "No matching nodes."
            color: root.themePalette.muted_fg
            font.pixelSize: 11
        }

        Text {
            text: "Up/Down to select, Enter to jump"
            color: root.themePalette.muted_fg
            font.pixelSize: 10
        }
    }
}
