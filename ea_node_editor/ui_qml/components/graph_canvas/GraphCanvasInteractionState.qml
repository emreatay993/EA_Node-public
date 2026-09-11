import QtQuick 2.15
import QtQml 2.15
import "GraphCanvasLogic.js" as GraphCanvasLogic

QtObject {
    id: root
    property Item canvasItem: null
    property var shellBridge: null
    property var sceneBridge: null
    property var edgeLayerItem: null
    property var interactionIdleTimer: null
    property int interactionIdleDelayMs: 150
    property bool viewportInteractionHeld: false
    property real wireDragThreshold: 2

    property var hoveredPort: null
    property var dropPreviewPort: null
    property string dropPreviewEdgeId: ""
    property var dropPreviewNodePayload: null
    property string dropPreviewProjectionKey: ""
    property real dropPreviewScreenX: -1
    property real dropPreviewScreenY: -1
    property var pendingConnectionPort: null
    property var wireDragState: null
    property int compatibilityGraphRevision: 0
    property bool compatibilityRefreshPending: false
    property var wireDropCandidate: null
    property var wireInvalidDropCandidate: null
    property bool edgeContextVisible: false
    property bool nodeContextVisible: false
    property bool selectionContextVisible: false
    property bool canvasOptionsVisible: false
    property string edgeContextEdgeId: ""
    property string nodeContextNodeId: ""
    property real contextMenuX: 0
    property real contextMenuY: 0
    property bool contextMenuSceneAnchorActive: false
    property real contextMenuSceneAnchorX: 0
    property real contextMenuSceneAnchorY: 0
    property bool selectionContextSceneAnchorActive: false
    property real selectionContextSceneAnchorX: 0
    property real selectionContextSceneAnchorY: 0
    property bool interactionActive: false
    readonly property bool viewportInteractionCacheActive: root.interactionActive

    function _requestEdgeRedraw() {
        if (root.edgeLayerItem && root.edgeLayerItem.requestRedraw)
            root.edgeLayerItem.requestRedraw();
    }

    function _canvasEdges() {
        return root.canvasItem ? (root.canvasItem.edgePayload || []) : [];
    }

    function _sceneNodes() {
        if (!root.sceneBridge)
            return [];
        if (root.sceneBridge.visible_nodes_payloads !== undefined)
            return root.sceneBridge.visible_nodes_payloads || [];
        return root.sceneBridge.nodes_model || [];
    }

    function _scenePortData(nodeId, portKey) {
        var normalizedNodeId = String(nodeId || "").trim();
        var normalizedPortKey = String(portKey || "").trim();
        if (!normalizedNodeId || !normalizedPortKey)
            return null;
        var nodes = _sceneNodes();
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node || String(node.node_id || "").trim() !== normalizedNodeId)
                continue;
            var ports = node.ports || [];
            for (var j = 0; j < ports.length; j++) {
                var port = ports[j];
                if (port && String(port.key || "").trim() === normalizedPortKey)
                    return port;
            }
            break;
        }
        return null;
    }

    function _normalizedPortDirection(directionLike, fallbackDirection) {
        var normalized = String(directionLike || "").trim().toLowerCase();
        if (normalized === "in" || normalized === "out" || normalized === "neutral")
            return normalized;
        return String(fallbackDirection || "").trim().toLowerCase();
    }

    function _portCardinalSide(portLike, fallbackPortKey) {
        return GraphCanvasLogic.normalizedPortSide(
            portLike && portLike.side !== undefined
                ? portLike.side
                : fallbackPortKey
        );
    }

    function _authoringPortPayload(nodeId, portKey, fallbackDirection, sceneX, sceneY) {
        var portData = _scenePortData(nodeId, portKey);
        var direction = _normalizedPortDirection(
            portData ? portData.direction : fallbackDirection,
            fallbackDirection
        );
        var side = _portCardinalSide(portData, portKey);
        var payload = {
            "node_id": nodeId,
            "port_key": portKey,
            "direction": direction,
            "kind": portData ? String(portData.kind || "") : "",
            "data_type": portData ? String(portData.data_type || "") : "",
            "catalog_generation": portData ? String(portData.catalog_generation || "") : "",
            "allow_multiple_connections": portData ? Boolean(portData.allow_multiple_connections) : false,
            "scene_x": sceneX,
            "scene_y": sceneY,
            "valid_drop": false
        };
        if (side)
            payload.side = side;
        if (GraphCanvasLogic.isNeutralFlowPort(payload))
            payload.origin_side = side;
        return payload;
    }

    function _dropTargetInput(sourceDrag, candidate) {
        return GraphCanvasLogic.dropTargetInput(sourceDrag, candidate);
    }

    function _isExactDuplicate(sourceDrag, candidate, edge) {
        return GraphCanvasLogic.isExactDuplicate(sourceDrag, candidate, edge);
    }

    function _portKind(nodeId, portKey) {
        var port = _scenePortData(nodeId, portKey);
        return port ? String(port.kind || "") : "";
    }

    function _portDataType(nodeId, portKey) {
        var port = _scenePortData(nodeId, portKey);
        return port
            ? String(port.data_type || "COREX.DataTypes.Any")
            : "COREX.DataTypes.Any";
    }

    function _arePortKindsCompatible(sourceKind, targetKind) {
        if (!root.sceneBridge || !root.sceneBridge.are_port_kinds_compatible)
            return false;
        return root.sceneBridge.are_port_kinds_compatible(
            String(sourceKind || ""),
            String(targetKind || "")
        );
    }

    function _areDataTypesCompatible(sourceType, targetType) {
        if (!root.sceneBridge || !root.sceneBridge.are_data_types_compatible)
            return false;
        return root.sceneBridge.are_data_types_compatible(
            String(sourceType || ""),
            String(targetType || "")
        );
    }

    function _isDropAllowed(sourceDrag, candidate) {
        if (!sourceDrag || !candidate)
            return false;
        var state = root.pendingConnectionPort || sourceDrag;
        state.source_direction = sourceDrag.source_direction;
        _activateWireCompatibilitySnapshot(state);
        var candidatePort = _scenePortData(candidate.node_id, candidate.port_key);
        if (!candidatePort || candidatePort.exposed === false)
            return false;
        return _isWireDragDropAllowed(state, _wireDragSourceData(state),
            Object.assign({}, candidate, candidatePort));
    }

    function _compatibleEndpointKey(nodeId, portKey) {
        var normalizedNodeId = String(nodeId || "");
        var normalizedPortKey = String(portKey || "");
        return "$" + normalizedNodeId.length + ":" + normalizedNodeId
            + ":" + normalizedPortKey.length + ":" + normalizedPortKey;
    }

    function _wireDragCandidateRole(state) {
        if (!state)
            return "";
        var movingEndpoint = String(state.moving_endpoint || "").trim().toLowerCase();
        if (state.rewire && (movingEndpoint === "source" || movingEndpoint === "target"))
            return movingEndpoint;
        return _normalizedPortDirection(state.source_direction, "") === "in"
            ? "source"
            : "target";
    }

    function _copyWireCompatibilitySnapshot(source, target) {
        if (!source || !target || source.compatibility_snapshot_loaded === undefined)
            return;
        target.compatibility_snapshot_loaded = Boolean(source.compatibility_snapshot_loaded);
        target.compatibility_graph_revision = source.compatibility_graph_revision;
        target.compatibility_snapshot_valid = Boolean(source.compatibility_snapshot_valid);
        target.compatibility_candidate_role = String(source.compatibility_candidate_role || "");
        target.compatibility_catalog_generation = String(source.compatibility_catalog_generation || "");
        target.compatibility_anchor_catalog_generation = String(
            source.compatibility_anchor_catalog_generation || ""
        );
        target.compatible_endpoint_ids = source.compatible_endpoint_ids || [];
        target.compatible_endpoint_lookup = source.compatible_endpoint_lookup || ({});
    }

    function _activateWireCompatibilitySnapshot(state) {
        if (!state || (state.compatibility_snapshot_loaded
                && state.compatibility_graph_revision === root.compatibilityGraphRevision))
            return state;

        state.compatibility_graph_revision = root.compatibilityGraphRevision;
        state.compatibility_snapshot_loaded = true;
        state.compatibility_snapshot_valid = false;
        state.compatibility_candidate_role = _wireDragCandidateRole(state);
        state.compatibility_catalog_generation = "";
        state.compatibility_anchor_catalog_generation = "";
        state.compatible_endpoint_ids = [];
        state.compatible_endpoint_lookup = ({});
        if (!root.sceneBridge)
            return state;

        var sourcePort = _scenePortData(state.node_id, state.port_key);
        if (!sourcePort || sourcePort.exposed === false)
            return state;
        var anchorGeneration = String(sourcePort && sourcePort.catalog_generation || "").trim();
        state.compatibility_anchor_catalog_generation = anchorGeneration;
        var snapshot = null;
        try {
            if (state.rewire) {
                if (!root.sceneBridge.compatible_rewire_endpoint_snapshot)
                    return state;
                snapshot = root.sceneBridge.compatible_rewire_endpoint_snapshot(
                    state.moving_edge_ids || [],
                    String(state.moving_endpoint || ""),
                    Boolean(state.copy_requested),
                    Boolean(state.append_requested)
                );
            } else {
                if (!root.sceneBridge.compatible_endpoint_snapshot)
                    return state;
                snapshot = root.sceneBridge.compatible_endpoint_snapshot(
                    String(state.node_id || ""),
                    String(state.port_key || ""),
                    state.compatibility_candidate_role
                );
            }
        } catch (_error) {
            return state;
        }
        if (!snapshot)
            return state;

        var generation = String(snapshot.catalog_generation || "").trim();
        var role = String(snapshot.candidate_role || "").trim().toLowerCase();
        var endpoints = snapshot.compatible_endpoint_ids;
        if (!/^[0-9a-f]{64}$/.test(generation)
                || generation !== anchorGeneration
                || role !== state.compatibility_candidate_role
                || !endpoints
                || typeof endpoints.length !== "number") {
            return state;
        }

        var normalizedEndpoints = [];
        var lookup = ({});
        for (var index = 0; index < endpoints.length; ++index) {
            var endpoint = endpoints[index];
            var endpointNodeId = String(endpoint && endpoint.node_id || "");
            var endpointPortKey = String(endpoint && endpoint.port_key || "");
            if (!endpointNodeId.trim() || !endpointPortKey.trim())
                return state;
            normalizedEndpoints.push({
                "node_id": endpointNodeId,
                "port_key": endpointPortKey
            });
            lookup[_compatibleEndpointKey(endpointNodeId, endpointPortKey)] = true;
        }

        state.compatibility_snapshot_valid = true;
        state.compatibility_catalog_generation = generation;
        state.compatible_endpoint_ids = normalizedEndpoints;
        state.compatible_endpoint_lookup = lookup;
        return state;
    }

    function _rewireTopologyIsCurrent(state) {
        if (!state.rewire)
            return true;
        var original = _scenePortData(state.origin_node_id, state.origin_port_key);
        if (!original || original.exposed === false)
            return false;
        var edges = _canvasEdges();
        return (state.moving_edges || []).every(function(member) {
            return edges.some(function(edge) {
                if (edge.edge_id !== member.edge_id)
                    return false;
                var sourceMoved = state.moving_endpoint === "source";
                return edge.source_node_id === (sourceMoved ? state.origin_node_id : member.fixed_node_id)
                    && edge.source_port_key === (sourceMoved ? state.origin_port_key : member.fixed_port_key)
                    && edge.target_node_id === (sourceMoved ? member.fixed_node_id : state.origin_node_id)
                    && edge.target_port_key === (sourceMoved ? member.fixed_port_key : state.origin_port_key);
            });
        });
    }

    function invalidateWireCompatibility() {
        // Scene publications invalidate graph facts independently of the type catalog.
        root.compatibilityGraphRevision += 1;
        if (root.compatibilityRefreshPending)
            return;
        root.compatibilityRefreshPending = true;
        Qt.callLater(function() {
            root.compatibilityRefreshPending = false;
            var state = root.wireDragState ? Object.assign({}, root.wireDragState) : null;
            var pending = root.pendingConnectionPort;
            if (pending && !_scenePortData(pending.node_id, pending.port_key))
                root.clearPendingConnection();
            if (!state || !state.active) {
                _requestEdgeRedraw();
                return;
            }
            var anchor = _scenePortData(state.node_id, state.port_key);
            if (!anchor || anchor.exposed === false || !_rewireTopologyIsCurrent(state)) {
                root._clearWireDragState();
                return;
            }
            _activateWireCompatibilitySnapshot(state);
            root.wireDragState = state;
            root._updateWireDropCandidate(root.canvasItem.sceneToScreenX(state.cursor_x),
                root.canvasItem.sceneToScreenY(state.cursor_y), state);
            _requestEdgeRedraw();
        });
    }

    function _isWireDragDropAllowed(state, sourceDrag, candidate) {
        if (!state || !sourceDrag || !candidate)
            return false;
        if (Boolean(candidate.blocks_new_connections) || Boolean(candidate.inactive))
            return false;
        _activateWireCompatibilitySnapshot(state);
        var snapshotCompatible = Boolean(state.compatibility_snapshot_valid)
            && String(state.compatibility_catalog_generation || "").length > 0
            && String(sourceDrag.catalog_generation || "")
                === String(state.compatibility_catalog_generation || "")
            && String(candidate.catalog_generation || "")
                === String(state.compatibility_catalog_generation || "")
            && Boolean(
                (state.compatible_endpoint_lookup || ({}))[
                    _compatibleEndpointKey(candidate.node_id, candidate.port_key)
                ]
            );
        return GraphCanvasLogic.isDropAllowedWithCompatibility(
            sourceDrag,
            candidate,
            _canvasEdges(),
            snapshotCompatible,
            snapshotCompatible
        );
    }

    function _appendRequested(modifiers) {
        return (Number(modifiers || 0) & Qt.ShiftModifier) !== 0;
    }

    function _controlRequested(modifiers) {
        return (Number(modifiers || 0) & Qt.ControlModifier) !== 0;
    }

    function _scenePortFacts(nodeId, portKey) {
        var nodes = _sceneNodes();
        for (var nodeIndex = 0; nodeIndex < nodes.length; ++nodeIndex) {
            var node = nodes[nodeIndex];
            if (!node || String(node.node_id || "") !== String(nodeId || ""))
                continue;
            var inputRow = 0;
            var outputRow = 0;
            var ports = node.ports || [];
            for (var portIndex = 0; portIndex < ports.length; ++portIndex) {
                var port = ports[portIndex];
                if (!port || port.handle_visible === false)
                    continue;
                var point = _scenePortPoint(node, port, inputRow, outputRow);
                if (port.direction === "in")
                    inputRow += 1;
                else
                    outputRow += 1;
                if (String(port.key || "") === String(portKey || ""))
                    return {"port": port, "point": point};
            }
            break;
        }
        return null;
    }

    function _edgeEndpointDragForPort(nodeId, portKey, direction, copyRequested) {
        var matches = [];
        var edges = _canvasEdges();
        for (var edgeIndex = 0; edgeIndex < edges.length; ++edgeIndex) {
            var edge = edges[edgeIndex];
            if (!edge)
                continue;
            if (String(edge.source_node_id || "") === String(nodeId || "")
                    && String(edge.source_port_key || "") === String(portKey || "")) {
                matches.push({"edge": edge, "endpoint": "source"});
            }
            if (String(edge.target_node_id || "") === String(nodeId || "")
                    && String(edge.target_port_key || "") === String(portKey || "")) {
                matches.push({"edge": edge, "endpoint": "target"});
            }
        }

        var normalizedDirection = _normalizedPortDirection(direction, "");
        var expectedEndpoint = normalizedDirection === "out"
            ? "source"
            : (normalizedDirection === "in" ? "target" : "");
        if (expectedEndpoint) {
            matches = matches.filter(function(match) {
                return match.endpoint === expectedEndpoint;
            });
        }
        if (matches.length === 0)
            return null;

        var activeMatches = matches.filter(function(match) {
            return Boolean(match.edge && match.edge.active_data_wire);
        });
        var parityBundle = activeMatches.length > 0;
        if (parityBundle)
            matches = activeMatches;

        var selectedIds = root.canvasItem ? (root.canvasItem.selectedEdgeIds || []) : [];
        if (Boolean(copyRequested) || !parityBundle) {
            if (matches.length !== 1) {
                var selectedMatches = matches.filter(function(match) {
                    return selectedIds.indexOf(String(match.edge.edge_id || "")) >= 0;
                });
                if (selectedMatches.length !== 1)
                    return null;
                matches = selectedMatches;
            }
        }

        var endpoint = String(matches[0].endpoint || "");
        var members = [];
        var edgeIds = [];
        for (var matchIndex = 0; matchIndex < matches.length; ++matchIndex) {
            var match = matches[matchIndex];
            if (String(match.endpoint || "") !== endpoint)
                return null;
            var edge = match.edge;
            var fixedNodeId = endpoint === "source" ? edge.target_node_id : edge.source_node_id;
            var fixedPortKey = endpoint === "source" ? edge.target_port_key : edge.source_port_key;
            var fixedFacts = _scenePortFacts(fixedNodeId, fixedPortKey);
            if (!fixedFacts)
                return null;
            var fixedPort = fixedFacts.port;
            var member = {
                "edge_id": String(edge.edge_id || ""),
                "fixed_node_id": String(fixedNodeId || ""),
                "fixed_port_key": String(fixedPortKey || ""),
                "fixed_direction": _normalizedPortDirection(fixedPort.direction, ""),
                "fixed_kind": String(fixedPort.kind || ""),
                "fixed_x": Number(fixedFacts.point.x),
                "fixed_y": Number(fixedFacts.point.y),
                "active_data_wire": Boolean(edge.active_data_wire)
            };
            var fixedSide = _portCardinalSide(fixedPort, fixedPortKey);
            if (fixedSide)
                member.fixed_side = fixedSide;
            members.push(member);
            edgeIds.push(member.edge_id);
        }
        return {
            "endpoint": endpoint,
            "edge_ids": edgeIds,
            "members": members,
            "active_data_wire": parityBundle
        };
    }

    function _connectionPreviewFacts(sourceDrag, candidate, appendRequested) {
        var facts = {
            "append_requested": Boolean(appendRequested),
            "connection_mode": Boolean(appendRequested) ? "append" : "connect",
            "duplicate": false,
            "replaces_existing": false,
            "replacement_edge_ids": []
        };
        if (!sourceDrag || !candidate)
            return facts;
        var targetInput = _dropTargetInput(sourceDrag, candidate);
        var edges = _canvasEdges();
        var targetEdges = [];
        for (var i = 0; i < edges.length; ++i) {
            var edge = edges[i];
            if (!edge
                    || String(edge.target_node_id || "") !== String(targetInput.node_id || "")
                    || String(edge.target_port_key || "") !== String(targetInput.port_key || "")) {
                continue;
            }
            targetEdges.push(edge);
            if (_isExactDuplicate(sourceDrag, candidate, edge))
                facts.duplicate = true;
        }
        if (facts.duplicate) {
            facts.connection_mode = "noop";
            return facts;
        }
        if (!facts.append_requested && targetEdges.length > 0) {
            facts.connection_mode = "replace";
            facts.replaces_existing = true;
            targetEdges.sort(function(left, right) {
                var orderDelta = Number(left.input_order || 0) - Number(right.input_order || 0);
                if (orderDelta !== 0)
                    return orderDelta;
                return String(left.edge_id || "").localeCompare(String(right.edge_id || ""));
            });
            for (var replacementIndex = 0; replacementIndex < targetEdges.length; ++replacementIndex) {
                facts.replacement_edge_ids.push(String(targetEdges[replacementIndex].edge_id || ""));
            }
        }
        return facts;
    }

    function _scenePortPoint(node, port, inputRow, outputRow) {
        return GraphCanvasLogic.scenePortPoint(node, port, inputRow, outputRow);
    }

    function _nearestDropCandidateForWireDrag(
        screenX,
        screenY,
        sourceDrag,
        thresholdOverride,
        includeInvalid,
        wireState
    ) {
        if (!sourceDrag || !root.canvasItem)
            return null;
        if (!wireState)
            wireState = root.wireDragState;

        var threshold = Number(thresholdOverride);
        if (!(threshold > 0.0))
            threshold = 14.0;

        var nodes = _sceneNodes();
        var best = null;
        var bestDistance = Number.POSITIVE_INFINITY;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node)
                continue;
            var ports = node.ports || [];
            var inputRow = 0;
            var outputRow = 0;
            for (var j = 0; j < ports.length; j++) {
                var port = ports[j];
                if (!port || port.handle_visible === false)
                    continue;
                var point = _scenePortPoint(node, port, inputRow, outputRow);
                if (port.direction === "in")
                    inputRow += 1;
                else
                    outputRow += 1;
                var dx = Number(screenX) - root.canvasItem.sceneToScreenX(point.x);
                var dy = Number(screenY) - root.canvasItem.sceneToScreenY(point.y);
                var distance = Math.sqrt(dx * dx + dy * dy);
                if (distance > threshold || distance >= bestDistance)
                    continue;
                var side = _portCardinalSide(port, port.key);
                var candidate = {
                    "node_id": node.node_id,
                    "port_key": port.key,
                    "direction": _normalizedPortDirection(port.direction, ""),
                    "kind": String(port.kind || ""),
                    "data_type": String(port.data_type || ""),
                    "catalog_generation": String(port.catalog_generation || ""),
                    "blocks_new_connections": Boolean(port.blocks_new_connections),
                    "inactive": Boolean(port.inactive),
                    "allow_multiple_connections": Boolean(port.allow_multiple_connections),
                    "scene_x": point.x,
                    "scene_y": point.y,
                    "valid_drop": false
                };
                if (side)
                    candidate.side = side;
                candidate.valid_drop = _isWireDragDropAllowed(wireState, sourceDrag, candidate);
                if (!candidate.valid_drop && !Boolean(includeInvalid))
                    continue;
                bestDistance = distance;
                best = candidate;
            }
        }
        return best;
    }

    function _portsCompatibleForAuto(sourcePort, targetPort) {
        return GraphCanvasLogic.portsCompatibleForAuto(
            sourcePort,
            targetPort,
            _arePortKindsCompatible(
                sourcePort ? sourcePort.kind : "",
                targetPort ? targetPort.kind : ""
            ),
            _arePortTypesCompatible(sourcePort, targetPort)
        );
    }

    function _arePortTypesCompatible(sourcePort, targetPort) {
        if (!sourcePort || !targetPort || sourcePort.source_types_unresolved)
            return false;
        var sources = sourcePort.source_type_ids || [sourcePort.data_type];
        var targets = [targetPort.data_type].concat(targetPort.accepted_data_types || []);
        return sources.length > 0 && sources.every(function(sourceType) {
            return targets.some(function(targetType) { return _areDataTypesCompatible(sourceType, targetType); });
        });
    }

    function _libraryPorts(payload) {
        return GraphCanvasLogic.libraryPorts(payload);
    }

    function _hasCompatiblePortForTarget(targetPort, nodePorts) {
        if (!targetPort || !nodePorts || !nodePorts.length)
            return false;
        if (
            targetPort.direction === "in"
            && GraphCanvasLogic.isFlowEdgePortKind(targetPort.kind)
            && !Boolean(targetPort.allow_multiple_connections)
            && Number(targetPort.connection_count || 0) > 0
        )
            return false;

        for (var i = 0; i < nodePorts.length; i++) {
            var nodePort = nodePorts[i];
            if (!nodePort || nodePort.exposed === false)
                continue;
            if (
                GraphCanvasLogic.autoConnectCompatibleWithTarget(
                    targetPort,
                    nodePort,
                    _arePortKindsCompatible(
                        nodePort.kind || "",
                        targetPort.kind || ""
                    ),
                    targetPort.direction === "out" ? _arePortTypesCompatible(targetPort, nodePort)
                        : _arePortTypesCompatible(nodePort, targetPort)
                )
            )
                return true;
        }
        return false;
    }

    function _portDropTargetAtScreen(screenX, screenY, payload) {
        if (!root.canvasItem)
            return null;

        var nodePorts = _libraryPorts(payload);
        if (!nodePorts.length)
            return null;

        var nodes = _sceneNodes();
        var threshold = 12.0;
        var best = null;
        var bestDistance = Number.POSITIVE_INFINITY;

        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node)
                continue;
            var ports = node.ports || [];
            var inputRow = 0;
            var outputRow = 0;
            for (var j = 0; j < ports.length; j++) {
                var port = ports[j];
                if (!port || port.handle_visible === false)
                    continue;
                var point = _scenePortPoint(node, port, inputRow, outputRow);
                if (port.direction === "in")
                    inputRow += 1;
                else
                    outputRow += 1;
                var dx = Number(screenX) - root.canvasItem.sceneToScreenX(point.x);
                var dy = Number(screenY) - root.canvasItem.sceneToScreenY(point.y);
                var distance = Math.sqrt(dx * dx + dy * dy);
                if (distance > threshold || distance >= bestDistance)
                    continue;
                if (!_hasCompatiblePortForTarget(port, nodePorts))
                    continue;
                bestDistance = distance;
                best = {
                    "mode": "port",
                    "node_id": node.node_id,
                    "port_key": port.key,
                    "direction": port.direction,
                    "edge_id": ""
                };
            }
        }
        return best;
    }

    function _edgeSupportsDrop(edgeId, payload) {
        var normalizedEdgeId = String(edgeId || "").trim();
        if (!normalizedEdgeId)
            return false;

        var edges = _canvasEdges();
        var edge = null;
        for (var i = 0; i < edges.length; i++) {
            if (String(edges[i].edge_id || "").trim() === normalizedEdgeId) {
                edge = edges[i];
                break;
            }
        }
        if (!edge)
            return false;

        var sourcePort = _scenePortData(edge.source_node_id, edge.source_port_key);
        var targetPort = _scenePortData(edge.target_node_id, edge.target_port_key);
        if (!sourcePort || !targetPort)
            return false;

        var nodePorts = _libraryPorts(payload);
        var hasInputCandidate = false;
        var hasOutputCandidate = false;
        for (var j = 0; j < nodePorts.length; j++) {
            var nodePort = nodePorts[j];
            if (!nodePort || nodePort.exposed === false)
                continue;
            if (
                !hasInputCandidate
                && GraphCanvasLogic.autoConnectCompatibleAsInsertedInput(
                    sourcePort,
                    nodePort,
                    _arePortKindsCompatible(
                        sourcePort.kind || "",
                        nodePort.kind || ""
                    ),
                    _arePortTypesCompatible(sourcePort, nodePort)
                )
            )
                hasInputCandidate = true;
            if (
                !hasOutputCandidate
                && GraphCanvasLogic.autoConnectCompatibleAsInsertedOutput(
                    nodePort,
                    targetPort,
                    _arePortKindsCompatible(
                        nodePort.kind || "",
                        targetPort.kind || ""
                    ),
                    _arePortTypesCompatible(nodePort, targetPort)
                )
            )
                hasOutputCandidate = true;
            if (hasInputCandidate && hasOutputCandidate)
                return true;
        }
        return false;
    }

    function _computeLibraryDropTarget(screenX, screenY, payload) {
        var portTarget = _portDropTargetAtScreen(screenX, screenY, payload);
        if (portTarget)
            return portTarget;

        var edgeId = root.edgeLayerItem && root.edgeLayerItem.edgeAtScreen
            ? root.edgeLayerItem.edgeAtScreen(screenX, screenY)
            : "";
        if (edgeId && _edgeSupportsDrop(edgeId, payload)) {
            return {
                "mode": "edge",
                "node_id": "",
                "port_key": "",
                "direction": "",
                "edge_id": edgeId
            };
        }

        return {
            "mode": "",
            "node_id": "",
            "port_key": "",
            "direction": "",
            "edge_id": ""
        };
    }

    function _previewNodeMetrics(payload) {
        return GraphCanvasLogic.previewNodeMetrics(payload);
    }

    function _projectLibraryDropPreviewPayload(payload) {
        if (root.sceneBridge && root.sceneBridge.library_drop_preview_payload) {
            var projected = root.sceneBridge.library_drop_preview_payload(payload);
            if (projected && String(projected.type_id || "").trim())
                return projected;
        }
        return payload;
    }

    function _libraryDropPreviewProjectionKey(payload) {
        var prefs = root.canvasItem && root.canvasItem.prefs ? root.canvasItem.prefs : null;
        return [
            String(payload ? payload.type_id || "" : ""),
            String(payload ? payload.workflow_id || "" : ""),
            String(payload ? payload.revision || "" : ""),
            root.canvasItem ? Boolean(root.canvasItem.hideOptionalPorts) : false
        ].join("|");
    }

    function previewNodeMetrics() {
        return _previewNodeMetrics(root.dropPreviewNodePayload);
    }

    function _previewVisiblePorts(payload, direction) {
        return GraphCanvasLogic.previewVisiblePorts(payload, direction);
    }

    function previewInputPorts() {
        return _previewVisiblePorts(root.dropPreviewNodePayload, "in");
    }

    function previewOutputPorts() {
        return _previewVisiblePorts(root.dropPreviewNodePayload, "out");
    }

    function previewPortColor(kind) {
        return GraphCanvasLogic.previewPortColor(kind);
    }

    function previewNodeScreenWidth() {
        var zoom = root.canvasItem && root.canvasItem.canvasViewBridgeRef
            ? root.canvasItem.canvasViewBridgeRef.zoom_value
            : 1.0;
        var metrics = _previewNodeMetrics(root.dropPreviewNodePayload);
        return GraphCanvasLogic.previewNodeScreenExtent(metrics.default_width, zoom);
    }

    function previewNodeScreenHeight() {
        var zoom = root.canvasItem && root.canvasItem.canvasViewBridgeRef
            ? root.canvasItem.canvasViewBridgeRef.zoom_value
            : 1.0;
        var metrics = _previewNodeMetrics(root.dropPreviewNodePayload);
        return GraphCanvasLogic.previewNodeScreenExtent(metrics.default_height, zoom);
    }

    function previewPortLabelsVisible() {
        var zoom = root.canvasItem && root.canvasItem.canvasViewBridgeRef
            ? root.canvasItem.canvasViewBridgeRef.zoom_value
            : 1.0;
        return GraphCanvasLogic.previewPortLabelsVisible(zoom, root.previewNodeScreenWidth());
    }

    function clearLibraryDropPreview() {
        root.dropPreviewPort = null;
        root.dropPreviewEdgeId = "";
        root.dropPreviewNodePayload = null;
        root.dropPreviewProjectionKey = "";
        root.dropPreviewScreenX = -1;
        root.dropPreviewScreenY = -1;
    }

    function _validLibraryDropPreviewPoint(screenX, screenY) {
        if (!root.canvasItem)
            return false;
        var x = Number(screenX);
        var y = Number(screenY);
        if (!isFinite(x) || !isFinite(y))
            return false;
        if (root.canvasItem.isPointInCanvas && !root.canvasItem.isPointInCanvas(x, y))
            return false;
        return true;
    }

    function updateLibraryDropPreview(screenX, screenY, payload) {
        var previewTypeId = String(payload ? payload.type_id || "" : "").trim();
        if (!payload || !previewTypeId.length || !_validLibraryDropPreviewPoint(screenX, screenY)) {
            clearLibraryDropPreview();
            return;
        }
        var projectionKey = _libraryDropPreviewProjectionKey(payload);
        if (!root.dropPreviewNodePayload || root.dropPreviewProjectionKey !== projectionKey) {
            root.dropPreviewNodePayload = _projectLibraryDropPreviewPayload(payload);
            root.dropPreviewProjectionKey = projectionKey;
        }
        root.dropPreviewScreenX = Number(screenX);
        root.dropPreviewScreenY = Number(screenY);
        var target = _computeLibraryDropTarget(screenX, screenY, payload);
        root.dropPreviewPort = target.mode === "port"
            ? {
                "node_id": target.node_id,
                "port_key": target.port_key,
                "direction": target.direction
            }
            : null;
        root.dropPreviewEdgeId = target.mode === "edge" ? target.edge_id : "";
    }

    function performLibraryDrop(screenX, screenY, payload) {
        if (!payload || !root.shellBridge || !root.shellBridge.request_drop_node_from_library || !payload.type_id) {
            clearLibraryDropPreview();
            return;
        }
        if (!_validLibraryDropPreviewPoint(screenX, screenY)) {
            clearLibraryDropPreview();
            return;
        }
        root.canvasItem.forceActiveFocus();
        root._closeContextMenus();
        root.clearPendingConnection();
        var target = _computeLibraryDropTarget(screenX, screenY, payload);
        root.shellBridge.request_drop_node_from_library(
            String(payload.type_id || ""),
            root.canvasItem.screenToSceneX(screenX),
            root.canvasItem.screenToSceneY(screenY),
            target.mode || "",
            target.node_id || "",
            target.port_key || "",
            target.edge_id || ""
        );
        root.canvasItem.clearEdgeSelection();
        root.clearLibraryDropPreview();
    }

    function _samePort(a, b) {
        if (!a || !b)
            return false;
        return a.node_id === b.node_id && a.port_key === b.port_key;
    }

    function clearPendingConnection() {
        if (!root.pendingConnectionPort)
            return;
        root.pendingConnectionPort = null;
        root.hoveredPort = null;
        _requestEdgeRedraw();
    }

    function _wireDragSourceData(state) {
        if (!state)
            return null;
        var sourcePort = _scenePortData(state.node_id, state.port_key);
        var payload = {
            "node_id": state.node_id,
            "port_key": state.port_key,
            "source_direction": _normalizedPortDirection(
                state.source_direction,
                sourcePort ? sourcePort.direction : ""
            ),
            "kind": sourcePort ? String(sourcePort.kind || "") : "",
            "data_type": sourcePort ? String(sourcePort.data_type || "") : "",
            "catalog_generation": sourcePort ? String(sourcePort.catalog_generation || "") : "",
            "allow_multiple_connections": sourcePort ? Boolean(sourcePort.allow_multiple_connections) : false,
            "start_x": state.start_x,
            "start_y": state.start_y,
            "cursor_x": state.cursor_x,
            "cursor_y": state.cursor_y
        };
        var side = _portCardinalSide(sourcePort, state.port_key);
        if (side)
            payload.side = side;
        if (state.origin_side !== undefined)
            payload.origin_side = GraphCanvasLogic.normalizedPortSide(state.origin_side);
        else if (GraphCanvasLogic.isNeutralFlowPort(payload))
            payload.origin_side = side;
        return payload;
    }

    function wireDragSourcePort() {
        var state = root.wireDragState;
        if (!state || !state.active)
            return null;
        if (state.rewire) {
            return {
                "node_id": state.origin_node_id,
                "port_key": state.origin_port_key,
                "direction": state.origin_direction
            };
        }
        var payload = {
            "node_id": state.node_id,
            "port_key": state.port_key,
            "direction": state.source_direction
        };
        if (state.origin_side !== undefined)
            payload.origin_side = GraphCanvasLogic.normalizedPortSide(state.origin_side);
        return payload;
    }

    function _activeDataWirePreview(sourceDrag, candidate) {
        if (!sourceDrag || !candidate)
            return false;
        if (String(sourceDrag.kind || "").trim().toLowerCase() === "flow"
                || String(candidate.kind || "").trim().toLowerCase() === "flow") {
            return false;
        }
        var endpointIds = [String(sourceDrag.node_id || ""), String(candidate.node_id || "")];
        var nodes = _sceneNodes();
        for (var nodeIndex = 0; nodeIndex < nodes.length; ++nodeIndex) {
            var node = nodes[nodeIndex];
            if (!node || endpointIds.indexOf(String(node.node_id || "")) < 0)
                continue;
            var behavior = String(node.runtime_behavior || "").trim().toLowerCase();
            if (behavior === "active" || behavior === "compile_only")
                return true;
        }
        return false;
    }

    function _rewirePreviewConnections(state, target) {
        var connections = [];
        var members = state ? (state.moving_edges || []) : [];
        for (var index = 0; index < members.length; ++index) {
            var member = members[index];
            var mode = !target
                ? (Boolean(state.copy_requested) ? "noop" : "disconnect")
                : (!target.valid_drop
                    ? "noop"
                    : (Boolean(state.copy_requested) ? "copy" : "rewire"));
            var connection = {
                "edge_id": String(member.edge_id || ""),
                "source_direction": String(member.fixed_direction || ""),
                "source_node_id": String(member.fixed_node_id || ""),
                "source_port_key": String(member.fixed_port_key || ""),
                "source_kind": String(member.fixed_kind || ""),
                "start_x": Number(member.fixed_x),
                "start_y": Number(member.fixed_y),
                "target_x": target ? Number(target.scene_x) : Number(state.cursor_x),
                "target_y": target ? Number(target.scene_y) : Number(state.cursor_y),
                "valid_drop": target ? Boolean(target.valid_drop) : false,
                "append_requested": Boolean(state.append_requested),
                "copy_requested": Boolean(state.copy_requested),
                "connection_mode": mode,
                "active_data_wire": Boolean(member.active_data_wire),
                "duplicate": false,
                "replaces_existing": false
            };
            if (member.fixed_side !== undefined)
                connection.origin_side = GraphCanvasLogic.normalizedPortSide(member.fixed_side);
            if (target) {
                connection.target_node_id = target.node_id;
                connection.target_port_key = target.port_key;
                connection.target_kind = String(_portKind(target.node_id, target.port_key) || "");
                if (target.side !== undefined)
                    connection.target_side = GraphCanvasLogic.normalizedPortSide(target.side);
            }
            connections.push(connection);
        }
        if (connections.length === 1)
            return connections[0];
        return {"connections": connections};
    }

    function wireDragPreviewConnection() {
        var state = root.wireDragState;
        if (!state || !state.active)
            state = null;
        if (state) {
            var target = root.wireDropCandidate;
            if (state.rewire)
                return _rewirePreviewConnections(
                    state,
                    target ? target : root.wireInvalidDropCandidate
                );
            var sourcePort = _scenePortData(state.node_id, state.port_key);
            var sourceDrag = _wireDragSourceData(state);
            var previewFacts = _connectionPreviewFacts(
                sourceDrag,
                target,
                Boolean(state.append_requested)
            );
            var activeDataWire = _activeDataWirePreview(sourceDrag, target);
            var preview = {
                "source_direction": state.source_direction,
                "source_node_id": state.node_id,
                "source_port_key": state.port_key,
                "source_kind": sourcePort ? String(sourcePort.kind || "") : "",
                "start_x": state.start_x,
                "start_y": state.start_y,
                "target_x": target ? target.scene_x : state.cursor_x,
                "target_y": target ? target.scene_y : state.cursor_y,
                "valid_drop": target ? Boolean(target.valid_drop) : false,
                "append_requested": previewFacts.append_requested,
                "connection_mode": previewFacts.connection_mode,
                "duplicate": previewFacts.duplicate,
                "replaces_existing": previewFacts.replaces_existing,
                "replacement_edge_ids": previewFacts.replacement_edge_ids,
                "active_data_wire": activeDataWire
            };
            if (state.origin_side !== undefined)
                preview.origin_side = GraphCanvasLogic.normalizedPortSide(state.origin_side);
            if (target) {
                preview.target_node_id = target.node_id;
                preview.target_port_key = target.port_key;
                preview.target_kind = String(_portKind(target.node_id, target.port_key) || "");
                if (target.side !== undefined)
                    preview.target_side = GraphCanvasLogic.normalizedPortSide(target.side);
            }
            return preview;
        }

        var pending = root.pendingConnectionPort;
        var hovered = root.hoveredPort;
        if (!pending || !hovered || _samePort(pending, hovered))
            return null;

        var pendingSource = {
            "node_id": pending.node_id,
            "port_key": pending.port_key,
            "source_direction": pending.direction,
            "kind": String(pending.kind || ""),
            "data_type": String(pending.data_type || ""),
            "allow_multiple_connections": Boolean(pending.allow_multiple_connections),
            "start_x": pending.scene_x,
            "start_y": pending.scene_y,
            "cursor_x": hovered.scene_x,
            "cursor_y": hovered.scene_y
        };
        if (pending.side !== undefined)
            pendingSource.side = pending.side;
        if (pending.origin_side !== undefined)
            pendingSource.origin_side = pending.origin_side;
        var pendingCandidate = {
            "node_id": hovered.node_id,
            "port_key": hovered.port_key,
            "direction": hovered.direction,
            "kind": String(hovered.kind || ""),
            "data_type": String(hovered.data_type || ""),
            "allow_multiple_connections": Boolean(hovered.allow_multiple_connections),
            "scene_x": hovered.scene_x,
            "scene_y": hovered.scene_y,
            "valid_drop": _isDropAllowed(pendingSource, hovered)
        };
        if (hovered.side !== undefined)
            pendingCandidate.side = hovered.side;
        var pendingFacts = _connectionPreviewFacts(pendingSource, pendingCandidate, false);
        var pendingActiveDataWire = _activeDataWirePreview(pendingSource, pendingCandidate);
        var pendingPreview = {
            "source_direction": pending.direction,
            "source_node_id": pending.node_id,
            "source_port_key": pending.port_key,
            "source_kind": String(_portKind(pending.node_id, pending.port_key) || ""),
            "start_x": pending.scene_x,
            "start_y": pending.scene_y,
            "target_x": pendingCandidate.scene_x,
            "target_y": pendingCandidate.scene_y,
            "valid_drop": pendingCandidate.valid_drop,
            "append_requested": pendingFacts.append_requested,
            "connection_mode": pendingFacts.connection_mode,
            "duplicate": pendingFacts.duplicate,
            "replaces_existing": pendingFacts.replaces_existing,
            "replacement_edge_ids": pendingFacts.replacement_edge_ids,
            "active_data_wire": pendingActiveDataWire
        };
        pendingPreview.target_node_id = pendingCandidate.node_id;
        pendingPreview.target_port_key = pendingCandidate.port_key;
        pendingPreview.target_kind = String(_portKind(pendingCandidate.node_id, pendingCandidate.port_key) || "");
        if (pending.origin_side !== undefined)
            pendingPreview.origin_side = pending.origin_side;
        if (pendingCandidate.side !== undefined)
            pendingPreview.target_side = pendingCandidate.side;
        return pendingPreview;
    }

    function _updateWireDropCandidate(screenX, screenY, state) {
        var candidate = _nearestDropCandidateForWireDrag(
            screenX,
            screenY,
            _wireDragSourceData(state),
            undefined,
            false,
            state
        );
        root.wireInvalidDropCandidate = !candidate && state && state.rewire
            ? _nearestDropCandidateForWireDrag(
                screenX,
                screenY,
                _wireDragSourceData(state),
                undefined,
                true,
                state
            )
            : null;
        root.wireDropCandidate = candidate;
        root.hoveredPort = candidate ? candidate : null;
    }

    function _clearWireDragState() {
        if (!root.wireDragState && !root.wireDropCandidate && !root.wireInvalidDropCandidate)
            return;
        root.wireDragState = null;
        root.wireDropCandidate = null;
        root.wireInvalidDropCandidate = null;
        root.hoveredPort = root.pendingConnectionPort ? root.pendingConnectionPort : null;
        if (root.edgeLayerItem && root.edgeLayerItem.requestImmediateRedraw)
            root.edgeLayerItem.requestImmediateRedraw();
        else
            _requestEdgeRedraw();
    }

    function beginPortWireDrag(nodeId, portKey, direction, sceneX, sceneY, screenX, screenY, modifiers) {
        if (!root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        root._closeContextMenus();
        root.wireDropCandidate = null;
        root.wireInvalidDropCandidate = null;
        var source = _authoringPortPayload(nodeId, portKey, direction, sceneX, sceneY);
        var controlRequested = _controlRequested(modifiers);
        var copyRequested = controlRequested && _appendRequested(modifiers);
        var endpointDrag = null;
        if (controlRequested) {
            endpointDrag = _edgeEndpointDragForPort(nodeId, portKey, direction, copyRequested);
            if (!endpointDrag)
                return;
            copyRequested = copyRequested && Boolean(endpointDrag.active_data_wire);
            var firstMember = endpointDrag.members[0];
            source = _authoringPortPayload(
                firstMember.fixed_node_id,
                firstMember.fixed_port_key,
                firstMember.fixed_direction,
                firstMember.fixed_x,
                firstMember.fixed_y
            );
        }
        var state = {
            "node_id": source.node_id,
            "port_key": source.port_key,
            "source_direction": source.direction,
            "start_x": source.scene_x,
            "start_y": source.scene_y,
            "cursor_x": sceneX,
            "cursor_y": sceneY,
            "press_screen_x": Number(screenX),
            "press_screen_y": Number(screenY),
            "active": false,
            "append_requested": root._appendRequested(modifiers),
            "rewire": endpointDrag !== null,
            "copy_requested": copyRequested
        };
        if (endpointDrag) {
            state.moving_edge_ids = endpointDrag.edge_ids;
            state.moving_edges = endpointDrag.members;
            state.moving_endpoint = String(endpointDrag.endpoint || "");
            state.origin_node_id = String(nodeId || "");
            state.origin_port_key = String(portKey || "");
            state.origin_direction = _normalizedPortDirection(direction, "");
        }
        if (source.origin_side !== undefined)
            state.origin_side = source.origin_side;
        root.wireDragState = state;
    }

    function updatePortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) {
        if (!root.canvasItem)
            return;
        var state = root.wireDragState;
        if (!state)
            return;
        var normalizedDirection = _normalizedPortDirection(
            (_scenePortData(nodeId, portKey) || {}).direction,
            direction
        );
        var expectedNodeId = state.rewire ? state.origin_node_id : state.node_id;
        var expectedPortKey = state.rewire ? state.origin_port_key : state.port_key;
        var expectedDirection = state.rewire ? state.origin_direction : state.source_direction;
        if (expectedNodeId !== nodeId || expectedPortKey !== portKey || expectedDirection !== normalizedDirection)
            return;

        var movedEnough = Boolean(dragActive)
            || Math.abs(Number(screenX) - Number(state.press_screen_x)) >= root.wireDragThreshold
            || Math.abs(Number(screenY) - Number(state.press_screen_y)) >= root.wireDragThreshold;
        var next = {
            "node_id": state.node_id,
            "port_key": state.port_key,
            "source_direction": state.source_direction,
            "start_x": state.start_x,
            "start_y": state.start_y,
            "cursor_x": root.canvasItem.screenToSceneX(screenX),
            "cursor_y": root.canvasItem.screenToSceneY(screenY),
            "press_screen_x": state.press_screen_x,
            "press_screen_y": state.press_screen_y,
            "active": state.active || movedEnough,
            "append_requested": state.rewire
                ? Boolean(state.append_requested)
                : root._appendRequested(modifiers),
            "rewire": Boolean(state.rewire),
            "copy_requested": Boolean(state.copy_requested)
        };
        if (state.rewire) {
            next.moving_edge_ids = state.moving_edge_ids || [];
            next.moving_edges = state.moving_edges || [];
            next.moving_endpoint = state.moving_endpoint;
            next.origin_node_id = state.origin_node_id;
            next.origin_port_key = state.origin_port_key;
            next.origin_direction = state.origin_direction;
        }
        if (state.origin_side !== undefined)
            next.origin_side = state.origin_side;
        var becameActive = movedEnough && !state.active;
        _copyWireCompatibilitySnapshot(state, next);
        if (next.active)
            _activateWireCompatibilitySnapshot(next);
        root.wireDragState = next;
        if (!next.active)
            return;
        if (becameActive)
            root.clearPendingConnection();
        root._updateWireDropCandidate(screenX, screenY, next);
        _requestEdgeRedraw();
    }

    function finishPortWireDrag(nodeId, portKey, direction, _sceneX, _sceneY, screenX, screenY, dragActive, modifiers) {
        if (!root.canvasItem)
            return;
        var state = root.wireDragState;
        if (!state)
            return;
        var normalizedDirection = _normalizedPortDirection(
            (_scenePortData(nodeId, portKey) || {}).direction,
            direction
        );
        var expectedNodeId = state.rewire ? state.origin_node_id : state.node_id;
        var expectedPortKey = state.rewire ? state.origin_port_key : state.port_key;
        var expectedDirection = state.rewire ? state.origin_direction : state.source_direction;
        if (expectedNodeId !== nodeId || expectedPortKey !== portKey || expectedDirection !== normalizedDirection) {
            root._clearWireDragState();
            return;
        }

        var movedEnoughAtRelease = Math.abs(Number(screenX) - Number(state.press_screen_x)) >= root.wireDragThreshold
            || Math.abs(Number(screenY) - Number(state.press_screen_y)) >= root.wireDragThreshold;
        var wasActive = Boolean(state.active) || Boolean(dragActive) || movedEnoughAtRelease;
        if (!wasActive) {
            root.wireDragState = null;
            root.wireDropCandidate = null;
            return;
        }

        var finalState = {
            "node_id": state.node_id,
            "port_key": state.port_key,
            "source_direction": state.source_direction,
            "start_x": state.start_x,
            "start_y": state.start_y,
            "cursor_x": root.canvasItem.screenToSceneX(screenX),
            "cursor_y": root.canvasItem.screenToSceneY(screenY),
            "press_screen_x": state.press_screen_x,
            "press_screen_y": state.press_screen_y,
            "active": true,
            "append_requested": state.rewire
                ? Boolean(state.append_requested)
                : root._appendRequested(modifiers),
            "rewire": Boolean(state.rewire),
            "copy_requested": Boolean(state.copy_requested)
        };
        if (state.rewire) {
            finalState.moving_edge_ids = state.moving_edge_ids || [];
            finalState.moving_edges = state.moving_edges || [];
            finalState.moving_endpoint = state.moving_endpoint;
            finalState.origin_node_id = state.origin_node_id;
            finalState.origin_port_key = state.origin_port_key;
            finalState.origin_direction = state.origin_direction;
        }
        if (state.origin_side !== undefined)
            finalState.origin_side = state.origin_side;
        _copyWireCompatibilitySnapshot(state, finalState);
        _activateWireCompatibilitySnapshot(finalState);
        root.wireDragState = finalState;
        root.clearPendingConnection();
        root._updateWireDropCandidate(screenX, screenY, finalState);
        if (!root.wireDropCandidate) {
            var widened = _nearestDropCandidateForWireDrag(
                Number(screenX),
                Number(screenY),
                _wireDragSourceData(finalState),
                28.0,
                false,
                finalState
            );
            if (widened) {
                root.wireDropCandidate = widened;
                root.hoveredPort = widened;
            }
        }

        var candidate = root.wireDropCandidate;
        if (finalState.rewire) {
            var originalSocket = candidate
                && String(candidate.node_id || "") === String(finalState.origin_node_id || "")
                && String(candidate.port_key || "") === String(finalState.origin_port_key || "");
            if (candidate && candidate.valid_drop && !originalSocket
                    && root.shellBridge && root.shellBridge.request_rewire_edges) {
                root.shellBridge.request_rewire_edges(
                    finalState.moving_edge_ids,
                    finalState.moving_endpoint,
                    candidate.node_id,
                    candidate.port_key,
                    finalState.copy_requested,
                    finalState.append_requested
                );
            } else if (!candidate && !finalState.copy_requested) {
                var nearbyPort = _nearestDropCandidateForWireDrag(
                    Number(screenX),
                    Number(screenY),
                    _wireDragSourceData(finalState),
                    28.0,
                    true,
                    finalState
                );
                if (!nearbyPort && root.shellBridge && root.shellBridge.request_rewire_edges) {
                    root.shellBridge.request_rewire_edges(
                        finalState.moving_edge_ids,
                        finalState.moving_endpoint,
                        "",
                        "",
                        false,
                        false
                    );
                }
            }
            root._clearWireDragState();
            return;
        }
        if (candidate && candidate.valid_drop && root.shellBridge && root.shellBridge.request_connect_ports) {
            root.shellBridge.request_connect_ports(
                finalState.node_id,
                finalState.port_key,
                candidate.node_id,
                candidate.port_key,
                finalState.append_requested
            );
        } else if (root.shellBridge && root.shellBridge.request_open_connection_quick_insert) {
            var overlayPoint = root.canvasItem.mapToItem(
                root.canvasItem.overlayHostItem ? root.canvasItem.overlayHostItem : root.canvasItem,
                Number(screenX),
                Number(screenY)
            );
            root.shellBridge.request_open_connection_quick_insert(
                finalState.node_id,
                finalState.port_key,
                finalState.cursor_x,
                finalState.cursor_y,
                overlayPoint.x,
                overlayPoint.y,
                finalState.append_requested
            );
        }
        root._clearWireDragState();
    }

    function cancelWireDrag() {
        if (!root.wireDragState)
            return false;
        root._clearWireDragState();
        return true;
    }

    function handlePortClick(nodeId, portKey, direction, sceneX, sceneY, modifiers) {
        if (!root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        root._closeContextMenus();
        var clicked = _authoringPortPayload(nodeId, portKey, direction, sceneX, sceneY);

        if (!root.pendingConnectionPort) {
            root.pendingConnectionPort = clicked;
            root.hoveredPort = clicked;
            _requestEdgeRedraw();
            return;
        }

        var pending = root.pendingConnectionPort;
        if (_samePort(pending, clicked)) {
            root.pendingConnectionPort = null;
            root.hoveredPort = null;
            _requestEdgeRedraw();
            return;
        }

        var neutralGesturePair = GraphCanvasLogic.isNeutralFlowPort(pending)
            && GraphCanvasLogic.isNeutralFlowPort(clicked);
        if (pending.direction === clicked.direction && !neutralGesturePair) {
            root.pendingConnectionPort = clicked;
            root.hoveredPort = clicked;
            _requestEdgeRedraw();
            return;
        }

        var sourceDrag = {
            "node_id": pending.node_id,
            "port_key": pending.port_key,
            "source_direction": pending.direction,
            "kind": String(pending.kind || ""),
            "data_type": String(pending.data_type || ""),
            "allow_multiple_connections": Boolean(pending.allow_multiple_connections),
            "start_x": pending.scene_x,
            "start_y": pending.scene_y,
            "cursor_x": sceneX,
            "cursor_y": sceneY
        };
        if (pending.side !== undefined)
            sourceDrag.side = pending.side;
        if (pending.origin_side !== undefined)
            sourceDrag.origin_side = pending.origin_side;
        clicked.valid_drop = _isDropAllowed(sourceDrag, clicked);
        if (clicked.valid_drop && root.shellBridge && root.shellBridge.request_connect_ports) {
            var created = root.shellBridge.request_connect_ports(
                pending.node_id,
                pending.port_key,
                clicked.node_id,
                clicked.port_key,
                root._appendRequested(modifiers)
            );
            if (created) {
                root.pendingConnectionPort = null;
                root.hoveredPort = null;
                _requestEdgeRedraw();
                return;
            }
        }

        root.hoveredPort = clicked;
        _requestEdgeRedraw();
    }

    function _closeContextMenus() {
        root.edgeContextVisible = false;
        root.nodeContextVisible = false;
        root.selectionContextVisible = false;
        root.canvasOptionsVisible = false;
        root.edgeContextEdgeId = "";
        root.nodeContextNodeId = "";
        root.contextMenuSceneAnchorActive = false;
        root.selectionContextSceneAnchorActive = false;
    }

    function _finiteCoordinate(value) {
        var numberValue = Number(value);
        return isFinite(numberValue) ? numberValue : 0.0;
    }

    function _setContextMenuPosition(x, y) {
        root.contextMenuX = root._finiteCoordinate(x);
        root.contextMenuY = root._finiteCoordinate(y);
    }

    function _setContextMenuSceneAnchor(sceneX, sceneY) {
        root.contextMenuSceneAnchorX = root._finiteCoordinate(sceneX);
        root.contextMenuSceneAnchorY = root._finiteCoordinate(sceneY);
        root.contextMenuSceneAnchorActive = true;
        if (root.canvasItem) {
            root.contextMenuX = root.canvasItem.sceneToScreenX(root.contextMenuSceneAnchorX);
            root.contextMenuY = root.canvasItem.sceneToScreenY(root.contextMenuSceneAnchorY);
        }
    }

    function _setContextMenuSceneAnchorFromScreen(screenX, screenY) {
        root._setContextMenuPosition(screenX, screenY);
        if (!root.canvasItem)
            return;
        root.contextMenuSceneAnchorX = root.canvasItem.screenToSceneX(root.contextMenuX);
        root.contextMenuSceneAnchorY = root.canvasItem.screenToSceneY(root.contextMenuY);
        root.contextMenuSceneAnchorActive = true;
    }

    function _openEdgeContext(edgeId, x, y) {
        if (!edgeId || !root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        var menuHeight = 267;
        var position = root.canvasItem._clampMenuPosition(x, y, 206, menuHeight);
        root._closeContextMenus();
        root.edgeContextEdgeId = edgeId;
        root._setContextMenuSceneAnchorFromScreen(position.x, position.y);
        root.edgeContextVisible = true;
    }

    function _activeCommentPeekNodeId() {
        if (!root.shellBridge || !root.shellBridge.active_comment_peek_node_id)
            return "";
        return String(root.shellBridge.active_comment_peek_node_id() || "").trim();
    }

    function _nodeCanPeekInside(nodeId) {
        var normalized = String(nodeId || "").trim();
        if (!normalized || !root.canvasItem || root._activeCommentPeekNodeId() === normalized)
            return false;
        var payload = root.canvasItem._sceneNodePayload(normalized);
        if (
            !payload
            || String(payload.surface_family || "").trim() !== "group_backdrop"
            || !Boolean(payload.collapsed)
        )
            return false;
        if (root.shellBridge && root.shellBridge.can_open_comment_peek)
            return Boolean(root.shellBridge.can_open_comment_peek(normalized));
        return true;
    }

    function _nodeContextMenuHeight(nodeId) {
        var rowCount = 4; // Add link, add comment, rename, and remove are available on editable nodes.
        if (root.canvasItem._nodeCanEnterScope(nodeId))
            rowCount += 3;
        if (root.canvasItem._nodeSupportsPassiveStyle(nodeId))
            rowCount += 5;
        if (root._nodeCanPeekInside(nodeId))
            rowCount += 1;
        if (root._activeCommentPeekNodeId() === String(nodeId || "").trim())
            rowCount += 1;
        return 20 + (rowCount * 30) + Math.max(0, rowCount - 1);
    }

    function _selectionContextMenuHeight() {
        var rowCount = 8;
        return 20 + (rowCount * 30) + Math.max(0, rowCount - 1);
    }

    function _openNodeContext(nodeId, x, y) {
        if (!nodeId || !root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        var menuHeight = root._nodeContextMenuHeight(nodeId);
        var position = root.canvasItem._clampMenuPosition(x, y, 206, menuHeight);
        root._closeContextMenus();
        root.nodeContextNodeId = nodeId;
        root._setContextMenuSceneAnchorFromScreen(position.x, position.y);
        root.nodeContextVisible = true;
    }

    function _openSelectionContext(x, y) {
        if (!root.canvasItem)
            return;
        var selectedNodeIds = root.canvasItem.selectedNodeIds ? root.canvasItem.selectedNodeIds() : [];
        if (selectedNodeIds.length < 2)
            return;
        root.canvasItem.forceActiveFocus();
        var position = root.canvasItem._clampMenuPosition(
            x,
            y,
            242,
            root._selectionContextMenuHeight()
        );
        root._closeContextMenus();
        root._setContextMenuSceneAnchorFromScreen(position.x, position.y);
        root.selectionContextVisible = true;
    }

    function _openSelectionContextAtScene(sceneX, sceneY) {
        if (!root.canvasItem)
            return;
        var selectedNodeIds = root.canvasItem.selectedNodeIds ? root.canvasItem.selectedNodeIds() : [];
        if (selectedNodeIds.length < 2)
            return;
        root.canvasItem.forceActiveFocus();
        var anchorX = Number(sceneX);
        var anchorY = Number(sceneY);
        if (!isFinite(anchorX))
            anchorX = 0.0;
        if (!isFinite(anchorY))
            anchorY = 0.0;
        root._closeContextMenus();
        root._setContextMenuSceneAnchor(anchorX, anchorY);
        root.selectionContextSceneAnchorX = anchorX;
        root.selectionContextSceneAnchorY = anchorY;
        root.selectionContextSceneAnchorActive = true;
        root.selectionContextVisible = true;
    }

    function _openCanvasOptions(x, y) {
        if (!root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        var menuHeight = (root.canvasItem.selectedEdgeIds || []).length > 0 ? 411 : 358;
        var position = root.canvasItem._clampMenuPosition(x, y, 252, menuHeight);
        root._closeContextMenus();
        root._setContextMenuPosition(position.x, position.y);
        root.canvasOptionsVisible = true;
    }

    function _openCanvasOptionsAtScene(sceneX, sceneY) {
        if (!root.canvasItem)
            return;
        root.canvasItem.forceActiveFocus();
        var menuHeight = (root.canvasItem.selectedEdgeIds || []).length > 0 ? 411 : 358;
        var position = root.canvasItem._clampMenuPosition(
            root.canvasItem.sceneToScreenX(root._finiteCoordinate(sceneX)),
            root.canvasItem.sceneToScreenY(root._finiteCoordinate(sceneY)),
            252,
            menuHeight
        );
        root._closeContextMenus();
        root._setContextMenuSceneAnchorFromScreen(position.x, position.y);
        root.canvasOptionsVisible = true;
    }

    function beginViewportInteraction() {
        root.viewportInteractionHeld = true;
        if (!root.interactionActive)
            root.interactionActive = true;
        if (root.interactionIdleTimer)
            root.interactionIdleTimer.stop();
    }

    function finishViewportInteractionSoon() {
        root.viewportInteractionHeld = false;
        if (!root.interactionActive) {
            if (root.interactionIdleTimer)
                root.interactionIdleTimer.stop();
            return;
        }
        if (root.interactionIdleTimer)
            root.interactionIdleTimer.restart();
    }

    function noteViewportInteraction() {
        if (!root.interactionActive)
            root.interactionActive = true;
        if (root.interactionIdleTimer) {
            if (root.viewportInteractionHeld)
                root.interactionIdleTimer.stop();
            else
                root.interactionIdleTimer.restart();
        }
    }

    function endViewportInteraction() {
        root.viewportInteractionHeld = false;
        if (root.interactionIdleTimer)
            root.interactionIdleTimer.stop();
        root.interactionActive = false;
    }

    function resetSceneBridgeState() {
        root.viewportInteractionHeld = false;
        root.interactionActive = false;
        if (root.interactionIdleTimer)
            root.interactionIdleTimer.stop();
        root.pendingConnectionPort = null;
        root.hoveredPort = null;
        root.wireDragState = null;
        root.wireDropCandidate = null;
        root.wireInvalidDropCandidate = null;
        root.clearLibraryDropPreview();
    }

    function releaseHostReferences() {
        root.edgeLayerItem = null;
        root.canvasItem = null;
        root.shellBridge = null;
        root.sceneBridge = null;
        root.interactionIdleTimer = null;
    }
}
