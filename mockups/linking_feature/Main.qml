import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

// Throwaway gallery shell for the COREX linking-feature concepts. A top bar with
// a 5-concept switcher + live Dark/Light toggle; a Loader swaps the concepts.
// Theme is one ThemePalette instance passed by reference into each concept (via
// inline Components, so the binding is live from creation — no Loader staleness).
Window {
    id: win
    visible: true
    width: 1240
    height: 780
    title: "COREX — Linking Feature Concepts (P0 mockups)"
    color: pal.appBg

    ThemePalette { id: pal; isDark: true }

    readonly property var conceptNames: ["Omnibox", "Browser dialog", "Drag anchor", "Inspector list", "Hover badge"]
    readonly property var conceptLetters: ["A", "B", "C", "D", "E"]
    readonly property var conceptBlurbs: [
        "Select text or hover a node, then use one smart search/paste popover that auto-detects URLs, files, nodes & workspaces.",
        "A centered dialog with Web / File / Folder / Workspace / Node tabs, recents, and a live preview pane.",
        "Drag from a node's link anchor onto another node, a workspace tab, or empty space to pick a target.",
        "A side dock listing every link on the current selection — open / edit / remove / reorder, and add new ones.",
        "Linked nodes show a chain badge; linked text is underlined; hovering reveals a rich preview card."
    ]
    property int currentIndex: 0

    // ---------- top bar ----------
    Rectangle {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 58
        color: pal.toolbarBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pal.border }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "chain"; size: 24; color: pal.accent }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "COREX · Linking"; color: pal.appFg; font.family: pal.fontFamily; font.pixelSize: 15; font.bold: true }
                Text { text: "P0 interactive concept gallery"; color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 11 }
            }
        }

        Row {
            anchors.centerIn: parent
            spacing: 4
            Repeater {
                model: 5
                delegate: Rectangle {
                    id: tab
                    required property int index
                    readonly property bool active: index === win.currentIndex
                    width: tabRow.implicitWidth + 24
                    height: 36
                    radius: 8
                    color: active ? Qt.rgba(pal.accent.r, pal.accent.g, pal.accent.b, 0.18)
                                  : (tma.containsMouse ? pal.hover : "transparent")
                    border.width: active ? 1 : 0
                    border.color: Qt.rgba(pal.accent.r, pal.accent.g, pal.accent.b, 0.6)
                    Behavior on color { ColorAnimation { duration: 110 } }
                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20; height: 20; radius: 10
                            color: tab.active ? pal.accent : Qt.rgba(pal.mutedFg.r, pal.mutedFg.g, pal.mutedFg.b, 0.22)
                            Text {
                                anchors.centerIn: parent
                                text: win.conceptLetters[tab.index]
                                color: tab.active ? pal.onAccent : pal.mutedFg
                                font.family: pal.fontFamily; font.pixelSize: 11; font.bold: true
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: win.conceptNames[tab.index]
                            color: tab.active ? pal.appFg : pal.mutedFg
                            font.family: pal.fontFamily; font.pixelSize: 13; font.bold: tab.active
                        }
                    }
                    MouseArea { id: tma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: win.currentIndex = tab.index }
                }
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 9
            Text { anchors.verticalCenter: parent.verticalCenter; text: pal.isDark ? "Dark" : "Light"; color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 12 }
            Switch {
                id: themeSwitch
                anchors.verticalCenter: parent.verticalCenter
                checked: pal.isDark
                onToggled: pal.isDark = checked
            }
        }
    }

    // ---------- concept blurb strip ----------
    Rectangle {
        id: blurb
        anchors.top: topBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 30
        color: pal.panelBg
        Behavior on color { ColorAnimation { duration: 200 } }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pal.border }
        Text {
            anchors.left: parent.left; anchors.leftMargin: 18
            anchors.right: parent.right; anchors.rightMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            text: win.conceptLetters[win.currentIndex] + " · " + win.conceptNames[win.currentIndex]
                  + " — " + win.conceptBlurbs[win.currentIndex]
            color: pal.mutedFg
            font.family: pal.fontFamily
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }

    // ---------- concept stage ----------
    Loader {
        id: stageLoader
        anchors.top: blurb.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        sourceComponent: [compA, compB, compC, compD, compE][win.currentIndex]
    }

    Component { id: compA; ConceptA_Omnibox       { theme: pal } }
    Component { id: compB; ConceptB_BrowserDialog  { theme: pal } }
    Component { id: compC; ConceptC_DragAnchor     { theme: pal } }
    Component { id: compD; ConceptD_InspectorList  { theme: pal } }
    Component { id: compE; ConceptE_HoverBadge     { theme: pal } }
}
