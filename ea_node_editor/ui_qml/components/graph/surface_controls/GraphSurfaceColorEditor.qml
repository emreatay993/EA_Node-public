import QtQuick 2.15
import QtQuick.Layouts 1.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry
import "../../common/TooltipCopy.js" as TooltipCopy

Item {
    id: root
    property Item host: null
    property string propertyKey: ""
    property string committedText: ""
    property string fieldObjectName: "graphSurfaceColorEditorField"
    property string pickButtonObjectName: "graphSurfaceColorPickerButton"
    property var colorResolver: null
    readonly property string text: colorField.text
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.combineRectLists(
        [colorField.embeddedInteractiveRects, pickButton.embeddedInteractiveRects]
    )
    readonly property real textFitWidth: {
        var requiredWidth = Number(colorField.textFitWidth)
            + Number(editorRow.spacing)
            + 26.0;
        return isFinite(requiredWidth) && requiredWidth > 0.0
            ? Math.ceil(requiredWidth)
            : 0.0;
    }
    implicitWidth: editorRow.implicitWidth
    implicitHeight: editorRow.implicitHeight

    signal controlStarted()
    signal commitRequested(string text)

    function _normalizedText(value) {
        return String(value || "").trim();
    }

    function _hasValidColor(value) {
        return /^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(root._normalizedText(value));
    }

    function _swatchFillColor(value) {
        return root._hasValidColor(value)
            ? root._normalizedText(value)
            : "transparent";
    }

    function _swatchBorderColor() {
        return root.host ? root.host.inlineInputBorderColor : "#4a4f5a";
    }

    function _resolvePickedColor(currentValue) {
        if (typeof colorResolver !== "function")
            return "";
        return String(colorResolver(String(currentValue || "")) || "");
    }

    function syncTextToCommitted() {
        if (colorField.text !== committedText)
            colorField.text = committedText;
    }

    function pickColor() {
        var selectedColor = root._resolvePickedColor(colorField.text);
        if (!selectedColor.length)
            return;
        if (colorField.text !== selectedColor)
            colorField.text = selectedColor;
        root.commitRequested(colorField.text);
    }

    onCommittedTextChanged: {
        if (!colorField.activeFocus)
            syncTextToCommitted();
    }

    Component.onCompleted: syncTextToCommitted()

    RowLayout {
        id: editorRow
        anchors.fill: parent
        spacing: 6

        GraphSurfaceButton {
            id: pickButton
            objectName: root.pickButtonObjectName
            property string propertyKey: root.propertyKey
            visible: root.visible
            enabled: root.enabled
            host: root.host
            iconOnly: true
            text: ""
            tooltipText: TooltipCopy.text(tooltipCopyBridge, "graph.surface_color.pick_color")
            tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "graph.surface_color.pick_color")
            baseFillColor: root._swatchFillColor(colorField.text)
            hoverFillColor: root._swatchFillColor(colorField.text)
            pressedFillColor: root._swatchFillColor(colorField.text)
            baseBorderColor: root._swatchBorderColor()
            hoverBorderColor: root.host ? root.host.selectedOutlineColor : "#60CDFF"
            pressedBorderColor: root.host ? root.host.selectedOutlineColor : "#60CDFF"
            foregroundColor: "transparent"
            disabledForegroundColor: "transparent"
            contentHorizontalPadding: 0
            contentVerticalPadding: 0
            Layout.preferredWidth: 26
            Layout.minimumWidth: 26
            Layout.maximumWidth: 26
            onControlStarted: root.controlStarted()
            onClicked: root.pickColor()
        }

        GraphSurfaceTextField {
            id: colorField
            objectName: root.fieldObjectName
            property string propertyKey: root.propertyKey
            Layout.fillWidth: true
            visible: root.visible
            enabled: root.enabled
            host: root.host
            onControlStarted: root.controlStarted()
            onAccepted: root.commitRequested(text)
            onEditingFinished: root.commitRequested(text)
        }
    }
}
