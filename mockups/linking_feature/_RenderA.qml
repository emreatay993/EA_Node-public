import QtQuick

// Throwaway render harness: poses Concept A (omnibox open, one chip attached).
Rectangle {
    width: 1180
    height: 720
    ThemePalette { id: pal; isDark: (typeof themeDark !== "undefined") ? themeDark : true }
    color: pal.appBg
    ConceptA_Omnibox {
        anchors.fill: parent
        theme: pal
        posed: true
    }
}
