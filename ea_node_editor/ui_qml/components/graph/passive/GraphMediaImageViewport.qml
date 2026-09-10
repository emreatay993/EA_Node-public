// Purpose: Render static and animated image frames for Media Panel.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15
import "../surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "GraphMediaPanelGeometry.js" as GraphMediaPanelGeometry

Rectangle {
    id: root
    property var surface: null
    property var overlayInteractiveRects: []
    default property alias overlayData: overlayLayer.data
    readonly property int previewImageStatus: root.surface && root.surface.imageAnimationSupported
        ? (root.animatedImageItem ? root.animatedImageItem.status : Image.Loading)
        : sourceImageProbe.status
    readonly property real sourcePixelWidth: !!root.surface
        && root.surface.imageAnimationSupported
        ? Number(root.surface.imagePreviewInfo.source_pixel_width || 0)
        : (!!root.surface
            && sourceImageProbe.status === Image.Ready
            ? Number(sourceImageProbe.implicitWidth || 0)
            : 0)
    readonly property real sourcePixelHeight: !!root.surface
        && root.surface.imageAnimationSupported
        ? Number(root.surface.imagePreviewInfo.source_pixel_height || 0)
        : (!!root.surface
            && sourceImageProbe.status === Image.Ready
            ? Number(sourceImageProbe.implicitHeight || 0)
            : 0)
    readonly property var animatedImageItem: appliedAnimatedImageLoader.item
    readonly property bool animationObjectLoaded: !!root.animatedImageItem
        && root.animatedImageItem.source.toString().length > 0
    readonly property bool animationPlaying: !!root.animatedImageItem && root.animatedImageItem.playing
    readonly property int animationCurrentFrame: root.animatedImageItem
        ? Number(root.animatedImageItem.currentFrame || 0)
        : 0
    readonly property int animationFrameCount: root.animatedImageItem
        ? Number(root.animatedImageItem.frameCount || 0)
        : 0
    readonly property var cropDisplayRect: GraphMediaPanelGeometry.containRect(
        root.width,
        root.height,
        root.sourcePixelWidth,
        root.sourcePixelHeight
    )
    readonly property var draftDisplayCropRect: GraphMediaPanelGeometry.displayCropRect(
        root.surface ? root.surface.draftCropX : 0.0,
        root.surface ? root.surface.draftCropY : 0.0,
        root.surface ? root.surface.draftCropW : 1.0,
        root.surface ? root.surface.draftCropH : 1.0,
        root.cropDisplayRect
    )
    readonly property real effectivePreviewSourceWidth: root.sourcePixelWidth > 0
        ? root.sourcePixelWidth * Number(root.surface ? root.surface.normalizedStoredCropRect.width || 0 : 0)
        : 0
    readonly property real effectivePreviewSourceHeight: root.sourcePixelHeight > 0
        ? root.sourcePixelHeight * Number(root.surface ? root.surface.normalizedStoredCropRect.height || 0 : 0)
        : 0
    readonly property bool appliedRotationSwapsAxes: !!root.surface
        && (Number(root.surface.appliedImageRotationQuarterTurns || 0) % 2) !== 0
    readonly property real transformedPreviewSourceWidth: root.appliedRotationSwapsAxes
        ? root.effectivePreviewSourceHeight
        : root.effectivePreviewSourceWidth
    readonly property real transformedPreviewSourceHeight: root.appliedRotationSwapsAxes
        ? root.effectivePreviewSourceWidth
        : root.effectivePreviewSourceHeight
    readonly property var appliedPreviewRect: GraphMediaPanelGeometry.fitRect(
        root.width,
        root.height,
        root.transformedPreviewSourceWidth,
        root.transformedPreviewSourceHeight,
        root.surface ? root.surface.appliedFitMode : "contain"
    )
    readonly property real appliedPreviewScale: {
        if (!(root.transformedPreviewSourceWidth > 0) || !(root.transformedPreviewSourceHeight > 0))
            return 0.0;
        if (root.surface && root.surface.appliedFitMode === "original")
            return 1.0;
        return Number(root.appliedPreviewRect.width || 0) / root.transformedPreviewSourceWidth;
    }
    readonly property real appliedFullImageWidth: root.sourcePixelWidth > 0
        ? root.sourcePixelWidth * root.appliedPreviewScale
        : 0
    readonly property real appliedFullImageHeight: root.sourcePixelHeight > 0
        ? root.sourcePixelHeight * root.appliedPreviewScale
        : 0
    readonly property real appliedCropFrameWidth: root.effectivePreviewSourceWidth > 0
        ? root.effectivePreviewSourceWidth * root.appliedPreviewScale
        : 0
    readonly property real appliedCropFrameHeight: root.effectivePreviewSourceHeight > 0
        ? root.effectivePreviewSourceHeight * root.appliedPreviewScale
        : 0
    readonly property real appliedImageOffsetX: -Number(
        root.surface ? root.surface.normalizedStoredCropRect.x || 0 : 0
    ) * root.appliedFullImageWidth
    readonly property real appliedImageOffsetY: -Number(
        root.surface ? root.surface.normalizedStoredCropRect.y || 0 : 0
    ) * root.appliedFullImageHeight
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
        [
            root.overlayInteractiveRects
        ]
    )
    readonly property bool proxyPreviewVisible: !!root.surface && Boolean(root.surface.proxySurfaceActive)
    readonly property var overlayViewportRect: Qt.rect(0, 0, root.width, root.height)
    readonly property var overlayContentRect: Qt.rect(
        appliedImageViewport.x,
        appliedImageViewport.y,
        appliedImageViewport.width,
        appliedImageViewport.height
    )
    readonly property var overlaySourceClipRect: root.surface
        ? root.surface.appliedSourceClipRect
        : Qt.rect(0, 0, 0, 0)
    readonly property string overlayPreviewKind: "image"
    readonly property bool overlayPreviewVisible: !!root.surface
        && root.surface.previewState === "ready"
        && !root.surface.cropModeActive
    readonly property bool viewportFrameVisible: !root.surface || Boolean(root.surface.imageFrameVisible)

    objectName: "graphNodeMediaPreviewViewport"
    radius: root.viewportFrameVisible ? 8 : 0
    color: root.viewportFrameVisible
        ? (root.surface ? root.surface.viewportFillColor : "#202228")
        : "transparent"
    border.width: root.viewportFrameVisible ? 1 : 0
    border.color: root.viewportFrameVisible
        ? Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.82)
        : "transparent"
    clip: true

    Item {
        anchors.fill: parent

        Image {
            id: sourceImageProbe
            visible: false
            asynchronous: true
            cache: true
            source: root.surface && root.surface.imageAnimationSupported
                ? ""
                : (root.surface ? root.surface.previewSourceUrl : "")
        }

        Item {
            id: appliedImageViewport
            objectName: "graphNodeMediaAppliedImageViewport"
            x: Number(root.appliedPreviewRect.x || 0)
            y: Number(root.appliedPreviewRect.y || 0)
            width: Math.max(0, Number(root.appliedPreviewRect.width || 0))
            height: Math.max(0, Number(root.appliedPreviewRect.height || 0))
            visible: root.surface
                && root.surface.previewState === "ready"
                && !root.proxyPreviewVisible
                && !root.surface.cropModeActive
            clip: true

            Item {
                id: appliedImageTransformFrame
                objectName: "graphNodeMediaAppliedImageTransformFrame"
                x: (parent.width - width) * 0.5
                y: (parent.height - height) * 0.5
                width: Math.max(0, Number(root.appliedCropFrameWidth || 0))
                height: Math.max(0, Number(root.appliedCropFrameHeight || 0))
                rotation: root.surface ? Number(root.surface.appliedImageRotationDegrees || 0) : 0
                transformOrigin: Item.Center

                Item {
                    id: appliedImageMirrorFrame
                    objectName: "graphNodeMediaAppliedImageMirrorFrame"
                    anchors.fill: parent
                    transform: Scale {
                        origin.x: appliedImageMirrorFrame.width * 0.5
                        origin.y: appliedImageMirrorFrame.height * 0.5
                        xScale: root.surface && root.surface.appliedImageMirrorHorizontal ? -1 : 1
                        yScale: root.surface && root.surface.appliedImageMirrorVertical ? -1 : 1
                    }

                    Image {
                        id: appliedImage
                        objectName: "graphNodeMediaAppliedImage"
                        x: Number(root.appliedImageOffsetX || 0)
                        y: Number(root.appliedImageOffsetY || 0)
                        width: Math.max(0, Number(root.appliedFullImageWidth || 0))
                        height: Math.max(0, Number(root.appliedFullImageHeight || 0))
                        asynchronous: true
                        cache: true
                        mipmap: true
                        fillMode: Image.Stretch
                        source: root.surface && !root.surface.imageAnimationSupported
                            ? root.surface.previewSourceUrl
                            : ""
                        visible: source.toString().length > 0
                        smooth: true
                    }

                    Loader {
                        id: appliedAnimatedImageLoader
                        objectName: "graphNodeMediaAppliedAnimatedImageLoader"
                        anchors.fill: parent
                        active: !!root.surface && root.surface.imageAnimationSupported

                        sourceComponent: AnimatedImage {
                            objectName: "graphNodeMediaAppliedAnimatedImage"
                            x: Number(root.appliedImageOffsetX || 0)
                            y: Number(root.appliedImageOffsetY || 0)
                            width: Math.max(0, Number(root.appliedFullImageWidth || 0))
                            height: Math.max(0, Number(root.appliedFullImageHeight || 0))
                            asynchronous: true
                            cache: false
                            mipmap: true
                            fillMode: Image.Stretch
                            autoTransform: true
                            source: root.surface ? root.surface.animatedSourceUrl : ""
                            playing: !!root.surface && root.surface.animationShouldPlay
                            visible: source.toString().length > 0
                            smooth: true

                            onPlayingChanged: {
                                if (!playing && currentFrame !== 0)
                                    currentFrame = 0;
                            }
                            onSourceChanged: {
                                if (!playing && currentFrame !== 0)
                                    currentFrame = 0;
                            }
                        }
                    }
                }
            }
        }

        Item {
            id: proxyPreview
            objectName: "graphNodeMediaProxyPreview"
            anchors.fill: parent
            visible: root.proxyPreviewVisible

            Rectangle {
                anchors.fill: parent
                radius: 6
                color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.08)
                border.width: 1
                border.color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.38)
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 24, 208)
                spacing: 8

                Item {
                    width: 44
                    height: 44
                    anchors.horizontalCenter: parent.horizontalCenter

                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        color: Qt.alpha(root.surface ? root.surface.panelFillColor : "#1b1d22", 0.82)
                        border.width: 1
                        border.color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.68)
                    }

                    Rectangle {
                        anchors.centerIn: parent
                        width: 20
                        height: 16
                        radius: 3
                        color: "transparent"
                        border.width: 1
                        border.color: Qt.alpha(root.surface ? root.surface.hintTextColor : "#bdc5d3", 0.9)
                    }

                    Rectangle {
                        anchors.centerIn: parent
                        width: 10
                        height: 6
                        radius: 2
                        color: Qt.alpha(root.surface ? root.surface.hintTextColor : "#bdc5d3", 0.65)
                    }

                }

                Text {
                    objectName: "graphNodeMediaProxyPreviewTitle"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    color: root.surface ? root.surface.captionTextColor : "#f0f2f5"
                    font.pixelSize: 12
                    font.bold: true
                    text: "Image proxy preview"
                    renderType: root.surface && root.surface.host
                        ? root.surface.host.nodeTextRenderType
                        : Text.CurveRendering
                }

                Text {
                    objectName: "graphNodeMediaProxyPreviewDetail"
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    color: root.surface ? root.surface.hintTextColor : "#bdc5d3"
                    font.pixelSize: 11
                    text: "Full preview returns automatically after the interaction settles."
                    renderType: root.surface && root.surface.host
                        ? root.surface.host.nodeTextRenderType
                        : Text.CurveRendering
                }
            }
        }

        GraphMediaImagePlaceholder {
            surface: root.surface
        }

        Item {
            id: overlayLayer
            anchors.fill: parent
            z: 3
        }
    }
}
