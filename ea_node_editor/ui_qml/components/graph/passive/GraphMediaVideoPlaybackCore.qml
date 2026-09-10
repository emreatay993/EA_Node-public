// Purpose: Own shared Media Panel video playback, seek, clip, bookmark, and frame-primer behavior.
// Map: feature_routes/media_image_video_pdf_refocus.md
// Tests: tests/test_media_panel_qml_surface.py
import QtQuick 2.15
import QtMultimedia

Item {
    id: root
    objectName: "graphMediaVideoPlaybackCore"
    width: 0
    height: 0
    visible: false

    property string sourceUrl: ""
    property bool sourceEnabled: true
    property var videoOutput: null
    property string playerObjectName: ""
    property bool muted: false
    property real volume: 1.0
    property real playbackRate: 1.0
    property bool loopEnabled: false
    property string fitMode: "contain"
    property var timelineBookmarks: []
    property bool clipEnabled: false
    property int clipStartMs: 0
    property int clipEndMs: 0
    property int initialPositionMs: 0
    property bool shouldResumePlaying: false
    property bool playbackAllowed: true
    property bool thumbnailPrimingEnabled: true
    property bool released: false
    property bool initialPositionApplied: false
    property bool clipEnforcing: false
    property bool thumbnailPrimerActive: false
    property bool thumbnailPrimerComplete: false
    property bool thumbnailPrimerPauseCommitGuard: false
    property bool restorePending: false
    property int restorePositionMs: 0
    property bool restorePlaying: false

    readonly property var mediaPlayer: player
    readonly property int positionMs: Math.max(0, Math.round(Number(player.position || 0)))
    readonly property int durationMs: Math.max(0, Math.round(Number(player.duration || 0)))
    readonly property bool sourceActive: !released && sourceEnabled && sourceUrl.length > 0
    readonly property bool clipRangeActive: clipEnabled && clipEndMs > clipStartMs
    readonly property bool readyOrPlaying: player.mediaStatus === MediaPlayer.LoadedMedia
        || player.mediaStatus === MediaPlayer.BufferedMedia
        || player.mediaStatus === MediaPlayer.EndOfMedia
        || player.playbackState === MediaPlayer.PlayingState
        || player.playbackState === MediaPlayer.PausedState
    readonly property bool readyForInitialPosition: player.mediaStatus === MediaPlayer.LoadedMedia
        || player.mediaStatus === MediaPlayer.BufferedMedia
        || player.mediaStatus === MediaPlayer.EndOfMedia
    readonly property bool errorActive: player.error !== MediaPlayer.NoError
        || player.mediaStatus === MediaPlayer.InvalidMedia
        || !sourceActive

    signal positionCommitRequested(int positionMs)

    onSourceUrlChanged: {
        restorePending = false;
        _resetSourceState();
    }
    onSourceEnabledChanged: _resetSourceState()
    onSourceActiveChanged: _scheduleSourceReadiness()
    onInitialPositionMsChanged: {
        if (readyForInitialPosition && !restorePending && Math.abs(positionMs - initialPositionMs) > 250)
            seekTo(initialPositionMs);
    }
    Component.onDestruction: release()

    AudioOutput {
        id: audioOutput
        muted: root.muted || root.thumbnailPrimerActive
        volume: root.volume
    }

    MediaPlayer {
        id: player
        objectName: root.playerObjectName
        source: root.sourceActive ? root.sourceUrl : ""
        audioOutput: audioOutput
        videoOutput: root.videoOutput
        playbackRate: root.playbackRate
        loops: root.loopEnabled && !root.clipRangeActive ? MediaPlayer.Infinite : 1

        onMediaStatusChanged: root._scheduleSourceReadiness()
        onPositionChanged: root.enforceClipRange()
        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState || !root.sourceActive)
                return;
            if (root.thumbnailPrimerActive || root.thumbnailPrimerPauseCommitGuard) {
                root.thumbnailPrimerPauseCommitGuard = false;
                primerPauseGuardTimer.stop();
                return;
            }
            root.positionCommitRequested(root.positionMs);
        }
    }

    Timer {
        id: thumbnailPrimerTimer
        interval: 500
        repeat: false
        onTriggered: root.finishThumbnailPrimer()
    }

    Timer {
        id: primerPauseGuardTimer
        interval: 350
        repeat: false
        onTriggered: root.thumbnailPrimerPauseCommitGuard = false
    }

    function _resetSourceState() {
        initialPositionApplied = false;
        clipEnforcing = false;
        thumbnailPrimerTimer.stop();
        primerPauseGuardTimer.stop();
        thumbnailPrimerActive = false;
        thumbnailPrimerComplete = false;
        thumbnailPrimerPauseCommitGuard = false;
        _scheduleSourceReadiness();
    }

    function _scheduleSourceReadiness() {
        Qt.callLater(function() {
            if (!root.sourceActive)
                return;
            root.applyInitialPosition();
            root.maybeResumePlaying();
            root.primeThumbnailFrame();
        });
    }

    function release() {
        if (released)
            return;
        released = true;
        thumbnailPrimerTimer.stop();
        primerPauseGuardTimer.stop();
        thumbnailPrimerActive = false;
        player.stop();
    }

    function restoreState(state) {
        var payload = state || ({});
        restorePositionMs = nonNegativeInt(
            payload.position_ms !== undefined ? payload.position_ms : payload.position
        );
        restorePlaying = boolValue(payload.playing, false);
        restorePending = true;
        initialPositionApplied = false;
        if (readyForInitialPosition) {
            applyInitialPosition();
            maybeResumePlaying();
            primeThumbnailFrame();
        }
    }

    function _requestedPositionMs() {
        if (restorePending)
            return restorePositionMs;
        if (initialPositionMs > 0)
            return initialPositionMs;
        if (clipRangeActive && clipStartMs > 0)
            return clipStartMs;
        return 1;
    }

    function _requestedPlaying() {
        return restorePending ? restorePlaying : shouldResumePlaying;
    }

    function applyInitialPosition() {
        if (initialPositionApplied || !readyForInitialPosition)
            return;
        seekTo(_requestedPositionMs());
        initialPositionApplied = true;
    }

    function maybeResumePlaying() {
        if (!_requestedPlaying() || !playbackAllowed || !readyOrPlaying || errorActive)
            return;
        if (player.playbackState !== MediaPlayer.PlayingState)
            player.play();
        restorePending = false;
    }

    function primeThumbnailFrame() {
        if (!thumbnailPrimingEnabled || thumbnailPrimerComplete || thumbnailPrimerActive)
            return;
        if (_requestedPlaying() || !playbackAllowed || !readyOrPlaying || errorActive)
            return;
        if (player.playbackState === MediaPlayer.PlayingState)
            return;
        thumbnailPrimerComplete = true;
        thumbnailPrimerActive = true;
        thumbnailPrimerTimer.restart();
        player.play();
    }

    function finishThumbnailPrimer() {
        if (!thumbnailPrimerActive)
            return;
        thumbnailPrimerPauseCommitGuard = true;
        primerPauseGuardTimer.restart();
        player.pause();
        thumbnailPrimerActive = false;
        restorePending = false;
    }

    function togglePlayback() {
        if (!sourceActive || errorActive)
            return false;
        if (player.playbackState === MediaPlayer.PlayingState) {
            player.pause();
            return true;
        }
        if (!playbackAllowed)
            return false;
        player.play();
        restorePending = false;
        return true;
    }

    function seekTo(position) {
        var target = clampedPlaybackPosition(position);
        if (durationMs > 0)
            target = Math.min(target, durationMs);
        player.position = target;
        return target;
    }

    function seekBy(deltaMs) {
        if (!sourceActive)
            return false;
        seekTo(positionMs + Number(deltaMs || 0));
        return true;
    }

    function rewindToStart() {
        if (!sourceActive)
            return false;
        seekTo(0);
        return true;
    }

    function clampedPlaybackPosition(position) {
        var target = nonNegativeInt(position);
        if (durationMs > 0)
            target = Math.min(target, durationMs);
        if (!clipRangeActive)
            return target;
        var start = nonNegativeInt(clipStartMs);
        var end = Math.max(start + 1, nonNegativeInt(clipEndMs));
        if (durationMs > 0)
            end = Math.min(end, durationMs);
        return Math.max(start, Math.min(end, target));
    }

    function enforceClipRange() {
        if (!clipRangeActive || clipEnforcing)
            return;
        var start = nonNegativeInt(clipStartMs);
        var end = Math.max(start + 1, nonNegativeInt(clipEndMs));
        if (durationMs > 0)
            end = Math.min(end, durationMs);
        if (positionMs < start) {
            clipEnforcing = true;
            seekTo(start);
            clipEnforcing = false;
            return;
        }
        if (positionMs >= end) {
            clipEnforcing = true;
            if (loopEnabled && playbackAllowed) {
                seekTo(start);
                player.play();
            } else {
                seekTo(end);
                player.pause();
            }
            clipEnforcing = false;
        }
    }

    function seekMarkers() {
        var markers = [];
        if (clipEndMs > clipStartMs) {
            markers.push({ "role": "clip_start", "position_ms": clipStartMs });
            markers.push({ "role": "clip_end", "position_ms": clipEndMs });
        }
        var bookmarks = normalizedTimelineBookmarks(timelineBookmarks);
        for (var index = 0; index < bookmarks.length; index++) {
            var bookmark = bookmarks[index] || ({});
            markers.push({
                "role": "bookmark",
                "position_ms": nonNegativeInt(bookmark.position_ms),
                "label": String(bookmark.label || "")
            });
        }
        return markers;
    }

    function withBookmarkAdded(position) {
        var normalizedPosition = nonNegativeInt(position);
        var bookmarks = normalizedTimelineBookmarks(timelineBookmarks).slice(0);
        bookmarks.push({
            "id": "bookmark-" + Date.now() + "-" + normalizedPosition,
            "label": formatTime(normalizedPosition),
            "position_ms": normalizedPosition
        });
        return normalizedTimelineBookmarks(bookmarks);
    }

    function bookmarkIndex(bookmarkId) {
        var normalizedId = String(bookmarkId || "");
        var bookmarks = normalizedTimelineBookmarks(timelineBookmarks);
        for (var index = 0; index < bookmarks.length; index++) {
            if (String((bookmarks[index] || {}).id || "") === normalizedId)
                return index;
        }
        return -1;
    }

    function withBookmarkDeleted(bookmarkId) {
        var normalizedId = String(bookmarkId || "");
        return normalizedTimelineBookmarks(timelineBookmarks).filter(function(bookmark) {
            return String((bookmark || {}).id || "") !== normalizedId;
        });
    }

    function withBookmarkRenamed(bookmarkId, label) {
        var normalizedId = String(bookmarkId || "");
        var nextLabel = String(label || "").trim().slice(0, 80);
        if (!nextLabel.length)
            return null;
        return normalizedTimelineBookmarks(timelineBookmarks).map(function(bookmark) {
            if (String((bookmark || {}).id || "") !== normalizedId)
                return bookmark;
            return {
                "id": String(bookmark.id || ""),
                "label": nextLabel,
                "position_ms": root.nonNegativeInt(bookmark.position_ms)
            };
        });
    }

    function clipStateWithStart(position) {
        var start = nonNegativeInt(position);
        var end = nonNegativeInt(clipEndMs);
        if (end <= start)
            end = Math.max(start + 1000, durationMs);
        return { "clip_enabled": true, "clip_start_ms": start, "clip_end_ms": end };
    }

    function clipStateWithEnd(position) {
        var end = nonNegativeInt(position);
        var start = nonNegativeInt(clipStartMs);
        if (end <= start)
            start = Math.max(0, end - 1000);
        return { "clip_enabled": true, "clip_start_ms": start, "clip_end_ms": Math.max(start + 1, end) };
    }

    function clearedClipState() {
        return { "clip_enabled": false, "clip_start_ms": 0, "clip_end_ms": 0 };
    }

    function currentState(positionOverride, volumeOverride) {
        return {
            "position_ms": nonNegativeInt(positionOverride !== undefined ? positionOverride : positionMs),
            "playing": player.playbackState === MediaPlayer.PlayingState,
            "muted": muted,
            "volume": boundedNumber(volumeOverride !== undefined ? volumeOverride : volume, 1.0, 0.0, 1.0),
            "playback_rate": boundedNumber(playbackRate, 1.0, 0.25, 4.0),
            "loop": loopEnabled,
            "fit_mode": normalizedFitMode(fitMode),
            "timeline_bookmarks": normalizedTimelineBookmarks(timelineBookmarks),
            "clip_enabled": clipRangeActive,
            "clip_start_ms": nonNegativeInt(clipStartMs),
            "clip_end_ms": nonNegativeInt(clipEndMs)
        };
    }

    function boolValue(value, fallback) {
        if (typeof value === "boolean")
            return value;
        if (value === undefined || value === null)
            return Boolean(fallback);
        if (typeof value === "number")
            return value !== 0;
        var normalized = String(value).trim().toLowerCase();
        if (normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on")
            return true;
        if (normalized === "false" || normalized === "0" || normalized === "no" || normalized === "off")
            return false;
        return Boolean(fallback);
    }

    function boundedNumber(value, fallback, minimum, maximum) {
        var numeric = typeof value === "boolean" ? Number(fallback) : Number(value);
        if (!isFinite(numeric))
            numeric = Number(fallback);
        return Math.max(minimum, Math.min(maximum, numeric));
    }

    function nonNegativeInt(value) {
        if (typeof value === "boolean")
            return 0;
        var numeric = Number(value);
        if (!isFinite(numeric))
            return 0;
        return Math.max(0, Math.floor(numeric));
    }

    function normalizedFitMode(value) {
        return String(value || "").trim().toLowerCase() === "cover" ? "cover" : "contain";
    }

    function normalizedTimelineBookmarks(value) {
        var source = [];
        if (Array.isArray(value))
            source = value;
        else if (value && value.length !== undefined) {
            for (var sourceIndex = 0; sourceIndex < value.length; sourceIndex++)
                source.push(value[sourceIndex]);
        }
        var bookmarks = [];
        var seen = {};
        for (var index = 0; index < source.length; index++) {
            var item = source[index];
            if (!item || typeof item !== "object")
                continue;
            var position = nonNegativeInt(item.position_ms);
            var bookmarkId = String(item.id || "").trim() || "bookmark-" + position + "-" + index;
            if (seen[bookmarkId])
                continue;
            seen[bookmarkId] = true;
            var label = String(item.label || "").trim() || formatTime(position);
            bookmarks.push({ "id": bookmarkId, "label": label.slice(0, 80), "position_ms": position });
        }
        bookmarks.sort(function(left, right) {
            if (left.position_ms !== right.position_ms)
                return left.position_ms - right.position_ms;
            var labelOrder = String(left.label || "").toLowerCase().localeCompare(String(right.label || "").toLowerCase());
            return labelOrder !== 0 ? labelOrder : String(left.id || "").localeCompare(String(right.id || ""));
        });
        return bookmarks.slice(0, 200);
    }

    function rateIndex(rate) {
        var value = Number(rate || 1.0);
        if (value <= 0.75)
            return 0;
        if (value <= 1.125)
            return 1;
        if (value <= 1.375)
            return 2;
        if (value <= 1.75)
            return 3;
        return 4;
    }

    function rateForIndex(index) {
        var rates = [0.5, 1.0, 1.25, 1.5, 2.0];
        return rates[Math.max(0, Math.min(rates.length - 1, Number(index || 0)))];
    }

    function formatTime(position) {
        var totalSeconds = Math.floor(nonNegativeInt(position) / 1000);
        var hours = Math.floor(totalSeconds / 3600);
        var minutes = Math.floor((totalSeconds % 3600) / 60);
        var seconds = totalSeconds % 60;
        var secondText = seconds < 10 ? "0" + seconds : "" + seconds;
        if (hours > 0)
            return hours + ":" + (minutes < 10 ? "0" + minutes : "" + minutes) + ":" + secondText;
        return minutes + ":" + secondText;
    }
}
