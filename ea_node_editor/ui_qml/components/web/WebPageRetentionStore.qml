import QtQuick 2.15

Item {
    id: root
    objectName: "webPageRetentionStore"

    property int maxRetainedPages: 8
    property int workspaceSwitchParkingGraceMs: 350
    property bool workspaceSwitchParkingActive: false
    property string workspaceSwitchTargetId: ""
    property var _entries: ({})
    property var _lruKeys: []

    visible: false
    width: 0
    height: 0

    Item {
        id: parkingLot
        objectName: "webPageRetentionParkingLot"
        visible: false
        width: 0
        height: 0
    }

    Timer {
        id: workspaceSwitchParkingTimer
        interval: Math.max(0, Math.round(Number(root.workspaceSwitchParkingGraceMs || 0)))
        repeat: false
        onTriggered: root.finishWorkspaceSwitch()
    }

    Component.onDestruction: root.clearAll()

    function keyFor(workspaceId, nodeId) {
        var workspace = String(workspaceId || "").trim();
        var node = String(nodeId || "").trim();
        if (!workspace.length || !node.length)
            return "";
        return workspace + "\u001f" + node;
    }

    function beginWorkspaceSwitch(targetWorkspaceId) {
        root.workspaceSwitchParkingActive = true;
        root.workspaceSwitchTargetId = String(targetWorkspaceId || "").trim();
        workspaceSwitchParkingTimer.restart();
    }

    function finishWorkspaceSwitch() {
        root.workspaceSwitchParkingActive = false;
        root.workspaceSwitchTargetId = "";
    }

    function shouldParkForWorkspaceSwitch() {
        return root.workspaceSwitchParkingActive;
    }

    function retainedCount() {
        return root._lruKeys.length;
    }

    function containsKey(key) {
        return Boolean(root._entries[String(key || "")]);
    }

    function _touchKey(key) {
        var normalized = String(key || "");
        var next = [];
        for (var index = 0; index < root._lruKeys.length; ++index) {
            if (root._lruKeys[index] !== normalized)
                next.push(root._lruKeys[index]);
        }
        next.push(normalized);
        root._lruKeys = next;
    }

    function _removeKey(key) {
        var normalized = String(key || "");
        var next = [];
        for (var index = 0; index < root._lruKeys.length; ++index) {
            if (root._lruKeys[index] !== normalized)
                next.push(root._lruKeys[index]);
        }
        root._lruKeys = next;
        delete root._entries[normalized];
    }

    function _setPagePaused(item, paused) {
        if (!item)
            return;
        try {
            item.visible = !Boolean(paused);
        } catch (error) {
        }
        try {
            if (item.setRetainedPaused)
                item.setRetainedPaused(Boolean(paused));
            else if (item.setPageRetained)
                item.setPageRetained(Boolean(paused));
        } catch (error) {
        }
    }

    function _destroyEntry(entry) {
        if (!entry || !entry.item)
            return;
        root._setPagePaused(entry.item, true);
        try {
            entry.item.destroy();
        } catch (error) {
        }
    }

    function _workspaceIdForEntry(entry) {
        return String(entry && entry.workspaceId ? entry.workspaceId : "").trim();
    }

    function _oldestEvictableKey(protectedWorkspaceId) {
        var protectedWorkspace = String(protectedWorkspaceId || "").trim();
        var fallback = "";
        for (var index = 0; index < root._lruKeys.length; ++index) {
            var key = root._lruKeys[index];
            var entry = root._entries[key];
            if (!entry)
                return key;
            if (!fallback.length)
                fallback = key;
            if (!protectedWorkspace.length || root._workspaceIdForEntry(entry) !== protectedWorkspace)
                return key;
        }
        return fallback;
    }

    function _enforceLimit(protectedWorkspaceId) {
        var limit = Math.max(0, Math.round(Number(root.maxRetainedPages || 0)));
        while (root._lruKeys.length > limit) {
            var key = root._oldestEvictableKey(protectedWorkspaceId);
            if (!key.length)
                return;
            root.evictPage(key);
        }
    }

    function parkPage(key, item, metadata) {
        var normalized = String(key || "").trim();
        if (!normalized.length || !item)
            return false;
        var existing = root._entries[normalized];
        if (existing && existing.item !== item)
            root.evictPage(normalized);
        var data = metadata || ({});
        root._setPagePaused(item, true);
        item.parent = parkingLot;
        try {
            item.anchors.fill = parkingLot;
        } catch (error) {
        }
        root._entries[normalized] = {
            "item": item,
            "workspaceId": String(data.workspace_id || data.workspaceId || "").trim(),
            "nodeId": String(data.node_id || data.nodeId || "").trim(),
            "currentUrl": String(data.current_url || data.currentUrl || "").trim()
        };
        root._touchKey(normalized);
        root._enforceLimit(root.workspaceSwitchTargetId);
        return root.containsKey(normalized);
    }

    function claimPage(key, expectedUrl, targetParent, allowUrlMismatch) {
        var normalized = String(key || "").trim();
        if (!normalized.length || !targetParent)
            return null;
        var entry = root._entries[normalized];
        if (!entry || !entry.item) {
            root._removeKey(normalized);
            return null;
        }
        var requestedUrl = String(expectedUrl || "").trim();
        var retainedUrl = String(entry.currentUrl || "").trim();
        if (!Boolean(allowUrlMismatch) && requestedUrl.length && retainedUrl.length && requestedUrl !== retainedUrl) {
            root.evictPage(normalized);
            return null;
        }
        root._removeKey(normalized);
        var item = entry.item;
        item.parent = targetParent;
        try {
            item.anchors.fill = targetParent;
        } catch (error) {
        }
        root._setPagePaused(item, false);
        return item;
    }

    function evictPage(key) {
        var normalized = String(key || "").trim();
        if (!normalized.length)
            return false;
        var entry = root._entries[normalized];
        root._removeKey(normalized);
        root._destroyEntry(entry);
        return Boolean(entry);
    }

    function clearAll() {
        var keys = root._lruKeys.slice(0);
        for (var index = 0; index < keys.length; ++index)
            root.evictPage(keys[index]);
        root._entries = ({});
        root._lruKeys = [];
        root.finishWorkspaceSwitch();
    }
}
