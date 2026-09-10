import QtQuick 2.15
import QtQuick.Controls 2.15

ComboBox {
    id: control
    property var pane
    property string placeholderText: ""
    readonly property real popupMaxHeight: 240
    implicitHeight: 34
    leftPadding: 8
    rightPadding: 30
    hoverEnabled: true
    font.pixelSize: 11
    palette.buttonText: pane.themePalette.input_fg
    palette.text: pane.themePalette.input_fg
    palette.highlight: pane.selectedSurfaceColor
    palette.highlightedText: pane.themePalette.panel_title_fg
    palette.base: pane.themePalette.input_bg
    palette.window: pane.cardBackgroundColor

    indicator: Text {
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        color: control.pane.themePalette.muted_fg
        font.pixelSize: 11
        font.bold: true
    }

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: control.currentIndex >= 0 ? control.displayText : control.placeholderText
        color: control.pane.themePalette.input_fg
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 10
        color: control.pane.themePalette.input_bg
        border.color: control.activeFocus ? control.pane.themePalette.accent : control.pane.themePalette.input_border
        border.width: 1
    }

    delegate: ItemDelegate {
        width: ListView.view ? ListView.view.width : control.width
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: modelData
            color: highlighted ? control.pane.themePalette.panel_title_fg : control.pane.themePalette.input_fg
            font.pixelSize: 11
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: highlighted ? control.pane.selectedSurfaceColor : "transparent"
            radius: 7
        }
    }

    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 4

        background: Rectangle {
            radius: 9
            color: control.pane.cardBackgroundColor
            border.color: control.pane.themePalette.input_border
            border.width: 1
        }

        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, control.popupMaxHeight)
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                interactive: true
            }
        }
    }
}
