import QtQuick 2.15
import "GraphMediaPanelSourceUtils.js" as SourceUtils
import "../surface_controls" as GraphSurfaceControls

Rectangle {
    id: root
    objectName: "graphNodeWebBoardPreviewViewport"
    property var surface: null
    readonly property var previewRef: surface && surface.previewRef ? surface.previewRef : ({})
    readonly property string snapshotStatus: String(previewRef.status || "")
    readonly property bool snapshotCurrent: Boolean(previewRef.current) && snapshotStatus === "ready"
    readonly property string previewSourceRef: snapshotCurrent ? String(previewRef.uri || previewRef.artifact_ref || "") : ""
    readonly property string previewImageSource: previewSourceRef.length > 0
        ? SourceUtils.previewSourceUrl(previewSourceRef) : ""
    readonly property bool exportedPreviewLoaded: snapshotCurrent && previewImage.status === Image.Ready
    readonly property string previewMode: {
        if (snapshotStatus === "updating" || (snapshotCurrent && previewImage.status === Image.Loading))
            return "updating";
        if (snapshotStatus === "error") return "error";
        if (surface && surface.boardElementCount === 0) return "empty";
        return exportedPreviewLoaded ? "image" : "error";
    }
    readonly property var embeddedInteractiveRects: retryButton.visible ? retryButton.embeddedInteractiveRects : []

    radius: 8
    color: surface ? surface.viewportFillColor : "#202228"
    border.width: 1
    border.color: Qt.alpha(surface ? surface.panelBorderColor : "#4a4f5a", 0.86)
    clip: true

    Image {
        id: previewImage
        objectName: "graphNodeWebBoardExportedPreviewImage"
        anchors.fill: parent
        anchors.margins: 4
        visible: root.previewMode === "image"
        source: root.previewImageSource
        sourceSize.width: 2048
        sourceSize.height: 2048
        fillMode: Image.PreserveAspectFit
        smooth: true
        asynchronous: true
        cache: false
    }

    Column {
        objectName: "graphNodeWebBoardSnapshotState"
        anchors.centerIn: parent
        width: Math.max(0, Math.min(parent.width - 24, 270))
        spacing: 8
        visible: root.previewMode !== "image"

        Text {
            objectName: "graphNodeWebBoardSnapshotTitle"
            width: parent.width
            text: root.previewMode === "empty" ? "Empty board"
                : root.previewMode === "updating" ? "Updating preview..." : "Preview unavailable"
            horizontalAlignment: Text.AlignHCenter
            color: root.surface ? root.surface.captionTextColor : "#f0f2f5"
            font.pixelSize: 13
            font.bold: true
            wrapMode: Text.WordWrap
        }

        Text {
            objectName: "graphNodeWebBoardSnapshotDetail"
            width: parent.width
            text: root.previewMode === "empty" ? "Open the editor to start drawing."
                : root.previewMode === "updating" ? "The latest drawing is being saved."
                : "Open the editor to regenerate the preview."
            horizontalAlignment: Text.AlignHCenter
            color: root.surface ? root.surface.hintTextColor : "#bdc5d3"
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }

        GraphSurfaceControls.GraphSurfaceButton {
            id: retryButton
            objectName: "graphNodeWebBoardRetryButton"
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(implicitWidth, parent.width)
            host: root.surface ? root.surface.host : null
            visible: root.previewMode === "error"
            enabled: root.surface && root.surface.fullscreenAvailable
            text: "Open editor to retry"
            onClicked: root.surface._requestContentFullscreen()
        }
    }
}
