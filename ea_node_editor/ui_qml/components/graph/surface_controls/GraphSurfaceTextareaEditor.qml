import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    property Item host: null
    property alias fieldFont: textareaField.font
    property alias fieldFillColor: textareaField.fillColor
    property alias fieldBorderColor: textareaField.borderColor
    property alias fieldFocusBorderColor: textareaField.focusBorderColor
    property alias fieldTextColor: textareaField.textColor
    property alias fieldLeftPadding: textareaField.leftPadding
    property alias fieldRightPadding: textareaField.rightPadding
    property alias fieldTopPadding: textareaField.topPadding
    property alias fieldBottomPadding: textareaField.bottomPadding
    property string propertyKey: ""
    property string committedText: ""
    property string fieldObjectName: "graphSurfaceTextareaField"
    property bool _focusInitialized: false
    property bool _blurCommitEnabled: false
    readonly property string draftText: textareaField.text
    readonly property bool dirty: draftText !== committedText
    readonly property var embeddedInteractiveRects: textareaField.embeddedInteractiveRects
    implicitWidth: textareaField.implicitWidth
    implicitHeight: textareaField.implicitHeight

    signal controlStarted()
    signal commitRequested(string text)

    function syncDraftToCommitted() {
        if (textareaField.text !== committedText)
            textareaField.text = committedText;
    }

    function resetDraft() {
        syncDraftToCommitted();
    }

    function commitDraft() {
        commitRequested(textareaField.text);
    }

    function activateEditor() {
        root._blurCommitEnabled = false;
        textareaField.forceActiveFocus();
        textareaField.cursorPosition = textareaField.length;
        textareaField.deselect();
        Qt.callLater(function() {
            root._blurCommitEnabled = root.visible && textareaField.activeFocus;
        });
    }

    onCommittedTextChanged: {
        if (!textareaField.activeFocus || !dirty)
            syncDraftToCommitted();
    }

    onVisibleChanged: {
        if (visible) {
            _focusInitialized = false;
            _blurCommitEnabled = false;
        }
    }

    Component.onCompleted: syncDraftToCommitted()

    GraphSurfaceTextArea {
        id: textareaField
        objectName: root.fieldObjectName
        property string propertyKey: root.propertyKey
        anchors.fill: parent
        visible: root.visible
        enabled: root.enabled
        host: root.host
        onControlStarted: {
            root._focusInitialized = true;
            root.controlStarted();
            Qt.callLater(function() {
                root._blurCommitEnabled = root.visible && textareaField.activeFocus;
            });
        }
        Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                    && (event.modifiers & Qt.ControlModifier)) {
                root.commitDraft();
                event.accepted = true;
            } else if (event.key === Qt.Key_Escape) {
                root.resetDraft();
                event.accepted = true;
            }
        }
    }

    Connections {
        target: textareaField

        function onActiveFocusChanged() {
            if (textareaField.activeFocus)
                return;
            if (!root.visible || !root._focusInitialized || !root._blurCommitEnabled || !root.dirty)
                return;
            root._blurCommitEnabled = false;
            root.commitDraft();
        }
    }
}
