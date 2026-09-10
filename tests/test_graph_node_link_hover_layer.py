from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtProperty
from PyQt6.QtQml import QQmlComponent, QQmlEngine

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOVER_LAYER_IMPORT = (
    _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph" / "overlay"
).as_posix()


class _NodePayloadProvider(QObject):
    @pyqtProperty("QVariantList", constant=True)
    def payloads(self) -> list[dict[str, object]]:
        return [
            {
                "node_id": "node-video",
                "links": [
                    {
                        "id": "link-docs",
                        "kind": "url",
                        "title": "Docs",
                        "target": "https://example.com/docs",
                    },
                    {
                        "id": "link-notes",
                        "kind": "file",
                        "title": "Notes",
                        "target": "C:/notes.txt",
                    },
                ],
            }
        ]


def _qml_error_text(component: QQmlComponent) -> str:
    return "\n".join(error.toString() for error in component.errors())


def _create_hover_sync_probe(qapp):  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            id: probe
            width: 900
            height: 700

            property int step: 0
            property var scene: [
                {{
                    "node_id": "node-video",
                    "x": 100,
                    "y": 80,
                    "width": 180,
                    "links": [
                        {{
                            "id": "link-docs",
                            "kind": "url",
                            "title": "Docs",
                            "target": "https://example.com/docs"
                        }}
                    ]
                }}
            ]
            property bool layerActive: layer.activeNodeData !== null && layer.activeLink !== null
            property bool activeNodeDataMissing: layer.activeNodeData === null
            property bool activeLinkMissing: layer.activeLink === null
            property string activeNodeIdValue: layer.activeNodeId
            property string activeLinkIdValue: layer.activeLinkId
            property string activeLinkTitle: layer.activeLink ? String(layer.activeLink.title || "") : ""
            property real activeAnchorXValue: layer.activeAnchorX
            property real activeAnchorYValue: layer.activeAnchorY

            Item {{
                id: fakeCanvas
                property real worldOffset: 0
                property real worldSize: 2000
                property var liveDragNodeLookup: ({{}})
                property real liveDragDx: 0
                property real liveDragDy: 0
                property var liveNodeGeometry: ({{}})
            }}

            GraphOverlay.GraphNodeLinkHoverLayer {{
                id: layer
                objectName: "layer"
                canvasItem: fakeCanvas
                sceneModel: probe.scene
                badgeModel: probe.scene
                visibleSceneRectPayload: ({{"x": 0, "y": 0, "width": 1000, "height": 700}})
            }}

            onStepChanged: {{
                if (step === 1) {{
                    layer.showNodeLinkCard("node-video", "link-docs", 111, 222);
                }} else if (step === 2) {{
                    scene = [];
                }} else if (step === 3) {{
                    scene = [
                        {{
                            "node_id": "node-video",
                            "x": 100,
                            "y": 80,
                            "width": 180,
                            "links": []
                        }}
                    ];
                }} else if (step === 4) {{
                    scene = [
                        {{
                            "node_id": "node-video",
                            "x": 420,
                            "y": 160,
                            "width": 240,
                            "links": [
                                {{
                                    "id": "link-docs",
                                    "kind": "url",
                                    "title": "Docs moved",
                                    "target": "https://example.com/docs"
                                }}
                            ]
                        }}
                    ];
                }} else if (step === 5) {{
                    layer.forceClearCard();
                }}
            }}
        }}
        """.encode("utf-8"),
        QUrl("node-link-hover-sync-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()

    layer = probe.findChild(QObject, "layer")
    card = probe.findChild(QObject, "graphNodeLinkHoverCard")
    assert layer is not None
    assert card is not None
    return engine, probe, layer, card


def _set_probe_step(qapp, probe: QObject, step: int) -> None:  # noqa: ANN001
    probe.setProperty("step", step)
    qapp.processEvents()
    qapp.processEvents()


def test_node_link_hover_layer_accepts_qt_projected_link_lists(qapp) -> None:  # noqa: ANN001
    provider = _NodePayloadProvider()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("provider", provider)
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            GraphOverlay.GraphNodeLinkHoverLayer {{ id: layer }}
            property int seenLinkCount: layer.linksForNode(provider.payloads[0]).length
            property string firstLinkTitle: String(layer.firstLink(provider.payloads[0]).title || "")
            property string secondLinkId: String(layer.linkForId(provider.payloads[0], "link-notes").id || "")
        }}
        """.encode("utf-8"),
        QUrl("node-link-hover-list-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()

    assert probe.property("seenLinkCount") == 2
    assert probe.property("firstLinkTitle") == "Docs"
    assert probe.property("secondLinkId") == "link-notes"


def test_node_link_hover_layer_static_fallback_tracks_live_drag(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            id: probe
            property var payload: {{
                "node_id": "node-video",
                "x": 120,
                "y": 80,
                "width": 220,
                "links": [{{"id": "link-docs", "kind": "url", "title": "Docs", "target": "https://example.com/docs"}}]
            }}

            Item {{
                id: fakeCanvas
                property real worldOffset: 1000
                property var liveDragNodeLookup: ({{"node-video": true}})
                property real liveDragDx: 36
                property real liveDragDy: -18
                property var liveNodeGeometry: ({{}})
            }}

            GraphOverlay.GraphNodeLinkHoverLayer {{
                id: layer
                canvasItem: fakeCanvas
            }}

            property real fallbackNodeX: layer.nodeX(payload)
            property real fallbackNodeY: layer.nodeY(payload)
            property real fallbackBadgeX: layer.nodeX(payload) + layer.nodeWidth(payload)
        }}
        """.encode("utf-8"),
        QUrl("node-link-hover-live-drag-fallback-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()

    assert float(probe.property("fallbackNodeX")) == 1156.0
    assert float(probe.property("fallbackNodeY")) == 1062.0
    assert float(probe.property("fallbackBadgeX")) == 1376.0


def test_node_link_and_comment_badges_clear_bottom_neutral_port(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            id: probe
            property var linkBadgeHost: null
            property var commentBadgeHost: null
            property real linkBadgeX: linkBadgeHost ? linkBadgeHost.x : -1
            property real linkBadgeY: linkBadgeHost ? linkBadgeHost.y : -1
            property real linkBadgeWidth: linkBadgeHost ? linkBadgeHost.width : -1
            property real commentBadgeX: commentBadgeHost ? commentBadgeHost.x : -1
            property real commentBadgeY: commentBadgeHost ? commentBadgeHost.y : -1
            property real commentBadgeWidth: commentBadgeHost ? commentBadgeHost.width : -1
            property var commentScene: [
                {{
                    "node_id": "node-video",
                    "x": 100,
                    "y": 80,
                    "width": 200,
                    "height": 100,
                    "ports": [{{"key": "bottom", "side": "bottom", "direction": "neutral", "kind": "flow", "data_type": "flow"}}],
                    "links": [{{"id": "link-docs", "kind": "url", "title": "Docs", "target": "https://example.com/docs"}}],
                    "comments": [{{"id": "comment-1", "body": "Review this."}}],
                    "comment_badge": {{"count": 3, "open_count": 3, "unread": true}}
                }}
            ]
            property var scene: commentScene

            Item {{
                id: fakeCanvas
                property real worldOffset: 0
                property real worldSize: 2000
                property var liveDragNodeLookup: ({{}})
                property real liveDragDx: 0
                property real liveDragDy: 0
                property var liveNodeGeometry: ({{}})
            }}

            GraphOverlay.GraphNodeLinkHoverLayer {{
                id: linkLayer
                canvasItem: fakeCanvas
                sceneModel: probe.scene
                badgeModel: probe.scene
            }}

            GraphOverlay.GraphNodeCommentPopoverLayer {{
                id: commentLayer
                canvasItem: fakeCanvas
                sceneModel: probe.scene
                badgeModel: probe.scene
            }}

            function findNamedChild(item, name) {{
                if (!item)
                    return null;
                if (item.objectName === name)
                    return item;
                for (var i = 0; i < item.children.length; ++i) {{
                    var found = findNamedChild(item.children[i], name);
                    if (found)
                        return found;
                }}
                return null;
            }}

            function refreshBadgeHosts() {{
                linkBadgeHost = findNamedChild(linkLayer, "graphNodeLinkBadgeHost");
                commentBadgeHost = findNamedChild(commentLayer, "graphNodeCommentBadgeHost");
            }}

            Component.onCompleted: Qt.callLater(refreshBadgeHosts)
        }}
        """.encode("utf-8"),
        QUrl("node-link-comment-bottom-center-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()
    qapp.processEvents()

    def assert_badges_clear_port() -> None:
        qapp.processEvents()
        qapp.processEvents()
        link_x = float(probe.property("linkBadgeX"))
        link_y = float(probe.property("linkBadgeY"))
        link_width = float(probe.property("linkBadgeWidth"))
        comment_x = float(probe.property("commentBadgeX"))
        comment_y = float(probe.property("commentBadgeY"))
        comment_width = float(probe.property("commentBadgeWidth"))

        assert link_x >= 212
        assert comment_x >= 0
        assert abs(link_y - 171.0) < 0.01
        assert abs(comment_y - link_y) < 0.01
        assert abs(comment_x - (link_x + link_width) - 6.0) < 0.01
        assert comment_x > 212

    assert_badges_clear_port()


def test_node_comment_popover_hides_immediately_on_close(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            id: probe
            property int step: 0
            property var scene: [
                {{
                    "node_id": "node-comment",
                    "title": "Decision",
                    "x": 100,
                    "y": 80,
                    "width": 200,
                    "height": 100,
                    "comments": [{{"id": "comment-1", "body": "Needs review.", "resolved": false}}],
                    "comment_badge": {{
                        "count": 1,
                        "open_count": 1,
                        "preview_comments": [
                            {{"id": "comment-1", "body": "Needs review.", "resolved": false}}
                        ]
                    }}
                }}
            ]

            Item {{
                id: fakeCanvas
                property real worldOffset: 0
                property real worldSize: 2000
                property var liveDragNodeLookup: ({{}})
                property real liveDragDx: 0
                property real liveDragDy: 0
                property var liveNodeGeometry: ({{}})
            }}

            GraphOverlay.GraphNodeCommentPopoverLayer {{
                id: layer
                objectName: "layer"
                canvasItem: fakeCanvas
                sceneModel: probe.scene
                badgeModel: probe.scene
                visibleSceneRectPayload: ({{"x": 0, "y": 0, "width": 1000, "height": 700}})
            }}

            onStepChanged: {{
                if (step === 1) {{
                    layer.showPeek(scene[0], 0, 0);
                }} else if (step === 2) {{
                    layer.forceClearCard();
                }}
            }}
        }}
        """.encode("utf-8"),
        QUrl("node-comment-popover-close-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()
    card = probe.findChild(QObject, "graphNodeCommentPopover")
    layer = probe.findChild(QObject, "layer")
    assert card is not None
    assert layer is not None

    _set_probe_step(qapp, probe, 1)
    assert card.property("visible") is True

    _set_probe_step(qapp, probe, 2)

    assert card.property("visible") is False
    assert layer.property("activeNodeId") == ""


def test_node_link_hover_card_clears_when_active_node_leaves_scene(qapp) -> None:  # noqa: ANN001
    _engine, probe, layer, _card = _create_hover_sync_probe(qapp)

    _set_probe_step(qapp, probe, 1)
    assert probe.property("layerActive") is True
    assert layer.property("activeNodeId") == "node-video"
    assert layer.property("activeLinkId") == "link-docs"

    _set_probe_step(qapp, probe, 2)

    assert probe.property("layerActive") is False
    assert probe.property("activeNodeDataMissing") is True
    assert probe.property("activeLinkMissing") is True
    assert layer.property("activeNodeId") == ""
    assert layer.property("activeLinkId") == ""


def test_node_link_hover_card_clears_when_active_link_leaves_node(qapp) -> None:  # noqa: ANN001
    _engine, probe, layer, _card = _create_hover_sync_probe(qapp)

    _set_probe_step(qapp, probe, 1)
    assert probe.property("layerActive") is True

    _set_probe_step(qapp, probe, 3)

    assert probe.property("layerActive") is False
    assert layer.property("activeNodeId") == ""
    assert layer.property("activeLinkId") == ""


def test_node_link_hover_card_follows_active_node_geometry(qapp) -> None:  # noqa: ANN001
    _engine, probe, _layer, card = _create_hover_sync_probe(qapp)

    _set_probe_step(qapp, probe, 1)
    initial_x = float(card.property("x"))
    initial_y = float(card.property("y"))

    _set_probe_step(qapp, probe, 4)

    assert probe.property("layerActive") is True
    assert probe.property("activeLinkTitle") == "Docs moved"
    assert float(card.property("x")) > initial_x + 250.0
    assert float(card.property("y")) > initial_y + 70.0


def test_node_link_hover_force_clear_resets_active_ids_data_link_and_anchor(qapp) -> None:  # noqa: ANN001
    _engine, probe, layer, _card = _create_hover_sync_probe(qapp)

    _set_probe_step(qapp, probe, 1)
    assert probe.property("layerActive") is True
    assert float(probe.property("activeAnchorXValue")) == 111.0
    assert float(probe.property("activeAnchorYValue")) == 222.0

    _set_probe_step(qapp, probe, 5)

    assert probe.property("layerActive") is False
    assert probe.property("activeNodeDataMissing") is True
    assert probe.property("activeLinkMissing") is True
    assert layer.property("activeNodeId") == ""
    assert layer.property("activeLinkId") == ""
    assert float(layer.property("activeAnchorX")) == 0.0
    assert float(layer.property("activeAnchorY")) == 0.0


def test_node_link_hover_card_width_fits_action_buttons(qapp) -> None:  # noqa: ANN001
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        f"""
        import QtQuick 2.15
        import "file:///{_HOVER_LAYER_IMPORT}" as GraphOverlay

        Item {{
            GraphOverlay.GraphNodeLinkHoverLayer {{ objectName: "layer" }}
        }}
        """.encode("utf-8"),
        QUrl("node-link-hover-card-layout-probe.qml"),
    )
    assert component.status() == QQmlComponent.Status.Ready, _qml_error_text(component)

    probe = component.create()
    assert probe is not None, _qml_error_text(component)
    qapp.processEvents()

    card = probe.findChild(QObject, "graphNodeLinkHoverCard")
    actions = probe.findChild(QObject, "graphNodeLinkHoverCardActions")
    hover_handler = probe.findChild(QObject, "graphNodeLinkHoverCardHoverHandler")
    assert card is not None
    assert actions is not None
    assert hover_handler is not None
    assert float(card.property("width")) >= float(actions.property("implicitWidth")) + 28

    hover_layer_source = (_REPO_ROOT / "ea_node_editor/ui_qml/components/graph/overlay/GraphNodeLinkHoverLayer.qml").read_text(
        encoding="utf-8"
    )
    assert "acceptedButtons: Qt.NoButton" not in hover_layer_source


def test_badge_layers_share_sparse_model_without_empty_ghosts() -> None:
    components = _REPO_ROOT / "ea_node_editor/ui_qml/components"
    root_layers = (components / "graph_canvas/GraphCanvasRootLayers.qml").read_text(encoding="utf-8")
    link_layer = (components / "graph/overlay/GraphNodeLinkHoverLayer.qml").read_text(encoding="utf-8")
    comment_layer = (components / "graph/overlay/GraphNodeCommentPopoverLayer.qml").read_text(encoding="utf-8")
    node_host = (components / "graph/GraphNodeHost.qml").read_text(encoding="utf-8")

    assert root_layers.count("badgeModel: root.visibleBadgeNodesModel") == 2
    assert "model: root.badgeModel" in link_layer
    assert "model: root.badgeModel" in comment_layer
    assert "id: emptyNodeHoverHost" not in comment_layer
    assert "graphNodeCommentGhostBadge" not in node_host
    assert "hoveredEmptyNodeId" not in comment_layer
    assert "hoveredCommentGhostNodeId" not in link_layer
