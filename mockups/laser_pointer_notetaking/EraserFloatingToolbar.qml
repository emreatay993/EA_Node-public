import QtQuick

// Floating eraser-options toolbar: a type dropdown (Standard / Stroke) with a
// popover of big option cards, three transparency-checker size swatches, and
// an eraser-settings popover (Erase Highlighter Only, Auto-Deselect, Clear
// Page). Pure prototype UI - selections only feed the status line through
// optionChanged().
Item {
    id: root
    objectName: "eraserFloatingToolbar"

    property real toolbarScale: 1.0
    property string selectedType: "standard"
    property int selectedSizeIndex: 2
    property bool typePopupOpen: false
    property bool settingsPopupOpen: false
    property bool eraseHighlighterOnly: false
    property bool autoDeselect: false
    // Window-edge clamp for the popovers, mapped into this item's coords by
    // the host (the popovers are wider than the pill and may extend past it).
    property real viewportLeft: -10000
    property real viewportRight: 10000

    signal optionChanged(string summary)

    readonly property color shellBg: "#202023"
    readonly property color shellBorder: "#22ffffff"
    readonly property color popupBg: "#1f2023"
    readonly property color controlBg: "#2f2f34"
    readonly property color hoverBg: "#3a3a40"
    readonly property color cardBg: "#2c2c31"
    readonly property color fg: "#f5f5f7"
    readonly property color mutedFg: "#9a9aa0"
    readonly property color selectionBlue: "#1788ff"
    readonly property color eraserTipBlue: "#b7e3f6"
    readonly property color eraserBodyWhite: "#f2f4f6"
    readonly property color clearRed: "#eb5440"

    readonly property var eraserTypes: [
        { "typeId": "standard", "label": "Standard", "cardLabel": "Standard\nEraser",
          "description": "Efficient erasing without leaving any marks" },
        { "typeId": "stroke", "label": "Stroke", "cardLabel": "Stroke\nEraser",
          "description": "Erase entire strokes by touching them once" }
    ]
    // Preview diameters of the three eraser sizes; the largest matches the
    // pill height so it kisses the toolbar edges like the reference.
    readonly property var sizeDiameters: [ 34, 54, 74 ]

    readonly property int toolbarHeight: Math.round(76 * toolbarScale)
    readonly property int rowHeight: Math.round(58 * toolbarScale)
    readonly property real popupScale: Math.max(0.68, Math.min(1.0, toolbarScale))
    readonly property int popupPad: Math.round(28 * popupScale)
    readonly property int popupTitleSize: Math.round(24 * popupScale)
    readonly property int typePopupWidth: Math.round(560 * popupScale)
    readonly property int typePopupHeight: Math.round(318 * popupScale)
    readonly property int cardSize: Math.round(158 * popupScale)
    readonly property int cardGap: Math.round(16 * popupScale)
    readonly property int cardGlyphSize: Math.round(46 * popupScale)
    readonly property int cardLabelSize: Math.round(20 * popupScale)
    readonly property int descriptionSize: Math.round(17 * popupScale)
    readonly property int settingsPopupWidth: Math.round(580 * popupScale)
    readonly property int settingsLabelSize: Math.round(20 * popupScale)

    implicitWidth: shellRow.implicitWidth + Math.round(28 * toolbarScale)
    width: implicitWidth
    height: typePopup.visible ? typePopup.y + typePopup.height
        : settingsPopup.visible ? settingsPopup.y + settingsPopup.height
        : toolbarShell.height

    // Close any open popover when the host hides us (tool switch).
    onVisibleChanged: {
        if (!visible) {
            root.typePopupOpen = false;
            root.settingsPopupOpen = false;
        }
    }

    function typeData(typeId) {
        var id = String(typeId || "");
        for (var i = 0; i < root.eraserTypes.length; i++) {
            if (root.eraserTypes[i].typeId === id)
                return root.eraserTypes[i];
        }
        return root.eraserTypes[0];
    }

    function chooseType(typeId) {
        root.selectedType = String(typeData(typeId).typeId);
        root.optionChanged(typeData(typeId).label + " Eraser selected");
    }

    function chooseSize(index) {
        root.selectedSizeIndex = Math.max(0, Math.min(root.sizeDiameters.length - 1, index));
        root.optionChanged(typeData(root.selectedType).label + " eraser, size "
            + (root.selectedSizeIndex + 1) + " of " + root.sizeDiameters.length);
    }

    function toggleTypePopup() {
        root.settingsPopupOpen = false;
        root.typePopupOpen = !root.typePopupOpen;
    }

    function toggleSettingsPopup() {
        root.typePopupOpen = false;
        root.settingsPopupOpen = !root.settingsPopupOpen;
    }

    function clampPopupX(centerX, popupWidth) {
        var x = centerX - popupWidth / 2;
        x = Math.min(x, root.viewportRight - popupWidth);
        x = Math.max(x, root.viewportLeft);
        return Math.round(x);
    }

    // Tilted rubber block with a band separating the light-blue tip from the
    // white body. filled=false renders the white line-art variant used by the
    // unselected type card.
    component EraserGlyph: Canvas {
        id: glyph
        property bool filled: true
        property color lineColor: root.fg

        width: 42
        height: 42
        antialiasing: true

        onFilledChanged: requestPaint()
        onLineColorChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()

        onPaint: {
            var ctx = getContext("2d");
            var s = Math.min(width, height);
            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.translate(width / 2, height / 2);
            ctx.rotate(-Math.PI * 0.17);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";

            var hw = 0.36 * s;     // block half-width
            var hh = 0.20 * s;     // block half-height
            var r = 0.085 * s;     // corner radius
            var band = 0.07 * s;   // body | tip division
            var outline = glyph.filled ? "#17181c" : glyph.lineColor;

            function blockPath() {
                ctx.beginPath();
                ctx.moveTo(-hw + r, -hh);
                ctx.lineTo(hw - r, -hh);
                ctx.quadraticCurveTo(hw, -hh, hw, -hh + r);
                ctx.lineTo(hw, hh - r);
                ctx.quadraticCurveTo(hw, hh, hw - r, hh);
                ctx.lineTo(-hw + r, hh);
                ctx.quadraticCurveTo(-hw, hh, -hw, hh - r);
                ctx.lineTo(-hw, -hh + r);
                ctx.quadraticCurveTo(-hw, -hh, -hw + r, -hh);
                ctx.closePath();
            }

            if (glyph.filled) {
                // white body (left of the band)
                ctx.beginPath();
                ctx.moveTo(band, -hh);
                ctx.lineTo(-hw + r, -hh);
                ctx.quadraticCurveTo(-hw, -hh, -hw, -hh + r);
                ctx.lineTo(-hw, hh - r);
                ctx.quadraticCurveTo(-hw, hh, -hw + r, hh);
                ctx.lineTo(band, hh);
                ctx.closePath();
                ctx.fillStyle = root.eraserBodyWhite;
                ctx.fill();
                // light-blue rubber tip (right of the band)
                ctx.beginPath();
                ctx.moveTo(band, -hh);
                ctx.lineTo(hw - r, -hh);
                ctx.quadraticCurveTo(hw, -hh, hw, -hh + r);
                ctx.lineTo(hw, hh - r);
                ctx.quadraticCurveTo(hw, hh, hw - r, hh);
                ctx.lineTo(band, hh);
                ctx.closePath();
                ctx.fillStyle = root.eraserTipBlue;
                ctx.fill();
            }

            ctx.strokeStyle = outline;
            ctx.lineWidth = s * 0.07;
            blockPath();
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(band, -hh);
            ctx.lineTo(band, hh);
            ctx.stroke();

            ctx.restore();
        }
    }

    // Vertical "tune" sliders glyph for the eraser-settings button.
    component SlidersGlyph: Canvas {
        id: sliders
        property color lineColor: root.fg

        width: 26
        height: 26
        antialiasing: true

        onLineColorChanged: requestPaint()
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()

        onPaint: {
            var ctx = getContext("2d");
            var s = Math.min(width, height);
            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.strokeStyle = sliders.lineColor;
            ctx.lineWidth = s * 0.085;
            ctx.lineCap = "round";
            var knobR = 0.115 * s;

            function rail(x, knobY) {
                ctx.beginPath();
                ctx.moveTo(x, 0.14 * s);
                ctx.lineTo(x, knobY - knobR);
                ctx.moveTo(x, knobY + knobR);
                ctx.lineTo(x, 0.86 * s);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(x, knobY, knobR, 0, Math.PI * 2);
                ctx.stroke();
            }

            rail(0.36 * s, 0.64 * s);
            rail(0.64 * s, 0.36 * s);
            ctx.restore();
        }
    }

    // Round eraser-size preview: a circle of transparency checkerboard with a
    // grey ring, blue when selected.
    component SizeSwatch: Item {
        id: swatch
        property int diameter: 40
        property bool selected: false
        signal clicked()

        width: diameter + Math.round(8 * root.toolbarScale)
        height: diameter

        Canvas {
            id: checker
            anchors.centerIn: parent
            width: swatch.diameter
            height: swatch.diameter

            onWidthChanged: requestPaint()
            Component.onCompleted: requestPaint()

            onPaint: {
                var ctx = getContext("2d");
                var d = width;
                ctx.clearRect(0, 0, d, d);
                ctx.save();
                ctx.beginPath();
                ctx.arc(d / 2, d / 2, d / 2 - 1, 0, Math.PI * 2);
                ctx.clip();
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, d, d);
                ctx.fillStyle = "#d8d8d8";
                var cell = Math.max(4, Math.round(7 * root.toolbarScale));
                for (var ix = 0; ix * cell < d; ix++) {
                    for (var iy = 0; iy * cell < d; iy++) {
                        if ((ix + iy) % 2 === 0)
                            ctx.fillRect(ix * cell, iy * cell, cell, cell);
                    }
                }
                ctx.restore();
            }
        }

        Rectangle {
            anchors.centerIn: parent
            width: swatch.diameter
            height: width
            radius: width / 2
            color: "transparent"
            border.width: Math.max(2, Math.round((swatch.selected ? 4 : 3) * root.toolbarScale))
            border.color: swatch.selected ? root.selectionBlue
                : (swatchMouse.containsMouse ? "#dadade" : "#c2c2c6")
        }

        MouseArea {
            id: swatchMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: swatch.clicked()
        }
    }

    // iOS-style switch used by the settings popover.
    component SettingToggle: Item {
        id: toggle
        property bool checked: false
        signal toggled(bool value)

        width: Math.round(64 * root.popupScale)
        height: Math.round(34 * root.popupScale)

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: toggle.checked ? "#0a84ff" : "#0e0e11"
            border.width: 1
            border.color: toggle.checked ? "#330a84ff" : "#26ffffff"

            Rectangle {
                id: knob
                width: parent.height - Math.round(6 * root.popupScale)
                height: width
                radius: width / 2
                anchors.verticalCenter: parent.verticalCenter
                x: toggle.checked ? parent.width - width - Math.round(3 * root.popupScale)
                                  : Math.round(3 * root.popupScale)
                color: "#ffffff"
                Behavior on x { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                toggle.checked = !toggle.checked;
                toggle.toggled(toggle.checked);
            }
        }
    }

    Rectangle {
        id: toolbarShell
        width: root.width
        height: root.toolbarHeight
        radius: height / 2
        color: root.shellBg
        border.width: 1
        border.color: root.shellBorder

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: parent.radius
            anchors.rightMargin: parent.radius
            height: 1
            color: "#22ffffff"
        }

        Row {
            id: shellRow
            x: Math.round(14 * root.toolbarScale)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Math.round(12 * root.toolbarScale)

            // ---- Type dropdown pill ("Standard" / "Stroke") ----
            Item {
                id: typeDropdown
                width: dropdownRow.implicitWidth + Math.round(32 * root.toolbarScale)
                height: Math.round(52 * root.toolbarScale)
                anchors.verticalCenter: parent.verticalCenter

                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: root.typePopupOpen ? root.hoverBg
                        : (dropdownMouse.containsMouse ? "#37373c" : root.controlBg)
                }

                Row {
                    id: dropdownRow
                    anchors.centerIn: parent
                    spacing: Math.round(9 * root.toolbarScale)

                    EraserGlyph {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.round(26 * root.toolbarScale)
                        height: width
                        filled: true
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.typeData(root.selectedType).label
                        color: root.fg
                        font.pixelSize: Math.round(18 * root.toolbarScale)
                        font.bold: true
                    }

                    ToolbarIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        iconName: "chevron"
                        size: Math.round(16 * root.toolbarScale)
                        strokeColor: root.fg
                    }
                }

                MouseArea {
                    id: dropdownMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleTypePopup()
                }
            }

            // ---- Size swatches ----
            Repeater {
                model: root.sizeDiameters

                SizeSwatch {
                    anchors.verticalCenter: parent.verticalCenter
                    diameter: Math.round(modelData * root.toolbarScale)
                    selected: index === root.selectedSizeIndex
                    onClicked: root.chooseSize(index)
                }
            }

            Rectangle {
                width: 1
                height: Math.round(38 * root.toolbarScale)
                anchors.verticalCenter: parent.verticalCenter
                color: "#23ffffff"
            }

            // ---- Eraser-settings button ----
            Item {
                id: settingsButton
                width: Math.round(50 * root.toolbarScale)
                height: Math.round(50 * root.toolbarScale)
                anchors.verticalCenter: parent.verticalCenter

                Rectangle {
                    anchors.fill: parent
                    radius: width / 2
                    color: root.settingsPopupOpen ? root.controlBg
                        : (settingsMouse.containsMouse ? "#2c2c30" : "transparent")
                }

                SlidersGlyph {
                    anchors.centerIn: parent
                    width: Math.round(26 * root.toolbarScale)
                    height: width
                }

                MouseArea {
                    id: settingsMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleSettingsPopup()
                }
            }
        }
    }

    readonly property real dropdownCenterX: shellRow.x + typeDropdown.x + typeDropdown.width / 2
    readonly property real settingsCenterX: shellRow.x + settingsButton.x + settingsButton.width / 2

    // ---- "Standard Type" / "Stroke Type" popover ----
    Rectangle {
        id: typePopup
        objectName: "eraserTypePopover"
        visible: root.typePopupOpen
        width: root.typePopupWidth
        height: root.typePopupHeight
        x: root.clampPopupX(root.dropdownCenterX, width)
        y: toolbarShell.height + Math.round(14 * root.toolbarScale)
        radius: Math.round(18 * root.popupScale)
        color: root.popupBg
        border.width: 1
        border.color: "#22ffffff"

        Canvas {
            width: 36
            height: 18
            x: Math.max(18, Math.min(typePopup.width - width - 18,
                root.dropdownCenterX - typePopup.x - width / 2))
            y: -height + 1
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.fillStyle = root.popupBg;
                ctx.beginPath();
                ctx.moveTo(0, height);
                ctx.lineTo(width / 2, 0);
                ctx.lineTo(width, height);
                ctx.closePath();
                ctx.fill();
            }
        }

        Text {
            x: root.popupPad
            y: root.popupPad
            text: root.typeData(root.selectedType).label + " Type"
            color: root.fg
            font.pixelSize: root.popupTitleSize
            font.bold: true
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            y: root.popupPad + root.popupTitleSize + Math.round(34 * root.popupScale)
            spacing: root.cardGap

            Repeater {
                model: root.eraserTypes

                delegate: Item {
                    id: typeCard
                    width: root.cardSize
                    height: root.cardSize
                    readonly property bool cardSelected: root.selectedType === modelData.typeId

                    Rectangle {
                        anchors.fill: parent
                        radius: Math.round(18 * root.popupScale)
                        color: typeCard.cardSelected ? root.cardBg
                            : (cardMouse.containsMouse ? "#26262b" : "transparent")
                    }

                    EraserGlyph {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: Math.round(20 * root.popupScale)
                        width: root.cardGlyphSize
                        height: width
                        filled: typeCard.cardSelected
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: Math.round(20 * root.popupScale) + root.cardGlyphSize + Math.round(12 * root.popupScale)
                        text: String(modelData.cardLabel || "")
                        color: root.fg
                        font.pixelSize: root.cardLabelSize
                        horizontalAlignment: Text.AlignHCenter
                        lineHeight: 1.18
                    }

                    MouseArea {
                        id: cardMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.chooseType(String(modelData.typeId || "standard"))
                    }
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: typePopup.height - root.popupPad - root.descriptionSize - Math.round(4 * root.popupScale)
            text: root.typeData(root.selectedType).description
            color: root.mutedFg
            font.pixelSize: root.descriptionSize
        }
    }

    // ---- "Eraser Settings" popover ----
    Rectangle {
        id: settingsPopup
        objectName: "eraserSettingsPopover"
        visible: root.settingsPopupOpen
        width: root.settingsPopupWidth
        height: settingsColumn.implicitHeight + root.popupPad * 2
        x: root.clampPopupX(root.settingsCenterX, width)
        y: toolbarShell.height + Math.round(14 * root.toolbarScale)
        radius: Math.round(18 * root.popupScale)
        color: root.popupBg
        border.width: 1
        border.color: "#22ffffff"

        Canvas {
            width: 36
            height: 18
            x: Math.max(18, Math.min(settingsPopup.width - width - 18,
                root.settingsCenterX - settingsPopup.x - width / 2))
            y: -height + 1
            onPaint: {
                var ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                ctx.fillStyle = root.popupBg;
                ctx.beginPath();
                ctx.moveTo(0, height);
                ctx.lineTo(width / 2, 0);
                ctx.lineTo(width, height);
                ctx.closePath();
                ctx.fill();
            }
        }

        Column {
            id: settingsColumn
            x: root.popupPad
            y: root.popupPad
            width: parent.width - root.popupPad * 2

            Text {
                text: "Eraser Settings"
                color: root.fg
                font.pixelSize: root.popupTitleSize
                font.bold: true
            }

            Item { width: 1; height: Math.round(24 * root.popupScale) }

            Item {
                width: parent.width
                height: Math.round(44 * root.popupScale)

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Erase Highlighter Only"
                    color: root.fg
                    font.pixelSize: root.settingsLabelSize
                }

                SettingToggle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    checked: root.eraseHighlighterOnly
                    onToggled: function(value) {
                        root.eraseHighlighterOnly = value;
                        root.optionChanged("Erase Highlighter Only " + (value ? "on" : "off"));
                    }
                }
            }

            Item { width: 1; height: Math.round(18 * root.popupScale) }

            Item {
                width: parent.width
                height: Math.round(44 * root.popupScale)

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Auto-Deselect"
                    color: root.fg
                    font.pixelSize: root.settingsLabelSize
                }

                SettingToggle {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    checked: root.autoDeselect
                    onToggled: function(value) {
                        root.autoDeselect = value;
                        root.optionChanged("Auto-Deselect " + (value ? "on" : "off"));
                    }
                }
            }

            Item { width: 1; height: Math.round(26 * root.popupScale) }

            Text {
                id: clearPageText
                text: "Clear Page"
                color: clearPageMouse.containsMouse ? "#ff6a55" : root.clearRed
                font.pixelSize: root.settingsLabelSize

                MouseArea {
                    id: clearPageMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.settingsPopupOpen = false;
                        root.optionChanged("Clear Page requested");
                    }
                }
            }
        }
    }
}
