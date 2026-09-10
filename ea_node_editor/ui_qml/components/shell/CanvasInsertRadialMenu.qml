import QtQuick 2.15
import QtQuick.Controls 2.15
import "../common" as Common

Item {
    id: root
    objectName: "canvasInsertRadialMenu"

    property var shellLibraryBridgeRef: null
    property var canvasCommandBridgeRef: null
    property var graphCanvasStateBridgeRef: null
    property var themeBridgeRef: null
    property var uiIconsRef: null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property var learnedItems: root.shellLibraryBridgeRef
        ? root.shellLibraryBridgeRef.frequent_node_library_items
        : []
    readonly property var slotEntries: root._slotEntries()
    property int hoveredSlot: -1

    signal openNodeBrowserRequested(string initialQuery, real sceneX, real sceneY, string mode)

    visible: !!root.shellLibraryBridgeRef
        && root.shellLibraryBridgeRef.connection_quick_insert_open
        && root.shellLibraryBridgeRef.connection_quick_insert_is_canvas_mode
    z: 1120
    focus: visible

    function _slotEntries() {
        if (!root.learnedItems.length) {
            return [
                { "kind": "nodes", "angle": -90, "label": "Nodes" },
                { "kind": "templates", "angle": 90, "label": "Templates" }
            ]
        }
        var entries = [
            { "kind": "nodes", "angle": -112, "label": "Nodes" },
            { "kind": "templates", "angle": 180, "label": "Templates" }
        ]
        var angles = [-62, -12, 38, 88, 138]
        for (var index = 0; index < Math.min(5, root.learnedItems.length); ++index) {
            entries.push({
                "kind": "node",
                "angle": angles[index],
                "label": String(root.learnedItems[index].display_name || ""),
                "item": root.learnedItems[index]
            })
        }
        return entries
    }

    function _closeMenu() {
        if (root.shellLibraryBridgeRef)
            root.shellLibraryBridgeRef.request_close_connection_quick_insert()
    }

    function _openBrowser(query) {
        var sceneX = Number(root.shellLibraryBridgeRef.connection_quick_insert_scene_x || 0)
        var sceneY = Number(root.shellLibraryBridgeRef.connection_quick_insert_scene_y || 0)
        root._closeMenu()
        root.openNodeBrowserRequested(String(query || ""), sceneX, sceneY, "nodes")
    }

    function _insertNode(item) {
        if (!item || !root.canvasCommandBridgeRef)
            return false
        var typeId = String(item.type_id || "")
        if (!typeId.length)
            return false
        var created = root.canvasCommandBridgeRef.request_drop_node_from_library(
            typeId,
            Number(root.shellLibraryBridgeRef.connection_quick_insert_scene_x || 0),
            Number(root.shellLibraryBridgeRef.connection_quick_insert_scene_y || 0),
            "",
            "",
            "",
            ""
        )
        if (created)
            root._closeMenu()
        return Boolean(created)
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape) {
            root._closeMenu()
            event.accepted = true
            return
        }
        var typed = String(event.text || "")
        if (typed.length && (event.modifiers === Qt.NoModifier || event.modifiers === Qt.ShiftModifier)) {
            root._openBrowser(typed)
            event.accepted = true
        }
    }

    onVisibleChanged: {
        root.hoveredSlot = -1
        if (visible)
            Qt.callLater(function() { root.forceActiveFocus() })
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.visible
        onClicked: root._closeMenu()
    }

    Item {
        id: wheel
        objectName: "canvasInsertRadialWheel"
        width: Math.max(300, Math.min(320, root.width - 32, root.height - 32))
        height: width
        x: Math.max(
            16,
            Math.min(
                root.width - width - 16,
                Number(root.shellLibraryBridgeRef.connection_quick_insert_overlay_x || 0) - width / 2
            )
        )
        y: Math.max(
            16,
            Math.min(
                root.height - height - 16,
                Number(root.shellLibraryBridgeRef.connection_quick_insert_overlay_y || 0) - height / 2
            )
        )

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: root.themePalette.panel_bg
            border.color: root.themePalette.border
            border.width: 1
        }

        Canvas {
            id: hoverArc
            anchors.fill: parent
            property int slotIndex: root.hoveredSlot
            onSlotIndexChanged: requestPaint()
            onPaint: {
                var context = getContext("2d")
                context.clearRect(0, 0, width, height)
                if (slotIndex < 0 || slotIndex >= root.slotEntries.length)
                    return
                var angle = Number(root.slotEntries[slotIndex].angle || 0) * Math.PI / 180
                context.beginPath()
                context.strokeStyle = "#ff9b5b"
                context.lineWidth = 8
                context.arc(width / 2, height / 2, width / 2 - 7, angle - 0.35, angle + 0.35)
                context.stroke()
            }
        }

        Repeater {
            model: root.slotEntries

            delegate: Item {
                id: slot
                required property int index
                required property var modelData
                property real angleRadians: Number(modelData.angle || 0) * Math.PI / 180
                property real orbitRadius: wheel.width * 0.36
                property bool isLearnedNode: String(modelData.kind || "") === "node"
                property bool isTemplates: String(modelData.kind || "") === "templates"
                activeFocusOnTab: true
                width: Math.max(82, wheel.width * 0.17)
                height: Math.max(74, wheel.width * 0.15)
                x: wheel.width / 2 + Math.cos(angleRadians) * orbitRadius - width / 2
                y: wheel.height / 2 + Math.sin(angleRadians) * orbitRadius - height / 2

                onActiveFocusChanged: {
                    if (activeFocus)
                        root.hoveredSlot = slot.index
                    else if (root.hoveredSlot === slot.index && !slotMouse.containsMouse)
                        root.hoveredSlot = -1
                }

                Keys.onPressed: function(event) {
                    if (event.key !== Qt.Key_Return
                            && event.key !== Qt.Key_Enter
                            && event.key !== Qt.Key_Space)
                        return
                    if (!slot.isTemplates) {
                        if (slot.isLearnedNode)
                            root._insertNode(slot.modelData.item)
                        else
                            root._openBrowser("")
                    }
                    event.accepted = true
                }

                Column {
                    anchors.centerIn: parent
                    width: parent.width
                    spacing: 4

                    Item {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 40
                        height: 36

                        LibraryNodeVisual {
                            anchors.fill: parent
                            visible: slot.isLearnedNode
                            libraryVisual: slot.isLearnedNode ? slot.modelData.item.library_visual : ({})
                            displayName: slot.modelData.label
                            uiIconsRef: root.uiIconsRef
                            fillColor: root.themePalette.panel_alt_bg
                            fillCompositeBaseColor: root.themePalette.panel_bg
                            strokeColor: root.themePalette.border
                            iconColor: root.themePalette.app_fg
                        }

                        Image {
                            anchors.centerIn: parent
                            width: 30
                            height: 30
                            visible: !slot.isLearnedNode && source.toString().length > 0
                            source: root.uiIconsRef
                                ? root.uiIconsRef.sourceSized(
                                    slot.isTemplates ? "layout-dashboard" : "node-chrome",
                                    30,
                                    String(slot.isTemplates ? root.themePalette.muted_fg : root.themePalette.app_fg)
                                )
                                : ""
                            fillMode: Image.PreserveAspectFit
                        }
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: String(slot.modelData.label || "")
                        color: slot.isTemplates ? root.themePalette.muted_fg : root.themePalette.app_fg
                        font.pixelSize: Math.max(11, Math.min(15, wheel.width * 0.025))
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    id: slotMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: slot.isTemplates ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onContainsMouseChanged: {
                        if (containsMouse)
                            root.hoveredSlot = slot.index
                        else if (root.hoveredSlot === slot.index && !slot.activeFocus)
                            root.hoveredSlot = -1
                    }
                    onClicked: {
                        mouse.accepted = true
                        if (slot.isTemplates)
                            return
                        if (slot.isLearnedNode)
                            root._insertNode(slot.modelData.item)
                        else
                            root._openBrowser("")
                    }
                }

                Common.ManagedToolTip {
                    policyBridge: root.graphCanvasStateBridgeRef
                    category: "general"
                    active: slotMouse.containsMouse || slot.activeFocus
                    delay: 300
                    maximumTextWidth: 320
                    text: slot.isTemplates
                        ? "Templates (Ctrl+T)\nComing later."
                        : (slot.isLearnedNode
                            ? String(slot.modelData.label || "") + "\n" + String(slot.modelData.item.description || "")
                            : "Nodes (Ctrl+B)\nBrowse all available nodes.")
                }
            }
        }

        Rectangle {
            id: searchTarget
            objectName: "canvasInsertRadialSearchTarget"
            anchors.centerIn: parent
            width: wheel.width * 0.47
            height: width
            radius: width / 2
            color: Qt.rgba(0.35, 0.35, 0.35, 0.84)

            Text {
                anchors.centerIn: parent
                width: parent.width - 30
                horizontalAlignment: Text.AlignHCenter
                text: "Type to search"
                color: "white"
                font.pixelSize: Math.max(17, Math.min(28, wheel.width * 0.047))
                wrapMode: Text.WordWrap
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.IBeamCursor
                onClicked: {
                    mouse.accepted = true
                    root._openBrowser("")
                }
            }
        }
    }
}
