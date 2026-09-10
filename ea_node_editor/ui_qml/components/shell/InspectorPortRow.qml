import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: portRow
    property var pane
    property var portItem: ({})
    readonly property string portKey: String(portItem ? portItem.key || "" : "")

    width: parent ? parent.width : implicitWidth
    radius: 9
    color: pane.selectedPortKey === portKey
        ? pane.selectedSurfaceColor
        : pane.themePalette.input_bg
    border.color: pane.selectedPortKey === portKey
        ? pane.selectedOutlineColor
        : pane.themePalette.input_border
    border.width: 1
    implicitHeight: 46

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 6

        InspectorCheckBox {
            pane: portRow.pane
            Layout.alignment: Qt.AlignVCenter
            objectName: "inspectorPortExposedToggle"
            property string portKey: portRow.portKey
            enabled: !Boolean(portRow.portItem.required)
            checked: Boolean(portRow.portItem.required || portRow.portItem.exposed)
            onClicked: pane.selectPort(portRow.portKey)
            onToggled: {
                if (Boolean(portRow.portItem.required))
                    return
                if (portRow.pane.inspectorBridgeRef)
                    portRow.pane.inspectorBridgeRef.set_selected_port_exposed(portRow.portKey, checked)
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 0

            Item {
                Layout.fillWidth: true
                implicitHeight: 18

                Text {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !portLabelEditor.visible
                    text: String(portRow.portItem.label || portRow.portItem.key || "")
                    color: portRow.pane.themePalette.panel_title_fg
                    font.pixelSize: 11
                    font.bold: true
                    elide: Text.ElideRight
                }

                TextField {
                    id: portLabelEditor
                    objectName: "inspectorPortLabelEditor"
                    property string portKey: portRow.portKey
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    visible: portRow.pane.canEditPortLabels
                        && portRow.pane._isEditablePortKind(portRow.portItem.kind)
                        && portRow.pane.editingPortKey === portRow.portKey
                    implicitHeight: 24
                    leftPadding: 4
                    rightPadding: 4
                    topPadding: 1
                    bottomPadding: 1
                    selectByMouse: true
                    text: String(portRow.portItem.label || portRow.portItem.key || "")
                    color: portRow.pane.themePalette.panel_title_fg
                    font.pixelSize: 11
                    font.bold: true
                    background: Rectangle {
                        radius: 6
                        color: portRow.pane.themePalette.input_bg
                        border.color: portRow.pane.themePalette.accent
                        border.width: 1
                    }
                    onVisibleChanged: {
                        if (visible)
                            text = portRow.pane.editingPortLabel
                    }
                    onTextChanged: {
                        if (visible)
                            portRow.pane.editingPortLabel = text
                    }
                    onAccepted: portRow.pane.commitPortLabelEdit(portRow.portKey, text)
                    onEditingFinished: portRow.pane.commitPortLabelEdit(portRow.portKey, text)
                    onActiveFocusChanged: {
                        if (!activeFocus)
                            portRow.pane.commitPortLabelEdit(portRow.portKey, text)
                    }
                    Keys.onEscapePressed: {
                        text = String(portRow.portItem.label || portRow.portItem.key || "")
                        portRow.pane.cancelPortLabelEdit(portRow.portKey)
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: portRow.pane.canEditPortLabels
                        && portRow.pane._isEditablePortKind(portRow.portItem.kind)
                        && !portLabelEditor.visible
                    cursorShape: Qt.IBeamCursor
                    onClicked: {
                        portRow.pane.beginPortLabelEdit(portRow.portKey)
                        Qt.callLater(function() {
                            portLabelEditor.forceActiveFocus()
                            portLabelEditor.selectAll()
                        })
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: String(portRow.portItem.kind || "") + " / " + String(portRow.portItem.data_type || "COREX.DataTypes.Any")
                color: portRow.pane.themePalette.muted_fg
                font.pixelSize: 9
                elide: Text.ElideRight
            }
        }

        Rectangle {
            visible: !!portRow.portItem.required
            Layout.alignment: Qt.AlignVCenter
            radius: 8
            color: portRow.pane.sectionHeaderColor
            border.color: portRow.pane.themePalette.input_border
            border.width: 1
            implicitWidth: requiredLabel.implicitWidth + 10
            implicitHeight: requiredLabel.implicitHeight + 6

            Text {
                id: requiredLabel
                anchors.centerIn: parent
                text: "REQUIRED"
                color: portRow.pane.themePalette.muted_fg
                font.pixelSize: 8
                font.bold: true
                font.letterSpacing: 0.5
            }
        }
    }

    TapHandler {
        onTapped: portRow.pane.selectPort(portRow.portKey)
    }
}
