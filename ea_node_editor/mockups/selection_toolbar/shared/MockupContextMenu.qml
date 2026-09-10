import QtQuick 2.15

Item {
    id: root

    property var themePalette: ({})
    property var actions: []
    property int minimumWidth: 270
    property int rowHeight: 34
    property int contentPadding: 6
    property int cornerRadius: 8
    property bool showGlyphs: false

    signal actionTriggered(string actionId)

    readonly property int panelWidth: Math.max(root.minimumWidth, contentColumn.implicitWidth + root.contentPadding * 2)
    readonly property int separatorHeight: 10
    readonly property int panelHeight: root.contentPadding * 2
        + root.actions.length * root.rowHeight
        + root._separatorCount() * root.separatorHeight
        + Math.max(0, root.actions.length - 1)

    function _separatorCount() {
        var count = 0;
        for (var i = 0; i < root.actions.length; i++) {
            if (root.actions[i].separatorBefore === true)
                count++;
        }
        return count;
    }

    implicitWidth: panelWidth
    implicitHeight: panelHeight + 12
    width: implicitWidth
    height: implicitHeight

    Rectangle {
        x: 0
        y: 10
        width: root.panelWidth
        height: root.panelHeight
        radius: root.cornerRadius + 2
        color: Qt.alpha("#000000", 0.10)
    }

    Rectangle {
        x: 0
        y: 4
        width: root.panelWidth
        height: root.panelHeight
        radius: root.cornerRadius + 1
        color: Qt.alpha("#000000", 0.06)
    }

    Rectangle {
        width: root.panelWidth
        height: root.panelHeight
        radius: root.cornerRadius
        color: root.themePalette.panel_bg || "#1b1d22"
        border.width: 1
        border.color: Qt.alpha(root.themePalette.input_border || "#4a4f5a", 0.92)

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            radius: parent.radius
            color: Qt.alpha("#ffffff", 0.28)
        }

        Column {
            id: contentColumn
            anchors.fill: parent
            anchors.margins: root.contentPadding
            spacing: 0

            Repeater {
                model: root.actions

                delegate: Item {
                    readonly property bool actionEnabled: modelData.enabled !== false
                    readonly property bool separatorBefore: modelData.separatorBefore === true
                    readonly property string actionText: String(modelData.text || "")
                    readonly property string actionId: String(modelData.actionId || "")

                    implicitWidth: actionRow.implicitWidth + 30
                    width: contentColumn.width
                    height: root.rowHeight + (index < root.actions.length - 1 ? 1 : 0) + (separatorBefore ? root.separatorHeight : 0)
                    opacity: actionEnabled ? 1.0 : 0.48

                    Rectangle {
                        visible: separatorBefore
                        x: 10
                        y: 4
                        width: parent.width - 20
                        height: 1
                        color: Qt.alpha(root.themePalette.border || "#3a3d45", 0.62)
                    }

                    Rectangle {
                        id: actionBackground
                        y: separatorBefore ? root.separatorHeight : 0
                        width: parent.width
                        height: root.rowHeight
                        radius: 6
                        color: actionMouseArea.containsMouse && actionEnabled
                            ? Qt.alpha(root.themePalette.accent || "#60CDFF", 0.12)
                            : "transparent"
                    }

                    Rectangle {
                        visible: actionMouseArea.containsMouse && actionEnabled
                        x: 8
                        y: actionBackground.y + 7
                        width: 3
                        height: root.rowHeight - 14
                        radius: 2
                        color: root.themePalette.accent || "#60CDFF"
                    }

                    Row {
                        id: actionRow
                        anchors.left: parent.left
                        anchors.leftMargin: 18
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: actionBackground.verticalCenter
                        spacing: root.showGlyphs ? 12 : 0

                        Text {
                            visible: root.showGlyphs
                            width: root.showGlyphs ? 26 : 0
                            text: String(modelData.glyph || "")
                            color: actionEnabled
                                ? (root.themePalette.accent || "#60CDFF")
                                : (root.themePalette.muted_fg || "#8d98aa")
                            font.pixelSize: 11
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        Text {
                            width: root.showGlyphs ? 188 : 236
                            text: actionText
                            color: actionEnabled
                                ? (root.themePalette.panel_title_fg || "#f0f4fb")
                                : (root.themePalette.muted_fg || "#8d98aa")
                            font.pixelSize: 12
                            font.bold: actionMouseArea.containsMouse && actionEnabled
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        Text {
                            text: String(modelData.shortcut || "")
                            color: root.themePalette.muted_fg || "#8d98aa"
                            font.pixelSize: 11
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    Rectangle {
                        visible: index < root.actions.length - 1
                        x: 10
                        y: actionBackground.y + root.rowHeight
                        width: parent.width - 20
                        height: 1
                        color: Qt.alpha(root.themePalette.border || "#3a3d45", 0.55)
                    }

                    MouseArea {
                        id: actionMouseArea
                        anchors.fill: actionBackground
                        hoverEnabled: actionEnabled
                        cursorShape: actionEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (actionEnabled)
                                root.actionTriggered(actionId);
                        }
                    }
                }
            }
        }
    }
}
