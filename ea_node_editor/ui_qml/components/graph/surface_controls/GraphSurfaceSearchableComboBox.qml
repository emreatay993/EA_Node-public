import QtQuick 2.15
import QtQuick.Controls 2.15
import "SurfaceControlGeometry.js" as SurfaceControlGeometry

FocusScope {
    id: control
    property Item host: null
    property Item rectItem: control
    property var model: []
    property var optionCodes: []
    property bool exactSelectors: false
    property var _syncedValue: ""
    property string _syncedText: ""
    property string placeholderText: ""
    property var selectedValue: ""
    property alias editText: editor.text
    property int currentIndex: -1
    property bool suppressTextHandling: false
    property bool externalHover: false
    property bool externalPressed: false
    property color textColor: host ? host.inlineInputTextColor : "#f0f2f5"
    property color fillColor: host ? host.inlineInputBackgroundColor : "#22242a"
    property color borderColor: host ? host.inlineInputBorderColor : "#4a4f5a"
    property color focusBorderColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color accentColor: host ? host.selectedOutlineColor : "#60CDFF"
    property color popupFillColor: Qt.darker(fillColor, 1.04)
    property color popupBorderColor: borderColor
    property color hoverOverlayColor: Qt.alpha(accentColor, 0.08)
    property color activeOverlayColor: Qt.alpha(accentColor, 0.10)
    property color pressedOverlayColor: Qt.alpha(accentColor, 0.18)
    property color hoverBorderColor: Qt.alpha(accentColor, 0.82)
    property color pressedBorderColor: accentColor
    property color disabledTextColor: Qt.alpha(textColor, 0.58)
    property color disabledFillColor: host && typeof host.inlineRowColor !== "undefined"
        ? host.inlineRowColor
        : Qt.darker(fillColor, 1.08)
    property color disabledBorderColor: disabledTextColor
    readonly property color resolvedTextColor: enabled ? textColor : disabledTextColor
    readonly property color resolvedBackgroundColor: enabled ? fillColor : disabledFillColor
    readonly property bool hoverVisualActive: enabled && (externalHover || controlHoverHandler.hovered || editor.hovered || indicatorMouseArea.containsMouse)
    readonly property bool pressedVisualActive: enabled && (indicatorMouseArea.pressed || externalPressed)
    readonly property bool activeVisualActive: enabled && (activeFocus || popup.visible)
    readonly property color resolvedStateOverlayColor: pressedVisualActive
        ? pressedOverlayColor
        : (activeVisualActive ? activeOverlayColor : (hoverVisualActive ? hoverOverlayColor : Qt.rgba(0, 0, 0, 0)))
    readonly property color resolvedBorderColor: pressedVisualActive
        ? pressedBorderColor
        : (activeVisualActive
            ? focusBorderColor
            : (hoverVisualActive ? hoverBorderColor : (enabled ? borderColor : disabledBorderColor)))
    readonly property real resolvedBorderWidth: activeVisualActive || hoverVisualActive || pressedVisualActive ? 1.5 : 1
    readonly property color resolvedIndicatorColor: enabled && (activeVisualActive || hoverVisualActive || pressedVisualActive)
        ? accentColor
        : resolvedTextColor
    readonly property var typography: host && host.graphSharedTypography ? host.graphSharedTypography : null
    readonly property int inlineFontPixelSize: {
        var numeric = Number(typography ? typography.inlinePropertyPixelSize : NaN);
        return isFinite(numeric) ? Math.round(numeric) : 10;
    }
    readonly property int inlineFontWeight: {
        var numeric = Number(typography ? typography.inlinePropertyFontWeight : NaN);
        return isFinite(numeric) ? Math.round(numeric) : Font.Normal;
    }
    readonly property var interactiveRect: SurfaceControlGeometry.rectFromItem(rectItem, host)
    readonly property var embeddedInteractiveRects: SurfaceControlGeometry.rectList(interactiveRect)
    readonly property real textFitWidth: {
        var requiredWidth = Number(selectedTextMetrics.advanceWidth) + 8.0 + 24.0;
        return isFinite(requiredWidth) && requiredWidth > 0.0
            ? Math.ceil(requiredWidth)
            : 0.0;
    }
    readonly property var optionValues: control._optionValues()
    readonly property string activeFilterText: String(editor.text || "")
    readonly property var filteredOptions: control._filteredOptionsFor(control.activeFilterText)
    readonly property real popupRowHeight: Math.max(
        24,
        Math.round(Math.max(control.height, control.inlineFontPixelSize + 10))
    )
    readonly property real popupWidth: Math.max(1, control.width)
    readonly property real popupMaxHeight: 160

    implicitHeight: 28
    activeFocusOnTab: enabled
    Accessible.name: "Searchable enum"
    Accessible.description: enabled
        ? "Choose one declared option. Type to search after focusing."
        : "Searchable enum disabled."

    signal accepted()
    signal activated(int index)
    signal valueActivated(var value)
    signal controlStarted()

    function _optionValues() {
        var values = [];
        var source = control.model;
        if (!source || source.length === undefined)
            return values;
        for (var index = 0; index < source.length; ++index)
            values.push(String(source[index]));
        return values;
    }

    function _normalizedText(value) {
        return String(value || "").toLowerCase();
    }

    function _optionIndex(value) {
        if (control.exactSelectors && control.optionCodes.length === control.optionValues.length)
            return control.optionCodes.indexOf(value);
        var normalizedValue = String(value || "");
        for (var index = 0; index < control.optionValues.length; ++index) {
            if (control.optionValues[index] === normalizedValue)
                return index;
        }
        return -1;
    }

    function labelForValue(value) {
        var index = control._optionIndex(value);
        if (control.exactSelectors && index >= 0)
            return control.optionValues[index];
        if (control.exactSelectors && typeof value === "number")
            return "Column " + String(value + 1);
        return value === undefined || value === null ? "" : String(value);
    }

    function _filteredOptionsFor(filterText) {
        var normalizedFilter = control._normalizedText(filterText).trim();
        var exactMatches = [];
        var prefixMatches = [];
        var containsMatches = [];
        for (var index = 0; index < control.optionValues.length; ++index) {
            var value = control.optionValues[index];
            var normalizedValue = control._normalizedText(value);
            var option = {
                "sourceIndex": index,
                "value": value
            };
            if (!normalizedFilter.length) {
                prefixMatches.push(option);
            } else if (normalizedValue === normalizedFilter) {
                exactMatches.push(option);
            } else if (normalizedValue.indexOf(normalizedFilter) === 0) {
                prefixMatches.push(option);
            } else if (normalizedValue.indexOf(normalizedFilter) >= 0) {
                containsMatches.push(option);
            }
        }
        return exactMatches.concat(prefixMatches, containsMatches).slice(0, 50);
    }

    function _filteredIndexForSourceIndex(sourceIndex) {
        for (var index = 0; index < control.filteredOptions.length; ++index) {
            var option = control.filteredOptions[index];
            if (option && option.sourceIndex === sourceIndex)
                return index;
        }
        return control.filteredOptions.length > 0 ? 0 : -1;
    }

    function _setEditTextSilently(value) {
        control.suppressTextHandling = true;
        editor.text = String(value || "");
        control.suppressTextHandling = false;
    }

    function _syncSelectionFromValue() {
        var nextIndex = control._optionIndex(control.selectedValue);
        if (control.currentIndex !== nextIndex)
            control.currentIndex = nextIndex;
        if (!editor.activeFocus) {
            control._syncedValue = control.selectedValue;
            control._syncedText = control.labelForValue(control.selectedValue);
            control._setEditTextSilently(control._syncedText);
        }
    }

    function _syncCurrentIndexFromEditText() {
        var nextIndex = control.optionValues.indexOf(editor.text);
        if (control.currentIndex !== nextIndex)
            control.currentIndex = nextIndex;
    }

    function _refreshPopup() {
        if (!editor.activeFocus) {
            popup.close();
            return;
        }
        if (control.filteredOptions.length > 0) {
            popup.open();
            optionsView.currentIndex = control._filteredIndexForSourceIndex(control.currentIndex);
        } else {
            popup.close();
        }
    }

    function _commitOption(option) {
        if (!option)
            return;
        var nextIndex = Number(option.sourceIndex);
        var nextValue = String(option.value || "");
        control._syncedText = nextValue;
        control._syncedValue = control.exactSelectors && control.optionCodes.length === control.optionValues.length
            ? control.optionCodes[nextIndex] : nextValue;
        control.currentIndex = nextIndex;
        control._setEditTextSilently(nextValue);
        popup.close();
        control.activated(nextIndex);
        control.valueActivated(control.exactSelectors && control.optionCodes.length === control.optionValues.length
            ? control.optionCodes[nextIndex] : nextValue);
        editor.forceActiveFocus();
        editor.selectAll();
    }

    Component.onCompleted: control._syncSelectionFromValue()
    onSelectedValueChanged: control._syncSelectionFromValue()
    onOptionCodesChanged: control._syncSelectionFromValue()
    onOptionValuesChanged: {
        control._syncSelectionFromValue();
        if (editor.activeFocus)
            control._refreshPopup();
    }
    onActiveFocusChanged: {
        if (!activeFocus && !popup.containsPress)
            popup.close();
    }

    TextMetrics {
        id: selectedTextMetrics
        font.pixelSize: control.inlineFontPixelSize
        font.weight: control.inlineFontWeight
        text: control.labelForValue(control.selectedValue) || control.placeholderText
    }

    HoverHandler {
        id: controlHoverHandler
        enabled: control.enabled
    }

    Rectangle {
        anchors.fill: parent
        radius: 5
        color: control.resolvedBackgroundColor
        border.width: control.resolvedBorderWidth
        border.color: control.resolvedBorderColor

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.resolvedStateOverlayColor
        }

        Behavior on border.color {
            ColorAnimation { duration: 90 }
        }

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }

    TextField {
        id: editor
        anchors.fill: parent
        leftPadding: 8
        rightPadding: 24
        topPadding: 4
        bottomPadding: 4
        enabled: control.enabled
        hoverEnabled: true
        selectByMouse: true
        color: control.resolvedTextColor
        selectionColor: control.focusBorderColor
        selectedTextColor: control.host ? control.host.surfaceColor : "#1b1d22"
        font.pixelSize: control.inlineFontPixelSize
        font.weight: control.inlineFontWeight
        verticalAlignment: Text.AlignVCenter
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
        background: null

        onTextChanged: {
            if (control.suppressTextHandling)
                return;
            control._syncCurrentIndexFromEditText();
            control._refreshPopup();
        }

        onActiveFocusChanged: {
            if (activeFocus) {
                control.controlStarted();
                control._refreshPopup();
            } else if (!popup.containsPress) {
                popup.close();
            }
        }

        onAccepted: {
            if (control.exactSelectors) {
                control.valueActivated(editor.text === control._syncedText ? control._syncedValue : editor.text);
                control.accepted();
                popup.close();
                return;
            }
            var nextOption = null;
            var exactIndex = control.optionValues.indexOf(editor.text);
            if (exactIndex >= 0) {
                nextOption = {
                    "sourceIndex": exactIndex,
                    "value": control.optionValues[exactIndex]
                };
            } else if (control.filteredOptions.length > 0) {
                nextOption = control.filteredOptions[0];
            }
            if (nextOption) {
                control._commitOption(nextOption);
                control.accepted();
            } else {
                control._setEditTextSilently(control.labelForValue(control.selectedValue));
                popup.close();
            }
        }

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Down) {
                control._refreshPopup();
                if (popup.visible) {
                    popup.containsPress = true;
                    popup.focus = true;
                    optionsView.forceActiveFocus();
                    if (optionsView.currentIndex < 0 && control.filteredOptions.length > 0)
                        optionsView.currentIndex = 0;
                    event.accepted = true;
                }
            } else if (event.key === Qt.Key_Escape && popup.visible) {
                popup.close();
                event.accepted = true;
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
        color: Qt.alpha(control.resolvedTextColor, 0.58)
        font.pixelSize: control.inlineFontPixelSize
        font.weight: control.inlineFontWeight
        elide: Text.ElideRight
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
        visible: !String(editor.text || "").length && String(control.placeholderText || "").length > 0
    }

    Text {
        id: indicator
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: "v"
        color: control.resolvedIndicatorColor
        font.pixelSize: control.inlineFontPixelSize
        font.weight: control.inlineFontWeight
        renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }

    MouseArea {
        id: indicatorMouseArea
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        width: 24
        enabled: control.enabled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            control.controlStarted();
            editor.forceActiveFocus();
            if (popup.visible)
                popup.close();
            else
                control._refreshPopup();
        }
    }

    Popup {
        id: popup
        property bool containsPress: false
        y: control.height + 2
        width: control.popupWidth
        implicitWidth: control.popupWidth
        implicitHeight: Math.min(contentItem.implicitHeight + padding * 2, control.popupMaxHeight + padding * 2)
        padding: 2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        onClosed: { containsPress = false; focus = false; }

        background: Rectangle {
            radius: 4
            color: control.popupFillColor
            border.width: 1
            border.color: control.popupBorderColor
        }

        contentItem: ListView {
            id: optionsView
            objectName: "graphSelectorOptions"
            clip: true
            implicitHeight: Math.min(contentHeight, control.popupMaxHeight)
            implicitWidth: control.popupWidth
            model: popup.visible ? control.filteredOptions : null
            currentIndex: control._filteredIndexForSourceIndex(control.currentIndex)
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                interactive: true
            }

            delegate: ItemDelegate {
                width: ListView.view ? ListView.view.width : control.popupWidth
                height: control.popupRowHeight
                padding: 0
                leftPadding: 8
                rightPadding: 8
                topPadding: 0
                bottomPadding: 0
                hoverEnabled: true
                highlighted: ListView.isCurrentItem
                readonly property bool optionPressedVisualActive: down
                readonly property bool optionHoverVisualActive: hovered || highlighted
                contentItem: Text {
                    text: modelData.value
                    color: optionHoverVisualActive ? control.accentColor : control.resolvedTextColor
                    font.pixelSize: control.inlineFontPixelSize
                    font.weight: control.inlineFontWeight
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    renderType: control.host ? control.host.nodeTextRenderType : Text.CurveRendering
                }
                background: Rectangle {
                    color: optionPressedVisualActive
                        ? Qt.alpha(control.accentColor, 0.28)
                        : (highlighted
                            ? Qt.alpha(control.accentColor, 0.20)
                            : (hovered ? Qt.alpha(control.accentColor, 0.12) : "transparent"))
                    radius: 3

                    Behavior on color {
                        ColorAnimation { duration: 70 }
                    }
                }
                onPressed: popup.containsPress = true
                onClicked: control._commitOption(modelData)
            }

            Keys.onPressed: function(event) {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                        && currentIndex >= 0
                        && currentIndex < control.filteredOptions.length) {
                    control._commitOption(control.filteredOptions[currentIndex]);
                    event.accepted = true;
                } else if (event.key === Qt.Key_Escape) {
                    popup.close();
                    editor.forceActiveFocus();
                    event.accepted = true;
                }
            }
        }
    }
}
