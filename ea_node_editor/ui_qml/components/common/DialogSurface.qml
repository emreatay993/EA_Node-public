import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

FocusScope {
    id: root

    default property alias contentData: contentHost.data
    property var themePalette: ({})
    property string title: ""
    property bool closeButtonVisible: false

    signal closeRequested()

    implicitWidth: Math.max(240, surfaceLayout.implicitWidth)
    implicitHeight: surfaceLayout.implicitHeight

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: root.themePalette.panel_alt_bg || root.themePalette.panel_bg || "#24262c"
        border.width: 1
        border.color: root.themePalette.border || "#3a3d45"
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onClicked: function(mouse) { mouse.accepted = true }
    }

    ColumnLayout {
        id: surfaceLayout
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            visible: root.title.length > 0 || root.closeButtonVisible

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 16
                spacing: 12

                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: root.themePalette.panel_title_fg || root.themePalette.input_fg || "#eef3ff"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }

                ToolButton {
                    id: closeButton
                    objectName: "dialogSurfaceCloseButton"
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    visible: root.closeButtonVisible
                    hoverEnabled: true
                    padding: 0
                    Accessible.name: root.title.length > 0 ? "Close " + root.title : "Close dialog"
                    Accessible.role: Accessible.Button
                    onClicked: root.closeRequested()

                    contentItem: Item {
                        Rectangle {
                            anchors.centerIn: parent
                            width: 17
                            height: 2
                            radius: 1
                            rotation: 45
                            color: root.themePalette.panel_title_fg || root.themePalette.input_fg || "#eef3ff"
                        }

                        Rectangle {
                            anchors.centerIn: parent
                            width: 17
                            height: 2
                            radius: 1
                            rotation: -45
                            color: root.themePalette.panel_title_fg || root.themePalette.input_fg || "#eef3ff"
                        }
                    }

                    background: Rectangle {
                        radius: 6
                        color: closeButton.down
                            ? (root.themePalette.pressed || "transparent")
                            : (closeButton.hovered ? (root.themePalette.hover || "transparent") : "transparent")
                    }
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                visible: root.title.length > 0
                color: root.themePalette.border || "#3a3d45"
            }
        }

        ColumnLayout {
            id: contentHost
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
        }
    }
}
