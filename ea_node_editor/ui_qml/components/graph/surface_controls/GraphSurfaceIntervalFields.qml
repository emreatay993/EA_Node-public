import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    property Item host: null
    property string propertyKey: ""
    property var value: null
    property bool editorEnabled: true
    signal controlStarted()
    signal commitRequested(var value)

    function syncFields() {
        startField.text = value && value.start !== undefined ? String(value.start) : "";
        endField.text = value && value.end !== undefined ? String(value.end) : "";
    }

    function commitFields() {
        var start = Number(startField.text);
        var end = Number(endField.text);
        if (startField.text.length > 0 && endField.text.length > 0
                && isFinite(start) && isFinite(end) && start < end)
            commitRequested({"start": start, "end": end});
    }

    onValueChanged: syncFields()
    Component.onCompleted: syncFields()

    Row {
        anchors.fill: parent
        spacing: 4

        GraphSurfaceTextField {
            id: startField
            objectName: "graphSurfaceIntervalStartField"
            width: Math.max(40, (parent.width - autoButton.width - parent.spacing * 2) * 0.5)
            height: parent.height
            enabled: root.editorEnabled
            host: root.host
            placeholderText: "Auto start"
            inputMethodHints: Qt.ImhFormattedNumbersOnly
    Accessible.name: "Interval start"
            onControlStarted: root.controlStarted()
            onAccepted: root.commitFields()
            onEditingFinished: root.commitFields()
        }

        GraphSurfaceTextField {
            id: endField
            objectName: "graphSurfaceIntervalEndField"
            width: startField.width
            height: parent.height
            enabled: root.editorEnabled
            host: root.host
            placeholderText: "Auto end"
            inputMethodHints: Qt.ImhFormattedNumbersOnly
            Accessible.name: "Interval end"
            onControlStarted: root.controlStarted()
            onAccepted: root.commitFields()
            onEditingFinished: root.commitFields()
        }

        GraphSurfaceButton {
            id: autoButton
            objectName: "graphSurfaceIntervalAutoButton"
            width: 44
            height: parent.height
            enabled: root.editorEnabled
            host: root.host
            focusPolicy: Qt.TabFocus
            text: "Auto"
            Accessible.name: "Use automatic interval"
            onPressed: root.controlStarted()
            onClicked: root.commitRequested(null)
        }
    }
}
