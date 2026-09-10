import QtQuick 2.15
import QtQuick.Controls 2.15

FocusScope {
    id: control
    property var pane
    property var model: []
    property var optionCodes: []
    property bool exactSelectors: false
    property var _syncedValue: ""
    property string _syncedText: ""
    property string placeholderText: ""
    property var selectedValue: ""
    property alias editText: editor.text
    property int currentIndex: -1
    property bool previewValueAsFontFamily: false
    property string defaultFontFamilyLabel: "Default"
    readonly property real popupMaxHeight: 240
    readonly property bool popupInteractionActive: popup.containsPress
    readonly property var optionValues: control._optionValues()
    readonly property int optionCount: control.optionValues.length
    readonly property string firstOptionValue: control.optionValues.length > 0 ? control.optionValues[0] : ""
    readonly property string secondOptionValue: control.optionValues.length > 1 ? control.optionValues[1] : ""
    readonly property string activeFilterText: String(editor.text || "")
    readonly property var filteredOptions: control._filteredOptionsFor(control.activeFilterText)
    property bool suppressTextHandling: false
    implicitHeight: 34

    signal accepted()
    signal activated(int index)
    signal valueActivated(var value)

    function _optionValues() {
        var values = []
        var source = control.model
        if (!source || source.length === undefined)
            return values
        for (var index = 0; index < source.length; ++index)
            values.push(String(source[index]))
        return values
    }

    function _normalizedText(value) {
        return String(value || "").toLowerCase()
    }

    function _previewFontFamily(value) {
        var text = String(value || "")
        if (!control.previewValueAsFontFamily || text === control.defaultFontFamilyLabel)
            return Qt.application.font.family
        return text
    }

    function _optionIndex(value) {
        if (control.exactSelectors && control.optionCodes.length === control.optionValues.length)
            return control.optionCodes.indexOf(value)
        var normalizedValue = String(value || "")
        for (var index = 0; index < control.optionValues.length; ++index) {
            if (control.optionValues[index] === normalizedValue)
                return index
        }
        return -1
    }

    function labelForValue(value) {
        var index = control._optionIndex(value)
        if (control.exactSelectors && index >= 0)
            return control.optionValues[index]
        if (control.exactSelectors && typeof value === "number")
            return "Column " + String(value + 1)
        return value === undefined || value === null ? "" : String(value)
    }

    function valueForText(value) {
        return control.exactSelectors && String(value) === control._syncedText
            ? control._syncedValue : String(value)
    }

    function _filteredOptionsFor(filterText) {
        var normalizedFilter = control._normalizedText(filterText).trim()
        var exactMatches = []
        var prefixMatches = []
        var containsMatches = []
        for (var index = 0; index < control.optionValues.length; ++index) {
            var value = control.optionValues[index]
            var normalizedValue = control._normalizedText(value)
            var option = {
                "sourceIndex": index,
                "value": value
            }
            if (!normalizedFilter.length) {
                prefixMatches.push(option)
            } else if (normalizedValue === normalizedFilter) {
                exactMatches.push(option)
            } else if (normalizedValue.indexOf(normalizedFilter) === 0) {
                prefixMatches.push(option)
            } else if (normalizedValue.indexOf(normalizedFilter) >= 0) {
                containsMatches.push(option)
            }
        }
        return exactMatches.concat(prefixMatches, containsMatches).slice(0, 50)
    }

    function _filteredIndexForSourceIndex(sourceIndex) {
        for (var index = 0; index < control.filteredOptions.length; ++index) {
            var option = control.filteredOptions[index]
            if (option && option.sourceIndex === sourceIndex)
                return index
        }
        return control.filteredOptions.length > 0 ? 0 : -1
    }

    function _setEditTextSilently(value) {
        control.suppressTextHandling = true
        editor.text = String(value || "")
        control.suppressTextHandling = false
    }

    function _syncSelectionFromValue() {
        var nextIndex = control._optionIndex(control.selectedValue)
        if (control.currentIndex !== nextIndex)
            control.currentIndex = nextIndex
        if (!editor.activeFocus) {
            control._syncedValue = control.selectedValue
            control._syncedText = control.labelForValue(control.selectedValue)
            control._setEditTextSilently(control._syncedText)
        }
    }

    function _syncCurrentIndexFromEditText() {
        var nextIndex = control.optionValues.indexOf(editor.text)
        if (control.currentIndex !== nextIndex)
            control.currentIndex = nextIndex
    }

    function _refreshPopup() {
        if (!editor.activeFocus) {
            popup.close()
            return
        }
        if (control.filteredOptions.length > 0) {
            popup.open()
            optionsView.currentIndex = control._filteredIndexForSourceIndex(control.currentIndex)
        } else {
            popup.close()
        }
    }

    function _commitOption(option) {
        if (!option)
            return
        var nextIndex = Number(option.sourceIndex)
        var nextValue = String(option.value || "")
        control._syncedText = nextValue
        control._syncedValue = control.exactSelectors && control.optionCodes.length === control.optionValues.length
            ? control.optionCodes[nextIndex] : nextValue
        control.currentIndex = nextIndex
        control._setEditTextSilently(nextValue)
        popup.close()
        control.activated(nextIndex)
        control.valueActivated(control.exactSelectors && control.optionCodes.length === control.optionValues.length
            ? control.optionCodes[nextIndex] : nextValue)
        editor.forceActiveFocus()
        editor.selectAll()
    }

    Component.onCompleted: control._syncSelectionFromValue()
    onSelectedValueChanged: control._syncSelectionFromValue()
    onOptionCodesChanged: control._syncSelectionFromValue()
    onOptionValuesChanged: {
        control._syncSelectionFromValue()
        if (editor.activeFocus)
            control._refreshPopup()
    }
    onActiveFocusChanged: {
        if (!activeFocus && !popup.containsPress)
            popup.close()
    }

    Rectangle {
        anchors.fill: parent
        radius: 9
        color: control.pane.themePalette.input_bg
        border.color: control.activeFocus ? control.pane.themePalette.accent : control.pane.themePalette.input_border
        border.width: 1
    }

    TextField {
        id: editor
        anchors.fill: parent
        leftPadding: 8
        rightPadding: 30
        topPadding: 8
        bottomPadding: 8
        enabled: control.enabled
        selectByMouse: true
        color: control.pane.themePalette.input_fg
        selectionColor: control.pane.selectedSurfaceColor
        selectedTextColor: control.pane.themePalette.panel_title_fg
        font.pixelSize: 11
        font.family: control._previewFontFamily(editor.text)
        verticalAlignment: Text.AlignVCenter
        background: null

        onTextChanged: {
            if (control.suppressTextHandling)
                return
            control._syncCurrentIndexFromEditText()
            control._refreshPopup()
        }

        onActiveFocusChanged: {
            if (activeFocus) {
                control._refreshPopup()
            } else if (!popup.containsPress) {
                popup.close()
            }
        }

        onAccepted: {
            popup.close()
            control.accepted()
        }

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Down) {
                control._refreshPopup()
                if (popup.visible) {
                    popup.containsPress = true
                    popup.focus = true
                    optionsView.forceActiveFocus()
                    if (optionsView.currentIndex < 0 && control.filteredOptions.length > 0)
                        optionsView.currentIndex = 0
                    event.accepted = true
                }
            } else if (event.key === Qt.Key_Escape && popup.visible) {
                popup.close()
                event.accepted = true
            }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.right: indicator.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 8
        anchors.rightMargin: 6
        text: control.placeholderText
        color: control.pane.themePalette.muted_fg
        font.pixelSize: 11
        elide: Text.ElideRight
        visible: !String(editor.text || "").length && String(control.placeholderText || "").length > 0
    }

    Text {
        id: indicator
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        color: control.pane.themePalette.muted_fg
        font.pixelSize: 11
        font.bold: true
    }

    MouseArea {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        width: 26
        enabled: control.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            editor.forceActiveFocus()
            if (popup.visible) {
                popup.close()
            } else {
                control._refreshPopup()
            }
        }
    }

    Popup {
        id: popup
        property bool containsPress: false
        y: control.height + 4
        width: control.width
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        onClosed: { containsPress = false; focus = false; }

        background: Rectangle {
            radius: 9
            color: control.pane.cardBackgroundColor
            border.color: control.pane.themePalette.input_border
            border.width: 1
        }

        contentItem: ListView {
            id: optionsView
            objectName: "inspectorSelectorOptions"
            clip: true
            implicitHeight: Math.min(contentHeight, control.popupMaxHeight)
            model: popup.visible ? control.filteredOptions : null
            currentIndex: control._filteredIndexForSourceIndex(control.currentIndex)
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                interactive: true
            }

            delegate: ItemDelegate {
                width: ListView.view ? ListView.view.width : control.width
                highlighted: ListView.isCurrentItem
                contentItem: Text {
                    text: modelData.value
                    color: highlighted ? control.pane.themePalette.panel_title_fg : control.pane.themePalette.input_fg
                    font.pixelSize: 11
                    font.family: control._previewFontFamily(modelData.value)
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    color: highlighted ? control.pane.selectedSurfaceColor : "transparent"
                    radius: 7
                }
                onPressed: popup.containsPress = true
                onClicked: control._commitOption(modelData)
            }

            Keys.onPressed: function(event) {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        && currentIndex >= 0
                        && currentIndex < control.filteredOptions.length) {
                    control._commitOption(control.filteredOptions[currentIndex])
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    popup.close()
                    editor.forceActiveFocus()
                    event.accepted = true
                }
            }
        }
    }
}
