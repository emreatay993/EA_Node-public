import QtQuick 2.15
import QtQuick.Layouts 1.15
import "shared/SelectionMockupTheme.js" as Theme

Rectangle {
    id: root
    objectName: "selectionToolbarGallery"

    property string variantFilter: typeof mockupVariantFilter !== "undefined" ? String(mockupVariantFilter) : "all"
    property string themeFilter: typeof mockupThemeFilter !== "undefined" ? String(mockupThemeFilter) : "both"
    property bool screenshotMode: typeof mockupScreenshotMode !== "undefined" ? Boolean(mockupScreenshotMode) : false
    property string sampleState: "rich"

    readonly property bool singlePanel: root.variantFilter !== "all" && root.themeFilter !== "both"
    readonly property var variantIds: root.variantFilter === "all" ? ["1", "2", "3", "4"] : [root.variantFilter]
    readonly property var themeIds: root.themeFilter === "both" ? ["dark", "light"] : [root.themeFilter]
    readonly property var galleryPanels: root._buildPanels()
    readonly property var chromePalette: Theme.shellPalette(root.themeFilter === "light" ? "light" : "dark")

    function _buildPanels() {
        var panels = [];
        for (var i = 0; i < root.variantIds.length; i++) {
            for (var j = 0; j < root.themeIds.length; j++) {
                panels.push({ "variant": root.variantIds[i], "theme": root.themeIds[j] });
            }
        }
        return panels;
    }

    function variantSource(variantId) {
        return "variants/SelectionToolbarVariant0" + String(variantId) + ".qml";
    }

    function variantTitle(variantId) {
        var id = String(variantId);
        if (id === "1")
            return "Variant 01 - Compact Top Pill";
        if (id === "2")
            return "Variant 02 - Segmented Layout Bar";
        if (id === "3")
            return "Variant 03 - Side Rail";
        return "Variant 04 - Minimal Ghost + Menu";
    }

    function themeLabel(themeName) {
        return String(themeName) === "light" ? "Stitch Light" : "Stitch Dark";
    }

    color: root.chromePalette.app_bg || "#1f1f1f"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.screenshotMode && root.singlePanel ? 16 : 20
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            spacing: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: "Selection Envelope Toolbar Mockups"
                    color: root.chromePalette.panel_title_fg || "#f0f4fb"
                    font.pixelSize: 18
                    font.bold: true
                }

                Text {
                    text: "Temporary selected-object envelope, floating actions, and eligibility states."
                    color: root.chromePalette.muted_fg || "#d0d5de"
                    font.pixelSize: 11
                }
            }

            Row {
                id: stateSwitch
                spacing: 6

                Repeater {
                    model: [
                        { "state": "rich", "label": "3 nodes + edge" },
                        { "state": "two_nodes", "label": "2 nodes" },
                        { "state": "one_node", "label": "1 node" },
                        { "state": "mixed", "label": "mixed" }
                    ]

                    delegate: Rectangle {
                        readonly property bool selected: root.sampleState === modelData.state
                        width: Math.max(76, labelText.implicitWidth + 22)
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
                            id: labelText
                            anchors.centerIn: parent
                            text: modelData.label
                            color: selected
                                ? (root.chromePalette.panel_title_fg || "#f0f4fb")
                                : (root.chromePalette.muted_fg || "#d0d5de")
                            font.pixelSize: 11
                            font.bold: selected
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.sampleState = modelData.state
                        }
                    }
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
                columns: root.singlePanel ? 1 : (root.themeFilter === "both" ? 2 : 1)
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: root.galleryPanels

                    delegate: Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: root.singlePanel ? scroller.width : Math.max(620, (scroller.width - panelGrid.columnSpacing) / panelGrid.columns)
                        Layout.preferredHeight: root.singlePanel ? Math.max(620, scroller.height - 4) : 520

                        Loader {
                            id: variantLoader
                            anchors.fill: parent
                            source: root.variantSource(modelData.variant)

                            onLoaded: {
                                item.width = variantLoader.width;
                                item.height = variantLoader.height;
                                item.themeName = modelData.theme;
                                item.sampleState = root.sampleState;
                                item.variantTitle = root.variantTitle(modelData.variant) + " / " + root.themeLabel(modelData.theme);
                            }

                            onWidthChanged: if (item) item.width = width
                            onHeightChanged: if (item) item.height = height
                        }

                        Binding {
                            target: variantLoader.item
                            property: "sampleState"
                            value: root.sampleState
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
