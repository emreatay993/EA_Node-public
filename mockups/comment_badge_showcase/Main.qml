import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

// Throwaway gallery shell for the COREX node comment-badge concepts (P0). A
// top bar with a 5-concept switcher + live Dark/Light toggle; a Loader swaps
// concepts. Theme is one ThemePalette instance passed by reference into each
// concept (via inline Components, so the binding is live — no Loader
// staleness). `currentIndex` / `darkMode` / `posed` are set from the runner
// via setProperty for --concept / --light / --shot poses.
Window {
    id: win
    visible: true
    width: 1280
    height: 800
    title: "COREX — Node Comment Badge Concepts (P0 mockups)"
    color: pal.appBg

    property bool darkMode: true
    property bool posed: false
    property int currentIndex: 0

    ThemePalette { id: pal; isDark: win.darkMode }

    readonly property var conceptNames: ["Count pill", "Dog-ear fold", "Sticky peek", "Bubble tail", "Dot → chip"]
    readonly property var conceptLetters: ["A", "B", "C", "D", "E"]
    readonly property var conceptBlurbs: [
        "A count pill straddles the bottom edge, shifted left so the resize-grip corner stays free. Amber while open, green once resolved; hover the empty node for the ghost add.",
        "A folded paper corner marks the note — it wants the SAME corner as the resize grip. Hover the node: the fold slides aside to cede the corner. Locked nodes (no grip) keep it parked.",
        "A sticky note peeks from the right edge, above the grip zone by construction. Hovering unfolds it into the note itself — author + first words, no separate popup.",
        "A speech bubble floats outside the corner with a tail pointing at the node — zero grip conflict. Unread comments pulse once to catch the eye.",
        "A minimal dot sits in the bottom edge, left of the grip zone. Hovering the node expands it into a chip with count + first-line preview — quiet at rest, informative on demand."
    ]

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
            CommentGlyph { anchors.verticalCenter: parent.verticalCenter; name: "bubble"; size: 24; color: pal.comment }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "COREX · Node comments"; color: pal.appFg; font.family: pal.fontFamily; font.pixelSize: 15; font.bold: true }
                Text { text: "P0 lower-right badge concept gallery"; color: pal.mutedFg; font.family: pal.fontFamily; font.pixelSize: 11 }
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
                checked: win.darkMode
                onToggled: win.darkMode = checked
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

    Component { id: compA; ConceptA_CountPill  { theme: pal; posed: win.posed } }
    Component { id: compB; ConceptB_DogEar     { theme: pal; posed: win.posed } }
    Component { id: compC; ConceptC_StickyPeek { theme: pal; posed: win.posed } }
    Component { id: compD; ConceptD_BubbleTail { theme: pal; posed: win.posed } }
    Component { id: compE; ConceptE_DotChip    { theme: pal; posed: win.posed } }
}
