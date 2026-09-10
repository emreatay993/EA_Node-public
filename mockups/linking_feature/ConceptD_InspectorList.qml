import QtQuick
import "LinkData.js" as LinkData

// Concept D — Inspector Link List (side dock).
// A right-hand dock lists every link on the current selection. Click a node to
// repopulate it; each row has open / edit / remove on hover and reorder
// chevrons; "+ Add link" appends a new one.
Item {
    id: root
    property var theme
    property bool posed: false
    property var selNode: null

    FauxCanvas {
        id: canvas
        anchors.fill: parent
        theme: root.theme
        onNodeClicked: (node) => root.select(node)
    }

    // per-node link stores (brief comes pre-seeded)
    ListModel { id: researchLinks }
    ListModel { id: budgetLinks }
    ListModel { id: briefLinks }
    function modelFor(node) {
        if (node === canvas.research) return researchLinks;
        if (node === canvas.budget) return budgetLinks;
        return briefLinks;
    }
    function select(node) {
        root.selNode = node;
        canvas.research.selected = (node === canvas.research);
        canvas.budget.selected = (node === canvas.budget);
        canvas.brief.selected = (node === canvas.brief);
    }

    Component.onCompleted: {
        var seed = LinkData.seedLinks();
        for (var i = 0; i < seed.length; i++) briefLinks.append(seed[i]);
        select(canvas.brief);
    }

    readonly property var activeModel: selNode === canvas.research ? researchLinks
                                     : selNode === canvas.budget ? budgetLinks : briefLinks
    readonly property string activeTitle: selNode ? (selNode.title !== undefined ? selNode.title : "Selection") : "—"

    // ---------- side dock ----------
    Rectangle {
        id: dock
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 330
        color: theme.panelBg
        Behavior on color { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Rectangle { anchors.left: parent.left; width: 1; height: parent.height; color: theme.border }

        // header
        Item {
            id: dockHeader
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            height: 64
            Column {
                anchors.left: parent.left; anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Row {
                    spacing: 8
                    LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "chain"; size: 18; color: theme.accent }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: "Links"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 15; font.bold: true }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: cntTxt.implicitWidth + 14; height: 18; radius: 9
                        color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.18)
                        Text { id: cntTxt; anchors.centerIn: parent; text: root.activeModel.count; color: theme.accent; font.family: theme.fontFamily; font.pixelSize: 11; font.bold: true }
                    }
                }
                Text { text: "on  " + root.activeTitle; color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11 }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
        }

        // link rows
        ListView {
            id: lv
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: dockHeader.bottom; anchors.bottom: addRow.top
            anchors.margins: 8
            clip: true
            spacing: 4
            model: root.activeModel
            delegate: Item {
                id: rowItem
                required property int index
                required property string kind
                required property string title
                required property string breadcrumb
                width: ListView.view.width
                height: 56
                readonly property bool showActions: rowMa.containsMouse || actions.hovered || root.posed
                Rectangle {
                    anchors.fill: parent
                    radius: 8
                    color: showActions ? theme.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 90 } }
                }
                // Row-level hover via MouseArea (HoverHandler does NOT receive
                // hover inside a ListView delegate). The action buttons sit on
                // top with their own hover; `actions.hovered` ORs them in so
                // moving onto a button doesn't drop the row hover mid-click.
                MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true }
                Rectangle {
                    id: tile
                    anchors.left: parent.left; anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    width: 32; height: 32; radius: 7
                    property color tint: theme.typeColor(rowItem.kind)
                    color: Qt.rgba(tint.r, tint.g, tint.b, 0.18)
                    LinkGlyph { anchors.centerIn: parent; name: theme.typeGlyph(rowItem.kind); size: 17; color: parent.tint }
                }
                Column {
                    anchors.left: tile.right; anchors.leftMargin: 11
                    anchors.right: actions.left; anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text { width: parent.width; text: rowItem.title; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight }
                    Text { width: parent.width; text: theme.typeLabel(rowItem.kind) + "  ·  " + rowItem.breadcrumb; color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight }
                }
                Row {
                    id: actions
                    anchors.right: parent.right; anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    readonly property bool hovered: b1.hovered || b2.hovered || b3.hovered || b4.hovered || b5.hovered
                    // Always visible (hover delivery to ListView delegates is
                    // unreliable); brighten slightly on row/button hover.
                    opacity: rowItem.showActions ? 1 : 0.7
                    Behavior on opacity { NumberAnimation { duration: 110 } }
                    IconBtn { id: b1; glyph: "chevron"; rot: 180; tip: "up";   onTriggered: if (rowItem.index > 0) root.activeModel.move(rowItem.index, rowItem.index - 1, 1) }
                    IconBtn { id: b2; glyph: "chevron"; rot: 0;   tip: "down"; onTriggered: if (rowItem.index < root.activeModel.count - 1) root.activeModel.move(rowItem.index, rowItem.index + 1, 1) }
                    IconBtn { id: b3; glyph: "open"; onTriggered: {} }
                    IconBtn { id: b4; glyph: "edit"; onTriggered: {} }
                    IconBtn { id: b5; glyph: "x"; danger: true; onTriggered: root.activeModel.remove(rowItem.index) }
                }
            }

            // empty state
            Text {
                anchors.centerIn: parent
                visible: lv.count === 0
                width: parent.width - 40
                horizontalAlignment: Text.AlignHCenter
                text: "No links on “" + root.activeTitle + "” yet.\nClick + Add link below."
                color: theme.mutedFg
                font.family: theme.fontFamily
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }

        // + Add link
        Rectangle {
            id: addRow
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            anchors.margins: 12
            height: 40
            radius: 9
            color: addMa.containsMouse ? theme.hover : "transparent"
            border.width: 1
            border.color: theme.border
            Row {
                anchors.centerIn: parent
                spacing: 7
                LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "plus"; size: 15; color: theme.accent }
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Add link"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: true }
            }
            MouseArea {
                id: addMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                property int n: 0
                onClicked: {
                    var samples = [
                        { kind: "web", title: "anthropic.com", breadcrumb: "https://anthropic.com" },
                        { kind: "node", title: "Risk Register", breadcrumb: "Tasks" },
                        { kind: "folder", title: "Reference Material", breadcrumb: "C:\\Users\\me\\Docs" },
                        { kind: "workspace", title: "Design", breadcrumb: "Project" }
                    ];
                    root.activeModel.append(samples[n % samples.length]);
                    n++;
                }
            }
        }
    }

    // small icon button used in each row's action cluster
    component IconBtn: Rectangle {
        id: ib
        property string glyph: "x"
        property real rot: 0
        property bool danger: false
        property string tip: ""
        signal triggered()
        readonly property bool hovered: ibMa.containsMouse
        width: 26; height: 26; radius: 6
        color: ibMa.containsMouse ? (danger ? Qt.rgba(0.9, 0.3, 0.3, 0.18) : theme.pressed) : "transparent"
        LinkGlyph {
            anchors.centerIn: parent
            name: ib.glyph
            size: 15
            rotation: ib.rot
            color: ib.danger && ibMa.containsMouse ? "#ff7a7a" : (ibMa.containsMouse ? theme.appFg : theme.mutedFg)
        }
        MouseArea { id: ibMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ib.triggered() }
    }

    Text {
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Click a node to see its links · row actions: ↑↓ reorder · open · edit · ✕ remove"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
