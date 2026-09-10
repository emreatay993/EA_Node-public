import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    property Item host: null
    property string propertyKey: ""
    property var values: []
    property string itemType: "str"
    property var enumValues: []
    property var enumCodes: []
    property bool exactSelectors: false
    property var minimum: null
    property var maximum: null
    property real stepSize: 0
    property bool editorEnabled: true
    property bool _syncing: false
    property bool _ready: false
    readonly property int itemCount: itemModel.count
    signal controlStarted()
    signal commitRequested(var value)

    function syncModel() {
        if (_syncing)
            return;
        _syncing = true;
        itemModel.clear();
        itemModel.dynamicRoles = root.exactSelectors;
        var source = [];
        try {
            var normalized = JSON.parse(JSON.stringify(values || []));
            if (normalized instanceof Array)
                source = normalized;
        } catch (error) {
            source = [];
        }
        for (var index = 0; index < source.length; index++)
            itemModel.append({"itemValue": source[index]});
        _syncing = false;
    }

    function snapshot() {
        var result = [];
        for (var index = 0; index < itemModel.count; index++)
            result.push(itemModel.get(index).itemValue);
        return result;
    }

    function setItem(index, value) {
        itemModel.setProperty(index, "itemValue", value);
        commitRequested(snapshot());
    }

    function defaultItem() {
        if (exactSelectors)
            return enumCodes.length > 0 ? enumCodes[0] : "";
        if (itemType === "enum")
            return enumCodes.length > 0 ? enumCodes[0] : 0;
        if (itemType === "int" || itemType === "float")
            return minimum !== null && isFinite(Number(minimum)) ? Number(minimum) : 0;
        if (itemType === "color")
            return "#1f77b4";
        return "";
    }

    onValuesChanged: if (_ready) syncModel()
    onExactSelectorsChanged: if (_ready) syncModel()
    Component.onCompleted: { _ready = true; syncModel(); }

    ListModel { id: itemModel }

    ListView {
        id: listView
        objectName: "graphSurfaceListView"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: addButton.top
        anchors.bottomMargin: 4
        clip: true
        spacing: 3
        model: itemModel
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Row {
            width: listView.width
            height: 28
            spacing: 4

            Loader {
                width: Math.max(20, parent.width - removeButton.width - parent.spacing)
                height: parent.height
                visible: root.itemType !== "color"
                sourceComponent: root.exactSelectors ? searchableComponent : root.itemType === "enum"
                    ? enumComponent
                    : ((root.itemType === "int" || root.itemType === "float")
                        && root.minimum !== null && root.maximum !== null
                        ? sliderComponent
                        : valueComponent)
            }

            GraphSurfaceColorEditor {
                objectName: "graphSurfaceListColorEditor"
                width: Math.max(20, parent.width - removeButton.width - parent.spacing)
                height: parent.height
                visible: root.itemType === "color"
                enabled: root.editorEnabled
                host: root.host
                propertyKey: root.propertyKey
                committedText: String(itemValue)
                fieldObjectName: "graphSurfaceListColorField"
                pickButtonObjectName: "graphSurfaceListColorPickerButton"
                colorResolver: function(currentValue) {
                    return root.host && root.host.pickNodePropertyColor
                        ? root.host.pickNodePropertyColor(root.propertyKey, currentValue)
                        : "";
                }
                onControlStarted: root.controlStarted()
                onCommitRequested: function(value) { root.setItem(index, value); }
            }

            GraphSurfaceButton {
                id: removeButton
                objectName: "graphSurfaceListRemoveButton"
                width: 28
                height: parent.height
                enabled: root.editorEnabled
                host: root.host
                focusPolicy: Qt.TabFocus
                text: "-"
                Accessible.name: "Remove list item " + String(index + 1)
                onPressed: root.controlStarted()
                onClicked: {
                    itemModel.remove(index);
                    root.commitRequested(root.snapshot());
                }
            }

            Component {
                id: searchableComponent
                GraphSurfaceSearchableComboBox {
                    objectName: "graphSurfaceListSearchableEditor"
                    width: parent ? parent.width : 100
                    height: parent ? parent.height : 28
                    enabled: root.editorEnabled
                    host: root.host
                    model: root.enumValues
                    optionCodes: root.enumCodes
                    exactSelectors: true
                    selectedValue: itemValue
                    Accessible.name: "List item " + String(index + 1)
                    onControlStarted: root.controlStarted()
                    onValueActivated: function(value) { root.setItem(index, value); }
                }
            }

            Component {
                id: enumComponent
                GraphSurfaceComboBox {
                    width: parent ? parent.width : 100
                    height: parent ? parent.height : 28
                    enabled: root.editorEnabled
                    host: root.host
                    model: root.enumValues
                    currentIndex: root.enumCodes.indexOf(itemValue)
                    displayText: currentIndex >= 0 ? String(root.enumValues[currentIndex]) : ""
                    Accessible.name: "List item " + String(index + 1)
                    onControlStarted: root.controlStarted()
                    onActivated: function(selectedIndex) {
                        if (selectedIndex >= 0 && selectedIndex < root.enumCodes.length)
                            root.setItem(index, root.enumCodes[selectedIndex]);
                    }
                }
            }

            Component {
                id: valueComponent
                GraphSurfaceTextField {
                    width: parent ? parent.width : 100
                    height: parent ? parent.height : 28
                    enabled: root.editorEnabled
                    host: root.host
                    text: String(itemValue)
                    inputMethodHints: root.itemType === "int" || root.itemType === "float"
                        ? Qt.ImhFormattedNumbersOnly : Qt.ImhNone
                    Accessible.name: "List item " + String(index + 1)
                    onControlStarted: root.controlStarted()
                    onEditingFinished: {
                        var next = text;
                        if (root.itemType === "int")
                            next = Math.round(Number(text));
                        else if (root.itemType === "float")
                            next = Number(text);
                        if ((root.itemType === "int" || root.itemType === "float") && !isFinite(next))
                            return;
                        root.setItem(index, next);
                    }
                }
            }

            Component {
                id: sliderComponent
                GraphSurfaceSlider {
                    width: parent ? parent.width : 100
                    height: parent ? parent.height : 28
                    enabled: root.editorEnabled
                    host: root.host
                    from: Number(root.minimum)
                    to: Number(root.maximum)
                    stepSize: root.stepSize > 0 ? root.stepSize : (root.itemType === "int" ? 1 : 0)
                    valueType: root.itemType
                    value: Number(itemValue)
                    showRangeCaptions: false
                    Accessible.name: "List item " + String(index + 1)
                    onControlStarted: root.controlStarted()
                    onCommitRequested: function(value) {
                        root.setItem(index, root.itemType === "int" ? Math.round(value) : value);
                    }
                }
            }
        }
    }

    GraphSurfaceButton {
        id: addButton
        objectName: "graphSurfaceListAddButton"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 26
        enabled: root.editorEnabled
        host: root.host
        focusPolicy: Qt.TabFocus
        text: "+ Add"
        Accessible.name: "Add list item"
        onPressed: root.controlStarted()
        onClicked: {
            itemModel.append({"itemValue": root.defaultItem()});
            root.commitRequested(root.snapshot());
        }
    }
}
