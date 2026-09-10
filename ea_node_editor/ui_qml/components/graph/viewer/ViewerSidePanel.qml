import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../shell"
import "../../common" as Common
import "../../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: sidePanel
    objectName: "viewerSidePanel"
    property var themePalette: typeof themeBridge !== "undefined" ? themeBridge.palette : ({})
    property string nodeId: ""
    property var bridgeRef: typeof viewerControlBridge !== "undefined" ? viewerControlBridge : null
    property var fullscreenBridgeRef: null
    property var hostServiceRef: typeof viewerHostService !== "undefined" ? viewerHostService : null
    property var sessionState: {
        var revision = typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge.sessions_model : [];
        return typeof viewerSessionBridge !== "undefined" && viewerSessionBridge.session_state && nodeId.length
            ? viewerSessionBridge.session_state(nodeId) : ({});
    }
    property bool detachedPresentation: false
    property bool panelCollapsed: true
    property var savedSelections: ({ "published_name": "", "selections": [] })
    property string engineeringToolMessage: ""
    property string selectedSceneId: ""

    function refreshSelections() {
        if (!sidePanel.bridgeRef || !sidePanel.bridgeRef.viewer_saved_selections) {
            sidePanel.savedSelections = ({ "published_name": "", "selections": [] });
            return;
        }
        sidePanel.savedSelections = sidePanel.bridgeRef.viewer_saved_selections(sidePanel.nodeId);
    }

    onNodeIdChanged: {
        selectedSceneId = "";
        refreshSelections();
    }
    Component.onCompleted: {
        refreshSelections();
    }

    readonly property var sessionOptions: sessionState.options ? sessionState.options : ({})
    readonly property var sessionSummary: sessionState.summary ? sessionState.summary : ({})
    readonly property var sceneLayers: sessionSummary.scene_layers || []
    readonly property int selectedSceneIndex: {
        for (var index = 0; index < sceneLayers.length; ++index) {
            if (String(sceneLayers[index].id || "") === selectedSceneId)
                return index;
        }
        return sceneLayers.length ? 0 : -1;
    }
    readonly property var selectedScene: selectedSceneIndex >= 0 ? sceneLayers[selectedSceneIndex] : ({})
    readonly property var selectedSceneStyle: (sessionOptions.scene_styles || {})[String(selectedScene.id || "")] || ({})
    readonly property var infoSummary: engineeringViewer ? selectedScene : sessionSummary
    readonly property var capabilities: sessionSummary.capabilities ? sessionSummary.capabilities : ({})
    readonly property bool engineeringViewer: String(sessionSummary.viewer_kind || "") === "engineering_scene"
    readonly property bool supportsScalars: (capabilities.scalar_results === undefined
        ? true : Boolean(capabilities.scalar_results))
        && (!engineeringViewer || Boolean(capabilities.live_field_controls))
    readonly property bool supportsDeformation: capabilities.deformation === undefined
        ? true : Boolean(capabilities.deformation)
    readonly property bool supportsProbe: capabilities.probe === undefined
        ? true : Boolean(capabilities.probe)
    readonly property bool supportsMinmax: capabilities.minmax === undefined
        ? true : Boolean(capabilities.minmax)
    readonly property bool supportsModelTree: Boolean(capabilities.model_tree)
    readonly property bool supportsSceneLayers: Boolean(capabilities.scene_layers)
    readonly property bool supportsClipping: Boolean(capabilities.clipping)
    readonly property bool supportsMeasurements: Boolean(engineeringViewer
        ? (selectedScene.capabilities || {}).measure : capabilities.measure)
    readonly property bool supportsNeutralExport: Boolean(capabilities.export_3d)
    // Query/export controls follow the exact backend capability advertised by
    // the active source; the shared bridge provides the node-scoped transport.
    readonly property bool queryAvailable: Boolean(capabilities.live_query_transport)
    readonly property var renderStats: {
        var overlayRevision = sidePanel.hostServiceRef
            && sidePanel.hostServiceRef.viewer_overlay_revision !== undefined
            ? sidePanel.hostServiceRef.viewer_overlay_revision
            : 0;
        void(overlayRevision);
        if (!sidePanel.hostServiceRef
                || !sidePanel.hostServiceRef.viewer_render_stats
                || sidePanel.nodeId.length === 0)
            return ({});
        return sidePanel.hostServiceRef.viewer_render_stats(sidePanel.nodeId);
    }
    readonly property string statsUnit: String((engineeringViewer ? "" : sidePanel.renderStats.unit)
        || sidePanel.infoSummary.unit || "")
    readonly property var componentValues: ["magnitude", "x", "y", "z"]
    readonly property var rangeModeValues: ["auto", "custom"]
    readonly property var colormapValues: ["jet", "viridis", "turbo", "rainbow", "plasma", "coolwarm", "gray"]
    readonly property var backgroundValues: ["theme", "white", "black", "gray"]

    // Snap the width: the native-overlay geometry sync has a bounded retry
    // budget, so the viewport rect must settle immediately, not animate.
    implicitWidth: panelCollapsed ? 28 : 288
    color: themePalette.panel_bg
    border.width: 1
    border.color: themePalette.input_border
    radius: 6
    clip: true

    function setViewerOption(key, value) {
        if (!sidePanel.bridgeRef || !sidePanel.bridgeRef.set_viewer_option)
            return false;
        return Boolean(sidePanel.bridgeRef.set_viewer_option(sidePanel.nodeId, String(key || ""), value));
    }

    function setSceneStyle(key, value) {
        if (!sidePanel.bridgeRef || !sidePanel.bridgeRef.set_scene_style || !sidePanel.selectedScene.id)
            return false;
        var accepted = sidePanel.bridgeRef.set_scene_style(
            sidePanel.nodeId, String(sidePanel.selectedScene.id), key, value
        );
        sidePanel.engineeringToolMessage = accepted ? "" : "Use opacity from 0 to 1, or a color in #RRGGBB format.";
        return Boolean(accepted);
    }

    function renderModeSupported(mode) {
        var modes = sidePanel.capabilities.supported_render_modes
            || sidePanel.sessionSummary.supported_render_modes;
        if (!modes || modes.length === undefined)
            return !sidePanel.engineeringViewer;
        for (var index = 0; index < modes.length; ++index) {
            if (String(modes[index]) === String(mode || ""))
                return true;
        }
        return false;
    }

    function modelTreeDepth(entry) {
        var items = sidePanel.sessionSummary.model_tree || [];
        var parentId = String(entry && entry.parent_id ? entry.parent_id : "");
        var depth = 0;
        while (parentId.length > 0 && depth < 12) {
            var nextParent = "";
            for (var index = 0; index < items.length; ++index) {
                if (String(items[index].id || "") === parentId) {
                    nextParent = String(items[index].parent_id || "");
                    break;
                }
            }
            parentId = nextParent;
            depth += 1;
        }
        return depth;
    }

    function runEngineeringQuery(queryType) {
        if (!sidePanel.bridgeRef || !sidePanel.bridgeRef.query_viewer)
            return false;
        var result = sidePanel.bridgeRef.query_viewer(sidePanel.nodeId, String(queryType || ""),
            { "layer_id": String(sidePanel.selectedScene.id || "") });
        sidePanel.engineeringToolMessage = result && result.pending
            ? String(result.explanation || "Engineering query queued.")
            : result && result.supported
            ? JSON.stringify(result.value || ({}))
            : String(result && result.explanation ? result.explanation : "Engineering query is unavailable.");
        return Boolean(result && (result.pending || result.supported));
    }

    function runEngineeringExport(exportFormat) {
        if (!sidePanel.bridgeRef || !sidePanel.bridgeRef.export_engineering_viewer)
            return false;
        var result = sidePanel.bridgeRef.export_engineering_viewer(sidePanel.nodeId, String(exportFormat || ""));
        sidePanel.engineeringToolMessage = result && result.pending
            ? String(result.explanation || "Engineering export queued.")
            : result && result.supported
            ? "Exported " + String(result.value && result.value.path ? result.value.path : "scene")
            : String(result && result.explanation ? result.explanation : "Engineering export is unavailable.");
        return Boolean(result && (result.pending || result.supported));
    }

    Connections {
        target: sidePanel.bridgeRef
        ignoreUnknownSignals: true
        function onViewerControlChanged(changedNodeId) {
            if (String(changedNodeId) !== sidePanel.nodeId)
                return;
            sidePanel.refreshSelections();
        }
        function onViewerQueryCompleted(completedNodeId, result) {
            if (String(completedNodeId) !== sidePanel.nodeId)
                return;
            if (String(result.query_type || "") === "export" && result.supported) {
                sidePanel.engineeringToolMessage = "Exported "
                    + String(result.value && result.value.path ? result.value.path : "scene");
            } else {
                sidePanel.engineeringToolMessage = result && result.supported
                    ? JSON.stringify(result.value || ({}))
                    : String(result && result.explanation
                        ? result.explanation : "Engineering query failed.");
            }
        }
    }

    function _formatStat(value) {
        var numeric = Number(value);
        if (!isFinite(numeric))
            return "—";
        var magnitude = Math.abs(numeric);
        var text = (magnitude >= 1e5 || (magnitude > 0 && magnitude < 1e-3))
            ? numeric.toExponential(4)
            : String(Number(numeric.toPrecision(6)));
        return sidePanel.statsUnit.length > 0 ? text + " " + sidePanel.statsUnit : text;
    }

    component PanelField: TextField {
        id: panelField
        Layout.fillWidth: true
        Layout.preferredHeight: 24
        font.pixelSize: 11
        color: enabled ? sidePanel.themePalette.tab_fg : sidePanel.themePalette.muted_fg
        placeholderTextColor: sidePanel.themePalette.muted_fg
        selectionColor: sidePanel.themePalette.accent
        selectedTextColor: sidePanel.themePalette.tab_selected_fg
        background: Rectangle {
            radius: 4
            color: sidePanel.themePalette.input_bg
            border.width: 1
            border.color: panelField.activeFocus
                ? sidePanel.themePalette.accent
                : sidePanel.themePalette.input_border
        }
    }

    component PanelCheck: CheckBox {
        id: panelCheck
        font.pixelSize: 11
        spacing: 6
        indicator: Rectangle {
            implicitWidth: 15
            implicitHeight: 15
            x: panelCheck.leftPadding
            y: panelCheck.height / 2 - height / 2
            radius: 3
            color: panelCheck.checked
                ? sidePanel.themePalette.accent
                : sidePanel.themePalette.input_bg
            border.width: 1
            border.color: panelCheck.checked
                ? sidePanel.themePalette.accent
                : sidePanel.themePalette.input_border
            Text {
                anchors.centerIn: parent
                visible: panelCheck.checked
                text: "✓"
                color: sidePanel.themePalette.tab_selected_fg
                font.pixelSize: 10
                font.bold: true
            }
        }
        contentItem: Text {
            text: panelCheck.text
            color: sidePanel.themePalette.tab_fg
            font: panelCheck.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            leftPadding: panelCheck.indicator.width + panelCheck.spacing
        }
    }

    Text {
        id: panelTitle
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.topMargin: 8
        anchors.leftMargin: 10
        visible: !sidePanel.panelCollapsed
        text: "View Properties"
        color: sidePanel.themePalette.panel_title_fg
        font.pixelSize: 12
        font.bold: true
    }

    ToolButton {
        id: collapseButton
        objectName: "contentFullscreenViewerSidePanelToggle"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 3
        width: 22
        height: 22
        z: 2
        hoverEnabled: true
        onClicked: sidePanel.panelCollapsed = !sidePanel.panelCollapsed
        background: Rectangle {
            radius: 4
            color: collapseButton.hovered ? sidePanel.themePalette.input_bg : "transparent"
        }
        contentItem: Text {
            text: sidePanel.panelCollapsed ? "‹" : "›"
            color: sidePanel.themePalette.tab_fg
            font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    Rectangle {
        id: panelHeaderSeparator
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 30
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        height: 1
        visible: !sidePanel.panelCollapsed
        color: sidePanel.themePalette.input_border
    }

    Flickable {
        anchors.fill: parent
        anchors.margins: 10
        anchors.topMargin: 38
        visible: !sidePanel.panelCollapsed
        contentWidth: width
        contentHeight: panelColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: panelColumn
            width: parent.width
            spacing: 8

            Text {
                text: "Model"
                visible: sidePanel.supportsModelTree
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            Repeater {
                model: sidePanel.supportsModelTree && sidePanel.sessionSummary.model_tree
                    ? sidePanel.sessionSummary.model_tree : []

                Text {
                    Layout.fillWidth: true
                    leftPadding: 10 * sidePanel.modelTreeDepth(modelData)
                    text: String(modelData.name || modelData.id || "Entity")
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 10
                    elide: Text.ElideMiddle
                }
            }

            Repeater {
                model: sidePanel.supportsModelTree && sidePanel.sessionSummary.scene_layers
                    ? sidePanel.sessionSummary.scene_layers : []

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    property string layerId: String(modelData.id || "")
                    property string layerName: String(modelData.name || ("Layer " + (index + 1)))
                    property bool layerVisible: {
                        var layers = sidePanel.renderStats.layers || [];
                        for (var itemIndex = 0; itemIndex < layers.length; ++itemIndex) {
                            if (String(layers[itemIndex].id || "") === layerId)
                                return Boolean(layers[itemIndex].visible);
                        }
                        return modelData.visible === undefined ? true : Boolean(modelData.visible);
                    }

                    Text {
                        text: parent.layerName
                        color: sidePanel.themePalette.tab_fg
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    ShellButton {
                        text: parent.layerVisible ? "Hide" : "Show"
                        Layout.preferredWidth: 46
                        onClicked: {
                            if (sidePanel.hostServiceRef && sidePanel.hostServiceRef.set_viewer_layer_visibility)
                                sidePanel.hostServiceRef.set_viewer_layer_visibility(
                                    sidePanel.nodeId, parent.layerId, !parent.layerVisible
                                );
                        }
                    }
                    ShellButton {
                        text: "Iso"
                        Layout.preferredWidth: 34
                        onClicked: {
                            if (sidePanel.hostServiceRef && sidePanel.hostServiceRef.isolate_viewer_layer)
                                sidePanel.hostServiceRef.isolate_viewer_layer(sidePanel.nodeId, parent.layerId);
                        }
                    }
                }
            }

            Text {
                visible: Boolean(sidePanel.sessionSummary.warnings
                    && sidePanel.sessionSummary.warnings.length > 0)
                text: visible ? String(sidePanel.sessionSummary.warnings[0]) : ""
                color: sidePanel.themePalette.muted_fg
                font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Text {
                visible: sidePanel.engineeringViewer
                    && Boolean(sidePanel.capabilities.scalar_results)
                    && !sidePanel.supportsScalars
                text: "Field, time, and deformation controls are unavailable until the engineering transport provides live field updates."
                color: sidePanel.themePalette.muted_fg
                font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Text {
                text: "Clipping"
                visible: sidePanel.supportsClipping
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            RowLayout {
                visible: sidePanel.supportsClipping
                Layout.fillWidth: true
                spacing: 5

                PanelCheck {
                    objectName: "viewerSidePanelClipEnabledCheck"
                    text: "Enable"
                    checked: Boolean(sidePanel.sessionOptions.clip_enabled)
                    onToggled: sidePanel.setViewerOption("clip_enabled", checked)
                }
                ComboBox {
                    objectName: "viewerSidePanelClipAxisCombo"
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 24
                    model: ["X", "Y", "Z"]
                    currentIndex: Math.max(0, ["x", "y", "z"].indexOf(
                        String(sidePanel.sessionOptions.clip_axis || "x").toLowerCase()
                    ))
                    onActivated: function(index) {
                        sidePanel.setViewerOption("clip_axis", ["x", "y", "z"][index]);
                    }
                }
                PanelField {
                    objectName: "viewerSidePanelClipOffsetField"
                    text: String(sidePanel.sessionOptions.clip_offset || 0)
                    placeholderText: "Offset"
                    onEditingFinished: sidePanel.setViewerOption("clip_offset", text)
                }
            }

            Text {
                visible: sidePanel.engineeringViewer && !sidePanel.supportsClipping
                text: "Clipping is unavailable for this scene."
                color: sidePanel.themePalette.muted_fg
                font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            GridLayout {
                columns: 2
                columnSpacing: 8
                rowSpacing: 6
                Layout.fillWidth: true

                Text {
                    text: "Colormap"
                    visible: sidePanel.supportsScalars
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ComboBox {
                    objectName: "viewerSidePanelColormapCombo"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    model: sidePanel.colormapValues
                    visible: sidePanel.supportsScalars
                    font.pixelSize: 11
                    currentIndex: Math.max(
                        0,
                        sidePanel.colormapValues.indexOf(String(sidePanel.sessionOptions.colormap || "jet"))
                    )
                    palette.buttonText: sidePanel.themePalette.tab_fg
                    palette.text: sidePanel.themePalette.tab_fg
                    palette.highlight: sidePanel.themePalette.accent
                    palette.base: sidePanel.themePalette.input_bg
                    palette.window: sidePanel.themePalette.panel_bg
                    onActivated: function(index) {
                        sidePanel.setViewerOption("colormap", sidePanel.colormapValues[index]);
                    }
                }

                Text {
                    text: "Background"
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ComboBox {
                    objectName: "viewerSidePanelBackgroundCombo"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    model: ["Theme", "White", "Black", "Gray"]
                    font.pixelSize: 11
                    currentIndex: Math.max(
                        0,
                        sidePanel.backgroundValues.indexOf(
                            String(sidePanel.sessionOptions.viewer_background || "theme").toLowerCase()
                        )
                    )
                    palette.buttonText: sidePanel.themePalette.tab_fg
                    palette.text: sidePanel.themePalette.tab_fg
                    palette.highlight: sidePanel.themePalette.accent
                    palette.base: sidePanel.themePalette.input_bg
                    palette.window: sidePanel.themePalette.panel_bg
                    onActivated: function(index) {
                        sidePanel.setViewerOption("viewer_background", sidePanel.backgroundValues[index]);
                    }
                }

                Text {
                    text: "Scene"
                    visible: sidePanel.supportsSceneLayers
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ComboBox {
                    objectName: "viewerSidePanelSceneSelector"
                    Accessible.name: "Scene"
                    Layout.fillWidth: true
                    visible: sidePanel.supportsSceneLayers
                    model: sidePanel.sceneLayers
                    textRole: "name"
                    currentIndex: sidePanel.selectedSceneIndex
                    palette.text: sidePanel.themePalette.tab_fg
                    palette.buttonText: sidePanel.themePalette.tab_fg
                    palette.base: sidePanel.themePalette.input_bg
                    palette.window: sidePanel.themePalette.panel_bg
                    palette.highlight: sidePanel.themePalette.accent
                    onActivated: function(index) {
                        sidePanel.selectedSceneId = String(sidePanel.sceneLayers[index].id);
                    }
                }
                Text {
                    text: "Opacity"
                    visible: sidePanel.supportsSceneLayers
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                PanelField {
                    objectName: "viewerSidePanelSceneOpacityField"
                    Accessible.name: "Scene opacity"
                    visible: sidePanel.supportsSceneLayers
                    text: String(sidePanel.selectedSceneStyle.opacity === undefined
                        ? 1.0 : sidePanel.selectedSceneStyle.opacity)
                    placeholderText: "0.0 - 1.0"
                    onEditingFinished: sidePanel.setSceneStyle("opacity", text)
                }
                Text {
                    text: "Color"
                    visible: sidePanel.supportsSceneLayers
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                RowLayout {
                    visible: sidePanel.supportsSceneLayers
                    Layout.fillWidth: true
                    PanelField {
                        objectName: "viewerSidePanelSceneColorField"
                        Accessible.name: "Scene color"
                        Layout.fillWidth: true
                        text: String(sidePanel.selectedSceneStyle.color || "")
                        placeholderText: "Auto / #RRGGBB"
                        onEditingFinished: sidePanel.setSceneStyle("color", text)
                    }
                    ShellButton {
                        objectName: "viewerSidePanelSceneColorAutoButton"
                        text: "Auto"
                        onClicked: sidePanel.setSceneStyle("color", "")
                    }
                }

                Text {
                    text: "Component"
                    visible: sidePanel.supportsScalars
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ComboBox {
                    objectName: "viewerSidePanelComponentCombo"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    model: ["Magnitude", "X", "Y", "Z"]
                    visible: sidePanel.supportsScalars
                    font.pixelSize: 11
                    currentIndex: Math.max(
                        0,
                        sidePanel.componentValues.indexOf(
                            String(sidePanel.sessionOptions.result_component || "magnitude").toLowerCase()
                        )
                    )
                    palette.buttonText: sidePanel.themePalette.tab_fg
                    palette.text: sidePanel.themePalette.tab_fg
                    palette.highlight: sidePanel.themePalette.accent
                    palette.base: sidePanel.themePalette.input_bg
                    palette.window: sidePanel.themePalette.panel_bg
                    onActivated: function(index) {
                        sidePanel.setViewerOption("result_component", sidePanel.componentValues[index]);
                    }
                }

                Text {
                    text: "Range"
                    visible: sidePanel.supportsScalars
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                ComboBox {
                    objectName: "viewerSidePanelRangeModeCombo"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    model: ["Auto", "Custom"]
                    visible: sidePanel.supportsScalars
                    font.pixelSize: 11
                    currentIndex: Math.max(
                        0,
                        sidePanel.rangeModeValues.indexOf(
                            String(sidePanel.sessionOptions.scalar_range_mode || "auto").toLowerCase()
                        )
                    )
                    palette.buttonText: sidePanel.themePalette.tab_fg
                    palette.text: sidePanel.themePalette.tab_fg
                    palette.highlight: sidePanel.themePalette.accent
                    palette.base: sidePanel.themePalette.input_bg
                    palette.window: sidePanel.themePalette.panel_bg
                    onActivated: function(index) {
                        sidePanel.setViewerOption("scalar_range_mode", sidePanel.rangeModeValues[index]);
                    }
                }

                Text {
                    text: "Min"
                    visible: sidePanel.supportsScalars
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                PanelField {
                    objectName: "viewerSidePanelRangeMinField"
                    text: String(sidePanel.sessionOptions.scalar_range_min || "")
                    visible: sidePanel.supportsScalars
                    enabled: String(sidePanel.sessionOptions.scalar_range_mode || "auto") === "custom"
                    placeholderText: "auto"
                    onEditingFinished: sidePanel.setViewerOption("scalar_range_min", text)
                }

                Text {
                    text: "Max"
                    visible: sidePanel.supportsScalars
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                PanelField {
                    objectName: "viewerSidePanelRangeMaxField"
                    text: String(sidePanel.sessionOptions.scalar_range_max || "")
                    visible: sidePanel.supportsScalars
                    enabled: String(sidePanel.sessionOptions.scalar_range_mode || "auto") === "custom"
                    placeholderText: "auto"
                    onEditingFinished: sidePanel.setViewerOption("scalar_range_max", text)
                }

                Text {
                    text: "Deform"
                    visible: sidePanel.supportsDeformation
                    color: sidePanel.themePalette.muted_fg
                    font.pixelSize: 11
                }
                PanelField {
                    objectName: "viewerSidePanelDeformScaleField"
                    text: String(sidePanel.sessionOptions.deform_scale || "off")
                    visible: sidePanel.supportsDeformation
                    placeholderText: "off | auto | factor"
                    onEditingFinished: sidePanel.setViewerOption("deform_scale", text)
                }
            }

            RowLayout {
                spacing: 6
                Layout.fillWidth: true

                PanelCheck {
                    objectName: "viewerSidePanelPointsModeCheck"
                    readonly property bool actionAvailable: sidePanel.renderModeSupported("points")
                    text: "Points mode"
                    visible: sidePanel.supportsSceneLayers
                    checked: String(sidePanel.sessionOptions.representation || "surface") === "points"
                    checkable: actionAvailable
                    hoverEnabled: true
                    opacity: actionAvailable ? 1.0 : 0.55
                    onToggled: {
                        if (actionAvailable)
                            sidePanel.setViewerOption("representation", checked ? "points" : "surface");
                    }
                    Common.ManagedToolTip {
                        policyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                        category: "general"
                        active: parent.hovered && !parent.actionAvailable
                        text: TooltipCopy.text(tooltipCopyBridge, "viewer.render.points_unavailable")
                        delay: 300
                    }
                }

                PanelCheck {
                    objectName: "viewerSidePanelScalarBarCheck"
                    text: "Scalar bar"
                    visible: sidePanel.supportsScalars
                    checked: sidePanel.sessionOptions.show_scalar_bar === undefined
                        ? true
                        : Boolean(sidePanel.sessionOptions.show_scalar_bar)
                    onToggled: sidePanel.setViewerOption("show_scalar_bar", checked)
                }
            }

            RowLayout {
                spacing: 6
                Layout.fillWidth: true

                PanelCheck {
                    objectName: "viewerSidePanelProbeCheck"
                    text: "Hover probe"
                    visible: sidePanel.supportsProbe
                    checked: Boolean(sidePanel.sessionOptions.hover_probe)
                    onToggled: sidePanel.setViewerOption("hover_probe", checked)
                }

                PanelCheck {
                    objectName: "viewerSidePanelMarkersCheck"
                    text: "Min/max markers"
                    visible: sidePanel.supportsMinmax
                    checked: Boolean(sidePanel.sessionOptions.show_minmax_markers)
                    onToggled: sidePanel.setViewerOption("show_minmax_markers", checked)
                }
            }

            ShellButton {
                objectName: "viewerSidePanelScreenshotButton"
                text: "Export screenshot…"
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.side_panel.export_screenshot")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.side_panel.export_screenshot")
                Layout.fillWidth: true
                onClicked: {
                    if (sidePanel.hostServiceRef && sidePanel.hostServiceRef.export_viewer_screenshot)
                        sidePanel.hostServiceRef.export_viewer_screenshot(sidePanel.nodeId);
                }
            }

            ShellButton {
                objectName: "viewerSidePanelClipboardButton"
                text: "Copy viewer image"
                Layout.fillWidth: true
                onClicked: {
                    if (sidePanel.hostServiceRef
                            && sidePanel.hostServiceRef.copy_viewer_screenshot_to_clipboard)
                        sidePanel.hostServiceRef.copy_viewer_screenshot_to_clipboard(sidePanel.nodeId);
                }
            }

            Text {
                text: "Measurements and Properties"
                visible: sidePanel.engineeringViewer && sidePanel.supportsMeasurements
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            RowLayout {
                visible: sidePanel.engineeringViewer && sidePanel.supportsMeasurements
                Layout.fillWidth: true
                spacing: 4

                ShellButton {
                    objectName: "viewerSidePanelBoundsQueryButton"
                    text: "Bounds"
                    enabled: sidePanel.queryAvailable
                    Layout.fillWidth: true
                    onClicked: sidePanel.runEngineeringQuery("bounds")
                }
                ShellButton {
                    objectName: "viewerSidePanelEntityInfoQueryButton"
                    text: "Entity"
                    enabled: sidePanel.queryAvailable
                    Layout.fillWidth: true
                    onClicked: sidePanel.runEngineeringQuery("entity_info")
                }
                ShellButton {
                    objectName: "viewerSidePanelMassQueryButton"
                    text: "Mass props"
                    enabled: sidePanel.queryAvailable
                    Layout.fillWidth: true
                    onClicked: sidePanel.runEngineeringQuery("mass_properties")
                }
            }

            Text {
                text: "Neutral Export"
                visible: sidePanel.engineeringViewer && sidePanel.supportsNeutralExport
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            GridLayout {
                visible: sidePanel.engineeringViewer && sidePanel.supportsNeutralExport
                columns: 3
                columnSpacing: 4
                rowSpacing: 4
                Layout.fillWidth: true

                Repeater {
                    model: ["STEP", "VTU", "VTM", "glTF", "GLB"]
                    ShellButton {
                        objectName: "viewerSidePanelNeutralExportButton"
                        text: String(modelData)
                        enabled: sidePanel.queryAvailable
                        Layout.fillWidth: true
                        onClicked: sidePanel.runEngineeringExport(String(modelData).toLowerCase())
                    }
                }
            }

            Text {
                visible: sidePanel.engineeringViewer
                    && (sidePanel.supportsMeasurements || sidePanel.supportsNeutralExport)
                    && (!sidePanel.queryAvailable || sidePanel.engineeringToolMessage.length > 0)
                text: sidePanel.engineeringToolMessage.length > 0
                    ? sidePanel.engineeringToolMessage
                    : "Worker engineering queries are unavailable for this session."
                color: sidePanel.themePalette.muted_fg
                font.pixelSize: 10
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: sidePanel.themePalette.input_border
            }

            Text {
                text: sidePanel.engineeringViewer ? "Selected Scene" : "Result Info"
                visible: sidePanel.supportsScalars || sidePanel.supportsSceneLayers
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            GridLayout {
                columns: 2
                columnSpacing: 8
                rowSpacing: 3
                Layout.fillWidth: true
                visible: sidePanel.supportsScalars || sidePanel.supportsSceneLayers

                Text { text: "Result"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    objectName: "viewerSidePanelResultValue"
                    text: String(sidePanel.infoSummary.result_name || sidePanel.infoSummary.name || "—")
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Text { text: "Location"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    text: String(sidePanel.infoSummary.location || "—")
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                }

                Text { text: "Unit"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    text: sidePanel.statsUnit.length > 0 ? sidePanel.statsUnit : "—"
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                }

                Text { text: "Sets"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    text: String(sidePanel.infoSummary.field_count || "—")
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                }

                Text { text: "Set"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    text: String(sidePanel.infoSummary.set_label || "—")
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: sidePanel.themePalette.input_border
            }

            Text {
                text: "Live Readouts"
                visible: sidePanel.supportsScalars
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            GridLayout {
                columns: 2
                columnSpacing: 8
                rowSpacing: 3
                Layout.fillWidth: true
                visible: sidePanel.supportsScalars

                Text { text: "Showing"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    objectName: "viewerSidePanelShowingValue"
                    text: {
                        var array = String(sidePanel.renderStats.array || "");
                        if (!array.length)
                            return "—";
                        var component = String(sidePanel.renderStats.component || "");
                        return component.length ? array + " (" + component + ")" : array;
                    }
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Text { text: "Min"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    objectName: "viewerSidePanelMinValue"
                    text: {
                        var value = sidePanel._formatStat(sidePanel.renderStats.min);
                        var entity = Number(sidePanel.renderStats.min_entity_id);
                        if (value !== "—" && isFinite(entity) && entity > 0)
                            value += " @ " + String(sidePanel.renderStats.entity_kind || "node") + " " + entity;
                        return value;
                    }
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Text { text: "Max"; color: sidePanel.themePalette.muted_fg; font.pixelSize: 11 }
                Text {
                    objectName: "viewerSidePanelMaxValue"
                    text: {
                        var value = sidePanel._formatStat(sidePanel.renderStats.max);
                        var entity = Number(sidePanel.renderStats.max_entity_id);
                        if (value !== "—" && isFinite(entity) && entity > 0)
                            value += " @ " + String(sidePanel.renderStats.entity_kind || "node") + " " + entity;
                        return value;
                    }
                    color: sidePanel.themePalette.tab_fg
                    font.pixelSize: 11
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: sidePanel.themePalette.input_border
            }

            Text {
                text: "Saved Selections"
                visible: Boolean(sidePanel.capabilities.saved_selections)
                color: sidePanel.themePalette.panel_title_fg
                font.pixelSize: 12
                font.bold: true
            }

            ShellButton {
                text: "Save current selection"
                visible: Boolean(sidePanel.capabilities.saved_selections)
                Layout.fillWidth: true
                onClicked: {
                    if (sidePanel.bridgeRef
                            && sidePanel.bridgeRef.save_current_viewer_selection
                            && sidePanel.bridgeRef.save_current_viewer_selection(sidePanel.nodeId, ""))
                        sidePanel.refreshSelections();
                }
            }

            Repeater {
                model: Boolean(sidePanel.capabilities.saved_selections)
                    && sidePanel.savedSelections.selections
                    ? sidePanel.savedSelections.selections : []

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    PanelField {
                        text: String(modelData.name || ("Selection " + (index + 1)))
                        placeholderText: "Selection name"
                        Layout.fillWidth: true
                        onEditingFinished: {
                            if (sidePanel.bridgeRef
                                    && sidePanel.bridgeRef.rename_viewer_selection
                                    && sidePanel.bridgeRef.rename_viewer_selection(sidePanel.nodeId, index, text))
                                sidePanel.refreshSelections();
                        }
                    }
                    ShellButton {
                        text: "Use"
                        Layout.preferredWidth: 38
                        onClicked: {
                            if (sidePanel.bridgeRef
                                    && sidePanel.bridgeRef.activate_viewer_selection)
                                sidePanel.bridgeRef.activate_viewer_selection(sidePanel.nodeId, index);
                        }
                    }
                    ShellButton {
                        text: "Out"
                        selectedStyle: sidePanel.savedSelections.published_name === modelData.name
                        Layout.preferredWidth: 36
                        onClicked: {
                            if (sidePanel.bridgeRef
                                    && sidePanel.bridgeRef.publish_viewer_selection
                                    && sidePanel.bridgeRef.publish_viewer_selection(sidePanel.nodeId, index))
                                sidePanel.refreshSelections();
                        }
                    }
                    ShellButton {
                        text: "âœ•"
                        Layout.preferredWidth: 26
                        onClicked: {
                            if (sidePanel.bridgeRef
                                    && sidePanel.bridgeRef.remove_viewer_selection
                                    && sidePanel.bridgeRef.remove_viewer_selection(sidePanel.nodeId, index))
                                sidePanel.refreshSelections();
                        }
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }
}
