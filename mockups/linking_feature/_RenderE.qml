import QtQuick

// Throwaway render harness: poses Concept E (badge + hover card visible).
Rectangle {
    width: 1180
    height: 720
    ThemePalette { id: pal; isDark: (typeof themeDark !== "undefined") ? themeDark : true }
    color: pal.appBg
    ConceptE_HoverBadge {
        anchors.fill: parent
        theme: pal
        posed: true
    }
}
