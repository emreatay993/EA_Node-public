import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: bar
    property var pane
    property string query: ""
    property string scope: "name"
    property bool compact: false
    property string placeholder: ""
    property alias fieldItem: searchField

    readonly property string resolvedPlaceholder: placeholder.length > 0
        ? placeholder
        : (scope === "value"
            ? "Filter by value…"
            : scope === "name"
                ? "Filter by name…"
                : "Filter properties…")

    implicitHeight: contentRow.implicitHeight
    width: parent ? parent.width : contentRow.implicitWidth

    RowLayout {
        id: contentRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 6

        Rectangle {
            id: searchContainer
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            color: bar.pane ? bar.pane.themePalette.input_bg : "#22242a"
            border.color: searchField.activeFocus
                ? (bar.pane ? bar.pane.themePalette.accent : "#60CDFF")
                : (bar.pane ? bar.pane.themePalette.input_border : "#4a4f5a")
            border.width: 1
            radius: 3
            implicitHeight: Math.max(28, searchField.implicitHeight)

            Image {
                id: searchIcon
                width: 12
                height: 12
                sourceSize.width: 12
                sourceSize.height: 12
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                smooth: true
                source: bar.pane && bar.pane.uiIconsRef ? bar.pane.uiIconsRef.sourceSized(
                    "search",
                    12,
                    String(bar.pane ? bar.pane.themePalette.muted_fg : "#d0d5de")
                ) : ""
            }

            TextField {
                id: searchField
                objectName: "inspectorFilterBarField"
                anchors.fill: parent
                anchors.leftMargin: 26
                anchors.rightMargin: bar.query.length > 0 ? 24 : 8
                text: bar.query
                placeholderText: bar.resolvedPlaceholder
                placeholderTextColor: bar.pane ? bar.pane.themePalette.muted_fg : "#d0d5de"
                color: bar.pane ? bar.pane.themePalette.input_fg : "#f0f2f5"
                selectByMouse: true
                background: Rectangle { color: "transparent" }
                font.pixelSize: bar.compact ? 11 : 12
                topPadding: 4
                bottomPadding: 4
                leftPadding: 0
                rightPadding: 0

                onTextEdited: {
                    if (bar.query !== text)
                        bar.query = text
                }
            }

            Rectangle {
                id: clearButton
                visible: bar.query.length > 0
                width: 18
                height: 18
                radius: 3
                anchors.right: parent.right
                anchors.rightMargin: 4
                anchors.verticalCenter: parent.verticalCenter
                color: clearHover.containsMouse
                    ? (bar.pane ? bar.pane.themePalette.hover : "#33373f")
                    : "transparent"

                Text {
                    anchors.centerIn: parent
                    text: "\u2715"
                    font.pixelSize: 11
                    color: bar.pane ? bar.pane.themePalette.muted_fg : "#d0d5de"
                }

                MouseArea {
                    id: clearHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (bar.query.length > 0)
                            bar.query = ""
                    }
                }
            }
        }

        InspectorScopeToggle {
            id: scopeToggle
            pane: bar.pane
            scope: bar.scope
            compact: bar.compact
            onSelectRequested: function (nextScope) {
                if (bar.scope !== nextScope)
                    bar.scope = nextScope
            }
        }
    }
}
