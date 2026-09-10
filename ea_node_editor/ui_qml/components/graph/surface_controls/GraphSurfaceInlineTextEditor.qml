import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

Item {
    id: root
    property Item host: null
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color selectionColor: host ? Qt.alpha(host.selectedOutlineColor, 0.28) : "#6040CDFF"
    property color selectedTextColor: host ? host.surfaceColor : "#1b1d22"
    property string committedText: ""
    property string fieldObjectName: "graphSurfaceInlineTextEditorField"
    property real fontPixelSize: 12
    property bool fontBold: false
    property int horizontalAlignment: TextInput.AlignLeft
    property real leftPadding: 0
    property real rightPadding: 0
    property real topPadding: 0
    property real bottomPadding: 0
    property bool centerTextVertically: false
    property bool commitOnFocusLoss: true
    property bool _focusInitialized: false
    property bool _blurCommitEnabled: false
    readonly property string draftText: editor.text
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(editor, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)

    implicitWidth: Math.max(40, editor.implicitWidth)
    implicitHeight: Math.max(24, editor.contentHeight + editor.topPadding + editor.bottomPadding)

    signal controlStarted()
    signal commitRequested(string text)
    signal cancelRequested()

    function syncDraftToCommitted() {
        if (editor.text !== committedText)
            editor.text = committedText;
    }

    function resetDraft() {
        syncDraftToCommitted();
    }

    function activateEditor() {
        root._blurCommitEnabled = false;
        editor.forceActiveFocus();
        editor.cursorPosition = editor.length;
        editor.deselect();
        Qt.callLater(function() {
            root._blurCommitEnabled = root.visible && root.commitOnFocusLoss && editor.activeFocus;
        });
    }

    function _centeredVerticalPadding(basePadding) {
        if (!centerTextVertically)
            return basePadding;
        return Math.max(basePadding, (editor.height - editor.contentHeight) * 0.5);
    }

    onCommittedTextChanged: {
        if (!editor.activeFocus || draftText === committedText)
            syncDraftToCommitted();
    }

    onVisibleChanged: {
        if (visible) {
            _focusInitialized = false;
            _blurCommitEnabled = false;
        }
    }

    Component.onCompleted: syncDraftToCommitted()

    TextArea {
        id: editor
        objectName: root.fieldObjectName
        anchors.fill: parent
        wrapMode: TextEdit.Wrap
        selectByMouse: true
        persistentSelection: true
        color: root.textColor
        selectionColor: root.selectionColor
        selectedTextColor: root.selectedTextColor
        horizontalAlignment: root.horizontalAlignment
        font.pixelSize: root.fontPixelSize
        font.bold: root.fontBold
        leftPadding: root.leftPadding
        rightPadding: root.rightPadding
        topPadding: root._centeredVerticalPadding(root.topPadding)
        bottomPadding: root._centeredVerticalPadding(root.bottomPadding)
        renderType: root.host ? root.host.nodeTextRenderType : Text.CurveRendering
        background: Item {}

        onActiveFocusChanged: {
            if (activeFocus) {
                root._focusInitialized = true;
                root.controlStarted();
                return;
            }
            if (!root.visible || !root._focusInitialized || !root._blurCommitEnabled)
                return;
            root.commitRequested(text);
        }

        Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                    && (event.modifiers & Qt.ControlModifier)) {
                root.commitRequested(text);
                event.accepted = true;
            } else if (event.key === Qt.Key_Escape) {
                root.cancelRequested();
                event.accepted = true;
            }
        }
    }
}
