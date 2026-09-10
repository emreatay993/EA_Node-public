import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "pythonScriptDecoratorGuidePane"

    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property var graphCanvasStateBridgeRef: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    readonly property var themePalette: root.themeBridgeRef ? root.themeBridgeRef.palette : ({})
    readonly property string guideHtml: root._buildGuideHtml()
    signal closeRequested()

    function _color(name, fallback) {
        var value = root.themePalette && root.themePalette[name];
        return value !== undefined && value !== null && String(value).length > 0
            ? String(value)
            : fallback;
    }

    function _buildGuideHtml() {
        var foreground = root._color("app_fg", "#e6edf3");
        var muted = root._color("muted_fg", "#9ba7b4");
        var accent = root._color("accent", "#4f8cff");
        var panel = root._color("panel_bg", "#161b22");
        var input = root._color("input_bg", "#0d1117");
        var border = root._color("border", "#30363d");
        var success = root._color("success", "#55d65b");

        return [
            "<html><head><style>",
            "body { color: ", foreground, "; background-color: ", panel,
                "; font-family: 'Segoe UI', sans-serif; font-size: 12px; line-height: 1.45; margin: 8px; }",
            "h1 { color: ", foreground, "; font-size: 22px; margin: 0 0 6px 0; }",
            "h2 { color: ", accent, "; font-size: 16px; margin: 22px 0 8px 0; }",
            "h3 { color: ", foreground, "; font-size: 13px; margin: 14px 0 5px 0; }",
            "p { margin: 6px 0; }",
            ".hero { background-color: ", input, "; border: 1px solid ", border,
                "; padding: 14px; margin-bottom: 14px; }",
            ".callout { background-color: ", input, "; border-left: 4px solid ", accent,
                "; padding: 9px 11px; margin: 10px 0; }",
            ".success { border-left-color: ", success, "; }",
            ".badge { color: ", accent, "; border: 1px solid ", accent,
                "; padding: 2px 6px; margin-right: 5px; font-weight: 600; }",
            "pre { color: ", foreground, "; background-color: ", input,
                "; border: 1px solid ", border,
                "; font-family: Consolas, monospace; font-size: 11px; padding: 10px; white-space: pre-wrap; }",
            "code { color: ", foreground, "; background-color: ", input,
                "; font-family: Consolas, monospace; }",
            "table { width: 100%; border-collapse: collapse; margin: 8px 0 12px 0; }",
            "th { color: ", foreground, "; background-color: ", input,
                "; border: 1px solid ", border, "; padding: 6px; text-align: left; }",
            "td { color: ", foreground, "; border: 1px solid ", border,
                "; padding: 6px; vertical-align: top; }",
            "ul, ol { margin: 5px 0 8px 20px; padding: 0; }",
            ".muted { color: ", muted, "; }",
            "</style></head><body>",

            "<div class='hero'>",
            "<h1>Python Script customization</h1>",
            "<p>Decorators above <code>run</code> define this node's ports, inline controls, and collapsible sections.</p>",
            "<p><span class='badge'>Apply-safe</span><span class='badge'>Typed ports</span><span class='badge'>Shared controls</span></p>",
            "<p class='muted'>Edit the source, then click <b>Apply</b>. Invalid drafts stay in the editor and do not change the graph.</p>",
            "</div>",

            "<h2>1. Smallest working script</h2>",
            "<pre>@corex.node\n@corex.input(&quot;payload&quot;, value_type=corex.Any)\n@corex.output(&quot;result&quot;, value_type=corex.Any)\ndef run(ctx, payload):\n    return {&quot;result&quot;: payload}</pre>",
            "<div class='callout success'><b>Signature rule:</b> every input or control name must appear once after <code>ctx</code> in <code>run(...)</code>. Returned mapping keys must match declared outputs.</div>",

            "<h2>2. Declare typed ports</h2>",
            "<p>Green canvas handles add input/output decorators with <code>value_type=corex.Any</code>. Red handles remove them; input changes also update the <code>run</code> parameters. Apply or Revert a dirty draft first. Each click is undoable.</p>",
            "<div class='callout'>Handles preserve your function body and comments. After removing a port, update any references or returned output keys before Run. Control decorators are edited in source; port-label rename changes only the display label.</div>",
            "<pre>@corex.input(&quot;values&quot;, value_type=float, structure=&quot;tree&quot;, required=True, section=&quot;Data&quot;)\n@corex.output(&quot;image&quot;, value_type=corex.Image)</pre>",
            "<table><tr><th>Option</th><th>Meaning</th></tr>",
            "<tr><td><code>value_type</code></td><td><code>bool</code>, <code>int</code>, <code>float</code>, <code>str</code>, <code>corex.Any</code>, <code>corex.Image</code>, <code>corex.Color</code>, <code>corex.Interval</code>, or a registered type-ID string.</td></tr>",
            "<tr><td><code>structure</code></td><td><code>&quot;item&quot;</code>, <code>&quot;list&quot;</code>, or <code>&quot;tree&quot;</code>. The default is Item.</td></tr>",
            "<tr><td><code>required=True</code></td><td>Wait for the input before running.</td></tr>",
            "<tr><td><code>section</code></td><td>Place an input in a collapsible on-node group. Outputs remain top-level.</td></tr></table>",

            "<h2>3. Add inline controls</h2>",
            "<table><tr><th>Decorator</th><th>Purpose</th></tr>",
            "<tr><td><code>@corex.text</code></td><td>Single-line text field</td></tr>",
            "<tr><td><code>@corex.number</code></td><td>Integer or floating-point field</td></tr>",
            "<tr><td><code>@corex.switch</code></td><td>Boolean switch</td></tr>",
            "<tr><td><code>@corex.dropdown</code></td><td>Fixed text or integer-coded options</td></tr>",
            "<tr><td><code>@corex.slider</code></td><td>Bounded numeric slider</td></tr>",
            "<tr><td><code>@corex.color</code></td><td>Color value and picker</td></tr>",
            "<tr><td><code>@corex.path</code></td><td>File path field</td></tr>",
            "<tr><td><code>@corex.text_area</code></td><td>Multi-line text field</td></tr>",
            "<tr><td><code>@corex.interval</code></td><td>Endpoint fields or bounded range slider</td></tr>",
            "<tr><td><code>@corex.list</code></td><td>Typed editable list</td></tr></table>",
            "<pre>@corex.switch(&quot;show_legend&quot;, default=True, section=&quot;Display&quot;, port=True)\n@corex.dropdown(&quot;mode&quot;, default=&quot;Mean&quot;, options=(&quot;Mean&quot;, &quot;Maximum&quot;), section=&quot;Settings&quot;)\n@corex.slider(&quot;line_width&quot;, default=2.0, minimum=0.5, maximum=8.0, step=0.5, section=&quot;Display&quot;, port=True)</pre>",

            "<h3>More templates</h3>",
            "<pre>@corex.text(&quot;title&quot;, default=&quot;Plot&quot;, section=&quot;Display&quot;, port=True)\n@corex.number(&quot;count&quot;, default=10, minimum=1, maximum=100, section=&quot;Settings&quot;)\n@corex.color(&quot;accent&quot;, default=&quot;#336699&quot;, section=&quot;Display&quot;)\n@corex.path(&quot;source_file&quot;, default=&quot;&quot;, file_filter=&quot;All files (*)&quot;, section=&quot;Files&quot;)\n@corex.text_area(&quot;notes&quot;, default=&quot;&quot;, section=&quot;Notes&quot;)\n@corex.interval(&quot;bounds&quot;, default=(0.0, 1.0), section=&quot;Ranges&quot;, port=True)\n@corex.list(&quot;labels&quot;, default=[&quot;A&quot;], item_type=str, section=&quot;Data&quot;, port=True)</pre>",

            "<div class='callout'><b><code>port=True</code></b> adds an optional same-name input. A wire temporarily overrides and disables the local control; disconnecting restores the saved value.</div>",
            "<div class='callout'><b><code>section=&quot;...&quot;</code></b> creates a collapsible group. First appearance controls group and row order.</div>",

            "<h2>4. Apply and run</h2>",
            "<ol><li>Click <b>Apply</b> to parse decorators and update the node in one undoable action.</li>",
            "<li>Compatible same-name settings and wires are preserved. Removed or incompatible ports are pruned.</li>",
            "<li>Explicit Run applies a valid dirty draft first. Automatic runs use the last applied source.</li>",
            "<li>Use <code>ctx.log_info(...)</code>, <code>ctx.log_warning(...)</code>, and <code>ctx.log_error(...)</code> for node-scoped messages.</li></ol>",
            "<p class='muted'>The entrypoint must be synchronous and use plain named parameters—no async, <code>*args</code>, or <code>**kwargs</code>.</p>",
            "</body></html>"
        ].join("");
    }

    radius: 4
    color: root.themePalette.panel_bg
    border.width: 1
    border.color: root.themePalette.border

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: root.themePalette.inspector_section_header_bg
            border.color: root.themePalette.border

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 6
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: "Python Script guide"
                    color: root.themePalette.panel_title_fg
                    font.pixelSize: 12
                    font.bold: true
                    elide: Text.ElideRight
                }

                ShellButton {
                    objectName: "pythonScriptDecoratorGuideCloseButton"
                    themeBridgeRef: root.themeBridgeRef
                    graphCanvasStateBridgeRef: root.graphCanvasStateBridgeRef
                    uiIconsRef: root.uiIconsRef
                    text: "Close"
                    tooltipText: "Close the Python Script guide"
                    Accessible.name: "Close Python Script guide"
                    onClicked: root.closeRequested()
                }
            }
        }

        ScrollView {
            id: guideScroll
            objectName: "pythonScriptDecoratorGuideScrollView"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            TextArea {
                id: guideText
                objectName: "pythonScriptDecoratorGuideText"
                width: guideScroll.availableWidth
                readOnly: true
                selectByMouse: true
                wrapMode: TextArea.WrapAtWordBoundaryOrAnywhere
                textFormat: TextEdit.RichText
                text: root.guideHtml
                color: root.themePalette.app_fg
                font.pixelSize: 12
                leftPadding: 12
                rightPadding: 12
                topPadding: 10
                bottomPadding: 16
                background: Rectangle { color: "transparent" }
                Accessible.name: "Python Script customization guide"
            }
        }
    }
}
