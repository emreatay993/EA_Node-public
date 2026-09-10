import QtQuick 2.15
import QtQuick.Layouts 1.15
import "../common/contrast_utils.js" as ContrastUtils

Rectangle {
    id: root
    objectName: "webPageToolbar"
    property var uiIconsRef: typeof uiIcons !== "undefined" ? uiIcons : null
    property var themePalette: ({})
    property string addressText: ""
    property bool loading: false
    property bool canGoBack: false
    property bool canGoForward: false
    property bool compact: false
    property bool detachedVisible: true
    property int zoomPercent: 100
    signal navigateRequested(string location)
    signal backRequested()
    signal forwardRequested()
    signal reloadStopRequested()
    signal homeRequested()
    signal zoomInRequested()
    signal zoomOutRequested()
    signal zoomResetRequested()
    signal fullscreenRequested()
    signal detachedRequested()

    implicitHeight: compact ? 34 : 40
    radius: 6
    color: root.themePalette.toolbar_bg || "#202635"
    border.width: 1
    border.color: root.themePalette.border || "#3a4355"

    onAddressTextChanged: {
        if (!addressField.activeFocus && addressField.text !== root.addressText)
            addressField.text = root.addressText;
    }

    Component.onCompleted: addressField.text = root.addressText

    function _buttonFill(enabled, pressed, hovered) {
        if (!enabled)
            return root.themePalette.input_bg || "#151821";
        if (pressed)
            return root.themePalette.pressed || "#22304a";
        if (hovered)
            return root.themePalette.hover || "#33405c";
        return root.themePalette.panel_bg || "#1f2431";
    }

    function _buttonFg(enabled) {
        return enabled
            ? (root.themePalette.panel_title_fg || "#eef3ff")
            : (root.themePalette.muted_fg || "#95a0b8");
    }

    function _iconSource(name, size, color) {
        var normalized = String(name || "");
        if (!normalized.length || !root.uiIconsRef || !root.uiIconsRef.has(normalized))
            return "";
        return root.uiIconsRef.sourceSized(normalized, size, String(color || root._buttonFg(true)));
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        spacing: 5

        Rectangle {
            id: backButton
            objectName: "webPageBackButton"
            Layout.preferredWidth: root.compact ? 28 : 34
            Layout.fillHeight: true
            radius: 4
            enabled: root.canGoBack
            readonly property string iconSource: root._iconSource("browser-back", 17, root._buttonFg(enabled))
            color: root._buttonFill(enabled, backMouse.pressed, backMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: backButton.iconSource.length > 0
                source: backButton.iconSource
                width: 17
                height: 17
                sourceSize.width: 17
                sourceSize.height: 17
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: backButton.iconSource.length === 0
                text: "<"
                color: root._buttonFg(backButton.enabled)
                font.pixelSize: 13
                font.bold: true
            }

            MouseArea {
                id: backMouse
                anchors.fill: parent
                enabled: backButton.enabled
                hoverEnabled: true
                onClicked: root.backRequested()
            }
        }

        Rectangle {
            id: forwardButton
            objectName: "webPageForwardButton"
            Layout.preferredWidth: root.compact ? 28 : 34
            Layout.fillHeight: true
            radius: 4
            enabled: root.canGoForward
            readonly property string iconSource: root._iconSource("browser-forward", 17, root._buttonFg(enabled))
            color: root._buttonFill(enabled, forwardMouse.pressed, forwardMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: forwardButton.iconSource.length > 0
                source: forwardButton.iconSource
                width: 17
                height: 17
                sourceSize.width: 17
                sourceSize.height: 17
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: forwardButton.iconSource.length === 0
                text: ">"
                color: root._buttonFg(forwardButton.enabled)
                font.pixelSize: 13
                font.bold: true
            }

            MouseArea {
                id: forwardMouse
                anchors.fill: parent
                enabled: forwardButton.enabled
                hoverEnabled: true
                onClicked: root.forwardRequested()
            }
        }

        Rectangle {
            id: reloadButton
            objectName: "webPageReloadStopButton"
            Layout.preferredWidth: root.compact ? 34 : 38
            Layout.fillHeight: true
            radius: 4
            readonly property string iconName: root.loading ? "browser-stop" : "browser-reload"
            readonly property string iconSource: root._iconSource(iconName, 16, root._buttonFg(true))
            color: root._buttonFill(enabled, reloadMouse.pressed, reloadMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: reloadButton.iconSource.length > 0
                source: reloadButton.iconSource
                width: 16
                height: 16
                sourceSize.width: 16
                sourceSize.height: 16
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: reloadButton.iconSource.length === 0
                text: root.loading ? "Stop" : "Reload"
                color: root._buttonFg(true)
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            MouseArea {
                id: reloadMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.reloadStopRequested()
            }
        }

        Rectangle {
            id: homeButton
            objectName: "webPageHomeButton"
            Layout.preferredWidth: root.compact ? 34 : 38
            Layout.fillHeight: true
            radius: 4
            readonly property string iconSource: root._iconSource("browser-home", 16, root._buttonFg(true))
            color: root._buttonFill(enabled, homeMouse.pressed, homeMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: homeButton.iconSource.length > 0
                source: homeButton.iconSource
                width: 16
                height: 16
                sourceSize.width: 16
                sourceSize.height: 16
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: homeButton.iconSource.length === 0
                text: "Home"
                color: root._buttonFg(true)
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            MouseArea {
                id: homeMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.homeRequested()
            }
        }

        Rectangle {
            objectName: "webPageAddressFrame"
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 4
            color: root.themePalette.input_bg || "#151821"
            border.width: 1
            border.color: addressField.activeFocus
                ? (root.themePalette.accent || "#5da9ff")
                : (root.themePalette.input_border || root.themePalette.border || "#3a4355")

            TextInput {
                id: addressField
                objectName: "webPageAddressField"
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                verticalAlignment: TextInput.AlignVCenter
                selectByMouse: true
                clip: true
                color: ContrastUtils.inputForeground(root.themePalette)
                selectionColor: ContrastUtils.inputSelectionBackground(root.themePalette)
                selectedTextColor: ContrastUtils.inputSelectedForeground(root.themePalette)
                font.pixelSize: 12
                onAccepted: root.navigateRequested(text)
            }
        }

        Rectangle {
            id: zoomOutButton
            objectName: "webPageZoomOutButton"
            Layout.preferredWidth: 28
            Layout.fillHeight: true
            radius: 4
            readonly property string iconSource: root._iconSource("zoom-out", 15, root._buttonFg(true))
            color: root._buttonFill(enabled, zoomOutMouse.pressed, zoomOutMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: zoomOutButton.iconSource.length > 0
                source: zoomOutButton.iconSource
                width: 15
                height: 15
                sourceSize.width: 15
                sourceSize.height: 15
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: zoomOutButton.iconSource.length === 0
                text: "-"
                color: root._buttonFg(true)
                font.pixelSize: 13
                font.bold: true
            }

            MouseArea {
                id: zoomOutMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.zoomOutRequested()
            }
        }

        Rectangle {
            id: zoomResetButton
            objectName: "webPageZoomResetButton"
            Layout.preferredWidth: 52
            Layout.fillHeight: true
            radius: 4
            color: root._buttonFill(enabled, zoomResetMouse.pressed, zoomResetMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Text {
                anchors.centerIn: parent
                text: root.zoomPercent + "%"
                color: root._buttonFg(true)
                font.pixelSize: 11
            }

            MouseArea {
                id: zoomResetMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.zoomResetRequested()
            }
        }

        Rectangle {
            id: zoomInButton
            objectName: "webPageZoomInButton"
            Layout.preferredWidth: 28
            Layout.fillHeight: true
            radius: 4
            readonly property string iconSource: root._iconSource("zoom-in", 15, root._buttonFg(true))
            color: root._buttonFill(enabled, zoomInMouse.pressed, zoomInMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: zoomInButton.iconSource.length > 0
                source: zoomInButton.iconSource
                width: 15
                height: 15
                sourceSize.width: 15
                sourceSize.height: 15
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: zoomInButton.iconSource.length === 0
                text: "+"
                color: root._buttonFg(true)
                font.pixelSize: 13
                font.bold: true
            }

            MouseArea {
                id: zoomInMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.zoomInRequested()
            }
        }

        Rectangle {
            id: fullscreenButton
            objectName: "webPageFullscreenButton"
            Layout.preferredWidth: root.compact ? 34 : 38
            Layout.fillHeight: true
            radius: 4
            readonly property string iconSource: root._iconSource("fullscreen", 16, root._buttonFg(true))
            color: root._buttonFill(enabled, fullscreenMouse.pressed, fullscreenMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: fullscreenButton.iconSource.length > 0
                source: fullscreenButton.iconSource
                width: 16
                height: 16
                sourceSize.width: 16
                sourceSize.height: 16
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: fullscreenButton.iconSource.length === 0
                text: root.compact ? "Full" : "Fullscreen"
                color: root._buttonFg(true)
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            MouseArea {
                id: fullscreenMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.fullscreenRequested()
            }
        }

        Rectangle {
            id: detachedButton
            objectName: "webPageDetachedButton"
            Layout.preferredWidth: root.detachedVisible ? (root.compact ? 34 : 38) : 0
            Layout.fillHeight: true
            visible: root.detachedVisible
            radius: 4
            readonly property string iconSource: root._iconSource("browser-detach", 16, root._buttonFg(true))
            color: root._buttonFill(enabled, detachedMouse.pressed, detachedMouse.containsMouse)
            border.width: 1
            border.color: root.themePalette.border || "#3a4355"

            Image {
                anchors.centerIn: parent
                visible: detachedButton.iconSource.length > 0
                source: detachedButton.iconSource
                width: 16
                height: 16
                sourceSize.width: 16
                sourceSize.height: 16
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
            }

            Text {
                anchors.centerIn: parent
                visible: detachedButton.iconSource.length === 0
                text: "Detach"
                color: root._buttonFg(true)
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            MouseArea {
                id: detachedMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.detachedRequested()
            }
        }
    }
}
