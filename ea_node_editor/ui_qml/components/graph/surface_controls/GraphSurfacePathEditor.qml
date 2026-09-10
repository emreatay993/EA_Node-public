import QtQuick 2.15
import QtQuick.Layouts 1.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    property Item host: null
    property string propertyKey: ""
    property string committedText: ""
    property bool shortenDisplayPathWhenInactive: false
    property string fieldObjectName: "graphSurfacePathEditorField"
    property string browseButtonObjectName: "graphSurfacePathEditorBrowseButton"
    property string browseButtonText: "Browse"
    property bool browseButtonIconOnly: false
    property string browseButtonIconName: ""
    property int browseButtonIconSize: 14
    property var iconSourceResolver: null
    property var browsePathResolver: null
    property string rawText: String(committedText || "")
    readonly property string text: rawText
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
        [pathField.embeddedInteractiveRects, browseButton.embeddedInteractiveRects]
    )
    readonly property real textFitWidth: {
        var requiredWidth = Number(displayTextMetrics.advanceWidth)
            + Number(pathField.leftPadding)
            + Number(pathField.rightPadding)
            + Number(editorRow.spacing)
            + Number(browseButton.implicitWidth);
        return isFinite(requiredWidth) && requiredWidth > 0.0
            ? Math.ceil(requiredWidth)
            : 0.0;
    }
    implicitWidth: editorRow.implicitWidth
    implicitHeight: editorRow.implicitHeight

    signal controlStarted()
    signal commitRequested(string text)

    function _resolveBrowsePath(currentPath) {
        if (typeof browsePathResolver !== "function")
            return "";
        return String(browsePathResolver(String(currentPath || "")) || "");
    }

    function _shortDisplayPath(pathText) {
        var text = String(pathText || "");
        if (!text.length)
            return "";
        var trimmed = text.replace(/[\\/]+$/, "");
        if (!trimmed.length)
            return text;
        var segments = trimmed.split(/[\\/]/);
        var tail = segments.length > 0 ? segments[segments.length - 1] : trimmed;
        return tail.length ? tail : trimmed;
    }

    function _displayTextForRaw(rawText) {
        var text = String(rawText || "");
        if (!shortenDisplayPathWhenInactive)
            return text;
        return _shortDisplayPath(text);
    }

    function _syncFieldTextFromRaw() {
        var nextText = pathField.activeFocus ? rawText : _displayTextForRaw(rawText);
        if (pathField.text !== nextText)
            pathField.text = nextText;
    }

    function syncTextToCommitted() {
        rawText = String(committedText || "");
        _syncFieldTextFromRaw();
    }

    function focusFieldAndSelect() {
        pathField.forceActiveFocus();
        pathField.selectAll();
    }

    onCommittedTextChanged: {
        if (!pathField.activeFocus)
            syncTextToCommitted();
    }

    onShortenDisplayPathWhenInactiveChanged: {
        if (!pathField.activeFocus)
            _syncFieldTextFromRaw();
    }

    Component.onCompleted: syncTextToCommitted()

    Timer {
        interval: 0
        running: true
        repeat: false
        onTriggered: root._syncFieldTextFromRaw()
    }

    TextMetrics {
        id: displayTextMetrics
        font: pathField.font
        text: root._displayTextForRaw(root.rawText)
    }

    RowLayout {
        id: editorRow
        anchors.fill: parent
        spacing: 6

        GraphSurfaceTextField {
            id: pathField
            objectName: root.fieldObjectName
            property string propertyKey: root.propertyKey
            Layout.fillWidth: true
            visible: root.visible
            enabled: root.enabled
            host: root.host
            // Read-only hint shown when no path is set yet; disappears as
            // soon as the user types or a path is committed.
            placeholderText: "..."
            onControlStarted: root.controlStarted()
            onTextEdited: root.rawText = text
            onActiveFocusChanged: root._syncFieldTextFromRaw()
            onAccepted: root.commitRequested(root.rawText)
            onEditingFinished: root.commitRequested(root.rawText)
        }

        GraphSurfaceButton {
            id: browseButton
            objectName: root.browseButtonObjectName
            property string propertyKey: root.propertyKey
            visible: root.visible
            enabled: root.enabled
            host: root.host
            text: root.browseButtonIconOnly ? "" : root.browseButtonText
            iconName: root.browseButtonIconOnly ? root.browseButtonIconName : ""
            iconOnly: root.browseButtonIconOnly
            iconSize: root.browseButtonIconSize
            iconSourceResolver: root.iconSourceResolver
            tooltipText: root.browseButtonText
            tooltipCategory: "general"
            onControlStarted: root.controlStarted()
            onClicked: {
                var selectedPath = root._resolveBrowsePath(root.rawText);
                if (!selectedPath.length)
                    return;
                root.rawText = selectedPath;
                root._syncFieldTextFromRaw();
                root.commitRequested(root.rawText);
            }
        }
    }
}
