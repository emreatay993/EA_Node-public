import QtQuick
import QtQuick.Controls.Basic
import "LinkData.js" as LinkData

// Concept A — Smart Omnibox Popover.
// Hover a node → a "Link" pill; select body text → a floating "Link" button.
// Either opens one omnibox that auto-detects intent (paste URL / type path /
// search nodes, files & workspaces). A chosen target docks as a chip.
Item {
    id: root
    property var theme
    property bool posed: false   // render-harness hook: open the omnibox for a static capture

    Component.onCompleted: if (posed) Qt.callLater(function () {
        researchLinks.append({ kind: "web", label: "anthropic.com" });
        root.openForNode(canvas.research);
        omniField.text = "b";
    })

    // per-node attached-link stores
    ListModel { id: researchLinks }
    ListModel { id: budgetLinks }
    ListModel { id: briefLinks }
    function modelFor(node) {
        if (node === canvas.research) return researchLinks;
        if (node === canvas.budget) return budgetLinks;
        return briefLinks;
    }

    FauxCanvas { id: canvas; anchors.fill: parent; theme: root.theme }

    // ---- hover "Link" pill on each node ----
    Repeater {
        model: [canvas.research, canvas.budget, canvas.brief]
        delegate: Item {
            id: pill
            required property var modelData
            readonly property var target: modelData
            readonly property bool srcActive: omni.opened && omni.srcNode === target && omni.srcSpan.length === 0
            visible: target && (target.hovered || pillMa.containsMouse || srcActive)
            width: pillRect.width
            height: pillRect.height
            x: target ? target.x + target.width - width + 2 : 0
            y: target ? target.y - height / 2 : 0
            z: 50
            Rectangle {
                id: pillRect
                width: prow.implicitWidth + 18
                height: 26
                radius: 13
                color: pillMa.containsMouse || pill.srcActive ? theme.accentStrong : theme.accent
                Behavior on color { ColorAnimation { duration: 110 } }
                Row {
                    id: prow
                    anchors.centerIn: parent
                    spacing: 5
                    LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "chain"; size: 14; color: theme.onAccent }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: "Link"; color: theme.onAccent; font.family: theme.fontFamily; font.pixelSize: 12; font.bold: true }
                }
                MouseArea {
                    id: pillMa
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.openForNode(pill.target)
                }
            }
        }
    }

    // ---- floating "Link selection" button for the body node ----
    Item {
        id: selBtn
        visible: canvas.brief.hasSelection && !(omni.opened && omni.srcSpan.length > 0)
        z: 50
        property rect r: canvas.brief.hasSelection
            ? canvas.brief.textEdit.positionToRectangle(canvas.brief.textEdit.selectionEnd)
            : Qt.rect(0, 0, 0, 0)
        property point sp: canvas.brief.textEdit.mapToItem(root, r.x, r.y + r.height)
        x: sp.x
        y: sp.y + 5
        width: sbRect.width
        height: sbRect.height
        Rectangle {
            id: sbRect
            width: sbRow.implicitWidth + 18
            height: 26
            radius: 13
            color: sbMa.containsMouse ? theme.accentStrong : theme.accent
            Behavior on color { ColorAnimation { duration: 110 } }
            Row {
                id: sbRow
                anchors.centerIn: parent
                spacing: 5
                LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "chain"; size: 14; color: theme.onAccent }
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Link selection"; color: theme.onAccent; font.family: theme.fontFamily; font.pixelSize: 12; font.bold: true }
            }
            MouseArea {
                id: sbMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openForSpan(canvas.brief.textEdit.selectedText)
            }
        }
    }

    // ---- attached chips beneath each node ----
    component AttachedChips: Flow {
        id: ac
        property var target
        property var linkModel
        x: target ? target.x : 0
        y: target ? target.y + target.height + 9 : 0
        width: target ? target.width + 70 : 200
        spacing: 6
        Repeater {
            model: ac.linkModel
            delegate: Item {
                required property int index
                required property string kind
                required property string label
                width: chip.width
                height: chip.height
                LinkChip {
                    id: chip
                    theme: root.theme
                    kind: parent.kind
                    label: parent.label
                    removable: true
                    onRemoveClicked: ac.linkModel.remove(index)
                }
            }
        }
    }
    AttachedChips { target: canvas.research; linkModel: researchLinks }
    AttachedChips { target: canvas.budget;   linkModel: budgetLinks }
    AttachedChips { target: canvas.brief;    linkModel: briefLinks }

    // ---- omnibox helpers ----
    function openForNode(node) {
        omni.srcNode = node;
        omni.srcSpan = "";
        omniField.clear();
        var px = Math.max(10, Math.min(node.x, root.width - omni.width - 10));
        omni.x = px;
        omni.y = Math.min(node.y + node.height + 14, root.height - 60);
        omni.open();
        omniField.forceActiveFocus();
    }
    function openForSpan(text) {
        omni.srcNode = canvas.brief;
        omni.srcSpan = text;
        omniField.clear();
        omni.x = Math.max(10, Math.min(selBtn.x - 40, root.width - omni.width - 10));
        omni.y = Math.min(selBtn.y + 30, root.height - 60);
        omni.open();
        omniField.forceActiveFocus();
    }
    function commit(kind, label) {
        modelFor(omni.srcNode).append({ kind: kind, label: label });
        omni.close();
    }

    // ---- the omnibox popover ----
    Popup {
        id: omni
        property var srcNode: null
        property string srcSpan: ""
        readonly property var intent: LinkData.detectIntent(omniField.text)
        readonly property var results: LinkData.filterIndex(omniField.text)
        property int current: 0
        width: 392
        padding: 0
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: theme.panelAltBg
            border.width: 1
            border.color: theme.border
            radius: 12
        }

        contentItem: Column {
            spacing: 0

            // source context line
            Item {
                width: parent.width
                height: 26
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right; anchors.rightMargin: 14
                    text: omni.srcSpan.length > 0
                        ? "Linking selected text: “" + omni.srcSpan + "”"
                        : (omni.srcNode ? "Linking node: " + (omni.srcNode.title !== undefined ? omni.srcNode.title : "node") : "")
                    color: theme.mutedFg
                    font.family: theme.fontFamily
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }

            // search field
            Rectangle {
                width: parent.width
                height: 46
                color: "transparent"
                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 12; anchors.rightMargin: 12
                    anchors.topMargin: 1; anchors.bottomMargin: 7
                    radius: 9
                    color: theme.inputBg
                    border.width: 1
                    border.color: omniField.activeFocus ? theme.accent : theme.inputBorder
                    Behavior on border.color { ColorAnimation { duration: 120 } }
                    LinkGlyph { id: sg; anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 16; color: theme.mutedFg }
                    TextField {
                        id: omniField
                        anchors.left: sg.right; anchors.leftMargin: 8
                        anchors.right: parent.right; anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        placeholderText: "Paste a URL, type a path, or search…"
                        placeholderTextColor: theme.mutedFg
                        color: theme.inputFg
                        font.family: theme.fontFamily
                        font.pixelSize: 13
                        background: Item {}
                        onTextChanged: omni.current = 0
                        Keys.onDownPressed: if (omni.intent.kind === "search" || omni.intent.kind === "empty") omni.current = Math.min(omni.current + 1, omni.results.length - 1)
                        Keys.onUpPressed: omni.current = Math.max(omni.current - 1, 0)
                        Keys.onReturnPressed: omni.commitCurrent()
                    }
                }
            }

            // intent-driven content
            Loader {
                width: parent.width
                sourceComponent: {
                    if (omni.intent.kind === "web") return webConfirm;
                    if (omni.intent.kind === "file" || omni.intent.kind === "folder") return fileConfirm;
                    return resultList;
                }
            }
        }

        function commitCurrent() {
            if (intent.kind === "web") { root.commit("web", intent.label); return; }
            if (intent.kind === "file" || intent.kind === "folder") { root.commit(intent.kind, shortPath(intent.label)); return; }
            if (results.length > 0) {
                var r = results[Math.max(0, Math.min(current, results.length - 1))];
                root.commit(r.kind, r.title);
            }
        }
        function shortPath(p) {
            var parts = p.split(/[\\/]/);
            var last = parts[parts.length - 1];
            return last.length > 0 ? last : p;
        }

        // --- confirm rows / results ---
        Component {
            id: webConfirm
            Item {
                height: 64
                ResultRow {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.margins: 8
                    anchors.verticalCenter: parent.verticalCenter
                    theme: root.theme
                    kind: "web"
                    title: "Link to web page"
                    breadcrumb: omni.intent.label
                    current: true
                    onClicked: root.commit("web", omni.intent.label)
                }
            }
        }
        Component {
            id: fileConfirm
            Item {
                height: 64
                ResultRow {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.margins: 8
                    anchors.verticalCenter: parent.verticalCenter
                    theme: root.theme
                    kind: omni.intent.kind
                    title: omni.intent.kind === "folder" ? "Link to folder" : "Link to file"
                    breadcrumb: omni.intent.label
                    current: true
                    onClicked: root.commit(omni.intent.kind, omni.shortPath(omni.intent.label))
                }
            }
        }
        Component {
            id: resultList
            Column {
                topPadding: 4
                bottomPadding: 8
                ListView {
                    id: lv
                    width: omni.width
                    height: Math.min(contentHeight, 252)
                    clip: true
                    model: omni.results
                    interactive: contentHeight > height
                    delegate: Item {
                        required property int index
                        required property var modelData
                        width: lv.width
                        height: 46
                        ResultRow {
                            anchors.fill: parent
                            anchors.leftMargin: 8; anchors.rightMargin: 8
                            anchors.topMargin: 2; anchors.bottomMargin: 2
                            theme: root.theme
                            kind: parent.modelData.kind
                            title: parent.modelData.title
                            breadcrumb: parent.modelData.breadcrumb
                            current: index === omni.current
                            onClicked: root.commit(parent.modelData.kind, parent.modelData.title)
                        }
                    }
                }
                Text {
                    visible: omni.results.length === 0
                    leftPadding: 16; bottomPadding: 12; topPadding: 4
                    text: "No matches. Paste a URL or a file path to link externally."
                    color: theme.mutedFg
                    font.family: theme.fontFamily
                    font.pixelSize: 12
                }
            }
        }
    }

    // hint when nothing is attached yet
    Text {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 16
        text: "Hover a node for the Link pill · select text in “Project Brief” to link a span"
        color: theme.mutedFg
        font.family: theme.fontFamily
        font.pixelSize: 11
        opacity: 0.8
    }
}
