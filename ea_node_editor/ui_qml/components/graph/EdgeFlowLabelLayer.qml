import QtQuick 2.15
import QtQml 2.15
import "EdgePaintPolicy.js" as EdgePaintPolicy

Item {
    id: root
    objectName: "graphEdgeFlowLabelLayer"
    property Item edgeLayer: null
    property Item canvasLayer: null
    property int snapshotRevisionToken: root.edgeLayer ? root.edgeLayer._visibleEdgeSnapshotRevision : -1
    property int profileLabelDelegateCreateCount: 0
    property int profileLabelDelegateDestroyCount: 0
    property int profileFlowLabelModelSyncSkipCount: 0
    property var _lastFlowLabelEntryRefs: []
    readonly property int effectiveGraphLabelPixelSize: {
        var numeric = NaN;
        if (root.canvasLayer && root.canvasLayer.graphLabelPixelSize !== undefined)
            numeric = Number(root.canvasLayer.graphLabelPixelSize);
        if (!isFinite(numeric) && root.canvasLayer && root.canvasLayer.canvasStateBridgeRef)
            numeric = Number(root.canvasLayer.canvasStateBridgeRef.graphics_graph_label_pixel_size);
        if (!isFinite(numeric)
                && root.edgeLayer
                && root.edgeLayer.parent
                && root.edgeLayer.parent.canvasItem
                && root.edgeLayer.parent.canvasItem.prefs) {
            numeric = Number(root.edgeLayer.parent.canvasItem.prefs.graphLabelPixelSize);
        }
        if (!isFinite(numeric) && root.edgeLayer && root.edgeLayer.graphLabelPixelSize !== undefined)
            numeric = Number(root.edgeLayer.graphLabelPixelSize);
        if (!isFinite(numeric))
            numeric = 10;
        return Math.max(8, Math.min(18, Math.round(numeric)));
    }
    readonly property var graphSharedTypography: sharedTypographyState

    GraphSharedTypography {
        id: sharedTypographyState
        objectName: "graphEdgeSharedTypography"
        graphLabelPixelSize: root.effectiveGraphLabelPixelSize
    }

    ListModel {
        id: flowLabelModel
        dynamicRoles: true
    }

    function _modelEdgeId(model, index) {
        var entry = model.get(index);
        return String(entry && entry.edgeId || "");
    }

    function _findModelIndexByEdgeId(model, edgeId, startIndex) {
        var normalized = String(edgeId || "");
        for (var i = Math.max(0, Number(startIndex || 0)); i < model.count; i++) {
            if (root._modelEdgeId(model, i) === normalized)
                return i;
        }
        return -1;
    }

    function _flowLabelEntries() {
        var entries = [];
        var snapshots = root.edgeLayer ? (root.edgeLayer._visibleEdgeSnapshots || []) : [];
        for (var i = 0; i < snapshots.length; i++) {
            var snapshot = snapshots[i];
            var edgeId = String(snapshot && snapshot.edgeId || "");
            if (!edgeId || Boolean(snapshot.culled))
                continue;
            if (String(snapshot.labelMode || "hidden") === "hidden")
                continue;
            if (!snapshot.labelAnchorScene)
                continue;
            entries.push({"edgeId": edgeId, "edgeData": snapshot.edgeData || ({})});
        }
        return entries;
    }

    function _setFlowLabelModelEntry(index, entry) {
        flowLabelModel.setProperty(index, "edgeId", entry.edgeId);
        flowLabelModel.setProperty(index, "edgeData", entry.edgeData || ({}));
    }

    function _flowLabelEntriesInSync(entries) {
        if (flowLabelModel.count !== entries.length)
            return false;
        var refs = root._lastFlowLabelEntryRefs || [];
        if (refs.length !== entries.length)
            return false;
        for (var i = 0; i < entries.length; i++) {
            var entry = entries[i];
            var ref = refs[i] || null;
            if (!ref || ref.edgeId !== entry.edgeId || ref.edgeData !== entry.edgeData)
                return false;
        }
        return true;
    }

    function _rememberFlowLabelEntryRefs(entries) {
        var refs = [];
        for (var i = 0; i < entries.length; i++)
            refs.push({"edgeId": entries[i].edgeId, "edgeData": entries[i].edgeData});
        root._lastFlowLabelEntryRefs = refs;
    }

    function _syncFlowLabelModel() {
        var entries = root._flowLabelEntries();
        if (root._flowLabelEntriesInSync(entries)) {
            root.profileFlowLabelModelSyncSkipCount += 1;
            return;
        }
        var nextLookup = {};
        for (var i = 0; i < entries.length; i++)
            nextLookup[entries[i].edgeId] = true;
        for (var removeIndex = flowLabelModel.count - 1; removeIndex >= 0; removeIndex--) {
            if (!nextLookup[root._modelEdgeId(flowLabelModel, removeIndex)])
                flowLabelModel.remove(removeIndex);
        }
        for (var targetIndex = 0; targetIndex < entries.length; targetIndex++) {
            var entry = entries[targetIndex];
            if (targetIndex < flowLabelModel.count
                    && root._modelEdgeId(flowLabelModel, targetIndex) === entry.edgeId) {
                root._setFlowLabelModelEntry(targetIndex, entry);
                continue;
            }
            var existingIndex = root._findModelIndexByEdgeId(flowLabelModel, entry.edgeId, targetIndex + 1);
            if (existingIndex >= 0) {
                flowLabelModel.move(existingIndex, targetIndex, 1);
                root._setFlowLabelModelEntry(targetIndex, entry);
                continue;
            }
            flowLabelModel.insert(targetIndex, entry);
        }
        while (flowLabelModel.count > entries.length)
            flowLabelModel.remove(flowLabelModel.count - 1);
        root._rememberFlowLabelEntryRefs(entries);
    }

    onEdgeLayerChanged: root._syncFlowLabelModel()
    onSnapshotRevisionTokenChanged: root._syncFlowLabelModel()
    Component.onCompleted: root._syncFlowLabelModel()

    function edgeLabelText(edge) {
        return String(edge && edge.label ? edge.label : "").trim();
    }

    function flowLabelMode(edge) {
        if (!root.edgeLayer || !EdgePaintPolicy.edgeIsFlow(edge) || !edgeLabelText(edge))
            return "hidden";
        var zoom = root.edgeLayer.viewBridge ? root.edgeLayer.viewBridge.zoom_value : 1.0;
        if (zoom < root.edgeLayer.flowLabelSimplifyZoomThreshold)
            return "text";
        return "pill";
    }

    function flowLabelScale() {
        if (!root.edgeLayer || !root.edgeLayer.viewBridge)
            return 1.0;
        var zoom = Number(root.edgeLayer.viewBridge.zoom_value);
        var threshold = Number(root.edgeLayer.flowLabelHideZoomThreshold);
        if (!isFinite(zoom) || !isFinite(threshold) || threshold <= 0.0 || zoom >= threshold)
            return 1.0;
        return Math.max(0.35, Math.min(1.0, zoom / threshold));
    }

    function flowLabelTextColor(edge) {
        return EdgePaintPolicy.styleString(EdgePaintPolicy.flowStyle(edge).label_text_color)
            || root.edgeLayer.flowDefaultLabelTextColor;
    }

    function flowLabelBackgroundColor(edge) {
        var explicitColor = EdgePaintPolicy.styleString(
            EdgePaintPolicy.flowStyle(edge).label_background_color
        );
        if (explicitColor)
            return explicitColor;
        return "transparent";
    }

    function flowLabelBorderColor(edge, selected, previewed) {
        if (selected || previewed)
            return EdgePaintPolicy.flowStrokeColor(root.edgeLayer, edge, selected, previewed);
        return root.edgeLayer.flowDefaultLabelBorderColor;
    }

    function flowLabelAnchorScene(geometry) {
        var anchor = null;
        if (geometry && geometry.route === "pipe") {
            var pipePoints = geometry.pipe_points || [];
            var longestHorizontal = null;
            for (var i = 1; i < pipePoints.length; i++) {
                var start = pipePoints[i - 1];
                var end = pipePoints[i];
                var dx = end.x - start.x;
                var dy = end.y - start.y;
                if (Math.abs(dy) > 0.01)
                    continue;
                var length = Math.abs(dx);
                if (!longestHorizontal || length > longestHorizontal.length) {
                    longestHorizontal = {
                        "x": (start.x + end.x) * 0.5,
                        "y": start.y,
                        "dx": dx >= 0.0 ? 1.0 : -1.0,
                        "dy": 0.0,
                        "angle": dx >= 0.0 ? 0.0 : 180.0,
                        "length": length
                    };
                }
            }
            anchor = longestHorizontal || root.edgeLayer._edgeAnchor(geometry, 0.5);
        } else {
            anchor = root.edgeLayer._edgeAnchor(geometry, 0.5);
        }
        if (!anchor)
            return null;
        var normalX = -anchor.dy;
        var normalY = anchor.dx;
        if (normalY > 0.0) {
            normalX = -normalX;
            normalY = -normalY;
        }
        return {
            "x": anchor.x,
            "y": anchor.y,
            "dx": anchor.dx,
            "dy": anchor.dy,
            "normal_x": normalX,
            "normal_y": normalY,
            "angle": anchor.angle
        };
    }

    function flowLabelAnchor(labelAnchorScene) {
        if (!labelAnchorScene || !root.edgeLayer)
            return null;
        return {
            "screen_x": root.edgeLayer.sceneToScreenX(labelAnchorScene.x),
            "screen_y": root.edgeLayer.sceneToScreenY(labelAnchorScene.y),
            "angle": labelAnchorScene.angle
        };
    }

    Repeater {
        model: flowLabelModel

        delegate: Item {
            objectName: "graphEdgeFlowLabelItem"
            property var edgeData: model.edgeData || ({})
            property string edgeId: String(model.edgeId || "")
            property int snapshotRevisionToken: root.snapshotRevisionToken
            property var snapshotData: snapshotRevisionToken >= 0 && edgeId && root.edgeLayer
                ? root.edgeLayer._visibleEdgeSnapshot(edgeId)
                : null
            property string labelText: snapshotData ? String(snapshotData.labelText || "") : ""
            property string labelMode: snapshotData ? String(snapshotData.labelMode || "hidden") : "hidden"
            property bool labelRequested: labelMode !== "hidden"
            property var snapshotRevision: snapshotData ? snapshotData.revision : 0
            property bool culledByViewport: labelRequested && snapshotData ? Boolean(snapshotData.culled) : false
            property bool pillVisible: labelMode === "pill"
            property real anchorScreenX: labelAnchor ? labelAnchor.screen_x : 0.0
            property real anchorScreenY: labelAnchor ? labelAnchor.screen_y : 0.0
            property var geometry: labelRequested && !culledByViewport && snapshotData ? snapshotData.geometry : null
            property var labelAnchorScene: labelRequested && !culledByViewport && snapshotData ? snapshotData.labelAnchorScene : null
            property var labelAnchor: labelAnchorScene ? root.flowLabelAnchor(labelAnchorScene) : null
            property bool hitTestMatches: visible
            property bool selectedEdge: snapshotData ? Boolean(snapshotData.selected) : false
            property bool previewedEdge: snapshotData ? Boolean(snapshotData.previewed) : false
            property bool labelBackingVisible: labelMode === "pill" || labelMode === "text"
            property real horizontalPadding: pillVisible ? 10.0 : 8.0
            property real verticalPadding: pillVisible ? 6.0 : 3.0
            property real maximumTextWidth: pillVisible ? 220.0 : 120.0
            property real labelBackingRadius: pillVisible ? 5.0 : 2.0
            property real labelScale: root.flowLabelScale()
            visible: labelRequested && !culledByViewport && labelAnchor !== null
            width: labelTextItem.width + horizontalPadding * 2.0
            height: labelTextItem.height + verticalPadding * 2.0
            x: anchorScreenX - width * 0.5
            y: anchorScreenY - height * 0.5
            scale: labelScale
            transformOrigin: Item.Center

            Rectangle {
                objectName: "graphEdgeFlowLabelPill"
                anchors.fill: parent
                radius: parent.labelBackingRadius
                visible: parent.labelBackingVisible
                color: root.flowLabelBackgroundColor(parent.edgeData)
                border.width: 0
                border.color: root.flowLabelBorderColor(parent.edgeData, parent.selectedEdge, parent.previewedEdge)
            }

            Text {
                id: labelTextItem
                objectName: "graphEdgeFlowLabelText"
                anchors.centerIn: parent
                width: Math.min(parent.maximumTextWidth, implicitWidth)
                text: parent.labelText
                color: root.flowLabelTextColor(parent.edgeData)
                font.pixelSize: parent.pillVisible
                    ? root.graphSharedTypography.edgePillPixelSize
                    : root.graphSharedTypography.edgeLabelPixelSize
                font.weight: parent.pillVisible
                    ? root.graphSharedTypography.edgePillFontWeight
                    : root.graphSharedTypography.edgeLabelFontWeight
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                renderType: Text.NativeRendering
            }

            Component.onCompleted: root.profileLabelDelegateCreateCount += 1
            Component.onDestruction: root.profileLabelDelegateDestroyCount += 1
        }
    }
}
