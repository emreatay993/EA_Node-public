import QtQuick 2.15
import "../graph/GraphNodeSurfaceMetrics.js" as GraphNodeSurfaceMetrics
import "../graph/passive" as GraphPassiveComponents

Rectangle {
    id: root
    objectName: "graphCanvasDropPreview"
    property Item canvasItem: null
    property var viewBridge: null
    readonly property var themePalette: themeBridge.palette
    readonly property color previewChromeColor: Qt.alpha(themePalette.panel_bg, 0.66)
    readonly property color previewBorderColor: themePalette.accent
    readonly property color previewTitleColor: themePalette.panel_title_fg
    readonly property color previewLabelColor: themePalette.muted_fg
    readonly property color flowchartPreviewFillColor: Qt.alpha("#F5FAFD", 0.96)
    readonly property color flowchartPreviewBorderColor: "#61798B"
    readonly property color flowchartPreviewTitleColor: "#173247"
    readonly property color flowchartPreviewPortColor: Qt.alpha(flowchartPreviewBorderColor, 0.74)
    readonly property color flowchartPreviewPortFillColor: Qt.alpha(flowchartPreviewBorderColor, 0.16)
    readonly property var previewPayload: root.canvasItem ? root.canvasItem.dropPreviewNodePayload : null
    readonly property var previewMetrics: GraphNodeSurfaceMetrics.surfaceMetrics(previewPayload)
    readonly property real previewZoom: root.viewBridge ? root.viewBridge.zoom_value : 1.0
    readonly property bool previewIsFlowchart: String(previewPayload ? previewPayload.surface_family || "standard" : "standard") === "flowchart"
    readonly property bool previewUsesCardinalNeutralFlowHandles: GraphNodeSurfaceMetrics.nodeUsesCardinalNeutralFlowHandles(previewPayload)
    readonly property bool previewUsesHostChrome: !previewIsFlowchart || Boolean(previewMetrics.use_host_chrome)
    readonly property color effectivePreviewFillColor: previewIsFlowchart ? flowchartPreviewFillColor : previewChromeColor
    readonly property color effectivePreviewBorderColor: previewIsFlowchart ? flowchartPreviewBorderColor : previewBorderColor
    readonly property color effectivePreviewTitleColor: previewIsFlowchart ? flowchartPreviewTitleColor : previewTitleColor
    readonly property bool previewPortLabelsEnabled: !previewUsesCardinalNeutralFlowHandles
        && (root.canvasItem ? root.canvasItem.previewPortLabelsVisible() : false)
    readonly property string previewTypeId: String(previewPayload ? previewPayload.type_id || "" : "").trim()
    readonly property int previewTextRenderType: Text.CurveRendering

    function _scaledMetric(value, fallback) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            numeric = Number(fallback);
        return numeric * previewZoom;
    }

    function _portPoint(port, direction, rowIndex) {
        return GraphNodeSurfaceMetrics.localPortPointForPort(
            previewPayload,
            port,
            direction === "in" ? rowIndex : 0,
            direction === "out" ? rowIndex : 0
        );
    }

    visible: !!root.canvasItem && !!previewPayload && root.previewTypeId.length > 0
    z: 34
    x: root.canvasItem ? root.canvasItem.dropPreviewScreenX : -1
    y: root.canvasItem ? root.canvasItem.dropPreviewScreenY : -1
    width: root.canvasItem ? root.canvasItem.previewNodeScreenWidth() : 0
    height: root.canvasItem ? root.canvasItem.previewNodeScreenHeight() : 0
    radius: previewUsesHostChrome ? Math.max(4, 6 * previewZoom) : 0
    color: previewUsesHostChrome ? root.effectivePreviewFillColor : "transparent"
    border.width: previewUsesHostChrome ? 1 : 0
    border.color: root.effectivePreviewBorderColor
    clip: previewUsesHostChrome

    GraphPassiveComponents.FlowchartShapeCanvas {
        anchors.fill: parent
        visible: root.previewIsFlowchart && !root.previewUsesHostChrome
        variant: root.previewPayload ? root.previewPayload.surface_variant : ""
        fillColor: root.effectivePreviewFillColor
        strokeColor: root.effectivePreviewBorderColor
        strokeWidth: Math.max(1.0, root.previewZoom)
    }

    Item {
        id: titleBounds
        anchors.left: parent.left
        anchors.leftMargin: root._scaledMetric(root.previewMetrics.title_left_margin, 10.0)
        anchors.right: parent.right
        anchors.rightMargin: root._scaledMetric(root.previewMetrics.title_right_margin, 10.0)
        y: root._scaledMetric(root.previewMetrics.title_top, 4.0)
        height: root._scaledMetric(root.previewMetrics.title_height, 24.0)
    }

    Text {
        anchors.fill: titleBounds
        text: root.previewPayload
            ? String(root.previewPayload.display_name || root.previewTypeId || "")
            : ""
        color: root.effectivePreviewTitleColor
        font.bold: true
        font.pixelSize: Math.max(10, Math.min(16, 12 * root.previewZoom))
        horizontalAlignment: Boolean(root.previewMetrics.title_centered) ? Text.AlignHCenter : Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        renderType: root.previewTextRenderType
    }

    Repeater {
        model: root.canvasItem ? root.canvasItem.previewInputPorts() : []
        delegate: Item {
            readonly property var portPoint: root._portPoint(modelData, "in", index)
            readonly property real dotSize: root.previewUsesCardinalNeutralFlowHandles
                ? Math.max(4, Math.min(8, 6 * root.previewZoom))
                : Math.max(5, Math.min(10, 8 * root.previewZoom))
            x: 0
            y: portPoint.y * root.previewZoom - height * 0.5
            width: root.width
            height: Math.max(dotSize, 18 * root.previewZoom)

            Rectangle {
                id: inputDot
                objectName: "graphCanvasDropPreviewInputPortDot"
                x: portPoint.x * root.previewZoom - width * 0.5
                anchors.verticalCenter: parent.verticalCenter
                width: parent.dotSize
                height: parent.dotSize
                radius: width * 0.5
                color: root.previewUsesCardinalNeutralFlowHandles ? root.flowchartPreviewPortFillColor : "transparent"
                border.width: 1
                border.color: root.previewUsesCardinalNeutralFlowHandles
                    ? root.flowchartPreviewPortColor
                    : (root.canvasItem ? root.canvasItem.previewPortColor(modelData.kind) : root.previewLabelColor)
            }

            Text {
                objectName: "graphCanvasDropPreviewInputPortLabel"
                visible: root.previewPortLabelsEnabled
                anchors.verticalCenter: parent.verticalCenter
                x: Math.max(0, inputDot.x + inputDot.width + Math.max(4, 6 * root.previewZoom))
                width: Math.max(0, root.width - x - 4)
                text: String(modelData.label || modelData.key || "")
                color: root.previewLabelColor
                font.pixelSize: Math.max(7, Math.min(11, 10 * root.previewZoom))
                elide: Text.ElideRight
                renderType: root.previewTextRenderType
            }
        }
    }

    Repeater {
        model: root.canvasItem ? root.canvasItem.previewOutputPorts() : []
        delegate: Item {
            readonly property var portPoint: root._portPoint(modelData, "out", index)
            readonly property real dotSize: root.previewUsesCardinalNeutralFlowHandles
                ? Math.max(4, Math.min(8, 6 * root.previewZoom))
                : Math.max(5, Math.min(10, 8 * root.previewZoom))
            x: 0
            y: portPoint.y * root.previewZoom - height * 0.5
            width: root.width
            height: Math.max(dotSize, 18 * root.previewZoom)

            Rectangle {
                id: outputDot
                objectName: "graphCanvasDropPreviewOutputPortDot"
                x: portPoint.x * root.previewZoom - width * 0.5
                anchors.verticalCenter: parent.verticalCenter
                width: parent.dotSize
                height: parent.dotSize
                radius: width * 0.5
                color: root.previewUsesCardinalNeutralFlowHandles ? root.flowchartPreviewPortFillColor : "transparent"
                border.width: 1
                border.color: root.previewUsesCardinalNeutralFlowHandles
                    ? root.flowchartPreviewPortColor
                    : (root.canvasItem ? root.canvasItem.previewPortColor(modelData.kind) : root.previewLabelColor)
            }

            Text {
                objectName: "graphCanvasDropPreviewOutputPortLabel"
                visible: root.previewPortLabelsEnabled
                anchors.verticalCenter: parent.verticalCenter
                x: 4
                width: Math.max(0, outputDot.x - Math.max(4, 6 * root.previewZoom) - x)
                text: String(modelData.label || modelData.key || "")
                color: root.previewLabelColor
                font.pixelSize: Math.max(7, Math.min(11, 10 * root.previewZoom))
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideLeft
                renderType: root.previewTextRenderType
            }
        }
    }
}
