import QtQuick
import QtQuick.Controls.Basic

// Pen options popover (GoodNotes-style), anchored under the writing-tools pen
// button. Page 1: pen style cards (Fountain / Ball / Brush) with a live stroke
// preview, the per-style sliders and the shared SETTINGS rows. Page 2 ("Pen
// Gestures") slides in horizontally inside the same panel. All state lives in
// WritingToolsFloatingToolbar (bind down / signal up); this file is
// presentation only.
Item {
    id: pop

    // ---- In (bound by WritingToolsFloatingToolbar) ----
    property real popScale: 1.0
    property string variant: "fountain"     // "fountain" | "ball" | "brush"
    property real fountainSharpness: 1.0
    property real fountainPressure: 1.0
    property real fountainStabilization: 0.0
    property real ballStabilization: 0.0
    property real brushPressure: 0.75
    property real brushStabilization: 0.0
    property bool drawAndHold: true
    property bool scribbleToErase: true
    property bool eraseShapesHighlighter: true
    property bool circleToLasso: true
    property real anchorCenterX: width / 2  // pen-button centre, parent coords
    property real minX: 0
    property real maxX: 100000
    property real maxHeight: 700

    // ---- Out ----
    signal variantSelected(string variant)
    signal sliderChanged(string key, real value, string summaryText)
    signal toggleChanged(string key, bool on, string label)

    // 0 = main page, 1 = Pen Gestures. Reopening always lands on the main page.
    property int currentPage: 0
    onVisibleChanged: if (visible) currentPage = 0

    function px(v) { return Math.round(v * popScale); }

    readonly property color panelBg: "#202023"
    readonly property color panelBorder: "#33ffffff"
    readonly property color fg: "#f5f5f7"
    readonly property color subFg: "#9a9ca1"
    readonly property color captionFg: "#94969b"
    readonly property color dividerColor: "#1fffffff"
    readonly property color cardBg: "#2b2d31"
    readonly property color sliderFill: "#4d9bf5"
    readonly property color sliderTrack: "#46484c"
    readonly property color toggleOn: "#0a84ff"
    readonly property color toggleOff: "#39393d"
    readonly property color cream: "#e8d9a8"
    readonly property color iconDark: "#101114"

    readonly property int pad: px(26)
    readonly property real contentW: width - pad * 2

    width: px(375)
    x: Math.max(minX, Math.min(maxX - width, anchorCenterX - width / 2))
    implicitHeight: caret.height + panel.height
    height: implicitHeight

    function variantTitle() {
        return pop.variant === "ball" ? "Ball Pen"
             : pop.variant === "brush" ? "Brush Pen" : "Fountain Pen";
    }
    function sharpnessText(v) { return v <= 0 ? "Round" : v >= 1 ? "Sharp" : Math.round(v * 100) + "%"; }
    function pressureText(v) { return v <= 0 ? "None" : v >= 1 ? "Max" : Math.round(v * 100) + "%"; }
    function percentText(v) { return Math.round(v * 100) + "%"; }

    // ---- Styled sub-components ----

    // Detent slider matching the reference: 4px track, blue fill, tick marks at
    // the stops (detents > 0), round blue thumb with a white ring. Bind-down /
    // signal-up: the slider never writes its own `value`.
    component PenSlider: Item {
        id: sld
        property string settingKey: ""
        objectName: "penSlider_" + settingKey
        property string labelText: ""
        property string valueText: ""
        property real value: 0
        property int detents: 0          // 0 = continuous
        signal userChanged(real newValue)

        width: pop.contentW
        height: pop.px(58)

        readonly property real thumbD: pop.px(26)
        readonly property real trackY: pop.px(42)

        Text {
            x: 0
            y: 0
            text: sld.labelText
            color: pop.subFg
            font.pixelSize: pop.px(12)
            font.letterSpacing: 0.8
        }
        Text {
            anchors.right: parent.right
            y: 0
            text: sld.valueText
            color: pop.subFg
            font.pixelSize: pop.px(13)
        }

        Rectangle {
            id: track
            x: 0
            y: sld.trackY - height / 2
            width: parent.width
            height: Math.max(3, pop.px(4))
            radius: height / 2
            color: pop.sliderTrack
        }
        Rectangle {
            x: 0
            y: track.y
            width: thumb.x + sld.thumbD / 2
            height: track.height
            radius: track.radius
            color: pop.sliderFill
        }
        Repeater {
            model: sld.detents
            Rectangle {
                required property int index
                width: Math.max(2, pop.px(2))
                height: pop.px(10)
                radius: width / 2
                x: sld.thumbD / 2
                   + (index / Math.max(1, sld.detents - 1)) * (sld.width - sld.thumbD)
                   - width / 2
                y: sld.trackY - height / 2
                // lighter on the filled (blue) section, grey on the empty one
                color: x + width / 2 <= thumb.x + sld.thumbD / 2 ? "#9cc4f8" : "#6a6c70"
            }
        }
        Rectangle {
            id: thumb
            width: sld.thumbD
            height: sld.thumbD
            radius: width / 2
            x: Math.max(0, Math.min(1, sld.value)) * (sld.width - sld.thumbD)
            y: sld.trackY - height / 2
            color: pop.sliderFill
            border.width: Math.max(2, pop.px(3))
            border.color: "#ffffff"
        }

        MouseArea {
            anchors.left: parent.left
            anchors.right: parent.right
            y: sld.trackY - pop.px(16)
            height: pop.px(32)
            preventStealing: true       // keep drags away from the page Flickable
            cursorShape: Qt.PointingHandCursor
            function apply(mx) {
                var t = (mx - sld.thumbD / 2) / Math.max(1, sld.width - sld.thumbD);
                t = Math.max(0, Math.min(1, t));
                if (sld.detents > 1)
                    t = Math.round(t * (sld.detents - 1)) / (sld.detents - 1);
                if (Math.abs(t - sld.value) > 0.0001)
                    sld.userChanged(t);
            }
            onPressed: function(mouse) { apply(mouse.x); }
            onPositionChanged: function(mouse) { if (pressed) apply(mouse.x); }
        }
    }

    // iOS-style switch: blue pill, white knob, both animated.
    component ToggleSwitch: Item {
        id: toggle
        property bool checked: true
        signal toggled(bool on)

        width: pop.px(50)
        height: pop.px(30)

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: toggle.checked ? pop.toggleOn : pop.toggleOff
            Behavior on color { ColorAnimation { duration: 130 } }
        }
        Rectangle {
            width: parent.height - pop.px(4)
            height: width
            radius: width / 2
            x: toggle.checked ? parent.width - width - pop.px(2) : pop.px(2)
            anchors.verticalCenter: parent.verticalCenter
            color: "#ffffff"
            Behavior on x { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: toggle.toggled(!toggle.checked)
        }
    }

    component ToggleRow: Item {
        id: trow
        property string settingKey: ""
        objectName: "penToggle_" + settingKey
        property string label: ""
        property bool checked: true
        signal toggled(bool on)

        height: pop.px(44)

        Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: trow.label
            color: pop.fg
            font.pixelSize: pop.px(17)
        }
        ToggleSwitch {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            checked: trow.checked
            onToggled: function(on) { trow.toggled(on); }
        }
    }

    // Pen style icon for the cards: white line art when idle, filled dark +
    // cream accents when selected (matching the reference flyout).
    component PenVariantIcon: Canvas {
        id: vIcon
        property string variantId: "fountain"
        property bool selected: false

        width: pop.px(38)
        height: pop.px(38)
        antialiasing: true
        onVariantIdChanged: requestPaint()
        onSelectedChanged: requestPaint()
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()

        onPaint: {
            var ctx = getContext("2d");
            var s = Math.min(width, height);
            ctx.clearRect(0, 0, width, height);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            var sel = vIcon.selected;
            var rim = "#565963";        // edge for dark fills on the card bg
            var darkEdge = "#0c0d10";   // edge for cream fills
            ctx.lineWidth = s * 0.055;
            ctx.strokeStyle = pop.fg;

            if (vIcon.variantId === "fountain") {
                // flag wing (cream when selected)
                ctx.beginPath();
                ctx.moveTo(0.573 * s, 0.093 * s);
                ctx.lineTo(0.885 * s, 0.403 * s);
                ctx.lineTo(0.718 * s, 0.443 * s);
                ctx.lineTo(0.524 * s, 0.249 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.cream; ctx.strokeStyle = darkEdge; ctx.fill(); }
                ctx.stroke();

                // dark spike tip
                ctx.beginPath();
                ctx.moveTo(0.098 * s, 0.887 * s);
                ctx.lineTo(0.221 * s, 0.687 * s);
                ctx.lineTo(0.298 * s, 0.742 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.iconDark; ctx.strokeStyle = rim; ctx.fill(); }
                ctx.stroke();

                // nib body (dark when selected)
                ctx.beginPath();
                ctx.moveTo(0.298 * s, 0.405 * s);
                ctx.lineTo(0.487 * s, 0.324 * s);
                ctx.lineTo(0.645 * s, 0.487 * s);
                ctx.lineTo(0.553 * s, 0.671 * s);
                ctx.lineTo(0.298 * s, 0.742 * s);
                ctx.lineTo(0.221 * s, 0.687 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.iconDark; ctx.strokeStyle = rim; ctx.fill(); }
                ctx.stroke();

                // slit + breather hole (cream centre when selected)
                ctx.lineWidth = s * 0.045;
                ctx.strokeStyle = sel ? rim : pop.fg;
                ctx.beginPath();
                ctx.moveTo(0.405 * s, 0.575 * s);
                ctx.lineTo(0.250 * s, 0.712 * s);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(0.430 * s, 0.537 * s, 0.055 * s, 0, Math.PI * 2);
                if (sel) { ctx.fillStyle = pop.cream; ctx.fill(); }
                ctx.stroke();
            } else if (vIcon.variantId === "ball") {
                ctx.save();
                ctx.translate(0.50 * s, 0.46 * s);
                ctx.rotate(Math.PI / 4);

                // barrel (dark when selected)
                var bHalf = 0.125 * s;
                ctx.beginPath();
                ctx.moveTo(-bHalf, -0.36 * s + 0.05 * s);
                ctx.quadraticCurveTo(-bHalf, -0.36 * s, -bHalf + 0.05 * s, -0.36 * s);
                ctx.lineTo(bHalf - 0.05 * s, -0.36 * s);
                ctx.quadraticCurveTo(bHalf, -0.36 * s, bHalf, -0.36 * s + 0.05 * s);
                ctx.lineTo(bHalf, 0.10 * s);
                ctx.lineTo(-bHalf, 0.10 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.iconDark; ctx.strokeStyle = rim; ctx.fill(); }
                ctx.stroke();

                // chisel cone (cream when selected)
                ctx.beginPath();
                ctx.moveTo(-bHalf, 0.10 * s);
                ctx.lineTo(bHalf, 0.10 * s);
                ctx.lineTo(0.045 * s, 0.33 * s);
                ctx.lineTo(-0.045 * s, 0.33 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.cream; ctx.strokeStyle = darkEdge; ctx.fill(); }
                ctx.stroke();

                // point (dark)
                ctx.beginPath();
                ctx.moveTo(-0.045 * s, 0.33 * s);
                ctx.lineTo(0.045 * s, 0.33 * s);
                ctx.lineTo(0, 0.44 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.iconDark; ctx.strokeStyle = rim; ctx.fill(); }
                ctx.stroke();
                ctx.restore();
            } else {
                // brush
                ctx.save();
                ctx.translate(0.50 * s, 0.46 * s);
                ctx.rotate(Math.PI / 4);

                // handle + ferrule as one cream piece
                var hHalf = 0.09 * s;
                ctx.beginPath();
                ctx.moveTo(-hHalf, -0.46 * s + 0.04 * s);
                ctx.quadraticCurveTo(-hHalf, -0.46 * s, -hHalf + 0.04 * s, -0.46 * s);
                ctx.lineTo(hHalf - 0.04 * s, -0.46 * s);
                ctx.quadraticCurveTo(hHalf, -0.46 * s, hHalf, -0.46 * s + 0.04 * s);
                ctx.lineTo(0.10 * s, -0.04 * s);
                ctx.lineTo(-0.10 * s, -0.04 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.cream; ctx.strokeStyle = darkEdge; ctx.fill(); }
                ctx.stroke();

                // bristle head (dark when selected): swells, then tapers to a point
                ctx.beginPath();
                ctx.moveTo(-0.10 * s, -0.04 * s);
                ctx.quadraticCurveTo(-0.175 * s, 0.13 * s, 0, 0.46 * s);
                ctx.quadraticCurveTo(0.175 * s, 0.13 * s, 0.10 * s, -0.04 * s);
                ctx.closePath();
                if (sel) { ctx.fillStyle = pop.iconDark; ctx.strokeStyle = rim; ctx.fill(); }
                ctx.stroke();
                ctx.restore();
            }
        }
    }

    component VariantCard: Item {
        id: card
        property string variantId: "fountain"
        objectName: "penCard_" + variantId
        property string label: ""
        property bool selected: false

        width: Math.floor((pop.contentW - pop.px(10) * 2) / 3)
        height: pop.px(86)

        Rectangle {
            anchors.fill: parent
            radius: pop.px(14)
            color: card.selected ? pop.cardBg
                 : (cardMouse.containsMouse ? "#17ffffff" : "transparent")
        }
        PenVariantIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            y: pop.px(10)
            variantId: card.variantId
            selected: card.selected
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: pop.px(10)
            width: parent.width - pop.px(6)
            text: card.label
            color: pop.fg
            font.pixelSize: pop.px(17)
            horizontalAlignment: Text.AlignHCenter
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: pop.px(11)
        }
        MouseArea {
            id: cardMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pop.variantSelected(card.variantId)
        }
    }

    // ---- Caret pointing up at the pen button ----
    Canvas {
        id: caret
        width: pop.px(34)
        height: pop.px(16)
        x: Math.max(18, Math.min(pop.width - 18 - width, pop.anchorCenterX - pop.x - width / 2))
        onWidthChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d");
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = pop.panelBg;
            ctx.beginPath();
            ctx.moveTo(0, height);
            ctx.lineTo(width / 2, 0);
            ctx.lineTo(width, height);
            ctx.closePath();
            ctx.fill();
        }
    }

    Rectangle {
        id: panel
        anchors.top: caret.bottom
        anchors.topMargin: -1
        width: pop.width
        radius: 22
        color: pop.panelBg
        border.width: 1
        border.color: pop.panelBorder
        clip: true
        height: Math.min(
            (pop.currentPage === 0 ? mainCol.implicitHeight : gestCol.implicitHeight) + pop.pad * 2,
            pop.maxHeight - caret.height)
        Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

        // ---- Page 1: pen styles + settings ----
        Flickable {
            id: mainFlick
            x: pop.currentPage === 0 ? 0 : -panel.width
            Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            y: 0
            width: panel.width
            height: panel.height
            contentWidth: width
            contentHeight: mainCol.implicitHeight + pop.pad * 2
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: pop.currentPage === 0 && contentHeight > height
            ScrollIndicator.vertical: ScrollIndicator { }

            Column {
                id: mainCol
                x: pop.pad
                y: pop.pad
                width: pop.contentW
                spacing: pop.px(16)

                Text {
                    text: pop.variantTitle()
                    color: pop.fg
                    font.pixelSize: pop.px(21)
                    font.bold: true
                }

                // Live stroke preview: rendering follows the pen style and its
                // slider values (calligraphic / uniform / brush-tapered).
                Canvas {
                    id: strokePreview
                    width: mainCol.width
                    height: pop.px(108)
                    antialiasing: true

                    readonly property string v: pop.variant
                    readonly property real sharp: pop.fountainSharpness
                    readonly property real fPress: pop.fountainPressure
                    readonly property real bPress: pop.brushPressure
                    readonly property real stab: pop.variant === "fountain" ? pop.fountainStabilization
                                               : pop.variant === "ball" ? pop.ballStabilization
                                               : pop.brushStabilization
                    onVChanged: requestPaint()
                    onSharpChanged: requestPaint()
                    onFPressChanged: requestPaint()
                    onBPressChanged: requestPaint()
                    onStabChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    Component.onCompleted: requestPaint()

                    function bez(p0, c1, c2, p1, t) {
                        var mt = 1 - t;
                        var a = mt * mt * mt, b = 3 * mt * mt * t, c = 3 * mt * t * t, d = t * t * t;
                        return { x: a * p0.x + b * c1.x + c * c2.x + d * p1.x,
                                 y: a * p0.y + b * c1.y + c * c2.y + d * p1.y };
                    }

                    onPaint: {
                        var ctx = getContext("2d");
                        var W = width, H = height;
                        ctx.clearRect(0, 0, W, H);
                        ctx.fillStyle = "#ffffff";
                        ctx.strokeStyle = "#ffffff";
                        ctx.lineCap = "round";
                        ctx.lineJoin = "round";

                        // higher stabilization calms the wave down a little
                        var amp = 1.0 - 0.25 * stab;
                        var yMid = 0.50 * H;
                        var p0 = { x: 0.07 * W, y: yMid + 0.12 * H * amp };
                        var c1 = { x: 0.30 * W, y: yMid + 0.55 * H * amp };
                        var c2 = { x: 0.56 * W, y: yMid - 0.62 * H * amp };
                        var p1 = { x: 0.93 * W, y: yMid + 0.02 * H * amp };

                        var n = 320;
                        if (v === "ball") {
                            ctx.lineWidth = Math.max(3, 0.045 * H);
                            ctx.beginPath();
                            ctx.moveTo(p0.x, p0.y);
                            for (var i = 1; i <= n; i++) {
                                var p = bez(p0, c1, c2, p1, i / n);
                                ctx.lineTo(p.x, p.y);
                            }
                            ctx.stroke();
                            return;
                        }

                        for (var j = 0; j <= n; j++) {
                            var t = j / n;
                            var pt = bez(p0, c1, c2, p1, t);
                            var q = bez(p0, c1, c2, p1, Math.min(1, t + 1.0 / n));
                            var theta = Math.atan2(q.y - pt.y, q.x - pt.x);
                            var r;
                            if (v === "fountain") {
                                var rMax = H * (0.030 + 0.026 * fPress);
                                var minK = 1 - 0.78 * sharp;
                                var dir = Math.abs(Math.sin(theta - Math.PI / 4));
                                var te = 0.10;
                                var taper = Math.pow(Math.max(0, Math.min(1, Math.min(t, 1 - t) / te)),
                                                     0.5 + 0.8 * fPress);
                                r = rMax * taper * (minK + (1 - minK) * Math.pow(dir, 1.15));
                            } else {
                                // brush: thick belly, dramatic tapers at both ends
                                var rMaxB = H * (0.10 + 0.08 * bPress);
                                var gamma = 1.15 - 0.40 * bPress;
                                r = rMaxB * Math.pow(Math.sin(Math.PI * t), gamma);
                            }
                            if (r <= 0.3)
                                continue;
                            ctx.beginPath();
                            ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2);
                            ctx.fill();
                        }
                    }
                }

                Row {
                    spacing: pop.px(10)

                    VariantCard {
                        variantId: "fountain"
                        label: "Fountain Pen"
                        selected: pop.variant === "fountain"
                    }
                    VariantCard {
                        variantId: "ball"
                        label: "Ball Pen"
                        selected: pop.variant === "ball"
                    }
                    VariantCard {
                        variantId: "brush"
                        label: "Brush Pen"
                        selected: pop.variant === "brush"
                    }
                }

                Rectangle { width: mainCol.width; height: 1; color: pop.dividerColor }

                PenSlider {
                    settingKey: "penFountainSharpness"
                    visible: pop.variant === "fountain"
                    labelText: "TIP SHARPNESS"
                    detents: 5
                    value: pop.fountainSharpness
                    valueText: pop.sharpnessText(pop.fountainSharpness)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penFountainSharpness", v,
                                          "Fountain Pen tip sharpness: " + pop.sharpnessText(v));
                    }
                }
                PenSlider {
                    settingKey: "penFountainPressure"
                    visible: pop.variant === "fountain"
                    labelText: "PRESSURE SENSITIVITY"
                    detents: 5
                    value: pop.fountainPressure
                    valueText: pop.pressureText(pop.fountainPressure)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penFountainPressure", v,
                                          "Fountain Pen pressure sensitivity: " + pop.pressureText(v));
                    }
                }
                PenSlider {
                    settingKey: "penFountainStabilization"
                    visible: pop.variant === "fountain"
                    labelText: "STROKE STABILIZATION"
                    detents: 0
                    value: pop.fountainStabilization
                    valueText: pop.percentText(pop.fountainStabilization)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penFountainStabilization", v,
                                          "Fountain Pen stroke stabilization: " + pop.percentText(v));
                    }
                }
                PenSlider {
                    settingKey: "penBallStabilization"
                    visible: pop.variant === "ball"
                    labelText: "STROKE STABILIZATION"
                    detents: 0
                    value: pop.ballStabilization
                    valueText: pop.percentText(pop.ballStabilization)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penBallStabilization", v,
                                          "Ball Pen stroke stabilization: " + pop.percentText(v));
                    }
                }
                PenSlider {
                    settingKey: "penBrushPressure"
                    visible: pop.variant === "brush"
                    labelText: "PRESSURE SENSITIVITY"
                    detents: 5
                    value: pop.brushPressure
                    valueText: pop.pressureText(pop.brushPressure)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penBrushPressure", v,
                                          "Brush Pen pressure sensitivity: " + pop.pressureText(v));
                    }
                }
                PenSlider {
                    settingKey: "penBrushStabilization"
                    visible: pop.variant === "brush"
                    labelText: "STROKE STABILIZATION"
                    detents: 0
                    value: pop.brushStabilization
                    valueText: pop.percentText(pop.brushStabilization)
                    onUserChanged: function(v) {
                        pop.sliderChanged("penBrushStabilization", v,
                                          "Brush Pen stroke stabilization: " + pop.percentText(v));
                    }
                }

                Rectangle { width: mainCol.width; height: 1; color: pop.dividerColor }

                Text {
                    text: "SETTINGS"
                    color: pop.subFg
                    font.pixelSize: pop.px(12)
                    font.letterSpacing: 0.8
                }

                ToggleRow {
                    settingKey: "penDrawAndHold"
                    width: mainCol.width
                    label: "Draw and Hold"
                    checked: pop.drawAndHold
                    onToggled: function(on) { pop.toggleChanged("penDrawAndHold", on, "Draw and Hold"); }
                }

                Item {
                    objectName: "penGesturesRow"
                    width: mainCol.width
                    height: pop.px(40)

                    Text {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Pen Gestures"
                        color: pop.fg
                        font.pixelSize: pop.px(17)
                    }
                    // small filled disclosure triangle, like the reference
                    Canvas {
                        anchors.right: parent.right
                        anchors.rightMargin: pop.px(2)
                        anchors.verticalCenter: parent.verticalCenter
                        width: pop.px(10)
                        height: pop.px(12)
                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.clearRect(0, 0, width, height);
                            ctx.fillStyle = pop.fg;
                            ctx.beginPath();
                            ctx.moveTo(width * 0.12, height * 0.10);
                            ctx.lineTo(width * 0.95, height * 0.50);
                            ctx.lineTo(width * 0.12, height * 0.90);
                            ctx.closePath();
                            ctx.fill();
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: pop.currentPage = 1
                    }
                }
            }
        }

        // ---- Page 2: Pen Gestures ----
        Flickable {
            id: gestFlick
            x: pop.currentPage === 1 ? 0 : panel.width
            Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            y: 0
            width: panel.width
            height: panel.height
            contentWidth: width
            contentHeight: gestCol.implicitHeight + pop.pad * 2
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: pop.currentPage === 1 && contentHeight > height
            ScrollIndicator.vertical: ScrollIndicator { }

            Column {
                id: gestCol
                x: pop.pad
                y: pop.pad
                width: pop.contentW
                spacing: pop.px(14)

                Item {
                    width: gestCol.width
                    height: pop.px(30)

                    Canvas {
                        id: backArrow
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: pop.px(24)
                        height: pop.px(24)
                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.clearRect(0, 0, width, height);
                            ctx.strokeStyle = pop.fg;
                            ctx.lineWidth = Math.max(2, pop.px(2.4));
                            ctx.lineCap = "round";
                            ctx.lineJoin = "round";
                            var cy = height / 2;
                            ctx.beginPath();
                            ctx.moveTo(width * 0.88, cy);
                            ctx.lineTo(width * 0.16, cy);
                            ctx.moveTo(width * 0.46, cy - width * 0.28);
                            ctx.lineTo(width * 0.16, cy);
                            ctx.lineTo(width * 0.46, cy + width * 0.28);
                            ctx.stroke();
                        }
                    }
                    Text {
                        anchors.left: backArrow.right
                        anchors.leftMargin: pop.px(18)
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Pen Gestures"
                        color: pop.fg
                        font.pixelSize: pop.px(21)
                        font.bold: true
                    }
                    MouseArea {
                        objectName: "penGesturesBack"
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: pop.px(40)
                        height: pop.px(40)
                        cursorShape: Qt.PointingHandCursor
                        onClicked: pop.currentPage = 0
                    }
                }

                ToggleRow {
                    settingKey: "penScribbleToErase"
                    width: gestCol.width
                    label: "Scribble to Erase"
                    checked: pop.scribbleToErase
                    onToggled: function(on) { pop.toggleChanged("penScribbleToErase", on, "Scribble to Erase"); }
                }

                ToggleRow {
                    settingKey: "penEraseShapesHighlighter"
                    width: gestCol.width
                    label: "Erase Shapes and Highlighter"
                    checked: pop.eraseShapesHighlighter
                    onToggled: function(on) {
                        pop.toggleChanged("penEraseShapesHighlighter", on, "Erase Shapes and Highlighter");
                    }
                }

                Text {
                    width: gestCol.width
                    text: "Erase handwriting and drawings by scribbling over"
                    color: pop.captionFg
                    font.pixelSize: pop.px(15)
                    wrapMode: Text.WordWrap
                    bottomPadding: pop.px(10)
                }

                ToggleRow {
                    settingKey: "penCircleToLasso"
                    width: gestCol.width
                    label: "Circle to Lasso"
                    checked: pop.circleToLasso
                    onToggled: function(on) { pop.toggleChanged("penCircleToLasso", on, "Circle to Lasso"); }
                }

                Text {
                    width: gestCol.width
                    text: "Draw around anything to select and move it"
                    color: pop.captionFg
                    font.pixelSize: pop.px(15)
                    wrapMode: Text.WordWrap
                }
            }
        }

        // subtle top edge highlight, like the other dark panels
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: parent.radius
            anchors.rightMargin: parent.radius
            height: 1
            color: "#1affffff"
        }
    }
}
