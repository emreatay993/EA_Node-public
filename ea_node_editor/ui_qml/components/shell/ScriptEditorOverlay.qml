import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property var workspaceBridgeRef: typeof shellWorkspaceBridge !== "undefined" ? shellWorkspaceBridge : null
    property var scriptEditorBridgeRef
    property var scriptHighlighterBridgeRef
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    // User-resizable panel width. `panelWidth` holds the user's chosen width
    // (0 => use the responsive default); the rendered `width` is always clamped
    // to the current window so the panel stays usable and on screen.
    property real panelWidth: 0
    property bool resizeDragActive: false
    readonly property real minPanelWidth: 320
    readonly property real defaultPanelWidth: Math.min((parent ? parent.width : 1200) * 0.42, 520)
    readonly property real maxPanelWidth: Math.max(minPanelWidth, (parent ? parent.width : 1200) * 0.85)

    function clampPanelWidth(value) {
        return Math.max(root.minPanelWidth, Math.min(root.maxPanelWidth, value))
    }

    function effectivePanelWidth() {
        return root.clampPanelWidth(root.panelWidth > 0 ? root.panelWidth : root.defaultPanelWidth)
    }

    function syncWidthFromModel() {
        var stored = root.scriptEditorBridgeRef ? Number(root.scriptEditorBridgeRef.panel_width) : 0
        root.panelWidth = stored > 0 ? stored : 0
    }

    visible: root.scriptEditorBridgeRef.visible
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.bottom: parent.bottom
    width: root.effectivePanelWidth()
    color: themePalette.panel_bg
    border.color: themePalette.accent
    border.width: 1
    z: 999

    Component.onCompleted: root.syncWidthFromModel()

    Connections {
        target: root.scriptEditorBridgeRef
        function onWidth_changed() { root.syncWidthFromModel() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            color: root.themePalette.toolbar_bg
            border.color: root.themePalette.border
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                Text {
                    text: root.scriptEditorBridgeRef.current_node_label
                        ? "Python Script: " + root.scriptEditorBridgeRef.current_node_label
                        : "Python Script Editor"
                    color: root.themePalette.panel_title_fg
                    font.pixelSize: 12
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: root.scriptEditorBridgeRef.dirty ? "*Modified" : "Saved"
                    color: root.scriptEditorBridgeRef.dirty
                        ? root.themePalette.accent
                        : root.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ShellButton {
                    themeBridgeRef: root.themeBridgeRef
                    graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                    uiIconsRef: root.uiIconsRef
                    text: "X"
                    onClicked: root.workspaceBridgeRef.set_script_editor_panel_visible(false)
                }
            }
        }

        ScriptCodeEditorPane {
            Layout.fillWidth: true
            Layout.fillHeight: true
            scriptEditorBridgeRef: root.scriptEditorBridgeRef
            scriptHighlighterBridgeRef: root.scriptHighlighterBridgeRef
            themeBridgeRef: root.themeBridgeRef
            graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
            uiIconsRef: root.uiIconsRef
        }
    }

    Rectangle {
        id: scriptEditorResizeHandle
        objectName: "scriptEditorResizeHandle"
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 6
        z: 1000
        color: scriptEditorResizeMouseArea.containsMouse || root.resizeDragActive
            ? Qt.alpha(root.themePalette.accent || "#60CDFF", 0.45)
            : "transparent"

        MouseArea {
            id: scriptEditorResizeMouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real pressSceneX: 0
            property real pressWidth: 0
            property bool dragMoved: false

            onPressed: function(mouse) {
                var scenePoint = mapToItem(null, mouse.x, mouse.y)
                pressSceneX = scenePoint.x
                pressWidth = root.width
                dragMoved = false
                root.resizeDragActive = true
                mouse.accepted = true
            }

            onPositionChanged: function(mouse) {
                if (!pressed)
                    return
                var scenePoint = mapToItem(null, mouse.x, mouse.y)
                // The panel is anchored to the right edge, so dragging the left
                // handle leftwards (decreasing scene x) widens the panel.
                dragMoved = true
                root.panelWidth = root.clampPanelWidth(pressWidth - (scenePoint.x - pressSceneX))
            }

            onReleased: {
                root.resizeDragActive = false
                if (dragMoved && root.scriptEditorBridgeRef)
                    root.scriptEditorBridgeRef.set_width(root.panelWidth)
            }

            onCanceled: root.resizeDragActive = false
        }
    }
}
