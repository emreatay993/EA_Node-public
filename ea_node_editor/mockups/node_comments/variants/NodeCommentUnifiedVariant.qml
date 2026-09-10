import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../shared/NodeCommentMockupTheme.js" as Theme

Rectangle {
    id: root
    objectName: "nodeCommentUnifiedVariant"

    property string themeName: "dark"
    property string variantTitle: "Corner Badge + Inspector Comments"
    property string selectedNodeId: "python"
    property string peekNodeId: "python"
    property bool peekLocked: true
    property string filterMode: "open"

    readonly property var themePalette: Theme.shellPalette(root.themeName)
    readonly property var nodePalette: Theme.nodePalette(root.themeName)
    readonly property var selectedNode: root.nodeFor(root.selectedNodeId)
    readonly property var peekNode: root.nodeFor(root.peekNodeId)
    readonly property int selectedCommentCount: root.commentCount(root.selectedNode)
    readonly property var visibleComments: root.commentsFor(root.selectedNode, root.filterMode)

    radius: 12
    color: root.themePalette.panel_bg
    border.width: 1
    border.color: root.themePalette.border
    clip: true

    function iconSource(name, size, color) {
        if (typeof uiIcons === "undefined" || !uiIcons || !uiIcons.has(name))
            return "";
        return uiIcons.sourceSized(name, size, String(color));
    }

    function nodeFor(nodeId) {
        for (var i = 0; i < nodes.length; ++i) {
            if (String(nodes[i].id) === String(nodeId))
                return nodes[i];
        }
        return nodes[0];
    }

    function commentCount(nodeData) {
        return nodeData && nodeData.comments ? nodeData.comments.length : 0;
    }

    function openCommentCount(nodeData) {
        var count = 0;
        var comments = nodeData && nodeData.comments ? nodeData.comments : [];
        for (var i = 0; i < comments.length; ++i) {
            if (!comments[i].resolved)
                count += 1;
        }
        return count;
    }

    function commentsFor(nodeData, filter) {
        var comments = nodeData && nodeData.comments ? nodeData.comments : [];
        var result = [];
        for (var i = 0; i < comments.length; ++i) {
            var item = comments[i];
            if (filter === "open" && item.resolved)
                continue;
            if (filter === "pinned" && !item.pinned)
                continue;
            result.push(item);
        }
        return result;
    }

    function badgeTone(nodeData) {
        return root.openCommentCount(nodeData) > 0 ? root.themePalette.comment : root.themePalette.success;
    }

    function statusLabel(nodeData) {
        var openCount = root.openCommentCount(nodeData);
        if (openCount === 0)
            return "Resolved";
        return openCount === 1 ? "1 open" : openCount + " open";
    }

    function showPeek(nodeId, locked) {
        root.peekNodeId = String(nodeId || "");
        root.peekLocked = Boolean(locked);
        peekDismissTimer.stop();
    }

    function schedulePeekDismiss() {
        if (root.peekLocked)
            return;
        peekDismissTimer.restart();
    }

    function commentsSummary(nodeData) {
        var count = root.commentCount(nodeData);
        if (count === 0)
            return "No comments";
        var openCount = root.openCommentCount(nodeData);
        if (openCount === 0)
            return count + " resolved comments";
        return count + " comments, " + openCount + " open";
    }

    property var nodes: [
        {
            "id": "tabular",
            "title": "Tabular Data Input",
            "type": "data.table",
            "x": 58,
            "y": 166,
            "w": 210,
            "h": 118,
            "status": "ready",
            "accent": "#64C88A",
            "comments": [
                {
                    "author": "Maya",
                    "time": "09:24",
                    "body": "Keep the preview-only behavior when this feeds a plot.",
                    "tag": "UX",
                    "resolved": false,
                    "pinned": true
                }
            ]
        },
        {
            "id": "python",
            "title": "Python Script",
            "type": "core.python",
            "x": 334,
            "y": 118,
            "w": 230,
            "h": 142,
            "status": "stale",
            "accent": "#60CDFF",
            "comments": [
                {
                    "author": "Emre",
                    "time": "10:11",
                    "body": "Call out the pandas import path before the run button is used.",
                    "tag": "Open",
                    "resolved": false,
                    "pinned": true
                },
                {
                    "author": "Nora",
                    "time": "10:18",
                    "body": "The warning row should stay visible after reconnecting the input.",
                    "tag": "Inspector",
                    "resolved": false,
                    "pinned": false
                },
                {
                    "author": "Ari",
                    "time": "Yesterday",
                    "body": "Renamed output variable to match the downstream plot mapping.",
                    "tag": "Done",
                    "resolved": true,
                    "pinned": false
                }
            ]
        },
        {
            "id": "plot",
            "title": "Scatter Plot",
            "type": "plot.scatter",
            "x": 616,
            "y": 194,
            "w": 208,
            "h": 126,
            "status": "preview",
            "accent": "#8B7CF6",
            "comments": [
                {
                    "author": "Maya",
                    "time": "11:02",
                    "body": "Legend placement is fine; wait on styling until the data shape is stable.",
                    "tag": "Review",
                    "resolved": false,
                    "pinned": false
                },
                {
                    "author": "Emre",
                    "time": "11:16",
                    "body": "Keep render_request available for downstream export.",
                    "tag": "Export",
                    "resolved": false,
                    "pinned": true
                }
            ]
        }
    ]

    Timer {
        id: peekDismissTimer
        interval: 190
        repeat: false
        onTriggered: {
            if (!peekCardMouse.containsMouse && !root.peekLocked)
                root.peekNodeId = "";
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            spacing: 10

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: root.variantTitle
                    color: root.themePalette.panel_title_fg
                    font.pixelSize: 14
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Text {
                    text: root.selectedNode.title + " - " + root.commentsSummary(root.selectedNode)
                    color: root.themePalette.muted_fg
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            Pill {
                label: root.themeName === "light" ? "Light" : "Dark"
                selected: true
                iconName: root.themeName === "light" ? "sun" : "moon"
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 10
            color: root.themePalette.app_bg
            border.width: 1
            border.color: root.themePalette.border
            clip: true

            RowLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 12

                Rectangle {
                    id: canvasPane
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 9
                    color: root.themePalette.canvas_bg
                    border.width: 1
                    border.color: root.themePalette.border
                    clip: true

                    Canvas {
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d");
                            ctx.reset();
                            ctx.fillStyle = root.themePalette.canvas_bg;
                            ctx.fillRect(0, 0, width, height);

                            ctx.lineWidth = 1;
                            ctx.strokeStyle = root.themePalette.canvas_minor_grid;
                            for (var x = 0; x < width; x += 28) {
                                ctx.beginPath();
                                ctx.moveTo(x, 0);
                                ctx.lineTo(x, height);
                                ctx.stroke();
                            }
                            for (var y = 0; y < height; y += 28) {
                                ctx.beginPath();
                                ctx.moveTo(0, y);
                                ctx.lineTo(width, y);
                                ctx.stroke();
                            }
                            ctx.strokeStyle = root.themePalette.canvas_major_grid;
                            for (x = 0; x < width; x += 112) {
                                ctx.beginPath();
                                ctx.moveTo(x, 0);
                                ctx.lineTo(x, height);
                                ctx.stroke();
                            }
                            for (y = 0; y < height; y += 112) {
                                ctx.beginPath();
                                ctx.moveTo(0, y);
                                ctx.lineTo(width, y);
                                ctx.stroke();
                            }

                            function node(id) { return root.nodeFor(id); }
                            function connect(a, b) {
                                var source = node(a);
                                var target = node(b);
                                var x1 = source.x + source.w;
                                var y1 = source.y + source.h * 0.52;
                                var x2 = target.x;
                                var y2 = target.y + target.h * 0.52;
                                ctx.beginPath();
                                ctx.moveTo(x1, y1);
                                ctx.bezierCurveTo(x1 + 74, y1, x2 - 74, y2, x2, y2);
                                ctx.lineWidth = target.id === root.selectedNodeId ? 3 : 2;
                                ctx.strokeStyle = target.id === root.selectedNodeId ? root.themePalette.accent : Qt.alpha(root.themePalette.muted_fg, 0.42);
                                ctx.stroke();
                            }
                            connect("tabular", "python");
                            connect("python", "plot");
                        }
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 6

                        Pill {
                            label: "Preview"
                            selected: true
                            iconName: "eye"
                        }
                        Pill {
                            label: "3 nodes"
                            selected: false
                            iconName: "hierarchy-2"
                        }
                    }

                    Repeater {
                        model: root.nodes

                        delegate: Item {
                            id: nodeShell
                            x: modelData.x
                            y: modelData.y
                            width: modelData.w
                            height: modelData.h
                            z: root.selectedNodeId === modelData.id ? 10 : 5

                            Rectangle {
                                x: 0
                                y: 8
                                width: parent.width
                                height: parent.height
                                radius: 12
                                color: Qt.rgba(0, 0, 0, root.themeName === "light" ? 0.12 : 0.26)
                            }

                            Rectangle {
                                id: nodeCard
                                anchors.fill: parent
                                radius: 10
                                color: root.nodePalette.card_bg
                                border.width: root.selectedNodeId === modelData.id ? 2 : 1
                                border.color: root.selectedNodeId === modelData.id
                                    ? root.nodePalette.card_selected_border
                                    : root.nodePalette.card_border

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 38
                                    radius: 10
                                    color: "transparent"
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: root.nodePalette.header_bg }
                                        GradientStop { position: 1.0; color: root.nodePalette.header_gradient }
                                    }
                                }

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 5
                                    radius: 10
                                    color: modelData.accent
                                    opacity: root.selectedNodeId === modelData.id ? 0.88 : 0.55
                                }

                                Column {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 8

                                    Row {
                                        width: parent.width
                                        spacing: 8

                                        Rectangle {
                                            width: 25
                                            height: 25
                                            radius: 7
                                            color: Qt.alpha(modelData.accent, 0.18)

                                            Image {
                                                anchors.centerIn: parent
                                                width: 15
                                                height: 15
                                                source: root.iconSource(modelData.id === "plot" ? "chart-dots-2" : (modelData.id === "tabular" ? "table" : "code"), 15, modelData.accent)
                                                fillMode: Image.PreserveAspectFit
                                                sourceSize.width: 15
                                                sourceSize.height: 15
                                            }
                                        }

                                        Column {
                                            width: parent.width - 34
                                            spacing: 1

                                            Text {
                                                width: parent.width
                                                text: modelData.title
                                                color: root.nodePalette.header_fg
                                                font.pixelSize: 12
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                width: parent.width
                                                text: modelData.type
                                                color: root.nodePalette.inline_label_fg
                                                font.pixelSize: 10
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }

                                    Rectangle {
                                        width: parent.width
                                        height: 28
                                        radius: 7
                                        color: root.nodePalette.inline_row_bg
                                        border.width: 1
                                        border.color: root.nodePalette.inline_row_border

                                        Row {
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 8
                                            spacing: 6

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: 42
                                                text: "state"
                                                color: root.nodePalette.inline_label_fg
                                                font.pixelSize: 10
                                            }

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: modelData.status
                                                color: root.nodePalette.inline_input_fg
                                                font.pixelSize: 11
                                                font.bold: true
                                            }
                                        }
                                    }

                                    Row {
                                        spacing: 7
                                        Repeater {
                                            model: modelData.id === "plot" ? ["render_request", "figure"] : ["input", "output"]

                                            delegate: Rectangle {
                                                width: Math.max(52, portLabel.implicitWidth + 18)
                                                height: 20
                                                radius: 10
                                                color: Qt.alpha(root.nodePalette.card_selected_border, 0.1)
                                                border.width: 1
                                                border.color: Qt.alpha(root.nodePalette.card_selected_border, 0.34)

                                                Text {
                                                    id: portLabel
                                                    anchors.centerIn: parent
                                                    text: modelData
                                                    color: root.nodePalette.inline_driven_fg
                                                    font.pixelSize: 9
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton
                                    onClicked: {
                                        root.selectedNodeId = modelData.id;
                                        if (root.commentCount(modelData) > 0)
                                            root.showPeek(modelData.id, true);
                                    }
                                    onEntered: {
                                        if (root.commentCount(modelData) > 0)
                                            root.showPeek(modelData.id, false);
                                    }
                                    onExited: root.schedulePeekDismiss()
                                }
                            }

                            CommentBadge {
                                id: commentBadge
                                visible: root.commentCount(modelData) > 0
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.topMargin: -10
                                anchors.rightMargin: -8
                                count: root.commentCount(modelData)
                                openCount: root.openCommentCount(modelData)
                                accentColor: root.badgeTone(modelData)
                                selected: root.peekNodeId === modelData.id
                                onShowRequested: root.showPeek(modelData.id, locked)
                                onHideRequested: root.schedulePeekDismiss()
                            }
                        }
                    }

                    Rectangle {
                        id: peekCard
                        readonly property bool active: root.peekNodeId.length > 0 && !!root.peekNode
                        readonly property real sourceX: root.peekNode ? root.peekNode.x + root.peekNode.w - width * 0.62 : 0
                        readonly property real sourceY: root.peekNode ? root.peekNode.y + 24 : 0
                        width: Math.min(330, Math.max(292, canvasPane.width * 0.42))
                        height: peekColumn.implicitHeight + 24
                        radius: 12
                        visible: opacity > 0.01
                        opacity: active ? 1.0 : 0.0
                        x: Math.max(12, Math.min(sourceX, canvasPane.width - width - 12))
                        y: Math.max(54, Math.min(sourceY, canvasPane.height - height - 12))
                        z: 40
                        color: root.themePalette.panel_alt_bg
                        border.width: 1
                        border.color: root.themePalette.border

                        Behavior on opacity {
                            NumberAnimation { duration: 130; easing.type: Easing.InOutCubic }
                        }

                        Column {
                            id: peekColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 12
                            spacing: 10

                            Row {
                                width: parent.width
                                spacing: 9

                                Rectangle {
                                    width: 30
                                    height: 30
                                    radius: 8
                                    color: Qt.alpha(root.badgeTone(root.peekNode), 0.18)

                                    Image {
                                        anchors.centerIn: parent
                                        width: 17
                                        height: 17
                                        source: root.iconSource("message-circle", 17, root.badgeTone(root.peekNode))
                                        fillMode: Image.PreserveAspectFit
                                        sourceSize.width: 17
                                        sourceSize.height: 17
                                    }
                                }

                                Column {
                                    width: parent.width - 39
                                    spacing: 1

                                    Text {
                                        width: parent.width
                                        text: root.peekNode ? root.peekNode.title : ""
                                        color: root.themePalette.panel_title_fg
                                        font.pixelSize: 13
                                        font.bold: true
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        width: parent.width
                                        text: root.peekNode ? root.commentsSummary(root.peekNode) : ""
                                        color: root.themePalette.muted_fg
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Repeater {
                                model: root.peekNode ? root.commentsFor(root.peekNode, "open").slice(0, 2) : []

                                delegate: Row {
                                    width: parent.width
                                    spacing: 8

                                    Avatar {
                                        author: modelData.author
                                        fillColor: root.themePalette.comment_soft
                                        textColor: root.themePalette.comment
                                    }

                                    Column {
                                        width: parent.width - 34
                                        spacing: 2

                                        Text {
                                            width: parent.width
                                            text: modelData.author + " - " + modelData.time
                                            color: root.themePalette.group_title_fg
                                            font.pixelSize: 10
                                            font.bold: true
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            width: parent.width
                                            text: modelData.body
                                            color: root.themePalette.panel_title_fg
                                            font.pixelSize: 11
                                            wrapMode: Text.WordWrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }

                            Row {
                                width: parent.width
                                spacing: 6

                                ActionButton {
                                    width: 104
                                    label: "Add comment"
                                    iconName: "plus"
                                    accent: true
                                    onClicked: {
                                        root.selectedNodeId = root.peekNodeId;
                                        root.peekLocked = true;
                                    }
                                }

                                ActionButton {
                                    width: 112
                                    label: "Show thread"
                                    iconName: "list-details"
                                    onClicked: {
                                        root.selectedNodeId = root.peekNodeId;
                                        root.peekLocked = true;
                                    }
                                }
                            }
                        }

                        MouseArea {
                            id: peekCardMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                            onEntered: peekDismissTimer.stop()
                            onExited: root.schedulePeekDismiss()
                        }
                    }
                }

                Rectangle {
                    id: inspector
                    Layout.preferredWidth: 344
                    Layout.fillHeight: true
                    radius: 9
                    color: root.themePalette.panel_bg
                    border.width: 1
                    border.color: root.themePalette.border
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 9

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            spacing: 8

                            Rectangle {
                                width: 30
                                height: 30
                                radius: 8
                                color: Qt.alpha(root.selectedNode.accent, 0.18)

                                Image {
                                    anchors.centerIn: parent
                                    width: 17
                                    height: 17
                                    source: root.iconSource(root.selectedNode.id === "plot" ? "chart-dots-2" : (root.selectedNode.id === "tabular" ? "table" : "code"), 17, root.selectedNode.accent)
                                    fillMode: Image.PreserveAspectFit
                                    sourceSize.width: 17
                                    sourceSize.height: 17
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    text: "Inspector"
                                    color: root.themePalette.group_title_fg
                                    font.pixelSize: 10
                                    font.bold: true
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                Text {
                                    text: root.selectedNode.title
                                    color: root.themePalette.panel_title_fg
                                    font.pixelSize: 13
                                    font.bold: true
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            Pill {
                                label: root.statusLabel(root.selectedNode)
                                selected: root.openCommentCount(root.selectedNode) > 0
                                iconName: root.openCommentCount(root.selectedNode) > 0 ? "message-circle" : "check"
                            }
                        }

                        SectionCard {
                            Layout.fillWidth: true
                            title: "Comments"
                            subtitle: root.selectedCommentCount === 1 ? "1 node comment" : root.selectedCommentCount + " node comments"

                            Row {
                                width: parent.width
                                spacing: 6

                                FilterChip {
                                    label: "Open"
                                    selected: root.filterMode === "open"
                                    count: root.openCommentCount(root.selectedNode)
                                    onClicked: root.filterMode = "open"
                                }
                                FilterChip {
                                    label: "All"
                                    selected: root.filterMode === "all"
                                    count: root.selectedCommentCount
                                    onClicked: root.filterMode = "all"
                                }
                                FilterChip {
                                    label: "Pinned"
                                    selected: root.filterMode === "pinned"
                                    count: root.commentsFor(root.selectedNode, "pinned").length
                                    onClicked: root.filterMode = "pinned"
                                }
                            }

                            Text {
                                width: parent.width
                                visible: root.visibleComments.length === 0
                                text: "No comments in this view."
                                color: root.themePalette.muted_fg
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }

                            Column {
                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: root.visibleComments

                                    delegate: CommentRow {
                                        width: parent.width
                                        author: modelData.author
                                        timeText: modelData.time
                                        bodyText: modelData.body
                                        tagText: modelData.tag
                                        resolved: modelData.resolved
                                        pinned: modelData.pinned
                                    }
                                }
                            }

                            Rectangle {
                                width: parent.width
                                radius: 9
                                color: root.themePalette.input_bg
                                border.width: 1
                                border.color: root.themePalette.input_border
                                implicitHeight: composerColumn.implicitHeight + 20

                                Column {
                                    id: composerColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 10
                                    spacing: 8

                                    TextArea {
                                        id: composer
                                        width: parent.width
                                        height: 74
                                        text: root.selectedNode.id === "python"
                                            ? "The input schema warning should link to the table preview row."
                                            : ""
                                        placeholderText: "Add a comment to this node"
                                        color: root.themePalette.input_fg
                                        placeholderTextColor: root.themePalette.muted_fg
                                        selectionColor: Qt.alpha(root.themePalette.accent, 0.32)
                                        selectedTextColor: root.themePalette.panel_title_fg
                                        selectByMouse: true
                                        wrapMode: TextArea.Wrap
                                        font.pixelSize: 11
                                        background: Rectangle {
                                            radius: 7
                                            color: root.themePalette.panel_alt_bg
                                            border.width: 1
                                            border.color: composer.activeFocus ? root.themePalette.accent : root.themePalette.border
                                        }
                                    }

                                    Row {
                                        width: parent.width
                                        spacing: 6

                                        ActionButton {
                                            width: 98
                                            label: "Post"
                                            iconName: "send"
                                            accent: true
                                        }
                                        ActionButton {
                                            width: 92
                                            label: "Pin"
                                            iconName: "pin"
                                        }
                                        ActionButton {
                                            width: 110
                                            label: "Resolve all"
                                            iconName: "check"
                                        }
                                    }
                                }
                            }
                        }

                        SectionCard {
                            Layout.fillWidth: true
                            title: "Node"
                            subtitle: root.selectedNode.type

                            Row {
                                width: parent.width
                                spacing: 7
                                Pill {
                                    label: root.selectedNode.status
                                    selected: true
                                    iconName: "activity"
                                }
                                Pill {
                                    label: "Preview only"
                                    selected: false
                                    iconName: "eye"
                                }
                            }
                        }

                        Item {
                            Layout.fillHeight: true
                        }
                    }
                }
            }
        }
    }

    component SectionCard: Rectangle {
        id: card
        property string title: ""
        property string subtitle: ""
        default property alias bodyData: bodyColumn.data
        radius: 12
        color: root.themePalette.panel_alt_bg
        border.width: 1
        border.color: root.themePalette.border
        implicitHeight: cardColumn.implicitHeight
        clip: true

        Column {
            id: cardColumn
            width: parent.width
            spacing: 0

            Rectangle {
                width: parent.width
                height: headerColumn.implicitHeight + 14
                color: root.themePalette.toolbar_bg

                Column {
                    id: headerColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    spacing: subtitleLabel.visible ? 2 : 0

                    Text {
                        width: parent.width
                        text: card.title.toUpperCase()
                        color: root.themePalette.group_title_fg
                        font.pixelSize: 10
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    Text {
                        id: subtitleLabel
                        width: parent.width
                        visible: card.subtitle.length > 0
                        text: card.subtitle
                        color: root.themePalette.muted_fg
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Item {
                width: parent.width
                implicitHeight: bodyColumn.implicitHeight + 18

                Column {
                    id: bodyColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    spacing: 8
                }
            }
        }
    }

    component Pill: Rectangle {
        id: pill
        property string label: ""
        property string iconName: ""
        property bool selected: false
        width: Math.max(54, pillRow.implicitWidth + 18)
        height: 26
        radius: 13
        color: selected ? Qt.alpha(root.themePalette.accent, 0.18) : root.themePalette.toolbar_bg
        border.width: 1
        border.color: selected ? Qt.alpha(root.themePalette.accent, 0.75) : root.themePalette.border

        Row {
            id: pillRow
            anchors.centerIn: parent
            spacing: 5

            Image {
                visible: pill.iconName.length > 0
                width: 13
                height: 13
                source: root.iconSource(pill.iconName, 13, selected ? root.themePalette.accent : root.themePalette.muted_fg)
                fillMode: Image.PreserveAspectFit
                sourceSize.width: 13
                sourceSize.height: 13
            }

            Text {
                text: pill.label
                color: selected ? root.themePalette.panel_title_fg : root.themePalette.muted_fg
                font.pixelSize: 10
                font.bold: selected
            }
        }
    }

    component FilterChip: Rectangle {
        id: chip
        property string label: ""
        property int count: 0
        property bool selected: false
        signal clicked()
        width: Math.max(66, chipRow.implicitWidth + 18)
        height: 28
        radius: 7
        color: selected ? Qt.alpha(root.themePalette.accent, 0.18) : root.themePalette.toolbar_bg
        border.width: 1
        border.color: selected ? root.themePalette.accent : root.themePalette.border

        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 5

            Text {
                text: chip.label
                color: selected ? root.themePalette.panel_title_fg : root.themePalette.muted_fg
                font.pixelSize: 10
                font.bold: selected
            }

            Rectangle {
                width: Math.max(18, countLabel.implicitWidth + 8)
                height: 16
                radius: 8
                color: selected ? root.themePalette.accent : root.themePalette.hover

                Text {
                    id: countLabel
                    anchors.centerIn: parent
                    text: chip.count
                    color: selected ? root.themePalette.on_accent : root.themePalette.panel_title_fg
                    font.pixelSize: 9
                    font.bold: true
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chip.clicked()
        }
    }

    component ActionButton: Rectangle {
        id: control
        property string label: ""
        property string iconName: ""
        property bool accent: false
        property bool danger: false
        signal clicked()
        height: 30
        radius: 7
        color: accent
            ? root.themePalette.accent
            : (buttonMouse.containsMouse
                ? (danger ? Qt.alpha(root.themePalette.danger, 0.14) : root.themePalette.hover)
                : "transparent")
        border.width: accent ? 0 : 1
        border.color: danger ? Qt.alpha(root.themePalette.danger, 0.36) : root.themePalette.border

        Row {
            anchors.centerIn: parent
            spacing: 5

            Image {
                width: 14
                height: 14
                source: root.iconSource(control.iconName, 14, control.accent ? root.themePalette.on_accent : (control.danger ? root.themePalette.danger : root.themePalette.muted_fg))
                fillMode: Image.PreserveAspectFit
                sourceSize.width: 14
                sourceSize.height: 14
            }

            Text {
                text: control.label
                color: control.accent ? root.themePalette.on_accent : (control.danger ? root.themePalette.danger : root.themePalette.panel_title_fg)
                font.pixelSize: 11
                font.bold: control.accent
                elide: Text.ElideRight
            }
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: control.clicked()
        }
    }

    component Avatar: Rectangle {
        id: avatar
        property string author: ""
        property color fillColor: root.themePalette.accent_soft
        property color textColor: root.themePalette.accent
        width: 26
        height: 26
        radius: 13
        color: fillColor
        border.width: 1
        border.color: Qt.alpha(textColor, 0.35)

        Text {
            anchors.centerIn: parent
            text: Theme.initials(avatar.author)
            color: avatar.textColor
            font.pixelSize: 10
            font.bold: true
        }
    }

    component CommentRow: Rectangle {
        id: row
        property string author: ""
        property string timeText: ""
        property string bodyText: ""
        property string tagText: ""
        property bool resolved: false
        property bool pinned: false
        height: Math.max(64, rowTextColumn.implicitHeight + 20)
        radius: 9
        color: rowMouse.containsMouse ? root.themePalette.hover : "transparent"
        border.width: row.pinned ? 1 : 0
        border.color: Qt.alpha(root.themePalette.comment, 0.42)

        Row {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            Avatar {
                author: row.author
                fillColor: row.resolved ? root.themePalette.success_soft : root.themePalette.comment_soft
                textColor: row.resolved ? root.themePalette.success : root.themePalette.comment
            }

            Column {
                id: rowTextColumn
                width: parent.width - 34 - rowActions.width - 14
                spacing: 3

                Row {
                    width: parent.width
                    spacing: 6

                    Text {
                        text: row.author
                        color: root.themePalette.panel_title_fg
                        font.pixelSize: 11
                        font.bold: true
                    }

                    Text {
                        text: row.timeText
                        color: root.themePalette.muted_fg
                        font.pixelSize: 10
                    }

                    Rectangle {
                        width: Math.max(42, tagTextItem.implicitWidth + 14)
                        height: 18
                        radius: 9
                        color: row.resolved ? root.themePalette.success_soft : root.themePalette.comment_soft
                        border.width: 1
                        border.color: row.resolved ? Qt.alpha(root.themePalette.success, 0.32) : Qt.alpha(root.themePalette.comment, 0.32)

                        Text {
                            id: tagTextItem
                            anchors.centerIn: parent
                            text: row.resolved ? "Done" : row.tagText
                            color: row.resolved ? root.themePalette.success : root.themePalette.comment
                            font.pixelSize: 9
                            font.bold: true
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: row.bodyText
                    color: row.resolved ? root.themePalette.muted_fg : root.themePalette.panel_title_fg
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
            }

            Row {
                id: rowActions
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                opacity: rowMouse.containsMouse ? 1.0 : 0.68

                IconButton { iconName: row.pinned ? "pinned-filled" : "pin" }
                IconButton { iconName: "edit" }
                IconButton {
                    iconName: row.resolved ? "rotate-clockwise" : "check"
                    danger: false
                }
            }
        }

        MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }
    }

    component IconButton: Rectangle {
        id: iconButton
        property string iconName: ""
        property bool danger: false
        width: 24
        height: 24
        radius: 6
        color: iconMouse.containsMouse ? root.themePalette.pressed : "transparent"

        Image {
            anchors.centerIn: parent
            width: 14
            height: 14
            source: root.iconSource(iconButton.iconName, 14, iconButton.danger ? root.themePalette.danger : root.themePalette.muted_fg)
            fillMode: Image.PreserveAspectFit
            sourceSize.width: 14
            sourceSize.height: 14
        }

        MouseArea {
            id: iconMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
        }
    }

    component CommentBadge: Rectangle {
        id: badge
        property int count: 0
        property int openCount: 0
        property color accentColor: root.themePalette.comment
        property bool selected: false
        signal showRequested(bool locked)
        signal hideRequested()
        width: badgeRow.implicitWidth + 16
        height: 24
        radius: 12
        z: 60
        color: selected || badgeMouse.containsMouse
            ? accentColor
            : Qt.alpha(accentColor, 0.9)
        border.width: 1
        border.color: Qt.alpha(root.themePalette.app_fg, root.themeName === "light" ? 0.2 : 0.18)

        Row {
            id: badgeRow
            anchors.centerIn: parent
            spacing: 5

            Image {
                width: 13
                height: 13
                source: root.iconSource(badge.openCount > 0 ? "message-circle" : "message-check", 13, root.themePalette.on_accent)
                fillMode: Image.PreserveAspectFit
                sourceSize.width: 13
                sourceSize.height: 13
            }

            Text {
                text: badge.count
                color: root.themePalette.on_accent
                font.pixelSize: 12
                font.bold: true
            }
        }

        MouseArea {
            id: badgeMouse
            anchors.fill: parent
            anchors.margins: -5
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: badge.showRequested(false)
            onExited: badge.hideRequested()
            onClicked: badge.showRequested(true)
        }
    }
}
