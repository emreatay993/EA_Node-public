import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15
import QtQml 2.15
import "TooltipPolicy.js" as TooltipPolicy

ToolTip {
    id: control
    property var policyBridge: null
    property var themeBridgeRef: typeof themeBridge !== "undefined" ? themeBridge : null
    property string category: TooltipPolicy.GENERAL
    property bool active: false
    property int textFormat: Text.PlainText
    property int maximumTextWidth: 360
    property bool screenStablePositioning: false
    property real anchorScale: 1.0
    property real screenGap: 3.0
    property string screenStablePlacement: "above"
    // Poll interval and travel threshold for the anchor watchdog below.
    property int anchorWatchInterval: 200
    property real anchorMoveThreshold: 1.5
    readonly property var themePalette: control.themeBridgeRef ? control.themeBridgeRef.palette : ({})
    readonly property color resolvedBackgroundColor: control.themePalette.panel_alt_bg
        || control.themePalette.panel_bg
        || "#24262c"
    readonly property color resolvedBorderColor: control.themePalette.input_border
        || control.themePalette.border
        || "#4a4f5a"
    readonly property color resolvedTextColor: control.themePalette.app_fg
        || control.themePalette.panel_title_fg
        || "#e8e8e8"
    readonly property bool policyAllowsTooltip: TooltipPolicy.categoryEnabled(policyBridge, category)

    // Lifecycle guards. Because popupType is Popup.Window (see below) an open
    // tooltip is a real top-level OS window, and Qt will not take it down when
    // the app loses focus, gets minimised, or when a hover-exit event is never
    // delivered. Without these guards a stuck `active` leaves the tooltip
    // floating over the desktop and over other applications.
    //
    // Window.active is deliberately NOT used: under QQuickWidget the QML scene
    // lives in a QQuickWidgetOffscreenWindow that the window manager never
    // activates, so Window.active is permanently false and would suppress every
    // tooltip in the app. Qt.application.active is the signal that tracks a
    // foreign application taking the foreground.
    readonly property var _anchorWindow: control.parent ? control.parent.Window.window : null
    readonly property bool _hostWindowShown: control._anchorWindow
        ? control._anchorWindow.visibility !== Window.Hidden
        : true
    readonly property bool _anchorPresentable: !!control.parent && control.parent.visible
    // Set by the anchor watchdog when the anchor item travels while the tooltip
    // is open (canvas pan, node drag, view switch). Qt delivers no pointer event
    // when an item moves out from under a stationary cursor, so hover state
    // sticks and only this catches it. Cleared when the caller drops `active`.
    property bool _anchorMoved: false
    readonly property bool _lifecycleAllowsTooltip: Qt.application.active
        && control._hostWindowShown
        && control._anchorPresentable
        && !control._anchorMoved
    readonly property bool managedVisible: TooltipPolicy.tooltipVisible(
        policyBridge,
        category,
        active && text.length > 0 && control._lifecycleAllowsTooltip
    )
    readonly property real _resolvedAnchorScale: Math.max(0.1, Number(anchorScale || 1.0))
    readonly property real _screenStableX: {
        if (!parent)
            return control.x;
        if (control.screenStablePlacement === "left")
            return -(control.width + control.screenGap) / control._resolvedAnchorScale;
        if (control.screenStablePlacement === "right")
            return parent.width + control.screenGap / control._resolvedAnchorScale;
        return parent.width * 0.5 - control.width / (2 * control._resolvedAnchorScale);
    }
    readonly property real _screenStableY: {
        if (!parent)
            return control.y;
        if (control.screenStablePlacement === "below")
            return parent.height + control.screenGap / control._resolvedAnchorScale;
        if (control.screenStablePlacement === "left" || control.screenStablePlacement === "right")
            return parent.height * 0.5 - control.height / (2 * control._resolvedAnchorScale);
        return -(control.height + control.screenGap) / control._resolvedAnchorScale;
    }

    visible: managedVisible
    // Bounded lifetime so any hover-exit event we never receive cannot pin the
    // popup window open indefinitely. Closing this way does not destroy the
    // `visible: managedVisible` binding, so the next hover reopens normally.
    timeout: 12000
    leftPadding: 12
    rightPadding: 12
    topPadding: 8
    bottomPadding: 8
    implicitWidth: Math.min(implicitContentWidth, maximumTextWidth)
        + leftPadding + rightPadding
    // Render as a real popup window so tooltips composite above native child
    // widgets (embedded plot/viewer/web surfaces). Platforms without popup
    // window support silently fall back to the in-scene item.
    popupType: Popup.Window
    // Enlarge the background below the control so the soft-shadow tail stays
    // inside the popup window instead of being clipped at the control bounds.
    bottomInset: -8

    contentItem: Text {
        text: control.text
        color: control.resolvedTextColor
        font: control.font
        textFormat: control.textFormat
        wrapMode: Text.WordWrap
    }

    background: Item {
        Rectangle {
            x: 0
            y: 8
            width: parent.width
            height: parent.height - 8
            radius: 10
            color: Qt.alpha("#000000", 0.10)
        }

        Rectangle {
            x: 0
            y: 4
            width: parent.width
            height: parent.height - 8
            radius: 9
            color: Qt.alpha("#000000", 0.06)
        }

        Rectangle {
            id: tooltipPanel
            objectName: "managedToolTipPanel"
            anchors.fill: parent
            anchors.bottomMargin: 8
            radius: 8
            color: control.resolvedBackgroundColor
            border.width: 1
            border.color: Qt.alpha(control.resolvedBorderColor, 0.92)
        }
    }

    onActiveChanged: {
        if (!control.active)
            control._anchorMoved = false;
    }

    onVisibleChanged: {
        if (control.visible && control.parent)
            anchorWatchdog.baseline = control.parent.mapToItem(null, 0, 0);
    }

    // Watchdog for the one hover case Qt cannot report: the anchor moving out
    // from under a stationary cursor. Runs only while a tooltip is on screen.
    Timer {
        id: anchorWatchdog
        property point baseline: Qt.point(0, 0)
        interval: control.anchorWatchInterval
        repeat: true
        running: control.visible && !!control.parent
        onTriggered: {
            var here = control.parent.mapToItem(null, 0, 0);
            if (Math.abs(here.x - baseline.x) > control.anchorMoveThreshold
                || Math.abs(here.y - baseline.y) > control.anchorMoveThreshold) {
                control._anchorMoved = true;
            }
        }
    }

    Binding {
        target: control
        property: "x"
        value: control._screenStableX
        when: control.screenStablePositioning
        restoreMode: Binding.RestoreBindingOrValue
    }

    Binding {
        target: control
        property: "y"
        value: control._screenStableY
        when: control.screenStablePositioning
        restoreMode: Binding.RestoreBindingOrValue
    }
}
