// Purpose: Show image renderer loading and decode feedback.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15

Column {
    id: root
    property var surface: null
    anchors.centerIn: parent
    width: Math.min(parent.width - 24, 180)
    spacing: 8
    visible: root.surface ? root.surface.previewState !== "ready" : true

    Item {
        width: 42
        height: 42
        anchors.horizontalCenter: parent.horizontalCenter

        Rectangle {
            width: 42
            height: 42
            radius: 8
            color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.1)
            border.width: 1
            border.color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.55)

            Rectangle {
                anchors.centerIn: parent
                width: 22
                height: 16
                radius: 3
                color: "transparent"
                border.width: 1
                border.color: Qt.alpha(root.surface ? root.surface.hintTextColor : "#bdc5d3", 0.9)
            }
        }

    }

    Text {
        objectName: "graphNodeMediaPreviewHint"
        visible: parent.visible
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: root.surface ? root.surface.hintTextColor : "#bdc5d3"
        font.pixelSize: 11
        text: root.surface ? root.surface.previewHintText : ""
        renderType: root.surface && root.surface.host
            ? root.surface.host.nodeTextRenderType
            : Text.CurveRendering
    }
}
