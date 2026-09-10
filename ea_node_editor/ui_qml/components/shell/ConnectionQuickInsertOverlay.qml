import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "connectionQuickInsertOverlay"
    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    function _wheelDeltaY(wheel) {
        if (!wheel)
            return 0
        if (wheel.angleDelta && wheel.angleDelta.y !== undefined)
            return Number(wheel.angleDelta.y)
        if (wheel.pixelDelta && wheel.pixelDelta.y !== undefined)
            return Number(wheel.pixelDelta.y)
        return 0
    }

    function _clamp(value, minValue, maxValue) {
        return Math.max(minValue, Math.min(maxValue, value))
    }

    function _scrollResultsByWheel(wheel) {
        if (!quickInsertResults.visible)
            return
        var deltaY = root._wheelDeltaY(wheel)
        if (Math.abs(deltaY) < 0.001)
            return
        var step = (-deltaY / 120.0) * 40.0
        if (Math.abs(step) < 1.0)
            step = deltaY > 0 ? -24.0 : 24.0
        var maxContentY = Math.max(0, quickInsertResults.contentHeight - quickInsertResults.height)
        quickInsertResults.contentY = root._clamp(
            quickInsertResults.contentY + step,
            0,
            maxContentY
        )
    }

    visible: root.shellLibraryBridgeRef.connection_quick_insert_open
    width: Math.min(parent.width * 0.34, 360)
    height: quickInsertContent.implicitHeight + 20
    color: themePalette.panel_alt_bg
    border.color: themePalette.accent
    border.width: 1
    radius: 6
    z: 1120
    focus: visible
    activeFocusOnTab: visible

    x: {
        if (!parent)
            return 0
        var preferred = Number(root.shellLibraryBridgeRef.connection_quick_insert_overlay_x || 0) + 12
        return Math.max(8, Math.min(parent.width - width - 8, preferred))
    }
    y: {
        if (!parent)
            return 0
        var preferred = Number(root.shellLibraryBridgeRef.connection_quick_insert_overlay_y || 0) + 12
        return Math.max(8, Math.min(parent.height - height - 8, preferred))
    }

    onVisibleChanged: {
        if (!visible)
            return
        Qt.callLater(function() {
            quickInsertField.forceActiveFocus()
            quickInsertField.selectAll()
        })
    }

    Connections {
        target: quickInsertField
        function onActiveFocusChanged() {
            if (!quickInsertField.activeFocus && root.visible)
                Qt.callLater(function() {
                    if (!quickInsertField.activeFocus && root.visible)
                        root.shellLibraryBridgeRef.request_close_connection_quick_insert()
                })
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        propagateComposedEvents: true
        onWheel: function(wheel) {
            root._scrollResultsByWheel(wheel)
            wheel.accepted = true
        }
    }

    Connections {
        target: root.shellLibraryBridgeRef
        function onConnection_quick_insert_changed() {
            var index = Number(root.shellLibraryBridgeRef.connection_quick_insert_highlight_index)
            if (!root.visible || index < 0 || index >= quickInsertResults.count)
                return
            quickInsertResults.positionViewAtIndex(index, ListView.Contain)
        }
    }

    Column {
        id: quickInsertContent
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 8

        RowLayout {
            width: parent.width

            Text {
                text: "Quick Insert"
                color: root.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            Item { Layout.fillWidth: true }

            Text {
                text: "Esc"
                color: root.themePalette.muted_fg
                font.pixelSize: 11
            }
        }

        Text {
            width: parent.width
            visible: text.length > 0
            text: root.shellLibraryBridgeRef.connection_quick_insert_source_summary
            color: root.themePalette.muted_fg
            font.pixelSize: 10
            elide: Text.ElideRight
        }

        TextField {
            id: quickInsertField
            objectName: "connectionQuickInsertField"
            width: parent.width
            placeholderText: root.shellLibraryBridgeRef.connection_quick_insert_is_canvas_mode
                ? "Search nodes..."
                : "Insert compatible node..."
            text: root.shellLibraryBridgeRef.connection_quick_insert_query
            selectByMouse: true
            color: root.themePalette.input_fg
            placeholderTextColor: root.themePalette.muted_fg
            Keys.priority: Keys.BeforeItem
            background: Rectangle {
                color: root.themePalette.input_bg
                border.color: root.themePalette.input_border
                radius: 4
            }
            onTextChanged: root.shellLibraryBridgeRef.set_connection_quick_insert_query(text)
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Up) {
                    root.shellLibraryBridgeRef.request_connection_quick_insert_move(-1)
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Down) {
                    root.shellLibraryBridgeRef.request_connection_quick_insert_move(1)
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
                    root.shellLibraryBridgeRef.request_connection_quick_insert_accept()
                    event.accepted = true
                    return
                }
                if (event.key === Qt.Key_Escape) {
                    root.shellLibraryBridgeRef.request_close_connection_quick_insert()
                    event.accepted = true
                }
            }
        }

        ListView {
            id: quickInsertResults
            width: parent.width
            height: visible ? Math.min(
                280,
                Math.max(64, root.shellLibraryBridgeRef.connection_quick_insert_results.length * 66)
            ) : 0
            clip: true
            spacing: 2
            model: root.shellLibraryBridgeRef.connection_quick_insert_results
            visible: model.length > 0

            delegate: Rectangle {
                width: ListView.view.width
                height: 64
                radius: 3
                color: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index
                    ? root.themePalette.accent_strong
                    : (resultMouse.containsMouse ? root.themePalette.hover : "transparent")
                border.width: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index ? 1 : 0
                border.color: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index
                    ? root.themePalette.accent
                    : "transparent"

                Column {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    spacing: 2

                    Text {
                        width: parent.width
                        text: String(modelData.display_name || "")
                        color: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index
                            ? root.themePalette.tab_selected_fg
                            : root.themePalette.app_fg
                        font.pixelSize: 12
                        font.bold: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index
                        elide: Text.ElideRight
                    }

                    Text {
                        width: parent.width
                        text: String(modelData.category || "")
                        color: index === root.shellLibraryBridgeRef.connection_quick_insert_highlight_index
                            ? root.themePalette.tab_selected_fg
                            : root.themePalette.muted_fg
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }

                    Text {
                        objectName: "connectionQuickInsertPortSummary"
                        width: parent.width
                        text: (modelData.compatible_port_summaries || []).join(", ")
                        color: "#8EC9A6"
                        font.pixelSize: 10
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: resultMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    onEntered: root.shellLibraryBridgeRef.request_connection_quick_insert_highlight(index)
                    onClicked: root.shellLibraryBridgeRef.request_connection_quick_insert_choose(index)
                }
            }
        }

        Text {
            objectName: "connectionQuickInsertEmptyMessage"
            visible: root.shellLibraryBridgeRef.connection_quick_insert_results.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            text: root.shellLibraryBridgeRef.connection_quick_insert_is_canvas_mode
                ? "No matching nodes."
                : (String(root.shellLibraryBridgeRef.connection_quick_insert_query || "").trim().length === 0
                    ? "No direct type matches. Type to search broader compatible nodes."
                    : "No matching compatible nodes.")
            color: root.themePalette.muted_fg
            font.pixelSize: 11
        }
    }
}
