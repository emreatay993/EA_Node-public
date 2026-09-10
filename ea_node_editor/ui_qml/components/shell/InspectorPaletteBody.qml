import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "InspectorFilter.js" as InspectorFilter

Column {
    id: body
    objectName: "inspectorPaletteBody"

    property var pane
    property var propertyItems: []
    property string filterQuery: ""
    property string filterScope: "name"
    property int activeIndex: 0

    readonly property var _filterMatcher: InspectorFilter.makePropMatcher(body.filterQuery, body.filterScope)
    readonly property var _filteredItems: {
        var source = body.propertyItems || []
        var result = []
        for (var i = 0; i < source.length; ++i) {
            var item = source[i]
            if (!item)
                continue
            if (body._filterMatcher(item))
                result.push(item)
        }
        return result
    }
    readonly property int _clampedActive: {
        var len = body._filteredItems.length
        if (len <= 0)
            return 0
        var value = body.activeIndex
        if (value < 0)
            return 0
        if (value >= len)
            return len - 1
        return value
    }

    width: parent ? parent.width : implicitWidth
    spacing: 0
    focus: true

    Keys.onUpPressed: body.moveActive(-1)
    Keys.onDownPressed: body.moveActive(1)
    Keys.onEscapePressed: body.clearQuery()
    Keys.onReturnPressed: {}
    Keys.onEnterPressed: {}

    function setActive(i) {
        var next = Number(i)
        if (isNaN(next))
            return
        if (body.activeIndex !== next)
            body.activeIndex = next
    }

    function moveActive(delta) {
        var len = body._filteredItems.length
        if (len <= 0)
            return
        var base = body._clampedActive
        var next = ((base + delta) % len + len) % len
        if (body.activeIndex !== next)
            body.activeIndex = next
    }

    function clearQuery() {
        if (body.filterQuery !== "")
            body.filterQuery = ""
        if (body.activeIndex !== 0)
            body.activeIndex = 0
    }

    Rectangle {
        id: headerCard
        objectName: "inspectorPaletteHeader"
        width: parent.width
        color: body.pane ? body.pane.themePalette.toolbar_bg : "#2a2b30"
        implicitHeight: headerColumn.implicitHeight + 20

        Rectangle {
            width: parent.width
            height: 1
            anchors.bottom: parent.bottom
            color: body.pane ? body.pane.themePalette.border : "#3a3d45"
        }

        Column {
            id: headerColumn
            width: parent.width - 24
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            InspectorFilterBar {
                id: filterBar
                objectName: "inspectorPaletteFilterBar"
                pane: body.pane
                width: parent.width
                query: body.filterQuery
                scope: body.filterScope
                placeholder: body.filterScope === "value"
                    ? "Jump to value\u2026"
                    : "Jump to property\u2026"
                onQueryChanged: {
                    if (body.filterQuery !== query) {
                        body.filterQuery = query
                        body.activeIndex = 0
                    }
                }
                onScopeChanged: {
                    if (body.filterScope !== scope)
                        body.filterScope = scope
                }
            }
        }
    }

    Column {
        id: listColumn
        objectName: "inspectorPaletteList"
        width: parent.width
        spacing: 2
        topPadding: 6
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6

        Repeater {
            id: rowRepeater
            model: InspectorRowsModel { id: propertiesModel; rows: body._filteredItems }

            delegate: Rectangle {
                id: paletteRow
                readonly property var rowItem: propertiesModel.rowsByKey[model.rowKey] || ({})
                readonly property string rowKey: String(rowItem && rowItem.key ? rowItem.key : index)
                readonly property bool isActive: index === body._clampedActive

                objectName: "inspectorPaletteRow_" + rowKey
                width: listColumn.width - listColumn.leftPadding - listColumn.rightPadding
                color: isActive
                    ? (body.pane ? body.pane.themePalette.inspector_selected_bg : "#2f4a66")
                    : "transparent"
                border.color: isActive
                    ? (body.pane ? body.pane.themePalette.accent : "#60CDFF")
                    : "transparent"
                border.width: 1
                radius: 6
                clip: true
                implicitHeight: rowContent.implicitHeight + 18

                MouseArea {
                    id: rowHover
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton
                    cursorShape: Qt.PointingHandCursor
                    onEntered: body.setActive(index)
                    onClicked: body.setActive(index)
                }

                Column {
                    id: rowContent
                    width: parent.width - 20
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    RowLayout {
                        id: metaRow
                        width: parent.width
                        spacing: 8

                        Rectangle {
                            id: groupChip
                            readonly property string chipText: String(
                                paletteRow.rowItem && paletteRow.rowItem.group
                                    ? paletteRow.rowItem.group
                                    : "Properties"
                            )
                            Layout.alignment: Qt.AlignVCenter
                            radius: 3
                            color: "transparent"
                            border.color: body.pane ? body.pane.themePalette.border : "#3a3d45"
                            border.width: 1
                            implicitWidth: chipLabel.implicitWidth + 10
                            implicitHeight: chipLabel.implicitHeight + 4

                            Text {
                                id: chipLabel
                                anchors.centerIn: parent
                                text: groupChip.chipText
                                color: body.pane ? body.pane.themePalette.muted_fg : "#d0d5de"
                                font.pixelSize: 9
                                font.family: "Monospace"
                            }
                        }

                        Text {
                            id: rowLabel
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            text: String(paletteRow.rowItem && paletteRow.rowItem.label
                                ? paletteRow.rowItem.label
                                : "")
                            color: body.pane ? body.pane.themePalette.panel_title_fg : "#f0f4fb"
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }

                        Rectangle {
                            visible: !!(paletteRow.rowItem && paletteRow.rowItem.required)
                            Layout.alignment: Qt.AlignVCenter
                            width: 6
                            height: 6
                            radius: 3
                            color: body.pane ? body.pane.themePalette.inspector_danger_border : "#b96a72"
                        }

                        Rectangle {
                            visible: !!(paletteRow.rowItem && paletteRow.rowItem.dirty)
                            Layout.alignment: Qt.AlignVCenter
                            width: 6
                            height: 6
                            radius: 3
                            color: body.pane ? body.pane.themePalette.accent_strong : "#1D8CE0"
                        }

                        InspectorOverrideBadge {
                            visible: !!(paletteRow.rowItem
                                && (paletteRow.rowItem.driven_by
                                    || paletteRow.rowItem.overridden_by_input))
                            pane: body.pane
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Rectangle {
                            id: enterPill
                            visible: paletteRow.isActive
                            Layout.alignment: Qt.AlignVCenter
                            radius: 3
                            color: body.pane ? body.pane.themePalette.input_bg : "#22242a"
                            border.color: body.pane ? body.pane.themePalette.border : "#3a3d45"
                            border.width: 1
                            implicitWidth: enterPillText.implicitWidth + 10
                            implicitHeight: enterPillText.implicitHeight + 4

                            Text {
                                id: enterPillText
                                anchors.centerIn: parent
                                text: "\u21B5"
                                color: body.pane ? body.pane.themePalette.muted_fg : "#d0d5de"
                                font.pixelSize: 9
                                font.family: "Monospace"
                            }
                        }
                    }

                    InspectorPropertyEditor {
                        pane: body.pane
                        propertyItem: paletteRow.rowItem
                        width: parent.width
                    }
                }
            }
        }

        Text {
            id: emptyState
            objectName: "inspectorPaletteEmptyState"
            visible: body._filteredItems.length === 0
            width: listColumn.width - listColumn.leftPadding - listColumn.rightPadding
            horizontalAlignment: Text.AlignHCenter
            topPadding: 18
            bottomPadding: 18
            text: "No matches for \"" + body.filterQuery + "\"."
            color: body.pane ? body.pane.themePalette.muted_fg : "#d0d5de"
            font.pixelSize: 11
        }
    }

    Rectangle {
        id: footerStrip
        objectName: "inspectorPaletteFooter"
        width: parent.width
        color: body.pane ? body.pane.themePalette.toolbar_bg : "#2a2b30"
        implicitHeight: footerRow.implicitHeight + 12

        Rectangle {
            width: parent.width
            height: 1
            anchors.top: parent.top
            color: body.pane ? body.pane.themePalette.border : "#3a3d45"
        }

        Row {
            id: footerRow
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 14

            Repeater {
                model: [
                    { hintKey: "\u2191\u2193", hintLabel: "navigate" },
                    { hintKey: "\u21B5", hintLabel: "edit" },
                    { hintKey: "esc", hintLabel: "close" }
                ]

                delegate: Row {
                    spacing: 6

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        radius: 3
                        color: body.pane ? body.pane.themePalette.input_bg : "#22242a"
                        border.color: body.pane ? body.pane.themePalette.border : "#3a3d45"
                        border.width: 1
                        implicitWidth: hintKeyText.implicitWidth + 10
                        implicitHeight: hintKeyText.implicitHeight + 4

                        Text {
                            id: hintKeyText
                            anchors.centerIn: parent
                            text: modelData.hintKey
                            color: body.pane ? body.pane.themePalette.muted_fg : "#d0d5de"
                            font.pixelSize: 9
                            font.family: "Monospace"
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.hintLabel
                        color: body.pane ? body.pane.themePalette.muted_fg : "#d0d5de"
                        font.pixelSize: 10
                    }
                }
            }
        }
    }
}
