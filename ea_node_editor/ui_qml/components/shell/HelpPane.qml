import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    objectName: "inspectorHelpPane"

    property var helpBridgeRef: typeof helpBridge !== "undefined" ? helpBridge : null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    property string titleText: root.helpBridgeRef ? root.helpBridgeRef.title : ""
    property string markdownText: root.helpBridgeRef ? root.helpBridgeRef.markdown : ""
    property bool hasMarkdown: root.helpBridgeRef ? root.helpBridgeRef.has_help : false
    property bool hasSelectedNode: false

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 2
        anchors.rightMargin: 2
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: root.themePalette.inspector_section_header_bg
            border.color: root.themePalette.border

            Text {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                verticalAlignment: Text.AlignVCenter
                text: root.hasMarkdown
                    ? (root.titleText.length > 0 ? root.titleText : "Operator Help")
                    : "Help"
                color: root.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
                elide: Text.ElideRight
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.themePalette.panel_bg
            border.color: root.themePalette.border

            Text {
                anchors.centerIn: parent
                visible: !root.hasMarkdown
                width: parent.width - 40
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: root.hasSelectedNode
                    ? "No help is available for this node."
                    : "Select a node to view its help."
                color: root.themePalette.muted_fg
                font.pixelSize: 11
            }

            ScrollView {
                id: helpScroll
                objectName: "helpScrollView"
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                visible: root.hasMarkdown
                ScrollBar.horizontal.policy: ScrollBar.AsNeeded

                TextArea {
                    id: helpText
                    objectName: "helpMarkdownText"
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextArea.WrapAtWordBoundaryOrAnywhere
                    textFormat: TextEdit.MarkdownText
                    text: root.markdownText
                    color: root.themePalette.app_fg
                    font.pixelSize: 12
                    background: Rectangle { color: "transparent" }

                    Component.onCompleted: {
                        if (root.helpBridgeRef)
                            root.helpBridgeRef.apply_document_spacing(textDocument)
                    }
                    onTextChanged: {
                        if (root.helpBridgeRef)
                            root.helpBridgeRef.apply_document_spacing(textDocument)
                    }
                }
            }
        }
    }
}
