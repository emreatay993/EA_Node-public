import QtQuick
import QtQuick.Controls.Basic
import "LinkData.js" as LinkData

// Concept B — Tabbed Link Browser Dialog.
// A centered modal with a Web / File / Folder / Workspace / Node tab rail, a
// browse pane per tab, recents, and a live preview pane. "Insert link" commits.
Item {
    id: root
    property var theme
    property bool posed: false

    // selection being built in the dialog
    property var sel: null
    property string webUrl: ""
    property int currentTab: 0
    readonly property var tabs: [
        { key: "web",       glyph: "globe",     label: "Web page" },
        { key: "file",      glyph: "document",  label: "File" },
        { key: "folder",    glyph: "folder",    label: "Folder" },
        { key: "workspace", glyph: "workspace", label: "Workspace" },
        { key: "node",      glyph: "node",      label: "Node" }
    ]

    FauxCanvas { id: canvas; anchors.fill: parent; theme: root.theme }

    ListModel { id: briefLinks }

    // inserted links shown as chips under the brief node
    Flow {
        x: canvas.brief.x
        y: canvas.brief.y + canvas.brief.height + 9
        width: canvas.brief.width + 80
        spacing: 6
        Repeater {
            model: briefLinks
            delegate: Item {
                required property int index
                required property string kind
                required property string label
                width: c.width; height: c.height
                LinkChip { id: c; theme: root.theme; kind: parent.kind; label: parent.label; removable: true; onRemoveClicked: briefLinks.remove(index) }
            }
        }
    }

    // ---- trigger button ----
    Rectangle {
        id: addBtn
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 18
        width: abRow.implicitWidth + 28
        height: 38
        radius: 9
        color: abMa.containsMouse ? theme.accentStrong : theme.accent
        Behavior on color { ColorAnimation { duration: 110 } }
        Row {
            id: abRow
            anchors.centerIn: parent
            spacing: 8
            LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: "plus"; size: 15; color: theme.onAccent }
            Text { anchors.verticalCenter: parent.verticalCenter; text: "Add link to “Project Brief”"; color: theme.onAccent; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: true }
        }
        MouseArea { id: abMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: dialog.open() }
    }

    function commit() {
        if (!sel) return;
        briefLinks.append({ kind: sel.kind, label: sel.title });
        dialog.close();
    }

    // ---------- dialog ----------
    Popup {
        id: dialog
        width: 740
        height: 470
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, theme.isDark ? 0.55 : 0.32) }

        background: Rectangle {
            color: theme.panelBg
            radius: 14
            border.width: 1
            border.color: theme.border
        }

        contentItem: Item {
            // title bar
            Item {
                id: titleBar
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 52
                Text { anchors.left: parent.left; anchors.leftMargin: 20; anchors.verticalCenter: parent.verticalCenter; text: "Add link"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 16; font.bold: true }
                Rectangle {
                    anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 30; radius: 7
                    color: closeMa.containsMouse ? theme.hover : "transparent"
                    LinkGlyph { anchors.centerIn: parent; name: "x"; size: 16; color: theme.mutedFg }
                    MouseArea { id: closeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: dialog.close() }
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
            }

            // tab rail
            Rectangle {
                id: rail
                anchors.left: parent.left; anchors.top: titleBar.bottom; anchors.bottom: footer.top
                width: 176
                color: theme.panelAltBg
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: theme.border }
                Column {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 3
                    Repeater {
                        model: root.tabs
                        delegate: Rectangle {
                            required property int index
                            required property var modelData
                            readonly property bool active: index === root.currentTab
                            width: parent.width
                            height: 40
                            radius: 8
                            color: active ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16)
                                          : (trMa.containsMouse ? theme.hover : "transparent")
                            Behavior on color { ColorAnimation { duration: 90 } }
                            Rectangle { visible: active; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; width: 3; height: 22; radius: 2; color: theme.accent }
                            Row {
                                anchors.left: parent.left; anchors.leftMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10
                                LinkGlyph { anchors.verticalCenter: parent.verticalCenter; name: modelData.glyph; size: 17; color: active ? theme.accent : theme.mutedFg }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.label; color: active ? theme.appFg : theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: active }
                            }
                            MouseArea { id: trMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { root.currentTab = index; root.sel = null; } }
                        }
                    }
                }
            }

            // center browse pane
            Loader {
                id: pane
                anchors.left: rail.right; anchors.top: titleBar.bottom
                anchors.right: preview.left; anchors.bottom: footer.top
                anchors.margins: 16
                sourceComponent: [webPane, listPane, listPane, listPane, listPane][root.currentTab]
            }

            // preview pane
            Rectangle {
                id: preview
                anchors.right: parent.right; anchors.top: titleBar.bottom; anchors.bottom: footer.top
                width: 236
                color: theme.panelAltBg
                Rectangle { anchors.left: parent.left; width: 1; height: parent.height; color: theme.border }
                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12
                    Text { text: "PREVIEW"; color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1 }
                    LinkCard {
                        visible: root.sel !== null
                        width: parent.width
                        theme: root.theme
                        addAffordance: false
                        kind: root.sel ? root.sel.kind : "web"
                        title: root.sel ? root.sel.title : ""
                        subtitle: root.sel ? root.sel.breadcrumb : ""
                    }
                    Text {
                        visible: root.sel === null
                        width: parent.width
                        text: "Pick a target on the left to preview it here."
                        color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                }
            }

            // footer
            Item {
                id: footer
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                height: 58
                Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: theme.border }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Rectangle {
                        width: 92; height: 36; radius: 8
                        color: cancelMa.containsMouse ? theme.hover : "transparent"
                        border.width: 1; border.color: theme.border
                        Text { anchors.centerIn: parent; text: "Cancel"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 13 }
                        MouseArea { id: cancelMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: dialog.close() }
                    }
                    Rectangle {
                        width: 116; height: 36; radius: 8
                        opacity: root.sel ? 1 : 0.4
                        color: insMa.containsMouse && root.sel ? theme.accentStrong : theme.accent
                        Behavior on color { ColorAnimation { duration: 110 } }
                        Text { anchors.centerIn: parent; text: "Insert link"; color: theme.onAccent; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: true }
                        MouseArea { id: insMa; anchors.fill: parent; hoverEnabled: true; cursorShape: root.sel ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: root.commit() }
                    }
                }
            }
        }

        // --- web pane ---
        Component {
            id: webPane
            Column {
                spacing: 12
                Text { text: "Web address"; color: theme.appFg; font.family: theme.fontFamily; font.pixelSize: 13; font.bold: true }
                Rectangle {
                    width: parent.width; height: 42; radius: 9
                    color: theme.inputBg
                    border.width: 1; border.color: urlField.activeFocus ? theme.accent : theme.inputBorder
                    Behavior on border.color { ColorAnimation { duration: 120 } }
                    LinkGlyph { id: gg; anchors.left: parent.left; anchors.leftMargin: 11; anchors.verticalCenter: parent.verticalCenter; name: "globe"; size: 16; color: theme.mutedFg }
                    TextField {
                        id: urlField
                        anchors.left: gg.right; anchors.leftMargin: 8
                        anchors.right: parent.right; anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        placeholderText: "https://…"
                        placeholderTextColor: theme.mutedFg
                        color: theme.inputFg; font.family: theme.fontFamily; font.pixelSize: 13
                        text: root.webUrl
                        background: Item {}
                        onTextChanged: { root.webUrl = text; root.sel = text.length > 0 ? { kind: "web", title: text.replace(/^https?:\/\//, ""), breadcrumb: text } : null; }
                    }
                }
                Text { text: "Recent"; color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11; font.bold: true; topPadding: 4 }
                Flow {
                    width: parent.width
                    spacing: 7
                    Repeater {
                        model: [
                            { title: "anthropic.com", url: "https://anthropic.com" },
                            { title: "Qt for Python docs", url: "https://doc.qt.io/qtforpython" },
                            { title: "github.com", url: "https://github.com" }
                        ]
                        delegate: LinkChip {
                            required property var modelData
                            theme: root.theme
                            kind: "web"
                            label: modelData.title
                            onClicked: { root.webUrl = modelData.url; root.sel = { kind: "web", title: modelData.title, breadcrumb: modelData.url }; }
                        }
                    }
                }
            }
        }

        // --- shared list pane for file / folder / workspace / node ---
        Component {
            id: listPane
            Item {
                property var rows: {
                    var key = root.tabs[root.currentTab].key;
                    if (key === "file") return [
                        { kind: "file", title: "Q3 Report.pdf", breadcrumb: "C:\\Users\\me\\Docs" },
                        { kind: "file", title: "spec_v4.docx", breadcrumb: "C:\\Users\\me\\Docs" },
                        { kind: "file", title: "interview_notes.md", breadcrumb: "C:\\Users\\me\\Docs\\Research" }
                    ];
                    if (key === "folder") return [
                        { kind: "folder", title: "Reference Material", breadcrumb: "C:\\Users\\me\\Docs" },
                        { kind: "folder", title: "Assets", breadcrumb: "C:\\Users\\me\\Project" },
                        { kind: "folder", title: "Exports", breadcrumb: "C:\\Users\\me\\Project" }
                    ];
                    if (key === "workspace") return LinkData.workspaces;
                    return LinkData.nodes;
                }
                Column {
                    anchors.fill: parent
                    spacing: 10
                    Rectangle {
                        width: parent.width; height: 38; radius: 9
                        color: theme.inputBg
                        border.width: 1; border.color: filterField.activeFocus ? theme.accent : theme.inputBorder
                        LinkGlyph { id: fg; anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 15; color: theme.mutedFg }
                        TextField {
                            id: filterField
                            anchors.left: fg.right; anchors.leftMargin: 8; anchors.right: parent.right; anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            placeholderText: "Filter " + root.tabs[root.currentTab].label.toLowerCase() + "s…"
                            placeholderTextColor: theme.mutedFg
                            color: theme.inputFg; font.family: theme.fontFamily; font.pixelSize: 13
                            background: Item {}
                        }
                    }
                    ListView {
                        id: plv
                        width: parent.width
                        height: parent.height - 48
                        clip: true
                        spacing: 2
                        model: {
                            var q = filterField.text.toLowerCase();
                            if (q.length === 0) return parent.parent.rows;
                            var out = [];
                            var src = parent.parent.rows;
                            for (var i = 0; i < src.length; i++)
                                if (src[i].title.toLowerCase().indexOf(q) !== -1) out.push(src[i]);
                            return out;
                        }
                        delegate: Item {
                            required property var modelData
                            width: plv.width
                            height: 46
                            ResultRow {
                                anchors.fill: parent
                                anchors.bottomMargin: 2; anchors.topMargin: 2
                                theme: root.theme
                                kind: parent.modelData.kind
                                title: parent.modelData.title
                                breadcrumb: parent.modelData.breadcrumb
                                current: root.sel && root.sel.title === parent.modelData.title
                                onClicked: root.sel = { kind: parent.modelData.kind, title: parent.modelData.title, breadcrumb: parent.modelData.breadcrumb }
                            }
                        }
                    }
                }
            }
        }
    }

    Component.onCompleted: if (posed) Qt.callLater(function () {
        root.currentTab = 4;
        root.sel = { kind: "node", title: "Budget Model", breadcrumb: "Tasks" };
        dialog.open();
    })

    Text {
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 16
        text: "Click “Add link” to open the browser · pick a tab, choose a target, preview, then Insert"
        color: theme.mutedFg; font.family: theme.fontFamily; font.pixelSize: 11; opacity: 0.8
    }
}
