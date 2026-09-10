import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "MainShellUtils.js" as MainShellUtils

ColumnLayout {
    id: root
    objectName: "scriptCodeEditorPane"
    property var scriptEditorBridgeRef
    property var scriptHighlighterBridgeRef
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    property bool guideButtonVisible: false
    property bool guideButtonSelected: false
    property bool applyFailed: false
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property bool editorAvailable: !!root.scriptEditorBridgeRef
    signal guideRequested()

    spacing: 0

    function updateCursorMetrics() {
        if (!root.editorAvailable)
            return;
        var before = scriptEditorArea.text.slice(0, scriptEditorArea.cursorPosition);
        var lines = before.split("\n");
        var line = lines.length;
        var col = lines[lines.length - 1].length + 1;
        var sel = Math.abs(scriptEditorArea.selectionStart - scriptEditorArea.selectionEnd);
        root.scriptEditorBridgeRef.set_cursor_metrics(line, col, scriptEditorArea.cursorPosition, sel);
    }

    function attachSyntaxHighlighter() {
        if (root.scriptHighlighterBridgeRef && root.scriptHighlighterBridgeRef.attach_document)
            root.scriptHighlighterBridgeRef.attach_document(scriptEditorArea.textDocument);
    }

    onScriptHighlighterBridgeRefChanged: root.attachSyntaxHighlighter()
    Component.onCompleted: root.attachSyntaxHighlighter()

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 0

        Rectangle {
            id: scriptLineGutter
            Layout.preferredWidth: 52
            Layout.fillHeight: true
            color: root.themePalette.console_bg
            border.color: root.themePalette.border
            clip: true

            Text {
                id: scriptLineNumberText
                anchors.right: parent.right
                anchors.rightMargin: 8
                y: (scriptEditorScroll.contentItem ? -scriptEditorScroll.contentItem.contentY : 0) + 6
                text: MainShellUtils.lineNumbersText(scriptEditorArea.lineCount)
                color: root.themePalette.muted_fg
                font.family: "Consolas"
                font.pixelSize: 12
                horizontalAlignment: Text.AlignRight
                verticalAlignment: Text.AlignTop
            }
        }

        ScrollView {
            id: scriptEditorScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AsNeeded
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            TextArea {
                id: scriptEditorArea
                objectName: "scriptEditorArea"
                width: scriptEditorScroll.availableWidth
                text: root.editorAvailable ? root.scriptEditorBridgeRef.script_text : ""
                readOnly: !root.editorAvailable || !root.scriptEditorBridgeRef.current_node_id
                color: root.themePalette.input_fg
                font.family: "Consolas"
                font.pixelSize: 12
                wrapMode: TextArea.NoWrap
                background: Rectangle { color: root.themePalette.console_bg }
                selectByMouse: true
                persistentSelection: true
                leftPadding: 8
                rightPadding: 8
                topPadding: 6
                bottomPadding: 6

                Keys.onTabPressed: function(event) {
                    var insertionPosition = cursorPosition;
                    insert(insertionPosition, "    ");
                    cursorPosition = insertionPosition + 4;
                    event.accepted = true;
                }

                onTextChanged: {
                    if (root.editorAvailable && text !== root.scriptEditorBridgeRef.script_text)
                        root.scriptEditorBridgeRef.set_script_text(text);
                    root.applyFailed = false;
                    root.updateCursorMetrics();
                }

                onCursorPositionChanged: root.updateCursorMetrics()
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 30
        color: root.themePalette.toolbar_bg

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8

            Text {
                text: root.applyFailed
                    ? "Apply failed - see Console for details"
                    : (root.editorAvailable ? root.scriptEditorBridgeRef.cursor_label : "")
                color: root.applyFailed
                    ? (root.themePalette.inspector_danger_fg || "#f1b0b7")
                    : root.themePalette.muted_fg
                font.pixelSize: 11
            }

            Item { Layout.fillWidth: true }

            ShellButton {
                objectName: "pythonScriptGuideButton"
                visible: root.guideButtonVisible
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                text: "Guide"
                selectedStyle: root.guideButtonSelected
                tooltipText: root.guideButtonSelected
                    ? "Hide the Python Script customization guide"
                    : "Show the Python Script customization guide"
                Accessible.name: root.guideButtonSelected
                    ? "Hide Python Script guide"
                    : "Show Python Script guide"
                onClicked: root.guideRequested()
            }

            ShellButton {
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                text: "Revert"
                enabled: root.editorAvailable && root.scriptEditorBridgeRef.dirty
                onClicked: root.scriptEditorBridgeRef.revert()
            }

            ShellButton {
                themeBridgeRef: root.themeBridgeRef
                graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                uiIconsRef: root.uiIconsRef
                text: "Apply"
                enabled: root.editorAvailable && root.scriptEditorBridgeRef.dirty
                onClicked: root.applyFailed = !root.scriptEditorBridgeRef.apply()
            }
        }
    }
}
