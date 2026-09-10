import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "InspectorFilter.js" as InspectorFilter

Column {
    id: body
    objectName: "inspectorAccordionCardsBody"

    property var pane
    property var propertyItems: []
    property string filterQuery: ""
    property string filterScope: "name"
    property var expandedMap: ({})
    property var groupQueryMap: ({})

    readonly property var _allGroups: InspectorFilter.groupPropertyItems(body.propertyItems || [])
    readonly property bool _globalActive: String(body.filterQuery || "").trim().length > 0
    readonly property var _visibleGroups: {
        var groups = body._allGroups || []
        var result = []
        var globalMatcher = InspectorFilter.makePropMatcher(body.filterQuery, body.filterScope)
        var globalActive = body._globalActive
        for (var i = 0; i < groups.length; ++i) {
            var group = groups[i]
            if (!group)
                continue
            var allItems = group.items || []
            var groupName = String(group.name || "")
            var localQ = globalActive
                ? ""
                : (body.groupQueryMap && body.groupQueryMap[groupName]
                    ? String(body.groupQueryMap[groupName])
                    : "")
            var localActive = !globalActive && localQ.trim().length > 0
            var matcher = globalActive
                ? globalMatcher
                : (localActive
                    ? InspectorFilter.makePropMatcher(localQ, body.filterScope)
                    : function () { return true })
            var filtered = []
            for (var j = 0; j < allItems.length; ++j) {
                if (matcher(allItems[j]))
                    filtered.push(allItems[j])
            }
            if (globalActive && filtered.length === 0)
                continue
            result.push({
                name: groupName,
                items: filtered,
                allCount: allItems.length,
                matchCount: filtered.length,
                localQuery: localQ,
                showLocalFilter: allItems.length > 3 && !globalActive
            })
        }
        return result
    }

    width: parent ? parent.width : implicitWidth
    spacing: 10

    function isGroupOpen(name) {
        var map = body.expandedMap || {}
        if (map[name] === undefined)
            return false
        return !!map[name]
    }

    function toggleGroup(name) {
        var next = {}
        var source = body.expandedMap || {}
        for (var existing in source)
            next[existing] = source[existing]
        next[name] = !body.isGroupOpen(name)
        body.expandedMap = next
    }

    function setGroupQuery(name, value) {
        var next = {}
        var source = body.groupQueryMap || {}
        for (var existing in source)
            next[existing] = source[existing]
        next[name] = String(value || "")
        body.groupQueryMap = next
    }

    InspectorFilterBar {
        id: filterBar
        objectName: "inspectorAccordionCardsFilterBar"
        pane: body.pane
        width: parent.width
        query: body.filterQuery
        scope: body.filterScope
        placeholder: "Filter across all groups\u2026"
        onQueryChanged: {
            if (body.filterQuery !== query)
                body.filterQuery = query
        }
        onScopeChanged: {
            if (body.filterScope !== scope)
                body.filterScope = scope
        }
    }

    Repeater {
        id: groupRepeater
        model: InspectorRowsModel { id: groupsModel; rows: body._visibleGroups; keyRole: "name" }

        delegate: Rectangle {
            id: groupCard
            width: body.width
            color: body.pane ? body.pane.themePalette.panel_bg : "#1b1d22"
            border.color: body.pane ? body.pane.themePalette.border : "#3a3d45"
            border.width: 1
            radius: 8
            clip: true

            readonly property var groupData: groupsModel.rowsByKey[rowKey] || ({})
            readonly property string groupName: String(groupData ? groupData.name : "")
            readonly property var groupItems: groupData && groupData.items ? groupData.items : []
            readonly property int groupAllCount: groupData ? groupData.allCount || 0 : 0
            readonly property int groupMatchCount: groupData ? groupData.matchCount || 0 : 0
            readonly property string groupLocalQuery: String(groupData ? groupData.localQuery || "" : "")
            readonly property bool groupShowLocalFilter: !!(groupData && groupData.showLocalFilter)
            readonly property bool groupOpen: body.isGroupOpen(groupName)
            property bool bodyCreated: false
            onGroupOpenChanged: { if (groupOpen) bodyCreated = true }
            Component.onCompleted: { if (groupOpen) bodyCreated = true }

            implicitHeight: cardColumn.implicitHeight
            height: implicitHeight

            Column {
                id: cardColumn
                width: parent.width
                spacing: 0

                InspectorSmartGroupHeader {
                    objectName: "inspectorAccordionCardHeader_" + groupCard.groupName
                    pane: body.pane
                    width: cardColumn.width
                    label: groupCard.groupName
                    count: groupCard.groupMatchCount === groupCard.groupAllCount
                        ? groupCard.groupAllCount
                        : Number(groupCard.groupMatchCount)
                    open: groupCard.groupOpen
                    uppercase: true
                    onToggleRequested: body.toggleGroup(groupCard.groupName)
                }

                Column {
                    id: cardBody
                    objectName: "inspectorAccordionCardBody_" + groupCard.groupName
                    width: cardColumn.width
                    visible: groupCard.groupOpen
                    spacing: 12
                    topPadding: groupCard.groupOpen ? 12 : 0
                    bottomPadding: groupCard.groupOpen ? 12 : 0
                    leftPadding: 12
                    rightPadding: 12

                    InspectorFilterBar {
                        id: localFilterBar
                        objectName: "inspectorAccordionCardLocalFilter_" + groupCard.groupName
                        visible: groupCard.groupShowLocalFilter
                        pane: body.pane
                        width: cardBody.width - cardBody.leftPadding - cardBody.rightPadding
                        compact: true
                        placeholder: "Filter within " + groupCard.groupName + "\u2026"
                        query: groupCard.groupLocalQuery
                        scope: body.filterScope
                        onQueryChanged: body.setGroupQuery(groupCard.groupName, query)
                        onScopeChanged: {
                            if (body.filterScope !== scope)
                                body.filterScope = scope
                        }
                    }

                    Repeater {
                        model: InspectorRowsModel {
                            id: propertyModel
                            rows: groupCard.bodyCreated ? groupCard.groupItems : []
                        }

                        delegate: InspectorPropertyEditor {
                            pane: body.pane
                            width: cardBody.width - cardBody.leftPadding - cardBody.rightPadding
                            propertyItem: propertyModel.rowsByKey[rowKey] || ({})
                        }
                    }
                }
            }
        }
    }
}
