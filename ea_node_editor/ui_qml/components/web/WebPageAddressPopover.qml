import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../common" as Common

FocusScope {
    id: root
    objectName: "webPageAddressPopover"

    property var themePalette: ({})
    property string addressText: ""
    property string _originalAddress: ""
    property real shadowStrength: 55
    property real shadowSoftness: 50
    property real shadowOffset: 4

    readonly property var embeddedInteractiveRects: []

    signal accepted(string location)
    signal canceled()

    visible: false
    implicitWidth: 420
    implicitHeight: dialogSurface.implicitHeight
    activeFocusOnTab: true

    onAddressTextChanged: {
        if (!root.visible && addressField.text !== root.addressText)
            addressField.text = root.addressText;
    }

    function openWithAddress(location) {
        root._originalAddress = String(location || root.addressText || "");
        addressField.text = root._originalAddress;
        root.visible = true;
        Qt.callLater(function() {
            addressField.forceActiveFocus();
            addressField.selectAll();
        });
    }

    function acceptEdit() {
        var location = String(addressField.text || "").trim();
        root.visible = false;
        root.accepted(location);
    }

    function cancelEdit() {
        addressField.text = root._originalAddress;
        root.visible = false;
        root.canceled();
    }

    function closeSilently() {
        root.visible = false;
    }

    Keys.onEscapePressed: root.cancelEdit()

    Common.DialogSurface {
        id: dialogSurface
        anchors.fill: parent
        themePalette: root.themePalette
        title: "Address"
        closeButtonVisible: true
        onCloseRequested: root.cancelEdit()

        RowLayout {
            id: addressContent
            Layout.fillWidth: true
            Layout.margins: 10
            spacing: 6

            Common.DialogTextField {
                id: addressField
                objectName: "webPageAddressPopoverField"
                Layout.fillWidth: true
                themePalette: root.themePalette
                placeholderText: "Enter a URL or local HTML path..."
                Accessible.name: "Address"
                onAccepted: root.acceptEdit()
                Keys.onEscapePressed: root.cancelEdit()
            }

            Common.DialogButton {
                id: cancelButton
                objectName: "webPageAddressPopoverCancelButton"
                Layout.preferredWidth: 72
                controlHeight: 32
                themePalette: root.themePalette
                text: "Cancel"
                onClicked: root.cancelEdit()
            }

            Common.DialogButton {
                id: okButton
                objectName: "webPageAddressPopoverOkButton"
                Layout.preferredWidth: 58
                controlHeight: 32
                themePalette: root.themePalette
                text: "OK"
                primary: true
                onClicked: root.acceptEdit()
            }
        }
    }
}
