import QtQuick 2.15

Rectangle {
    id: root
    objectName: "graphHintOverlay"
    property var shellLibraryBridgeRef: typeof shellLibraryBridge !== "undefined" ? shellLibraryBridge : null
    property bool graphSearchVisible: false
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})

    visible: root.shellLibraryBridgeRef.graph_hint_visible && !root.graphSearchVisible
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 32
    width: Math.min(parent.width * 0.68, Math.max(260, graphHintText.implicitWidth + 28))
    height: graphHintText.implicitHeight + 14
    radius: 5
    color: Qt.alpha(themePalette.panel_bg, 0.8)
    border.width: 1
    border.color: themePalette.accent
    z: 1080

    Text {
        id: graphHintText
        anchors.centerIn: parent
        width: parent.width - 24
        text: root.shellLibraryBridgeRef.graph_hint_message
        color: root.themePalette.panel_title_fg
        font.pixelSize: 12
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
}
