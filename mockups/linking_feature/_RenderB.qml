import QtQuick

// Throwaway render harness: poses Concept B (browser dialog open, Node tab).
Rectangle {
    width: 1180
    height: 720
    ThemePalette { id: pal; isDark: (typeof themeDark !== "undefined") ? themeDark : true }
    color: pal.appBg
    ConceptB_BrowserDialog {
        anchors.fill: parent
        theme: pal
        posed: true
    }
}
