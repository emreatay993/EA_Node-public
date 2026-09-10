import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "InspectorFilter.js" as InspectorFilter

Column {
    id: body
    objectName: "inspectorSmartGroupsBody"

    property var pane
    property var propertyItems: []
    property string filterQuery: ""
    property string filterScope: "name"
    property var expandedMap: ({})

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
    readonly property var _smartSections: InspectorFilter.smartGroups(body._filteredItems)
    readonly property var _staticGroups: InspectorFilter.groupPropertyItems(body._filteredItems)

    width: parent ? parent.width : implicitWidth
    spacing: 8

    function _groupKey(kind, label) {
        return String(kind || "static") + ":" + String(label || "")
    }

    function isGroupOpen(kind, label) {
        var key = _groupKey(kind, label)
        var map = body.expandedMap || {}
        if (map[key] === undefined)
            return false
        return !!map[key]
    }

    function seedDefaultOpenGroups() {
        var source = body.expandedMap || {}
        var next = {}
        var changed = false
        for (var existing in source)
            next[existing] = source[existing]
        var items = body.propertyItems || []
        for (var index = 0; index < items.length; ++index) {
            var item = items[index]
            if (!item || !item.group_default_open)
                continue
            var label = String(item.group || "Properties")
            var key = body._groupKey("static", label)
            if (next[key] === undefined) {
                next[key] = true
                changed = true
            }
        }
        if (changed)
            body.expandedMap = next
    }

    onPropertyItemsChanged: Qt.callLater(seedDefaultOpenGroups)
    Component.onCompleted: seedDefaultOpenGroups()

    function toggleGroup(kind, label) {
        var key = _groupKey(kind, label)
        var next = {}
        var source = body.expandedMap || {}
        for (var existing in source)
            next[existing] = source[existing]
        next[key] = !body.isGroupOpen(kind, label)
        body.expandedMap = next
    }

    function _accentColorForKind(kind) {
        if (!body.pane)
            return "transparent"
        var palette = body.pane.themePalette
        if (kind === "modified")
            return palette.accent_strong
        if (kind === "driven")
            return palette.accent
        if (kind === "required")
            return palette.inspector_danger_border
        return "transparent"
    }

    function _labelColorForKind(kind) {
        if (!body.pane)
            return "transparent"
        var palette = body.pane.themePalette
        if (kind === "modified")
            return palette.inspector_smart_modified_fg
        if (kind === "driven")
            return palette.accent
        if (kind === "required")
            return palette.inspector_danger_fg
        return "transparent"
    }

    InspectorFilterBar {
        id: filterBar
        objectName: "inspectorSmartGroupsFilterBar"
        pane: body.pane
        width: parent.width
        query: body.filterQuery
        scope: body.filterScope
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
        id: smartRepeater
        model: InspectorRowsModel { id: smartModel; rows: body._smartSections; keyRole: "kind" }

        delegate: Column {
            id: smartSection
            width: body.width
            spacing: 0

            readonly property var sectionData: smartModel.rowsByKey[rowKey] || ({})
            readonly property string sectionKind: String(sectionData ? sectionData.kind : "")
            readonly property string sectionLabel: String(sectionData ? sectionData.label : "")
            readonly property var sectionItems: sectionData && sectionData.items ? sectionData.items : []
            readonly property bool sectionOpen: body.isGroupOpen(sectionKind, sectionLabel)
            property bool bodyCreated: false
            onSectionOpenChanged: { if (sectionOpen) bodyCreated = true }
            Component.onCompleted: { if (sectionOpen) bodyCreated = true }

            InspectorSmartGroupHeader {
                objectName: "inspectorSmartGroupHeader_" + smartSection.sectionKind
                pane: body.pane
                width: smartSection.width
                label: "\u2605 " + smartSection.sectionLabel
                count: smartSection.sectionItems.length
                open: smartSection.sectionOpen
                uppercase: false
                accentColor: body._accentColorForKind(smartSection.sectionKind)
                labelColor: body._labelColorForKind(smartSection.sectionKind)
                onToggleRequested: body.toggleGroup(smartSection.sectionKind, smartSection.sectionLabel)
            }

            Column {
                id: smartSectionBody
                objectName: "inspectorSmartGroupBody_" + smartSection.sectionKind
                width: smartSection.width
                visible: smartSection.sectionOpen
                spacing: 10
                topPadding: smartSection.sectionOpen ? 10 : 0
                bottomPadding: smartSection.sectionOpen ? 12 : 0
                leftPadding: 12
                rightPadding: 12

                Repeater {
                    model: InspectorRowsModel {
                        id: smartPropertyModel
                        rows: smartSection.bodyCreated ? smartSection.sectionItems : []
                    }

                    delegate: InspectorPropertyEditor {
                        pane: body.pane
                        width: smartSectionBody.width - smartSectionBody.leftPadding - smartSectionBody.rightPadding
                        propertyItem: smartPropertyModel.rowsByKey[rowKey] || ({})
                    }
                }
            }
        }
    }

    Repeater {
        id: staticRepeater
        model: InspectorRowsModel { id: staticModel; rows: body._staticGroups; keyRole: "name" }

        delegate: Column {
            id: staticSection
            width: body.width
            spacing: 0

            readonly property var groupData: staticModel.rowsByKey[rowKey] || ({})
            readonly property string groupName: String(groupData ? groupData.name : "")
            readonly property var groupItems: groupData && groupData.items ? groupData.items : []
            readonly property bool groupOpen: body.isGroupOpen("static", staticSection.groupName)
            property bool bodyCreated: false
            onGroupOpenChanged: { if (groupOpen) bodyCreated = true }
            Component.onCompleted: { if (groupOpen) bodyCreated = true }

            InspectorSmartGroupHeader {
                objectName: "inspectorStaticGroupHeader_" + staticSection.groupName
                pane: body.pane
                width: staticSection.width
                label: staticSection.groupName
                count: staticSection.groupItems.length
                open: staticSection.groupOpen
                uppercase: true
                onToggleRequested: body.toggleGroup("static", staticSection.groupName)
            }

            Column {
                id: staticSectionBody
                objectName: "inspectorStaticGroupBody_" + staticSection.groupName
                width: staticSection.width
                visible: staticSection.groupOpen
                spacing: 10
                topPadding: staticSection.groupOpen ? 10 : 0
                bottomPadding: staticSection.groupOpen ? 12 : 0
                leftPadding: 12
                rightPadding: 12

                Repeater {
                    model: InspectorRowsModel {
                        id: staticPropertyModel
                        rows: staticSection.bodyCreated ? staticSection.groupItems : []
                    }

                    delegate: InspectorPropertyEditor {
                        pane: body.pane
                        width: staticSectionBody.width - staticSectionBody.leftPadding - staticSectionBody.rightPadding
                        propertyItem: staticPropertyModel.rowsByKey[rowKey] || ({})
                    }
                }
            }
        }
    }
}
