import QtQuick

// Throwaway render harness: poses Concept D (inspector dock with links).
Rectangle {
    width: 1180
    height: 720
    ThemePalette { id: pal; isDark: (typeof themeDark !== "undefined") ? themeDark : true }
    color: pal.appBg
    ConceptD_InspectorList {
        anchors.fill: parent
        theme: pal
        posed: true
    }
}
