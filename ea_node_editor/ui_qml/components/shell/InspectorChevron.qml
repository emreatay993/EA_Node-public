import QtQuick 2.15

Item {
    id: chevron
    property bool open: false
    property color strokeColor: "#d0d5de"
    property int glyphSize: 10
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null

    implicitWidth: glyphSize
    implicitHeight: glyphSize
    width: implicitWidth
    height: implicitHeight

    Image {
        id: glyph
        anchors.centerIn: parent
        sourceSize.width: chevron.glyphSize
        sourceSize.height: chevron.glyphSize
        width: chevron.glyphSize
        height: chevron.glyphSize
        smooth: true
        source: chevron.uiIconsRef ? chevron.uiIconsRef.sourceSized("chevron-down", chevron.glyphSize, String(chevron.strokeColor)) : ""
        rotation: chevron.open ? 0 : -90
        transformOrigin: Item.Center

        Behavior on rotation {
            NumberAnimation { duration: 100 }
        }
    }
}
