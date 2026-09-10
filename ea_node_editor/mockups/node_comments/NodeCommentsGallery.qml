import QtQuick 2.15
import QtQuick.Layouts 1.15
import "shared/NodeCommentMockupTheme.js" as Theme

Rectangle {
    id: root
    objectName: "nodeCommentsGallery"

    property string variantFilter: typeof mockupVariantFilter !== "undefined" ? String(mockupVariantFilter) : "all"
    property string themeFilter: typeof mockupThemeFilter !== "undefined" ? String(mockupThemeFilter) : "both"
    property bool screenshotMode: typeof mockupScreenshotMode !== "undefined" ? Boolean(mockupScreenshotMode) : false
    property string themeView: root.themeFilter

    readonly property var variantIds: root.variantFilter === "all" ? ["1"] : [root.variantFilter]
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
        return "variants/NodeCommentUnifiedVariant.qml";
    }

    function variantTitle(variantId) {
        return "Corner Badge + Inspector Comments";
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
            spacing: 14
            visible: !(root.screenshotMode && root.singlePanel)

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: "Node Comments"
                    color: root.chromePalette.panel_title_fg || "#f0f4fb"
                    font.pixelSize: 18
                    font.bold: true
                }

                Text {
                    text: "COREX graph node comments with canvas peek and Inspector thread editing."
                    color: root.chromePalette.muted_fg || "#d0d5de"
                    font.pixelSize: 11
                }
            }

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
                        width: Math.max(58, themeLabelText.implicitWidth + 20)
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
                            id: themeLabelText
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
                            onClicked: root.themeView = modelData.id
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
                columns: root.singlePanel ? 1 : (root.themeIds.length === 2 ? 2 : 1)
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: root.galleryPanels

                    delegate: Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: root.singlePanel
                            ? scroller.width
                            : Math.max(640, (scroller.width - panelGrid.columnSpacing) / panelGrid.columns)
                        Layout.preferredHeight: root.singlePanel ? Math.max(680, scroller.height - 4) : 700

                        Loader {
                            id: variantLoader
                            anchors.fill: parent
                            source: root.variantSource(modelData.variant)

                            onLoaded: {
                                item.width = variantLoader.width;
                                item.height = variantLoader.height;
                                item.themeName = modelData.theme;
                                item.variantTitle = root.variantTitle(modelData.variant) + " / " + root.themeLabel(modelData.theme);
                            }

                            onWidthChanged: if (item) item.width = width
                            onHeightChanged: if (item) item.height = height
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
