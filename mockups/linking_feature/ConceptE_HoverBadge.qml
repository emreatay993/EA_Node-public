import QtQuick

// Concept E - Hover Preview Badge + Rich Card.
// Linked nodes show a chain badge with a count; linked text is underlined.
// Hovering a badge or the span reveals a rich preview card
// (with Open / + Add link / Delete link). A short hover timer bridges gap.
Item {
    id: root
    property var theme
    property bool posed: false
    property int researchCount: 2
    property int budgetCount: 1

    FauxCanvas { id: canvas; anchors.fill: parent; theme: root.theme }

    // ---- shared hover-card state ----
    property bool cardOn: false
    property string cKind: "web"
    property string cTitle: ""
    property string cSub: ""
    property string cLinkKey: ""
    property real cx: 0
    property real cy: 0
    Timer { id: dismiss; interval: 200; onTriggered: root.cardOn = false }
    function showCard(k, t, s, key, x, y) {
        cKind = k; cTitle = t; cSub = s; cLinkKey = key;
        cx = Math.max(10, Math.min(x, root.width - hoverCard.width - 10));
        cy = y;
        cardOn = true;
        dismiss.stop();
    }
    function hideSoon() { dismiss.restart() }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        root.showCard("web", "anthropic.com", "https://anthropic.com", "research",
                      canvas.research.x + canvas.research.width - hoverCard.width + 40,
                      canvas.research.y + 20);
    })

    // ---- chain badge on a linked node ----
    component Badge: Item {
        id: badge
        property var target
        property int count: 1
        property string pKind: "web"
        property string pTitle: ""
        property string pSub: ""
        property string pLinkKey: ""
        property bool visibleLink: true
        width: bRect.width
        height: bRect.height
        x: target ? target.x + target.width - width + 8 : 0
        y: target ? target.y - 9 : 0
        z: 40
        visible: visibleLink
        Rectangle {
            id: bRect
            width: bRow.implicitWidth + 16
            height: 24
            radius: 12
            color: bMa.containsMouse ? theme.accent : Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.9)
            border.width: 1
            border.color: theme.isDark ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(0, 0, 0, 0.12)
            Behavior on color { ColorAnimation { duration: 110 } }
            Row {
                id: bRow
                anchors.centerIn: parent
                spacing: 5
                LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "chain"; size: 13; color: theme.onAccent }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: badge.count
                    color: theme.onAccent
                    font.family: theme.fontFamily
                    font.pixelSize: 12
                    font.bold: true
                }
            }
            MouseArea {
                id: bMa
                anchors.fill: parent
                anchors.margins: -4
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onContainsMouseChanged: {
                    if (containsMouse)
                        root.showCard(badge.pKind, badge.pTitle, badge.pSub, badge.pLinkKey,
                                      badge.x + badge.width - hoverCard.width,
                                      badge.y + badge.height + 4);
                    else
                        root.hideSoon();
                }
            }
        }
    }

    Badge {
        target: canvas.research
        count: root.researchCount
        pKind: "web"
        pTitle: "anthropic.com"
        pSub: "https://anthropic.com"
        pLinkKey: "research"
        visibleLink: root.researchCount > 0
    }
    Badge {
        target: canvas.budget
        count: root.budgetCount
        pKind: "file"
        pTitle: "Q3 Report.pdf"
        pSub: "C:\\Users\\me\\Docs"
        pLinkKey: "budget"
        visibleLink: root.budgetCount > 0
    }

    // ---- span hover on the body node ----
    Connections {
        target: canvas.brief
        function onLinkHovered(href) {
            if (href && href.length > 0)
                root.showCard("node", "Budget Model", "Node - Tasks", "brief-budget", canvas.brief.x + 30, canvas.brief.y + 70);
            else
                root.hideSoon();
        }
    }

    // ---- the floating rich card ----
    LinkCard {
        id: hoverCard
        theme: root.theme
        kind: root.cKind
        title: root.cTitle
        subtitle: root.cSub
        deleteAffordance: true
        x: root.cx
        y: root.cy + (root.cardOn ? 0 : 8)
        z: 100
        opacity: root.cardOn ? 1 : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: 130 } }
        Behavior on y { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        HoverHandler { onHoveredChanged: hovered ? dismiss.stop() : root.hideSoon() }
        onDeleteClicked: {
            if (root.cLinkKey === "research") root.researchCount = Math.max(0, root.researchCount - 1);
            else if (root.cLinkKey === "budget") root.budgetCount = Math.max(0, root.budgetCount - 1);
            root.hideSoon();
            root.cLinkKey = "";
        }
    }

    Text {
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Hover a chain badge or the underlined text in \"Project Brief\" to preview the link"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
