// Purpose: Render image and animated-image behavior for Media Panel.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
// Landmarks: source resolution and actions; crop helpers; preview viewport and crop overlay.
import QtQuick 2.15
import ".." as GraphShared
import QtQuick.Controls 2.15
import "../surface_controls" as GraphSurfaceControls
import "../surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "GraphMediaPanelGeometry.js" as GraphMediaPanelGeometry

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeMediaImageRenderer"
    property var sourceResolution: ({})
    property bool rendererReleased: false
    property bool cropModeActive: false
    property real draftCropX: 0.0
    property real draftCropY: 0.0
    property real draftCropW: 1.0
    property real draftCropH: 1.0
    property string hoveredCropHandle: ""
    property string activeCropHandle: ""
    readonly property bool blocksHostInteraction: cropModeActive
    readonly property var renderQuality: host && host.renderQuality
        ? host.renderQuality
        : ({
            "supported_quality_tiers": ["full"]
        })
    readonly property string requestedQualityTier: host ? String(host.requestedQualityTier || "full") : "full"
    readonly property string resolvedQualityTier: host ? String(host.resolvedQualityTier || "full") : "full"
    readonly property bool proxySurfaceRequested: host ? Boolean(host.proxySurfaceRequested) : false
    readonly property bool imageTitleVisible: surfaceShowTitle
    readonly property bool imageFrameVisible: surfaceShowFrame
    readonly property bool imageContentOnlyActive: surfaceContentOnly
    readonly property bool sourceInputExposed: Boolean(sourceResolution.input_exposed)
    readonly property string normalizedFitMode: _normalizedFitMode()
    property var imagePreviewInfo: ({})
    property string _imagePreviewSignature: ""
    property bool _imagePreviewRefreshQueued: false
    property bool artifactRenameReleaseActive: false
    property int artifactRenameResolveGeneration: 0
    readonly property string resolvedSourceUrl: rendererReleased
        ? ""
        : String(sourceResolution.resolved_source_url || "")
    readonly property string previewSourceUrl: rendererReleased
        ? ""
        : String(sourceResolution.preview_source_url || "")
    readonly property bool imageIsAnimated: Boolean(imagePreviewInfo.is_animated)
    readonly property bool imageAnimationSupported: imageIsAnimated
        && Boolean(imagePreviewInfo.animation_supported)
    readonly property string animatedSourceUrl: artifactRenameReleaseActive
        ? ""
        : String(imagePreviewInfo.resolved_source_url || "")
    readonly property string animationPlaybackMode: _normalizedAnimationPlaybackMode(
        propValue("animation_playback_mode")
    )
    readonly property bool animationAutoplayEnabled: host && host.prefs
        && host.prefs.mediaPanelAutoplayAnimations !== undefined
        ? Boolean(host.prefs.mediaPanelAutoplayAnimations)
        : true
    readonly property bool animationModePermitsPlayback: animationPlaybackMode === "play"
        || (animationPlaybackMode === "auto" && animationAutoplayEnabled)
    readonly property bool animationInteractionActive: !!host && (host.isSelected || host.hoverActive)
    readonly property var fullscreenBridgeRef: typeof contentFullscreenBridge !== "undefined" && contentFullscreenBridge
        ? contentFullscreenBridge
        : null
    readonly property bool fullscreenOwnsPlayback: fullscreenBridgeRef
        && Boolean(fullscreenBridgeRef.open)
        && String(fullscreenBridgeRef.content_kind || "") === "media"
        && fullscreenBridgeRef.media_payload
        && String(fullscreenBridgeRef.media_payload.media_kind || "") === "image"
        && host
        && host.nodeData
        && String(fullscreenBridgeRef.node_id || "") === String(host.nodeData.node_id || "")
    readonly property bool animationShouldPlay: imageAnimationSupported
        && previewState === "ready"
        && animatedSourceUrl.length > 0
        && host
        && host.inVisibleViewport
        && animationInteractionActive
        && animationModePermitsPlayback
        && !proxySurfaceActive
        && !cropModeActive
        && !fullscreenOwnsPlayback
        && !artifactRenameReleaseActive
    readonly property string previewState: {
        var imageState = String(sourceResolution.state || "");
        if (imageState !== "ready")
            return "error";
        if (previewSourceUrl.length === 0)
            return "error";
        if (previewViewport.previewImageStatus === Image.Error)
            return "error";
        if (previewViewport.previewImageStatus === Image.Ready)
            return "ready";
        return "placeholder";
    }
    readonly property bool proxySurfaceActive: proxySurfaceRequested
        && previewState === "ready"
        && !cropModeActive
    readonly property string appliedFitMode: normalizedFitMode
    readonly property bool originalModeActive: normalizedFitMode === "original"
    readonly property real sourcePixelWidth: Number(previewViewport.sourcePixelWidth || 0)
    readonly property real sourcePixelHeight: Number(previewViewport.sourcePixelHeight || 0)
    readonly property bool animationObjectLoaded: previewViewport.animationObjectLoaded
    readonly property bool animationPlaying: previewViewport.animationPlaying
    readonly property int animationCurrentFrame: previewViewport.animationCurrentFrame
    readonly property int animationFrameCount: previewViewport.animationFrameCount
    readonly property var normalizedStoredCropRect: _normalizedStoredCropRect()
    readonly property var normalizedDraftCropRect: _normalizedDraftCropRect()
    readonly property int appliedImageRotationDegrees: _normalizedImageRotationDegrees()
    readonly property int appliedImageRotationQuarterTurns: Math.floor(appliedImageRotationDegrees / 90)
    readonly property bool appliedImageMirrorHorizontal: propBool("mirror_horizontal", false)
    readonly property bool appliedImageMirrorVertical: propBool("mirror_vertical", false)
    readonly property bool imageAspectRatioLocked: propBool("lock_aspect_ratio", false)
    readonly property bool aspectRatioLocked: imageAspectRatioLocked
    readonly property bool imageTransformAvailable: previewState === "ready"
        && !cropModeActive
    readonly property bool hasEffectiveCrop: !GraphMediaPanelGeometry.isFullCropRect(normalizedStoredCropRect)
    readonly property bool hasEffectiveDraftCrop: !GraphMediaPanelGeometry.isFullCropRect(normalizedDraftCropRect)
    readonly property rect appliedSourceClipRect: _sourceClipRectFromNormalized(normalizedStoredCropRect)
    readonly property real appliedClipX: Number(appliedSourceClipRect.x || 0)
    readonly property real appliedClipY: Number(appliedSourceClipRect.y || 0)
    readonly property real appliedClipWidth: Number(appliedSourceClipRect.width || 0)
    readonly property real appliedClipHeight: Number(appliedSourceClipRect.height || 0)
    readonly property bool cropToolAvailable: !proxySurfaceActive
        && previewState === "ready"
        && sourcePixelWidth > 0
        && sourcePixelHeight > 0
    readonly property bool cropButtonVisible: cropToolAvailable
        && !cropModeActive
        && (host ? host.hoverActive : false)
    readonly property var cropDisplayRect: previewViewport.cropDisplayRect
    readonly property var draftDisplayCropRect: previewViewport.draftDisplayCropRect
    readonly property real effectivePreviewSourceWidth: Number(previewViewport.effectivePreviewSourceWidth || 0)
    readonly property real effectivePreviewSourceHeight: Number(previewViewport.effectivePreviewSourceHeight || 0)
    readonly property var appliedPreviewRect: previewViewport.appliedPreviewRect
    readonly property real appliedPreviewScale: Number(previewViewport.appliedPreviewScale || 0)
    readonly property real appliedFullImageWidth: Number(previewViewport.appliedFullImageWidth || 0)
    readonly property real appliedFullImageHeight: Number(previewViewport.appliedFullImageHeight || 0)
    readonly property real appliedImageOffsetX: Number(previewViewport.appliedImageOffsetX || 0)
    readonly property real appliedImageOffsetY: Number(previewViewport.appliedImageOffsetY || 0)
    readonly property var overlayViewportRect: previewViewport.overlayViewportRect
    readonly property var overlayContentRect: previewViewport.overlayContentRect
    readonly property var overlaySourceClipRect: previewViewport.overlaySourceClipRect
    readonly property string overlayPreviewKind: previewViewport.overlayPreviewKind
    readonly property bool overlayPreviewVisible: previewViewport.overlayPreviewVisible
    readonly property string previewHintText: {
        return previewState === "error"
            ? "Unable to load the current image preview. Use Repair file... to relink it."
            : "Choose a local image file to preview it here.";
    }
    readonly property color panelFillColor: host && host.hasPassiveFillOverride
        ? host.surfaceColor
        : Qt.darker(host ? host.surfaceColor : "#1b1d22", 1.03)
    readonly property color panelBorderColor: host && host.isSelected
        ? host.themeSelectedOutlineColor
        : (host && host.hasPassiveBorderOverride
            ? host.outlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a"))
    readonly property color viewportFillColor: host
        ? Qt.darker(host.inlineInputBackgroundColor, 1.02)
        : "#202228"
    readonly property color hintTextColor: host ? host.inlineDrivenTextColor : "#bdc5d3"
    readonly property color captionTextColor: host ? host.inlineInputTextColor : "#f0f2f5"
    readonly property real contentInset: host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14
    readonly property real contentLeftMargin: imageFrameVisible ? (host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14) : 0
    readonly property real contentRightMargin: imageFrameVisible ? (host ? Number(host.surfaceMetrics.body_right_margin || 14) : 14) : 0
    readonly property real contentTopMargin: {
        if (!host)
            return imageTitleVisible ? 44 : (imageFrameVisible ? contentInset : 0);
        if (!imageTitleVisible)
            return imageFrameVisible ? contentInset : 0;
        return Number(host.surfaceMetrics.body_top || 44);
    }
    readonly property real contentBottomMargin: host ? surfaceBodyBottomMargin : (imageFrameVisible ? 12 : 0)
    readonly property color cropOverlayShadeColor: Qt.alpha("#11151A", 0.44)
    readonly property color cropFrameColor: host ? host.selectedOutlineColor : "#60CDFF"
    readonly property color cropHandleFillColor: host ? host.surfaceColor : "#1b1d22"
    readonly property color cropHandleBorderColor: host ? host.selectedOutlineColor : "#60CDFF"
    readonly property color cropButtonIconColor: host ? host.headerTextColor : "#f0f2f5"
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
        [
            previewViewport.embeddedInteractiveRects
        ]
    )
    readonly property var surfaceActions: {
        var actions = [];
        if (imageAnimationSupported) {
                actions.push({
                    "id": "animationPlayback",
                    "label": "Animation playback",
                    "icon": animationPlaybackMode === "pause" ? "pause" : "run",
                    "kind": "media",
                    "enabled": previewState === "ready" && !cropModeActive && !fullscreenOwnsPlayback,
                    "checked": animationShouldPlay,
                    "primary": false,
                    "popover_layout": "row",
                    "popoverActions": [
                        {
                            "id": "animationPlaybackAuto",
                            "label": "Auto",
                            "toolbar_text": "Auto",
                            "icon": "run",
                            "kind": "media",
                            "checked": animationPlaybackMode === "auto",
                            "close_popover": true
                        },
                        {
                            "id": "animationPlaybackPlay",
                            "label": "Play",
                            "toolbar_text": "Play",
                            "icon": "run",
                            "kind": "media",
                            "checked": animationPlaybackMode === "play",
                            "close_popover": true
                        },
                        {
                            "id": "animationPlaybackPause",
                            "label": "Pause",
                            "toolbar_text": "Pause",
                            "icon": "pause",
                            "kind": "media",
                            "checked": animationPlaybackMode === "pause",
                            "close_popover": true
                        }
                    ]
                });
        }
            actions.push({
                "id": "crop",
                "label": "Crop",
                "icon": "crop",
                "kind": "media",
                "enabled": cropToolAvailable && !cropModeActive,
                "primary": cropModeActive
            });
            actions.push({
                "id": "save_crop_image",
                "label": "Save crop",
                "icon": "crop",
                "kind": "media",
                "enabled": !sourceInputExposed && cropToolAvailable && hasEffectiveCrop && !cropModeActive,
                "primary": hasEffectiveCrop
            });
            actions.push({
                "id": "lock_aspect_ratio",
                "label": "Lock aspect ratio",
                "icon": "lock",
                "kind": "media",
                "enabled": !cropModeActive,
                "primary": imageAspectRatioLocked,
                "checked": imageAspectRatioLocked
            });
            actions.push({
                "id": "rotate_clockwise",
                "label": "Rotate clockwise",
                "icon": "rotate-clockwise",
                "kind": "media",
                "enabled": imageTransformAvailable,
                "primary": appliedImageRotationDegrees !== 0,
                "checked": appliedImageRotationDegrees !== 0
            });
            actions.push({
                "id": "mirror_horizontal",
                "label": "Mirror horizontal",
                "icon": "flip-horizontal",
                "kind": "media",
                "enabled": imageTransformAvailable,
                "primary": appliedImageMirrorHorizontal,
                "checked": appliedImageMirrorHorizontal
            });
            actions.push({
                "id": "mirror_vertical",
                "label": "Mirror vertical",
                "icon": "flip-vertical",
                "kind": "media",
                "enabled": imageTransformAvailable,
                "primary": appliedImageMirrorVertical,
                "checked": appliedImageMirrorVertical
            });
        return actions;
    }
    readonly property real cropHandleSize: 12
    readonly property real cropHandleHitSlop: 8
    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    onCropToolAvailableChanged: {
        if (!cropToolAvailable && cropModeActive) {
            _cancelCropEdit();
            return;
        }
        if (cropToolAvailable)
            _tryConsumePendingSurfaceAction();
        _syncCropCursor();
    }

    onCropModeActiveChanged: _syncCropCursor()
    onHoveredCropHandleChanged: _syncCropCursor()
    onActiveCropHandleChanged: _syncCropCursor()

    onResolvedSourceUrlChanged: {
        if (cropModeActive)
            _cancelCropEdit();
        _queueImagePreviewRefresh();
        _syncCropCursor();
    }

    Component.onCompleted: {
        _queueImagePreviewRefresh();
        _tryConsumePendingSurfaceAction();
        _syncCropCursor();
    }

    Component.onDestruction: release()

    function release() {
        rendererReleased = true;
        _clearGraphCursorShape();
    }

    Connections {
        target: host

        function onIsSelectedChanged() {
            if (host && host.isSelected)
                surface._tryConsumePendingSurfaceAction();
        }

        function onCanvasItemChanged() {
            surface._queueImagePreviewRefresh();
        }

        function onNodeDataChanged() {
            surface._queueImagePreviewRefresh();
        }

    }

    Connections {
        target: surface._canvasCommandBridge()

        function onManagedArtifactRenameReleaseRequested(nodeId) {
            surface._releaseForManagedArtifactRename(nodeId);
        }

        function onManagedArtifactRenameReleaseFinished(nodeId) {
            surface._restoreAfterManagedArtifactRename(nodeId);
        }
    }

    function _tryConsumePendingSurfaceAction() {
        if (!cropToolAvailable || cropModeActive)
            return;
        var nodeId = host && host.nodeData ? String(host.nodeData.node_id || "") : "";
        var canvasItem = _canvasItem();
        if (nodeId.length > 0
                && canvasItem
                && canvasItem.consumePendingNodeSurfaceAction
                && canvasItem.consumePendingNodeSurfaceAction(nodeId)) {
            _loadDraftFromStoredCrop();
            cropModeActive = true;
        }
    }

    function _canvasItem() {
        return host && host.canvasItem ? host.canvasItem : null;
    }




    function _beginInlineInteraction() {
        if (host && host.nodeData)
            host.surfaceControlInteractionStarted(String(host.nodeData.node_id || ""));
    }

    function _commitInlineProperty(key, value) {
        if (host && host.nodeData)
            host.inlinePropertyCommitted(String(host.nodeData.node_id || ""), key, value);
    }

    function _commitSurfaceProperties(values) {
        if (!host || !host.nodeData)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var payload = values || ({});
        var canvasItem = _canvasItem();
        if (canvasItem && canvasItem.commitNodeSurfaceProperties) {
            if (canvasItem.commitNodeSurfaceProperties(nodeId, payload))
                return true;
        }
        var changed = false;
        for (var key in payload) {
            if (!Object.prototype.hasOwnProperty.call(payload, key))
                continue;
            _commitInlineProperty(key, payload[key]);
            changed = true;
        }
        return changed;
    }

    function _normalizedFitMode() {
        var value = propValue("fit_mode").trim().toLowerCase();
        if (value === "cover" || value === "original")
            return value;
        return "contain";
    }

    function _normalizedAnimationPlaybackMode(value) {
        var normalized = String(value || "auto").trim().toLowerCase();
        if (normalized === "play" || normalized === "pause")
            return normalized;
        return "auto";
    }

    function _normalizedStoredCropRect() {
        return GraphMediaPanelGeometry.normalizedCropRect(
            propNumber("crop_x", 0.0),
            propNumber("crop_y", 0.0),
            propNumber("crop_w", 1.0),
            propNumber("crop_h", 1.0)
        );
    }

    function _normalizedDraftCropRect() {
        return GraphMediaPanelGeometry.normalizedCropRect(
            draftCropX,
            draftCropY,
            draftCropW,
            draftCropH
        );
    }

    function _normalizedImageRotationDegrees() {
        var degrees = Number(propRaw("rotation_degrees", 0));
        if (!isFinite(degrees))
            return 0;
        degrees = Math.round(degrees);
        degrees = ((degrees % 360) + 360) % 360;
        return degrees % 90 === 0 ? degrees : 0;
    }

    function _sourceClipRectFromNormalized(rect) {
        return GraphMediaPanelGeometry.sourceClipRectFromNormalized(
            rect,
            sourcePixelWidth,
            sourcePixelHeight
        );
    }

    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
    }

    function _setDraftCropRect(rect) {
        draftCropX = Number(rect.x || 0);
        draftCropY = Number(rect.y || 0);
        draftCropW = Number(rect.width || 1);
        draftCropH = Number(rect.height || 1);
    }

    function _setGraphCursorShape(cursorShape) {
        var canvasItem = _canvasItem();
        if (!canvasItem || !canvasItem.setNodeSurfaceCursorShape)
            return false;
        return Boolean(canvasItem.setNodeSurfaceCursorShape(cursorShape));
    }

    function _clearGraphCursorShape() {
        var canvasItem = _canvasItem();
        if (!canvasItem || !canvasItem.clearNodeSurfaceCursorShape)
            return false;
        return Boolean(canvasItem.clearNodeSurfaceCursorShape());
    }

    function _canvasCommandBridge() {
        var canvasItem = _canvasItem();
        return canvasItem && canvasItem.sceneCommandBridge
            ? canvasItem.sceneCommandBridge
            : null;
    }

    function _loadDraftFromStoredCrop() {
        _setDraftCropRect(normalizedStoredCropRect);
    }

    function _beginCropEdit() {
        if (!cropToolAvailable)
            return;
        var nodeId = host && host.nodeData ? String(host.nodeData.node_id || "") : "";
        var canvasItem = _canvasItem();
        if (canvasItem && canvasItem.requestNodeSurfaceCropEdit && nodeId.length > 0) {
            if (!canvasItem.requestNodeSurfaceCropEdit(nodeId))
                return;
        } else if (host && !host.isSelected) {
            return;
        }
        _loadDraftFromStoredCrop();
        cropModeActive = true;
    }

    function _cancelCropEdit() {
        cropModeActive = false;
        hoveredCropHandle = "";
        activeCropHandle = "";
        _loadDraftFromStoredCrop();
    }

    function _applyCropEdit() {
        var rect = GraphMediaPanelGeometry.normalizedCropRect(
            draftCropX,
            draftCropY,
            draftCropW,
            draftCropH
        );
        var canvasItem = _canvasItem();
        if (canvasItem && canvasItem.commitNodeSurfaceProperties && host && host.nodeData) {
            var applied = canvasItem.commitNodeSurfaceProperties(
                String(host.nodeData.node_id || ""),
                {
                    "crop_x": rect.x,
                    "crop_y": rect.y,
                    "crop_w": rect.width,
                    "crop_h": rect.height
                }
            );
            if (!applied && !GraphMediaPanelGeometry.cropRectsEqual(rect, normalizedStoredCropRect))
                return;
        }
        cropModeActive = false;
        hoveredCropHandle = "";
        activeCropHandle = "";
        _setDraftCropRect(rect);
    }

    function _resetCropEditAfterSourceBake() {
        cropModeActive = false;
        hoveredCropHandle = "";
        activeCropHandle = "";
        _setDraftCropRect({
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0
        });
    }

    function _saveCropImage(cropRect) {
        if (sourceInputExposed || !cropToolAvailable || !host || !host.nodeData)
            return false;
        var rect = GraphMediaPanelGeometry.normalizedCropRect(
            Number(cropRect.x || 0),
            Number(cropRect.y || 0),
            Number(cropRect.width || 1),
            Number(cropRect.height || 1)
        );
        if (GraphMediaPanelGeometry.isFullCropRect(rect))
            return false;
        var bridge = _canvasCommandBridge();
        if (!bridge || !bridge.request_save_image_crop_replace)
            return false;
        var result = bridge.request_save_image_crop_replace(
            String(host.nodeData.node_id || ""),
            {
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height
            }
        );
        if (!Boolean(result && result.success))
            return false;
        _resetCropEditAfterSourceBake();
        return true;
    }

    function triggerHoverAction() {
        _beginCropEdit();
    }

    function _rotateImageClockwise() {
        if (!imageTransformAvailable)
            return false;
        return _commitSurfaceProperties({
            "rotation_degrees": (appliedImageRotationDegrees + 90) % 360
        });
    }

    function _toggleImageMirrorHorizontal() {
        if (!imageTransformAvailable)
            return false;
        return _commitSurfaceProperties({
            "mirror_horizontal": !appliedImageMirrorHorizontal
        });
    }

    function _toggleImageMirrorVertical() {
        if (!imageTransformAvailable)
            return false;
        return _commitSurfaceProperties({
            "mirror_vertical": !appliedImageMirrorVertical
        });
    }

    function _toggleImageAspectRatioLock() {
        if (cropModeActive)
            return false;
        return _commitSurfaceProperties({
            "lock_aspect_ratio": !imageAspectRatioLocked
        });
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        _beginInlineInteraction();
        if (normalized === "crop") {
            _beginCropEdit();
            return cropModeActive;
        }
        if (normalized === "save_crop_image")
            return _saveCropImage(normalizedStoredCropRect);
        if (normalized === "lock_aspect_ratio")
            return _toggleImageAspectRatioLock();
        if (normalized === "rotate_clockwise")
            return _rotateImageClockwise();
        if (normalized === "mirror_horizontal")
            return _toggleImageMirrorHorizontal();
        if (normalized === "mirror_vertical")
            return _toggleImageMirrorVertical();
        if (normalized === "animationPlaybackAuto")
            return _commitSurfaceProperties({"animation_playback_mode": "auto"});
        if (normalized === "animationPlaybackPlay")
            return _commitSurfaceProperties({"animation_playback_mode": "play"});
        if (normalized === "animationPlaybackPause")
            return _commitSurfaceProperties({"animation_playback_mode": "pause"});
        return false;
    }

    function _updateDraftFromHandle(handle, deltaPixelsX, deltaPixelsY, startX, startY, startW, startH) {
        _setDraftCropRect(
            GraphMediaPanelGeometry.updatedDraftCropRect(
                handle,
                deltaPixelsX,
                deltaPixelsY,
                startX,
                startY,
                startW,
                startH,
                cropDisplayRect,
                sourcePixelWidth,
                sourcePixelHeight
            )
        );
    }

    function _handleCursorShape(handle) {
        return GraphMediaPanelGeometry.handleCursorShape(handle);
    }

    function _resolvedCropCursorShape() {
        var handle = activeCropHandle.length > 0 ? activeCropHandle : hoveredCropHandle;
        if (handle.length > 0)
            return _handleCursorShape(handle);
        return Qt.ArrowCursor;
    }

    function _syncCropCursor() {
        if (!cropModeActive || !cropToolAvailable) {
            _clearGraphCursorShape();
            return;
        }
        _setGraphCursorShape(_resolvedCropCursorShape());
    }

    function _handleX(handle, frameRect, handleSize) {
        return GraphMediaPanelGeometry.handleX(handle, frameRect, handleSize);
    }

    function _handleY(handle, frameRect, handleSize) {
        return GraphMediaPanelGeometry.handleY(handle, frameRect, handleSize);
    }

    function _imagePreviewInfoSignature(info) {
        var value = info || ({});
        return [
            String(resolvedSourceUrl || ""),
            String(value.state || ""),
            String(value.resolved_source_url || ""),
            String(value.format || ""),
            String(value.source_pixel_width || 0),
            String(value.source_pixel_height || 0),
            String(value.frame_count || 0),
            String(Boolean(value.is_animated)),
            String(Boolean(value.animation_supported)),
            String(value.file_stamp_token || ""),
            String(value.message || "")
        ].join("\u001f");
    }

    function _applyImagePreviewInfo(info) {
        var value = info || ({});
        var signature = _imagePreviewInfoSignature(value);
        if (signature === _imagePreviewSignature)
            return false;
        _imagePreviewSignature = signature;
        imagePreviewInfo = value;
        return true;
    }

    function _queueImagePreviewRefresh() {
        if (_imagePreviewRefreshQueued)
            return;
        _imagePreviewRefreshQueued = true;
        Qt.callLater(function() {
            surface._imagePreviewRefreshQueued = false;
            surface._refreshImagePreviewInfo();
        });
    }

    function _refreshImagePreviewInfo() {
        return _applyImagePreviewInfo(_describeImagePreview(resolvedSourceUrl));
    }

    function _describeImagePreview(source) {
        var canvasItem = _canvasItem();
        if (canvasItem && canvasItem.describeNodeSurfaceImagePreview) {
            try {
                return canvasItem.describeNodeSurfaceImagePreview(String(source || ""));
            } catch (error) {
            }
        }
        if (host && host.describeImagePreview) {
            try {
                return host.describeImagePreview(String(source || ""));
            } catch (hostError) {
            }
        }
        if (String(sourceResolution.state || "") === "ready") {
            return {
                "state": "ready",
                "message": "",
                "resolved_source_url": resolvedSourceUrl,
                "format": "",
                "source_pixel_width": 0,
                "source_pixel_height": 0,
                "frame_count": 0,
                "is_animated": false,
                "animation_supported": false,
                "file_stamp_token": ""
            };
        }
        return {
            "state": "error",
            "message": "Image preview service unavailable.",
            "resolved_source_url": "",
            "format": "",
            "source_pixel_width": 0,
            "source_pixel_height": 0,
            "frame_count": 0,
            "is_animated": false,
            "animation_supported": false,
            "file_stamp_token": ""
        };
    }

    function _isManagedArtifactRenameTarget(nodeId) {
        return !!(host && host.nodeData)
            && String(nodeId || "") === String(host.nodeData.node_id || "");
    }

    function _releaseForManagedArtifactRename(nodeId) {
        if (!_isManagedArtifactRenameTarget(nodeId))
            return;
        artifactRenameReleaseActive = true;
    }

    function _restoreAfterManagedArtifactRename(nodeId) {
        if (!_isManagedArtifactRenameTarget(nodeId) || !artifactRenameReleaseActive)
            return;
        artifactRenameResolveGeneration += 1;
        artifactRenameReleaseActive = false;
        _imagePreviewSignature = "";
        Qt.callLater(function() {
            if (!surface.artifactRenameReleaseActive)
                surface._queueImagePreviewRefresh();
        });
    }

    Rectangle {
        visible: surface.surfaceShowFrame
        anchors.fill: parent
        radius: host ? Number(host.resolvedCornerRadius || 6) : 6
        color: surface.panelFillColor
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: surface.panelBorderColor
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: surface.contentLeftMargin
        anchors.right: parent.right
        anchors.rightMargin: surface.contentRightMargin
        anchors.top: parent.top
        anchors.topMargin: surface.contentTopMargin
        anchors.bottom: parent.bottom
        anchors.bottomMargin: surface.contentBottomMargin
        spacing: 0

        GraphMediaImageViewport {
            id: previewViewport
            width: parent.width
            height: parent.height
            surface: surface
            overlayInteractiveRects: cropOverlay.embeddedInteractiveRects

            overlayData: [
                Item {
                    id: cropOverlay
                    objectName: "graphNodeMediaCropOverlay"
                    property var handleEmbeddedInteractiveRects: {
                        var frameWidth = Number(surface.draftDisplayCropRect.width || 0);
                        var frameHeight = Number(surface.draftDisplayCropRect.height || 0);
                        if (!(surface.cropModeActive && surface.cropToolAvailable)
                                || !(frameWidth > 0)
                                || !(frameHeight > 0)) {
                            return [];
                        }
                        var rectLists = [];
                        for (var index = 0; index < cropHandleRepeater.count; index++) {
                            var handleItem = cropHandleRepeater.itemAt(index);
                            if (!handleItem || handleItem.embeddedInteractiveRects === undefined || handleItem.embeddedInteractiveRects === null)
                                continue;
                            rectLists.push(handleItem.embeddedInteractiveRects);
                        }
                        return SurfaceControlGeometry.combineRectLists(rectLists);
                    }
                    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
                        [
                            cropApplyButton.embeddedInteractiveRects,
                            cropSaveButton.embeddedInteractiveRects,
                            cropCancelButton.embeddedInteractiveRects,
                            cropOverlay.handleEmbeddedInteractiveRects
                        ]
                    )
                    anchors.fill: parent
                    visible: surface.cropModeActive && surface.cropToolAvailable
                    z: 3

                    HoverHandler {
                        id: cropCursorArea
                        objectName: "graphNodeMediaCropCursorArea"
                        cursorShape: surface._resolvedCropCursorShape()
                    }

                    Image {
                        id: cropEditImage
                        objectName: "graphNodeMediaCropEditImage"
                        x: Number(surface.cropDisplayRect.x || 0)
                        y: Number(surface.cropDisplayRect.y || 0)
                        width: Number(surface.cropDisplayRect.width || 0)
                        height: Number(surface.cropDisplayRect.height || 0)
                        asynchronous: false
                        cache: true
                        mipmap: true
                        fillMode: Image.PreserveAspectFit
                        source: surface.previewSourceUrl
                        visible: parent.visible
                        smooth: true
                    }

                    Rectangle {
                        color: surface.cropOverlayShadeColor
                        x: 0
                        y: 0
                        width: parent.width
                        height: Number(surface.draftDisplayCropRect.y || 0)
                    }

                    Rectangle {
                        color: surface.cropOverlayShadeColor
                        x: 0
                        y: Number(surface.draftDisplayCropRect.y || 0)
                            + Number(surface.draftDisplayCropRect.height || 0)
                        width: parent.width
                        height: Math.max(0, parent.height - y)
                    }

                    Rectangle {
                        color: surface.cropOverlayShadeColor
                        x: 0
                        y: Number(surface.draftDisplayCropRect.y || 0)
                        width: Number(surface.draftDisplayCropRect.x || 0)
                        height: Number(surface.draftDisplayCropRect.height || 0)
                    }

                    Rectangle {
                        color: surface.cropOverlayShadeColor
                        x: Number(surface.draftDisplayCropRect.x || 0)
                            + Number(surface.draftDisplayCropRect.width || 0)
                        y: Number(surface.draftDisplayCropRect.y || 0)
                        width: Math.max(0, parent.width - x)
                        height: Number(surface.draftDisplayCropRect.height || 0)
                    }

                    Rectangle {
                        id: cropFrame
                        objectName: "graphNodeMediaCropFrame"
                        x: Number(surface.draftDisplayCropRect.x || 0)
                        y: Number(surface.draftDisplayCropRect.y || 0)
                        width: Number(surface.draftDisplayCropRect.width || 0)
                        height: Number(surface.draftDisplayCropRect.height || 0)
                        color: "transparent"
                        border.width: 2
                        border.color: surface.cropFrameColor
                    }

                    Repeater {
                        id: cropHandleRepeater
                        model: [
                            "top_left",
                            "top",
                            "top_right",
                            "left",
                            "right",
                            "bottom_left",
                            "bottom",
                            "bottom_right"
                        ]

                        delegate: Rectangle {
                            objectName: "graphNodeMediaCropHandle"
                            property string handleId: String(modelData || "")
                            property real pressGlobalX: 0
                            property real pressGlobalY: 0
                            property real startCropX: 0
                            property real startCropY: 0
                            property real startCropW: 1
                            property real startCropH: 1
                            readonly property var embeddedInteractiveRects: handleInteractiveRegion.embeddedInteractiveRects
                            width: surface.cropHandleSize
                            height: surface.cropHandleSize
                            radius: 3
                            z: 4
                            visible: surface.cropModeActive && surface.cropToolAvailable
                            color: surface.cropHandleFillColor
                            border.width: 2
                            border.color: surface.cropHandleBorderColor
                            x: surface._handleX(handleId, surface.draftDisplayCropRect, width)
                            y: surface._handleY(handleId, surface.draftDisplayCropRect, height)

                            GraphSurfaceControls.GraphSurfaceInteractiveRegion {
                                id: handleInteractiveRegion
                                host: surface.host
                                targetItem: handleMouseArea
                                enabled: parent.visible
                                onControlStarted: surface._beginInlineInteraction()
                            }

                            MouseArea {
                                id: handleMouseArea
                                objectName: "graphNodeMediaCropHandleMouseArea"
                                property string handleId: parent.handleId
                                x: -surface.cropHandleHitSlop
                                y: -surface.cropHandleHitSlop
                                width: parent.width + surface.cropHandleHitSlop * 2
                                height: parent.height + surface.cropHandleHitSlop * 2
                                acceptedButtons: Qt.LeftButton
                                cursorShape: surface._handleCursorShape(handleId)
                                hoverEnabled: true
                                preventStealing: true

                                onEntered: {
                                    surface.hoveredCropHandle = handleId;
                                }

                                onExited: {
                                    if (surface.hoveredCropHandle === handleId)
                                        surface.hoveredCropHandle = "";
                                }

                                onPressed: function(mouse) {
                                    handleInteractiveRegion.beginControl();
                                    surface.activeCropHandle = handleId;
                                    surface.hoveredCropHandle = handleId;
                                    var gp = mapToGlobal(mouse.x, mouse.y);
                                    parent.pressGlobalX = gp.x;
                                    parent.pressGlobalY = gp.y;
                                    parent.startCropX = surface.draftCropX;
                                    parent.startCropY = surface.draftCropY;
                                    parent.startCropW = surface.draftCropW;
                                    parent.startCropH = surface.draftCropH;
                                    mouse.accepted = true;
                                }

                                onPositionChanged: function(mouse) {
                                    if (!pressed)
                                        return;
                                    var gp = mapToGlobal(mouse.x, mouse.y);
                                    surface._updateDraftFromHandle(
                                        handleId,
                                        gp.x - parent.pressGlobalX,
                                        gp.y - parent.pressGlobalY,
                                        parent.startCropX,
                                        parent.startCropY,
                                        parent.startCropW,
                                        parent.startCropH
                                    );
                                }

                                onReleased: function(_mouse) {
                                    if (surface.activeCropHandle === handleId)
                                        surface.activeCropHandle = "";
                                }

                                onCanceled: {
                                    if (surface.activeCropHandle === handleId)
                                        surface.activeCropHandle = "";
                                }
                            }
                        }
                    }

                    Row {
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.topMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        z: 5

                        GraphSurfaceControls.GraphSurfaceButton {
                            id: cropApplyButton
                            objectName: "graphNodeMediaCropApplyButton"
                            host: surface.host
                            visible: surface.cropModeActive && surface.cropToolAvailable
                            enabled: visible
                            text: "Apply"
                            tooltipCategory: "general"
                            foregroundColor: surface.cropButtonIconColor
                            baseFillColor: Qt.alpha(surface.panelFillColor, 0.82)
                            baseBorderColor: Qt.alpha(surface.panelBorderColor, 0.82)
                            onControlStarted: surface._beginInlineInteraction()
                            onClicked: surface._applyCropEdit()
                        }

                        GraphSurfaceControls.GraphSurfaceButton {
                            id: cropSaveButton
                            objectName: "graphNodeMediaCropSaveButton"
                            host: surface.host
                            visible: surface.cropModeActive && surface.cropToolAvailable
                            enabled: visible && !surface.sourceInputExposed && surface.hasEffectiveDraftCrop
                            text: "Save"
                            tooltipCategory: "general"
                            foregroundColor: surface.cropButtonIconColor
                            baseFillColor: Qt.alpha(surface.panelFillColor, 0.82)
                            baseBorderColor: Qt.alpha(surface.panelBorderColor, 0.82)
                            onControlStarted: surface._beginInlineInteraction()
                            onClicked: surface._saveCropImage(surface.normalizedDraftCropRect)
                        }

                        GraphSurfaceControls.GraphSurfaceButton {
                            id: cropCancelButton
                            objectName: "graphNodeMediaCropCancelButton"
                            host: surface.host
                            visible: surface.cropModeActive && surface.cropToolAvailable
                            enabled: visible
                            text: "Cancel"
                            tooltipCategory: "general"
                            foregroundColor: surface.cropButtonIconColor
                            baseFillColor: Qt.alpha(surface.panelFillColor, 0.82)
                            baseBorderColor: Qt.alpha(surface.panelBorderColor, 0.82)
                            onControlStarted: surface._beginInlineInteraction()
                            onClicked: surface._cancelCropEdit()
                        }
                    }
                }
            ]
        }
    }
}
