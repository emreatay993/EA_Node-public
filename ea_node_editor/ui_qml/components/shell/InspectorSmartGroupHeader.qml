import QtQuick 2.15

Rectangle {
    id: header
    property var pane
    property string label: ""
    property int count: 0
    property bool open: true
    property color accentColor: "transparent"
    property color labelColor: "transparent"
    property bool uppercase: true
    property bool showCount: true

    signal toggleRequested()

    readonly property color headerBackground: pane
        ? pane.themePalette.inspector_section_header_bg
        : "#32363f"
    readonly property color labelFallback: pane
        ? pane.themePalette.group_title_fg
        : "#bdc5d3"
    readonly property color mutedForeground: pane
        ? pane.themePalette.muted_fg
        : "#d0d5de"
    readonly property color displayedLabelColor: Qt.colorEqual(labelColor, "transparent")
        ? (Qt.colorEqual(accentColor, "transparent") ? labelFallback : accentColor)
        : labelColor

    color: headerBackground
    implicitHeight: headerRow.implicitHeight + 14
    height: implicitHeight
    width: parent ? parent.width : headerRow.implicitWidth

    Rectangle {
        id: accentStripe
        width: 2
        height: parent.height
        anchors.left: parent.left
        color: Qt.colorEqual(header.accentColor, "transparent")
            ? "transparent"
            : header.accentColor
    }

    Row {
        id: headerRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 6

        InspectorChevron {
            id: chevron
            uiIconsRef: header.pane ? header.pane.uiIconsRef : null
            open: header.open
            strokeColor: header.displayedLabelColor
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            id: labelText
            width: parent.width - chevron.width - countLabel.implicitWidth - headerRow.spacing * 2
            text: header.uppercase ? String(header.label).toUpperCase() : String(header.label)
            color: header.displayedLabelColor
            font.pixelSize: 11
            font.bold: true
            font.letterSpacing: header.uppercase ? 0.5 : 0
            elide: Text.ElideRight
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            id: countLabel
            visible: header.showCount
            text: String(header.count)
            color: header.mutedForeground
            font.pixelSize: 10
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: header.toggleRequested()
    }
}
