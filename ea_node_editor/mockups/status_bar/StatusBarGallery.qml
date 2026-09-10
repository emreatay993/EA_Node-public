import QtQuick 2.15
import QtQuick.Layouts 1.15
import "shared/StatusMockupTheme.js" as Theme
import "shared/StatusScenarios.js" as Scenarios

Rectangle {
    id: root
    objectName: "statusBarGallery"

    property string variantFilter: typeof mockupVariantFilter !== "undefined" ? String(mockupVariantFilter) : "all"
    property string themeFilter: typeof mockupThemeFilter !== "undefined" ? String(mockupThemeFilter) : "both"
    property bool screenshotMode: typeof mockupScreenshotMode !== "undefined" ? Boolean(mockupScreenshotMode) : false

    // In-window override for which themes to render (seeded from the CLI filter).
    property string themeView: root.themeFilter

    readonly property var variantIds: root.variantFilter === "all" ? ["1", "2", "3", "4", "5"] : [root.variantFilter]
    readonly property var themeIds: root.themeView === "both" ? ["dark", "light"] : [root.themeView]
    readonly property bool singlePanel: root.variantIds.length === 1 && root.themeIds.length === 1
    readonly property var galleryPanels: root._buildPanels()
    readonly property var chromePalette: Theme.shellPalette(root.themeView === "light" ? "light" : "dark")

    function _buildPanels() {
        var panels = [];
        for (var i = 0; i < root.variantIds.length; i++) {
            for (var j = 0; j < root.themeIds.length; j++)
                panels.push({ "variant": root.variantIds[i], "theme": root.themeIds[j] });
        }
        return panels;
    }

    function variantSource(variantId) {
        return "variants/StatusBarVariant0" + String(variantId) + ".qml";
    }

    function variantTitle(variantId) {
        switch (String(variantId)) {
        case "1": return "Segmented Pill Cluster";
        case "2": return "Live Telemetry HUD";
        case "3": return "Minimal + Reveal";
        case "4": return "Semantic Ambient Bar";
        default: return "Floating Control Dock";
        }
    }

    function themeLabel(themeName) {
        return String(themeName) === "light" ? "Stitch Light" : "Stitch Dark";
    }

    color: root.chromePalette.app_bg || "#1f1f1f"

    // ---- Shared, live, fake telemetry driving every panel at once ----------
    QtObject {
        id: telemetry
        property string scenario: "running"
        property string engineState: "running"
        property string engineDetail: "Executing graph"
        property int jobsR: 2
        property int jobsQ: 5
        property int jobsD: 12
        property int jobsF: 0
        property bool fpsEnabled: true
        property real fps: 47
        property real cpu: 38
        property real ram: 14.6
        property real ramTotal: 31.8
        property real diskRead: 18.4
        property real diskWrite: 4.2
        property int warnings: 1
        property int errors: 0
        property var cpuHistory: []
        property var ramHistory: []
        property var fpsHistory: []
        property var diskReadHistory: []
        property var diskWriteHistory: []

        property real _baseFps: 47
        property real _baseCpu: 38
        property real _baseRam: 14.6
        property real _baseDiskRead: 18.4
        property real _baseDiskWrite: 4.2

        function applyScenario(name) {
            var p = Scenarios.preset(name);
            scenario = String(name);
            engineState = p.engineState;
            engineDetail = p.engineDetail;
            jobsR = p.jobsR; jobsQ = p.jobsQ; jobsD = p.jobsD; jobsF = p.jobsF;
            ramTotal = p.ramTotal;
            warnings = p.warnings; errors = p.errors;
            fpsEnabled = p.fpsEnabled;
            _baseFps = p.fps; _baseCpu = p.cpu; _baseRam = p.ram;
            _baseDiskRead = p.diskRead; _baseDiskWrite = p.diskWrite;
            fps = p.fps; cpu = p.cpu; ram = p.ram; diskRead = p.diskRead; diskWrite = p.diskWrite;
            var seedC = [], seedR = [], seedF = [], seedDR = [], seedDW = [];
            for (var i = 0; i < 26; i++) {
                seedC.push(p.cpu); seedR.push(p.ram); seedF.push(p.fps);
                seedDR.push(p.diskRead); seedDW.push(p.diskWrite);
            }
            cpuHistory = seedC; ramHistory = seedR; fpsHistory = seedF;
            diskReadHistory = seedDR; diskWriteHistory = seedDW;
        }

        function _clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

        function _push(arr, v) {
            var next = arr.slice();
            next.push(v);
            if (next.length > 26)
                next.shift();
            return next;
        }

        function tick() {
            cpu = _clamp(_baseCpu + (Math.random() - 0.5) * Math.max(8, _baseCpu * 0.35), 0, 100);
            ram = _clamp(_baseRam + (Math.random() - 0.5) * 1.1, 0, ramTotal);
            fps = _clamp(_baseFps + (Math.random() - 0.5) * 9, 1, 120);
            diskRead = _clamp(_baseDiskRead + (Math.random() - 0.5) * Math.max(3, _baseDiskRead * 0.55), 0, 980);
            diskWrite = _clamp(_baseDiskWrite + (Math.random() - 0.5) * Math.max(2, _baseDiskWrite * 0.7), 0, 980);
            cpuHistory = _push(cpuHistory, cpu);
            ramHistory = _push(ramHistory, ram);
            fpsHistory = _push(fpsHistory, fps);
            diskReadHistory = _push(diskReadHistory, diskRead);
            diskWriteHistory = _push(diskWriteHistory, diskWrite);
        }

        Component.onCompleted: applyScenario(scenario)
    }

    Timer {
        interval: 850
        running: true
        repeat: true
        onTriggered: telemetry.tick()
    }

    // ---- Layout -------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.screenshotMode && root.singlePanel ? 16 : 20
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            visible: !(root.screenshotMode && root.singlePanel)

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: "Status / Performance Bar — 5 Design Routes"
                    color: root.chromePalette.panel_title_fg || "#f0f4fb"
                    font.pixelSize: 18
                    font.bold: true
                }
                Text {
                    text: "Modernizing the bottom strip: engine state, jobs, FPS / CPU / RAM, notifications, and the graphics-mode toggle."
                    color: root.chromePalette.muted_fg || "#d0d5de"
                    font.pixelSize: 11
                }
            }

            // Theme-view toggle (Both / Dark / Light)
            Row {
                spacing: 6
                Repeater {
                    model: [
                        { "id": "both", "label": "Both" },
                        { "id": "dark", "label": "Dark" },
                        { "id": "light", "label": "Light" }
                    ]
                    delegate: Rectangle {
                        readonly property bool selected: root.themeView === modelData.id
                        width: Math.max(58, themeLbl.implicitWidth + 20)
                        height: 30
                        radius: 7
                        color: selected
                            ? Qt.alpha(root.chromePalette.accent || "#60CDFF", 0.22)
                            : Qt.alpha(root.chromePalette.toolbar_bg || "#2a2b30", 0.92)
                        border.width: 1
                        border.color: selected
                            ? (root.chromePalette.accent || "#60CDFF")
                            : Qt.alpha(root.chromePalette.input_border || "#4a4f5a", 0.85)
                        Text {
                            id: themeLbl
                            anchors.centerIn: parent
                            text: modelData.label
                            color: selected ? (root.chromePalette.panel_title_fg || "#f0f4fb") : (root.chromePalette.muted_fg || "#d0d5de")
                            font.pixelSize: 11
                            font.bold: selected
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.themeView = modelData.id
                        }
                    }
                }
            }
        }

        // Scenario switcher (drives all panels)
        Row {
            id: scenarioSwitch
            Layout.fillWidth: true
            spacing: 6
            visible: !(root.screenshotMode && root.singlePanel)

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Scenario:"
                color: root.chromePalette.muted_fg || "#d0d5de"
                font.pixelSize: 11
                rightPadding: 4
            }
            Repeater {
                model: Scenarios.ids()
                delegate: Rectangle {
                    readonly property bool selected: telemetry.scenario === modelData
                    width: Math.max(86, scLbl.implicitWidth + 22)
                    height: 30
                    radius: 7
                    color: selected
                        ? Qt.alpha(root.chromePalette.accent || "#60CDFF", 0.22)
                        : Qt.alpha(root.chromePalette.toolbar_bg || "#2a2b30", 0.92)
                    border.width: 1
                    border.color: selected
                        ? (root.chromePalette.accent || "#60CDFF")
                        : Qt.alpha(root.chromePalette.input_border || "#4a4f5a", 0.85)
                    Text {
                        id: scLbl
                        anchors.centerIn: parent
                        text: Scenarios.label(modelData)
                        color: selected ? (root.chromePalette.panel_title_fg || "#f0f4fb") : (root.chromePalette.muted_fg || "#d0d5de")
                        font.pixelSize: 11
                        font.bold: selected
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: telemetry.applyScenario(modelData)
                    }
                }
            }

            Rectangle {
                width: Math.max(92, fpsToggleLbl.implicitWidth + 22)
                height: 30
                radius: 7
                color: telemetry.fpsEnabled
                    ? Qt.alpha(root.chromePalette.accent || "#60CDFF", 0.22)
                    : Qt.alpha(root.chromePalette.toolbar_bg || "#2a2b30", 0.92)
                border.width: 1
                border.color: telemetry.fpsEnabled
                    ? (root.chromePalette.accent || "#60CDFF")
                    : Qt.alpha(root.chromePalette.input_border || "#4a4f5a", 0.85)
                Text {
                    id: fpsToggleLbl
                    anchors.centerIn: parent
                    text: telemetry.fpsEnabled ? "FPS on" : "FPS off"
                    color: telemetry.fpsEnabled ? (root.chromePalette.panel_title_fg || "#f0f4fb") : (root.chromePalette.muted_fg || "#d0d5de")
                    font.pixelSize: 11
                    font.bold: telemetry.fpsEnabled
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: telemetry.fpsEnabled = !telemetry.fpsEnabled
                }
            }
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: panelGrid.implicitWidth
            contentHeight: panelGrid.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            GridLayout {
                id: panelGrid
                width: scroller.width
                columns: root.singlePanel ? 1 : (root.themeIds.length === 2 ? 2 : 1)
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: root.galleryPanels

                    delegate: Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: root.singlePanel
                            ? scroller.width
                            : Math.max(560, (scroller.width - panelGrid.columnSpacing) / panelGrid.columns)
                        Layout.preferredHeight: root.singlePanel ? Math.max(360, scroller.height - 4) : 300

                        Loader {
                            id: variantLoader
                            anchors.fill: parent
                            source: root.variantSource(modelData.variant)

                            onLoaded: {
                                item.width = variantLoader.width;
                                item.height = variantLoader.height;
                                item.themeName = modelData.theme;
                                item.telemetry = telemetry;
                                item.variantTitle = root.variantTitle(modelData.variant) + "  ·  " + root.themeLabel(modelData.theme);
                            }
                            onWidthChanged: if (item) item.width = width
                            onHeightChanged: if (item) item.height = height
                        }

                        Binding {
                            target: variantLoader.item
                            property: "telemetry"
                            value: telemetry
                            when: variantLoader.status === Loader.Ready
                        }
                        Binding {
                            target: variantLoader.item
                            property: "themeName"
                            value: modelData.theme
                            when: variantLoader.status === Loader.Ready
                        }
                    }
                }
            }
        }
    }
}
