import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "shellStatusStrip"

    property var canvasStateBridgeRef
    property var statusEngineRef
    property var statusJobsRef
    property var statusMetricsRef
    property var statusNotificationsRef
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null

    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property string statusBarLayout: root.canvasStateBridgeRef
        && root.canvasStateBridgeRef.graphics_status_bar_layout !== undefined
        ? String(root.canvasStateBridgeRef.graphics_status_bar_layout || "option_1")
        : "option_1"
    readonly property bool telemetryHudLayout: root.statusBarLayout === "option_2"
    readonly property string metricsTextValue: root._text(root.statusMetricsRef)
    property var cpuHistory: []
    property var ramHistory: []
    property var diskReadHistory: []
    property string _lastFpsGaugePaintKey: ""

    onMetricsTextValueChanged: root._recordMetricsSample()
    onTelemetryHudLayoutChanged: if (root.telemetryHudLayout) root._recordMetricsSample()
    Component.onCompleted: root._recordMetricsSample()

    Layout.fillWidth: true
    Layout.preferredHeight: root.telemetryHudLayout ? 46 : 32
    color: root.telemetryHudLayout ? root._pal("panel_bg", "#171d24") : root._pal("toolbar_bg", "#20242b")
    border.color: root.telemetryHudLayout ? Qt.alpha(root._stateColor(), 0.5) : root._pal("border", "#3d4652")

    function _pal(name, fallback) {
        var value = root.themePalette ? root.themePalette[name] : null;
        return value ? value : fallback;
    }

    function _text(model) {
        return model ? String(model.text_value || "") : "";
    }

    function _icon(model) {
        return model ? String(model.icon_value || "") : "";
    }

    function _modelText(model) {
        var icon = root._icon(model);
        var text = root._text(model);
        return (icon ? icon + " " : "") + text;
    }

    function _requestStatusAction(model, action) {
        if (model && model.requestAction)
            model.requestAction(action);
    }

    function _stateColor() {
        var source = root._modelText(root.statusEngineRef).toLowerCase();
        if (source.indexOf("error") >= 0 || source.indexOf("fail") >= 0)
            return root._pal("error", "#ff5d6c");
        if (source.indexOf("warn") >= 0)
            return root._pal("warning", "#f7c948");
        if (source.indexOf("running") >= 0 || source.indexOf("execut") >= 0)
            return root._pal("success", "#63d471");
        return root._pal("accent", "#60cdff");
    }

    function _matchNumber(source, pattern, fallback) {
        var match = String(source || "").match(pattern);
        if (!match || match.length < 2)
            return fallback;
        var value = Number(match[1]);
        return isNaN(value) ? fallback : value;
    }

    function _jobsText() { return root._text(root.statusJobsRef); }
    function _metricsText() { return root.metricsTextValue; }
    function _notificationsText() { return root._text(root.statusNotificationsRef); }
    function _jobCount(label) { return Math.round(root._matchNumber(root._jobsText(), new RegExp(label + ":([0-9]+)"), 0)); }
    function _notificationCount(label) { return Math.round(root._matchNumber(root._notificationsText(), new RegExp(label + ":([0-9]+)"), 0)); }
    function _cpu() { return root._matchNumber(root._metricsText(), /CPU:([0-9.]+)/, 0); }
    function _ram() { return root._matchNumber(root._metricsText(), /RAM:([0-9.]+)\//, 0); }
    function _ramTotal() { return root._matchNumber(root._metricsText(), /RAM:[0-9.]+\/([0-9.]+)/, 1); }
    function _diskRead() { return root._matchNumber(root._metricsText(), /Disk R:([0-9.]+)/, 0); }
    function _diskWrite() { return root._matchNumber(root._metricsText(), /W:([0-9.]+)/, 0); }
    function _fps() { return root._matchNumber(root._metricsText(), /FPS:([0-9.]+)/, 0); }
    function _hasFps() { return root._metricsText().indexOf("FPS:") >= 0; }
    function _ratio(value, total) { return total > 0 ? Math.max(0, Math.min(1, value / total)) : 0; }

    function _metricColor(ratio) {
        if (ratio >= 0.82)
            return root._pal("error", "#ff5d6c");
        if (ratio >= 0.62)
            return root._pal("warning", "#f7c948");
        return root._pal("success", "#63d471");
    }

    function _fpsColor() {
        var fps = root._fps();
        if (fps >= 50)
            return root._pal("success", "#63d471");
        if (fps >= 30)
            return root._pal("warning", "#f7c948");
        return root._pal("error", "#ff5d6c");
    }

    function _option1MetricModel() {
        var metrics = ["cpu", "ram", "disk"];
        if (root._hasFps())
            metrics.push("fps");
        return metrics;
    }

    function _pushMetricSample(history, value) {
        var next = history && history.length ? history.slice() : [];
        if (next.length === 0) {
            for (var i = 0; i < 26; i++)
                next.push(value);
            return next;
        }
        next.push(value);
        while (next.length > 26)
            next.shift();
        return next;
    }

    function _recordMetricsSample() {
        if (!root._metricsText())
            return;
        root.cpuHistory = root._pushMetricSample(root.cpuHistory, root._cpu());
        root.ramHistory = root._pushMetricSample(root.ramHistory, root._ram());
        root.diskReadHistory = root._pushMetricSample(root.diskReadHistory, root._diskRead());
    }

    function _historyMax(history, fallback) {
        var maxValue = fallback;
        if (!history || history.length === 0)
            return maxValue;
        for (var i = 0; i < history.length; i++)
            maxValue = Math.max(maxValue, Number(history[i]) || 0);
        return maxValue;
    }

    function _metricCaption(kind) {
        if (kind === "cpu") return "CPU";
        if (kind === "ram") return "RAM";
        if (kind === "disk") return "DISK";
        return "FPS";
    }

    function _metricValue(kind) {
        if (kind === "cpu") return Math.round(root._cpu()) + "%";
        if (kind === "ram") return root._ram().toFixed(1) + " / " + root._ramTotal().toFixed(1) + " GB";
        if (kind === "disk") return "R " + root._diskRead().toFixed(1) + " W " + root._diskWrite().toFixed(1);
        return String(Math.round(root._fps()));
    }

    function _metricRatio(kind) {
        if (kind === "cpu") return root._ratio(root._cpu(), 100);
        if (kind === "ram") return root._ratio(root._ram(), root._ramTotal());
        return 0;
    }

    function _requestFpsGaugePaintIfNeeded(force) {
        if (!root.telemetryHudLayout || !root._hasFps() || !fpsGauge.visible || fpsGauge.width <= 0 || fpsGauge.height <= 0)
            return;
        var key = [
            String(Math.round(root._fps())),
            String(root._fpsColor()),
            String(root._pal("muted_fg", "#8f99a8")),
            String(Math.round(fpsGauge.width * 10) / 10),
            String(Math.round(fpsGauge.height * 10) / 10)
        ].join("|");
        if (!Boolean(force) && key === root._lastFpsGaugePaintKey)
            return;
        root._lastFpsGaugePaintKey = key;
        fpsGauge.requestPaint();
    }

    Timer {
        interval: 900
        repeat: true
        running: root.telemetryHudLayout
        onTriggered: {
            root._recordMetricsSample();
            root._requestFpsGaugePaintIfNeeded(false);
        }
    }

    Rectangle {
        id: option1Strip
        visible: !root.telemetryHudLayout
        anchors.fill: parent
        color: root._pal("toolbar_bg", "#20242b")

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: Qt.alpha(root._pal("border", "#3d4652"), 0.9)
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            anchors.topMargin: 1
            spacing: 7

            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredHeight: 22
                implicitWidth: option1EngineRow.implicitWidth + 18
                radius: 11
                color: Qt.alpha(root._stateColor(), 0.16)
                border.width: 1
                border.color: Qt.alpha(root._stateColor(), 0.55)

                Row {
                    id: option1EngineRow
                    anchors.centerIn: parent
                    spacing: 6
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: root._stateColor() }
                    Text {
                        objectName: "shellStatusStripEngineStatus"
                        anchors.verticalCenter: parent.verticalCenter
                        text: root._modelText(root.statusEngineRef)
                        color: root._pal("panel_title_fg", "#f0f4fb")
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusEngineRef, "auto") }
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 16; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root._pal("border", "#3d4652"), 0.8) }

            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredHeight: 22
                implicitWidth: option1JobsRow.implicitWidth + 16
                radius: 6
                color: Qt.alpha(root._pal("panel_bg", "#151a21"), 0.55)

                Row {
                    id: option1JobsRow
                    anchors.centerIn: parent
                    spacing: 9
                    Repeater {
                        model: [
                            { "label": "R", "dot": root._pal("accent", "#60cdff") },
                            { "label": "Q", "dot": root._pal("muted_fg", "#8f99a8") },
                            { "label": "D", "dot": root._pal("success", "#63d471") },
                            { "label": "F", "dot": root._pal("error", "#ff5d6c") }
                        ]
                        delegate: Row {
                            id: option1JobDelegate
                            readonly property int count: root._jobCount(modelData.label)
                            spacing: 4
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5; color: modelData.dot; opacity: option1JobDelegate.count > 0 ? 1 : 0.4 }
                            Text { objectName: modelData.label === "R" ? "shellStatusStripJobStatus" : ""; anchors.verticalCenter: parent.verticalCenter; text: option1JobDelegate.count; color: option1JobDelegate.count > 0 ? root._pal("panel_title_fg", "#f0f4fb") : root._pal("muted_fg", "#8f99a8"); font.pixelSize: 11; font.bold: option1JobDelegate.count > 0 }
                        }
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusJobsRef, "auto") }
            }

            Repeater {
                model: root._option1MetricModel()
                delegate: Rectangle {
                    id: metricChip
                    readonly property bool hasBar: modelData === "cpu" || modelData === "ram"
                    readonly property real ratio: root._metricRatio(modelData)
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredHeight: 22
                    Layout.preferredWidth: modelData === "cpu" ? 172 : (modelData === "fps" ? 96 : implicitWidth)
                    implicitWidth: chipRow.implicitWidth + 16
                    radius: 6
                    color: Qt.alpha(root._pal("panel_bg", "#151a21"), 0.55)
                    Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 6
                        Text { anchors.verticalCenter: parent.verticalCenter; text: root._metricCaption(modelData); color: root._pal("muted_fg", "#8f99a8"); font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.5 }
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: metricChip.hasBar
                            width: metricChip.hasBar ? 30 : 0
                            height: 5
                            radius: 2.5
                            color: Qt.alpha(root._pal("muted_fg", "#8f99a8"), 0.22)
                            Rectangle { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: parent.width * metricChip.ratio; radius: parent.radius; color: root._metricColor(metricChip.ratio) }
                        }
                        Text { objectName: modelData === "cpu" ? "shellStatusStripMetricsStatus" : ""; anchors.verticalCenter: parent.verticalCenter; text: root._metricValue(modelData); color: modelData === "fps" ? root._fpsColor() : root._pal("panel_title_fg", "#f0f4fb"); font.pixelSize: 11; font.bold: true }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 16; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root._pal("border", "#3d4652"), 0.8) }

            Item {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: option1NotificationsRow.implicitWidth
                Layout.preferredHeight: 22
                Row {
                    id: option1NotificationsRow
                    anchors.centerIn: parent
                    spacing: 10
                    Repeater {
                        model: [
                            { "label": "W", "dot": root._pal("warning", "#f7c948") },
                            { "label": "E", "dot": root._pal("error", "#ff5d6c") }
                        ]
                        delegate: Row {
                            id: option1NotificationDelegate
                            readonly property int count: root._notificationCount(modelData.label)
                            spacing: 5
                            opacity: count > 0 ? 1 : 0.5
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: option1NotificationDelegate.count > 0 ? modelData.dot : "transparent"; border.width: option1NotificationDelegate.count > 0 ? 0 : 1; border.color: root._pal("muted_fg", "#8f99a8") }
                            Text { objectName: modelData.label === "W" ? "shellStatusStripNotificationStatus" : ""; anchors.verticalCenter: parent.verticalCenter; text: option1NotificationDelegate.count; color: option1NotificationDelegate.count > 0 ? root._pal("panel_title_fg", "#f0f4fb") : root._pal("muted_fg", "#8f99a8"); font.pixelSize: 11; font.bold: option1NotificationDelegate.count > 0 }
                        }
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusNotificationsRef, "failed") }
            }
        }
    }

    Rectangle {
        id: option2Strip
        objectName: "shellStatusStripOption2TelemetryHud"
        visible: root.telemetryHudLayout
        anchors.fill: parent
        color: root._pal("panel_bg", "#171d24")

        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 1; color: Qt.alpha(root._stateColor(), 0.5) }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 16

            Item {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 178
                Layout.preferredHeight: 36
                Rectangle { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 30; radius: 1.5; color: root._stateColor() }
                ColumnLayout {
                    anchors.left: parent.left
                    anchors.leftMargin: 11
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    RowLayout {
                        spacing: 6
                        Rectangle { Layout.alignment: Qt.AlignVCenter; width: 7; height: 7; radius: 3.5; color: root._stateColor() }
                        Text { objectName: "shellStatusStripEngineStatus"; text: root._modelText(root.statusEngineRef).toUpperCase(); color: root._pal("panel_title_fg", "#f0f4fb"); font.pixelSize: 11; font.bold: true; font.letterSpacing: 0.8 }
                    }
                    Text { text: root._text(root.statusEngineRef); color: root._pal("muted_fg", "#8f99a8"); font.pixelSize: 9; elide: Text.ElideRight; Layout.maximumWidth: 150 }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusEngineRef, "auto") }
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root._pal("border", "#3d4652"), 0.8) }

            Item {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 118
                Layout.preferredHeight: 36
                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 2
                    Text { text: "JOBS"; color: root._pal("muted_fg", "#8f99a8"); font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Row {
                        spacing: 8
                        Repeater {
                            model: [
                                { "label": "R", "dot": root._pal("accent", "#60cdff") },
                                { "label": "Q", "dot": root._pal("muted_fg", "#8f99a8") },
                                { "label": "D", "dot": root._pal("success", "#63d471") },
                                { "label": "F", "dot": root._pal("error", "#ff5d6c") }
                            ]
                            delegate: Row {
                                id: option2JobDelegate
                                readonly property int count: root._jobCount(modelData.label)
                                spacing: 3
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: modelData.dot; opacity: option2JobDelegate.count > 0 ? 1 : 0.4 }
                                Text { objectName: modelData.label === "R" ? "shellStatusStripJobStatus" : ""; anchors.verticalCenter: parent.verticalCenter; text: option2JobDelegate.count; color: option2JobDelegate.count > 0 ? root._pal("panel_title_fg", "#f0f4fb") : root._pal("muted_fg", "#8f99a8"); font.pixelSize: 12; font.bold: option2JobDelegate.count > 0 }
                            }
                        }
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusJobsRef, "auto") }
            }

            Item { Layout.fillWidth: true }

            Repeater {
                model: [
                    { "label": "CPU", "value": Math.round(root._cpu()) + "%", "ratio": root._ratio(root._cpu(), 100), "width": 92 },
                    { "label": "RAM", "value": root._ram().toFixed(1) + " GB", "ratio": root._ratio(root._ram(), root._ramTotal()), "width": 116 },
                    { "label": "DISK", "value": "R " + root._diskRead().toFixed(1) + " / W " + root._diskWrite().toFixed(1), "ratio": root._ratio(root._diskRead(), Math.max(10, root._diskRead() * 1.3)), "width": 116 }
                ]
                delegate: Item {
                    id: telemetryModule
                    readonly property string moduleLabel: modelData.label
                    readonly property string moduleValue: modelData.value
                    readonly property real moduleRatio: modelData.ratio
                    readonly property real moduleWidth: modelData.width
                    readonly property var moduleHistory: moduleLabel === "CPU"
                        ? root.cpuHistory
                        : (moduleLabel === "RAM" ? root.ramHistory : root.diskReadHistory)
                    readonly property real moduleMaxValue: moduleLabel === "CPU"
                        ? 100
                        : (moduleLabel === "RAM"
                            ? Math.max(1, root._ramTotal())
                            : Math.max(10, root._historyMax(root.diskReadHistory, root._diskRead()) * 1.3))
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: telemetryModule.moduleWidth
                    Layout.preferredHeight: 36
                    Text { anchors.left: parent.left; anchors.top: parent.top; text: telemetryModule.moduleLabel; color: root._pal("muted_fg", "#8f99a8"); font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
                    Text { objectName: telemetryModule.moduleLabel === "CPU" ? "shellStatusStripMetricsStatus" : ""; anchors.right: parent.right; anchors.top: parent.top; text: telemetryModule.moduleValue; color: telemetryModule.moduleLabel === "DISK" ? root._pal("panel_title_fg", "#f0f4fb") : root._metricColor(telemetryModule.moduleRatio); font.pixelSize: telemetryModule.moduleLabel === "DISK" ? 10 : 12; font.bold: true }
                    Canvas {
                        id: telemetrySparkline
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 16
                        readonly property var values: telemetryModule.moduleHistory
                        readonly property real maxValue: telemetryModule.moduleMaxValue
                        readonly property color strokeColor: telemetryModule.moduleLabel === "DISK"
                            ? root._pal("accent", "#60cdff")
                            : root._metricColor(telemetryModule.moduleRatio)
                        onValuesChanged: requestPaint()
                        onMaxValueChanged: requestPaint()
                        onStrokeColorChanged: requestPaint()
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        Component.onCompleted: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.reset();
                            ctx.clearRect(0, 0, width, height);
                            if (width <= 0 || height <= 0)
                                return;

                            var rawValues = telemetrySparkline.values || [];
                            var values = rawValues.length > 0 ? rawValues : [0];
                            var maxValue = Math.max(0.001, telemetrySparkline.maxValue);
                            var points = values.length;
                            var step = points > 1 ? width / (points - 1) : width;
                            ctx.beginPath();
                            ctx.moveTo(0, height);
                            for (var j = 0; j < points; j++) {
                                var fillRatio = Math.max(0, Math.min(1, Number(values[j]) / maxValue));
                                ctx.lineTo(j * step, height - fillRatio * height);
                            }
                            ctx.lineTo(width, height);
                            ctx.closePath();
                            ctx.fillStyle = Qt.alpha(telemetrySparkline.strokeColor, 0.16);
                            ctx.fill();

                            ctx.beginPath();
                            ctx.lineWidth = 1.6;
                            ctx.lineJoin = "round";
                            ctx.lineCap = "round";
                            for (var k = 0; k < points; k++) {
                                var x = k * step;
                                var ratio = Math.max(0, Math.min(1, Number(values[k]) / maxValue));
                                var y = height - ratio * height;
                                if (k === 0)
                                    ctx.moveTo(x, y);
                                else
                                    ctx.lineTo(x, y);
                            }
                            ctx.strokeStyle = telemetrySparkline.strokeColor;
                            ctx.stroke();
                        }
                    }
                }
            }

            Item {
                visible: root._hasFps()
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: root._hasFps() ? 40 : 0
                Layout.preferredHeight: 40
                Canvas {
                    id: fpsGauge
                    anchors.fill: parent
                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.reset();
                        ctx.clearRect(0, 0, width, height);
                        var cx = width / 2;
                        var cy = height / 2;
                        var r = width / 2 - 4;
                        var start = Math.PI * 0.75;
                        var sweep = Math.PI * 1.5;
                        ctx.lineWidth = 4;
                        ctx.lineCap = "round";
                        ctx.beginPath();
                        ctx.arc(cx, cy, r, start, start + sweep);
                        ctx.strokeStyle = Qt.alpha(root._pal("muted_fg", "#8f99a8"), 0.22);
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.arc(cx, cy, r, start, start + sweep * Math.max(0, Math.min(1, root._fps() / 60)));
                        ctx.strokeStyle = root._fpsColor();
                        ctx.stroke();
                    }
                    Component.onCompleted: root._requestFpsGaugePaintIfNeeded(true)
                    onVisibleChanged: if (visible) root._requestFpsGaugePaintIfNeeded(true)
                    onWidthChanged: root._requestFpsGaugePaintIfNeeded(false)
                    onHeightChanged: root._requestFpsGaugePaintIfNeeded(false)
                }
                Column {
                    anchors.centerIn: parent
                    spacing: -2
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: Math.round(root._fps()); color: root._pal("panel_title_fg", "#f0f4fb"); font.pixelSize: 13; font.bold: true }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "FPS"; color: root._pal("muted_fg", "#8f99a8"); font.pixelSize: 7; font.bold: true; font.letterSpacing: 0.5 }
                }
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; Layout.alignment: Qt.AlignVCenter; color: Qt.alpha(root._pal("border", "#3d4652"), 0.8) }

            Item {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: option2NotificationsRow.implicitWidth
                Layout.preferredHeight: 22
                Row {
                    id: option2NotificationsRow
                    anchors.centerIn: parent
                    spacing: 6
                    Repeater {
                        model: [
                            { "label": "W", "dot": root._pal("warning", "#f7c948") },
                            { "label": "E", "dot": root._pal("error", "#ff5d6c") }
                        ]
                        delegate: Rectangle {
                            id: option2NotificationPill
                            readonly property int count: root._notificationCount(modelData.label)
                            width: option2NotificationRow.implicitWidth + 14
                            height: 22
                            radius: 11
                            color: count > 0 ? Qt.alpha(modelData.dot, 0.18) : "transparent"
                            border.width: 1
                            border.color: count > 0 ? Qt.alpha(modelData.dot, 0.55) : Qt.alpha(root._pal("muted_fg", "#8f99a8"), 0.4)
                            Row {
                                id: option2NotificationRow
                                anchors.centerIn: parent
                                spacing: 4
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5; color: option2NotificationPill.count > 0 ? modelData.dot : "transparent"; border.width: option2NotificationPill.count > 0 ? 0 : 1; border.color: root._pal("muted_fg", "#8f99a8") }
                                Text { objectName: modelData.label === "W" ? "shellStatusStripNotificationStatus" : ""; anchors.verticalCenter: parent.verticalCenter; text: option2NotificationPill.count; color: option2NotificationPill.count > 0 ? root._pal("panel_title_fg", "#f0f4fb") : root._pal("muted_fg", "#8f99a8"); font.pixelSize: 11; font.bold: option2NotificationPill.count > 0 }
                            }
                        }
                    }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root._requestStatusAction(root.statusNotificationsRef, "failed") }
            }
        }
    }
}
