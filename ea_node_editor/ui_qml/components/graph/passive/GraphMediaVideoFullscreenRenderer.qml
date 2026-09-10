// Purpose: Render fullscreen video playback and controls for Media Panel.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtMultimedia
import "../../shell" as ShellComponents
import "../../common/TooltipCopy.js" as TooltipCopy
import "GraphMediaPanelSourceUtils.js" as GraphMediaPanelSourceUtils

FocusScope {
    id: root
    objectName: "contentFullscreenVideoSurface"
    property var payload: ({})
    property var bridgeRef: null
    property var themePalette: ({})
    property bool resumeAfterSeek: false
    property alias mutedValue: playback.muted
    property alias volumeValue: playback.volume
    property alias playbackRateValue: playback.playbackRate
    property alias loopValue: playback.loopEnabled
    property alias fitModeValue: playback.fitMode
    property alias timelineBookmarksValue: playback.timelineBookmarks
    property alias clipEnabledValue: playback.clipEnabled
    property alias clipStartValue: playback.clipStartMs
    property alias clipEndValue: playback.clipEndMs
    property string activeSourceIdentity: ""
    property bool rendererReleased: false
    readonly property var transientState: payload && payload.transient_state ? payload.transient_state : ({})
    readonly property bool videoPayloadActive: String(payload && payload.media_kind || "") === "video"
    readonly property bool sourceInputExposed: Boolean(payload && payload.input_exposed)
    readonly property string sourceUrl: videoPayloadActive && !rendererReleased
        ? String(payload && payload.resolved_source_url || "")
        : ""
    readonly property bool localSourceActive: GraphMediaPanelSourceUtils.resolvedLocalFileSourceUrl(
        sourceUrl
    ).length > 0
    readonly property int initialPositionMs: Math.max(
        0,
        Math.round(Number(transientState.position_ms !== undefined
            ? transientState.position_ms
            : (payload ? payload.position_ms || 0 : 0)))
    )
    readonly property bool shouldResumePlaying: transientState.playing !== undefined
        ? Boolean(transientState.playing)
        : Boolean(payload && payload.auto_play)
    readonly property bool readyOrPlaying: playback.readyOrPlaying
    readonly property bool errorActive: playback.errorActive
    readonly property bool clipRangeActive: playback.clipRangeActive
    readonly property string statusText: _statusText()

    focus: visible
    activeFocusOnTab: visible

    onVisibleChanged: {
        if (visible) {
            _syncFromPayload();
            Qt.callLater(function() {
                if (root.visible)
                    root.forceActiveFocus();
            });
        }
    }

    onPayloadChanged: _syncFromPayload()
    Component.onDestruction: release()

    function release() {
        if (rendererReleased)
            return;
        rendererReleased = true;
        playback.release();
    }

    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Space) {
            togglePlayback();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Left) {
            seekBy(-10000);
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Right) {
            seekBy(10000);
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_M) {
            mutedValue = !mutedValue;
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_Escape || event.key === Qt.Key_F11) {
            requestCloseWithState();
            event.accepted = true;
        }
    }

    GraphMediaVideoPlaybackCore {
        id: playback
        sourceUrl: root.sourceUrl
        sourceEnabled: root.visible && !root.rendererReleased
        videoOutput: videoOutput
        playerObjectName: "contentFullscreenVideoMediaPlayer"
        initialPositionMs: root.initialPositionMs
        shouldResumePlaying: root.shouldResumePlaying
        playbackAllowed: true
        thumbnailPrimingEnabled: root.initialPositionMs <= 0
            && !root.shouldResumePlaying

        onPositionMsChanged: root._syncSeekSlider()
        onDurationMsChanged: root._syncSeekSlider()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            id: viewport
            objectName: "contentFullscreenVideoViewport"
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 6
            color: root.themePalette.input_bg || "#111418"
            border.width: 1
            border.color: root.themePalette.input_border || "#4a4f5a"
            clip: true

            VideoOutput {
                id: videoOutput
                objectName: "contentFullscreenVideoOutput"
                anchors.fill: parent
                fillMode: root.fitModeValue === "cover"
                    ? VideoOutput.PreserveAspectCrop
                    : VideoOutput.PreserveAspectFit
                visible: playback.sourceActive && !root.errorActive
            }

            Text {
                objectName: "contentFullscreenVideoPlaceholder"
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 520)
                text: root.statusText
                visible: root.errorActive || !root.readyOrPlaying
                color: root.themePalette.muted_fg || "#bdc5d3"
                font.pixelSize: 13
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }

        ColumnLayout {
            id: controls
            objectName: "contentFullscreenVideoControls"
            Layout.fillWidth: true
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    objectName: "contentFullscreenVideoElapsedLabel"
                    text: playback.formatTime(seekSlider.value)
                    color: root.themePalette.panel_fg || "#f0f2f5"
                    font.pixelSize: 11
                    Layout.preferredWidth: 54
                    horizontalAlignment: Text.AlignRight
                    verticalAlignment: Text.AlignVCenter
                }

                Slider {
                    id: seekSlider
                    objectName: "contentFullscreenVideoSeekSlider"
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, playback.durationMs)
                    enabled: root.sourceUrl.length > 0 && !root.errorActive
                    live: true
                    onPressedChanged: {
                        if (pressed) {
                            root.resumeAfterSeek = playback.mediaPlayer.playbackState === MediaPlayer.PlayingState;
                        } else {
                            root._seekTo(value);
                            if (root.resumeAfterSeek)
                                playback.mediaPlayer.play();
                            root.resumeAfterSeek = false;
                        }
                    }
                    onMoved: root._seekTo(value)

                    Repeater {
                        model: playback.seekMarkers()

                        Rectangle {
                            readonly property var marker: modelData || ({})
                            readonly property real markerRatio: {
                                var duration = Math.max(1, playback.durationMs);
                                return Math.max(0.0, Math.min(1.0, Number(marker.position_ms || 0) / duration));
                            }
                            objectName: "contentFullscreenVideoSeekMarker_" + String(marker.role || "")
                            parent: seekSlider
                            width: String(marker.role || "") === "bookmark" ? 3 : 2
                            height: String(marker.role || "") === "bookmark" ? 12 : 18
                            radius: 1
                            x: Math.round(Math.max(0, Math.min(seekSlider.width - width, 9 + (seekSlider.width - 18) * markerRatio)))
                            y: Math.round((seekSlider.height - height) / 2)
                            color: String(marker.role || "") === "bookmark"
                                ? (root.themePalette.accent || "#4DA8DA")
                                : "#F2B84B"
                            opacity: seekSlider.enabled ? 0.92 : 0.35
                            z: 10
                        }
                    }
                }

                Text {
                    objectName: "contentFullscreenVideoDurationLabel"
                    text: playback.formatTime(playback.durationMs)
                    color: root.themePalette.muted_fg || "#bdc5d3"
                    font.pixelSize: 11
                    Layout.preferredWidth: 54
                    verticalAlignment: Text.AlignVCenter
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                ShellComponents.ShellButton {
                    id: playButton
                    objectName: "contentFullscreenVideoPlayButton"
                    iconName: playback.mediaPlayer.playbackState === MediaPlayer.PlayingState ? "pause" : "run"
                    tooltipText: playback.mediaPlayer.playbackState === MediaPlayer.PlayingState
                        ? TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.pause")
                        : TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.play")
                    enabled: root.sourceUrl.length > 0 && !root.errorActive
                    onClicked: root.togglePlayback()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoRewindButton"
                    iconName: "video-rewind"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.rewind_start")
                    enabled: playButton.enabled
                    onClicked: root.rewindToStart()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoBackButton"
                    iconName: "video-seek-back-10"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.seek_back_10")
                    enabled: playButton.enabled
                    onClicked: root.seekBy(-10000)
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoForwardButton"
                    iconName: "video-seek-forward-10"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.seek_forward_10")
                    enabled: playButton.enabled
                    onClicked: root.seekBy(10000)
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoLoopButton"
                    iconName: "video-loop"
                    tooltipText: root.loopValue
                        ? TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.disable_loop")
                        : TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.loop")
                    selectedStyle: root.loopValue
                    enabled: playButton.enabled
                    onClicked: root.loopValue = !root.loopValue
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoMuteButton"
                    iconName: root.mutedValue ? "volume-muted" : "volume"
                    tooltipText: root.mutedValue
                        ? TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.unmute")
                        : TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.mute")
                    enabled: playButton.enabled
                    onClicked: root.mutedValue = !root.mutedValue
                }

                Slider {
                    id: volumeSlider
                    objectName: "contentFullscreenVideoVolumeSlider"
                    Layout.preferredWidth: 96
                    from: 0
                    to: 1
                    stepSize: 0.05
                    value: root.volumeValue
                    enabled: playButton.enabled
                    onPressedChanged: {
                        if (!pressed)
                            root.volumeValue = Math.max(0, Math.min(1, value));
                    }
                }

                ComboBox {
                    id: rateCombo
                    objectName: "contentFullscreenVideoRateCombo"
                    Layout.preferredWidth: 82
                    model: ["0.5x", "1x", "1.25x", "1.5x", "2x"]
                    currentIndex: playback.rateIndex(root.playbackRateValue)
                    enabled: playButton.enabled
                    onActivated: root.playbackRateValue = playback.rateForIndex(index)
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoFitButton"
                    iconName: root.fitModeValue === "cover" ? "video-fit" : "video-fill"
                    tooltipText: root.fitModeValue === "cover"
                        ? TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.fit_video")
                        : TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.fill_video")
                    selectedStyle: root.fitModeValue === "cover"
                    onClicked: root.fitModeValue = root.fitModeValue === "cover" ? "contain" : "cover"
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoAddBookmarkButton"
                    iconName: "video-bookmark-add"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.add_bookmark")
                    enabled: playButton.enabled
                    selectedStyle: root.timelineBookmarksValue.length > 0
                    onClicked: root._addBookmarkAtCurrentPosition()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoClipInButton"
                    iconName: "video-clip-in"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.set_clip_in")
                    enabled: playButton.enabled
                    selectedStyle: root.clipRangeActive
                    onClicked: root._setClipStartAtCurrentPosition()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoClipOutButton"
                    iconName: "video-clip-out"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.set_clip_out")
                    enabled: playButton.enabled
                    selectedStyle: root.clipRangeActive
                    onClicked: root._setClipEndAtCurrentPosition()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoTrimReplaceButton"
                    iconName: "video-trim-save"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.replace_trimmed_video")
                    enabled: playButton.enabled && !root.sourceInputExposed && root.localSourceActive && root.clipRangeActive
                    selectedStyle: false
                    onClicked: root._replaceWithTrimmedClip()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoTrimCopyButton"
                    iconName: "video-trim-save"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.save_trimmed_copy")
                    enabled: playButton.enabled && root.localSourceActive && root.clipRangeActive
                    selectedStyle: false
                    onClicked: root._saveTrimmedClipCopy()
                }

                ShellComponents.ShellButton {
                    objectName: "contentFullscreenVideoClipClearButton"
                    iconName: "x"
                    tooltipText: TooltipCopy.text(tooltipCopyBridge, "fullscreen.video.clear_clip_range")
                    enabled: playButton.enabled && (root.clipStartValue > 0 || root.clipEndValue > 0 || root.clipEnabledValue)
                    onClicked: root._clearClipRange()
                }

                Item { Layout.fillWidth: true }
            }
        }
    }

    function _syncFromPayload() {
        var source = payload || ({});
        var nextSourceIdentity = String(source.resolved_source_url || "").trim();
        if (activeSourceIdentity.length > 0 && nextSourceIdentity === activeSourceIdentity)
            return;
        activeSourceIdentity = nextSourceIdentity;
        var state = source.transient_state || ({});
        mutedValue = playback.boolValue(state.muted !== undefined ? state.muted : source.muted, false);
        volumeValue = playback.boundedNumber(state.volume !== undefined ? state.volume : source.volume, 1.0, 0.0, 1.0);
        playbackRateValue = playback.boundedNumber(
            state.playback_rate !== undefined ? state.playback_rate : source.playback_rate,
            1.0,
            0.25,
            4.0
        );
        loopValue = playback.boolValue(state.loop !== undefined ? state.loop : source.loop, false);
        fitModeValue = playback.normalizedFitMode(state.fit_mode !== undefined ? state.fit_mode : source.fit_mode);
        timelineBookmarksValue = playback.normalizedTimelineBookmarks(
            state.timeline_bookmarks !== undefined ? state.timeline_bookmarks : source.timeline_bookmarks
        );
        clipEnabledValue = playback.boolValue(
            state.clip_enabled !== undefined ? state.clip_enabled : source.clip_enabled,
            false
        );
        clipStartValue = playback.nonNegativeInt(
            state.clip_start_ms !== undefined ? state.clip_start_ms : source.clip_start_ms
        );
        clipEndValue = playback.nonNegativeInt(
            state.clip_end_ms !== undefined ? state.clip_end_ms : source.clip_end_ms
        );
    }

    function _statusText() {
        if (sourceUrl.length === 0)
            return "Video source is unavailable.";
        if (playback.mediaPlayer.error !== MediaPlayer.NoError)
            return playback.mediaPlayer.errorString && playback.mediaPlayer.errorString.length > 0
                ? playback.mediaPlayer.errorString
                : "Video could not be loaded.";
        if (playback.mediaPlayer.mediaStatus === MediaPlayer.InvalidMedia)
            return "Video could not be loaded.";
        return "Loading video...";
    }

    function togglePlayback() {
        return playback.togglePlayback();
    }

    function _seekTo(positionMs) {
        var target = playback.seekTo(positionMs);
        seekSlider.value = target;
        return target;
    }

    function seekBy(deltaMs) {
        return playback.seekBy(deltaMs);
    }

    function rewindToStart() {
        return playback.rewindToStart();
    }

    function _syncSeekSlider() {
        if (seekSlider.pressed)
            return;
        seekSlider.to = Math.max(1, playback.durationMs);
        seekSlider.value = playback.positionMs;
    }

    function _currentPositionMs() {
        return Math.max(0, Math.round(seekSlider.pressed ? seekSlider.value : playback.positionMs));
    }

    function _addBookmarkAtCurrentPosition() {
        var position = _currentPositionMs();
        timelineBookmarksValue = playback.withBookmarkAdded(position);
    }

    function _setClipStartAtCurrentPosition() {
        var position = _currentPositionMs();
        var state = playback.clipStateWithStart(position);
        clipStartValue = state.clip_start_ms;
        clipEndValue = state.clip_end_ms;
        clipEnabledValue = state.clip_enabled;
    }

    function _setClipEndAtCurrentPosition() {
        var position = _currentPositionMs();
        var state = playback.clipStateWithEnd(position);
        clipStartValue = state.clip_start_ms;
        clipEndValue = state.clip_end_ms;
        clipEnabledValue = state.clip_enabled;
    }

    function _clearClipRange() {
        var state = playback.clearedClipState();
        clipEnabledValue = state.clip_enabled;
        clipStartValue = state.clip_start_ms;
        clipEndValue = state.clip_end_ms;
    }

    function _replaceWithTrimmedClip() {
        if (sourceInputExposed
                || !localSourceActive
                || !bridgeRef
                || !bridgeRef.request_trim_video_clip_replace
                || !clipRangeActive)
            return false;
        var result = bridgeRef.request_trim_video_clip_replace(currentState());
        return Boolean(result && result.success);
    }

    function _saveTrimmedClipCopy() {
        if (!localSourceActive || !bridgeRef || !bridgeRef.request_trim_video_clip_copy || !clipRangeActive)
            return false;
        var result = bridgeRef.request_trim_video_clip_copy(currentState());
        return Boolean(result && result.success);
    }

    function currentState() {
        return playback.currentState(
            seekSlider.pressed ? seekSlider.value : playback.positionMs,
            volumeSlider.pressed ? volumeSlider.value : volumeValue
        );
    }

    function requestCloseWithState() {
        if (bridgeRef && bridgeRef.request_close_with_state)
            return Boolean(bridgeRef.request_close_with_state(currentState()));
        if (bridgeRef && bridgeRef.request_close) {
            bridgeRef.request_close();
            return true;
        }
        return false;
    }

}
