import QtQuick
import QtQuick3D

// Feature (5): a 3D preview node — an orbitable Quick3D View3D embedded right in
// the node body (evokes a Model Viewer/mesh result viewer). Built-in primitive meshes, so
// no asset files. Auto-spins; drag to orbit.
Item {
    id: b
    property var theme

    View3D {
        id: view
        anchors.fill: parent
        camera: cam

        environment: SceneEnvironment {
            clearColor: b.theme ? b.theme.nodeBodyBg : "#191b20"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        PerspectiveCamera {
            id: cam
            position: Qt.vector3d(0, 90, 260)
            eulerRotation.x: -18
            clipFar: 2000
        }

        DirectionalLight {
            eulerRotation.x: -32
            eulerRotation.y: -70
            brightness: 1.1
        }
        DirectionalLight {
            eulerRotation.x: 40
            eulerRotation.y: 120
            brightness: 0.4
            color: b.theme ? b.theme.accent : "#60CDFF"
        }

        Node {
            id: spin
            eulerRotation.y: orbit.active ? spin.eulerRotation.y : autoY
            property real autoY: 0
            NumberAnimation on autoY {
                running: !orbit.active
                from: 0; to: 360
                duration: 9000
                loops: Animation.Infinite
            }

            // a little "result mesh": stacked torus-ish rings made of primitives
            Model {
                source: "#Sphere"
                scale: Qt.vector3d(0.95, 0.95, 0.95)
                materials: PrincipledMaterial {
                    baseColor: b.theme ? b.theme.accent : "#60CDFF"
                    metalness: 0.25
                    roughness: 0.35
                }
            }
            Model {
                source: "#Cylinder"
                position: Qt.vector3d(0, 0, 0)
                scale: Qt.vector3d(1.9, 0.18, 1.9)
                eulerRotation.x: 90
                materials: PrincipledMaterial {
                    baseColor: b.theme ? b.theme.stDone : "#46c98b"
                    metalness: 0.2
                    roughness: 0.4
                    opacity: 0.85
                }
            }
        }
    }

    DragHandler {
        id: orbit
        target: null
        property real lastX: 0
        onActiveChanged: if (active) lastX = centroid.position.x
        onCentroidChanged: {
            if (active) {
                spin.eulerRotation.y += (centroid.position.x - lastX) * 0.6;
                lastX = centroid.position.x;
            }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 4
        text: "drag to orbit"
        color: b.theme ? b.theme.mutedFg : "#9aa3af"
        font.family: b.theme ? b.theme.fontFamily : "Segoe UI"
        font.pixelSize: 9
        opacity: 0.7
    }
}
