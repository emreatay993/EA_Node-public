import QtQuick
import "CommentScenarios.js" as Scenarios

// The shared hover peek card (one instance per concept). Owns the show/hide
// choreography: showAt() opens it clamped inside the stage, hideSoon() starts
// a 200ms dismiss timer, and the card's own HoverHandler bridges the pointer
// gap so moving from badge to card doesn't flicker it shut (ConceptE pattern
// from the linking gallery). Actions are inert — this is a design probe.
Item {
    id: card
    property var theme
    property string nodeTitle: ""
    property var comments: []
    property bool shown: false

    readonly property int openCount: Scenarios.openCount(card.comments)
    readonly property var previewComments: (card.comments || []).slice(0, 2)
    readonly property int moreCount: Math.max(0, (card.comments ? card.comments.length : 0) - 2)

    function showAt(title, comments, px, py) {
        card.nodeTitle = title;
        card.comments = comments || [];
        card.x = Math.max(10, Math.min(px, (card.parent ? card.parent.width : px) - card.width - 10));
        card.y = py;
        card.shown = true;
        dismiss.stop();
    }
    function hideSoon() { dismiss.restart() }
    function hideNow() { card.shown = false; dismiss.stop() }

    Timer { id: dismiss; interval: 200; onTriggered: card.shown = false }

    implicitWidth: 286
    implicitHeight: surface.height
    width: implicitWidth
    height: implicitHeight
    z: 100
    opacity: card.shown ? 1 : 0
    visible: opacity > 0.01
    Behavior on opacity { NumberAnimation { duration: 130 } }

    HoverHandler { onHoveredChanged: hovered ? dismiss.stop() : card.hideSoon() }

    Rectangle {            // drop shadow
        x: 1; y: 5
        width: surface.width
        height: surface.height
        radius: surface.radius
        color: Qt.rgba(0, 0, 0, theme.isDark ? 0.42 : 0.16)
    }

    Rectangle {
        id: surface
        width: parent.width
        height: col.implicitHeight + 28
        radius: 12
        color: theme.panelAltBg
        border.width: 1
        border.color: theme.border

        Column {
            id: col
            x: 14; y: 14
            width: parent.width - 28
            spacing: 10

            // ---- header: amber bubble tile + counts ----
            Row {
                width: parent.width
                spacing: 10
                Rectangle {
                    width: 30; height: 30; radius: 7
                    color: theme.commentSoft
                    border.width: 1
                    border.color: theme.commentBorder
                    CommentGlyph { anchors.centerIn: parent; name: "bubble"; size: 17; color: theme.comment }
                }
                Column {
                    width: parent.width - 40
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        width: parent.width
                        text: card.openCount > 0
                              ? "Comments · " + card.openCount + " open"
                              : "Comments · all resolved"
                        color: theme.appFg
                        font.family: theme.fontFamily
                        font.pixelSize: 13
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        text: "on " + card.nodeTitle
                        color: theme.mutedFg
                        font.family: theme.fontFamily
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }
            }

            // ---- up to two comment rows ----
            Repeater {
                model: card.previewComments
                delegate: Row {
                    id: crow
                    required property var modelData
                    readonly property bool resolvedRow: modelData.resolved === true
                    width: col.width
                    spacing: 9
                    opacity: resolvedRow ? 0.55 : 1.0

                    Rectangle {           // initials disc
                        width: 22; height: 22; radius: 11
                        anchors.top: parent.top
                        color: crow.resolvedRow ? theme.successSoft : theme.commentSoft
                        border.width: 1
                        border.color: crow.resolvedRow ? theme.success : theme.commentBorder
                        Text {
                            anchors.centerIn: parent
                            text: theme.initials(crow.modelData.author)
                            color: crow.resolvedRow ? theme.success : theme.comment
                            font.family: theme.fontFamily
                            font.pixelSize: 9
                            font.bold: true
                        }
                    }
                    Column {
                        width: parent.width - 31
                        spacing: 2
                        Row {
                            spacing: 6
                            Text {
                                id: authorText
                                text: crow.modelData.author
                                color: theme.appFg
                                font.family: theme.fontFamily
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text {
                                anchors.baseline: authorText.baseline
                                text: crow.modelData.time
                                color: theme.mutedFg
                                font.family: theme.fontFamily
                                font.pixelSize: 10
                            }
                            CommentGlyph {
                                visible: crow.modelData.pinned === true
                                anchors.verticalCenter: parent.verticalCenter
                                name: "pin"; size: 11; color: theme.mutedFg
                            }
                            CommentGlyph {
                                visible: crow.resolvedRow
                                anchors.verticalCenter: parent.verticalCenter
                                name: "check"; size: 11; color: theme.success
                            }
                        }
                        Text {
                            width: parent.width
                            text: crow.modelData.body
                            color: crow.resolvedRow ? theme.mutedFg : theme.inputFg
                            font.family: theme.fontFamily
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            lineHeight: 1.15
                        }
                    }
                }
            }

            Text {
                visible: card.moreCount > 0
                text: "+" + card.moreCount + " more…"
                color: theme.mutedFg
                font.family: theme.fontFamily
                font.pixelSize: 11
            }

            // ---- inert footer actions ----
            Row {
                spacing: 14
                Text {
                    text: "Open thread ›"
                    color: theme.accent
                    font.family: theme.fontFamily
                    font.pixelSize: 12
                    font.bold: true
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor }
                }
                Text {
                    visible: card.openCount > 0
                    text: "Resolve all"
                    color: theme.mutedFg
                    font.family: theme.fontFamily
                    font.pixelSize: 12
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor }
                }
            }
        }
    }
}
