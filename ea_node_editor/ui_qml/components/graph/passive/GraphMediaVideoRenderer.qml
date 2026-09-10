// Purpose: Render inline video playback and controls for Media Panel.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
// Landmarks: media lifecycle; inline controls; bookmark and clip helpers; action dispatch.
import QtQuick 2.15
import ".." as GraphShared
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtMultimedia
import "../surface_controls" as GraphSurfaceControls
import "../surface_controls/SurfaceControlGeometry.js" as SurfaceControlGeometry
import "GraphMediaPanelSourceUtils.js" as GraphMediaPanelSourceUtils

GraphShared.GraphSurfaceBase {
    id: surface
    objectName: "graphNodeMediaVideoRenderer"
    property var sourceResolution: ({})
    property bool rendererReleased: false
    property bool resumeAfterSeek: false
    property alias initialPositionApplied: playback.initialPositionApplied
    property bool artifactRenameReleaseActive: false
    property var artifactRenameReleaseState: ({})
    property int artifactRenameResolveGeneration: 0
    readonly property string sourcePath: String(sourceResolution.source_ref || "")
    readonly property bool sourceInputExposed: Boolean(sourceResolution.input_exposed)
    readonly property string normalizedFitMode: playback.normalizedFitMode(propValue("fit_mode"))
    readonly property bool autoPlayEnabled: propBool("auto_play", false)
    readonly property bool loopEnabled: propBool("loop", false)
    readonly property bool muted: propBool("muted", false)
    readonly property real volume: _boundedNumber("volume", 1.0, 0.0, 1.0)
    readonly property real playbackRate: _boundedNumber("playback_rate", 1.0, 0.25, 4.0)
    readonly property int storedPositionMs: Math.max(0, Math.round(propNumber("position_ms", 0)))
    readonly property var timelineBookmarks: playback.normalizedTimelineBookmarks(propRaw("timeline_bookmarks", []))
    readonly property bool clipEnabled: propBool("clip_enabled", false)
    readonly property int clipStartMs: Math.max(0, Math.round(propNumber("clip_start_ms", 0)))
    readonly property int clipEndMs: Math.max(0, Math.round(propNumber("clip_end_ms", 0)))
    readonly property bool clipRangeActive: clipEnabled && clipEndMs > clipStartMs
    readonly property bool validSourceActive: resolvedSourceUrl.length > 0
    readonly property string resolvedSourceUrl: rendererReleased
        ? ""
        : String(sourceResolution.resolved_source_url || "")
    readonly property string effectiveResolvedSourceUrl: artifactRenameReleaseActive ? "" : resolvedSourceUrl
    readonly property bool localSourceActive: GraphMediaPanelSourceUtils.resolvedLocalFileSourceUrl(
        effectiveResolvedSourceUrl
    ).length > 0
    readonly property var fullscreenBridgeRef: typeof contentFullscreenBridge !== "undefined" && contentFullscreenBridge
        ? contentFullscreenBridge
        : null
    readonly property bool fullscreenOwnsPlayback: fullscreenBridgeRef
        && Boolean(fullscreenBridgeRef.open)
        && String(fullscreenBridgeRef.content_kind || "") === "media"
        && fullscreenBridgeRef.media_payload
        && String(fullscreenBridgeRef.media_payload.media_kind || "") === "video"
        && host
        && host.nodeData
        && String(fullscreenBridgeRef.node_id || "") === String(host.nodeData.node_id || "")
    readonly property bool hostPlaybackAllowed: !fullscreenOwnsPlayback
    readonly property real contentInset: host ? Number(host.surfaceMetrics.body_bottom_margin || 12) : 12
    readonly property real contentLeftMargin: surfaceShowFrame ? (host ? Number(host.surfaceMetrics.body_left_margin || 14) : 14) : 0
    readonly property real contentRightMargin: surfaceShowFrame ? (host ? Number(host.surfaceMetrics.body_right_margin || 14) : 14) : 0
    readonly property real contentTopMargin: {
        if (!host)
            return surfaceShowTitle ? 44 : (surfaceShowFrame ? contentInset : 0);
        if (!surfaceShowTitle)
            return surfaceShowFrame ? contentInset : 0;
        return Number(host.surfaceMetrics.body_top || 44);
    }
    readonly property real contentBottomMargin: host ? surfaceBodyBottomMargin : (surfaceShowFrame ? 12 : 0)
    readonly property string statusText: _statusText()
    readonly property string previewState: {
        if (String(sourceResolution.state || "") !== "ready" || resolvedSourceUrl.length === 0)
            return "error";
        if (playback.mediaPlayer.error !== MediaPlayer.NoError
                || playback.mediaPlayer.mediaStatus === MediaPlayer.InvalidMedia)
            return "error";
        if (playback.mediaPlayer.mediaStatus === MediaPlayer.LoadingMedia
                || playback.mediaPlayer.mediaStatus === MediaPlayer.BufferingMedia
                || playback.mediaPlayer.mediaStatus === MediaPlayer.StalledMedia)
            return "loading";
        if (playback.readyOrPlaying)
            return "ready";
        return "placeholder";
    }
    readonly property bool blocksHostInteraction: seekSlider.pressed
    readonly property bool aspectRatioLocked: false
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
        [
            seekRegion.embeddedInteractiveRects
        ]
    )
    readonly property var surfaceActions: {
        var actions = [];
        if (validSourceActive) {
            actions.push({
                "id": "playPause",
                "label": playback.mediaPlayer.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play",
                "icon": playback.mediaPlayer.playbackState === MediaPlayer.PlayingState ? "pause" : "run",
                "kind": "media",
                "enabled": true,
                "primary": playback.mediaPlayer.playbackState !== MediaPlayer.PlayingState
            });
            actions.push({
                "id": "rewindToStart",
                "label": "Rewind",
                "icon": "video-rewind",
                "kind": "media",
                "enabled": true,
                "primary": false
            });
            actions.push({
                "id": "seekBack10",
                "label": "Back 10s",
                "icon": "video-seek-back-10",
                "kind": "media",
                "enabled": true,
                "primary": false
            });
            actions.push({
                "id": "seekForward10",
                "label": "Forward 10s",
                "icon": "video-seek-forward-10",
                "kind": "media",
                "enabled": true,
                "primary": false
            });
            actions.push({
                "id": "loop",
                "label": loopEnabled ? "Disable loop" : "Loop",
                "icon": "video-loop",
                "kind": "media",
                "enabled": true,
                "primary": loopEnabled,
                "checked": loopEnabled
            });
            actions.push({
                "id": "bookmarks",
                "label": "Bookmarks",
                "icon": "video-bookmarks",
                "kind": "media",
                "enabled": true,
                "primary": timelineBookmarks.length > 0,
                "checked": timelineBookmarks.length > 0,
                "popover_layout": "video_bookmarks",
                "popoverActions": _bookmarkPopoverActions()
            });
            actions.push({
                "id": "captureFrame",
                "label": "Capture frame",
                "icon": "video-capture-frame",
                "kind": "media",
                "enabled": readyOrPlayingForAction(),
                "primary": false
            });
            actions.push({
                "id": "timestampAnnotation",
                "label": "Timestamp note",
                "icon": "video-timestamp-note",
                "kind": "media",
                "enabled": true,
                "primary": false
            });
            actions.push({
                "id": "clipRange",
                "label": clipRangeActive ? "Clip range" : "Set clip range",
                "icon": "video-clip-range",
                "kind": "media",
                "enabled": true,
                "primary": clipRangeActive,
                "checked": clipRangeActive,
                "popoverActions": _clipPopoverActions()
            });
            actions.push({
                "id": "mute",
                "label": muted ? "Unmute" : "Mute",
                "icon": muted ? "volume-muted" : "volume",
                "kind": "media",
                "enabled": true,
                "primary": muted,
                "checked": muted
            });
            actions.push({
                "id": "fitMode",
                "label": normalizedFitMode === "cover" ? "Fit video" : "Fill video",
                "icon": normalizedFitMode === "cover" ? "video-fit" : "video-fill",
                "kind": "media",
                "enabled": true,
                "primary": normalizedFitMode === "cover",
                "checked": normalizedFitMode === "cover"
            });
        }
        return actions;
    }

    implicitHeight: host ? Number(host.surfaceMetrics.body_height || 0) : 0

    onResolvedSourceUrlChanged: {
        seekSlider.value = 0;
    }

    onStoredPositionMsChanged: {
        if (seekSlider.pressed)
            return;
        if (!initialPositionApplied) {
            _applyInitialPosition();
            return;
        }
        if (Math.abs(playback.positionMs - storedPositionMs) > 250)
            playback.seekTo(storedPositionMs);
    }

    Component.onCompleted: {
        _syncSeekSlider();
    }
    Component.onDestruction: release()

    function release() {
        if (rendererReleased)
            return;
        rendererReleased = true;
        playback.release();
    }

    function fullscreenRuntimeState() {
        return _runtimeState();
    }

    Connections {
        target: host

        function onIsSelectedChanged() {
            if (host && host.isSelected) {
                surface._maybeAutoPlay();
            }
        }
    }

    Connections {
        target: fullscreenBridgeRef

        function onVideoFullscreenClosed(nodeId, state) {
            if (!host || !host.nodeData)
                return;
            if (String(nodeId || "") !== String(host.nodeData.node_id || ""))
                return;
            surface._applyFullscreenReturnState(state || ({}));
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

    GraphMediaVideoPlaybackCore {
        id: playback
        sourceUrl: surface.effectiveResolvedSourceUrl
        sourceEnabled: !surface.fullscreenOwnsPlayback && !surface.rendererReleased
        videoOutput: videoOutput
        playerObjectName: "graphNodeVideoMediaPlayer"
        muted: surface.muted
        volume: surface.volume
        playbackRate: surface.playbackRate
        loopEnabled: surface.loopEnabled
        fitMode: surface.normalizedFitMode
        timelineBookmarks: surface.timelineBookmarks
        clipEnabled: surface.clipEnabled
        clipStartMs: surface.clipStartMs
        clipEndMs: surface.clipEndMs
        initialPositionMs: surface.storedPositionMs
        shouldResumePlaying: surface.autoPlayEnabled
        playbackAllowed: surface.hostPlaybackAllowed
        thumbnailPrimingEnabled: !surface.autoPlayEnabled

        onPositionMsChanged: surface._syncSeekSlider()
        onDurationMsChanged: surface._syncSeekSlider()
        onPositionCommitRequested: function(positionMs) {
            if (!surface.rendererReleased && !surface.artifactRenameReleaseActive)
                surface._commitPosition(positionMs);
        }
    }

    Rectangle {
        visible: surface.surfaceShowFrame
        anchors.fill: parent
        radius: host ? Number(host.resolvedCornerRadius || 6) : 6
        color: host ? Qt.darker(host.surfaceColor, 1.03) : "#1b1d22"
        border.width: host ? Number(host.resolvedBorderWidth || 1) : 1
        border.color: host && host.isSelected
            ? host.themeSelectedOutlineColor
            : (host ? Qt.lighter(host.outlineColor, 1.1) : "#4a4f5a")
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: surface.contentLeftMargin
        anchors.rightMargin: surface.contentRightMargin
        anchors.topMargin: surface.contentTopMargin
        anchors.bottomMargin: surface.contentBottomMargin
        spacing: 6

        Rectangle {
            id: viewport
            objectName: "graphNodeVideoViewport"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 132
            radius: 8
            color: host ? Qt.darker(host.inlineInputBackgroundColor, 1.04) : "#202228"
            border.width: 1
            border.color: host ? Qt.alpha(host.inlineInputBorderColor, 0.88) : "#4a4f5a"
            clip: true

            VideoOutput {
                id: videoOutput
                objectName: "graphNodeVideoOutput"
                anchors.fill: parent
                fillMode: surface.normalizedFitMode === "cover"
                    ? VideoOutput.PreserveAspectCrop
                    : VideoOutput.PreserveAspectFit
                visible: surface.resolvedSourceUrl.length > 0
                    && surface.previewState !== "error"
            }

            Text {
                objectName: "graphNodeVideoPlaceholder"
                anchors.centerIn: parent
                width: Math.min(parent.width - 28, 260)
                text: surface.statusText
                color: host ? host.inlineDrivenTextColor : "#bdc5d3"
                font.pixelSize: host ? Number(host.passiveFontPixelSize || 12) : 12
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: surface.previewState !== "ready"
                renderType: host ? host.nodeTextRenderType : Text.CurveRendering
            }
        }

        RowLayout {
            id: controls
            objectName: "graphNodeVideoControls"
            Layout.fillWidth: true
            Layout.preferredHeight: 26
            spacing: 6

            Text {
                objectName: "graphNodeVideoElapsedLabel"
                text: surface._formatTime(seekSlider.value)
                color: host ? host.inlineInputTextColor : "#f0f2f5"
                font.pixelSize: 10
                Layout.preferredWidth: 42
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignVCenter
                renderType: host ? host.nodeTextRenderType : Text.CurveRendering
            }

            Slider {
                id: seekSlider
                objectName: "graphNodeVideoSeekSlider"
                Layout.fillWidth: true
                from: 0
                to: Math.max(1, playback.durationMs)
                enabled: surface.validSourceActive
                live: true

                onPressedChanged: {
                    if (pressed) {
                        surface._beginInlineInteraction();
                        surface.resumeAfterSeek = playback.mediaPlayer.playbackState === MediaPlayer.PlayingState;
                    } else {
                        surface._seekTo(value);
                        if (surface.resumeAfterSeek && surface.hostPlaybackAllowed)
                            playback.mediaPlayer.play();
                        surface.resumeAfterSeek = false;
                        surface._commitPosition(value);
                    }
                }

                onMoved: surface._seekTo(value)

                Repeater {
                    model: surface._seekMarkers()

                    Rectangle {
                        readonly property var marker: modelData || ({})
                        readonly property real markerRatio: {
                        var duration = Math.max(1, playback.durationMs);
                            return Math.max(0.0, Math.min(1.0, Number(marker.position_ms || 0) / duration));
                        }
                        objectName: "graphNodeVideoSeekMarker_" + String(marker.role || "")
                        parent: seekSlider
                        width: String(marker.role || "") === "bookmark" ? 3 : 2
                        height: String(marker.role || "") === "bookmark" ? 12 : 18
                        radius: 1
                        x: Math.round(Math.max(0, Math.min(seekSlider.width - width, 9 + (seekSlider.width - 18) * markerRatio)))
                        y: Math.round((seekSlider.height - height) / 2)
                        color: String(marker.role || "") === "bookmark"
                            ? (host ? host.nodeThemeColor : "#4DA8DA")
                            : "#F2B84B"
                        opacity: seekSlider.enabled ? 0.92 : 0.35
                        z: 10
                    }
                }
            }

            Text {
                objectName: "graphNodeVideoDurationLabel"
                text: playback.formatTime(playback.durationMs)
                color: host ? host.inlineDrivenTextColor : "#bdc5d3"
                font.pixelSize: 10
                Layout.preferredWidth: 42
                verticalAlignment: Text.AlignVCenter
                renderType: host ? host.nodeTextRenderType : Text.CurveRendering
            }
        }
    }

    GraphSurfaceControls.GraphSurfaceInteractiveRegion {
        id: seekRegion
        host: surface.host
        targetItem: seekSlider
        enabled: seekSlider.enabled
        onControlStarted: surface._beginInlineInteraction()
    }





    function _boundedNumber(key, fallback, minimum, maximum) {
        return playback.boundedNumber(propNumber(key, fallback), fallback, minimum, maximum);
    }

    function _readyOrPlayingForAction() {
        return playback.readyOrPlaying;
    }

    function readyOrPlayingForAction() {
        return _readyOrPlayingForAction();
    }

    function _iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, color);
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

    // Position saves can be triggered by blur-pausing playback; avoid the inline
    // property path because it reselects the node as a control interaction.
    function _persistPlaybackPosition(position) {
        if (!host || !host.nodeData)
            return false;
        if (host.graphReadOnly !== undefined && Boolean(host.graphReadOnly))
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var canvasItem = _canvasItem();
        var bridge = canvasItem && canvasItem.sceneCommandBridge
            ? canvasItem.sceneCommandBridge
            : null;
        if (bridge) {
            try {
                if (bridge.set_node_properties)
                    return Boolean(bridge.set_node_properties(nodeId, { "position_ms": position }));
            } catch (error) {
                // Fall back to the single-property slot below.
            }
            try {
                if (bridge.set_node_property) {
                    bridge.set_node_property(nodeId, "position_ms", position);
                    return true;
                }
            } catch (error) {
                return false;
            }
        }
        _commitInlineProperty("position_ms", position);
        return true;
    }

    function _canvasItem() {
        return host && host.canvasItem ? host.canvasItem : null;
    }

    function _canvasCommandBridge() {
        var canvasItem = _canvasItem();
        return canvasItem && canvasItem.canvasCommandBridgeRef
            ? canvasItem.canvasCommandBridgeRef
            : null;
    }

    function _currentPositionMs() {
        return Math.max(0, Math.round(seekSlider.pressed ? seekSlider.value : playback.positionMs));
    }

    function _sidecarScenePoint(verticalOffset) {
        var nodeX = 0;
        var nodeY = 0;
        if (host && host.nodeData) {
            nodeX = Number(host.nodeData.x || 0);
            nodeY = Number(host.nodeData.y || 0);
        }
        var width = host ? Number(host.width || 0) : 0;
        return {
            "x": nodeX + Math.max(width + 28, 260),
            "y": nodeY + Number(verticalOffset || 0)
        };
    }

    function _capturedFrameImageNodeSize() {
        var width = host ? Number(host.width || 0) : 0;
        var height = host ? Number(host.height || 0) : 0;
        return {
            "width": isFinite(width) && width > 0 ? width : 0,
            "height": isFinite(height) && height > 0 ? height : 0
        };
    }

    function _commitTimelineBookmarks(bookmarks) {
        return _commitSurfaceProperties({
            "timeline_bookmarks": playback.normalizedTimelineBookmarks(bookmarks)
        });
    }

    function _bookmarkPopoverActions() {
        var actions = [
            {
                "id": "videoBookmarkAdd",
                "label": "Add " + _formatTime(_currentPositionMs()),
                "icon": "video-bookmark-add",
                "kind": "media",
                "role": "add",
                "enabled": true,
                "close_popover": false
            }
        ];
        for (var index = 0; index < timelineBookmarks.length; index++) {
            var bookmark = timelineBookmarks[index] || {};
            var encodedId = encodeURIComponent(String(bookmark.id || ""));
            actions.push({
                "id": "videoBookmarkJump:" + encodedId,
                "label": String(bookmark.label || ""),
                "icon": "video-bookmark-jump",
                "kind": "media",
                "role": "bookmark",
                "bookmark_id": String(bookmark.id || ""),
                "position_ms": Math.max(0, Math.round(Number(bookmark.position_ms || 0))),
                "time_text": _formatTime(bookmark.position_ms || 0),
                "rename_action_prefix": "videoBookmarkRename:" + encodedId + ":",
                "delete_action_id": "videoBookmarkDelete:" + encodedId,
                "enabled": true,
                "close_popover": false
            });
        }
        return actions;
    }

    function _clipPopoverActions() {
        return [
            {
                "id": "videoClipToggle",
                "label": clipRangeActive ? "Disable range" : "Enable range",
                "icon": "video-clip-range",
                "kind": "media",
                "toolbar_text": clipRangeActive ? "Disable" : "Enable",
                "enabled": clipEndMs > clipStartMs,
                "checked": clipRangeActive,
                "close_popover": false
            },
            {
                "id": "videoClipSetIn",
                "label": "Set in " + _formatTime(_currentPositionMs()),
                "icon": "video-clip-in",
                "kind": "media",
                "toolbar_text": "Set in",
                "enabled": true,
                "close_popover": false
            },
            {
                "id": "videoClipSetOut",
                "label": "Set out " + _formatTime(_currentPositionMs()),
                "icon": "video-clip-out",
                "kind": "media",
                "toolbar_text": "Set out",
                "enabled": true,
                "close_popover": false
            },
            {
                "id": "videoClipReplaceTrimmed",
                "label": "Replace with trimmed video",
                "icon": "video-trim-save",
                "kind": "media",
                "toolbar_text": "Replace",
                "enabled": !sourceInputExposed && localSourceActive && clipRangeActive,
                "close_popover": true
            },
            {
                "id": "videoClipSaveTrimmedCopy",
                "label": "Save trimmed copy",
                "icon": "video-trim-save",
                "kind": "media",
                "toolbar_text": "Copy",
                "enabled": localSourceActive && clipRangeActive,
                "close_popover": true
            },
            {
                "id": "videoClipClear",
                "label": "Clear range",
                "icon": "x",
                "kind": "media",
                "toolbar_text": "Clear",
                "enabled": clipStartMs > 0 || clipEndMs > 0 || clipEnabled,
                "close_popover": true
            }
        ];
    }

    function _addBookmarkAtCurrentPosition() {
        var position = _currentPositionMs();
        return _commitTimelineBookmarks(playback.withBookmarkAdded(position));
    }

    function _bookmarkIndex(bookmarkId) {
        var normalizedId = String(bookmarkId || "");
        return playback.bookmarkIndex(normalizedId);
    }

    function _jumpToBookmark(bookmarkId) {
        var index = _bookmarkIndex(bookmarkId);
        if (index < 0)
            return false;
        _seekTo(timelineBookmarks[index].position_ms || 0);
        _commitPosition(playback.positionMs);
        return true;
    }

    function _deleteBookmark(bookmarkId) {
        return _commitTimelineBookmarks(playback.withBookmarkDeleted(bookmarkId));
    }

    function _renameBookmark(bookmarkId, label) {
        var next = playback.withBookmarkRenamed(bookmarkId, label);
        if (next === null)
            return false;
        return _commitTimelineBookmarks(next);
    }

    function _commitClipProperties(values) {
        return _commitSurfaceProperties(values || ({}));
    }

    function _setClipStartAtCurrentPosition() {
        var position = _currentPositionMs();
        return _commitClipProperties(playback.clipStateWithStart(position));
    }

    function _setClipEndAtCurrentPosition() {
        var position = _currentPositionMs();
        return _commitClipProperties(playback.clipStateWithEnd(position));
    }

    function _toggleClipRange() {
        if (clipEndMs <= clipStartMs)
            return false;
        return _commitClipProperties({ "clip_enabled": !clipRangeActive });
    }

    function _clearClipRange() {
        return _commitClipProperties(playback.clearedClipState());
    }

    function _trimStatePayload() {
        return {
            "source": sourcePath,
            "fit_mode": normalizedFitMode,
            "muted": muted,
            "loop": loopEnabled,
            "volume": volume,
            "playback_rate": playbackRate,
            "timeline_bookmarks": timelineBookmarks,
            "clip_enabled": clipRangeActive,
            "clip_start_ms": clipStartMs,
            "clip_end_ms": clipEndMs
        };
    }

    function _replaceWithTrimmedClip() {
        if (sourceInputExposed || !localSourceActive || !clipRangeActive || !host || !host.nodeData)
            return false;
        var bridge = _canvasCommandBridge();
        if (!bridge || !bridge.request_trim_video_clip_replace)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var result = bridge.request_trim_video_clip_replace(
            nodeId,
            clipStartMs,
            clipEndMs,
            _trimStatePayload()
        );
        return Boolean(result && result.success);
    }

    function _saveTrimmedClipCopy() {
        if (!localSourceActive || !clipRangeActive || !host || !host.nodeData)
            return false;
        var bridge = _canvasCommandBridge();
        if (!bridge || !bridge.request_trim_video_clip_copy)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var point = _sidecarScenePoint(96);
        var result = bridge.request_trim_video_clip_copy(
            nodeId,
            clipStartMs,
            clipEndMs,
            point.x,
            point.y,
            _trimStatePayload()
        );
        return Boolean(result && result.success);
    }

    function _captureFrameToImageNode() {
        if (!validSourceActive || !_readyOrPlayingForAction())
            return false;
        if (!videoOutput || !videoOutput.grabToImage)
            return false;
        var bridge = _canvasCommandBridge();
        if (!bridge || !bridge.video_frame_capture_path || !bridge.request_create_video_frame_image_node)
            return false;
        if (!host || !host.nodeData)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var position = _currentPositionMs();
        var capturePath = String(bridge.video_frame_capture_path(nodeId, position) || "");
        if (!capturePath.length)
            return false;
        var point = _sidecarScenePoint(0);
        var size = _capturedFrameImageNodeSize();
        videoOutput.grabToImage(function(result) {
            if (!result || !result.saveToFile || !result.saveToFile(capturePath))
                return;
            bridge.request_create_video_frame_image_node(
                nodeId,
                capturePath,
                position,
                point.x,
                point.y,
                size.width,
                size.height
            );
        });
        return true;
    }

    function _createTimestampAnnotation() {
        if (!validSourceActive || !host || !host.nodeData)
            return false;
        var bridge = _canvasCommandBridge();
        if (!bridge || !bridge.request_create_video_timestamp_annotation)
            return false;
        var nodeId = String(host.nodeData.node_id || "");
        if (!nodeId.length)
            return false;
        var point = _sidecarScenePoint(72);
        var result = bridge.request_create_video_timestamp_annotation(nodeId, _currentPositionMs(), point.x, point.y);
        return Boolean(result && result.success);
    }

    function _statusText() {
        if (sourcePath.trim().length === 0)
            return "Choose a local video file to preview it here.";
        if (playback.mediaPlayer.error !== MediaPlayer.NoError)
            return playback.mediaPlayer.errorString && playback.mediaPlayer.errorString.length > 0
                ? playback.mediaPlayer.errorString
                : "Video could not be loaded.";
        if (playback.mediaPlayer.mediaStatus === MediaPlayer.InvalidMedia)
            return "Video could not be loaded.";
        if (previewState === "loading")
            return "Loading video...";
        return "";
    }

    function _applyInitialPosition() {
        playback.applyInitialPosition();
        _syncSeekSlider();
    }

    function _maybeAutoPlay() {
        playback.maybeResumePlaying();
    }

    // A play-button click selects the node, but host.isSelected can lag until
    // after this action handler returns.
    function _explicitPlaybackStartAllowed() {
        if (fullscreenOwnsPlayback)
            return false;
        if (hostPlaybackAllowed)
            return true;
        return !!(host && host.nodeData);
    }

    function togglePlayback() {
        if (!validSourceActive || artifactRenameReleaseActive)
            return false;
        _beginInlineInteraction();
        if (playback.mediaPlayer.playbackState === MediaPlayer.PlayingState) {
            playback.mediaPlayer.pause();
            _commitPosition(playback.positionMs);
            return true;
        }
        if (!_explicitPlaybackStartAllowed())
            return false;
        return playback.togglePlayback();
    }

    function _seekTo(positionMs) {
        var target = playback.seekTo(positionMs);
        seekSlider.value = target;
        return target;
    }

    function seekBy(deltaMs) {
        if (!validSourceActive)
            return false;
        _beginInlineInteraction();
        playback.seekBy(deltaMs);
        _syncSeekSlider();
        _commitPosition(playback.positionMs);
        return true;
    }

    function rewindToStart() {
        if (!validSourceActive)
            return false;
        _beginInlineInteraction();
        playback.rewindToStart();
        _syncSeekSlider();
        _commitPosition(playback.positionMs);
        return true;
    }

    function _syncSeekSlider() {
        if (seekSlider.pressed)
            return;
        seekSlider.to = Math.max(1, playback.durationMs);
        seekSlider.value = playback.positionMs;
    }

    function _seekMarkers() {
        return playback.seekMarkers();
    }

    function _commitPosition(positionMs) {
        var position = Math.max(0, Math.round(Number(positionMs || 0)));
        if (position !== storedPositionMs)
            return _persistPlaybackPosition(position);
        return false;
    }

    function _runtimeState() {
        return playback.currentState(
            seekSlider.pressed ? seekSlider.value : playback.positionMs,
            surface.volume
        );
    }

    function _isManagedArtifactRenameTarget(nodeId) {
        return !!(host && host.nodeData)
            && String(nodeId || "") === String(host.nodeData.node_id || "");
    }

    function _releaseForManagedArtifactRename(nodeId) {
        if (!_isManagedArtifactRenameTarget(nodeId))
            return;
        artifactRenameReleaseState = _runtimeState();
        artifactRenameReleaseActive = true;
    }

    function _restoreAfterManagedArtifactRename(nodeId) {
        if (!_isManagedArtifactRenameTarget(nodeId) || !artifactRenameReleaseActive)
            return;
        var state = artifactRenameReleaseState || ({});
        artifactRenameResolveGeneration += 1;
        artifactRenameReleaseActive = false;
        Qt.callLater(function() {
            if (!surface.artifactRenameReleaseActive)
                surface._applyFullscreenReturnState(state);
        });
    }

    function _applyFullscreenReturnState(state) {
        var payload = state || ({});
        if (artifactRenameReleaseActive) {
            artifactRenameReleaseState = payload;
            return;
        }
        playback.restoreState(payload);
    }

    function _formatTime(positionMs) {
        return playback.formatTime(positionMs);
    }

    function dispatchSurfaceAction(actionId) {
        var normalized = String(actionId || "");
        _beginInlineInteraction();
        if (normalized === "playPause")
            return togglePlayback();
        if (normalized === "rewindToStart")
            return rewindToStart();
        if (normalized === "seekBack10")
            return seekBy(-10000);
        if (normalized === "seekForward10")
            return seekBy(10000);
        if (normalized === "videoBookmarkAdd")
            return _addBookmarkAtCurrentPosition();
        if (normalized.indexOf("videoBookmarkJump:") === 0)
            return _jumpToBookmark(decodeURIComponent(normalized.slice("videoBookmarkJump:".length)));
        if (normalized.indexOf("videoBookmarkDelete:") === 0)
            return _deleteBookmark(decodeURIComponent(normalized.slice("videoBookmarkDelete:".length)));
        if (normalized.indexOf("videoBookmarkRename:") === 0) {
            var renamePayload = normalized.slice("videoBookmarkRename:".length);
            var splitAt = renamePayload.indexOf(":");
            if (splitAt < 0)
                return false;
            return _renameBookmark(
                decodeURIComponent(renamePayload.slice(0, splitAt)),
                decodeURIComponent(renamePayload.slice(splitAt + 1))
            );
        }
        if (normalized === "videoClipToggle")
            return _toggleClipRange();
        if (normalized === "videoClipSetIn")
            return _setClipStartAtCurrentPosition();
        if (normalized === "videoClipSetOut")
            return _setClipEndAtCurrentPosition();
        if (normalized === "videoClipReplaceTrimmed")
            return _replaceWithTrimmedClip();
        if (normalized === "videoClipSaveTrimmedCopy")
            return _saveTrimmedClipCopy();
        if (normalized === "videoClipClear")
            return _clearClipRange();
        if (normalized === "captureFrame")
            return _captureFrameToImageNode();
        if (normalized === "timestampAnnotation")
            return _createTimestampAnnotation();
        if (normalized === "mute") {
            if (!validSourceActive)
                return false;
            _commitInlineProperty("muted", !muted);
            return true;
        }
        if (normalized === "loop") {
            if (!validSourceActive)
                return false;
            _commitInlineProperty("loop", !loopEnabled);
            return true;
        }
        if (normalized === "fitMode") {
            if (!validSourceActive)
                return false;
            _commitInlineProperty(
                "fit_mode",
                normalizedFitMode === "cover" ? "contain" : "cover"
            );
            return true;
        }
        return false;
    }
}
