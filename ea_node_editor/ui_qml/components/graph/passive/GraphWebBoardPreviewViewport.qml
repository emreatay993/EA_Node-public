import QtQuick 2.15
import "GraphMediaPanelSourceUtils.js" as SourceUtils

Rectangle {
    id: root
    objectName: "graphNodeWebBoardPreviewViewport"
    property var surface: null
    property var webEngineView: null
    property string webEngineDiagnostic: ""
    readonly property bool webEnginePreviewAllowed: !!root.surface && Boolean(root.surface.webEnginePreviewAllowed)
    readonly property string previewSourceRef: _previewSourceRef()
    readonly property string previewImageSource: previewSourceRef.length > 0
        ? SourceUtils.previewSourceUrl(previewSourceRef)
        : ""
    readonly property bool exportedPreviewLoaded: previewImageSource.length > 0 && previewImage.status === Image.Ready
    readonly property string previewDataUrl: "data:text/html;charset=utf-8," + encodeURIComponent(_previewHtml())
    readonly property bool webEngineAvailable: !!webEngineView
    readonly property string previewMode: exportedPreviewLoaded ? "image" : (webEngineAvailable ? "webengine" : "fallback")
    readonly property string webEngineFallbackReason: webEngineAvailable
        ? ""
        : (webEnginePreviewAllowed
            ? "Qt WebEngine is unavailable. Compact metadata preview is shown."
            : "Qt WebEngine preview is disabled. Compact metadata preview is shown.")

    radius: 8
    color: root.surface ? root.surface.viewportFillColor : "#202228"
    border.width: 1
    border.color: Qt.alpha(root.surface ? root.surface.panelBorderColor : "#4a4f5a", 0.86)
    clip: true

    Component.onCompleted: _syncWebEnginePreview()
    onPreviewDataUrlChanged: _syncWebEngineUrl()
    onWebEnginePreviewAllowedChanged: _syncWebEnginePreview()

    function _syncWebEnginePreview() {
        if (!webEnginePreviewAllowed) {
            if (webEngineView) {
                webEngineView.destroy();
                webEngineView = null;
            }
            return;
        }
        if (webEngineView) {
            _syncWebEngineUrl();
            return;
        }
        var qmlSource = [
            "import QtQuick 2.15",
            "import QtWebEngine",
            "WebEngineView {",
            "    objectName: \"graphNodeWebBoardWebEngineView\"",
            "    anchors.fill: parent",
            "    enabled: false",
            "    url: \"about:blank\"",
            "}"
        ].join("\n");
        try {
            webEngineView = Qt.createQmlObject(qmlSource, webEngineLayer, "GraphWebBoardWebEngineView");
            webEngineDiagnostic = "";
            _syncWebEngineUrl();
        } catch (error) {
            webEngineView = null;
            webEngineDiagnostic = String(error || "");
        }
    }

    function _syncWebEngineUrl() {
        if (webEngineView)
            webEngineView.url = previewDataUrl;
    }

    function _previewSourceRef() {
        var ref = root.surface && root.surface.previewRef ? root.surface.previewRef : ({});
        var candidates = [
            ref.uri,
            ref.artifact_ref,
            ref.preview_ref,
            ref.ref,
            ref.artifact_id,
            ref.path
        ];
        for (var index = 0; index < candidates.length; index++) {
            var value = String(candidates[index] || "").trim();
            if (value.length > 0)
                return value;
        }
        return "";
    }

    function _previewHtml() {
        var title = _escapeHtml(root.surface ? root.surface.boardTitle : "Excalidraw board");
        var elements = _escapeHtml(root.surface ? String(root.surface.boardElementCount) : "0");
        var files = _escapeHtml(root.surface ? String(root.surface.boardFileCount) : "0");
        var preview = _escapeHtml(root.surface ? root.surface.previewReferenceLabel : "No exported preview");
        return "<!doctype html><html><head><meta charset=\"utf-8\">"
            + "<style>"
            + "html,body{margin:0;width:100%;height:100%;background:#202228;color:#f0f2f5;"
            + "font-family:Inter,Segoe UI,Arial,sans-serif;overflow:hidden;}"
            + ".wrap{box-sizing:border-box;width:100%;height:100%;padding:18px;display:flex;"
            + "flex-direction:column;justify-content:center;gap:10px;border:1px solid rgba(255,255,255,.10);}"
            + ".title{font-weight:700;font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}"
            + ".meta{display:flex;gap:8px;flex-wrap:wrap;color:#cbd2df;font-size:12px;}"
            + ".chip{border:1px solid rgba(96,205,255,.38);border-radius:6px;padding:5px 7px;background:rgba(96,205,255,.08);}"
            + ".sketch{flex:1;min-height:42px;border:1px dashed rgba(203,210,223,.42);border-radius:8px;position:relative;}"
            + ".sketch:before{content:\"\";position:absolute;left:18%;top:28%;width:38%;height:34%;"
            + "border:2px solid rgba(96,205,255,.72);border-radius:8px;transform:rotate(-3deg);}"
            + ".sketch:after{content:\"\";position:absolute;right:17%;top:37%;width:24%;height:2px;"
            + "background:rgba(240,242,245,.68);box-shadow:0 12px 0 rgba(240,242,245,.42);}"
            + "</style></head><body><div class=\"wrap\">"
            + "<div class=\"title\">" + title + "</div>"
            + "<div class=\"meta\"><span class=\"chip\">" + elements + " elements</span>"
            + "<span class=\"chip\">" + files + " files</span><span class=\"chip\">" + preview + "</span></div>"
            + "<div class=\"sketch\"></div>"
            + "</div></body></html>";
    }

    function _escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    Item {
        id: webEngineLayer
        objectName: "graphNodeWebBoardWebEngineLayer"
        anchors.fill: parent
        visible: root.webEngineAvailable && !root.exportedPreviewLoaded
    }

    Image {
        id: previewImage
        objectName: "graphNodeWebBoardExportedPreviewImage"
        anchors.fill: parent
        anchors.margins: 4
        visible: root.exportedPreviewLoaded
        source: root.previewImageSource
        fillMode: Image.PreserveAspectFit
        smooth: true
        asynchronous: true
        cache: false
    }

    Item {
        id: fallbackLayer
        objectName: "graphNodeWebBoardFallbackPanel"
        anchors.fill: parent
        visible: !root.webEngineAvailable && !root.exportedPreviewLoaded

        Column {
            anchors.centerIn: parent
            width: Math.min(parent.width - 28, 260)
            spacing: 8

            Item {
                width: 44
                height: 36
                anchors.horizontalCenter: parent.horizontalCenter

                Rectangle {
                    x: 5
                    y: 5
                    width: 28
                    height: 20
                    radius: 5
                    color: "transparent"
                    border.width: 2
                    border.color: Qt.alpha(root.surface ? root.surface.accentColor : "#60cdff", 0.82)
                    rotation: -5
                }

                Rectangle {
                    x: 22
                    y: 19
                    width: 16
                    height: 2
                    radius: 1
                    color: Qt.alpha(root.surface ? root.surface.captionTextColor : "#f0f2f5", 0.62)
                }
            }

            Text {
                objectName: "graphNodeWebBoardFallbackTitle"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.surface ? root.surface.boardTitle : "Excalidraw board"
                color: root.surface ? root.surface.captionTextColor : "#f0f2f5"
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
                renderType: root.surface && root.surface.host
                    ? root.surface.host.nodeTextRenderType
                    : Text.CurveRendering
            }

            Text {
                objectName: "graphNodeWebBoardFallbackDetail"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: root.webEngineFallbackReason
                color: root.surface ? root.surface.hintTextColor : "#bdc5d3"
                font.pixelSize: 10
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
                renderType: root.surface && root.surface.host
                    ? root.surface.host.nodeTextRenderType
                    : Text.CurveRendering
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 6

                Repeater {
                    model: root.surface ? root.surface.metadataChips : []

                    delegate: Rectangle {
                        height: 20
                        width: chipText.implicitWidth + 12
                        radius: 5
                        color: Qt.alpha(root.surface ? root.surface.accentColor : "#60cdff", 0.10)
                        border.width: 1
                        border.color: Qt.alpha(root.surface ? root.surface.accentColor : "#60cdff", 0.34)

                        Text {
                            id: chipText
                            anchors.centerIn: parent
                            text: String(modelData || "")
                            color: root.surface ? root.surface.hintTextColor : "#bdc5d3"
                            font.pixelSize: 9
                            renderType: root.surface && root.surface.host
                                ? root.surface.host.nodeTextRenderType
                                : Text.CurveRendering
                        }
                    }
                }
            }
        }
    }
}
