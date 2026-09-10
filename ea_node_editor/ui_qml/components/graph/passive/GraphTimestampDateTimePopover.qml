import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../common" as Common
import "../../common/TooltipCopy.js" as TooltipCopy

FocusScope {
    id: root
    objectName: "graphNodeTimestampDateTimePopover"

    property Item host: null
    property var themePalette: ({})
    property string _originalValueText: ""
    property int selectedYear: 2026
    property int selectedMonth: 0
    property int selectedDay: 1
    property string hourText: "00"
    property string minuteText: "00"
    property string secondText: "00"
    property real shadowStrength: 55
    property real shadowSoftness: 50
    property real shadowOffset: 4

    readonly property var embeddedInteractiveRects: []
    readonly property var tooltipPolicyBridge: root.host && root.host.canvasItem
        ? root.host.canvasItem.canvasStateBridgeRef
        : null
    readonly property var _monthNames: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    readonly property var _weekdayNames: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    readonly property color panelTextColor: root.themePalette.panel_title_fg || "#eef3ff"
    readonly property color mutedTextColor: root.themePalette.muted_fg || "#95a0b8"
    readonly property color fieldFillColor: root.themePalette.input_bg || "#151821"
    readonly property color fieldBorderColor: root.themePalette.input_border || root.themePalette.border || "#3a4355"
    readonly property color accentColor: root.themePalette.accent || "#5da9ff"

    signal accepted(string timestamp)
    signal canceled()

    visible: false
    implicitWidth: 330
    implicitHeight: dialogSurface.implicitHeight
    activeFocusOnTab: true

    function _pad(value) {
        var numeric = Math.max(0, Math.floor(Number(value || 0)));
        return numeric < 10 ? "0" + numeric : String(numeric);
    }

    function _daysInMonth(year, month) {
        return new Date(year, month + 1, 0).getDate();
    }

    function _clamp(value, minimum, maximum) {
        var numeric = parseInt(String(value || ""), 10);
        if (!isFinite(numeric))
            numeric = minimum;
        return Math.max(minimum, Math.min(maximum, numeric));
    }

    function _formatTimestamp(date) {
        return root._weekdayNames[date.getDay()] + " "
            + root._monthNames[date.getMonth()] + " "
            + root._pad(date.getDate()) + " "
            + date.getFullYear() + " "
            + root._pad(date.getHours()) + ":"
            + root._pad(date.getMinutes()) + ":"
            + root._pad(date.getSeconds());
    }

    function _parseTimestamp(value) {
        var text = String(value || "").trim();
        var monthLookup = {
            "jan": 0, "feb": 1, "mar": 2, "apr": 3, "may": 4, "jun": 5,
            "jul": 6, "aug": 7, "sep": 8, "oct": 9, "nov": 10, "dec": 11
        };
        var match = /^([A-Za-z]{3})\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})$/.exec(text);
        if (match) {
            var month = monthLookup[String(match[2]).toLowerCase()];
            if (month !== undefined)
                return new Date(
                    parseInt(match[4], 10),
                    month,
                    parseInt(match[3], 10),
                    parseInt(match[5], 10),
                    parseInt(match[6], 10),
                    parseInt(match[7], 10)
                );
        }
        var parsed = new Date(text);
        if (!isNaN(parsed.getTime()))
            return parsed;
        return new Date();
    }

    function _applyDate(date) {
        root.selectedYear = date.getFullYear();
        root.selectedMonth = date.getMonth();
        root.selectedDay = date.getDate();
        root.hourText = root._pad(date.getHours());
        root.minuteText = root._pad(date.getMinutes());
        root.secondText = root._pad(date.getSeconds());
    }

    function _selectedDate() {
        return new Date(
            root.selectedYear,
            root.selectedMonth,
            root.selectedDay,
            root._clamp(root.hourText, 0, 23),
            root._clamp(root.minuteText, 0, 59),
            root._clamp(root.secondText, 0, 59)
        );
    }

    function _gridDay(slot) {
        var firstWeekday = new Date(root.selectedYear, root.selectedMonth, 1).getDay();
        var day = Number(slot || 0) - firstWeekday + 1;
        if (day < 1 || day > root._daysInMonth(root.selectedYear, root.selectedMonth))
            return 0;
        return day;
    }

    function _shiftMonth(delta) {
        var next = new Date(root.selectedYear, root.selectedMonth + Number(delta || 0), 1);
        root.selectedYear = next.getFullYear();
        root.selectedMonth = next.getMonth();
        root.selectedDay = Math.min(root.selectedDay, root._daysInMonth(root.selectedYear, root.selectedMonth));
    }

    function openWithTimestamp(value) {
        root._originalValueText = String(value || "");
        root._applyDate(root._parseTimestamp(root._originalValueText));
        root.visible = true;
        Qt.callLater(function() {
            hourField.forceActiveFocus();
            hourField.selectAll();
        });
    }

    function acceptEdit() {
        root.hourText = root._pad(root._clamp(root.hourText, 0, 23));
        root.minuteText = root._pad(root._clamp(root.minuteText, 0, 59));
        root.secondText = root._pad(root._clamp(root.secondText, 0, 59));
        root.visible = false;
        root.accepted(root._formatTimestamp(root._selectedDate()));
    }

    function cancelEdit() {
        root._applyDate(root._parseTimestamp(root._originalValueText));
        root.visible = false;
        root.canceled();
    }

    function closeSilently() {
        root.visible = false;
    }

    Keys.onEscapePressed: root.cancelEdit()

    Common.DialogSurface {
        id: dialogSurface
        anchors.fill: parent
        themePalette: root.themePalette
        title: "Date & Time"
        closeButtonVisible: true
        onCloseRequested: root.cancelEdit()

        ColumnLayout {
            id: contentColumn
            Layout.fillWidth: true
            Layout.margins: 16
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Common.DialogButton {
                    id: previousMonthButton
                    objectName: "graphNodeTimestampPreviousMonthButton"
                    Layout.preferredWidth: 36
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: "‹"
                    property string tooltipText: TooltipCopy.text(
                        tooltipCopyBridge,
                        "fullscreen.timestamp.previous_month"
                    )
                    Accessible.name: tooltipText
                    onClicked: root._shiftMonth(-1)

                    Common.ManagedToolTip {
                        policyBridge: root.tooltipPolicyBridge
                        category: "general"
                        active: previousMonthButton.hovered
                        text: previousMonthButton.tooltipText
                    }
                }

                Text {
                    objectName: "graphNodeTimestampMonthLabel"
                    Layout.fillWidth: true
                    text: root._monthNames[root.selectedMonth] + " " + root.selectedYear
                    color: root.panelTextColor
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Common.DialogButton {
                    id: nextMonthButton
                    objectName: "graphNodeTimestampNextMonthButton"
                    Layout.preferredWidth: 36
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: "›"
                    property string tooltipText: TooltipCopy.text(
                        tooltipCopyBridge,
                        "fullscreen.timestamp.next_month"
                    )
                    Accessible.name: tooltipText
                    onClicked: root._shiftMonth(1)

                    Common.ManagedToolTip {
                        policyBridge: root.tooltipPolicyBridge
                        category: "general"
                        active: nextMonthButton.hovered
                        text: nextMonthButton.tooltipText
                    }
                }
            }

            GridLayout {
                id: weekdayHeader
                objectName: "graphNodeTimestampWeekdayHeader"
                Layout.fillWidth: true
                columns: 7
                columnSpacing: 4
                rowSpacing: 2

                Repeater {
                    model: root._weekdayNames
                    Text {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 16
                        text: String(modelData)
                        color: root.mutedTextColor
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            GridLayout {
                id: calendarGrid
                objectName: "graphNodeTimestampCalendarGrid"
                Layout.fillWidth: true
                columns: 7
                columnSpacing: 4
                rowSpacing: 4

                Repeater {
                    model: 42

                    Rectangle {
                        id: dayCell
                        property int dayNumber: root._gridDay(index)
                        property bool selected: dayNumber === root.selectedDay
                        objectName: dayNumber > 0 ? "graphNodeTimestampDayButton_" + dayNumber : "graphNodeTimestampDaySlot"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        radius: 4
                        color: dayNumber <= 0
                            ? "transparent"
                            : (selected ? Qt.alpha(root.accentColor, 0.32) : root.fieldFillColor)
                        border.width: dayNumber > 0 ? 1 : 0
                        border.color: selected ? root.accentColor : root.fieldBorderColor

                        Text {
                            anchors.centerIn: parent
                            text: dayCell.dayNumber > 0 ? String(dayCell.dayNumber) : ""
                            color: dayCell.selected ? root.panelTextColor : root.mutedTextColor
                            font.pixelSize: 11
                            font.weight: dayCell.selected ? Font.DemiBold : Font.Normal
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: dayCell.dayNumber > 0
                            hoverEnabled: true
                            onClicked: root.selectedDay = dayCell.dayNumber
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Common.DialogTextField {
                    id: hourField
                    objectName: "graphNodeTimestampHourField"
                    Layout.preferredWidth: 44
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: root.hourText
                    horizontalAlignment: TextInput.AlignHCenter
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 0; top: 23 }
                    Accessible.name: "Hour"
                    onTextChanged: root.hourText = text
                }

                Text {
                    text: ":"
                    color: root.panelTextColor
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Common.DialogTextField {
                    id: minuteField
                    objectName: "graphNodeTimestampMinuteField"
                    Layout.preferredWidth: 44
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: root.minuteText
                    horizontalAlignment: TextInput.AlignHCenter
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 0; top: 59 }
                    Accessible.name: "Minute"
                    onTextChanged: root.minuteText = text
                }

                Text {
                    text: ":"
                    color: root.panelTextColor
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Common.DialogTextField {
                    id: secondField
                    objectName: "graphNodeTimestampSecondField"
                    Layout.preferredWidth: 44
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: root.secondText
                    horizontalAlignment: TextInput.AlignHCenter
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 0; top: 59 }
                    Accessible.name: "Second"
                    onTextChanged: root.secondText = text
                }

                Item { Layout.fillWidth: true }

                Common.DialogButton {
                    id: cancelButton
                    objectName: "graphNodeTimestampCancelButton"
                    Layout.preferredWidth: 58
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: "Cancel"
                    onClicked: root.cancelEdit()
                }

                Common.DialogButton {
                    id: okButton
                    objectName: "graphNodeTimestampOkButton"
                    Layout.preferredWidth: 48
                    controlHeight: 32
                    themePalette: root.themePalette
                    text: "OK"
                    primary: true
                    onClicked: root.acceptEdit()
                }
            }
        }
    }
}
