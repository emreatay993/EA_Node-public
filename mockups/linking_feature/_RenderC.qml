import QtQuick

// Throwaway render harness: poses Concept C (mid-drag connector + satellite).
Rectangle {
    width: 1180
    height: 720
    ThemePalette { id: pal; isDark: (typeof themeDark !== "undefined") ? themeDark : true }
    color: pal.appBg
    ConceptC_DragAnchor {
        anchors.fill: parent
        theme: pal
        posed: true
    }
}
