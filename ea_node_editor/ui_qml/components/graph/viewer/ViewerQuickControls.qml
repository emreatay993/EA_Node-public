import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../../shell"
import "../../common" as Common
import "../../common/TooltipCopy.js" as TooltipCopy

Rectangle {
    id: quickControls
    objectName: "viewerQuickControls"
    property var themePalette: typeof themeBridge !== "undefined" ? themeBridge.palette : ({})
    property string nodeId: ""
    property var fullscreenBridgeRef: null
    property var sessionBridgeRef: typeof viewerSessionBridge !== "undefined" ? viewerSessionBridge : null
    property var controlBridgeRef: typeof viewerControlBridge !== "undefined" ? viewerControlBridge : null
    property var hostServiceRef: typeof viewerHostService !== "undefined" ? viewerHostService : null
    property var sessionState: {
        var revision = sessionBridgeRef ? sessionBridgeRef.sessions_model : [];
        return sessionBridgeRef && sessionBridgeRef.session_state && nodeId.length
            ? sessionBridgeRef.session_state(nodeId) : ({});
    }
    property bool detachedPresentation: false
    property var cameraBookmarks: []
    property int currentBookmarkIndex: -1

    color: themePalette.panel_bg || "#20242b"
    border.color: themePalette.input_border || "#3d4652"
    border.width: 1
    implicitHeight: 54
    clip: true

    readonly property var sessionOptions: sessionState.options || ({})
    readonly property var sessionSummary: sessionState.summary || ({})
    readonly property var capabilities: sessionSummary.capabilities || ({})
    readonly property bool sessionOpen: String(sessionState.phase || "") === "open"
    readonly property bool engineeringViewer: String(sessionSummary.viewer_kind || "") === "engineering_scene"
    readonly property bool supportsPlayback: capabilities.playback === undefined
        ? !engineeringViewer : Boolean(capabilities.playback)
    readonly property bool playing: String(sessionState.playback_state || "paused") === "playing"
    readonly property string sessionIdentity: String(sessionState.session_id || "")
    readonly property bool supportsWireframe: renderModeSupported("wireframe")
    readonly property bool supportsShaded: renderModeSupported("surface")
    readonly property bool supportsMeshEdges: capability("mesh_edges", !engineeringViewer)
    readonly property bool supportsBodyEdges: capability("topological_edges", false)
        && renderModeSupported("surface_with_edges")
    readonly property bool supportsAttributeColors: capability("attribute_colors", false)
    readonly property bool supportsVisibleEdges: capability(
        "wireframe_visible_edges",
        renderModeSupported("wireframe_visible_edges")
    ) && renderModeSupported("wireframe_visible_edges")
    readonly property var selectionSnapshot: {
        var revision = hostServiceRef ? hostServiceRef.viewer_overlay_revision : 0;
        void(revision);
        if (!hostServiceRef || !hostServiceRef.viewer_selection_snapshot || !nodeId.length)
            return ({});
        return hostServiceRef.viewer_selection_snapshot(nodeId) || ({});
    }
    readonly property bool selectionAvailable: Boolean(selectionSnapshot.entities
        && selectionSnapshot.entities.length > 0)
    readonly property bool isolateActive: Boolean(selectionSnapshot.isolate_active)
    readonly property bool detachedActive: {
        var detachedCount = hostServiceRef ? hostServiceRef.detached_viewer_count : 0;
        void(detachedCount);
        return hostServiceRef && hostServiceRef.detached_viewer_active
            ? Boolean(hostServiceRef.detached_viewer_active(nodeId)) : detachedPresentation;
    }

    function capability(name, fallbackValue) {
        var value = capabilities[name];
        if (value && typeof value === "object" && value.available !== undefined)
            return Boolean(value.available);
        return value === undefined ? Boolean(fallbackValue) : Boolean(value);
    }

    function capabilityReason(name, fallbackText) {
        var value = capabilities[name];
        if (value && typeof value === "object")
            return String(value.reason || value.unsupported_reason || fallbackText || "Unavailable for this source.");
        return String(fallbackText || "Unavailable for this source.");
    }

    function renderModeSupported(mode) {
        var modes = capabilities.supported_render_modes || sessionSummary.supported_render_modes;
        if (!modes || modes.length === undefined)
            return !engineeringViewer && mode !== "wireframe_visible_edges";
        for (var index = 0; index < modes.length; ++index) {
            if (String(modes[index]) === mode)
                return true;
        }
        return false;
    }

    function setViewerOption(key, value) {
        return controlBridgeRef && controlBridgeRef.set_viewer_option && nodeId.length
            ? Boolean(controlBridgeRef.set_viewer_option(nodeId, String(key || ""), value)) : false;
    }

    function setRepresentation(value) {
        return setViewerOption("representation", value);
    }

    function cameraFit() {
        return hostServiceRef && hostServiceRef.reset_overlay_camera
            ? Boolean(hostServiceRef.reset_overlay_camera(nodeId)) : false;
    }

    function togglePlayback() {
        if (!sessionBridgeRef || !sessionOpen)
            return false;
        return playing ? Boolean(sessionBridgeRef.pause(nodeId)) : Boolean(sessionBridgeRef.play(nodeId));
    }

    function stepForward() {
        return sessionBridgeRef && sessionOpen ? Boolean(sessionBridgeRef.step(nodeId)) : false;
    }

    function stepBack() {
        return sessionBridgeRef && sessionBridgeRef.step_back && sessionOpen
            ? Boolean(sessionBridgeRef.step_back(nodeId)) : false;
    }

    function applyStandardView(viewId) {
        return hostServiceRef && hostServiceRef.apply_standard_view
            ? Boolean(hostServiceRef.apply_standard_view(nodeId, String(viewId || ""))) : false;
    }

    function fitSelection() {
        return hostServiceRef && hostServiceRef.fit_viewer_selection
            ? Boolean(hostServiceRef.fit_viewer_selection(nodeId)) : false;
    }

    function isolateSelection(updateSelection) {
        return hostServiceRef && hostServiceRef.toggle_viewer_selection_isolate
            ? Boolean(hostServiceRef.toggle_viewer_selection_isolate(nodeId, Boolean(updateSelection))) : false;
    }

    function refreshBookmarks() {
        cameraBookmarks = controlBridgeRef && controlBridgeRef.viewer_camera_bookmarks
            ? controlBridgeRef.viewer_camera_bookmarks(nodeId) : [];
        currentBookmarkIndex = controlBridgeRef
                && controlBridgeRef.viewer_camera_bookmark_current_index
            ? Number(controlBridgeRef.viewer_camera_bookmark_current_index(nodeId)) : -1;
    }

    function cycleSavedView(delta) {
        return controlBridgeRef && controlBridgeRef.cycle_viewer_camera_bookmark
            ? Boolean(controlBridgeRef.cycle_viewer_camera_bookmark(nodeId, delta)) : false;
    }

    function toggleDetached() {
        if (!hostServiceRef)
            return false;
        if (detachedActive && hostServiceRef.close_detached_viewer)
            return Boolean(hostServiceRef.close_detached_viewer(nodeId));
        if (hostServiceRef.open_detached_viewer)
            return Boolean(hostServiceRef.open_detached_viewer(nodeId));
        return false;
    }

    function toggleFullscreen() {
        return fullscreenBridgeRef && fullscreenBridgeRef.request_toggle_for_node
            ? Boolean(fullscreenBridgeRef.request_toggle_for_node(nodeId)) : false;
    }

    function scrollBy(amount) {
        toolbarFlick.contentX = Math.max(
            0,
            Math.min(toolbarFlick.contentWidth - toolbarFlick.width, toolbarFlick.contentX + amount)
        );
    }

    Component.onCompleted: refreshBookmarks()
    onNodeIdChanged: refreshBookmarks()

    Connections {
        target: quickControls.controlBridgeRef
        ignoreUnknownSignals: true
        function onViewerControlChanged(changedNodeId) {
            if (String(changedNodeId) === quickControls.nodeId)
                quickControls.refreshBookmarks();
        }
    }

    ViewerToolButton {
        id: leftChevron
        objectName: "viewerQuickControlsLeftChevron"
        anchors.left: parent.left
        anchors.leftMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        buttonWidth: 28
        buttonHeight: 34
        iconSize: 16
        iconName: "navigate-previous"
        accessibleName: "Scroll viewer controls left"
        tooltipText: accessibleName
        visible: toolbarFlick.contentX > 1
        z: 4
        onClicked: quickControls.scrollBy(-220)
    }

    Flickable {
        id: toolbarFlick
        objectName: "viewerQuickControlsFlickable"
        anchors.fill: parent
        anchors.leftMargin: leftChevron.visible ? 34 : 8
        anchors.rightMargin: rightChevron.visible ? 34 : 8
        contentWidth: toolbarRow.implicitWidth
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        RowLayout {
            id: toolbarRow
            height: toolbarFlick.height
            spacing: 8

            Text {
                text: "Render mode"
                color: quickControls.themePalette.muted_fg || "#aeb7c2"
                font.pixelSize: 11
            }
            Rectangle {
                Layout.preferredHeight: 34
                Layout.preferredWidth: renderModeSegments.implicitWidth + 2
                radius: 5
                color: "transparent"
                border.width: 1
                border.color: quickControls.themePalette.input_border || "#3d4652"

                RowLayout {
                    id: renderModeSegments
                    anchors.centerIn: parent
                    spacing: -1

                    ViewerToolButton {
                        objectName: "viewerRenderWireframeButton"
                        actionEnabled: quickControls.supportsWireframe
                        iconName: "viewer-wireframe"
                        checkable: true
                        selectedStyle: String(quickControls.sessionOptions.representation || "surface") === "wireframe"
                        accessibleName: "Wireframe"
                        tooltipText: actionEnabled
                            ? TooltipCopy.text(tooltipCopyBridge, "viewer.render.wireframe")
                            : quickControls.capabilityReason("wireframe", TooltipCopy.text(tooltipCopyBridge, "viewer.render.wireframe_unavailable"))
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.render.wireframe")
                        onClicked: quickControls.setRepresentation("wireframe")
                    }
                    ViewerToolButton {
                        objectName: "viewerRenderVisibleEdgesButton"
                        actionEnabled: quickControls.supportsVisibleEdges
                        iconName: "viewer-visible-edges"
                        checkable: true
                        selectedStyle: String(quickControls.sessionOptions.representation || "") === "wireframe_visible_edges"
                        accessibleName: "Wireframe without hidden lines"
                        tooltipText: actionEnabled
                            ? TooltipCopy.text(tooltipCopyBridge, "viewer.render.visible_edges")
                            : quickControls.capabilityReason("wireframe_visible_edges", TooltipCopy.text(tooltipCopyBridge, "viewer.render.visible_edges_unavailable"))
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.render.visible_edges")
                        onClicked: quickControls.setRepresentation("wireframe_visible_edges")
                    }
                    ViewerToolButton {
                        objectName: "viewerRenderShadedButton"
                        actionEnabled: quickControls.supportsShaded
                        iconName: "viewer-shaded"
                        checkable: true
                        selectedStyle: String(quickControls.sessionOptions.representation || "surface") === "surface"
                        accessibleName: "Shaded"
                        tooltipText: actionEnabled
                            ? TooltipCopy.text(tooltipCopyBridge, "viewer.render.shaded")
                            : quickControls.capabilityReason("surface", TooltipCopy.text(tooltipCopyBridge, "viewer.render.shaded_unavailable"))
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.render.shaded")
                        onClicked: quickControls.setRepresentation("surface")
                    }
                    ViewerToolButton {
                        objectName: "viewerRenderBodyEdgesButton"
                        actionEnabled: quickControls.supportsBodyEdges
                        iconName: "viewer-body-edges"
                        checkable: true
                        selectedStyle: String(quickControls.sessionOptions.representation || "") === "surface_with_edges"
                        accessibleName: "Shaded with exact body edges"
                        tooltipText: actionEnabled
                            ? TooltipCopy.text(tooltipCopyBridge, "viewer.render.body_edges")
                            : quickControls.capabilityReason("topological_edges", TooltipCopy.text(tooltipCopyBridge, "viewer.render.body_edges_unavailable"))
                        tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.render.body_edges")
                        onClicked: quickControls.setRepresentation("surface_with_edges")
                    }
                }
            }
            ViewerToolButton {
                objectName: "viewerRenderMeshEdgesButton"
                actionEnabled: quickControls.supportsMeshEdges
                iconName: "viewer-mesh-edges"
                checkable: true
                selectedStyle: Boolean(quickControls.sessionOptions.show_mesh_edges)
                accessibleName: "Show mesh or facet edges"
                tooltipText: actionEnabled
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.quick.show_mesh_edges")
                    : quickControls.capabilityReason("mesh_edges", TooltipCopy.text(tooltipCopyBridge, "viewer.render.mesh_edges_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.quick.show_mesh_edges")
                onClicked: quickControls.setViewerOption("show_mesh_edges", !Boolean(quickControls.sessionOptions.show_mesh_edges))
            }
            ViewerToolButton {
                objectName: "viewerRenderAttributeColorsButton"
                actionEnabled: quickControls.supportsAttributeColors
                iconName: "viewer-attribute-colors"
                checkable: true
                selectedStyle: Boolean(quickControls.sessionOptions.show_attribute_colors)
                accessibleName: "Show source attribute colors"
                tooltipText: actionEnabled
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.render.attribute_colors")
                    : quickControls.capabilityReason("attribute_colors", TooltipCopy.text(tooltipCopyBridge, "viewer.render.attribute_colors_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.render.attribute_colors")
                onClicked: quickControls.setViewerOption("show_attribute_colors", !Boolean(quickControls.sessionOptions.show_attribute_colors))
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; color: quickControls.themePalette.input_border || "#3d4652" }
            Text { text: "View"; color: quickControls.themePalette.muted_fg || "#aeb7c2"; font.pixelSize: 11 }
            ViewerToolButton {
                objectName: "viewerFitAllButton"
                iconName: "viewer-fit-all"
                accessibleName: "Fit all visible objects"
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.quick.camera_fit")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.quick.camera_fit")
                onClicked: quickControls.cameraFit()
            }
            ViewerToolButton {
                objectName: "viewerFitSelectionButton"
                readonly property bool capabilityAvailable: quickControls.capability("fit_selection", !quickControls.engineeringViewer)
                actionEnabled: capabilityAvailable && quickControls.selectionAvailable
                iconName: "viewer-fit-selection"
                accessibleName: "Fit selection"
                tooltipText: actionEnabled ? TooltipCopy.text(tooltipCopyBridge, "viewer.view.fit_selection")
                    : capabilityAvailable
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.view.fit_selection_unavailable")
                    : quickControls.capabilityReason("fit_selection", TooltipCopy.text(tooltipCopyBridge, "viewer.view.fit_selection_capability_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.view.fit_selection")
                onClicked: quickControls.fitSelection()
            }
            ViewerToolButton {
                objectName: "viewerIsolateSelectionButton"
                readonly property bool capabilityAvailable: quickControls.capability("selection_isolate", !quickControls.engineeringViewer)
                actionEnabled: capabilityAvailable
                    && (quickControls.isolateActive || quickControls.selectionAvailable)
                iconName: "viewer-isolate"
                accessibleName: quickControls.isolateActive ? "Restore isolated selection" : "Isolate selection"
                checkable: true
                selectedStyle: quickControls.isolateActive
                tooltipText: actionEnabled
                    ? TooltipCopy.text(tooltipCopyBridge, quickControls.isolateActive ? "viewer.view.isolate_restore" : "viewer.view.isolate")
                    : capabilityAvailable
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.view.isolate_unavailable")
                    : quickControls.capabilityReason("selection_isolate", TooltipCopy.text(tooltipCopyBridge, "viewer.view.isolate_capability_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.view.isolate")
                onClicked: quickControls.isolateSelection(Boolean(Qt.application.keyboardModifiers & Qt.ShiftModifier))
            }
            ViewerToolButton {
                id: viewerUiControlsButton
                objectName: "viewerUiControlsButton"
                iconName: "viewer-ui-controls"
                accessibleName: "Viewer UI controls"
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.view.ui_controls")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.view.ui_controls")
                onClicked: uiControlsPopup.open()
            }
            ViewerToolButton {
                id: viewerSavedViewsButton
                objectName: "viewerSavedViewsButton"
                actionEnabled: quickControls.capability("camera_bookmarks", !quickControls.engineeringViewer)
                    && quickControls.controlBridgeRef !== null
                iconName: "viewer-saved-views"
                accessibleName: "Saved views"
                tooltipText: actionEnabled
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views")
                    : quickControls.capabilityReason("camera_bookmarks", TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.view.saved_views")
                onClicked: {
                    quickControls.refreshBookmarks();
                    savedViewsPopup.open();
                }
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; color: quickControls.themePalette.input_border || "#3d4652" }
            Text { text: "Camera"; color: quickControls.themePalette.muted_fg || "#aeb7c2"; font.pixelSize: 11 }
            ViewerToolButton {
                objectName: "viewerProjectionButton"
                actionEnabled: quickControls.capability("projection", !quickControls.engineeringViewer)
                iconName: Boolean(quickControls.sessionOptions.parallel_projection)
                    ? "viewer-orthographic" : "viewer-perspective"
                accessibleName: Boolean(quickControls.sessionOptions.parallel_projection)
                    ? "Orthographic projection" : "Perspective projection"
                checkable: true
                selectedStyle: Boolean(quickControls.sessionOptions.parallel_projection)
                tooltipText: actionEnabled
                    ? TooltipCopy.text(
                        tooltipCopyBridge,
                        Boolean(quickControls.sessionOptions.parallel_projection)
                            ? "viewer.camera.orthographic" : "viewer.camera.perspective"
                    )
                    : quickControls.capabilityReason("projection", TooltipCopy.text(tooltipCopyBridge, "viewer.camera.projection_unavailable"))
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.camera.perspective")
                onClicked: quickControls.setViewerOption(
                    "parallel_projection",
                    !Boolean(quickControls.sessionOptions.parallel_projection)
                )
            }

            Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 26; color: quickControls.themePalette.input_border || "#3d4652" }
            Text { text: "Docking"; color: quickControls.themePalette.muted_fg || "#aeb7c2"; font.pixelSize: 11 }
            ViewerToolButton {
                objectName: "viewerDetachDockButton"
                iconName: quickControls.detachedActive ? "viewer-dock" : "viewer-detach"
                accessibleName: quickControls.detachedActive ? "Dock viewer" : "Detach viewer"
                tooltipText: quickControls.detachedActive
                    ? TooltipCopy.text(tooltipCopyBridge, "viewer.docking.dock")
                    : TooltipCopy.text(tooltipCopyBridge, "viewer.docking.detach")
                tooltipCategory: "general"
                onClicked: quickControls.toggleDetached()
            }
            ViewerToolButton {
                objectName: "viewerFullscreenButton"
                iconName: "viewer-fullscreen"
                actionEnabled: quickControls.fullscreenBridgeRef !== null
                accessibleName: "Fullscreen viewer"
                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.docking.fullscreen")
                tooltipCategory: TooltipCopy.category(tooltipCopyBridge, "viewer.docking.fullscreen")
                onClicked: quickControls.toggleFullscreen()
            }

            Rectangle {
                Layout.preferredWidth: quickControls.supportsPlayback ? 1 : 0
                Layout.preferredHeight: 26
                visible: quickControls.supportsPlayback
                color: quickControls.themePalette.input_border || "#3d4652"
            }
            Text {
                text: "Playback"
                visible: quickControls.supportsPlayback
                color: quickControls.themePalette.muted_fg || "#aeb7c2"
                font.pixelSize: 11
            }
            ShellButton {
                objectName: "viewerPreviousStepButton"
                text: "Previous"
                visible: quickControls.supportsPlayback
                enabled: quickControls.sessionOpen
                onClicked: quickControls.sessionBridgeRef.step_back(quickControls.nodeId)
            }
            ShellButton {
                objectName: "viewerPlayPauseButton"
                text: quickControls.playing ? "Pause" : "Play"
                visible: quickControls.supportsPlayback
                enabled: quickControls.sessionOpen
                onClicked: quickControls.playing
                    ? quickControls.sessionBridgeRef.pause(quickControls.nodeId)
                    : quickControls.sessionBridgeRef.play(quickControls.nodeId)
            }
            ShellButton {
                objectName: "viewerNextStepButton"
                text: "Next"
                visible: quickControls.supportsPlayback
                enabled: quickControls.sessionOpen
                onClicked: quickControls.sessionBridgeRef.step(quickControls.nodeId)
            }
        }
    }

    ViewerToolButton {
        id: rightChevron
        objectName: "viewerQuickControlsRightChevron"
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        buttonWidth: 28
        buttonHeight: 34
        iconSize: 16
        iconName: "navigate-next"
        accessibleName: "Scroll viewer controls right"
        tooltipText: accessibleName
        visible: toolbarFlick.contentWidth > toolbarFlick.width
            && toolbarFlick.contentX < toolbarFlick.contentWidth - toolbarFlick.width - 1
        z: 4
        onClicked: quickControls.scrollBy(220)
    }

    Popup {
        id: uiControlsPopup
        objectName: "viewerUiControlsPopup"
        parent: quickControls
        x: Math.max(0, Math.min(quickControls.width - width, viewerUiControlsButton.mapToItem(quickControls, 0, 0).x))
        y: -height - 4
        width: Math.max(1, Math.min(230, quickControls.width - 16))
        padding: 10
        modal: false
        popupType: Popup.Window
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 6
            color: quickControls.themePalette.panel_bg || "#20242b"
            border.width: 1
            border.color: quickControls.themePalette.input_border || "#3d4652"
        }
        contentItem: ColumnLayout {
            spacing: 6
            Label {
                text: "UI controls"
                color: quickControls.themePalette.panel_title_fg || "#f3f5f7"
                font.bold: true
            }
            CheckBox {
                readonly property bool actionAvailable: quickControls.capability("orientation_triad", !quickControls.engineeringViewer)
                text: "Show triad"
                checked: quickControls.sessionOptions.show_orientation_triad === undefined
                    ? true : Boolean(quickControls.sessionOptions.show_orientation_triad)
                enabled: actionAvailable
                hoverEnabled: true
                opacity: actionAvailable ? 1.0 : 0.55
                Accessible.name: "Show orientation triad"
                palette.windowText: quickControls.themePalette.tab_fg || "#f3f5f7"
                onToggled: {
                    if (actionAvailable)
                        quickControls.setViewerOption("show_orientation_triad", checked);
                }
                Common.ManagedToolTip {
                    policyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                    category: "general"
                    active: parent.hovered && !parent.actionAvailable
                    text: quickControls.capabilityReason("orientation_triad", TooltipCopy.text(tooltipCopyBridge, "viewer.view.orientation_triad_unavailable"))
                    delay: 300
                }
            }
            CheckBox {
                readonly property bool actionAvailable: quickControls.capability("view_cube", !quickControls.engineeringViewer)
                text: "Show view cube"
                checked: quickControls.sessionOptions.show_view_cube === undefined
                    ? true : Boolean(quickControls.sessionOptions.show_view_cube)
                enabled: actionAvailable
                hoverEnabled: true
                opacity: actionAvailable ? 1.0 : 0.55
                Accessible.name: "Show view cube"
                palette.windowText: quickControls.themePalette.tab_fg || "#f3f5f7"
                onToggled: {
                    if (actionAvailable)
                        quickControls.setViewerOption("show_view_cube", checked);
                }
                Common.ManagedToolTip {
                    policyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                    category: "general"
                    active: parent.hovered && !parent.actionAvailable
                    text: quickControls.capabilityReason("view_cube", TooltipCopy.text(tooltipCopyBridge, "viewer.view.view_cube_unavailable"))
                    delay: 300
                }
            }
            CheckBox {
                readonly property bool actionAvailable: quickControls.capability("world_axes", !quickControls.engineeringViewer)
                text: "Show axes"
                checked: Boolean(quickControls.sessionOptions.show_world_axes)
                enabled: actionAvailable
                hoverEnabled: true
                opacity: actionAvailable ? 1.0 : 0.55
                Accessible.name: "Show world axes"
                palette.windowText: quickControls.themePalette.tab_fg || "#f3f5f7"
                onToggled: {
                    if (actionAvailable)
                        quickControls.setViewerOption("show_world_axes", checked);
                }
                Common.ManagedToolTip {
                    policyBridge: typeof graphCanvasStateBridge !== "undefined" ? graphCanvasStateBridge : null
                    category: "general"
                    active: parent.hovered && !parent.actionAvailable
                    text: quickControls.capabilityReason("world_axes", TooltipCopy.text(tooltipCopyBridge, "viewer.view.world_axes_unavailable"))
                    delay: 300
                }
            }
        }
    }

    Popup {
        id: savedViewsPopup
        objectName: "viewerSavedViewsPopup"
        parent: quickControls
        x: Math.max(0, Math.min(quickControls.width - width, viewerSavedViewsButton.mapToItem(quickControls, 0, 0).x))
        y: -height - 4
        width: Math.max(1, Math.min(350, quickControls.width - 16))
        height: Math.min(420, savedViewsContent.implicitHeight + 24)
        padding: 10
        modal: false
        popupType: Popup.Window
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 6
            color: quickControls.themePalette.panel_bg || "#20242b"
            border.width: 1
            border.color: quickControls.themePalette.input_border || "#3d4652"
        }
        contentItem: ColumnLayout {
            id: savedViewsContent
            spacing: 6
            ShellButton {
                objectName: "viewerSaveCurrentViewButton"
                Layout.fillWidth: true
                text: "Save current view…"
                iconName: "video-bookmark-add"
                tooltipCategory: "general"
                onClicked: {
                    if (quickControls.controlBridgeRef
                            && quickControls.controlBridgeRef.save_viewer_camera_bookmark
                            && quickControls.controlBridgeRef.save_viewer_camera_bookmark(
                                quickControls.nodeId,
                                ""))
                        quickControls.refreshBookmarks();
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(300, savedViewsColumn.implicitHeight)
                clip: true
                ColumnLayout {
                    id: savedViewsColumn
                    width: savedViewsPopup.availableWidth
                    spacing: 4
                    Repeater {
                        model: quickControls.cameraBookmarks
                        delegate: RowLayout {
                            required property int index
                            required property var modelData
                            property bool editingName: false
                            readonly property string bookmarkName: String(modelData.name || ("View " + (index + 1)))
                            width: savedViewsColumn.width
                            spacing: 4

                            ShellButton {
                                text: parent.bookmarkName
                                visible: !parent.editingName
                                Layout.fillWidth: true
                                selectedStyle: quickControls.currentBookmarkIndex === index
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views_apply")
                                tooltipCategory: TooltipCopy.category(
                                    tooltipCopyBridge,
                                    "viewer.view.saved_views_apply"
                                )
                                onClicked: {
                                    if (quickControls.controlBridgeRef && quickControls.controlBridgeRef.apply_viewer_camera_bookmark)
                                        quickControls.controlBridgeRef.apply_viewer_camera_bookmark(quickControls.nodeId, index);
                                }
                            }
                            TextField {
                                id: bookmarkNameField
                                text: parent.bookmarkName
                                visible: parent.editingName
                                Layout.fillWidth: true
                                selectByMouse: true
                                color: quickControls.themePalette.tab_fg || "#f3f5f7"
                                placeholderTextColor: quickControls.themePalette.muted_fg || "#aeb7c2"
                                selectionColor: quickControls.themePalette.accent || "#3399ff"
                                selectedTextColor: quickControls.themePalette.tab_selected_fg || "#ffffff"
                                background: Rectangle {
                                    radius: 4
                                    color: quickControls.themePalette.input_bg || "#161a20"
                                    border.width: 1
                                    border.color: parent.activeFocus
                                        ? (quickControls.themePalette.accent || "#3399ff")
                                        : (quickControls.themePalette.input_border || "#3d4652")
                                }
                                onEditingFinished: {
                                    if (quickControls.controlBridgeRef
                                            && quickControls.controlBridgeRef.rename_viewer_camera_bookmark)
                                        quickControls.controlBridgeRef.rename_viewer_camera_bookmark(
                                            quickControls.nodeId, index, text
                                        );
                                    parent.editingName = false;
                                }
                            }
                            ViewerToolButton {
                                iconName: "edit"
                                accessibleName: "Rename " + parent.bookmarkName
                                tooltipText: accessibleName
                                onClicked: {
                                    parent.editingName = true;
                                    bookmarkNameField.forceActiveFocus();
                                    bookmarkNameField.selectAll();
                                }
                            }
                            ViewerToolButton {
                                iconName: "chevron-up"
                                actionEnabled: index > 0
                                accessibleName: "Move " + parent.bookmarkName + " earlier"
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views_move_up")
                                onClicked: {
                                    if (quickControls.controlBridgeRef && quickControls.controlBridgeRef.move_viewer_camera_bookmark)
                                        quickControls.controlBridgeRef.move_viewer_camera_bookmark(quickControls.nodeId, index, -1);
                                }
                            }
                            ViewerToolButton {
                                iconName: "chevron-down"
                                actionEnabled: index + 1 < quickControls.cameraBookmarks.length
                                accessibleName: "Move " + parent.bookmarkName + " later"
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views_move_down")
                                onClicked: {
                                    if (quickControls.controlBridgeRef && quickControls.controlBridgeRef.move_viewer_camera_bookmark)
                                        quickControls.controlBridgeRef.move_viewer_camera_bookmark(quickControls.nodeId, index, 1);
                                }
                            }
                            ViewerToolButton {
                                iconName: "delete"
                                accessibleName: "Delete " + parent.bookmarkName
                                tooltipText: TooltipCopy.text(tooltipCopyBridge, "viewer.view.saved_views_delete")
                                onClicked: {
                                    if (quickControls.controlBridgeRef && quickControls.controlBridgeRef.remove_viewer_camera_bookmark)
                                        quickControls.controlBridgeRef.remove_viewer_camera_bookmark(quickControls.nodeId, index);
                                }
                            }
                        }
                    }
                }
            }
            ShellButton {
                objectName: "viewerNextSavedViewButton"
                Layout.fillWidth: true
                text: "Next view (PageDown)"
                enabled: quickControls.cameraBookmarks.length > 0
                tooltipText: "Next saved view (PageDown)"
                tooltipCategory: "general"
                onClicked: quickControls.cycleSavedView(1)
            }
            ShellButton {
                objectName: "viewerPreviousSavedViewButton"
                Layout.fillWidth: true
                text: "Previous view (PageUp)"
                enabled: quickControls.cameraBookmarks.length > 0
                tooltipText: "Previous saved view (PageUp)"
                tooltipCategory: "general"
                onClicked: quickControls.cycleSavedView(-1)
            }
        }
    }
}
